# Post-Deploy Audit — 2026-05-01

**Branch:** `main` (post Phase C merge)
**Tag baseline:** `redesign-ui-2026-05-shipped` → `20587d2`
**Deploy:** https://cryptosignal-ddb1.streamlit.app/
**Auditor:** Cowork (browser walk via Claude in Chrome)
**Method:** visited Home, Signals (BTC default), Backtester at Beginner level / dark theme. Patterns repeated across pages so deeper sub-state walks (light theme, Intermediate/Advanced levels, individual segmented sub-views) deferred — root issues identified will affect those equally.

---

## Triage summary

3 cross-cutting roots account for ~80% of visible pain. Fix those first and most page-specific symptoms collapse with them.

| Severity | Issues | Recommended order |
|---|---|---|
| **CRIT** | 1 cross-cutting | Fix first |
| **HIGH** | 2 cross-cutting + 1 page-specific | Fix second |
| **MED** | 2 page-specific + 1 data-layer | Fix third |
| **LOW** | 1 cosmetic | Last / opportunistic |

No issues touch `composite_signal.py` — **§4 regression-diff dance not required for this batch.** All fixes are presentation-layer (CSS overrides, sidebar state, data wiring shims). Composite-signal logic stays untouched.

---

## Cross-cutting roots — fix these first

### **C-fix-01 · CRIT · Topbar buttons rendering as wide-wrapped Streamlit defaults**

**Symptom:** On every page, the level-group (Beginner / Intermediate / Advanced) plus the Refresh / Theme buttons render as oversized Streamlit `stButton` defaults — text wraps mid-word ("Beginn / er", "Upda / te", "The / me"), each button takes a full viewport-column slot, and the topbar consumes ~280px of vertical space pushing all hero/page content far below the fold.

**Root cause:** the `.ds-level-group` and `.ds-chip-btn` CSS in `ui/overrides.py` isn't reaching the actual rendered buttons. Either the buttons aren't wearing those classes (Streamlit inserts its own wrapper that overrides the class), or the override CSS specificity isn't beating Streamlit's defaults at the `[data-testid="stButton"] > button` level for the topbar context specifically.

**Pages affected:** Home, Signals, Regimes, Backtester, On-chain, Alerts, AI Assistant, Settings — i.e. all 8 (any page that calls `render_top_bar`).

**Fix:**
1. Inspect the actual DOM the topbar produces (Streamlit may render a column container around each button).
2. Either: (a) wrap the topbar buttons in a custom `<div class="ds-level-group">…</div>` HTML block via `st.markdown(unsafe_allow_html=True)` and trigger state via separate hidden buttons + callback pattern (the H5/C2 callback technique), or (b) add aggressive `[data-testid="stSidebar-topbar"] > div > div [data-testid="stButton"] > button { all: unset; … apply pill style ... }` overrides scoped to the topbar context only.
3. The mockup style is in `docs/mockups/sibling-family-crypto-signal.html` lines ~160-176 (`.level-group`, `.refresh-btn`, `.theme-btn`).

**Acceptance:** topbar collapses from ~280px to ~56px (matches `--topbar-h`), buttons render as horizontal pills with no text wrap, hero cards visible above the fold on every page.

---

### **C-fix-02 · HIGH · Sidebar wordmark "Signal.app" wraps to two lines**

**Symptom:** the sidebar brand block shows "Signal.a / pp" — wordmark wraps mid-word at the rail's 150px width.

