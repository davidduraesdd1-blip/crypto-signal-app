# Phase D — Streamlit Retirement + Next.js + FastAPI Cutover

**Author:** Cowork (Claude Opus)
**Date:** 2026-05-02
**Branch (when started):** `phase-d/next-fastapi-cutover` off `main`
**Tag baseline:** `redesign-ui-2026-05-shipped` → `20587d2` (rollback point)
**Streamlit fallback:** https://cryptosignal-ddb1.streamlit.app/ (stays live throughout)

---

## TL;DR

Streamlit is the bottleneck. Mockups are pixel-locked. Engine is done.
**Replace the Streamlit frontend with a Next.js + Tailwind + shadcn/ui
app generated from our locked mockups via v0, wrap the existing Python
engine in a FastAPI service, deploy to Vercel + Render free tiers,
retire Streamlit after a 30-day fallback overlap.**

Build cost: ~$20-40 for one month of v0 Premium, then cancelled.
Steady-state cost: **$0/mo** (Vercel Hobby + Render free tier).
Shelf mode: **$0/mo** (stop pinging Render; Vercel always-on stays free).

---

## 1. Why Streamlit must go

Three specific failures from the past two days, each independently
sufficient to motivate the pivot:

| # | Symptom | Root cause | Effort spent |
|---|---|---|---|
| 1 | Topbar buttons render as wide-wrapped Streamlit defaults (text wraps mid-word, ~280px tall instead of mockup's 56px) on every page | Streamlit injects `primaryColor` at inline-style level which beats CSS overrides | 3 unsuccessful Code-driven fix attempts on C-fix-01 |
| 2 | Sidebar active-state lags page nav by one click | Streamlit's render-then-callback cycle emits sidebar markdown before click writes new state | C-fix-03 — partial fix landed but still lags occasionally |
| 3 | Mobile nuclear-defense CSS battle | Streamlit's universal `<div>` nesting requires `* { min-width: 0 }`, `max-width: 100vw`, `overflow-x: hidden`, `minmax(0, 1fr)` defenses everywhere | Multiple debug cycles; "fixed" but fragile |

The pattern: **every fight with Streamlit costs 5-10x what the same
fight would cost in vanilla React**, because Streamlit owns the DOM
and won't let go. We've already paid that cost twice (Phase C +
c-stabilization-sprint). Paying it a third time on the next 3 sibling
apps is unacceptable.

---

## 2. Target architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (David / future users)                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Vercel Hobby (free, always-on)                             │
│  Next.js 15 + Tailwind + shadcn/ui                          │
│  - Mockups → v0 → React components                          │
│  - Tanstack Query for data fetching                         │
│  - Auth handled at frontend (NextAuth, future)              │
└──────────────────────┬──────────────────────────────────────┘
                       │  HTTPS + JWT
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Render Free Tier (sleeps 15min, ~30s cold start, $0)       │
│  FastAPI + Uvicorn                                          │
│  - Wraps existing Python engine (composite_signal,          │
│    cycle_indicators, top_bottom_detector, regime detection) │
│  - SQLite WAL-mode for cached signals/backtests             │
│  - Endpoints mirror current Streamlit page data needs       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  External data (existing fallback chains, §10 unchanged)    │
│  - ccxt OKX/Kraken/CoinGecko                                │
│  - alternative.me Fear & Greed                              │
│  - cryptorank.io, Glassnode, Dune, Google Trends            │
└─────────────────────────────────────────────────────────────┘

         (parallel, retiring after 30-day overlap)
                       │
┌─────────────────────────────────────────────────────────────┐
│  Streamlit Cloud — cryptosignal-ddb1.streamlit.app/         │
│  - Stays live as fallback during cutover (§14)              │
│  - Day 31 post-cutover: domain redirect to Vercel,          │
│    Streamlit app archived (not deleted)                     │
└─────────────────────────────────────────────────────────────┘
```

### Why this stack

- **Next.js + Tailwind + shadcn/ui:** v0 generates this stack natively
  — code matches what a senior React dev writes by hand, no rework
  needed. Same stack for the next 3 sibling apps (compounding return
  on learning).
- **FastAPI:** already in `requirements.txt` (§22), Python so we keep
  100% of the engine code, async-native so it handles burst load on
  Render's small instance.
- **Vercel Hobby:** $0/mo, always-on, edge-deployed CDN, auto-deploys
  from GitHub PR previews.
- **Render free tier:** $0/mo, sleeps after 15min idle (perfect for
  shelf mode — just stop pinging it), wakes in ~30s on first request.
- **SQLite WAL-mode:** $0 storage, read-heavy concurrency safe, swaps
  to Postgres later if needed.

---

## 3. Cost architecture (build → steady → shelf)

| Phase | Vercel | Render | v0 | Streamlit | Domain | **Total/mo** |
|---|---|---|---|---|---|---|
| Build (weeks 1-3) | $0 (Hobby) | $0 (free) | $20 (Premium) | $0 (existing) | $0 (subdomain) | **~$20** |
| Optional polish (week 4) | $0 | $0 | $20 (extend if needed) or $0 (cancel) | $0 | $0 | **$0-20** |
| Steady state | $0 | $0 (kept alive via self-ping or Cron-job.org free) | $0 (cancelled) | $0 (running as fallback for 30 days then archived) | $0 | **$0** |
| Shelf mode (funds tight) | $0 (stays live) | $0 (stop the keep-alive ping; Render sleeps and stays asleep) | $0 (cancelled) | $0 (Streamlit Cloud stays free indefinitely as backup) | $0 | **$0** |

**Shelf-mode mechanics:**
- Vercel Hobby: free forever, always-on, no action needed.
- Render: stops pinging → goes to sleep → first user visit triggers
  a 30s cold wake. If no users visit, **stays at $0 forever**.
- v0: subscription cancelled, generated code lives in repo, can re-up
  any month if more screens needed.
- Streamlit fallback: free Streamlit Cloud account stays parked.
- Custom domain (future): when added, Cloudflare DNS is free; Vercel
  Hobby supports custom domains at $0.

**Wake-up cost on shelf mode:** when shelf-moded for months and you
return, run `git pull` + `npm install` + `vercel deploy`; Render
auto-redeploys on push. Maybe 10 min wall-clock to come back online.

---

## 4. Mockup-to-code tool decision

Three contenders evaluated:

| Tool | Code quality | Stack match | Pricing | Code ownership | Verdict |
|---|---|---|---|---|---|
| **v0 by Vercel** | Senior-React-dev quality, modular typed components, slots into existing codebase | Next.js + Tailwind + shadcn/ui (perfect match for our mockups) | $20/mo Premium, can cancel | Full export, GitHub Git panel, branches + PRs from chat | **WINNER** |
| Lovable | Polished UI, advanced state mgmt, "skip most coding" | Generates full-stack but more black-box | $20/mo equivalent | Two-way GitHub sync | Wrong fit — we need to own and extend the code, not let an AI manage it |
| Bolt.new | Functional but inconsistent (variable names drift between sessions) | Full-stack including backend | $20/mo equivalent | GitHub integration | We don't need full-stack from the tool — engine already exists in Python |

**Winner: v0.** Three reasons:
1. Same stack as our mockups (shadcn/ui + Tailwind + Next.js).
2. Code consistent enough to inherit and extend without rewrite.
3. Frontend-only matches our reality (we already have a Python engine).

**Security flag noted from research:** Veracode 2026 finds 45% of
AI-generated code has vulnerabilities; Stanford puts it at 80%. **We
add a mandatory code-review pass + dependency audit (npm audit, semgrep)
before every deploy.** This is folded into batch D6.

---

## 5. Secrets architecture (better + faster pattern)

User said: *"if you feel there is a better more secure and faster way
then plan for it now."* Plan:

- **Vercel:** environment variables in Project Settings → Environment
  Variables. Encrypted at rest, exposed only to deployments. Can scope
  to Production / Preview / Development separately.
- **Render:** environment variables in dashboard or via `render.yaml`
  (committed to repo, encrypted vars referenced by name). Group secrets
  into an Env Group for sharing across services later.
- **GitHub Actions (CI):** repository secrets for any deploy-time creds
  (Vercel token, Render deploy hook).
- **Local dev:** `.env.local` (gitignored — already in `.gitignore`),
  Doppler optional later if multi-app secret sharing becomes painful.

**No copy-paste from chat ever.** All secrets entered once via Vercel/
Render dashboards, referenced by name in code.

**API keys to migrate from Streamlit secrets:** OKX, Kraken, CoinGecko,
alternative.me (none — public), cryptorank.io, Glassnode, Dune.

---

## 6. Batch sequence (D1-D8)

Each batch ships as its own commit on `phase-d/next-fastapi-cutover`,
PRs back to main when D8 lands. No §4 regression diff per batch
(presentation + transport layer). One §4 regression at D7 right before
cutover (full composite_signal output diff, frontend-rendered values
must match Streamlit-rendered values to within rounding).

### D1 · FastAPI scaffold (1-2 days)
- New `api/` directory at repo root.
- `api/main.py` — FastAPI app, CORS for Vercel preview + production
  domains.
- `api/routers/` — one router per page: `signals.py`, `regimes.py`,
  `backtester.py`, `onchain.py`, `alerts.py`, `ai_assistant.py`,
  `settings.py`.
- Each router exposes the data the corresponding Streamlit page needs
  today, no UI logic.
- `api/dependencies.py` — auth (None for now, JWT-ready), rate-limit,
  cache helpers.
- Wraps existing engine via `from crypto_model_core import ...`,
  `from composite_signal import ...` — zero engine changes.
- Local dev: `uvicorn api.main:app --reload` on :8000.
- **Deliverable:** all current page data accessible via REST,
  documented in auto-generated `/docs` (FastAPI Swagger).

### D2 · Render deploy of FastAPI (0.5 day)
- `render.yaml` at repo root, describes the web service.
- Free tier, autodeploy from main branch.
- Env vars set up in Render dashboard.
- Smoke test: `curl https://crypto-api-XXX.onrender.com/healthz` → 200.
- Smoke test: `curl .../api/signals/btc-usdt` returns same composite
  signal value as Streamlit page.
- Cold-start measured + documented (~30-60s expected).
- Keep-alive: Cron-job.org free pings `/healthz` every 10 min.

### D3 · v0 generation pass (2-3 days)
- v0 Premium subscription started (~$20).
- Feed the 13 mockup HTML files to v0 one at a time, generate Next.js
  + shadcn/ui components.
- Each generated page exported via v0's GitHub panel as a PR to a new
  `web/` directory on `phase-d/next-fastapi-cutover`.
- Components go into `web/components/`, pages into `web/app/`
  (Next.js 15 app router).
- Design tokens (rail-w, topbar-h, sibling-family palette) imported
  from `web/styles/tokens.css` mirroring our `ui/design_system.py`.
- **Deliverable:** all 8 pages render in `npm run dev` with mock data.

### D4 · Wire frontend to FastAPI (1-2 days)
- Tanstack Query for all data fetching.
- `web/lib/api.ts` — typed client functions, one per FastAPI endpoint.
- Replace v0's mock data with live API calls.
- Loading + error states (already in mockups).
- 5-min cache match (§12) handled client-side via Tanstack stale time.
- Local dev with `NEXT_PUBLIC_API_BASE=http://localhost:8000`.

### D5 · Vercel deploy of frontend (0.5 day)
- Connect GitHub repo to Vercel.
- Project root: `web/`.
- Env var `NEXT_PUBLIC_API_BASE` = Render URL.
- Auto-deploy on push to `phase-d/next-fastapi-cutover`.
- Preview URL shared in PR.
- Smoke test: every page loads, every chart renders, no console errors.

### D6 · Security + perf pass (1 day)
- `npm audit fix` clean.
- Semgrep run on `web/` and `api/` (CI workflow added).
- Manual code review of every v0-generated component (no PII leaks,
  no `dangerouslySetInnerHTML` without sanitization, no client-side
  secrets).
- Lighthouse audit on Vercel preview, target 90+ Performance + 100 A11y.
- Mobile viewport check on real device.
- §22 indicator fixtures still pass (they don't touch frontend, but
  re-run for confidence).

### D7 · §4 regression + parity verification (1 day)
- Run `composite_signal.compute_composite_signal` on the canonical
  5-scenario fixture set (`docs/signal-regression/2026-04-28-baseline.json`).
- Pull same scenarios via FastAPI → Vercel-rendered Signals page.
- Verify rendered BUY/HOLD/SELL + confidence + regime + sub-scores
  all match Streamlit-rendered values to within rounding.
- 20-point browser walkthrough on Vercel preview at all 3 user levels
  + both themes.
- Audit doc at `docs/redesign/2026-05-XX_d-cutover-verification.md`.

### D8 · Cutover + Streamlit overlap (0.5 day + 30 days passive)
- Merge `phase-d/next-fastapi-cutover` to main.
- Vercel production deploy.
- Communication: README updates, both URLs documented.
- **Streamlit stays live for 30 days as fallback.**
- Day 31: archive Streamlit app (don't delete — leave the secrets +
  config in place so it can be revived in <1 hour if needed). Update
  README to point to Vercel URL only.

**Estimated wall-clock:** 8-12 working days end-to-end. Code-driven on
the Windows side after D1 scaffold; David approves the plan, then
review touchpoints at D5 (preview deploy walkthrough) and D7 (parity
sign-off) only.

---

## 7. Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| v0 output worse than expected → manual rework needed | Medium | +3-5 days | Render-mode preview on each batch; if quality unacceptable, fall back to manual Tailwind translation of mockups (slower but deterministic) |
| Render cold starts annoy users (30-60s on first hit) | High in steady state | Low (we have ~1 user) | Cron-job.org keep-alive ping every 10min stays free, eliminates cold starts entirely |
| FastAPI security gaps from AI-generated code | Medium | High | Semgrep + manual review pass at D6; minimum-viable auth (FastAPI's `Depends`-based JWT pattern) wired before any user beyond David |
| Engine import path breaks on Render (different Python version, missing system deps) | Medium | Medium | `requirements.txt` already locked to Python 3.11; Render uses 3.11 by default; smoke test in D2 catches this |
| §22 indicator outputs drift between local Python 3.14 and Render Python 3.11 (we already saw this with `hmmlearn` on 3.14) | Low | Low | §22 fixtures are version-tolerant (`_hmmlearn_available()` helper); D7 parity check catches any drift in composite output |
| Streamlit Cloud removes free tier mid-cutover | Low | Low | We have 30-day overlap; if Streamlit free tier vanishes, we cut over immediately and skip the overlap |
| User decides to stop paying mid-build | Low | Low | After D2 ships, FastAPI on Render is shelf-mode-able. If we have to pause at D2-D3, we restart D3 with a fresh v0 month later. |

---

## 8. Rollback plan

`redesign-ui-2026-05-shipped` tag = current Streamlit-on-main snapshot.

If Phase D fails for any reason at any point:
- `git checkout redesign-ui-2026-05-shipped` → Streamlit code intact.
- Streamlit Cloud deploy = unchanged throughout (we're touching `web/`
  and `api/` directories that Streamlit doesn't see).
- `phase-d/next-fastapi-cutover` branch can stay alive indefinitely
  for restart attempts.

---

## 9. What changes for the next 3 sibling apps

If Phase D ships clean for crypto-signal-app, the same pattern
compounds:

| App | Frontend | Backend | Estimated time (with v0 + pattern locked) |
|---|---|---|---|
| flare-defi-model | Next.js (port + recolor) | FastAPI (new wrap) | 4-6 days |
| rwa-infinity-model | Next.js (port + recolor) | FastAPI (new wrap) | 4-6 days |
| etf-advisor-platform | TBD with partner | TBD | TBD |

**Mockups already exist** for the sibling family palette — they share
the same design system, only the accent color and copy change.
Compounding return on the v0 + Tailwind tokens + shadcn pattern is the
strategic prize here.

---

## 10. Decision points for David (single-batch ask)

Three questions before execution starts. After answers, full autonomy
through D8 per stated preference (§17).

1. **Approve the framework pivot to Next.js + Tailwind + FastAPI?**
   (Approve / Pivot to alternative / Discuss)

2. **Approve the cost arc** ($0 → ~$20 for 1 month → $0 steady state /
   shelf mode)? (Approve / Cap at $0 throughout / Discuss)

3. **Approve folding c-stabilization-sprint into Phase D** (don't
   ship 7 fixes against Streamlit code we're about to retire)?
   (Fold / Ship c-stab first then Phase D / Discuss)

---

## 11. Out of scope for Phase D

- Custom domain (after D8, separate ticket — Cloudflare DNS, $0).
- Real auth beyond David (after D8 — NextAuth + FastAPI JWT, separate
  ticket).
- Background scheduler / 24/7 agents (architected for later, not
  wired in this phase — `agent.ensure_supervisor_running()` helper
  carries over to FastAPI startup hook when activated).
- Sibling apps (Phase E, F, G — start after D8 lands).
- ML model serving (LightGBM/XGBoost — current lazy-load pattern
  ports to FastAPI lazy router import, no architecture change).

---

## Hand-off briefing for Claude Code (when approved)

```
Branch off main → phase-d/next-fastapi-cutover.
Tag baseline already = redesign-ui-2026-05-shipped.
Read CLAUDE.md, MEMORY.md (entries through 2026-05-02),
  docs/redesign/2026-05-02_phase-d-streamlit-retirement.md.
Execute D1 through D8 in order.
Per-batch commit: feat(phase-d-DN): <title>.
Single PR to main when D8 lands.
§4 regression diff at D7 only (composite_signal output parity).
Semgrep + npm audit at D6.
Streamlit code untouched — we own web/ and api/ directories,
  Streamlit code stays for 30-day overlap.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```
