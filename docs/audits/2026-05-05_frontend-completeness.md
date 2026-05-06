# Tier 1 — Frontend Completeness Sweep
**Date:** 2026-05-05
**Scope:** `web/app/` — 14 page.tsx routes + supporting components (note: prompt mentioned 16, only 14 page.tsx files exist; the discrepancy comes from `error.tsx` / `not-found.tsx` / `global-error.tsx` / `layout.tsx` which are framework chrome, not user routes)
**Methodology:** Read every `app/**/page.tsx`, traced every imported component used to render user-visible content, grep-swept for `"—"`, `TODO(D-ext)`, `loading`, `live in /...`, demo-month strings (Feb/Mar/Apr 2026), and round-number percentages. Categorized each finding A–E and ranked P0–P2 by visibility. Read-only — no code modified.

## Routes audited (14)

| # | Route | File |
|---|---|---|
| 1 | `/` (Home) | [web/app/page.tsx](web/app/page.tsx) |
| 2 | `/signals` | [web/app/signals/page.tsx](web/app/signals/page.tsx) |
| 3 | `/regimes` | [web/app/regimes/page.tsx](web/app/regimes/page.tsx) |
| 4 | `/on-chain` | [web/app/on-chain/page.tsx](web/app/on-chain/page.tsx) |
| 5 | `/ai-assistant` | [web/app/ai-assistant/page.tsx](web/app/ai-assistant/page.tsx) |
| 6 | `/backtester` | [web/app/backtester/page.tsx](web/app/backtester/page.tsx) |
| 7 | `/backtester/arbitrage` | [web/app/backtester/arbitrage/page.tsx](web/app/backtester/arbitrage/page.tsx) |
| 8 | `/alerts` | [web/app/alerts/page.tsx](web/app/alerts/page.tsx) |
| 9 | `/alerts/history` | [web/app/alerts/history/page.tsx](web/app/alerts/history/page.tsx) |
| 10 | `/settings` (redirect) | [web/app/settings/page.tsx](web/app/settings/page.tsx) |
| 11 | `/settings/trading` | [web/app/settings/trading/page.tsx](web/app/settings/trading/page.tsx) |
| 12 | `/settings/signal-risk` | [web/app/settings/signal-risk/page.tsx](web/app/settings/signal-risk/page.tsx) |
| 13 | `/settings/execution` | [web/app/settings/execution/page.tsx](web/app/settings/execution/page.tsx) |
| 14 | `/settings/dev-tools` | [web/app/settings/dev-tools/page.tsx](web/app/settings/dev-tools/page.tsx) |

## Summary table

| Page | Total findings | P0 | P1 | P2 | Hotspot |
|---|---:|---:|---:|---:|---|
| `/` (Home) | 7 | 3 | 4 | 0 | MacroStrip + Watchlist + DataSourceRow all v0 mock; demo prices for BTC/ETH/SOL/AVAX/LINK/NEAR |
| `/signals` | 9 | 6 | 3 | 0 | Hero card price/30d/1y `"—"`; multi-tf strip + composite score + sentiment + price tiles all mock; signal history is Feb-Apr 2026 demo data |
| `/regimes` | 6 | 2 | 4 | 0 | RegimeCard `since="—" durationDays=0`; timeline + macro overlay + regime weights mocked |
| `/on-chain` | 3 | 1 | 2 | 0 | WhaleActivity table 100% mock with "live stream" label |
| `/ai-assistant` | 6 | 2 | 4 | 0 | AgentMetricStrip 4× `"—"`, EmergencyStopCard inert, AgentConfigCard sliders inert, hardcoded `cycle={47}` + "uptime 17d 6h" + "AVAX/USDT cycle 14s" status banner |
| `/backtester` | 3 | 0 | 3 | 0 | Equity curve is hardcoded SVG; Optuna table 5 demo runs |
| `/backtester/arbitrage` | 5 | 0 | 5 | 0 | FundingCarryTable 5 demo rows; "last scan 47s ago" hardcoded; beginner-view XRP/SOL story cards have hardcoded prices |
| `/alerts` | 3 | 0 | 3 | 0 | Alert types 5 hardcoded toggles (no persistence); channels 4 hardcoded; SMTP defaults hardcoded |
| `/alerts/history` | 3 | 0 | 3 | 0 | 4 stat cards `"—"`; 4 filter dropdowns inert; Export CSV inert |
| `/settings/trading` | 4 | 0 | 0 | 4 | Quick-setup Portfolio Size / Risk % / API Key inert (defaultValue only) |
| `/settings/signal-risk` | 6 | 0 | 0 | 6 | 6 sliders explicitly labelled `TODO(D-ext): no FastAPI key today` |
| `/settings/execution` | 3 | 0 | 0 | 3 | 3× OKX API key inputs disabled by design but no read-back; auto-exec slider inert |
| `/settings/dev-tools` | 6 | 0 | 0 | 6 | Sidebar tools (Auto-Scan / Demo / API Health / Wallet / API Keys / Build Info) buttons inert; "Show all 18 table counts" button inert; API Config form inert |
| **Total** | **64** | **14** | **31** | **19** | |

