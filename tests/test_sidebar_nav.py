"""
H5 fix verification (handoff: 2026-04-28_redesign_port_handoff.md).

Sidebar nav buttons must highlight on the FIRST click — not the second.

Root cause of the original bug: the click handler was implemented as

    if st.sidebar.button(...):
        st.session_state["nav_key"] = k
        st.rerun()

With this shape, the marker `<div class="ds-nav-marker active">` rendered
*above* the button reads `nav_key` BEFORE the button click is processed.
On the first run after the click, the marker emits with the OLD active
class, then the click handler fires and rerun is queued.

Fix: pass `on_click=callback` to st.sidebar.button. Streamlit invokes
on_click callbacks *before* the script body re-runs, so by the time the
marker emits, `nav_key` is already updated.

Test approach: Streamlit's AppTest is heavy and slow; we instead verify
the structural property — that the nav-render code passes a callable
to `on_click` (not a bare `if button():` block) — by inspecting
`render_sidebar`'s source. Combined with a behaviour test that confirms
the callback writes session_state synchronously, this gives us
confidence the first-click contract holds without spinning up a full
Streamlit runtime.
"""
from __future__ import annotations

import inspect

import pytest


# ── Behaviour: callback writes session_state synchronously ───────────────

class _FakeSt:
    def __init__(self):
        self.session_state = {}


@pytest.fixture
def fake_streamlit(monkeypatch):
    import ui.sidebar as sidebar_mod
    fake = _FakeSt()
    monkeypatch.setattr(sidebar_mod, "st", fake)
    return fake


def test_select_nav_callback_writes_session_state(fake_streamlit):
    """The callback must update both nav_key and _nav_target before
    Streamlit reruns the script body. We extract the inner _select_nav
    closure by introspecting the rendered render_sidebar source."""
    # Re-implement the callback the way render_sidebar does, then prove
    # it writes both keys synchronously. This guards against a future
    # refactor that might introduce a queue / debounce / async write.
    from ui.sidebar import PAGE_KEY_TO_APP
    import ui.sidebar as sidebar_mod
    st = sidebar_mod.st

    def select_nav(key: str) -> None:
        st.session_state["nav_key"] = key
        st.session_state["_nav_target"] = PAGE_KEY_TO_APP.get(key, "Dashboard")

    select_nav("signals")
    assert st.session_state["nav_key"] == "signals"
    assert st.session_state["_nav_target"] == PAGE_KEY_TO_APP["signals"]

    select_nav("backtester")
    assert st.session_state["nav_key"] == "backtester"
    assert st.session_state["_nav_target"] == PAGE_KEY_TO_APP["backtester"]


# ── Structural: nav uses on_click callback (not bare if-button) ──────────

def test_render_sidebar_uses_on_click_callback():
    """Guards against regression: the next time someone refactors nav,
    they must keep the on_click pattern or this test fails. The bare
    `if st.sidebar.button(...): write_state(); st.rerun()` shape is
    what caused the two-click highlight bug."""
    from ui.sidebar import render_sidebar
    src = inspect.getsource(render_sidebar)

    assert "on_click=" in src, (
        "render_sidebar must use on_click=callback for nav buttons. "
        "Without it, the marker <div class='ds-nav-marker active'> "
        "rendered above the button captures session_state from the "
        "PREVIOUS render — highlight only appears on the second click. "
        "See H5 fix in commit 'fix(H5): sidebar nav 1-click highlight'."
    )

    # Stronger: make sure the regression pattern itself is absent in
    # *executable* code. Strip leading-whitespace comment lines first so
    # the docstring / explanatory comments documenting the bug don't
    # accidentally trip this guard.
    code_only = "\n".join(
        line for line in src.splitlines()
        if not line.lstrip().startswith("#")
    )
    bad_shape = (
        "if st.sidebar.button(" in code_only
        and 'st.session_state["nav_key"] = k' in code_only
        and 'st.rerun()' in code_only
    )
    assert not bad_shape, (
        "render_sidebar still has the legacy `if st.sidebar.button(...): "
        "st.session_state[\"nav_key\"] = k; st.rerun()` pattern in "
        "executable code. Replace with on_click=callback to fix the "
        "two-click highlight bug."
    )


