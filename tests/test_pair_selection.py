"""
C3 verification (Phase C plan §C3): pair-selection affordances.

Acceptance:
  - All 4 components write session_state on first click (callback pattern).
  - on_select / on_swap / on_save callbacks fire with the right value.
  - pair_dropdown surfaces the first 5 as quick pills + the rest behind
    the popover with a +N count.
  - ticker_pill_button is a per-instance widget (independent slots).
  - watchlist_customize_btn round-trips: scratch → save → session_state.
  - multi_timeframe_strip honours the optional signals dict.
"""
from __future__ import annotations

import pytest


# ── Fake Streamlit harness (extends the C2 pattern) ──────────────────────

class _FakeColumn:
    def __enter__(self): return self
    def __exit__(self, *exc): return False


class _FakePopover:
    def __init__(self):
        self._returns: list = []

    def __enter__(self): return self
    def __exit__(self, *exc): return False


class _FakeSt:
    def __init__(self):
        self.session_state: dict = {}
        self.markdown_calls: list[tuple[str, dict]] = []
        self.button_calls: list[dict] = []
        self.checkbox_calls: list[dict] = []
        self.popover_labels: list[str] = []
        self.text_input_calls: list[dict] = []

    def markdown(self, body: str, **kwargs):
        self.markdown_calls.append((body, kwargs))

    def caption(self, body: str, **kwargs):
        pass

    def columns(self, n):
        if isinstance(n, list):
            n = len(n)
        return [_FakeColumn() for _ in range(n)]

    def button(self, label, *, key, on_click=None, args=(), **kwargs):
        self.button_calls.append({
            "label": label, "key": key, "on_click": on_click,
            "args": args, "kwargs": kwargs,
        })
        return False

    def checkbox(self, label, *, value=False, key, **kwargs):
        self.checkbox_calls.append({"label": label, "key": key, "value": value})
        # Return whatever was last set in session_state for this key
        # (or the initial value), so the helper's mid-edit toggle path
        # exercises the "user toggled" branch when we override.
        return self.session_state.get(key, value)

    def popover(self, label, **kwargs):
        self.popover_labels.append(label)
        return _FakePopover()

    def text_input(self, label, *, key, **kwargs):
        self.text_input_calls.append({"label": label, "key": key})
        return ""


@pytest.fixture
def fake_streamlit(monkeypatch):
    import ui.sidebar as sidebar_mod
    fake = _FakeSt()
    monkeypatch.setattr(sidebar_mod, "st", fake)
    return fake


# ── pair_dropdown ────────────────────────────────────────────────────────

UNIVERSE_33 = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT",
    "BNB/USDT", "TRX/USDT", "ADA/USDT", "BCH/USDT", "LINK/USDT",
    "LTC/USDT", "AVAX/USDT", "XLM/USDT", "SUI/USDT", "TAO/USDT",
    "NEAR/USDT", "APT/USDT", "POL/USDT", "OP/USDT", "ARB/USDT",
    "ATOM/USDT", "FIL/USDT", "INJ/USDT", "PENDLE/USDT", "WIF/USDT",
    "PYTH/USDT", "JUP/USDT", "HBAR/USDT", "FLR/USDT", "CC/USDT",
    "XDC/USDT", "SHX/USDT", "ZBCN/USDT",
]


def test_pair_dropdown_quick_pills_are_first_5(fake_streamlit):
    from ui.sidebar import pair_dropdown
    pair_dropdown(UNIVERSE_33, active="BTC/USDT", key="pair")
    quick_labels = [b["label"] for b in fake_streamlit.button_calls
                    if b["key"].startswith("_pdpd_quick_pair_")]
    assert quick_labels == ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"]


def test_pair_dropdown_more_label_shows_remaining_count(fake_streamlit):
    from ui.sidebar import pair_dropdown
    pair_dropdown(UNIVERSE_33, active="BTC/USDT", key="pair")
    # 33 total - 5 quick = 28 in the popover.
    assert any("+28" in lbl for lbl in fake_streamlit.popover_labels), (
        "pair_dropdown popover trigger should advertise the remaining "
        "pair count (e.g. 'More ▾  +28' for a 33-pair universe)."
    )


def test_pair_dropdown_first_click_writes_session_state(fake_streamlit):
    from ui.sidebar import pair_dropdown
    pair_dropdown(UNIVERSE_33, active="BTC/USDT", key="pair")
    eth_btn = next(b for b in fake_streamlit.button_calls
                   if b["label"] == "ETH/USDT" and b["key"].startswith("_pdpd_quick_"))
    eth_btn["on_click"](*eth_btn["args"])
    assert fake_streamlit.session_state["pair"] == "ETH/USDT"


def test_pair_dropdown_invalid_active_falls_back(fake_streamlit):
    from ui.sidebar import pair_dropdown
    # Should not raise.
    pair_dropdown(UNIVERSE_33, active="ZZZ/USDT", key="pair")
    types = {b["label"]: b["kwargs"].get("type")
             for b in fake_streamlit.button_calls
             if b["key"].startswith("_pdpd_quick_")}
    # First quick (BTC) becomes the fallback active = primary.
    assert types["BTC/USDT"] == "primary"


