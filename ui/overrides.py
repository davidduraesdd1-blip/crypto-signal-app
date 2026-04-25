"""
ui/overrides.py — Streamlit widget CSS overrides that shadow default Streamlit
styling so existing pages inherit the mockup's look without structural changes.

All selectors target Streamlit's stable data-testid hooks. Call
inject_streamlit_overrides() once per page, after inject_theme().
"""
from __future__ import annotations


def inject_streamlit_overrides() -> None:
    try:
        import streamlit as st
    except ImportError:  # pragma: no cover
        return

    css = """
    /* ─── Sibling-family design-system shell overrides ─── */

    /* Main content column */
    section.main > div.block-container {
      padding-top: 16px;
      padding-bottom: 80px;
      max-width: none;
    }

    /* Sidebar canvas */
    [data-testid="stSidebar"] {
      background: var(--bg-1) !important;
      border-right: 1px solid var(--border) !important;
      min-width: var(--rail-w) !important;
      max-width: calc(var(--rail-w) + 24px) !important;
    }
    [data-testid="stSidebar"] > div:first-child {
      padding: 16px 12px !important;
      background: var(--bg-1) !important;
    }

    /* Brand block */
    .ds-rail-brand {
      display: flex; align-items: center; gap: 10px;
      padding: 6px 10px 20px;
      font-weight: 600; font-size: 15px; letter-spacing: -0.01em;
      color: var(--text-primary);
    }
    .ds-brand-dot {
      width: 22px; height: 22px; border-radius: 6px;
      display: grid; place-items: center;
      font-weight: 700; font-size: 12px;
    }
    .ds-brand-wm { color: var(--text-primary); }

    /* Nav group header */
    .ds-nav-group {
      margin: 14px 0 4px; padding: 0 10px;
      color: var(--text-muted); font-size: 11px; font-weight: 500;
      letter-spacing: 0.08em; text-transform: uppercase;
    }

    /* Sidebar nav buttons — compact left-aligned items so the whole rail
       fits without scroll. Uses plain st.sidebar.button() now (no
       marker/overlay pattern). */
    [data-testid="stSidebar"] [data-testid="stButton"] > button {
      width: 100%;
      min-height: 30px !important;
      height: auto !important;
      padding: 4px 10px !important;
      border-radius: 6px;
      font-size: 13px !important;
      font-weight: 500;
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-secondary);
      box-shadow: none;
      text-align: left !important;
      justify-content: flex-start !important;
      transition: background 120ms, color 120ms, border-color 120ms;
    }
    /* Force the inner span/div inside the button to left-align too, since
       Streamlit wraps the label in a flex container that defaults to center. */
    [data-testid="stSidebar"] [data-testid="stButton"] > button > div,
    [data-testid="stSidebar"] [data-testid="stButton"] > button > div > p,
    [data-testid="stSidebar"] [data-testid="stButton"] > button > span {
      width: 100%;
      text-align: left !important;
      justify-content: flex-start !important;
      margin: 0 !important;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] > button:hover {
      background: var(--bg-2);
      color: var(--text-primary);
      border-color: transparent;
    }
    [data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] {
      background: var(--accent-soft);
      color: var(--text-primary);
      border-color: transparent;
      font-weight: 600;
    }
    /* Remove default margin/padding on each sidebar widget container so
       items pack tightly. */
    [data-testid="stSidebar"] [data-testid="stButton"],
    [data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> [data-testid="stButton"]) {
      margin: 0 !important;
      padding: 0 !important;
    }
    /* Tighten the vertical gap between sidebar items globally — the default
       stVerticalBlock gap is 1rem which makes the rail very tall. */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 2px; }

    /* Sidebar popover trigger (Glossary lives in the footer cluster).
       Plain text-link look matching the nav buttons — no ghost-button
       chrome (the legacy stylesheet's popover rule is scoped to
       section.main so it doesn't touch this). */
    [data-testid="stSidebar"] [data-testid="stPopover"] button {
      width: 100%;
      min-height: 30px !important;
      padding: 4px 10px !important;
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-secondary);
      font-size: 12.5px !important;
      font-weight: 500;
      border-radius: 6px;
      text-align: left !important;
      justify-content: flex-start !important;
      box-shadow: none;
    }
    [data-testid="stSidebar"] [data-testid="stPopover"] button:hover {
      background: var(--bg-2);
      color: var(--text-primary);
    }

    /* Section headers — visually distinct from the nav items below them.
       Uppercase, bolder, slightly larger text-secondary color, with a thin
       divider above each section so the boundary is unambiguous. */
    .ds-nav-group-header {
      font-size: 11.5px !important;
      font-weight: 700 !important;
      color: var(--text-secondary) !important;
      margin: 10px 0 2px 0 !important;
      padding: 6px 10px 4px 10px !important;
      text-transform: uppercase !important;
      letter-spacing: 0.14em !important;
      border-top: 1px solid var(--border) !important;
    }
    /* No top border on the very first section header — it sits right
       under the brand block already. */
    [data-testid="stSidebar"] .ds-nav-group-header:first-of-type {
      border-top: none !important;
      margin-top: 4px !important;
    }

    /* Top bar */
    .ds-topbar {
      background: var(--bg-0);
      border-bottom: 1px solid var(--border);
      display: flex; align-items: center; gap: 12px;
      padding: 10px 4px 14px 4px;
      margin: -8px 0 16px 0;
    }
    .ds-crumbs { color: var(--text-muted); font-size: 13px; }
    .ds-crumbs b { color: var(--text-primary); font-weight: 500; }
    .ds-topbar-spacer { flex: 1; }
    .ds-level-group {
      display: inline-flex; align-items: center; gap: 0;
      background: var(--bg-1); border: 1px solid var(--border);
      border-radius: 8px; padding: 2px;
    }
    .ds-level-group button {
      all: unset; cursor: pointer;
      padding: 4px 10px; border-radius: 6px; font-size: 12.5px;
      color: var(--text-muted); font-weight: 500;
      font-family: var(--font-ui);
    }
    .ds-level-group button.on {
      background: var(--accent-soft); color: var(--text-primary);
    }
    .ds-chip-btn {
      all: unset; cursor: pointer;
      display: inline-flex; align-items: center; gap: 6px;
      background: var(--bg-1); border: 1px solid var(--border);
      border-radius: 8px; padding: 6px 10px; font-size: 13px;
      color: var(--text-secondary); font-family: var(--font-ui);
    }
    .ds-chip-btn:hover { border-color: var(--border-strong); color: var(--text-primary); }

    /* Topbar status pills (Paper / Live, Claude AI status, Demo).
       Compact inline chips that sit next to the breadcrumb. */
    .ds-status-pill {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 11px; line-height: 1; font-weight: 600;
      padding: 3px 7px; border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--bg-2); color: var(--text-secondary);
      letter-spacing: 0.02em; white-space: nowrap;
    }
    .ds-status-pill.info    { color: #a78bfa; border-color: rgba(167,139,250,0.35); background: rgba(99,102,241,0.10); }
    .ds-status-pill.success { color: #22c55e; border-color: rgba(34,197,94,0.35);  background: rgba(34,197,94,0.10); }
    .ds-status-pill.warning { color: #f59e0b; border-color: rgba(245,158,11,0.35); background: rgba(245,158,11,0.10); }
    .ds-status-pill.danger  { color: #ef4444; border-color: rgba(239,68,68,0.40);  background: rgba(239,68,68,0.10); }
    .ds-status-pill.muted   { color: var(--text-muted); }

    /* Page header */
    .ds-page-hd {
      display: flex; justify-content: space-between; align-items: flex-end;
      gap: 16px; margin: 0 0 20px 0; flex-wrap: wrap;
    }
    /* High-specificity selectors so we win against Streamlit's default h1
       styling (which would otherwise blow this up to ~46px). */
    .stApp .ds-page-hd h1.ds-page-title,
    [data-testid="stMarkdown"] h1.ds-page-title,
    h1.ds-page-title {
      margin: 0 !important;
      padding: 0 !important;
      font-size: 22px !important;
      font-weight: 600 !important;
      letter-spacing: -0.01em !important;
      line-height: 1.25 !important;
      color: var(--text-primary) !important;
    }
    .ds-page-sub { color: var(--text-muted); font-size: 13.5px; margin-top: 4px; }

    /* Data-source pills */
    .ds-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
    .ds-pill {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 11.5px; padding: 3px 8px; border-radius: 999px;
      background: var(--bg-2); color: var(--text-secondary);
      border: 1px solid var(--border);
    }
    .ds-pill .tick { width: 6px; height: 6px; border-radius: 50%; background: var(--success); }
    .ds-pill.warn .tick { background: var(--warning); }
    .ds-pill.down .tick { background: var(--danger); }

    /* Card primitive + variants */
    .ds-card {
      background: var(--bg-1);
      border: 1px solid var(--border);
      border-radius: var(--card-radius);
      padding: var(--card-pad);
    }
    .ds-strip {
      display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; padding: 0;
    }
    .ds-strip > div { padding: 12px 14px; border-right: 1px solid var(--border); }
    .ds-strip > div:last-child { border-right: none; }
    .ds-strip .lbl { font-size: 10.5px; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: 0.05em; }
    .ds-strip .val { font-size: 17px; font-family: var(--font-mono);
      font-weight: 600; margin-top: 2px; color: var(--text-primary); }
    .ds-strip .sub { font-size: 11.5px; color: var(--text-muted);
      margin-top: 2px; font-family: var(--font-mono); }

    /* Card headers (shared) */
    .ds-card-hd {
      display: flex; justify-content: space-between; align-items: baseline;
      margin-bottom: 10px;
    }
    .ds-card-title { font-size: 12px; color: var(--text-muted); font-weight: 500;
      letter-spacing: 0.04em; text-transform: uppercase; }
    .ds-card-sub { font-size: 11.5px; color: var(--text-muted); }

    /* Restyle Streamlit native widgets so in-page content inherits the look */
    .stMarkdown, .stMarkdown p, .stMarkdown li { color: var(--text-primary); }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stMetric"] {
      background: var(--bg-1); border: 1px solid var(--border);
      border-radius: var(--card-radius); padding: 14px var(--card-pad);
    }
    [data-testid="stMetricLabel"] {
      color: var(--text-muted) !important;
      font-size: 11px !important; text-transform: uppercase;
      letter-spacing: 0.06em; font-weight: 500;
    }
    [data-testid="stMetricValue"] {
      font-family: var(--font-mono);
      font-size: 22px !important; font-weight: 600 !important;
      color: var(--text-primary) !important;
      line-height: 1.1;
    }
    [data-testid="stMetricDelta"] {
      font-family: var(--font-mono); font-size: 12px !important;
    }

    /* Primary buttons — outside the sidebar */
    section.main [data-testid="stButton"] > button {
      background: var(--bg-1); color: var(--text-primary);
      border: 1px solid var(--border); border-radius: 8px;
      font-weight: 500; padding: 6px 14px;
      transition: background 120ms, border-color 120ms;
    }
    section.main [data-testid="stButton"] > button:hover {
      border-color: var(--border-strong); background: var(--bg-2);
    }
    section.main [data-testid="stButton"] > button[kind="primary"] {
      background: var(--accent); color: var(--accent-ink);
      border-color: var(--accent);
    }

    /* Topbar row container — matches mockup .topbar (bg-0 + border-bottom +
       16px gap + center alignment). Scoped via the data-topbar="1" hook on
       the breadcrumb cell so it only restyles the topbar's stHorizontalBlock. */
    [data-testid="stHorizontalBlock"]:has(.ds-crumbs[data-topbar="1"]) {
      background: var(--bg-0);
      border-bottom: 1px solid var(--border);
      padding: 4px 0 10px 0;
      margin-bottom: 18px;
      align-items: center;
    }

    /* Topbar buttons (Beginner / Intermediate / Advanced / ↻ Refresh / ☾ Theme).
       Scoped via the data-topbar="1" hook on the breadcrumb cell so the rule
       only affects buttons in the same stHorizontalBlock. Without nowrap +
       compact padding, "Intermediate" wraps to 2-3 lines in the 1/11-width
       column. */
    [data-testid="stHorizontalBlock"]:has(.ds-crumbs[data-topbar="1"]) [data-testid="stButton"] > button {
      white-space: nowrap;
      padding: 4px 8px;
      font-size: 12.5px;
      min-width: 0;
      line-height: 1.4;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    /* Tighten the vertical block element wrapping each button so the row
       feels like a topbar, not a stack of inputs. */
    [data-testid="stHorizontalBlock"]:has(.ds-crumbs[data-topbar="1"]) [data-testid="stButton"] {
      margin: 0;
    }

    /* Inputs */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stSelectbox"] [data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
      background: var(--bg-1) !important;
      color: var(--text-primary) !important;
      border-color: var(--border) !important;
    }

    /* Expanders */
    [data-testid="stExpander"] {
      background: var(--bg-1); border: 1px solid var(--border);
      border-radius: var(--card-radius);
    }
    [data-testid="stExpander"] summary { color: var(--text-primary); }

    /* Tabs */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
      gap: 4px; border-bottom: 1px solid var(--border);
    }
    [data-testid="stTabs"] button[role="tab"] {
      background: transparent; color: var(--text-muted);
      border-radius: 6px 6px 0 0; padding: 8px 14px;
      font-weight: 500;
    }
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
      color: var(--text-primary);
      border-bottom: 2px solid var(--accent);
    }

    /* Dataframes */
    [data-testid="stDataFrame"] {
      border: 1px solid var(--border); border-radius: var(--card-radius);
      overflow: hidden;
    }

    /* Radios (sidebar nav alternative) — we hide native radio visuals inside sidebar
       but keep them functional for fallback callers */
    [data-testid="stSidebar"] [data-testid="stRadio"] > label { display: none; }

    /* ─── Hero signal cards ─── */
    .ds-hero-grid {
      display: grid; grid-template-columns: repeat(3, 1fr);
      gap: var(--gap); margin-bottom: 24px;
    }
    .ds-signal-hero {
      display: flex; align-items: center; justify-content: space-between;
      padding: 20px;
    }
    .ds-signal-lhs { display: flex; flex-direction: column; gap: 4px; }
    .ds-signal-ticker { font-size: 14px; color: var(--text-secondary); font-weight: 500; }
    .ds-signal-big {
      font-size: 44px; font-weight: 600; font-family: var(--font-mono);
      line-height: 1; letter-spacing: -0.02em; color: var(--text-primary);
    }
    .ds-signal-change { font-size: 13px; font-family: var(--font-mono); color: var(--text-muted); }
    .ds-signal-change.up { color: var(--success); }
    .ds-signal-change.down { color: var(--danger); }
    .ds-signal-rhs { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
    .ds-signal-badge {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 12px; border-radius: 999px;
      font-weight: 600; font-size: 13px; letter-spacing: 0.05em;
    }
    .ds-signal-badge.ds-sb-buy  { background: color-mix(in srgb, var(--success) 16%, transparent); color: var(--success); }
    .ds-signal-badge.ds-sb-hold { background: color-mix(in srgb, var(--warning) 16%, transparent); color: var(--warning); }
    .ds-signal-badge.ds-sb-sell { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
    .ds-regime {
      font-size: 11.5px; color: var(--text-muted);
      display: flex; align-items: center; gap: 6px;
    }
    .ds-regime .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }

    /* ─── Watchlist ─── */
    .ds-watchlist { display: flex; flex-direction: column; }
    .ds-wl-row {
      display: grid; grid-template-columns: 1.2fr 1fr 1fr 90px;
      gap: 12px; align-items: center;
      padding: 10px 4px; border-bottom: 1px solid var(--border);
      font-size: 13px;
    }
    .ds-wl-row:last-child { border-bottom: none; }
    .ds-wl-row .t { font-weight: 600; color: var(--text-primary); }
    .ds-wl-row .p { font-family: var(--font-mono); color: var(--text-secondary); }
    .ds-wl-row .d { font-family: var(--font-mono); }
    .ds-wl-row .d.up { color: var(--success); }
    .ds-wl-row .d.down { color: var(--danger); }
    .ds-spark { height: 22px; width: 100%; }

    /* ─── KPI grid (inside cards) ─── */
    .ds-kpi-grid {
      display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px;
    }
    .ds-kpi { display: flex; flex-direction: column; gap: 4px; }
    .ds-kpi-label { font-size: 11px; color: var(--text-muted);
      text-transform: uppercase; letter-spacing: 0.06em; }
    .ds-kpi-value { font-size: 22px; font-weight: 600; font-family: var(--font-mono);
      line-height: 1.1; color: var(--text-primary); }
    .ds-kpi-delta { font-size: 12px; font-family: var(--font-mono); color: var(--text-muted); }
    .ds-kpi-delta.up { color: var(--success); }
    .ds-kpi-delta.down { color: var(--danger); }

    /* ─── Generic grid helpers ─── */
    .ds-grid { display: grid; gap: var(--gap); }
    .ds-grid.ds-cols-2 { grid-template-columns: repeat(2, 1fr); }
    .ds-grid.ds-cols-3 { grid-template-columns: repeat(3, 1fr); }
    .ds-grid.ds-cols-4 { grid-template-columns: repeat(4, 1fr); }

    /* ─── Regime cards (from REGIMES mockup) ─── */
    .ds-rgm {
      padding: 16px; display: flex; flex-direction: column; gap: 6px;
      position: relative; border-left: 3px solid transparent;
    }
    .ds-rgm.bull  { border-left-color: var(--success); }
    .ds-rgm.bear  { border-left-color: var(--danger); }
    .ds-rgm.trans { border-left-color: var(--warning); }
    .ds-rgm.accum { border-left-color: var(--info); }
    .ds-rgm.dist  { border-left-color: var(--warning); }
    .ds-rgm .t { font-family: var(--font-mono); font-size: 14px; font-weight: 600; color: var(--text-primary); }
    .ds-rgm .state { font-size: 12.5px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }
    .ds-rgm.bull  .state { color: var(--success); }
    .ds-rgm.bear  .state { color: var(--danger); }
    .ds-rgm.trans .state { color: var(--warning); }
    .ds-rgm.accum .state { color: var(--info); }
    .ds-rgm.dist  .state { color: var(--warning); }
    .ds-rgm .conf  { font-size: 11.5px; color: var(--text-muted); font-family: var(--font-mono); }
    .ds-rgm .since { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

    /* ─── Legacy-header suppression ───
       Kill the old emoji-heavy h1 strings that duplicate the new page_header.
       We only target the exact legacy markup patterns; real user content untouched. */
    section.main h1:has(> :where([style*="font-size:26px"])) {
      /* placeholder — real suppression handled via element-level class toggles */
    }
    /* Hide the old "🎯 Crypto Signals — What To Do Today" h1 after our new
       page_header ships. It's emitted via raw st.markdown with inline style,
       so we match on the specific large-font h1 style that lives outside our
       .ds-page-title container. */
    section.main > div.block-container > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]
      > [data-testid="stMarkdown"] h1[style*="font-size:26px"] {
      display: none !important;
    }
    section.main > div.block-container > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]
      > [data-testid="stMarkdown"] h1[style*="clamp(24px, 2.2vw, 32px)"] {
      display: none !important;
    }

    /* Responsive hero cards */
    @media (max-width: 1024px) {
      .ds-hero-grid { grid-template-columns: 1fr; }
      .ds-grid.ds-cols-4 { grid-template-columns: repeat(2, 1fr); }
      .ds-grid.ds-cols-3 { grid-template-columns: repeat(2, 1fr); }
    }

    /* Mobile */
    @media (max-width: 768px) {
      [data-testid="stSidebar"] { min-width: 100% !important; max-width: 100% !important; }
      section.main > div.block-container { padding-top: 12px; padding-bottom: 48px; }
      .ds-strip { grid-template-columns: repeat(2, 1fr) !important; }
      .ds-strip > div { border-right: none; border-bottom: 1px solid var(--border); }
      .ds-strip > div:last-child { border-bottom: none; }
      .ds-page-hd { flex-direction: column; align-items: flex-start; }
      .ds-level-group { display: none; }
      .ds-hero-grid { grid-template-columns: 1fr !important; }
      .ds-grid.ds-cols-2, .ds-grid.ds-cols-3, .ds-grid.ds-cols-4 { grid-template-columns: 1fr !important; }
      .ds-signal-big { font-size: 32px; }
      /* Hide the level pills in the topbar on mobile (mockup behaviour).
         The level can still be changed via Settings. Refresh + Theme stay. */
      [data-testid="stHorizontalBlock"]:has(.ds-crumbs[data-topbar="1"])
        > [data-testid="column"]:nth-child(2),
      [data-testid="stHorizontalBlock"]:has(.ds-crumbs[data-topbar="1"])
        > [data-testid="column"]:nth-child(3),
      [data-testid="stHorizontalBlock"]:has(.ds-crumbs[data-topbar="1"])
        > [data-testid="column"]:nth-child(4) {
        display: none !important;
      }
      .ds-status-pill { font-size: 10px; padding: 2px 6px; }
    }
    """

    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
