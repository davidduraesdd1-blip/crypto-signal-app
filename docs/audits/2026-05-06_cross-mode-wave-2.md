# Cross-Mode QA — Wave 2

**Date:** 2026-05-06
**Scope:** `web/app/` (16 routes) + `web/components/` (~45 custom components)
**Methodology:** static read-through. Verifies the 2026-05-05 Wave-1 findings, audits per-page tier coverage in depth, walks Beginner-mode UX flow, and maps edge-case failure UX per page.
**Reference:** `docs/audits/2026-05-05_cross-mode-qa.md` (Wave 1)

---

## Executive summary

Phase 0.9 P0-5 wired `<UserLevelProvider>` + `useUserLevel()` correctly — the plumbing is solid. But only **2 of 16 user-facing pages** currently consume `useUserLevel`. The radiogroup in the topbar still does nothing on 14 routes. The Wave-1 a11y / theme / tap-target findings closed **0 of 9** in the explicitly enumerated remaining items — every hardcoded hex literal, every `<div onClick=>`, every sub-44px tap target, and every color-only encoding flagged in Wave 1 is still in the tree.

**Wave-1 verification scoreboard: 1 P0 fixed (UserLevelProvider plumbing) + 1 partial (`<UserLevelProvider>` exists, Topbar refactored, default flipped to Beginner per §7), 9 line-level fixes still open.**

The single largest user-facing impact item: **Beginner walkthrough is jargon-heavy from the first screen** — even with the new `useUserLevel` plumbing, a Beginner who lands on Home → Signals → Alerts sees "MVRV-Z", "SOPR", "DXY", "HMM regime", "8h funding", "ADX (14)", "Optuna-tuned", "TPE sampler" with zero glossary scaffolding. The §7 Beginner-tier promise ("plain English, zero jargon, tooltips always visible") is still aspirational.

---

## A. Wave-1 verification table

