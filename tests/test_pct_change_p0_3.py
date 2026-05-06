"""P0-3 (Phase 0.9 audit) regression test for the price-delta helper
embedded inside `_scan_pair`.

The helper itself is a closure inside crypto_model_core.py:_scan_pair, so
this test re-implements the same logic locally and asserts the
properties we care about. If the implementation drifts, update both.
"""
import pandas as pd


def _pct_change_from_frame(_df, _bars_back):
    """Mirror of crypto_model_core.py:_pct_change_from_frame (P0-3)."""
    if _df is None or len(_df) <= _bars_back:
        return None
    try:
        _now = float(_df["close"].iloc[-1])
        _then = float(_df["close"].iloc[-1 - _bars_back])
        if _then <= 0:
            return None
        return round((_now - _then) / _then * 100.0, 2)
    except Exception:
        return None


def _frame(closes):
    return pd.DataFrame({"close": closes})


def test_pct_change_simple_up():
    df = _frame([100.0, 110.0])
    assert _pct_change_from_frame(df, 1) == 10.0


def test_pct_change_simple_down():
    df = _frame([100.0, 80.0])
    assert _pct_change_from_frame(df, 1) == -20.0


def test_pct_change_24h_window():
    # 25 bars: index 0..24, last=110, [-25]=100 → +10%
    df = _frame([100.0] + [105.0] * 23 + [110.0])
    assert _pct_change_from_frame(df, 24) == 10.0


def test_pct_change_handles_short_history():
    # Only 5 bars; can't look 30 back
    df = _frame([100.0, 101.0, 102.0, 103.0, 104.0])
    assert _pct_change_from_frame(df, 30) is None


def test_pct_change_handles_empty():
    assert _pct_change_from_frame(_frame([]), 1) is None


def test_pct_change_handles_none():
    assert _pct_change_from_frame(None, 1) is None


def test_pct_change_handles_zero_then():
    # If the historical close was 0 (broken fetch), don't divide-by-zero
    df = _frame([0.0, 100.0])
    assert _pct_change_from_frame(df, 1) is None


def test_pct_change_rounds_to_2_decimals():
    df = _frame([100.0, 100.123456])
    assert _pct_change_from_frame(df, 1) == 0.12