---

## Per-page findings

### `/` — Home page

- [web/app/page.tsx:30-37](web/app/page.tsx) — `dataSources` array hardcoded `OKX/Glassnode/Google Trends` with status `"live"/"live"/"cached"` regardless of actual API state — **E** — **P0** — wire to GET `/diagnostics/api-health` (or `/data-sources` once it exists).
- [web/app/page.tsx:39-49](web/app/page.tsx) — `macroItems` 5 hardcoded values (BTC Dom 58.9%, F&G 72, DXY 104.21, Funding +0.012%, regime "Risk-on 76%") never updated — **E** — **P0** — needs consolidated `/macro` endpoint per CLAUDE.md §9 Layer 2; today macro values come from disparate sources.
- [web/app/page.tsx:51-99](web/app/page.tsx) — `watchlistItems` 6 hardcoded prices: BTC $104,280 / ETH $3,844 / SOL $192.40 / AVAX $41.80 / LINK $22.04 / NEAR $5.82 with hardcoded sparkline polylines — **E** — **P0** — `/signals` does have these pairs; needs `/signals/{pair}/sparkline` for the sparkline component or mark sparkline decorative.
- [web/app/page.tsx:148-151](web/app/page.tsx) — Backtest KPI fallback shows `"—" / "loading"` for Return-90d / Max DD / Sharpe / Win-rate when `useBacktestSummary()` is loading (legitimate transient) **but** `subtitle="loading"` persists as visible text even after data lands if any field is null — **A** — **P1** — backend may return null for these fields; needs verification that `/backtest/summary` always returns numeric.
- [web/components/watchlist.tsx:16](web/components/watchlist.tsx) — `refreshedAgo = "2m ago"` hardcoded default never updated from real `dataUpdatedAt` — **E** — **P1** — pipe `homeQuery.dataUpdatedAt` formatted relative.
- [web/components/backtest-card.tsx:18-20](web/components/backtest-card.tsx) — Default subtitle `"BTC basket · 5.2 Sharpe"` hardcoded; never overridden from `/backtester/page.tsx` caller — **E** — **P1** — hide or derive from summary.
- [web/components/backtest-card.tsx:18](web/components/backtest-card.tsx) — Default title `"Composite backtest · last 90d"` hardcoded; doesn't reflect actual backtest date range — **E** — **P1** — accept date-range prop from `/backtest/summary`.

### `/signals` — Signal detail

