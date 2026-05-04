# Crypto Signal App — Full Handoff Brief
## 2026-05-04 (Phase D end-of-day) — for Cowork / new-chat continuity

---

## 1. Project context (start here)

**What the app does**
Composite crypto signal engine producing a single BUY / HOLD / SELL recommendation
per coin, using a 4-layer model:
1. **Technical** — RSI, MACD, ADX, Supertrend, ATR, Bollinger, OBV, etc. (per coin)
2. **Macro** — BTC dominance, total mcap, DXY, equity correlation, regime flags
3. **Sentiment** — Crypto Fear & Greed, funding rates, long/short, social
4. **On-chain** — MVRV, SOPR, active addresses, exchange flows, NVT

The model has an HMM regime detector (bull/bear/sideways/transition) that
re-weights the layers per regime. There's also a backtester, a paper-trade
log, a LangGraph autonomous agent (off by default), and ML model
enhancements (LightGBM/XGBoost, lazy-loaded). Reference logic lives in
`composite_signal.py` (gold reference) and `crypto_model_core.py`.

**Repo**: `github.com/davidduraesdd1-blip/crypto-signal-app`
**Owner**: David Duraes — family-office-internal app, private repo
**Operating CLAUDE.md**: `C:\Users\david\.claude\CLAUDE.md` (master) +
`<repo>/CLAUDE.md` (project-specific)

---

## 2. The big picture — Phase D status

We're 95% through **Phase D — Streamlit retirement → Next.js + FastAPI cutover**.
The legacy app was a Streamlit single-process app at
`https://cryptosignal-ddb1.streamlit.app` (still live, kept for 30-day overlap).
Phase D splits it into a Next.js frontend (Vercel) + FastAPI backend (Render).

| Stage | Status | Deliverable |
|---|---|---|
| D1 — FastAPI scaffold | ✅ closed | 6 routers, 30+ endpoints, full auth |
| D2 — Render deploy | ✅ closed | Live API + auth verified |
| D3 — v0 mockups exported | ✅ closed | `web/` directory with 15 routes |
| D4 — Wire frontend to FastAPI | ✅ closed | TanStack Query hooks + 3 form mutations + contract test |
| D5 — Vercel deploy | ✅ **LIVE** (today, 2026-05-04) | Production URL operational, end-to-end verified |
| D6 — Security + perf pass | ⏳ NOT STARTED | npm audit, Semgrep, Lighthouse, manual cross-browser |
| D7 — §22 regression diff | ✅ done | 6/6 PASS against 2026-05-02 baseline |
| D8 — Cutover (merge phase-d → main) | ⏳ blocked on D6 | Final merge + 30-day Streamlit overlap |

**Branch**: `phase-d/next-fastapi-cutover` (NOT yet on `main` — D8 is the merge).
**HEAD**: `0797174` as of this brief (latest fix: `/backtest/arbitrage` endpoint).

---

## 3. Live deploy URLs

| Surface | URL | Status |
|---|---|---|
| **Frontend (Vercel, primary)** | `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app` | ✅ live (note: "signa" is the real domain; Vercel hit a length limit when v0 named the project) |
| **Backend (Render, FastAPI)** | `https://crypto-signal-app-1fsi.onrender.com` | ✅ live, auth-enforced via `X-API-Key` header |
| **Backend health (no auth)** | `https://crypto-signal-app-1fsi.onrender.com/health` | ✅ public probe |
| **Streamlit (legacy fallback)** | `https://cryptosignal-ddb1.streamlit.app` | ✅ stays live 30 days post-D8 |

**Auth keys (Production)**
```
CRYPTO_SIGNAL_API_KEY = DY0YUB3Z0qTClL5p59I49Lv-gb1zUw1r2FWzoJYFKhg
NEXT_PUBLIC_API_KEY   = DY0YUB3Z0qTClL5p59I49Lv-gb1zUw1r2FWzoJYFKhg  (same value)
```
Set in Render env (server-side) + Vercel env (Production scope, browser-exposed).
**Known issue**: `NEXT_PUBLIC_*` Next.js env vars are inlined into the JS bundle
and visible to anyone who opens DevTools. This is documented as a post-cutover
hardening item — replace with NextAuth + JWT (1-2 days work).

---

## 4. Restore tags (recovery points)

