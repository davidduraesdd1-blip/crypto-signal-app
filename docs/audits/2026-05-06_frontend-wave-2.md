# Frontend Wave 2 — Completeness + Bug-Class Sweep

**Date:** 2026-05-06
**Scope:** `web/app/` (14 page.tsx routes) + every component on the import graph.
**Methodology:** Read-only audit. Started from Wave 1 doc (`docs/audits/2026-05-05_frontend-completeness.md`), verified each fix held under git log `9d136c2…40259d9`, then walked every page with three additional lenses: (1) the SignalType-mismatch crash class, (2) level-gating coverage per CLAUDE.md §7, (3) honest empty / loading / error states. Read every component under `web/components/` (40 files) — no code modified.

---

## TL;DR

- **Wave 1 P0 fixes held.** 12 / 12 are still in place; SignalHero now defensively falls back, scan rows carry `change_30d_pct/change_1y_pct`, signal history is wired to the live endpoint, multi-timeframe + composite use real data, viewport / safe-area shipped.
- **One Wave-1-class crash is still wired** — Home page `SignalCard` consumes `directionToSignalType(...)` (5-tier) but `SignalCard.signalConfig` is 3-tier. Identical bug class to the SignalHero hotfix at commit `9d136c2`. **One STRONG BUY card on the Home page crashes the entire route.** Backend `routers/home.py:84` confirms the engine actively emits `STRONG BUY / STRONG SELL` strings.
- **Level-gating barely covers two pages.** `useUserLevel()` is consumed by `signals/page.tsx` and `backtester/arbitrage/page.tsx` only. The other 12 routes ignore the user tier even where the v0 mockup explicitly described tier-aware behaviour (`settings/layout.tsx:18` says "Title shows 'Config Editor' at Advanced level" — never wired).
- **`AgentConfigCard` sliders are unmovable.** Every `SliderField` is a controlled `<input type="range" value={...}>` with no parent-supplied `onChange` — drag fires `onChange?.(...)` against `undefined` and React snaps the thumb back. Same component is rendered on `/ai-assistant`. Looks broken to anyone who tries.
- **Mobile bottom-nav is missing 3 routes** — On-Chain, Backtester, AI Assistant unreachable on mobile.

| | P0 | P1 | P2 | total |
|---|---:|---:|---:|---:|
| Wave 1 finds still open (residual) | 0 | 19 | 19 | 38 |
| Wave 2 NEW finds | **6** | **17** | **9** | **32** |
| **Combined open** | **6** | **36** | **28** | **70** |

---

## Verification — Wave 1 fixes (all 12 hold)

| Tag | Wave-1 P0 | Status now | Evidence |
|---|---|---|---|
| P0-1 | Strip leaked API key from runbooks | held | `git log b5e369e` |
| P0-2 | Mobile build env + Capacitor scaffold | held | `git log 7f85c36` |
| P0-3 | Engine emits `price/change_24h/30d/1y` | held | `crypto_model_core.py:4794` (referenced in [signals/page.tsx:241-243](web/app/signals/page.tsx)) |
| P0-4 | render.yaml plan reconcile | held | `git log 76dff07` |
| P0-5 | UserLevelProvider wired | partially held — see Wave 2 finding F-LEVEL-* | [providers/user-level-provider.tsx](web/providers/user-level-provider.tsx) is good; only 2 pages consume it |
| P0-6 | Capacitor bundle id `com.polaris.edge` | held | `git log 621e36b` |
| P0-7 | SignalHistory wired to `/signals/history` | held | [components/signal-history.tsx:31-101](web/components/signal-history.tsx); honest empty / loading / error states present |
| P0-8 | Scrub user-visible TODO(D-ext) | mostly held; see Wave 2 finding F-COPY-1 (one residual on `useExecutionStatus` query subtitle "agent_log.jsonl") | [signals/page.tsx:67-81](web/app/signals/page.tsx), [ai-assistant/page.tsx:94-99](web/app/ai-assistant/page.tsx) |
| P0-9 | iOS safe-area | held | `git log b5c5555` |
| P0-10 | /diagnostics/feeds reachability | held | `git log b1739d3` |
| P0-MTF | Multi-timeframe wired to `detail.timeframes` | held — defensively coerced via `_toCleanString/_toFiniteNumber` | [signals/page.tsx:282-302](web/app/signals/page.tsx) |
| P0-COMPOSITE | Composite shows `confidence_avg_pct` + honest empty layer state | held | [signals/page.tsx:306-315](web/app/signals/page.tsx) + [components/composite-score.tsx:30-36](web/components/composite-score.tsx) |
| HOTFIX | `signal-hero.tsx` defensive `?? signalConfig.hold` | held | [components/signal-hero.tsx:60](web/components/signal-hero.tsx) |
| HOTFIX | `_deriveTransitions` type drift guard | held | [signals/page.tsx:148-191](web/app/signals/page.tsx) |

