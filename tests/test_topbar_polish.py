"""
H1 + H2 fix verification (handoff: 2026-04-28_redesign_port_handoff.md).

H1 — topbar pill labels wrapped inside their pills on narrow viewports.
H2 — refresh button gave no visible feedback on click.

Static checks against the rendered CSS + render_top_bar source — running
the full Streamlit app in pytest is heavyweight and brittle, but the
structural guarantees are easy to verify here.
"""
from __future__ import annotations

import inspect
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_overrides_css_has_intermediate_viewport_breakpoint():
    """The pill-wrap bug happened between 769-1200px. The fix adds a
    @media (max-width: 1200px) rule that compacts the topbar buttons
    before the wrap can occur."""
    css_src = (REPO_ROOT / "ui" / "overrides.py").read_text(encoding="utf-8")
    assert "@media (max-width: 1200px)" in css_src, (
        "overrides.py is missing the intermediate-viewport breakpoint "
        "(@media (max-width: 1200px)) that prevents topbar pill labels "
        "from wrapping. Without it, 'Intermediate' wraps to 2-3 lines "
        "in the 1.7/11-width column."
    )
    # C-fix-01 (2026-05-01): topbar selector migrated from
    # `:has(.ds-crumbs[data-topbar="1"])` to `data-stkey="ds_topbar_row"`
    # because the audit confirmed the :has-based scope was being beaten
    # by section.main's default stButton specificity. The new selector
    # is unambiguous and uses Streamlit's `st.container(key=...)` hook.
    assert '[data-stkey="ds_topbar_row"]' in css_src, (
        "overrides.py is missing the data-stkey topbar scope. Without it "
        "the topbar buttons render as Streamlit defaults (oversized pills "
        "with mid-word text wrap and ~280px row height)."
    )
    # Inner-element nowrap (Streamlit wraps button text in <p> /
    # stMarkdownContainer with their own white-space rules — the
    # button-level nowrap alone isn't enough on tight viewports).
    assert (
        "[data-testid=\"stButton\"] > button > *" in css_src
        and "white-space: nowrap !important" in css_src
    ), (
        "overrides.py no longer pushes white-space:nowrap into the "
        "button's inner elements. Streamlit wraps button labels in "
        "<p> / stMarkdownContainer which can re-introduce wrapping "
        "inside the button even when the button itself is nowrap."
    )


def test_render_top_bar_wraps_columns_in_keyed_container():
    """C-fix-01 (2026-05-01): the topbar columns must be created inside
    `st.container(key="ds_topbar_row")` so Streamlit emits the
    `data-stkey="ds_topbar_row"` DOM hook the CSS scope depends on."""
    from ui.sidebar import render_top_bar
    src = inspect.getsource(render_top_bar)
    assert 'st.container(key="ds_topbar_row")' in src, (
        "render_top_bar no longer wraps its columns in a keyed container — "
        "the data-stkey CSS scope will not match anything and the topbar "
        "will revert to oversized Streamlit defaults."
    )


def test_topbar_refresh_label_unified_across_user_levels():
    """C-fix-10 (2026-05-02): the topbar refresh button must use the
    same label ('↻ Update') for every user level. The previous
    level-aware split — '↻ Update' for Beginner, '↻ Refresh' for
    Intermediate/Advanced, with different click semantics — was
    rejected: the user wants ONE button that does the full
    'make everything fresh' action regardless of level."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "ui" / "sidebar.py"
    ).read_text(encoding="utf-8")
    # Locate the refresh button construction inside render_top_bar.
    idx = src.find("def render_top_bar")
    assert idx > 0
    # Read forward to the show_refresh block.
    block = src[idx : idx + 8000]
    # The level-conditional label must be gone.
    assert (
        '"↻ Update" if user_level == "beginner" else "↻ Refresh"' not in block
    ), (
        "render_top_bar reverted to level-aware refresh labels. "
        "Per C-fix-10 the label must be unified to '↻ Update' across "
        "all levels."
    )
    # And the unified label must be present.
    assert '_ref_lbl = "↻ Update"' in block, (
        "render_top_bar no longer uses '↻ Update' as the unified "
        "refresh label. Without it, the topbar button text varies "
        "by level — confusing UX."
    )


def test_refresh_all_data_kicks_off_scan_for_every_level():
    """C-fix-10: _refresh_all_data must trigger a fresh scan after
    the cache clear regardless of user_level. The previous Beginner-
    only auto-scan was rejected — every Update click for every level
    should refresh caches AND run a scan."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "app.py"
    ).read_text(encoding="utf-8")
    idx = src.find("def _refresh_all_data")
    assert idx > 0
    body = src[idx : idx + 4000]
    # Negative: the level gate must not appear in executable code
    # (comments documenting the change are fine).
    code_only = "\n".join(
        line for line in body.splitlines()
        if not line.lstrip().startswith("#")
    )
    assert 'if _ref_lv == "beginner":' not in code_only, (
        "_refresh_all_data still gates the auto-scan on user_level == "
        "'beginner'. Remove the level gate per C-fix-10."
    )
    # Positive: scan kicks off if not already running.
    assert "_start_scan()" in body, (
        "_refresh_all_data no longer calls _start_scan(). The Update "
        "button needs to fire a scan after the cache clear, every level."
    )


