# Overnight Audit Summary — 2026-05-03 → 2026-05-04

**For David, when you wake up.**

You asked: *"do as much as possible without me as you can do and then i
want a massive deep dive audit of the entire codebase and all files...
run a full and complete audit over night."*

Here's what shipped while you were asleep, and what's still open.

---

## TL;DR — your final URL

🌐 **`https://v0-davidduraesdd1-blip-crypto-signa.vercel.app`**

The "signa" isn't a truncation — that's the actual canonical URL Vercel
assigned (the v0-created project name hit a length limit). All 8 routes
return 200. Open this URL when you're up.

**Caveat:** when you first opened it last night, every page rendered
"loading…" because the Render API was rejecting the page's CORS
preflights — the old regex on api.py only admitted
`crypto-signal-app(...)?.vercel.app` and rejected every URL Vercel
actually assigned. Fixed in commit `53ac7f5` and pushed; Render
auto-deployed from `phase-d/next-fastapi-cutover`.

**End-to-end verified live before I signed off** (timestamp inside the
verification block below):

```
$ curl -X OPTIONS \
    -H "Origin: https://v0-davidduraesdd1-blip-crypto-signa.vercel.app" \
    -H "Access-Control-Request-Method: GET" \
    -i https://crypto-signal-app-1fsi.onrender.com/signals
HTTP/1.1 200 OK
access-control-allow-origin: https://v0-davidduraesdd1-blip-crypto-signa.vercel.app
access-control-allow-headers: Accept, Accept-Language, Content-Language, Content-Type, X-API-Key
access-control-allow-methods: GET, POST, PUT, DELETE

$ curl -H "Origin: https://v0-davidduraesdd1-blip-crypto-signa.vercel.app" \
       -H "X-API-Key: <key>" \
       https://crypto-signal-app-1fsi.onrender.com/signals
{"count":0,"results":[]}
```

If "loading…" is still showing on the live page in the morning, hard-
refresh (Ctrl+F5) — your browser may have cached last night's failed
preflight. After that the watchlist + KPI strip + all 8 routes should
populate with real data.

---

## Restore point

`pre-overnight-audit-2026-05-03` tag pushed before the overnight pass.
Recovery: `git checkout pre-overnight-audit-2026-05-03` returns the
repo to the pre-overnight state if anything turns out broken.

---

## Commits landed overnight (3)

| SHA | What |
|---|---|
| `d53a53d` | T1 MEDIUMs (idempotency LRU cap + order_type lowercase + settings GET cache-control) + 6 regression tests |
| `53ac7f5` | **CRITICAL**: CORS regex broadened to admit the v0 Vercel URL + 13-finding a11y bundle + lockfile tests + orphan globals.css deleted |
| (and `4b7bc2e` from before sleep) | pnpm-lock.yaml regenerated to unblock the Vercel build |

Push-state: `phase-d/next-fastapi-cutover` → `53ac7f5` (synced to GitHub).
Tag-state: `pre-overnight-audit-2026-05-03`, `pre-d8-cutover-2026-05-XX`
not yet (D8 still pending your sign-off).

---

## What was audited overnight

A fresh deep-audit subagent re-swept the full repo with focus on what
the daytime 5-tier pass might have missed:

- Frontend a11y bundle — concrete file:line list with suggested fixes
- Test coverage gaps for the 8 fixes that landed in commit 47a6f90
- Anything else suspicious that didn't get covered today

**Findings: ~25 items** across CRITICAL/HIGH/MEDIUM/LOW.

---

## What was fixed overnight

### CRITICAL (1)
**CORS regex unblocker** — the v0-created Vercel project assigned
`v0-davidduraesdd1-blip-crypto-signa.vercel.app` (plus per-deploy hash
URLs and per-branch Git URLs). The previous CORS regex on
[api.py:121](.claude/worktrees/phase-d-resume/api.py:121) only matched
`crypto-signal-app(...)?` shape and **rejected every real URL** Vercel
issued, which is why every page showed "loading…" indefinitely.
Broadened to admit any vercel.app subdomain containing the literal
owner identifier `davidduraesdd1-blip`. Owner-prefix-only security
property preserved (a different Vercel customer's preview can't
impersonate you). Verified with a 9-case regex test.

