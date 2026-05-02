"""tests/test_arbitrage_diagnostic_pair.py

Phase 5 audit C8 (Image 5): the Spot Spread table previously rendered
"—" in Buy On / Sell On / Buy Price / Sell Price columns whenever
signal == "NO_ARB", even when the underlying prices dict was fully
populated. Users could see "All Prices" with multiple exchange ticks
but couldn't tell where the cheapest / most expensive prices were.

The fix populates buy/sell exchange + price using min-by-ask /
max-by-bid as a non-actionable diagnostic when no profitable arb
exists. Marked with is_diagnostic=True so the UI can style differently.

These tests lock in:
1. NO_ARB return is no longer all-None for prices/exchanges.
2. Buy On = the exchange with the lowest ASK.
3. Sell On = the exchange with the highest BID.
4. is_diagnostic flag is True for NO_ARB returns.
5. is_diagnostic is absent (or falsy) for actionable arb returns.
"""
from __future__ import annotations

from unittest import mock

import pytest


def test_spot_spread_no_arb_populates_min_max_pair() -> None:
    """When no profitable arb exists, table cells should still reflect
    the min-ask exchange + max-bid exchange so the user sees price
    differential."""
    import arbitrage

    fake_prices = {
        "okx":     {"price": 60000.0, "ask": 60001.0, "bid": 59999.0},
        "kraken":  {"price": 60010.0, "ask": 60012.0, "bid": 60008.0},
        "bybit":   {"price": 59995.0, "ask": 59997.0, "bid": 59993.0},
    }
    with mock.patch.object(arbitrage, "get_spot_prices", return_value=fake_prices):
        out = arbitrage.compute_spot_spread("BTC/USDT")

    # min ask should be bybit (59997) and max bid should be kraken (60008)
    assert out["buy_exchange"] == "bybit"
    assert out["sell_exchange"] == "kraken"
    assert out["buy_price"] == pytest.approx(59997.0, abs=0.01)
    assert out["sell_price"] == pytest.approx(60008.0, abs=0.01)


def test_spot_spread_no_arb_marks_diagnostic_flag() -> None:
    """The diagnostic display must be distinguishable from an
    actionable arb. is_diagnostic=True signals 'show the cells but
    don't act on them.'"""
    import arbitrage
    fake_prices = {
        "okx":    {"price": 60000.0, "ask": 60001.0, "bid": 59999.0},
        "kraken": {"price": 60005.0, "ask": 60006.0, "bid": 60004.0},
    }
    with mock.patch.object(arbitrage, "get_spot_prices", return_value=fake_prices):
        out = arbitrage.compute_spot_spread("BTC/USDT")

    # Spread is ~0.005% which is well below MIN_NET_SPREAD_PCT after fees
    # → should be NO_ARB with diagnostic flag.
    assert out["signal"] == "NO_ARB"
    assert out.get("is_diagnostic") is True


def test_spot_spread_actionable_arb_no_diagnostic_flag() -> None:
    """When a real arb exists, the diagnostic flag should NOT be set
    (or should be falsy)."""
    import arbitrage
    fake_prices = {
        "okx":    {"price": 60000.0, "ask": 60001.0, "bid": 59999.0},
        "kraken": {"price": 60500.0, "ask": 60501.0, "bid": 60499.0},
    }
    with mock.patch.object(arbitrage, "get_spot_prices", return_value=fake_prices):
        out = arbitrage.compute_spot_spread("BTC/USDT")

    assert out["signal"] in ("OPPORTUNITY", "MARGINAL")
    assert not out.get("is_diagnostic", False)


def test_spot_spread_single_exchange_returns_diagnostic() -> None:
    """With only one exchange we can still surface the price for that
    one but cannot compute buy != sell. Test that it returns a stable
    shape (no crash) and signal NO_ARB."""
    import arbitrage
    fake_prices = {
        "okx": {"price": 60000.0, "ask": 60001.0, "bid": 59999.0},
    }
    with mock.patch.object(arbitrage, "get_spot_prices", return_value=fake_prices):
        out = arbitrage.compute_spot_spread("BTC/USDT")

    assert out["signal"] == "NO_ARB"
    # Single-exchange diagnostic still has the diagnostic marker.
    assert out.get("is_diagnostic") is True