def test_pair_dropdown_on_select_callback_fires(fake_streamlit):
    from ui.sidebar import pair_dropdown
    received: list[str] = []
    pair_dropdown(UNIVERSE_33, active="BTC/USDT", key="pair",
                  on_select=lambda v: received.append(v))
    sol_btn = next(b for b in fake_streamlit.button_calls
                   if b["label"] == "SOL/USDT" and b["key"].startswith("_pdpd_quick_"))
    sol_btn["on_click"](*sol_btn["args"])
    assert received == ["SOL/USDT"]


# ── ticker_pill_button ────────────────────────────────────────────────────

def test_ticker_pill_button_renders_each_pair_in_popover(fake_streamlit):
    from ui.sidebar import ticker_pill_button
    pairs = ["BTC", "ETH", "SOL"]
    ticker_pill_button("BTC", pairs=pairs, key="card1_ticker")
    labels = [b["label"] for b in fake_streamlit.button_calls
              if b["key"].startswith("_tpb_card1_ticker_")]
    assert labels == pairs


def test_ticker_pill_button_swap_writes_session_state(fake_streamlit):
    from ui.sidebar import ticker_pill_button
    pairs = ["BTC", "ETH", "SOL"]
    ticker_pill_button("BTC", pairs=pairs, key="card1_ticker")
    eth_btn = next(b for b in fake_streamlit.button_calls
                   if b["label"] == "ETH" and b["key"].startswith("_tpb_card1_ticker_"))
    eth_btn["on_click"](*eth_btn["args"])
    assert fake_streamlit.session_state["card1_ticker"] == "ETH"


def test_ticker_pill_button_instances_are_independent(fake_streamlit):
    """Card 1 and card 2 each have their own session_state slot — a
    swap on card 1 must not move card 2."""
    from ui.sidebar import ticker_pill_button
    pairs = ["BTC", "ETH", "SOL"]
    ticker_pill_button("BTC", pairs=pairs, key="card1")
    ticker_pill_button("SOL", pairs=pairs, key="card2")

    eth_card1 = next(b for b in fake_streamlit.button_calls
                     if b["label"] == "ETH" and b["key"].startswith("_tpb_card1_"))
    eth_card1["on_click"](*eth_card1["args"])

    assert fake_streamlit.session_state["card1"] == "ETH"
    assert "card2" not in fake_streamlit.session_state, (
        "ticker_pill_button instances must not share session_state — "
        "card1 swap leaked into card2."
    )


# ── watchlist_customize_btn ──────────────────────────────────────────────

def test_watchlist_customize_btn_seeds_session_state_from_current(fake_streamlit):
    from ui.sidebar import watchlist_customize_btn
    watchlist_customize_btn(
        available=["BTC", "ETH", "SOL", "AVAX"],
        current=["BTC", "ETH"],
        key="wl",
    )
    # session_state seeded from `current` on first render.
    assert fake_streamlit.session_state["wl"] == ["BTC", "ETH"]


def test_watchlist_customize_btn_save_callback_uses_scratch(fake_streamlit):
    from ui.sidebar import watchlist_customize_btn
    received: list[list] = []

    fake_streamlit.session_state["_wclb_scratch_wl"] = ["BTC", "ETH", "SOL"]

    watchlist_customize_btn(
        available=["BTC", "ETH", "SOL", "AVAX"],
        current=["BTC", "ETH"],
        key="wl",
        on_save=lambda lst: received.append(list(lst)),
    )
    save_btn = next(b for b in fake_streamlit.button_calls
                    if b["key"] == "_wclb_save_wl")
    save_btn["on_click"]()
    assert fake_streamlit.session_state["wl"] == ["BTC", "ETH", "SOL"]
    assert received == [["BTC", "ETH", "SOL"]]


# ── multi_timeframe_strip ────────────────────────────────────────────────

def test_multi_timeframe_strip_renders_all_timeframes(fake_streamlit):
    from ui.sidebar import multi_timeframe_strip
    multi_timeframe_strip(["1h", "4h", "1d", "1w"], active="1d", key="tf")
    labels = [b["label"] for b in fake_streamlit.button_calls
              if b["key"].startswith("_tfs_tf_")]
    assert labels == ["1h", "4h", "1d", "1w"]


def test_multi_timeframe_strip_active_is_primary(fake_streamlit):
    from ui.sidebar import multi_timeframe_strip
    multi_timeframe_strip(["1h", "4h", "1d", "1w"], active="4h", key="tf")
    types = {b["label"]: b["kwargs"].get("type")
             for b in fake_streamlit.button_calls
             if b["key"].startswith("_tfs_tf_")}
    assert types["4h"] == "primary"
    assert types["1d"] == "secondary"


