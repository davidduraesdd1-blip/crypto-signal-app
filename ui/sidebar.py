"""
ui/sidebar.py — Shared sibling-family left rail, top bar, and page header.

Mirrors the static mockups in shared-docs/design-mockups/sibling-family-crypto-signal*.html.
Streamlit's native sidebar is wrapped with our own CSS so it reads as the mockup's
left rail. The top bar, page header, and macro strip render as the first elements
of the main column via st.markdown.

Every page should:

    from ui import inject_theme, inject_streamlit_overrides, render_sidebar, render_top_bar, page_header

    inject_theme("crypto-signal-app", theme=st.session_state.get("theme", "dark"))
    inject_streamlit_overrides()
    render_sidebar(active="home", user_level=...)
    render_top_bar(breadcrumb=("Markets", "Home"), user_level=...)
    page_header(title="Market home", subtitle="...", data_sources=[...])
"""
from __future__ import annotations

from typing import Iterable, Literal, Sequence

try:
    import streamlit as st
except ImportError:  # pragma: no cover — module is streamlit-specific
    st = None  # type: ignore

from .design_system import ACCENTS, family_of


# ── Navigation model ──────────────────────────────────────────────────

NavItem = tuple[str, str, str]  # (key, label, icon)

# Full nav as shown on the mockups. The key maps to the internal page key the
# running Streamlit app already uses (Dashboard, Config Editor, etc.) via
# PAGE_KEY_TO_APP below — preserves existing logic, only relabels.
DEFAULT_NAV: dict[str, list[NavItem]] = {
    "Markets": [
        ("home",     "Home",       "◉"),
        ("signals",  "Signals",    "▲"),
        ("regimes",  "Regimes",    "◈"),
    ],
    "Research": [
        ("backtester", "Backtester", "∿"),
        ("onchain",    "On-chain",   "⬡"),
    ],
    "Account": [
        ("alerts",   "Alerts",     "◐"),
        ("settings", "Settings",   "⚙"),
    ],
}

# Maps the mockup-friendly key → existing app.py page key. Keeps all the
# existing page_* functions intact — only the presentation changes.
PAGE_KEY_TO_APP: dict[str, str] = {
    "home":       "Dashboard",
    "signals":    "Dashboard",        # Signals tab inside Dashboard
    "regimes":    "Dashboard",        # Regime section inside Dashboard
    "backtester": "Backtest Viewer",
    "onchain":    "Dashboard",        # On-chain subsection inside Dashboard
    "alerts":     "Config Editor",    # Alerts tab in Settings
    "settings":   "Config Editor",
}


# ── Sidebar renderer ──────────────────────────────────────────────────