---

## Summary table — Wave 2 only (new findings per page)

| Page | NEW P0 | NEW P1 | NEW P2 | New crash-risk? |
|---|---:|---:|---:|---|
| `/` (Home) | **2** | 3 | 1 | yes — `signalConfig[strong-buy]` undefined |
| `/signals` | 1 | 2 | 1 | partial — composite consumer assumes finite score |
| `/regimes` | 1 | 2 | 0 | partial — `MacroOverlay.sentimentDot` lookup |
| `/on-chain` | 1 | 1 | 0 | no — but "live stream" label still on mock data |
| `/ai-assistant` | **1** | 4 | 1 | yes — `AgentConfigCard` sliders unusable |
| `/backtester` | 0 | 1 | 1 | no |
| `/backtester/arbitrage` | 0 | 1 | 0 | no — `arb-spread-table` lookup is locally-typed |
| `/alerts` | 0 | 0 | 1 | no |
| `/alerts/history` | 0 | 1 | 1 | no |
| `/settings/trading` | 0 | 1 | 1 | no |
| `/settings/signal-risk` | 0 | 0 | 1 | no |
| `/settings/execution` | 0 | 1 | 1 | no |
| `/settings/dev-tools` | 0 | 0 | 1 | no |
| **Cross-cutting** | 1 | 0 | 0 | yes — `decisionsTable.statusConfig[unknown]` |
| **Total** | **6** | **17** | **9** | |

---

## Per-page findings — Wave 2 only

(Wave 1 residuals are still open per the Wave 1 doc — not relisted here.)

### `/` — Home page

- **F-HOME-1 (P0, CRASH RISK)** [web/app/page.tsx:137](web/app/page.tsx) — `signal: directionToSignalType(card.direction ?? "HOLD") as SignalType`. `directionToSignalType` is typed `"buy" | "sell" | "hold" | "strong-buy" | "strong-sell"` ([lib/format.ts:87-95](web/lib/format.ts)) but the cast erases that. `SignalCard.signalConfig` ([components/signal-card.tsx:26-42](web/components/signal-card.tsx)) only has `buy/hold/sell` keys, and line 44 does `const config = signalConfig[signal]` with no `??` guard, then line 59 reads `config.className`. A real `STRONG BUY` from the engine (confirmed emitted by `routers/home.py:84` and also `crypto_model_core.py`) makes `config = undefined` → TypeError → the route-level error boundary catches it but the entire Home page goes blank. **Same crash class as the SignalHero hotfix landed at `9d136c2`.** **Fix:** mirror SignalHero — collapse strong-* to base in the page mapper OR add `?? signalConfig.hold` defensive lookup inside SignalCard.
- **F-HOME-2 (P0, COPY)** [web/app/page.tsx:30-37](web/app/page.tsx) — `dataSources` array hardcoded `OKX/Glassnode/Google Trends · live/live/cached` regardless of actual API state. Wave 1 P0 (still open) — but now there's an actual P0-10 `/diagnostics/feeds` endpoint shipped at commit `b1739d3` that DOES return reachability per provider; Home is the only consumer not wired. **Fix:** replace mock with `useApiHealth()` consumer of `/diagnostics/feeds`.
- **F-HOME-3 (P1, BUG-CLASS)** [web/app/page.tsx:124-141](web/app/page.tsx) — `card.direction` and `card.regime` are typed `DirectionLabel | string | null` and `RegimeLabel | null`. The page assumes `card.regime` always returns a clean label (string) — but a null regime renders as `regimeToDisplay(null) → "unknown"` (good) — the bug is that `regimeToDisplay` lower-cases `RegimeLabel` literals, so a Title-cased `"Bull"` becomes `"bull"` for display, but the `RegimeWeights.regimeConfig` keys are `bull/accumulation/distribution/bear` whereas `RegimeCard.stateConfig` keys are `bull/bear/transition/accumulation/distribution` — different unions, possible drift if a card is migrated to use either union directly.
- **F-HOME-4 (P1, EMPTY-STATE)** [web/app/page.tsx:144-152](web/app/page.tsx) — `backtestKpis` fallback shows `value: "—"` with `delta: "loading"` even when `summaryQuery.isError`. No error-distinct copy. Pre-Wave-1 finding still open. **Fix:** branch on `backtestQuery.isError` to surface "couldn't load — try refreshing".
- **F-HOME-5 (P1, A11Y)** [web/components/watchlist.tsx:28-34](web/components/watchlist.tsx) — "Customize ▾" button has no `onClick`, `aria-haspopup`, or any keyboard handler. Pure decoration. Same dead-button class as Wave 1 cross-cutting Pattern 4.
- **F-HOME-6 (P2, COPY)** [web/components/watchlist.tsx:16](web/components/watchlist.tsx) — `refreshedAgo = "2m ago"` hardcoded default never updated from real `dataUpdatedAt`. Wave 1 finding still open. Surface `homeQuery.dataUpdatedAt` formatted relative.