- [web/app/signals/page.tsx:37-47](web/app/signals/page.tsx) — `timeframes` array fully mocked (1m/5m/15m/30m/1h/4h/1d/1w with hardcoded buy/hold scores 52,64,70,73,76,80,78,84) — **C** — **P0** — needs `/signals/{pair}/timeframes` endpoint that doesn't exist.
- [web/app/signals/page.tsx:49-60](web/app/signals/page.tsx) — `compositeFallback.score = 78.4` and 4 layer scores (82/74/71/86) hardcoded — **C** — **P0** — needs `/signals/{pair}/composite-layers` endpoint.
- [web/app/signals/page.tsx:62-68](web/app/signals/page.tsx) — On-chain tile group: 4× `value="—" subtext="live in /on-chain"` — cross-page reference UX is bad: looks broken to a user who doesn't know this is intentional — **D** — **P1** — either pull from `useOnchainDashboard(activePair)` (the endpoint exists) or remove the section and replace with a "see /on-chain" link card.
- [web/app/signals/page.tsx:70-76](web/app/signals/page.tsx) — Sentiment tiles 4× `value="—" subtext="TODO(D-ext)"` — **C** — **P0** — needs `/sentiment` endpoint that doesn't exist; on-screen "TODO(D-ext)" text is leaked dev jargon.
- [web/app/signals/page.tsx:78-86](web/app/signals/page.tsx) — Price-indicator strip 5× `value="—" subtext="TODO(D-ext)"` (Vol / ATR / Beta / Funding / Token unlocks) — **C** — **P0** — Vol/ATR are in the OHLCV stream so derivable; Beta/Funding/Unlocks need new endpoints; on-screen "TODO(D-ext)" leaks dev jargon.
- [web/app/signals/page.tsx:88-96](web/app/signals/page.tsx) — `signalHistory` 6 hardcoded entries with Feb 14 / Feb 28 / Mar 14 / Mar 28 / Apr 12 demo dates and narrative copy ("Composite crossed above 70; regime shifted bull → accumulation", returnPct +18.4% etc.) — **C** — **P0** — needs `/signals/{pair}/history` endpoint; this is the most likely "obviously fake" thing a user notices on the signals page because dates are stale (>3 weeks old as of 2026-05-05).
- [web/app/signals/page.tsx:142-143](web/app/signals/page.tsx) — `change30d` and `change1y` hardcoded `"—"` even when `detail` is loaded — **A** — **P0** (above-fold hero card) — `/signals/{pair}` doesn't return `change_30d_pct` / `change_1y_pct`; backend FastAPI router needs to derive or expose these.
- [web/app/signals/page.tsx:151](web/app/signals/page.tsx) — `regimeAge: "—"` hardcoded; renders as "stable —" in hero card — **A** — **P0** — needs `regime_age_days` from `regime_history` table join.
- [web/app/signals/page.tsx:138-140](web/app/signals/page.tsx) — Hero `price` falls back to `"—"` when `detail.price ?? detail.price_usd` is missing — known-broken per prompt: backend `price_usd` returns None — **A** — **P0** — backend FastAPI router needs to populate `price_usd` from latest scan row or live ticker.
- [web/components/signal-history.tsx:27-28](web/components/signal-history.tsx) — Card heading hardcoded `"Recent signal history · BTC"` — pair label not parameterized; even when wired the title would always say BTC — **B** — **P1** — accept ticker prop from caller.

### `/regimes` — HMM regime view

- [web/app/regimes/page.tsx:36-45](web/app/regimes/page.tsx) — `timelineSegments` 6 hardcoded states (bear/trans/accum/bull/trans/bull) with hardcoded width % and `timelineDates` (Jan 24 → Apr 23) — **C** — **P1** — needs `/regimes/{pair}/history` endpoint.
- [web/app/regimes/page.tsx:47-96](web/app/regimes/page.tsx) — `macroIndicators` 6 hardcoded values (BTC Dom 58.9%, DXY 104.21, VIX 14.2, 10Y 4.18%, F&G 72, HY spreads 312bps) with hardcoded change deltas — **E** — **P1** — needs consolidated `/macro` endpoint (same gap as Home page).
- [web/app/regimes/page.tsx:98-119](web/app/regimes/page.tsx) — `regimeWeightColumns` 4 hardcoded weight sets per regime — visual reference; comment says "actual weights live in alerts_config" — **B** — **P1** — backend has `composite_layer_weights` per regime in `alerts_config.json`; needs `/weights` endpoint (one exists per dev-tools page line 92, "GET /weights auth: key"!) wired into this page.
- [web/app/regimes/page.tsx:135](web/app/regimes/page.tsx) + [web/components/regime-card.tsx:103-105](web/components/regime-card.tsx) — Each regime card renders `since {since} · {durationDays}d` where since=`"—"` and durationDays=`0` — UX reads as "since — · 0d" for every card — **A** — **P0** — needs `regime_since_iso` + `regime_duration_days` on the `/regimes/` response payload.
- [web/app/regimes/page.tsx:191](web/app/regimes/page.tsx) — Static description string in `RegimeTimeline` props: "Current state: Bull since Apr 12, confidence 82%" — hardcoded date and confidence regardless of selected ticker — **E** — **P0** — derive from selected regime row or remove.
- [web/app/regimes/page.tsx:193](web/app/regimes/page.tsx) — `MacroOverlay` props: `regime="Risk-on"`, `confidence={76}` hardcoded — **E** — **P1** — pull from same `/macro` endpoint as the indicators.

### `/on-chain` — Glassnode + Dune metrics

