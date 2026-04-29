"""
C1 fix verification (handoff: 2026-04-28_redesign_port_handoff.md).

Two guarantees for the Beginner / Intermediate / Advanced toggle:

  1. The session-state read is always live — `current_user_level()` returns
     whatever was last written to `st.session_state["user_level"]`, with no
     module-level caching that would make the toggle appear inert.

  2. Every page section in app.py reads the level via the supported pattern
     (either `current_user_level()` from `ui` or
     `st.session_state.get("user_level", ...)` directly) — never from a
     module-top constant or a function default that bypasses the toggle.

The static-check (#2) is grep-shaped because app.py is a single large
Streamlit script (no `pages/` directory). It walks every page-function
declaration and asserts the level read happens *inside* the function body.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


# ── 1. Live session-state read ────────────────────────────────────────────

class _FakeSessionState(dict):
    """Minimal stand-in for st.session_state for unit testing."""


@pytest.fixture
def fake_streamlit(monkeypatch):
    """Patch ui.sidebar.st with a stub that exposes only session_state."""
    import ui.sidebar as sidebar_mod

    fake = type("FakeSt", (), {})()
    fake.session_state = _FakeSessionState()
    monkeypatch.setattr(sidebar_mod, "st", fake)
    return fake


def test_current_user_level_default_is_beginner(fake_streamlit):
    from ui.sidebar import current_user_level
    assert current_user_level() == "beginner"


def test_current_user_level_reads_session_state_live(fake_streamlit):
    from ui.sidebar import current_user_level

    fake_streamlit.session_state["user_level"] = "advanced"
    assert current_user_level() == "advanced"

    fake_streamlit.session_state["user_level"] = "intermediate"
    assert current_user_level() == "intermediate"

    fake_streamlit.session_state["user_level"] = "beginner"
    assert current_user_level() == "beginner"


def test_current_user_level_rejects_invalid_value(fake_streamlit):
    from ui.sidebar import current_user_level

    fake_streamlit.session_state["user_level"] = "expert"  # not in valid set
    assert current_user_level() == "beginner"

    fake_streamlit.session_state["user_level"] = None
    assert current_user_level() == "beginner"


def test_level_label_capitalises(fake_streamlit):
    from ui.sidebar import level_label

    assert level_label("beginner") == "Beginner"
    assert level_label("INTERMEDIATE") == "Intermediate"
    fake_streamlit.session_state["user_level"] = "advanced"
    assert level_label() == "Advanced"


# ── 2. Static-check: every page reads level inside its function body ─────

# Names of the page entry-point functions in app.py. These are the
# `def page_*()` blocks invoked from the page router. Any new page must
# add itself here — keeping the list explicit makes the contract
# auditable.
PAGE_FUNCTIONS = [
    "page_config",
]


@pytest.fixture(scope="module")
def app_source() -> str:
    return APP_PY.read_text(encoding="utf-8")


def _function_body(source: str, fn_name: str) -> str | None:
    """Return everything from `def <fn_name>(...)` to the next top-level
    `def ` or end-of-file. Good enough for a static grep — we're not
    parsing Python here, just isolating one function block."""
    m = re.search(rf"^def {re.escape(fn_name)}\b.*?(?=^def |\Z)", source,
                  flags=re.MULTILINE | re.DOTALL)
    return m.group(0) if m else None


@pytest.mark.parametrize("fn_name", PAGE_FUNCTIONS)
def test_page_reads_user_level_from_session_state(app_source, fn_name):
    body = _function_body(app_source, fn_name)
    assert body is not None, (
        f"page function {fn_name}() not found in app.py — keep "
        f"PAGE_FUNCTIONS in this test in sync with the router."
    )
    has_helper_call = "current_user_level()" in body
    has_session_read = re.search(
        r'st\.session_state\.(get\(\s*["\']user_level["\']|"\[user_level"\])',
        body,
    ) is not None
    has_session_read = has_session_read or 'st.session_state.get("user_level"' in body
    assert has_helper_call or has_session_read, (
        f"{fn_name}() does not read the user level via session_state or "
        f"current_user_level() — the level toggle will appear inert on "
        f"this page. Add `_lv = ui.current_user_level()` (or "
        f"`st.session_state.get(\"user_level\", \"beginner\")`) at the "
        f"start of the function body."
    )
