# D8 — Cutover Guide

**Trigger:** D7 verified + D6 sign-off complete (no high/critical
audit findings open). At this point Phase D is functionally done and
the Vercel preview is parity-verified against Streamlit.

**Goal:** flip the primary URL from Streamlit Cloud to Vercel +
preserve Streamlit as a 30-day fallback.

**Effort:** 30-60 min for the cutover itself + 30 days of passive
overlap monitoring.

---

## Pre-flight verification (10 min)

Before merging anything:

```bash
# 1. Confirm phase-d/next-fastapi-cutover is clean and pushed
cd /c/dev/Cowork/crypto-signal-app
git status                         # → clean
git fetch origin
git log origin/phase-d/next-fastapi-cutover..phase-d/next-fastapi-cutover  # → empty

# 2. Confirm latest commit on phase-d builds + tests pass
cd web && npm run build && npm run test:contract
# → Build: clean. Test: passed against live deploy.
cd .. && python -m pytest -q --tb=no
# → 428+ passed, 1 skipped, 0 regressions

# 3. Confirm Vercel preview is up-to-date with the latest phase-d
#    commit (auto-deploy should have picked it up):
#    Visit https://crypto-signal-app-web-<hash>.vercel.app
#    Check footer/version indicator → matches latest commit short hash

# 4. Confirm Render API is healthy + auth still enforced:
curl -s -o /dev/null -w "%{http_code}\n" https://crypto-signal-app-1fsi.onrender.com/health  # → 200
curl -s -o /dev/null -w "%{http_code}\n" https://crypto-signal-app-1fsi.onrender.com/signals  # → 401
```

If anything above fails, **abort cutover** and fix first.

---

## Restore point (1 min)

```bash
cd /c/dev/Cowork/crypto-signal-app
git tag -a pre-d8-cutover-2026-05-XX -m "Restore point before phase-d → main merge. \
Recovery: git checkout pre-d8-cutover-2026-05-XX returns the repo to the \
last known-good pre-cutover state."
git push origin pre-d8-cutover-2026-05-XX
```

---

## Step 1 — Merge phase-d → main (5 min)

**Option A: GitHub PR (recommended).** Cleaner history + commentary
trail.

1. Open https://github.com/davidduraesdd1-blip/crypto-signal-app
2. Click **Pull Requests** → **New Pull Request**
3. Base: `main` ← Compare: `phase-d/next-fastapi-cutover`
4. Title: `Phase D: Streamlit retirement — Next.js + FastAPI cutover`
5. Body: paste the cutover summary block from the bottom of this guide
6. Click **Create Pull Request**
7. Verify CI passes (none configured yet, so just GitHub's "no merge
   conflicts" check)
8. Click **Merge Pull Request** → **Squash and merge** (squash so main
   gets a single clean commit) OR **Create a merge commit** (preserves
   the full Phase D history; recommended for posterity)
9. Confirm merge.

**Option B: CLI (faster if you prefer).**

```bash
git checkout main
git pull origin main
git merge phase-d/next-fastapi-cutover --no-ff -m "Phase D: Streamlit retirement → Next.js + FastAPI cutover

29+ commits across audit work + D1-D8 in 2026-04-27 through 2026-05-03.
Streamlit (app.py) stays live for 30 days as fallback. Next.js (web/)
is the new primary frontend, deployed to Vercel. FastAPI (api.py +
routers/) is the unified backend, deployed to Render.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push origin main
```

---

## Step 2 — Vercel production promotion (5 min)

By default, Vercel deploys every branch to a unique preview URL. After
merging phase-d → main, the main-branch deploy becomes a fresh
production deploy.

1. Open https://vercel.com → your project
2. Settings → **Git** → confirm **Production Branch** is `main`
   (it likely defaulted to `phase-d/next-fastapi-cutover` during D5
   setup; flip it to `main` now)
3. Settings → **Domains** → if you set up a custom domain in D5,
   confirm it's pointing at the production deploy. If not, the
   `*.vercel.app` URL is your production URL.
4. Trigger a manual production deploy from the Deployments tab if
   Vercel didn't auto-deploy on the merge.

**Production URL post-cutover:**
- If custom domain: `https://signals.duraes.family` (or whatever you
  picked)
- If no custom domain: `https://crypto-signal-app-web.vercel.app`
  (the canonical short URL Vercel assigns to the production branch)

---

## Step 3 — Update README (2 min)

The README currently lists D8 as ⏳ pending. Flip to ✅ closed:

```bash
git checkout main
# Edit README.md:
# - Phase D status table: D8 ⏳ → D8 ✅ (date)
# - Live deploys section: add the Vercel production URL
# - "Next.js (Vercel)" row: replace "landing in D5" with the URL
git add README.md
git commit -m "docs: mark D8 cutover complete + add Vercel URL"
git push origin main
```

---

## Step 4 — Streamlit overlap (passive, 30 days)

**Streamlit stays live unchanged on Streamlit Cloud at
https://cryptosignal-ddb1.streamlit.app for 30 days.** Both URLs serve
the same data (same Render-hosted FastAPI backend), but Streamlit reads
directly from the Python engine while Vercel reads via FastAPI.

This is intentional — gives you a 30-day window to:
- Notice if Vercel has any rendering or behavior bug
- Compare specific signals between the two UIs
- Roll back if something catastrophic surfaces (revert main commit,
  push, Vercel auto-deploys the rollback)

During the overlap:
- Don't push UI changes to `app.py` (would change Streamlit
  independently)
