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

import html as _html
from typing import Callable, Iterable, Literal, Sequence

try:
    import streamlit as st
except ImportError:  # pragma: no cover — module is streamlit-specific
    st = None  # type: ignore

from .design_system import ACCENTS, family_of


# ── Single source of truth for user level ─────────────────────────────
# C1 fix (2026-04-28): every page must read the level via this helper so
# the Beginner/Intermediate/Advanced toggle is observed consistently.
# Reads st.session_state["user_level"] each call — never cache the result
# at module top, or the toggle will appear inert until the next full reload.

_VALID_LEVELS = ("beginner", "intermediate", "advanced")
_DEFAULT_LEVEL = "beginner"


def current_user_level() -> str:
    """Return the active user level from session state.

    Always returns one of `_VALID_LEVELS`; falls back to "beginner" if
    state is missing or corrupted. Use this at the start of every page
    section instead of reading session_state directly so the toggle's
    effect is visible app-wide on the very next render.
    """
    if st is None:
        return _DEFAULT_LEVEL
    val = st.session_state.get("user_level", _DEFAULT_LEVEL)
    if val not in _VALID_LEVELS:
        return _DEFAULT_LEVEL
    return val


def level_label(level: str | None = None) -> str:
    """Capitalised label for display, e.g. "Beginner"."""
    lv = (level or current_user_level()).lower()
    return lv.capitalize() if lv in _VALID_LEVELS else "Beginner"


# ── Navigation model ──────────────────────────────────────────────────

NavItem = tuple[str, str, str]  # (key, label, icon)

# Full nav as shown on the mockups. The key maps to the internal page key the
# running Streamlit app already uses (Dashboard, Config Editor, etc.) via
# PAGE_KEY_TO_APP below — preserves existing logic, only relabels.
DEFAULT_NAV: dict[str, list[NavItem]] = {
    "Markets": [
        ("home",     "Home",         "◉"),
        ("signals",  "Signals",      "▲"),
        ("regimes",  "Regimes",      "◈"),
    ],
    "Research": [
        ("backtester", "Backtester", "∿"),
        ("onchain",    "On-chain",   "⬡"),
    ],
    "Account": [
        ("alerts",       "Alerts",       "◐"),
        # C1 (2026-04-29): AI Assistant promoted from a sub-link inside
        # Settings to a first-class nav item — matches the full-mockup-
        # match spec and exposes the agent surface (page_agent at the
        # `Agent` page-router key) without burying it in Settings.
        # Key is `ai_assistant` (not `agent`) per Phase C plan §C1; that
        # leaves `agent` available as a session_state namespace for the
        # autonomous agent runtime without colliding with the nav key.
        ("ai_assistant", "AI Assistant", "💬"),
        ("settings",     "Settings",     "⚙"),
    ],
}

# Maps the mockup-friendly key → existing app.py page key. Keeps all the
# existing page_* functions intact — only the presentation changes.
#
# C1 (2026-04-29): the legacy aliases for signals/regimes/onchain
# all routed to "Dashboard" (a Tabs container that no longer exists
# post-redesign), so clicking those nav items navigated to the wrong
# page. Each now maps to its real page-router key — see app.py
# `if page == "..." :` block at line 9923+.
PAGE_KEY_TO_APP: dict[str, str] = {
    "home":         "Dashboard",
    "signals":      "Signals",
    "regimes":      "Regimes",
    "backtester":   "Backtest Viewer",
    "onchain":      "On-chain",
    "alerts":       "Config Editor",   # TODO C6 — split into page_alerts
    "ai_assistant": "Agent",
    "settings":     "Config Editor",
}


# ── Sidebar brand block (standalone — usable without full nav swap) ──