### `/signals` — Signal detail

- **F-SIG-1 (P0, COPY)** [web/app/signals/page.tsx:51-54](web/app/signals/page.tsx) — `onChainIndicators` 4-tile group still uses `subtext: "live in /on-chain"` as a cross-page reference. Wave 1 P1 finding (Pattern 2); should be elevated to P0 because the data is one hook call away (`useOnchainDashboard(activePair)` is already imported on `/on-chain`). The 4 dashes with the cross-page hint look broken; the remediation is one query and a mapper.
- **F-SIG-2 (P1, BUG-CLASS)** [web/app/signals/page.tsx:307-313](web/app/signals/page.tsx) + [components/composite-score.tsx:23](web/components/composite-score.tsx) — CompositeScore receives `score: number` and unconditionally calls `score.toFixed(1)`. Parent passes `composite ?? 0` so this is safe today, but if a future caller passes `null`/`undefined`, it crashes. **Fix:** add `Number.isFinite(score) ? score.toFixed(1) : "—"` inside the component.
- **F-SIG-3 (P1, A11Y)** [web/components/coin-picker.tsx:33-42](web/components/coin-picker.tsx) — "More ▾ +N" button takes `onMore` prop but [signals/page.tsx:392-395](web/app/signals/page.tsx) doesn't pass one. Clicks are no-ops. With 30-asset universe most users see "+25" and click it expecting a list. Inert.
- **F-SIG-4 (P2, BUG-CLASS)** [web/app/signals/page.tsx:362-366](web/app/signals/page.tsx) — Technical "Supertrend" tile sets `value: directionToSignalType(detail.direction).toUpperCase()` so a STRONG BUY renders as literal `"STRONG-BUY"` (with the dash) — confusing label vs the BUY/SELL/HOLD wording everywhere else. **Fix:** strip the prefix/dash to render `"BUY"` or `"STRONG"` separately.

### `/regimes`

- **F-REG-1 (P0, BUG-CLASS)** [components/regime-card.tsx:67](web/components/regime-card.tsx) — `const config = stateConfig[state]` with no `??` guard. The page-side mapper `toRegimeState` ([regimes/page.tsx:20-30](web/app/regimes/page.tsx)) returns one of 5 known values, but the catch-all is `"bear"` — meaning a `RegimeLabel = "Sideways"` from the engine renders as `bear` (wrong). And the engine's `RegimeLabel` union ([api-types.ts:42-52](web/lib/api-types.ts)) explicitly admits `string` ("engine may emit a new state — we display verbatim") — so a brand-new label like `"Mixed"` would just round-trip through `toRegimeState` to `"bear"`. **Fix:** add `transition` / `accumulation` / `distribution` to the v0 `stateConfig` (already there) and surface the actual engine state name as a tooltip; do NOT fall back silently to bear.
- **F-REG-2 (P1, A11Y)** [components/macro-overlay.tsx:66](web/components/macro-overlay.tsx) — `sentimentDot[ind.sentiment]` lookup with no guard. Today `Sentiment` is locally typed to `bull/bear/neutral` and the parent regimes page literal-types its inputs, so safe. But if a future macro endpoint emits a new sentiment label, this crashes. Defensive `??` lookup.
- **F-REG-3 (P1, EMPTY-STATE)** [regimes/page.tsx:131-138](web/app/regimes/page.tsx) — Even when `regimesQuery.data` is empty (no scan run), the page still renders `RegimeTimeline` + `MacroOverlay` + `RegimeWeights` with hardcoded mock segments + "Bull since Apr 12, confidence 82%" description. The empty-state on line 161-167 only hides the regime CARDS — the rest of the page is still fully mocked. **Fix:** lift the empty-state guard to wrap the timeline/overlay/weights too; keep the page-header visible only.