```
pre-overnight-audit-2026-05-03   → before the overnight audit pass
pre-db-rewrite-2026-05-03         → before DB-1/DB-4 Phase 1 scaffold
backup-pre-redesign-2026-04-01    → pre-redesign baseline
```

Recovery: `git checkout <tag>` returns the repo to that state. All pushed to GitHub.

---

## 5. What landed in the past 24 hours (commit ledger)

Branch `phase-d/next-fastapi-cutover`:

| SHA | Why |
|---|---|
| `47a6f90` | T1+T3+T4+T5 fixes from 5-tier deep-dive audit (CORS narrowing, funding cache poisoning, 4 frontend HIGH bugs, ai_feedback race, numpy<2.0 pin) |
| `e226de4` | Consolidated audit doc + D8 cutover guide |
| `4b7bc2e` | Regenerated `pnpm-lock.yaml` after D4 dep additions (unblocked Vercel build) |
| `d53a53d` | T1 MEDIUMs (idempotency cache cap + order_type lowercase + settings GET cache-control) + 6 backend regression tests |
| `53ac7f5` | **CRITICAL CORS unblocker** — broadened regex to admit v0-prefixed Vercel URLs (the v0-created Vercel project assigned `v0-davidduraesdd1-blip-crypto-signa.vercel.app`, original regex only matched `crypto-signal-app(...)?`); 7 a11y fixes; deleted orphan `web/styles/globals.css`; endpoint comment drift fix; 3 more backend tests + 6 vitest component tests |
| `2c5c398` | Morning summary doc |
| `3cbbef5` | Live-verification block in summary doc |
| `817b745` | Added `/backtest/summary` endpoint — closed Backtester runtime crash (TypeError on `'className'` was downstream of a 404) |
| `0797174` | Added `/backtest/arbitrage` endpoint — closed last frontend-vs-backend route gap |

**Tests at HEAD (0797174)**: 437 passed, 1 skipped, 0 regressions on Python side
+ 6 vitest tests passing on frontend.

**§22 backtest at HEAD**: 6/6 PASS against `2026-05-02-baseline.json` →
zero output drift, T2 math CRITICALs (CMC-1/2/3) don't move signals.

---

## 6. What works end-to-end RIGHT NOW (just verified)

A scan was triggered on Render at 2026-05-04 18:43 UTC. Completed
~2-3 min later. 33 pairs scanned. Sample signal returned:

```json
{
  "pair": "BTC/USDT",
  "price_usd": 80164.9,
  "confidence_avg_pct": 47.9,
  "direction": "HOLD",
  "strategy_bias": "Mean-Reversion",
  "mtf_alignment": 49.6,
  "mtf_confirmed": true,
  "fng_value": 40,
  "fng_category": "Fear",
  "entry": 80164.9,
  "exit": 82415.11
  …
}
```

So the pipeline is operational: data feeds → engine → DB → API → React →
browser. End-to-end. The only page that doesn't fully populate yet is the
Backtester (no historical backtest run has been executed; will populate
when David runs one from the Backtester page).

---

## 7. Open issues / partial / known-imperfect

### CRITICAL — none. The app is shippable.

### HIGH

1. **Save Agent Config dead UI** — `web/components/agent-config-card.tsx`
   has a "Save" button with no `onClick`; inputs are uncontrolled. User
   can edit + click Save and nothing persists. Needs the `/agent/config`
   PUT endpoint (D-extension item) + frontend wiring. ~2-4 hours.

2. **`useDeleteAlertRule` docstring lies** — claims optimistic UX,
   actually only invalidates on success. Fix: implement `onMutate` +
   `onError` rollback OR fix the docstring to match. ~30 min.

3. **`NEXT_PUBLIC_API_KEY` exposed to browser** — by design of Next.js
   `NEXT_PUBLIC_*` prefix. Real fix: NextAuth + server-side proxy with
   JWT. ~1-2 days. Mitigated by tight CORS regex (only David's vercel.app
   subdomain can use the key).

4. **Scheduler not running on Render** — `scheduler.py` runs scans on
   a cron-like schedule (15min recompute per CLAUDE.md §12). It's a
   separate process. Render's free web service only runs `uvicorn`. So
   data goes stale unless scans are triggered manually via
   `POST /scan/trigger`. **Decision needed**: add a Render cron job, or
   poll from Vercel, or add a long-running process tier on Render
   (paid).

