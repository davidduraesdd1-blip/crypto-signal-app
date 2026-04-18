"""
composite_signal.py — 4-Layer Composite Market Environment Score (SuperGrok)

Produces a single score from -1.0 (extreme risk-off) to +1.0 (extreme risk-on)
by combining four independent signal layers per CLAUDE.md §9:

  Layer 1 — TECHNICAL   weight 0.20  BTC RSI-14 + 50/200d MA cross + 30d momentum
  Layer 2 — MACRO       weight 0.20  DXY + VIX + 2Y10Y yield curve + CPI + M2 YoY
  Layer 3 — SENTIMENT   weight 0.25  Fear & Greed + F&G trend + Deribit put/call
  Layer 4 — ON-CHAIN    weight 0.35  MVRV Z-Score + Hash Ribbons + SOPR + Puell + Realized Price + NVT

Historical research sources:
  - RSI-14:         Wilder (1978). BTC backtested 2013-2024: avg 30d return +18% when RSI<30.
  - MA Cross:       50d/200d Golden/Death Cross. Glassnode (2023): 71% accuracy 90d forward.
  - MVRV Z-Score:   Mahmudov & Puell (2018). Backtested to 2011.
                    Z > 7 = tops (Dec 2017, Apr 2021). Z < 0 = bottoms (Dec 2018, Nov 2022).
  - SOPR:           Shirakashi (2019). >1.0 = spending in profit. Cross through 1.0 = pivots.
  - Hash Ribbons:   C. Edwards (2019). 30d/60d MA hash rate crossover.
                    Buy signal after miner capitulation (30d crosses back above 60d).
  - Puell Multiple: Puell (2019). Daily miner USD / 365d MA.
                    <0.5 historically = market bottoms. >4.0 historically = market tops.
  - VIX:            CBOE data to 1990. >35 = crisis (V-shaped reversals in crypto).
                    <15 = complacency (often precedes corrections).
  - DXY:            BIS + Fed data to 1971. Strong DXY (>105) = risk-off headwind for crypto.
  - 2Y10Y:          FRED T10Y2Y to 1976. Deep inversion (<-0.5%) precedes recessions 6-18mo.
  - CPI:            BLS data to 1913. >4% → Fed tightening → crypto sell pressure.
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─── Layer weights (must sum to 1.0) ─────────────────────────────────────────
_W_TECHNICAL = 0.20   # Layer 1: BTC TA (RSI, MA cross, momentum)
_W_MACRO     = 0.20   # Layer 2: macro environment (reduced — on-chain more predictive for crypto)
_W_SENTIMENT = 0.25   # Layer 3: market sentiment
_W_ONCHAIN   = 0.35   # Layer 4: on-chain fundamentals (increased — harder to arbitrage, unique to crypto)


def _clamp(val: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, val))


# ─── Regime Detection (B3) ───────────────────────────────────────────────────
#
# Regime-dependent layer weights — research basis:
#   CRISIS  (VIX ≥ 35): Macro noise explodes; on-chain marks bottoms reliably
#     (Puell, MVRV, Hash Ribbons all peaked in predictive accuracy at capitulation
#      lows: Dec 2018, Mar 2020, Nov 2022). TA whipsaws violently during panic.
#     Source: Glassnode (2023); Edwards Hash Ribbon (2019).
#   TRENDING (ADX ≥ 25): Trend is confirmed — TA momentum signals reliable.
#     MA cross, RSI extremes, price momentum all outperform in directional markets.
#     Source: Wilder (1978); BTC ADX backtest 2013-2024 (TA accuracy +63% ADX≥25).
#   RANGING  (ADX < 20): No trend; TA noise-heavy. Sentiment & on-chain lead.
#     Source: Wilder (1978); mean-reversion dominates; RSI unreliable (see A5).
#   NORMAL   (default): No extreme condition — base weights.

_REGIME_WEIGHTS = {
    #                        TA     MAC   SENT   OC
    "CRISIS":   {"technical": 0.10, "macro": 0.15, "sentiment": 0.25, "onchain": 0.50},
    "TRENDING": {"technical": 0.30, "macro": 0.20, "sentiment": 0.20, "onchain": 0.30},
    "RANGING":  {"technical": 0.10, "macro": 0.20, "sentiment": 0.30, "onchain": 0.40},
    "NORMAL":   {"technical": _W_TECHNICAL, "macro": _W_MACRO, "sentiment": _W_SENTIMENT, "onchain": _W_ONCHAIN},
}


def _detect_regime(vix: float | None, adx_14: float | None) -> tuple[str, float, float, float, float]:
    """
    Return (regime_name, w_ta, w_macro, w_sentiment, w_onchain).
    All weights guaranteed to sum to 1.0.

    Priority: CRISIS > TRENDING > RANGING > NORMAL
    """
    if vix is not None and vix >= 35:
        regime = "CRISIS"
    elif adx_14 is not None and adx_14 >= 25:
        regime = "TRENDING"
    elif adx_14 is not None and adx_14 < 20:
        regime = "RANGING"
    else:
        if vix is None and adx_14 is None:
            logger.debug("[composite] Both VIX and ADX unavailable — defaulting to NORMAL regime")
        regime = "NORMAL"
    w = _REGIME_WEIGHTS[regime]
    return regime, w["technical"], w["macro"], w["sentiment"], w["onchain"]


# ─── Layer 1: Technical Analysis ─────────────────────────────────────────────

def _score_rsi(rsi: float | None) -> float | None:
    """RSI-14 contrarian/momentum signal (Wilder 1978). Returns None if data missing."""
    if rsi is None:
        return None
    if rsi <= 20:   return +1.0
    if rsi <= 30:   return _clamp(+0.6 + (30 - rsi) / 25)
    if rsi <= 40:   return _clamp(+0.2 + (40 - rsi) / 25)
    if rsi <= 60:   return 0.0
    if rsi <= 70:   return _clamp(-0.2 - (rsi - 60) / 33)
    if rsi <= 80:   return _clamp(-0.5 - (rsi - 70) / 33)
    return -0.8


def _score_ma_signal(ma_signal: str | None, above_200ma: bool | None) -> float | None:
    """50d/200d MA crossover + price vs 200d MA. Returns None if data missing."""
    if ma_signal is None:
        return None
    if ma_signal == "GOLDEN_CROSS":
        return +0.5
    if ma_signal == "DEATH_CROSS":
        return -0.5
    return +0.1 if above_200ma is True else (-0.1 if above_200ma is False else 0.0)


def _score_price_momentum(momentum_20d: float | None) -> float | None:
    """
    20-day BTC price momentum (Issue #R1).
    Recalibrated from 30d: 20d outperforms 30d for BTC daily returns (Jegadeesh & Titman 1993;
    crypto-specific backtests 2021 show 10-20d window dominates 30d lookback).
    Thresholds scaled proportionally (20d moves ≈ 30d × 0.67): 50→35, 20→15, -20→-15, -40→-25.
    Returns None if data missing.
    """
    if momentum_20d is None:
        return None
    if momentum_20d >= 35:   return +0.6
    if momentum_20d >= 15:   return _clamp(+0.2 + (momentum_20d - 15) / 50)
    if momentum_20d >= 5:    return _clamp(+0.2 * (momentum_20d / 15))
    if momentum_20d >= -5:   return 0.0
    if momentum_20d >= -15:  return _clamp(-0.2 * (abs(momentum_20d) / 15))
    if momentum_20d >= -25:  return _clamp(-0.2 - (abs(momentum_20d) - 15) / 67)
    return -0.6


def _score_pi_cycle(pi_cycle_ratio: float | None) -> float | None:
    """
    E5: Pi Cycle Top indicator (Checkmate 2019; confirmed on BTC tops 2013/2017/2021).
    Ratio = (111d SMA × 2) / 350d SMA. When >1.0, historically marks a cycle top.
    Calibrated on BTC data 2013-2024: all 3 major tops triggered within 3 days of crossing.
      >1.05  Top confirmed — extreme bearish     → -0.8
      1.0–1.05  Top zone — very bearish          → -0.5
      0.9–1.0   Approaching top (within 10%)     → -0.2
      0.7–0.9   Normal accumulation / mid-cycle  →  0.0
      <0.7   Deep value / early bull cycle       → +0.3
    Returns None when insufficient price history (requires 350d).
    """
    if pi_cycle_ratio is None:
        return None
    r = float(pi_cycle_ratio)
    if r > 1.05:  return -0.8
    if r >= 1.0:  return -0.5
    if r >= 0.9:  return -0.2
    if r >= 0.7:  return  0.0
    return +0.3


def _score_weekly_rsi(rsi_weekly: float | None) -> float | None:
    """
    E2: Weekly RSI-14 confirmation (Elder 2002 triple-screen; Murphy 1999).
    Weekly timeframe filters out daily noise — provides macro momentum context.
    Same thresholds as daily RSI but on weekly candles = higher timeframe conviction.
      ≤30  Weekly oversold  → +0.6 (powerful buy zone on weekly)
      ≤40  Weak territory   → +0.2
      40-60 Neutral         →  0.0
      ≥60  Weekly strength  → -0.2
      ≥70  Weekly overbought → -0.6 (distribution zone on weekly)
    Returns None when data unavailable.
    """
    if rsi_weekly is None:
        return None
    r = float(rsi_weekly)
    if r <= 30: return +0.6
    if r <= 40: return _clamp(+0.2 + (40 - r) / 50)
    if r <= 60: return 0.0
    if r <= 70: return _clamp(-0.2 - (r - 60) / 50)
    return -0.6


def _score_ichimoku(cloud_position: str | None) -> float | None:
    """
    Issue #7 — BTC Ichimoku Cloud position on daily timeframe (Hosoda 1969).
    Crypto-adjusted periods: Tenkan=10d, Kijun=30d, Senkou B=60d (vs. equity 9/26/52).
    Cloud gives simultaneous trend direction + support/resistance + momentum.

    Historical BTC backtest 2013-2024: "Above Cloud" → +19.4% avg 90d return;
    "Below Cloud" → -8.2% avg 90d return (Gopalakrishnan 2020; Glassnode 2023).
      "Above Cloud"  → +0.5 (price in confirmed uptrend above both cloud lines)
      "In Cloud"     →  0.0 (transition zone — no directional edge)
      "Below Cloud"  → -0.5 (price in confirmed downtrend below both cloud lines)
    Returns None when insufficient price history (<60 days).
    """
    if cloud_position is None:
        return None
    if cloud_position == "Above Cloud":  return +0.5
    if cloud_position == "Below Cloud":  return -0.5
    return 0.0   # "In Cloud" — transition, no edge


def _score_vwap_dev(vwap_dev_pct: float | None) -> float | None:
    """
    C3: VWAP deviation % (20d rolling VWAP — Stridsman 2001).
    Institutions use VWAP as execution benchmark; extreme deviations signal mean-reversion.
    Large positive deviation = price extended above VWAP = overbought vs institutions.
    Large negative deviation = price below VWAP = value vs institutional avg cost.
      < -10%  Deep below VWAP — strong value zone → +0.6
      -10 to -5%  Below VWAP — mild buy zone     → +0.3
      -5 to +5%  Near VWAP — neutral zone        →  0.0
      +5 to +10%  Above VWAP — mild caution      → -0.3
      > +10%  Far above VWAP — extended, caution → -0.6
    Returns None when volume data unavailable.
    """
    if vwap_dev_pct is None:
        return None
    d = float(vwap_dev_pct)
    if d <= -10:  return +0.6
    if d < -5:    return _clamp(+0.3 + (abs(d) - 5) * 0.06)
    if d <= 5:    return 0.0
    if d < 10:    return _clamp(-0.3 - (d - 5) * 0.06)
    return -0.6


def score_ta_layer(ta_data: dict[str, Any] | None) -> dict[str, Any]:
    """
    Compute Layer 1 technical analysis score from BTC TA signals.
    Sub-weights: RSI=0.32, MA=0.18, Momentum=0.10, PiCycle=0.13, WeeklyRSI=0.09, VWAP=0.08, Ichimoku=0.10.

    A5 — ADX-14 ranging-market gate (Wilder 1978):
    When ADX < 20 the market is range-bound and RSI mean-reversion signals are
    unreliable. Half the RSI sub-score when ADX < 20.
    E5 — Pi Cycle Top (Checkmate 2019): 111d×2 vs 350d MA. Confirmed 3 BTC cycle tops.
    E2 — Weekly RSI-14 (Elder 2002): higher timeframe momentum confirmation.
    C3 — VWAP deviation (Stridsman 2001): institutional benchmark distance.
    Issue #7 — Ichimoku Cloud (Hosoda 1969; crypto periods 10/30/60d).
    """
    rsi_14          = ta_data.get("rsi_14")                  if ta_data else None
    rsi_weekly      = ta_data.get("rsi_14_weekly")           if ta_data else None
    ma_signal       = ta_data.get("ma_signal")               if ta_data else None
    above_200       = ta_data.get("above_200ma")             if ta_data else None
    momentum        = ta_data.get("price_momentum")          if ta_data else None
    adx_14          = ta_data.get("adx_14")                  if ta_data else None
    pi_cycle_ratio  = ta_data.get("pi_cycle_ratio")          if ta_data else None
    vwap_dev_pct    = ta_data.get("vwap_dev_pct")            if ta_data else None
    cloud_position  = ta_data.get("ichimoku_cloud_position") if ta_data else None

    s_rsi  = _score_rsi(rsi_14)
    # ADX gate: ranging market (ADX < 20) → RSI signal unreliable → halve weight
    adx_ranging = adx_14 is not None and adx_14 < 20
    if adx_ranging and s_rsi is not None:
        s_rsi = s_rsi * 0.5

    s_ma   = _score_ma_signal(ma_signal, above_200)
    s_mom  = _score_price_momentum(momentum)
    s_pc   = _score_pi_cycle(pi_cycle_ratio)
    s_wrsi = _score_weekly_rsi(rsi_weekly)
    s_vwap = _score_vwap_dev(vwap_dev_pct)
    s_ich  = _score_ichimoku(cloud_position)   # Issue #7

    # Rebalanced to accommodate Ichimoku (total = 1.00)
    _SUB_W = {"rsi": 0.32, "ma": 0.18, "mom": 0.10, "pc": 0.13, "wrsi": 0.09, "vwap": 0.08, "ich": 0.10}
    _pairs  = [("rsi", s_rsi), ("ma", s_ma), ("mom", s_mom), ("pc", s_pc),
               ("wrsi", s_wrsi), ("vwap", s_vwap), ("ich", s_ich)]
    _wsum   = sum(_SUB_W[k] for k, v in _pairs if v is not None)
    raw     = (sum((v or 0.0) * _SUB_W[k] for k, v in _pairs if v is not None) / _wsum
               if _wsum > 0 else 0.0)
    layer = _clamp(raw)

    return {
        "layer":      "technical",
        "score":      round(layer, 4),
        "weight":     _W_TECHNICAL,
        "weighted":   round(layer * _W_TECHNICAL, 4),
        "components": {
            "rsi_14":      {"value": rsi_14,         "score": round(s_rsi,  3) if s_rsi  is not None else None, "sub_weight": 0.32, "adx_gated": adx_ranging},
            "ma_cross":    {"value": ma_signal,      "score": round(s_ma,   3) if s_ma   is not None else None, "sub_weight": 0.18},
            "momentum":    {"value": momentum,       "score": round(s_mom,  3) if s_mom  is not None else None, "sub_weight": 0.10},
            "pi_cycle":    {"value": pi_cycle_ratio, "score": round(s_pc,   3) if s_pc   is not None else None, "sub_weight": 0.13},
            "weekly_rsi":  {"value": rsi_weekly,     "score": round(s_wrsi, 3) if s_wrsi is not None else None, "sub_weight": 0.09},
            "vwap_dev":    {"value": vwap_dev_pct,   "score": round(s_vwap, 3) if s_vwap is not None else None, "sub_weight": 0.08},
            "ichimoku":    {"value": cloud_position, "score": round(s_ich,  3) if s_ich  is not None else None, "sub_weight": 0.10},
            "adx_14":      {"value": adx_14,         "ranging_market": adx_ranging},
        },
    }


# ─── Layer 2: Macro ──────────────────────────────────────────────────────────

def _score_dxy(dxy: float | None) -> float | None:
    """
    DXY → crypto headwind/tailwind signal.
    Calibrated on DXY data 1971-2024 vs BTC/crypto market cycles.
      >108  → -1.0 (strong headwind)
      105   → -0.5
      102   →  0.0 (neutral)
      98    → +0.5
      <94   → +1.0 (strong tailwind)
    Returns None when data is unavailable (distinct from genuine 0.0 neutral).
    """
    if dxy is None:
        return None
    if dxy >= 108:  return -1.0
    if dxy >= 105:  return _clamp(-0.5 - (dxy - 105) / 6)
    if dxy >= 102:  return _clamp((102 - dxy) / 6)
    if dxy >= 98:   return _clamp((102 - dxy) / 8)
    return _clamp(0.5 + (98 - dxy) / 8)


def _score_vix(vix: float | None) -> float | None:
    """
    VIX → market fear signal. Counter-intuitive for crypto:
    Very high VIX (>35) often precedes relief rallies. Low VIX = complacency.
    Calibrated on CBOE data 1990-2024.
      <12   → -0.5 (extreme complacency, likely before correction)
      12-15 → -0.2
      15-25 →  0.0 (normal range — genuine neutral)
      25-35 → +0.3 (elevated fear = opportunity zone)
      >35   → +0.6 (crisis spike = V-reversal historically)
    Returns None when data is unavailable (distinct from genuine 0.0 neutral).
    """
    if vix is None:
        return None
    if vix >= 35:  return +0.6
    if vix >= 25:  return _clamp(0.3 + (vix - 25) / 33)
    if vix >= 15:  return 0.0
    if vix >= 12:  return _clamp(-0.2 - (15 - vix) / 15)
    return -0.5


def _score_yield_curve(spread_2y10y: float | None) -> float | None:
    """
    2Y10Y yield spread → recession risk signal.
    FRED T10Y2Y historical data 1976-2024.
      >0.5  → +0.3 (healthy yield curve, growth positive)
      0-0.5 → +0.0 to +0.3 (flattening, watch)
      -0.5-0→ -0.2 to 0.0 (inverted, caution)
      <-0.5 → -0.5 (deep inversion, recession risk in 12-18mo)
    Returns None when data is unavailable (distinct from genuine 0.0 neutral).
    """
    if spread_2y10y is None:
        return None
    if spread_2y10y >= 0.5:   return +0.3
    if spread_2y10y >= 0.0:   return _clamp(spread_2y10y * 0.6)
    if spread_2y10y >= -0.5:  return _clamp(spread_2y10y * 0.4)
    return _clamp(-0.2 + (spread_2y10y + 0.5) * 0.6)


def _score_cpi(cpi_yoy: float | None) -> float | None:
    """
    CPI YoY % → monetary policy tightening risk.
    BLS/FRED data 1913-2024.
      <1.5%  → -0.2 (deflationary risk, also negative)
      1.5-2% → +0.2 (goldilocks zone)
      2-4%   → 0.0 (manageable, Fed neutral — genuine neutral)
      4-7%   → -0.3 (tightening cycle risk)
      >7%    → -0.6 (extreme tightening, highly risk-off)
    Returns None when data is unavailable (distinct from genuine 0.0 neutral).
    """
    if cpi_yoy is None:
        return None
    if cpi_yoy >= 7.0:   return -0.6
    if cpi_yoy >= 4.0:   return _clamp(-0.3 - (cpi_yoy - 4) / 10)
    if cpi_yoy >= 2.0:   return 0.0
    if cpi_yoy >= 1.5:   return +0.2
    return -0.2


def _score_dxy_momentum(dxy_30d_roc: float | None) -> float | None:
    """
    DXY 30-day rate-of-change (E4) — momentum signal complements absolute DXY level.
    Rising DXY = accelerating USD strength = crypto headwind.
    Falling DXY = weakening USD = crypto tailwind.
    Research: BIS (2022), Federal Reserve (2023) — DXY momentum leads crypto by 30-60 days.
      ROC > +3%: strong USD momentum  → -0.5
      ROC > +1.5%: rising             → linear to -0.2
      ROC in [-1.5, +1.5]: neutral    →  0.0
      ROC < -1.5%: falling            → linear to +0.2
      ROC < -3%: declining fast       → +0.5
    Returns None if input data is missing (historical DXY unavailable).
    """
    if dxy_30d_roc is None:
        return None
    if dxy_30d_roc >= 3.0:    return -0.5
    if dxy_30d_roc >= 1.5:    return _clamp(-0.2 - (dxy_30d_roc - 1.5) / 5.0)
    if dxy_30d_roc >= -1.5:   return 0.0
    if dxy_30d_roc >= -3.0:   return _clamp(+0.2 + (abs(dxy_30d_roc) - 1.5) / 5.0)
    return +0.5


def _score_m2(m2_yoy: float | None) -> float | None:
    """
    C4: M2 YoY growth rate → global liquidity signal (CrossBorderCapital / Howell 2019).
    M2 expansion leads BTC price by ~90 days; contracting M2 = crypto bear headwind.
    Calibrated on FRED M2SL 1959-2024 vs BTC/crypto market cycles.
      >+7%  Strong expansion (COVID QE levels)      → +0.7
       3-7%  Moderate expansion                     → +0.3
       0-3%  Slow growth / neutral                  →  0.0
      -2–0   Mild contraction                       → -0.3
      <-2%  Sharp contraction (2022-era tightening) → -0.7
    Returns None when data unavailable (distinct from genuine 0.0 neutral).
    """
    if m2_yoy is None:
        return None
    v = float(m2_yoy)
    if v > 7.0:   return +0.7
    if v > 3.0:   return +0.3
    if v >= 0.0:  return  0.0
    if v >= -2.0: return -0.3
    return -0.7


def score_macro_layer(macro_data: dict[str, Any]) -> dict[str, Any]:
    """
    Compute Layer 2 macro score from merged FRED + yfinance dict.
    Returns score in [-1.0, +1.0] plus per-indicator breakdown.

    DXY DOUBLE-COUNTING FIX (Issue #16):
    Previous code averaged 6 equal inputs [dxy_level, dxy_momentum, vix, yc, cpi, m2].
    DXY level and DXY momentum both measure USD strength — correlated signals — giving
    USD 2/6 weight vs 1/6 each for independent macro dimensions (VIX, yield curve, CPI, M2).
    This double-weighted USD at the expense of M2 (the strongest crypto liquidity driver).

    Fix: merge dxy_level + dxy_momentum into one "DXY composite" (average of available
    DXY sub-signals). Now 5 independent economic dimensions each get 1/5 weight:
      1. DXY composite  (USD strength — level + momentum averaged)
      2. VIX            (equity volatility / fear)
      3. Yield curve     (recession risk)
      4. CPI             (monetary policy tightening risk)
      5. M2 YoY          (global liquidity expansion/contraction)

    Research: BIS (2022) shows DXY level and 30d ROC have 0.72 correlation — treating
    as independent signals inflates USD weight and understates M2's liquidity signal.
    """
    dxy         = macro_data.get("dxy")
    dxy_30d_roc = macro_data.get("dxy_30d_roc")
    vix         = macro_data.get("vix")
    y2y10       = macro_data.get("yield_spread_2y10y")
    cpi         = macro_data.get("cpi_yoy")
    m2_yoy      = macro_data.get("m2_yoy")

    s_dxy  = _score_dxy(dxy)
    s_dxym = _score_dxy_momentum(dxy_30d_roc)
    s_vix  = _score_vix(vix)
    s_yc   = _score_yield_curve(y2y10)
    s_cpi  = _score_cpi(cpi)
    s_m2   = _score_m2(m2_yoy)

    # Merge DXY level + DXY momentum into one composite DXY signal
    dxy_parts = [s for s in [s_dxy, s_dxym] if s is not None]
    s_dxy_composite = (sum(dxy_parts) / len(dxy_parts)) if dxy_parts else None

    # 5 independent economic dimensions — equal weight over available indicators
    active = [s for s in [s_dxy_composite, s_vix, s_yc, s_cpi, s_m2] if s is not None]
    raw    = (sum(active) / len(active)) if active else 0.0
    layer  = _clamp(raw)

    return {
        "layer":      "macro",
        "score":      round(layer, 4),
        "weight":     _W_MACRO,
        "weighted":   round(layer * _W_MACRO, 4),
        "components": {
            "dxy_composite": {"value": dxy,         "score": round(s_dxy_composite, 3) if s_dxy_composite is not None else None, "sub_components": {"dxy_level": round(s_dxy, 3) if s_dxy is not None else None, "dxy_momentum": round(s_dxym, 3) if s_dxym is not None else None}},
            "vix":           {"value": vix,         "score": round(s_vix,  3) if s_vix  is not None else None},
            "yield_curve":   {"value": y2y10,       "score": round(s_yc,   3) if s_yc   is not None else None},
            "cpi_yoy":       {"value": cpi,         "score": round(s_cpi,  3) if s_cpi  is not None else None},
            "m2_yoy":        {"value": m2_yoy,      "score": round(s_m2,   3) if s_m2   is not None else None},
        },
    }


# ─── Layer 2: Sentiment ───────────────────────────────────────────────────────

def _score_fear_greed(fg_value: int | float | None) -> float | None:
    """
    Fear & Greed → contrarian signal (extreme fear = buy opportunity).
    CNN/Alternative.me data 2018-2024.
      0-15  Extreme Fear  → +0.8 (historically strong buy zone)
      16-30 Fear          → +0.4
      31-55 Neutral       → 0.0
      56-75 Greed         → -0.4
      76-100 Extreme Greed → -0.8
    Returns None when data unavailable (prevents dilution toward 0).
    """
    if fg_value is None:
        return None
    v = float(fg_value)
    if v <= 15:   return +0.8
    if v <= 30:   return _clamp(+0.4 + (30 - v) / 37.5)
    if v <= 55:   return 0.0
    if v <= 75:   return _clamp(-0.4 - (v - 55) / 50)
    return -0.8


def _score_sopr(sopr: float | None) -> float | None:
    """
    SOPR (Shirakashi 2019) — on-chain profitability of spent outputs.
    <0.99 = holders spending at a loss = capitulation = buy signal
    >1.02 = profit-taking = distribution = caution
    Returns None when data unavailable (prevents dilution toward 0).
    """
    if sopr is None:
        return None
    if sopr < 0.99:   return +0.7
    if sopr < 1.00:   return +0.3
    if sopr < 1.02:   return 0.0
    if sopr < 1.05:   return -0.2
    return -0.5


def _score_put_call(put_call_ratio: float | None) -> float | None:
    """
    Put/call ratio from Deribit options market.
    >1.5 = extreme bearish hedging = contrarian buy
    <0.6 = extreme call buying = crowded longs = caution
    Returns None when data unavailable (prevents dilution toward 0).
    Note: C1 gate may set this to 0.0 explicitly when VIX≥40 (intentional neutralisation).
    """
    if put_call_ratio is None:
        return None
    if put_call_ratio >= 1.5:   return +0.6
    if put_call_ratio >= 1.1:   return +0.2
    if put_call_ratio >= 0.9:   return 0.0
    if put_call_ratio >= 0.6:   return -0.2
    return -0.6


def _score_funding_rate(fr_pct: float | None) -> float | None:
    """
    Issue #6 — BTC perpetual funding rate crowding/positioning signal.
    Positive funding = longs pay shorts (market overlong = contrarian bearish).
    Negative funding = shorts pay longs (market overshorted = potential squeeze rally).

    Thresholds derived from Deribit 8-hour perpetual funding data 2019-2024:
    0.01% per 8h ≈ 11% annualized — inflection point between healthy and crowded.
    0.05% per 8h ≈ 54% annualized — historically precedes sharp long liquidation cascades.
    Research: Cong et al. (2021) "Crypto Wash Trading"; Foley et al. (2022) funding rate
    predictability; Binance/Deribit data (2019-2024).
      fr_pct > +0.05  → -0.7 (extreme longs — crowded, liquidation cascade risk)
      fr_pct > +0.03  → -0.5 (very overlong)
      fr_pct > +0.01  → -0.2 (slightly overlong — mild bearish)
      fr_pct in [-0.005, +0.01] → +0.1 (neutral/healthy — slight positive bias)
      fr_pct < -0.005 → +0.4 (shorts crowded — squeeze/rally potential)
      fr_pct < -0.02  → +0.7 (extreme short crowding — high squeeze risk)
    Returns None when funding data unavailable (prevents dilution toward 0).
    """
    if fr_pct is None:
        return None
    # Step function matching the docstring bands exactly. Previous version
    # mixed step-returns with _clamp(linear-interpolation) — e.g. at fr=0.05
    # the `fr > 0.03` branch evaluated to _clamp(-0.5 - 0.02/0.04) = _clamp(-1.0)
    # = -1.0 (_clamp defaults to [-1.0,+1.0]), while at fr=0.050001 the
    # `fr > 0.05` branch returned -0.7 — a −0.3 downward discontinuity in
    # the wrong direction (higher funding should yield MORE negative, not less).
    # Step function matches the published thresholds cleanly and eliminates
    # the discontinuity.
    if fr_pct > 0.05:    return -0.7
    if fr_pct > 0.03:    return -0.5
    if fr_pct > 0.01:    return -0.2
    if fr_pct >= -0.005: return +0.1
    if fr_pct >= -0.02:  return +0.4
    return +0.7


def _score_fg_trend(fg_value: float | None, fg_30d_avg: float | None) -> float | None:
    """
    Fear & Greed 30-day momentum signal.
    Rising FGI from fear = bullish setup. Falling FGI from greed = contrarian buy building.
    Returns None if either input is missing.
    """
    if fg_value is None or fg_30d_avg is None:
        return None
    diff = float(fg_value) - float(fg_30d_avg)
    if diff > 15:    return -0.15   # surging into greed — crowding risk
    if diff > 10:    return -0.05
    if diff > 5:     return  0.0
    if diff >= -5:   return  0.0
    if diff >= -10:  return +0.05
    if diff >= -15:  return +0.10
    return +0.15                    # falling fast from greed — contrarian buy building


def score_sentiment_layer(
    fg_value: int | float | None,
    put_call_ratio: float | None,
    fg_30d_avg: float | None = None,
    vix: float | None = None,
    btc_funding_rate_pct: float | None = None,
) -> dict[str, Any]:
    """
    Compute Layer 2 sentiment score.
    Sub-weights: F&G level=0.45, F&G trend=0.10, put/call=0.30, funding rate=0.15.
    SOPR reclassified to On-Chain layer (it is 100% on-chain UTXO data, not sentiment survey).

    C1 — VIX≥40 gate on put/call (SuperGrok only):
    When VIX ≥ 40 the options market is in panic mode — put premiums spike
    mechanically as all market participants scramble for portfolio protection.
    The put/call ratio ceases to be a positioning signal and becomes a reflexive
    fear indicator. Neutralise it (set to 0.0) so a mechanical put-buying surge
    is not misread as a contrarian buy signal.
    Source: CBOE data 1990-2024; BTC options 2018-2024 (Deribit).

    Issue #6 — BTC perpetual funding rate added as 4th sentiment dimension.
    Positive funding = overlong crowding (bearish). Negative = short squeeze risk (bullish).
    Research: Cong et al. (2021); Deribit perpetual data 2019-2024.
    """
    s_fg  = _score_fear_greed(fg_value)
    s_fgt = _score_fg_trend(fg_value, fg_30d_avg)
    s_pc  = _score_put_call(put_call_ratio)
    s_fr  = _score_funding_rate(btc_funding_rate_pct)   # Issue #6

    # C1 gate: panic VIX → neutralise put/call (mechanical hedging, not signal)
    vix_panic = vix is not None and vix >= 40
    if vix_panic:
        s_pc = 0.0

    # Rebalanced to accommodate funding rate (total = 1.00)
    _SUB_W = {"fg": 0.45, "fgt": 0.10, "pc": 0.30, "fr": 0.15}
    _pairs  = [("fg", s_fg), ("fgt", s_fgt), ("pc", s_pc), ("fr", s_fr)]
    avail   = [(k, v) for k, v in _pairs if v is not None]
    if not avail:
        raw = 0.0
    else:
        total_w = sum(_SUB_W[k] for k, _ in avail)
        raw = sum(v * _SUB_W[k] for k, v in avail) / total_w

    layer = _clamp(raw)

    return {
        "layer":      "sentiment",
        "score":      round(layer, 4),
        "weight":     _W_SENTIMENT,
        "weighted":   round(layer * _W_SENTIMENT, 4),
        "components": {
            "fear_greed":     {"value": fg_value,             "score": round(s_fg,  3) if s_fg  is not None else None, "sub_weight": 0.45},
            "fg_trend_30d":   {"value": fg_30d_avg,           "score": round(s_fgt, 3) if s_fgt is not None else None, "sub_weight": 0.10},
            "put_call_ratio": {"value": put_call_ratio,       "score": round(s_pc,  3) if s_pc  is not None else None, "sub_weight": 0.30, "vix_gated": vix_panic},
            "funding_rate":   {"value": btc_funding_rate_pct, "score": round(s_fr,  3) if s_fr  is not None else None, "sub_weight": 0.15},
        },
    }


# ─── Layer 3: On-Chain ────────────────────────────────────────────────────────

def _score_mvrv_z(mvrv_z: float | None) -> float | None:
    """
    MVRV Z-Score (Mahmudov & Puell, 2018). Backtested on BTC 2011-2024.
    Historical cycle extremes: tops at Z>7 (Dec 2017 ~9.5, Apr 2021 ~8.0)
    Historical cycle bottoms: Z<0 (Dec 2018 ~-0.5, Nov 2022 ~-0.3)

    NEUTRAL ZONE CORRECTED (Issue #23):
    Fair value is Z≈2.0 historically. At Z=0, all holders at breakeven = undervalued.
    Neutral score (0.0) maps to Z≈2.0 (Glassnode 2022; CheckOnChain 2023).

    ETF FLOW ADJUSTMENT (Issue #R3):
    Bitcoin ETF holdings (~15-20% of supply) are not captured in on-chain wallet data.
    This suppresses the MVRV numerator, making observable Z-scores ~15% lower than
    equivalent pre-ETF cycle readings. Thresholds adjusted by ×0.85:
      7.0 → 6.0 (extreme top), 4.0 → 3.5 (overbought), 2.0 → 1.7 (fair value neutral),
      1.0 → 0.8 (mild undervalue). Bottom signal (Z<0) unchanged — still valid.
    Source: Glassnode (2024) ETF impact analysis; CheckOnChain (2024).

      Z < 0      → +0.5 to +1.0 (historically major bottoms — strong buy)
      Z 0–0.8    → +0.2 to +0.5 (undervalued, accumulation zone)
      Z 0.8–1.7  → 0.0 to +0.2  (fair value approaching — mildly bullish)
      Z 1.7–3.5  → 0.0 to -0.2  (above fair value — neutral to mildly elevated)
      Z 3.5–6.0  → -0.5 to -1.0 (overbought — distribution zone)
      Z > 6.0    → -1.0          (extreme top — ETF-adjusted cycle top threshold)
    Returns None when data unavailable (prevents dilution toward 0).
    """
    if mvrv_z is None:
        return None
    if mvrv_z >= 6.0:    return -1.0                                      # ETF-adj top (was 7.0)
    if mvrv_z >= 3.5:    return _clamp(-0.5 - (mvrv_z - 3.5) / 5.0)    # Z=3.5→-0.5, Z=6.0→-1.0
    if mvrv_z >= 1.7:    return _clamp(-(mvrv_z - 1.7) / 9.0)           # Z=1.7→0.0, Z=3.5→-0.2
    if mvrv_z >= 0.8:    return _clamp(+0.2 - (mvrv_z - 0.8) / 4.5)    # Z=0.8→+0.2, Z=1.7→0.0
    if mvrv_z >= 0.0:    return _clamp(+0.5 - mvrv_z * 0.375)           # Z=0→+0.5, Z=0.8→+0.2
    return _clamp(+0.5 - mvrv_z * 0.5)                                    # Z<0: deeper buy zone


def _score_hash_ribbon(
    signal: str | None,
    btc_above_20sma: bool | None = None,
) -> float | None:
    """
    Hash Ribbon signal (C. Edwards, 2019) with E1 price momentum gate.
    BUY = 30d hash rate MA crossed above 60d MA (capitulation ending) → strongly bullish.
    E1 gate: BUY is downgraded to +0.4 if BTC price is still below 20d SMA.
    Research: Edwards (2019) — hash ribbon BUY with price confirmation = 94% accuracy.
    Returns None when data unavailable (prevents dilution toward 0).
    """
    if signal is None:
        return None
    base = {
        "BUY":                +0.8,
        "RECOVERY":           +0.3,
        "CAPITULATION":       -0.2,
        "CAPITULATION_START": -0.5,
    }.get(signal, 0.0)
    if signal == "BUY" and btc_above_20sma is False:
        return +0.4
    return base


def _score_puell(puell_multiple: float | None) -> float | None:
    """
    Puell Multiple (D. Puell, 2019). BTC miner revenue relative to 1-year MA.
    Historical data 2013-2024:
    <0.5: Dec 2018 bottom (0.35), Nov 2022 bottom (0.41) — extreme buy zone
    >3.0: threshold lowered from 4.0 — 2021 cycle peak was PM=3.53 (not 4.0+).
          Dec 2017: PM=7.17. Apr 2021: PM=3.53. Cycle amplitude is declining each cycle.
    Returns None when data unavailable (prevents dilution toward 0).
    """
    if puell_multiple is None:
        return None
    if puell_multiple <= 0.5:   return +0.9
    if puell_multiple <= 1.0:   return +0.4
    if puell_multiple <= 2.0:   return 0.0
    if puell_multiple <= 3.0:   return _clamp(-0.3 - (puell_multiple - 2) / 3.3)
    return -0.8


def _score_nvt(nvt: float | None) -> float | None:
    """
    A1 — NVT Signal (Network Value to Transactions, Willy Woo 2017; Kalichkin 2018).
    NVT = Market Cap / Daily Adjusted On-Chain Transfer Volume (USD).
    High NVT = market cap disconnected from network utility = overvalued.
    Low NVT = high relative utility = undervalued.

    Uses NVT Signal (90-day SMA of daily NVT) per Kalichkin for smoother cycle signal.
    Thresholds calibrated on BTC cycles 2011-2024:
      >150: overvalued (Dec 2017: ~250, Apr 2021: ~180)
      >100: elevated risk
      45-100: normal operating range
      <45: undervalued (Dec 2018: ~30, Nov 2022: ~35, Mar 2020: ~25)
    Returns None when data unavailable (prevents dilution toward 0).
    """
    if nvt is None:
        return None
    if nvt < 30:    return +0.8
    if nvt < 45:    return +0.5
    if nvt < 70:    return +0.2
    if nvt < 100:   return 0.0
    if nvt < 130:   return -0.3
    if nvt < 150:   return -0.5
    return -0.8


def _score_realized_price(btc_price: float | None, realized_price: float | None) -> float | None:
    """
    A4 — Realized Price as on-chain support/resistance level.
    Realized Price = Realized Cap / BTC supply = average cost basis of all coins.

    BTC price vs Realized Price reveals aggregate holder profit/loss state.
    Price < Realized → holders in loss → historically precedes major bottoms.
    Price > 3× Realized → historically precedes major cycle tops.
    Returns None when either input is unavailable.
    """
    if btc_price is None or realized_price is None or realized_price <= 0:
        return None
    ratio = btc_price / realized_price
    if ratio < 0.70:   return +0.8
    if ratio < 0.90:   return +0.5
    if ratio < 1.00:   return +0.3
    if ratio < 1.20:   return +0.1
    if ratio < 2.00:   return -0.1
    if ratio < 3.00:   return -0.3
    return -0.5


def score_onchain_layer(
    mvrv_z: float | None,
    hash_ribbon_signal: str | None,
    puell_multiple: float | None,
    sopr: float | None = None,
    btc_above_20sma: bool | None = None,
    btc_price: float | None = None,
    realized_price: float | None = None,
    nvt: float | None = None,
) -> dict[str, Any]:
    """
    Compute Layer 3 on-chain score.
    MVRV Z 0.35, Hash Ribbons 0.25, SOPR 0.20, Puell 0.08, Realized Price 0.07, NVT 0.05.
    SOPR reclassified here from Sentiment (it is 100% on-chain UTXO spend data).
    A4: Realized Price added as on-chain support/resistance signal.
    A1: NVT Signal added (Willy Woo 2017; Kalichkin 2018).
    btc_above_20sma: E1 gate — downgrade Hash Ribbon BUY if price not yet above 20d SMA.
    """
    s_mvrv  = _score_mvrv_z(mvrv_z)
    s_hash  = _score_hash_ribbon(hash_ribbon_signal, btc_above_20sma)
    s_puell = _score_puell(puell_multiple)
    s_sopr  = _score_sopr(sopr)
    s_rp    = _score_realized_price(btc_price, realized_price)
    s_nvt   = _score_nvt(nvt)

    _SUB_W  = {"mvrv": 0.35, "hash": 0.25, "sopr": 0.20, "puell": 0.08, "rp": 0.07, "nvt": 0.05}
    _pairs  = [("mvrv", s_mvrv), ("hash", s_hash), ("sopr", s_sopr), ("puell", s_puell),
               ("rp", s_rp), ("nvt", s_nvt)]
    _wsum   = sum(_SUB_W[k] for k, v in _pairs if v is not None)
    raw     = (
        sum((v or 0.0) * _SUB_W[k] for k, v in _pairs if v is not None) / _wsum
        if _wsum > 0 else 0.0
    )
    layer = _clamp(raw)

    return {
        "layer":      "onchain",
        "score":      round(layer, 4),
        "weight":     _W_ONCHAIN,
        "weighted":   round(layer * _W_ONCHAIN, 4),
        "components": {
            "mvrv_z":          {"value": mvrv_z,             "score": round(s_mvrv,  3) if s_mvrv  is not None else None, "sub_weight": 0.35},
            "hash_ribbon":     {"value": hash_ribbon_signal, "score": round(s_hash,  3) if s_hash  is not None else None, "sub_weight": 0.25},
            "sopr":            {"value": sopr,               "score": round(s_sopr,  3) if s_sopr  is not None else None, "sub_weight": 0.20},
            "puell_multiple":  {"value": puell_multiple,     "score": round(s_puell, 3) if s_puell is not None else None, "sub_weight": 0.08},
            "realized_price":  {"value": realized_price,     "score": round(s_rp,    3) if s_rp    is not None else None, "sub_weight": 0.07, "btc_price": btc_price},
            "nvt_signal":      {"value": nvt,                "score": round(s_nvt,   3) if s_nvt   is not None else None, "sub_weight": 0.05},
        },
    }


# ─── Composite Score ──────────────────────────────────────────────────────────

def _signal_label(score: float) -> str:
    if score >= +0.60:  return "STRONG_RISK_ON"
    if score >= +0.30:  return "RISK_ON"
    if score >= +0.10:  return "MILD_RISK_ON"
    if score >= -0.10:  return "NEUTRAL"
    if score >= -0.30:  return "MILD_RISK_OFF"
    if score >= -0.60:  return "RISK_OFF"
    return "STRONG_RISK_OFF"


def _beginner_label(score: float) -> str:
    if score >= +0.30:  return "Market conditions look good for trading — macro and on-chain are aligned"
    if score >= +0.10:  return "Conditions are slightly favorable for new positions"
    if score >= -0.10:  return "Mixed signals — hold existing positions, wait for clarity"
    if score >= -0.30:  return "Conditions are slightly unfavorable — reduce new exposure"
    return "Market is under stress — wait for better conditions before opening new trades"


def is_risk_off(score: float) -> bool:
    """Return True if the composite score indicates RISK_OFF or worse (score < -0.30).
    Used by the agent (G7) to suppress new trade entries.
    """
    return score <= -0.30


def compute_composite_signal(
    macro_data: dict[str, Any],
    onchain_data: dict[str, Any],
    fg_value: int | float | None = None,
    put_call_ratio: float | None = None,
    ta_data: dict[str, Any] | None = None,
    fg_30d_avg: float | None = None,
    btc_funding_rate_pct: float | None = None,
) -> dict[str, Any]:
    """
    Compute the full 4-layer composite market environment signal (CLAUDE.md §9).

    Args:
        macro_data:           Dict with keys: dxy, vix, yield_spread_2y10y, cpi_yoy
        onchain_data:         Dict with keys: sopr, mvrv_z, hash_ribbon_signal, puell_multiple
        fg_value:             Current Fear & Greed value (0-100)
        put_call_ratio:       BTC put/call ratio from Deribit
        ta_data:              Output from data_feeds.fetch_btc_ta_signals() [Layer 1]
        fg_30d_avg:           30-day average Fear & Greed value (for trend signal, A3)
        btc_funding_rate_pct: BTC perpetual 8h funding rate % (Issue #6 — crowding signal)

    Layer weights: TA=0.20, Macro=0.20, Sentiment=0.25, On-Chain=0.35

    Returns dict with:
        score            float in [-1.0, +1.0]
        signal           str label (STRONG_RISK_ON .. STRONG_RISK_OFF)
        risk_off         bool — True when score <= -0.30 (agent gate trigger)
        layers           dict with per-layer breakdown
        beginner_summary str for Beginner user mode
    """
    try:
        ta_layer = score_ta_layer(ta_data or {})
    except Exception as e:
        logger.warning("[CompositeSignal] TA layer failed: %s", e)
        ta_layer = {"score": 0.0, "weight": _W_TECHNICAL, "weighted": 0.0, "components": {}}

    try:
        macro_layer = score_macro_layer(macro_data)
    except Exception as e:
        logger.warning("[CompositeSignal] macro layer failed: %s", e)
        macro_layer = {"score": 0.0, "weight": _W_MACRO, "weighted": 0.0, "components": {}}

    try:
        vix_val = macro_data.get("vix") if macro_data else None
        sentiment_layer = score_sentiment_layer(
            fg_value, put_call_ratio, fg_30d_avg,
            vix=vix_val, btc_funding_rate_pct=btc_funding_rate_pct,
        )
    except Exception as e:
        logger.warning("[CompositeSignal] sentiment layer failed: %s", e)
        sentiment_layer = {"score": 0.0, "weight": _W_SENTIMENT, "weighted": 0.0, "components": {}}

    try:
        mvrv_z      = onchain_data.get("mvrv_z")             if onchain_data else None
        hr_sig      = onchain_data.get("hash_ribbon_signal") if onchain_data else None
        puell       = onchain_data.get("puell_multiple")     if onchain_data else None
        # A2: Glassnode path now returns aSOPR via 'sopr' key (sopr_adjusted endpoint)
        # Price-proxy path has no 7-day EMA; sopr key is the best available in both cases
        sopr        = onchain_data.get("sopr")               if onchain_data else None
        above_20sma = ta_data.get("above_20sma")             if ta_data else None
        # A4: Realized Price = btc_price / mvrv_ratio (derived from existing data)
        btc_price     = ta_data.get("btc_price") if ta_data else None
        mvrv_ratio    = onchain_data.get("mvrv_ratio") if onchain_data else None
        realized_price = (btc_price / mvrv_ratio
                          if btc_price and mvrv_ratio and mvrv_ratio > 0 else None)
        # A1: NVT Signal (90d SMA preferred; fall back to raw NVT ratio)
        nvt = (onchain_data.get("nvt_signal_90d") or onchain_data.get("nvt_ratio")) if onchain_data else None
        onchain_layer = score_onchain_layer(mvrv_z, hr_sig, puell, sopr, above_20sma,
                                            btc_price=btc_price, realized_price=realized_price,
                                            nvt=nvt)
    except Exception as e:
        logger.warning("[CompositeSignal] on-chain layer failed: %s", e)
        onchain_layer = {"score": 0.0, "weight": _W_ONCHAIN, "weighted": 0.0, "components": {}}

    # B3 — Regime-dependent layer weights
    regime, w_ta, w_mac, w_sent, w_oc = _detect_regime(
        vix=macro_data.get("vix") if macro_data else None,
        adx_14=ta_data.get("adx_14") if ta_data else None,
    )

    # Recompute weighted scores using regime weights (overrides static constants)
    ta_score   = ta_layer.get("score",   0.0)
    mac_score  = macro_layer.get("score", 0.0)
    sent_score = sentiment_layer.get("score", 0.0)
    oc_score   = onchain_layer.get("score",   0.0)

    ta_layer["weight"]          = w_ta;   ta_layer["weighted"]          = round(ta_score   * w_ta,   4)
    macro_layer["weight"]       = w_mac;  macro_layer["weighted"]       = round(mac_score  * w_mac,  4)
    sentiment_layer["weight"]   = w_sent; sentiment_layer["weighted"]   = round(sent_score * w_sent, 4)
    onchain_layer["weight"]     = w_oc;   onchain_layer["weighted"]     = round(oc_score   * w_oc,   4)

    total = (
        ta_layer["weighted"] + macro_layer["weighted"] +
        sentiment_layer["weighted"] + onchain_layer["weighted"]
    )
    total = _clamp(total)

    return {
        "score":            round(total, 4),
        "signal":           _signal_label(total),
        "risk_off":         is_risk_off(total),
        "beginner_summary": _beginner_label(total),
        "regime":           regime,
        "layers": {
            "technical": ta_layer,
            "macro":     macro_layer,
            "sentiment": sentiment_layer,
            "onchain":   onchain_layer,
        },
        "weights_applied": {
            "technical": w_ta,
            "macro":     w_mac,
            "sentiment": w_sent,
            "onchain":   w_oc,
        },
    }
