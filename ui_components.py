"""
ui_components.py — Premium UI design system for Crypto Signal Dashboard
Glass-morphism, gradient borders, fluid typography, animated backgrounds.
Inspired by KOI, Flare Network, dYdX, and Uniswap visual design systems.
"""
import streamlit as st


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
    --bg-base:   #080b12;
    --bg-0:      #0c0f1a;
    --bg-1:      #111520;
    --bg-2:      #181d2e;
    --bg-3:      #1f2538;
    --bg-glass:  rgba(14, 18, 30, 0.72);

    /* brand */
    --primary:       #00d4aa;
    --primary-dim:   #009e80;
    --primary-glow:  rgba(0, 212, 170, 0.18);
    --primary-glow2: rgba(0, 212, 170, 0.06);
    --accent:        #6366f1;   /* indigo accent — dYdX-inspired */
    --accent-glow:   rgba(99, 102, 241, 0.14);

    /* signal */
    --bull:       #00d4aa;
    --bull-dim:   rgba(0, 212, 170, 0.15);
    --bull-border:rgba(0, 212, 170, 0.35);
    --bear:       #f6465d;
    --bear-dim:   rgba(246, 70, 93, 0.15);
    --bear-border:rgba(246, 70, 93, 0.35);
    --warn:       #f59e0b;
    --warn-dim:   rgba(245, 158, 11, 0.15);
    --neutral:    #64748b;

    /* text */
    --text-1: #e8ecf4;
    --text-2: #a8b4c8;
    --text-3: #6b7a94;
    --text-4: #3d4a60;

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
        #080b12 !important;
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
    background: linear-gradient(135deg, #e8ecf4 0%, #a8b4c8 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    padding-bottom: 2px !important;
}
h2 {
    font-size: var(--fs-md) !important;
    font-weight: 600 !important;
    color: #c4cedd !important;
    letter-spacing: -0.2px !important;
}
h3 {
    font-size: var(--fs-sm) !important;
    font-weight: 600 !important;
    color: #9aa3b8 !important;
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
[data-testid="stMetricDelta"][data-direction="positive"] { color: #00c076 !important; }
[data-testid="stMetricDelta"][data-direction="negative"] { color: #f6465d !important; }

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
   SIDEBAR — deeper glass panel
═══════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background:
        radial-gradient(ellipse 120% 60% at 50% 0%, rgba(0,212,170,0.05) 0%, transparent 60%),
        #09010d !important;
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
    background: linear-gradient(135deg, #00d4aa 0%, #00b08e 60%, #5b8df5 100%) !important;
    border: none !important;
    color: #06101c !important;
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
    background: linear-gradient(90deg, var(--primary), #00e5c0, var(--accent), var(--primary)) !important;
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

</style>
"""


def inject_css():
    """Inject the full premium CSS design system into the Streamlit app.
    PERF: guarded by session_state so the 600-line CSS block is only parsed
    and sent to the browser once per session, not on every rerun.
    """
    if not st.session_state.get("_css_injected"):
        st.markdown(_CSS, unsafe_allow_html=True)
        st.session_state["_css_injected"] = True


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
    st.markdown(
        f'<script>document.body.classList.{action}("beginner-mode");</script>',
        unsafe_allow_html=True,
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
            border-image: linear-gradient(180deg,#00d4aa,#6366f1) 1;
            padding-left: 14px;
            margin: 26px 0 12px 0">
            <div style="
                font-size: 15px;
                font-weight: 700;
                letter-spacing: -0.2px;
                background: linear-gradient(120deg, #e8ecf4 0%, #a8b4c8 100%);
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


# ── Signal direction pill ──────────────────────────────────────────────────────

_PILL_CFG = {
    "STRONG BUY":  ("#00d4aa", "#06101c", "0 0 12px rgba(0,212,170,0.5)"),
    "BUY":         ("#00c076", "#06101c", "0 0 8px  rgba(0,192,118,0.35)"),
    "STRONG SELL": ("#f6465d", "#fff",    "0 0 12px rgba(246,70,93,0.5)"),
    "SELL":        ("#c0392b", "#fff",    "0 0 8px  rgba(192,57,43,0.35)"),
    "NEUTRAL":     ("#2a3352", "#64748b", "none"),
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
        f'<span style="background:#2a3352;color:#64748b;'
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
        color, bg = "#f6465d", "rgba(246,70,93,0.1)"
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
            <span style="font-size:14px;font-weight:700;color:#e8ecf4;
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
        accent_gradient = "linear-gradient(180deg,#00d4aa,#00b08e)"
        regime_color    = "rgba(0,212,170,0.12)"
    elif "SELL" in direction:
        accent_gradient = "linear-gradient(180deg,#f6465d,#c0392b)"
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
                    <span style="font-size:17px;font-weight:800;color:#e8ecf4;
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
    delta_color = "#00c076" if delta_positive else ("#f6465d" if delta_positive is False else "#64748b")
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
        <div style="font-size:22px;font-weight:700;color:#e8ecf4;
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
    """Render a premium gradient branding header in the sidebar."""
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
                background: linear-gradient(135deg, #00d4aa 0%, #5b8df5 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                letter-spacing: -0.5px;
                line-height: 1.1;
                position: relative">
                ⬡ CryptoSignal
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
        accent = "#f6465d"
        bg     = "rgba(246,70,93,0.05)"
    else:
        accent = "#f59e0b"
        bg     = "rgba(245,158,11,0.05)"
    st.markdown(
        f'<div style="background:{bg};border-left:3px solid {accent};'
        f'border-radius:0 8px 8px 0;padding:10px 14px;margin:0 0 14px 0;">'
        f'<span style="font-size:13px;color:#c4cedd;line-height:1.65;'
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
        emoji, mood_color, advice = "😱", "#f6465d", "Markets are very fearful — historically a buying opportunity, but use caution."
    elif pct <= 40:
        emoji, mood_color, advice = "😟", "#f59e0b", "Markets are fearful — some may see this as a buying opportunity."
    elif pct <= 60:
        emoji, mood_color, advice = "😐", "#64748b", "Markets are neutral — no strong emotion either way. Wait for a clearer signal."
    elif pct <= 80:
        emoji, mood_color, advice = "🤩", "#00d4aa", "Markets are greedy — prices may be elevated. Be careful chasing gains."
    else:
        emoji, mood_color, advice = "🤑", "#f6465d", "Extreme Greed — the market may be overheated. Historically a warning sign."

    # Track fill color gradient
    bar_gradient = f"linear-gradient(90deg, #f6465d 0%, #f59e0b 25%, #64748b 50%, #00c076 75%, #00d4aa 100%)"
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
        label, dot_color = "Strong", "#00c076"
    elif conf >= 45:
        label, dot_color = "Moderate", "#f59e0b"
    elif conf >= 30:
        label, dot_color = "Weak", "#f6465d"
    else:
        label, dot_color = "Very Weak", "#f6465d"

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
        label, bg, border, tc = "HIGHER RISK", "rgba(246,70,93,0.12)", "rgba(246,70,93,0.35)", "#f6465d"

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
        <div style="font-size:20px;font-weight:800;color:#e8ecf4;margin-bottom:6px">
            Welcome to CryptoSignal
        </div>
        <div style="font-size:13px;color:rgba(168,180,200,0.75);line-height:1.7;margin-bottom:18px">
            This tool scans cryptocurrency markets and tells you which coins may be worth buying,
            selling, or avoiding — in plain English, no trading experience needed.
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:18px">
            <div style="background:rgba(0,212,170,0.07);border:1px solid rgba(0,212,170,0.15);
                        border-radius:10px;padding:14px 16px">
                <div style="font-size:20px;margin-bottom:6px">1️⃣</div>
                <div style="font-size:12px;font-weight:700;color:#e8ecf4;margin-bottom:4px">Run the Scan</div>
                <div style="font-size:11px;color:rgba(168,180,200,0.6)">
                    Click <strong style="color:#00d4aa">▶ Analyze Market Now</strong> above.
                    The model will fetch live market data for all coins (~1–3 min).
                </div>
            </div>
            <div style="background:rgba(99,102,241,0.07);border:1px solid rgba(99,102,241,0.15);
                        border-radius:10px;padding:14px 16px">
                <div style="font-size:20px;margin-bottom:6px">2️⃣</div>
                <div style="font-size:12px;font-weight:700;color:#e8ecf4;margin-bottom:4px">Read the Results</div>
                <div style="font-size:11px;color:rgba(168,180,200,0.6)">
                    Each coin gets a <strong style="color:#e8ecf4">BUY / SELL / HOLD</strong> signal
                    with a plain-English explanation. Look for ⚡ Top Picks.
                </div>
            </div>
            <div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.15);
                        border-radius:10px;padding:14px 16px">
                <div style="font-size:20px;margin-bottom:6px">3️⃣</div>
                <div style="font-size:12px;font-weight:700;color:#e8ecf4;margin-bottom:4px">Do Your Research</div>
                <div style="font-size:11px;color:rgba(168,180,200,0.6)">
                    This model is a research tool — <strong style="color:#f59e0b">not financial advice.</strong>
                    Always do your own due diligence before trading.
                </div>
            </div>
        </div>
        <div style="background:rgba(246,70,93,0.07);border:1px solid rgba(246,70,93,0.18);
                    border-radius:10px;padding:10px 14px;font-size:11px;color:rgba(168,180,200,0.65)">
            ⚠️ <strong style="color:#f6465d">Risk Warning:</strong>
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
        accent      = "#f6465d"
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
                <span style="font-size:22px;font-weight:800;color:#e8ecf4;
                             font-family:'JetBrains Mono',monospace">{base}</span>
                <span style="background:{accent};color:#060f18;border-radius:999px;
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


def glossary_popover() -> None:
    """Render a sidebar-friendly 'Crypto Glossary' popover button."""
    with st.popover("📖 Crypto Glossary — 28 terms explained"):
        st.markdown("### Crypto & Trading Terms — Plain English")
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
        color  = "#00e676" if is_gainer else "#ff5252"
        sign   = "+" if pct >= 0 else ""
        price_fmt = f"${price:,.4f}" if price < 1 else f"${price:,.2f}"
        return (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
            f'<span style="font-weight:600;color:#e2e8f0;font-size:0.88rem;">{sym}</span>'
            f'<span style="color:#94a3b8;font-size:0.78rem;">{price_fmt}</span>'
            f'<span style="color:{color};font-weight:700;font-size:0.88rem;">'
            f'{arrow} {sign}{pct:.2f}%</span>'
            f'</div>'
        )

    gainer_rows = "".join(_row(c, True)  for c in gainers[:3]) if gainers else '<div style="color:#64748b;font-size:0.82rem;padding:8px 0;">No data</div>'
    loser_rows  = "".join(_row(c, False) for c in losers[:3])  if losers  else '<div style="color:#64748b;font-size:0.82rem;padding:8px 0;">No data</div>'

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
      <div style="color:#00e676;font-size:0.75rem;font-weight:600;letter-spacing:0.08em;
                  text-transform:uppercase;margin-bottom:6px;">▲ Gainers</div>
      {gainer_rows}
    </div>
    <div>
      <div style="color:#ff5252;font-size:0.75rem;font-weight:600;letter-spacing:0.08em;
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
        "LOW":      ("#00e676", "#1a3a2a"),
        "MODERATE": ("#ffd740", "#3a320a"),
        "HIGH":     ("#ff9100", "#3a1f00"),
        "EXTREME":  ("#ff5252", "#3a0a0a"),
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
                f'font-size:0.78rem;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
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
                 padding:3px 10px;font-size:0.78rem;font-weight:700;">{icon} {risk_level}</span>
  </div>

  <!-- Score gauge bar -->
  <div style="background:rgba(255,255,255,0.06);border-radius:8px;height:10px;margin-bottom:8px;overflow:hidden;">
    <div style="width:{bar_pct}%;height:100%;border-radius:8px;
                background:linear-gradient(90deg,#00e676,{color});
                transition:width 0.5s ease;"></div>
  </div>

  <div style="display:flex;justify-content:space-between;align-items:center;font-size:0.82rem;">
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
        color, label = "#00e676", "High Accuracy"
    elif pct >= 55:
        color, label = "#ffd740", "Moderate"
    elif pct >= 45:
        color, label = "#94a3b8", "Neutral"
    else:
        color, label = "#ff5252", "Below Average"

    suffix = f" {signal_type}" if signal_type else ""
    n_text = f"{sample_size} signals" if sample_size >= 10 else "New signal"

    return (
        f'<span title="Historical accuracy of{suffix} signals over last {sample_size} trades" '
        f'style="display:inline-flex;align-items:center;gap:5px;'
        f'background:rgba(15,23,42,0.8);border:1px solid {color}44;border-radius:20px;'
        f'padding:3px 9px;font-size:0.76rem;cursor:help;">'
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
        "BULL":    ("🐂", "#00e676", "rgba(0,230,118,0.08)", "Bull Market",    "Trend-following strategies preferred"),
        "BEAR":    ("🐻", "#ff5252", "rgba(255,82,82,0.08)",  "Bear Market",    "Reduce size, defensive positioning"),
        "RANGING": ("↔",  "#ffd740", "rgba(255,215,64,0.08)", "Ranging Market", "Mean-reversion strategies preferred"),
        "CRISIS":  ("🚨", "#ff9100", "rgba(255,145,0,0.08)",  "Crisis / High Volatility", "Extreme caution — reduce all exposure"),
    }
    icon, color, bg, title, advice = _REGIME_META.get(
        regime, ("❓", "#94a3b8", "rgba(148,163,184,0.08)", "Unknown Regime", "")
    )

    hurst_html = ""
    if hurst is not None:
        h_color = "#00e676" if hurst > 0.55 else ("#ff5252" if hurst < 0.45 else "#ffd740")
        h_label = "Trending" if hurst > 0.55 else ("Mean-Reverting" if hurst < 0.45 else "Random Walk")
        hurst_html = (
            f'<span style="background:rgba(255,255,255,0.05);border-radius:8px;'
            f'padding:3px 8px;font-size:0.78rem;margin-left:10px;">'
            f'Hurst: <span style="color:{h_color};font-weight:700;">{hurst:.2f}</span>'
            f' <span style="color:#64748b;">({h_label})</span></span>'
        )

    squeeze_html = ""
    if squeeze_active:
        squeeze_html = (
            '<span style="background:rgba(255,215,64,0.15);border:1px solid #ffd74066;'
            'border-radius:8px;padding:3px 8px;font-size:0.78rem;margin-left:10px;'
            'animation:pulse 1.5s ease-in-out infinite;">'
            '🗜 <span style="color:#ffd740;font-weight:700;">SQUEEZE</span>'
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
  <span style="color:#64748b;font-size:0.82rem;">— {advice}</span>
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
        border_col  = "#ff5252"
        size_color  = "#ff5252"
        status_html = (
            '<div style="background:rgba(255,82,82,0.15);border:1px solid #ff525266;'
            'border-radius:8px;padding:8px 12px;margin-top:10px;font-size:0.82rem;">'
            '🚨 <span style="color:#ff5252;font-weight:700;">Circuit Breaker ACTIVE</span>'
            ' — all new signals suppressed until daily/weekly loss limit resets.</div>'
        )
    else:
        bg_color    = "rgba(15,23,42,0.7)"
        border_col  = "rgba(255,255,255,0.08)"
        size_color  = "#00e676" if recommended_pct >= 1.0 else "#ffd740"
        pnl_color   = "#00e676" if daily_pnl_pct >= 0 else "#ff5252"
        pnl_sign    = "+" if daily_pnl_pct >= 0 else ""
        status_html = (
            f'<div style="font-size:0.8rem;color:#94a3b8;margin-top:8px;">'
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
                background:linear-gradient(90deg,#6366f1,{size_color});"></div>
  </div>
  <div style="color:#94a3b8;font-size:0.8rem;">{rationale}</div>
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
    _SIG_COLORS = {"BUY": "#00e676", "SELL": "#ff5252", "NEUTRAL": "#94a3b8"}
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
    <span style="font-size:0.82rem;color:#cbd5e1;font-weight:500;">{name}</span>
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="color:{color};font-size:0.8rem;font-weight:700;">{icon} {signal}</span>
      <span style="color:#64748b;font-size:0.75rem;">contrib: <span style="color:{color};">{c_sign}{contrib:.1f}</span></span>
    </div>
  </div>
  <div style="background:rgba(255,255,255,0.05);border-radius:4px;height:4px;overflow:hidden;">
    <div style="width:{bar_w}%;height:100%;border-radius:4px;background:{color};opacity:0.7;"></div>
  </div>
  <div style="text-align:right;font-size:0.7rem;color:#475569;margin-top:1px;">weight {weight:.0%}</div>
</div>""")

    rows_html = "".join(rows) if rows else '<div style="color:#64748b;font-size:0.82rem;">No agent data</div>'

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
  font-size: 0.82rem;
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
        color  = "#00e676" if chg >= 0 else "#ff5252"
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
