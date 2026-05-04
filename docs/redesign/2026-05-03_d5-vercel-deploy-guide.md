# D5 — Vercel Deploy Guide (paste-ready)

**Status:** ready to execute. D4 closed (commit `c846387`). `web/` is
production-buildable: `npm run build` → all 15 routes static-prerendered,
0 errors. Contract test against live FastAPI: green.

**Outcome of D5:** the Next.js frontend in `web/` ships to a Vercel URL.
Pulls live data from the Render FastAPI deploy via env-configured
`NEXT_PUBLIC_API_BASE`. Auth header `X-API-Key` attached to every
protected call.

**Time estimate:** 15-25 minutes of dashboard clicks.

---

## Pre-flight (already true)

- ✅ `phase-d/next-fastapi-cutover` branch pushed to GitHub
- ✅ `web/` directory exists at the repo root
- ✅ `web/package.json` declares Next.js 16 + Turbopack
- ✅ `web/.gitignore` excludes `node_modules`, `.next`, `package-lock.json`
- ✅ Render FastAPI deploy live: `https://crypto-signal-app-1fsi.onrender.com`
- ✅ `CRYPTO_SIGNAL_API_KEY` set in Render dashboard (the 43-char URL-safe
  key you wrote down on 2026-05-03 morning — same value goes into Vercel
  as `NEXT_PUBLIC_API_KEY` so the frontend can authenticate)

---

## Step 1 — Create the Vercel project

1. Go to **vercel.com/new**
2. Sign in with GitHub (use the `davidduraesdd1-blip` account)
3. Click **Import** next to `crypto-signal-app` in the repo list. If it
   doesn't show up, click **Adjust GitHub App Permissions** at the
   bottom and grant Vercel access to that repo.
4. On the **Configure Project** screen, set:
   - **Project Name:** `crypto-signal-app-web` (or whatever you prefer)
   - **Framework Preset:** Vercel should auto-detect **Next.js** ✅
   - **Root Directory:** click **Edit** → set to `web` (this is the
     critical one — Vercel needs to build from inside `web/`, not from
     the repo root)
   - **Build Command:** leave default `next build` ✅
   - **Output Directory:** leave default `.next` ✅
   - **Install Command:** Vercel detects `pnpm-lock.yaml` and runs
     `pnpm install` automatically — leave default ✅
5. **Don't click Deploy yet** — set env vars first (Step 2).

---

## Step 2 — Set environment variables (BEFORE first deploy)

On the **Configure Project** screen, expand **Environment Variables**
and add these two:

| Key | Value | Environments |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `https://crypto-signal-app-1fsi.onrender.com` | Production, Preview, Development |
| `NEXT_PUBLIC_API_KEY` | `DY0YUB3Z0qTClL5p59I49Lv-gb1zUw1r2FWzoJYFKhg` | Production, Preview, Development |

**Important:**
- The `NEXT_PUBLIC_*` prefix is required. Without it, Next.js won't
  expose the value to client-side code and every fetch will fail with
  `undefined` API base.
- Apply to all 3 environments so preview deploys work the same as
  production. Vercel's default selection is "Production" only — change
  it to all 3.
- The API key value matches what you set in Render (the same 43-char
  URL-safe base64 string).

**Known trade-off (D4 plan §2.4):** `NEXT_PUBLIC_API_KEY` ships in the
client bundle. Acceptable for the D4-D8 single-user window per master
plan §11. Real auth (NextAuth + JWT) lands post-D8.

---

## Step 3 — Deploy

1. Click **Deploy** at the bottom of the Configure Project screen
2. Vercel runs `pnpm install` then `next build` (~2-3 min for the first
   build; subsequent deploys take ~30-60s thanks to the build cache)
3. Build log live-streams. Watch for:
   - ✅ "Compiled successfully"
   - ✅ "Generating static pages (16/16)"
   - ✅ "Finished page optimization"