- [web/app/on-chain/page.tsx:29-39](web/app/on-chain/page.tsx) — `whaleEvents` 8 hardcoded events with specific times/coins/notes ("Coinbase Pro → cold storage · single TX $184.2M", "DAO treasury → Coinbase Prime $36.4M") — **C** — **P0** — needs `/onchain/whale-events` endpoint that doesn't exist; combined with the [web/components/whale-activity.tsx:23-27](web/components/whale-activity.tsx) hardcoded "≥ $10M USD equivalent · live stream" label this is actively misleading.
- [web/app/on-chain/page.tsx:23-27](web/app/on-chain/page.tsx) — `dataSources` 3 hardcoded badges (Glassnode/Dune/On-chain status) — **E** — **P1** — could read from `useOnchainDashboard().data.source` per pair.
- [web/components/whale-activity.tsx:26](web/components/whale-activity.tsx) — Header subtitle hardcoded "≥ $10M USD equivalent · live stream" while data is fully mock — **E** — **P1** — change to truthful empty-state when no event endpoint wired.

### `/ai-assistant` — LangGraph agent

- [web/app/ai-assistant/page.tsx:93-98](web/app/ai-assistant/page.tsx) — `metrics` strip: 4× `value="—" subtext="TODO(D-ext)"` (Total Cycles / Last Cycle / Last Pair / Last Decision) — **C** — **P0** — needs `/agent/summary` endpoint; on-screen "TODO(D-ext)" leaks dev jargon to user.
- [web/app/ai-assistant/page.tsx:137](web/app/ai-assistant/page.tsx) — `<AgentStatusCard cycle={47} ...>` — `cycle={47}` hardcoded constant; never updated from server — **E** — **P0** (visible immediately on page) — wire to `agent_log.jsonl` last cycle index via `/agent/summary`.
- [web/app/ai-assistant/page.tsx:159-167](web/app/ai-assistant/page.tsx) — "Engine: LangGraph state machine · graph: 7 nodes · 12 edges" + "Crash Restarts: 0 · supervisor active · uptime 17d 6h" — uptime is hardcoded — **E** — **P1** — wire crash count and uptime from a healthcheck or `/agent/summary`.
- [web/app/ai-assistant/page.tsx:170-180](web/app/ai-assistant/page.tsx) — In-progress banner shows hardcoded "Processing AVAX/USDT — cycle running for 14s · waiting on Layer 4 (on-chain) Glassnode call" whenever `running` is true — **E** — **P1** — needs real per-cycle progress endpoint or remove the banner.
- [web/components/agent-config-card.tsx:128-211](web/components/agent-config-card.tsx) — Entire AgentConfigCard is hardcoded values: dryRun=true, cycle=60, minConf=75, maxTrade=10, cooldown=1800, portfolio=100,000, maxConcurrent=6, dailyLoss=5, maxDD=15. Sliders update local state but Save Agent Config button (line 197) has no onClick handler — **B** — **P1** — backend has `alerts_config.json` keys for these; needs `/agent/config` GET + PUT.
- [web/components/emergency-stop-card.tsx:21-26](web/components/emergency-stop-card.tsx) — "Activate Emergency Stop" button accepts `onActivate` prop but caller in ai-assistant doesn't pass one — clicks are no-ops — **B** — **P1** — wire `/agent/emergency-stop` POST.

### `/backtester` — Composite backtest

- [web/app/backtester/page.tsx:31-38](web/app/backtester/page.tsx) — `optunaRuns` 5 hardcoded entries with sharpe 4.12/3.98/3.84/3.72/3.58 and returnPct +342.8% / +321.4% / +305.2% / +289.6% / +274.1% — **C** — **P1** — needs `/backtest/optuna-runs` endpoint reading from `optuna_studies.sqlite` (the file exists per CLAUDE.md §22).
- [web/app/backtester/page.tsx:186](web/app/backtester/page.tsx) + [web/components/equity-curve.tsx:30-48](web/components/equity-curve.tsx) — EquityCurve receives only `dateRange="2023-01 → 2026-04-23"` (hardcoded) — the SVG polylines are baked in (signal equity ascending from 240→20, BTC dashed from 240→125) — **C** — **P1** — needs `/backtest/equity-curve` endpoint returning point pairs.
- [web/app/backtester/page.tsx:157-162](web/app/backtester/page.tsx) — ControlButtons "Universe: Top 10 cap", "Period: 2023-01-01 → today", "Initial: $100,000", "Rebalance: Weekly", "Costs: 12 bps" — visual only, no editable state — **B** — **P1** — backend backtester takes these as params; needs ControlButton wired to backtest config form + Re-run button (line 162) wired to POST.

### `/backtester/arbitrage`

