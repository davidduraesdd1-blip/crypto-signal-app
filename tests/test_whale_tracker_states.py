"""tests/test_whale_tracker_states.py

Phase 2 audit C12 (Image 8): whale tracker now reports tracker_status
disambiguating offline / live-quiet / not-supported / no-price.
Previous implementation only returned a single 'NEUTRAL' signal that
the page rendered as the ambiguous "no transfers OR offline" copy
regardless of actual state.

Tests lock in:
- _NEUTRAL_RESULT carries tracker_status='live' (used when no chain
  is configured but result is still synthesized cleanly).
- _synthesize_signal returns events list (was discarded).
- get_whale_activity sets tracker_status='not_supported' for unknown
  chains, 'no_price' when price=0, 'offline' when fetch raises,
  'live' when fetch succeeds (with or without events).
"""
from __future__ import annotations

from unittest import mock


def test_neutral_result_includes_events_and_status() -> None:
    """The neutral result template must carry the new fields."""
    import whale_tracker
    nr = whale_tracker._NEUTRAL_RESULT
    assert "events" in nr
    assert isinstance(nr["events"], list)
    assert "tracker_status" in nr


def test_synthesize_signal_returns_events() -> None:
    """_synthesize_signal must include the moves list it consumed."""
    import whale_tracker
    moves = [
        {"direction": "accumulation", "amount_usd": 6_000_000, "timestamp": "t1", "symbol": "BTC"},
        {"direction": "distribution", "amount_usd": 4_000_000, "timestamp": "t2", "symbol": "BTC"},
    ]
    out = whale_tracker._synthesize_signal(moves)
    assert "events" in out
    assert len(out["events"]) == 2
    assert out["tracker_status"] == "live"


def test_unknown_chain_marks_not_supported() -> None:
    import whale_tracker
    whale_tracker._cache.clear()
    out = whale_tracker.get_whale_activity("FOO/USDT", price_usd=100.0)
    assert out["tracker_status"] == "not_supported"


def test_zero_price_marks_no_price() -> None:
    """If price_usd=0 and CoinGecko fallback fails, tracker should
    report no_price, not pretend to be live."""
    import whale_tracker
    whale_tracker._cache.clear()

    fake_resp = mock.Mock()
    fake_resp.json.return_value = {}  # no price returned
    with mock.patch.object(whale_tracker._SESSION, "get", return_value=fake_resp):
        out = whale_tracker.get_whale_activity("BTC/USDT", price_usd=0.0)
    assert out["tracker_status"] == "no_price"


def test_fetch_exception_marks_offline() -> None:
    """When the chain fetcher raises, get_whale_activity should mark
    tracker_status='offline' (so the UI renders 'tracker offline' not
    'no transfers in 24h')."""
    import whale_tracker
    whale_tracker._cache.clear()
    with mock.patch.object(whale_tracker, "_fetch_btc_whales",
                           side_effect=RuntimeError("API down")):
        out = whale_tracker.get_whale_activity("BTC/USDT", price_usd=60000.0)
    assert out["tracker_status"] == "offline"


def test_successful_fetch_with_no_moves_marks_live() -> None:
    """When fetcher succeeds but returns 0 transfers, status is
    'live' (tracker is up; window is just genuinely quiet)."""
    import whale_tracker
    whale_tracker._cache.clear()
    with mock.patch.object(whale_tracker, "_fetch_btc_whales", return_value=[]):
        out = whale_tracker.get_whale_activity("BTC/USDT", price_usd=60000.0)
    assert out["tracker_status"] == "live"
    assert out["whale_count"] == 0
