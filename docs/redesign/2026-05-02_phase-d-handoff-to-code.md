# Phase D — Hand-off Briefing for Claude Code

**From:** Cowork (Claude Opus, Linux mount session)
**To:** Claude Code (Windows-side, full repo access)
**Date:** 2026-05-02
**Status:** Plan approved by David. D1 audit complete. Ready to execute.

---

## Resume protocol (§16)

Before reading anything else, in this order:

1. `CLAUDE.md` — full project governance (master template inherits)
2. `MEMORY.md` — entries through 2026-05-02 (most recent at top)
3. `docs/redesign/2026-05-02_phase-d-streamlit-retirement.md` — full Phase D plan, approved
4. `docs/redesign/2026-05-02_d1-api-audit.md` — endpoint inventory + D1 gap list
5. This file — executive summary + autonomy boundaries

All §3, §4, §5, §16, §22, §24, §25 protocols apply unchanged.

---

## What's been approved by David

| # | Question | Answer |
|---|---|---|
| 1 | Framework pivot to Next.js + Tailwind + FastAPI? | **Approve Path B** |
| 2 | Cost arc ($0 → ~$20/mo build → $0 steady)? | **Approve** |
| 3 | Fold c-stabilization-sprint into Phase D? | **Fold** (don't fix Streamlit code we're retiring) |

David's stated autonomy preference: **approve initial plan, then full
autonomy through ship.** No mid-batch check-ins required unless
something exceeds plan scope or risk profile.

---

## Branch + tag layout

- **Working branch:** `phase-d/next-fastapi-cutover` (create off `main`)
- **Rollback tag:** `redesign-ui-2026-05-shipped` (already exists; do not move)
- **Streamlit code:** UNTOUCHED throughout Phase D — fallback stays
  live during 30-day overlap

---

## Sequence: D1 → D8

Each batch ships as a single commit on `phase-d/next-fastapi-cutover`.
PR back to `main` only at end of D8.

| Batch | Subject | Owner | Notes |
|---|---|---|---|
| **D1** | FastAPI gap-fill (6 new routers) | **Code** | See `2026-05-02_d1-api-audit.md` for full spec |
| **D2** | Render deploy of FastAPI | **David + Code** | David creates Render account; Code adds `render.yaml` + Cron-job.org keep-alive |
| **D3** | v0 generation of 13 mockups | **David** | David subscribes v0 Premium ($20), drives interactive generation, exports to `web/` via GitHub panel |
| **D4** | Wire Next.js frontend to FastAPI | **Code** | Tanstack Query, typed `web/lib/api.ts`, replace v0 mocks |
| **D5** | Vercel deploy of frontend | **David + Code** | David creates Vercel account; Code does the rest |
| **D6** | Security + perf pass | **Code** | semgrep, npm audit, manual review of v0 components, Lighthouse |
| **D7** | §4 regression + parity verification | **Code + David** | Code runs, David walks the preview deploy at 3 levels + 2 themes |
| **D8** | Cutover + 30-day Streamlit overlap | **Code + David** | Code merges + deploys; David verifies Vercel prod URL |

---

## Autonomy boundaries

**Code MAY proceed without David on:**
- D1 implementation (Python files, new routers, tests)
- D2 config files (`render.yaml`, env-var documentation)
- D4 entirely (TypeScript edits in `web/`)
- D6 entirely
- D7 the testing portion (parity asserts)

**Code MUST wait for David on:**
- D2 Render account + deploy hook (provide him the exact steps in
  Render dashboard)
- D3 entirely (v0 is interactive, requires subscription)
- D5 Vercel account + GitHub integration (provide exact steps)
- D7 the manual browser walk
- D8 final merge to main

**Code MUST escalate to David if:**
- Any v0 output requires substantive rework that pushes timeline
  beyond +5 days of plan
- A §4 regression fails (composite_signal output drift between
  Streamlit and Next.js renders)
- A security finding from D6 exceeds "fix in current PR" — i.e.
  needs an architectural change
- Render or Vercel free-tier limits insufficient for actual usage
  (cold-start + traffic shape)

---

## Files Cowork modified this session

- `MEMORY.md` — added 2026-04-29 / 2026-04-29-to-05-01 / 2026-05-01 / 2026-05-02 entries
- `docs/redesign/2026-05-02_phase-d-streamlit-retirement.md` (new) — full Phase D plan
- `docs/redesign/2026-05-02_d1-api-audit.md` (new) — D1 gap analysis
- `docs/redesign/2026-05-02_phase-d-handoff-to-code.md` (this file)
- `docs/redesign/2026-05-01_post-deploy-audit.md` (already existed) — c-stabilization-sprint, **folded into Phase D, do not implement separately**

No code changes. No tests changed. No git operations.

---

## Streamlit fallback — preservation rules

- **Do not delete** `app.py`, `ui/`, or any Streamlit-specific module
  during D1-D7.
- **Do not remove** the Streamlit Cloud deployment.
- D8 cutover keeps Streamlit live for 30 days as fallback.
- Day 31 post-D8 (estimated 2026-06-01 to 06-15 depending on batch
  pacing): archive Streamlit (don't delete) — leave the Streamlit
  Cloud config + secrets in place so it can be revived in <1 hour.

---

## c-stabilization-sprint — disposition

7 fixes from `docs/redesign/2026-05-01_post-deploy-audit.md`:
**FOLDED INTO PHASE D, DO NOT IMPLEMENT.**

Rationale per David: those fixes are against Streamlit code being
retired in D8. The new Next.js renders the mockups as designed; the
7 issues simply don't exist in Next.js.

If a fix is conceptually relevant to Next.js (e.g. C-fix-04's 8-cell
timeframe strip is a real product requirement), it's covered by the
v0 generation in D3.

---

## §4 regression diff — when required

Only at **D7**, on `composite_signal.compute_composite_signal`.

Test: pull the canonical 5-scenario fixture from
`docs/signal-regression/2026-04-28-baseline.json`, run through the
new FastAPI → Next.js render path, assert output matches Streamlit-
rendered values to within rounding (BUY/HOLD/SELL category exact match,
confidence ±0.01, regime exact match, sub-scores ±0.01).

If the test fails, escalate immediately. Do not ship D8.

---

## Cost flag — David's spending

- v0 Premium: David subscribes for 1 month, cancels at end of D3.
  **Code does not spend money or sign up for accounts.**
- Render free tier: $0, no credit card required.
- Vercel Hobby: $0, no credit card required.
- All other infra: existing.

If at any point Code's plan implies a cost David hasn't approved,
escalate before incurring it.

---

## Communication back to David

After each batch ships its commit, append a one-line update to
`MEMORY.md` under a new "## 2026-05-XX — Phase D batch N landed"
entry. Format per existing entries (newest on top).

After D8 lands, write the full post-cutover summary to
`docs/redesign/2026-05-XX_phase-d-cutover-summary.md` covering:
- final endpoint count
- final page count
- Lighthouse scores
- §4 regression result
- Streamlit retirement date
- next-app handoff (which sibling app is next)

---

## Final note

The pattern locked in Phase D — Next.js + Tailwind + shadcn + v0 +
FastAPI + Vercel + Render — is intended to compound across the next
3 sibling apps (`flare-defi-model`, `rwa-infinity-model`,
`etf-advisor-platform`). Document any pattern decisions in
`shared-docs/` so they're reusable.
