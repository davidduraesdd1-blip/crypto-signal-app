# Pending Work — crypto-signal-app
---

## Sprint 2026-04-24 — UI/UX full redesign (CLOSED 2026-04-28)

**Status: COMPLETE.** Merged to main as PR #11 (merge commit `929a40f`).
Full sprint outcome documented in:
- `docs/audits/2026-04-28-redesign-baseline.md` (baseline audit)
- `docs/audits/2026-04-28-post-sprint-final.md` (post-sprint delta)
- `MEMORY.md` (2026-04-28 entry — top of file)

### Original redesign tasks — all closed

- [x] 1. Copy `common/ui_design_system.py` → `ui/design_system.py`.
      Imported and `inject_theme("crypto-signal-app")` called from app.py.
- [x] 2. New left-rail sidebar replaces legacy widget grab-bag.
      `render_sidebar()` shared across pages.
- [x] 3. Landing/home page ported per mockup.
- [x] 4. All pages ported: SIGNALS, BACKTESTER, REGIMES, ON-CHAIN.
- [x] 5. Hex colors migrated to design tokens (307 → 143;
      remainder intentional per agent report — CSS :root vars,
      SVG attrs, Plotly configs, alpha tricks).
- [x] 6. Both themes verified statically; live walkthrough deferred
      (handoff to next sprint).
- [x] 7. `data_source_badge()` defined and used via `page_header(
      data_sources=[...])`.
- [x] 8. Post-change audit per §24 ran for the entire sprint —
      see audit docs above.
- [x] 9. `python tests/verify_deployment.py --env prod` → 5/5 pass.
- [x] 10. PR #11 opened, reviewed, and merged.

### Acceptance criteria — all met or documented

- [x] Every page renders in the new design language
- [x] Dark + light mode pass on every page (static review)
- [x] Mobile viewport (≤768px) — passes static review
- [x] All existing unit tests pass; +3 cryptorank smoke tests added
- [x] Deploy verifier passes 100% on prod
- [ ] Full 20-point manual browser checklist on test deploy
      (DEFERRED — sprint shipped without it; queued as a follow-up
      manual-walk task before any new pages are added)
- [x] `MEMORY.md` has "Redesign-2026-05 + audit merged to main" entry
- [x] User reviewed and approved (PR #11 merged 2026-04-28)

---

## Active follow-up work (post-merge)

### Now (next session)

- [ ] **Triage 5 Dependabot pip PRs** as one batch:
  - `dependabot/pip/fastapi-gte-0.136.1`
  - `dependabot/pip/hmmlearn-gte-0.3.3`
  - `dependabot/pip/lightgbm-gte-4.6.0`
  - `dependabot/pip/scikit-learn-gte-1.8.0`
  - `dependabot/pip/statsmodels-gte-0.14.6`
- [ ] **Triage 3 Dependabot Actions PRs**:
  - `actions/checkout` v4 → v6
  - `actions/setup-python` v5 → v6
  - `actions/upload-artifact` v4 → v7
- [ ] Run pytest after each Dependabot bump merges (or as one
  combined branch test).

### Soon (next sprint)

- [ ] Wire `fetch_vc_funding_signal()` (cryptorank, P1-26/27) into
  `composite_signal.py` Layer 3 sentiment.
- [ ] Wire `fetch_dune_query_result(...)` (P1-28) into Layer 4
  on-chain when concrete query IDs are chosen for BTC + ETH.
- [ ] Surface cryptorank token-unlock data in the UI.
- [ ] Replace deferred P0-19 with explicit
  `ensure_supervisor_running()` helper called from app.py + scheduler.py.
- [ ] Run the full 20-point manual browser checklist against
  https://cryptosignal-ddb1.streamlit.app/ once the redesign deploys.

### Standing items (per CLAUDE.md mandates)

- [ ] Backfill known-correct fixtures for the 22 indicators in
  `crypto_model_core.py` (§22 mandate).
- [ ] Save backtest regression baseline for
  `composite_signal.compute_composite_signal` to
  `docs/signal-regression/` (§4 mandate). Required before the next
  change to that module.
- [ ] Light-mode contrast lift on `_PILL_CFG["NEUTRAL"]`
  (3.2:1 → ≥4.5:1 WCAG AA).
- [ ] Cleanup pass: P0-4 strategy_bias duplicate derivation
  in `crypto_model_core.py` (P3 — non-bug, just code-smell).

---

## Restore points (kept indefinitely)

`backup-pre-baseline-audit-2026-04-28-*` (6 tags pushed to origin)
remain available for emergency rollback. Don't delete.