- [web/app/backtester/arbitrage/page.tsx:40-47](web/app/backtester/arbitrage/page.tsx) — `carries` 5 hardcoded funding-rate carry rows with annualized yields +32.9% / +17.5% / +64.7% / +30.7% / +2.2% — **C** — **P1** — needs `/funding-carry` endpoint per the comment.
- [web/app/backtester/arbitrage/page.tsx:101-117](web/app/backtester/arbitrage/page.tsx) — Control row "Min Net Spread 0.40%", "Universe Top 25 cap", "Exchanges OKX·Kraken·Bybit·Coinbase", "Scan Now" button, "last scan 47s ago · live" — all visual-only — **B/E** — **P1** — Scan Now button has no onClick; "47s ago" is decorative.
- [web/app/backtester/arbitrage/page.tsx:147-174](web/app/backtester/arbitrage/page.tsx) — Beginner-view story cards: "XRP/USDT · Net spread + 0.56% · XRP is currently $2.836 on Bybit and $2.852 on Coinbase" + "SOL $192.10 on Kraken vs $193.18 on OKX" — fully hardcoded narrative — **E** — **P1** — should derive from top-2 spread rows of `arbQuery.data.opportunities` or hide when no opportunities.
- [web/app/backtester/arbitrage/page.tsx:189-195](web/app/backtester/arbitrage/page.tsx) — "Historical Arbitrage Log — last 48 opportunities · DB-backed · click to expand" button is inert; clicking does nothing — **B/C** — **P1** — needs persisted arb-history endpoint.
- [web/app/backtester/arbitrage/page.tsx:182-185](web/app/backtester/arbitrage/page.tsx) — FundingCarryTable footer copy mentions "Strategy ... typically 1-4 days" — narrative around mock carries — **E** — **P1** — moot once data is live.

### `/alerts` — Alert configuration

- [web/app/alerts/page.tsx:16-52](web/app/alerts/page.tsx) — `alertTypes` 5 toggles (Buy/Sell, Regime, On-chain, Funding, Unlock) wire to local state only; no PUT to backend — **B** — **P1** — backend has `alerts_config.json` keys for these; needs `/alerts/config` GET + PUT.
- [web/app/alerts/page.tsx:54-79](web/app/alerts/page.tsx) — `channels` 4 rows (Email connected with `david.duraes.dd1@gmail.com`, Slack/Telegram/Push not connected) hardcoded; the email defaults match David's actual address but it's hardcoded in the UI not from settings — **B** — **P1** — needs `/alerts/channels` endpoint.
- [web/app/alerts/page.tsx:142-202](web/app/alerts/page.tsx) — Email notifications card: Recipient defaultValue david.duraes... / Sender alerts@cryptosignal.app / SMTP password placeholder / threshold slider 75% — Save Config button (line 202) has no onClick; Send Test Email (line 203) inert — **B** — **P1** — needs SMTP config persistence + test-send endpoint.

### `/alerts/history`

- [web/app/alerts/history/page.tsx:21-27](web/app/alerts/history/page.tsx) — 4 stat cards: Last 24h / Last 7d / Sent rate / Avg latency all `value="—" sub="—"` — **A** — **P1** — `/alerts/log` returns rows but no aggregate counters; the comment says "TODO(D-ext): aggregate counts from /alerts/log enriched response".
- [web/app/alerts/history/page.tsx:151-178](web/app/alerts/history/page.tsx) — 4 filter buttons (Range / Type / Status / Channel) + search input — all inert; clicking the filter button does nothing — **B** — **P1** — filters need URL-search-param wiring.
- [web/app/alerts/history/page.tsx:180-185](web/app/alerts/history/page.tsx) — "↓ Export CSV" button has no onClick — **B/C** — **P1** — needs `/alerts/log?format=csv` or client-side CSV from already-fetched alerts.

### `/settings/trading`

- [web/app/settings/trading/page.tsx:139-159](web/app/settings/trading/page.tsx) — Quick Setup: Portfolio Size USD `defaultValue="10000"`, Risk per trade `defaultValue="2"`, API Key password placeholder — uncontrolled inputs (no `value`/`onChange`) so user edits aren't captured by `handleSave` — **B** — **P2** — these need to live in the trading group's persisted patch or route to dev-tools group.
- [web/app/settings/trading/page.tsx:174-178](web/app/settings/trading/page.tsx) — Footer "More settings ↓ · full tab stack below" decorative arrow — minor — **E** — **P2**.
- (Note: pairs / timeframes / TA exchange / regional colors / compact watchlist ARE wired through `useSettings` + `useSaveSettings` correctly — these are NOT findings.)

