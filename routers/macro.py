"""
routers/macro.py — Macro indicator strip for Home + Regimes pages.

AUDIT-2026-05-06 (Everything-Live sprint, item 1): pre-fix, both Home
MacroStrip (5 items) and Regimes MacroOverlay (6 items) rendered
hardcoded literals — BTC Dom 58.9%, F&G 72, DXY 104.21, VIX 14.2, etc.
The values were string literals in web/app/page.tsx + web/app/regimes/
page.tsx, never refreshed regardless of actual market state.

This endpoint composes existing data_feeds helpers into a single
macro payload:
  - btc_dominance     ← get_global_market()        (CoinGecko free)
  - fear_greed        ← get_fear_greed()           (alternative.me free)
  - dxy / vix / 10y   ← get_macro_enrichment()     (yfinance + FRED)
  - btc_funding       ← get_funding_rate('BTC/USDT')
  - hy_spreads        ← FRED BAMLH0A0HYM2          (free CSV, no key)
  - macro_signal      ← get_macro_enrichment().macro_signal
                        (RISK_ON | MILD_RISK_ON | NEUTRAL | RISK_OFF)

5-min cache via the upstream helpers' own caches; this endpoint adds
no extra layer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

import data_feeds

from .deps import require_api_key
from .utils import serialize

logger = logging.getLogger(__name__)

router = APIRouter()


# ── HY spreads (FRED BAMLH0A0HYM2, free, no API key needed) ────────────────────
# Direct CSV pull — same pattern as fetch_fred_macro() but the series
# isn't in _FRED_MACRO_SERIES_SG so we fetch ad-hoc here.

_HY_CACHE: dict[str, Any] = {"value": None, "ts": 0.0}
_HY_TTL = 3600  # 1 hour


def _fetch_hy_spreads() -> float | None:
    """ICE BofA US High Yield Index Option-Adjusted Spread, in basis points.
    Returns None on failure. Cached 1h."""
    import time
    now = time.time()
    if _HY_CACHE["value"] is not None and now - _HY_CACHE["ts"] < _HY_TTL:
        return _HY_CACHE["value"]
    try:
        import requests
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            return None
        for line in reversed(resp.text.strip().split("\n")[1:]):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in (".", ""):
                try:
                    pct = float(parts[1].strip())
                    bps = round(pct * 100.0, 0)  # FRED reports as % — convert to bps
                    _HY_CACHE["value"] = bps
                    _HY_CACHE["ts"] = now
                    return bps
                except ValueError:
                    continue
    except Exception as exc:
        logger.debug("[macro] HY spreads fetch failed: %s", exc)
    return None


@router.get(
    "/strip",
    summary="Macro indicator strip (BTC dom + F&G + DXY + VIX + 10Y + HY + funding + regime)",
    dependencies=[Depends(require_api_key)],
)
def get_macro_strip() -> dict[str, Any]:
    """Returns the macro indicator payload powering Home MacroStrip + Regimes MacroOverlay.

    Each indicator includes the raw value, a human-readable sub-label,
    and (where applicable) a 7d / 30d delta. Frontend picks fields per page.

    Fail-open: any individual fetcher returning None doesn't fail the whole
    response — that field surfaces with `value: null` so the front-end
    renders a truthful "—" empty-state instead of a stack trace.
    """
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # BTC dominance (CoinGecko free)
    try:
        gm = data_feeds.get_global_market() or {}
        payload["btc_dominance"] = {
            "value": gm.get("btc_dominance"),
            "alt_season_label": gm.get("altcoin_season_label"),
            "source": gm.get("source"),
        }
    except Exception as exc:
        logger.warning("[macro] get_global_market failed: %s", exc)
        payload["btc_dominance"] = {"value": None, "source": "unavailable"}

    # Fear & Greed (alternative.me free)
    try:
        fg = data_feeds.get_fear_greed() or {}
        payload["fear_greed"] = {
            "value": fg.get("value"),
            "label": fg.get("label"),
            "bias": fg.get("bias"),
            "signal": fg.get("signal"),
        }
    except Exception as exc:
        logger.warning("[macro] get_fear_greed failed: %s", exc)
        payload["fear_greed"] = {"value": None, "label": None}

    # Macro enrichment (DXY, VIX, 10Y, yield curve, macro signal)
    try:
        me = data_feeds.get_macro_enrichment() or {}
        payload["dxy"] = {
            "value": me.get("dxy"),
            "trend": me.get("dxy_trend"),
        }
        payload["vix"] = {
            "value": me.get("vix"),
            "vix3m": me.get("vix3m"),
            "structure": me.get("vix_structure"),
        }
        payload["ten_yr_yield"] = {
            "value": me.get("yield_spread_pp"),  # for 2Y10Y spread
            "raw_10y": me.get("ten_yr"),
        }
        payload["yield_curve"] = me.get("yield_curve")
        payload["macro_signal"] = {
            "label": me.get("macro_signal"),
            "score": me.get("macro_score"),
        }
    except Exception as exc:
        logger.warning("[macro] get_macro_enrichment failed: %s", exc)
        payload["dxy"] = {"value": None}
        payload["vix"] = {"value": None}
        payload["ten_yr_yield"] = {"value": None}
        payload["yield_curve"] = None
        payload["macro_signal"] = {"label": None, "score": None}

    # 10Y treasury yield raw — re-pull from fred_macro for clarity
    try:
        fred = data_feeds.fetch_fred_macro() or {}
        payload["ten_yr_yield"]["raw"] = fred.get("ten_yr_yield")
        payload["two_yr_yield"] = {"value": fred.get("two_yr_yield")}
        payload["m2_yoy"] = fred.get("m2_yoy")
    except Exception as exc:
        logger.debug("[macro] fetch_fred_macro failed: %s", exc)

    # BTC funding rate (8h) — Bybit primary
    try:
        fund = data_feeds.get_funding_rate("BTC/USDT") or {}
        payload["btc_funding"] = {
            "value": fund.get("funding_rate_pct"),
            "signal": fund.get("signal"),
            "source": fund.get("source"),
        }
    except Exception as exc:
        logger.warning("[macro] get_funding_rate failed: %s", exc)
        payload["btc_funding"] = {"value": None}

    # HY spreads (FRED BAMLH0A0HYM2)
    payload["hy_spreads"] = {"value": _fetch_hy_spreads()}

    return serialize(payload)
