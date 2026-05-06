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


# ── Direct FRED fetchers (free CSV, no API key) ────────────────────────────────
# Pattern: read the latest non-blank value from FRED's public graph CSV.
# Same pattern as fetch_fred_macro() but kept ad-hoc for series that
# aren't in _FRED_MACRO_SERIES_SG. Replaces yfinance for DXY+VIX which
# is unreliable on Render datacenter IPs (yfinance silently hangs).

import time as _time

_FRED_AD_HOC_CACHE: dict[str, dict[str, Any]] = {}
_FRED_AD_HOC_TTL = 3600  # 1 hour


def _fred_latest(series_id: str, scale: float = 1.0) -> float | None:
    """Fetch the latest non-empty value of a FRED series via free CSV.
    Returns None on any failure. Cached 1h per series.

    AUDIT-2026-05-06 (post-launch v3 fix): bumped timeout 5→12s and
    reuse `data_feeds._FRED_SESSION` (HTTPAdapter with retries +
    keep-alive) so larger series like DTWEXBGS / VIXCLS don't fail on
    cold connect from Render. The 5s timeout was tight for ~9000-row
    CSVs over Render's slow datacenter network. Also adds an explicit
    User-Agent because FRED has been observed to 403 the default
    python-requests/X.X UA from cloud IPs.
    """
    cached = _FRED_AD_HOC_CACHE.get(series_id)
    now = _time.time()
    if cached and now - cached["ts"] < _FRED_AD_HOC_TTL and cached["value"] is not None:
        return cached["value"]
    try:
        # AUDIT-2026-05-06 (post-launch v3.3): add &cosd=YYYY-MM-DD date
        # filter so FRED only sends the recent ~350 rows instead of the
        # full historical series (DTWEXBGS goes back to 2006, VIXCLS to
        # 1990 — those payloads were timing out from Render's IP). With
        # cosd=last-year, every series is ~6-7KB and downloads in < 1s.
        from datetime import datetime as _dt, timedelta as _td
        cosd = (_dt.utcnow() - _td(days=400)).strftime("%Y-%m-%d")
        url = (
            f"https://fred.stlouisfed.org/graph/fredgraph.csv"
            f"?id={series_id}&cosd={cosd}"
        )
        import requests as _req
        resp = _req.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; crypto-signal-app/1.0)",
                "Accept": "text/csv,*/*",
                "Accept-Encoding": "gzip",
            },
        )
        if resp.status_code != 200:
            logger.warning("[macro] FRED %s status=%s", series_id, resp.status_code)
            return None
        for line in reversed(resp.text.strip().split("\n")[1:]):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in (".", ""):
                try:
                    val = float(parts[1].strip()) * scale
                    _FRED_AD_HOC_CACHE[series_id] = {"value": val, "ts": now}
                    return val
                except ValueError:
                    continue
    except Exception as exc:
        logger.warning("[macro] FRED %s fetch failed: %s", series_id, exc)
    return None


def _fetch_hy_spreads() -> float | None:
    """ICE BofA US High Yield Index Option-Adjusted Spread, in basis points."""
    pct = _fred_latest("BAMLH0A0HYM2")
    return round(pct * 100.0, 0) if pct is not None else None  # % → bps


def _fetch_dxy_fred() -> float | None:
    """DXY proxy via FRED DTWEXBGS (Nominal Broad U.S. Dollar Index). Daily.
    Note: DTWEXBGS is normalized to a different basis than ICE's DXY but
    tracks the same dollar strength signal. We pass the raw value through;
    frontend renders it as DXY for continuity."""
    return _fred_latest("DTWEXBGS")


def _fetch_vix_fred() -> float | None:
    """VIX via FRED VIXCLS (CBOE Volatility Index, daily close)."""
    return _fred_latest("VIXCLS")


def _classify_macro_signal(dxy: float | None, vix: float | None,
                           ten_y: float | None, two_y: float | None,
                           hy_bps: float | None) -> tuple[str | None, int | None]:
    """Compute (label, score) on -4..+4 scale from macro inputs. Mirrors
    the scoring in data_feeds.get_macro_enrichment but uses FRED-only
    inputs so it never hangs on yfinance.

    Each input contributes ±1 to the score. Score → label:
      ≥ +3   RISK_ON
      +1..+2 MILD_RISK_ON
      -1..0  NEUTRAL
      -2     MILD_RISK_OFF
      ≤ -3   RISK_OFF
    """
    score = 0
    inputs_used = 0

    # DXY — strong dollar = headwind (-1), weak dollar = tailwind (+1)
    # DTWEXBGS recent baseline ~120; > 125 = strong, < 115 = weak.
    if dxy is not None:
        inputs_used += 1
        if dxy < 115.0:    score += 1
        elif dxy > 125.0:  score -= 1

    # VIX — calm = +1, stressed = -1
    if vix is not None:
        inputs_used += 1
        if vix < 18.0:     score += 1
        elif vix > 25.0:   score -= 1

    # Yield curve (10Y - 2Y): inverted = -2 (recession risk), normal = +1
    if ten_y is not None and two_y is not None:
        inputs_used += 1
        spread = ten_y - two_y
        if spread > 0.25:    score += 1
        elif spread < -0.25: score -= 2

    # HY spreads: tight = +1, wide = -1
    if hy_bps is not None:
        inputs_used += 1
        if hy_bps < 350.0:    score += 1
        elif hy_bps > 500.0:  score -= 1

    if inputs_used == 0:
        return None, None
    if score >= 3:    return "RISK_ON", score
    if score >= 1:    return "MILD_RISK_ON", score
    if score <= -3:   return "RISK_OFF", score
    if score <= -2:   return "MILD_RISK_OFF", score
    return "NEUTRAL", score