### `/settings/signal-risk`

- [web/app/settings/signal-risk/page.tsx:188-218](web/app/settings/signal-risk/page.tsx) — Position-sizing card has 3 inputs marked `TODO(D-ext): no FastAPI key today` (Portfolio size USD / Max position cap USD / Max open per pair) and 1 slider Max exposure marked the same — values change locally but never persist — **B** — **P2** — these need to land in either signal-risk or execution group; the help text leaks "TODO(D-ext)" jargon to the user.
- [web/app/settings/signal-risk/page.tsx:258-268](web/app/settings/signal-risk/page.tsx) — MTF alignment threshold + Regime-confidence floor sliders both marked `TODO(D-ext): no FastAPI key today` — local-state only — **B** — **P2** — same as above; user-facing help text says "TODO(D-ext)".
- [web/app/settings/signal-risk/page.tsx:105-112](web/app/settings/signal-risk/page.tsx) — `compositeWeights` 4 hardcoded weight values (0.30/0.15/0.20/0.35) labelled "Visual reference" — comment says actual weights live in alerts_config — **B** — **P2** — same `/weights` endpoint as regimes page.

### `/settings/execution`

- [web/app/settings/execution/page.tsx:194-200](web/app/settings/execution/page.tsx) — Auto-execute confidence threshold slider marked `TODO(D-ext): no FastAPI key today` — local state only — **B** — **P2** — needs `auto_exec_confidence_threshold` key in execution group allowlist.
- [web/app/settings/execution/page.tsx:226-262](web/app/settings/execution/page.tsx) — OKX API Key / Secret / Passphrase inputs are intentionally `disabled` with placeholder text "set via OKX_API_KEY env var" — by design but no read-back mechanism: user can't tell if keys ARE set or NOT — **B** — **P2** — needs `/exchange/key-status` returning `{api_key_set: bool, secret_set: bool, passphrase_set: bool}` (do NOT expose values).
- [web/app/settings/execution/page.tsx:71-76](web/app/settings/execution/page.tsx) — Initial state defaults `liveMode=false`, `autoExecute=true`, `exchange="OKX"`, `maxOrderSizeUsd=1000` — these get hydrated from `/settings` so OK, but `autoExecConfidence=80` (line 77) does NOT hydrate (no FastAPI key) — see above bullet.

### `/settings/dev-tools`

- [web/app/settings/dev-tools/page.tsx:40-77](web/app/settings/dev-tools/page.tsx) — `sidebarTools` 6 cards with action buttons (Configure / Open / Check / Import / Manage / Details) — none wire onClick handlers — **B** — **P2** — each links to a defunct legacy Streamlit feature; either rebuild the targets or remove the section.
- [web/app/settings/dev-tools/page.tsx:74](web/app/settings/dev-tools/page.tsx) — Build Info card hardcoded `"v2026.04.29 · commit 335832c · branch redesign/ui-2026-05-full-mockup-match"` — stale (today is 2026-05-05 and branches have moved on) — **E** — **P2** — pipe from `/diagnostics/version` or build-time env var.
- [web/app/settings/dev-tools/page.tsx:300-307](web/app/settings/dev-tools/page.tsx) — "Show all 18 table counts" toggle button: state flips `showAllTables` boolean but nothing renders the table list when true (the JSX block ends at the button) — **B** — **P2** — either render the additional rows from `useDatabaseHealth()` or remove the button.
- [web/app/settings/dev-tools/page.tsx:323-364](web/app/settings/dev-tools/page.tsx) — REST API Server card: API Key / Host / Port inputs uncontrolled (defaultValue only); "Save API Config" button has no onClick — **B** — **P2** — these are runtime server config so could be informational-only; if so, label as such instead of editable inputs.
- [web/app/settings/dev-tools/page.tsx:82-97](web/app/settings/dev-tools/page.tsx) — `endpoints` table has 14 hardcoded REST endpoints; backend probably has more — **E** — **P2** — could derive from FastAPI's OpenAPI JSON (`/openapi.json`).
- [web/app/settings/dev-tools/page.tsx:373-377](web/app/settings/dev-tools/page.tsx) — Start command pre block hardcoded `cd "/path/to/crypto-signal-app" python -m uvicorn api:app ...` — operator-doc text, fine but stale — **E** — **P2**.

---

## Cross-cutting patterns

