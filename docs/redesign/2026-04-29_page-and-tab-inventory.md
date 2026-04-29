# Phase A — Page & Tab Inventory

**Project:** crypto-signal-app
**Branch:** `redesign/ui-2026-05-full-mockup-match`
**Tag base:** `redesign-port-fixed-2026-04-29`
**Prepared:** 2026-04-29
**Status:** DRAFT — awaiting user sign-off before Phase B mockup builds begin
**Governance:** Master template §1 (numbered proposal → execute autonomously) · §4 (audit) · §5 (research mandate, satisfied by `2026-04-29_ux-research-tab-vs-flat.md`) · §8 (design standards) · §18 (Streamlit patterns) · §19 (cross-app discipline) · §22 (project-specific constraints)

This document catalogs every sidebar item, every tab inside, every section, every level-specific variation, every data source, and every component for the 2026-05 redesign of the Crypto Signal App. It is the gate to Phase B (HTML mockup creation). No mockups get built and no implementation code gets written until this document is signed off by the user.

---

## 1. Decisions locked in this session

These were settled in conversation across April 29, 2026; recorded here for traceability.

| # | Decision | Rationale |
|---|---|---|
| D1 | Branch is `redesign/ui-2026-05-full-mockup-match` off the `redesign-port-fixed-2026-04-29` tag. Single PR back to main at close-out. | Clean separation; tag is at-rest, branch is in-flight. |
| D2 | All work is audit-first. Phase A inventory → user sign-off → Phase B HTML mockups in batches → user sign-off per batch → Phase C implementation. | §4 audit protocol; user-confirmed thoroughness preference. |
| D3 | Worktree cleanup is deferred to close-out, not now. The 4 `.claude/worktrees/` directories stay in place during the redesign. | Don't disturb stable state mid-work. |
| D4 | `.gitattributes` enforces canonical LF line endings repo-wide. Committed: `5f4b36c`. | §20 — fixes 50k-line CRLF↔LF spurious diffs on every Windows clone. |
| D5 | Stale `flare-magenta` accent comment in `sibling-family-crypto-signal.html` line 21 fixed to `flare-blue #1d4ed8`. The Flare chain icon at line 99 of `sibling-family-flare-defi-MARKET-INTELLIGENCE.html` left as-is (intentional brand identification, not app accent). | Comment was a stale alternative-accent option. Chain icon is per-chain brand, distinct from app accent. |
| D6 | UX research saved at `docs/redesign/2026-04-29_ux-research-tab-vs-flat.md`. Committed. | 35+ sources surveyed per §5; informs hybrid tab decision. |
| D7 | Sidebar architecture: 8 items, 3 groups. Adds `AI Assistant` to Account so the Agent surface stays prominent and gets full-page real estate (the page is too content-dense for a right-rail panel). | Revised from initial Q2 right-rail recommendation after reading actual `page_agent` content. |
| D8 | Tabs treatment is hybrid per the research: content surfaces flatten, Settings keeps tabs (drawer-style), Backtester gets a 2-view segmented control (Backtest \| Arbitrage). | NN/g + Material + industry consensus. |
| D9 | Mobile pattern: bottom nav for top 4-5 items + hamburger for the rest at ≤768px. Already partially implemented in existing mockups. | Industry consensus. |

---

## 2. Final sidebar architecture

```
┌─────────────────────────┐
│  ◈  Signal.app           │
├─────────────────────────┤
│  MARKETS                 │
│  ◉ Home                  │   → page_dashboard
│  ▲ Signals               │   → page_signals
│  ◈ Regimes               │   → page_regimes
│                          │
│  RESEARCH                │
│  ∿ Backtester            │   → page_backtest (with segmented control: Backtest | Arbitrage)
│                          │     - Backtest view → existing backtest content
│                          │     - Arbitrage view → existing page_arbitrage content
│  ⬡ On-chain              │   → page_onchain
│                          │
│  ACCOUNT                 │
│  ◐ Alerts                │   → NEW page (separate from Settings — see §6 Q3)
│  💬 AI Assistant         │   → page_agent
│  ⚙ Settings              │   → page_config (keeps 5 tabs)
└─────────────────────────┘
```

**Mapping update required** in `ui/sidebar.py` — `PAGE_KEY_TO_APP` is currently stale. New mapping:

```python
PAGE_KEY_TO_APP: dict[str, str] = {
    "home":         "Dashboard",
    "signals":      "Signals",
    "regimes":      "Regimes",
    "backtester":   "Backtest Viewer",   # contains Arbitrage segmented view
    "onchain":      "On-chain",
    "alerts":       "Alerts",            # NEW route, see §6 Q3
    "ai_assistant": "Agent",
    "settings":     "Config Editor",
}
```

`DEFAULT_NAV` extended:

```python
DEFAULT_NAV = {
    "Markets":  [("home","Home","◉"), ("signals","Signals","▲"), ("regimes","Regimes","◈")],
    "Research": [("backtester","Backtester","∿"), ("onchain","On-chain","⬡")],
    "Account":  [("alerts","Alerts","◐"), ("ai_assistant","AI Assistant","💬"), ("settings","Settings","⚙")],
}
```