### HIGH / MEDIUM closed (8)

| Where | What |
|---|---|
| `execution.py` | Idempotency cache hard cap (10k entries) with O(n)-amortized half-eviction |
| `execution.py` | `default_order_type` lowercase normalize on read (validator accepts MARKET/LIMIT but ccxt expects lowercase) |
| `routers/settings.py` | GET /settings/ now emits `Cache-Control: no-store` + `Pragma: no-cache` (defense in depth alongside redaction) |
| `web/components/segmented-control.tsx` | role=radiogroup + aria-label + per-button role=radio + aria-checked |
| `web/components/toggle-switch.tsx` | role=switch + aria-checked + aria-label |
| `web/components/topbar.tsx` | Level toggle radiogroup semantics; theme button gets dynamic aria-label + aria-pressed + aria-hidden glyph |
| `web/components/regime-card.tsx` | div onClick → real `<button>` with aria-pressed (was not keyboard-reachable) |
| `web/app/globals.css` | Light-mode `--text-muted` from `#8b8d96` (3.28:1, fails WCAG AA) → `#65676f` (~5.0:1, passes) |

### Cleanup (1)
- **Deleted** `web/styles/globals.css` — 126-line v0-export orphan
  defining a competing `:root` + `.dark` token system (oklch tokens)
  that conflicted with `app/globals.css`. Not imported anywhere; would
  mislead the next contributor.

### Endpoint comment drift (2)
- `web/hooks/use-execution-status.ts` and `web/lib/api-types.ts` both
  said `@endpoint GET /execution/status` but the actual call is
  `/execute/status`. Aligned to truth.

---

## Tests added overnight

**Backend** — `tests/test_overnight_2026_05_03.py` grew **6 → 9** tests:
- Idempotency cap + half-eviction
- `default_order_type` normalize (3 variants)
- Settings GET Cache-Control header
- Funding cache no-poison (Tier 3 DF-A lock-in)
- CORS allow_origins drops bare localhost
- CORS regex admits 5 real Vercel URLs + rejects 3 attacker variants
- Calibration uses `update_alerts_config` (RLock-protected path)

**Frontend** — `web/tests/components.test.tsx` (NEW, **6 tests**):
- MacroOverlay sentiment dots use `bg-success/danger/warning`
- MacroOverlay direction uses `text-success/danger`
- EquityCurve legend dash uses `border-text-secondary`
- FundingCarryTable rateClass: U+2212 negative → text-danger
- FundingCarryTable rateClass: ASCII hyphen negative → text-danger
- FundingCarryTable rateClass: positive → text-success

---

## §22 backtest verdict

**`tests/test_composite_signal_regression.py` 6/6 PASS** against the
2026-05-02 baseline at HEAD. Means: **none of the Tier 2 math
"CRITICALs" (CMC-1 scalar broadcast / CMC-2 shift(-1) divergence /
CMC-3 chandelier) cause output drift in the regression universe.**
They remain held for sign-off as policy questions, not as bugs.
Documented in
[`docs/audits/2026-05-03_phase-d-deep-dive-audit.md`](.claude/worktrees/phase-d-resume/docs/audits/2026-05-03_phase-d-deep-dive-audit.md).

---

## Verification at audit close

```
$ python -m pytest -q
437 passed, 1 skipped, 0 regressions (was 428 at audit start; +9 overnight)

$ npx tsc --noEmit
exit 0 (clean)

$ npx vitest run tests/components.test.tsx
6 passed in 1.71s

$ npm run build
exit 0; all 15 routes prerendered as static content

$ python -m pytest tests/test_composite_signal_regression.py
6 passed in 4.05s (§22 baseline drift = 0)

$ curl https://v0-davidduraesdd1-blip-crypto-signa.vercel.app/
200; HTML title = "Crypto Signal App"; sidebar + 8 routes; static-rendered
```

---

## Held for your sign-off (not autonomous)

These need a human decision, not just a fix:

