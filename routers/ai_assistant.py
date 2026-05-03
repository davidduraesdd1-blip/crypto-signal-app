"""
routers/ai_assistant.py — AI Assistant page endpoints.

Wraps `llm_analysis.generate_signal_story` (claude-haiku-4-5) for
short plain-English narratives, and exposes recent signal direction
calls from the persistent signals_df as a "Recent Decisions" log.

LLM calls are sync inside `llm_analysis`; this router uses
`asyncio.to_thread` to keep the FastAPI event loop responsive while
the Anthropic call is in flight.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database as db
import llm_analysis

from .deps import require_api_key
from .utils import normalize_pair, serialize

logger = logging.getLogger(__name__)

router = APIRouter()


# AUDIT-2026-05-03 (LOW input validation): canonical signal vocabulary
# matches the engine's BUY/HOLD/SELL output rule (CLAUDE.md §9). Bad
# input fails fast at 422 instead of reaching the LLM call where it
# would be interpolated into the prompt verbatim.
_ALLOWED_SIGNALS = {"BUY", "SELL", "STRONG BUY", "STRONG SELL", "NEUTRAL", "HOLD"}


class AskRequest(BaseModel):
    pair:       str             = Field(..., min_length=3, max_length=32, description="Trading pair, e.g. BTC/USDT")
    signal:     str             = Field(..., description=f"Direction call (one of: {', '.join(sorted(_ALLOWED_SIGNALS))})")
    confidence: float           = Field(..., ge=0.0, le=100.0, description="Confidence pct, 0-100")
    indicators: dict[str, Any]  = Field(default_factory=dict, max_length=64, description="Indicator snapshot (rsi, macd, adx, ...)")
    question:   Optional[str]   = Field(default=None, max_length=2000, description="Optional free-text follow-up question")


@router.post(
    "/ask",
    summary="Generate a plain-English explanation for a signal",
    dependencies=[Depends(require_api_key)],
)
async def ask_ai(req: AskRequest):
    """Returns a 1-2 sentence plain-English narrative for the given signal.

    Falls back to the rule-based story when the Anthropic API key is
    not configured — caller cannot tell the difference at the response
    level, only via the `source` field.
    """
    try:
        normalized = normalize_pair(req.pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    signal_norm = req.signal.upper().strip()
    if signal_norm not in _ALLOWED_SIGNALS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown signal {req.signal!r}. Allowed: {sorted(_ALLOWED_SIGNALS)}",
        )

    try:
        text = await asyncio.to_thread(
            llm_analysis.generate_signal_story,
            normalized,
            signal_norm,
            float(req.confidence),
            req.indicators,
        )
    except Exception as exc:
        logger.warning("[ai] generate_signal_story failed: %s", exc)
        text = None

    if not text:
        return serialize({
            "pair":     normalized,
            "signal":   signal_norm,
            "text":     "",
            "source":   "unavailable",
        })

    return serialize({
        "pair":     normalized,
        "signal":   signal_norm,
        "text":     text,
        "source":   "llm_analysis.generate_signal_story",
    })


@router.get(
    "/decisions",
    summary="Recent signal direction calls (Recent Decisions log)",
    dependencies=[Depends(require_api_key)],
)
def list_recent_decisions(
    limit: int = Query(default=20, ge=1, le=200),
    pair:  Optional[str] = Query(default=None),
):
    """Return the most recent N signal direction calls from the persistent
    log. The Next.js Recent Decisions panel renders these as the AI's
    rolling history."""
    df = db.get_signals_df()
    if df is None or df.empty:
        return {"count": 0, "decisions": []}

    if pair:
        try:
            normalized = normalize_pair(pair)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        df = df[df["pair"] == normalized]

    df = df.tail(limit)
    return {"count": len(df), "decisions": serialize(df.to_dict(orient="records"))}
