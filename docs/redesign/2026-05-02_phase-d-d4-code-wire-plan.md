# D4 — Code-Wire Plan: Next.js Frontend → FastAPI Backend

**Date:** 2026-05-02
**Author:** Claude Code (Windows-side, full repo access)
**Branch:** `phase-d/next-fastapi-cutover` (continuation; D3 mockups land first)
**Inherits from:** `2026-05-02_phase-d-streamlit-retirement.md` (master plan §6, batch D4)
**Inherits from:** `2026-05-02_d1-api-audit.md` (endpoint inventory)

---

## TL;DR

D4 replaces the v0 mock data on every page with live FastAPI calls.
Stack: TanStack Query v5 + a typed `web/lib/api.ts` client + per-route
loaders + truthful empty states. No new components, no visual changes,
no backend changes (any endpoint additions land as a D-extension).

Estimated wall-clock: **1–2 days** of autonomous Code work after the
D3 v0 polish-pass commit lands. Single commit `feat(phase-d-4): wire
frontend to FastAPI`, no PR to main until D8.

---

## 1. Pre-conditions

D4 starts only after **all** of the following are true:

- D3 mockups committed to `phase-d/next-fastapi-cutover` (single push,
  per the D3 rule).
- v0 polish-pass committed on top of mockups (active-state colors
  swapped to `--accent-soft`; Streamlit secrets-path copy updated).
- `phase-d/next-fastapi-cutover` builds clean: `npm run build` exits 0,
  `npm run lint` exits 0.
- FastAPI live deploy reachable: `curl https://crypto-signal-app-1fsi.onrender.com/health` returns 200 (this URL set in D2).
- D1 + D2 commits already merged (already done — `c182444`, `834601f`,
  `4f924a7`).

If any of these is false, abort D4 and surface the blocker.

---

## 2. Library + pattern decisions

### Data fetching: TanStack Query v5

Locked. Already named in master plan §6 D4. Reasons that still hold:

- First-class Next.js 15 app-router support (server-side hydration via
  `HydrationBoundary` + `dehydrate`)
- `staleTime` + `gcTime` map directly onto §12 refresh windows
  (5min / 10min / 1h / 24h)
- Built-in dedup, retry, and request cancellation — no hand-rolled
  AbortController plumbing
- "Refresh All Data" button = `queryClient.invalidateQueries()` on the
  current route's query keys (master template §12 requirement)

Not chosen and why:
- **SWR** — simpler but lacks query-key invalidation patterns we need
  for the global refresh button
- **RTK Query** — Redux is overkill for our state shape
- **Plain fetch + useEffect** — would require re-implementing dedup +
  cache + retry + the refresh-all button by hand

### HTTP client: `fetch` + thin typed wrapper

No axios. Native `fetch` is sufficient and ships zero kB of extra JS.

`web/lib/api.ts` exposes one typed function per endpoint. Each function
returns a `Promise<T>` where `T` is derived from the FastAPI Pydantic
response model (see §4).

### Type generation: manual TS types from Pydantic

Two paths considered:

| Approach | Pros | Cons |
|---|---|---|
| **Manual TS types** mirrored from Pydantic models | Zero build-step coupling, instant feedback, easy to evolve | Drift risk between Python and TS |
| `openapi-typescript` codegen from `/openapi.json` | Single source of truth | Adds codegen step + churn on every endpoint change; brittle on FastAPI's auto-generated schema names |

**Chosen: manual TS types** in `web/lib/api-types.ts`. Drift risk
is mitigated by:
1. A contract test in `web/tests/api-contract.test.ts` that fetches
   `/openapi.json` from the deployed API and asserts our type names
   exist in `components.schemas`.
2. Every TS type carries a `// @endpoint <route>` JSDoc comment so
   grep finds the consumer when the Pydantic model changes.

If drift becomes painful (>1 false-positive bug in a sprint),
revisit codegen.

### Auth: none in D4

D1 already wired `require_api_key` for mutations. The frontend will
read the key from `NEXT_PUBLIC_API_KEY` (we accept the trade-off that
this is exposed to clients — there's only David accessing the app
in D4-D8 window; real auth comes post-D8).

For D4: every fetch attaches `X-API-Key: <process.env.NEXT_PUBLIC_API_KEY>`
on routes that require it (mutations + protected GETs per the
endpoint reference table).

### State outside fetches: React state + URL search params

- Filter state (date range, type/status filters on /alerts/history,
  pair picker on /signals) lives in `useState` + URL search params.
  No client store.
- User level (Beginner / Intermediate / Advanced) and theme persist
  in `localStorage`, hydrated in a top-level `<AppProviders>` wrapper.

---

## 3. Endpoint → page binding map

Every page from the 13 mockups gets a fetch wiring. Source: D1 audit
inventory + 6 new D1 routers + the live deploy's 14-endpoint reference
already rendered in `/settings/dev-tools`.

