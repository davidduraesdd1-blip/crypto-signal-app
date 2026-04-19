"""
ui_components.py — Premium UI design system for Crypto Signal Dashboard
Glass-morphism, gradient borders, fluid typography, animated backgrounds.
Inspired by KOI, Flare Network, dYdX, and Uniswap visual design systems.
"""
import logging
import streamlit as st

logger = logging.getLogger(__name__)

# ── Full CSS design system ─────────────────────────────────────────────────────

_CSS = """
<style>

/* ═══════════════════════════════════════════════
   GOOGLE FONTS — Inter (UI) + JetBrains Mono (data)
═══════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* ═══════════════════════════════════════════════
   DESIGN TOKENS — single source of truth
═══════════════════════════════════════════════ */
:root {
    /* backgrounds */
    --bg-base:   #0d0e14;
    --bg-0:      #0d0e14;
    --bg-1:      #111827;
    --bg-2:      #1e293b;
    --bg-3:      #1e293b;
    --bg-glass:  rgba(14, 18, 30, 0.72);

    /* brand */
    --primary:       #00d4aa;
    --primary-dim:   #10b981;
    --primary-glow:  rgba(0, 212, 170, 0.18);
    --primary-glow2: rgba(0, 212, 170, 0.06);
    --accent:        #8b5cf6;   /* indigo accent — dYdX-inspired */
    --accent-glow:   rgba(99, 102, 241, 0.14);

    /* signal */
    --bull:       #00d4aa;
    --bull-dim:   rgba(0, 212, 170, 0.15);
    --bull-border:rgba(0, 212, 170, 0.35);
    --bear:       #ef4444;
    --bear-dim:   rgba(246, 70, 93, 0.15);
    --bear-border:rgba(246, 70, 93, 0.35);
    --warn:       #f59e0b;
    --warn-dim:   rgba(245, 158, 11, 0.15);
    --neutral:    #64748b;

    /* text */
    --text-1: #e2e8f0;
    --text-2: #94a3b8;
    --text-3: #64748b;
    --text-4: #334155;

    /* borders */
    --border:    rgba(255, 255, 255, 0.07);
    --border-hi: rgba(255, 255, 255, 0.13);
    --border-px: rgba(255, 255, 255, 0.04);

    /* typography — fluid (clamp: min, preferred, max) */
    --font-ui:   'Inter', system-ui, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
    --fs-xxs:    clamp(9px,  0.65vw, 10px);
    --fs-xs:     clamp(11px, 0.75vw, 12px);
    --fs-sm:     clamp(12px, 0.85vw, 13px);
    --fs-base:   clamp(13px, 0.9vw,  14px);
    --fs-md:     clamp(14px, 1vw,    16px);
    --fs-lg:     clamp(16px, 1.2vw,  20px);
    --fs-xl:     clamp(20px, 1.6vw,  26px);
    --fs-2xl:    clamp(24px, 2vw,    32px);

    /* radii */
    --r-xs:  4px;
    --r-sm:  8px;
    --r-md:  12px;
    --r-lg:  16px;
    --r-xl:  22px;
    --r-pill:999px;

    /* shadows */
    --shadow-sm:   0 2px 8px  rgba(0,0,0,0.5);
    --shadow-card: 0 4px 24px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.05);
    --shadow-glow: 0 0 28px rgba(0,212,170,0.13);
    --shadow-pop:  0 8px 40px rgba(0,0,0,0.7);

    /* transitions */
    --t-fast:  0.12s ease;
    --t-base:  0.22s ease;
    --t-slow:  0.38s ease;
}

/* ═══════════════════════════════════════════════
   BASE — typography & font
═══════════════════════════════════════════════ */
html, body, [class*="css"], .stApp {
    font-family: var(--font-ui) !important;
    -webkit-font-smoothing: antialiased !important;
    text-rendering: optimizeLegibility !important;
}

/* ═══════════════════════════════════════════════
   APP BACKGROUND — radial mesh (dYdX / KOI style)
   Two subtle color orbs give depth without distraction
═══════════════════════════════════════════════ */
.stApp {
    background:
        radial-gradient(ellipse 80% 50% at 15% 0%,   rgba(99,102,241,0.07) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 85% 100%, rgba(0,212,170,0.06)  0%, transparent 55%),
        radial-gradient(ellipse 100% 80% at 50% 0%,  rgba(0,0,0,0.3)        0%, transparent 100%),
        #0d0e14 !important;
    background-attachment: fixed !important;
}
[data-testid="stAppViewContainer"] > .main {
    background: transparent !important;
}

/* ═══════════════════════════════════════════════
   HEADINGS — fluid + gradient on h1
═══════════════════════════════════════════════ */
h1 {
    font-size: var(--fs-xl) !important;
    font-weight: 800 !important;
    letter-spacing: -0.6px !important;
    background: linear-gradient(135deg, #e2e8f0 0%, #94a3b8 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    padding-bottom: 2px !important;
}
h2 {
    font-size: var(--fs-md) !important;
    font-weight: 600 !important;
    color: #cbd5e1 !important;
    letter-spacing: -0.2px !important;
}
h3 {
    font-size: var(--fs-sm) !important;
    font-weight: 600 !important;
    color: #94a3b8 !important;
}

/* ═══════════════════════════════════════════════
   METRIC CARDS — glassmorphic + gradient border
   Technique: gradient background-box + padding-box clipping
═══════════════════════════════════════════════ */
[data-testid="metric-container"] {
    background:
        linear-gradient(var(--bg-glass), var(--bg-glass)) padding-box,
        linear-gradient(135deg, rgba(0,212,170,0.22) 0%, rgba(99,102,241,0.15) 50%, rgba(255,255,255,0.04) 100%) border-box !important;
    border: 1px solid transparent !important;
    border-radius: var(--r-md) !important;
    padding: 18px 20px !important;
    position: relative !important;
    overflow: hidden !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    transition: box-shadow var(--t-base), transform var(--t-fast) !important;
    box-shadow: var(--shadow-card) !important;
}
/* teal top accent bar */
[data-testid="metric-container"]::before {
    content: '' !important;
    position: absolute !important;
    top: 0; left: 0; right: 0 !important;
    height: 2px !important;
    background: linear-gradient(90deg, var(--primary) 0%, var(--accent) 100%) !important;
    opacity: 0.7 !important;
    border-radius: var(--r-md) var(--r-md) 0 0 !important;
}
[data-testid="metric-container"]:hover {
    box-shadow: var(--shadow-glow), var(--shadow-card) !important;
    transform: translateY(-2px) !important;
}

/* Metric label */
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] > div {
    color: rgba(168,180,200,0.7) !important;
    font-size: var(--fs-xxs) !important;
    font-weight: 600 !important;
    letter-spacing: 1.1px !important;
    text-transform: uppercase !important;
}

/* Metric value */
[data-testid="stMetricValue"] > div,
[data-testid="stMetricValue"] {
    color: var(--text-1) !important;
    font-size: clamp(20px, 1.5vw, 26px) !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px !important;
    font-family: var(--font-mono) !important;
}

/* Deltas */
[data-testid="stMetricDelta"][data-direction="positive"] { color: #22c55e !important; }
[data-testid="stMetricDelta"][data-direction="negative"] { color: #ef4444 !important; }

/* ═══════════════════════════════════════════════
   EXPANDERS / PAIR CARDS — glassmorphic panels
═══════════════════════════════════════════════ */
[data-testid="stExpander"] {
    background:
        linear-gradient(rgba(14,18,30,0.8), rgba(14,18,30,0.8)) padding-box,
        linear-gradient(160deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.02) 100%) border-box !important;
    border: 1px solid transparent !important;
    border-radius: var(--r-md) !important;
    margin-bottom: 8px !important;
    overflow: hidden !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    transition: box-shadow var(--t-base), border-color var(--t-fast) !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stExpander"]:hover {
    background:
        linear-gradient(rgba(16,20,34,0.85), rgba(16,20,34,0.85)) padding-box,
        linear-gradient(160deg, rgba(0,212,170,0.25) 0%, rgba(99,102,241,0.15) 100%) border-box !important;
    box-shadow: 0 0 0 0 transparent, 0 4px 20px rgba(0,0,0,0.5) !important;
}
[data-testid="stExpander"] > details[open] {
    background:
        linear-gradient(rgba(14,18,30,0.9), rgba(14,18,30,0.9)) padding-box,
        linear-gradient(160deg, rgba(0,212,170,0.3) 0%, rgba(99,102,241,0.18) 60%, rgba(255,255,255,0.06) 100%) border-box !important;
    box-shadow: var(--shadow-glow) !important;
}
[data-testid="stExpander"] > details > summary {
    padding: 13px 18px !important;
    font-weight: 600 !important;
    font-size: var(--fs-sm) !important;
    cursor: pointer !important;
    color: var(--text-2) !important;
}
[data-testid="stExpander"] > details > div {
    padding: 4px 18px 18px 18px !important;
}

/* ═══════════════════════════════════════════════
   GLOBAL BASE FONT — 0.85rem for all interactive + body elements
   Metric values (1rem+) and page titles kept large intentionally.
   Captions/badges kept at 0.75rem for visual hierarchy.
═══════════════════════════════════════════════ */
[data-testid="stMarkdownContainer"] div,
[data-testid="stMarkdownContainer"] span { font-size: 0.85rem; }
[data-testid="stMain"] label, [data-testid="stMain"] label p, [data-testid="stMain"] label span { font-size: 0.85rem !important; }
[data-testid="stMain"] input, [data-testid="stMain"] textarea { font-size: 0.85rem !important; }
[data-testid="stMain"] [data-baseweb="select"] span, [data-testid="stMain"] [data-baseweb="select"] div, [data-testid="stMain"] [data-baseweb="select"] input { font-size: 0.85rem !important; }
[data-testid="stMain"] [role="listbox"] li, [data-testid="stMain"] [role="option"], [data-testid="stMain"] [role="option"] * { font-size: 0.85rem !important; }
[data-testid="stMain"] button p, [data-testid="stMain"] button span, [data-testid="stFormSubmitButton"] button p { font-size: 0.85rem !important; }
[data-testid="stMain"] [data-testid="stTab"] p, [data-testid="stMain"] [data-testid="stTab"] span { font-size: 0.85rem !important; }
[data-testid="stMain"] p { font-size: 0.85rem !important; }
[data-testid="stSidebar"] label, [data-testid="stSidebar"] label p, [data-testid="stSidebar"] label span { font-size: 0.85rem !important; }
[data-testid="stSidebar"] p { font-size: 0.85rem !important; }
[data-testid="stExpander"] > details > summary { font-size: 0.85rem !important; }
[data-testid="stCaptionContainer"] p, [data-testid="stMain"] small { font-size: 0.75rem !important; }

/* ═══════════════════════════════════════════════
   SIDEBAR — deeper glass panel
═══════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background:
        radial-gradient(ellipse 120% 60% at 50% 0%, rgba(0,212,170,0.05) 0%, transparent 60%),
        #0d0e14 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] .stRadio label {
    font-size: var(--fs-sm) !important;
    color: rgba(168,180,200,0.65) !important;
    padding: 6px 0 !important;
    transition: color var(--t-fast) !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    color: var(--primary) !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255,255,255,0.025) !important;
    border-color: rgba(255,255,255,0.05) !important;
    border-radius: var(--r-sm) !important;
    backdrop-filter: none !important;
}

/* ═══════════════════════════════════════════════
   BUTTONS — gradient primary, ghost secondary
═══════════════════════════════════════════════ */
.stButton > button[kind="primary"],
button[kind="primary"] {
    background: linear-gradient(135deg, #00d4aa 0%, #10b981 60%, #a78bfa 100%) !important;
    border: none !important;
    color: #0d0e14 !important;
    font-weight: 700 !important;
    font-size: var(--fs-sm) !important;
    letter-spacing: 0.3px !important;
    border-radius: var(--r-sm) !important;
    transition: box-shadow var(--t-base), transform var(--t-fast) !important;
    box-shadow: 0 2px 14px rgba(0,212,170,0.25) !important;
    padding: 8px 18px !important;
}
.stButton > button[kind="primary"]:hover,
button[kind="primary"]:hover {
    box-shadow: 0 4px 28px rgba(0,212,170,0.45), 0 0 0 1px rgba(0,212,170,0.3) !important;
    transform: translateY(-2px) !important;
}
.stButton > button[kind="primary"]:active,
button[kind="primary"]:active {
    transform: translateY(0) !important;
    box-shadow: 0 1px 8px rgba(0,212,170,0.25) !important;
}

/* Secondary / ghost buttons */
.stButton > button[kind="secondary"],
button[kind="secondary"],
.stButton > button:not([kind]) {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: rgba(168,180,200,0.75) !important;
    border-radius: var(--r-sm) !important;
    font-size: var(--fs-sm) !important;
    transition: all var(--t-base) !important;
    backdrop-filter: blur(8px) !important;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button:not([kind]):hover {
    border-color: rgba(0,212,170,0.35) !important;
    color: var(--primary) !important;
    background: rgba(0,212,170,0.06) !important;
    box-shadow: 0 0 12px rgba(0,212,170,0.1) !important;
}
.stButton > button:disabled { opacity: 0.32 !important; cursor: not-allowed !important; }

/* Download buttons */
.stDownloadButton > button {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: rgba(168,180,200,0.7) !important;
    border-radius: var(--r-sm) !important;
    font-size: var(--fs-sm) !important;
    transition: all var(--t-base) !important;
}
.stDownloadButton > button:hover {
    border-color: var(--bull-border) !important;
    color: var(--primary) !important;
    box-shadow: 0 0 10px var(--primary-glow2) !important;
}

/* ═══════════════════════════════════════════════
   TABS — pill-style active indicator (KOI-inspired)
═══════════════════════════════════════════════ */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.025) !important;
    border-radius: var(--r-sm) !important;
    padding: 4px !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    gap: 2px !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 6px !important;
    color: rgba(168,180,200,0.55) !important;
    font-weight: 500 !important;
    font-size: var(--fs-sm) !important;
    padding: 7px 18px !important;
    border-bottom: none !important;
    transition: all var(--t-base) !important;
    background: transparent !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(0,212,170,0.18) 0%, rgba(99,102,241,0.12) 100%) !important;
    color: var(--primary) !important;
    font-weight: 700 !important;
    border-bottom: none !important;
    box-shadow: 0 0 0 1px rgba(0,212,170,0.25) !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    color: rgba(232,236,244,0.75) !important;
    background: rgba(255,255,255,0.04) !important;
}

/* ═══════════════════════════════════════════════
   INPUT FIELDS — glass style + teal focus ring
═══════════════════════════════════════════════ */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    background: rgba(14,18,30,0.9) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: var(--r-sm) !important;
    color: var(--text-1) !important;
    font-size: var(--fs-sm) !important;
    transition: border-color var(--t-base), box-shadow var(--t-base) !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: rgba(0,212,170,0.45) !important;
    box-shadow: 0 0 0 3px rgba(0,212,170,0.1), 0 0 16px rgba(0,212,170,0.08) !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stNumberInput"] input::placeholder {
    color: var(--text-4) !important;
}

/* Selectbox */
[data-testid="stSelectbox"] > div > div {
    background: rgba(14,18,30,0.9) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: var(--r-sm) !important;
    color: var(--text-1) !important;
}
[data-testid="stMultiSelect"] > div {
    background: rgba(14,18,30,0.9) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: var(--r-sm) !important;
}

/* Slider */
[data-baseweb="slider"] [role="slider"] {
    background: var(--primary) !important;
    border-color: var(--primary) !important;
    box-shadow: 0 0 8px var(--primary-glow) !important;
}

/* ═══════════════════════════════════════════════
   DATA TABLES / DATAFRAMES
═══════════════════════════════════════════════ */
[data-testid="stDataFrame"],
[data-testid="stDataFrameResizable"] {
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: var(--r-md) !important;
    overflow: hidden !important;
    background: rgba(14,18,30,0.6) !important;
}

/* ═══════════════════════════════════════════════
   PROGRESS BAR — animated gradient
═══════════════════════════════════════════════ */
@keyframes shimmer-bar {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}
[data-testid="stProgressBar"] > div > div > div > div {
    background: linear-gradient(90deg, var(--primary), #00d4aa, var(--accent), var(--primary)) !important;
    background-size: 200% auto !important;
    animation: shimmer-bar 2.5s linear infinite !important;
    border-radius: var(--r-xs) !important;
}
[data-testid="stProgressBar"] > div > div {
    background: rgba(255,255,255,0.06) !important;
    border-radius: var(--r-xs) !important;
}

/* ═══════════════════════════════════════════════
   ALERTS / STATUS BANNERS
═══════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: var(--r-sm) !important;
    font-size: var(--fs-sm) !important;
    backdrop-filter: blur(8px) !important;
}
.stSuccess {
    background: rgba(0,192,118,0.09) !important;
    border-color: rgba(0,192,118,0.28) !important;
}
.stError {
    background: rgba(246,70,93,0.09) !important;
    border-color: rgba(246,70,93,0.28) !important;
}
.stWarning {
    background: rgba(245,158,11,0.09) !important;
    border-color: rgba(245,158,11,0.28) !important;
}
.stInfo {
    background: rgba(0,212,170,0.07) !important;
    border-color: rgba(0,212,170,0.22) !important;
}

/* ═══════════════════════════════════════════════
   DIVIDERS
═══════════════════════════════════════════════ */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.08) 30%, rgba(255,255,255,0.08) 70%, transparent) !important;
    margin: 20px 0 !important;
}

/* ═══════════════════════════════════════════════
   CAPTIONS / MUTED TEXT
═══════════════════════════════════════════════ */
[data-testid="stCaptionContainer"] p,
.stCaption p {
    color: rgba(168,180,200,0.4) !important;
    font-size: var(--fs-xs) !important;
    line-height: 1.55 !important;
}

/* ═══════════════════════════════════════════════
   CHECKBOX & TOGGLE
═══════════════════════════════════════════════ */
[data-testid="stCheckbox"] label { color: rgba(168,180,200,0.78) !important; font-size: var(--fs-sm) !important; }
[data-testid="stToggle"] label   { font-size: var(--fs-sm) !important; }

/* ═══════════════════════════════════════════════
   FORM CONTAINER
═══════════════════════════════════════════════ */
[data-testid="stForm"] {
    background: rgba(14,18,30,0.7) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: var(--r-md) !important;
    padding: 18px !important;
    backdrop-filter: blur(12px) !important;
}

/* ═══════════════════════════════════════════════
   HIDE DEFAULT STREAMLIT CHROME
═══════════════════════════════════════════════ */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"] { background: transparent !important; }

/* ═══════════════════════════════════════════════
   CUSTOM SCROLLBAR — thin teal thumb
═══════════════════════════════════════════════ */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, rgba(0,212,170,0.35), rgba(99,102,241,0.25));
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(0,212,170,0.55); }

/* ═══════════════════════════════════════════════
   POPOVER
═══════════════════════════════════════════════ */
[data-testid="stPopover"] button {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: var(--r-xs) !important;
    color: rgba(168,180,200,0.55) !important;
    font-size: var(--fs-xs) !important;
    padding: 3px 10px !important;
    transition: all var(--t-fast) !important;
}
[data-testid="stPopover"] button:hover {
    border-color: rgba(0,212,170,0.4) !important;
    color: var(--primary) !important;
}

/* ═══════════════════════════════════════════════
   PULSING LIVE DOT — expanded glow ring
═══════════════════════════════════════════════ */
@keyframes pulse-dot {
    0%   { box-shadow: 0 0 0 0   rgba(0,212,170,0.8); }
    60%  { box-shadow: 0 0 0 5px rgba(0,212,170,0); }
    100% { box-shadow: 0 0 0 0   rgba(0,212,170,0); }
}
.live-dot {
    display: inline-block;
    width: 7px; height: 7px;
    background: var(--primary);
    border-radius: 50%;
    animation: pulse-dot 2.2s ease-out infinite;
    vertical-align: middle;
    margin-right: 5px;
    box-shadow: 0 0 6px rgba(0,212,170,0.6);
}

/* ═══════════════════════════════════════════════
   FADE-IN-UP — applied to custom HTML cards
═══════════════════════════════════════════════ */
@keyframes fade-up {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
.fade-up { animation: fade-up 0.35s ease forwards; }

/* ═══════════════════════════════════════════════
   SHIMMER GRADIENT — loading skeleton style
═══════════════════════════════════════════════ */
@keyframes shimmer {
    0%   { background-position: -400px 0; }
    100% { background-position:  400px 0; }
}
.shimmer {
    background: linear-gradient(90deg,
        rgba(255,255,255,0.04) 0%,
        rgba(255,255,255,0.09) 40%,
        rgba(255,255,255,0.04) 80%
    ) !important;
    background-size: 800px 100% !important;
    animation: shimmer 1.6s infinite !important;
}

/* ═══════════════════════════════════════════════
   GLOBAL UTILITY CLASSES
═══════════════════════════════════════════════ */
.mono  { font-family: var(--font-mono) !important; }
.bull  { color: var(--bull) !important; }
.bear  { color: var(--bear) !important; }
.warn  { color: var(--warn) !important; }
.muted { color: var(--text-3) !important; }
.upper { text-transform: uppercase; letter-spacing: 0.8px; font-size: 10px; font-weight: 600; }

/* ═══════════════════════════════════════════════
   BEGINNER MODE — hide advanced elements
   Toggle via st.session_state["beginner_mode"]
   Inject class "advanced-only" on elements to hide in simple view.
   JS reads session state cookie to apply/remove body class.
═══════════════════════════════════════════════ */
body.beginner-mode .advanced-only {
    display: none !important;
}

/* Beginner mode — larger signal pills for readability */
body.beginner-mode .signal-pill {
    font-size: 15px !important;
    padding: 6px 18px !important;
}

/* Beginner mode — increase metric value font size slightly */
body.beginner-mode [data-testid="stMetricValue"] > div {
    font-size: clamp(22px, 1.8vw, 30px) !important;
}

/* Beginner mode body tag injected by inject_beginner_mode_js() */

/* ═══════════════════════════════════════════════
   MOBILE — 768px breakpoint + 44px tap targets
═══════════════════════════════════════════════ */
@media (max-width: 768px) {
    .stApp { font-size: var(--fs-sm) !important; }
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
    /* 44px minimum tap targets */
    div[data-testid="stButton"] > button { min-height: 44px !important; }
    [data-testid="stRadio"] label { min-height: 44px !important; padding: 10px 0 !important; }
    [data-testid="stCheckbox"] label { min-height: 44px !important; padding: 10px 0 !important; }
    [data-testid="stToggle"] label { min-height: 44px !important; }
    [data-baseweb="select"] { min-height: 44px !important; }
    /* Stack columns */
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    [data-testid="stColumn"] { min-width: 100% !important; }
}

/* ═══════════════════════════════════════════════
   PHONE — 375px breakpoint (iPhone SE / small Android)
   Item 16: Small-phone layout hardening
═══════════════════════════════════════════════ */
@media (max-width: 390px) {
    /* Tighter padding on very small screens */
    .block-container { padding-left: 0.25rem !important; padding-right: 0.25rem !important; }
    /* Metric values: clamp to fit 375px without overflow */
    [data-testid="stMetricValue"] > div { font-size: clamp(16px, 4vw, 22px) !important; }
    [data-testid="stMetricLabel"] { font-size: 11px !important; }
    /* Section headers: reduce padding */
    .section-header { padding: 8px 10px !important; }
    /* Hero cards: single column, full width */
    .hero-card { min-width: 100% !important; max-width: 100% !important; }
    /* Coin cards grid: single column */
    .coin-card { min-width: calc(100% - 8px) !important; max-width: 100% !important; }
    /* Signal rank list: hide entry/stop columns to save space */
    .rank-stop-col { display: none !important; }
    /* Sidebar: smaller text */
    [data-testid="stSidebar"] { font-size: 12px !important; }
    /* Buttons: full width, 44px minimum height */
    div[data-testid="stButton"] > button {
        min-height: 44px !important;
        width: 100% !important;
        font-size: 14px !important;
    }
    /* Selectbox: 44px minimum height */
    [data-baseweb="select"] > div { min-height: 44px !important; }
    /* Input fields: larger font for readability */
    input[type="text"], input[type="number"] { font-size: 16px !important; }
    /* Tables: allow horizontal scroll */
    .stDataFrame { overflow-x: auto !important; }
    /* Charts: no overflow */
    .js-plotly-plot { max-width: 100vw !important; overflow: hidden !important; }
}

/* ═══════════════════════════════════════════════
   LIGHT MODE — full WCAG AA implementation
   Body class toggled by render_theme_toggle_sg() JS
═══════════════════════════════════════════════ */

/* 1. Override all design token variables so every var() flips automatically */
body.light-mode {
    --bg-base:   #f1f5f9;
    --bg-0:      #f1f5f9;
    --bg-1:      #ffffff;
    --bg-2:      #f8fafc;
    --bg-3:      #f1f5f9;
    --bg-glass:  rgba(255, 255, 255, 0.88);
    --text-1:    #0f172a;
    --text-2:    #334155;
    --text-3:    #64748b;
    --text-4:    #94a3b8;
    --border:    rgba(0, 0, 0, 0.09);
    --border-hi: rgba(0, 0, 0, 0.14);
    --border-px: rgba(0, 0, 0, 0.05);
    --shadow-sm:   0 2px 6px rgba(0,0,0,0.08);
    --shadow-card: 0 2px 12px rgba(0,0,0,0.07), inset 0 1px 0 rgba(255,255,255,0.9);
    --shadow-glow: 0 0 20px rgba(0,212,170,0.10);
    --shadow-pop:  0 8px 32px rgba(0,0,0,0.14);
}

/* 2. App shell */
body.light-mode,
body.light-mode .stApp { background: #f1f5f9 !important; color: #1e293b !important; }
body.light-mode .stApp {
    background:
        radial-gradient(ellipse 80% 50% at 15% 0%,   rgba(99,102,241,0.04) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 85% 100%, rgba(0,212,170,0.04)  0%, transparent 55%),
        #f1f5f9 !important;
    background-attachment: fixed !important;
}
body.light-mode [data-testid="stAppViewContainer"] > .main { background: transparent !important; }

/* 3. Sidebar */
body.light-mode [data-testid="stSidebar"] {
    background: #e2e8f0 !important;
    border-right: 1px solid rgba(0,0,0,0.08) !important;
}
body.light-mode [data-testid="stSidebar"] .stRadio label { color: #475569 !important; }
body.light-mode [data-testid="stSidebar"] .stRadio label:hover { color: #00d4aa !important; }
body.light-mode [data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255,255,255,0.75) !important;
    border-color: rgba(0,0,0,0.08) !important;
}

/* 4. Headings */
body.light-mode h1 {
    background: linear-gradient(135deg, #0f172a 0%, #334155 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
}
body.light-mode h2 { color: #1e293b !important; }
body.light-mode h3 { color: #475569 !important; }

/* 5. Metric containers */
body.light-mode [data-testid="metric-container"] {
    background:
        linear-gradient(rgba(255,255,255,0.96), rgba(255,255,255,0.96)) padding-box,
        linear-gradient(135deg, rgba(0,212,170,0.20) 0%, rgba(99,102,241,0.12) 50%, rgba(0,0,0,0.05) 100%) border-box !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.9) !important;
}
body.light-mode [data-testid="stMetricLabel"],
body.light-mode [data-testid="stMetricLabel"] > div { color: rgba(71,85,105,0.85) !important; }
body.light-mode [data-testid="stMetricValue"] > div,
body.light-mode [data-testid="stMetricValue"] { color: #0f172a !important; }

/* 6. Expanders */
body.light-mode [data-testid="stExpander"] {
    background:
        linear-gradient(rgba(255,255,255,0.94), rgba(255,255,255,0.94)) padding-box,
        linear-gradient(160deg, rgba(0,0,0,0.07) 0%, rgba(0,0,0,0.03) 100%) border-box !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}
body.light-mode [data-testid="stExpander"]:hover {
    background:
        linear-gradient(rgba(240,254,250,0.97), rgba(240,254,250,0.97)) padding-box,
        linear-gradient(160deg, rgba(0,212,170,0.22) 0%, rgba(99,102,241,0.10) 100%) border-box !important;
}
body.light-mode [data-testid="stExpander"] > details > summary { color: #334155 !important; }

/* 7. Tabs */
body.light-mode [data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.92) !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
}
body.light-mode [data-testid="stTabs"] [data-baseweb="tab"] { color: #64748b !important; }
body.light-mode [data-testid="stTabs"] [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(0,212,170,0.14) 0%, rgba(99,102,241,0.08) 100%) !important;
    color: #10b981 !important;
    box-shadow: 0 0 0 1px rgba(0,212,170,0.20) !important;
}
body.light-mode [data-testid="stTabs"] [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    background: rgba(0,0,0,0.04) !important;
    color: #334155 !important;
}

/* 8. Input fields */
body.light-mode [data-testid="stTextInput"] input,
body.light-mode [data-testid="stNumberInput"] input {
    background: rgba(255,255,255,0.97) !important;
    border: 1px solid rgba(0,0,0,0.10) !important;
    color: #1e293b !important;
}
body.light-mode [data-testid="stTextInput"] input::placeholder,
body.light-mode [data-testid="stNumberInput"] input::placeholder { color: #94a3b8 !important; }

/* 9. Select / dropdown (baseweb) */
body.light-mode [data-testid="stSelectbox"] > div > div {
    background: rgba(255,255,255,0.97) !important;
    border: 1px solid rgba(0,0,0,0.10) !important;
    color: #1e293b !important;
}
body.light-mode [data-testid="stMultiSelect"] > div {
    background: rgba(255,255,255,0.97) !important;
    border: 1px solid rgba(0,0,0,0.10) !important;
}
body.light-mode [data-baseweb="select"] [data-baseweb="input-container"],
body.light-mode [data-baseweb="input"],
body.light-mode [data-baseweb="textarea"] { background-color: #ffffff !important; color: #1e293b !important; }
body.light-mode [data-baseweb="list"],
body.light-mode [data-baseweb="popover"] { background-color: #ffffff !important; color: #1e293b !important; border: 1px solid rgba(0,0,0,0.10) !important; }
body.light-mode [data-baseweb="list"] li,
body.light-mode [data-baseweb="menu-item"] { color: #1e293b !important; }
body.light-mode [data-baseweb="list"] li:hover,
body.light-mode [data-baseweb="menu-item"]:hover { background-color: rgba(0,212,170,0.07) !important; }

/* 10. Buttons */
body.light-mode .stButton > button[kind="secondary"],
body.light-mode .stButton > button:not([kind]) {
    background: rgba(255,255,255,0.92) !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    color: #334155 !important;
}
body.light-mode .stButton > button[kind="secondary"]:hover,
body.light-mode .stButton > button:not([kind]):hover {
    border-color: rgba(0,212,170,0.4) !important;
    color: #10b981 !important;
    background: rgba(0,212,170,0.06) !important;
}
body.light-mode .stDownloadButton > button {
    background: rgba(255,255,255,0.92) !important;
    border: 1px solid rgba(0,0,0,0.12) !important;
    color: #334155 !important;
}

/* 11. Data tables */
body.light-mode [data-testid="stDataFrame"],
body.light-mode [data-testid="stDataFrameResizable"] {
    border: 1px solid rgba(0,0,0,0.08) !important;
    background: rgba(255,255,255,0.97) !important;
}

/* 12. Progress bar track */
body.light-mode [data-testid="stProgressBar"] > div > div { background: rgba(0,0,0,0.07) !important; }

/* 13. Alerts */
body.light-mode .stSuccess { background: rgba(34,197,94,0.08) !important;  border-color: rgba(34,197,94,0.25) !important; }
body.light-mode .stError   { background: rgba(239,68,68,0.08) !important;  border-color: rgba(239,68,68,0.25) !important; }
body.light-mode .stWarning { background: rgba(245,158,11,0.08) !important; border-color: rgba(245,158,11,0.25) !important; }
body.light-mode .stInfo    { background: rgba(0,212,170,0.06) !important;  border-color: rgba(0,212,170,0.22) !important; }
body.light-mode [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p { color: #1e293b !important; }

/* 14. Dividers */
body.light-mode hr { background: linear-gradient(90deg, transparent, rgba(0,0,0,0.09) 30%, rgba(0,0,0,0.09) 70%, transparent) !important; }

/* 15. Text + labels */
body.light-mode [data-testid="stCaptionContainer"] p,
body.light-mode .stCaption p { color: #64748b !important; }
body.light-mode [data-testid="stMarkdownContainer"] p,
body.light-mode [data-testid="stMarkdownContainer"] li { color: #1e293b !important; }
body.light-mode [data-testid="stCheckbox"] label { color: #475569 !important; }
body.light-mode [data-testid="stToggle"] label   { color: #475569 !important; }
body.light-mode [data-testid="stRadio"] label span { color: #475569 !important; }

/* 16. Forms */
body.light-mode [data-testid="stForm"] {
    background: rgba(255,255,255,0.88) !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
}

/* 17. Popovers */
body.light-mode [data-testid="stPopover"] button {
    background: rgba(255,255,255,0.92) !important;
    border: 1px solid rgba(0,0,0,0.10) !important;
    color: #475569 !important;
}

/* 18. Scrollbar */
body.light-mode ::-webkit-scrollbar-track { background: #dde3ee; }
body.light-mode ::-webkit-scrollbar-thumb { background: linear-gradient(180deg, rgba(0,130,104,0.5), rgba(80,83,180,0.35)); }

/* 19. Inline HTML: flip known dark text colors → accessible on white */
body.light-mode :is(div,span,p,a,td,th)[style*="color:#e2e8f0"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:#cbd5e1"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:#94a3b8"] { color: #1e293b !important; }
body.light-mode :is(div,span,p,a,td,th)[style*="color:rgba(232,236,244"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:rgba(168,180,200,0.7"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:rgba(168,180,200,0.8"] { color: #1e293b !important; }
body.light-mode :is(div,span,p,a,td,th)[style*="color:#64748b"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:rgba(107,122,148"] { color: #475569 !important; }
body.light-mode :is(div,span,p,a,td,th)[style*="color:#334155"] { color: #64748b !important; }
body.light-mode :is(div,span,p,a,td,th)[style*="color:rgba(168,180,200,0.4"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:rgba(168,180,200,0.45"] { color: #64748b !important; }
body.light-mode :is(div,span,p,a,td,th)[style*="color:#9ca3af"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:#9CA3AF"] { color: #64748b !important; }
body.light-mode :is(div,span,p,a,td,th)[style*="color:#888"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:#aaa"],
body.light-mode :is(div,span,p,a,td,th)[style*="color:#999"] { color: #64748b !important; }

/* 20. Inline dark card backgrounds → white */
body.light-mode div[style*="background:rgba(14,18,30"],
body.light-mode div[style*="background:rgba(8,11,18"],
body.light-mode div[style*="background:rgba(16,20,34"] { background: rgba(255,255,255,0.92) !important; border-color: rgba(0,0,0,0.08) !important; }
body.light-mode div[style*="background:rgba(255,255,255,0.04"],
body.light-mode div[style*="background:rgba(255,255,255,0.03"] { background: rgba(0,0,0,0.04) !important; }
body.light-mode div[style*="border:1px solid rgba(255,255,255,0.07"],
body.light-mode div[style*="border:1px solid rgba(255,255,255,0.0"] { border-color: rgba(0,0,0,0.08) !important; }

</style>
"""


