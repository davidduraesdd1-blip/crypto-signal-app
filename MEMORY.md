# MEMORY.md — Crypto Signal App

Session continuity log. Newest entries on top. See master-template §16.

---

## 2026-04-28 — Redesign-2026-05 + audit baseline merged to main (PR #11)

**Merge commit:** `929a40f` — "Merge pull request #11 from
davidduraesdd1-blip/redesign/ui-2026-05-plotly".

**Scope (62 commits ahead of pre-sprint main):**
- Original redesign: ~30 commits porting the 2026-05 sibling-family
  design system (mockup ports, plotly template, sidebar+topbar,
  legacy widget removal).
- Audit-driven sprint: 30 commits closing P0 + P1 items from
  `docs/audits/2026-04-28-redesign-baseline.md`.
- 2 CI workflow hot-fixes for pip-audit flag bugs.

### P0 (21 items)
- ✓ 16 fixed (math, security/deploy, app correctness, ops, tests).
- ✗ 3 confirmed false positives during fix-time review:
  P0-3 (Gaussian Channel kernel — actually causal),
  P0-6 (cycle_score sign — formula correct),
  P0-8 (Sharpe annualization — `sqrt(365/avg_hold) = sqrt(trades/yr)`).
- ⊘ 1 closed as non-bug (P0-4 strategy_bias — duplicate derivation
  with identical logic; queued as P3 cleanup).
- ⏸ 1 deferred with rationale (P0-19 supervisor auto-start at
  module level — has import-time side effects on tests/CLI tools;
  needs explicit `ensure_supervisor_running()` helper called from
  app.py + scheduler.py instead).

### P1 (31 items)
- ✓ 29 fixed (TTLs, cache wrappers, cryptorank token-unlocks +
  VC fundraising, Dune Analytics, full design-system migration,
  XSS hardening, math correctness, data hygiene, ops, CI).
- ⊘ 1 already implemented (P1-29 pytrends — already in
  `cycle_indicators.fetch_google_trends_signal`; added a thin
  discoverability wrapper in `data_feeds.py`).
- ⏸ 1 deferred (P1-49 SHA-pinning Actions — Dependabot already
  configured for the actions ecosystem; auto-bumps cover the
  supply-chain risk).

### Test + deploy gates at merge time
- pytest: **45/45 pass in 2.35s** (was 42/42; +3 cryptorank smoke
  tests).
- `tests/verify_deployment.py --env prod`: **5/5 pass** against
  https://cryptosignal-ddb1.streamlit.app/.
- pip-audit: passing on HEAD (workflow flag bugs fixed in `c593250`
  + `ef2e9ec`).
- gitleaks / secret-scan: passing.
- 0 hardcoded API keys in `*.py`.
- 0 sub-11px font literals (§8 floor).
- ui_components hex literals: 307 → 143 (53% reduction; remainder
  intentional).
- §12 cache TTLs all match spec.
- Tap targets ≥44px desktop + mobile.

### Restore points (kept on origin)
6 backup tags from sprint start: `backup-pre-baseline-audit-2026-04-28-{
main, ui2026-05-parent, ui2026-05-p0fixes, ui2026-05-pagescss,
ui2026-05-plotly, ui2026-05-sidebarpolish}`.

### Audit docs landed
- `docs/audits/2026-04-28-redesign-baseline.md` — comprehensive
  baseline audit with P0/P1 fix lists.
- `docs/audits/2026-04-28-post-sprint-final.md` — post-sprint delta
  audit + verification matrix.

### Open follow-ups (low priority, none merge-blocking)
- Re-evaluate the 5 Dependabot pip PRs (fastapi 0.136.1, hmmlearn
  0.3.3, lightgbm 4.6, scikit-learn 1.8, statsmodels 0.14.6) +
  3 actions PRs.
- Wire `fetch_vc_funding_signal()` and `fetch_dune_query_result(...)`
  into `composite_signal.py` Layer 3 / Layer 4.
- Replace deferred P0-19 with explicit `ensure_supervisor_running()`
  helper in app.py + scheduler.py.
- Backfill known-correct fixtures for the 22 indicators per
  project §22 mandate.
- Save backtest regression baseline for
  `composite_signal.compute_composite_signal` per project §4 mandate.

### Resume point
**Sprint complete on main.** Ready to triage Dependabot PRs as the
next batch of work.

---

## 2026-04-23 — Deployment verification baseline (§25 Part A only)

**Context:** First automated smoke-test pass against live deploy
at https://cryptosignal-ddb1.streamlit.app/.

### Part A — automated smoke test

`python tests/verify_deployment.py --env prod` → **5/5 checks passed**
- base URL reachable (1.87s, HTTP 200)
- no Python error signatures in landing (clean)
- expected shell markers present (streamlit, <script, root)
- all pages render (0 configured — single-page app)
- health endpoint /_stcore/health (HTTP 200)

### Part B — manual 20-point walkthrough

**NOT YET RUN.** When walked, update this entry and record findings
to `pending_work.md` if any. Checklist at:
`../shared-docs/deployment-checklists/crypto-signal-app.md`

### Status

**Deploy: HEALTHY (Part A).** No automated blockers. Manual walkthrough
pending.

### Resume point

Part B manual walk is next baseline item. For feature work, see
`pending_work.md` if/when it exists.