def render_sidebar(
    *,
    app: str = "crypto-signal-app",
    active: str = "home",
    brand_name: str = "Signal",
    brand_tld: str = ".app",
    brand_glyph: str = "◈",
    user_level: Literal["beginner", "intermediate", "advanced"] = "beginner",
) -> str:
    """
    Render the brand header + grouped nav inside st.sidebar.

    Returns the active nav key, normalised via st.session_state['nav_key'] so
    downstream code can read it without re-computing.
    """
    if st is None:
        return active

    accent = ACCENTS[app]  # type: ignore[index]

    # The brand card — matches the mockup "◈ Signal.app" wordmark
    st.sidebar.markdown(
        f"""
        <div class="ds-rail-brand">
          <div class="ds-brand-dot" style="background:{accent['accent']};color:{accent['accent_ink']};">
            {brand_glyph}
          </div>
          <div class="ds-brand-wm">
            {brand_name}<span style="color:var(--text-muted);">{brand_tld}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Grouped nav rendered as clickable buttons — uses a radio under the hood
    # for selection state so Streamlit handles reruns cleanly, but visually
    # styled to look like the mockup.
    flat: list[tuple[str, str, str, str]] = []  # (group, key, label, icon)
    for group, items in DEFAULT_NAV.items():
        for k, lbl, ic in items:
            flat.append((group, k, lbl, ic))

    keys = [f[1] for f in flat]
    if active not in keys:
        active = keys[0]

    # Session default
    if "nav_key" not in st.session_state:
        st.session_state["nav_key"] = active

    # Render each group header + items. Use st.button for nav items so
    # Streamlit reruns on click; visual look comes from overrides.py.
    for group, items in DEFAULT_NAV.items():
        st.sidebar.markdown(
            f'<div class="ds-nav-group">{group}</div>',
            unsafe_allow_html=True,
        )
        for k, lbl, ic in items:
            is_active = (st.session_state.get("nav_key") == k)
            btn_class = "ds-nav-item active" if is_active else "ds-nav-item"
            # Streamlit doesn't let us style a button by class directly; we tag
            # the container via a wrapper markdown + button — the overrides
            # target the first-child button inside `[data-testid="stSidebar"]
            # div:has(> .ds-nav-marker.<key>)`.
            st.sidebar.markdown(
                f'<div class="ds-nav-marker {btn_class}" data-nav-key="{k}">'
                f'<span class="ds-nav-dot"></span>'
                f'<span class="ds-nav-icon">{ic}</span>'
                f'<span class="ds-nav-lbl">{lbl}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.sidebar.button(
                lbl,
                key=f"ds_nav_{k}",
                use_container_width=True,
                type=("primary" if is_active else "secondary"),
            ):
                st.session_state["nav_key"] = k
                st.session_state["_nav_target"] = PAGE_KEY_TO_APP.get(k, "Dashboard")
                st.rerun()

    return st.session_state.get("nav_key", active)


# ── Top bar ───────────────────────────────────────────────────────────

def render_top_bar(
    *,
    breadcrumb: Sequence[str] = ("Markets", "Home"),
    user_level: Literal["beginner", "intermediate", "advanced"] = "beginner",
    show_level: bool = True,
    show_refresh: bool = True,
    show_theme: bool = True,
) -> None:
    """
    Render the top bar: breadcrumb + level pills + refresh + theme. Renders
    into the main column (must be called BEFORE any other page markdown).
    """
    if st is None:
        return

    *rest, last = list(breadcrumb) or ["", ""]
    crumb_html = " / ".join(rest) + (" / " if rest else "") + f"<b>{last}</b>"

    level_html = ""
    if show_level:
        lvls = [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")]
        buttons = "".join(
            f'<button class="{"on" if user_level == k else ""}" data-level="{k}">{lbl}</button>'
            for k, lbl in lvls
        )
        level_html = f'<div class="ds-level-group">{buttons}</div>'

    refresh_html = '<button class="ds-chip-btn" data-action="refresh">↻ Refresh</button>' if show_refresh else ""
    theme_html   = '<button class="ds-chip-btn" data-action="theme">☾ Theme</button>' if show_theme else ""

    st.markdown(
        f"""
        <div class="ds-topbar">
          <div class="ds-crumbs">{crumb_html}</div>
          <div class="ds-topbar-spacer"></div>
          {level_html}
          {refresh_html}
          {theme_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Page header ───────────────────────────────────────────────────────

def page_header(
    title: str,
    subtitle: str = "",
    *,
    data_sources: Iterable[tuple[str, str]] | None = None,
) -> None:
    """
    Render the page-hd block seen on every mockup: title + subtitle on the
    left, data-source pills on the right.

    data_sources: iterable of (label, status). status ∈ {live, cached, down}.
    """
    if st is None:
        return

    if data_sources:
        pills = []
        for label, status in data_sources:
            cls = "ds-pill"
            if status == "cached":
                cls += " warn"
            elif status == "down":
                cls += " down"
            pills.append(f'<span class="{cls}"><span class="tick"></span> {label} · {status}</span>')
        pills_html = f'<div class="ds-row">{"".join(pills)}</div>'
    else:
        pills_html = ""

    sub_html = f'<div class="ds-page-sub">{subtitle}</div>' if subtitle else ""

    st.markdown(
        f"""
        <div class="ds-page-hd">
          <div>
            <h1 class="ds-page-title">{title}</h1>
            {sub_html}
          </div>
          {pills_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Macro strip ───────────────────────────────────────────────────────

def macro_strip(items: Sequence[tuple[str, str, str]]) -> None:
    """
    Render the 5-col macro strip from the Home mockup.
    Each item: (label, value, sub). sub may contain a leading "+" / "−".
    """
    if st is None:
        return

    cells = []
    for label, value, sub in items:
        cells.append(
            f'<div><div class="lbl">{label}</div>'
            f'<div class="val">{value}</div>'
            f'<div class="sub">{sub}</div></div>'
        )
    st.markdown(
        f'<div class="ds-card ds-strip">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )
