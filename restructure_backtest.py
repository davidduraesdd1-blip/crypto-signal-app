"""
Stage 4: Merge page_trade_log() into page_backtest() as 3 sub-tabs.
  Tab 1: Summary   — metrics, equity curve, trade table, Monte Carlo
  Tab 2: Trade History — full page_trade_log() content (5 sub-tabs)
  Tab 3: Advanced  — walk-forward, deep backtest, calibration, IC/WFE, stress test

Also removes "My Trades" from _NAV_BEGINNER, _NAV_INTERMEDIATE, _NAV_ADVANCED,
updates _PAGE_MAP (removes Trade Log entry), and cleans up the router.
"""
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split("\n")

def L(n): return n - 1  # 1-based → 0-based

# ── Exact line boundaries (1-based) ──────────────────────────────────────────
PAGE_BACKTEST_DEF   = 4728   # def page_backtest():
HEADER_END          = 4747   # last line of header (progress fragment call)
EARLY_RETURN_START  = 4749   # if st.session_state.get("backtest_error"):
TAB1_END            = 5062   # last line of Monte Carlo block (before walk-forward comment)
BT_LV_GUARD_START   = 5063   # # Walk-Forward + Deep Backtest comment
BT_LV_GUARD_END     = 5065   # return  # beginners see metrics...
TAB3_START          = 5067   # # Walk-forward out-of-sample validation
PAGE_BACKTEST_END   = 5838   # last content line of page_backtest()

PAGE_TRADELOG_DEF   = 5867   # def page_trade_log():
PAGE_TRADELOG_TITLE_END = 5872  # closing ) of st.markdown title
PAGE_TRADELOG_CONTENT   = 5874  # tab_master, tab_paper, ... = st.tabs([...])
PAGE_TRADELOG_END   = 6251   # last content line (before page_arbitrage)

# ── Helper: re-indent by adding extra_spaces ──────────────────────────────────
def reindent(text, extra=4):
    pad = " " * extra
    out = []
    for ln in text.split("\n"):
        if ln.strip() == "":
            out.append("")
        else:
            out.append(pad + ln)
    return "\n".join(out)

# ── Extract blocks ─────────────────────────────────────────────────────────────
# Header: def page_backtest(): ... _backtest_progress()
header_block = "\n".join(lines[L(PAGE_BACKTEST_DEF):L(HEADER_END)+1])

# Tab 1 content: error check + no-data early return + metrics/equity/trade table/Monte Carlo
tab1_raw = "\n".join(lines[L(EARLY_RETURN_START):L(TAB1_END)+1])
# The early return inside "no backtest data" needs to stay as-is (works fine inside a with block)
tab1_body = reindent(tab1_raw)

# Tab 3 content: walk-forward to end of page_backtest, skip the comment+beginner guard
tab3_raw = "\n".join(lines[L(TAB3_START):L(PAGE_BACKTEST_END)+1])
tab3_body = reindent(tab3_raw, extra=8)  # 4 (func) + 4 (with _bt_t3) + 4 (else body) = need 8 extra since raw is at 4-space

# Tab 2 content: page_trade_log body (skip title + blank line, start from the st.tabs line)
tab2_raw = "\n".join(lines[L(PAGE_TRADELOG_CONTENT):L(PAGE_TRADELOG_END)+1])
tab2_body = reindent(tab2_raw)

# ── Build new page_backtest function ──────────────────────────────────────────
new_page_backtest = (
    header_block
    + "\n\n"
    + "    _bt_t1, _bt_t2, _bt_t3 = st.tabs([\n"
    + '        "📊 Summary",\n'
    + '        "📋 Trade History",\n'
    + '        "🔬 Advanced Backtests",\n'
    + "    ])\n\n"
    + "    with _bt_t1:\n"
    + tab1_body
    + "\n\n"
    + "    with _bt_t2:\n"
    + tab2_body
    + "\n\n"
    + "    with _bt_t3:\n"
    + "        if _bt_lv == 'beginner':\n"
    + "            st.markdown(\n"
    + "                '<div style=\"background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);'\n"
    + "                'border-radius:12px;padding:28px 24px;text-align:center;margin:20px 0\">'\n"
    + "                '<div style=\"font-size:32px;margin-bottom:10px\">\\U0001f52c</div>'\n"
    + "                '<div style=\"font-size:18px;font-weight:700;color:#e8ecf4;margin-bottom:8px\">'\n"
    + "                'Advanced Analysis Tools</div>'\n"
    + "                '<div style=\"font-size:13px;color:#9ca3af;line-height:1.6;max-width:380px;margin:0 auto\">'\n"
    + "                'Walk-Forward Validation, Deep Backtest, and Signal Calibration are available at '\n"
    + "                '<strong style=\"color:#818cf8\">Intermediate</strong> or '\n"
    + "                '<strong style=\"color:#a78bfa\">Advanced</strong> level.<br><br>'\n"
    + "                'Switch your experience level in the sidebar to unlock these tools.</div>'\n"
    + "                '</div>',\n"
    + "                unsafe_allow_html=True,\n"
    + "            )\n"
    + "        else:\n"
    + tab3_body  # already at 12-space indent (extra=8 applied to 4-space-indented raw)
)

# ── page_trade_log becomes a thin shim (redirects to Performance) ─────────────
new_page_trade_log = '''\
def page_trade_log():
    """Merged into page_backtest() as the Trade History tab."""
    st.session_state["_nav_target"] = "Backtest Viewer"
    st.rerun()
'''

# ── Identify the full text blocks to replace ──────────────────────────────────
# Block A: page_backtest function (L4728 to L5838 inclusive)
old_page_backtest = "\n".join(lines[L(PAGE_BACKTEST_DEF):L(PAGE_BACKTEST_END)+1])

# Block B: page_trade_log function (L5867 to L6251 inclusive)
old_page_trade_log = "\n".join(lines[L(PAGE_TRADELOG_DEF):L(PAGE_TRADELOG_END)+1])

# ── Apply replacements ────────────────────────────────────────────────────────
if old_page_backtest not in content:
    print("ERROR: Could not find page_backtest block — check line numbers")
else:
    content = content.replace(old_page_backtest, new_page_backtest, 1)
    print("page_backtest replaced OK")

if old_page_trade_log not in content:
    print("ERROR: Could not find page_trade_log block — check line numbers")
else:
    content = content.replace(old_page_trade_log, new_page_trade_log, 1)
    print("page_trade_log replaced with shim OK")

# ── Remove My Trades from all 3 nav lists ─────────────────────────────────────
content = content.replace('    "📋 My Trades",\n', '', 3)
print("Removed My Trades from nav lists")

# ── Remove My Trades from _PAGE_MAP ──────────────────────────────────────────
content = content.replace('    "📋 My Trades":     "Trade Log & History",\n', '')
print("Removed My Trades from PAGE_MAP")

# ── Remove Trade Log & History router entry ───────────────────────────────────
content = content.replace(
    'elif page == "Trade Log & History":\n    page_trade_log()\n',
    ''
)
print("Removed Trade Log router entry")

# ── Write output ──────────────────────────────────────────────────────────────
with open("app_backtest_restructured.py", "w", encoding="utf-8") as f:
    f.write(content)
print(f"Written app_backtest_restructured.py — {len(content.splitlines())} lines")
print("Run: py -3 -m py_compile app_backtest_restructured.py")
