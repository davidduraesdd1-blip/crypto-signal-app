"""
Restructure page_dashboard() into 5 sub-tabs.
Run: py -3 restructure_dashboard.py
"""
import re

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()   # preserve line endings

# ── Helper: re-indent a block of lines by adding extra_spaces
def reindent(block_lines, extra_spaces=4):
    pad = " " * extra_spaces
    result = []
    for ln in block_lines:
        if ln.strip() == "" or ln == "\n":
            result.append(ln)          # blank lines unchanged
        else:
            result.append(pad + ln)

    return result

# Line number → 0-based index
# Section boundaries (1-based line numbers from search):
# preamble:      1358 – 1568   (keep as-is, move sorted_results before tabs)
# tab1:          1570 – 1675   (micro-tutorial → top movers)
# tab4a:         1676 – 1994   (Blood/DCA, Macro Intel, Wyckoff, Liquidation)
# tab2a:         1996 – 2268   (rank list → tier2)
# separator+tab3: 2269 – 3038  (coin selector → exports)
# tab4b:         3039 – 3167   (agent status + wallet)
# tab2b:         3168 – 3280   (phase9 heatmap + global market context)
# tab5:          3283 – 3570   (analysis tools expander)
# after_tabs:    3571 – 3577   (auto-refresh trigger)

# Convert to 0-based
def L(n): return n - 1

preamble      = lines[L(1358):L(1569)]   # 1358-1568 inclusive (indices 1357..1567)
tab1_lines    = lines[L(1570):L(1676)]   # 1570-1675
tab4a_lines   = lines[L(1676):L(1995)]   # 1676-1994
tab2a_lines   = lines[L(1996):L(2270)]   # 1996-2268 + the two-line gap 2269-2270
tab3_lines    = lines[L(2271):L(3039)]   # 2271-3038

# Remove sorted_results + exec vars from tab2a (they're now pre-computed before the tabs)
_tab2a_str = "".join(tab2a_lines)
_tab2a_str = re.sub(
    r'    # Sort results: high-conf first.*?_exec_cfg\s+=\s+_exec\.get_exec_config\(\)\n',
    '',
    _tab2a_str,
    flags=re.DOTALL
)
tab2a_lines = _tab2a_str.splitlines(keepends=True)
tab4b_lines   = lines[L(3039):L(3168)]   # 3039-3167
tab2b_lines   = lines[L(3168):L(3283)]   # 3168-3282
tab5_lines    = lines[L(3283):L(3571)]   # 3283-3570
after_tabs    = lines[L(3571):L(3578)]   # 3571-3577

# ── Patch preamble: inject sorted_results + _exec_status + _exec_cfg
# before the end of the preamble (just before the "# ── Item 9" micro-tutorial line)
# These are currently computed inside the function at lines 2108-2112
# We add them before the tabs so they're available in all tabs.
extra_vars = """\
    # Pre-compute shared variables used across multiple tabs
    sorted_results = sorted(results, key=lambda r: (r.get("high_conf", False), r.get("confidence_avg_pct", 0)), reverse=True)
    _exec_status = _exec.get_status()
    _exec_cfg    = _exec.get_exec_config()

"""

# Insert extra_vars at end of preamble (before the tabs definition)
preamble_str = "".join(preamble) + extra_vars

# ── Build tabs header (4-space indented inside page_dashboard)
tabs_header = """\
    # ─── 5-TAB DASHBOARD STRUCTURE ───────────────────────────────────────────
    _dash_tab1, _dash_tab2, _dash_tab3, _dash_tab4, _dash_tab5 = st.tabs([
        "\U0001f3af Today",
        "\U0001f4ca All Coins",
        "\U0001f50d Coin Detail",
        "\U0001f310 Market Intel",
        "\U0001f52c Analysis",
    ])

"""

# ── Tab 1: micro-tutorial → top movers
tab1_block = (
    "    with _dash_tab1:\n"
    + "".join(reindent(tab1_lines))
)

