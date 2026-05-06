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

POST-LAUNCH FIX (2026-05-06 — also Everything-Live, screenshot review):
yfinance + FRED can block 30+ seconds on Render cold-start, leaving the
frontend stuck on "loading" indefinitely. Each fetcher now runs inside
a 6-second-bounded ThreadPoolExecutor; on timeout the field surfaces as
null with `error: "timeout"` so the UI renders an honest "—" instead of
hanging. Subsequent calls hit the upstream helpers' own caches and
return fast.
"""

from __future__ import annotations

import concurrent.futures
import logging
from datetime import datetime, timezone
from typing import Any, Callable

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


_ENDPOINT_DEADLINE_S = 7   # whole-endpoint hard ceiling (was per-fetcher)
_PER_FETCHER_TIMEOUT_S = 7  # alias for compat with prior reads / docs

# Module-level executor so timed-out fetchers continue running in
# background, populating their upstream caches for the next call.
# A `with ThreadPoolExecutor` block was blocking the endpoint on exit
# (shutdown(wait=True) waits for all submitted threads), defeating the
# whole point of a per-fetcher timeout.
_MACRO_EXEC = concurrent.futures.ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="macro-fetch",
)


@router.get(
    "/strip",
    summary="Macro indicator strip (BTC dom + F&G + DXY + VIX + 10Y + HY + funding + regime)",
    dependencies=[Depends(require_api_key)],
)
def get_macro_strip() -> dict[str, Any]:
    """Returns the macro indicator payload powering Home MacroStrip + Regimes MacroOverlay.

    All 6 upstream fetchers run in parallel on a module-level
    ThreadPoolExecutor. The whole endpoint is bounded by a single
    ~7-second deadline (`_ENDPOINT_DEADLINE_S`), so a slow fetcher
    can't stall past that ceiling. In-flight fetchers that miss the
    deadline keep running in background and warm their upstream
    caches for the next call (5-60min TTLs upstream).

    Frontend sees `value: null` for any field whose fetcher missed
    the deadline — renders a truthful "—" empty-state. The next
    call hits the populated cache and returns the live value.
    """
    import time as _time
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    futures = {
        "gm":   _MACRO_EXEC.submit(data_feeds.get_global_market),
        "fg":   _MACRO_EXEC.submit(data_feeds.get_fear_greed),
        "me":   _MACRO_EXEC.submit(data_feeds.get_macro_enrichment),
        "fred": _MACRO_EXEC.submit(data_feeds.fetch_fred_macro),
        "fund": _MACRO_EXEC.submit(data_feeds.get_funding_rate, "BTC/USDT"),
        "hy":   _MACRO_EXEC.submit(_fetch_hy_spreads),
    }

    deadline = _time.time() + _ENDPOINT_DEADLINE_S
    results: dict[str, Any] = {}
    for label, fut in futures.items():
        remaining = max(0.05, deadline - _time.time())
        default = None if label == "hy" else {}
        try:
            value = fut.result(timeout=remaining)
            results[label] = value if value is not None else default
        except concurrent.futures.TimeoutError:
            logger.warning(
                "[macro] %s missed shared deadline (remaining=%.2fs)", label, remaining
            )
            results[label] = default
        except Exception as exc:
            logger.warning("[macro] %s failed: %s", label, exc)
            results[label] = default

    gm, fg, me, fred, fund, hy = (
        results["gm"], results["fg"], results["me"],
        results["fred"], results["fund"], results["hy"],
    )

    payload["btc_dominance"] = {
        "value": gm.get("btc_dominance"),
        "alt_season_label": gm.get("altcoin_season_label"),
        "source": gm.get("source") or "unavailable",
    }
    payload["fear_greed"] = {
        "value": fg.get("value"),
        "label": fg.get("label"),
        "bias": fg.get("bias"),
        "signal": fg.get("signal"),
    }
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
        "value": me.get("yield_spread_pp"),  # 2Y10Y spread
        "raw":   fred.get("ten_yr_yield"),
        "raw_10y": me.get("ten_yr"),
    }
    payload["two_yr_yield"] = {"value": fred.get("two_yr_yield")}
    payload["m2_yoy"] = fred.get("m2_yoy")
    payload["yield_curve"] = me.get("yield_curve")
    payload["macro_signal"] = {
        "label": me.get("macro_signal"),
        "score": me.get("macro_score"),
    }
    payload["btc_funding"] = {
        "value":  fund.get("funding_rate_pct"),
        "signal": fund.get("signal"),
        "source": fund.get("source"),
    }
    payload["hy_spreads"] = {"value": hy}

    return serialize(payload)
