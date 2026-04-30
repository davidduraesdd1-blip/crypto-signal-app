"""
C7 verification (Phase C plan §C7): Settings restructure.

Acceptance:
  - Tab labels match the mockup ("📊 Trading", "⚡ Signal & Risk",
    "🛠️ Dev Tools", "⚙️ Execution").
  - Beginner Quick Setup wrapped in `st.container(key="ds_beg_panel")`
    so overrides.py can target its inputs.
  - overrides.py contains the .ds-beg-panel-style input rules
    (bg-0 / border-strong / 15px / mono / 500) AND the underline-tab
    polish (gap 28px / font 13.5px / active 600 / accent border).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"
OVERRIDES_PY = REPO_ROOT / "ui" / "overrides.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_beginner_panel_wrapped_in_keyed_container():
    """C7 §C7.1: the 3-control Quick Setup panel must live inside
    `st.container(key="ds_beg_panel")` so overrides.py CSS can scope
    its boosted-contrast input styling without bleeding to other
    inputs on the Settings page."""
    s = _read(APP_PY)
    assert 'st.container(key="ds_beg_panel")' in s, (
        "Beginner panel is no longer wrapped in st.container("
        'key="ds_beg_panel") — overrides.py CSS will not bind to '
        "the Quick Setup inputs."
    )


def test_overrides_has_beg_panel_input_styling():
    s = _read(OVERRIDES_PY)
    # All 4 mockup-derived properties must be present in the rule.
    for token in (
        '[data-stkey="ds_beg_panel"]',
        "var(--bg-0)",
        "var(--border-strong)",
        "var(--font-mono)",
        "15px",
        "500",
    ):
        assert token in s, (
            f"overrides.py is missing token `{token}` from the "
            f"C7 .ds-beg-panel input styling rule."
        )


def test_tab_underline_styling_polished():
    """The tab CSS now matches the mockup pattern: 28px gap on
    desktop, 16px on mobile, 13.5px font, active tab accent
    underline + 600 weight."""
    s = _read(OVERRIDES_PY)
    # Match the rule block — be permissive about whitespace/layout.
    assert "stTabs" in s
    assert "gap: 28px" in s, "Tab list gap not bumped to 28px per mockup."
    assert "13.5px" in s, "Tab font-size not bumped to 13.5px per mockup."
    assert "border-bottom-color: var(--accent)" in s, (
        "Active tab no longer uses accent-coloured border-bottom."
    )
    # Mobile breakpoint
    assert "@media (max-width: 768px)" in s
    assert "gap: 16px" in s, "Mobile tab gap not present (mockup line 112)."


def test_settings_tab_labels_match_mockup():
    """Spot-check that the 4 tab names match the mockup exactly."""
    s = _read(APP_PY)
    cfg_idx = s.find("def page_config():")
    body = s[cfg_idx:cfg_idx + 20000]
    code_only = "\n".join(line for line in body.splitlines()
                          if not line.lstrip().startswith("#"))
    assert (
        '"📊 Trading", "⚡ Signal & Risk", "🛠️ Dev Tools", "⚙️ Execution"'
        in code_only
    ), "Settings tab names no longer match the mockup post-C7."