# ── Tab 4 (part A): Blood/DCA, Macro Intel, Wyckoff, Liquidation
tab4a_block = (
    "    with _dash_tab4:\n"
    + "".join(reindent(tab4a_lines))
)

# ── Tab 2 (part A): rank list → tier2
tab2a_block = (
    "    with _dash_tab2:\n"
    + "".join(reindent(tab2a_lines))
)

# ── Tab 3: coin selector → exports
# Remove the duplicate sorted_results line (now computed pre-tab)
tab3_str = "".join(tab3_lines)
# Remove the 2 lines that compute sorted_results + exec vars (they moved to pre-tab)
tab3_str = re.sub(
    r'    # Sort results.*?reverse=True\)\n\n    # Fetch once.*?_exec\.get_exec_config\(\)\n',
    '',
    tab3_str,
    flags=re.DOTALL
)
tab3_block = (
    "    with _dash_tab3:\n"
    + "".join(reindent(tab3_str.splitlines(keepends=True)))
)

# ── Tab 4 (part B): agent status + wallet  (append inside same tab4 with block)
# Since tab4 part A and part B need to be in the same `with _dash_tab4:` block,
# we combine them
tab4b_block = "".join(reindent(tab4b_lines))

# ── Tab 2 (part B): phase9 heatmap + global market (append inside same tab2 with block)
tab2b_block = "".join(reindent(tab2b_lines))

# ── Combine tab4 and tab2 (close part A, add part B in same block)
# Both partA and partB are within the same with block — we just concatenate
tab4_combined = (
    "    with _dash_tab4:\n"
    + "".join(reindent(tab4a_lines))
    + tab4b_block
    + "\n"
)

tab2_combined = (
    "    with _dash_tab2:\n"
    + "".join(reindent(tab2a_lines))
    + tab2b_block
    + "\n"
)

# ── Tab 5: analysis tools or beginner unlock card
tab5_unlock_card = """\
    with _dash_tab5:
        _analysis_lv = st.session_state.get("user_level", "beginner")
        if _analysis_lv == "beginner":
            st.markdown(
                '<div style="background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);'
                'border-radius:12px;padding:28px 24px;text-align:center;margin:20px 0">'
                '<div style="font-size:32px;margin-bottom:10px">\\U0001f52c</div>'
                '<div style="font-size:18px;font-weight:700;color:#e8ecf4;margin-bottom:8px">'
                'Advanced Analysis Tools</div>'
                '<div style="font-size:13px;color:#9ca3af;line-height:1.6;max-width:380px;margin:0 auto">'
                'Correlation matrix, volatility rankings, and pair trade scanner are available at '
                '<strong style="color:#818cf8">Intermediate</strong> or '
                '<strong style="color:#a78bfa">Advanced</strong> level.<br><br>'
                'Switch your experience level in the sidebar to unlock these tools.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
"""
# Grab tab5 lines and re-indent by 8 (4 for function body + 4 for with tab5 + 4 for else = 12 total,
# but tab5_lines start at 4-space indent, so we need to add 8 more to get to 12)
tab5_inner = "".join(reindent(tab5_lines, 8))
tab5_block = tab5_unlock_card + tab5_inner + "\n"

# ── After tabs: auto-refresh
after_str = "".join(after_tabs)

# ── Assemble the new page_dashboard function
new_func = (
    preamble_str
    + tabs_header
    + tab1_block
    + "\n"
    + tab4_combined
    + tab2_combined
    + tab3_block
    + "\n"
    + tab5_block
    + after_str
)

# ── Replace in original file
# Everything from line 1358 to line 3577 (inclusive)
before = lines[:L(1358)]       # lines before page_dashboard
after  = lines[L(3578):]       # lines after page_dashboard (from _progress_cb onward)

new_content = "".join(before) + new_func + "".join(after)

with open("app_restructured.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"Written app_restructured.py — {len(new_content.splitlines())} lines")
print("Run: py -3 -m py_compile app_restructured.py")
