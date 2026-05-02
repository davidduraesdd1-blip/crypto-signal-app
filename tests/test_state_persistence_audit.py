"""tests/test_state_persistence_audit.py

State-persistence audit (2026-05-02): Streamlit's `st.tabs()` doesn't
persist active-tab state across reruns — any button click inside a tab
kicks the user back to the first tab. The fix is to replace `st.tabs()`
with the new `_stateful_tabs` helper backed by `st.segmented_control`
(which supports `key=` natively).

These tests guard the fixes against regression:
  1. The _stateful_tabs helper exists and uses key= for state persistence
  2. Settings page tabs use _stateful_tabs (not st.tabs)
  3. Backtester sub-tabs use _stateful_tabs (not st.tabs)
  4. High-impact config widgets carry key= for state persistence
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _src() -> str:
    return APP_PY.read_text(encoding="utf-8")


# ── 1. _stateful_tabs helper exists ─────────────────────────────────────

def test_stateful_tabs_helper_exists():
    """The helper must exist and use key= for session_state persistence."""
    src = _src()
    assert "def _stateful_tabs(" in src, (
        "_stateful_tabs helper is missing — st.tabs() loses active-tab "
        "state on rerun. The helper provides a key-backed alternative."
    )
    # The helper must seed defaults + use a key-backed widget.
    idx = src.find("def _stateful_tabs(")
    body = src[idx : idx + 3000]
    assert "key=state_key" in body, (
        "_stateful_tabs is no longer using state_key on the underlying "
        "widget — without key= the selection still resets on rerun."
    )
    # And it should use segmented_control as the primary mechanism
    # (with st.radio fallback for older Streamlit versions).
    assert "segmented_control" in body, (
        "_stateful_tabs no longer uses st.segmented_control — that's "
        "the state-persistent widget choice."
    )


# ── 2. Settings page tabs use the helper ────────────────────────────────

def test_settings_page_uses_stateful_tabs():
    """Settings page (page_config) must NOT use st.tabs() — it must
    use _stateful_tabs(...). The user reported being kicked back to
    the Trading tab after clicking the Retune button on Dev Tools."""
    src = _src()
    # Anchor on the Settings tab names.
    assert '_cfg_tab_names = ["📊 Trading"' in src, (
        "Settings tab names list is missing or renamed."
    )
    # The call site must use _stateful_tabs, not st.tabs.
    assert '_cfg_active = _stateful_tabs(_cfg_tab_names' in src, (
        "Settings page is no longer using _stateful_tabs. Reverting "
        "to st.tabs() re-introduces the 'kicked back to Trading tab' bug."
    )
    # And the legacy with-blocks must be gone.
    assert "with _cfg_t1:" not in src, (
        "Legacy `with _cfg_t1:` block is back. The refactor must use "
        "`if _cfg_active == ...:` conditionals instead."
    )


# ── 3. Backtester sub-tabs use the helper ───────────────────────────────

def test_backtester_subtabs_use_stateful_tabs():
    """Backtester 'trades' subview's 5-tab sub-bar must be state-
    persistent so clicks inside any sub-tab don't reset the user to
    'Signal Master Log'."""
    src = _src()
    assert '_bt_tab_names = [' in src, (
        "Backtester _bt_tab_names list is missing or renamed."
    )
    assert '_bt_active_tab = _stateful_tabs(' in src, (
        "Backtester sub-tabs no longer use _stateful_tabs. Same "
        "kick-back-to-tab-1 bug pattern as the Settings page."
    )
    # Legacy with-blocks gone.
    assert "with tab_master:" not in src
    assert "with tab_paper:" not in src
    assert "with tab_feedback:" not in src
    assert "with tab_exec:" not in src
    assert "with tab_slip:" not in src


# ── 4. High-impact widgets carry key= ───────────────────────────────────

@pytest.mark.parametrize("widget_key", [
    # Trading config — auto-tuned daily, but mid-edit state still needs persistence.
    "cfg_portfolio_size",
    "cfg_risk_per_trade_pct",
    "cfg_max_total_exposure_pct",
    "cfg_max_position_pct_cap",
    "cfg_max_open_per_pair",
    # Signal & Risk thresholds — reactive sliders.
    "cfg_high_conf_threshold",
    "cfg_mtf_threshold",
    "cfg_corr_threshold",
    "cfg_corr_lookback_days",
    # Backtest settings.
    "cfg_trailing_stop_enabled",
    "cfg_drawdown_circuit_breaker_pct",
    # TA exchange (data source).
    "cfg_ta_exchange",
    # Auto-Scan form widgets.
    "cfg_form_autoscan_enabled",
    "cfg_form_autoscan_interval",
    "cfg_form_autoscan_quiet_on",
    "cfg_form_autoscan_quiet_start",
    "cfg_form_autoscan_quiet_end",
])
def test_high_impact_widgets_have_keys(widget_key):
    """Each listed widget must carry a `key=` so its user-edited value
    persists across reruns. Without key=, every rerun re-renders with
    the saved-config default, losing in-progress edits."""
    src = _src()
    assert f'key="{widget_key}"' in src, (
        f"Widget with expected key '{widget_key}' is missing or has "
        f"a different name. State-loss regression risk."
    )
