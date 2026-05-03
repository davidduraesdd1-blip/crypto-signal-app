"""
routers/onchain.py — Layer 4 on-chain metric endpoints.

Wraps `crypto_model_core.fetch_onchain_metrics` — the existing
fallback-chain helper that returns SOPR / MVRV-Z / net flow / whale
activity with documented graceful-degradation defaults.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

import crypto_model_core as model

from .deps import require_api_key
from .utils import normalize_pair, serialize

logger = logging.getLogger(__name__)

router = APIRouter()


_KNOWN_METRICS = {"sopr", "mvrv_z", "net_flow", "whale_activity"}


def _safe_fetch(pair: str) -> dict[str, Any]:
    """Fetch on-chain metrics for `pair` with truthful empty-state semantics.

    AUDIT-2026-05-02 (MEDIUM error-handling fix): the previous fallback
    returned hard-coded `sopr=1.0, mvrv_z=0.0, net_flow=0.0` — values that
    read as a real "neutral" signal. The frontend cannot distinguish
    "metric is genuinely neutral" from "API totally down" without
    inspecting the source string, and SOPR=1.0 / MVRV-Z=0 happens to
    be the literal "everything is fine" reading. For a Layer-4 input
    that can flip a BUY to SELL, fail-open with neutral values is wrong.

    Per `feedback_empty_states` memory: return explicit `None` for every
    metric and surface the failure in `source` + `error` so the page can
    render the "rate-limited / geo-blocked / unavailable" empty-state pill.
    """
    try:
        return model.fetch_onchain_metrics(pair) or {}
    except Exception as exc:
        logger.warning("[onchain] fetch_onchain_metrics(%s) failed: %s", pair, exc)
        return {
            "sopr": None, "mvrv_z": None, "net_flow": None,
            "whale_activity": None,
            "source": "unavailable",
            "error": "On-chain data temporarily unavailable — using cached values where possible",
        }


@router.get(
    "/dashboard",
    summary="Aggregate on-chain dashboard for a pair",
    dependencies=[Depends(require_api_key)],
)
def get_onchain_dashboard(pair: str = Query(default="BTC/USDT")):
    """Returns the full on-chain payload for `pair` (defaults to BTC/USDT).

    Drives the On-Chain page's 3-card grid. Source is recorded in the
    payload so the frontend can render a "live" / "fallback" status pill.
    """
    try:
        normalized = normalize_pair(pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return serialize({"pair": normalized, **_safe_fetch(normalized)})


@router.get(
    "/{metric}",
    summary="Single on-chain metric for a pair",
    dependencies=[Depends(require_api_key)],
)
def get_onchain_metric(metric: str, pair: str = Query(default="BTC/USDT")):
    """Returns a single named on-chain metric for `pair`.

    Known metrics: sopr, mvrv_z, net_flow, whale_activity. Unknown
    metric names return 404 to keep the contract tight.
    """
    metric_key = metric.lower().strip()
    if metric_key not in _KNOWN_METRICS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown on-chain metric: {metric!r}. Known: {sorted(_KNOWN_METRICS)}",
        )
    try:
        normalized = normalize_pair(pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    payload = _safe_fetch(normalized)
    return serialize({
        "pair":   normalized,
        "metric": metric_key,
        "value":  payload.get(metric_key),
        "source": payload.get("source", "unknown"),
    })