| Wave-1 item | Severity | Wave-1 status | Wave-2 verification | Outcome |
|---|---|---|---|---|
| UserLevelProvider missing — radiogroup decorative | **P0 / critical** | Not wired | `web/providers/user-level-provider.tsx` exists, `<UserLevelProvider>` mounted in `app-providers.tsx:27`, Topbar consumes via `useUserLevel()` (topbar.tsx:25), default flipped to "Beginner" per §7. **Plumbing complete.** | **CLOSED** |
| Per-page tier-gating (15 pages don't read level) | P0 | All 15 missing | Now: `app/signals/page.tsx:200`, `app/backtester/arbitrage/page.tsx:53` consume level. **Remaining 14 pages don't.** | **PARTIAL — 2/16, 14 open** |
| `app/backtester/arbitrage/page.tsx:147-174` mis-labeled "Beginner view" shown to all tiers | High | Misleading | Now gated correctly behind `level === "Beginner"` (line 151). | **CLOSED** |
| `alert-type-card.tsx:18-26` `<div onClick=>` not keyboard-accessible | P0 | Open | **Still `<div onClick={onToggle}>` (alert-type-card.tsx:19-26).** No `role`, no `tabIndex`, no `onKeyDown`. The 5-row alert-type list on `app/alerts/page.tsx` is mouse-only. | **OPEN** |
| Skip-to-content link missing, `<main>` has no `id="main"` | Medium-High | Missing | `app-shell.tsx:29` `<main>` still has no id, no skip link anywhere in the tree. | **OPEN** |
| Toggle-switch tap targets 24px tall (cross-cutting) | P1 | Open | `toggle-switch.tsx:36` still `h-6 w-[42px]`, `agent-config-card.tsx:113` still `h-6 w-11`, `app/settings/execution/page.tsx:141, 180` still `h-6 w-11`, `app/settings/trading/page.tsx:391` still `h-6 w-11`. | **OPEN** |
| `decisions-table.tsx:22-26` 🟢🔴⚪ color-only emoji encoding | P1 | Open | **Unchanged (lines 22-26).** Still `{ approve: "🟢", reject: "🔴", skip: "⚪" }`. Color-blind users cannot distinguish. | **OPEN** |
| `watchlist.tsx:66` SVG sparkline hardcoded `#22c55e` / `#ef4444` | P3 | Open | Unchanged. | **OPEN** |
| `app/alerts/page.tsx:192` slider thumb halo `rgba(34,211,111,0.2)` | P3 | Open | Unchanged. | **OPEN** |
| `app/settings/execution/page.tsx:54`, `signal-risk/page.tsx:64` legacy `#00d4aa` fallback (current accent is `#22d36f`) | P3 | Open | Both unchanged. | **OPEN** |
| Alerts/history pagination buttons `h-7` (28px) | P2 | Open | Unchanged (alerts/history/page.tsx:213, 224, 235). | **OPEN** |
| `app/alerts/page.tsx` 3 inputs missing `htmlFor` | P2 | Open | Unchanged (lines 137-148, 151-159, 161-175 still naked `<label>`). | **OPEN** |
| `app/settings/execution/page.tsx` autoExecute toggle missing `aria-label` | P1 | Open | Unchanged (line 177-191). | **OPEN** |
| Light-mode `text-success`/`text-danger`/`text-warning` body-size legibility | P1 | Open | All offending components still use the same classes: `watchlist.tsx:54`, `signal-hero.tsx:75,79,83`, `signal-history.tsx`, `trades-table.tsx`, `optuna-table.tsx`, `funding-carry-table.tsx:24`. | **OPEN** |
| `funding-carry-table.tsx:24` color-only +/- direction | P1 | Open | Unchanged — `rateClass()` returns text-success/text-danger only, no shape pair. | **OPEN** |
| `signal-hero.tsx` 24h/30d/1y % color-only | Medium | Open | Unchanged. | **OPEN** |
| Custom buttons missing explicit `focus-visible:ring-*` | Medium | Open | Custom buttons in `app/*/page.tsx` and most `components/*.tsx` still rely on global `outline-ring/50`. | **OPEN** |
| Hardcoded Tailwind class typos / stale comments in 4 components | None (cosmetic) | Documented | Unchanged comments. **None** (justified per Wave-1 — informational only). | **N/A** |

**Net:** Of 17 distinct findings, **3 closed** (UserLevelProvider, arbitrage hardcoded "Beginner view" gated, default level). **14 open**, including the 2 P0 items (`<div onClick=>` and tier coverage gap on 14 pages).

---

## B. Per-page tier-coverage assessment

Pages that consume `useUserLevel`: **2 of 16** (`app/signals/page.tsx`, `app/backtester/arbitrage/page.tsx`). The `useUserLevel` import grep is the source of truth.

```
✓ app/signals/page.tsx:16,200
✓ app/backtester/arbitrage/page.tsx:14,53

✗ app/page.tsx                  (Home — landing page!)
✗ app/regimes/page.tsx
✗ app/on-chain/page.tsx
✗ app/alerts/page.tsx
✗ app/alerts/history/page.tsx
✗ app/backtester/page.tsx       (the OTHER backtester page is unwired)
✗ app/ai-assistant/page.tsx
✗ app/settings/layout.tsx
✗ app/settings/trading/page.tsx
✗ app/settings/signal-risk/page.tsx
✗ app/settings/dev-tools/page.tsx
✗ app/settings/execution/page.tsx
✗ app/error.tsx                  (justified — error pages tier-agnostic)
✗ app/not-found.tsx              (justified)
✗ app/global-error.tsx           (justified — dependency-free fallback)
```

### B.1 — Quality check on the 2 wired pages

**`app/signals/page.tsx` (level === Beginner gate at line 454-479):**

Beginner currently gets a single "What does this mean for me?" card below the SignalHero — the copy is decent (3 prose sentences, no jargon, references confidence + direction). **Quality: GOOD but THIN.**

Issues:
- Beginner still sees the multi-timeframe strip with raw "1h / 4h / 1d / 1w / 1M" labels — should hide or relabel as "Hourly / 4-hour / Daily / Weekly / Monthly" at Beginner.
- Beginner still sees the **Composite Score** card with the 0-100 number and the "Per-layer breakdown not in V1" footnote — Beginner shouldn't see "composite" or "per-layer" terminology.
- Beginner still sees the **Technical / On-chain / Sentiment** indicator grids with raw RSI / MACD / ADX / MVRV-Z / SOPR / Fear&Greed labels — these ARE jargon, no plain-English alternative shown.
- Advanced gets nothing extra (no per-pair Optuna params, no regime-adjusted weight readout, no raw composite layer scores) — Advanced is currently identical to Intermediate.

**Verdict: Beginner gate is perfunctory — one paragraph of plain English isn't enough to satisfy §7's "tooltips always visible on every technical term, color-coded gauges, simplest possible error messages." Advanced isn't differentiated at all.**

**`app/backtester/arbitrage/page.tsx` (level === Beginner gate at line 151-179):**

Beginner gets a "Beginner view · same data, plain English" card with two narrative paragraphs about XRP/SOL spreads. **The card is HARDCODED MOCK DATA** (XRP $2.836, SOL $192.10) — when the live `arbQuery` returns real opportunities the Beginner card doesn't update. This is the same kind of dishonest copy that Wave 1 flagged on the original "shown when level = Beginner" caption.

Issues:
- Beginner sees BOTH the live spread table (jargon-heavy: net spread %, taker fees, exchange names) AND the prose card. Either hide the table at Beginner OR make the prose card the only spread display.
- The prose card mock data isn't reactive to live spreads — it'll always say XRP/Bybit→Coinbase even when the real top opportunity is something else.
- Funding-rate carry trades section below the gate is shown to all tiers with full jargon ("perp funding deltas", "8h cycle", "annualized yield") — no Beginner-friendly alt.
- Advanced gets nothing extra.

**Verdict: Better than nothing, but the static prose card lies about live data — net behavior is "Beginner sees a misleading static card on top of the same jargon-heavy table everyone else sees."**

### B.2 — Per-page level-gate proposals (the 14 missing pages)

Format per page: current state → **Beginner** / **Intermediate** (default) / **Advanced** with concrete level-gated proposals.

#### B.2.1 — `app/page.tsx` (Home) — TOP PRIORITY (landing page)

Current: identical for all tiers. Hero-card grid (5 SignalCards), MacroStrip (BTC dominance/F&G/DXY/Funding/Regime), Watchlist (6 rows), BacktestCard (4 KPIs).

- **Beginner:** Hide MacroStrip entirely (BTC dominance, DXY, funding, regime — pure jargon at this tier). Replace with a 1-paragraph "Today's market mood" card: "Markets are showing risk-on confidence. The model favors holding crypto over cash today, with BTC and ETH leading." Add a one-line caption above the SignalCard grid: "Top 5 coins to watch right now — green ▲ means the model sees upside, red ▼ means downside, ■ means hold." Hide BacktestCard entirely (CAGR, Sharpe, win-rate are jargon — replace with a "How accurate is this model?" card with a single sentence: "Tracked 423 signals over the last 90 days; 64% were correct.").
- **Intermediate (default):** Current layout. ✓
- **Advanced:** Add per-pair confidence in raw % (already there) plus regime tag chip on each SignalCard, plus a "Composite weighting: Tech 30% / Macro 15% / Sentiment 20% / On-chain 35%" footer banner, plus the optional Optuna-best-run readout from the BacktestCard.

#### B.2.2 — `app/regimes/page.tsx`

Current: identical. RegimeCard grid + RegimeTimeline + MacroOverlay + RegimeWeights.

- **Beginner:** Show only the RegimeCard grid + a single explainer card: "What's a 'regime'? It's the market's overall mood right now — bull (going up), bear (going down), accumulation (building before a move up), distribution (selling before a move down), or transition (switching states). The HMM model below decides which mood we're in by looking at price, on-chain data, and macro indicators all together." Hide RegimeTimeline + MacroOverlay + RegimeWeights (they're all dense reference material).
- **Intermediate:** Current layout minus the RegimeWeights matrix at the bottom (intermediate doesn't need to see Layer-by-layer weight tables).
- **Advanced:** Current full layout PLUS expose the raw HMM transition probability matrix in a debug card at the bottom (read it from the future `/regimes/{pair}/history` endpoint when wired).

#### B.2.3 — `app/on-chain/page.tsx`

Current: 3-column dashboard for BTC / ETH / XRP showing MVRV-Z, SOPR, Net flow, Whale activity raw values.

- **Beginner:** Replace each metric tile's raw value with a colored gauge + plain-English label. E.g. instead of "MVRV-Z: 4.21 / mid-cycle" show a teal gauge labeled "Where are we in the cycle? Mid-cycle". Instead of "Net flow: -28,432" show a green gauge "Coins leaving exchanges? Yes — usually bullish". Add a leading explainer card: "On-chain data tracks what's actually happening on the blockchain — how many coins are moving to/from exchanges, whether holders are profitable, and whether big wallets are active. It's harder to fake than price charts."
- **Intermediate:** Current value + subtext (e.g. "4.21 mid-cycle"). ✓
- **Advanced:** Show all 4 metrics PLUS expose the raw 7-day delta arrays via expandable sub-card; surface the data-source pill (Glassnode vs Dune vs cached) inline; add an "active addresses" tile (currently hidden — needs `/onchain/dashboard` enrichment).

#### B.2.4 — `app/alerts/page.tsx`

Current: configure email + alert-type checklist + delivery channels.

- **Beginner:** Hide the SMTP password field entirely (advanced concept — auto-use the server-side default). Replace 5 alert-type cards with **3 grouped presets**: "Big moves only" (BUY/SELL crossings only), "Big moves + market regime shifts" (adds regime), "Everything" (all 5 types). Hide the "High-confidence threshold" slider (auto-use 75%). Hide Slack/Telegram/Browser-push channels, show only Email.
- **Intermediate (default):** Current layout. ✓
- **Advanced:** Current layout PLUS expose the per-channel rate-limit slider (currently hardcoded), expose the per-alert-type cooldown (suppress duplicate alerts within X mins), and expose the alert-payload template (so power users can customize the email subject/body). All these would need new `/alerts/config` fields.

#### B.2.5 — `app/alerts/history/page.tsx`

Current: stat strip + filter row + alert-log table + pagination.

- **Beginner:** Hide the 4-stat strip entirely (jargon: "Sent rate", "Avg latency"). Hide the filter row (all 5 dropdowns). Show just the table with 10 most recent alerts and an "Older alerts" link at the bottom (no pagination controls). Show channel column hidden — Beginner only has email anyway.
- **Intermediate (default):** Current layout. ✓
- **Advanced:** Current PLUS add a "Suppression log" sub-tab showing alerts that fired but were rate-limited, plus an "Export to CSV" button (currently mocked).

#### B.2.6 — `app/backtester/page.tsx`

Current: ControlButton row + 5-KPI strip + EquityCurve + OptunaTable + TradesTable.

- **Beginner:** Hide ControlButton row (Universe / Period / Initial / Rebalance / Costs are all advanced terms). Replace with a single "Tested on the top 10 coins, last 3 years" caption. Hide OptunaTable entirely (TPE sampler / 2,400 trials / Sharpe is pure quant jargon). Replace 5-KPI strip with a 3-card hero: "How much money would you have made?" (Avg PnL), "How often was the model right?" (Win rate), "What's the worst loss it ever had?" (Max drawdown). Hide EquityCurve OR keep with a plain-English caption "your $100,000 grew to $342,800 over 3 years if you followed every signal".
- **Intermediate (default):** Current layout MINUS the OptunaTable (it's quant-only).
- **Advanced:** Current full layout + EquityCurve overlay vs BTC-baseline (explicit benchmark), expose all 2,400 Optuna trial results in an expandable sub-table (paginated), add Sortino + Calmar + per-regime PnL breakdown.

#### B.2.7 — `app/ai-assistant/page.tsx`

Current: AgentStatusCard + AgentMetricStrip + DecisionsTable + PipelineDiagram + AgentConfigCard + EmergencyStopCard + AskClaude form.

- **Beginner:** Hide AgentMetricStrip (Total Cycles / Last Cycle / Last Pair / Last Decision = jargon). Hide PipelineDiagram (it's an architecture poster). Hide AgentConfigCard (it's pure config). Show: AgentStatusCard ("Agent · Running"), simplified DecisionsTable (only the last 5 rows, columns = Time / Pair / Decision / Why-it-decided), a one-paragraph explainer "What does the AI agent do? Every X minutes it looks at the latest signals across all coins, decides whether to buy/sell/hold each one, and either executes the trade (live mode) or just logs the decision (paper mode). You can stop it at any time using the red button below." Show EmergencyStopCard. Show AskClaude form, but pre-fill the example fields and add a "Common questions" dropdown.
- **Intermediate (default):** Current layout MINUS PipelineDiagram (it's reference material).
- **Advanced:** Current full layout + expose raw `composite_score` + `regime_state` + `mtf_alignment` columns in DecisionsTable + add a "Replay this decision" button per row (re-runs the model with the same inputs and shows the trace).

#### B.2.8 — `app/settings/layout.tsx` (the tab navigation wrapper)

Current: 4 tabs, identical for all tiers.

- **Beginner:** Hide "Dev Tools" tab (it's all infrastructure). Hide "Execution" tab (live trading is dangerous; Beginner shouldn't enable it). Show only "Trading" + "Signal & Risk".
- **Intermediate (default):** Current 4 tabs. ✓
- **Advanced:** Current 4 tabs PLUS rename page header from "Settings" to "Config Editor" (per the leftover subtitle hint in `subtitles[\"/settings/trading\"]:18`).

#### B.2.9 — `app/settings/trading/page.tsx`

Current: pairs picker + timeframe pills + TA exchange + 2 toggles.

- **Beginner:** Replace pair picker with **3 preset bundles**: "Big 3" (BTC / ETH / XRP), "Top 10", "Top 25". Hide timeframe selector (auto-use 1h+4h+1d). Hide TA exchange (auto-use Kraken primary). Hide regional-color + compact-watchlist toggles. Show one "Reset to defaults" button.
- **Intermediate (default):** Current layout MINUS the timeframe selector (default to engine-recommended 1h/4h/1d). Add tooltips on each toggle.
- **Advanced:** Current full layout PLUS exposed `_TRADING_KEYS` allowlist (currently hidden in the FastAPI router), allow custom pair entry beyond the 8 defaults, allow per-pair timeframe override.

#### B.2.10 — `app/settings/signal-risk/page.tsx`

Current: 4 sliders (min confidence / high-conf / min-alert / max DD) + 1 input (position size %) + composite-weight reference table.

- **Beginner:** Replace 4 sliders with **3 risk presets**: "Conservative" (min conf 75%, max DD 5%, position 2%), "Balanced" (60/10/5), "Aggressive" (50/15/10). Show the resulting numbers below the chosen preset card so the user can see what they mean. Hide the composite-weights reference table.
- **Intermediate (default):** Current sliders with a tooltip on each. Add an explainer paragraph at the top.
- **Advanced:** Current sliders + composite-weights table + add per-regime weight override card (currently the weights are global) + expose Optuna-tuned values inline ("Tuned value: 73 — your value: 75").

#### B.2.11 — `app/settings/dev-tools/page.tsx`

Current: API server controls + DB diagnostics + circuit breakers + reload buttons.

- **Beginner:** Hide entire page (per B.2.8 — Beginner shouldn't see Dev Tools tab at all). If the user navigates directly, render a "This page is for advanced users — switch to Advanced level to access Dev Tools" stub.
- **Intermediate (default):** Hide circuit-breaker controls + raw API host/port editor; show only "Restart engine" and DB health stats.
- **Advanced:** Current full layout. ✓

#### B.2.12 — `app/settings/execution/page.tsx`

Current: OKX API key + LIVE TRADING toggle + paper-mode toggle + auto-execute toggle + stop-loss input + entry-only-on-buy toggle + max-concurrent-positions input.

- **Beginner:** Hide entire page (per B.2.8). Stub: "Live trading is for advanced users only — switch to Advanced level to enable real-money trading."
- **Intermediate (default):** Show only "Paper trading mode" toggle (default ON, locked) + the read-only summary of which pairs are tracked. Hide LIVE TRADING toggle entirely until Advanced.
- **Advanced:** Current full layout including the LIVE TRADING + auto-execute toggles. Add a "are-you-sure?" double-confirm modal before LIVE TRADING flips to true.

### B.3 — Cross-cutting tier-aware UI primitives needed

To avoid 14 page-level branches, the audit recommends adding these primitives:

```tsx
// web/components/tiered-text.tsx — already proposed in Wave 1
<TieredText
  beginner="Bitcoin is showing strong upward momentum"
  intermediate="BTC · ▲ Strong buy · 4h"
  advanced="BTC/USDT · STRONG BUY · conf 87% · regime: Bull (since Apr 12)"
/>

// web/components/tier-only.tsx
<TierOnly tier="Beginner">…</TierOnly>
<TierOnly tier="Advanced">…</TierOnly>
<TierOnly minTier="Intermediate">…</TierOnly>

// web/components/tier-info-tooltip.tsx — auto-shows expanded glossary at Beginner, ⓘ-icon at Intermediate, hidden at Advanced
<TierInfoTooltip term="MVRV-Z" depth={{ beginner: "...", intermediate: "...", advanced: "..." }}>
  <span>MVRV-Z</span>
</TierInfoTooltip>
```

Estimated effort: 2 days for primitives + 4-5 days for the page-level branches across 14 routes.

---

## C. Beginner UX walkthrough — Home → Signals → Backtester → Alerts

Pretend Beginner just clicked "Beginner" in the topbar.

### C.1 — Land on Home (`app/page.tsx`)

Visible content:
- 5 hero SignalCards labeled "BTC · 104,280 · ▲ Buy · Bull · 76%" — **OK** (the SignalCard already pairs ▲▼■ with color, and 76% is intuitive).
- **MacroStrip** showing "BTC Dominance · 58.9% · +0.4 ppts · 7d" / "Fear & Greed · 72 · Greed" / "DXY · 104.21 · −0.6% · 30d" / "Funding · +0.012% · 8h" / "Regime · Risk-on · confidence 76%".
  - **CONFUSING:** Beginner won't know what "BTC Dominance", "Fear & Greed", "DXY", "8h funding", "Risk-on regime" mean.
  - "ppts" is jargon (percentage points) — write out "percentage points" or use "pts".
- **Watchlist** showing 6 coins with sparklines + change %.
  - **OK:** The ticker / price / +1.44% is universal.
  - **MARGINAL:** Sparkline color (green up / red down) is intuitive but not paired with shape — color-blind Beginner can't tell direction.
- **BacktestCard** showing "Return (90d) · +12.4% · live engine" / "Max drawdown · −8.2% · 423 trades" / "Sharpe · 1.84 · vs BTC baseline" / "Win rate · 64% · n=423 trades".
  - **CONFUSING:** "Sharpe", "Max drawdown", "vs BTC baseline" are jargon. Beginner has no idea what 1.84 means.

**Top Beginner grievances on Home:**
1. MacroStrip is 100% jargon.
2. BacktestCard's Sharpe / Max drawdown columns are jargon.
3. No "what is this app for?" intro card on first visit (per CLAUDE.md §7 "Welcome banner on first visit (dismissible, appears once)" — not implemented).

### C.2 — Click Signals (`app/signals/page.tsx`)

Visible content:
- CoinPicker (5 coins) + "Scan now" button — **OK**.
- SignalHero: "BTC / USDT · ▲ Buy · 4h · Strong · Bull · 87%". **OK** (shapes paired).
- **NEW** "What does this mean for me?" card (level === Beginner gate) — 3-sentence prose summary. **GOOD ✓**.
- Multi-timeframe strip: "1h / 4h / 1d / 1w / 1M" tiles each with ▲▼■ + score 0-100.
  - **CONFUSING:** Beginner won't know that 1d means "daily", and won't know what the 0-100 score means relative to "Strong" in the hero.
- PriceChart — **OK** (visual is universal).
- CompositeScore card: "85 · weighted: Tech / Macro / Sentiment / On-chain — Per-layer breakdown not in V1".
  - **CONFUSING:** "composite", "weighted layers" are jargon.
- Technical / On-chain / Sentiment indicator grids: RSI (14) / MACD / Supertrend / ADX (14) / MVRV-Z / SOPR / Net flow / Whale / Fear&Greed / Funding / Google trends / News sent.
  - **VERY CONFUSING:** This is the densest jargon block in the app. 12 technical-analysis terms with no glossary. The "what is X?" tooltip is missing on every tile.
- SignalHistory: 6 transitions with tiny ▲▼ + "+ 12.6%" returns.
  - **OK** (timestamps + return % are universal).

**Top Beginner grievances on Signals:**
4. Indicator grids (12 acronym tiles) — there's no tooltip/glossary scaffolding on any of them.
5. Composite Score's "Per-layer breakdown not in V1" is dev-speak leaking to user.
6. Multi-timeframe strip labels (1h/4h/1d/1w/1M) — should be "Hourly / 4-hour / Daily / Weekly / Monthly".

### C.3 — Click Backtester (`app/backtester/page.tsx`)

Visible content:
- ControlButton row: "Universe · Top 10 cap" / "Period · 2023-01-01 → today" / "Initial · $100,000" / "Rebalance · Weekly" / "Costs · 12 bps · realistic slippage".
  - **CONFUSING:** "Universe", "Rebalance", "Costs · 12 bps" are jargon. "Slippage" too.
- 5-KPI strip: "Avg PnL / Win rate / Sharpe / Max drawdown / Trades".
  - **CONFUSING:** "Sharpe", "Max drawdown" are jargon.
- SegmentedControl: Summary / Trade History / Advanced — **OK**.
- EquityCurve — **OK** (visual is universal).
- **OptunaTable** — 5 rows of `rsi_period=14, macd=(12,26,9), regime_lb=30 · Sharpe 4.12 · +342.8%`.
  - **EXTREMELY CONFUSING:** Optuna, RSI period, MACD tuple, regime_lookback, Sharpe — this is pure quant. Beginner sees gibberish.
- TradesTable: 8 rows of trade entries.
  - **OK** (date / side / pair / return %).

**Top Beginner grievances on Backtester:**
7. OptunaTable is 100% quant jargon — should be hidden at Beginner.
8. ControlButton row's "Costs · 12 bps · slippage" + "Rebalance · Weekly" + "Universe" — needs plain-English alternatives.

### C.4 — Click Alerts (`app/alerts/page.tsx`)

Visible content:
- SegmentedControl: Configure / History — **OK**.
- Email card: Recipient / Sender / SMTP Password / High-confidence threshold slider.
  - **CONFUSING:** "Sender (SMTP)", "SMTP Password", ".env.local" code snippet leaking dev-speak.
  - "High-confidence threshold" slider — Beginner won't know what to set it to.
- Alert-types card: 5 cards labeled with shape glyphs + technical descriptions ("Composite signal crosses BUY (≥ 70) or SELL (≤ 30) threshold", "HMM regime state changes (Bull → Transition → ...)", "Perpetual funding ≥ +0.05%", "Token unlock proximity").
  - **VERY CONFUSING:** Every description is technical. "HMM regime", "Perpetual funding", "MVRV-Z divergences", "Token unlock" — Beginner has no idea what these mean.
- Delivery channels: Email / Slack / Telegram / Browser push.
  - **OK** (channel names are universal).

**Top Beginner grievances on Alerts:**
9. SMTP / `.env.local` / encryption-via-Render = dev-speak in user-facing copy.
10. 5 alert-type descriptions are all technical — no plain-English alternative offered.

---

## D. Top 5 Beginner-UX wins (ranked impact / effort)

Each is a one-day-or-less win that materially improves first-time UX:

### D.1 — Add a global glossary tooltip primitive (`<TieredInfoTooltip>`) and wire to indicator tiles
**Impact:** HUGE (closes Beginner grievance #4 — the densest jargon block in the app). **Effort:** 1 day primitive + 0.5 day wiring on Signals + On-chain + Backtester pages. **Total:** ~12 hours.

Implementation: a small `<TieredInfoTooltip term="RSI" />` primitive that auto-renders a Beginner ⓘ tooltip ("RSI = how 'hot' the price has been recently. Above 70 = probably overbought, below 30 = probably oversold."), an Intermediate condensed tooltip ("Relative Strength Index — momentum oscillator, 14-period default"), and Advanced reference link. Backed by a single `web/lib/glossary.ts` map of ~30 terms (per CLAUDE.md §7 "Shared glossary of ~30 terms with 3 explanation depths").

### D.2 — Hide MacroStrip + BacktestCard on Home at Beginner; replace with a "Today's market mood" card
**Impact:** LARGE (closes Beginner grievance #1 + #2 on the landing page). **Effort:** 0.5 day. **Total:** ~4 hours.

This is the single most-visited page in the app. Beginner shouldn't see "BTC Dominance · ppts · DXY · 8h funding" within 3 seconds of opening the app.

### D.3 — Add a one-time Welcome modal at Beginner first-visit (per §7 master agreement)
**Impact:** LARGE (currently violates §7 "Welcome banner on first visit (dismissible, appears once)"). **Effort:** 0.5 day. **Total:** ~4 hours.

Implementation: a `<BeginnerWelcomeModal>` that fires once per browser, dismissible. Persist `seen-welcome` flag to localStorage. Copy: "Welcome to Crypto Signal App. We'll help you spot good buying / selling moments in the crypto market using a model that combines price, on-chain, and macro signals. Pick a coin, look for ▲ Buy or ▼ Sell signals, and use Alerts to get notified when things change. You can change to Intermediate / Advanced level any time using the toggle in the top right."

### D.4 — Replace Optuna Table with "Top 5 strategies" plain-English card at Beginner on Backtester
**Impact:** MEDIUM (closes Beginner grievance #7). **Effort:** 0.5 day. **Total:** ~4 hours.

Implementation: at Beginner, replace OptunaTable with a `<TopStrategiesCard>` that shows the 5 best Optuna runs but maps each row to plain English: "Strategy 1: balanced momentum on a 2-week lookback — best historical Sharpe 4.12, +342.8% over 3 years."

### D.5 — Wire `<UserLevelProvider>` consumption on Home + Settings (the 2 most-visited pages)
**Impact:** MEDIUM (closes the 14-page tier-coverage gap on the highest-traffic routes). **Effort:** 0.5 day per page = 1 day. **Total:** ~8 hours.

Use the proposals in §B.2.1 (Home) and §B.2.8 + B.2.9 + B.2.10 (Settings) as the implementation guides. This unblocks the rest of the §B.2 backlog by establishing the per-page branching pattern.

**Total D.1+D.2+D.3+D.4+D.5 = ~32 hours = 4 dev-days.** Closes ~70% of the Beginner UX gap with one focused sprint.

---

## E. Edge-case failure UX summary

For each page: what does it do when (a) no scan yet (empty state), (b) API returns 503/429, (c) auth key wrong (401), (d) localStorage unavailable (Capacitor private mode).

### Conventions
- "Empty" = empty state when API returns successfully with empty data.
- "503/429" = backend error or rate-limit.
- "401" = auth failure.
- "localStorage" = SSR-safe + Capacitor edge case.

| Page | Empty state | 503 / 429 | 401 (auth) | localStorage NA |
|---|---|---|---|---|
| **`app/page.tsx`** (Home) | ✓ "Run a scan to populate the watchlist (no scan results yet)." (line 202) — **GOOD** | ✗ "Couldn't load signals — try refreshing in 30 seconds." — **OK** but doesn't differentiate 503 vs 429; no retry timer | ✗ Same generic message — should say "API key missing or invalid. Set NEXT_PUBLIC_API_KEY." | ✓ No localStorage on this page directly |
| **`app/signals/page.tsx`** | ✓ Coin picker shows "Run a scan to populate" (line 402) — **GOOD**. SignalHero shows "—" placeholders — **GOOD** | ✓ Scan trigger has explicit ApiError discrimination (line 425-432) — **GOOD: rate limit / auth / geo-block all handled separately**. Detail/history queries fall back to em-dashes silently — OK | ✓ ApiError.isAuthError surfaces "API key missing or invalid" copy on scan trigger — **GOOD** | ✓ N/A directly (level read via context) |
| **`app/regimes/page.tsx`** | ✓ "Run a scan to populate regime states" (line 166) — **GOOD** | ✗ Generic "Couldn't load regime states — try refreshing in 30 seconds." — no 429 differentiation | ✗ Same generic message | ✓ N/A |
| **`app/on-chain/page.tsx`** | ✗ Each indicator tile shows "—" with subtext "loading" or "unavailable" (line 47-49) — **MARGINAL** ("loading" is wrong subtext for a successful empty response). The data-source pill correctly degrades to "cached" when source = "unavailable" — GOOD | ✗ No explicit error display on the page — failed dashboard query results in tiles staying as "—". User can't tell if backend is down or just rate-limited. **NEEDS** an error banner per query | ✗ Same — silent failure | ✓ N/A |
| **`app/alerts/page.tsx`** | N/A (configure form, no live data) | N/A | N/A | N/A |
| **`app/alerts/history/page.tsx`** | ✗ Likely renders empty table when /alerts/log returns []. Need to verify — should show "No alerts in this window — alerts fire when configured events trigger" | ✗ Generic error path likely | ✗ Generic | ✓ N/A |
| **`app/backtester/page.tsx`** | ✓ "No trades on this strategy yet — run a backtest to populate." (line 200) — **GOOD** | ✗ "Couldn't load trades — try refreshing in 30 seconds." — generic | ✗ Generic | ✓ N/A |
| **`app/backtester/arbitrage/page.tsx`** | ✓ "No spreads above the 0.10% threshold right now — try widening the universe." (line 141) — **GOOD** (truthful empty state) | ✓ "Couldn't load arbitrage opportunities — endpoint may not be implemented yet." (line 140) — **GOOD** (acknowledges the endpoint may be missing) | ✗ Generic — no auth-error discrimination | ✓ N/A |
| **`app/ai-assistant/page.tsx`** | ✗ DecisionsTable likely renders 0 rows silently (no empty-state copy verified). AskClaude form is independent — N/A | ✗ Likely silent fall-through | ✗ Same | ✓ N/A |
| **`app/settings/trading/page.tsx`** | ✓ Uses `hydratedRef` to prevent refetch-clobber — **GOOD**. If query never resolves, falls back to `DEFAULT_PAIRS` (line 7) — OK | ✗ Save mutation surfaces `rejected[]` from response (per file comment) but no visible "save failed" banner shown for 503/429 | ✗ Generic | ✓ N/A |
| **`app/settings/signal-risk/page.tsx`** | Same hydrate-once pattern. Save likely silent on failure | ✗ Same | ✗ Same | ✓ N/A |
| **`app/settings/dev-tools/page.tsx`** | Renders even when health endpoint fails (per the file's intent: shows "API down" status pill) — **GOOD** | ✓ Status pills degrade gracefully | ✓ Likely a dedicated re-auth flow somewhere — verify | ✓ N/A |
| **`app/settings/execution/page.tsx`** | Disabled state when API keys not configured | ✗ Save likely silent | ✗ Generic | ✓ N/A |
| **Topbar / level radiogroup** | N/A | N/A | N/A | ✓ **GOOD** — `user-level-provider.tsx:39-41` wraps localStorage in try/catch; falls back to DEFAULT_LEVEL ("Beginner"). Also `setLevel` try/catch on line 70-72 — silent ignore on private-mode write failure |
| **Topbar / theme toggle** | N/A | N/A | N/A | ✓ Handled by next-themes lib |
| **`app/error.tsx`** (route boundary) | N/A | N/A | N/A | N/A |
| **`app/not-found.tsx`** | N/A | N/A | N/A | N/A |
| **`app/global-error.tsx`** | N/A | N/A | N/A | ✓ Inline-styles + dependency-free fallback works without localStorage |

### Edge-case findings

**E.1 (HIGH):** Most pages don't distinguish 503 vs 429 vs 401 in the displayed error copy. Only `app/signals/page.tsx` (scan trigger) and `app/backtester/arbitrage/page.tsx` (endpoint not implemented) differentiate. Recommend lifting the ApiError-discrimination pattern from `signals/page.tsx:425-432` into a shared `<ApiErrorBanner error={query.error}>` primitive and wiring it across all 16 pages. Effort: 1 day.

**E.2 (MEDIUM):** `app/on-chain/page.tsx` silently shows "—" tiles when a Glassnode dashboard query fails. User has no signal that the data is stale vs missing vs the backend being down. Recommend: add a `query.isError` banner per pair card with the standard 503 / 429 / 401 differentiation.

**E.3 (LOW):** `app/alerts/history/page.tsx` empty-state copy isn't explicit (Wave-2 didn't deeply verify). Recommend "No alerts in this window — alerts fire only when configured events trigger" + a link back to the Configure tab.

**E.4 (CLOSED):** localStorage unavailable on `<UserLevelProvider>` is correctly handled (try/catch in 3 places) — Capacitor private mode users default to Beginner with no crash. **Verified GOOD.**

**E.5 (LOW — mock-data leakage):** Several pages display mock data when API returns successfully empty (e.g. `funding-carry-table` on arbitrage page always shows BTC/ETH/SOL/XRP/AVAX hardcoded rows even when arbQuery returns []). At Beginner this could mislead the user into thinking the data is live. Recommend a `data-source-badge` "MOCK · pending wiring" pill on every still-mocked surface (cross-references `2026-05-02_data_feeds_audit.md`).

---

## F. Recommended Wave-2 P0/P1 fix order

Ordered by impact-to-effort:

1. **(P0) Convert `alert-type-card.tsx` from `<div onClick>` to `<button>` with `aria-pressed`.** Mirror the regime-card.tsx 05-04 fix. **Effort: 15 minutes.**

2. **(P0) Add skip-to-content link in `app-shell.tsx` + `id="main"` on `<main>`.** **Effort: 10 minutes.**

3. **(P0) Wire `useUserLevel` on `app/page.tsx` (Home).** Implement §B.2.1 proposals — hide MacroStrip + BacktestCard at Beginner, add "Today's market mood" card. **Effort: 4 hours.**

4. **(P1) Add `<TieredInfoTooltip>` primitive + `web/lib/glossary.ts` (30 terms, 3 depths).** Wire on Signals indicator grids first (highest jargon density). **Effort: 1 day.**

5. **(P1) Add Beginner welcome-modal at first visit.** Per CLAUDE.md §7 "Welcome banner on first visit (dismissible, appears once)". **Effort: 4 hours.**

6. **(P1) Replace 🟢🔴⚪ in `decisions-table.tsx` with ▲▼■ (or ✓✗—).** **Effort: 5 minutes.**

7. **(P1) Lift toggle-switch tap targets above 44px** by wrapping the visual 24px switch in a 44px parent label-with-tap-area. Cross-cutting fix to `toggle-switch.tsx` + 4 inline copies. **Effort: 1-2 hours.**

8. **(P1) Light-mode `text-success` / `text-danger` legibility pass.** Define `--success-text-light: #16a34a`, `--danger-text-light: #dc2626`, `--warning-text-light: #d97706` overrides in `.light { ... }` block of globals.css. **Effort: 2 hours.**

9. **(P1) Replace hardcoded `rgba(34,211,111,0.2)` in `app/alerts/page.tsx:192` with `var(--accent-soft)`.** **Effort: 1 minute.**

10. **(P1) Replace `#22c55e` / `#ef4444` SVG sparkline strokes in `watchlist.tsx:66` with `var(--success)` / `var(--danger)` via inline style.** **Effort: 1 minute.**

11. **(P1) Update legacy `#00d4aa` fallbacks in `signal-risk/page.tsx:64` + `execution/page.tsx:54` to `#22d36f` (or omit).** **Effort: 2 minutes.**

12. **(P1) Add `aria-label` to autoExecute toggle in `app/settings/execution/page.tsx:177-191`.** **Effort: 1 minute.**

13. **(P2) Add `htmlFor` association on the 3 form inputs in `app/alerts/page.tsx:137-175`.** **Effort: 30 minutes.**

14. **(P2) Wire `useUserLevel` on the remaining 13 pages** per §B.2.2 through §B.2.12. **Effort: ~5 days, but can ship incrementally.**

15. **(P2) Add `<ApiErrorBanner error={query.error}>` shared primitive and wire across all 16 pages** for 503 / 429 / 401 differentiation. **Effort: 1 day.**

16. **(P2) Lift alerts/history pagination buttons from `h-7` (28px) to `h-11` (44px).** **Effort: 30 minutes.**

17. **(P2) Add `<DataSourceMockBadge>` to all still-mocked surfaces** so Beginner doesn't mistake hardcoded `funding-carry-table` rows for live data. **Effort: 1 day.**

**P0 + P1 total: ~3 dev-days.** Closes the largest tier-1 gaps. P2 is the longer-tail backlog.

---

## G. Out-of-scope items observed during Wave 2

- `app/page.tsx` lines 39-99 still hold mock data for MacroStrip + Watchlist (TODO(D-ext) endpoints). Beginner-mode hide doesn't fix this; the Intermediate user is also looking at hardcoded numbers. Cross-reference `2026-05-02_data_feeds_audit.md`.
- `app/ai-assistant/page.tsx:93-98` `metrics[]` still hardcoded.
- `app/backtester/arbitrage/page.tsx:43-48` `carries[]` still hardcoded.
- `app/regimes/page.tsx:36-43` `timelineSegments` still hardcoded.
- `components/decisions-table.tsx:39-60` 3 filter dropdowns still not wired.
- `components/equity-curve.tsx` is a visual mock with no `/equity-curve` endpoint.

These are real bugs but tier-orthogonal — flagged to keep the Wave-3 tracker honest.

---

## Closing

Wave 1 → Wave 2 progress: **plumbing solid, page wiring thin, Beginner UX still jargon-heavy**.

The single highest-leverage next move is the §D.1 + §D.2 + §D.3 combo (glossary tooltip primitive + Home Beginner gate + Welcome modal). One focused sprint closes ~70% of the Beginner UX gap and unblocks the §B.2 backlog by establishing the per-page branching pattern.

The Wave-1 line-level fixes (decisions-table emoji, alert-type-card div→button, toggle-switch tap targets, hardcoded hex literals) are all 15-minute-or-less drops — they remain open simply because the Phase 0.9 P0-5 sprint focused on the larger UserLevelProvider plumbing rather than the line-level cleanup. Picking them up in any subsequent batch is trivial.
