"""
C2 fix verification (handoff: 2026-04-28_redesign_port_handoff.md).

The Backtester page had two buttons that did nothing on click:
  1. "Re-run backtest →" inside the controls-row markup
     — was an HTML `<button>` in an `st.markdown(...)` block, which
       cannot trigger a Streamlit callback. Hidden by default now.
  2. "▶ Run Backtest" — was wired with `if st.button(...): handler()`,
     which works in principle but produces no immediate visible feedback
     on the click frame. Switched to `on_click=callback` so the state
     write happens BEFORE the next render.
"""
from __future__ import annotations

import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def test_backtest_controls_row_hides_decorative_button_by_default():
    """The HTML <button> inside backtest_controls_row markup was the root
    cause of users clicking 'Re-run backtest →' and seeing nothing. With
    the C2 fix, the button is suppressed unless `show_decorative_button=
    True` is explicitly passed."""
    from ui.sidebar import backtest_controls_row

    html = backtest_controls_row([("Universe", "Top 10"), ("Period", "2024")])
    assert "ds-bt-runbtn" not in html, (
        "backtest_controls_row is still emitting the decorative "
        "<button class=ds-bt-runbtn> by default — that button cannot "
        "trigger a Streamlit handler, so users who click it see nothing "
        "happen. Set show_decorative_button=False (the new default)."
    )

    # Opt-in path still works for callers that explicitly want the visual.
    html_opt = backtest_controls_row(
        [("Universe", "Top 10")], show_decorative_button=True
    )
    assert "ds-bt-runbtn" in html_opt
    # And when shown, it must be marked disabled so a screen reader / a
    # keyboard user understands it isn't interactive.
    assert "disabled" in html_opt


def test_run_backtest_button_uses_on_click_callback():
    """The page_backtest run button must use on_click=_handler so the
    state update + thread spawn happen BEFORE the script body re-runs.
    With the legacy `if st.button(...): _start_backtest()` shape, the
    click frame had no immediate UI feedback — the button stayed
    rendered as 'enabled' for one extra paint."""
    src = APP_PY.read_text(encoding="utf-8")

    # Find the page_backtest function body.
    bt_idx = src.find("def page_backtest():")
    assert bt_idx > 0, "page_backtest() not found in app.py"
    # Take a generous slice (page_backtest is large but the run button is near the top).
    bt_body = src[bt_idx:bt_idx + 6000]

    assert 'key="bt_btn_run"' in bt_body, "run button key not found"
    assert "on_click=_on_run_backtest_click" in bt_body, (
        "page_backtest run button no longer uses on_click=callback. "
        "Without it, the click frame won't show immediate 'running' "
        "feedback — the button stays as 'enabled' for one extra render."
    )

    # And the legacy shape must NOT be present in executable code.
    legacy = 'if st.button("▶ Run Backtest", key="bt_btn_run"'
    assert legacy not in bt_body, (
        "Legacy `if st.button(\"▶ Run Backtest\", ...): _start_backtest()` "
        "shape is back. Replace with on_click=callback to keep C2 fixed."
    )


def test_start_backtest_writes_running_flag_synchronously():
    """The _start_backtest handler must set
    session_state['backtest_running'] = True synchronously, so the next
    render sees the disabled state on the run button."""
    src = APP_PY.read_text(encoding="utf-8")
    # Find _start_backtest body.
    sb_idx = src.find("def _start_backtest():")
    assert sb_idx > 0
    sb_body = src[sb_idx:sb_idx + 800]
    assert 'st.session_state["backtest_running"] = True' in sb_body, (
        "_start_backtest no longer writes session_state[\"backtest_"
        "running\"] = True synchronously — the run button won't disable "
        "after click."
    )
    assert "threading.Thread" in sb_body, (
        "_start_backtest no longer spawns a daemon thread for the "
        "backtest run."
    )