**Root cause:** `.ds-brand-wm` lacks `white-space: nowrap` (or has it but the dot+wordmark flex container is hitting min-width-0 from C1's universal defenses and wrapping anyway). When we shrunk the rail from 240px to 150px in C1, the wordmark's intrinsic width didn't get a corresponding tightening.

**Fix:** in `ui/overrides.py` `.ds-brand-wm`:
```css
.ds-brand-wm { color: var(--text-primary); white-space: nowrap; font-size: 14px; }
.ds-rail-brand { white-space: nowrap; }
```
Or, if 14px still wraps, either drop to 13px or trim "Signal.app" → "Signal" + .app muted on a second visual element.

**Acceptance:** wordmark on a single line, sized to fit comfortably inside the 150px rail.

---

### **C-fix-03 · HIGH · Sidebar active-state doesn't track page navigation**

**Symptom:** clicking "Signals" in the sidebar navigates to the Signals page, but the *highlighted* nav item stays on "Home" (or whichever was last clicked). Two clicks later, sidebar still shows the old highlight.

**Root cause:** likely the same H5 / C1 callback bug we fixed in Phase B — the highlight reads `nav_key` from session state but the markdown emits *before* the click callback writes the new value, so the highlight reflects pre-click state. C1 wired this correctly in `ui/sidebar.py` (`_select_nav` callback at line 189), but something downstream may be reading the wrong key, or the routing in `app.py` is updating `_nav_target` but `nav_key` falls behind. Could also be that Streamlit's rerun happens after the markdown emits the highlight class, in which case we need to force a rerender pass or use `st.rerun()` inside the callback.

**Fix:**
1. Verify `_select_nav` callback writes `st.session_state["nav_key"] = key` *before* `st.session_state["_nav_target"]`.
2. Confirm `render_sidebar` reads `nav_key` (not `_nav_target`) when deciding which item gets the active class.
3. If the order is right and it still desyncs, add `st.rerun()` at the end of `_select_nav` to force a full rerender after state writes.

**Acceptance:** clicking any nav item updates the highlight on the *first* render, no two-click lag, sidebar matches the rendered page.

---

## Page-specific issues

### **C-fix-04 · HIGH · Signals page — multi-timeframe strip shows only 4 cells (mockup specifies 8)**

**Symptom:** Signals page timeframe strip renders `1h / 4h / 1d / 1w` only. Mockup (`docs/mockups/sibling-family-crypto-signal-SIGNALS.html`) specifies 8 cells: `1m / 5m / 15m / 30m / 1h / 4h / 1d / 1w`.

**Root cause:** in C3, the `multi_timeframe_strip` component was probably wired to `model.TIMEFRAMES` which currently defaults to the 4-tf set the live engine uses. The mockup expects 8 timeframes including the noise-prone short ones (1m, 5m) and the slow 1w. Either the component should always render the canonical 8 (showing greyed-out / disabled state for any timeframes the engine isn't actively scanning) or `model.TIMEFRAMES` needs extending.

**Fix:** in `ui/sidebar.py` `multi_timeframe_strip`, accept a `timeframes` arg defaulting to `("1m","5m","15m","30m","1h","4h","1d","1w")`. Cells whose timeframe isn't in `model.TIMEFRAMES` render with `--text-muted` color and `cursor: not-allowed` + a tooltip "enable in Settings → Trading → Timeframes".

**Acceptance:** Signals timeframe strip shows all 8 cells; clicking an enabled cell switches the page; clicking a disabled cell shows tooltip; consistency with mockup.

---

### **C-fix-05 · MED · Signals page — period changes (30d, 1Y) show as "—" instead of values**

**Symptom:** hero card on Signals shows `+ 2.93% · 24h · — · 30d · — · 1Y` — the 30d and 1Y deltas are dashes.

**Root cause:** likely the OHLCV fetch returns less than 365 days of history or the period-change calculation isn't being run. Could also be a cache miss that resolves to None instead of fetching.

**Fix:** in `page_signals` (or wherever `signal_hero_detail_card` is composed), call `_sg_cached_ohlcv(_ex_id, _pair, "1d", limit=400)` (need ≥ 365 candles for 1Y), compute `pct_change(30)` and `pct_change(365)` from the returned series, pass both to the hero card. If fetch fails (offline / rate-limit), show a small `last updated · {ts}` caption rather than the dash placeholder.

**Acceptance:** hero card shows 24h / 30d / 1Y deltas with real percentages.

---

### **C-fix-06 · MED · Signals + Backtester data tiles show "—" / empty values**

**Symptom:** Signals indicator tiles (VOL 24H, ATR 14D, BETA, FUNDING) show "—" with no values. Backtester KPI strip shows labels (TOTAL RETURN, CAGR, SHARPE, MAX) but values empty.

**Root cause:** data layer not wired all the way through OR cache cold-start. Likely the cached fetcher functions return on Streamlit Cloud cold-start with a default empty value; once the scan runs, values populate. Possibly the page is rendering before the data layer has had a chance to fetch.

**Fix:**
1. Add a "first-load" populate step in `page_signals` and `page_backtest` that triggers the relevant cached fetch with a 5s spinner if values are None.
2. For the Backtester KPI strip specifically: if `_cached_backtest_df()` returns empty, show a CTA card "Run a backtest to populate metrics" instead of empty KPI labels — the labels-without-values state is misleading.
3. Verify the deploy environment has the necessary API keys / DB seeded.

**Acceptance:** tiles populate within 5s of page load OR show a CTA if no data exists yet.

---

## Cosmetic / low-priority

### **C-fix-07 · LOW · Sidebar Glossary expander wraps "Glossary — 30 terms (Plain English)" awkwardly**

**Symptom:** the Glossary popover trigger renders across 4 lines: "📖 / Glossary / — 30 / terms / (Plain / English)".

**Fix:** shorten the label to `📖 Glossary` with the 30-terms count as a small caption below or as a tooltip. Apply `white-space: nowrap; overflow: hidden; text-overflow: ellipsis` to the popover trigger label.

**Acceptance:** Glossary trigger fits on one line of the sidebar.

---

## Recommended fix sequence

**Stabilization sprint** branched off `redesign-ui-2026-05-shipped` tag (restore-point safety), branch name `c-stabilization-sprint`.

1. **C-fix-01** (CRIT topbar) — biggest visible win, unblocks every page's "above the fold" experience.
2. **C-fix-02** (HIGH wordmark) + **C-fix-03** (HIGH sidebar state) — both small, both touch sidebar/CSS, ship together.
3. **C-fix-04** (HIGH 8-cell timeframe strip) — Signals page, single-component fix.
4. **C-fix-05** (MED period deltas) + **C-fix-06** (MED empty data tiles) — same data-layer concern, address together.
5. **C-fix-07** (LOW Glossary wrap) — opportunistic, can ride along with any other commit.

Group commits as: `fix(c-stab-NN): <title>` per fix, single PR back to main when done. No §4 regression diff required for any of these — none touch `composite_signal.py`. Run `tests/verify_deployment.py --env prod` before merge. Manual browser walk on the PR's preview deploy at all 3 user levels + both themes.

---

## Out of scope for this audit

- The 2 cosmetic filesystem orphans (`.claude/worktrees/funny-jennings-1a4193`, `.git/worktrees/keen-faraday-10b9bb`) — Windows file locks, harmless empty dirs
- The 5 stale remote branches (`fix/redesign-port-data-wiring`, `redesign/ui-2026-05*`) — content reached main via tags; cleanup ticket
- Composite-signal logic, regime detection, backtester engine — Phase C verified these green at merge time, no signs of regression
- Light theme + Intermediate/Advanced levels — patterns identified above will affect them equally; verify on the stabilization PR's preview deploy
- Mobile viewport — not tested in this audit; handle as separate ticket if issues surface

---

## Hand-off briefing for Claude Code

```
Branch off redesign-ui-2026-05-shipped tag → c-stabilization-sprint.
Read docs/redesign/2026-05-01_post-deploy-audit.md.
Execute C-fix-01 through C-fix-07 in the order recommended.
Per-fix commit: fix(c-stab-NN): <title>. Single PR to main when all 7 land.
No §4 regression diff required (presentation layer only).
Run tests/verify_deployment.py --env prod before PR open.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```