def render_sidebar_brand(
    *,
    app: str = "crypto-signal-app",
    brand_name: str = "Signal",
    brand_tld: str = ".app",
    brand_glyph: str = "◈",
    version: str = "",
) -> None:
    """Render just the mockup brand block at the top of the sidebar.
    Use this when the caller wants to keep its existing nav but still get
    the new branded rail. Each sibling app passes its own name/tld/glyph."""
    if st is None:
        return
    accent = ACCENTS.get(app, ACCENTS["crypto-signal-app"])  # type: ignore[index]
    st.sidebar.markdown(
        f'<div class="ds-rail-brand">'
        f'<div class="ds-brand-dot" style="background:{accent["accent"]};color:{accent["accent_ink"]};">{brand_glyph}</div>'
        f'<div class="ds-brand-wm">{brand_name}<span style="color:var(--text-muted);">{brand_tld}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if version:
        st.sidebar.markdown(
            f'<div style="font-size:10px;color:var(--text-muted);letter-spacing:0.08em;'
            f'text-transform:uppercase;padding:0 10px 12px;">{version}</div>',
            unsafe_allow_html=True,
        )


# ── Sidebar renderer (full — brand + grouped nav + session state) ──────

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
        f'<div class="ds-rail-brand">'
        f'<div class="ds-brand-dot" style="background:{accent["accent"]};color:{accent["accent_ink"]};">{brand_glyph}</div>'
        f'<div class="ds-brand-wm">{brand_name}<span style="color:var(--text-muted);">{brand_tld}</span></div>'
        f'</div>',
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

    # Render each group header + items.
    #
    # H5 fix (2026-04-28): nav buttons use the `on_click=` callback
    # pattern instead of `if st.sidebar.button(...): write_state();
    # st.rerun()`. With the inline pattern, the marker `<div>` rendered
    # *above* the button captured `is_active` from the OLD session_state
    # (because the click handler runs only AFTER the markdown emits),
    # so the highlight only appeared on the second render. Callbacks
    # run *before* the script body re-runs, so by the time the marker
    # emits, `nav_key` is already updated and the active class is
    # correct on the very first click.
    def _select_nav(key: str) -> None:
        st.session_state["nav_key"] = key
        st.session_state["_nav_target"] = PAGE_KEY_TO_APP.get(key, "Dashboard")

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
            st.sidebar.button(
                lbl,
                key=f"ds_nav_{k}",
                use_container_width=True,
                type=("primary" if is_active else "secondary"),
                on_click=_select_nav,
                args=(k,),
            )

    return st.session_state.get("nav_key", active)


# ── Top bar ───────────────────────────────────────────────────────────

def render_top_bar(
    *,
    breadcrumb: Sequence[str] = ("Markets", "Home"),
    user_level: Literal["beginner", "intermediate", "advanced"] = "beginner",
    show_level: bool = True,
    show_refresh: bool = True,
    show_theme: bool = True,
    on_refresh=None,
    on_theme=None,
    status_pills: Sequence[dict] | None = None,
) -> None:
    """
    Render the top bar: breadcrumb + level pills + refresh + theme.

    Level pills are real Streamlit buttons that write to
    `st.session_state["user_level"]` and trigger a rerun on click.

    Refresh and theme are real Streamlit buttons when `on_refresh` /
    `on_theme` callbacks are provided; otherwise they fall back to a
    decorative chip and the user is expected to use the legacy sidebar
    controls.

    Must be called BEFORE any other main-column markdown.
    """
    if st is None:
        return

    *rest, last = list(breadcrumb) or ["", ""]
    crumb_html = " / ".join(rest) + (" / " if rest else "") + f"<b>{last}</b>"

    # 6-col row: breadcrumb + 3 level pills + refresh + theme. Ratios are
    # tuned so "Intermediate" (longest label) fits on one line at 12.5px font
    # without ellipsis on a typical desktop viewport.
    cols = st.columns([3, 1.4, 1.7, 1.4, 1.2, 1.2])

    with cols[0]:
        # data-topbar="1" is the CSS hook for scoped topbar-button styling
        # (see ui/overrides.py — the rule targets buttons in the same
        # stHorizontalBlock as this marker so they get nowrap + tighter padding).
        _pills_html = ""
        if status_pills:
            _tone_to_cls = {
                "info":    "ds-status-pill info",
                "success": "ds-status-pill success",
                "warning": "ds-status-pill warning",
                "danger":  "ds-status-pill danger",
                "muted":   "ds-status-pill muted",
            }
            _pp = []
            for p in status_pills:
                cls = _tone_to_cls.get(p.get("tone", "muted"), "ds-status-pill muted")
                icon = p.get("icon", "")
                lbl = p.get("label", "")
                _pp.append(f'<span class="{cls}">{icon} {lbl}</span>')
            _pills_html = (
                f'<span style="display:inline-flex;gap:6px;margin-left:12px;'
                f'vertical-align:middle;">{"".join(_pp)}</span>'
            )
        st.markdown(
            f'<div class="ds-crumbs" data-topbar="1">'
            f'{crumb_html}{_pills_html}</div>',
            unsafe_allow_html=True,
        )

    # H1+H2 fix (2026-04-28): topbar buttons now use on_click=callback so
    # the click frame paints with the new state immediately (no more
    # "type=secondary then primary" two-render lag on level pills).
    # Refresh additionally fires st.toast + records a wall-clock
    # timestamp so users see immediate "refreshed Xs ago" feedback.
    def _select_level(level: str) -> None:
        st.session_state["user_level"] = level

    def _on_topbar_refresh() -> None:
        if callable(on_refresh):
            try:
                on_refresh()
            except Exception:  # pragma: no cover — defensive only
                pass
        # Wall-clock timestamp for the "refreshed Xs ago" caption.
        import time as _time
        st.session_state["_topbar_last_refresh_at"] = _time.time()
        try:
            st.toast("Data refreshed", icon="✓")
        except Exception:
            pass

    def _on_topbar_theme() -> None:
        if callable(on_theme):
            try:
                on_theme()
            except Exception:  # pragma: no cover
                pass

    if show_level:
        lvls = [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")]
        for idx, (k, lbl) in enumerate(lvls, start=1):
            with cols[idx]:
                st.button(
                    lbl,
                    key=f"ds_topbar_lvl_{k}",
                    use_container_width=True,
                    type=("primary" if user_level == k else "secondary"),
                    help=f"Switch to {lbl} view",
                    on_click=_select_level,
                    args=(k,),
                )

    if show_refresh:
        with cols[4]:
            if on_refresh is not None:
                st.button(
                    "↻ Refresh",
                    key="ds_topbar_refresh",
                    use_container_width=True,
                    help="Clear all caches and reload data from all sources",
                    on_click=_on_topbar_refresh,
                )
                # Persistent caption directly under the button so users
                # have a passive indicator of recent refresh activity even
                # after the toast fades.
                _last = st.session_state.get("_topbar_last_refresh_at")
                if _last:
                    import time as _time
                    _delta = max(0.0, _time.time() - float(_last))
                    if _delta < 60:
                        _ago = f"✓ refreshed {int(_delta)}s ago"
                    elif _delta < 3600:
                        _ago = f"✓ refreshed {int(_delta // 60)}m ago"
                    else:
                        _ago = f"✓ refreshed {int(_delta // 3600)}h ago"
                    st.markdown(
                        f'<div style="font-size:10px;color:var(--text-muted);'
                        f'text-align:center;margin-top:2px;letter-spacing:0.02em;">'
                        f'{_html.escape(_ago)}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div class="ds-chip-btn" style="text-align:center;opacity:0.5;">↻ Refresh</div>',
                    unsafe_allow_html=True,
                )

    if show_theme:
        with cols[5]:
            if on_theme is not None:
                st.button(
                    "☾ Theme",
                    key="ds_topbar_theme",
                    use_container_width=True,
                    help="Toggle light / dark mode",
                    on_click=_on_topbar_theme,
                )
            else:
                st.markdown(
                    '<div class="ds-chip-btn" style="text-align:center;opacity:0.5;">☾ Theme</div>',
                    unsafe_allow_html=True,
                )


# ── Page header ───────────────────────────────────────────────────────

def page_header(
    title: str,
    subtitle: str = "",
    *,
    data_sources: Iterable[tuple[str, str]] | None = None,
    show_level: bool = True,
) -> None:
    """
    Render the page-hd block seen on every mockup: title + subtitle on the
    left, data-source pills on the right.

    data_sources: iterable of (label, status). status ∈ {live, cached, down}.
    show_level: when True (default), prepends a "View: <Level>" pill to the
        right-hand pill row so the topbar Beginner/Intermediate/Advanced
        toggle has a guaranteed visible effect on every page (C1 fix,
        2026-04-28).
    """
    if st is None:
        return

    # P1 audit fix — escape every interpolated caller string. Defense
    # in depth: even if today's callers only pass static literals, a
    # later change that pipes API/DB-derived data through page_header
    # must not become a stored-XSS surface.
    pills: list[str] = []

    if show_level:
        lv = current_user_level()
        # Tone the pill differently per level so the change is visually
        # obvious even with the title/subtitle unchanged.
        lv_cls = {
            "beginner":     "ds-pill",
            "intermediate": "ds-pill warn",
            "advanced":     "ds-pill",
        }.get(lv, "ds-pill")
        # Use a distinctive style attribute on the advanced pill to make
        # the three levels visually distinct without relying on color alone.
        lv_lbl = level_label(lv)
        pills.append(
            f'<span class="{lv_cls}" data-level="{lv}" '
            f'title="Active view level — set via the topbar toggle">'
            f'<span class="tick"></span> View · {_html.escape(lv_lbl)}'
            f'</span>'
        )

    if data_sources:
        for label, status in data_sources:
            cls = "ds-pill"
            if status == "cached":
                cls += " warn"
            elif status == "down":
                cls += " down"
            pills.append(
                f'<span class="{cls}"><span class="tick"></span> '
                f'{_html.escape(str(label))} · {_html.escape(str(status))}</span>'
            )

    pills_html = f'<div class="ds-row">{"".join(pills)}</div>' if pills else ""

    sub_html = (
        f'<div class="ds-page-sub">{_html.escape(str(subtitle))}</div>'
        if subtitle else ""
    )

    st.markdown(
        f'<div class="ds-page-hd">'
        f'<div>'
        f'<h1 class="ds-page-title">{_html.escape(str(title))}</h1>'
        f'{sub_html}'
        f'</div>'
        f'{pills_html}'
        f'</div>',
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

    # P1 audit fix — escape interpolated caller strings (defense in depth).
    cells = []
    for label, value, sub in items:
        cells.append(
            f'<div><div class="lbl">{_html.escape(str(label))}</div>'
            f'<div class="val">{_html.escape(str(value))}</div>'
            f'<div class="sub">{_html.escape(str(sub))}</div></div>'
        )
    st.markdown(
        f'<div class="ds-card ds-strip">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


# ── Hero signal cards ─────────────────────────────────────────────────

def hero_signal_card_html(
    ticker: str,
    price: float | None,
    change_pct: float | None,
    signal: Literal["BUY", "HOLD", "SELL", None] = None,
    regime_label: str = "",
    regime_confidence: float | None = None,
) -> str:
    """Return HTML for a single hero signal card (matches Home mockup)."""
    # Format price
    if price is None:
        price_str = "—"
    elif price >= 1000:
        price_str = f"{price:,.0f}"
    elif price >= 10:
        price_str = f"{price:,.2f}"
    else:
        price_str = f"{price:,.4f}"

    # Format change
    if change_pct is None:
        change_cls = ""
        change_str = "—"
    elif change_pct > 0:
        change_cls = "up"
        change_str = f"+ {change_pct:.2f}% · 24h"
    elif change_pct < 0:
        change_cls = "down"
        change_str = f"− {abs(change_pct):.2f}% · 24h"
    else:
        change_cls = ""
        change_str = "0.00% · 24h"

    # Signal badge (shape + color — matches mockup + CLAUDE.md §8 color-blind rule)
    badge_html = ""
    if signal in ("BUY", "HOLD", "SELL"):
        shape, css_class, label = {
            "BUY":  ("▲", "ds-sb-buy",  "Buy"),
            "HOLD": ("■", "ds-sb-hold", "Hold"),
            "SELL": ("▼", "ds-sb-sell", "Sell"),
        }[signal]
        badge_html = f'<span class="ds-signal-badge {css_class}">{shape} {label}</span>'

    # Regime line — callers pass a clean label (Bull/Bear/etc). Strip any
    # accidental "Regime" prefix so we never render "Regime: Regime Bull".
    # P1 audit fix — regime_label can flow from API/DB output via the
    # composite signal layer; escape before HTML interpolation.
    regime_html = ""
    if regime_label:
        _clean = str(regime_label).strip()
        _low = _clean.lower()
        for _prefix in ("regime: ", "regime:", "regime "):
            if _low.startswith(_prefix):
                _clean = _clean[len(_prefix):].strip()
                break
        # `regime_confidence` is numeric; only `_clean` needs escaping
        try:
            _conf_int = int(regime_confidence) if regime_confidence is not None else None
        except (TypeError, ValueError):
            _conf_int = None
        conf_txt = f" · {_conf_int}% conf" if _conf_int is not None else ""
        regime_html = (
            f'<div class="ds-regime"><span class="dot"></span> '
            f'Regime: {_html.escape(_clean)}{conf_txt}</div>'
        )

    # Single-line to avoid Streamlit markdown's 4-space = code-block rule.
    # P1 audit fix — escape `ticker` (caller-supplied symbol). Numeric strings
    # (price_str / change_str) and class names are produced internally above.
    return (
        f'<div class="ds-card ds-signal-hero">'
        f'<div class="ds-signal-lhs">'
        f'<div class="ds-signal-ticker">{_html.escape(str(ticker))}</div>'
        f'<div class="ds-signal-big">{price_str}</div>'
        f'<div class="ds-signal-change {change_cls}">{change_str}</div>'
        f'</div>'
        f'<div class="ds-signal-rhs">'
        f'{badge_html}{regime_html}'
        f'</div>'
        f'</div>'
    )


def hero_signal_cards_row(cards: Sequence[dict]) -> None:
    """
    Render a 3-col row of hero signal cards.
    Each card dict keys: ticker, price, change_pct, signal, regime_label, regime_confidence.
    """
    if st is None:
        return
    html = "".join(
        hero_signal_card_html(
            ticker=c.get("ticker", "—"),
            price=c.get("price"),
            change_pct=c.get("change_pct"),
            signal=c.get("signal"),
            regime_label=c.get("regime_label", ""),
            regime_confidence=c.get("regime_confidence"),
        )
        for c in cards
    )
    st.markdown(
        f'<div class="ds-hero-grid">{html}</div>',
        unsafe_allow_html=True,
    )


# ── Watchlist ─────────────────────────────────────────────────────────

def watchlist_card(
    title: str,
    subtitle: str,
    rows: Sequence[dict],
) -> None:
    """Render the 2-col watchlist card from the Home mockup.
    Each row dict: ticker, price, change_pct, spark_points (list of (x, y) tuples).
    """
    if st is None:
        return
    row_html = []
    for r in rows:
        ticker = r.get("ticker", "—")
        price = r.get("price")
        change = r.get("change_pct")
        if price is None:
            price_str = "—"
        elif price >= 1000:
            price_str = f"${price:,.0f}"
        elif price >= 10:
            price_str = f"${price:,.2f}"
        else:
            price_str = f"${price:,.4f}"
        if change is None:
            change_cls, change_str = "", "—"
        elif change > 0:
            change_cls, change_str = "up", f"+{change:.2f}%"
        elif change < 0:
            change_cls, change_str = "down", f"−{abs(change):.2f}%"
        else:
            change_cls, change_str = "", "0.00%"
        spark_points = r.get("spark_points") or []
        if spark_points:
            stroke = "#22c55e" if (change is not None and change >= 0) else "#ef4444"
            pts = " ".join(f"{x},{y}" for x, y in spark_points)
            spark = (
                f'<svg class="ds-spark" viewBox="0 0 80 22" preserveAspectRatio="none">'
                f'<polyline fill="none" stroke="{stroke}" stroke-width="1.5" points="{pts}"/>'
                f"</svg>"
            )
        else:
            spark = '<svg class="ds-spark" viewBox="0 0 80 22"></svg>'
        row_html.append(
            f'<div class="ds-wl-row">'
            f'<div class="t">{ticker}</div>'
            f'<div class="p">{price_str}</div>'
            f'<div class="d {change_cls}">{change_str}</div>'
            f"{spark}"
            f"</div>"
        )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd">'
        f'<div class="ds-card-title">{title}</div>'
        f'<div class="ds-card-sub">{subtitle}</div>'
        f'</div>'
        f'<div class="ds-watchlist">{"".join(row_html)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Backtest preview card (4-KPI grid) ────────────────────────────────

def backtest_preview_card(
    title: str,
    subtitle: str,
    kpis: Sequence[tuple[str, str, str, str]],
) -> None:
    """Render the 2×2 KPI grid shown next to the Watchlist on Home.
    Each kpi: (label, value, delta_text, delta_direction ∈ {up, down, ""}).
    """
    if st is None:
        return
    cells = []
    for label, value, delta_text, direction in kpis:
        dc = f" {direction}" if direction in ("up", "down") else ""
        val_color = ""
        if direction == "up":
            val_color = ' style="color: var(--success);"'
        elif direction == "down":
            val_color = ' style="color: var(--danger);"'
        cells.append(
            f'<div class="ds-kpi">'
            f'<div class="ds-kpi-label">{label}</div>'
            f'<div class="ds-kpi-value"{val_color}>{value}</div>'
            f'<div class="ds-kpi-delta{dc}">{delta_text}</div>'
            f"</div>"
        )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd">'
        f'<div class="ds-card-title">{title}</div>'
        f'<div class="ds-card-sub">{subtitle}</div>'
        f'</div>'
        f'<div class="ds-kpi-grid">{"".join(cells)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Regime card ───────────────────────────────────────────────────────

REGIME_VARIANT = {
    "bull":         "bull",
    "bullish":      "bull",
    "trending":     "bull",  # generic trending — scan's default, lean bull visually
    "bear":         "bear",
    "bearish":      "bear",
    "transition":   "trans",
    "trans":        "trans",
    "ranging":      "trans",
    "range":        "trans",
    "chop":         "trans",
    "accumulation": "accum",
    "accum":        "accum",
    "distribution": "dist",
    "dist":         "dist",
}


def _clean_regime_state(state: str) -> tuple[str, str]:
    """Return (display_state, variant_key) for a raw regime string.
    Strips "Regime " prefix and maps to one of the 5 mockup states."""
    raw = str(state or "").strip()
    low = raw.lower()
    for prefix in ("regime: ", "regime:", "regime "):
        if low.startswith(prefix):
            raw = raw[len(prefix):].strip()
            low = raw.lower()
            break
    # Exact taxonomy hit?
    if low in REGIME_VARIANT:
        return raw.title(), REGIME_VARIANT[low]
    # Contains hit (e.g. "Trending: Bull" or "Trending Bull")
    if "bull" in low and "bear" not in low:
        return "Bull", "bull"
    if "bear" in low:
        return "Bear", "bear"
    if "accum" in low:
        return "Accumulation", "accum"
    if "dist" in low:
        return "Distribution", "dist"
    if "trans" in low or "rang" in low or "chop" in low:
        return "Transition", "trans"
    if "trend" in low:
        return "Bull", "bull"
    # Unknown — show raw text, neutral amber border
    return raw.title() if raw else "—", "trans"


def regime_card_html(
    ticker: str,
    state: str,
    confidence: float | None = None,
    since: str = "",
) -> str:
    """Return HTML for a single regime card. state → bull/bear/trans/accum/dist."""
    display_state, variant = _clean_regime_state(state)
    # P1 audit fix — escape every interpolated caller string. ticker can
    # come from a data source list, state/since from upstream regime
    # classifier output. confidence is numeric, sanitize via int().
    try:
        _conf_int = int(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        _conf_int = None
    conf = f"confidence {_conf_int}%" if _conf_int is not None else ""
    since_html = (
        f'<div class="since">{_html.escape(str(since))}</div>'
        if since else ""
    )
    return (
        f'<div class="ds-card ds-rgm {_html.escape(variant)}">'
        f'<div class="t">{_html.escape(str(ticker))}</div>'
        f'<div class="state">{_html.escape(str(display_state))}</div>'
        f'<div class="conf">{conf}</div>'
        f'{since_html}'
        f'</div>'
    )


# ── Segmented control (C2 — Phase C plan §C2) ────────────────────────
# Mockup target: docs/mockups/sibling-family-crypto-signal-BACKTESTER.html
#   .seg-ctrl       — primary variant ([Backtest][Arbitrage] at top of
#                     Backtester page)
#   .seg-ctrl-sm    — small variant ([Summary][Trade History][Advanced]
#                     sub-view switcher)
#
# Critical: uses on_click callback (NOT `if button(): write_state();
# rerun()`). The inline pattern triggers the same two-click highlight
# bug we fixed in render_sidebar (see H5 fix in commit 075bec9). With
# on_click, Streamlit invokes the callback BEFORE the script body
# re-runs, so the segment paints with the new active state on the
# very first render.

# Sentinel marker class so overrides.py can scope CSS to this widget
# without touching every st.columns row in the app.
_SEG_CTRL_MARKER_CLS = "ds-seg-ctrl"
_SEG_CTRL_SM_MARKER_CLS = "ds-seg-ctrl ds-seg-ctrl-sm"


def segmented_control(
    items: Sequence[tuple[str, str]],
    *,
    active: str,
    key: str,
    on_select: Callable[[str], None] | None = None,
    variant: Literal["primary", "small"] = "primary",
) -> str:
    """Mockup-style segmented control with first-click highlight.

    Args:
        items:   `[(value, label), ...]` — value is the canonical id,
                 label is the visible text.
        active:  the currently-selected value (the segment painted as
                 "on"). Caller is responsible for sourcing this from
                 session_state if persistence across reruns is wanted.
        key:     session_state key the click handler writes to. The
                 callback writes BEFORE the next script re-run so the
                 first-click paint already shows the new active segment.
        on_select: optional callback fired with the new value after
                 session_state is updated. Use for side-effects like
                 cache invalidation; do NOT use to write more state
                 (that's what `key` is for).
        variant: 'primary' (Backtester top-of-page) or 'small' (sub-
                 view switcher). Drives which CSS class is emitted on
                 the marker div.

    Returns:
        The currently-selected value AFTER any click handler has run
        (i.e. session_state[key] if set, else `active`).
    """
    if st is None:
        return active

    # Validate the active value early — easier to spot caller bugs.
    # Use an ORDERED fallback (first item) so the regression test for
    # invalid `active` is deterministic; Python set iteration order is
    # implementation-dependent and can flip across pytest workers.
    valid_values = [v for v, _ in items]
    if active not in valid_values:
        # Fall back to first item; never raise (this is a UI primitive).
        active = valid_values[0] if valid_values else active

    def _on_segment_click(value: str) -> None:
        st.session_state[key] = value
        if on_select is not None:
            try:
                on_select(value)
            except Exception:  # pragma: no cover — defensive only
                # Component must never crash a page just because a
                # caller's on_select callback raised.
                pass

    # Marker div — CSS in overrides.py uses :has() to scope the seg-
    # ctrl styling to the stHorizontalBlock that immediately follows
    # this marker.
    marker_cls = (_SEG_CTRL_SM_MARKER_CLS if variant == "small"
                  else _SEG_CTRL_MARKER_CLS)
    st.markdown(
        f'<div class="{marker_cls}" data-seg-key="{_html.escape(str(key))}"></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(items))
    for col, (value, label) in zip(cols, items):
        with col:
            st.button(
                str(label),
                key=f"_segctrl_{key}_{value}",
                use_container_width=True,
                type=("primary" if value == active else "secondary"),
                on_click=_on_segment_click,
                args=(value,),
            )

    return st.session_state.get(key, active)


# ── Pair-selection affordances (C3 — Phase C plan §C3) ───────────────
# Four primitives shared across Home / Signals / Regimes / On-chain to
# give every page a consistent way to swap pairs:
#
#   pair_dropdown            "More ▾ +N" — opens a searchable list
#   ticker_pill_button       per-card swap (Home heroes + On-chain)
#   watchlist_customize_btn  add/remove panel for the Home watchlist
#   multi_timeframe_strip    1m/5m/.../1w strip on Signals
#
# All four use on_click=callback for first-paint state updates (same
# pattern as segmented_control, render_sidebar nav, topbar refresh).

def pair_dropdown(
    pairs: Sequence[str],
    *,
    active: str,
    key: str,
    label: str | None = None,
    on_select: Callable[[str], None] | None = None,
) -> str:
    """Quick-access pill row (5 fastest pairs) + "More ▾ +N" popover.

    Args:
        pairs:   full universe of selectable pairs (e.g. all 33 entries
                 of `model.PAIRS`). The first 5 are surfaced as direct
                 pill buttons; the rest live behind the "More ▾"
                 popover.
        active:  currently-selected pair (whatever value lives in
                 `st.session_state[key]`).
        key:     session_state key the click handler writes to.
        label:   optional override for the popover trigger label.
                 Defaults to "More ▾ +N" where N is len(pairs)-5.
        on_select: optional callback fired with the new value AFTER
                 session_state is updated.

    Returns:
        The currently-selected pair after any click handler has run.

    Persistence: clicks write `session_state[key] = chosen_pair` BEFORE
    the next script re-run via on_click. First-click correctness is
    therefore guaranteed (no two-click highlight bug).
    """
    if st is None:
        return active

    if not pairs:
        return active

    # Accept either bare tickers ("BTC") or full pairs ("BTC/USDT") —
    # the popover label uses whatever the caller provided.
    quick = list(pairs[:5])
    rest = list(pairs[5:])

    if active not in pairs:
        active = quick[0] if quick else (rest[0] if rest else active)

    def _on_pick(value: str) -> None:
        st.session_state[key] = value
        if on_select is not None:
            try:
                on_select(value)
            except Exception:  # pragma: no cover
                pass

    # Render row: 5 quick pills + popover trigger. Width ratios keep
    # the row compact even when the More label is long.
    cols = st.columns(len(quick) + (1 if rest else 0))
    for i, p in enumerate(quick):
        with cols[i]:
            st.button(
                str(p),
                key=f"_pdpd_quick_{key}_{p}",
                use_container_width=True,
                type=("primary" if p == active else "secondary"),
                on_click=_on_pick,
                args=(p,),
            )

    if rest:
        more_label = label or f"More ▾  +{len(rest)}"
        with cols[-1]:
            with st.popover(more_label, use_container_width=True):
                # Search filter for long universes — invisible if <=8.
                search = ""
                if len(rest) > 8:
                    search = st.text_input(
                        "Search",
                        key=f"_pdpd_search_{key}",
                        placeholder="filter…",
                        label_visibility="collapsed",
                    )
                filt = rest
                if search:
                    s = search.lower()
                    filt = [p for p in rest if s in str(p).lower()]
                # Render a button per filtered pair — clicking writes
                # session_state immediately; popover dismisses on rerun.
                for p in filt:
                    st.button(
                        str(p),
                        key=f"_pdpd_more_{key}_{p}",
                        use_container_width=True,
                        type=("primary" if p == active else "secondary"),
                        on_click=_on_pick,
                        args=(p,),
                    )

    return st.session_state.get(key, active)


def ticker_pill_button(
    ticker: str,
    *,
    pairs: Sequence[str],
    key: str,
    on_swap: Callable[[str], None] | None = None,
    label_override: str | None = None,
) -> str:
    """Per-card ticker that opens a pair-swap popover on click.

    Used on Home hero cards (3 independent slots) and On-chain detail
    cards (3 independent slots). Each instance is bound to its own
    `key` so the slot-1 swap doesn't affect slot-2.

    Args:
        ticker:  the currently-displayed ticker (e.g. "BTC", "BTC/USDT").
        pairs:   universe of pairs the slot can be swapped to.
        key:     session_state key — also used to namespace the popover
                 widget so multiple instances don't collide.
        on_swap: optional callback fired with the new ticker after
                 session_state is updated.
        label_override: alternative label to render inside the popover
                 trigger. Defaults to `ticker`.

    Returns:
        The currently-selected ticker after any click handler has run.
    """
    if st is None:
        return ticker

    if ticker not in pairs and pairs:
        # Caller may have passed a stale value; fall back to the first
        # pair so the popover doesn't render with no active row.
        ticker = pairs[0]

    def _on_pick(value: str) -> None:
        st.session_state[key] = value
        if on_swap is not None:
            try:
                on_swap(value)
            except Exception:  # pragma: no cover
                pass

    trigger = label_override or f"{ticker}  ▾"
    with st.popover(trigger, use_container_width=False):
        st.caption("Swap this card to a different pair")
        for p in pairs:
            st.button(
                str(p),
                key=f"_tpb_{key}_{p}",
                use_container_width=True,
                type=("primary" if p == ticker else "secondary"),
                on_click=_on_pick,
                args=(p,),
            )

    return st.session_state.get(key, ticker)


def watchlist_customize_btn(
    *,
    available: Sequence[str],
    current: Sequence[str],
    key: str,
    on_save: Callable[[Sequence[str]], None] | None = None,
    label: str = "Customize  ▾",
) -> Sequence[str]:
    """Open a popover with checkboxes to add/remove pairs from the
    watchlist. Selection persists in `st.session_state[key]`.

    Args:
        available: full universe of pairs the user can choose from.
        current:   currently-watched pairs (sourced from session_state
                   if persistence has already been seeded).
        key:       session_state key for the chosen list.
        on_save:   optional callback fired with the new list after
                   session_state is updated.
        label:     popover trigger label.

    Returns:
        The currently-watched list after any save.
    """
    if st is None:
        return current

    # Seed session_state on first render so the popover's checkboxes
    # know what to display as already-checked.
    if key not in st.session_state:
        st.session_state[key] = list(current)

    with st.popover(label, use_container_width=False):
        st.caption("Tick the pairs you want to watch")
        # Render two columns of checkboxes for compactness on long
        # universes. The state is kept in scratch keys until the user
        # presses Save — that way mid-edit toggles don't churn the
        # downstream watchlist render.
        scratch_key = f"_wclb_scratch_{key}"
        if scratch_key not in st.session_state:
            st.session_state[scratch_key] = list(st.session_state[key])

        cols = st.columns(2)
        for i, p in enumerate(available):
            with cols[i % 2]:
                checked = p in st.session_state[scratch_key]
                new_val = st.checkbox(
                    str(p),
                    value=checked,
                    key=f"_wclb_cb_{key}_{p}",
                )
                if new_val and p not in st.session_state[scratch_key]:
                    st.session_state[scratch_key].append(p)
                elif not new_val and p in st.session_state[scratch_key]:
                    st.session_state[scratch_key].remove(p)

        def _on_save_click():
            new_list = list(st.session_state[scratch_key])
            st.session_state[key] = new_list
            if on_save is not None:
                try:
                    on_save(new_list)
                except Exception:  # pragma: no cover
                    pass

        st.button(
            "💾 Save watchlist",
            key=f"_wclb_save_{key}",
            use_container_width=True,
            type="primary",
            on_click=_on_save_click,
        )

    return st.session_state.get(key, list(current))


def multi_timeframe_strip(
    timeframes: Sequence[str],
    *,
    active: str,
    key: str,
    signals: dict[str, tuple[str, float]] | None = None,
    on_select: Callable[[str], None] | None = None,
) -> str:
    """Multi-cell timeframe selector for the Signals page.

    Each cell shows the timeframe label plus an optional per-timeframe
    signal letter (BUY/HOLD/SELL) and confidence score from `signals`.
    The active cell is rendered as the primary chip.

    Args:
        timeframes: ordered list of timeframes to render (e.g.
                    ["1h", "4h", "1d", "1w"] or the full 8-cell
                    ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]).
        active:     currently-selected timeframe.
        key:        session_state key for persistence.
        signals:    optional `{tf: (signal_letter, score)}` map. Cells
                    without an entry just show the timeframe label.
        on_select:  optional callback fired with the clicked timeframe.

    Returns:
        The currently-selected timeframe after any click handler.
    """
    if st is None:
        return active

    if not timeframes:
        return active
    if active not in timeframes:
        active = timeframes[0]

    def _on_pick(tf: str) -> None:
        st.session_state[key] = tf
        if on_select is not None:
            try:
                on_select(tf)
            except Exception:  # pragma: no cover
                pass

    # Marker so overrides.py can scope the strip's CSS without
    # touching every other st.columns row.
    st.markdown(
        f'<div class="ds-tf-strip" data-tf-key="{_html.escape(str(key))}"></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(timeframes))
    for col, tf in zip(cols, timeframes):
        sig = (signals or {}).get(tf)
        if sig is not None:
            letter, score = sig
            label = f"{tf}\n{_html.escape(str(letter))} · {score:.0f}"
        else:
            label = tf
        with col:
            st.button(
                label,
                key=f"_tfs_{key}_{tf}",
                use_container_width=True,
                type=("primary" if tf == active else "secondary"),
                on_click=_on_pick,
                args=(tf,),
                help=f"Switch to {tf} timeframe",
            )

    return st.session_state.get(key, active)


# ── SIGNALS page (sibling-family-crypto-signal-SIGNALS.html) helpers ──

def coin_picker(coins: Sequence[str], active: str) -> str:
    """Return HTML for the chip-group coin picker shown on the Signals page.

    Visual only — clicks are wired by a separate st.button column rendered
    next to it (Streamlit can't capture clicks on raw HTML buttons). The
    helper is here so the layout matches the mockup exactly when no
    interaction is needed (e.g. screenshots / printouts).
    """
    # P1 audit fix — escape coin labels (caller data).
    btns = "".join(
        f'<button class="{"on" if c == active else ""}">{_html.escape(str(c))}</button>'
        for c in coins
    )
    return f'<div class="ds-coin-pick">{btns}</div>'


def signal_hero_detail_card(
    *,
    ticker: str,
    name: str,
    price: float | None,
    change_24h: float | None = None,
    change_30d: float | None = None,
    change_1y: float | None = None,
    signal: Literal["BUY", "HOLD", "SELL", None] = None,
    signal_strength: str = "",
    regime_label: str = "",
    regime_confidence: float | None = None,
    regime_since: str = "",
) -> str:
    """Big hero card for the Signals detail page.

    Mirrors the mockup .hero block — left side has ticker / price / 3 timeframe
    changes; right side has the large signal badge + a regime line.
    """
    if price is None:
        price_str = "—"
    elif price >= 1000:
        price_str = f"{price:,.0f}"
    elif price >= 10:
        price_str = f"{price:,.2f}"
    else:
        price_str = f"{price:,.4f}"

    def _fmt(pct, label):
        if pct is None:
            return f'<span style="color:var(--text-muted);">—</span> · {label}'
        sign = "+ " if pct > 0 else ("− " if pct < 0 else "")
        cls = "up" if pct > 0 else ("down" if pct < 0 else "")
        return f'<span class="{cls}">{sign}{abs(pct):.2f}%</span> · {label}'

    chg_cls = "up" if (change_24h or 0) > 0 else ("down" if (change_24h or 0) < 0 else "")
    chg_html = (
        f'<div class="ds-signal-detail-chg {chg_cls}">'
        f'{_fmt(change_24h, "24h")} &nbsp;·&nbsp; '
        f'{_fmt(change_30d, "30d")} &nbsp;·&nbsp; '
        f'{_fmt(change_1y, "1Y")}</div>'
    )

    badge_html = ""
    if signal in ("BUY", "HOLD", "SELL"):
        shape, css_class, label = {
            "BUY":  ("▲", "ds-sb-buy",  "Buy"),
            "HOLD": ("■", "ds-sb-hold", "Hold"),
            "SELL": ("▼", "ds-sb-sell", "Sell"),
        }[signal]
        strength = f" · {signal_strength}" if signal_strength else ""
        badge_html = f'<span class="ds-signal-badge ds-signal-badge-lg {css_class}">{shape} {label}{strength}</span>'

    regime_html = ""
    if regime_label:
        conf_txt = f" · {int(regime_confidence)}% conf" if regime_confidence is not None else ""
        since_txt = f" · {regime_since}" if regime_since else ""
        regime_html = (
            f'<div class="ds-regime"><span class="dot"></span> '
            f'Regime: {regime_label}{conf_txt}{since_txt}</div>'
        )

    return (
        f'<div class="ds-card ds-signal-detail-hero">'
        f'<div class="ds-signal-detail-lhs">'
        f'<div class="ds-signal-detail-ticker">{ticker} · {name}</div>'
        f'<div class="ds-signal-detail-price">{price_str}</div>'
        f'{chg_html}'
        f'</div>'
        f'<div class="ds-signal-detail-rhs">'
        f'{badge_html}{regime_html}'
        f'</div>'
        f'</div>'
    )


def composite_score_card(
    *,
    score: float | None,
    layers: Sequence[tuple[str, float | None]],
    weights_note: str = "",
) -> None:
    """Render the composite score card with N layer progress bars."""
    if st is None:
        return
    score_html = f'{score:.1f}' if score is not None else '—'
    bars_html = []
    for name, val in layers:
        v = val if val is not None else 0
        cls = "ds-bar-fill"
        if v < 60:
            cls += " mid"
        if v < 40:
            cls = "ds-bar-fill low"
        val_text = f"{v:.0f}" if val is not None else "—"
        bars_html.append(
            f'<div class="ds-layer">'
            f'<div class="ds-layer-hd"><div class="ds-layer-name">{name}</div>'
            f'<div class="ds-layer-val">{val_text}</div></div>'
            f'<div class="ds-bar"><div class="{cls}" style="width:{max(0,min(100,v))}%;"></div></div>'
            f'</div>'
        )
    note_html = ""
    if weights_note:
        note_html = (
            f'<div style="margin-top:18px;padding-top:14px;border-top:1px solid var(--border);'
            f'font-size:12px;color:var(--text-muted);">{weights_note}</div>'
        )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd">'
        f'<div class="ds-card-title">Composite score · 0–100</div>'
        f'<div style="color:var(--accent);font-family:var(--font-mono);font-weight:600;">{score_html}</div>'
        f'</div>'
        f'<div style="display:flex;flex-direction:column;gap:14px;margin-top:8px;">'
        f'{"".join(bars_html)}'
        f'</div>'
        f'{note_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def indicator_card(
    title: str,
    items: Sequence[tuple[str, str, str, str]],
) -> None:
    """Indicator-grid card (used 3× on Signals page: Technical / On-chain / Sentiment).

    Each item: (label, value, sub, color_token). color_token is one of
    'success' / 'danger' / 'warning' / '' (default text-primary).
    """
    if st is None:
        return
    cells = []
    for label, value, sub, tone in items:
        color_style = ""
        if tone in ("success", "danger", "warning"):
            color_style = f' style="color:var(--{tone});"'
        cells.append(
            f'<div class="ds-ind">'
            f'<div class="ds-ind-lbl">{label}</div>'
            f'<div class="ds-ind-val"{color_style}>{value}</div>'
            f'<div class="ds-ind-sub">{sub}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd"><div class="ds-card-title">{title}</div></div>'
        f'<div class="ds-ind-grid ds-ind-grid-2col">{"".join(cells)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def signal_history_table(
    rows: Sequence[dict],
    *,
    title: str = "Recent signal history",
    subtitle: str = "",
) -> None:
    """4-col history row table — time / signal / note / return.

    Each row dict: {time, signal: BUY/HOLD/SELL, note, return_pct}.
    """
    if st is None:
        return
    row_html = []
    for r in rows:
        sig = (r.get("signal") or "").upper()
        sig_cls = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}.get(sig, "hold")
        sig_glyph = {"BUY": "▲", "SELL": "▼", "HOLD": "■"}.get(sig, "•")
        ret = r.get("return_pct")
        if ret is None:
            ret_str = "—"
            ret_cls = ""
        else:
            ret_cls = "up" if ret > 0 else ("down" if ret < 0 else "")
            sign = "+ " if ret > 0 else ("− " if ret < 0 else "")
            ret_str = f"{sign}{abs(ret):.1f}%"
        row_html.append(
            f'<div class="ds-hist-row">'
            f'<span class="t">{r.get("time", "—")}</span>'
            f'<span class="s {sig_cls}">{sig_glyph} {sig or "—"}</span>'
            f'<span class="note">{r.get("note", "")}</span>'
            f'<span class="ret {ret_cls}">{ret_str}</span>'
            f'</div>'
        )
    sub_html = (
        f'<div style="color:var(--text-muted);font-size:12px;">{subtitle}</div>'
        if subtitle else ""
    )
    if row_html:
        body_html = "".join(row_html)
    else:
        body_html = (
            '<div style="color:var(--text-muted);font-size:13px;padding:8px 4px;">'
            'No signal history yet.</div>'
        )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd"><div class="ds-card-title">{title}</div>{sub_html}</div>'
        f'<div class="ds-hist">{body_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── BACKTESTER page helpers (sibling-family-crypto-signal-BACKTESTER.html) ──

def backtest_controls_row(
    items: Sequence[tuple[str, str]],
    *,
    run_button_label: str = "Re-run backtest →",
    show_decorative_button: bool = False,
) -> str:
    """Return HTML for the inline controls row (Universe, Period, Initial, etc.).

    Each item: (label, value). The decorative `<button>` previously
    embedded in this markup was causing C2 — users clicked it and nothing
    happened, because HTML `<button>` elements inside `st.markdown` cannot
    trigger Streamlit callbacks. The real run trigger is a separate
    `st.button(...)` rendered just below the controls row in app.py.

    `show_decorative_button` defaults to False as of the C2 fix
    (2026-04-28) so the misleading non-functional button is hidden by
    default. Callers that still want the visual placeholder can opt in
    explicitly. `run_button_label` is kept for back-compat with any
    callers that haven't migrated yet.
    """
    cells = "".join(
        f'<div class="ds-bt-ctrl"><span class="lbl">{lbl}</span>'
        f'<span class="v">{val}</span></div>'
        for lbl, val in items
    )
    btn_markup = (
        f'<button class="ds-bt-runbtn" disabled aria-disabled="true" '
        f'title="The run trigger is the prominent button below — '
        f'this is a visual marker only.">{_html.escape(run_button_label)}</button>'
        if show_decorative_button else ""
    )
    return (
        f'<div class="ds-bt-controls">{cells}{btn_markup}</div>'
    )


def backtest_kpi_strip(
    kpis: Sequence[tuple[str, str, str, str]],
) -> None:
    """Render the 5-col KPI strip (Total return / CAGR / Sharpe / Max DD / Win rate).

    Each kpi: (label, value, sub_text, tone). tone ∈ {success, danger, accent, ""}.
    """
    if st is None:
        return
    cards = []
    for label, value, sub, tone in kpis:
        v_color = ""
        if tone == "success":
            v_color = ' style="color:var(--success);"'
        elif tone == "danger":
            v_color = ' style="color:var(--danger);"'
        elif tone == "accent":
            v_color = ' style="color:var(--accent);"'
        # Sub line tone derived from the subtext content (up=green, down=red)
        sub_cls = ""
        sl = sub.lower()
        if any(x in sl for x in ("vs btc +", "+ ", "tightening", "tailwind")):
            sub_cls = " up"
        elif any(x in sl for x in ("vs btc −", "− ", "btc −", "−")):
            sub_cls = " down" if "btc −" in sl or sl.startswith("− ") else ""
        cards.append(
            f'<div class="ds-card">'
            f'<div class="ds-bt-kpi-lbl">{label}</div>'
            f'<div class="ds-bt-kpi-val"{v_color}>{value}</div>'
            f'<div class="ds-bt-kpi-sub{sub_cls}">{sub}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="ds-bt-kpi-grid">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def optuna_top_card(
    rows: Sequence[dict],
    *,
    title: str = "Optuna studies · top 5 hyperparam sets",
    footer: str = "",
) -> None:
    """5-row Optuna list. Each row dict:
        {rank: int, star: bool, params: str, sharpe: float, return_pct: float}
    """
    if st is None:
        return
    row_html = []
    for r in rows:
        rank = r.get("rank")
        star = " ★" if r.get("star") else ""
        rank_str = f"#{rank}{star}" if rank is not None else "—"
        sh = r.get("sharpe")
        sh_str = f"{float(sh):.2f}" if sh is not None else "—"
        ret = r.get("return_pct")
        if ret is None:
            ret_str = "—"
        else:
            sign = "+" if float(ret) > 0 else ("−" if float(ret) < 0 else "")
            ret_str = f"{sign}{abs(float(ret)):.1f}%"
        row_html.append(
            f'<div class="ds-bt-opt-row">'
            f'<span class="rank">{rank_str}</span>'
            f'<span class="params">{r.get("params", "—")}</span>'
            f'<span class="sh">{sh_str}</span>'
            f'<span class="ret">{ret_str}</span>'
            f'</div>'
        )
    if not row_html:
        body = ('<div style="color:var(--text-muted);font-size:13px;padding:8px 4px;">'
                'No Optuna study runs yet. Trigger a tuning run from Settings → Dev Tools.</div>')
    else:
        body = "".join(row_html)
    footer_html = (
        f'<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);'
        f'font-size:11.5px;color:var(--text-muted);">{footer}</div>' if footer else ""
    )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd"><div class="ds-card-title">{title}</div></div>'
        f'<div>{body}</div>{footer_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def recent_trades_card(
    rows: Sequence[dict],
    *,
    title: str = "Recent trades · signal-driven",
    subtitle: str = "",
) -> None:
    """5-col trades table. Each row dict:
        {date, side: BUY/SELL, reason, return_pct, duration}
    """
    if st is None:
        return
    head = (
        '<div class="ds-bt-trades-h">'
        '<span>Date</span><span>Side</span><span>Reason</span>'
        '<span>Return</span><span>Duration</span>'
        '</div>'
    )
    rh = []
    for r in rows:
        side = (r.get("side") or "").upper()
        s_cls = "buy" if side in ("BUY", "LONG") else ("sell" if side in ("SELL", "SHORT") else "")
        ret = r.get("return_pct")
        if ret is None:
            ret_str, ret_cls = "—", ""
        else:
            sign = "+" if float(ret) > 0 else ("−" if float(ret) < 0 else "")
            ret_str = f"{sign}{abs(float(ret)):.1f}%"
            ret_cls = "up" if float(ret) > 0 else ("down" if float(ret) < 0 else "")
        rh.append(
            f'<div class="ds-bt-trades-r">'
            f'<span class="dt">{r.get("date","—")}</span>'
            f'<span class="s {s_cls}">{side or "—"}</span>'
            f'<span class="n">{r.get("reason","")}</span>'
            f'<span class="p {ret_cls}">{ret_str}</span>'
            f'<span class="d">{r.get("duration","—")}</span>'
            f'</div>'
        )
    if not rh:
        body = ('<div style="color:var(--text-muted);font-size:13px;padding:14px 4px;">'
                'No trades recorded yet — run a backtest to populate.</div>')
    else:
        body = head + "".join(rh)
    sub_html = (
        f'<div style="color:var(--text-muted);font-size:12px;">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd"><div class="ds-card-title">{title}</div>{sub_html}</div>'
        f'<div class="ds-bt-trades">{body}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── REGIMES page helpers (sibling-family-crypto-signal-REGIMES.html) ──

def regime_state_bar(
    segments: Sequence[tuple[str, float]],
    *,
    title: str = "Regime state · last 90d",
    date_labels: Sequence[str] | None = None,
    note: str = "",
) -> None:
    """Stacked horizontal bar of regime segments (Bear / Trans / Accum / Bull / Dist).

    Each segment: (state_name, percentage_0_100). Color is derived from the
    state name. date_labels render evenly spaced under the bar.
    """
    if st is None:
        return
    _color_map = {
        "bull":         "#22c55e",
        "bear":         "#ef4444",
        "trans":        "#f59e0b",
        "transition":   "#f59e0b",
        "accum":        "#3b82f6",
        "accumulation": "#3b82f6",
        "dist":         "#f59e0b",
        "distribution": "#f59e0b",
    }
    seg_html = []
    for name, pct in segments:
        c = _color_map.get(str(name).lower(), "#5d5d6e")
        label = str(name).title()[:5]
        seg_html.append(
            f'<div class="ds-rgm-seg" style="background:{c};width:{max(0,min(100,pct))}%;">'
            f'{label}</div>'
        )
    label_html = ""
    if date_labels:
        cells = "".join(f'<span>{d}</span>' for d in date_labels)
        label_html = (
            f'<div style="display:flex;justify-content:space-between;'
            f'font-size:11px;color:var(--text-muted);margin-top:6px;">{cells}</div>'
        )
    note_html = (
        f'<div style="margin-top:20px;font-size:12px;color:var(--text-muted);'
        f'line-height:1.5;">{note}</div>' if note else ""
    )
    st.markdown(
        f'<div class="ds-card" style="padding:20px;">'
        f'<div style="font-size:13px;color:var(--text-muted);text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-bottom:14px;">{title}</div>'
        f'<div class="ds-rgm-bar">{"".join(seg_html)}</div>'
        f'{label_html}{note_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def macro_regime_overlay_card(
    rows: Sequence[dict],
    *,
    title: str = "Macro regime · overlay",
    overall_label: str = "",
    overall_confidence: float | None = None,
) -> None:
    """List card showing macro indicators. Each row dict:
        {name, value, delta_text, delta_dir: up|down|""}, sentiment: bull|bear|neut, sentiment_label}
    """
    if st is None:
        return
    row_html = []
    for r in rows:
        d_dir = (r.get("delta_dir") or "").lower()
        d_cls = "up" if d_dir == "up" else ("down" if d_dir == "down" else "")
        s_class = (r.get("sentiment") or "neut").lower()
        if s_class not in ("bull", "bear", "neut"):
            s_class = "neut"
        row_html.append(
            f'<div class="ds-macro-row">'
            f'<span class="n">{r.get("name","")}</span>'
            f'<span class="v">{r.get("value","—")}</span>'
            f'<span class="d {d_cls}">{r.get("delta_text","")}</span>'
            f'<span class="s {s_class}">{r.get("sentiment_label","")}</span>'
            f'</div>'
        )
    overall_html = ""
    if overall_label:
        conf_txt = f" · {int(overall_confidence)}%" if overall_confidence is not None else ""
        overall_html = (
            f'<div style="color:var(--accent);font-weight:600;">'
            f'{overall_label}{conf_txt}</div>'
        )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd">'
        f'<div class="ds-card-title">{title}</div>'
        f'{overall_html}'
        f'</div>'
        f'<div style="margin-top:8px;">{"".join(row_html)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def regime_weights_grid(
    weights_by_regime: Sequence[tuple[str, str, dict]],
    *,
    title: str = "Signal weights by regime",
    subtitle: str = "auto-adjusted by HMM state",
) -> None:
    """4-col grid showing layer weights per regime.

    Each entry: (regime_name, color_token, weights_dict).
    color_token: success | danger | warning | info.
    weights_dict: {"Tech": 0.30, "Macro": 0.15, ...}
    """
    if st is None:
        return
    cells = []
    for name, tone, weights in weights_by_regime:
        wlines = "<br>".join(
            f'{k}: {v:.2f}' for k, v in weights.items()
        )
        cells.append(
            f'<div>'
            f'<div style="font-size:13px;font-weight:500;margin-bottom:8px;color:var(--{tone});">{name}</div>'
            f'<div style="font-family:var(--font-mono);font-size:12px;line-height:1.7;color:var(--text-secondary);">{wlines}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="ds-card">'
        f'<div class="ds-card-hd">'
        f'<div class="ds-card-title">{title}</div>'
        f'<div style="color:var(--text-muted);font-size:12px;">{subtitle}</div>'
        f'</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:12px;">'
        f'{"".join(cells)}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def regime_cards_grid(cards: Sequence[dict], cols: int = 4) -> None:
    """Render a grid of regime cards.
    Each card dict: ticker, state, confidence, since.
    """
    if st is None:
        return
    html = "".join(
        regime_card_html(
            ticker=c.get("ticker", "—"),
            state=c.get("state", "Transition"),
            confidence=c.get("confidence"),
            since=c.get("since", ""),
        )
        for c in cards
    )
    st.markdown(
        f'<div class="ds-grid ds-cols-{cols}">{html}</div>',
        unsafe_allow_html=True,
    )