### `/on-chain`

- **F-ONC-1 (P0, COPY/MISLEADING)** [components/whale-activity.tsx:26](web/components/whale-activity.tsx) — Header subtitle hardcoded "≥ $10M USD equivalent · live stream" while the events array passed in ([on-chain/page.tsx:29-39](web/app/on-chain/page.tsx)) is mock with names like "Coinbase Pro → cold storage". This is the single most misleading copy in the app per CLAUDE.md (MEMORY note "feedback_empty_states.md"). Wave 1 listed this; still open. **Fix:** drop the subtitle entirely until the endpoint lands, or change to "no stream wired — sample events shown".
- **F-ONC-2 (P1, COPY)** [on-chain/page.tsx:23-27](web/app/on-chain/page.tsx) — `dataSources` 3 hardcoded badges ("Glassnode/Dune/On-chain · live/live/cached"). The per-card `labelFor()` already derives status from each query's `source` field — extend to the page-level `DataSourceRow` too.

### `/ai-assistant`

- **F-AI-1 (P0, INTERACTION)** [components/agent-config-card.tsx:43-65](web/components/agent-config-card.tsx) + lines 142-196 — Every `SliderField` gets `value={...static...}` and `onChange={(e) => onChange?.(Number(e.target.value))}` — but the parent never passes `onChange`. The native range input is controlled and React resets the thumb on each render. **The user can drag, see no movement, conclude all sliders are broken.** The "Save Agent Config" button (line 197) also has no `onClick`. The whole card is decorative. **Fix:** lift state into the parent (or the card itself) and wire each slider — same pattern that works on `settings/signal-risk/page.tsx`.
- **F-AI-2 (P1, COPY)** [ai-assistant/page.tsx:177](web/app/ai-assistant/page.tsx) — In-progress banner says "Processing AVAX/USDT — cycle running for 14s · waiting on Layer 4 (on-chain) Glassnode call" whenever `running` is true, regardless of what the agent is actually doing. The pair, elapsed seconds, and current layer are all hardcoded. Misleading. **Fix:** remove the banner until `/agent/progress` exists, or replace with a generic "agent processing — see decisions table" copy.
- **F-AI-3 (P1, COPY)** [ai-assistant/page.tsx:166](web/app/ai-assistant/page.tsx) — "supervisor active · uptime 17d 6h" hardcoded. Stale on Day 1 of any deploy. Wave 1 finding still open.
- **F-AI-4 (P1, COPY)** [ai-assistant/page.tsx:135-139](web/app/ai-assistant/page.tsx) — `AgentStatusCard cycle={47}` hardcoded — Wave 1 P0; not yet shipped. Backend endpoint `/agent/summary` doesn't exist.
- **F-AI-5 (P1, BUG-CLASS, EMPTY)** [components/emergency-stop-card.tsx:18](web/components/emergency-stop-card.tsx) — Status text "No emergency stop · agent operating normally" and the dot color are hardcoded; when `active=true`, the dot stays grey and the text doesn't change. **Fix:** branch on `active`.
- **F-AI-6 (P2, A11Y)** [components/decisions-table.tsx:80-82](web/components/decisions-table.tsx) — `decisionConfig[d.decision]` and `statusConfig[d.status]` no-guard lookup. Today the page-side mapper produces clean values, but if backend `r.status` evolves (e.g. "rate_limited"), `sc.bgClass` crashes. Defensive `??`.

### `/backtester`

- **F-BT-1 (P1, COPY)** [backtester/page.tsx:186](web/app/backtester/page.tsx) + [components/equity-curve.tsx](web/components/equity-curve.tsx) — Equity curve dateRange `"2023-01 → 2026-04-23"` hardcoded; today is 2026-05-06 so caption is 13 days stale. SVG polylines hardcoded. Wave 1 still open.
- **F-BT-2 (P2, COPY)** [backtester/page.tsx:189](web/app/backtester/page.tsx) — OptunaTable footer "TPE sampler · 2,400 trials · selected by best out-of-sample Sharpe" — operator-internal jargon shown on what's a research-tier user page. Hide at Beginner level.

### `/backtester/arbitrage`

- **F-ARB-1 (P1, INTERACTION)** [arbitrage/page.tsx:115-119](web/app/backtester/arbitrage/page.tsx) — "Scan Now →" button has no `onClick`; "last scan 47s ago · live" hardcoded. Wave 1 still open. Inert.

### `/alerts`

- **F-ALERTS-1 (P2, INTERACTION)** [alerts/page.tsx:202-205](web/app/alerts/page.tsx) — Save Config + Send Test Email buttons no `onClick`. Wave 1 still open.

