# Phase C — Implementation Plan

**Branch:** `redesign/ui-2026-05-full-mockup-match`
**Prepared:** 2026-04-29
**Author:** Claude Opus 4.7 (Cowork session) → handed off to Claude Code for execution
**Reference docs (read first):**

- `docs/redesign/2026-04-29_page-and-tab-inventory.md` — full Phase A inventory; the spec for what each page must do, including all Q1–Q10 resolutions
- `docs/redesign/2026-04-29_ux-research-tab-vs-flat.md` — 35-source UX research that informs the hybrid tab decision
- `docs/mockups/sibling-family-crypto-signal-*.html` — 13 HTML mockups; visual targets for every page state
- `CLAUDE.md` (project) → `../master-template/CLAUDE_master_template.md` (inherited governance)
- Commit history on this branch — Phase B Batches 1-6 (commits `5f4b36c` through `0eaa7fd`) show the design-token + mockup work that Phase C now wires into live code

---

## Cadence

**Per-batch review.** Each batch ends with: commit + push to origin, deploy to Streamlit Cloud, user verifies on the live deploy, then next batch. No autonomous run-through of all 11 — pause for user thumbs-up between each.

Every commit message ends with:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Per master template §3, never `git add -A`. Stage files by name. Per §4, run `python -m py_compile <files>` and `pytest tests/ -m "not slow"` after edits, before commit.

---

## C1 — Foundation / wiring layer

**Files:**
- `ui/sidebar.py` (lines 71-97)
- `ui/design_system.py` (`Tokens.rail_w` token; `_build_css` body)
- `ui/overrides.py` (`.ds-nav-group` rule)

**Scope:**