# ── Regional color helpers (ToS #10) ──────────────────────────────────────
# Supports "Asian" convention where RED = up (US/EU is green=up).
# Flipping st.session_state["sg_up_is_red"] flips every gain/loss color.

def color_up() -> str:
    """Return the hex color for positive/up moves per the user's regional preference."""
    return "#ef4444" if st.session_state.get("sg_up_is_red", False) else "#22c55e"

def color_down() -> str:
    """Return the hex color for negative/down moves per the user's regional preference."""
    return "#22c55e" if st.session_state.get("sg_up_is_red", False) else "#ef4444"

def color_for_delta(delta, default: str = "#64748b") -> str:
    """Given a delta string/number, return the regionally-correct color.
    Neutral (exactly 0 or '0' or '+0' / '-0') returns the default grey.
    """
    try:
        if isinstance(delta, (int, float)):
            if delta > 0:  return color_up()
            if delta < 0:  return color_down()
            return default
    except Exception:
        pass
    s = str(delta).strip()
    # Normalize common zero forms
    if s in ("0", "+0", "-0", "0.0", "+0.0", "-0.0", "0.00", "+0.00", "-0.00", "—"):
        return default
    first = next((c for c in s if c in "+-"), None)
    if first == "+": return color_up()
    if first == "-": return color_down()
    return default


# ── Quick-access popover row (ToS #7) ─────────────────────────────────────
# Top-right row of icon popovers for Agent / Alerts / Scans / Glossary.
# Mirrors DeFi Market Intelligence pattern; cached reads keep overhead low.