| Page (route) | Primary fetch | Secondary fetches | §12 staleTime |
|---|---|---|---|
| Home (`/`) | `GET /home/summary` | `GET /signals` (top strip) | 5 min |
| Signals (`/signals`) | `GET /signals` | `GET /signals/{pair}`, `GET /signals/{pair}/timeframes`, `GET /signals/{pair}/indicators` (on row select) | 5 min |
| Regimes (`/regimes`) | `GET /regimes` | `GET /regimes/{pair}/history`, `GET /regimes/transitions` | 15 min |
| Backtester (`/backtester`) | `GET /backtest/summary` | `GET /backtest/trades?limit=&offset=`, `GET /backtest/runs` | 1 h |
| Backtester · Arbitrage (`/backtester/arbitrage`) | `GET /backtest/arbitrage` | — | 1 h |
| On-Chain (`/on-chain`) | `GET /onchain/dashboard` | `GET /onchain/{metric}` per tile drill-down | 1 h |
| Alerts · Configure (`/alerts/configure`) | `GET /alerts/configure` | `POST /alerts/configure`, `DELETE /alerts/configure/{id}` | mutations only |
| Alerts · History (`/alerts/history`) | `GET /alerts/log?limit=&offset=` | — | 5 min |
| AI Assistant (`/ai-assistant`) | `GET /ai/decisions` | `GET /execution/status` (cycle counter), `POST /ai/ask` | 1 min for decisions; 5 s for status |
| Settings · Trading (`/settings/trading`) | `GET /settings` (single-shape) | `PUT /settings/trading` | mutations only |
| Settings · Signal & Risk (`/settings/signal-risk`) | `GET /settings` | `PUT /settings/signal-risk` | mutations only |
| Settings · Dev Tools (`/settings/dev-tools`) | `GET /settings`, `GET /health`, `GET /scan/status` | (none — dev tools are operator actions) | 5 min for health |
| Settings · Execution (`/settings/execution`) | `GET /settings` | `PUT /settings/execution`, `POST /exchange/test-connection` | mutations only |
| Topbar (global) | `GET /execution/status` polled | — | 5 s (the AGENT pill) |

### Endpoint gaps surfaced during this mapping

These were not in the D1 audit but are needed by the D3 mockups.
**Do not add in D4.** Capture as a D-extension batch:

1. `PUT /settings/trading` — Trading tab persistence (only `signal-risk`
   / `dev-tools` / `execution` were named in D1)
2. `POST /exchange/test-connection` — "Test OKX Connection" button
3. `GET /circuit-breakers` — the 7-gate status read on Dev Tools (could
   be folded into `/health` enhancement)
4. `GET /db-health` — 5-col KPI strip on Dev Tools (could be folded
   into `/health` enhancement)

D4 stubs these with optimistic mock-only behavior (button shows toast,
no real persistence) and adds `// TODO(D-ext): wire <endpoint>`
comments at the call sites. None of them block the cutover.

---

## 4. File layout in `web/`

```
web/
├── app/
│   ├── layout.tsx                # AppProviders + AppShell
│   ├── page.tsx                  # Home
│   ├── signals/page.tsx
│   ├── regimes/page.tsx
│   ├── backtester/
│   │   ├── page.tsx
│   │   └── arbitrage/page.tsx
│   ├── on-chain/page.tsx
│   ├── alerts/
│   │   ├── configure/page.tsx
│   │   └── history/page.tsx
│   ├── ai-assistant/page.tsx
│   └── settings/
│       ├── layout.tsx            # shared tab nav
│       ├── trading/page.tsx
│       ├── signal-risk/page.tsx
│       ├── dev-tools/page.tsx
│       └── execution/page.tsx
├── components/                   # v0 output (untouched in D4)
├── lib/
│   ├── api.ts                    # NEW — typed fetch functions
│   ├── api-types.ts              # NEW — TS types mirroring Pydantic
│   ├── query-client.ts           # NEW — TanStack Query setup + defaults
│   └── query-keys.ts             # NEW — central query key factory
├── providers/
│   ├── query-provider.tsx        # NEW — <QueryClientProvider>
│   └── app-providers.tsx         # NEW — composes Query + Theme + Level
├── hooks/                        # NEW — one hook per page section
│   ├── use-home-summary.ts
│   ├── use-signals.ts
│   ├── use-signal-detail.ts
│   ├── use-regimes.ts
│   ├── use-backtest-summary.ts
│   ├── use-backtest-trades.ts
│   ├── use-onchain-dashboard.ts
│   ├── use-alerts-config.ts
│   ├── use-alerts-history.ts
│   ├── use-ai-decisions.ts
│   ├── use-execution-status.ts   # global, drives AGENT pill
│   └── use-settings.ts
└── tests/
    ├── api-contract.test.ts      # NEW — guard Pydantic↔TS drift
    └── hooks.test.ts             # NEW — minimum-viable hook tests
```