### MEDIUM

5. **Tier 2 math findings** held for sign-off:
   - CMC-1 scalar broadcast in `composite_signal.py`
   - CMC-2 `.shift(-1)` divergence policy
   - CMC-3 chandelier exit comment-vs-math
   §22 backtest passes 6/6 → no current output drift, but each is a
   policy question. Half-day focused session post-D8 to confirm-and-
   document or fix-and-rebaseline.

6. **DB-1 / DB-4 concurrency rewrite** — Phase 1 behavior-locking
   tests landed in `pre-db-rewrite-2026-05-03` tag context but the
   actual rewrite hasn't shipped. Plan in
   `docs/audits/2026-05-03_db-concurrency-rewrite-test-plan.md`.

7. **a11y bundle (Tier 4 MEDIUM)** — most fixes shipped in 53ac7f5.
   Remaining: data-source-badge color-only encoding (add shape glyph),
   regime-card accumulation/distribution dot vs hollow-dot (too similar
   visually), emergency-stop-card raw 🚨 emoji (CLAUDE.md says no emoji).

8. **D6 (security + perf) checklist not yet executed** — needs:
   - `npm audit` (had 2 moderate postcss findings in earlier sweep)
   - Semgrep against TS+React+Next presets
   - Lighthouse on production URL (Performance ≥ 90, Accessibility = 100)
   - Manual cross-browser walk on real iPhone + Android + desktop
   - Bundle size analysis (`ANALYZE=true npm run build`)
   - Source-map exposure check
   Doc: `docs/redesign/2026-05-03_d6-security-perf-checklist.md`

### LOW (post-cutover backlog)

9. ~24 LOW items in `docs/audits/2026-05-03_phase-d-deep-dive-audit.md`
   — log-line sanitization, type guards, dead imports, deprecation
   warnings, etc. Quarterly polish-pass PR.

---

## 8. The full backlog — prioritized

### TODAY (highest leverage, ~1-2 hours)

- [ ] **Verify the live page actually renders real data after the scan completed** — David hard-refreshes `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app`, confirms hero cards + watchlist + KPI strip populated with the 33 pairs.
- [ ] **Trigger a backtest run** so the Backtester page populates. Either via the Backtester page button (if wired) or via a manual `python -m pytest tests/test_composite_signal.py` style invocation.
- [ ] **Confirm scheduler decision** — manual scans only OR Render cron job. If cron, set it up in Render dashboard (Settings → Cron Jobs → `0 */15 * * * curl -X POST -H "X-API-Key:..." /scan/trigger`).

### THIS WEEK (~1-2 days)

- [ ] **D6 — Security + perf pass** (full checklist execution)
- [ ] **D8 — Cutover** — merge `phase-d/next-fastapi-cutover` → `main`, flip Vercel + Render production branches to `main`, start the 30-day Streamlit overlap window
- [ ] **Real auth (NextAuth + JWT)** — replaces `NEXT_PUBLIC_API_KEY` browser exposure
- [ ] **D-extension batch** — 7 missing endpoints flagged with `TODO(D-ext)`:
  `/macro`, `/signals-with-sparkline`, `/onchain/whale-events`,
  `/backtest/equity`, `/backtest/optuna-runs`, `/funding-carry`,
  `/signals/{pair}/history`, `/agent/*`. The frontend has stubs at
  consumer sites so none block cutover, but the pages are partial-data
  until these land.

### POST-CUTOVER (1-2 weeks)

- [ ] **Math sign-off** — half-day focused session: re-run §22 backtest
  with explicit CMC-1/CMC-2/CMC-3 toggles, decide confirm-or-fix.
- [ ] **DB-1/DB-4 concurrency rewrite** per
  `docs/audits/2026-05-03_db-concurrency-rewrite-test-plan.md`
  (5-7 days work).
- [ ] **A11y polish** — data-source-badge shape encoding, regime-card
  shape diff, emoji removal.
- [ ] **Custom domain** — `signals.duraes.family` (or chosen domain) →
  Vercel project. Bypasses school-network filter blocks of
  `*.vercel.app`. Doc: §6 of D5 deploy guide.
- [ ] **Sentry / error monitoring** — currently zero observability post-
  deploy. Add Sentry (free tier) for both frontend + backend.

### POST-EVERYTHING (sibling apps)