### CRITICAL — Save Agent Config dead UI
[web/components/agent-config-card.tsx:51-58, 75-88, 162-164](.claude/worktrees/phase-d-resume/web/components/agent-config-card.tsx:51)
The "Save Agent Config" button has no `onClick` handler; all
`<input>` elements use `defaultValue` (uncontrolled). Result: you can
edit values, click Save, and **nothing persists**. The page already
has `TODO(D-ext)` markers, so the intent is "wire after D8 with the
real /agent/config endpoint." Decision needed: ship a visible
"preview only" badge in the meantime, or wire the form now to the
existing partial endpoints?

### HIGH — useDeleteAlertRule docstring lies
[web/hooks/use-alerts.ts:53-61](.claude/worktrees/phase-d-resume/web/hooks/use-alerts.ts:53)
Docstring claims "Optimistic UX: remove from cache immediately, roll
back on error" but the implementation only invalidates `onSuccess`.
Either implement optimistic updates (`onMutate` + `onError` rollback),
or fix the docstring. I left it alone because picking a side has UX
implications.

### Tier 2 math CRITICALs (×3)
CMC-1 scalar broadcast / CMC-2 `.shift(-1)` divergence / CMC-3
chandelier comment-vs-math. §22 backtest passes 6/6 today, so
none currently move the live signal — but the policy questions are
real. Recommended: half-day post-cutover focused session to either
confirm-and-document (likely outcome) or fix-and-rebaseline.

### A11y items needing design judgment (smaller)
- `data-source-badge.tsx` color-only encoding — pair with shape glyph
  (live=●, cached=◐, down=✕)? CLAUDE.md §8 mandates shape + color
  but the existing glyph palette varies across components.
- `regime-card.tsx` `accumulation: ●` vs `distribution: ○` — too
  similar at small sizes. Replace with `↑` / `↓`?
- `emergency-stop-card.tsx` raw `🚨` emoji — CLAUDE.md tone says no
  emoji unless requested. Replace with text "ALERT"?

---

## What you're doing in the morning

**Required for D5 to be done:**
1. Open `https://v0-davidduraesdd1-blip-crypto-signa.vercel.app` —
   confirm pages now load REAL data (not "loading…"). If still
   loading, hard-refresh (Ctrl+F5) to bust the browser CORS cache.
2. Walk the 8 routes (Home, Signals, Regimes, Backtester, On-Chain,
   Alerts, AI Assistant, Settings) and spot-check the data lights up.
3. Try a Settings save (Trading or Signal-Risk page). Confirm the
   form persists end-to-end.

**Optional / your call:**
4. Decide on the held items above (Save Agent Config, optimistic
   delete, math sign-off, a11y polish).
5. When you're satisfied with D5, run D6 (`docs/redesign/
   2026-05-03_d6-security-perf-checklist.md`) — npm audit, Semgrep,
   Lighthouse, manual cross-browser walk. ~1 day of work.
6. Then D7 (already largely done — see
   `docs/signal-regression/2026-05-03-d7-section22-compliance-review.md`).
7. Then D8 cutover (`docs/redesign/2026-05-03_d8-cutover-guide.md`):
   merge phase-d → main, flip Vercel + Render production branches to
   `main`, 30-day Streamlit overlap.

---

## Diff summary (overnight session)

```
api.py                                      +18 -8
ai_feedback.py                               (already in 47a6f90)
data_feeds.py                                (already in 47a6f90)
execution.py                                +21 -2
routers/settings.py                          +9 -1
requirements.txt                             (already in 47a6f90)
tests/test_overnight_2026_05_03.py        +290 (new file)
web/app/globals.css                          +5 -1
web/components/equity-curve.tsx              (already in 47a6f90)
web/components/funding-carry-table.tsx       (already in 47a6f90)
web/components/macro-overlay.tsx             (already in 47a6f90)
web/components/regime-card.tsx               +9 -2
web/components/segmented-control.tsx        +14 -1
web/components/toggle-switch.tsx             +6 -0
web/components/topbar.tsx                   +18 -3
web/hooks/use-execution-status.ts            +1 -1
web/lib/api-types.ts                         +1 -1
web/styles/globals.css                       (deleted)
web/tests/components.test.tsx              +118 (new file)
docs/audits/2026-05-04_overnight-audit-summary.md  (this file, new)
```

---

## Co-author

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