1. **`ui/sidebar.py`** — Update `DEFAULT_NAV` to add `("ai_assistant", "AI Assistant", "💬")` between Alerts and Settings in the Account group. Update `PAGE_KEY_TO_APP` to fix stale mappings (signals/regimes/onchain were all routed to "Dashboard"; they're first-class pages now). Add `"ai_assistant": "Agent"` mapping. Alerts stays routed to "Config Editor" until C6.

   Final dicts:
   ```python
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
           ("alerts",       "Alerts",       "◐"),
           ("ai_assistant", "AI Assistant", "💬"),
           ("settings",     "Settings",     "⚙"),
       ],
   }

   PAGE_KEY_TO_APP: dict[str, str] = {
       "home":         "Dashboard",
       "signals":      "Signals",
       "regimes":      "Regimes",
       "backtester":   "Backtest Viewer",
       "onchain":      "On-chain",
       "alerts":       "Config Editor",   # TODO C6
       "ai_assistant": "Agent",
       "settings":     "Config Editor",
   }
   ```

2. **`ui/design_system.py`** — change `Tokens.rail_w` from `"240px"` to `"150px"`.

3. **`ui/design_system.py` `_build_css`** — after the `.stApp { background: var(--bg-0); }` line, add universal mobile defenses:
   ```css
   html, body { overflow-x: hidden; max-width: 100vw; }
   *, *::before, *::after { box-sizing: border-box; min-width: 0; }
   .stApp { max-width: 100vw; overflow-x: hidden; }
   ```
   And modify `.ds-card` to add `min-width: 0; max-width: 100%; box-sizing: border-box; overflow: hidden;`.

4. **`ui/overrides.py` `.ds-nav-group`** — bold up section headers (per user feedback during Phase B):
   ```css
   .ds-nav-group {
     margin: 18px 0 6px; padding: 0 10px;
     color: var(--text-primary); font-size: 12px; font-weight: 700;
     letter-spacing: 0.12em; text-transform: uppercase;
   }
   ```

**Acceptance:**
- `python -m py_compile ui/sidebar.py ui/design_system.py ui/overrides.py` → no errors
- `pytest tests/ -m "not slow"` → all green
- Streamlit deploy: sidebar narrower (150px), MARKETS / RESEARCH / ACCOUNT bold-and-bright, AI Assistant nav item present, no horizontal-scroll on mobile viewport

**Commit:**
```
feat(c1): foundation wiring — 8-item nav, 150px rail, bold section labels, mobile overflow defenses

- ui/sidebar.py: DEFAULT_NAV adds AI Assistant; PAGE_KEY_TO_APP fixes
  stale signals/regimes/onchain mappings (now first-class pages),
  adds ai_assistant→Agent. Alerts stays routed to Config Editor
  until C6 (page_alerts split).
- ui/design_system.py: rail_w 240→150 token; inject_theme adds
  universal mobile defenses (html/body overflow-x:hidden +
  max-width:100vw, * min-width:0, .stApp max-width:100vw,
  .ds-card min-width:0 max-width:100% overflow:hidden).
- ui/overrides.py: .ds-nav-group bolded — text-primary, 12px,
  700 weight, 0.12em letter-spacing per Phase B Batch 1 user
  feedback.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## C2 — Segmented control component

**Files:**
- `ui/components.py` (NEW — extract general-purpose components from `ui/sidebar.py` if it gets crowded; otherwise add to `ui/sidebar.py`)
- `tests/test_segmented_control.py` (NEW)

**Scope:**

Build `segmented_control(items, active, key, on_select=None)`:
- `items`: list of `(value, label)` tuples
- `active`: currently selected value
- `key`: Streamlit session-state key for persistence
- `on_select`: optional callback fired on click with the new value

Two CSS variants: primary (Backtester `[Backtest][Arbitrage]`), secondary smaller (sub-views `[Summary][Trade History][Advanced]`).

**Critical**: callback pattern (`on_click=callback`), NOT `if button: write_state(); rerun()`. Master template §18 + the H5 fix in `ui/sidebar.py` lines 178-191. Inline pattern caused the two-click highlight bug — same trap here.

**Acceptance:**
- Unit test: clicking an item updates session_state on first click (no two-click lag)
- Unit test: `on_select` callback fires with correct value
- Visual: matches mockup CSS (`.seg-ctrl` and `.seg-ctrl-sm` from `docs/mockups/sibling-family-crypto-signal-BACKTESTER.html` lines ~33-40)

---

## C3 — Pair-selection affordances

**Files:**
- `ui/sidebar.py` (extend existing `coin_picker`, add new `pair_dropdown`, `ticker_pill_button`, `watchlist_customize_btn`, `multi_timeframe_strip`)
- `app.py` `page_dashboard`, `page_signals`, `page_regimes`, `page_onchain`

**Scope:**

1. **Signals** — `coin_picker` extends to 5 quick + `More ▾ +28` dropdown trigger. Dropdown opens a searchable list of all 33 pairs with `+28` count (or whatever the active universe minus 5 quick is). Selection persists in `st.session_state["selected_pair"]`.

2. **Regimes** — section header with `Showing 8 of 33 pairs · click any to drill in · More ▾ +25`. `More` dropdown lets user replace any of the 8 visible cards with another pair from the universe.

3. **On-chain** — each card's ticker becomes a `ticker_pill_button` (per Q10 Option B): clicking opens a per-card pair-swap dropdown. Card slot 1, 2, 3 are independent.

4. **Home** — 3 hero cards' tickers become `ticker_pill_button` (per-card swap). Watchlist card header gets `Customize ▾` button that opens an add/remove panel. Persisted to `st.session_state["watchlist_pairs"]`.

5. **Signals multi-timeframe strip** — new `multi_timeframe_strip` component, 8 cells (1m/5m/15m/30m/1h/4h/1d/1w), each shows the per-timeframe signal + score. Active cell drives the rest of the page (composite score, layer breakdown, indicator cards, history table all reflect the selected timeframe).

**Acceptance:** all 5 pages support pair selection per their respective patterns; selection persists across reruns; mobile views still fit.

---

## C4 — Backtester revision

**Files:**
- `app.py` `page_backtest` (lines 6243-8279) and `page_arbitrage` (lines 8280-8688) — the Arbitrage view merges into Backtester
- `ui/sidebar.py` (`backtest_kpi_strip`, `optuna_top_card`, `recent_trades_card`, plus new helpers for Arbitrage view)

**Scope:**

1. Add primary `segmented_control(["backtest", "arbitrage"])` above the controls row. Default to `backtest`. Selected view drives content below.

2. Add secondary `segmented_control(["summary", "trades", "advanced"])` above the equity/Optuna grid (only visible in `backtest` view). Replaces the existing 3-tab `st.tabs()`. Per Q8 Option B.

3. Add Universe selector dropdown — items: BTC only, ETH only, XRP only, SOL only, AVAX only, LINK only, NEAR only, DOT only, [...other pairs], Top 10 cap, Top 25 cap, All 33, Custom multi-select. Selected universe filters all backtester queries.

4. Move `page_arbitrage` content into the `arbitrage` view of `page_backtest`. Delete the standalone `page_arbitrage` function. Update `app.py` routing to remove the `Arbitrage` page. (Optional: keep a deprecation stub that routes to Backtester → Arbitrage view for any inbound deep links.)

5. Wire selectors to data: `_cached_backtest_df()` calls accept universe + period filters; equity curve, KPIs, Optuna list, trades table all re-run for the selection.

**Acceptance:** Backtester loads in `backtest` view by default; clicking `Arbitrage` swaps content (no full rerun); Universe dropdown filters everything; secondary segmented control swaps Summary/Trades/Advanced sub-views.

---

## C5 — AI Assistant promotion

**Files:**
- `app.py` `page_agent` (lines 8688-8984) — full layout rewrite to match `docs/mockups/sibling-family-crypto-signal-AI-ASSISTANT.html`
- `ui/sidebar.py` `render_top_bar` — add `agent_status_pill` slot (visible on every page)
- `database.py` (or wherever schema lives) — add `agent_decisions` table
- `agent.py` (or `crypto_model_core.py`) — log every decision to the new table
- `app.py` `page_config` `_cfg_t5` (Execution tab) — REMOVE the Autonomous Agent block (~150 lines starting line 6005); replace with a small "Configure agent → AI Assistant" link card

**Scope:**

1. Rewrite `page_agent` to match the mockup: live status row with Start/Stop, 4-metric strip, engine indicator + crash restarts, in-progress spinner, dual-card config (Cycle behavior + Risk limits), Emergency Stop card, Recent Decisions log (10 rows + filters), Pipeline Architecture code block.

2. Add `agent_decisions` DB table:
   ```sql
   CREATE TABLE agent_decisions (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     timestamp TEXT NOT NULL,
     pair TEXT NOT NULL,
     decision TEXT NOT NULL CHECK(decision IN ('approve','reject','skip')),
     confidence REAL,
     rationale TEXT,
     status TEXT NOT NULL CHECK(status IN ('executed','dry_run','pending','override')),
     cycle_id INTEGER,
     created_at TEXT DEFAULT CURRENT_TIMESTAMP
   );
   CREATE INDEX idx_agent_decisions_ts ON agent_decisions(timestamp DESC);
   ```

3. Wire `agent.py` to insert one row per cycle decision. Recent Decisions section queries this table.

4. Move agent config OUT of Settings → Execution. The form fields stay (Dry Run, Cycle Interval, etc.) but only on the AI Assistant page now. Settings → Execution shows: "Autonomous Agent settings live on the AI Assistant page → [Open AI Assistant]".

5. Add `agent_status_pill` to `render_top_bar`'s status_pills slot — visible on every page so users see if the agent is running without leaving their current page.

**Acceptance:** AI Assistant page matches mockup pixel-close; Recent Decisions populates from DB; Settings → Execution no longer has duplicate agent config; topbar pill shows running state on every page.

---

## C6 — Alerts split into Configure + History

**Files:**
- `app.py` (NEW `page_alerts()` function)
- `app.py` (REMOVE Alerts content from `page_config` `_cfg_t3`)
- `app.py` routing — add `elif page == "Alerts": page_alerts()`
- `ui/sidebar.py` `PAGE_KEY_TO_APP` — change `"alerts": "Config Editor"` → `"alerts": "Alerts"`
- `database.py` — add `alerts_log` table
- `alerts.py` (or wherever email/webhook dispatch lives) — log every fired alert to the new table

**Scope:**

1. New `page_alerts()` function with `[Configure][History]` segmented control.

2. **Configure view**: promote existing Settings → Alerts tab content (email config, alert types, channels). Match `docs/mockups/sibling-family-crypto-signal-ALERTS.html`.

3. **History view**: filter row (date range, alert type, status, channel) + alert log table + pagination. Match `docs/mockups/sibling-family-crypto-signal-ALERTS-HISTORY.html`. New `alerts_log` DB table:
   ```sql
   CREATE TABLE alerts_log (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     timestamp TEXT NOT NULL,
     type TEXT NOT NULL,
     asset TEXT,
     message TEXT NOT NULL,
     status TEXT CHECK(status IN ('sent','failed','suppressed')),
     channel TEXT,
     created_at TEXT DEFAULT CURRENT_TIMESTAMP
   );
   CREATE INDEX idx_alerts_log_ts ON alerts_log(timestamp DESC);
   ```

4. **Remove** Alerts tab from `page_config` (`_cfg_t3` block). Settings drops from 5 tabs to 4 (Trading, Signal & Risk, Dev Tools, Execution).

5. Update `_cfg_tab_names` in `page_config` (line 5257) to remove the Alerts entry.

**Acceptance:** Alerts is now a sidebar item with its own page; Configure + History segmented control works; alert log populates as alerts fire; Settings page shows 4 tabs not 5.

---

## C7 — Settings restructure

**Files:**
- `app.py` `page_config` (lines 5125-6242)

**Scope:**

1. After C5 + C6, Settings already has 4 tabs (Alerts dropped per C6, Agent block dropped per C5). Cosmetic cleanup:
   - Update tab labels to match the mockup: `📊 Trading`, `⚡ Signal & Risk`, `🛠️ Dev Tools`, `⚙️ Execution`
   - Beginner-level Quick Setup callout above the tabs (3 controls: Portfolio Size, Risk Per Trade %, API Key — boosted contrast input fields per `docs/mockups/sibling-family-crypto-signal-SETTINGS.html` `.beg-panel input` styling, with `bg-0` background, `border-strong`, 15px mono font, medium weight)

2. Wire the underline tab styling (matches mockup): horizontal tab strip with bottom border, active tab gets `border-bottom-color: var(--accent)` underline, font-weight: 600. Streamlit's `st.tabs()` default styling needs CSS override in `ui/overrides.py` to match.

**Acceptance:** Settings has 4 tabs with mockup-matching tab styling; Beginner level shows Quick Setup callout above tabs; all-level users can still reach all 4 tabs (no early-return regression of C5 fix).

---

## C8 — Regime history data layer (Q7)

**Files:**
- `database.py` — add `regime_history` table
- `scheduler.py` (or wherever scan loop lives) — write regime state per pair per cycle
- `ui/sidebar.py` `regime_state_bar` — wire to query the new table
- `app.py` `page_regimes` — pass real history to the BTC state bar

**Scope:**

1. New table:
   ```sql
   CREATE TABLE regime_history (
     pair TEXT NOT NULL,
     timestamp TEXT NOT NULL,
     state TEXT NOT NULL CHECK(state IN ('bull','bear','accumulation','distribution','transition')),
     confidence REAL,
     PRIMARY KEY (pair, timestamp)
   );
   CREATE INDEX idx_regime_history_pair_ts ON regime_history(pair, timestamp DESC);
   ```

2. After every HMM regime computation in the scan loop, INSERT (or UPSERT) the regime state. Backfill from current scan data where possible.

3. `regime_state_bar` accepts a `history` parameter (list of `{state, duration_pct, label}` tuples). Replace the current 100% single-segment placeholder with real segmented timeline data from the last 90 days.

**Acceptance:** Regimes page BTC state bar shows real segmented 90d history (bear/trans/accum/bull bands sized to actual durations); same data feeds per-pair detail when user clicks a regime card to drill in.

---

## C9 — Level-aware variations (Q5)

**Files:**
- `app.py` `page_signals`, `page_regimes`, `page_onchain`

**Scope:**

Add Beginner / Intermediate / Advanced content variants on the 3 pages currently treating all levels identically. Per CLAUDE.md §7.

Pattern (use throughout):
```python
lv = current_user_level()
if lv == "beginner":
    st.markdown("This coin is showing strong upward momentum...")  # plain English
elif lv == "intermediate":
    st.markdown(f"Composite signal: {score} (BUY · 4-layer alignment)")
else:  # advanced
    st.markdown(f"RSI={rsi:.1f}, MACD={macd_line:.2f}/{signal_line:.2f}, regime=Bull (HMM conf {conf:.0%})")
```

**Per page:**
- **Signals**: rationale block under hero card varies; indicator cards show plain-English vs raw values; signal history descriptions vary
- **Regimes**: regime card "since X · Yd stable" vs full HMM diagnostic; macro overlay rows show sentiment-only vs full delta+sentiment
- **On-chain**: tile sub-labels ("mid-cycle" vs "MVRV-Z 2.84 · 1.8σ above 365d mean")

**Acceptance:** Toggling Beginner/Intermediate/Advanced visibly changes content density on all 3 pages; no functional regressions; mobile still fits.

---

## C10 — Dashboard legacy cleanup (Q4)

**Files:**
- `app.py` `page_dashboard` (lines 1698-5124)

**Scope:**

The current `page_dashboard` renders the new flat-scrollable mockup content at the top, then drops into a legacy 5-tab `st.tabs([_dash_tab1, ..., _dash_tab5])` stack starting at line 2534. Per Q4 Option A, delete the legacy stack.

1. Audit what's in each `_dash_tab1..5` block. Confirm the new content above (hero cards, macro strip, watchlist, backtest preview, regime mini-grid) covers all the unique value. If anything genuinely unique exists in a legacy tab, surface it in one of the existing pages or document the loss in the commit message.

2. Delete the `st.tabs([...])` call and all 5 `with _dash_tabN:` blocks.

3. Verify `page_dashboard` ends after the new mockup-content sections.

**Acceptance:** `page_dashboard` is single-flow scrollable per mockup; line count drops by ~2500; no orphaned imports or unused helpers.

---

## C11 — Final audit + deployment verification

**Files:**
- `tests/verify_deployment.py`
- All touched pages

**Scope:**

1. Master template §4 audit across all 8 pages. 7 dimensions:
   - **Correctness**: every page renders without exceptions on dark + light themes, all 3 user levels
   - **Tests**: full pytest suite green; new tests for C2 segmented control, C5 agent_decisions, C6 alerts_log, C8 regime_history
   - **Optimization**: cold-start budget < 60s on Streamlit Cloud (lazy-load LightGBM/XGBoost preserved)
   - **Efficiency**: no N+1 queries on page loads; cached data layers respect TTLs from §12
   - **Accuracy**: composite-signal regression diff vs `docs/signal-regression/` baseline = zero categorical drift on BTC + ETH
   - **Speed**: hot paths (scanner, backtester, regime detector, composite signal) hit their § 24 perf targets
   - **UI/UX**: every touched page reviewed at all 3 user levels, both themes, mobile + desktop viewports

2. `python tests/verify_deployment.py --env prod` → 5/5 pass

3. 20-point manual browser checklist on the live deploy: https://cryptosignal-ddb1.streamlit.app/

4. Worktree pruning per D3: `.claude/worktrees/{hopeful-pike,keen-faraday,confident-lovelace,funny-jennings}` removed (`git worktree remove --force …`).

5. Open the PR back to `main` with the full Phase A + B + C summary in the body. Tag the merge commit `redesign-ui-2026-05-shipped`.

**Acceptance:** All audits pass, deploy verifier 5/5, manual checklist all checked, worktrees pruned, PR opened.

---

## Cross-batch notes

- **No `git add -A`** — every commit stages files by name (master template §3).
- **CRLF/LF**: `.gitattributes` is committed (Phase B Batch 1, commit `5f4b36c`); CI/local should respect it. If a file shows up modified with the entire content as a diff, run `git checkout -- <file>` to discard the EOL noise.
- **Worktrees**: 4 prior `.claude/worktrees/` are still on disk; leave them until C11. They don't conflict with anything.
- **Mockup cross-reference**: each batch's mockup file is the visual contract. If the implementation diverges, update both the mockup and the inventory in the same commit.

---

## Sign-off

This plan is the canonical hand-off artifact between Cowork (planning) and Claude Code (execution). Any changes to scope or sequence should be reflected here first via PR comment or new commit.

User starts each batch by saying "C# go" (e.g., "C2 go"). Claude Code reads this file + the inventory + the relevant mockup, executes, commits, pushes, and waits for next instruction.