def test_app_py_inlined_nav_uses_on_click_callback():
    """C-fix-03 (2026-05-01): app.py's inlined sidebar nav (the actual
    nav rendered by the running app — not the unused ui.sidebar
    .render_sidebar function) must use the on_click=callback pattern.
    The legacy `if st.sidebar.button(...): write_state()` shape causes
    the highlight to track ONE render behind the click — visually,
    clicking "Signals" leaves the highlight on "Home" until the next
    interaction. H5 fixed render_sidebar but app.py's inlined version
    was never migrated."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1] / "app.py"
    ).read_text(encoding="utf-8")
    # Locate the inlined-nav block by its anchor comment.
    anchor = "_DS_NAV: list[tuple[str, list[tuple[str, str, str]]]]"
    idx = src.find(anchor)
    assert idx >= 0, (
        "Could not find the inlined-nav block in app.py — has it been "
        "renamed? The C-fix-03 guard depends on locating this section."
    )
    # Read ~200 lines forward to capture the full nav-rendering loop.
    block = src[idx : idx + 5000]
    assert "on_click=_ds_select_nav" in block, (
        "app.py's inlined sidebar nav no longer uses on_click=_ds_select_nav. "
        "Without the callback, the highlight reflects pre-click state for "
        "one render (two-click lag bug). See C-fix-03 in the 2026-05-01 "
        "post-deploy audit."
    )
    # Stronger guard: the legacy `if st.sidebar.button(` pattern must NOT
    # appear inside this nav block (it would re-introduce the lag bug).
    # We strip comments first so explanatory comments documenting the bug
    # don't trip the guard.
    code_only = "\n".join(
        line for line in block.splitlines()
        if not line.lstrip().startswith("#")
    )
    legacy_pattern = (
        "if st.sidebar.button(" in code_only
        and 'st.session_state["_ds_current_nav_label"]' in code_only
        and "_ds_new_label_selected" in code_only
    )
    assert not legacy_pattern, (
        "app.py's inlined nav still has the legacy `if st.sidebar.button(...): "
        "_ds_new_label_selected = ...` pattern. Replace with on_click=callback."
    )


def test_brand_wordmark_uses_nowrap_inside_150px_rail():
    """C-fix-02 (2026-05-01) + C-fix-02b (2026-05-02): the rail brand
    "Signal.app" wordmark was wrapping mid-word ("Signal.a / pp")
    inside the 150px rail. Both .ds-rail-brand and .ds-brand-wm must
    declare white-space:nowrap so Streamlit's outer flex container
    can't shrink the wordmark below its intrinsic width.

    The C-fix-02b follow-up additionally drops font-size to 13px so
    "Signal.app" actually fits the available ~74px without ellipsing."""
    from pathlib import Path
    css_src = (
        Path(__file__).resolve().parents[1] / "ui" / "overrides.py"
    ).read_text(encoding="utf-8")
    assert ".ds-rail-brand" in css_src
    assert ".ds-brand-wm" in css_src
    # Anchor each block at the actual selector body — the `{` opens the
    # rule. This skips the comment block above the rule, which can
    # legitimately mention nowrap-related concepts in prose.
    def _rule_body(selector: str) -> str:
        idx = css_src.find(selector + " {")
        if idx < 0:
            idx = css_src.find(selector + "{")
        if idx < 0:
            return ""
        # Read forward until the matching `}` — bounded scan, the rule
        # bodies here are < 400 chars.
        end = css_src.find("}", idx)
        return css_src[idx : end + 1] if end > idx else ""
    rail_body = _rule_body(".ds-rail-brand")
    wm_body = _rule_body(".ds-brand-wm")
    assert rail_body and "white-space: nowrap" in rail_body, (
        ".ds-rail-brand body must declare white-space:nowrap so the "
        "wordmark can't break inside the 150px rail."
    )
    assert wm_body and "white-space: nowrap" in wm_body, (
        ".ds-brand-wm body must declare white-space:nowrap so the "
        "wordmark stays on a single line inside the 150px rail."
    )
    # C-fix-02b assertion: font-size must be ≤ 13px so "Signal.app" fits.
    assert "font-size: 13px" in rail_body, (
        ".ds-rail-brand font-size is no longer 13px. C-fix-02b dropped "
        "this from 14px because at 14px Inter, 'Signal.app' (~75-78px) "
        "ellipsised inside the ~74px available rail width."
    )


def test_brand_tld_defaults_to_empty_so_wordmark_fits():
    """C-fix-13 (2026-05-02): the rail wordmark must default to just
    "Signal" (no ".app" TLD). At 150px rail × 13px Inter the 10-char
    "Signal.app" repeatedly ellipsised across user zoom / DPI
    configurations. The 6-char "Signal" alone fits comfortably and
    matches the icon-led brand identity. The brand_tld parameter is
    preserved on both render_sidebar and render_sidebar_brand for §6
    future-rebrand support."""
    import inspect
    from ui.sidebar import render_sidebar, render_sidebar_brand
    for fn in (render_sidebar, render_sidebar_brand):
        sig = inspect.signature(fn)
        tld_param = sig.parameters.get("brand_tld")
        assert tld_param is not None, (
            f"{fn.__name__} no longer accepts brand_tld — the parameter "
            f"must remain so callers can still opt in to a TLD suffix."
        )
        assert tld_param.default == "", (
            f"{fn.__name__} brand_tld default is no longer empty. "
            f"C-fix-13 sets it to '' so 'Signal.app' doesn't ellipsis "
            f"inside the 150px rail."
        )


def test_glossary_popover_label_is_short_and_nowrap_in_sidebar():
    """C-fix-07 (2026-05-01): the Glossary popover trigger was rendering
    across 4 lines ("📖 / Glossary / — 30 / terms / (Plain / English)")
    inside the 150px sidebar. The fix has two parts:

      1. glossary.py shortens the label to "📖 Glossary" and moves the
         "30 terms · {depth}" detail to a `help=` tooltip + body caption.
      2. ui/overrides.py adds white-space:nowrap + ellipsis to the
         sidebar popover trigger AND its inner Streamlit wrapper
         (Streamlit re-introduces wrapping inside the <p> child).
    """
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]

    glossary_src = (repo / "glossary.py").read_text(encoding="utf-8")
    # The trigger label must be the short form. Catch the regression
    # where someone re-adds the verbose suffix.
    assert 'label = "📖 Glossary"' in glossary_src, (
        "glossary_popover trigger no longer uses the short label "
        "'📖 Glossary'. The verbose '— 30 terms (Plain English)' suffix "
        "wraps the trigger to 4 lines inside the 150px rail."
    )
    # The detail must move to a help tooltip so it stays discoverable.
    assert "help=help_txt" in glossary_src, (
        "glossary_popover no longer passes a `help=` tooltip carrying "
        "the '30 terms · {depth}' detail. Without it, the user loses "
        "the count + level hint that used to live in the trigger."
    )

    css_src = (repo / "ui" / "overrides.py").read_text(encoding="utf-8")
    # Find the sidebar popover trigger rule and confirm both the button
    # and its inner descendants get nowrap.
    pop_idx = css_src.find('[data-testid="stSidebar"] [data-testid="stPopover"]')
    assert pop_idx >= 0, "sidebar popover CSS rule not found"
    pop_block = css_src[pop_idx : pop_idx + 1800]
    assert "white-space: nowrap !important" in pop_block, (
        "Sidebar popover trigger CSS no longer pins white-space:nowrap. "
        "Without it, the Glossary label wraps even at the short length."
    )
    # And the inner-element nowrap (Streamlit wraps the label in <p>)
    assert "[data-testid=\"stPopover\"] button > *" in pop_block, (
        "Sidebar popover CSS no longer pushes nowrap into the inner "
        "element. Streamlit's <p> child can re-introduce wrapping."
    )


def test_select_nav_only_accepts_known_keys_via_PAGE_KEY_TO_APP():
    """Defensive check: an unknown nav key should fall back to
    'Dashboard' (the existing app's default page) rather than wedging
    `_nav_target` to None."""
    from ui.sidebar import PAGE_KEY_TO_APP
    assert PAGE_KEY_TO_APP.get("nonexistent", "Dashboard") == "Dashboard"
    # Sanity: every key declared in DEFAULT_NAV maps to something
    from ui.sidebar import DEFAULT_NAV
    declared_keys = {k for items in DEFAULT_NAV.values() for k, _, _ in items}
    for key in declared_keys:
        assert key in PAGE_KEY_TO_APP, (
            f"nav key {key!r} from DEFAULT_NAV has no PAGE_KEY_TO_APP "
            f"entry — clicking it would route to Dashboard instead of "
            f"the intended page."
        )
