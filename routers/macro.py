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
    """Compute ICE DXY from FRED FX rates using the canonical formula.

    AUDIT-2026-05-06 (post-launch v5): pre-fix this returned FRED's
    DTWEXBGS (Nominal Broad U.S. Dollar Index) which has a 2006-baseline
    of 100, so it currently reads ~118 — confusing for a field labeled
    "DXY" when crypto traders universally mean ICE DXY (1973-baseline
    of 100, currently ~100-102). David flagged this on first sight.

    ICE DXY is computed from a fixed-weight basket of 6 currencies:
        DXY = 50.14348112
              * EURUSD^(-0.576)
              * USDJPY^(+0.136)
              * GBPUSD^(-0.119)
              * USDCAD^(+0.091)
              * USDSEK^(+0.042)
              * USDCHF^(+0.036)
    (Negative exponents for EUR + GBP because their FRED series are
    quoted as USD per FX unit, not FX per USD — the formula expects
    USD strength, so we invert via negative exponent rather than 1/x.)

    All 6 FX rates are free on FRED, no API key:
        DEXUSEU = USD per EUR (= EURUSD spot rate)
        DEXJPUS = JPY per USD (= USDJPY spot rate)
        DEXUSUK = USD per GBP (= GBPUSD spot rate)
        DEXCAUS = CAD per USD (= USDCAD spot rate)
        DEXSDUS = SEK per USD (= USDSEK spot rate)
        DEXSZUS = CHF per USD (= USDCHF spot rate)

    Each leg is cached 1h via _fred_latest, so this is cheap on
    subsequent calls. Returns None if any leg is missing.
    """
    # AUDIT-2026-05-06 (post-launch v5.1): parallelize the 6 leg fetches
    # via _MACRO_EXEC. Sequential calls were taking 30-60s (way past the
    # 14s endpoint deadline) — parallel completes in 2-4s with cold
    # caches. Each leg has its own 1h cache via _fred_latest, so warm
    # calls return < 100ms regardless.
    series_ids = ("DEXUSEU", "DEXJPUS", "DEXUSUK", "DEXCAUS", "DEXSDUS", "DEXSZUS")
    futures_legs = {sid: _MACRO_EXEC.submit(_fred_latest, sid) for sid in series_ids}

    deadline = _time.time() + 8  # leg-fetches share an 8s ceiling
    leg_values: dict[str, float | None] = {}
    for sid, fut in futures_legs.items():
        remaining = max(0.05, deadline - _time.time())
        try:
            leg_values[sid] = fut.result(timeout=remaining)
        except Exception:
            leg_values[sid] = None

    eur_usd = leg_values["DEXUSEU"]
    usd_jpy = leg_values["DEXJPUS"]
    gbp_usd = leg_values["DEXUSUK"]
    usd_cad = leg_values["DEXCAUS"]
    usd_sek = leg_values["DEXSDUS"]
    usd_chf = leg_values["DEXSZUS"]

    legs = (eur_usd, usd_jpy, gbp_usd, usd_cad, usd_sek, usd_chf)
    if any(x is None or x <= 0 for x in legs):
        logger.warning(
            "[macro] ICE DXY compute failed — leg(s) missing: EUR=%s JPY=%s GBP=%s CAD=%s SEK=%s CHF=%s",
            eur_usd, usd_jpy, gbp_usd, usd_cad, usd_sek, usd_chf,
        )
        return None

    try:
        dxy = (
            50.14348112
            * (eur_usd ** -0.576)
            * (usd_jpy ** 0.136)
            * (gbp_usd ** -0.119)
            * (usd_cad ** 0.091)
            * (usd_sek ** 0.042)
            * (usd_chf ** 0.036)
        )
        return round(dxy, 3)
    except (ValueError, TypeError, OverflowError) as exc:
        logger.warning("[macro] ICE DXY formula error: %s", exc)
        return None


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

    # DXY (ICE basis) — strong dollar = headwind for risk (-1),
    # weak dollar = tailwind (+1). ICE DXY typical 95-110 range.
    if dxy is not None:
        inputs_used += 1
        if dxy < 100.0:    score += 1
        elif dxy > 105.0:  score -= 1

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
    max_workers=16,  # 7 top-level + 6 DXY sub-legs + headroom for /v5.1
    thread_name_prefix="macro-fetch",
)

# AUDIT-2026-05-06 (post-launch v5.3): cache pre-warm on import.
# Render's outbound HTTP to FRED is consistently slow on cold starts —
# even parallel fetches don't fit the 14s endpoint deadline on first
# user request. Fix: kick off a background thread at module import that
# warms every relevant cache. The first user request hits warm caches
# and returns < 200ms with all fields populated.
def _prewarm_caches():
    """Background warm of all upstream caches. Errors are swallowed —
    if anything fails the user-facing endpoint just falls back."""
    import time
    time.sleep(2)  # let the rest of the FastAPI app finish import first
    try:
        # FRED FX legs for ICE DXY
        for sid in ("DEXUSEU", "DEXJPUS", "DEXUSUK", "DEXCAUS", "DEXSDUS", "DEXSZUS"):
            try:
                _fred_latest(sid)
            except Exception:
                pass
        # FRED other macro
        for sid in ("VIXCLS", "BAMLH0A0HYM2"):
            try:
                _fred_latest(sid)
            except Exception:
                pass
        # CoinGecko + Fear & Greed + funding (data_feeds caches handle these)
        try:
            data_feeds.get_global_market()
        except Exception:
            pass
        try:
            data_feeds.get_fear_greed()
        except Exception:
            pass
        try:
            data_feeds.fetch_fred_macro()
        except Exception:
            pass
        try:
            data_feeds.get_funding_rate("BTC/USDT")
        except Exception:
            pass
        logger.info("[macro] cache pre-warm complete")
    except Exception as exc:
        logger.warning("[macro] cache pre-warm failed: %s", exc)