App.py routing extended with `Alerts` page (currently `Alerts` is a tab inside Config Editor; needs promotion or deep-link — see §6 Q3).

---

## 3. Page-by-page inventory

Each page below is the source of truth for what gets mocked and built. For every page: title, breadcrumb, level variations, sections in render order, components needed (split into existing helpers vs. new builds), data sources, mockup status, notes. Where Phase A surfaces a question, it lives in §6 alongside the others.

### 3.1 Home — `page_dashboard` (app.py 1698–5124)

| Field | Value |
|---|---|
| **Title** | "Market home" — same across all levels |
| **Breadcrumb** | ("Markets", "Home") |
| **Level variations** | None at the top (chrome is identical). Level pill on right pulls from session state. |
| **Tabs** | None — flat scrollable. ⚠ But the existing function has an "old tab stack below" that wasn't removed during the redesign port. See §6 Q4. |
| **Mockup** | EXISTS — `sibling-family-crypto-signal.html` |
| **Mockup status** | Anchor mockup. May need minor revisions if §6 Q4 resolves to "remove old tab stack" and we need to show what fills that vertical space. |

**Sections in render order (per mockup + current code):**

1. Top bar — `render_top_bar()` with breadcrumb, level pill, refresh button, theme toggle, status pills (Paper/Live, Claude AI status, Demo when applicable).
2. Page header — `page_header()` with title "Market home", subtitle "Composite signals + regime state across the top-cap set", data-source pills (OKX live, Glassnode live, Google Trends cached).
3. Hero signal cards — `hero_signal_cards_row([BTC, ETH, XRP])` — 3-column row, each card with ticker, price, 24h change, BUY/HOLD/SELL badge with shape, regime label + confidence.
4. Macro strip — `macro_strip([(BTC Dominance, 58.9%, +0.4 ppts·7d), (Fear & Greed, 72, Greed), (DXY, 104.21, -0.6%·30d), (Funding BTC, +0.012%, 8h avg), (Regime macro, Risk-on, conf 76%)])` — 5-column card.
5. Two-column row — `watchlist_card()` (top-cap with sparklines) + `backtest_preview_card()` (4-KPI grid: Return 90d, Max DD, Sharpe, Win rate).

**Data sources:** `_cached_global_market`, `_cached_macro_enrichment`, `_sg_cached_fear_greed`, `data_feeds.fetch_yfinance_macro`, `_sg_cached_funding_rate("BTC/USDT")`, `_cached_signals_df(500)`, `_ws.get_all_prices()`, `data_feeds.fetch_sparkline_closes()`.

**Existing components used:** `render_top_bar`, `page_header`, `macro_strip`, `hero_signal_cards_row`, `watchlist_card`, `backtest_preview_card`, `regime_cards_grid` (only if regime mini-grid retained).

**New components needed:** None for this page if the old tab stack is removed.

---

### 3.2 Signals — `page_signals` (app.py 8984–9430)

| Field | Value |
|---|---|
| **Title** | "Signal detail" |
| **Breadcrumb** | ("Markets", "Signals") |
| **Level variations** | None visible in current code; the page is the same for all 3 levels. ⚠ Per CLAUDE.md §7 the level system applies app-wide; either there's level-aware behavior I missed, or this page should have it. See §6 Q5. |
| **Tabs** | None — flat scrollable. |
| **Mockup** | EXISTS — `sibling-family-crypto-signal-SIGNALS.html` |
| **Mockup status** | Anchor mockup. Already covers the per-coin layout. |

**Sections in render order:**

1. Top bar — same pattern.
2. Page header — title "Signal detail", subtitle "Layer-by-layer composite signal breakdown for a single coin".
3. Coin picker — `coin_picker(["BTC","ETH","XRP","SOL","AVAX"], active=...)` — chip-group across the page top right.
4. Hero detail card — `signal_hero_detail_card(...)` — ticker · name, big price, 3-timeframe changes (24h · 30d · 1Y), BUY/HOLD/SELL signal badge with strength, regime label + confidence + duration.
5. Two-column row:
   - Left: Price chart (90d) inside a `.ds-card` + 4-tile inline strip (Vol 24h, ATR 14d, Beta vs S&P, Funding 8h). The mockup shows 4 tiles; current code adds a 5th (Token Unlocks) for a total of 5 — this is a real divergence between mockup and live page. See §6 Q6.
   - Right: `composite_score_card(score=78.4, layers=[("Layer 1 · Technical",82),...], weights_note="Composite = weighted avg per regime-adjusted weights. Current regime weights: tech 0.30, macro 0.15, sentiment 0.20, on-chain 0.35.")`
6. Three-column row of indicator cards — `indicator_card("Technical indicators", [...])`, `indicator_card("On-chain", [...])`, `indicator_card("Sentiment", [...])`.
7. Recent signal history — `signal_history_table(rows, title="Recent signal history · BTC", subtitle="last 8 state transitions")`.

**Data sources:** `_cached_signals_df(500)`, `_ws.get_all_prices()`, `_sg_cached_ohlcv(_ex_id, _pair, "1d", limit=400)`, `_sg_cached_funding_rate(_pair)`, `_sg_cached_token_unlocks(_pair)`.

