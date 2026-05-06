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
    """Return the current regime state for every pair in the latest scan.

    AUDIT-2026-05-02 (MEDIUM bug fix): the previous summary used hardcoded
    bucket keys {"Trending", "Ranging", "Neutral", "Unknown"} that never
    matched the actual HMM state labels emitted by the engine
    (Bull/Bear/Sideways/Transition per CLAUDE.md §9). Every real regime
    landed in "Unknown" and the four real labels never incremented —
    the summary card on the Regimes page was structurally wrong.

    Now seeds the canonical HMM labels at zero (so the front-end always
    renders the four pills even when an early scan has produced no rows
    yet) AND increments dynamically for any other state string the
    engine emits, with anything missing falling into "Unknown".
    """
    try:
        results = db.read_scan_results() or []
    except Exception as exc:
        logger.warning("[regimes] scan results unavailable: %s", exc)
        results = []

    rows: list[dict[str, Any]] = []
    # Canonical HMM labels per CLAUDE.md §9; seeded so the four pills
    # always render. The legacy {Trending, Ranging, Neutral} set is kept
    # alongside as a back-compat shim for any test or frontend still
    # asserting on those keys — they always read 0 unless the engine
    # actually emits them.
    summary: dict[str, int] = {
        "Bull": 0, "Bear": 0, "Sideways": 0, "Transition": 0,
        "Trending": 0, "Ranging": 0, "Neutral": 0,
        "Unknown": 0,
    }
    for r in results:
        pair = r.get("pair")
        if not pair:
            continue
        state = _extract_regime(r) or "Unknown"
        # Increment the matching bucket, creating it on the fly if the
        # engine emits a state name we haven't seen before. Never silently
        # bucket a real state into "Unknown".
        summary[state] = summary.get(state, 0) + 1
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
    "/weights",
    summary="Regime-specific layer weights (CRISIS / TRENDING / RANGING / NORMAL)",
    dependencies=[Depends(require_api_key)],
)
def get_regime_weights() -> dict:
    """Return the per-regime layer-weight table from composite_signal.

    AUDIT-2026-05-06 (Everything-Live, item 3): pre-fix the Regimes page
    RegimeWeights component rendered hardcoded weights for 4 made-up
    labels (bull/accumulation/distribution/bear) that don't match the
    engine's actual regime taxonomy (CRISIS/TRENDING/RANGING/NORMAL per
    composite_signal.py:175). Now reads the live table — including the
    NORMAL row's Optuna-tuned weights from alerts_config.json.

    Read-only. composite_signal.py is §22-protected; we only call its
    public-style `_regime_weights()` helper which returns a fresh dict
    each call.
    """
    try:
        import composite_signal
        table = composite_signal._regime_weights() or {}
    except Exception as exc:
        logger.warning("[regimes] _regime_weights() failed: %s", exc)
        table = {}

    columns = []
    for regime_label in ("CRISIS", "TRENDING", "RANGING", "NORMAL"):
        weights = table.get(regime_label, {})
        columns.append({
            "regime": regime_label,
            "weights": {
                "technical": weights.get("technical"),
                "macro":     weights.get("macro"),
                "sentiment": weights.get("sentiment"),
                "onchain":   weights.get("onchain"),
            },
        })
    return serialize({"columns": columns})


@router.get(
    "/{pair}/timeline",
    summary="Date-stamped regime timeline for one pair",
    dependencies=[Depends(require_api_key)],
)
def get_regime_timeline(pair: str, days: int = Query(default=90, ge=1, le=365)):
    """Return date-stamped regime transitions for `pair` over the last `days`.

    AUDIT-2026-05-06 (Everything-Live, item 5): the existing /history
    endpoint returns aggregated `[(state, pct)]` segments without dates,
    which can't power "Bull since Apr 12" framing on the Regimes page.
    This endpoint reads regime_history with timestamps and emits a
    chronological list of `(state, start_iso, end_iso, duration_days)`
    rows so the frontend can render both the segmented timeline AND the
    "current state since X" caption.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta
    try:
        normalized = normalize_pair(pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    cutoff_iso = (_dt.now(_tz.utc) - timedelta(days=int(days))).isoformat()

    rows: list[tuple[str, str]] = []
    try:
        # Read regime_history directly so we get the timestamps.
        conn = db._get_conn()
        try:
            cur = conn.execute(
                """SELECT timestamp, state FROM regime_history
                     WHERE pair = ? AND timestamp >= ?
                     ORDER BY timestamp ASC""",
                (normalized, cutoff_iso),
            )
            rows = list(cur.fetchall())
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[regimes] timeline fetch failed for %s: %s", normalized, exc)
        rows = []

    if not rows:
        return serialize({
            "pair":           normalized,
            "days":           days,
            "current_state":  None,
            "since":          None,
            "duration_days":  0,
            "segments":       [],
        })

    # Collapse contiguous same-state runs.
    def _parse(ts: str) -> _dt:
        try:
            return _dt.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return _dt.now(_tz.utc)

    parsed: list[tuple[_dt, str]] = [(_parse(ts), state) for ts, state in rows]

    segments: list[dict] = []
    seg_start = parsed[0][0]
    seg_state = parsed[0][1]
    for i in range(1, len(parsed)):
        ts, state = parsed[i]
        if state != seg_state:
            duration = (ts - seg_start).total_seconds() / 86400.0
            segments.append({
                "state":         seg_state,
                "start":         seg_start.isoformat(),
                "end":           ts.isoformat(),
                "duration_days": round(duration, 2),
            })
            seg_start, seg_state = ts, state

    # Final open segment extends to now
    now = _dt.now(_tz.utc)
    final_duration = (now - seg_start).total_seconds() / 86400.0
    segments.append({
        "state":         seg_state,
        "start":         seg_start.isoformat(),
        "end":           now.isoformat(),
        "duration_days": round(final_duration, 2),
    })

    return serialize({
        "pair":          normalized,
        "days":          days,
        "current_state": seg_state,
        "since":         seg_start.isoformat(),
        "duration_days": round(final_duration, 2),
        "segments":      segments,
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