4. When deploy completes, Vercel shows the production URL — copy it.
   It'll be something like `https://crypto-signal-app-web-<hash>.vercel.app`
   (or the project name with a generated suffix).

---

## Step 4 — Smoke test the deploy

Open the production URL in a browser. Walk through these checks:

### Home page (`/`)
- [ ] Loads without errors (check browser dev console — no red, no 401/404)
- [ ] Hero cards show real BTC/ETH/SOL/XRP/BNB prices (not the v0 mock
      placeholders like "104,280")
- [ ] BacktestCard at the bottom shows real `/backtest/summary` numbers

### Signals page (`/signals`)
- [ ] Coin picker populated (top-N from `/signals`)
- [ ] Hero card shows real direction + confidence + regime for the
      selected pair
- [ ] "Scan now" button visible in the header
- [ ] Click "Scan now" → green banner "Scan started — results refresh
      automatically (~30-60s)" → wait → cards update with new data

### Regimes page (`/regimes`)
- [ ] 8-card grid populated from `/regimes/`
- [ ] Each card shows ticker / state / confidence

### On-Chain page (`/on-chain`)
- [ ] BTC/ETH/XRP cards show MVRV-Z + SOPR + Net flow + Whale activity
      values from `/onchain/dashboard`
- [ ] Status pill ("live" / "cached") reflects the actual `source` field

### Backtester (`/backtester` + `/backtester/arbitrage`)
- [ ] KPI strip populated with real numbers from `/backtest/summary`
- [ ] Recent trades table shows real rows from `/backtest/trades`
- [ ] Arbitrage tab loads (may show empty state if `/backtest/arbitrage`
      isn't implemented on FastAPI side — that's expected)

### AI Assistant (`/ai-assistant`)
- [ ] AGENT · RUNNING / STOPPED pill in topbar reflects real state
      (refreshes every 5s)
- [ ] Recent Decisions table shows live data from `/ai/decisions`
- [ ] Ask Claude box renders. Submitting (with valid pair / signal /
      confidence) returns a response (or "AI Assistant unavailable" if
      Anthropic key isn't set on Render — that's also expected for now)

### Settings · Dev Tools (`/settings/dev-tools`)
- [ ] 7-gate circuit breaker card populated from
      `/diagnostics/circuit-breakers`
- [ ] Header pill: green if all 7 are `_ok`, **yellow if any are
      `_unmeasured`** (per the P-19 honest-UI fix — gates 4 + 5 are
      `_unmeasured` by design)
- [ ] DB KPI strip (5 cells) shows real row counts from
      `/diagnostics/database`

### Settings · Trading (`/settings/trading`)
- [ ] Trading-pairs chip list populated from API
- [ ] Active timeframes pills reflect persisted state
- [ ] TA exchange dropdown shows current value
- [ ] Click "Save Trading Config" → green "Saved" banner
- [ ] Refresh page → values persist (proves the PUT round-tripped)

### Settings · Signal-Risk (`/settings/signal-risk`)
- [ ] Sliders show persisted values
- [ ] Adjust min_confidence_threshold slider, click Save → green banner
- [ ] Visual-only fields show TODO(D-ext) help text — that's expected

### Settings · Execution (`/settings/execution`)
- [ ] Live trading mode toggle shows persisted state
- [ ] OKX API key fields are disabled (they're now env-var-only — copy
      reads "set via OKX_API_KEY env var")