### Pattern 1: "TODO(D-ext)" leaking to user-visible subtext (P0)
Five tile groups across the Signals page show `subtext: "TODO(D-ext)"` directly to end users — that's developer jargon visible above the fold of the most-visited drilldown page. Same pattern appears in AI Assistant metric strip and signal-risk help text. **Fix pattern: replace `subtext: "TODO(D-ext)"` with `subtext: "coming soon"` or `subtext: "not measured yet"` until the endpoints land.**

### Pattern 2: "live in /on-chain" cross-page references (P1)
Signals page on-chain tile group says `value="—" subtext="live in /on-chain"` — categorically different from a normal placeholder because the data does exist (via `/onchain/dashboard`), it's just not consumed. Either pull it (one extra hook call) or replace the 4-tile section with a single "View on-chain detail →" link card. **Don't show 4 dashes with cross-page hints.**

### Pattern 3: Hardcoded prices/dates that visibly age (P0)
Mock data with specific dates from Feb–Apr 2026 (signal history, regime timeline, equity curve dateRange "2023-01 → 2026-04-23") becomes increasingly suspicious as the user's clock drifts past those dates. The signal-history page (`Apr 12 08:20` BUY +18.4%) is now ~3 weeks old; the macro indicators (BTC Dom 58.9%) are static across all sessions and clearly don't match Coinbase/CoinGecko if the user cross-checks. **Highest-impact category for the pre-mobile audit because mobile users tend to cross-check more aggressively.**

### Pattern 4: Inert action buttons (P1/P2)
Buttons with hardcoded labels but no `onClick` or stub handlers: Save Agent Config, Send Test Email, Save API Config, Re-run backtest, Scan Now (arbitrage), Activate Emergency Stop (with prop but no caller wires it), Export CSV, "Show all 18 table counts", and the 6 sidebar-tool action buttons (Configure / Open / Check / Import / Manage / Details). Sum: ~14 inert buttons across the app. **Each one trains the user that buttons are decorative.**

### Pattern 5: Hardcoded macro indicators duplicated across 2 pages (P0/P1)
The same 5 hardcoded macro values (BTC Dominance 58.9%, F&G 72, DXY 104.21, etc.) appear on both `/` (Home → MacroStrip) and `/regimes` (RegimesPage → MacroOverlay) with slight format differences. **Single consolidated `/macro` endpoint would close both findings at once and is mentioned in the comments of both pages.**

### Pattern 6: `since="—" / durationDays=0` empty-state UX (P0)
The RegimeCard component renders `since {since} · {durationDays}d` unconditionally; with placeholder values it reads as literal "since — · 0d" on every card on the regimes page (8 cards). **Either compute these on backend (regime_history join) or have the card hide that line when missing.**

### Pattern 7: Components hardcoded to BTC/specific assumptions (P1)
- `SignalHistory` heading is `"Recent signal history · BTC"` ignoring the active coin
- `BacktestCard` defaults to `"BTC basket · 5.2 Sharpe"`
- `EquityCurve`'s SVG is BTC-shaped (always-up signal vs flat-ish BTC buy-and-hold)

These were OK when the v0 mockups were specifically a BTC demo, but as soon as the app supports multi-coin selection (which it does), the captions diverge from the data.

### Pattern 8: Dev-tools-style strings on user-facing routes
Several user-facing pages leak Streamlit-era / operator jargon: "v2026.04.29 · commit 335832c · branch redesign/ui-2026-05-full-mockup-match", "TPE sampler · 2,400 trials", "agent_log.jsonl", "alerts_config.json", "graph: 7 nodes · 12 edges". Some are appropriate (settings/dev-tools page); on `/ai-assistant` and `/backtester` these are out of place for any user level above Advanced.

---

## Recommended P0 fix order (most-visible-first)

