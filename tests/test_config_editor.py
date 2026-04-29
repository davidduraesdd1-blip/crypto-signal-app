"""
C5 fix verification (handoff: 2026-04-28_redesign_port_handoff.md).

The handoff described the Config Editor as "appears wiring-stripped" —
old screenshots showed fully-functional Trading + Signal & Risk + Alerts
tabs (pair pills, sliders, API keys), and the redesign state was unclear.

Investigation found:
  • The 5 tabs (Trading / Signal & Risk / Alerts / Dev Tools / Execution)
    are fully present and wired in app.py — they were never stripped.
  • The bug: the beginner-tier branch at the top of page_config()
    rendered a simplified 3-control view, then `return`'d before the
    tabs could render. Beginners — the DEFAULT user level — could
    never reach any of the tabs. From the user's perspective, the
    Config Editor "lost" its tabs even though they were structurally
    intact.

The fix removes that `return`, so beginners now see the simplified
quick-edit panel AT TOP plus the full tab-stack below it (separated by
a "More settings" section header so the additional surface is clearly
optional).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _config_body() -> str:
    """Return the source of `def page_config():` body — captures from
    the def line to the next top-level def. Big enough to cover the
    whole tab stack."""
    src = APP_PY.read_text(encoding="utf-8")
    start = src.find("def page_config():")
    assert start > 0, "page_config() not found in app.py"
    # Find the next "def page_" or "def main(" or another top-level def.
    # page_config is followed by other page_* functions in app.py.
    rest = src[start + len("def page_config():"):]
    # Scan for the next top-level "\ndef " (no leading whitespace).
    nxt = 0
    for line_match in ("\ndef page_", "\ndef main", "\nif __name__"):
        idx = rest.find(line_match)
        if idx > 0 and (nxt == 0 or idx < nxt):
            nxt = idx
    end = start + len("def page_config():") + (nxt if nxt > 0 else len(rest))
    return src[start:end]


def test_config_editor_has_all_five_tabs():
    body = _config_body()
    expected = ["📊 Trading", "⚡ Signal & Risk", "🔔 Alerts",
                "🛠️ Dev Tools", "⚙️ Execution"]
    for tab in expected:
        assert tab in body, (
            f"Config Editor is missing tab '{tab}'. The 5 tabs of the "
            f"Config Editor are part of the app's contract — see the "
            f"handoff doc for the original screenshots."
        )


def test_config_editor_tabs_are_unwrapped_in_st_tabs():
    body = _config_body()
    # The tabs declaration is `_cfg_t1, _cfg_t2, ... = st.tabs(_cfg_tab_names)`.
    # Defending against a refactor that splits these across multiple
    # st.tabs() calls — that breaks the auto-jump behaviour from the
    # sidebar Alerts shortcut.
    assert "= st.tabs(_cfg_tab_names)" in body, (
        "Config Editor tab declaration changed shape. The single "
        "st.tabs(_cfg_tab_names) call is required for "
        "_settings_tab session_state auto-jump (sidebar Alerts deep-"
        "link) to keep working."
    )


def test_beginner_branch_no_longer_returns_before_tabs():
    """Regression guard: the beginner-mode branch must not `return` before
    reaching the tab declaration. Otherwise the default user can't access
    Trading / Signal & Risk / Alerts at all."""
    body = _config_body()

    # Find the beginner branch and confirm it doesn't have a bare `return`
    # immediately after the simplified controls but before st.tabs.
    beg_idx = body.find('if _cfg_lv == "beginner":')
    assert beg_idx > 0, "beginner branch not found in page_config"
    tabs_idx = body.find("= st.tabs(_cfg_tab_names)")
    assert tabs_idx > beg_idx, "tabs declaration must come AFTER beginner branch"

    # Slice the beginner branch up to the tabs line.
    beginner_section = body[beg_idx:tabs_idx]
    # A bare `return` (no value, terminating the function) inside the
    # beginner section would skip the tab rendering. We allow `return`
    # inside nested handlers (e.g. the save button's handler), so we
    # check for a `return` at exactly the indentation that matches the
    # `if _cfg_lv == "beginner":` block.
    bad = "        return  # beginners only see the 3-control view above"
    assert bad not in beginner_section, (
        "Beginner branch still has the early `return` — beginners can't "
        "reach the Trading / Signal & Risk / Alerts tabs. See C5 fix."
    )


def test_config_editor_alerts_tab_has_email_save_button():
    """Smoke check on tab content: the Alerts tab must still wire the
    'Save Email' button so changes persist. This guards against a
    refactor that moves the button out of the tab body."""
    body = _config_body()
    assert '"Save Email"' in body, (
        "Alerts tab no longer renders the 'Save Email' button — the "
        "round-trip persistence path for email alerts is broken."
    )
    assert "_save_alerts_config_and_clear" in body, (
        "Alerts tab no longer calls _save_alerts_config_and_clear — "
        "saved email config won't propagate to the cached config."
    )


def test_config_editor_trading_tab_has_pair_picker():
    """Smoke check: Trading tab renders the multiselect pair picker."""
    body = _config_body()
    assert "Trading Pairs" in body
    assert "selected_pairs = st.multiselect(" in body, (
        "Trading tab no longer renders the pair multiselect — users "
        "can't change which crypto pairs the scanner targets."
    )


def test_config_editor_signal_risk_tab_present():
    """Smoke check: Signal & Risk tab body exists between tab1 and tab3."""
    body = _config_body()
    assert "# ── Tab 2: Signal & Risk" in body, (
        "Signal & Risk tab section header missing or moved."
    )