- [ ] Click "Test OKX Connection" → response shows inline (likely "OKX
      keys not configured" since you haven't set OKX_API_KEY in Render
      yet — that's expected)

### Topbar (every page)
- [ ] AGENT pill changes color/text every ~5s when state changes
- [ ] Click "Refresh" button → spinner animates → all on-page data
      re-fetches

---

## Step 5 — If smoke test surfaces issues

| Symptom | Likely cause | Fix |
|---|---|---|
| Every page shows "—" / loading state forever | `NEXT_PUBLIC_API_BASE` not set or wrong | Vercel dashboard → Settings → Environment Variables → confirm value matches Render URL exactly |
| 401 errors in dev console on every fetch | `NEXT_PUBLIC_API_KEY` mismatch with Render | Compare values byte-for-byte; redeploy after fixing |
| Build fails with "Cannot find module @/lib/api" | Root Directory not set to `web` | Vercel dashboard → Settings → General → Root Directory → set to `web`, redeploy |
| All routes 404 except `/` | Vercel didn't detect Next.js app router | Confirm `web/app/` directory exists with `layout.tsx` + `page.tsx`. Should auto-detect. |
| AGENT pill stuck on "—" | `/execute/status` 401 (auth header missing) or the route still references the old `/execution/status` path | The D4d drift fix already shipped — confirm `c846387` is in the deployed commit |

---

## Step 6 — Post-deploy follow-ups

1. **Add the Vercel URL to Render's CORS allowlist.** The FastAPI side
   has a tightened CORS regex from the audit (`api.py` AUDIT-2026-05-02
   HIGH fix #2): only owner-prefix `crypto-signal-app(-...)?.vercel.app`
   patterns are allowed. Your generated URL should match this; if not,
   update the regex.

2. **Set up auto-deploy on push.** Vercel does this by default — every
   push to `phase-d/next-fastapi-cutover` triggers a deploy. Production
   deploys come from the production branch (set in Settings → Git);
   leave it as `phase-d/next-fastapi-cutover` for now and switch to
   `main` after D8 cutover.

3. **Optional: custom domain.** If you want `signals.duraes.family` or
   similar, add it via Vercel Settings → Domains. Vercel handles the
   ACME cert auto-renewal. Skip for now if you're fine with the
   `*.vercel.app` URL.

---

## Step 7 — Tell me when D5 lands

Reply with the production URL (or "deploy live" + URL). I'll:
- Run the contract test against the new Vercel URL (proves end-to-end
  TS ↔ FastAPI contract still holds via the proxy)
- Open D6 (security + perf pass): npm audit, Lighthouse, bundle
  analyzer, manual walk through every page on both desktop + mobile
  viewports
- Open D7 (§22 regression diff paired with P4-C-6 + P5-LA-1+LA-4)
- Then D8 (cutover): merge phase-d → main, archive Streamlit (don't
  delete — 30-day fallback per master plan)

---

## Reference: env vars that need to be set across both platforms

| Var | Render (FastAPI) | Vercel (Next.js) | Local dev (.env.local) |
|---|---|---|---|
| `CRYPTO_SIGNAL_API_KEY` | ✅ set | — (different name) | ✅ uvicorn picks it up |
| `CRYPTO_SIGNAL_ALLOW_UNAUTH` | `false` | — | `true` for local-only |
| `NEXT_PUBLIC_API_BASE` | — | ✅ set in Step 2 | `http://localhost:8000` |
| `NEXT_PUBLIC_API_KEY` | — | ✅ set in Step 2 (same value as Render's CRYPTO_SIGNAL_API_KEY) | same |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_PASSPHRASE` | optional (live trading) | — | optional |
| `ANTHROPIC_API_KEY` | optional (Ask Claude) | — | optional |
| `ANTHROPIC_ENABLED` | `false` until you want LLM | — | same |
| `DEMO_MODE` | `true` | — | `true` |

---

## What's NEXT after D5 lands

| Stage | Owner | Effort |
|---|---|---|
| D6 — Security + perf pass | Claude | 1 day |
| D7 — §22 regression diff (paired with P4-C-6 + P5-LA-1/4) | Claude | 1 day |
| D8 — Cutover (merge to main, 30-day Streamlit overlap) | Claude + David | 0.5 day |

Plus the deferred D-extension endpoints for the still-mock UI surfaces
(MacroStrip, Watchlist sparklines, WhaleActivity, EquityCurve,
OptunaTable, FundingCarryTable, signal-history, AgentMetricStrip /
AgentConfigCard / EmergencyStopCard) — none block cutover, ship as
follow-up commits when the FastAPI endpoints land.