Every page imports its own hook(s) and renders. No fetch logic in
page components. No fetch logic in v0 components.

---

## 5. Caching + revalidation strategy

§12 of the master template defines the canonical refresh windows.
Map directly onto TanStack Query `staleTime`:

| Data class | §12 window | TanStack `staleTime` | TanStack `gcTime` |
|---|---|---|---|
| OHLCV intraday | 5 min | `5 * 60 * 1000` | `10 * 60 * 1000` |
| Fear & Greed | 24 h | `24 * 60 * 60 * 1000` | `48 * 60 * 60 * 1000` |
| Funding rates | 10 min | `10 * 60 * 1000` | `30 * 60 * 1000` |
| On-chain metrics | 1 h | `60 * 60 * 1000` | `2 * 60 * 60 * 1000` |
| Regime detection | 15 min | `15 * 60 * 1000` | `30 * 60 * 1000` |
| Composite signal | 5 min | `5 * 60 * 1000` | `15 * 60 * 1000` |
| Execution status (AGENT pill) | live | `5 * 1000` | `30 * 1000` |
| Alerts log | 5 min | `5 * 60 * 1000` | `15 * 60 * 1000` |
| Backtest summary/trades | 1 h | `60 * 60 * 1000` | `2 * 60 * 60 * 1000` |
| Settings (full read) | session | `Infinity` (manual invalidate on mutation) | `Infinity` |

`gcTime` ≈ 2× `staleTime` keeps cache warm long enough for back-nav
without being wasteful.

### Refresh All Data button

§12 master template: every page has a visible "Refresh All Data"
button that **bypasses all caches**. Implementation:

```ts
// in <Topbar>
const queryClient = useQueryClient()
const onRefreshAll = () => {
  queryClient.invalidateQueries()           // stale-mark everything
  queryClient.refetchQueries({ type: 'active' }) // force-refetch on-page
}
```

Add a 1.2s spinner on the button while `isFetching` from
`useIsFetching()` > 0.

---

## 6. Loading / error / empty state patterns

Per `feedback_empty_states.md` memory: **truthful labels, no silent
"None" or "—".**

### Loading

Each card section has an existing skeleton variant in the v0 output
(skeleton bars matching the final layout shape). Use it. Never show a
blank panel during fetch.

### Error

Three error categories, each with a distinct UI:

| Category | Detection | Copy | Action |
|---|---|---|---|
| **Geo-blocked** | 403 + body matches `/binance.*us|geo/i` | "Provider geo-blocked from this region — using fallback data" | Auto-fallback chain attempt; show muted footer note |
| **Rate-limited** | 429 OR body matches `/rate.?limit|too.?many/i` | "Rate-limited by upstream — showing cache from N min ago" | Display stale data with timestamp; retry button |
| **Generic** | Anything else | "Couldn't load this — try refreshing in 30 seconds" | Retry button; no stack trace |

User-level scaling per §8: Beginner sees the most reassuring copy;
Advanced sees the actual HTTP status + endpoint path in a collapsible
"Details" line.

### Empty

If a query succeeds but returns `[]` or zero meaningful state:
- "Run a scan to populate" (Signals on first load)
- "No alerts in the last 7d" (Alerts History)
- "No trades on this strategy yet" (Backtester)

Never silent "—" or empty grid. The mockups already render these
strings — we just wire them to the empty-array branch instead of mock
hard-coding.

---

## 7. Environment configuration

