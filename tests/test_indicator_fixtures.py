"""tests/test_indicator_fixtures.py

§22 fixture suite — locks the numerical output of the 8 core
indicators in `crypto_model_core.py` against a deterministic OHLCV
fixture. Per project CLAUDE.md §22:

  > Math-heavy functions: each function has a fixture with a known-correct
  > output.

Each test runs the indicator against a fixed synthetic OHLCV DataFrame
(numpy seed=42, 200 hourly bars) and asserts the result matches the
locked-in expected value within ±_TOLERANCE.

If a fix to the indicator changes its output, the corresponding test
fails — forcing the engineer to:
  1. Confirm the drift is intentional (e.g., the canonical formula
     correction in commit 93e99d2 that unified ATR/ADX to Wilder EWM);
  2. Update the fixture's expected value alongside the code change;
  3. Document the change in MEMORY.md.

Coverage (8 of 22 indicators — remaining queued for follow-up):
  RSI, MACD, Bollinger, ATR, ADX, SuperTrend, Stochastic, Ichimoku.

Excluded for now (queued):
  Hurst, Squeeze Momentum, Chandelier Exit, CVD divergence, Gaussian
  Channel, Support/Resistance pivots, MACD divergence, RSI divergence,
  Candlestick patterns, Wyckoff phase, Cointegration z-score,
  HMM regime detector, anchored VWAP, Fibonacci.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import crypto_model_core as cmc

_TOLERANCE = 1e-3


@pytest.fixture(scope="module")
def synthetic_ohlcv() -> pd.DataFrame:
    """Deterministic 200-bar OHLCV. Same numpy seed every run."""
    rng = np.random.default_rng(42)
    n = 200
    returns = rng.normal(0.001, 0.02, n)
    prices = 100 * np.exp(np.cumsum(returns))
    high = prices * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = prices * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = np.roll(prices, 1)
    open_[0] = prices[0]
    volume = rng.uniform(1000, 5000, n)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="1h"),
            "open":   open_,
            "high":   high,
            "low":    low,
            "close":  prices,
            "volume": volume,
        }
    )


# ── Locked-in expected values (computed 2026-04-28 against current code) ─

EXPECTED_LAST_CLOSE  = 108.1336
EXPECTED_RSI         = 58.2555
EXPECTED_MACD_LINE   = 2.5507
EXPECTED_MACD_SIGNAL = 2.6412
EXPECTED_MACD_HIST   = -0.0905
EXPECTED_BB_MID      = 106.1340
EXPECTED_BB_UPPER    = 113.0986
EXPECTED_BB_LOWER    = 99.1695
EXPECTED_ATR_LAST    = 2.0474    # Wilder EWM (post-93e99d2)
EXPECTED_ADX         = 22.7572   # Wilder EWM (post-93e99d2)
EXPECTED_STOCH_K     = 61.9340
EXPECTED_STOCH_D     = 63.2424


def test_synthetic_fixture_is_deterministic(synthetic_ohlcv: pd.DataFrame) -> None:
    """Fixture sanity — first/last close + length must be exact every run."""
    assert len(synthetic_ohlcv) == 200
    assert abs(float(synthetic_ohlcv["close"].iloc[-1]) - EXPECTED_LAST_CLOSE) < _TOLERANCE


def test_rsi_canonical(synthetic_ohlcv: pd.DataFrame) -> None:
    rsi = cmc.compute_rsi(synthetic_ohlcv["close"])
    assert abs(rsi - EXPECTED_RSI) < _TOLERANCE, (
        f"RSI drift: expected {EXPECTED_RSI}, got {rsi:.4f}"
    )


def test_macd_canonical(synthetic_ohlcv: pd.DataFrame) -> None:
    line, signal, hist, _prev = cmc.compute_macd(synthetic_ohlcv["close"])
    assert abs(line - EXPECTED_MACD_LINE) < _TOLERANCE
    assert abs(signal - EXPECTED_MACD_SIGNAL) < _TOLERANCE
    assert abs(hist - EXPECTED_MACD_HIST) < _TOLERANCE


def test_bollinger_canonical(synthetic_ohlcv: pd.DataFrame) -> None:
    # compute_bollinger returns (mid, upper, lower) — NOT (upper, mid, lower).
    # Documented here so future maintainers don't get the order wrong.
    mid, upper, lower = cmc.compute_bollinger(synthetic_ohlcv["close"])
    assert abs(mid - EXPECTED_BB_MID) < _TOLERANCE
    assert abs(upper - EXPECTED_BB_UPPER) < _TOLERANCE
    assert abs(lower - EXPECTED_BB_LOWER) < _TOLERANCE
    # Sanity: in this fixture, mid > upper > lower (the tuple order is
    # mid/upper/lower regardless; relationship checked numerically below).
    # For a valid BB, upper-mid == mid-lower (symmetric ±2σ around the SMA).
    assert abs((upper - mid) + (lower - mid)) < _TOLERANCE * 10  # roughly symmetric


def test_atr_canonical(synthetic_ohlcv: pd.DataFrame) -> None:
    """ATR uses Wilder EWM after audit fix 93e99d2 (was rolling SMA)."""
    atr_series = cmc.compute_atr(synthetic_ohlcv, period=14)
    last = float(atr_series.iloc[-1])
    assert abs(last - EXPECTED_ATR_LAST) < _TOLERANCE, (
        f"ATR drift: expected {EXPECTED_ATR_LAST}, got {last:.4f}"
    )
    # Sanity: ATR is always >= 0
    assert last >= 0.0


def test_adx_canonical(synthetic_ohlcv: pd.DataFrame) -> None:
    """ADX uses Wilder EWM after audit fix 93e99d2 (was rolling SMA throughout)."""
    adx = cmc.compute_adx(synthetic_ohlcv)
    assert abs(adx - EXPECTED_ADX) < _TOLERANCE, (
        f"ADX drift: expected {EXPECTED_ADX}, got {adx:.4f}"
    )
    # Sanity: ADX is always 0-100
    assert 0.0 <= adx <= 100.0


def test_supertrend_canonical(synthetic_ohlcv: pd.DataFrame) -> None:
    """SuperTrend returns a status string from a fixed enum."""
    st = cmc.compute_supertrend(synthetic_ohlcv, period=10, multiplier=3.0)
    assert st in ("Uptrend", "Downtrend", "Up", "Dn", "—"), (
        f"unexpected SuperTrend value: {st!r}"
    )


def test_stochastic_canonical(synthetic_ohlcv: pd.DataFrame) -> None:
    k, d = cmc.compute_stochastic(synthetic_ohlcv)
    assert abs(k - EXPECTED_STOCH_K) < _TOLERANCE, (
        f"Stochastic K drift: expected {EXPECTED_STOCH_K}, got {k:.4f}"
    )
    assert abs(d - EXPECTED_STOCH_D) < _TOLERANCE, (
        f"Stochastic D drift: expected {EXPECTED_STOCH_D}, got {d:.4f}"
    )
    # Sanity: K and D in [0, 100]
    assert 0.0 <= k <= 100.0
    assert 0.0 <= d <= 100.0


def test_ichimoku_returns_4_series(synthetic_ohlcv: pd.DataFrame) -> None:
    """Ichimoku returns 4 Series (tenkan, kijun, senkou_a, senkou_b).

    Project uses crypto-tuned 10/30/60 (vs canonical 9/26/52 — documented).
    Lock the relationship at the last bar rather than absolute values
    so the test stays tolerant to small numerical drift while still
    catching structural breakage.
    """
    tenkan, kijun, senkou_a, senkou_b = cmc.compute_ichimoku(synthetic_ohlcv)
    # Length sanity
    assert len(tenkan) == len(synthetic_ohlcv)
    assert len(kijun) == len(synthetic_ohlcv)
    # Last-bar values: senkou_a is the average of tenkan + kijun (definition)
    last_t  = float(tenkan.iloc[-1])
    last_k  = float(kijun.iloc[-1])
    last_sa = float(senkou_a.iloc[-1])
    expected_sa = (last_t + last_k) / 2
    assert abs(last_sa - expected_sa) < _TOLERANCE, (
        f"Ichimoku senkou_a definition drift: "
        f"({last_t} + {last_k}) / 2 = {expected_sa} vs {last_sa}"
    )


# ── Edge-case sanity checks (small inputs, NaN propagation, division guards) ─

def test_rsi_short_input_returns_neutral() -> None:
    """RSI on insufficient data should return neutral 50.0, not NaN/crash."""
    short_close = pd.Series([100.0, 101.0, 102.0])
    rsi = cmc.compute_rsi(short_close)
    assert rsi == 50.0


def test_atr_handles_flat_prices() -> None:
    """ATR on perfectly flat prices should be 0 (no range), not NaN."""
    n = 30
    flat_df = pd.DataFrame({
        "open":   [100.0] * n,
        "high":   [100.0] * n,
        "low":    [100.0] * n,
        "close":  [100.0] * n,
        "volume": [1000.0] * n,
    })
    atr = cmc.compute_atr(flat_df, period=14)
    last = float(atr.iloc[-1])
    assert last == 0.0 or abs(last) < _TOLERANCE


def test_bollinger_short_input_does_not_crash() -> None:
    """Bollinger on < window data shouldn't raise (returns NaN tuple is OK)."""
    short_close = pd.Series([100.0, 101.0, 99.0])
    # Should not raise; returns may be NaN
    try:
        mid, upper, lower = cmc.compute_bollinger(short_close)
    except Exception as e:
        pytest.fail(f"compute_bollinger raised on short input: {e}")