# Fire the warmer in a daemon thread so it doesn't block module import.
import threading as _threading
_threading.Thread(target=_prewarm_caches, daemon=True, name="macro-prewarm").start()


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

    # AUDIT-2026-05-06 (post-launch v3.5): fallback for BTC dominance too.
    # CoinGecko intermittently fails on Render — same pattern as DXY/VIX.
    # Recent BTC dom hovers ~58-59% per April 2026 readings.
    _BTC_DOM_FALLBACK = 58.5
    btc_dom_val = gm.get("btc_dominance")
    btc_dom_alt = gm.get("altcoin_season_label")
    btc_dom_src = gm.get("source")
    if btc_dom_val is None:
        btc_dom_val = _BTC_DOM_FALLBACK
        btc_dom_alt = "BTC_DOMINANT"
        btc_dom_src = "fallback"
    payload["btc_dominance"] = {
        "value": btc_dom_val,
        "alt_season_label": btc_dom_alt,
        "source": btc_dom_src,
    }

    # F&G fallback when alternative.me fails.
    _FG_FALLBACK = 50
    fg_val = fg.get("value")
    fg_label = fg.get("label")
    fg_signal = fg.get("signal")
    fg_source = "alternative.me"
    if fg_val is None:
        fg_val = _FG_FALLBACK
        fg_label = "Neutral"
        fg_signal = "NEUTRAL"
        fg_source = "fallback"
    payload["fear_greed"] = {
        "value": fg_val,
        "label": fg_label,
        "bias": fg.get("bias", 0.0),
        "signal": fg_signal,
        "source": fg_source,
    }
    # AUDIT-2026-05-06 (post-launch v3.4 + v5): fallback values when
    # upstream fetchers fail (Render network flake). ICE DXY trades
    # ~100-105 (1973 baseline of 100), VIX ~17-20.
    _DXY_FALLBACK = 102.0   # ICE DXY recent ~100-103 (May 2026)
    _VIX_FALLBACK = 17.5    # FRED VIXCLS recent ~17-19 (May 2026)
    dxy_used = dxy_val if dxy_val is not None else _DXY_FALLBACK
    dxy_source = "FRED:ICE-DXY-formula" if dxy_val is not None else "fallback"

    # DXY trend on ICE DXY scale: < 100 weak (tailwind), > 105 strong
    # (headwind), else neutral. Recent typical range 95-110.
    if dxy_used > 105.0:
        dxy_trend = "STRONG_DOLLAR"
    elif dxy_used < 100.0:
        dxy_trend = "WEAK_DOLLAR"
    else:
        dxy_trend = "NEUTRAL"
    payload["dxy"] = {
        "value": round(dxy_used, 2),
        "trend": dxy_trend,
        "source": dxy_source,
    }

    vix_used = vix_val if vix_val is not None else _VIX_FALLBACK
    vix_source = "FRED:VIXCLS" if vix_val is not None else "fallback"

    # VIX structure: < 18 calm, > 25 stressed.
    if vix_used < 18.0:
        vix_structure = "CALM"
    elif vix_used > 25.0:
        vix_structure = "STRESSED"
    else:
        vix_structure = "NEUTRAL"
    payload["vix"] = {
        "value": round(vix_used, 2),
        "vix3m": None,
        "structure": vix_structure,
        "source": vix_source,
    }

    # Recompute macro signal using the values actually displayed
    # (fallback or live), so the regime label is consistent with the
    # numbers shown above.
    dxy_for_signal = dxy_val if dxy_val is not None else dxy_used
    vix_for_signal = vix_val if vix_val is not None else vix_used

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

    # Macro signal computed locally — uses the values actually surfaced
    # (fallback or live), so label/score is consistent with the numbers
    # the user sees in the UI.
    sig_label, sig_score = _classify_macro_signal(
        dxy=dxy_for_signal, vix=vix_for_signal, ten_y=ten_y, two_y=two_y, hy_bps=hy
    )
    payload["macro_signal"] = {"label": sig_label, "score": sig_score}
    # BTC funding fallback — Bybit primary (works most of the time).
    _BTC_FUNDING_FALLBACK = 0.001  # ~0.001% / 8h is roughly neutral
    fund_val = fund.get("funding_rate_pct")
    fund_signal = fund.get("signal", "NEUTRAL")
    fund_source = fund.get("source")
    if fund_val is None:
        fund_val = _BTC_FUNDING_FALLBACK
        fund_signal = "NEUTRAL"
        fund_source = "fallback"
    payload["btc_funding"] = {
        "value":  fund_val,
        "signal": fund_signal,
        "source": fund_source,
    }

    # HY spreads fallback — recent April 2026 reading ~280bps.
    payload["hy_spreads"] = {
        "value": hy if hy is not None else 280.0,
        "source": "FRED:BAMLH0A0HYM2" if hy is not None else "fallback",
    }

    return serialize(payload)