**Existing components used:** `render_top_bar`, `page_header`, `coin_picker`, `signal_hero_detail_card`, `composite_score_card`, `indicator_card`, `signal_history_table`.

**New components needed:** None if §6 Q6 resolves to "match mockup at 4 tiles." If we keep the 5-tile (Token Unlocks added), the mockup needs revision.

---

### 3.3 Regimes — `page_regimes` (app.py 9431–9706)

| Field | Value |
|---|---|
| **Title** | "Regimes" |
| **Breadcrumb** | ("Markets", "Regimes") |
| **Level variations** | None visible. Same potential gap as Signals — see §6 Q5. |
| **Tabs** | None — flat scrollable. |
| **Mockup** | EXISTS — `sibling-family-crypto-signal-REGIMES.html` |
| **Mockup status** | Anchor mockup. |

**Sections in render order:**

1. Top bar.
2. Page header — title "Regimes", subtitle "HMM-inferred market regime per asset + macro overlay. Regime-specific signal weights auto-adjust."
3. 4-column regime grid — `regime_cards_grid(cards=[BTC,ETH,XRP,SOL,AVAX,LINK,NEAR,DOT], cols=4)` — 8 cards with ticker, state (Bull/Bear/Accumulation/Distribution/Transition), confidence %, "since X · Yd stable".
4. Two-column row:
   - Left: BTC regime state bar (90d timeline) — `regime_state_bar(segments=[("bear",12),("trans",8),("accum",18),("bull",44),("trans",6),("bull",12)], date_labels=[Jan 24, Feb 12, ...], note="HMM 4-state...")`. ⚠ Current code renders single 100% segment because there's no `regime_history` table yet. See §6 Q7.
   - Right: Macro regime overlay — `macro_regime_overlay_card(rows=[BTC Dominance, DXY, VIX, 10Y yield, Fear & Greed, HY spreads], overall_label="Risk-on", overall_confidence=76)`.
5. Signal weights by regime grid — `regime_weights_grid([("Bull","success",{...}),("Accumulation","info",{...}),("Distribution","warning",{...}),("Bear","danger",{...})])`.

**Data sources:** `_cached_signals_df(500)`, `_cached_global_market`, `_cached_macro_enrichment`, `data_feeds.fetch_yfinance_macro`, `_sg_cached_fear_greed`.

**Existing components used:** `render_top_bar`, `page_header`, `regime_cards_grid`, `regime_state_bar`, `macro_regime_overlay_card`, `regime_weights_grid`.