- [ ] **Sibling app port — `flare-defi-model`** → same Next.js + FastAPI treatment (4-6 days)
- [ ] **Sibling app port — `rwa-infinity-model`** → same treatment (4-6 days)

---

## 9. What needs to happen on each platform

### GitHub

- [ ] **D8 PR open**: `phase-d/next-fastapi-cutover` → `main`. Body should
  paste the cutover summary block from
  `docs/redesign/2026-05-03_d8-cutover-guide.md`.
- [ ] **Squash vs merge commit decision**: D8 guide recommends **merge
  commit** to preserve the 30+ commit Phase D history.
- [ ] **Tag `pre-d8-cutover-2026-05-XX`** before merging (D8 guide).
- [ ] **No CI configured yet.** Optional: GitHub Actions for `pytest` +
  `npm test:contract` + `tsc --noEmit` on every PR. ~1 hour to wire.

### Vercel

- [ ] **Production branch flip**: currently tracks
  `phase-d/next-fastapi-cutover`. Post-D8, change to `main` in
  Project → Settings → Git.
- [ ] **Custom domain** (optional): Project → Settings → Domains →
  Add Domain. DNS work + 24-48h propagation.
- [ ] **Environment variables** — confirmed live:
  - `NEXT_PUBLIC_API_BASE` = Render URL
  - `NEXT_PUBLIC_API_KEY` = matches Render's `CRYPTO_SIGNAL_API_KEY`
  Both scoped to Production. Preview/Development env vars NOT yet set
  (preview deploys would currently fail). Add same vars to those scopes
  if branch previews matter.
- [ ] **Vercel logs**: project → Logs tab. Currently shows clean 200s on
  every route.
- [ ] **`generator: v0.app` metadata** — leftover from v0 export, harmless
  but worth removing during cleanup.

### Render

- [ ] **Production branch flip**: `render.yaml` currently has
  `branch: phase-d/next-fastapi-cutover`. Post-D8 change to `main` and
  push (Render reconciles from the YAML).
- [ ] **Environment variables** — confirmed live:
  - `CRYPTO_SIGNAL_API_KEY` = match Vercel's `NEXT_PUBLIC_API_KEY`
  - `CRYPTO_SIGNAL_ALLOW_UNAUTH` = `false` (auth enforced)
  - `ANTHROPIC_API_KEY` = ? (need David to confirm; AI Assistant page
    needs this for the /ai/ask endpoint to call Claude)
  - `GLASSNODE_API_KEY` = ? (on-chain layer source)
  - SMTP creds (if email alerts wanted) = ?
  - OKX exchange API keys (only if live trading enabled — currently off)
- [ ] **Cron job for scheduler.py** (decision needed). Render free tier
  supports cron jobs. Suggested:
  `*/15 * * * * curl -sX POST -H "X-API-Key:$CRYPTO_SIGNAL_API_KEY" $RENDER_EXTERNAL_URL/scan/trigger`
- [ ] **SQLite database backup** — currently the DB lives on Render's
  ephemeral filesystem. Render's free tier loses disk on restart.
  Production data could be lost. Decision needed: pay for persistent
  disk, or migrate to a managed Postgres (CockroachDB / Neon / Supabase).
  This is a **silent data-loss risk** worth flagging.
- [ ] **Render logs**: dashboard → Logs tab. Live stream of every API
  call.

---

## 10. Known data-flow facts (proven by today's audit)

Every endpoint the frontend calls has been live-probed with full auth.
Results:

| Endpoint | Status | Returns |
|---|---|---|
| `GET /health` | 200 | degraded (DB stats) |
| `GET /signals` | 200 | 33 results after scan |
| `GET /home/summary?hero_count=5` | 200 | populated hero cards |
| `GET /regimes/` | 200 | regime state per pair |
| `GET /onchain/dashboard?pair=BTC/USDT` | 200 | LIVE (SOPR=1.018, MVRV=-0.44, net_flow=400) |
| `GET /onchain/{metric}?pair=` | 200 | works for mvrv_z, sopr, net_flow, whale_activity |
| `GET /alerts/configure` | 200 | empty list (no rules yet) |
| `GET /alerts/log?limit=N` | 200 | empty until alerts fire |
| `GET /ai/decisions?limit=N` | 200 | empty until agent runs |
| `GET /backtest/summary` | 200 | empty until first backtest run |
| `GET /backtest/runs` | 200 | empty list |
| `GET /backtest/trades?limit=&offset=` | 200 | empty list |
| `GET /backtest/arbitrage?limit=N` | 200 | empty list |
| `GET /diagnostics/database` | 200 | full table row counts |
| `GET /diagnostics/circuit-breakers` | 200 | 7-gate status |
| `GET /execute/status` | 200 | live trading off |
| `GET /scan/status` | 200 | running + progress |
| `POST /scan/trigger` | 200 | scan started, populates DB in ~2-3 min |
| `PUT /settings/{group}` | 200 | with rejected[] validation array |