def test_home_page_no_redundant_run_scan_cta():
    """C-fix-10: the Home page's '🔍 Run a fresh scan now' button
    is removed. The topbar Update button is the single canonical
    scan trigger. A pre-existing in-line status banner remains
    (read-only, surfaces when a scan is running)."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "app.py"
    ).read_text(encoding="utf-8")
    # The Home-only scan button used a specific key — guard against
    # its return.
    assert "ds_beginner_scan_btn" not in src, (
        "The Home-only '🔍 Run a fresh scan now' button is back. "
        "Remove it — the topbar Update button is the single trigger."
    )


def test_render_top_bar_uses_on_click_callbacks():
    """The level pills + refresh + theme buttons must use on_click=
    callbacks so the click frame paints with the new state immediately
    (consistent with H5 fix). The legacy `if st.button(...): write_state();
    st.rerun()` shape causes a one-render lag."""
    from ui.sidebar import render_top_bar
    src = inspect.getsource(render_top_bar)
    assert "on_click=_select_level" in src, (
        "Topbar level pills no longer use on_click=callback — clicking "
        "Beginner/Intermediate/Advanced will paint with the OLD type "
        "(secondary/primary) for one render before catching up."
    )
    assert "on_click=_on_topbar_refresh" in src, (
        "Topbar refresh button no longer uses on_click=callback — "
        "the toast + cache-clear won't fire reliably on the click frame."
    )
    assert "on_click=_on_topbar_theme" in src, (
        "Topbar theme button no longer uses on_click=callback."
    )


def test_topbar_refresh_handler_fires_toast_and_records_timestamp():
    """The refresh handler must:
       1. Call the user-supplied on_refresh callback
       2. Record _topbar_last_refresh_at in session state
       3. Fire st.toast for immediate user feedback (C-fix-14: wording
          now reflects the unified Update action — scan + cache clear)
    """
    from ui.sidebar import render_top_bar
    src = inspect.getsource(render_top_bar)
    assert 'st.session_state["_topbar_last_refresh_at"]' in src, (
        "Refresh handler no longer records a wall-clock timestamp — "
        "the persistent 'refreshed Xs ago' caption won't render."
    )
    # C-fix-14: toast wording now explicitly mentions the scan kickoff.
    # The legacy 'Data refreshed' is gone (it masked the scan side-effect).
    assert "st.toast(" in src, (
        "Refresh handler no longer fires st.toast on click — H2 says "
        "the button needs visible feedback."
    )
    assert 'st.toast("Data refreshed"' not in src, (
        "Refresh toast reverted to 'Data refreshed' — that wording "
        "implies cache-only and masks the scan kickoff per C-fix-14."
    )
    assert "Update started" in src and "scan running" in src, (
        "Refresh toast no longer surfaces the scan-running side effect. "
        "Users need immediate confirmation that the scan kicked off."
    )


def test_home_status_banner_shows_on_recent_click_even_without_running_flag():
    """C-fix-14 (2026-05-02): the in-line Home status banner must show
    in TWO cases:
      (a) scan thread is running (existing behaviour)
      (b) user clicked Update within the last 5s
    Without (b), a scan that fails fast (errors before the sidebar
    fragment's 2s tick catches the running flag) leaves the user with
    NO visual confirmation their click registered."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "app.py"
    ).read_text(encoding="utf-8")
    # The recent-click window check must be present.
    assert "_topbar_last_refresh_at" in src, (
        "Home status banner no longer reads _topbar_last_refresh_at — "
        "the recent-click window guard is gone, scan-fail-fast users "
        "see no confirmation."
    )
    # And the banner must trigger on EITHER running flag OR recent click.
    assert "_ds_sb_running or _ds_recent_click" in src, (
        "Home status banner no longer triggers on a recent click. "
        "If the scan thread fails before flipping the running flag, "
        "the banner never paints."
    )


def test_topbar_refresh_caption_renders_relative_time():
    """The persistent caption under the refresh button must include
    relative-time formatting so users can see how long ago they last
    refreshed."""
    from ui.sidebar import render_top_bar
    src = inspect.getsource(render_top_bar)
    # Must build s/m/h variants so the caption is human-readable
    # regardless of how stale the last refresh is.
    assert 'refreshed' in src.lower()
    for token in ("s ago", "m ago", "h ago"):
        assert token in src, (
            f"Refresh caption missing relative-time '{token}' formatting."
        )
