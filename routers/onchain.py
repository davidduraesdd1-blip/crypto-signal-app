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
    "/whale-events",
    summary="Recent whale activity events derived from per-pair net flow",
    dependencies=[Depends(require_api_key)],
)
def get_whale_events(min_usd: float = Query(default=10_000_000.0, ge=0.0)):
    """Return whale-class flow events derived from /onchain/dashboard
    net_flow + spot price for the on-chain-covered pairs.

    AUDIT-2026-05-06 (Everything-Live, item 10): pre-fix the Whale
    Activity table rendered 8 hardcoded events with fake amounts ($184.2M
    Coinbase Pro → cold storage, $94.6M Unknown wallet → Binance, etc.) —
    real data was nowhere. The "live stream" claim was already dropped
    in W2 to "sample data (not in V1)". Now wired to actual on-chain
    aggregate net flow.

    Trade-off vs the prior mock: narrower coverage (only the 3 pairs
    Glassnode covers — BTC/ETH/XRP) and aggregated 7-day deltas instead
    of individual transactions. A paid Whale Alert API or Glassnode
    higher tier would unlock per-tx granularity; until then, aggregate
    flow is the truthful free-tier surface.

    Empty list when net_flow is null (rate-limited / unavailable).
    """
    from datetime import datetime, timezone
    import database as db

    pairs = ("BTC/USDT", "ETH/USDT", "XRP/USDT")
    events: list[dict] = []

    # Pull current prices from latest scan cache so we can $-convert net flow
    try:
        results = db.read_scan_results() or []
    except Exception:
        results = []
    by_pair = {r.get("pair"): r for r in results if r.get("pair")}

    for p in pairs:
        try:
            payload = model.fetch_onchain_metrics(p) or {}
        except Exception as exc:
            logger.debug("[onchain/whale] %s fetch failed: %s", p, exc)
            continue
        net_flow = payload.get("net_flow")
        if net_flow is None:
            continue

        # net_flow units: most providers report in coin units (not USD).
        # Convert via the most-recent scan price.
        scan = by_pair.get(p, {})
        price = scan.get("price") or scan.get("price_usd")
        try:
            price_f = float(price) if price is not None else None
            net_f = float(net_flow)
        except (ValueError, TypeError):
            continue
        if price_f is None:
            continue
        usd_value = abs(net_f * price_f)
        if usd_value < float(min_usd):
            continue

        ticker = p.split("/")[0]
        direction = "outflow" if net_f < 0 else "inflow"
        notes = (
            f"Aggregated 7-day exchange {direction} · derived from net flow"
            if payload.get("source") and payload.get("source") != "unavailable"
            else "Aggregated flow · {} (cached)".format(payload.get("source") or "unknown")
        )
        # Use the data-source timestamp if present, else now
        ts_raw = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
        try:
            ts_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            ts_str = ts_dt.strftime("%H:%M")
        except Exception:
            ts_str = datetime.now(timezone.utc).strftime("%H:%M")

        events.append({
            "time":      ts_str,
            "coin":      ticker,
            "direction": direction,
            "notes":     notes,
            "amount_usd": round(usd_value, 0),
            "amount_label": f"${usd_value/1_000_000:.1f}M" if usd_value >= 1_000_000 else f"${usd_value/1_000:.0f}K",
            "source":    payload.get("source") or "unknown",
        })

    # Sort newest-first by amount magnitude (proxy for "biggest events first")
    events.sort(key=lambda e: e["amount_usd"], reverse=True)

    return serialize({
        "count":  len(events),
        "events": events,
        "min_usd": float(min_usd),
        "note":   "Aggregated 7-day flow (free-tier on-chain) · per-tx granularity needs paid Whale Alert API",
    })


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