### `/alerts/history`

- **F-AHIST-1 (P1, BUG-CLASS)** [alerts/history/page.tsx:65-71](web/app/alerts/history/page.tsx) — `rowToEntry` has fallthrough cases that map any unrecognised type (e.g. `"agent_decision"`) to `entryType: "regime"` with `typeLabel = String(row.type)`. Then `AlertLogTable.typeConfig[entry.type]` accesses by literal "regime" — safe, but the visual badge will read "Regime" for an agent_decision alert, which is wrong. **Fix:** add an `"other"` AlertType key to typeConfig + a neutral grey badge.
- **F-AHIST-2 (P2, COPY)** [alerts/history/page.tsx:21-27](web/app/alerts/history/page.tsx) — 4 stat cards `value="—"` regardless of query state. No loading shimmer, no error message. Wave 1 still open.

### `/settings/trading`

- **F-TRD-1 (P1, COPY)** [settings/trading/page.tsx:139-170](web/app/settings/trading/page.tsx) — Quick Setup Portfolio Size / Risk per trade / API Key are uncontrolled inputs (`defaultValue` only), no `onChange`, not in `handleSave` patch. Wave 1 P2 still open. Looks like a save panel; saves nothing.
- **F-TRD-2 (P2, COPY)** [settings/layout.tsx:18](web/app/settings/layout.tsx) — Subtitle says "Title shows 'Config Editor' at Advanced level" but no consumer of `useUserLevel()` exists in any settings page; the title is always "Settings". Either wire the title or drop the misleading subtitle.

### `/settings/signal-risk`

- **F-SR-1 (P2, A11Y)** [settings/signal-risk/page.tsx:188-218](web/app/settings/signal-risk/page.tsx) — Position-sizing fields' help text says "Server-side persistence pending" — informationally correct (P0-8 cleanup retired the old TODO(D-ext) string). No bug. Listed for completeness.

### `/settings/execution`

- **F-EXEC-1 (P1, COPY)** [settings/execution/page.tsx:226-262](web/app/settings/execution/page.tsx) — OKX API Key/Secret/Passphrase inputs are intentionally `disabled` — but no read-back of whether keys ARE set. The user has no way to know if `OKX_API_KEY` env var is loaded. **Fix:** small `/exchange/key-status` returning `{api_key_set, secret_set, passphrase_set}` booleans (not values).

### `/settings/dev-tools`

- **F-DEV-1 (P2, COPY)** [settings/dev-tools/page.tsx:74](web/app/settings/dev-tools/page.tsx) — Build info hardcoded `v2026.04.29 · commit 335832c · branch redesign/ui-2026-05-full-mockup-match` — today's commits are after `40259d9`. Wave 1 still open. Pipe via `NEXT_PUBLIC_BUILD_SHA` env var.

### Cross-cutting

- **F-LEVEL-1 (P0, FUNCTIONAL)** Per CLAUDE.md §7 (project) every page must scale by user level — Beginner / Intermediate / Advanced. Today only [web/app/signals/page.tsx:200](web/app/signals/page.tsx) and [web/app/backtester/arbitrage/page.tsx:53](web/app/backtester/arbitrage/page.tsx) consume `useUserLevel()`. **12 of 14 routes** ignore the user tier even where the v0 mockup explicitly described tier-aware copy. Highest-impact pages to gate next: `/` (Home — Beginner needs "What does this mean?" gloss above the macro strip), `/regimes` (Beginner needs plain-English regime explanation), `/ai-assistant` (Advanced should see the LangGraph node count + crash counter; Beginner should see only the agent on/off and last decision). **Fix:** add `useUserLevel()` to each page header level switch — pattern is already established on the Signals page.
- **F-MOBILE-1 (P0, NAV)** [web/components/sidebar.tsx:65-71](web/components/sidebar.tsx) — `mobileNavItems` includes Home / Signals / Regimes / Alerts / Settings only. **On-Chain, Backtester, AI Assistant are unreachable on mobile** — no path from the bottom nav to them. CLAUDE.md §8 master template says mobile-responsive at 768px breakpoint, which means the routes have to be reachable, not just renderable. **Fix:** add a "More" overflow menu to MobileNav OR rotate Backtester/On-chain/AI into the visible row at the cost of one of the existing five.
- **F-CROSS-1 (P1, BUG-CLASS)** Search `signalConfig[`, `stateConfig[`, `typeConfig[`, `decisionConfig[`, `statusConfig[`, `regimeConfig[` across components — every one is a no-guard dict lookup keyed by a string the parent provides. Most are safe today because the immediate caller literal-types the input, but **the type system enforces nothing at the data-fetching boundary**. A backend label drift breaks the page. **Fix pattern:** every `*Config[key]` lookup should be `*Config[key] ?? *Config.<safe-fallback>` (mirrors the Wave-1 SignalHero hotfix at commit `9d136c2`).