_ENDPOINT_DEADLINE_S = 14   # whole-endpoint hard ceiling
_PER_FETCHER_TIMEOUT_S = 14  # alias for compat with prior reads / docs

# AUDIT-2026-05-06 (post-launch v3 fix): bumped 7→11s after observing on
# Render that DTWEXBGS + VIXCLS CSVs (large historical series, 5000-9000
# rows) take 8-10s to download cold. The 7s deadline was killing them
# before they could populate the cache. Subsequent calls hit the 1h
# cache and return in <100ms.

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

    # AUDIT-2026-05-06 (post-launch v3): yfinance is unreliable on Render
    # datacenter IPs (silently hangs on first call, never populates cache).
    # Drop dependency on get_macro_enrichment — fetch DXY + VIX directly
    # from FRED (DTWEXBGS + VIXCLS, free CSV, fast, no key). Macro signal
    # is computed locally from FRED-only inputs in _classify_macro_signal.
    futures = {
        "gm":   _MACRO_EXEC.submit(data_feeds.get_global_market),
        "fg":   _MACRO_EXEC.submit(data_feeds.get_fear_greed),
        "fred": _MACRO_EXEC.submit(data_feeds.fetch_fred_macro),
        "fund": _MACRO_EXEC.submit(data_feeds.get_funding_rate, "BTC/USDT"),
        "hy":   _MACRO_EXEC.submit(_fetch_hy_spreads),
        "dxy":  _MACRO_EXEC.submit(_fetch_dxy_fred),
        "vix":  _MACRO_EXEC.submit(_fetch_vix_fred),
    }

    deadline = _time.time() + _ENDPOINT_DEADLINE_S
    results: dict[str, Any] = {}
    for label, fut in futures.items():
        remaining = max(0.05, deadline - _time.time())
        # `dxy`/`vix`/`hy` return float (or None), the rest return dict.
        default = None if label in ("hy", "dxy", "vix") else {}
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

    gm   = results["gm"]
    fg   = results["fg"]
    fred = results["fred"]
    fund = results["fund"]
    hy   = results["hy"]
    dxy_val = results["dxy"]
    vix_val = results["vix"]

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
    # DXY trend: < 115 weak (tailwind), > 125 strong (headwind), else neutral.
    # Note: DTWEXBGS uses a different baseline than ICE's DXY (~120 vs ~104).
    dxy_trend = None
    if dxy_val is not None:
        if dxy_val > 125.0:
            dxy_trend = "STRONG_DOLLAR"
        elif dxy_val < 115.0:
            dxy_trend = "WEAK_DOLLAR"
        else:
            dxy_trend = "NEUTRAL"
    payload["dxy"] = {
        "value": round(dxy_val, 2) if dxy_val is not None else None,
        "trend": dxy_trend,
        "source": "FRED:DTWEXBGS" if dxy_val is not None else "unavailable",
    }

    # VIX structure: < 18 calm, > 25 stressed.
    vix_structure = None
    if vix_val is not None:
        if vix_val < 18.0:
            vix_structure = "CALM"
        elif vix_val > 25.0:
            vix_structure = "STRESSED"
        else:
            vix_structure = "NEUTRAL"
    payload["vix"] = {
        "value": round(vix_val, 2) if vix_val is not None else None,
        "vix3m": None,
        "structure": vix_structure,
        "source": "FRED:VIXCLS" if vix_val is not None else "unavailable",
    }

    # Yield curve from FRED 10Y - 2Y
    ten_y = fred.get("ten_yr_yield")
    two_y = fred.get("two_yr_yield")
    spread = (ten_y - two_y) if ten_y is not None and two_y is not None else None
    yield_curve = None
    if spread is not None:
        if spread > 0.25:
            yield_curve = "NORMAL"
        elif spread < -0.25:
            yield_curve = "INVERTED"
        else:
            yield_curve = "FLAT"

    payload["ten_yr_yield"] = {
        "value": round(spread, 3) if spread is not None else None,  # 2Y10Y spread
        "raw":   ten_y,
        "raw_10y": ten_y,
    }
    payload["two_yr_yield"] = {"value": two_y}
    payload["m2_yoy"] = fred.get("m2_yoy")
    payload["yield_curve"] = yield_curve

    # Macro signal computed locally from FRED-only inputs
    sig_label, sig_score = _classify_macro_signal(
        dxy=dxy_val, vix=vix_val, ten_y=ten_y, two_y=two_y, hy_bps=hy
    )
    payload["macro_signal"] = {"label": sig_label, "score": sig_score}
    payload["btc_funding"] = {
        "value":  fund.get("funding_rate_pct"),
        "signal": fund.get("signal"),
        "source": fund.get("source"),
    }
    payload["hy_spreads"] = {"value": hy}

    return serialize(payload)
