"""
C5 verification (Phase C plan §C5): AI Assistant promotion.

Spec acceptance:
  1. Recent Decisions populates from DB (verify the query helper +
     page_agent's render path).
  2. Settings → Execution no longer has duplicate agent config (the
     legacy form + runtime controls were ~120 lines; now a single
     link card).
  3. Topbar pill shows running state on every page (helper exists,
     wired into every render_top_bar call).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"
DB_PY = REPO_ROOT / "database.py"


def _app() -> str:
    return APP_PY.read_text(encoding="utf-8")


def _db() -> str:
    return DB_PY.read_text(encoding="utf-8")


# ── Acceptance #1: Recent Decisions helper exists + page_agent renders ───

def test_recent_agent_decisions_helper_exists():
    s = _db()
    assert "def recent_agent_decisions(" in s, (
        "database.py is missing recent_agent_decisions(limit=10). The "
        "Phase C §C5.3 spec requires a query helper for the AI "
        "Assistant Recent Decisions log."
    )


def test_recent_agent_decisions_shape_matches_spec():
    """Helper must return rows with the spec-shaped keys (timestamp,
    pair, decision, confidence, rationale, status). The on-disk
    schema uses agent_log column names; the helper translates to the
    spec shape."""
    s = _db()
    helper_idx = s.find("def recent_agent_decisions(")
    assert helper_idx > 0
    body = s[helper_idx:helper_idx + 3000]
    for key in ('"timestamp"', '"pair"', '"decision"', '"confidence"',
                '"rationale"', '"status"'):
        assert key in body, (
            f"recent_agent_decisions row dict is missing {key} — "
            f"page_agent's Recent Decisions render expects this key."
        )


def test_page_agent_renders_recent_decisions_section():
    s = _app()
    assert "Recent Agent Decisions" in s, (
        "page_agent no longer has a Recent Agent Decisions section."
    )


# ── Acceptance #2: Settings → Execution agent block removed ─────────────

def test_settings_execution_agent_block_removed():
    """The duplicate agent block was 120 lines starting with
    "Autonomous AI Agent" section_header. Removed in C5; the
    replacement is a small link card + a tombstone comment.

    The form key `"agent_config_form"` and the Start/Stop runtime
    buttons LIVE on page_agent (canonical home) — they only need to
    be absent from page_config / Settings → Execution. We slice the
    page_config function body so the asserts are scoped correctly."""
    s = _app()
    assert "_LEGACY_REMOVED_C5" in s, (
        "C5 sentinel _LEGACY_REMOVED_C5 missing — the Settings → "
        "Execution agent-block deletion never happened, or the "
        "tombstone comment was removed."
    )

    # Slice the page_config function body so we only check Settings
    # surfaces, not page_agent (which legitimately keeps the form).
    cfg_idx = s.find("def page_config():")
    assert cfg_idx > 0
    next_def = s.find("\ndef ", cfg_idx + 1)
    cfg_body = s[cfg_idx:next_def if next_def > 0 else None]

    # Specific markers from the deleted form must NOT appear inside
    # page_config — they belong on page_agent now.
    forbidden = [
        '"agent_config_form"',           # the legacy form key
        'st.button("▶ Start Agent Now"',  # legacy runtime control
        'st.button("⏹ Stop Agent"',        # legacy runtime control
    ]
    for marker in forbidden:
        assert marker not in cfg_body, (
            f"Legacy agent block marker `{marker}` still present in "
            f"page_config — C5 §C5.4 cleanup didn't fully remove the "
            f"duplicate Settings → Execution block. (The same marker "
            f"in page_agent is fine — that's the canonical home now.)"
        )


def test_settings_execution_has_link_card():
    """Replacement link card directs users to the AI Assistant page."""
    s = _app()
    # The link button writes _nav_target=Agent so the sidebar router
    # lands the user on page_agent.
    assert 'st.session_state["_nav_target"] = "Agent"' in s, (
        "Settings → Execution link card is missing the nav redirect "
        "to the AI Assistant (page=Agent) page."
    )


# ── Acceptance #3: Topbar agent pill on every page ──────────────────────

def test_agent_topbar_pills_helper_exists():
    s = _app()
    assert "def _agent_topbar_pills(" in s, (
        "app.py is missing _agent_topbar_pills() — the helper that "
        "computes the topbar status pill for the autonomous agent."
    )


def test_every_top_bar_call_passes_status_pills():
    """Every render_top_bar invocation must pass the agent pill so
    users see the agent's running state on every page."""
    s = _app()
    # Count how many _ds_top_bar( call sites exist.
    n_calls = s.count("_ds_top_bar(")
    # n_calls counts ALL occurrences including the import alias line
    # `render_top_bar as _ds_top_bar` if it shows up somewhere
    # unrelated. The wired ones must each have status_pills= nearby.
    # Cheaper structural check: every call site has the substring
    # status_pills=_agent_topbar_pills() somewhere within ~600 chars
    # after `_ds_top_bar(`.
    idx = 0
    found_calls = 0
    found_with_pills = 0
    while True:
        idx = s.find("_ds_top_bar(", idx)
        if idx < 0:
            break
        # Skip import-alias lines.
        line_start = s.rfind("\n", 0, idx) + 1
        line = s[line_start:s.find("\n", idx)]
        if "render_top_bar as _ds_top_bar" in line:
            idx += 1
            continue
        found_calls += 1
        slice_ = s[idx:idx + 600]
        if "status_pills=_agent_topbar_pills()" in slice_:
            found_with_pills += 1
        idx += 1
    assert found_calls > 0
    assert found_calls == found_with_pills, (
        f"Only {found_with_pills} of {found_calls} render_top_bar "
        f"call sites pass status_pills=_agent_topbar_pills(). The "
        f"agent pill must be visible on every page per Phase C §C5.5."
    )


def test_agent_topbar_pills_shape():
    """Helper returns a list of dicts with `tone`, `icon`, `label`
    keys — the shape render_top_bar's status_pills parameter expects."""
    s = _app()
    helper_idx = s.find("def _agent_topbar_pills(")
    assert helper_idx > 0
    body = s[helper_idx:helper_idx + 1500]
    assert '"tone"' in body
    assert '"icon"' in body
    assert '"label"' in body