**New components needed:** None. May need a `regime_history` data layer (separate from this inventory's scope) to populate the segmented state bar with real history.

---

### 3.4 Backtester — `page_backtest` (app.py 6243–8279)

| Field | Value |
|---|---|
| **Title** | "Backtester" |
| **Breadcrumb** | ("Research", "Backtester") |
| **Level variations** | Tabs are level-agnostic; per-level panels live below the tab body. |
| **Top-level pattern** | **Segmented control** (per D8) replaces the existing `st.tabs([...])` — 2 views: `Backtest` \| `Arbitrage`. Each view contains its own scrollable layout. Backtest view has 3 internal sub-views (Summary, Trade History, Advanced). Arbitrage view inherits the existing `page_arbitrage` content. |
| **Mockup** | EXISTS for Backtest view — `sibling-family-crypto-signal-BACKTESTER.html`. NEW required for Arbitrage view. |
| **Mockup status** | Existing mockup needs minor revision: add the segmented control above the Backtest content. Arbitrage view is a new mockup. |

**Sections — Backtest view (default segmented selection):**

1. Top bar.
2. Page header — title "Backtester", subtitle "Composite signal backtested across 2023–2026. Optuna-tuned hyperparams.", data-source pill ("BTC benchmark · cached 5min").
3. **Segmented control** — `[Backtest] [Arbitrage]` — new component (see Phase B).
4. Controls row — `backtest_controls_row(items=[("Universe","Top 10 cap"),("Period","2023-01-01 → today"),("Initial","$100,000"),("Rebalance","Weekly"),("Costs","12 bps · realistic slippage")])` + a real `st.button("Re-run backtest →")` (the C2-fix decorative HTML button is suppressed by default).
5. 5-column KPI strip — `backtest_kpi_strip([("Total return","+ 342.8%","vs BTC + 184.1%","success"),("CAGR","+ 72.4%","vs BTC + 46.2%",""),("Sharpe","4.12","risk-free 4.5%","accent"),("Max drawdown","−18.4%","BTC −42.1%","danger"),("Win rate","68%","n=482 trades","")])`.
6. Two-column row:
   - Left: Equity curve (signal vs BTC) Plotly line chart inside `.ds-card`. Current code uses Plotly with the new `signal_dark`/`signal_light` template (transparent paper bg, gridcolor matches border, mono ticks). Legend below.
   - Right: `optuna_top_card(rows=[{rank:1,star:True,params:"rsi_period=14, macd=(12,26,9), regime_lb=30",sharpe:4.12,return_pct:342.8}, ...])` — 5 rows.
7. `recent_trades_card(rows=[...], title="Recent trades · signal-driven", subtitle="last 8 of 482")` — 5-column table.
8. **3 sub-views (existing st.tabs)** — `Summary`, `Trade History`, `Advanced Backtests`. These are deeper drill-downs. Recommendation: convert to a *secondary* segmented control below the KPI strip and equity card if any of them is heavily used; keep as `st.tabs()` if they're rarely visited and the current tabbed pattern works. See §6 Q8.

**Sections — Arbitrage view (segmented selection alternate):**

1. Top bar (same).
2. Page header — title shifts: "Opportunities" (Beginner/Intermediate) or "Arbitrage Scanner" (Advanced) — current `page_arbitrage` already implements this level-aware title.
3. Subtitle (level-aware): plain-English for Beginner ("Sometimes the same coin costs different amounts on different exchanges..."), technical for Advanced ("Cross-exchange spot price spreads and funding-rate carry trades. Net spread = gross spread − round-trip taker fees.").
4. Controls — `[Scan Now]` button + `[Min Net Spread %]` numeric input + `[freshness dot]` indicator (already implemented — `freshness_dot_html`).
5. Spot Price Spread section — `st.subheader("📊 Spot Price Spread")` + 4-metric strip (Pairs Scanned, Opportunities, Marginal, No Arb) + sortable table with color-coded Signal column and Net Spread column. Beginner/Intermediate tier shows "story cards" via `arb_opportunity_story_html`; Advanced shows technical expanders.
6. Funding-Rate Carry Trades section — table (Pair, Exchange, Funding Rate, Direction, Strategy, Annualized Yield) + caption explaining the strategy.
7. Historical Arbitrage Log expander — DB-backed table.

**Data sources:** Backtest — `_cached_backtest_df`, `optuna.load_study`, `_sg_cached_ohlcv` (BTC benchmark, 5min cache per P1-25). Arbitrage — `_arb.scan_all_arb(model.PAIRS)`, `_cached_arb_opportunities_df`.

**Existing components used:** `render_top_bar`, `page_header`, `backtest_controls_row`, `backtest_kpi_strip`, `optuna_top_card`, `recent_trades_card`, plus `freshness_dot_html` and `arb_opportunity_story_html` for arbitrage.

**New components needed:**
- `segmented_control(items=[("backtest","Backtest"),("arbitrage","Arbitrage")], active=...)` — generic, reusable across the app per D8. Must work with `st.button` callback pattern (no two-click lag).
- Arbitrage signal pill component (already partially in `_color_signal` / `_color_net` styles — should be promoted to a typed `arb_signal_pill` matching the design system).

---

### 3.5 On-chain — `page_onchain` (app.py 9707–9920)

| Field | Value |
|---|---|
| **Title** | "On-chain" |
| **Breadcrumb** | ("Research", "On-chain") |
| **Level variations** | None visible. See §6 Q5. |
| **Tabs** | None. |
| **Mockup** | NONE — needs to be built in Phase B. |
| **Mockup status** | New mockup. Inherits design tokens from Home / Signals; no novel components needed. |

**Sections in render order (per current code):**

1. Top bar.
2. Page header — title "On-chain", subtitle "Glassnode + Dune metrics for the major majors. MVRV-Z, SOPR, exchange flows, active addresses.", data-source pills (Glassnode live, Dune live, fallback to free Binance ticker for active addresses).
3. 3-column indicator cards — `indicator_card("BTC", [...])`, `indicator_card("ETH", [...])`, `indicator_card("XRP", [...])`. Each has 4 tiles: MVRV-Z, SOPR, Exch. reserve (7d flow), Active addr. (24h).
4. Whale activity section — `st.subheader("🐋 Whale Activity (BTC, last 24h)")` + table of large transfers (timestamp, coin, direction inflow/outflow, amount USD). Up to 8 rows. ⚠ Custom widget — could be promoted to a typed `whale_activity_table` in `ui/sidebar.py`.
5. Footnote `.ds-card` — "On-chain data is rate-limited on Glassnode free tier (cached 1h). MVRV-Z and SOPR refresh once per hour; whale events stream live."

**Data sources:** `st.session_state["scan_results"]` (per-coin on-chain metrics), `_cached_signals_df(500)` (DB fallback), `data_feeds.get_onchain_metrics(_pair)` (direct fetcher fallback), `_cached_whale_activity("BTC/USDT", 0.0)`.

**Existing components used:** `render_top_bar`, `page_header`, `indicator_card`.

**New components needed:**
- `whale_activity_table(events, max_rows=8)` — promotes the inline rendering to a typed helper. Each event row: `(timestamp, coin, direction:"inflow"|"outflow", amount_usd)`.
- Optional: `data_source_caption(text)` — small typed footnote card with rate-limit / refresh-cadence guidance, used here and potentially elsewhere.

---

### 3.6 Alerts — NEW PAGE (currently a tab inside Config Editor)

| Field | Value |
|---|---|
| **Title** | "Alerts" |
| **Breadcrumb** | ("Account", "Alerts") |
| **Level variations** | Same level system as everywhere else — Beginner gets plain-English explanations of alert types; Advanced gets full configuration controls. |
| **Tabs** | TBD — see §6 Q3. Recommended: 2 tabs OR segmented control: `[Configure]` and `[History]`. |
| **Mockup** | NONE — needs to be built in Phase B. |
| **Mockup status** | New page. Promote existing Config Editor → Alerts tab content into the new page; add an Alert History view that doesn't currently exist as a dedicated surface. |

**Sections in render order (proposed):**

1. Top bar.
2. Page header — title "Alerts", subtitle "Get notified when signals change, regimes shift, or thresholds break."
3. **Segmented control** — `[Configure] [History]` (D8 pattern).
4. **Configure view (default):**
   - Email toggle + recipient + sender + password (blank on load) + threshold slider — same as today's Config Editor → Alerts tab.
   - Save Alerts Config button + Test Email button.
   - Alert types panel — checkboxes for which signal events fire alerts (Buy crossings, Sell crossings, Regime transitions, On-chain divergences, Funding spikes).
5. **History view (alternate):**
   - Filter row — date range, alert type, status (sent / failed / suppressed).
   - Alert log table — timestamp, type, asset, message, status, channel.
   - Empty state if no alerts have fired yet.

**Data sources:** `_cached_alerts_config`, `_save_alerts_config_and_clear`, alerts log DB query (new — currently no UI surfaces fired-alert history; need to confirm `database.py` has the table or build a thin log layer).

**Existing components used:** `render_top_bar`, `page_header`, segmented control (new from §3.4).

**New components needed:**
- `segmented_control` (shared with Backtester).
- `alert_history_table(events, ...)` — typed log table.
- Possibly `alerts_log_db_query(filters)` — new DB layer if it doesn't exist.

---

### 3.7 AI Assistant — `page_agent` (app.py 8688–8984)

| Field | Value |
|---|---|
| **Title** | "AI Assistant" (Beginner/Intermediate) or "Autonomous Agent" (Advanced) — already level-aware in current code |
| **Breadcrumb** | ("Account", "AI Assistant") |
| **Level variations** | Already implemented — title, subtitle, status labels all flip per level. Beginner gets plain-English ("AI is watching the market"), Advanced gets technical ("▲ RUNNING"). |
| **Tabs** | None — flat scrollable per D8. |
| **Mockup** | NONE — needs to be built in Phase B. |
| **Mockup status** | New page. Inherits design tokens; agent surface is content-rich and needs full-width treatment. |

**Sections in render order:**

1. Top bar — with a status pill in the topbar ("Agent: ✓ Running" or "Agent: ⏸ Stopped") so the user sees agent state from any page.
2. Page header — title (level-aware), subtitle (level-aware).
3. Live status row — 3-column: status badge (success/warning/info per running/stopping/stopped), `[▶ Start]` button (primary, disabled when running), `[■ Stop]` button (secondary, disabled when stopped).
4. Metrics strip — 4-column: Total Cycles, Last Cycle (Xs/Xm/Xh ago), Last Pair, Last Decision (with icon: 🟢 approve, 🔴 reject, ⚪ skip).
5. Engine indicator row — 2-column: Crash Restarts, Engine ("LangGraph state machine" or "Sequential pipeline").
6. In-progress indicator (conditional) — `st.info(f"⏳ Processing {pair} — cycle running for {elapsed}s")` when active.
7. Agent Configuration section header.
8. Configuration form (`st.form`) — 2-column grid of 8 controls: Dry Run toggle, Cycle Interval, Min Confidence to Act, Max Trade Size %, Max Concurrent Positions, Daily Loss Limit %, Portfolio Size USD, Max Drawdown %, Cooldown After Loss. Submit button "💾 Save Agent Config".
9. Active Limits expander — shows current effective values with custom-override badges (`🔧 custom`).
10. Emergency Controls section header — "Overrides all other config — instant effect".
11. Emergency Stop row — 2-column: status text + activate/clear button (primary red when activating, secondary green when clearing).
12. Pipeline Architecture notes — `st.code(...)` block describing the agent flow.

**Data sources:** `_agent.supervisor.status`, `_agent.get_agent_config`, `_agent.save_overrides`, `_agent.get_active_limits`, `_agent.is_emergency_stop`, `_agent.set_emergency_stop`, `_cached_alerts_config`, `_save_alerts_config_and_clear`.

**Existing components used:** `render_top_bar`, `page_header`, `_ui.section_header` (existing).

**New components needed:**
- `agent_status_topbar_pill(state, label)` — small typed pill that lives in `render_top_bar`'s status_pills slot, visible from every page so the agent's running state is glanceable.
- Possibly `metric_strip(items)` — generic 4-or-5 column metric row that both `page_agent` and `page_dashboard`'s macro strip can share. (May already exist as `macro_strip`; check for unification.)

---

### 3.8 Settings — `page_config` (app.py 5125–6242)

| Field | Value |
|---|---|
| **Title** | "Settings" (Beginner/Intermediate) or "Config Editor" (Advanced) — already level-aware in current code |
| **Breadcrumb** | ("Account", "Settings") |
| **Level variations** | Beginner sees a 3-control quick-panel BEFORE the full tabs (Portfolio Size, Risk Per Trade %, API Key expander), then "More settings" divider, then full tab stack. Intermediate/Advanced jump straight to full tabs. |
| **Tabs** | **5 tabs (KEPT per D8):** "📊 Trading", "⚡ Signal & Risk", "🔔 Alerts", "🛠️ Dev Tools", "⚙️ Execution". Per the research, Settings is the right surface for tabs (low-frequency, grouped, drawer-like). |
| **Mockup** | NONE for the parent page or any tab — needs to be built in Phase B. |
| **Mockup status** | New mockups for parent + 5 tabs. ⚠ The Alerts tab here may need to be **removed or shrunk** because the new Alerts sidebar item supersedes it. See §6 Q3. |

**Sections in render order (parent page chrome):**

1. Top bar.
2. Page header — title (level-aware), subtitle (level-aware).
3. Beginner quick-panel (Beginner only) — 3 controls + "More settings ↓" divider. Falls through to tabs after.
4. Tab bar — 5 tabs.

**Tab 1 — Trading:**
- Trading Pairs multiselect.
- Custom Pair input.
- Timeframes multiselect.
- TA Exchange selectbox.
- Display Preferences expander — Regional Color Toggle (red-up vs red-down regional preference).

**Tab 2 — Signal & Risk:**
- Portfolio Size USD input.
- Risk Per Trade % slider.
- Max Exposure % slider.
- Max Position Cap USD.
- Max Open Per Pair.
- High-Confidence Threshold slider.
- MTF Alignment Threshold slider.

**Tab 3 — Alerts:** ⚠ See §6 Q3. Either:
- Removed (Alerts now has its own sidebar item) — tab disappears, count drops to 4.
- Kept as a quick-edit shortcut to common alert config; full alert work happens on the standalone Alerts page.

**Tab 4 — Dev Tools:** ⚠ Not fully read in this pass. Likely contains:
- Optuna study tools.
- Cache invalidation buttons.
- Diagnostic snapshots.
- Engineer-only toggles.

**Tab 5 — Execution:** ⚠ Not fully read in this pass. Likely contains:
- Paper / Live trading toggle.
- Exchange API key configuration.
- Order routing preferences.
- Slippage model parameters.

Both Tabs 4 and 5 need a focused read pass before mockups go to Phase B. Flagged in §6 Q9.

**Data sources:** `_cached_alerts_config`, `model.PAIRS / TIMEFRAMES / TA_EXCHANGE`, `model.load_config_overrides`, `_ws.start(model.PAIRS)`, `model.save_weights`, `_db.clear_weights`.

**Existing components used:** `render_top_bar`, `page_header`, `_ui.section_header`, `render_regional_color_toggle`.

**New components needed:**
- Possibly typed wrappers for the form rows (label + control + help-tooltip) so spacing is consistent across all 5 tabs. Decide during Phase B mockup.

---

## 4. Cross-cutting concerns

### 4.1 Topbar pattern (every page)

Every page calls `render_top_bar(breadcrumb=..., user_level=..., on_refresh=..., on_theme=..., status_pills=[...])`. Pills slot is where status indicators live (Paper/Live trading, Claude AI status, Demo mode, Agent running, etc.). Per D7 the agent status pill lives here on every page.

### 4.2 Level system (every page)

Beginner / Intermediate / Advanced. Set via `st.session_state["user_level"]`. Read via `current_user_level()` helper. Affects: page titles, subtitles, content density, plain-English vs technical labels, expanded vs collapsed states, advanced controls visible vs hidden. Per CLAUDE.md §7 the level is observed app-wide; gaps where it's not observed are §6 Q5 follow-ups.

### 4.3 Theme toggle (every page)

Dark / Light. Set via `st.session_state["theme"]`. Calls `inject_theme(app, theme)` at top of every page. Plotly charts pick up theme via `register_plotly_template(theme)` called on theme change.

### 4.4 Refresh button (every page)

Topbar refresh button calls `_refresh_all_data` which clears caches for the current page's data sources. Two-channel feedback (toast + persistent caption "✓ refreshed Xs ago") already implemented per the H1+H2 fix.

### 4.5 Mobile breakpoints

`@media (max-width: 768px)` already defined in mockups: sidebar moves to bottom rail (4-5 items + hamburger for the rest), level pills hide on narrow viewports, hero card price scales down, grids collapse to single column. Existing implementation matches mockups.

### 4.6 Plotly template

Single source of truth at `ui/plotly_template.py`. Two registered templates: `signal_dark` and `signal_light`. Transparent paper/plot bg (charts sit inside `.ds-card` containers), Inter font UI / JetBrains Mono ticks, gridcolor matches `--border`. `register_default(theme)` called on theme change. `apply(fig, theme)` for retro-fitting existing figures.

### 4.7 Component library status

`ui/sidebar.py` exports ~25 typed components (see §3 references). Coverage is strong for the 4 anchor mockups (Home, Signals, Backtester, Regimes). Gaps surface naturally per page in §3 — the new components needed across the inventory:

| New component | Used by | Phase B priority |
|---|---|---|
| `segmented_control(items, active, on_select)` | Backtester (Backtest \| Arbitrage), Alerts (Configure \| History) | HIGH — needed first |
| `whale_activity_table(events, max_rows=8)` | On-chain | MEDIUM |
| `data_source_caption(text)` | On-chain (footnote), maybe others | LOW |
| `alert_history_table(events, filters)` | Alerts → History | MEDIUM |
| `agent_status_topbar_pill(state, label)` | Agent surface visibility on every page | MEDIUM |
| Optionally: `metric_strip(items)` (generic, may unify with `macro_strip`) | Dashboard, Agent, Backtester | LOW |

---

## 5. Existing 4 mockups — revision pass needed?

Per D7 (revisable), the existing 4 mockups (Home, Signals, Backtester, Regimes) may need touch-ups when Phase B builds the new mockups. Likely revisions:

| Mockup | Revision needed? | Why |
|---|---|---|
| Home | Maybe | If §6 Q4 resolves to "remove the old tab stack below", the mockup may need to gain a 6th component (or stay as-is and we just delete the legacy code). |
| Signals | Maybe | If §6 Q6 keeps the 5-tile inline strip (Token Unlocks added), the mockup needs a 5th tile. |
| Backtester | YES (small) | Add the segmented control above the existing Backtest content. The Arbitrage mockup is a NEW file, not a revision. |
| Regimes | No | Already matches code intent. |

Each revision will be staged in the Phase B branch with a clear commit message so it's easy to review.

---

## 6. Open questions for sign-off

These are the points where I need a yes/no/override from the user before Phase B begins. Numbered for easy reference.

**Q1. Flare chain icon at line 99 of `sibling-family-flare-defi-MARKET-INTELLIGENCE.html`:** Leave magenta `#e847a8` (Flare's brand color, distinguishes from Ethereum at `#1d4ed8` two rows above) or force flare-blue `#1d4ed8`? *Recommendation: leave as-is.*

**Q2. AI Agent placement in the new sidebar:** Confirmed as `Account: Alerts · AI Assistant · Settings` (8-item nav, AI Assistant gets full page real estate). Override only if you want it elsewhere. *Recommendation: confirmed.*

**Q3. Alerts — separate page or tab-deeplink to Settings?** Two options:
- **Option A (recommended):** Promote `Alerts` to its own page with a 2-view segmented control: `Configure` (existing alert config UI from Settings → Alerts tab) + `History` (new view of fired alerts). The Settings → Alerts tab gets removed (count drops to 4). One canonical entry point per concern.
- **Option B:** Keep Alerts as a tab inside Settings; the sidebar `Alerts` item just deep-links to that tab. No History view.

Option A is the research-backed pattern (separate concern → separate surface). Option B is the path of least implementation work. *Recommendation: Option A.*

**Q4. Dashboard's "old tab stack below" the new flat content:** The current `page_dashboard` renders the new mockup-style hero cards / macro strip / watchlist / backtest preview at the top, then drops into a legacy tabbed dashboard below. Three options:
- **Option A (recommended):** Delete the legacy tab stack. The new content above is what was meant to replace it. Page becomes pure flat-scrollable per the mockup.
- **Option B:** Keep the legacy stack temporarily as a fallback during Phase C implementation, removed in a follow-up.
- **Option C:** Promote some legacy tabs to first-class sidebar items (e.g., something currently in a legacy tab that's not yet covered by the new pages).

*Recommendation: Option A unless the legacy stack contains something we haven't already covered in Signals/Regimes/On-chain/Backtester.*

**Q5. Level-system observation gap on Signals / Regimes / On-chain pages:** Current code doesn't appear to differentiate content per level on these 3 pages. Per CLAUDE.md §7 the level system applies app-wide. Two options:
- **Option A (recommended):** Add level-aware variations as part of Phase C. Beginner gets plain-English signal interpretation cards; Intermediate gets condensed; Advanced gets raw values + diagnostics. Effort is medium per page.
- **Option B:** Confirm these pages are intentionally level-agnostic and document the exception in CLAUDE.md §7.

*Recommendation: Option A — adds real user value, effort is contained.*

**Q6. Signals — 4-tile or 5-tile inline strip?** Mockup shows 4 tiles (Vol, ATR, Beta, Funding). Current code adds a 5th (Token Unlocks). Two options:
- **Option A (recommended):** Keep the 5th tile (Token Unlocks is a real Layer-3 signal worth surfacing) and revise the mockup to show 5.
- **Option B:** Remove the 5th tile from current code to match mockup at 4.

*Recommendation: Option A — Token Unlocks is genuinely valuable info, mockup revision is one-line.*

**Q7. BTC regime state bar — 100% single segment vs full segmented timeline:** Current code renders one 100% segment because there's no `regime_history` table populated. Two options:
- **Option A:** Build a thin `regime_history` data layer (HMM regime per day for last 90d, persisted to DB) so the segmented bar in the mockup actually renders. New data layer scope.
- **Option B:** Strip the segmented bar from the mockup; show a simpler "Current regime: Bull · since X · 12d stable" text. Less informative but works today.

*Recommendation: Option A — the segmented bar is one of the strongest visual signals on the Regimes page. Worth the small data-layer build.*

**Q8. Backtester — Summary / Trade History / Advanced Backtests sub-tabs:** Currently `st.tabs([Summary, Trade History, Advanced])`. Per D8 (hybrid), three options:
- **Option A:** Keep as `st.tabs()` since these are deeper drill-downs, low-frequency, grouped — settings-tab-pattern applies.
- **Option B:** Promote to a secondary segmented control below the KPI strip / equity card. Lighter feel, mobile-friendlier.
- **Option C:** Flatten — Summary becomes the default Backtest content, Trade History and Advanced get pulled into expanders.

*Recommendation: Option B — segmented control matches the primary `Backtest | Arbitrage` pattern and stays consistent.*

**Q9. Settings — Tabs 4 (Dev Tools) and 5 (Execution):** I haven't yet read these in detail. Will do a focused read pass before mockups for these tabs go to Phase B. Need confirmation: are both tabs in active use, or are either of them deprecated / hidden behind a feature flag?

*Action: I'll read in next turn unless you tell me one or both are deprecated.*

**Q10. Shared-docs versioning:** `C:\dev\Cowork\shared-docs\` has no `.git`. Where does this folder get versioned long-term? Options:
- Separate parent repo (e.g., `cowork-shared-docs`).
- Submodule inside each app repo.
- Manual versioning / personal backup.

Phase B will write 10+ new mockup files there; need to know how to make them durable. *Action: tell me your setup.*

---

## 7. Phase B — Mockup-build scope and batch order

After this inventory is signed off, Phase B builds HTML mockups one batch at a time. Each batch ends with user review in browser before the next batch starts. Files go in `shared-docs/design-mockups/` with the existing naming convention `sibling-family-crypto-signal-<PAGE>[-<TAB>].html`.

| Batch | Files | Scope | Approx effort |
|---|---|---|---|
| **B1** | `sibling-family-crypto-signal-ON-CHAIN.html` | New mockup matching `page_onchain`. Validates the design system on a non-anchor page first; cheapest test. | 1 file |
| **B2** | `sibling-family-crypto-signal-BACKTESTER.html` (revision) + `sibling-family-crypto-signal-BACKTESTER-ARBITRAGE.html` (new) | Revise existing Backtester mockup to add segmented control above content. New Arbitrage mockup matching `page_arbitrage` (with Beginner story-card and Advanced expander variants). | 2 files (1 revision, 1 new) |
| **B3** | `sibling-family-crypto-signal-ALERTS.html` + `sibling-family-crypto-signal-ALERTS-HISTORY.html` | Two views of the new Alerts page (Configure + History). Pending Q3 resolution. | 2 files |
| **B4** | `sibling-family-crypto-signal-AI-ASSISTANT.html` | New mockup for the agent surface — full-page treatment with all 12 sections from §3.7. | 1 file |
| **B5** | `sibling-family-crypto-signal-SETTINGS.html` (parent) + `sibling-family-crypto-signal-SETTINGS-TRADING.html` + `sibling-family-crypto-signal-SETTINGS-SIGNAL-RISK.html` + `sibling-family-crypto-signal-SETTINGS-DEV-TOOLS.html` + `sibling-family-crypto-signal-SETTINGS-EXECUTION.html` (and possibly `sibling-family-crypto-signal-SETTINGS-ALERTS.html` if Q3 resolves to Option B) | Settings parent + 4–5 tab body mockups. Beginner quick-panel variant of parent. | 5–6 files |
| **B6** | Revisions to anchor mockups (Home, Signals) per Q4 + Q6 | Touch-ups, not new files. | 0–2 mockup edits |

Total file output for Phase B: **11–13 mockups** (10 new + 1–3 revisions). Each batch sized for one focused review session.

---

## 8. Phase C preview — what implementation looks like after mockups land

(Not in scope for this inventory; included for context so D2's audit-first cadence is concrete.)

After every batch in Phase B is signed off:

1. Component-by-component implementation in `ui/sidebar.py` (or `ui/components.py` if scope justifies extracting a separate module). Each new component gets its own commit + a small unit test.
2. Wiring updates in `app.py` — new page functions for Alerts (if Q3 → Option A), updated `PAGE_KEY_TO_APP`, segmented control replacing `st.tabs()` where applicable.
3. Routing layer fix — sidebar nav keys map cleanly to live page functions per the new `PAGE_KEY_TO_APP`.
4. Per-page level-aware variations (Q5).
5. New `regime_history` data layer if Q7 → Option A.
6. New alerts log DB query / table if needed for Q3 → Option A.
7. Per-batch `§4 audit pass` (correctness/tests/optimization/efficiency/accuracy/speed/UI-UX) before commit, per master template §24 trigger matrix.
8. Per-batch `tests/verify_deployment.py --env prod` smoke test, per §25 Part A.
9. Single PR back to main when all batches land. Worktree cleanup (D3 deferred). Single canonical URL: `github.com/davidduraesdd1-blip/crypto-signal-app`.

Cold-start budget: stays under 60s on Streamlit Cloud (lazy-load LightGBM/XGBoost preserved).

---

## 9. Sign-off

User to review §6 (Q1–Q10) and either confirm recommendations or override per question. Once all 10 are resolved, this document gets committed to `main` (via the redesign branch's eventual PR), and Phase B Batch 1 (On-chain mockup) starts.

Inventory prepared by: Claude Opus 4.7 (1M context).
Next concrete action after sign-off: focused read pass on Settings → Dev Tools and Settings → Execution tabs (Q9), then Batch 1 mockup build.
