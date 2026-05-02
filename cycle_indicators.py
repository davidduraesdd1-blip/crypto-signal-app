"""
cycle_indicators.py — SuperGrok
CoinsKid-inspired composite cycle indicators layer.

Six independent signals composed on top of the existing 4-layer composite:
  1. Google Trends retail sentiment (pytrends, 24h TTL, graceful fallback)
  2. Stablecoin supply delta — USDT+USDC+DAI 7-day % change (dry powder gauge)
  3. Breadth confirmation — % of top-30 coins above 50D MA and 200D MA
  4. Voliquidity — ATR14 × (volume_24h / market_cap) move-magnitude gauge
  5. Dumb Money — retail interest surge proxy (small-wallet BTC accumulation)
  6. Unified Cycle Score (1-100, 5 zones) — UX wrapper over composite signal

All signals are optional and fail gracefully (return None).

Research:
  - Google Trends as top signal: Preis, Moat & Stanley (2013).
  - Stablecoin dry powder: Kaiko (2023), Glassnode (2024).
  - Breadth divergence: Lowry Research (1998).
  - Voliquidity: Amihud (2002) illiquidity ratio.
  - Dumb Money: retail search interest + small-wallet on-chain accumulation
    spike = late-cycle distribution zone. CryptoQuant wallet cohort (2023).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()

_TTL_TRENDS    = 86_400
_TTL_STABLE    = 3_600
_TTL_BREADTH   = 3_600
_TTL_VOLIQ     = 900
_TTL_DUMB      = 86_400


def _cached_get(key: str, ttl: int, fetch_fn):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and (time.time() - hit["ts"]) < ttl:
            return hit["data"]
    try:
        data = fetch_fn()
        if data is not None:
            with _CACHE_LOCK:
                _CACHE[key] = {"data": data, "ts": time.time()}
        return data
    except Exception as e:
        logger.debug("[CycleIndicators] %s failed: %s", key, e)
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit:
                return hit["data"]
        return None


def clear_cycle_caches() -> None:
    """Clear module-level caches (wired to 'Refresh All Data' button)."""
    with _CACHE_LOCK:
        _CACHE.clear()


# ─── 1. Google Trends retail sentiment ───────────────────────────────────────

def fetch_google_trends_signal(
    keyword: str = "bitcoin",
    geo: str = "",
    timeframe: str = "today 3-m",
) -> dict[str, Any] | None:
    """Retail search interest for a keyword.
    Returns {current, avg_4w, spike_pct, signal, score} or None on failure.
    """
    def _fetch() -> dict[str, Any] | None:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.debug("[Trends] pytrends not installed — skipping")
            return None
        try:
            tr = TrendReq(hl="en-US", tz=0, timeout=(4, 10), retries=1)
            tr.build_payload([keyword], cat=0, timeframe=timeframe, geo=geo)
            df = tr.interest_over_time()
            if df is None or df.empty or keyword not in df.columns:
                return None
            series = df[keyword].astype(float).tolist()
            if len(series) < 5:
                return None
            # Audit 2026-05-02 C19: prior baseline `series[-4:]` included
            # the current week, muting any actual spike. Use the 4 PRIOR
            # weeks (`series[-5:-1]`) so `current` is compared against the
            # truly trailing baseline.
            if len(series) < 5:
                return None
            current = float(series[-1])
            avg_4w  = sum(series[-5:-1]) / 4.0
            if avg_4w <= 0:
                return None
            spike = (current / avg_4w - 1.0) * 100.0
            if spike >= 50:   sig, score = "SURGE",    -0.8
            elif spike >= 20: sig, score = "RISING",   -0.3
            elif spike >= -10: sig, score = "STABLE",   0.0
            elif spike >= -30: sig, score = "FALLING", +0.3
            else:             sig, score = "COLLAPSE",  +0.6
            return {
                "current":   round(current, 1),
                "avg_4w":    round(avg_4w, 1),
                "spike_pct": round(spike, 1),
                "signal":    sig,
                "score":     score,
            }
        except Exception as e:
            logger.debug("[Trends] fetch failed: %s", e)
            return None

    return _cached_get(f"gtrends_{keyword}_{geo}_{timeframe}", _TTL_TRENDS, _fetch)


# ─── 2. Stablecoin supply delta ──────────────────────────────────────────────

_STABLE_COINS = ["tether", "usd-coin", "dai"]


def fetch_stablecoin_supply_delta() -> dict[str, Any] | None:
    """USDT+USDC+DAI aggregate supply 7d % change via CoinGecko (free, no key)."""
    def _fetch() -> dict[str, Any] | None:
        try:
            import requests
        except ImportError:
            return None

        total_now = 0.0
        total_7d  = 0.0
        fetched   = 0
        for coin_id in _STABLE_COINS:
            try:
                url = (f"https://api.coingecko.com/api/v3/coins/{coin_id}/"
                       f"market_chart?vs_currency=usd&days=7&interval=daily")
                r = requests.get(url, timeout=10,
                                 headers={"Accept": "application/json"})
                if r.status_code != 200:
                    continue
                data = r.json()
                caps = data.get("market_caps") or []
                if len(caps) < 2:
                    continue
                total_now += float(caps[-1][1])
                total_7d  += float(caps[0][1])
                fetched   += 1
            except Exception as e:
                logger.debug("[StableSupply] %s failed: %s", coin_id, e)
                continue

        if fetched == 0 or total_7d <= 0:
            return None

        delta_pct = (total_now / total_7d - 1.0) * 100.0
        if delta_pct >= 2.0:   sig, score = "ACCUMULATING", +0.6
        elif delta_pct >= 0.5: sig, score = "ACCUMULATING", +0.3
        elif delta_pct >= -0.5: sig, score = "STABLE",       0.0
        elif delta_pct >= -2.0: sig, score = "DISTRIBUTING", -0.3
        else:                  sig, score = "DISTRIBUTING", -0.6

        return {
            "total_now":    round(total_now),
            "total_7d_ago": round(total_7d),
            "delta_7d_pct": round(delta_pct, 2),
            "signal":       sig,
            "score":        score,
            "fetched":      fetched,
        }

    return _cached_get("stable_supply_delta", _TTL_STABLE, _fetch)


# ─── 3. Breadth confirmation ─────────────────────────────────────────────────

def compute_breadth(prices_df_dict: dict[str, list[float]] | None) -> dict[str, Any] | None:
    """% of tracked coins with close > 50D and > 200D SMA (Lowry 1998)."""
    if not prices_df_dict:
        return None

    n_50_total = n_50_above = 0
    n_200_total = n_200_above = 0
    for sym, closes in prices_df_dict.items():
        try:
            closes = [float(c) for c in closes if c is not None]
        except (TypeError, ValueError):
            continue
        if len(closes) < 50:
            continue
        price = closes[-1]
        ma_50 = sum(closes[-50:]) / 50.0
        n_50_total += 1
        if price > ma_50:
            n_50_above += 1
        if len(closes) >= 200:
            ma_200 = sum(closes[-200:]) / 200.0
            n_200_total += 1
            if price > ma_200:
                n_200_above += 1

    if n_50_total == 0 and n_200_total == 0:
        return None

    pct_50  = (n_50_above  / n_50_total  * 100.0) if n_50_total  else None
    pct_200 = (n_200_above / n_200_total * 100.0) if n_200_total else None
    primary = pct_200 if pct_200 is not None else pct_50
    if   primary is None:   sig, score = None,           None
    elif primary >= 80:     sig, score = "EXTENDED",     -0.4
    elif primary >= 60:     sig, score = "HEALTHY_BULL", +0.3
    elif primary >= 40:     sig, score = "MIXED",         0.0
    elif primary >= 20:     sig, score = "CORRECTION",   +0.3
    else:                   sig, score = "CAPITULATION", +0.6

    return {
        "pct_above_50d":  round(pct_50,  1) if pct_50  is not None else None,
        "pct_above_200d": round(pct_200, 1) if pct_200 is not None else None,
        "n_sampled":      max(n_50_total, n_200_total),
        "signal":         sig,
        "score":          score,
    }


# ─── 4. Voliquidity ──────────────────────────────────────────────────────────

def compute_voliquidity(
    atr_14: float | None,
    price: float | None,
    volume_24h: float | None,
    market_cap: float | None,
) -> dict[str, Any] | None:
    """Voliquidity = (ATR14/price) × (vol24h/mcap). Amihud (2002) adaptation."""
    try:
        if not (atr_14 and price and volume_24h and market_cap):
            return None
        atr_pct  = float(atr_14) / float(price)
        turnover = float(volume_24h) / float(market_cap)
        voliq    = atr_pct * turnover
    except (TypeError, ValueError, ZeroDivisionError):
        return None

    if   voliq >= 0.0030: bucket, score = "EXTREME_VOLATILITY", -0.3
    elif voliq >= 0.0015: bucket, score = "ELEVATED",            -0.1
    elif voliq >= 0.0007: bucket, score = "NORMAL",               0.0
    elif voliq >= 0.0003: bucket, score = "COMPRESSED",          +0.2
    else:                 bucket, score = "ULTRA_COMPRESSED",    +0.4

    return {
        "voliquidity": round(voliq, 6),
        "atr_pct":     round(atr_pct, 4),
        "turnover":    round(turnover, 4),
        "bucket":      bucket,
        "score":       score,
    }


# ─── 5. Dumb Money (retail FOMO top signal) ──────────────────────────────────

def fetch_dumb_money_signal() -> dict[str, Any] | None:
    """
    Retail late-cycle signal.  Combines:
      - Google Trends 'bitcoin' spike (our retail interest proxy)
      - If spike >= +50% AND F&G > 75: strong DUMB_MONEY_ACTIVE top signal
      - If spike <= -30% AND F&G < 25: SMART_MONEY_ZONE bottom signal
    Works only off signals already fetched — no new external calls.

    Args: None.  Pulls from cached Google Trends signal.
    Returns: dict with signal, score, explanation, or None if no data.
    """
    trends = fetch_google_trends_signal("bitcoin")
    if not trends:
        return None
    spike = trends.get("spike_pct", 0.0) or 0.0
    # Simplified: score off spike alone. Caller combines with F&G at signal compute time.
    if   spike >= 50:   sig, score = "DUMB_MONEY_SURGE",  -0.7
    elif spike >= 25:   sig, score = "RETAIL_ACTIVE",      -0.3
    elif spike >= -15:  sig, score = "QUIET",               0.0
    elif spike >= -40:  sig, score = "RETAIL_LEAVING",     +0.3
    else:               sig, score = "SMART_MONEY_ZONE",   +0.6
    return {
        "spike_pct":   round(spike, 1),
        "signal":      sig,
        "score":       score,
        "explanation": f"Retail interest {'surging' if score<0 else 'fading'} vs 4w avg",
    }


# ─── 6. Unified Cycle Score (1-100, 5 zones) ─────────────────────────────────

def cycle_score_100(
    composite_score: float | None,
    extras: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    """Map composite [-1,+1] to CoinsKid-style 1-100 (100 = euphoria/top)."""
    parts: list[tuple[float, float]] = []
    if composite_score is not None:
        parts.append((float(composite_score), 0.60))
    if extras:
        for key, w in (("trends", 0.08), ("stable_delta", 0.10),
                       ("breadth", 0.10), ("voliquidity", 0.05),
                       ("dumb_money", 0.07)):
            v = extras.get(key)
            if v is not None:
                parts.append((float(v), w))

    if not parts:
        return {"score": 50, "zone": "NEUTRAL", "zone_label": "Neutral",
                "color": "#64748b", "inputs_used": 0}

    wsum  = sum(w for _, w in parts)
    blend = sum(s * w for s, w in parts) / wsum if wsum > 0 else 0.0
    blend = max(-1.0, min(1.0, blend))
    # Audit 2026-05-02 C18: legacy used 49, capping cycle at [1, 99]
    # asymmetric to the documented [0, 100] range. blend=-1 should map
    # to 100 (max euphoria) and blend=+1 to 0 (max accumulation).
    cycle = int(round(50 - blend * 50))
    cycle = max(0, min(100, cycle))

    if   cycle <= 15:  zone, label, color = "STRONG_BUY",   "Strong Buy",    "#22c55e"
    elif cycle <= 35:  zone, label, color = "BUY",           "Buy",           "#00d4aa"
    elif cycle <= 65:  zone, label, color = "NEUTRAL",       "Neutral",       "#64748b"
    elif cycle <= 85:  zone, label, color = "SELL",          "Sell",          "#f59e0b"
    else:              zone, label, color = "STRONG_SELL",   "Strong Sell",   "#ef4444"

    return {
        "score":       cycle,
        "zone":        zone,
        "zone_label":  label,
        "color":       color,
        "blend_raw":   round(blend, 4),
        "inputs_used": len(parts),
    }


def render_cycle_gauge_html(cycle: dict[str, Any], user_level: str = "beginner") -> str:
    """Hero card HTML — 1-100 gauge + zone label."""
    score = int(cycle.get("score", 50))
    zone  = cycle.get("zone_label", "Neutral")
    color = cycle.get("color", "#64748b")
    if   score <= 15: tag = "Historically strong accumulation zone"
    elif score <= 35: tag = "Favorable buying conditions"
    elif score <= 65: tag = "Neutral — hold existing positions"
    elif score <= 85: tag = "Caution — distribution zone forming"
    else:             tag = "Historically extreme top zone — reduce exposure"

    shape = "▼" if score >= 66 else ("▲" if score <= 34 else "■")
    bar_width = max(2, min(100, score))

    return (
        f"<div style='background:linear-gradient(135deg,{color}11,{color}05);"
        f"border:1px solid {color}55;border-left:4px solid {color};"
        f"border-radius:12px;padding:16px 22px;margin:0 0 18px;'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"flex-wrap:wrap;gap:16px;'>"
        f"<div style='flex:1;min-width:180px;'>"
        f"<div style='font-size:10px;font-weight:800;letter-spacing:1.2px;"
        f"color:{color};text-transform:uppercase;margin-bottom:4px;'>"
        f"⏱ Market Cycle Position</div>"
        f"<div style='font-size:22px;font-weight:800;color:{color};'>"
        f"{shape} {zone} · {score}/100</div>"
        f"<div style='font-size:13px;color:#94a3b8;margin-top:4px;'>{tag}</div>"
        f"</div>"
        f"<div style='flex:2;min-width:220px;'>"
        f"<div style='position:relative;height:12px;background:#1e293b;"
        f"border-radius:6px;overflow:hidden;'>"
        f"<div style='position:absolute;left:0;top:0;width:{bar_width}%;"
        f"height:100%;background:linear-gradient(90deg,#22c55e,#00d4aa,"
        f"#64748b,#f59e0b,#ef4444);'></div>"
        f"<div style='position:absolute;left:{bar_width}%;top:-3px;"
        f"width:3px;height:18px;background:#e2e8f0;border-radius:2px;'></div>"
        f"</div>"
        f"<div style='display:flex;justify-content:space-between;"
        f"font-size:10px;color:#64748b;margin-top:4px;'>"
        f"<span>1 Strong Buy</span><span>50 Neutral</span><span>100 Strong Sell</span>"
        f"</div></div></div></div>"
    )


# ─── Convenience composer ────────────────────────────────────────────────────

def compute_cycle_bundle(composite_score: float | None,
                        breadth_data: dict | None = None,
                        voliq_data: dict | None = None) -> dict[str, Any]:
    """
    High-level one-shot helper.  Fetches trends + stable + dumb-money, combines
    with caller-provided breadth + voliq, and returns both the full extras
    dict and the cycle_100 result.  Returns empty dict on total failure.
    """
    try:
        trends = fetch_google_trends_signal("bitcoin")
        stable = fetch_stablecoin_supply_delta()
        dumb   = fetch_dumb_money_signal()
        extras = {
            "trends":       (trends or {}).get("score"),
            "stable_delta": (stable or {}).get("score"),
            "breadth":      (breadth_data or {}).get("score"),
            "voliquidity":  (voliq_data   or {}).get("score"),
            "dumb_money":   (dumb   or {}).get("score"),
        }
        cycle = cycle_score_100(composite_score, extras=extras)
        return {
            "cycle_100":     cycle,
            "trends":        trends,
            "stable_delta":  stable,
            "breadth":       breadth_data,
            "voliquidity":   voliq_data,
            "dumb_money":    dumb,
        }
    except Exception as e:
        logger.debug("[CycleBundle] failed: %s", e)
        return {}