- Don't archive the Render deploy
- Watch the Render dashboard for any new error patterns
- If Vercel surfaces a bug that Streamlit doesn't, that's a Phase D
  regression — file as `D8-regression-<date>` in
  `docs/audits/` and fix on a hotfix branch off main

---

## Step 5 — Day 31: archive Streamlit (5 min)

After 30 days of clean Vercel operation:

1. Go to https://share.streamlit.io → app settings
2. Click **Pause app** (NOT delete — pause keeps the config + secrets)
3. Update README:
   - Remove the Streamlit row from the live-deploys table
   - Note the pause: "Streamlit (legacy) — paused 2026-06-XX, can be
     unpaused in <1 hour for emergency recovery"
4. Commit + push.

**Don't delete the app or its secrets.** Pause is reversible; delete
is not. The `app.py` code stays in the repo so we can always
re-enable.

---

## Cutover summary block (paste into PR body)

```markdown
## Phase D — Streamlit Retirement → Next.js + FastAPI

### What ships in this PR

- **FastAPI backend** (api.py + routers/) — 6 new routers, ~30
  endpoints, full auth via X-API-Key, deployed to Render at
  https://crypto-signal-app-1fsi.onrender.com
- **Next.js 16 frontend** (web/) — 15 routes, TanStack Query,
  shadcn/ui components, deployed to Vercel
- **428 Python tests + 1 frontend contract test** — all passing
- **50+ audit findings closed** across overnight + Phase D-specific
  audit batches
- **§22 compliance** — verified + documented in
  docs/signal-regression/2026-05-03-d7-section22-compliance-review.md

### What does NOT ship

- Streamlit (app.py + ui/) stays as 30-day fallback
- 7 D-extension endpoints stubbed with TODO(D-ext) comments at
  consumer sites (none block cutover)
- Larger-scope deferred items in
  docs/audits/2026-05-03_deferred-fixes-proposals.md (P4-P7
  partially landed; full DB-1/DB-4 concurrency rewrite has a test
  plan but no code yet)

### Live deploys post-merge

| Surface | URL |
|---|---|
| Frontend (primary, post-cutover) | TBD — Vercel production URL |
| Backend (FastAPI) | https://crypto-signal-app-1fsi.onrender.com |
| Streamlit (30-day fallback) | https://cryptosignal-ddb1.streamlit.app |

### Rollback

If anything surfaces in the 30-day overlap:
- Vercel: revert the main commit, push, auto-deploy rollback
- FastAPI: same — Render auto-deploys on push
- Streamlit: untouched; just point users back at the Streamlit URL

Restore tag: `pre-d8-cutover-2026-05-XX` (created in this PR's
prerequisite step).

### Co-author

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## Post-cutover monitoring (passive)

Watch these signals during the 30-day overlap:

| Signal | Source | Threshold |
|---|---|---|
| Vercel error rate | Vercel dashboard → Analytics → Errors | < 1% per hour |
| FastAPI 5xx rate | Render dashboard → Logs | < 0.5% per hour |
| Frontend bundle size | Lighthouse on production URL | < 300 kB shared |
| Render uptime | https://crypto-signal-app-1fsi.onrender.com/health | 200 on 99% of probes |
| Sentry / error log | (not yet wired — post-D8 task) | — |

---

## What's NEXT (post-cutover)

| Task | Owner | Effort |
|---|---|---|
| D-extension batch — 7 missing endpoints (/macro, /signals-with-sparkline, /onchain/whale-events, /backtest/equity, /backtest/optuna-runs, /funding-carry, /signals/{pair}/history, /agent/*) | Claude | 3-5 days |
| Real auth (NextAuth + JWT) — replaces NEXT_PUBLIC_API_KEY exposure | Claude | 1-2 days |
| DB-1/DB-4 concurrency rewrite per `docs/audits/2026-05-03_db-concurrency-rewrite-test-plan.md` | Claude | 5-7 days |
| Sibling-app port — flare-defi-model gets the same Next.js + FastAPI treatment | Claude | 4-6 days |
| Sibling-app port — rwa-infinity-model | Claude | 4-6 days |
| Streamlit archive (pause, not delete) | David + Claude | 5 min on day 31 |
