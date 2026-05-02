"""
C10 verification (Phase C plan §C10): legacy 5-tab Dashboard stack
removed. Single-flow scrollable Home per the redesign mockup.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _src() -> str:
    return APP_PY.read_text(encoding="utf-8")


def test_legacy_dash_tabs_declaration_removed():
    """The 5-tab st.tabs([...]) declaration was the entry point for
    the legacy Today / All Coins / Coin Detail / Market Intel /
    Analysis stack. C10 removes it entirely."""
    s = _src()
    forbidden = "_dash_tab1, _dash_tab2, _dash_tab3, _dash_tab4, _dash_tab5 = st.tabs("
    assert forbidden not in s, (
        "Legacy 5-tab Dashboard declaration is back — C10 was supposed "
        "to remove it. ~2800-line block of duplicate content shouldn't "
        "be reintroduced; the new mockup-content sections in "
        "page_dashboard cover the same surface."
    )


def test_legacy_dash_tab_with_blocks_removed():
    """Each `with _dash_tabN:` block opens a tab body. None of them
    should remain in executable code (the tombstone comment is OK)."""
    s = _src()
    code_only = "\n".join(line for line in s.splitlines()
                          if not line.lstrip().startswith("#"))
    for n in range(1, 6):
        marker = f"with _dash_tab{n}:"
        assert marker not in code_only, (
            f"Legacy `{marker}` block remains in executable code — "
            f"C10 cleanup didn't fully delete the tab body."
        )


def test_legacy_removed_c10_sentinel_present():
    """The deletion left a tombstone comment so git blame can find it."""
    s = _src()
    assert "_LEGACY_REMOVED_C10" in s, (
        "C10 sentinel _LEGACY_REMOVED_C10 missing — without it, no "
        "audit trail for the ~2800-line deletion."
    )


def test_app_py_size_dropped_below_legacy_bound():
    """Spec: 'line count drops by ~2500'. Pre-C10 app.py was ~10,667
    lines; post-cut should stay well below that. Generous upper bound
    here so future feature work doesn't trip this guard needlessly —
    the point is just to flag if someone restores the legacy ~2800-
    line tabs block.

    Bound history:
      8500  — initial post-C10 cut (2026-04-30)
      9500  — raised after the C-fix-19/20/21/22 sprint added auto-
              backtest chain, layer-weight loading, math-model UI
              section, etc. (2026-05-02)"""
    s = _src()
    n = len(s.splitlines())
    assert n < 9500, (
        f"app.py is {n} lines — expected < 9500. If a feature "
        f"genuinely needs to push past this, raise the bound; "
        f"otherwise the legacy tabs may have crept back."
    )
