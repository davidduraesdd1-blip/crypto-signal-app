"""
C4 verification (Phase C plan §C4): Backtester revision.

Static checks against app.py — running the full Streamlit page in
pytest is heavy; the structural guarantees here cover:

  - Primary segmented_control [backtest][arbitrage] is wired in.
  - Universe selectbox is wired with bt_universe session-state key.
  - Secondary segmented_control [summary][trades][advanced] replaces
    the legacy `st.tabs([...])` in page_backtest.
  - page_arbitrage stub keeps the legacy route alive (deep-link
    compatibility) by setting bt_view=arbitrage and calling
    page_backtest.
  - _render_arbitrage_view exists and is called from page_backtest
    when bt_view=="arbitrage".
  - "Arbitrage" is no longer in the _DS_NAV nav model.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _src() -> str:
    return APP_PY.read_text(encoding="utf-8")


def test_primary_segmented_control_wired():
    s = _src()
    assert 'key="bt_view"' in s, (
        "Backtester is missing the primary segmented control bound to "
        "bt_view (per Phase C §C4.1). Without it, users have no way to "
        "swap between Backtest and Arbitrage views."
    )
    assert '("backtest", "Backtest")' in s
    assert '("arbitrage", "Arbitrage")' in s


def test_arbitrage_branch_returns_early_in_page_backtest():
    """When bt_view == 'arbitrage', page_backtest must call
    _render_arbitrage_view and `return` so it doesn't also render the
    Backtester equity curve / KPI strip below."""
    s = _src()
    bt_idx = s.find("def page_backtest():")
    assert bt_idx > 0
    # Slice generously — the branch is near the top, before the universe
    # selector and the controls row.
    bt_body = s[bt_idx:bt_idx + 8000]
    assert "_render_arbitrage_view" in bt_body
    assert 'if _bt_view == "arbitrage":' in bt_body, (
        "page_backtest no longer pivots into the arbitrage view via "
        '`if _bt_view == "arbitrage": _render_arbitrage_view(); return`.'
    )


def test_secondary_segmented_replaces_st_tabs():
    s = _src()
    assert 'key="bt_subview"' in s, (
        "Backtester is missing the secondary segmented control bound "
        "to bt_subview (per Phase C §C4.2)."
    )
    # Ensure the legacy 3-tab st.tabs declaration is gone — it was the
    # exact 4-line block `_bt_t1, _bt_t2, _bt_t3 = st.tabs([...])`.
    legacy_tabs = (
        '_bt_t1, _bt_t2, _bt_t3 = st.tabs(['
    )
    assert legacy_tabs not in s, (
        "page_backtest still declares the legacy 3-tab st.tabs(...). "
        "The secondary segmented control must replace it (per Q8 Option B)."
    )


def test_universe_selectbox_wired():
    s = _src()
    assert "Top 10 cap" in s and "Top 25 cap" in s and "All 33" in s
    assert '"bt_universe"' in s, (
        "Universe selector must persist in st.session_state[\"bt_universe\"]"
    )
    assert "Custom multi-select" in s


def test_page_arbitrage_is_deprecation_stub():
    """page_arbitrage stays alive but only sets bt_view=arbitrage and
    delegates to page_backtest (so legacy `?page=Arbitrage` deep links
    still land on the merged view)."""
    s = _src()
    arb_idx = s.find("def page_arbitrage():")
    assert arb_idx > 0
    # The stub body lives in the next ~500 chars before the next def.
    body = s[arb_idx:arb_idx + 800]
    assert 'st.session_state["bt_view"] = "arbitrage"' in body
    assert "page_backtest()" in body


def test_render_arbitrage_view_helper_exists():
    s = _src()
    assert "def _render_arbitrage_view():" in s, (
        "Phase C §C4.4 requires the arbitrage scanner body to be "
        "extracted into _render_arbitrage_view() so page_backtest "
        "can call it conditionally without duplicating the body."
    )


def test_arbitrage_not_in_ds_nav():
    """C4 removes the standalone Arbitrage nav entry. Legacy route alive
    in the dispatcher still works for deep links via the page_arbitrage
    stub, but the user-facing nav list must drop it.

    We strip comment lines first so the explanatory comment about why
    the entry was removed (which legitimately mentions "Arbitrage")
    doesn't trip the regression guard. The check looks for the actual
    tuple shape `("opps", ...)` since that was the legacy nav key.
    """
    s = _src()
    nav_idx = s.find("_DS_NAV: list[tuple")
    assert nav_idx > 0, "_DS_NAV not found"
    nav_block = s[nav_idx:nav_idx + 2500]
    code_only = "\n".join(
        line for line in nav_block.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert '"opps"' not in code_only, (
        "_DS_NAV still has an `opps` (Arbitrage) entry. Phase C §C4 "
        "removes it — Arbitrage is now a sub-view of the Backtester page."
    )
    assert '("Arbitrage"' not in code_only, (
        "_DS_NAV still has an entry with `Arbitrage` as the page-router "
        "target. Phase C §C4 removes it from the visible nav."
    )