def test_multi_timeframe_strip_signals_decorate_label(fake_streamlit):
    from ui.sidebar import multi_timeframe_strip
    multi_timeframe_strip(
        ["1h", "4h", "1d", "1w"],
        active="1d", key="tf",
        signals={"1h": ("BUY", 78.0), "1d": ("SELL", 42.0)},
    )
    by_label = {b["label"]: b for b in fake_streamlit.button_calls
                if b["key"].startswith("_tfs_tf_")}
    # Decorated cells have a newline + signal · score
    assert "1h\nBUY · 78" in by_label
    assert "1d\nSELL · 42" in by_label
    # Cells without signal stay bare
    assert "4h" in by_label


def test_multi_timeframe_strip_first_click_writes_session_state(fake_streamlit):
    from ui.sidebar import multi_timeframe_strip
    multi_timeframe_strip(["1h", "4h", "1d", "1w"], active="1d", key="tf")
    btn_4h = next(b for b in fake_streamlit.button_calls
                  if b["label"] == "4h" and b["key"].startswith("_tfs_tf_"))
    btn_4h["on_click"](*btn_4h["args"])
    assert fake_streamlit.session_state["tf"] == "4h"


# ── C-fix-04: canonical 8-cell strip + disabled-cell behaviour ──────────

def test_canonical_timeframes_is_eight_cells_in_mockup_order():
    """C-fix-04 (2026-05-01): the canonical timeframe set must be the 8
    cells specified in docs/mockups/sibling-family-crypto-signal-SIGNALS.html
    in display order. Any reorder risks breaking visual parity."""
    from ui.sidebar import CANONICAL_TIMEFRAMES
    assert CANONICAL_TIMEFRAMES == (
        "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w",
    )


def test_multi_timeframe_strip_default_renders_eight_cells(fake_streamlit):
    """C-fix-04: with no `timeframes` argument, the strip falls back to
    the canonical 8-cell set (matches the Signals mockup spec)."""
    from ui.sidebar import multi_timeframe_strip
    multi_timeframe_strip(active="1d", key="tf")
    labels = [b["label"] for b in fake_streamlit.button_calls
              if b["key"].startswith("_tfs_tf_")]
    assert labels == ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]


def test_multi_timeframe_strip_disabled_cells_render_disabled(fake_streamlit):
    """C-fix-04: cells in `timeframes` but not in `enabled_timeframes`
    render with disabled=True so the user can see the full spec but
    can't click into a timeframe the engine isn't scanning."""
    from ui.sidebar import multi_timeframe_strip, CANONICAL_TIMEFRAMES
    multi_timeframe_strip(
        list(CANONICAL_TIMEFRAMES),
        active="1d",
        key="tf",
        enabled_timeframes=["1h", "4h", "1d", "1w"],
    )
    by_label = {b["label"]: b for b in fake_streamlit.button_calls
                if b["key"].startswith("_tfs_tf_")}
    # Engine-scanned cells are enabled
    for tf in ("1h", "4h", "1d", "1w"):
        assert by_label[tf]["kwargs"].get("disabled") is False, (
            f"{tf} is in enabled_timeframes but rendered disabled"
        )
    # Cells outside the enabled set are disabled
    for tf in ("1m", "5m", "15m", "30m"):
        assert by_label[tf]["kwargs"].get("disabled") is True, (
            f"{tf} is NOT in enabled_timeframes — must render disabled"
        )


def test_multi_timeframe_strip_disabled_click_is_noop(fake_streamlit):
    """C-fix-04: even if Streamlit's disabled attribute fails (browser
    bug, accessibility tooling), the on_click handler must guard against
    a disabled-cell click writing a non-scannable timeframe to session
    state."""
    from ui.sidebar import multi_timeframe_strip, CANONICAL_TIMEFRAMES
    fake_streamlit.session_state["tf"] = "1d"
    multi_timeframe_strip(
        list(CANONICAL_TIMEFRAMES),
        active="1d",
        key="tf",
        enabled_timeframes=["1h", "4h", "1d", "1w"],
    )
    btn_1m = next(b for b in fake_streamlit.button_calls
                  if b["label"] == "1m" and b["key"].startswith("_tfs_tf_"))
    btn_1m["on_click"](*btn_1m["args"])
    # Click was a no-op — session state still on 1d
    assert fake_streamlit.session_state["tf"] == "1d"


def test_multi_timeframe_strip_active_outside_enabled_falls_back(fake_streamlit):
    """C-fix-04: if the caller passes `active="1m"` but the engine isn't
    scanning 1m, the strip must fall back to a real enabled timeframe
    (preferring 1d) so downstream data fetches don't pull empty results."""
    from ui.sidebar import multi_timeframe_strip, CANONICAL_TIMEFRAMES
    out = multi_timeframe_strip(
        list(CANONICAL_TIMEFRAMES),
        active="1m",  # not in enabled set
        key="tf",
        enabled_timeframes=["1h", "4h", "1d", "1w"],
    )
    # The function returns whatever's in session_state, but the
    # rendered active cell must be 1d (preferred fallback).
    by_label = {b["label"]: b for b in fake_streamlit.button_calls
                if b["key"].startswith("_tfs_tf_")}
    assert by_label["1d"]["kwargs"].get("type") == "primary"