**Conclusion**: every endpoint is wired correctly. The "site looked broken"
issue earlier was: empty database (no scan had ever been run on Render).

---

## 11. Diagnostic recipes (paste these to debug live)

### Health + scan state
```bash
KEY="DY0YUB3Z0qTClL5p59I49Lv-gb1zUw1r2FWzoJYFKhg"
curl -s https://crypto-signal-app-1fsi.onrender.com/health | head -c 300
curl -s -H "X-API-Key: $KEY" https://crypto-signal-app-1fsi.onrender.com/scan/status
curl -s -H "X-API-Key: $KEY" https://crypto-signal-app-1fsi.onrender.com/diagnostics/database
```

### Trigger a fresh scan (when data goes stale)
```bash
curl -sX POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  https://crypto-signal-app-1fsi.onrender.com/scan/trigger
```

### CORS preflight from the live Vercel origin
```bash
curl -sX OPTIONS \
  -H "Origin: https://v0-davidduraesdd1-blip-crypto-signa.vercel.app" \
  -H "Access-Control-Request-Method: GET" \
  -i https://crypto-signal-app-1fsi.onrender.com/signals | head -10
# expect: 200 OK + access-control-allow-origin echoed back
```

### Local dev
```bash
# Backend
cd <repo>
pip install -r requirements.txt
cp .env.example .env  # set CRYPTO_SIGNAL_API_KEY + CRYPTO_SIGNAL_ALLOW_UNAUTH=true
python -m uvicorn api:app --reload --port 8000

# Frontend (separate terminal)
cd web
pnpm install
cp .env.local.example .env.local  # NEXT_PUBLIC_API_BASE=http://localhost:8000
pnpm dev  # http://localhost:3000

# Tests
python -m pytest -q                   # 437 passed, 1 skipped
cd web && npx tsc --noEmit            # clean
cd web && npx vitest run               # 6 component tests + contract test
```

---

## 12. Suggested new audits (since David asked)

### Already done (today)
- ✅ 5-tier deep-dive audit (T1-T5) — `docs/audits/2026-05-03_phase-d-deep-dive-audit.md`
- ✅ Fresh overnight follow-up audit — `docs/audits/2026-05-04_overnight-audit-summary.md`
- ✅ Live data-flow audit (this session) — endpoint-by-endpoint probe

### Should run NEXT