1. **Wire `price_usd` on `/signals/{pair}` response** ([web/app/signals/page.tsx:138-140](web/app/signals/page.tsx)) — the giant `"—"` in the hero card is the single most damaging UI bug; visible to every user landing on Signals. Backend fix only — frontend already reads `detail.price ?? detail.price_usd`.
2. **Replace `signalHistory` mock with real `/signals/{pair}/history` endpoint** ([web/app/signals/page.tsx:88-96](web/app/signals/page.tsx)) — narrative copy with stale 2026-Q1 dates is the highest-confidence "this is fake" signal a user can spot.
3. **Replace `macroItems` and `macroIndicators` mocks with consolidated `/macro` endpoint** ([web/app/page.tsx:39-49](web/app/page.tsx) + [web/app/regimes/page.tsx:47-96](web/app/regimes/page.tsx)) — macro values appear on first-load Home + Regimes; closing both at once.
4. **Replace `watchlistItems` mock with derived data from existing `/signals` payload** ([web/app/page.tsx:51-99](web/app/page.tsx)) — the prices/changes are already in `/home/summary` hero cards; just need a watchlist-shape endpoint or client-side derive (drop sparkline column for now).
5. **Replace 4 sentiment tiles + 5 price-indicator tiles `TODO(D-ext)` text** ([web/app/signals/page.tsx:70-86](web/app/signals/page.tsx)) — at minimum change the user-facing subtext from `"TODO(D-ext)"` to `"coming soon"` while endpoints are built; ideally derive Vol(24h)/ATR from OHLCV.
6. **Wire `change_30d_pct` and `change_1y_pct` in `/signals/{pair}`** ([web/app/signals/page.tsx:142-143](web/app/signals/page.tsx)) — hero card shows three change figures; only 24h is real.
7. **Wire `regime_age_days` for SignalHero + RegimeCard** ([web/app/signals/page.tsx:151](web/app/signals/page.tsx) + [web/app/regimes/page.tsx:135](web/app/regimes/page.tsx)) — current "since — · 0d" reads as broken on every regime card.
8. **Replace `cycle={47}` hardcoded prop on AgentStatusCard** ([web/app/ai-assistant/page.tsx:137](web/app/ai-assistant/page.tsx)) — needs `/agent/summary`; bonus: closes the AgentMetricStrip 4× `"—"` placeholders too.
9. **Hide or replace WhaleActivity table on `/on-chain`** ([web/app/on-chain/page.tsx:29-39](web/app/on-chain/page.tsx)) — fake events labelled "live stream" is the worst kind of placeholder; either remove until `/onchain/whale-events` lands, or stub with empty state.
10. **Replace `compositeFallback.score = 78.4` and `timeframes` mocks on Signals** ([web/app/signals/page.tsx:37-60](web/app/signals/page.tsx)) — both need new endpoints; hide both panels (or render empty-state) until they exist.
11. **Wire RegimeTimeline real data** ([web/app/regimes/page.tsx:36-45](web/app/regimes/page.tsx) + line 191) — segment widths, dates, AND the "Bull since Apr 12, confidence 82%" description are all hardcoded.
12. **Replace data-source pill mocks on Home + On-chain** ([web/app/page.tsx:30-37](web/app/page.tsx) + [web/app/on-chain/page.tsx:23-27](web/app/on-chain/page.tsx)) — show actual provider availability.
13. **Cross-page on-chain tile fix on Signals page** ([web/app/signals/page.tsx:62-68](web/app/signals/page.tsx)) — pull from `useOnchainDashboard(activePair)` (endpoint exists) OR replace with a "View on-chain detail →" link card.
14. **Remove "live stream" / "live · 24h" labels when data is mock** (cross-cutting) — anywhere a "live" pill is shown above mock data, swap for the truthful empty-state pattern from MEMORY.md (e.g. "geo-blocked", "rate limited", "run a scan to populate").

---

## Notes for the audit consumer

- Backend endpoints that DO exist and ARE consumed correctly (no findings filed): `/home/summary`, `/signals` (top-N), `/signals/{pair}` (partial), `/regimes/`, `/onchain/dashboard`, `/backtest/summary`, `/backtest/trades`, `/backtest/arbitrage`, `/scan/trigger`, `/scan/status`, `/execute/status`, `/diagnostics/circuit-breakers`, `/diagnostics/database`, `/alerts/log`, `/settings` (trading + signal-risk + execution groups), `/exchange/test-connection`, `/ai/decisions`, `/ai/ask`. The wiring on these is solid.
- Backend endpoints LISTED in dev-tools but not visibly consumed elsewhere: `/weights` (line 92 of dev-tools page) — **could close the regime-weights and composite-weights findings**.
- The 14 findings tagged P0 are concentrated on Home (3) and Signals (6) and Regimes (2) and AI Assistant (2) and On-chain (1). Mobile-first audience will see Home and Signals on first launch; those should be the cutover priority.
- No security or correctness bugs found in this sweep — all findings are completeness/UX gaps. Static rendering is correct, hooks are correctly wired, error states exist. The frontend was clearly built with explicit fallbacks in mind; the gap is just that "fallback" became "permanent" while backend endpoints lag.
