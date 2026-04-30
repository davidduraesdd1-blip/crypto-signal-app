"""
C2 verification (Phase C plan §C2): segmented_control component.

Acceptance criteria from the plan:
  1. Clicking an item updates session_state on FIRST click (no two-click
     lag — same trap that caused the H5 sidebar bug).
  2. on_select callback fires with the correct value when supplied.
  3. Visual: matches `.seg-ctrl` and `.seg-ctrl-sm` from
     docs/mockups/sibling-family-crypto-signal-BACKTESTER.html. Visual
     parity is verified manually on Streamlit Cloud per the per-batch
     cadence; this test file covers the behavioural + structural
     guarantees.
"""
from __future__ import annotations

import inspect

import pytest


# ── Fake Streamlit harness ────────────────────────────────────────────────

class _FakeSt:
    """Minimal stand-in for `streamlit` exposing only what
    segmented_control touches (session_state + button + columns +
    markdown). Lets us drive the on_click callback directly without
    spinning up a real runtime."""

    def __init__(self):
        self.session_state: dict = {}
        self.markdown_calls: list[tuple[str, dict]] = []
        self.button_calls: list[dict] = []

    # No-op renderers — segmented_control writes via the on_click cb.
    def markdown(self, body: str, **kwargs):
        self.markdown_calls.append((body, kwargs))

    def columns(self, n):  # noqa: D401 — match streamlit shape
        return [_FakeColumn() for _ in range(n)]

    def button(self, label, *, key, on_click=None, args=(), **kwargs):
        # Record the call for assertion-by-introspection.
        self.button_calls.append({
            "label": label, "key": key, "on_click": on_click,
            "args": args, "kwargs": kwargs,
        })
        # NB: we do NOT auto-fire on_click here — the test triggers it
        # manually so we control timing (mirrors Streamlit's actual
        # behaviour: callbacks fire at user-click time, not render time).
        return False


class _FakeColumn:
    """Tiny `with col:` context for the fake harness."""
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_streamlit(monkeypatch):
    import ui.sidebar as sidebar_mod
    fake = _FakeSt()
    monkeypatch.setattr(sidebar_mod, "st", fake)
    return fake


# ── Acceptance #1: first-click updates session_state ─────────────────────

def test_first_click_writes_session_state(fake_streamlit):
    from ui.sidebar import segmented_control

    items = [("backtest", "Backtest"), ("arbitrage", "Arbitrage")]
    segmented_control(items, active="backtest", key="bt_view")

    # Two buttons rendered, one per item.
    assert len(fake_streamlit.button_calls) == 2

    # Find the Arbitrage button's on_click closure.
    arb = next(b for b in fake_streamlit.button_calls if b["label"] == "Arbitrage")
    assert callable(arb["on_click"])
    assert arb["args"] == ("arbitrage",)

    # Fire the callback as Streamlit would on user click. The test passes
    # only if session_state is updated SYNCHRONOUSLY — i.e. before any
    # subsequent re-render. That's the contract that prevents the two-
    # click highlight bug.
    arb["on_click"](*arb["args"])
    assert fake_streamlit.session_state["bt_view"] == "arbitrage"


def test_active_segment_renders_as_primary_button(fake_streamlit):
    """The currently-active value's button must use type='primary' so
    the CSS overrides paint it as the filled chip. Other segments stay
    type='secondary'."""
    from ui.sidebar import segmented_control

    items = [("a", "A"), ("b", "B"), ("c", "C")]
    segmented_control(items, active="b", key="seg_x")

    types = {b["label"]: b["kwargs"].get("type") for b in fake_streamlit.button_calls}
    assert types == {"A": "secondary", "B": "primary", "C": "secondary"}


# ── Acceptance #2: on_select callback fires with correct value ───────────