@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def _sg_recent_alerts() -> list:
    try:
        from pathlib import Path
        import json
        fp = Path("data") / "alert_history.jsonl"
        if not fp.exists():
            return []
        out = []
        for line in fp.read_text(encoding="utf-8").strip().split("\n")[-5:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []

def render_quick_access_row() -> None:
    """Render a 4-popover row flush-right at the top of a page."""
    _sp, _agent, _alerts, _scans, _glos = st.columns([10, 1, 1, 1, 1])
    with _agent:
        with st.popover("⚙", help="Agent status"):
            st.markdown("**Agent Status**")
            _running = st.session_state.get("sg_agent_running", False)
            st.markdown(f"Status: {'🟢 Active' if _running else '⚫ Idle'}")
            st.caption("Full control on the Agent page.")
    with _alerts:
        with st.popover("🔔", help="Recent alerts"):
            st.markdown("**Recent Alerts**")
            _recent = _sg_recent_alerts()
            if _recent:
                for _a in _recent:
                    st.markdown(f"• {_a.get('timestamp','—')[:16]} — {_a.get('message','—')[:60]}")
            else:
                st.caption("No alerts yet — configure in Settings.")
    with _scans:
        with st.popover("📜", help="Scan history"):
            st.markdown("**Recent Scans**")
            _sr = st.session_state.get("scan_results") or []
            _last = st.session_state.get("scan_results_ts")
            st.caption(f"Last scan: {str(_last)[:16] if _last else '—'}")
            st.caption(f"Coins scanned: {len(_sr) if _sr else 0}")
    with _glos:
        with st.popover("📖", help="Glossary"):
            st.markdown("**Quick Glossary**")
            st.markdown(
                "• **RSI** — momentum oscillator\n\n"
                "• **MACD** — trend/momentum indicator\n\n"
                "• **ADX** — trend strength\n\n"
                "• **MTF** — multi-timeframe alignment\n\n"
                "• **FNG** — Fear & Greed Index"
            )
            st.caption("Full glossary on the Dashboard page.")


# ── Regional Color Preference toggle (ToS #10) ────────────────────────────

def render_regional_color_toggle() -> None:
    """Side-by-side Western/Asian swatch picker for up/down color convention."""
    st.markdown(
        "<div style='color:#94a3b8; font-size:0.88rem; margin-bottom:8px;'>"
        "Regional color convention for gains and losses.</div>",
        unsafe_allow_html=True,
    )
    _is_asian = st.session_state.get("sg_up_is_red", False)
    _c1, _c2, _c3 = st.columns([4, 1, 4])
    with _c1:
        _active = "border:1px solid #00d4aa;" if not _is_asian else "border:1px solid rgba(148,163,184,0.15);"
        st.markdown(
            f"<div style='{_active} border-radius:10px; padding:14px; background:rgba(15,23,42,0.5);'>"
            f"<div style='font-size:1.25rem; font-weight:700; color:#22c55e; font-variant-numeric:tabular-nums;'>+1.00 ▲</div>"
            f"<div style='font-size:1.25rem; font-weight:700; color:#ef4444; font-variant-numeric:tabular-nums;'>-1.00 ▼</div>"
            f"<div style='color:#94a3b8; font-size:0.8rem; margin-top:6px;'>Western (US, EU)</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with _c2:
        st.markdown("<div style='display:flex; justify-content:center; align-items:center; height:100%;'>⇄</div>", unsafe_allow_html=True)
        if st.toggle("Flip", value=_is_asian, key="sg_up_is_red_toggle", label_visibility="collapsed"):
            if not _is_asian:
                st.session_state["sg_up_is_red"] = True
                st.rerun()
        else:
            if _is_asian:
                st.session_state["sg_up_is_red"] = False
                st.rerun()
    with _c3:
        _active = "border:1px solid #00d4aa;" if _is_asian else "border:1px solid rgba(148,163,184,0.15);"
        st.markdown(
            f"<div style='{_active} border-radius:10px; padding:14px; background:rgba(15,23,42,0.5);'>"
            f"<div style='font-size:1.25rem; font-weight:700; color:#ef4444; font-variant-numeric:tabular-nums;'>+1.00 ▲</div>"
            f"<div style='font-size:1.25rem; font-weight:700; color:#22c55e; font-variant-numeric:tabular-nums;'>-1.00 ▼</div>"
            f"<div style='color:#94a3b8; font-size:0.8rem; margin-top:6px;'>Asian (CN, JP, KR)</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def inject_css():
    """Inject the full premium CSS design system into the Streamlit app.
    Re-injects when theme changes so body.light-mode rules activate correctly.
    PERF: guarded by (session_state + theme) so the large CSS block is only
    sent to the browser when the theme actually changes.
    """
    _theme = st.session_state.get("_sg_theme", "dark")
    if (st.session_state.get("_css_injected")
            and st.session_state.get("_css_theme_last") == _theme):
        return
    st.markdown(_CSS, unsafe_allow_html=True)
    st.session_state["_css_injected"] = True
    st.session_state["_css_theme_last"] = _theme
    # Apply body.light-mode class via streamlit.components.v1.html — renders
    # the <script> inside a sandboxed iframe that actually executes JS, unlike
    # st.markdown(<script>) which React silently strips. Audit R10h: the
    # previous code called st.iframe(...) which is NOT a real Streamlit API
    # and crashed on every theme change with AttributeError.
    _mode = "add" if _theme == "light" else "remove"
    import streamlit.components.v1 as _components
    _components.html(
        f'<script>try{{window.parent.document.body.classList.{_mode}("light-mode");}}catch(e){{}}</script>',
        height=1,
    )


def inject_beginner_mode_js(beginner_mode: bool) -> None:
    """
    Toggle 'beginner-mode' class on <body> so CSS can hide .advanced-only elements.
    Call once per page render, after inject_css().
    PERF: only re-injects JS when beginner_mode state actually changes.
    """
    last = st.session_state.get("_beginner_mode_last")
    if last == beginner_mode:
        return
    st.session_state["_beginner_mode_last"] = beginner_mode
    action = "add" if beginner_mode else "remove"
    # st.markdown(<script>) is silently dropped by React's dangerouslySetInnerHTML,
    # so use streamlit.components.v1.html which renders in a sandboxed iframe that
    # actually executes JS. st.iframe is NOT a Streamlit API (audit R10h caught
    # the first instance; this is the second — same fix).
    import streamlit.components.v1 as _components
    _components.html(
        f'<script>try{{window.parent.document.body.classList.{action}("beginner-mode");}}catch(e){{}}</script>',
        height=1,
    )


# ── Section header — gradient text accent ─────────────────────────────────────

def section_header(title: str, subtitle: str = None, icon: str = None):
    """
    Render a styled section header.
    Uses gradient text for title, teal left-border + muted subtitle.
    """
    icon_html = f'<span style="margin-right:8px;font-size:15px;opacity:0.85">{icon}</span>' if icon else ''
    subtitle_html = (
        f'<p style="color:rgba(168,180,200,0.45);font-size:12px;margin:4px 0 0 0;'
        f'font-weight:400;letter-spacing:0.2px;line-height:1.4">{subtitle}</p>'
    ) if subtitle else ''
    st.markdown(
        f"""
        <div class="fade-up" style="
            border-left: 2px solid;
            border-image: linear-gradient(180deg,#00d4aa,#8b5cf6) 1;
            padding-left: 14px;
            margin: 26px 0 12px 0">
            <div style="
                font-size: 15px;
                font-weight: 700;
                letter-spacing: -0.2px;
                background: linear-gradient(120deg, #e2e8f0 0%, #94a3b8 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                display: inline-block">
                {icon_html}{title}
            </div>
            {subtitle_html}
        </div>
        """.strip(),
        unsafe_allow_html=True,
    )


# ── Reusable card wrapper ────────────────────────────────────────────────────

from contextlib import contextmanager as _contextmanager

@_contextmanager
def render_card(title: str = None, icon: str = None, accent: str = "#00d4aa",
                padding: str = "18px 20px", compact: bool = False):
    """
    Context manager that wraps Streamlit content in a glass-morphism card.

    Usage::

        with _ui.render_card("Market Snapshot", icon="🌐"):
            st.metric("BTC", "$65,000")
            st.metric("ETH", "$3,200")

    Args:
        title:   Optional card title (displayed in small caps above content).
        icon:    Optional emoji icon prepended to the title.
        accent:  Accent color for the left border stripe (hex or CSS var).
        padding: Inner padding CSS value.
        compact: If True, uses tighter padding.
    """
    pad = "12px 14px" if compact else padding
    header_html = ""
    if icon or title:
        label = f"{icon} {title}" if icon and title else (icon or title)
        header_html = (
            f'<div style="font-size:11px;font-weight:600;color:rgba(168,180,200,0.55);'
            f'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:10px">{label}</div>'
        )
    st.markdown(
        f'<div style="background:rgba(14,18,30,0.72);border:1px solid rgba(255,255,255,0.07);'
        f'border-left:3px solid {accent};border-radius:12px;padding:{pad};margin-bottom:12px">'
        f'{header_html}',
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        st.markdown("</div>", unsafe_allow_html=True)


# ── Signal direction pill ──────────────────────────────────────────────────────

_PILL_CFG = {
    "STRONG BUY":  ("#00d4aa", "#0d0e14", "0 0 12px rgba(0,212,170,0.5)"),
    "BUY":         ("#22c55e", "#0d0e14", "0 0 8px  rgba(0,192,118,0.35)"),
    "STRONG SELL": ("#ef4444", "#fff",    "0 0 12px rgba(246,70,93,0.5)"),
    "SELL":        ("#ef4444", "#fff",    "0 0 8px  rgba(192,57,43,0.35)"),
    "NEUTRAL":     ("#1e293b", "#64748b", "none"),
}

def signal_pill(direction: str) -> str:
    """Return an HTML colored pill badge for a signal direction."""
    # UI-06: guard against None direction to prevent TypeError in `key in direction`
    direction = direction or ""
    for key, (bg, fg, glow) in _PILL_CFG.items():
        if key in direction:
            return (
                f'<span style="background:{bg};color:{fg};'
                f'padding:4px 13px;border-radius:999px;'
                f'font-size:11px;font-weight:800;letter-spacing:0.5px;'
                f'display:inline-block;box-shadow:{glow};'
                f'text-transform:uppercase">{key}</span>'
            )
    return (
        f'<span style="background:#1e293b;color:#64748b;'
        f'padding:4px 13px;border-radius:999px;font-size:11px;'
        f'font-weight:700;display:inline-block">{direction}</span>'
    )


# ── Confidence badge ───────────────────────────────────────────────────────────

def conf_badge_html(conf: float) -> str:
    """Return an HTML confidence percentage badge with color tier."""
    if conf >= 75:
        color, bg = "#00d4aa", "rgba(0,212,170,0.1)"
    elif conf >= 60:
        color, bg = "#f59e0b", "rgba(245,158,11,0.1)"
    else:
        color, bg = "#ef4444", "rgba(246,70,93,0.1)"
    return (
        f'<span style="background:{bg};color:{color};'
        f'padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;'
        f'border:1px solid {color}38;display:inline-block;'
        f'font-family:\'JetBrains Mono\',monospace">{conf:.0f}%</span>'
    )


# ── Top market stat bar ────────────────────────────────────────────────────────

def market_stat_bar(stats: dict):
    """
    Render a top-of-page stat strip — glassmorphic with gradient border.
    stats: dict of label → value strings, e.g. {"BTC": "$98,400", "F&G": "72 Greed"}
    """
    _SEP = (
        '<div style="width:1px;height:28px;'
        'background:linear-gradient(180deg,transparent,rgba(255,255,255,0.1),transparent);'
        'flex-shrink:0"></div>'
    )
    _stat_items = []
    _stats_list = list(stats.items())
    for i, (k, v) in enumerate(_stats_list):
        sep = _SEP if i < len(_stats_list) - 1 else ""
        _stat_items.append(f"""
        <div style="display:flex;flex-direction:column;align-items:center;
                    padding:0 18px;flex-shrink:0;gap:3px">
            <span style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;
                         letter-spacing:1.1px;font-weight:600">{k}</span>
            <span style="font-size:14px;font-weight:700;color:#e2e8f0;
                         font-family:'JetBrains Mono',monospace;letter-spacing:-0.3px">{v}</span>
        </div>
        {sep}""")
    items_html = "".join(_stat_items)

    st.markdown(
        f"""
        <div class="fade-up" style="
            display: flex;
            align-items: center;
            background:
                linear-gradient(rgba(12,16,26,0.8),rgba(12,16,26,0.8)) padding-box,
                linear-gradient(90deg, rgba(0,212,170,0.3) 0%, rgba(99,102,241,0.2) 50%, rgba(0,212,170,0.1) 100%) border-box;
            border: 1px solid transparent;
            border-radius: 12px;
            padding: 12px 8px;
            margin-bottom: 20px;
            overflow-x: auto;
            backdrop-filter: blur(16px);
            box-shadow: 0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04)">
            {items_html.strip()}
        </div>
        """.strip(),
        unsafe_allow_html=True,
    )


# ── Per-pair signal card header ────────────────────────────────────────────────

def signal_card_header(pair: str, direction: str, conf: float, bias: str, regime: str, is_hc: bool = False):
    """
    Glass-style card header with gradient left accent + signal pill + HC badge.
    Shows plain English regime/bias labels for non-trader readability.
    """
    direction = direction or ""
    if "BUY" in direction:
        accent_gradient = "linear-gradient(180deg,#00d4aa,#10b981)"
        regime_color    = "rgba(0,212,170,0.12)"
    elif "SELL" in direction:
        accent_gradient = "linear-gradient(180deg,#ef4444,#ef4444)"
        regime_color    = "rgba(246,70,93,0.1)"
    else:
        accent_gradient = "linear-gradient(180deg,#f59e0b,#d97706)"
        regime_color    = "rgba(245,158,11,0.08)"

    hc_badge = (
        '<span style="background:rgba(0,212,170,0.12);color:#00d4aa;'
        'border:1px solid rgba(0,212,170,0.3);'
        'padding:2px 10px;border-radius:999px;font-size:10px;font-weight:700;'
        'letter-spacing:0.6px;margin-left:8px;'
        'box-shadow:0 0 8px rgba(0,212,170,0.15)">⚡ TOP PICK</span>'
        if is_hc else ""
    )

    # Plain English labels
    regime_display = REGIME_PLAIN.get(regime, regime or "—")
    bias_display   = BIAS_PLAIN.get(bias, bias or "—")

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;
                    margin-bottom:14px;padding-bottom:12px;
                    border-bottom:1px solid rgba(255,255,255,0.06)">
            <div style="width:3px;min-height:44px;
                        background:{accent_gradient};
                        border-radius:2px;flex-shrink:0;
                        box-shadow:0 0 8px rgba(0,212,170,0.3)"></div>
            <div style="flex:1;min-width:0">
                <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin-bottom:5px">
                    <span style="font-size:17px;font-weight:800;color:#e2e8f0;
                                font-family:'JetBrains Mono',monospace;
                                letter-spacing:-0.3px">{pair}</span>{hc_badge}
                </div>
                <div style="font-size:11px;color:rgba(168,180,200,0.55);
                            display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                    <span style="background:{regime_color};padding:2px 9px;border-radius:999px;
                                font-size:10px;font-weight:600;color:rgba(168,180,200,0.75)">{regime_display}</span>
                    <span style="opacity:0.4">·</span>
                    <span>{bias_display}</span>
                    <span style="opacity:0.4">·</span>
                    <span style="font-family:'JetBrains Mono',monospace">{conf:.0f}% signal strength</span>
                </div>
            </div>
            <div style="flex-shrink:0">{signal_pill(direction)}</div>
        </div>
        """.strip(),
        unsafe_allow_html=True,
    )


# ── Custom KPI card (pure HTML — bypasses st.metric for full style control) ────

def kpi_card_html(label: str, value: str, delta: str = None,
                  delta_positive: bool = None, icon: str = None,
                  accent: str = "#00d4aa") -> str:
    """
    Return HTML for a standalone glassmorphic KPI card.
    Render with st.markdown(..., unsafe_allow_html=True).
    """
    delta_color = "#22c55e" if delta_positive else ("#ef4444" if delta_positive is False else "#64748b")
    delta_html  = (
        f'<div style="font-size:11px;color:{delta_color};margin-top:4px;'
        f'font-family:\'JetBrains Mono\',monospace;font-weight:600">{delta}</div>'
    ) if delta else ""
    icon_html   = f'<div style="font-size:18px;margin-bottom:6px;opacity:0.75">{icon}</div>' if icon else ""
    return f"""
    <div style="
        background: linear-gradient(rgba(14,18,30,0.8),rgba(14,18,30,0.8)) padding-box,
                    linear-gradient(135deg,{accent}38,rgba(99,102,241,0.2),rgba(255,255,255,0.04)) border-box;
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 16px 18px;
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(16px);
        box-shadow: 0 4px 20px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.04)">
        <div style="position:absolute;top:0;left:0;right:0;height:2px;
                    background:linear-gradient(90deg,{accent},{accent}88,transparent);
                    border-radius:12px 12px 0 0"></div>
        {icon_html}
        <div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;
                    letter-spacing:1.1px;font-weight:600;margin-bottom:6px">{label}</div>
        <div style="font-size:22px;font-weight:700;color:#e2e8f0;
                    font-family:'JetBrains Mono',monospace;letter-spacing:-0.5px">{value}</div>
        {delta_html}
    </div>"""


# ── Gradient divider ───────────────────────────────────────────────────────────

def gradient_divider(margin: str = "18px 0"):
    """Render a decorative fade-out divider line."""
    st.markdown(
        f'<div style="height:1px;background:linear-gradient(90deg,'
        f'transparent,rgba(0,212,170,0.25) 30%,rgba(99,102,241,0.2) 70%,'
        f'transparent);margin:{margin}"></div>',
        unsafe_allow_html=True,
    )


# ── Badge row ─────────────────────────────────────────────────────────────────

def badge_row_html(badges: list[tuple]) -> str:
    """
    Return HTML for a row of small badge chips.
    badges: list of (label, value, color_hex) tuples.
    """
    _chips = []
    for label, value, color in badges:
        _chips.append(f"""
        <div style="display:flex;flex-direction:column;align-items:center;gap:1px;
                    background:rgba(255,255,255,0.035);border:1px solid rgba(255,255,255,0.07);
                    border-radius:8px;padding:5px 12px;flex-shrink:0">
            <span style="font-size:9px;color:rgba(168,180,200,0.42);text-transform:uppercase;
                         letter-spacing:0.9px;font-weight:600">{label}</span>
            <span style="font-size:13px;font-weight:700;color:{color};
                         font-family:'JetBrains Mono',monospace">{value}</span>
        </div>""")
    return f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:6px 0">{"".join(_chips)}</div>'


# ── Live dot HTML ─────────────────────────────────────────────────────────────

def live_dot_html() -> str:
    """Return HTML for a pulsing green live indicator dot."""
    return '<span class="live-dot"></span>'


# ── Sidebar branding header ───────────────────────────────────────────────────

def sidebar_header(version: str, exchange: str, n_pairs: int):
    """Render a premium gradient branding header in the sidebar.

    Uses BRAND_NAME / BRAND_LOGO_PATH from config when set.
    When unset, shows the clean default 'CryptoSignal' placeholder.
    """
    try:
        from config import BRAND_NAME, BRAND_LOGO_PATH
        from pathlib import Path as _Path
    except ImportError:
        BRAND_NAME, BRAND_LOGO_PATH = "", ""
        _Path = None

    # If a logo image is set and exists, render it instead of the text wordmark
    if BRAND_LOGO_PATH and _Path and _Path(BRAND_LOGO_PATH).exists():
        st.sidebar.image(BRAND_LOGO_PATH, width=120)
    else:
        _wordmark = BRAND_NAME if BRAND_NAME else "⬡ Family Office · Signal Intelligence"
        st.sidebar.markdown(
            f"""
            <div style="
                text-align: center;
                padding: 22px 10px 16px 10px;
                border-bottom: 1px solid rgba(255,255,255,0.06);
                margin-bottom: 10px;
                position: relative">
                <!-- glow blob behind logo -->
                <div style="
                    position: absolute;
                    top: 10px; left: 50%;
                    transform: translateX(-50%);
                    width: 120px; height: 60px;
                    background: radial-gradient(ellipse, rgba(0,212,170,0.18) 0%, transparent 70%);
                    pointer-events: none"></div>
                <!-- wordmark -->
                <div style="
                    font-size: 21px;
                    font-weight: 800;
                    background: linear-gradient(135deg, #00d4aa 0%, #a78bfa 100%);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                    letter-spacing: -0.5px;
                    line-height: 1.1;
                    position: relative">
                    {_wordmark}
                </div>
                <!-- version + model tag -->
                <div style="
                    font-size: 9px;
                    color: rgba(168,180,200,0.35);
                    letter-spacing: 1.3px;
                    text-transform: uppercase;
                    margin-top: 5px">
                    v{version} &nbsp;·&nbsp; AI Ensemble
                </div>
                <!-- exchange + pairs chips -->
                <div style="display:flex;justify-content:center;gap:8px;margin-top:12px">
                    <div style="
                        background: linear-gradient(rgba(0,212,170,0.12),rgba(0,212,170,0.12)) padding-box,
                                    linear-gradient(135deg,rgba(0,212,170,0.5),rgba(99,102,241,0.3)) border-box;
                        border: 1px solid transparent;
                        border-radius: 999px;
                        padding: 3px 12px;
                        font-size: 11px;
                        color: #00d4aa;
                        font-weight: 700;
                        letter-spacing: 0.3px">
                        {exchange.upper()}
                    </div>
                    <div style="
                        background: rgba(255,255,255,0.04);
                        border: 1px solid rgba(255,255,255,0.1);
                        border-radius: 999px;
                        padding: 3px 12px;
                        font-size: 11px;
                        color: rgba(168,180,200,0.55);
                        font-weight: 500">
                        {n_pairs} pairs
                    </div>
                </div>
            </div>
            """.strip(),
            unsafe_allow_html=True,
        )


# ── Plain English helpers for non-traders ─────────────────────────────────────

# Maps internal regime codes → plain English labels shown in the UI
REGIME_PLAIN = {
    "TrendFollow":    "Trending Market",
    "MeanReversion":  "Ranging / Sideways",
    "Breakout":       "Breakout Setup",
    "Volatile":       "High Volatility",
    "Trending":       "Trending Market",
    "Ranging":        "Ranging / Sideways",
    "Neutral":        "Mixed / Unclear",
}

# Maps strategy bias codes → plain English labels
BIAS_PLAIN = {
    "TrendFollow":   "Riding the Trend",
    "MeanReversion": "Range Trade",
    "Breakout":      "Breakout Play",
    "Scalp":         "Short-term Scalp",
    "Swing":         "Swing Trade",
    "StatArb":       "Pair Trade",
}


def regime_label(regime: str) -> str:
    """Return plain English regime label."""
    return REGIME_PLAIN.get(regime, regime or "—")


def bias_label(bias: str) -> str:
    """Return plain English strategy bias label."""
    return BIAS_PLAIN.get(bias, bias or "—")


def signal_plain_english(
    pair: str,
    direction: str,
    conf: float,
    mtf: float,
    regime: str = "",
    entry: float = None,
    stop: float = None,
    exit_: float = None,
) -> str:
    """
    Return a beginner-friendly 2–3 sentence plain English signal summary.
    Safe for use directly inside st.markdown (no HTML — plain text).
    """
    base = pair.split("/")[0]

    # Confidence descriptor
    if conf >= 75:
        conf_desc = "strong"
    elif conf >= 60:
        conf_desc = "moderate"
    elif conf >= 45:
        conf_desc = "weak"
    else:
        conf_desc = "very weak"

    # Agreement descriptor
    if mtf >= 80:
        agree_desc = "all timeframes agree"
    elif mtf >= 60:
        agree_desc = "most timeframes agree"
    elif mtf >= 40:
        agree_desc = "some timeframes agree"
    else:
        agree_desc = "timeframes are mixed"

    # Direction line
    d = (direction or "").upper()
    if "STRONG BUY" in d:
        line1 = f"{base} is showing a strong potential buy opportunity right now."
    elif "BUY" in d:
        line1 = f"{base} is leaning bullish — a modest buy opportunity worth watching."
    elif "STRONG SELL" in d:
        line1 = f"{base} is showing a strong sell / exit signal — caution on new buys."
    elif "SELL" in d:
        line1 = f"{base} is leaning bearish — consider reducing exposure or avoiding new buys."
    else:
        line1 = f"{base} has no clear signal right now. Best to wait and watch for a cleaner setup."

    line2 = (
        f"Model confidence is {conf_desc} at {conf:.0f}%, and {agree_desc} "
        f"({mtf:.0f}% timeframe agreement)."
    )

    # Trade detail line
    line3 = ""
    if entry and stop and exit_ and "NEUTRAL" not in d:
        risk_pct   = abs(entry - stop) / entry * 100 if entry > 0 else 0
        reward_pct = abs(exit_ - entry) / entry * 100 if entry > 0 else 0
        rr = reward_pct / risk_pct if risk_pct > 0 else 0
        line3 = (
            f"Entry ~${entry:,.5g}  ·  Stop ${stop:,.5g} (risk {risk_pct:.1f}%)  ·  "
            f"Target ${exit_:,.5g} (gain {reward_pct:.1f}%)  ·  Risk/Reward {rr:.1f}×."
        )

    parts = [line1, line2]
    if line3:
        parts.append(line3)
    return "  ".join(parts)


def plain_english_box(text: str, direction: str) -> None:
    """
    Render a styled plain-English summary box inside a pair card.
    direction determines the accent color (buy=teal, sell=red, neutral=amber).
    """
    d = (direction or "").upper()
    if "BUY" in d:
        accent = "#00d4aa"
        bg     = "rgba(0,212,170,0.05)"
    elif "SELL" in d:
        accent = "#ef4444"
        bg     = "rgba(246,70,93,0.05)"
    else:
        accent = "#f59e0b"
        bg     = "rgba(245,158,11,0.05)"
    st.markdown(
        f'<div style="background:{bg};border-left:3px solid {accent};'
        f'border-radius:0 8px 8px 0;padding:10px 14px;margin:0 0 14px 0;">'
        f'<span style="font-size:13px;color:#cbd5e1;line-height:1.65;'
        f'font-family:Inter,sans-serif">{text}</span></div>',
        unsafe_allow_html=True,
    )


# ── TF Breakdown column guide ─────────────────────────────────────────────────

TF_COLUMN_GUIDE_MD = """
| Column | What It Is | What It Means |
|--------|-----------|----------------|
| **Conf** | Signal Strength | 0–100% — how confident the model is for this timeframe |
| **Dir** | Signal Direction | Strong Buy / Buy / Neutral / Sell / Strong Sell |
| **RSI** | Momentum Score | Above 70 = overbought (may drop soon) · Below 30 = oversold (may bounce) |
| **ADX** | Trend Strength | Above 25 = price is in a strong trend · Below 20 = price is choppy |
| **Stoch** | Short-Term Momentum | Above 80 = stretched to the upside · Below 20 = stretched to the downside |
| **SuperTrend** | Trend Direction | BULL = riding an uptrend · BEAR = in a downtrend |
| **Ichimoku** | Cloud Analysis | BULL = above the cloud (strong) · BEAR = below · NEUTRAL = inside (unclear) |
| **Fib** | Key Price Level | Nearest Fibonacci retracement — acts as natural support or resistance |
| **MACD Div** | Momentum Divergence | BULL = price falling but momentum rising (reversal signal) · BEAR = opposite |
| **S/R** | Price Level | Near a key support/resistance, breaking out, or in open space |
| **Patterns** | Candle Patterns | Visual patterns: Hammer (potential reversal up), Doji (indecision), Engulfing |
| **Funding** | Perp Funding | Positive = longs paying (bearish lean) · Negative = shorts paying (bullish lean) |
| **OI** | Open Interest | HIGH = more contracts open than usual (big move possible) · LOW = quiet market |
| **On-Chain** | Blockchain Data | On-chain proxies: holder behavior, net flows, whale activity (CoinGecko) |
| **Options IV** | Options Volatility | EXTREME_FEAR = big move expected · NORMAL = calm · COMPLACENCY = overconfident |
| **OB Depth** | Order Book Pressure | BUY_PRESSURE = more buyers stacked · SELL_PRESSURE = more sellers stacked |
| **TVL** | DeFi Activity | How much money is locked in DeFi — GROWING = healthy · DECLINING = concern |
| **Regime** | Market Mode | Trending = strong directional move · Ranging = bouncing sideways · Breakout |
| **Strategy** | Recommended Style | The trading approach that fits the current market conditions |
| **StatArb** | Pair Trade Signal | Whether this coin is cheap/expensive vs Bitcoin — statistical edge |
| **Agent Vote** | AI Consensus | % of individual AI models (RSI, MACD, ADX, etc.) agreeing on direction |
"""


def tf_column_guide_popover():
    """Render a popover button with the full TF breakdown column guide."""
    with st.popover("ℹ Column Guide — 21 indicators explained"):
        st.markdown("#### Timeframe Breakdown — Column Reference")
        st.markdown(TF_COLUMN_GUIDE_MD)


# ── Help text constants (plain English — designed for beginners) ───────────────

# Dashboard summary metrics
HELP_PAIRS_SCANNED   = "How many cryptocurrencies were analyzed in this scan."
HELP_HIGH_CONF       = "The model's highest-confidence signals — the best opportunities it found. Think of these as the model's top picks. Expand them below to see details."
HELP_AVG_CONF        = "Average signal strength across all coins scanned. 100% = model is very sure, 50% = some evidence, below 40% = unclear. A healthy scan shows 50–70%."
HELP_BUY_SIGNALS     = "How many coins the model thinks could move higher. These show a bullish (upward) signal."
HELP_SELL_SIGNALS    = "How many coins the model thinks could move lower. These show a bearish (downward) signal — could be good to sell or avoid buying."

# Per-pair card metrics
HELP_MTF_ALIGN       = "Timeframe Agreement — how many different time periods (15 min, 1 hr, 4 hr, daily, weekly) all show the same signal direction. 100% = all 5 agree. Higher = stronger, more reliable signal."
HELP_ENTRY           = "Suggested price to enter the trade. Based on recent support and resistance levels. Treat this as a price zone, not an exact number — try to get close."
HELP_EXIT_TARGET     = "Where to take your profits. This is the model's price target based on the next key resistance (for buys) or support (for sells). Always plan your exit before you enter."
HELP_STOP_LOSS       = "The price where you should cut your loss to protect your money. If price hits this level, exit the trade. Never risk more than you can afford to lose."
HELP_POSITION_SIZE   = "How much of your total funds the model suggests allocating to this trade, based on the model's historical win rate. Smaller % = lower risk."
HELP_RISK_MODE       = "NORMAL = trade at the full suggested size. REDUCED = the model recommends caution — use a smaller position than usual due to high correlation with Bitcoin or market conditions."

# Config Editor
HELP_HIGH_CONF_THRESH = "How confident the model must be to flag a signal as a 'Top Pick'. Higher number = fewer signals but higher quality. Lower = more signals but more noise. Start at 70–80%."
HELP_MTF_THRESH       = "How many timeframes must agree before showing a confirmed signal. Higher = stricter, fewer but stronger signals."
HELP_CORR_THRESH      = "If a coin moves too closely with Bitcoin (above this level), the model shrinks the suggested trade size to avoid putting too many eggs in one basket."
HELP_CORR_LB          = "How many days of price history to use when checking how closely a coin follows Bitcoin."
HELP_HOLD_DAYS        = "In the backtest simulation, how many days each trade is held before being automatically closed. Affects how the model's past performance is calculated."
HELP_PORTFOLIO_SIZE   = "The total amount of money you're trading with. Used to calculate exact dollar amounts for each position."
HELP_RISK_PER_TRADE   = "The most you're willing to lose on a single trade, as % of your total funds. Keep this low — 1–2% is standard practice to protect your account."
HELP_MAX_EXPOSURE     = "Maximum % of your total funds that can be in open trades at the same time. This limits your total risk exposure."
HELP_MAX_POS_CAP      = "The biggest single trade allowed, as % of your total funds. Acts as a hard ceiling regardless of other settings."
HELP_MAX_PER_PAIR     = "How many simultaneous open trades you can have on the same coin at the same time."

# Backtest metrics
HELP_TOTAL_TRADES     = "How many simulated trades the model would have made during the tested time period."
HELP_WIN_RATE         = "What percentage of those trades would have been profitable. Above 50% means more wins than losses — a good sign."
HELP_AVG_PNL          = "The average profit or loss per trade, after exchange fees and price slippage. Positive is good."
HELP_PROFIT_FACTOR    = "Total profits divided by total losses. Above 1.0 = strategy is profitable. 2.0 = you made twice as much as you lost. Higher is better."
HELP_SHARPE           = "Performance score that accounts for risk — higher is better. Above 1.0 is acceptable, above 2.0 is very good. Tells you if you're being paid fairly for the risk you're taking."
HELP_MAX_DRAWDOWN     = "The biggest drop from a peak to a low point during the test — the worst losing streak. Lower is better. This is what you'd feel during a bad stretch."
HELP_SORTINO          = "Similar to the performance score above, but only counts losing periods as 'risky'. Better suited for assets with asymmetric returns. Higher is better."
HELP_CALMAR           = "How well the strategy bounced back from its worst period of losses. Higher = recovered faster. Below 1.0 means drawdowns were bigger than total returns."
HELP_EXPECTANCY       = "On average, how much do you make per trade? Positive means the strategy has a real edge over time. This is the most important single number."

# Market Overview
HELP_COMPOSITE_SCORE  = "Overall market mood score. Positive = more coins are bullish, Negative = more are bearish. Range −100 to +100. Above +20 = broadly bullish market, below −20 = broadly bearish."
HELP_MTF_HEATMAP      = "Color grid showing each coin's signal across different timeframes. Green = buy signal, Red = sell signal, Grey = no clear signal. Darker colors = stronger signals."
HELP_FNG              = "The Crypto Fear & Greed Index — measures overall market emotion (0 = Extreme Fear, 100 = Extreme Greed). Historically, extreme fear can signal buying opportunities and extreme greed can signal tops."


# ═══════════════════════════════════════════════════════════════════════════════
#  BEGINNER-FRIENDLY UI COMPONENTS
#  Designed for rookie financial advisors and first-time retail investors.
#  Core philosophy: plain English, visual cues, progressive disclosure.
# ═══════════════════════════════════════════════════════════════════════════════

# ── Fear & Greed visual gauge ─────────────────────────────────────────────────

def fng_gauge_html(fng_value: int, fng_category: str) -> str:
    """
    Return HTML for a visual Fear & Greed gauge bar with emoji + label.
    fng_value: 0–100. Categories: Extreme Fear / Fear / Neutral / Greed / Extreme Greed.
    """
    pct = max(0, min(100, float(fng_value or 50)))

    # Emoji that matches the mood
    if pct <= 20:
        emoji, mood_color, advice = "😱", "#ef4444", "Markets are very fearful — historically a buying opportunity, but use caution."
    elif pct <= 40:
        emoji, mood_color, advice = "😟", "#f59e0b", "Markets are fearful — some may see this as a buying opportunity."
    elif pct <= 60:
        emoji, mood_color, advice = "😐", "#64748b", "Markets are neutral — no strong emotion either way. Wait for a clearer signal."
    elif pct <= 80:
        emoji, mood_color, advice = "🤩", "#00d4aa", "Markets are greedy — prices may be elevated. Be careful chasing gains."
    else:
        emoji, mood_color, advice = "🤑", "#ef4444", "Extreme Greed — the market may be overheated. Historically a warning sign."

    # Track fill color gradient
    bar_gradient = f"linear-gradient(90deg, #ef4444 0%, #f59e0b 25%, #64748b 50%, #22c55e 75%, #00d4aa 100%)"
    marker_left  = pct  # 0–100%

    return f"""
    <div style="background:rgba(14,18,30,0.7);border:1px solid rgba(255,255,255,0.08);
                border-radius:12px;padding:14px 16px;margin-bottom:12px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <span style="font-size:26px;line-height:1">{emoji}</span>
            <div>
                <div style="font-size:11px;color:rgba(168,180,200,0.5);text-transform:uppercase;
                            letter-spacing:0.9px;font-weight:600">Market Mood (Fear &amp; Greed)</div>
                <div style="font-size:18px;font-weight:800;color:{mood_color};
                            letter-spacing:-0.3px">{fng_value} — {fng_category}</div>
            </div>
        </div>
        <!-- Track bar -->
        <div style="position:relative;height:8px;border-radius:4px;
                    background:{bar_gradient};margin:6px 0 4px 0;overflow:visible">
            <!-- Marker dot -->
            <div style="position:absolute;top:50%;left:{marker_left}%;
                        transform:translate(-50%,-50%);width:14px;height:14px;
                        border-radius:50%;background:#fff;
                        box-shadow:0 0 6px rgba(0,0,0,0.6);z-index:2"></div>
        </div>
        <!-- Scale labels -->
        <div style="display:flex;justify-content:space-between;
                    font-size:9px;color:rgba(168,180,200,0.35);margin-top:6px">
            <span>😱 Extreme Fear</span><span>😐 Neutral</span><span>🤑 Extreme Greed</span>
        </div>
        <div style="margin-top:8px;font-size:11px;color:rgba(168,180,200,0.55);
                    border-top:1px solid rgba(255,255,255,0.05);padding-top:8px">
            💡 {advice}
        </div>
    </div>"""


# ── Signal strength visual (5-dot meter) ─────────────────────────────────────

def signal_strength_stars(conf: float) -> str:
    """
    Return HTML for a 5-dot visual confidence meter.
    conf: 0–100. Maps to 0–5 filled dots.
    Used as a plain-English alternative to a raw percentage.
    """
    filled = round(conf / 20)       # 0–5 dots
    filled = max(0, min(5, filled))

    if conf >= 75:
        label, dot_color = "Very Strong", "#00d4aa"
    elif conf >= 60:
        label, dot_color = "Strong", "#22c55e"
    elif conf >= 45:
        label, dot_color = "Moderate", "#f59e0b"
    elif conf >= 30:
        label, dot_color = "Weak", "#ef4444"
    else:
        label, dot_color = "Very Weak", "#ef4444"

    dots = ""
    for i in range(5):
        color = dot_color if i < filled else "rgba(255,255,255,0.1)"
        dots += f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:3px"></span>'

    return (
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'{dots}'
        f'<span style="font-size:11px;color:{dot_color};font-weight:700">{label} ({conf:.0f}%)</span>'
        f'</div>'
    )


# ── Risk level badge ──────────────────────────────────────────────────────────

def risk_level_badge_html(conf: float, pos_pct: float = None) -> str:
    """
    Return HTML for a color-coded risk level chip.
    Risk is LOW when confidence is high and position size is small.
    """
    # Determine risk: low conf or large position = higher risk
    size = pos_pct if pos_pct else 10.0
    if conf >= 70 and size <= 15:
        label, bg, border, tc = "LOW RISK", "rgba(0,212,170,0.12)", "rgba(0,212,170,0.35)", "#00d4aa"
    elif conf >= 55 and size <= 25:
        label, bg, border, tc = "MODERATE RISK", "rgba(245,158,11,0.12)", "rgba(245,158,11,0.35)", "#f59e0b"
    else:
        label, bg, border, tc = "HIGHER RISK", "rgba(246,70,93,0.12)", "rgba(246,70,93,0.35)", "#ef4444"

    return (
        f'<span style="display:inline-block;background:{bg};border:1px solid {border};'
        f'color:{tc};border-radius:999px;padding:2px 10px;font-size:10px;'
        f'font-weight:700;letter-spacing:0.5px">{label}</span>'
    )


# ── Welcome / getting started banner (shown when no scan has been run) ─────────

def beginner_welcome_html() -> str:
    """Return HTML for a welcome card shown before the first scan."""
    return """
    <div style="background:linear-gradient(rgba(14,18,30,0.85),rgba(14,18,30,0.85)) padding-box,
                linear-gradient(135deg,rgba(0,212,170,0.25),rgba(99,102,241,0.18)) border-box;
                border:1px solid transparent;border-radius:16px;
                padding:28px 32px;margin:8px 0 24px 0;
                box-shadow:0 4px 32px rgba(0,0,0,0.4)">
        <div style="font-size:28px;margin-bottom:10px">👋</div>
        <div style="font-size:20px;font-weight:800;color:#e2e8f0;margin-bottom:6px">
            Welcome to Family Office · Signal Intelligence
        </div>
        <div style="font-size:13px;color:rgba(168,180,200,0.75);line-height:1.7;margin-bottom:18px">
            This tool scans cryptocurrency markets and tells you which coins may be worth buying,
            selling, or avoiding — in plain English, no trading experience needed.
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:18px">
            <div style="background:rgba(0,212,170,0.07);border:1px solid rgba(0,212,170,0.15);
                        border-radius:10px;padding:14px 16px">
                <div style="font-size:20px;margin-bottom:6px">1️⃣</div>
                <div style="font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:4px">Run the Scan</div>
                <div style="font-size:11px;color:rgba(168,180,200,0.6)">
                    Click <strong style="color:#00d4aa">▶ Analyze Market Now</strong> above.
                    The model will fetch live market data for all coins (~1–3 min).
                </div>
            </div>
            <div style="background:rgba(99,102,241,0.07);border:1px solid rgba(99,102,241,0.15);
                        border-radius:10px;padding:14px 16px">
                <div style="font-size:20px;margin-bottom:6px">2️⃣</div>
                <div style="font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:4px">Read the Results</div>
                <div style="font-size:11px;color:rgba(168,180,200,0.6)">
                    Each coin gets a <strong style="color:#e2e8f0">BUY / SELL / HOLD</strong> signal
                    with a plain-English explanation. Look for ⚡ Top Picks.
                </div>
            </div>
            <div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.15);
                        border-radius:10px;padding:14px 16px">
                <div style="font-size:20px;margin-bottom:6px">3️⃣</div>
                <div style="font-size:12px;font-weight:700;color:#e2e8f0;margin-bottom:4px">Do Your Research</div>
                <div style="font-size:11px;color:rgba(168,180,200,0.6)">
                    This model is a research tool — <strong style="color:#f59e0b">not financial advice.</strong>
                    Always do your own due diligence before trading.
                </div>
            </div>
        </div>
        <div style="background:rgba(246,70,93,0.07);border:1px solid rgba(246,70,93,0.18);
                    border-radius:10px;padding:10px 14px;font-size:11px;color:rgba(168,180,200,0.65)">
            ⚠️ <strong style="color:#f59e0b">Risk Warning:</strong>
            Cryptocurrency trading carries a <strong>high level of risk</strong> and may not be
            suitable for all investors. Only invest money you can afford to lose.
            Past model performance does not guarantee future results.
        </div>
    </div>"""


# ── Scan action summary CTA (best opportunity card) ───────────────────────────

def scan_action_cta(pair: str, direction: str, conf: float,
                    entry: float = None, stop: float = None, exit_: float = None) -> None:
    """
    Render a prominent 'Today's Best Opportunity' action card after scan completes.
    Shown only when there is a high-confidence signal. Designed for beginners.
    """
    d = (direction or "").upper()
    if "BUY" in d:
        action_verb = "Consider Buying"
        accent      = "#00d4aa"
        bg          = "rgba(0,212,170,0.07)"
        border      = "rgba(0,212,170,0.25)"
        arrow       = "▲"
    elif "SELL" in d:
        action_verb = "Consider Reducing / Selling"
        accent      = "#ef4444"
        bg          = "rgba(246,70,93,0.07)"
        border      = "rgba(246,70,93,0.25)"
        arrow       = "▼"
    else:
        return  # No CTA for neutral

    base    = pair.split("/")[0]
    rr_str  = ""
    if entry and stop and exit_:
        risk   = abs(entry - stop) / entry * 100 if entry > 0 else 0
        reward = abs(exit_ - entry) / entry * 100 if entry > 0 else 0
        rr     = reward / risk if risk > 0 else 0
        rr_str = f" · Risk/Reward {rr:.1f}×"

    st.markdown(
        f"""
        <div style="background:{bg};border:1px solid {border};border-radius:14px;
                    padding:18px 22px;margin:12px 0 16px 0">
            <div style="font-size:10px;color:rgba(168,180,200,0.45);text-transform:uppercase;
                        letter-spacing:1.1px;font-weight:600;margin-bottom:6px">
                ⚡ Today's Best Opportunity
            </div>
            <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
                <span style="font-size:22px;font-weight:800;color:#e2e8f0;
                             font-family:'JetBrains Mono',monospace">{base}</span>
                <span style="background:{accent};color:#0d0e14;border-radius:999px;
                             padding:4px 14px;font-size:13px;font-weight:800;
                             letter-spacing:0.3px">{arrow} {direction}</span>
                <span style="font-size:13px;color:rgba(168,180,200,0.7)">
                    {conf:.0f}% confidence{rr_str}
                </span>
            </div>
            <div style="margin-top:8px;font-size:12px;color:rgba(168,180,200,0.6)">
                Suggested action: <strong style="color:{accent}">{action_verb} {base}</strong>
                {"· Entry ~$" + f"{entry:,.4g}" if entry else ""}
                {"· Stop $" + f"{stop:,.4g}" if stop else ""}
                {"· Target $" + f"{exit_:,.4g}" if exit_ else ""}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Risk disclaimer (shown before execute buttons) ────────────────────────────

def risk_disclaimer_banner() -> None:
    """Render a compact risk warning above the execute buttons."""
    st.markdown(
        '<div style="background:rgba(246,70,93,0.06);border:1px solid rgba(246,70,93,0.2);'
        'border-radius:10px;padding:10px 14px;margin:4px 0 10px 0;font-size:11px;'
        'color:rgba(200,160,160,0.85)">'
        '⚠️ <strong>Risk Warning</strong> — Placing orders involves real financial risk. '
        'Paper mode simulates trades with no real money. '
        'In Live mode, real funds are used. Never invest more than you can afford to lose. '
        'This is not financial advice.</div>',
        unsafe_allow_html=True,
    )


# ── Crypto glossary popover ───────────────────────────────────────────────────

_GLOSSARY_MD = """
| Term | Plain English |
|------|--------------|
| **BUY / BULLISH** | The model thinks the price may go UP. |
| **SELL / BEARISH** | The model thinks the price may go DOWN. |
| **NEUTRAL / HOLD** | No clear signal. Best to wait and do nothing. |
| **Signal Strength** | How confident the model is (0–100%). 70%+ = strong. |
| **Top Pick (⚡)** | The model's highest-confidence opportunity this scan. |
| **Entry Price** | The suggested price to start your trade. |
| **Stop Loss** | The price where you exit if you're wrong — limits your loss. |
| **Take Profit** | The price where you take your gains. |
| **Risk/Reward** | For every $1 you risk, how much could you gain. 2× = gain $2 per $1 risk. |
| **Timeframe** | The time period of each candle: 15m, 1h, 4h, 1d, 1w. |
| **MTF Alignment** | How many timeframes agree on the same direction. More = stronger. |
| **RSI** | Momentum indicator: above 70 = may be overheated, below 30 = may be oversold. |
| **ADX** | Trend strength: above 25 = strong trend, below 20 = choppy/sideways. |
| **MACD** | Moving average indicator — tracks trend momentum. |
| **SuperTrend** | BULL = uptrend, BEAR = downtrend (simple trend tracker). |
| **Bollinger Bands** | Measures how stretched price is. Near upper = extended up, lower = extended down. |
| **Ichimoku Cloud** | Above cloud = bullish, below cloud = bearish. |
| **Fear & Greed** | 0 = Extreme Fear (market panicking), 100 = Extreme Greed (market euphoric). |
| **Open Interest** | Total number of open futures contracts. HIGH = big move possible. |
| **Funding Rate** | Cost of holding a futures position. Positive = longs paying. |
| **On-Chain** | Data from the actual blockchain (wallets, transactions, flows). |
| **TVL** | Total Value Locked in DeFi — higher = more activity and confidence in the protocol. |
| **Options IV** | Implied Volatility — how big a price move the options market expects. |
| **Kelly Criterion** | A math formula for how much of your account to risk per trade. |
| **Sharpe Ratio** | Performance vs risk score. Above 1.0 = good, above 2.0 = very good. |
| **Drawdown** | The biggest drop from a high point. The worst losing streak in the backtest. |
| **Paper Trade** | A simulated trade using fake money — safe for learning and testing. |
| **Circuit Breaker** | Auto-protection: if losses exceed a threshold, all new signals are suppressed. |
"""


def glossary_popover(user_level: str = "beginner") -> None:
    """Render a sidebar-friendly 'Crypto Glossary' popover button.

    Explanation depth scales with user_level: beginner / intermediate / advanced.
    """
    try:
        from glossary import glossary_popover as _gp
        _gp(user_level)
    except ImportError:
        # Fallback: legacy flat glossary (single depth)
        label_depth = {"beginner": "Plain English", "intermediate": "Key Metrics", "advanced": "Technical Detail"}
        depth_name = label_depth.get(user_level, "Plain English")
        with st.popover(f"📖 Crypto Glossary ({depth_name})"):
            st.markdown("### Crypto & Trading Terms")
            st.markdown(_GLOSSARY_MD)
            st.caption("Tip: hover over any metric card in the app for a tooltip explanation.")


# ─── Top Movers Card ────────────────────────────────────────────────────────────

def top_movers_card_html(gainers: list, losers: list) -> str:
    """
    Render a bento-style Top Movers card showing top 3 gainers and losers.

    Parameters
    ----------
    gainers : list of dicts with keys: symbol, name, price_change_24h_pct, current_price
    losers  : list of dicts (same structure, negative price_change_24h_pct)

    Returns HTML string for use with st.markdown(..., unsafe_allow_html=True).
    """
    def _row(coin: dict, is_gainer: bool) -> str:
        sym    = coin.get("symbol", "?").upper()
        pct    = coin.get("price_change_24h_pct", 0.0) or 0.0
        price  = coin.get("current_price", 0.0) or 0.0
        arrow  = "▲" if is_gainer else "▼"
        color  = "#22c55e" if is_gainer else "#ef4444"
        sign   = "+" if pct >= 0 else ""
        price_fmt = f"${price:,.4f}" if price < 1 else f"${price:,.2f}"
        return (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
            f'<span style="font-weight:600;color:#e2e8f0;font-size:0.88rem;">{sym}</span>'
            f'<span style="color:#94a3b8;font-size:0.85rem;">{price_fmt}</span>'
            f'<span style="color:{color};font-weight:700;font-size:0.88rem;">'
            f'{arrow} {sign}{pct:.2f}%</span>'
            f'</div>'
        )

    gainer_rows = "".join(_row(c, True)  for c in gainers[:3]) if gainers else '<div style="color:#64748b;font-size:0.85rem;padding:8px 0;">No data</div>'
    loser_rows  = "".join(_row(c, False) for c in losers[:3])  if losers  else '<div style="color:#64748b;font-size:0.85rem;padding:8px 0;">No data</div>'

    return f"""
<div style="
    background:rgba(15,23,42,0.7);
    border:1px solid rgba(255,255,255,0.08);
    border-radius:16px;
    padding:16px 18px;
    backdrop-filter:blur(12px);
    -webkit-backdrop-filter:blur(12px);
    box-shadow:0 4px 24px rgba(0,0,0,0.3);
    margin-bottom:12px;
">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
    <span style="font-size:1.1rem;">🔥</span>
    <span style="font-weight:700;color:#e2e8f0;font-size:0.95rem;letter-spacing:0.02em;">Top Movers — 24h</span>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
    <div>
      <div style="color:#22c55e;font-size:0.75rem;font-weight:600;letter-spacing:0.08em;
                  text-transform:uppercase;margin-bottom:6px;">▲ Gainers</div>
      {gainer_rows}
    </div>
    <div>
      <div style="color:#ef4444;font-size:0.75rem;font-weight:600;letter-spacing:0.08em;
                  text-transform:uppercase;margin-bottom:6px;">▼ Losers</div>
      {loser_rows}
    </div>
  </div>
</div>
"""


# ─── Liquidation Cascade Risk Card ─────────────────────────────────────────────

def cascade_risk_card_html(score: float, risk_level: str, direction: str,
                           components: dict | None = None) -> str:
    """
    Render a liquidation cascade risk gauge card.

    Parameters
    ----------
    score      : 0-100 composite risk score
    risk_level : 'LOW' | 'MODERATE' | 'HIGH' | 'EXTREME'
    direction  : 'LONG_CASCADE' | 'SHORT_CASCADE' | 'NEUTRAL'
    components : optional dict with sub-scores (funding, oi, orderbook, iv)

    Returns HTML string.
    """
    _LEVEL_COLORS = {
        "LOW":      ("#22c55e", "#1e293b"),
        "MODERATE": ("#f59e0b", "#1e293b"),
        "HIGH":     ("#f59e0b", "#1e293b"),
        "EXTREME":  ("#ef4444", "#1e293b"),
    }
    _LEVEL_ICONS = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "EXTREME": "🔴"}
    _DIR_LABELS = {
        "LONG_CASCADE":  "⚡ Long Squeeze Risk",
        "SHORT_CASCADE": "⚡ Short Squeeze Risk",
        "NEUTRAL":       "⚖ Balanced",
    }

    color, bg = _LEVEL_COLORS.get(risk_level, ("#94a3b8", "#1e293b"))
    icon  = _LEVEL_ICONS.get(risk_level, "⚪")
    label = _DIR_LABELS.get(direction, direction)

    # Progress bar fill (score 0-100)
    bar_pct = min(max(float(score), 0), 100)

    comp_html = ""
    if components:
        rows = []
        _comp_labels = {
            "funding_score": "Funding Rate",
            "oi_score":      "Open Interest",
            "ob_score":      "Book Imbalance",
            "iv_score":      "Options IV",
        }
        for k, lbl in _comp_labels.items():
            val = components.get(k, 0) or 0
            rows.append(
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:0.85rem;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
                f'<span style="color:#94a3b8;">{lbl}</span>'
                f'<span style="color:{color};font-weight:600;">{val:.0f}</span>'
                f'</div>'
            )
        comp_html = (
            '<div style="margin-top:10px;">'
            + "".join(rows)
            + "</div>"
        )

    return f"""
<div style="
    background:rgba(15,23,42,0.7);
    border:1px solid {color}33;
    border-radius:16px;
    padding:16px 18px;
    backdrop-filter:blur(12px);
    -webkit-backdrop-filter:blur(12px);
    box-shadow:0 4px 24px rgba(0,0,0,0.3);
    margin-bottom:12px;
">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="font-size:1.1rem;">⚡</span>
      <span style="font-weight:700;color:#e2e8f0;font-size:0.95rem;">Liquidation Cascade Risk</span>
    </div>
    <span style="background:{bg};color:{color};border:1px solid {color}66;border-radius:20px;
                 padding:3px 10px;font-size:0.85rem;font-weight:700;">{icon} {risk_level}</span>
  </div>

  <!-- Score gauge bar -->
  <div style="background:rgba(255,255,255,0.06);border-radius:8px;height:10px;margin-bottom:8px;overflow:hidden;">
    <div style="width:{bar_pct}%;height:100%;border-radius:8px;
                background:linear-gradient(90deg,#22c55e,{color});
                transition:width 0.5s ease;"></div>
  </div>

  <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.85rem;">
    <span style="color:{color};font-weight:700;font-size:1.1rem;">{score:.0f}<span style="font-size:0.75rem;color:#94a3b8;">/100</span></span>
    <span style="color:#94a3b8;">{label}</span>
  </div>
  {comp_html}
</div>
"""


# ─── Signal Accuracy Badge ──────────────────────────────────────────────────────

def signal_accuracy_badge_html(win_rate: float, sample_size: int,
                                signal_type: str = "") -> str:
    """
    Render a small badge showing historical signal accuracy.

    Parameters
    ----------
    win_rate    : float [0, 1] — fraction of signals that were correct
    sample_size : int — number of historical signals
    signal_type : optional label (e.g. 'BUY', 'SELL')

    Returns HTML string.
    """
    pct = win_rate * 100
    if pct >= 70:
        color, label = "#22c55e", "High Accuracy"
    elif pct >= 55:
        color, label = "#f59e0b", "Moderate"
    elif pct >= 45:
        color, label = "#94a3b8", "Neutral"
    else:
        color, label = "#ef4444", "Below Average"

    suffix = f" {signal_type}" if signal_type else ""
    n_text = f"{sample_size} signals" if sample_size >= 10 else "New signal"

    return (
        f'<span title="Historical accuracy of{suffix} signals over last {sample_size} trades" '
        f'style="display:inline-flex;align-items:center;gap:5px;'
        f'background:rgba(15,23,42,0.8);border:1px solid {color}44;border-radius:20px;'
        f'padding:3px 9px;font-size:0.85rem;cursor:help;">'
        f'<span style="color:{color};font-weight:700;">{pct:.0f}%</span>'
        f'<span style="color:#94a3b8;">{label} · {n_text}</span>'
        f'</span>'
    )


# ─── Market Regime Banner ───────────────────────────────────────────────────────

def regime_banner_html(regime: str, hurst: float | None = None,
                       squeeze_active: bool = False) -> str:
    """
    Full-width market regime banner with Hurst exponent and squeeze indicator.

    Parameters
    ----------
    regime         : 'BULL' | 'BEAR' | 'RANGING' | 'CRISIS'
    hurst          : Hurst exponent [0,1] — >0.5 = trending, <0.5 = mean-reverting
    squeeze_active : True if Bollinger Band is inside Keltner Channel (volatility squeeze)
    """
    _REGIME_META = {
        "BULL":    ("🐂", "#22c55e", "rgba(0,230,118,0.08)", "Bull Market",    "Trend-following strategies preferred"),
        "BEAR":    ("🐻", "#ef4444", "rgba(255,82,82,0.08)",  "Bear Market",    "Reduce size, defensive positioning"),
        "RANGING": ("↔",  "#f59e0b", "rgba(255,215,64,0.08)", "Ranging Market", "Mean-reversion strategies preferred"),
        "CRISIS":  ("🚨", "#f59e0b", "rgba(255,145,0,0.08)",  "Crisis / High Volatility", "Extreme caution — reduce all exposure"),
    }
    icon, color, bg, title, advice = _REGIME_META.get(
        regime, ("❓", "#94a3b8", "rgba(148,163,184,0.08)", "Unknown Regime", "")
    )

    hurst_html = ""
    if hurst is not None:
        h_color = "#22c55e" if hurst > 0.55 else ("#ef4444" if hurst < 0.45 else "#f59e0b")
        h_label = "Trending" if hurst > 0.55 else ("Mean-Reverting" if hurst < 0.45 else "Random Walk")
        hurst_html = (
            f'<span style="background:rgba(255,255,255,0.05);border-radius:8px;'
            f'padding:3px 8px;font-size:0.85rem;margin-left:10px;">'
            f'Hurst: <span style="color:{h_color};font-weight:700;">{hurst:.2f}</span>'
            f' <span style="color:#64748b;">({h_label})</span></span>'
        )

    squeeze_html = ""
    if squeeze_active:
        squeeze_html = (
            '<span style="background:rgba(255,215,64,0.15);border:1px solid #f59e0b66;'
            'border-radius:8px;padding:3px 8px;font-size:0.85rem;margin-left:10px;'
            'animation:pulse 1.5s ease-in-out infinite;">'
            '🗜 <span style="color:#f59e0b;font-weight:700;">SQUEEZE</span>'
            ' <span style="color:#94a3b8;">— breakout imminent</span></span>'
        )

    return f"""
<div style="
    background:{bg};
    border:1px solid {color}33;
    border-left:4px solid {color};
    border-radius:12px;
    padding:12px 18px;
    margin-bottom:14px;
    display:flex;
    align-items:center;
    flex-wrap:wrap;
    gap:6px;
">
  <span style="font-size:1.2rem;">{icon}</span>
  <span style="color:{color};font-weight:700;font-size:0.95rem;">{title}</span>
  <span style="color:#64748b;font-size:0.85rem;">— {advice}</span>
  {hurst_html}
  {squeeze_html}
</div>
"""


# ─── Position Size Recommendation Card ─────────────────────────────────────────

def position_size_card_html(recommended_pct: float, rationale: str,
                             circuit_breaker_active: bool = False,
                             daily_pnl_pct: float = 0.0) -> str:
    """
    Display a volatility-adjusted position size recommendation.

    Parameters
    ----------
    recommended_pct        : float [0, 100] — % of account to risk
    rationale              : short explanation string
    circuit_breaker_active : True if daily/weekly loss limit hit
    daily_pnl_pct          : today's running P&L %
    """
    if circuit_breaker_active:
        bg_color    = "rgba(255,82,82,0.08)"
        border_col  = "#ef4444"
        size_color  = "#ef4444"
        status_html = (
            '<div style="background:rgba(255,82,82,0.15);border:1px solid #ef444466;'
            'border-radius:8px;padding:8px 12px;margin-top:10px;font-size:0.85rem;">'
            '🚨 <span style="color:#ef4444;font-weight:700;">Circuit Breaker ACTIVE</span>'
            ' — all new signals suppressed until daily/weekly loss limit resets.</div>'
        )
    else:
        bg_color    = "rgba(15,23,42,0.7)"
        border_col  = "rgba(255,255,255,0.08)"
        size_color  = "#22c55e" if recommended_pct >= 1.0 else "#f59e0b"
        pnl_color   = "#22c55e" if daily_pnl_pct >= 0 else "#ef4444"
        pnl_sign    = "+" if daily_pnl_pct >= 0 else ""
        status_html = (
            f'<div style="font-size:0.85rem;color:#94a3b8;margin-top:8px;">'
            f'Today\'s P&L: <span style="color:{pnl_color};font-weight:600;">'
            f'{pnl_sign}{daily_pnl_pct:.2f}%</span>'
            f'</div>'
        )

    bar_pct = min(max(recommended_pct * 4, 0), 100)  # 0-25% maps to 0-100% bar

    return f"""
<div style="
    background:{bg_color};
    border:1px solid {border_col};
    border-radius:16px;
    padding:16px 18px;
    backdrop-filter:blur(12px);
    -webkit-backdrop-filter:blur(12px);
    box-shadow:0 4px 24px rgba(0,0,0,0.3);
    margin-bottom:12px;
">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
    <span style="font-size:1.1rem;">⚖</span>
    <span style="font-weight:700;color:#e2e8f0;font-size:0.95rem;">Position Size (Vol-Adjusted)</span>
  </div>
  <div style="display:flex;align-items:baseline;gap:6px;margin-bottom:8px;">
    <span style="color:{size_color};font-weight:800;font-size:2rem;">{recommended_pct:.1f}%</span>
    <span style="color:#64748b;font-size:0.85rem;">of account</span>
  </div>
  <div style="background:rgba(255,255,255,0.06);border-radius:6px;height:6px;margin-bottom:8px;overflow:hidden;">
    <div style="width:{bar_pct}%;height:100%;border-radius:6px;
                background:linear-gradient(90deg,#8b5cf6,{size_color});"></div>
  </div>
  <div style="color:#94a3b8;font-size:0.85rem;">{rationale}</div>
  {status_html}
</div>
"""


# ─── Agent Confidence Breakdown ─────────────────────────────────────────────────

def agent_confidence_breakdown_html(agents: list[dict]) -> str:
    """
    Show per-agent signal votes with Sharpe-weighted confidence bars.

    Parameters
    ----------
    agents : list of dicts, each with:
        name    : str  — agent name
        signal  : str  — 'BUY' | 'SELL' | 'NEUTRAL'
        weight  : float [0,1] — rolling Sharpe-based weight
        contrib : float — contribution to final score

    Returns HTML string.
    """
    _SIG_COLORS = {"BUY": "#22c55e", "SELL": "#ef4444", "NEUTRAL": "#94a3b8"}
    _SIG_ICONS  = {"BUY": "▲", "SELL": "▼", "NEUTRAL": "—"}

    rows = []
    for ag in agents:
        name    = ag.get("name", "Agent")
        signal  = ag.get("signal", "NEUTRAL").upper()
        weight  = float(ag.get("weight", 0.5))
        contrib = float(ag.get("contrib", 0.0))
        color   = _SIG_COLORS.get(signal, "#94a3b8")
        icon    = _SIG_ICONS.get(signal, "—")
        bar_w   = int(weight * 100)
        c_sign  = "+" if contrib >= 0 else ""
        rows.append(f"""
<div style="margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">
    <span style="font-size:0.85rem;color:#cbd5e1;font-weight:500;">{name}</span>
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="color:{color};font-size:0.85rem;font-weight:700;">{icon} {signal}</span>
      <span style="color:#64748b;font-size:0.75rem;">contrib: <span style="color:{color};">{c_sign}{contrib:.1f}</span></span>
    </div>
  </div>
  <div style="background:rgba(255,255,255,0.05);border-radius:4px;height:4px;overflow:hidden;">
    <div style="width:{bar_w}%;height:100%;border-radius:4px;background:{color};opacity:0.7;"></div>
  </div>
  <div style="text-align:right;font-size:0.85rem;color:#475569;margin-top:1px;">weight {weight:.0%}</div>
</div>""")

    rows_html = "".join(rows) if rows else '<div style="color:#64748b;font-size:0.85rem;">No agent data</div>'

    return f"""
<div style="
    background:rgba(15,23,42,0.7);
    border:1px solid rgba(255,255,255,0.08);
    border-radius:16px;
    padding:16px 18px;
    backdrop-filter:blur(12px);
    -webkit-backdrop-filter:blur(12px);
    box-shadow:0 4px 24px rgba(0,0,0,0.3);
    margin-bottom:12px;
">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
    <span style="font-size:1.1rem;">🤖</span>
    <span style="font-weight:700;color:#e2e8f0;font-size:0.95rem;">AI Agent Votes</span>
    <span style="color:#475569;font-size:0.75rem;">(Sharpe-weighted)</span>
  </div>
  {rows_html}
</div>
"""


# ─── Live Price Ticker Strip ────────────────────────────────────────────────────

_PRICE_TICKER_CSS = """
<style>
@keyframes ticker-scroll {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
.price-ticker-wrap {
  overflow: hidden;
  background: rgba(8,11,18,0.9);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  padding: 6px 0;
  margin-bottom: 12px;
}
.price-ticker-track {
  display: flex;
  gap: 32px;
  width: max-content;
  animation: ticker-scroll 40s linear infinite;
  white-space: nowrap;
}
.price-ticker-track:hover { animation-play-state: paused; }
.ticker-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size:0.85rem;
  font-weight: 600;
}
</style>
"""


def price_ticker_strip_html(prices: list[dict]) -> str:
    """
    Animated horizontal price ticker strip (pauses on hover).

    Parameters
    ----------
    prices : list of dicts with keys: symbol, price, change_pct
    """
    items = []
    for p in prices:
        sym    = p.get("symbol", "?").upper()
        price  = p.get("price", 0.0) or 0.0
        chg    = p.get("change_pct", 0.0) or 0.0
        color  = "#22c55e" if chg >= 0 else "#ef4444"
        arrow  = "▲" if chg >= 0 else "▼"
        sign   = "+" if chg >= 0 else ""
        pf     = f"${price:,.4f}" if price < 1 else f"${price:,.2f}"
        items.append(
            f'<span class="ticker-item">'
            f'<span style="color:#94a3b8;">{sym}</span>'
            f'<span style="color:#e2e8f0;">{pf}</span>'
            f'<span style="color:{color};">{arrow} {sign}{chg:.2f}%</span>'
            f'</span>'
        )

    # Duplicate items for seamless loop
    track = "".join(items * 2)

    return (
        _PRICE_TICKER_CSS
        + f'<div class="price-ticker-wrap"><div class="price-ticker-track">{track}</div></div>'
    )


# ─── Coin Card Grid (teen-friendly overview of all coins) ───────────────────

def coin_cards_grid_html(results: list, ws_prices: dict | None = None,
                         squeeze_data: dict | None = None) -> str:
    """
    Render a 2- or 3-column grid of coin signal cards for quick at-a-glance view.
    Designed to be immediately understandable by a 13-year-old:
      - Giant colored action word (BUY / SELL / WAIT)
      - Score bar 1-10
      - Entry and stop-loss prices
      - Live price if available

    Parameters
    ----------
    results   : list of scan result dicts
    ws_prices : optional dict from _ws.get_all_prices() for live prices

    Returns HTML string.
    """
    if not results:
        return ""

    if ws_prices is None:
        ws_prices = {}

    def _score(conf: float) -> int:
        """Convert 0-100% confidence to 1-10 score."""
        return max(1, min(10, round(conf / 10)))

    def _action_style(direction: str) -> tuple:
        """Return (label, color, bg, emoji) for an action."""
        d = (direction or "").upper()
        if "STRONG BUY" in d:
            return "STRONG BUY", "#00d4aa", "rgba(0,212,170,0.18)", "🚀"
        if "BUY" in d:
            return "BUY", "#00d4aa", "rgba(0,212,170,0.12)", "📈"
        if "STRONG SELL" in d:
            return "STRONG SELL", "#ef4444", "rgba(246,70,93,0.18)", "💥"
        if "SELL" in d:
            return "SELL", "#ef4444", "rgba(246,70,93,0.12)", "📉"
        return "WAIT", "#f59e0b", "rgba(245,158,11,0.10)", "⏳"

    def _score_bar(score: int, color: str) -> str:
        """Render a 10-segment score bar."""
        segs = []
        for i in range(1, 11):
            filled = i <= score
            bg = color if filled else "rgba(255,255,255,0.07)"
            segs.append(
                f'<div style="flex:1;height:6px;border-radius:3px;'
                f'background:{bg};margin:0 1px;"></div>'
            )
        return f'<div style="display:flex;gap:0;margin:6px 0 2px 0">{"".join(segs)}</div>'

    def _card(r: dict) -> str:
        pair      = r.get("pair", "?")
        sym       = pair.replace("/USDT", "")
        conf      = float(r.get("confidence_avg_pct") or 0)
        direction = r.get("direction", "WAIT")
        entry     = r.get("entry")
        stop      = r.get("stop_loss")
        tgt       = r.get("exit") or r.get("tp1")
        is_hc     = r.get("high_conf", False)
        score     = _score(conf)
        label, color, _bg, _emoji = _action_style(direction)

        # Direction arrow + border color (matches top_picks_hero_html exactly)
        d = direction.upper()
        if "BUY" in d:
            arrow, border_col = "▲", "rgba(0,212,170,0.35)"
        elif "SELL" in d:
            arrow, border_col = "▼", "rgba(246,70,93,0.35)"
        else:
            arrow, border_col = "■", "rgba(245,158,11,0.30)"

        # Donut gauge SVG — compact size (52px) for grid cards
        gauge_pct   = conf / 100
        r_o, cx, cy, sw = 21, 26, 26, 7
        circ        = 2 * 3.141592653589793 * (r_o - sw / 2)
        dash_filled = circ * gauge_pct
        dash_empty  = circ - dash_filled
        gauge_svg = (
            f'<svg width="52" height="52" viewBox="0 0 52 52">'
            f'<circle cx="{cx}" cy="{cy}" r="{r_o - sw/2}" fill="none" '
            f'stroke="rgba(255,255,255,0.07)" stroke-width="{sw}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r_o - sw/2}" fill="none" '
            f'stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-dasharray="{dash_filled:.1f} {dash_empty:.1f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
            f'<text x="{cx}" y="{cy+1}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="12" font-weight="800" fill="{color}">{score}</text>'
            f'<text x="{cx}" y="{cy+11}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="6" fill="rgba(255,255,255,0.4)">/10</text>'
            f'</svg>'
        )

        # TOP PICK badge
        hc_badge = (
            f'<span style="background:rgba(0,212,170,0.15);color:#00d4aa;'
            f'border:1px solid rgba(0,212,170,0.35);border-radius:99px;'
            f'font-size:9px;font-weight:800;padding:2px 8px;margin-left:6px;'
            f'letter-spacing:0.5px">⚡ TOP PICK</span>'
        ) if is_hc else ""

        # Cascade risk badge (shown when squeeze_data says HIGH_RISK)
        _sq_sig = (squeeze_data or {}).get(pair, "NORMAL")
        liq_badge = (
            '<span style="background:rgba(239,68,68,0.15);color:#ef4444;'
            'border:1px solid rgba(239,68,68,0.35);border-radius:99px;'
            'font-size:9px;font-weight:800;padding:2px 7px;margin-left:4px;'
            'letter-spacing:0.4px">⚠ LIQ RISK</span>'
        ) if _sq_sig in ("HIGH_RISK", "EXTREME") else ""

        # Price formatting helper
        def _fmt(p):
            if p is None:
                return "—"
            return f"${p:,.4f}" if p < 1 else f"${p:,.2f}"

        # Live price + 24h change
        ws        = ws_prices.get(pair, {})
        price     = ws.get("price") or r.get("price_usd")
        chg       = ws.get("change_24h_pct", 0) or 0
        chg_c     = "#00d4aa" if chg >= 0 else "#ef4444"
        price_str = _fmt(price) if price else "—"
        chg_str   = (
            f'<span style="color:{chg_c};font-size:11px">{chg:+.2f}%</span>'
            if ws else ""
        )

        # Plain-English one-liner (matches top_picks_hero_html)
        if "BUY" in d:
            plain = f"Model thinks <strong style='color:{color}'>{sym}</strong> price will go UP"
        elif "SELL" in d:
            plain = f"Model thinks <strong style='color:{color}'>{sym}</strong> price will go DOWN"
        else:
            plain = f"Model sees <strong style='color:{color}'>no clear direction</strong> yet"

        return f"""
<div style="
    background:linear-gradient(145deg,rgba(17,24,40,0.98),rgba(24,32,56,0.95));
    border:1px solid {border_col};
    border-top:3px solid {color};
    border-radius:12px;
    padding:14px;
    box-sizing:border-box;
    position:relative;
">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <div style="font-size:18px;font-weight:800;color:#e2e8f0;letter-spacing:-0.5px">{sym}</div>
      <div style="font-size:10px;color:rgba(168,180,200,0.5);margin-top:1px">{pair}{hc_badge}{liq_badge}</div>
    </div>
    <div style="text-align:center">{gauge_svg}</div>
  </div>
  <div style="margin:8px 0 6px">
    <span style="background:{color};color:#0d0e14;border-radius:999px;padding:4px 12px;
                 font-size:12px;font-weight:800;letter-spacing:0.3px">{arrow} {label}</span>
  </div>
  <div style="font-size:11px;color:rgba(200,210,230,0.75);margin-bottom:8px;line-height:1.4">{plain}</div>
  <div style="display:flex;gap:10px;font-size:10px;font-family:'JetBrains Mono',monospace;flex-wrap:wrap">
    <div><span style="color:rgba(168,180,200,0.45)">Price</span><br/>
         <span style="color:#e2e8f0;font-size:11px;font-weight:600">{price_str} {chg_str}</span></div>
    <div><span style="color:rgba(168,180,200,0.45)">Entry</span><br/>
         <span style="color:{color};font-weight:600">{_fmt(entry)}</span></div>
    <div><span style="color:rgba(168,180,200,0.45)">Stop</span><br/>
         <span style="color:#ef4444;font-weight:600">{_fmt(stop)}</span></div>
    <div><span style="color:rgba(168,180,200,0.45)">Target</span><br/>
         <span style="color:#00d4aa;font-weight:600">{_fmt(tgt)}</span></div>
  </div>
</div>"""

    # Build grid — tighter min-width for compact cards
    cards_html = "".join(_card(r) for r in results)

    return f"""
<div style="
    display:grid;
    grid-template-columns:repeat(auto-fill,minmax(210px,1fr));
    gap:12px;
    margin:8px 0 24px 0;
">
  {cards_html}
</div>"""


# ─── Skeleton shimmer cards (shown for pending pairs while others load) ────────

_SKELETON_CSS = """
<style>
@keyframes skeleton-shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
.skeleton-card {
    background: linear-gradient(
        90deg,
        rgba(30,35,55,0.8) 25%,
        rgba(50,57,85,0.6) 50%,
        rgba(30,35,55,0.8) 75%
    );
    background-size: 400px 100%;
    animation: skeleton-shimmer 1.4s ease-in-out infinite;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 16px;
    min-height: 170px;
}
.skeleton-line {
    background: linear-gradient(
        90deg,
        rgba(255,255,255,0.04) 25%,
        rgba(255,255,255,0.08) 50%,
        rgba(255,255,255,0.04) 75%
    );
    background-size: 400px 100%;
    animation: skeleton-shimmer 1.4s ease-in-out infinite;
    border-radius: 6px;
    height: 12px;
    margin: 8px 0;
}
</style>
"""


def skeleton_cards_html(n: int) -> str:
    """
    Render n shimmer skeleton cards to fill remaining grid slots while coins
    are still being analyzed. Each card shows animated grey-glow placeholders
    instead of a boring spinner — makes the loading feel premium and fast.
    """
    if n <= 0:
        return ""

    def _skeleton_card() -> str:
        return """
<div class="skeleton-card" style="padding:18px 20px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <div class="skeleton-line" style="width:80px;height:18px;"></div>
    <div class="skeleton-line" style="width:50px;height:18px;border-radius:99px;"></div>
  </div>
  <div class="skeleton-line" style="width:120px;height:26px;margin:10px 0 14px 0;"></div>
  <div class="skeleton-line" style="width:100%;height:6px;border-radius:3px;"></div>
  <div style="display:flex;gap:12px;margin-top:16px;">
    <div>
      <div class="skeleton-line" style="width:35px;height:9px;"></div>
      <div class="skeleton-line" style="width:70px;height:14px;"></div>
    </div>
    <div>
      <div class="skeleton-line" style="width:55px;height:9px;"></div>
      <div class="skeleton-line" style="width:70px;height:14px;"></div>
    </div>
  </div>
  <div style="margin-top:12px;font-size:11px;color:rgba(168,180,200,0.3);text-align:center;">
    ⏳ Analyzing...
  </div>
</div>"""

    cards = "".join(_skeleton_card() for _ in range(n))
    return f"{_SKELETON_CSS}<div style='display:contents'>{cards}</div>"


# ─── Fun loading screen while scan runs ────────────────────────────────────────

_CRYPTO_FACTS = [
    "💡 Bitcoin was created in 2009 by the mysterious Satoshi Nakamoto — nobody knows who they really are!",
    "🌍 There are over 20,000 different cryptocurrencies in the world today.",
    "⚡ The Lightning Network can process millions of Bitcoin transactions per second.",
    "🐋 'Whale' means a person who owns a huge amount of crypto — their trades move the market!",
    "📈 RSI (Relative Strength Index) measures how overbought or oversold a coin is on a 0-100 scale.",
    "🔒 Blockchain is basically a tamper-proof digital notebook that thousands of computers share.",
    "🎯 MACD compares two moving averages to spot when momentum is shifting — like a heads-up signal.",
    "🏦 DeFi = Decentralized Finance. No banks needed — just code running on a blockchain.",
    "🌐 Ethereum introduced 'smart contracts' — programs that run automatically when conditions are met.",
    "📊 Volume tells you how many people are trading a coin. High volume = more people paying attention.",
    "🔴 A 'Stop Loss' automatically sells your coin if it drops too far, protecting you from big losses.",
    "💎 'Diamond hands' means holding onto your crypto even when prices fall. 'Paper hands' means selling quickly.",
    "🤖 Our AI uses 6 different models that vote on the direction — like a jury deciding a verdict.",
    "⏱️ The '1h' timeframe shows what the market looks like over 1-hour candles — great for short trades.",
    "🌕 'To the moon' is crypto slang for when a price goes way up. Traders love this phrase!",
]


def loading_screen_html(progress: int, total: int, pair_name: str = "",
                        fact_index: int = 0) -> str:
    """
    Engaging loading screen shown while the scan runs.
    Shows a fact carousel + animated progress ring.
    """
    fact = _CRYPTO_FACTS[fact_index % len(_CRYPTO_FACTS)]
    pct  = int(progress / max(total, 1) * 100)

    status = (
        f"Connecting to Kraken..." if progress == 0
        else f"Analyzing {pair_name}... ({progress}/{total} pairs done)"
    )

    # SVG circle progress ring
    r   = 28
    circ = 2 * 3.141592653589793 * r
    dash = circ * pct / 100

    return f"""
<div style="
    background:linear-gradient(135deg,rgba(12,15,26,0.97),rgba(17,21,32,0.95));
    border:1px solid rgba(0,212,170,0.15);
    border-radius:20px;
    padding:28px 32px;
    text-align:center;
    margin:12px 0;
    box-shadow:0 8px 40px rgba(0,0,0,0.5);
">
  <!-- Progress ring -->
  <div style="position:relative;display:inline-block;margin-bottom:16px;">
    <svg width="72" height="72" viewBox="0 0 72 72" style="transform:rotate(-90deg);">
      <circle cx="36" cy="36" r="{r}" fill="none" stroke="rgba(0,212,170,0.1)" stroke-width="5"/>
      <circle cx="36" cy="36" r="{r}" fill="none" stroke="#00d4aa" stroke-width="5"
              stroke-dasharray="{dash:.1f} {circ:.1f}"
              stroke-linecap="round" style="transition:stroke-dasharray 0.4s ease;"/>
    </svg>
    <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                font-size:16px;font-weight:800;color:#00d4aa;
                font-family:JetBrains Mono,monospace;">{pct}%</div>
  </div>

  <div style="font-size:14px;font-weight:600;color:#e2e8f0;margin-bottom:6px;">
    🔍 Scanning the market...
  </div>
  <div style="font-size:12px;color:rgba(168,180,200,0.6);margin-bottom:20px;">
    {status}
  </div>

  <!-- Fun fact -->
  <div style="
      background:rgba(0,212,170,0.06);
      border:1px solid rgba(0,212,170,0.15);
      border-radius:12px;
      padding:14px 18px;
      text-align:left;
  ">
    <div style="font-size:10px;color:rgba(0,212,170,0.7);font-weight:700;
                text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px;">
      💡 Did you know?
    </div>
    <div style="font-size:13px;color:#94a3b8;line-height:1.5;">{fact}</div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# SPARKLINE MINI-CHART  (#60)
# Inline SVG sparkline — no plotly overhead for scan overview grids
# ─────────────────────────────────────────────────────────────────────────────

def sparkline_svg(closes: list, width: int = 80, height: int = 30,
                  color: str = "#2dd4bf") -> str:
    """
    Generate an inline SVG sparkline polyline from a list of close prices.
    Returns an empty string if fewer than 2 data points.
    """
    if len(closes) < 2:
        return ""
    lo  = min(closes)
    hi  = max(closes)
    rng = hi - lo or 1.0
    pad = 2  # pixel padding top/bottom
    xs  = [round(i / (len(closes) - 1) * width, 1) for i in range(len(closes))]
    ys  = [round(pad + (1 - (c - lo) / rng) * (height - pad * 2), 1) for c in closes]
    pts = " ".join(f"{x},{y}" for x, y in zip(xs, ys))
    trend_color = "#2dd4bf" if closes[-1] >= closes[0] else "#ef4444"
    col = color if color != "#2dd4bf" else trend_color
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:inline-block;vertical-align:middle">'
        f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def scan_sparkline_card_html(pair: str, direction: str, conf: float,
                              closes: list) -> str:
    """
    Compact scan-mode card with pair name, direction badge, confidence and sparkline.
    Used in scan overview mini-grid (#60).
    """
    dir_colors = {"BUY": "#2dd4bf", "STRONG BUY": "#00D4AA",
                  "SELL": "#ef4444", "STRONG SELL": "#EF4444"}
    d_upper = direction.upper()
    d_col   = next((v for k, v in dir_colors.items() if k in d_upper), "#9CA3AF")
    spk_svg = sparkline_svg(closes)
    conf_int = int(conf)
    return (
        f'<div style="background:#111827;border:1px solid #1F2937;border-left:3px solid {d_col};'
        f'border-radius:8px;padding:8px 10px;display:flex;justify-content:space-between;align-items:center">'
        f'<div>'
        f'<div style="font-size:12px;font-weight:700;color:#E2E8F0">{pair}</div>'
        f'<div style="font-size:10px;color:{d_col};margin-top:1px">{direction}</div>'
        f'<div style="font-size:10px;color:#6B7280;margin-top:1px">{conf_int}% conf</div>'
        f'</div>'
        f'<div>{spk_svg}</div>'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# GRADIENT CONFIDENCE BAR  (#62)
# CSS linear-gradient progress bar — more visual than st.progress()
# ─────────────────────────────────────────────────────────────────────────────

def gradient_confidence_bar_html(conf: float) -> str:
    """
    Return an HTML gradient progress bar for a confidence value 0–100.
    Color transitions: red (0%) → amber (50%) → green (100%).
    """
    pct = max(0, min(int(conf), 100))
    if pct >= 70:
        bar_color  = "linear-gradient(90deg,#2dd4bf,#00D4AA)"
        label_color = "#2dd4bf"
        label_text  = "Strong signal"
    elif pct >= 50:
        bar_color  = "linear-gradient(90deg,#FBBF24,#f59e0b)"
        label_color = "#FBBF24"
        label_text  = "Moderate signal"
    else:
        bar_color  = "linear-gradient(90deg,#EF4444,#f59e0b)"
        label_color = "#EF4444"
        label_text  = "Weak — use caution"
    score_10 = max(0, min(10, round(pct / 10)))
    return (
        f'<div style="margin:8px 0 12px 0">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
        f'<span style="font-size:12px;color:{label_color};font-weight:600">'
        f'Confidence: {score_10}/10 ({pct}%)</span>'
        f'<span style="font-size:11px;color:#6B7280">{label_text}</span>'
        f'</div>'
        f'<div style="background:#1F2937;border-radius:6px;height:10px;overflow:hidden">'
        f'<div style="background:{bar_color};width:{pct}%;height:100%;border-radius:6px;'
        f'transition:width 0.5s ease;box-shadow:0 0 8px rgba(52,211,153,0.3)"></div>'
        f'</div>'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# #62 — render_confidence_bar (signal-aware alias, spec-compliant name)
# BUY → green gradient, SELL → red gradient, HOLD/NEUTRAL → amber/orange.
# Width = confidence%.  Renders inline HTML via st.markdown(unsafe_allow_html=True).
# ─────────────────────────────────────────────────────────────────────────────

def render_confidence_bar(confidence: float, signal: str = "") -> str:
    """
    #62 — Signal-aware gradient confidence bar.

    Parameters
    ----------
    confidence : float 0-100
    signal     : direction string — BUY | SELL | HOLD | NEUTRAL | etc.

    Returns HTML string to render via st.markdown(unsafe_allow_html=True).
    """
    pct = max(0, min(int(confidence), 100))
    sig_upper = (signal or "").upper()

    if "BUY" in sig_upper:
        # BUY: light green → dark green
        bar_color   = f"linear-gradient(90deg,#86efac,#00D4AA)"
        label_color = "#00D4AA"
        label_text  = "BUY Signal"
    elif "SELL" in sig_upper:
        # SELL: light red → deep red
        bar_color   = "linear-gradient(90deg,#FCA5A5,#EF4444)"
        label_color = "#EF4444"
        label_text  = "SELL Signal"
    else:
        # HOLD / NEUTRAL: amber → orange
        bar_color   = "linear-gradient(90deg,#FDE68A,#F59E0B)"
        label_color = "#F59E0B"
        label_text  = "HOLD / Neutral"

    score_10 = max(0, min(10, round(pct / 10)))
    return (
        f'<div style="margin:8px 0 12px 0">'
        f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
        f'<span style="font-size:12px;color:{label_color};font-weight:600">'
        f'Confidence: {score_10}/10 ({pct}%) — {label_text}</span>'
        f'</div>'
        f'<div style="background:#1F2937;border-radius:6px;height:10px;overflow:hidden">'
        f'<div style="background:{bar_color};width:{pct}%;height:100%;border-radius:6px;'
        f'transition:width 0.5s ease;"></div>'
        f'</div>'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# #60 — render_sparkline (Plotly-based, spec-compliant name)
# Thin Plotly wrapper; returns a go.Figure with minimal layout.
# Green if last > first, red if declining.
# ─────────────────────────────────────────────────────────────────────────────

# ─── Phase 3 — New helpers ────────────────────────────────────────────────────

# ── Welcome Banner (Phase 3, item 19) ─────────────────────────────────────────

def render_welcome_banner() -> None:
    """Show a one-time welcome message for Beginner users.

    Appears once per session, dismissible. No-op for Intermediate/Advanced.
    """
    if st.session_state.get("user_level", "beginner") != "beginner":
        return
    if st.session_state.get("_sg_welcome_dismissed"):
        return
    _c1, _c2 = st.columns([11, 1])
    with _c1:
        st.info(
            "👋 **Welcome to Family Office · Signal Intelligence!**  \n"
            "This app scans crypto markets and delivers clear, actionable trade signals. "
            "Every metric is explained in plain English — no experience needed.  \n"
            "**Quick start:** The **Dashboard** shows today's top signals ranked by confidence. "
            "Set your coin in the sidebar, pick a timeframe, and scan.  \n"
            "💡 *Raise your experience level in the sidebar to see more detail.*"
        )
    with _c2:
        if st.button("✕", key="_sg_dismiss_welcome", help="Dismiss welcome message"):
            st.session_state["_sg_welcome_dismissed"] = True
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# UI OVERHAUL — Beginner-first components (Items 1-17 sprint)
# Target audience: high school seniors, young adults, first-time retail investors
# ══════════════════════════════════════════════════════════════════════════════

def top_picks_hero_html(results: list, ws_prices: dict | None = None) -> str:
    """
    Item 1/2 — Hero panel: top 3 signals as large, clear action cards.
    First thing a beginner sees after scan. Zero scrolling required.
    Shows up to 3 cards (top picks first, then highest confidence).
    """
    if not results:
        return ""
    if ws_prices is None:
        ws_prices = {}

    def _dir_style(d: str):
        d = (d or "").upper()
        if "BUY" in d:
            return "#00d4aa", "rgba(0,212,170,0.13)", "▲", "rgba(0,212,170,0.35)"
        if "SELL" in d:
            return "#ef4444", "rgba(246,70,93,0.13)", "▼", "rgba(246,70,93,0.35)"
        return "#f59e0b", "rgba(245,158,11,0.10)", "■", "rgba(245,158,11,0.30)"

    def _score(conf):
        return max(1, min(10, round((conf or 0) / 10)))

    def _fmt(p):
        if p is None:
            return "—"
        return f"${p:,.4f}" if p < 1 else f"${p:,.2f}"

    sorted_r = sorted(results,
                      key=lambda r: (r.get("high_conf", False), r.get("confidence_avg_pct", 0)),
                      reverse=True)
    top3 = sorted_r[:3]

    cards_html = ""
    for r in top3:
        pair  = r.get("pair", "?")
        sym   = pair.replace("/USDT", "")
        conf  = float(r.get("confidence_avg_pct") or 0)
        dirn  = r.get("direction", "WAIT")
        score = _score(conf)
        entry = r.get("entry")
        stop  = r.get("stop_loss")
        tgt   = r.get("exit") or r.get("tp1")
        is_hc = r.get("high_conf", False)
        color, bg, arrow, border_col = _dir_style(dirn)

        ws    = ws_prices.get(pair, {})
        price = ws.get("price") or r.get("price_usd")
        chg   = ws.get("change_24h_pct", 0) or 0
        chg_c = "#00d4aa" if chg >= 0 else "#ef4444"
        price_str = _fmt(price) if price else "—"
        chg_str = f'<span style="color:{chg_c};font-size:11px">{chg:+.2f}%</span>' if ws else ""

        # Donut gauge — compact 52px (matches grid cards)
        gauge_pct = conf / 100
        r_outer, cx, cy, sw = 21, 26, 26, 7
        circ = 2 * 3.141592653589793 * (r_outer - sw / 2)
        dash_filled = circ * gauge_pct
        dash_empty  = circ - dash_filled
        gauge_svg = (
            f'<svg width="52" height="52" viewBox="0 0 52 52">'
            f'<circle cx="{cx}" cy="{cy}" r="{r_outer - sw/2}" fill="none" '
            f'stroke="rgba(255,255,255,0.07)" stroke-width="{sw}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r_outer - sw/2}" fill="none" '
            f'stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-dasharray="{dash_filled:.1f} {dash_empty:.1f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
            f'<text x="{cx}" y="{cy+1}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="12" font-weight="800" fill="{color}">{score}</text>'
            f'<text x="{cx}" y="{cy+11}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="6" fill="rgba(255,255,255,0.4)">/10</text>'
            f'</svg>'
        )

        hc_badge = (
            f'<span style="background:rgba(0,212,170,0.15);color:#00d4aa;'
            f'border:1px solid rgba(0,212,170,0.35);border-radius:99px;'
            f'font-size:9px;font-weight:800;padding:2px 8px;margin-left:6px;'
            f'letter-spacing:0.5px">⚡ TOP PICK</span>'
        ) if is_hc else ""

        # Plain-English one-liner
        if "BUY" in (dirn or "").upper():
            plain = f"Model thinks <strong style='color:{color}'>{sym}</strong> price will go UP"
        elif "SELL" in (dirn or "").upper():
            plain = f"Model thinks <strong style='color:{color}'>{sym}</strong> price will go DOWN"
        else:
            plain = f"Model sees <strong style='color:{color}'>no clear direction</strong> yet"

        cards_html += f"""
<div style="flex:1;min-width:200px;max-width:340px;
            background:linear-gradient(145deg,rgba(17,24,40,0.98),rgba(24,32,56,0.95));
            border:1px solid {border_col};border-top:3px solid {color};
            border-radius:12px;padding:14px;box-sizing:border-box;position:relative">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <div style="font-size:18px;font-weight:800;color:#e2e8f0;letter-spacing:-0.5px">{sym}</div>
      <div style="font-size:10px;color:rgba(168,180,200,0.5);margin-top:1px">{pair}{hc_badge}</div>
    </div>
    <div style="text-align:center">{gauge_svg}</div>
  </div>
  <div style="margin:8px 0 6px">
    <span style="background:{color};color:#0d0e14;border-radius:999px;padding:4px 12px;
                 font-size:12px;font-weight:800;letter-spacing:0.3px">{arrow} {dirn}</span>
  </div>
  <div style="font-size:11px;color:rgba(200,210,230,0.75);margin-bottom:8px;line-height:1.4">{plain}</div>
  <div style="display:flex;gap:10px;font-size:10px;font-family:'JetBrains Mono',monospace;flex-wrap:wrap">
    <div><span style="color:rgba(168,180,200,0.45)">Price</span><br/>
         <span style="color:#e2e8f0;font-size:11px;font-weight:600">{price_str} {chg_str}</span></div>
    <div><span style="color:rgba(168,180,200,0.45)">Entry</span><br/>
         <span style="color:{color};font-weight:600">{_fmt(entry)}</span></div>
    <div><span style="color:rgba(168,180,200,0.45)">Stop</span><br/>
         <span style="color:#ef4444;font-weight:600">{_fmt(stop)}</span></div>
    <div><span style="color:rgba(168,180,200,0.45)">Target</span><br/>
         <span style="color:#00d4aa;font-weight:600">{_fmt(tgt)}</span></div>
  </div>
</div>"""

    return f"""
<div style="margin:0 0 20px 0">
  <div style="font-size:10px;color:rgba(168,180,200,0.4);text-transform:uppercase;
              letter-spacing:1px;font-weight:600;margin-bottom:10px">
    ⚡ Today's Top Picks — model's highest-confidence signals
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap">{cards_html}</div>
  <div style="font-size:10px;color:rgba(168,180,200,0.3);margin-top:8px">
    Score 7–10/10 = actionable signal &nbsp;·&nbsp; 5–6 = watch &nbsp;·&nbsp;
    1–4 = avoid &nbsp;·&nbsp; Always set a Stop Loss before entering any trade
  </div>
</div>"""


def how_it_works_html(win_rate: float = 0, n_months: int = 0,
                       n_indicators: int = 24) -> str:
    """
    Item 11 — Trust card: brief plain-English model explainer.
    Shown as a collapsible card near the top of Dashboard.
    """
    wr_str = f"{win_rate:.0f}%" if win_rate else "calculating…"
    mo_str = f"{n_months} months" if n_months else "extensive history"
    return f"""
<div style="background:rgba(0,212,170,0.04);border:1px solid rgba(0,212,170,0.15);
            border-left:3px solid #00d4aa;border-radius:10px;padding:14px 18px;
            margin:0 0 16px 0;font-size:12px;color:rgba(200,210,230,0.8);line-height:1.7">
  <div style="font-size:11px;color:#00d4aa;font-weight:700;text-transform:uppercase;
              letter-spacing:0.8px;margin-bottom:6px">🔬 How This Model Works</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px">
    <div>📊 Watches <strong style="color:#e2e8f0">{n_indicators} indicators</strong>
         across 4 timeframes</div>
    <div>🕐 Backtested over <strong style="color:#e2e8f0">{mo_str}</strong> of data</div>
    <div>🎯 Win rate in backtesting: <strong style="color:#00d4aa">{wr_str}</strong></div>
    <div>🛡️ Signals 7/10+ confidence have historically been most reliable</div>
  </div>
</div>"""


def wdtmfm_html(direction: str, entry: float, stop: float, target: float,
                 conf: float, portfolio_usd: float = 1000) -> str:
    """
    Item 7 — 'What Does This Mean For Me?' contextual box.
    Converts abstract signal data into a concrete personal dollar example.
    portfolio_usd: user's configured portfolio size (default $1,000 example).
    """
    d = (direction or "").upper()
    if "BUY" in d:
        accent = "#00d4aa"
        verb   = "going UP"
        action = "BUY"
    elif "SELL" in d:
        accent = "#ef4444"
        verb   = "going DOWN"
        action = "SELL (or skip)"
    else:
        return ""

    score = max(1, min(10, round((conf or 0) / 10)))

    if entry and stop and target:
        risk_pct   = abs(entry - stop) / entry * 100 if entry > 0 else 0
        reward_pct = abs(target - entry) / entry * 100 if entry > 0 else 0
        rr         = reward_pct / risk_pct if risk_pct > 0 else 0
        risk_usd   = portfolio_usd * (risk_pct / 100)
        reward_usd = portfolio_usd * (reward_pct / 100)
        numbers = (
            f"On a <strong style='color:#e2e8f0'>${portfolio_usd:,.0f}</strong> position — "
            f"risk up to <strong style='color:#ef4444'>${risk_usd:,.0f}</strong> "
            f"({risk_pct:.1f}%) to potentially gain "
            f"<strong style='color:#00d4aa'>${reward_usd:,.0f}</strong> "
            f"({reward_pct:.1f}%). Risk/reward = <strong style='color:#e2e8f0'>{rr:.1f}×</strong>."
        )
    else:
        numbers = "Set your portfolio size in Settings to see your personal dollar figures."

    return f"""
<div style="background:rgba(0,212,170,0.04);border:1px solid rgba(0,212,170,0.12);
            border-left:3px solid {accent};border-radius:10px;
            padding:12px 16px;margin:8px 0 12px 0;font-size:12px;
            color:rgba(200,210,230,0.85);line-height:1.7">
  <div style="font-size:10px;color:{accent};font-weight:700;text-transform:uppercase;
              letter-spacing:0.8px;margin-bottom:4px">💡 What Does This Mean For Me?</div>
  The model thinks this coin has a <strong style="color:{accent}">{conf:.0f}%</strong>
  chance of {verb}. Confidence score: <strong style="color:{accent}">{score}/10</strong>
  {'— strong signal' if score >= 7 else '— watch but be cautious' if score >= 5 else '— uncertain, avoid acting'}.
  Suggested action: <strong style="color:{accent}">{action}</strong>.<br/>
  {numbers}
</div>"""


def why_signal_html(
    direction: str,
    conf: float,
    rsi: float | None,
    adx: float | None,
    mtf: float,
    consensus: float,
    regime: str,
    bias: str,
    funding_rate: float | None,
) -> str:
    """
    Item 6 — Tier 2 'Why this signal?' plain-English reasoning panel.
    Converts raw indicator values into human-readable bullet-point reasons
    so beginners understand *why* the model says BUY/SELL — not just that it does.
    """
    d = (direction or "").upper()
    is_buy  = "BUY"  in d
    is_sell = "SELL" in d
    is_hold = not is_buy and not is_sell

    accent = "#00d4aa" if is_buy else "#ef4444" if is_sell else "#f59e0b"
    reasons: list[str] = []

    # ── HOLD-specific reasons ─────────────────────────────────────────────────
    if is_hold:
        reasons.append(
            "⏸️ <b>No clear edge right now</b> — the model's indicators are mixed or "
            "conflicting. Entering a trade without a clear edge increases risk unnecessarily."
        )
        if rsi is not None and 40 <= rsi <= 60:
            reasons.append(
                f"↔️ <b>Momentum is neutral</b> — RSI of {rsi:.0f} sits in the middle "
                f"zone (40–60), which signals neither buyers nor sellers are in control."
            )
        if adx is not None and adx < 20:
            reasons.append(
                f"😴 <b>Trend is weak / choppy</b> — ADX of {adx:.0f} is below 20, meaning "
                f"the market is ranging sideways. Trend-following signals are unreliable here."
            )
        if mtf > 0 and mtf < 60:
            reasons.append(
                f"🕐 <b>Timeframes are split</b> — only {mtf:.0f}% of the 1h / 4h / daily "
                f"charts agree on direction. Waiting for alignment reduces false-signal risk."
            )
        agents_agree = round((consensus or 0) * 6)
        if agents_agree < 3:
            reasons.append(
                f"🤖 <b>AI models are divided</b> — only {agents_agree} of 6 AI models "
                f"agree on a direction. The model recommends waiting for clearer consensus."
            )
        reasons.append(
            "💡 <b>What to do</b> — consider watching for a breakout above resistance or "
            "below support before entering. Keep existing positions; don't add new ones."
        )
        # Build and return HOLD card immediately
        bullet_html = "".join(
            f'<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">'
            f'<span style="min-width:4px;background:{accent};border-radius:2px;align-self:stretch"></span>'
            f'<span>{r}</span>'
            f'</div>'
            for r in reasons
        )
        return f"""
<div style="background:rgba(20,24,36,0.6);border:1px solid rgba(255,255,255,0.06);
            border-radius:10px;padding:14px 16px;margin:4px 0 8px 0;font-size:12.5px;
            color:rgba(200,210,230,0.85);line-height:1.65">
  <div style="font-size:10px;color:{accent};font-weight:700;text-transform:uppercase;
              letter-spacing:0.8px;margin-bottom:10px">🔍 Why HOLD?</div>
  {bullet_html}
</div>"""

    # Tooltip wrappers for key jargon — Item 10
    _rsi_tip = tt("RSI", "Relative Strength Index — a momentum indicator (0–100). Above 70 = potentially overbought, below 30 = potentially oversold.")
    _adx_tip = tt("ADX", "Average Directional Index — measures trend strength (0–100). Above 25 = strong trend, below 20 = choppy/sideways market.")
    _fr_tip  = tt("funding rate", "A fee paid between long and short traders every 8 hours in perpetual futures. Positive = longs pay shorts (bullish crowd). Negative = shorts pay longs (bearish crowd).")
    _mtf_tip = tt("timeframes", "Multiple time periods checked: 1 hour, 4 hours, daily, and weekly charts. When all agree it's more reliable.")

    # ── RSI reason ────────────────────────────────────────────────────────────
    if rsi is not None:
        if rsi >= 70:
            if is_sell:
                reasons.append(f"🌡️ <b>Price looks overheated</b> — the momentum indicator ({_rsi_tip}: {rsi:.0f}) is very high, suggesting a potential pullback.")
            else:
                reasons.append(f"🌡️ <b>Momentum is strong</b> — {_rsi_tip} of {rsi:.0f} confirms buyers are in control, even in overbought territory.")
        elif rsi <= 30:
            if is_buy:
                reasons.append(f"🧊 <b>Price looks oversold</b> — {_rsi_tip} of {rsi:.0f} shows extreme selling pressure, which often precedes a bounce.")
            else:
                reasons.append(f"🧊 <b>Momentum is weak</b> — {_rsi_tip} of {rsi:.0f} confirms sellers are in control.")
        elif rsi >= 55 and is_buy:
            reasons.append(f"📈 <b>Momentum is building</b> — {_rsi_tip} of {rsi:.0f} shows buyers are gaining the upper hand.")
        elif rsi <= 45 and is_sell:
            reasons.append(f"📉 <b>Momentum is fading</b> — {_rsi_tip} of {rsi:.0f} shows sellers are pushing price lower.")
        else:
            reasons.append(f"↔️ <b>Momentum is neutral</b> — {_rsi_tip} of {rsi:.0f} means no clear momentum edge right now.")

    # ── ADX reason ────────────────────────────────────────────────────────────
    if adx is not None:
        if adx >= 25:
            reasons.append(f"💪 <b>Strong trend confirmed</b> — trend strength ({_adx_tip}: {adx:.0f}) is above 25, meaning this isn't random noise.")
        elif adx >= 15:
            reasons.append(f"🔎 <b>Moderate trend forming</b> — {_adx_tip} of {adx:.0f} suggests a trend is developing but not yet fully confirmed.")
        else:
            reasons.append(f"😴 <b>Market is ranging / choppy</b> — {_adx_tip} of {adx:.0f} is low, which means signals are less reliable in sideways markets.")

    # ── Multi-timeframe alignment reason ─────────────────────────────────────
    if mtf >= 75:
        reasons.append(f"🕐 <b>Multiple {_mtf_tip} agree</b> — the 1h, 4h, and daily charts all point the same direction ({mtf:.0f}% alignment). Strong consensus.")
    elif mtf >= 50:
        reasons.append(f"🕐 <b>Most {_mtf_tip} agree</b> — about {mtf:.0f}% of time periods confirm this direction. Good but not perfect.")
    elif mtf > 0:
        reasons.append(f"⚠️ <b>Mixed {_mtf_tip} signals</b> — only {mtf:.0f}% of time periods agree. The model is less certain here.")

    # ── AI consensus reason ───────────────────────────────────────────────────
    agents_agree = round((consensus or 0) * 6)
    if agents_agree >= 5:
        reasons.append(f"🤖 <b>Strong AI consensus</b> — {agents_agree} out of 6 AI models independently agree on this direction. Very high confidence.")
    elif agents_agree >= 3:
        reasons.append(f"🤖 <b>Majority AI agreement</b> — {agents_agree} of 6 AI models agree. A solid signal but monitor closely.")
    elif agents_agree >= 1:
        reasons.append(f"🤖 <b>Weak AI agreement</b> — only {agents_agree} of 6 AI models agree. The models are divided.")

    # ── Regime reason ─────────────────────────────────────────────────────────
    reg = (regime or "").upper()
    if "BULL" in reg or "TRENDING_UP" in reg:
        reasons.append("🐂 <b>Bullish market environment</b> — the overall market trend favours upward moves.")
    elif "BEAR" in reg or "TRENDING_DOWN" in reg:
        reasons.append("🐻 <b>Bearish market environment</b> — the overall trend is downward, supporting the sell signal.")
    elif "RANGING" in reg or "SIDEWAYS" in reg:
        reasons.append("↔️ <b>Sideways / ranging market</b> — the market has no clear direction right now. Use tighter stops.")

    # ── Funding rate reason ───────────────────────────────────────────────────
    if funding_rate is not None and abs(funding_rate) > 0.02:
        if funding_rate > 0.05 and is_sell:
            reasons.append(f"📊 <b>Overextended longs</b> — {_fr_tip} ({funding_rate:+.3f}%) shows longs are paying shorts heavily, signalling a crowded trade that could reverse.")
        elif funding_rate < -0.03 and is_buy:
            reasons.append(f"📊 <b>Overextended shorts</b> — {_fr_tip} ({funding_rate:+.3f}%) shows shorts paying longs — a potential short squeeze setup.")

    if not reasons:
        reasons.append(f"📊 The model analysed {24} technical indicators across 4 timeframes and found a {conf:.0f}% confidence {direction} signal.")

    bullet_html = "".join(
        f'<div style="display:flex;gap:10px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">'
        f'<span style="min-width:4px;background:{accent};border-radius:2px;align-self:stretch"></span>'
        f'<span>{r}</span>'
        f'</div>'
        for r in reasons
    )

    return f"""
<div style="background:rgba(20,24,36,0.6);border:1px solid rgba(255,255,255,0.06);
            border-radius:10px;padding:14px 16px;margin:4px 0 8px 0;font-size:12.5px;
            color:rgba(200,210,230,0.85);line-height:1.65">
  <div style="font-size:10px;color:{accent};font-weight:700;text-transform:uppercase;
              letter-spacing:0.8px;margin-bottom:10px">🔍 Why this signal?</div>
  {bullet_html}
</div>"""


def render_micro_tutorial() -> None:
    """
    Item 9 — 3-step beginner micro-tutorial shown on first visit.
    Stored in session_state so it only shows once per session.
    Revisitable via sidebar button (set _sg_show_tutorial=True to re-trigger).
    """
    if st.session_state.get("user_level", "beginner") != "beginner":
        return
    if st.session_state.get("_sg_tutorial_done") and not st.session_state.get("_sg_show_tutorial"):
        return

    step = st.session_state.get("_sg_tutorial_step", 0)

    steps = [
        {
            "icon": "📈",
            "title": "Step 1 of 3 — Reading a Signal",
            "body": (
                "**BUY (▲)** = the model thinks the price will go up.  \n"
                "**SELL (▼)** = the model thinks the price will go down.  \n"
                "**WAIT (■)** = the model isn't sure — sit it out.  \n\n"
                "The **score (1–10)** shows how confident the model is. "
                "**7 or higher** = actionable. **5 or below** = too uncertain to trade."
            ),
        },
        {
            "icon": "🛡️",
            "title": "Step 2 of 3 — Protecting Yourself",
            "body": (
                "Every signal comes with a **Stop Loss** price.  \n"
                "This is the price where you exit if the trade goes wrong — it limits your loss.  \n\n"
                "**Rule:** Always set your Stop Loss *before* you enter any trade.  \n"
                "The model also shows a **Target** (Take Profit) — the price where you take your gains."
            ),
        },
        {
            "icon": "📋",
            "title": "Step 3 of 3 — Tracking Progress",
            "body": (
                "Go to **My Trades** in the menu to see your paper trading history.  \n"
                "Paper trading = simulated trades with fake money. No real money at risk.  \n\n"
                "Use paper trading to learn the system and build confidence before using real money.  \n"
                "Check **Performance** to see how the model has done historically."
            ),
        },
    ]

    s = steps[step]
    st.info(
        f"{s['icon']} **{s['title']}**  \n\n{s['body']}",
        icon=None,
    )
    c1, c2, c3 = st.columns([2, 2, 4])
    with c1:
        if step > 0:
            if st.button("← Back", key="_sg_tut_back"):
                st.session_state["_sg_tutorial_step"] = step - 1
                st.rerun()
    with c2:
        if step < len(steps) - 1:
            if st.button("Next →", key="_sg_tut_next", type="primary"):
                st.session_state["_sg_tutorial_step"] = step + 1
                st.rerun()
        else:
            if st.button("Got it! ✓", key="_sg_tut_done", type="primary"):
                st.session_state["_sg_tutorial_done"] = True
                st.session_state["_sg_show_tutorial"] = False
                st.session_state["_sg_tutorial_step"] = 0
                st.rerun()
    with c3:
        if st.button("Skip tutorial", key="_sg_tut_skip"):
            st.session_state["_sg_tutorial_done"] = True
            st.session_state["_sg_show_tutorial"] = False
            st.session_state["_sg_tutorial_step"] = 0
            st.rerun()


def tt(term: str, definition: str, color: str = "#00d4aa") -> str:
    """
    Item 10 — Inline glossary tooltip. Wraps a jargon term with a dashed
    underline and HTML title attribute (hover tooltip).
    Returns HTML string: <span title="definition">term</span>
    """
    safe_def = definition.replace('"', '&quot;').replace("'", "&#39;")
    return (
        f'<span title="{safe_def}" style="border-bottom:1px dashed {color};'
        f'cursor:help;color:inherit">{term}</span>'
    )


def freshness_dot_html(last_updated_ts: float | None, max_age_sec: int,
                        label: str) -> str:
    """
    Item 17 — Colored freshness dot with tooltip.
    Returns HTML string: colored circle + label.
    last_updated_ts: unix timestamp of last update (None = unknown/stale)
    max_age_sec: threshold for 'fresh' (green). amber at 2×, red at 4×.
    """
    import time as _time
    if last_updated_ts is None:
        color, tip = "#6b7280", f"{label}: unknown age"
    else:
        age = _time.time() - last_updated_ts
        if age < max_age_sec:
            color, tip = "#22c55e", f"{label}: {int(age//60)}m ago (fresh)"
        elif age < max_age_sec * 2:
            color, tip = "#f59e0b", f"{label}: {int(age//60)}m ago (aging)"
        else:
            color, tip = "#ef4444", f"{label}: {int(age//60)}m ago (stale)"
    return (
        f'<span title="{tip}" style="display:inline-block;width:8px;height:8px;'
        f'border-radius:50%;background:{color};margin-right:4px;'
        f'cursor:help;vertical-align:middle"></span>'
        f'<span style="font-size:11px;color:rgba(168,180,200,0.5)">{label}</span>'
    )


def signal_rank_list_html(results: list, max_show: int | None = None) -> str:
    """
    Item 8 — Beginner-friendly ranked signal list to replace the Plotly heatmap.
    Renders a compact scrollable card-list sorted by confidence descending.
    Each row shows: rank, coin name, direction badge (▲/▼/■), confidence bar, entry/stop.
    max_show=None means show all results (no cap).
    """
    if not results:
        return '<div style="color:rgba(168,180,200,0.5);padding:12px">No signals yet — run a scan first.</div>'

    sorted_r = sorted(results, key=lambda x: x.get("confidence_avg_pct", 0), reverse=True)
    if max_show is not None:
        sorted_r = sorted_r[:max_show]

    rows_html = ""
    for i, r in enumerate(sorted_r, 1):
        pair  = r.get("pair", "?")
        coin  = pair.replace("/USDT", "").replace("/USD", "")
        conf  = float(r.get("confidence_avg_pct", 0) or 0)
        d     = (r.get("direction") or "NEUTRAL").upper()
        entry = r.get("entry")
        stop  = r.get("stop_loss")
        hc    = r.get("high_conf", False)

        if "BUY" in d:
            dir_color  = "#00d4aa"
            dir_symbol = "▲"
            dir_label  = "BUY" if "STRONG" not in d else "STRONG BUY"
            bar_color  = "#00d4aa"
        elif "SELL" in d:
            dir_color  = "#ef4444"
            dir_symbol = "▼"
            dir_label  = "SELL" if "STRONG" not in d else "STRONG SELL"
            bar_color  = "#ef4444"
        else:
            dir_color  = "#888"
            dir_symbol = "■"
            dir_label  = "WAIT"
            bar_color  = "#888"

        score    = max(1, min(10, round(conf / 10)))
        bar_w    = max(4, int(conf))
        hc_badge = ' <span style="background:rgba(0,212,170,0.15);color:#00d4aa;font-size:9px;padding:1px 5px;border-radius:4px;font-weight:700">⚡ TOP PICK</span>' if hc else ""

        entry_str = f"${entry:,.4f}" if entry else "—"
        stop_str  = f"${stop:,.4f}"  if stop  else "—"

        rows_html += f"""
<div style="display:flex;align-items:center;gap:10px;padding:8px 10px;
            border-bottom:1px solid rgba(255,255,255,0.04);
            background:{'rgba(0,212,170,0.03)' if hc else 'transparent'}">
  <span style="color:rgba(168,180,200,0.35);font-size:11px;min-width:18px;text-align:right">{i}</span>
  <span style="font-size:13px;font-weight:700;color:#e2e8f0;min-width:52px">{coin}</span>
  <span style="background:rgba({('0,212,170' if 'BUY' in d else ('246,70,93' if 'SELL' in d else '136,136,136'))},0.15);
              color:{dir_color};border-radius:5px;padding:2px 7px;font-size:11px;
              font-weight:700;min-width:70px;text-align:center">{dir_symbol} {dir_label}</span>
  <div style="flex:1;background:rgba(255,255,255,0.06);border-radius:4px;height:6px;position:relative">
    <div style="width:{bar_w}%;background:{bar_color};border-radius:4px;height:6px;
                transition:width 0.3s ease"></div>
  </div>
  <span style="font-size:11px;color:{bar_color};font-weight:700;min-width:32px;text-align:right">{score}/10</span>
  <span style="font-size:10px;color:rgba(168,180,200,0.5);min-width:80px">▶ {entry_str}</span>
  <span style="font-size:10px;color:rgba(246,70,93,0.7);min-width:80px">✕ {stop_str}</span>
  {hc_badge}
</div>"""

    return f"""
<div style="background:#0d0e14;border:1px solid rgba(255,255,255,0.07);border-radius:10px;
            overflow:hidden;margin-bottom:8px">
  <div style="display:flex;gap:10px;padding:6px 10px;background:rgba(255,255,255,0.03);
              border-bottom:1px solid rgba(255,255,255,0.06);font-size:10px;
              color:rgba(168,180,200,0.4);font-weight:600;text-transform:uppercase;
              letter-spacing:0.6px">
    <span style="min-width:18px">#</span>
    <span style="min-width:52px">Coin</span>
    <span style="min-width:70px">Signal</span>
    <span style="flex:1">Strength</span>
    <span style="min-width:32px;text-align:right">Score</span>
    <span style="min-width:80px">Entry</span>
    <span style="min-width:80px">Stop</span>
  </div>
  <div style="max-height:460px;overflow-y:auto">{rows_html}</div>
</div>"""


def arb_opportunity_story_html(pair: str, buy_ex: str, sell_ex: str,
                                net_spread_pct: float,
                                buy_price: float, sell_price: float) -> str:
    """
    Item 13 — Arbitrage opportunity as a plain-English story card.
    """
    profit_per_1k = net_spread_pct / 100 * 1000
    color = "#00d4aa" if net_spread_pct >= 0.5 else "#f59e0b"
    return f"""
<div style="background:rgba(17,24,40,0.95);border:1px solid {color}33;
            border-left:3px solid {color};border-radius:12px;
            padding:16px 20px;margin:8px 0;font-size:13px;
            color:rgba(200,210,230,0.9)">
  <div style="font-weight:700;font-size:15px;color:#e2e8f0;margin-bottom:6px">
    {pair.replace('/USDT','')} &nbsp;
    <span style="color:{color};font-size:13px">{net_spread_pct:.2f}% profit</span>
  </div>
  Buy on <strong style="color:#e2e8f0">{buy_ex}</strong> at
  <strong style="color:#e2e8f0">${buy_price:,.4f}</strong>,
  sell on <strong style="color:#e2e8f0">{sell_ex}</strong> at
  <strong style="color:#e2e8f0">${sell_price:,.4f}</strong> —
  pocket <strong style="color:{color}">{net_spread_pct:.2f}%</strong> after fees.<br/>
  <span style="font-size:11px;color:rgba(168,180,200,0.5)">
    On a $1,000 trade that's approximately
    <strong style="color:{color}">${profit_per_1k:.2f}</strong>.
  </span>
</div>"""


# ── Signal Badge — Shape Encoding (Phase 3, item 22) ──────────────────────────

def signal_badge_html(direction: str, label: str = "") -> str:
    """Return HTML for a shape+color signal badge (color-blind safe).

    ▲ BUY (teal) / ▼ SELL (red) / ■ NEUTRAL (gray)
    Shape + color always combined — never color alone.
    """
    _dir = direction.upper().strip()
    if _dir in {"BUY", "BULLISH", "BULL", "LONG", "STRONG_BUY"}:
        _shape, _bg, _txt, _border = "▲", "rgba(0,212,170,0.12)", "#00d4aa", "rgba(0,212,170,0.35)"
        _default = "BUY"
    elif _dir in {"SELL", "BEARISH", "BEAR", "SHORT", "STRONG_SELL"}:
        _shape, _bg, _txt, _border = "▼", "rgba(246,70,93,0.12)", "#ef4444", "rgba(246,70,93,0.35)"
        _default = "SELL"
    else:
        _shape, _bg, _txt, _border = "■", "rgba(100,116,139,0.12)", "#64748b", "rgba(100,116,139,0.3)"
        _default = "NEUTRAL"
    _display = label if label else _default
    return (
        f"<span style='display:inline-flex;align-items:center;gap:4px;"
        f"background:{_bg};border:1px solid {_border};border-radius:6px;"
        f"padding:2px 8px;font-size:0.85rem;font-weight:700;color:{_txt};'>"
        f"{_shape} {_display}</span>"
    )


# ── "What does this mean?" Panel (Phase 3, item 21) ───────────────────────────

def render_what_this_means(message: str, title: str = "What does this mean for me?") -> None:
    """Render a plain-English explanation panel. Only shown at Beginner level."""
    if st.session_state.get("user_level", "beginner") != "beginner":
        return
    st.info(f"💡 **{title}**  \n{message}")


# ── Fear & Greed Trend (Phase 3, item 26) ─────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
def _fetch_fng_30d_avg() -> float:
    """Fetch 30-day average Fear & Greed from alternative.me. Cached 60 min."""
    try:
        import requests as _req
        _r = _req.get(
            "https://api.alternative.me/fng/?limit=30",
            timeout=6,
            headers={"Accept": "application/json"},
        )
        if _r.status_code == 200:
            _data = _r.json().get("data", [])
            _vals = [int(d["value"]) for d in _data if "value" in d]
            if _vals:
                return sum(_vals) / len(_vals)
    except Exception as _fng30_err:
        logger.debug("[UI] FNG 30d avg fetch failed: %s", _fng30_err)
    return 50.0


def render_fear_greed_trend_sg(user_level: str = "beginner") -> None:
    """Render Fear & Greed current + 7-day avg + 30-day avg.

    Uses data_feeds.get_fear_greed_index() for the current value and 7-day avg.
    Fetches 30 days directly from alternative.me via _fetch_fng_30d_avg() (cached 60 min).
    """
    _cur, _avg7, _avg30 = 50, 50.0, 50.0
    try:
        from data_feeds import get_fear_greed_index as _fg_fetch
        _fg = _fg_fetch(days=7)
        _cur  = _fg.get("value", 50)
        _hist = _fg.get("history_7d", [])
        _vals7 = [int(h["value"]) for h in _hist if "value" in h]
        _avg7  = sum(_vals7) / max(1, len(_vals7)) if _vals7 else float(_cur)
    except Exception as _fng_err:
        logger.debug("[UI] Fear & Greed 7d fetch failed: %s", _fng_err)

    # 30-day average: cached API call (1-hour TTL) — was uncached, hitting API on every rerun
    try:
        _avg30 = _fetch_fng_30d_avg()
    except Exception:
        _avg30 = _avg7

    def _fg_label(v: float) -> tuple[str, str]:
        if v <= 25:  return "Extreme Fear",  "#ef4444"
        if v <= 45:  return "Fear",           "#f59e0b"
        if v <= 55:  return "Neutral",        "#64748b"
        if v <= 75:  return "Greed",          "#f59e0b"
        return "Extreme Greed", "#22c55e"

    _cl, _cc = _fg_label(_cur)
    _7l, _7c = _fg_label(_avg7)
    _30l, _30c = _fg_label(_avg30)

    _c1, _c2, _c3 = st.columns(3)
    for _col, _val, _lbl, _chex, _period in [
        (_c1, float(_cur), _cl,  _cc,  "Now"),
        (_c2, _avg7,       _7l,  _7c,  "7-Day Avg"),
        (_c3, _avg30,      _30l, _30c, "30-Day Avg"),
    ]:
        with _col:
            st.markdown(
                f"<div style='text-align:center;padding:12px;"
                f"background:var(--bg-1);border-radius:8px;border:1px solid var(--border);'>"
                f"<div style='font-size:0.62rem;color:var(--text-3);text-transform:uppercase;"
                f"letter-spacing:0.8px;margin-bottom:4px'>{_period}</div>"
                f"<div style='font-size:1.9rem;font-weight:800;color:{_chex};"
                f"font-family:var(--font-mono)'>{_val:.0f}</div>"
                f"<div style='font-size:0.85rem;color:{_chex};margin-top:2px'>{_lbl}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if user_level == "beginner":
        st.caption(
            f"💡 Fear & Greed measures crowd emotion — 0 = extreme panic (often a buy signal), "
            f"100 = extreme euphoria (often a sell signal). Current: **{_cur}** ({_cl})."
        )


# ── Light/Dark mode toggle helper (Phase 3, item 18) ──────────────────────────

def render_theme_toggle_sg() -> None:
    """Render a sun/moon theme toggle for SuperGrok sidebar.

    Stores theme in st.session_state["_sg_theme"].
    The body.light-mode class is applied by inject_css() via st.iframe()
    on the same rerun — no separate JS injection needed here.
    """
    _is_light = st.session_state.get("_sg_theme") == "light"
    if st.sidebar.button(
        "☀" if _is_light else "🌙",
        key="_sg_theme_toggle",
        help="Switch to light mode" if not _is_light else "Switch to dark mode",
    ):
        st.session_state["_sg_theme"] = "dark" if _is_light else "light"
        # Reset CSS injection guard so inject_css() re-fires on next rerun
        st.session_state["_css_injected"] = False
        st.rerun()


# ── Coin Universe (Phase 3, item 28) ──────────────────────────────────────────

_SG_MUST_HAVE: list[str] = ["XRP", "XLM", "XDC", "CC", "HBAR", "SHX", "ZBCN"]
_SG_STABLECOINS: frozenset[str] = frozenset({
    "usdt","usdc","dai","busd","tusd","fdusd","usdd","frax","lusd",
    "usdp","gusd","crvusd","pyusd","eurc",
})


# ══════════════════════════════════════════════════════════════════════════════
# S-UPGRADES: S1–S10  (Sprint — SuperGrok)
# ══════════════════════════════════════════════════════════════════════════════

def render_market_regime_banner(results: list, fng_value: int = 50,
                                 macro_regime: str = "MACRO_NEUTRAL",
                                 altcoin_season: str = "MIXED") -> None:
    """S10 — Market Regime Dashboard banner.

    Shows the overall market regime (BULL / BEAR / SIDEWAYS) computed from:
    - Majority BTC/ETH signal direction across all scan results
    - Fear & Greed value
    - Macro regime flag
    Displayed at the top of the Dashboard section so users instantly know
    the big-picture direction before looking at individual signals.
    """
    if not results:
        return
    import streamlit as _st

    # Determine overall bias from scan results
    _buy_count  = sum(1 for r in results if "BUY"  in r.get("direction", ""))
    _sell_count = sum(1 for r in results if "SELL" in r.get("direction", ""))
    _total      = len(results)
    _buy_pct    = _buy_count  / _total * 100 if _total else 50
    _sell_pct   = _sell_count / _total * 100 if _total else 50

    # Regime label
    if _buy_pct >= 60 and fng_value >= 45:
        _regime   = "BULL MARKET"
        _icon     = "📈"
        _color    = "#22c55e"
        _bg       = "rgba(34,197,94,0.08)"
        _border   = "rgba(34,197,94,0.3)"
        _desc     = f"{_buy_pct:.0f}% of signals bullish · F&G {fng_value} · {altcoin_season}"
    elif _sell_pct >= 60 or fng_value <= 25:
        _regime   = "BEAR MARKET"
        _icon     = "📉"
        _color    = "#ef4444"
        _bg       = "rgba(239,68,68,0.08)"
        _border   = "rgba(239,68,68,0.3)"
        _desc     = f"{_sell_pct:.0f}% of signals bearish · F&G {fng_value} · {macro_regime.replace('_',' ')}"
    else:
        _regime   = "SIDEWAYS / MIXED"
        _icon     = "➡️"
        _color    = "#f59e0b"
        _bg       = "rgba(245,158,11,0.08)"
        _border   = "rgba(245,158,11,0.3)"
        _desc     = f"{_buy_pct:.0f}% bullish · {_sell_pct:.0f}% bearish · F&G {fng_value}"

    _macro_badge = ""
    if macro_regime and macro_regime != "MACRO_NEUTRAL":
        _mc = macro_regime.replace("_", " ")
        _macro_badge = (
            f"<span style='background:rgba(99,102,241,0.15);border:1px solid rgba(99,102,241,0.3);"
            f"border-radius:12px;padding:1px 8px;font-size:11px;color:#a78bfa;margin-left:8px'>"
            f"Macro: {_mc}</span>"
        )

    _st.markdown(
        f"<div style='background:{_bg};border:1px solid {_border};border-left:4px solid {_color};"
        f"border-radius:10px;padding:12px 18px;margin-bottom:16px;display:flex;align-items:center;"
        f"justify-content:space-between;flex-wrap:wrap;gap:8px'>"
        f"<div>"
        f"<span style='font-size:18px;font-weight:800;color:{_color}'>{_icon} {_regime}</span>"
        f"{_macro_badge}"
        f"</div>"
        f"<div style='color:#9ca3af;font-size:12px'>{_desc}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_ttm_squeeze_panel(sparkline_data: dict, results: list,
                              user_level: str = "beginner") -> None:
    """S1 — TTM Squeeze Momentum panel.

    Identifies pairs with compressed Bollinger Bands (squeeze state) — a classic
    signal that a large breakout move is imminent. Uses sparkline closes to compute
    BB width ratio. Narrow BB width (<2% of price) = squeeze active.

    Args:
        sparkline_data: {pair: [close prices]} dict from the scan overview fetch
        results: list of scan result dicts (for direction context)
        user_level: 'beginner' | 'intermediate' | 'advanced'
    """
    import streamlit as _st
    import numpy as _np

    def _compute_squeeze(closes: list) -> dict:
        """Compute TTM Squeeze proxy from close prices."""
        if len(closes) < 10:
            return {"state": "NO_DATA", "bb_width_pct": None, "momentum": 0}
        arr = _np.array(closes, dtype=float)
        _mean  = float(_np.mean(arr[-20:])) if len(arr) >= 20 else float(_np.mean(arr))
        _std   = float(_np.std(arr[-20:]))  if len(arr) >= 20 else float(_np.std(arr))
        _bb_w  = (_std * 2) / _mean * 100 if _mean > 0 else 0  # BB width as % of price
        _mom   = float(arr[-1] - arr[-5]) / arr[-5] * 100 if len(arr) >= 5 and arr[-5] > 0 else 0
        if _bb_w < 3.0:
            _state = "SQUEEZE"
        elif _bb_w < 6.0:
            _state = "COMPRESSION"
        else:
            _state = "EXPANDED"
        return {"state": _state, "bb_width_pct": round(_bb_w, 2), "momentum": round(_mom, 2)}

    squeeze_pairs = []
    for r in results:
        p      = r["pair"]
        closes = sparkline_data.get(p, [])
        sq     = _compute_squeeze(closes)
        dir_   = r.get("direction", "—")
        if sq["state"] in ("SQUEEZE", "COMPRESSION"):
            squeeze_pairs.append({"pair": p, "direction": dir_, **sq})

    if user_level == "beginner" and not squeeze_pairs:
        return  # hide empty section from beginners

    section_header(
        "TTM Squeeze Momentum",
        "Pairs with compressed volatility — breakout imminent when BB width narrows to extreme lows",
        icon="🗜️",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "When a coin's price range gets very narrow (like a coiled spring), "
            "it often means a big move is coming. Green spring = possible big BUY coming. "
            "Red spring = possible big DROP coming. The direction shows what our model thinks.",
            title="What does squeeze mean?",
        )

    if not squeeze_pairs:
        _st.success("▲ No squeeze states detected — all pairs show normal volatility.")
        return

    _cols = _st.columns(min(len(squeeze_pairs), 4))
    for _ci, _sp in enumerate(squeeze_pairs[:8]):
        _col    = "#f59e0b" if _sp["state"] == "COMPRESSION" else "#ef4444"
        _dir_cl = "#22c55e" if "BUY" in _sp["direction"] else "#ef4444" if "SELL" in _sp["direction"] else "#9ca3af"
        with _cols[_ci % 4]:
            _st.markdown(
                f"<div style='background:rgba(0,0,0,0.25);border:1px solid {_col}44;"
                f"border-top:2px solid {_col};border-radius:8px;padding:10px 12px;margin-bottom:8px'>"
                f"<div style='font-size:12px;color:#9ca3af'>{_sp['pair'].replace('/USDT','')}</div>"
                f"<div style='font-size:14px;font-weight:700;color:{_col}'>🗜 {_sp['state']}</div>"
                f"<div style='font-size:11px;color:{_dir_cl};margin-top:4px'>Signal: {_sp['direction']}</div>"
                f"<div style='font-size:10px;color:#475569;margin-top:2px'>"
                f"BB width: {_sp['bb_width_pct']:.2f}% · Mom: {_sp['momentum']:+.1f}%</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    _st.caption(
        f"{len(squeeze_pairs)} pair(s) in squeeze/compression. "
        "BB width <3% = SQUEEZE (breakout imminent). 3–6% = COMPRESSION. "
        "Momentum = 5-bar price change %."
    )


def render_hurst_exponent_panel(sparkline_data: dict, results: list,
                                 user_level: str = "beginner") -> None:
    """S2 — Hurst Exponent Regime Filter.

    H > 0.6  = trending market (momentum strategies work)
    H ≈ 0.5  = random walk (signals unreliable)
    H < 0.4  = mean-reverting (fade extremes)

    Computed via R/S analysis on sparkline close prices.
    """
    import streamlit as _st
    import numpy as _np

    def _hurst(closes: list) -> float:
        """Estimate Hurst exponent via rescaled range (R/S) analysis."""
        if len(closes) < 20:
            return 0.5
        arr = _np.log(_np.array(closes, dtype=float) + 1e-9)
        n   = len(arr)
        # R/S across lags 4, 8, 16
        rs_pairs = []
        for lag in [4, 8, 16]:
            if n < lag * 2:
                continue
            splits = [arr[i:i+lag] for i in range(0, n - lag, lag)]
            if not splits:
                continue
            rs_vals = []
            for seg in splits:
                m = float(_np.mean(seg))
                dev = seg - m
                cum = _np.cumsum(dev)
                r   = float(cum.max() - cum.min())
                s   = float(_np.std(seg, ddof=1)) or 1e-9
                rs_vals.append(r / s)
            rs_pairs.append((float(_np.log(lag)), float(_np.log(_np.mean(rs_vals) + 1e-9))))
        if len(rs_pairs) < 2:
            return 0.5
        x = _np.array([p[0] for p in rs_pairs])
        y = _np.array([p[1] for p in rs_pairs])
        h = float(_np.polyfit(x, y, 1)[0])
        return max(0.0, min(1.0, h))

    section_header(
        "Hurst Exponent Regime Filter",
        "H>0.6 = trending (follow signals) · H≈0.5 = random · H<0.4 = mean-reverting (fade signals)",
        icon="〽️",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "The Hurst number tells you whether a coin is in a 'trend mode' or 'bounce mode'. "
            "Above 0.6 means the trend is real — follow our signals. "
            "Below 0.4 means prices tend to reverse — be cautious about following breakouts.",
            title="What is the Hurst number?",
        )

    _hurst_rows = []
    for r in results[:12]:
        p      = r["pair"]
        closes = sparkline_data.get(p, [])
        h      = _hurst(closes)
        _label = "TRENDING" if h > 0.6 else "RANDOM" if h > 0.4 else "MEAN-REVERTING"
        _color = "#22c55e" if h > 0.6 else "#9ca3af" if h > 0.4 else "#f59e0b"
        _strat = "▲ Follow signals" if h > 0.6 else "■ Reduce position size" if h > 0.4 else "▼ Fade extremes"
        _hurst_rows.append({
            "Pair":    p.replace("/USDT", ""),
            "H":       f"{h:.3f}",
            "Regime":  _label,
            "Signal":  r.get("direction", "—"),
            "Strategy": _strat,
        })

    if _hurst_rows:
        import pandas as _pd
        _st.dataframe(_pd.DataFrame(_hurst_rows), width='stretch', hide_index=True)
        _st.caption("Computed via R/S analysis on 24h sparkline closes. H=0.5 = random walk baseline.")


def render_rsi_macd_divergence_panel(results: list, user_level: str = "beginner") -> None:
    """S3 — RSI+MACD Divergence Auto-Detector.

    Scans tf_data for existing macd_div signals from the model engine.
    Displays pairs with bullish/bearish divergences as trade alerts.
    """
    import streamlit as _st

    section_header(
        "RSI/MACD Divergence Alerts",
        "Pairs where price direction conflicts with momentum — classic reversal signal",
        icon="⚡",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "A divergence happens when a coin's price goes up but its momentum is going down "
            "(or vice versa). This often means the move is running out of steam and a reversal is near. "
            "Bullish divergence = price making lower lows but momentum making higher lows → possible bounce.",
            title="What is a divergence?",
        )

    _div_alerts = []
    for r in results:
        _tfs = r.get("timeframes") or {}
        for tf, td in _tfs.items():
            _macd_div = str(td.get("macd_div") or "").lower()
            if "bullish" in _macd_div or "bearish" in _macd_div:
                _is_bull = "bullish" in _macd_div
                _div_alerts.append({
                    "pair":    r["pair"],
                    "tf":      tf,
                    "type":    "BULLISH" if _is_bull else "BEARISH",
                    "macd_div": td.get("macd_div", ""),
                    "rsi":     td.get("rsi", "—"),
                    "direction": r.get("direction", "—"),
                })

    if not _div_alerts:
        _st.info("No RSI/MACD divergences detected in current scan data. Run a scan first.")
        return

    for _da in _div_alerts[:10]:
        _is_bull = _da["type"] == "BULLISH"
        _col     = "#22c55e" if _is_bull else "#ef4444"
        _icon    = "▲" if _is_bull else "▼"
        _st.markdown(
            f"<div style='background:rgba(0,0,0,0.2);border-left:3px solid {_col};"
            f"border-radius:6px;padding:8px 12px;margin-bottom:6px;font-size:13px'>"
            f"<b style='color:{_col}'>{_icon} {_da['type']} DIVERGENCE</b> · "
            f"<b>{_da['pair'].replace('/USDT','')}</b> · {_da['tf']} · "
            f"RSI: <b>{_da['rsi']}</b> · "
            f"Model signal: <span style='color:#9ca3af'>{_da['direction']}</span><br>"
            f"<span style='font-size:11px;color:#475569'>{_da['macd_div']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    _st.caption(f"{len(_div_alerts)} divergence(s) detected across all pairs and timeframes.")


def render_funding_rate_arb_panel(results: list, user_level: str = "beginner") -> None:
    """S4 — Funding Rate Arb Signal.

    Identifies pairs with extreme funding rates where a funding arbitrage
    opportunity exists (extreme positive = shorts paid, extreme negative = longs paid).
    """
    import streamlit as _st

    section_header(
        "Funding Rate Arb Signals",
        "Extreme funding rates create risk-free-ish arb: spot vs perp hedge to collect funding",
        icon="💰",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "Funding rate is a fee that traders pay each other in perpetual futures markets. "
            "When it's very high (>0.1%), longs are paying shorts a lot — you can earn that fee "
            "by buying spot AND shorting the same amount in futures. "
            "This is called 'cash-and-carry arbitrage' — it's not risk-free but has low directional risk.",
            title="What is funding rate arbitrage?",
        )

    _fr_alerts = []
    for r in results:
        _tfs   = r.get("timeframes") or {}
        _fund  = str(_tfs.get("1h", {}).get("funding") or "").strip()
        if not _fund or _fund in ("N/A", "—", ""):
            continue
        try:
            # Parse funding string: usually "0.0100% 8h (LONG PAYS)" or similar
            import re as _re2
            _m = _re2.search(r"([+-]?\d+\.?\d*)", _fund)
            if not _m:
                continue
            _fr_pct = float(_m.group(1))
        except Exception:
            continue

        if abs(_fr_pct) >= 0.05:  # 0.05% threshold for notable funding
            _arb_type  = "LONGS PAY" if _fr_pct > 0 else "SHORTS PAY"
            _arb_col   = "#f59e0b" if _fr_pct > 0 else "#22c55e"
            _arb_action = ("Buy spot + Short perp to collect funding" if _fr_pct > 0.1
                           else "Short spot + Long perp to collect funding" if _fr_pct < -0.05
                           else "Watch — elevated but not extreme")
            _fr_alerts.append({
                "pair":       r["pair"],
                "fr_pct":     _fr_pct,
                "fr_raw":     _fund,
                "arb_type":   _arb_type,
                "arb_color":  _arb_col,
                "arb_action": _arb_action,
                "confidence": r.get("confidence_avg_pct", 0),
            })

    _fr_alerts.sort(key=lambda x: abs(x["fr_pct"]), reverse=True)

    if not _fr_alerts:
        _st.info("No extreme funding rates detected — market is balanced. Run a scan to populate.")
        return

    for _fa in _fr_alerts[:8]:
        _badge_col = "#ef4444" if _fa["fr_pct"] > 0.15 else "#f59e0b" if _fa["fr_pct"] > 0.05 else "#22c55e"
        _st.markdown(
            f"<div style='background:rgba(0,0,0,0.2);border-left:3px solid {_fa['arb_color']};"
            f"border-radius:6px;padding:8px 12px;margin-bottom:6px;font-size:13px'>"
            f"<b>{_fa['pair'].replace('/USDT','')}</b> · "
            f"<span style='color:{_badge_col}'><b>{_fa['fr_pct']:+.4f}%</b></span> · "
            f"<span style='color:{_fa['arb_color']}'>{_fa['arb_type']}</span><br>"
            f"<span style='font-size:11px;color:#9ca3af'>"
            f"Arb: {_fa['arb_action']}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    _st.caption(
        "Funding >0.1%: longs pay shorts — buy spot + short perp to collect. "
        "Funding <-0.05%: shorts pay longs — reverse arb. Not risk-free. "
        "Basis risk and liquidation risk apply."
    )


def render_social_momentum_panel(results: list, user_level: str = "beginner") -> None:
    """S6 — Social Momentum Proxy.

    Uses CoinGecko trending flag + sentiment data from scan results to build
    a social momentum proxy score per pair. Trending + bullish signal = strong
    momentum. Trending + sell signal = potential pump-and-dump warning.
    """
    import streamlit as _st

    section_header(
        "Social Momentum",
        "Trending coins + sentiment signals — social momentum proxy",
        icon="🔥",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "When lots of people are talking about a coin, it often moves more than usual. "
            "This panel shows which coins are trending on social media + exchanges. "
            "Trending + BUY signal = strong momentum. Trending + SELL signal = caution — could be FOMO.",
            title="What is social momentum?",
        )

    _social_rows = []
    for r in results:
        _is_trending = r.get("trending", False)
        _dir         = r.get("direction", "—")
        _conf        = r.get("confidence_avg_pct", 50)
        _fng         = r.get("fng_value", 50)
        # Social score: 0-100
        _s_score  = 50
        if _is_trending:  _s_score += 30
        if "BUY"  in _dir: _s_score += min(20, (_conf - 50) / 2) if _conf > 50 else 0
        if "SELL" in _dir: _s_score -= min(20, (50 - _conf) / 2) if _conf < 50 else 0
        _s_score = max(0, min(100, round(_s_score)))

        _momentum = ("🔥 HOT"     if _is_trending and "BUY" in _dir
                     else "⚠️ FOMO" if _is_trending and "SELL" in _dir
                     else "🔥 Trending" if _is_trending
                     else "📊 Normal")
        _social_rows.append({
            "Pair":          r["pair"].replace("/USDT", ""),
            "Social Score":  _s_score,
            "Trending":      "🔥 Yes" if _is_trending else "—",
            "Signal":        _dir,
            "Momentum":      _momentum,
        })

    _social_rows.sort(key=lambda x: x["Social Score"], reverse=True)

    import pandas as _pd
    if _social_rows:
        _st.dataframe(_pd.DataFrame(_social_rows[:12]), width='stretch', hide_index=True)
        _hot = [r for r in _social_rows if "HOT" in r["Momentum"]]
        _fomo = [r for r in _social_rows if "FOMO" in r["Momentum"]]
        if _hot:
            _st.success(f"▲ Hot momentum: {', '.join(r['Pair'] for r in _hot[:3])}")
        if _fomo:
            _st.warning(f"⚠️ FOMO risk (trending but sell signal): {', '.join(r['Pair'] for r in _fomo[:3])}")
    _st.caption(
        "Social score: 50 base + 30 for CoinGecko trending + ±20 for signal direction. "
        "Source: CoinGecko trending API + scan signals."
    )


def render_github_dev_activity_panel(user_level: str = "beginner") -> None:
    """S7 — GitHub Dev Activity Signal.

    Fetches commit activity (last 4 weeks) for major crypto protocol repos.
    Active development is a positive long-term signal (protocol is maintained).
    """
    import streamlit as _st

    section_header(
        "GitHub Dev Activity",
        "Commit activity in crypto protocol repos — active development = healthy project",
        icon="⚙️",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "The best crypto projects are actively developed — bugs fixed, features added. "
            "This panel shows how many code changes were made in the last 4 weeks. "
            "More commits = more active team. A dead project often means the team has given up.",
            title="Why does GitHub activity matter?",
        )

    try:
        import data_feeds as _df_sg
        with _st.spinner("Fetching GitHub activity…"):
            _gh = _df_sg.fetch_github_dev_activity()
    except Exception as _ghe:
        import logging as _lg_gh
        _lg_gh.getLogger(__name__).warning("[GitHub] fetch error: %s", _ghe)
        _st.warning("GitHub activity data temporarily unavailable — try refreshing.")
        return

    _items = [(k, v) for k, v in _gh.items() if k not in ("timestamp", "error") and isinstance(v, dict)]
    _items.sort(key=lambda x: x[1].get("commits_4w", 0), reverse=True)

    if not _items:
        _st.info("GitHub data unavailable — check connectivity. Unauthenticated limit: 60 req/hr.")
        return

    _gh_rows = []
    for _sym, _d in _items:
        _sig = _d.get("signal", "—")
        _sig_col = {
            "VERY_ACTIVE": "#22c55e", "ACTIVE": "#84cc16",
            "MODERATE": "#f59e0b",   "LOW": "#f59e0b", "STALLED": "#ef4444",
        }.get(_sig, "#9ca3af")
        _gh_rows.append({
            "Symbol":       _sym,
            "Repo":         _d.get("repo", "—"),
            "Commits 4w":   _d.get("commits_4w", 0),
            "Open Issues":  _d.get("open_issues", "—"),
            "Stars":        f"{_d.get('stars', 0):,}",
            "Activity":     _sig,
        })

    import pandas as _pd
    _st.dataframe(_pd.DataFrame(_gh_rows), width='stretch', hide_index=True)
    _stalled = [r["Symbol"] for r in _gh_rows if r["Activity"] == "STALLED"]
    if _stalled:
        _st.warning(f"⚠️ Low/stalled dev activity: {', '.join(_stalled)}")
    _ts = _gh.get("timestamp", "")
    _st.caption(f"Source: GitHub public API · unauthenticated (60 req/hr limit) · {_ts}")


def render_trader_investor_split(results: list, user_level: str = "beginner") -> None:
    """S8 — Trader vs Investor Grade split.

    Splits signals into:
    - Trader view (1h/4h timeframes) — short-term entry timing
    - Investor view (1d/1w timeframes) — macro trend direction
    Shows agreement/disagreement between the two horizons.
    """
    import streamlit as _st

    section_header(
        "Trader vs Investor Signals",
        "Short-term (1h/4h) vs long-term (1d/1w) signal alignment",
        icon="⏳",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "Traders look at short time periods (hours). Investors look at long time periods (days/weeks). "
            "When both say BUY, that's a strong signal. When they disagree, wait — the market is confused. "
            "Green = both agree. Orange = only one agrees. Red = they disagree.",
            title="Trader vs Investor — what does it mean?",
        )

    _split_rows = []
    for r in results:
        _tfs = r.get("timeframes") or {}
        # Trader TFs: 1h, 4h
        _trader_dirs = [
            _tfs.get("1h", {}).get("direction", ""),
            _tfs.get("4h", {}).get("direction", ""),
        ]
        _investor_dirs = [
            _tfs.get("1d", {}).get("direction", ""),
            _tfs.get("1w", {}).get("direction", ""),
        ]
        _trader_dirs   = [d for d in _trader_dirs   if d and d not in ("N/A", "NO DATA", "LOW VOL")]
        _investor_dirs = [d for d in _investor_dirs if d and d not in ("N/A", "NO DATA", "LOW VOL")]

        if not _trader_dirs and not _investor_dirs:
            continue

        def _majority(dirs):
            if not dirs:
                return "—"
            _buys  = sum(1 for d in dirs if "BUY" in d)
            _sells = sum(1 for d in dirs if "SELL" in d)
            if _buys > _sells:   return "▲ BUY"
            if _sells > _buys:   return "▼ SELL"
            return "■ MIXED"

        _t_dir = _majority(_trader_dirs)
        _i_dir = _majority(_investor_dirs)

        _agree = (("BUY" in _t_dir and "BUY" in _i_dir) or
                  ("SELL" in _t_dir and "SELL" in _i_dir))
        _agree_col = "#22c55e" if _agree else "#f59e0b" if _t_dir != _i_dir else "#ef4444"
        _grade = "ALIGNED" if _agree else "MIXED"

        _split_rows.append({
            "Pair":           r["pair"].replace("/USDT", ""),
            "Trader (1h/4h)": _t_dir,
            "Investor (1d/1w)": _i_dir,
            "Alignment":      f"{'✅' if _agree else '⚠️'} {_grade}",
            "Confidence":     f"{r.get('confidence_avg_pct', 0):.0f}%",
        })

    if _split_rows:
        import pandas as _pd
        _st.dataframe(_pd.DataFrame(_split_rows), width='stretch', hide_index=True)
        _aligned = sum(1 for r in _split_rows if "ALIGNED" in r["Alignment"])
        _st.caption(
            f"{_aligned}/{len(_split_rows)} pairs aligned across both horizons. "
            "Strong signals occur when Trader AND Investor timeframes agree."
        )
    else:
        _st.info("Run a multi-timeframe scan to see trader vs investor split.")


def render_threshold_alerts_panel(results: list, user_level: str = "beginner") -> None:
    """S9 — In-App Threshold Alerts.

    User-configurable thresholds shown in the UI.
    Flags pairs that have crossed configured RSI / confidence thresholds.
    """
    import streamlit as _st

    section_header(
        "Custom Threshold Alerts",
        "Configure RSI and signal strength thresholds — get notified when coins cross your criteria",
        icon="🔔",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "Set your own rules for when you want to be alerted. "
            "For example: 'Alert me when a coin has RSI below 30 AND the model says BUY'. "
            "These are personal filters you control.",
            title="What are threshold alerts?",
        )

    with _st.expander("Configure alert thresholds", expanded=False):
        _thr_col1, _thr_col2 = _st.columns(2)
        with _thr_col1:
            _rsi_ob  = _st.slider("RSI Overbought", 60, 90, 70, key="thr_rsi_ob",
                                   help="Alert when RSI is above this — overbought warning")
            _rsi_os  = _st.slider("RSI Oversold",   10, 50, 30, key="thr_rsi_os",
                                   help="Alert when RSI is below this — oversold opportunity")
        with _thr_col2:
            _conf_hi = _st.slider("Min Confidence for BUY alert", 50, 95, 70, key="thr_conf_hi")
            _conf_lo = _st.slider("Max Confidence for SELL alert", 5, 50, 30, key="thr_conf_lo")

    # Evaluate alerts against current scan results
    _thr_alerts = []
    for r in results:
        _tfs   = r.get("timeframes") or {}
        _rsi   = None
        for _tf in ("1h", "4h", "1d"):
            _r_raw = _tfs.get(_tf, {}).get("rsi")
            if _r_raw not in (None, "N/A", "—"):
                try:
                    _rsi = float(_r_raw)
                    break
                except Exception:
                    pass

        _conf = r.get("confidence_avg_pct", 50)
        _dir  = r.get("direction", "")

        _thr_fired = []
        if _rsi is not None and _rsi >= _st.session_state.get("thr_rsi_ob", 70):
            _thr_fired.append(f"RSI {_rsi:.0f} ≥ OB threshold {_st.session_state.get('thr_rsi_ob', 70)}")
        if _rsi is not None and _rsi <= _st.session_state.get("thr_rsi_os", 30):
            _thr_fired.append(f"RSI {_rsi:.0f} ≤ OS threshold {_st.session_state.get('thr_rsi_os', 30)}")
        if "BUY" in _dir and _conf >= _st.session_state.get("thr_conf_hi", 70):
            _thr_fired.append(f"BUY confidence {_conf:.0f}% ≥ {_st.session_state.get('thr_conf_hi', 70)}%")
        if "SELL" in _dir and _conf <= _st.session_state.get("thr_conf_lo", 30):
            _thr_fired.append(f"SELL confidence {_conf:.0f}% ≤ {_st.session_state.get('thr_conf_lo', 30)}%")

        if _thr_fired:
            _thr_alerts.append({
                "pair":   r["pair"],
                "dir":    _dir,
                "conf":   _conf,
                "fired":  _thr_fired,
            })

    if _thr_alerts:
        for _ta in _thr_alerts[:10]:
            _dir_col = "#22c55e" if "BUY" in _ta["dir"] else "#ef4444" if "SELL" in _ta["dir"] else "#9ca3af"
            _st.markdown(
                f"<div style='background:rgba(0,0,0,0.2);border-left:3px solid {_dir_col};"
                f"border-radius:6px;padding:8px 12px;margin-bottom:6px'>"
                f"<b style='color:{_dir_col}'>🔔 {_ta['pair'].replace('/USDT','')}</b> · "
                f"<span style='color:#9ca3af'>{_ta['dir']} · {_ta['conf']:.0f}% confidence</span><br>"
                f"<span style='font-size:11px;color:#64748b'>"
                f"{'  ·  '.join(_ta['fired'])}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        _st.success("▲ No pairs matching your current thresholds. Adjust sliders above to customize.")


def render_liquidation_overlay_panel(results: list, user_level: str = "beginner",
                                     liq_data: dict | None = None) -> None:
    """S5 — Liquidation Heatmap & Cluster Map.

    Enhanced panel showing:
      1. Real forced-liquidation events from Binance (if accessible)
      2. OI-weighted liquidation cluster heatmap per coin (leverage distribution model)
      3. Per-coin table with cascade risk scores
    """
    import streamlit as _st
    import plotly.graph_objects as _go
    import pandas as _pd
    import data_feeds as _df

    section_header(
        "Liquidation Heatmap & Cluster Map",
        "Where forced liquidations are most likely to cluster — real events + OI-based model",
        icon="⚠️",
    )

    if user_level == "beginner":
        render_what_this_means_sg(
            "When crypto traders borrow money to trade (leverage), they can get 'liquidated' — "
            "their positions are force-closed if the price moves against them. "
            "This panel shows WHERE those forced closures are most likely to happen. "
            "Red zones = where many long positions would be wiped. Green zones = where shorts get wiped. "
            "Large clusters = potential for rapid price acceleration through that zone.",
            title="What is a liquidation heatmap?",
        )

    # ── Section 1: Real Binance Forced Orders (if geo-accessible) ────────────
    _pairs = [r["pair"] for r in results[:10] if r.get("pair")]
    _btc_liq = _df.fetch_binance_liquidations("BTCUSDT", limit=20)

    if _btc_liq:
        _st.markdown(
            '<div style="font-size:11px;color:rgba(168,180,200,0.6);text-transform:uppercase;'
            'letter-spacing:0.8px;font-weight:600;margin:4px 0 8px 0">'
            '🔴 Recent Actual Liquidations — Binance Futures (live)</div>',
            unsafe_allow_html=True,
        )
        _liq_rows = []
        for _ev in _btc_liq[:10]:
            _side_label = "🔴 Long Wiped" if _ev["side"] == "SELL" else "🟢 Short Wiped"
            import datetime as _dt
            try:
                _ts = _dt.datetime.fromtimestamp(_ev["timestamp_ms"] / 1000,
                                                  tz=_dt.timezone.utc).strftime("%H:%M:%S UTC")
            except Exception:
                _ts = "—"
            _liq_rows.append({
                "Time":     _ts,
                "Symbol":   _ev["symbol"].replace("USDT", ""),
                "Type":     _side_label,
                "Price":    f"${_ev['price']:,.2f}",
                "Size":     f"${_ev['usd_value']:,.0f}",
            })
        _st.dataframe(_pd.DataFrame(_liq_rows), width='stretch', hide_index=True)
        _st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)
    else:
        _st.caption("⚠️ Live Binance liquidation feed unavailable in this region — showing model estimates below.")

    # ── Section 2: OI-based Heatmap per Coin ─────────────────────────────────
    _ws_prices = {}
    try:
        import websocket_feeds as _ws
        _ws_prices = _ws.get_all_prices()
    except ImportError:
        pass  # websocket-client optional
    except Exception as _ws_liq_err:
        logger.debug("[UI] WS prices for liquidation heatmap failed: %s", _ws_liq_err)

    if liq_data is None:
        try:
            liq_data = _df.build_liquidation_heatmap_data(_pairs, _ws_prices)
        except Exception:
            liq_data = {}

    if not liq_data:
        _st.info("Run a scan to generate liquidation cluster data.")
        return

    # Cascade risk score chart — the meaningful per-coin differentiation.
    # The ±% distances to liquidation levels are fixed by the leverage model (always ±1%/2%/5%/10%/20%).
    # What VARIES per coin is the cascade score: driven by OI size × proximity.
    # BTC with $2B OI scores very differently from XRP with $80M OI — this is what matters.
    _fig = _go.Figure()
    _table_rows = []
    _syms, _scores, _bar_colors, _oi_labels = [], [], [], []

    _color_map = {
        "EXTREME":  "rgba(239,68,68,0.80)",
        "HIGH":     "rgba(245,158,11,0.80)",
        "MODERATE": "rgba(245,158,11,0.50)",
        "LOW":      "rgba(34,197,94,0.65)",
    }
    _risk_thresh = {"EXTREME": 75, "HIGH": 50, "MODERATE": 25, "LOW": 0}

    for _pair, _ld in list(liq_data.items())[:8]:
        _sym   = _pair.replace("/USDT", "")
        _price = _ld["price"]
        _cs    = _ld["cascade_score"]
        _css   = _ld["cascade_signal"]
        _oi_bn = _ld["oi_usd"] / 1e9

        _syms.append(_sym)
        _scores.append(_cs)
        _bar_colors.append(_color_map.get(_css, "rgba(107,114,128,0.5)"))
        _oi_labels.append(f"${_oi_bn:.2f}B OI")

        _table_rows.append({
            "Coin":          _sym,
            "Price":         f"${_price:,.4f}" if _price < 10 else f"${_price:,.2f}",
            "OI ($B)":       f"${_oi_bn:.2f}B",
            "Cascade Score": f"{_cs:.0f} / 100",
            "Risk":          _css,
        })

    _fig.add_trace(_go.Bar(
        x=_syms, y=_scores,
        marker_color=_bar_colors,
        text=_oi_labels,
        textposition="outside",
        textfont=dict(size=9, color="#94a3b8"),
        hovertemplate="<b>%{x}</b><br>Cascade score: %{y:.0f}<br>%{text}<extra></extra>",
        name="Cascade Risk Score",
    ))

    # Risk threshold reference lines
    for _label, _thresh in [("EXTREME (75)", 75), ("HIGH (50)", 50), ("MODERATE (25)", 25)]:
        _fig.add_hline(
            y=_thresh,
            line=dict(color="rgba(148,163,184,0.2)", dash="dot", width=1),
            annotation_text=_label,
            annotation_font=dict(size=8, color="rgba(148,163,184,0.4)"),
            annotation_position="right",
        )

    _fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,23,42,0.8)",
        font_color="#94a3b8",
        yaxis=dict(title="Cascade Risk Score (0–100)",
                   gridcolor="rgba(148,163,184,0.06)", range=[0, 110]),
        xaxis=dict(gridcolor="rgba(0,0,0,0)"),
        height=280, margin=dict(l=50, r=90, t=10, b=20),
        showlegend=False,
    )
    _st.plotly_chart(_fig, width='stretch', config={"displayModeBar": False})

    # ── Table with cascade risk scores ────────────────────────────────────────
    if _table_rows:
        _st.dataframe(_pd.DataFrame(_table_rows), width='stretch', hide_index=True)

    _st.caption(
        "Cascade Risk Score = how dangerous the current setup is. "
        "Higher score = more leveraged money close to current price = bigger risk of a cascade move. "
        "Driven by: OI size (how much money) × leverage proximity (how close to getting wiped). "
        "EXTREME ≥75, HIGH ≥50, MODERATE ≥25, LOW <25. "
        "Model uses 5×/10×/20×/50×/100× leverage distribution — same methodology as Coinglass free tier."
    )


def render_macro_scorecard_panel(macro_data: dict, user_level: str = "beginner") -> None:
    """
    S25 — Always-visible Macro Intelligence scorecard.

    Shows:
      1. Overall macro signal banner (RISK_ON → RISK_OFF)
      2. 5-card row: Global M2 · Yield Curve · DXY · VIX · Score
      3. Global M2 vs BTC 90-day lag correlation chart
      4. Regime impact callout (how many pts applied to coin scores)
      5. Beginner plain-English summary
    """
    import streamlit as _st
    import plotly.graph_objects as _go
    import data_feeds as _df

    section_header(
        "Macro Intelligence",
        "Global money supply · Interest rates · US Dollar · Market fear — how the big picture affects crypto",
        icon="🌐",
    )

    _ms   = macro_data.get("macro_signal", "NEUTRAL")
    _sc   = macro_data.get("macro_score",  0)
    _sig_col = {
        "RISK_ON":       "#00d4aa", "MILD_RISK_ON":  "#22c55e",
        "NEUTRAL":       "#6b7280", "MILD_RISK_OFF": "#f59e0b",
        "RISK_OFF":      "#ef4444",
    }.get(_ms, "#6b7280")
    _sig_bg = {
        "RISK_ON":       "rgba(0,212,170,0.08)",  "MILD_RISK_ON":  "rgba(34,197,94,0.08)",
        "NEUTRAL":       "rgba(107,114,128,0.06)","MILD_RISK_OFF": "rgba(245,158,11,0.08)",
        "RISK_OFF":      "rgba(239,68,68,0.08)",
    }.get(_ms, "rgba(107,114,128,0.06)")

    _plain_map = {
        "RISK_ON":       "Central banks printing money, dollar weakening, calm markets — ideal conditions for crypto.",
        "MILD_RISK_ON":  "Conditions moderately support risk assets. Macro is a tailwind, but not full throttle.",
        "NEUTRAL":       "Mixed macro signals — no strong directional push from the big picture.",
        "MILD_RISK_OFF": "Some macro headwinds active. Be more selective with position sizing.",
        "RISK_OFF":      "Multiple macro headwinds: high rates, strong dollar, or fear spike. Historically tough for crypto.",
    }

    # ── Overall signal banner ────────────────────────────────────────────────
    _st.markdown(
        f'<div style="background:{_sig_bg};border:1px solid {_sig_col}33;border-left:4px solid {_sig_col};'
        f'border-radius:10px;padding:14px 18px;margin-bottom:14px;display:flex;'
        f'justify-content:space-between;align-items:center">'
        f'<div>'
        f'<span style="font-size:10px;color:rgba(168,180,200,0.5);text-transform:uppercase;'
        f'letter-spacing:1px;font-weight:600">Macro Environment</span><br/>'
        f'<span style="font-size:22px;font-weight:800;color:{_sig_col}">'
        f'{_ms.replace("_", " ")}</span>'
        f'</div>'
        f'<div style="text-align:right">'
        f'<span style="font-size:11px;color:rgba(168,180,200,0.5)">Composite score</span><br/>'
        f'<span style="font-size:28px;font-weight:800;color:{_sig_col}">{_sc:+d}</span>'
        f'<span style="font-size:13px;color:rgba(168,180,200,0.4)"> / 4</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 5-card row ────────────────────────────────────────────────────────────
    _c1, _c2, _c3, _c4 = _st.columns(4)

    def _mini_card(col, label, value, sub, color, plain=""):
        _plain_div = (
            '<div style="font-size:9px;color:rgba(168,180,200,0.35);margin-top:5px;line-height:1.3">'
            + plain + '</div>'
        ) if plain else ""
        col.markdown(
            f'<div style="background:linear-gradient(145deg,rgba(17,24,40,0.98),rgba(24,32,56,0.95));'
            f'border:1px solid rgba(255,255,255,0.06);border-top:3px solid {color};'
            f'border-radius:10px;padding:12px 14px">'
            f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;'
            f'letter-spacing:0.8px;font-weight:600;margin-bottom:4px">{label}</div>'
            f'<div style="font-size:15px;font-weight:700;color:{color}">{value}</div>'
            f'<div style="font-size:10px;color:rgba(168,180,200,0.55);margin-top:3px">{sub}</div>'
            f'{_plain_div}'
            f'</div>',
            unsafe_allow_html=True,
        )

    _m2t  = macro_data.get("m2_trend", "—")
    _m2c  = {"EXPANDING": "#00d4aa", "CONTRACTING": "#ef4444", "FLAT": "#6b7280"}.get(_m2t, "#6b7280")
    _m2p  = macro_data.get("m2_pct_change_90d", 0.0)
    _mini_card(_c1, "Global M2", _m2t, f"{_m2p:+.2f}% (90d)", _m2c,
               "Expanding = more liquidity = crypto tailwind" if user_level == "beginner" else "")

    _yct  = macro_data.get("yield_curve", "—")
    _ycc  = {"NORMAL": "#22c55e", "FLAT": "#f59e0b", "INVERTED": "#ef4444"}.get(_yct, "#6b7280")
    _spr  = macro_data.get("yield_spread_pp", 0.0)
    _mini_card(_c2, "Yield Curve (10Y–2Y)", _yct, f"Spread {_spr:+.2f}pp", _ycc,
               "Inverted = recession warning" if user_level == "beginner" else "")

    _dxt  = macro_data.get("dxy_trend", "—")
    _dxc  = {"STRONG_DOLLAR": "#ef4444", "NEUTRAL": "#6b7280", "WEAK_DOLLAR": "#00d4aa"}.get(_dxt, "#6b7280")
    _dxv  = macro_data.get("dxy", 104.0)
    _mini_card(_c3, "US Dollar (DXY)", _dxt.replace("_", " "), f"DXY {_dxv:.1f}", _dxc,
               "Weak dollar = crypto tailwind" if user_level == "beginner" else "")

    _vxt  = macro_data.get("vix_structure", "—")
    _vxc  = {"CONTANGO": "#22c55e", "FLAT": "#6b7280", "BACKWARDATION": "#ef4444"}.get(_vxt, "#6b7280")
    _vxv  = macro_data.get("vix", 18.0)
    _vx3  = macro_data.get("vix3m", 20.0)
    _mini_card(_c4, "VIX Term Structure", _vxt, f"VIX {_vxv:.1f} · VIX3M {_vx3:.1f}", _vxc,
               "Backwardation = fear spike" if user_level == "beginner" else "")

    _st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

    # ── Beginner plain-English summary ────────────────────────────────────────
    if user_level == "beginner":
        render_what_this_means_sg(_plain_map.get(_ms, ""), title="What does this mean for me?")

    # ── Global M2 vs BTC correlation chart ────────────────────────────────────
    try:
        _chart_data = _df.fetch_m2_btc_chart_data(months=24)
        if _chart_data and _chart_data.get("dates"):
            _dates     = _chart_data["dates"]
            _m2_vals   = _chart_data["m2_values"]
            _btc_p     = _chart_data["btc_prices"]
            _lag_dates = _chart_data["lag_dates"]

            _fig_m2 = _go.Figure()

            # M2 line (left axis) — Scattergl = WebGL backend, 5-10x faster render
            _fig_m2.add_trace(_go.Scattergl(
                x=_dates, y=_m2_vals,
                name="US M2 (tn USD)", mode="lines",
                line=dict(color="#8b5cf6", width=2),
                yaxis="y1",
            ))
            # M2 lagged line (shifted +90d — shown on same axis for alignment)
            _fig_m2.add_trace(_go.Scattergl(
                x=_lag_dates, y=_m2_vals,
                name="M2 +90d lag", mode="lines",
                line=dict(color="#8b5cf6", width=1.5, dash="dot"),
                yaxis="y1", opacity=0.55,
            ))
            # BTC price line (right axis)
            _btc_clean = [v for v in _btc_p if v is not None]
            if _btc_clean:
                _fig_m2.add_trace(_go.Scattergl(
                    x=[_dates[i] for i, v in enumerate(_btc_p) if v is not None],
                    y=_btc_clean,
                    name="BTC Price (USD)", mode="lines",
                    line=dict(color="#f59e0b", width=2),
                    yaxis="y2",
                ))

            _fig_m2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(15,23,42,0.6)",
                font=dict(color="#94a3b8", size=10),
                height=220,
                margin=dict(l=50, r=50, t=10, b=30),
                legend=dict(orientation="h", y=1.08, x=0,
                            font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
                yaxis=dict(
                    title="M2 (tn USD)", gridcolor="rgba(148,163,184,0.07)",
                    titlefont=dict(color="#8b5cf6"), tickfont=dict(color="#8b5cf6"),
                ),
                yaxis2=dict(
                    title="BTC (USD)", overlaying="y", side="right",
                    gridcolor="rgba(0,0,0,0)",
                    titlefont=dict(color="#f59e0b"), tickfont=dict(color="#f59e0b"),
                ),
                xaxis=dict(gridcolor="rgba(0,0,0,0)"),
            )
            _st.plotly_chart(_fig_m2, width='stretch', config={"displayModeBar": False})
            _st.caption(
                "Purple solid = current US M2 money supply. "
                "Purple dashed = M2 shifted forward 90 days (lag model: BTC historically follows M2 ~3 months later). "
                "Gold = BTC price. Source: FRED + yfinance."
            )
    except Exception as _e:
        logger.warning("[ui_components] M2 chart error: %s", _e)
        _st.caption("M2 chart temporarily unavailable.")

    # ── Regime impact callout ─────────────────────────────────────────────────
    try:
        _adj = _df.get_macro_signal_adjustment()
        _adj_pts = _adj.get("adjustment", 0)
        _adj_regime = _adj.get("regime", "MACRO_NEUTRAL")
        _adj_col = "#00d4aa" if _adj_pts > 0 else ("#ef4444" if _adj_pts < 0 else "#6b7280")
        _st.markdown(
            f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);'
            f'border-radius:8px;padding:10px 14px;margin-top:8px;font-size:11px;'
            f'color:rgba(168,180,200,0.7)">'
            f'📊 <b>Macro adjustment applied to all coin signals today:</b> '
            f'<span style="color:{_adj_col};font-weight:700;font-size:13px">{_adj_pts:+.0f} pts</span>'
            f' &nbsp;·&nbsp; Regime: <span style="color:{_adj_col}">{_adj_regime.replace("_"," ")}</span>'
            f' &nbsp;·&nbsp; DXY {_adj.get("dxy", 0):.1f} ({_adj.get("dxy_signal","—")})'
            f' &nbsp;·&nbsp; 10Y {_adj.get("ten_yr", 0):.2f}% ({_adj.get("yr_signal","—")})'
            f'</div>',
            unsafe_allow_html=True,
        )
    except Exception as _macro_adj_err:
        logger.debug("[UI] macro adjustment banner render failed: %s", _macro_adj_err)


def render_what_this_means_sg(message: str, title: str = "What does this mean for me?") -> None:
    """Beginner 'What does this mean?' info box for SuperGrok sections.
    Only renders at beginner level — callers should gate on user_level."""
    import streamlit as _st
    _st.info(f"ℹ️ **{title}** — {message}")