### Local dev (`.env.local`, gitignored)

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_API_KEY=<dev-key-matching-api-py-DEV_API_KEY>
```

### Vercel preview / production (set via dashboard)

```
NEXT_PUBLIC_API_BASE=https://crypto-signal-app-1fsi.onrender.com
NEXT_PUBLIC_API_KEY=<prod-key-matching-Render-env>
```

### `.env.example` (committed, no secrets)

Updated to add the two `NEXT_PUBLIC_*` variables. README reference
unchanged otherwise.

D5 polish-pass copy fix on `/settings/execution` lands these names in
the on-page security callout (replacing the legacy
`.streamlit/secrets.toml` reference).

---

## 8. Sub-phase breakdown (D4a → D4d)

Each sub-phase is one push to `phase-d/next-fastapi-cutover`. No PR
intermediate. All 4 close out as one D4 commit at the end.

### D4a · Plumbing (~2 hours)
- Install `@tanstack/react-query` + `@tanstack/react-query-devtools`
- Create `web/lib/{query-client,query-keys,api,api-types}.ts`
- Create `<QueryProvider>` and wire into `app/layout.tsx`
- Add `.env.local`, update `.env.example`, update `README.md` env section
- Verify `npm run build` clean

### D4b · Read-side wiring (~4–6 hours)
- One hook per page section (~12 hooks)
- Replace mock data on every page with hook output
- Wire loading skeletons + error states + empty-state strings
- Wire global "Refresh All Data" button on the Topbar
- Wire AGENT · RUNNING pill polling

### D4c · Mutations (~2–3 hours)
- `POST /alerts/configure` (Alerts Configure tab — save rule)
- `DELETE /alerts/configure/{id}` (delete a rule row)
- `PUT /settings/{tab}` × 4 tabs (Save Trading/Signal-Risk/Dev-Tools/Execution Config)
- `POST /ai/ask` (AI Assistant ask box, if rendered)
- `POST /scan/trigger` (Refresh All Data also calls scan/trigger when
  on Signals page, per §12 spirit)
- Toast on success + invalidate relevant queries
- Optimistic UI for toggle controls (Dry Run mode, auto-execute,
  Live Trading mode banner)

### D4d · Test + verify (~2 hours)
- `web/tests/api-contract.test.ts` — drift guard
- `web/tests/hooks.test.ts` — at minimum: each hook's success path
  via MSW (Mock Service Worker) + happy-path integration test
- Manual walk: every page loads, every chart renders, every error
  state displays the right copy when API is killed
- Lighthouse on local build: target 90+ Performance / 100 A11y
  (formal Lighthouse runs in D6; D4 just sanity)
- Update `MEMORY.md` with the D4 wrap-up entry

### Final commit
```
feat(phase-d-4): wire Next.js frontend to FastAPI

- TanStack Query v5 + typed lib/api.ts client
- 12 hooks, one per page section
- §12 cache windows mapped to staleTime/gcTime
- Truthful empty-state labels per feedback_empty_states memory
- Refresh All Data button invalidates + refetches active queries
- AGENT · RUNNING pill polls /execution/status every 5s
- 4 endpoint gaps stubbed with TODO(D-ext) for follow-up batch
- contract test + minimum-viable hook tests pass

Closes D4 in phase-d plan.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## 9. Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| TanStack Query v5 SSR hydration mismatch with Next.js 15 app router | Low | Medium | Use the canonical `<HydrationBoundary>` pattern from TanStack docs; avoid prefetch-on-server for D4 (client-only fetching keeps the surface small) |
| Pydantic ↔ TS type drift breaks runtime | Medium | Medium | Contract test (§4) + JSDoc `@endpoint` comments at every type def for grep |
| Render cold-start (~30s) yields jarring first-paint | High on first hit | Low | Cron-job.org keep-alive (D2c) keeps it warm; first-load skeleton handles the rare cold case |
| 4 missing endpoints (§3 gaps) block UX flows | Medium | Low | Stub with toast-only behavior; `TODO(D-ext)` comment; user can still see + read every page |
| `NEXT_PUBLIC_API_KEY` exposure in client bundle | Known accepted | Low for D4 audience (David only) | Documented as known trade-off; real auth in post-D8 ticket per master plan §11 |
| TanStack Query bundle adds ~13kB gzipped | Known | Low | Already in master plan §6 D4; under Lighthouse budget |

---

## 10. §4 regression — NOT in D4

Per master plan §6: §4 regression diff happens at **D7 only**, not
per-batch. D4 is a presentation/transport-layer change; the engine
(`composite_signal.compute_composite_signal`) is untouched.

If any D4 wiring accidentally transforms a numeric value (rounding,
locale formatting, sub-score truncation), it shows up as a category
flip in D7 and gets fixed there. D4 itself only renders what FastAPI
returns — no derived computation in TS.

---

## 11. Out of scope (post-D4)

- Real auth (NextAuth + JWT) — post-D8 ticket per master plan §11
- WebSocket live streams — TanStack polling at 5s/5min sufficient
- Background job control panel (start/stop scheduler) — post-D8
- 4 missing endpoints from §3 gaps — D-extension batch
- Custom domain — post-D8
- Sibling apps (`flare-defi-model`, `rwa-infinity-model`,
  `etf-advisor-platform`) — Phase E onward, after D8 lands

---

## 12. Hand-off contract

When this plan executes:

- Read `CLAUDE.md`, `MEMORY.md`, this doc, the master plan
  (`2026-05-02_phase-d-streamlit-retirement.md`), and the D1 audit
  (`2026-05-02_d1-api-audit.md`) before touching any file
- Branch is already `phase-d/next-fastapi-cutover` — do not branch
  off main
- Single commit at end per master plan rule
- Append a one-line `MEMORY.md` entry under "## 2026-05-XX — Phase D
  D4 landed" once shipped (master plan §6 communication)
- Do not push to main; D8 handles that
- Do not touch `app.py`, `ui/`, or any Streamlit module — they stay
  intact for the 30-day fallback overlap
- §4 regression deferred to D7