def test_on_select_callback_receives_clicked_value(fake_streamlit):
    from ui.sidebar import segmented_control

    received: list[str] = []

    def cb(value: str) -> None:
        received.append(value)

    items = [("summary", "Summary"), ("trades", "Trade History"), ("adv", "Advanced")]
    segmented_control(items, active="summary", key="sub_view",
                      on_select=cb, variant="small")

    # Trigger the Trade History button's on_click.
    th = next(b for b in fake_streamlit.button_calls if b["label"] == "Trade History")
    th["on_click"](*th["args"])

    assert received == ["trades"]
    assert fake_streamlit.session_state["sub_view"] == "trades"


def test_on_select_failure_does_not_crash_widget(fake_streamlit):
    """A buggy caller callback must not propagate out of the widget —
    the segmented control is a UI primitive and must remain robust."""
    from ui.sidebar import segmented_control

    def crash(_: str) -> None:
        raise RuntimeError("caller bug")

    items = [("a", "A"), ("b", "B")]
    segmented_control(items, active="a", key="k", on_select=crash)
    btn_b = next(b for b in fake_streamlit.button_calls if b["label"] == "B")
    # The session_state write happens BEFORE on_select runs, so even
    # if the callback raises, session_state must reflect the click.
    btn_b["on_click"](*btn_b["args"])
    assert fake_streamlit.session_state["k"] == "b"


# ── Variant marker class on the marker div ───────────────────────────────

def test_primary_variant_emits_ds_seg_ctrl_marker(fake_streamlit):
    from ui.sidebar import segmented_control
    segmented_control([("a", "A"), ("b", "B")], active="a", key="k")
    body, _ = fake_streamlit.markdown_calls[-1]
    assert 'class="ds-seg-ctrl"' in body
    assert "ds-seg-ctrl-sm" not in body


def test_small_variant_emits_ds_seg_ctrl_sm_marker(fake_streamlit):
    from ui.sidebar import segmented_control
    segmented_control([("a", "A"), ("b", "B")], active="a",
                      key="k", variant="small")
    body, _ = fake_streamlit.markdown_calls[-1]
    assert "ds-seg-ctrl-sm" in body
    # Both classes present on the marker so the primary rules still
    # apply and the -sm rules layer on top.
    assert "ds-seg-ctrl ds-seg-ctrl-sm" in body


# ── Defensive: invalid `active` falls back without raising ───────────────

def test_invalid_active_falls_back_to_first_item(fake_streamlit):
    """If a caller passes an `active` value that isn't in `items`
    (e.g. a stale session_state value after items were redefined),
    the widget must NOT raise — it should fall back gracefully."""
    from ui.sidebar import segmented_control

    items = [("a", "A"), ("b", "B")]
    # Should not raise.
    segmented_control(items, active="zzz_not_in_items", key="k")
    # The first item gets primary type as the fallback.
    types = {b["label"]: b["kwargs"].get("type") for b in fake_streamlit.button_calls}
    assert types["A"] == "primary"
    assert types["B"] == "secondary"


# ── Structural: callback pattern is preserved (regression guard) ─────────

def test_segmented_control_uses_on_click_pattern_not_if_button():
    """Regression guard. The H5 sidebar fix taught us that
    `if button(): write_state(); rerun()` lags one render — the marker
    `<div>` paints with the OLD active state. segmented_control must
    use on_click=callback so the click frame already has the new
    session_state when the buttons render."""
    from ui.sidebar import segmented_control
    src = inspect.getsource(segmented_control)
    assert "on_click=" in src, (
        "segmented_control no longer passes on_click= to st.button. "
        "Without it, the active segment paints with the OLD value on "
        "the click frame — same bug as the H5 sidebar 2-click highlight."
    )
    # And the bad shape must NOT be present.
    code_only = "\n".join(
        line for line in src.splitlines()
        if not line.lstrip().startswith("#")
    )
    bad = ("if st.button(" in code_only) and ("st.rerun()" in code_only)
    assert not bad, (
        "segmented_control reverted to the legacy if-button-rerun "
        "pattern. Use on_click=callback instead."
    )