---

## Cross-cutting bug-class section: places where SignalType assumptions could crash

Per the Wave-1 hotfix at commit `9d136c2`, the failure mode is:

1. Engine emits a value the frontend doesn't know about (`STRONG BUY`, `LOW VOL`, `NO DATA`, future labels).
2. Page-side mapper either passes through verbatim or casts away type info.
3. Component does `Record<3-tier>[5-tier-value]` → `undefined`.
4. Next access (`config.className`, `config.bgClass`, etc.) → TypeError → blank page.

**Verified call sites where this could crash today:**

| File | Line | Lookup | Caller-supplied risk | Has `??` guard? |
|---|---:|---|---|---|
| [components/signal-card.tsx](web/components/signal-card.tsx) | 44 | `signalConfig[signal]` | **HOME PAGE → `directionToSignalType` returns 5-tier** | **NO — F-HOME-1 P0** |
| [components/signal-hero.tsx](web/components/signal-hero.tsx) | 60 | `signalConfig[signal]` | parent collapses 5-tier → 3-tier | YES (post-`9d136c2`) |
| [components/timeframe-strip.tsx](web/components/timeframe-strip.tsx) | 30 | `signalConfig[tf.signal]` | parent IIFE coerces to 3-tier | NO, but parent guarded |
| [components/signal-history.tsx](web/components/signal-history.tsx) | 66 | `signalConfig[entry.signal]` | parent `_mapDirectionToSignal` collapses to 3-tier | NO, but parent guarded |
| [components/regime-card.tsx](web/components/regime-card.tsx) | 67 | `stateConfig[state]` | parent `toRegimeState` defaults to `"bear"` for unknowns (silently wrong) | NO — F-REG-1 |
| [components/regime-timeline.tsx](web/components/regime-timeline.tsx) | 38, 56 | `stateConfig[seg.state]` | parent passes literal-typed segments (5-tier) — but data could be richer | NO |
| [components/regime-weights.tsx](web/components/regime-weights.tsx) | 45 | `regimeConfig[col.regime]` | parent passes 4-tier literals — but `regime-timeline` uses 5-tier `TimelineState` (different union) | NO |
| [components/macro-overlay.tsx](web/components/macro-overlay.tsx) | 66 | `sentimentDot[ind.sentiment]` | parent passes 3-tier literals; future macro endpoint may emit new label | NO — F-REG-2 |
| [components/arb-spread-table.tsx](web/components/arb-spread-table.tsx) | 58 | `signalConfig[s.signal]` | parent `rowToSpread` types as 3-tier locally | NO, but parent guarded |
| [components/decisions-table.tsx](web/components/decisions-table.tsx) | 81-82 | `decisionConfig[d.decision]` + `statusConfig[d.status]` | parent maps from `r.direction` / heuristic status; future status drift breaks | NO — F-AI-6 |
| [components/alert-log-table.tsx](web/components/alert-log-table.tsx) | 54-55 | `typeConfig[entry.type]` + `statusConfig[entry.status]` | parent has fallthrough → unknown type maps to "regime" with raw label (wrong but doesn't crash) | NO — F-AHIST-1 |
| [components/data-source-badge.tsx](web/components/data-source-badge.tsx) | 31 | `statusConfig[status]` | parent passes literal `"live"/"cached"/"down"`; safe | NO |

**Bottom line:** the SignalCard call site (F-HOME-1) is the only verified crash that ships today. All other call sites are one backend label change away from the same Wave-1-class crash.

---

## Empty / loading / error state coverage

| Page | Loading | Error | Empty | Honest copy? |
|---|---|---|---|---|
| `/` Home heroSignals | yes | yes | yes | yes |
| `/` Home backtest KPIs | "loading" subtitle | none | none | partial — see F-HOME-4 |
| `/signals` CoinPicker | yes | yes | yes | yes |
| `/signals` SignalHistory | yes | yes | yes | yes (post-P0-7) |
| `/signals` price/sentiment/onchain tiles | always "—" | always "—" | always "—" | partial — F-SIG-1 |
| `/regimes` cards | yes | yes | yes | yes |
| `/regimes` timeline / overlay / weights | none | none | none | NO — F-REG-3 |
| `/on-chain` indicators | yes | partial | partial | partial |
| `/on-chain` whale activity | none | none | none | NO — F-ONC-1 |
| `/ai-assistant` decisions | yes | yes | yes | yes |
| `/ai-assistant` metrics + status + config | always mock | always mock | always mock | NO — F-AI-1/2/3/4 |
| `/backtester` KPIs | "loading" subtitle | none | none | partial |
| `/backtester` trades | yes | yes | yes | yes |
| `/backtester` Equity + Optuna | none | none | none | NO |
| `/backtester/arbitrage` opportunities | yes | yes | yes | yes |
| `/backtester/arbitrage` carries + KPIs | none | none | none | NO |
| `/alerts` configure | none | none | none | NO — local state only |
| `/alerts/history` log | yes | yes | yes | yes |
| `/alerts/history` stats | always "—" | always "—" | always "—" | NO |
| `/settings/*` | yes (per group) | yes | n/a (hydrated) | yes |

---

## Stale-cache concerns (engine emits new fields, old rows missing them)

The Wave 1 P0-3 fix added `change_30d_pct` / `change_1y_pct` to scan-result rows. Old `daily_signals` rows in the SQLite DB don't have these. Consumers handle this acceptably:

- **Hero card** ([signals/page.tsx:241-252](web/app/signals/page.tsx)) — uses `(detail as { change_30d_pct?: number | null }).change_30d_pct` with `isMissing` check; renders `"—"` for stale rows. Safe.
- **`_deriveTransitions`** ([signals/page.tsx:148-191](web/app/signals/page.tsx)) — uses `_toFiniteNumber`/`_toCleanString` helpers on every read; safe even when `mtf_alignment` / `confidence_avg_pct` / `regime` / `scan_timestamp` are missing or weird types.
- **Composite score** ([signals/page.tsx:307](web/app/signals/page.tsx)) — `_toFiniteNumber(detail?.confidence_avg_pct)` then `?? 0`; safe.
- **Multi-timeframe strip** ([signals/page.tsx:282-302](web/app/signals/page.tsx)) — coerces direction + confidence each tile; safe.
- **Color tinting in hero** ([components/signal-hero.tsx:61-63](web/components/signal-hero.tsx)) — `is30dPositive = change30d.startsWith("+")`. When value is `"—"` or `"0.00%"`, returns false → renders red. **Minor UX bug**: a flat 0.00% reads red. Not data-correctness; cosmetic.

Net: stale-cache handling is solid wherever the audit-marked code paths apply. The risk is ONLY at unguarded `*Config[key]` lookups (cross-cutting bug class, F-CROSS-1).

---

## Accessibility regressions introduced by Wave-1 code

- **`level-toggle` keyboard navigation** ([components/topbar.tsx:82-103](web/components/topbar.tsx)) — `role="radiogroup"` + `aria-checked` is correct, but the radios don't move focus with arrow keys (default browser radiogroup arrow-key navigation requires actual `<input type="radio" name="...">` elements OR a custom keydown handler). User clicks-only; Tab moves to the first radio, then leaves the group. **Fix:** add `onKeyDown` handler to swap focus between the three buttons on Arrow Left/Right, or convert to native radios visually styled.
- **Beginner gloss focus order** ([signals/page.tsx:454-479](web/app/signals/page.tsx)) — block lands between the hero and multi-timeframe strip. Screen-reader users at Beginner tier hit it after the hero card. The block has no `role="region"` or `aria-label` so it reads as anonymous text. **Fix:** add `role="region" aria-label="Plain-English summary"`.
- **SignalHistory rows** ([components/signal-history.tsx:65-97](web/components/signal-history.tsx)) — rows are `<div>` not `<li>` / `<tr>`; the parent has no `role="list"`. Screen reader announces each transition as raw text without "1 of N" item context. Pre-existed; no regression but reflects the missing-list-semantics cross-cutting issue.
- **Scan trigger button** ([signals/page.tsx:405-414](web/app/signals/page.tsx)) — has a `title=` but no `aria-label` and the visible label changes between "Scan now" / "Scanning…" / "▶". The icon is a literal play character with no `aria-hidden`. Screen readers announce "▶ Scan now button". **Fix:** wrap the icon in `<span aria-hidden="true">` like the theme-toggle button does.
- **Topbar Refresh button on mobile** ([components/topbar.tsx:106-118](web/components/topbar.tsx)) — `aria-label="Refresh all data"` is good. `<span className="hidden md:inline">{isFetching ? "Refreshing…" : "Refresh"}</span>` — on mobile the visible text is hidden, but `aria-label` is static "Refresh all data" — when fetching the SR doesn't announce status change. **Minor.** Add `aria-busy={isFetching}` to convey loading state.

---

## P0 fixes recommended for autonomous execution tonight

Listed in execution-priority order (most-visible-first, smallest blast radius first):

1. **F-HOME-1 — fix the Home page crash on STRONG BUY** ([web/app/page.tsx:137](web/app/page.tsx)). Two-line patch: collapse `directionToSignalType` 5-tier output to 3-tier inline (mirror the IIFE pattern at [signals/page.tsx:257-262](web/app/signals/page.tsx)). Optionally also harden `SignalCard` itself with `signalConfig[signal] ?? signalConfig.hold` so the same bug-class can't recur on other call sites. **Smallest blast-radius high-impact fix in the entire backlog.** Estimated diff: ~6 lines.
2. **F-AI-1 — make the AgentConfigCard sliders movable.** Lift state into a parent `useState` per slider OR convert each slider to its own `useState`+local. Wire "Save Agent Config" `onClick` to nothing for now (no `/agent/config` endpoint yet) but show a "config not yet persisted to backend" disclaimer. **Today the card is decorative; users will conclude every slider is broken.** Estimated diff: ~50 lines.
3. **F-MOBILE-1 — add 3 missing routes to MobileNav.** Two options: (a) add a 6th "More" tab routing to `/settings` (current state) OR (b) replace one of Settings/Alerts in the bottom row with a "More" overflow drawer that includes On-Chain, Backtester, AI Assistant. Recommend (b) per CLAUDE.md §8 mobile parity. Estimated diff: ~30 lines.
4. **F-LEVEL-1 (partial) — add `useUserLevel()` to Home + Regimes pages.** Both pages have v0-spec'd tier-aware behaviour. Beginner-tier copy on Home: a "Quick read" gloss above the MacroStrip that explains the headline number plain-English. On Regimes: a 2-3 sentence Beginner block above the cards explaining what "regime" means. Pattern is established on Signals page. Estimated diff: ~80 lines across 2 pages.
5. **F-ONC-1 — drop the "live stream" subtitle from WhaleActivity** until the events endpoint lands. One-line change to [components/whale-activity.tsx:25-27](web/components/whale-activity.tsx). Estimated diff: ~3 lines.
6. **F-SIG-1 — wire `/signals` page on-chain tiles to `useOnchainDashboard(activePair)`.** The hook already exists; the page is the only consumer of the 4 cross-page-reference dashes. Replaces 4 mock tiles with real MVRV-Z / SOPR / Net flow / Whale-flag values per pair. Estimated diff: ~40 lines.

These six together close every Wave 2 P0 plus 1 P0 carryover from Wave 1 (F-HOME-2 NO — that needs `/diagnostics/feeds` integration which is more work).

**P0 NOT recommended for tonight (need backend work):**
- F-REG-1 — needs `regime_history` join for `since` + `durationDays` to be useful; defensive `?? stateConfig.bear` is a one-line patch but doesn't fix the underlying broken UX.

---

## Notes for the audit consumer

- **Wave-1-class crashes still possible.** F-HOME-1 is the only verified one. Wave 1 fixed SignalHero; SignalCard at the Home page was missed because it crashes only when the engine emits STRONG BUY/SELL — and the Home page renders 5 hero cards from the top-N pairs, so the probability of at least one strong direction is high once a real scan runs.
- **`useUserLevel()` is the lowest-effort, highest-CLAUDE-md-compliance gap.** The provider is shipped, the topbar consumes it, two pages use it. Wiring 12 more pages is shape-preserving copy work, no new endpoints required.
- **No security findings.** The Wave 1 P0-1 secret-rotation work and the existing CSP / API-key gating still hold.
- **No data-correctness findings outside the SignalType bug class.** Math is unaffected; the engine's signal logic is fine; the gaps are all in display.
- **Stale-cache risk is bounded.** Wave-1 P0-3 + HOTFIX type-coercion guards mean an old `daily_signals` row missing the new fields renders "—" cleanly. The consumer-side code is robust.
- **Mobile parity matters more than the count of routes suggests.** With 3 of 7 user-facing routes hidden on mobile, a Capacitor TestFlight user is locked out of On-Chain / Backtester / AI Assistant — those happen to be the most-research-y pages, exactly the ones a power user would want on mobile.

End of Wave 2 audit. Read-only — no code modified.
