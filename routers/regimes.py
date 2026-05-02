"""
routers/regimes.py — HMM regime state endpoints for the Regimes page.

Reads pre-computed regime state from the scan_results cache (current
state) and the regime_history table (history + transitions). The
expensive HMM computation runs inside the scanner; routes here are
read-only and fast.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

import database as db

from .deps import require_api_key
from .utils import normalize_pair, serialize

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_regime(result: dict) -> str | None:
    return result.get("regime") or result.get("regime_label")


@router.get(
    "/",
    summary="Current regime state across the universe",
    dependencies=[Depends(require_api_key)],
)
def list_regimes():
    """Return the current regime state for every pair in the latest scan."""
    try:
        results = db.read_scan_results() or []
    except Exception as exc:
        logger.warning("[regimes] scan results unavailable: %s", exc)
        results = []

    rows: list[dict[str, Any]] = []
    summary = {"Trending": 0, "Ranging": 0, "Neutral": 0, "Unknown": 0}
    for r in results:
        pair = r.get("pair")
        if not pair:
            continue
        state = _extract_regime(r) or "Unknown"
        bucket = state if state in summary else "Unknown"
        summary[bucket] += 1
        rows.append({
            "pair":       pair,
            "regime":     state,
            "direction":  r.get("direction"),
            "confidence": r.get("confidence_avg_pct"),
        })

    return serialize({"count": len(rows), "summary": summary, "results": rows})


@router.get(
    "/{pair}/history",
    summary="Historical regime segments for one pair",
    dependencies=[Depends(require_api_key)],
)
def get_regime_history(pair: str, days: int = Query(default=90, ge=1, le=365)):
    """Return contiguous regime segments over the last `days` for `pair`.

    Each segment is `(state, duration_pct)` per regime_state_bar widget
    contract from Phase C8. Empty list when no history is recorded yet.
    """
    try:
        normalized = normalize_pair(pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        segments = db.regime_history_segments(normalized, days=days) or []
    except Exception as exc:
        logger.warning("[regimes] history fetch failed for %s: %s", normalized, exc)
        segments = []

    return serialize({
        "pair":     normalized,
        "days":     days,
        "count":    len(segments),
        "segments": [{"state": s, "pct": p} for s, p in segments],
    })


@router.get(
    "/transitions",
    summary="Recent regime transitions across the universe",
    dependencies=[Depends(require_api_key)],
)
def get_regime_transitions(days: int = Query(default=30, ge=1, le=180), limit: int = Query(default=200, ge=1, le=1000)):
    """Return regime change events across the universe over the last `days`.

    Iterates `regime_history_segments` per pair and emits one row per
    state-change boundary (consecutive segments with different states).
    """
    try:
        results = db.read_scan_results() or []
    except Exception as exc:
        logger.warning("[regimes] scan results unavailable: %s", exc)
        results = []

    transitions: list[dict[str, Any]] = []
    for r in results:
        pair = r.get("pair")
        if not pair:
            continue
        try:
            segs = db.regime_history_segments(pair, days=days) or []
        except Exception as exc:
            logger.debug("[regimes] segment fetch failed for %s: %s", pair, exc)
            continue
        prev_state: str | None = None
        for state, pct in segs:
            if prev_state is not None and state != prev_state:
                transitions.append({
                    "pair":       pair,
                    "from":       prev_state,
                    "to":         state,
                    "segment_pct": pct,
                })
                if len(transitions) >= limit:
                    break
            prev_state = state
        if len(transitions) >= limit:
            break

    return serialize({
        "count":       len(transitions),
        "days":        days,
        "transitions": transitions,
    })
