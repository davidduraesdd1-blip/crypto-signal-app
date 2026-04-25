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

    if show_level:
        lvls = [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")]
        for idx, (k, lbl) in enumerate(lvls, start=1):
            with cols[idx]:
                if st.button(
                    lbl,
                    key=f"ds_topbar_lvl_{k}",
                    use_container_width=True,
                    type=("primary" if user_level == k else "secondary"),
                    help=f"Switch to {lbl} view",
                ):
                    st.session_state["user_level"] = k
                    st.rerun()

    if show_refresh:
        with cols[4]:
            if on_refresh is not None:
                if st.button(
                    "↻ Refresh",
                    key="ds_topbar_refresh",
                    use_container_width=True,
                    help="Clear all caches and reload data from all sources",
                ):
                    on_refresh()
                    st.rerun()
            else:
                st.markdown(
                    '<div class="ds-chip-btn" style="text-align:center;opacity:0.5;">↻ Refresh</div>',
                    unsafe_allow_html=True,
                )

    if show_theme:
        with cols[5]:
            if on_theme is not None:
                if st.button(
                    "☾ Theme",
                    key="ds_topbar_theme",
                    use_container_width=True,
                    help="Toggle light / dark mode",
                ):
                    on_theme()
                    st.rerun()
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
        f'<div class="ds-page-hd">'
        f'<div>'
        f'<h1 class="ds-page-title">{title}</h1>'
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
    regime_html = ""
    if regime_label:
        _clean = str(regime_label).strip()
        _low = _clean.lower()
        for _prefix in ("regime: ", "regime:", "regime "):
            if _low.startswith(_prefix):
                _clean = _clean[len(_prefix):].strip()
                break
        conf_txt = f" · {int(regime_confidence)}% conf" if regime_confidence is not None else ""
        regime_html = (
            f'<div class="ds-regime"><span class="dot"></span> '
            f'Regime: {_clean}{conf_txt}</div>'
        )

    # Single-line to avoid Streamlit markdown's 4-space = code-block rule.
    return (
        f'<div class="ds-card ds-signal-hero">'
        f'<div class="ds-signal-lhs">'
        f'<div class="ds-signal-ticker">{ticker}</div>'
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
    conf = f"confidence {int(confidence)}%" if confidence is not None else ""
    since_html = f'<div class="since">{since}</div>' if since else ""
    return (
        f'<div class="ds-card ds-rgm {variant}">'
        f'<div class="t">{ticker}</div>'
        f'<div class="state">{display_state}</div>'
        f'<div class="conf">{conf}</div>'
        f'{since_html}'
        f'</div>'
    )


# ── SIGNALS page (sibling-family-crypto-signal-SIGNALS.html) helpers ──

def coin_picker(coins: Sequence[str], active: str) -> str:
    """Return HTML for the chip-group coin picker shown on the Signals page.

    Visual only — clicks are wired by a separate st.button column rendered
    next to it (Streamlit can't capture clicks on raw HTML buttons). The
    helper is here so the layout matches the mockup exactly when no
    interaction is needed (e.g. screenshots / printouts).
    """
    btns = "".join(
        f'<button class="{"on" if c == active else ""}">{c}</button>'
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
