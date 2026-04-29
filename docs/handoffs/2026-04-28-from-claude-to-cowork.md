# Handoff: Crypto Signal App — Claude → Cowork

**Date:** 2026-04-28
**From:** Claude (engineering / code-correctness)
**To:** Cowork (design / UX / mockup authority)
**Live deploy:** https://cryptosignal-ddb1.streamlit.app/
**Repo:** github.com/davidduraesdd1-blip/crypto-signal-app
**Main branch HEAD at handoff:** post-merge of redesign sprint (PR #11) + ~14 follow-up commits

---

## 0. TL;DR — What this doc is + what we need from you

Engineering side is at a **clean checkpoint**. The redesign port shipped, every `CLAUDE.md` mandate is closed, all tests green, deploy verifier 5/5, no merge blockers. That part is done.

But the live deploy reveals **a clear class of failure**: the redesign port shipped the **new visual chrome** (cards, tokens, fonts, sidebar, top bar, plotly template) but **lost the data-to-component wiring** on most deeper pages — Regimes/BTC detail, On-chain detail, Backtester, parts of Config Editor. The Market Home page works end-to-end; everything past it shows empty cells, broken buttons, or missing layouts that previously worked.

We're stopping engineering work on UX before we make more guesses. **We need cowork to:**

1. **Walk the live app** at the URL above (3 user levels × dark/light × mobile if possible). The "Walkthrough script" in §3 below lists every screen we know about so nothing is missed.
2. **Diff each page against the mockup** in `shared-docs/design-mockups/sibling-family-crypto-signal-*.html`. Use the tables in §4 to mark drift.
3. **Decide the open design questions** in §5 (border-radius, NEUTRAL contrast, token-unlock placement, plotly theme override policy, etc.).
4. **Prioritize the issue list** in §6 — which are MVP-blocking, which can ship in v2, which are nice-to-have.
5. **Reply with a written verdict + priority order**, and we resume engineering against it.

After your review we re-open Claude execution against your priorities. No code changes happen between now and then.

---

## 1. Where the app is right now

### 1.1 Live URLs

| Environment | URL | Status |
|---|---|---|
| Production | https://cryptosignal-ddb1.streamlit.app/ | Live; deploy verifier 5/5 |

### 1.2 How to test the 3 user levels + theme

- **User level**: top bar — three pills "Beginner / Intermediate / Advanced" (Advanced is the default in the screenshots cowork has).
- **Theme**: top bar — "☾ Theme" button toggles dark ↔ light.
- **Mobile**: open the URL on a phone OR use browser dev tools at width ≤768px.

> ⚠ **Known issue (CRITICAL):** in current state, switching the user-level pill produces no visible content change. This needs to be design-resolved (see §5).

### 1.3 Branch / commit summary

| Stream | Status |
|---|---|
| Original redesign port (mockup → code) | Merged in PR #11 |
| Audit-driven P0 + P1 fixes (30 commits) | Merged in PR #11 |
| Post-merge follow-ups (§22 fixtures, VC funding wiring, Dune scaffold, MEDIUM picks, token-unlock UI) | Direct on main |
| Dependabot (5 pip + 3 actions) | Merged |
| Total commits ahead of pre-sprint main | 80+ |
| Tests | 88/88 pass, 5.75s |
| Deploy verifier (5-check smoke) | 5/5 |
| Hardcoded secrets in `*.py` | 0 |
| Sub-11px font violations | 0 |
| §22 indicator fixtures | 22/22 |
| §4 backtest regression baseline | locked at `docs/signal-regression/2026-04-28-baseline.json` |

### 1.4 Restore points (origin tags)

If anything goes wrong during cowork's review or subsequent work:

```
backup-pre-baseline-audit-2026-04-28-main
backup-pre-baseline-audit-2026-04-28-ui2026-05-parent
backup-pre-baseline-audit-2026-04-28-ui2026-05-p0fixes
backup-pre-baseline-audit-2026-04-28-ui2026-05-pagescss
backup-pre-baseline-audit-2026-04-28-ui2026-05-plotly
backup-pre-baseline-audit-2026-04-28-ui2026-05-sidebarpolish
```

`git checkout <tag>` restores the named state.

---

## 2. Reference docs already on main

Cowork should also skim these for context:

| File | What it is |
|---|---|
| `docs/audits/2026-04-28-redesign-baseline.md` | Pre-sprint audit (~44 CRITICAL, ~124 HIGH, ~290 total findings) |
| `docs/audits/2026-04-28-post-sprint-final.md` | Post-sprint delta + verification of every audit claim |
| `docs/signal-regression/2026-04-28-baseline.json` | 5-scenario locked composite-signal output |
| `tests/test_indicator_fixtures.py` | 22/22 indicator fixtures (RSI / MACD / Bollinger / ATR / ADX / SuperTrend / Stochastic / Ichimoku / Hurst / Squeeze / Chandelier / CVD / Gaussian / S/R / divergences / candlestick / Wyckoff / cointegration / HMM / VWAP / Fibonacci) |
| `tests/test_composite_signal_regression.py` | 5-scenario regression lock |
| `pending_work.md` | Active follow-up list with priority |
| `MEMORY.md` | Session continuity log (newest entry on top) |
| `shared-docs/design-mockups/sibling-family-crypto-signal*.html` | Cowork's original mockups (4 pages) |

---

## 3. Walkthrough script — every page we know about

This is the master list cowork should walk. For each page, do all 3 user levels + both themes; on mobile do dark mode at minimum.

| # | Page | Sidebar entry | Mockup file | Currently appears... |
|---|---|---|---|---|
| 1 | **Market Home** | `Markets / Home` | `sibling-family-crypto-signal.html` | ✅ Mostly working — hero cards, macro strip, watchlist all populate from live data |
| 2 | **Signals** | `Markets / Signals` | `sibling-family-crypto-signal-SIGNALS.html` | ⚠ Per-coin info strip works (Vol / ATR / Beta / Funding / Next Unlock) but full per-pair detail TBD by walkthrough |
| 3 | **Regimes / Coin detail** | `Markets / Regimes` | `sibling-family-crypto-signal-REGIMES.html` | ❌ Broken — ALL composite layers (1/2/3/4), technical indicators, on-chain values, sentiment shown as "—". Price chart says "Price history unavailable — try refreshing." |
| 4 | **Backtester** | `Research / Backtester` | `sibling-family-crypto-signal-BACKTESTER.html` | ❌ Broken — "▶ Run Backtest" and "Re-run backtest →" buttons do nothing. Total Return / CAGR / Sharpe / Max DD / Win Rate all "—". Equity curve unavailable. |
| 5 | **On-chain** | `Research / On-chain` | (no dedicated mockup — thin design-system pass per inline note) | ❌ Broken — BTC/ETH/XRP all show "—" for MVRV-Z, SOPR, Exch Reserve, Active Addr. The page was never given a real mockup; it's currently a shell. |
| 6 | **Alerts** | `Account / Alerts` | (no dedicated mockup) | ❓ Untested in screenshots — needs walkthrough |
| 7 | **Settings / Config Editor** | `Account / Settings` | (no dedicated mockup; previously had Trading / Signal & Risk / Alerts / Dev Tools / Execution tabs that worked) | ⚠ Cowork's screenshots show the OLD pre-redesign Config Editor was fully populated and functional (pair pills, sliders, API-key fields, save buttons). Current redesign state of these tabs needs walkthrough. |
| 8 | **AI Agent** | `Account / AI Agent` | (no dedicated mockup) | ✅ Working — STOPPED state, Start/Stop buttons, agent-config sliders + values present |
| 9 | **Arbitrage** | `Account / Arbitrage` | (no dedicated mockup) | ❓ Untested in screenshots — appears to have an "Arbitrage Scanner" panel; needs walkthrough |
| 10 | **Glossary** | `📖 Glossary — 30 terms` (sidebar popover) | (n/a) | ✅ Working in code per audit; popover renders the 30-term × 3-depth list |
| 11 | **Legal (Internal Beta)** | sidebar bottom expander | (n/a) | ❓ Untested |
| 12 | **Top bar — user-level pills** | always visible | (mockup shows them as a 3-pill row at top right) | ❌ Broken — pills appear distinct but switching produces no visible content change |
| 13 | **Top bar — Refresh** | always visible | (mockup) | ⚠ Refresh button click registers but shows no progress or feedback (the sidebar SCANNING bar fires for "Run a fresh scan now" but NOT for the top-bar Refresh) |
| 14 | **Top bar — Theme toggle** | always visible | (mockup) | ✅ Working — flips dark ↔ light |
| 15 | **Top bar — Share / Pencil / GitHub** | always visible | (mockup placement) | ❓ Visible but cropped behind theme toggle in some viewports — overflow handling |
| 16 | **Sidebar — nav highlight** | always visible | (mockup) | ❌ Bug — sidebar nav buttons require **two clicks** to be clearly highlighted as active. First click navigates but underlight doesn't refresh until a second click. |
| 17 | **"Run a fresh scan now"** | bottom of Market Home | (mockup) | ✅ Working — fires the scan, sidebar shows progress 0%→100% |

---

## 4. Per-page mockup-vs-implementation diff (cowork to fill in)

Below is a table to mark up during walkthrough. Three states: ✅ matches mockup, ⚠ drifts (note what), ❌ missing/broken.

### 4.1 Market Home

Mockup file: `shared-docs/design-mockups/sibling-family-crypto-signal.html`

| Element | Match? | Notes |
|---|---|---|
| Hero brand block (Signal.app logo) | | |
| 3 hero price cards (BTC / ETH / XRP) | | |
| 5-cell macro strip (BTC dom / F&G / DXY / Funding / Regime) | | |
| Data source pills (KRAKEN · live, Glassnode · live, News sentiment · cached) | | |
| Watchlist · TOP-CAP | | |
| Composite Backtest preview card | | |
| "Run a fresh scan now" CTA | | |

### 4.2 Signals

Mockup file: `shared-docs/design-mockups/sibling-family-crypto-signal-SIGNALS.html`

| Element | Match? | Notes |
|---|---|---|
| Coin picker chips | | |
| Hero detail card (ticker + price + 24h/30d/1y) | | |
| BUY/HOLD/SELL signal hero badge + regime line | | |
| Composite score breakdown | | |
| Per-indicator card grid | | |
| Signal history table | | |
| 5-cell info strip (Vol / ATR / Beta / Funding / Next Unlock) | | |

### 4.3 Regimes / Coin detail

Mockup file: `shared-docs/design-mockups/sibling-family-crypto-signal-REGIMES.html`

| Element | Match? | Notes |
|---|---|---|
| Coin price hero block | | |
| Hold/Buy/Sell decision badge + Regime: Ranging/Trending pill | | |
| 4-cell strip (Vol / ATR / Beta / Funding) | | |
| Composite Score 0–100 panel with collapsible Layer 1-4 | | |
| Technical Indicators card (RSI/MACD/SuperTrend/ADX) | | |
| On-Chain card (MVRV-Z/SOPR/Exch Reserve/Active Addr) | | |
| Sentiment card (F&G/Funding/Google Trends/News Sent) | | |
| Recent signal history (last 8 transitions) | | |
| **Note:** in current state EVERY value here is "—". The cards render but data is not flowing. | | |

### 4.4 Backtester

Mockup file: `shared-docs/design-mockups/sibling-family-crypto-signal-BACKTESTER.html`

| Element | Match? | Notes |
|---|---|---|
| Universe / Period / Initial / Rebalance / Costs row | | |
| ▶ Run Backtest CTA + Re-run backtest button | | |
| 5-cell KPI strip (Total Return / CAGR / Sharpe / Max DD / Win Rate) | | |
| Equity curve · signal vs BTC | | |
| Optuna studies · top 5 hyperparam sets | | |
| Recent trades · signal-driven | | |
| Summary / Trade History / Advanced Backtests tabs | | |
| **Note:** Run Backtest does nothing. Both buttons are dead. | | |

### 4.5 On-chain

No dedicated mockup. Page is currently a thin design-system pass.

| Element | Match expected? | Notes |
|---|---|---|
| BTC · Valuation & Flows card | | needs mockup |
| ETH · Valuation & Flows card | | needs mockup |
| XRP · Valuation & Flows card | | needs mockup |
| Glassnode + Dune source pills | | |
| Disclaimer about Glassnode free-tier 1h cache | | |

**Question for cowork:** does this page get a real mockup, or do we redirect to per-coin Regimes detail and remove this nav entry?

### 4.6 Settings / Config Editor

No dedicated mockup. Cowork's older screenshots show the previous version had 5 functional tabs:

| Tab | Old state (screenshots) | Current state |
|---|---|---|
| Trading | Pair pills (~25), Add custom pair, Timeframes (1h/4h/1d/1w), TA Exchange dropdown | needs walkthrough |
| Signal & Risk | Portfolio Size, Risk per Trade, Max Total Exposure, Max Position Cap, Max Open per Pair, High-Confidence Threshold slider, MTF Alignment slider, Indicator Weights sliders (Core/Momentum/Stochastic/ADX/VWAP/Fibonacci/MACD-Div/SuperTrend/S/R-Breakout) | needs walkthrough |
| Alerts | Email Alerts collapsible, Notifications & Scheduler, API Keys (LunarCrush, Coinglass, CryptoQuant, Glassnode, CryptoPanic) with masked-password fields, Save API Keys button | needs walkthrough |
| Dev Tools | (cowork to confirm what was here) | needs walkthrough |
| Execution | (cowork to confirm what was here) | needs walkthrough |

**Major question for cowork:** does the Config Editor get a redesign mockup, or should we restore the old chrome (which worked) and skin it with design tokens only?

### 4.7 AI Agent (Settings tab visible in screenshot)

| Element | Match? | Notes |
|---|---|---|
| ▼ STOPPED state pill | | |
| ▶ Start / ■ Stop buttons | | |
| Total Cycles / Last Cycle / Last Pair / Last Decision strip | | |
| Crash Restarts / Engine row | | |
| Agent Configuration card with Dry Run toggle, Cycle Interval, Min Confidence, Max Trade Size sliders | | |
| Right column: Max Concurrent Positions, Daily Loss Limit, Portfolio Size, Max Drawdown, Cooldown After Loss | | |

This page appears to be working — confirm in walkthrough.

### 4.8 Arbitrage

No dedicated mockup. Sidebar entry exists; page has an "Arbitrage Scanner" panel per the screenshot. Walkthrough needed.

---

## 5. Open design decisions cowork must rule on

Each of these blocks downstream engineering. Pick one option per row.

| # | Question | Options |
|---|---|---|
| D1 | Card `border-radius`: §8 says **10px**, design tokens (`tokens.card_radius`) say **12px** | (a) 10px / (b) 12px / (c) 14px |
| D2 | NEUTRAL pill contrast: currently 4.67:1 (AA passes) | (a) keep / (b) lift to ≥7:1 (AAA) |
| D3 | Token-unlock placement: currently 5th cell of Signals info-strip | (a) keep as 5th cell / (b) dedicated card / (c) sidebar widget / (d) hide for now |
| D4 | Plotly chart theme overrides: design-system template registered, but per-chart `update_layout(...)` calls override it | (a) sweep all overrides / (b) accept hybrid / (c) document allowed override list |
| D5 | User-level pills currently produce no visible content change | (a) wire up — what changes per level? / (b) collapse to one level / (c) hide pills until v2 |
| D6 | Refresh button (top bar) gives no feedback | (a) progress bar in sidebar / (b) toast / (c) disabled-while-running pill |
| D7 | Sidebar nav double-click bug | (a) fix to single-click / (b) leave (deliberate confirm UX) |
| D8 | On-chain page: keep or remove? | (a) keep + needs mockup / (b) merge into per-coin Regimes / (c) hide for now |
| D9 | Config Editor: redesign or restore? | (a) full mockup needed / (b) restore old chrome + token skin / (c) hybrid (mockup later, restore now) |
| D10 | Top-bar overflow on narrow viewports (Beginner/Intermediate/Advanced labels wrap) | (a) abbreviate / (b) icon-only / (c) collapse to dropdown |
| D11 | Light-mode component-by-component review (most pages) | sign-off list per page |
| D12 | Mobile (≤768px) per-page approval | sign-off list per page |

---

## 6. Categorized issue list (severity-ordered, awaiting cowork priority)

### CRITICAL — page is broken / data missing

| # | Where | Issue | Engineering note |
|---|---|---|---|
| C1 | **All pages** | User-level Beginner/Intermediate/Advanced toggle has no visible effect on rendered content | Design + code work both required (D5) |
| C2 | **Backtester** | "▶ Run Backtest" and "Re-run backtest →" buttons do nothing | Code wiring lost during port; data path TBD |
| C3 | **Regimes / coin detail** | All composite layers + technical + on-chain + sentiment values empty ("—"); price history unavailable | Data-to-component wiring lost; underlying data fetchers all healthy (proven by §22 fixtures + §4 baseline) |
| C4 | **On-chain page** | BTC/ETH/XRP all empty | Same wiring failure as C3 + mockup ambiguity (D8) |
| C5 | **Config Editor** | Redesign-state of Trading / Signal & Risk / Alerts tabs unclear vs cowork's older fully-functional screenshots | (D9) |

### HIGH — visible defect or UX failure

| # | Where | Issue | Engineering note |
|---|---|---|---|
| H1 | **Top bar** | Beginner/Intermediate/Advanced/Refresh/Theme labels wrap inside their pills on narrow viewports | (D10) |
| H2 | **Top bar** | Refresh button — no visible feedback after click | (D6) |
| H3 | **Sidebar** | Nav buttons require double-click to be clearly highlighted as active | (D7) |
| H4 | **Regimes / BTC detail** | Price · last 90d shows "Price history unavailable — try refreshing" | C3 wiring |
| H5 | **Sentiment cards** | Google Trends + News Sent show "—" on detail pages | C3 wiring |

### MEDIUM — present but worth deciding before next iteration

(D1, D2, D3, D4, D11, D12 above.)

### LOW — opportunistic, no blocker

The ~270 remaining MEDIUM/LOW items from the audit baseline (file paths + line numbers in `docs/audits/2026-04-28-redesign-baseline.md` §2) — Claude can grind through these as time permits, but each is small. Cowork doesn't need to triage these unless one specifically affects design.

---

## 7. What we already know we have to do regardless

Even before cowork's review there are tasks engineering will do as soon as you greenlight:

1. **Re-wire Regimes / On-chain / Backtester** to the existing data fetchers (the data is there; the connection got severed during the port).
2. **Wire up the user-level pills** to actually swap content depth (per §7 of CLAUDE.md: Beginner = plain English + tooltips visible; Intermediate = condensed + key metrics; Advanced = raw numbers + all indicators).
3. **Add Refresh-button feedback** (sidebar progress bar tied to the same scan-state machine that "Run a fresh scan now" already drives).
4. **Fix sidebar double-click highlight bug.**

These are clear engineering tasks. They're held until cowork's review so we can sequence them with whatever else is decided.

---

## 8. Mandates already closed (engineering side, no rework)

- §1 Permission/autonomy ✓
- §3 Commit & push hygiene ✓
- §4 Backtest regression baseline ✓ (`docs/signal-regression/2026-04-28-baseline.json`)
- §8 Design tokens / shape badges / font floor / tap targets ✓
- §10 Data sources (cryptorank, Dune, pytrends) ✓
- §11 24/7 agent operation (`ensure_supervisor_running()` helper) ✓
- §12 Cache TTLs match spec ✓
- §22 Indicator fixtures 22/22 ✓
- §25 Deploy verifier 5/5 ✓

Light-mode + mobile per-page acceptance is the standing item that **needs cowork sign-off** — those are the only mandate items still open.

---

## 9. What cowork's reply should include

To minimise round-trips, please reply with all of the following in one go:

1. **Per-page walkthrough verdicts** (§4 tables filled in or equivalent comments)
2. **D1-D12 design decisions** — pick one option per row
3. **Critical/High issue priority order** (which to fix first, second, third)
4. **Anything missing from this list** — pages we don't know about, mockup updates we don't have
5. **Ship vs hold verdict** — is the current state shippable as v1 once C1-C5 are fixed, or does it need more before public eyes see it?

After your reply, Claude resumes execution against your priorities.

---

## 10. Out of scope

These are NOT blocked on cowork's review and Claude will continue to address as code is touched:

- The ~270 MEDIUM/LOW backlog items in the baseline audit
- Live runtime verification of agents/rate-limits/Web3 (needs deploy + monitoring)
- Backfilling additional regression scenarios beyond the 5-baseline (more `docs/signal-regression/` entries)
- Strategy_bias duplicate-derivation cleanup (P3 hygiene)
- §22 indicator fixture maintenance as math evolves

---

## 11. Quick links

- Live deploy: https://cryptosignal-ddb1.streamlit.app/
- Repo: https://github.com/davidduraesdd1-blip/crypto-signal-app
- Baseline audit: `docs/audits/2026-04-28-redesign-baseline.md`
- Post-sprint audit: `docs/audits/2026-04-28-post-sprint-final.md`
- Signal regression baseline: `docs/signal-regression/2026-04-28-baseline.json`
- Mockups: `shared-docs/design-mockups/sibling-family-crypto-signal-*.html`
- This doc: `docs/handoffs/2026-04-28-from-claude-to-cowork.md`

---

*Handoff prepared 2026-04-28 by Claude (Opus 4.7). Engineering paused pending cowork review.*