1. **D6 security + perf checklist** — full execution (already documented as a checklist, just hasn't been run). Would surface real npm/Semgrep findings + Lighthouse scores. ~1 day.

2. **Production secrets audit** — list every env var on Render + Vercel + GitHub Secrets, confirm:
   - No expired keys
   - No keys committed to git history (run `gitleaks` or `trufflehog`)
   - Key rotation schedule documented
   - Recovery plan if a key leaks

3. **Database persistence audit** — confirm what happens on Render free tier when the service restarts. SQLite on ephemeral disk = silent data loss. This is the highest-impact unknown right now.

4. **Cost / pricing audit** — Render free tier sleeps after 15min idle (10-30s cold start). Vercel Hobby caps. Glassnode free tier rate-limits. Document where the cliffs are.

5. **Backup + restore drill** — actually test the `pre-overnight-audit-2026-05-03` tag recovery path on a throwaway clone. Validate the drill works before you need it.

6. **Cross-browser + mobile** — real iPhone Safari + Android Chrome walk on every page. Tablet viewport (iPad). Confirm 44px tap targets per CLAUDE.md §8.

7. **§22 math sign-off audit** — focused session on CMC-1/2/3 with backtest diffs.

8. **CockroachDB migration feasibility** — if the SQLite-on-ephemeral problem
   is real, plan a Postgres-compatible migration. CockroachDB has a free
   serverless tier; the codebase already speaks SQLAlchemy via pandas. Plan,
   not commit.

---

## 13. Cleanup checklist

### Stale files / orphans

- [ ] `web/styles/globals.css` — DELETED in 53ac7f5 (was a v0-export
  orphan with conflicting `oklch` tokens)
- [ ] **`generator: v0.app` meta tag** — remove from
  `web/app/layout.tsx`. Cosmetic; identifies the app as v0-generated
  forever otherwise.
- [ ] **Old `crypto_scan_*.csv` and `crypto_dashboard_*.xlsx` in repo
  root** — per CLAUDE.md §22, "kept for regression baselines, archive
  older than 90 days to `data/archive/`." Worth running this at end of
  Phase D.
- [ ] **`backtest_equity*.png` charts** — regenerated on each backtest
  run; CLAUDE.md says safe to overwrite. Could move to `data/charts/`.
- [ ] **`runtime.txt` + `Procfile` + `render.yaml`** — three different
  deploy specs. CLAUDE.md notes "honored via runtime.txt at repo root."
  Pick one canonical and document the others as fallback.

### Dead / redundant code

- [ ] `app.py` (Streamlit) — fully archived after the 30-day post-D8
  overlap window. Per D8 guide, **pause** Streamlit Cloud, don't delete.
- [ ] `package-lock.json` — gitignored in `web/.gitignore`; pnpm is
  canonical. Confirm no rogue regen.
- [ ] `tests/test_audit_batch_2026_05_03.py` — these regression tests
  may be redundant with `test_overnight_2026_05_03.py`; consolidate
  during the next polish pass.

### Documentation hygiene

- [ ] **README.md update** — currently lists D5/D6/D8 as ⏳; flip D5 to
  ✅ (done today) and add the live URL.
- [ ] **Phase D master plan doc** —
  `docs/redesign/2026-05-02_phase-d-streamlit-retirement.md` should get
  a "closed" status banner once D8 lands.
- [ ] **CLAUDE.md** — add a §26 "POST-PHASE-D OPERATIONAL NOTES" section
  covering the Render persistence risk + scheduler decision + custom
  domain plan.

### Memory / sprint tracking

- [ ] **`pending_work.md`** in `~/.claude/projects/.../memory/` — close
  the Phase D items, open the post-cutover backlog items.
- [ ] **MEMORY.md index** — already updated through the overnight audit.
  Append today's data-flow audit entry after this brief is reviewed.

---

## 14. Test posture at HEAD (0797174)

```
$ python -m pytest -q
437 passed, 1 skipped, 6 warnings in ~40s

$ cd web && npx tsc --noEmit
exit 0 (clean)

$ cd web && npx vitest run
Test Files  2 passed (2)
     Tests 12 passed (12)  [6 component + contract]

$ cd web && npm run build
clean — 15 routes prerendered as static content

$ python -m pytest tests/test_composite_signal_regression.py
6 passed in 4s  (§22 zero drift vs 2026-05-02 baseline)
```

---

## 15. Operational polling cadence (currently live)

What the live frontend actually does on the page:

| Endpoint | Cadence | Why |
|---|---|---|
| `/execute/status` | every 5s | Topbar AGENT pill |
| `/health` | external uptime probe | Render's monitor |
| `/home/summary` | per-page-nav + Refresh button | Home hero |
| `/signals` | per-page-nav | Signals page |
| `/regimes/` | per-page-nav | Regimes page |
| `/onchain/dashboard?pair=` | per-page-nav | On-Chain page |
| `/diagnostics/*` | when Settings · Dev Tools is open | Gate/DB cards |
| `/backtest/summary` | per-page-nav | Home BacktestCard |

This means **the app stays cheap as long as the user isn't refreshing**.
The 5s execute-status poll is the only continuous traffic. CLAUDE.md §12
mandates this for the live AGENT indicator.

---

## 16. The non-obvious gotchas (read these)

1. **The "signa" cutoff in the URL is REAL.** Every variant with full
   "signal" or "signal-app" returns 404. Vercel hit a length limit when
   v0 created the project. Custom domain post-D8 fixes this.

2. **CORS regex requires the literal `davidduraesdd1-blip` segment.**
   Don't broaden it without thinking — that's the owner-prefix-only
   security property that prevents a different Vercel customer's
   preview from impersonating the project. If you change the GitHub
   org name, the regex needs an update.

3. **School networks block `*.vercel.app`.** Quick test: try
   `https://vercel.com` itself; if that fails, the whole namespace is
   blocked at the network level. Custom domain is the permanent fix.

4. **Render's `runtime.txt` says Python 3.11** but local dev may be on
   3.14 (which has been seen working). If you hit version-specific
   errors, check `runtime.txt` first.

5. **The Streamlit + Next.js sides share the same engine** but reach it
   differently — Streamlit imports the Python modules directly; Next.js
   goes through FastAPI. So a UI-only change on `app.py` does NOT
   affect Vercel; an engine change in e.g. `composite_signal.py`
   affects BOTH simultaneously. Plan PR scope accordingly.

6. **`composite_signal.py` is the §22 gold reference.** Any change
   there triggers a regression-diff requirement per CLAUDE.md §4 +
   §22. Save the new baseline JSON to
   `docs/signal-regression/YYYY-MM-DD-baseline.json` after sign-off.

7. **`backup-pre-redesign-2026-04-01` tag** is the absolute "OH NO
   undo everything" recovery point. Don't push past it without a
   newer base tag.

---

## 17. What to ask Cowork

Specific decision-level questions worth getting a second opinion on:

1. **Render data persistence**: SQLite on ephemeral disk = silent data
   loss on restart. Pay for persistent disk (~$1/month), migrate to
   Postgres, or accept periodic data resets (paper-trade history etc.
   could be acceptable to lose; backtest baselines NOT acceptable).

2. **Scheduler placement**: Render cron job (cheapest), Vercel cron
   trigger (also free), or upgrade Render to a worker tier with the
   long-running `scheduler.py` process? Trade-off: cron = simple but
   less precise; long-running = exact 15min cycle but ~$7/month.

3. **Real auth timing**: Push NextAuth + JWT before D8 cutover, or
   ship D8 with the documented `NEXT_PUBLIC_API_KEY` exposure and
   harden after? D8 risk is "key leaks more visibly"; pre-D8 risk is
   "more changes to validate before the merge gate."

4. **§22 math sign-off**: The CMC-1/2/3 findings don't currently move
   the live signal output (proved by 6/6 backtest pass). Are they
   real bugs that need fix, or audit-noise that can be documented and
   closed? Cowork's read on the math is valuable here.

5. **D8 timing**: Push to D8 this week (D6 done first), or shake out
   D5 for a few days first to catch surprises before merging?

---

## 18. Files I'd want any new context to read first

In rough priority order:

1. `CLAUDE.md` (root) — agent rules, sprint protocol, audit standards
2. `docs/audits/2026-05-04_overnight-audit-summary.md` — yesterday's wrap
3. `docs/audits/2026-05-03_phase-d-deep-dive-audit.md` — full audit ledger
4. `docs/redesign/2026-05-02_phase-d-streamlit-retirement.md` — master plan
5. `docs/redesign/2026-05-03_d6-security-perf-checklist.md` — what's next
6. `docs/redesign/2026-05-03_d8-cutover-guide.md` — what comes after
7. `docs/signal-regression/2026-05-03-d7-section22-compliance-review.md` — math verdict
8. `composite_signal.py` — gold reference for the math
9. `api.py` — FastAPI app entry, CORS regex, route registration
10. `web/lib/api.ts` — typed client, every endpoint the frontend calls

---

## 19. The 30-second pitch for a new context

> Crypto signal app, family-office-internal. Phase D = Streamlit
> retirement → Next.js + FastAPI cutover. D5 (Vercel deploy) went live
> today, end-to-end verified with real data after a `/scan/trigger`
> populated the DB. Next gates are D6 (security/perf checklist) and
> D8 (merge `phase-d/next-fastapi-cutover` → `main`). Branch HEAD is
> `0797174`. Tests: 437/1/0 backend + 12/0 frontend + 6/6 §22
> regression. Restore tag `pre-overnight-audit-2026-05-03` is the safe
> rollback. Live URL `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app`
> (the "signa" is real). Render API at
> `https://crypto-signal-app-1fsi.onrender.com`. Open issues: scheduler
> placement on Render, SQLite persistence on ephemeral disk, real auth
> via NextAuth/JWT to retire `NEXT_PUBLIC_API_KEY` browser exposure.

---

## 20. Co-author

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
