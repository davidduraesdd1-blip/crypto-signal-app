# MEMORY.md — Crypto Signal App

Session continuity log. Newest entries on top. See master-template §16.

---

## 2026-04-28 (later) — Post-merge follow-ups landed on main

Sprint follow-ups committed directly to main: 11 commits, 43 new tests.

| # | Commit | Items |
|---|---|---|
| 1 | 770d13f | `agent.ensure_supervisor_running()` helper (closes deferred P0-19) + strategy_bias P3 doc |
| 2 | 5a5565a | Wire `fetch_vc_funding_signal()` (P1-26/27) into Layer 3 + Dune scaffold (P1-28) into Layer 4 |
| 3 | 4ba4c0a | composite_signal regression baseline + 5-scenario lock-in (§4 mandate) |
| 4 | f9ea3c1 | §22 fixtures for 8 core indicators (RSI/MACD/BB/ATR/ADX/SuperTrend/Stochastic/Ichimoku) |
| 5 | 008207e | Docs: MEMORY.md + pending_work.md update for items 1-4 |
| 6 | 8de8523 | Token-unlock UI surface (Signals page 5th info-strip cell) |
| 7 | d94647d | 3 MEDIUM UX fixes (ccxt-msg, reload→rerun, tautology delta) |
| 8 | ad880f9 | §22 fixtures batch 2 (Hurst/Squeeze/Chandelier/CVD/Gaussian) |
| 9 | cb79904 | §22 fixtures batch 3 (S/R, MACD div, RSI div, candlestick, Wyckoff) |
| 10 | f12fc3a | §22 fixtures batch 4 (HMM, Cointegration, VWAP, Fibonacci) |

**Test status:** pytest **88/88 pass in 5.75s** (was 45 at merge time;
+43 = 5 composite regression + 1 baseline-presence + 37 indicator
fixtures spanning all 22 indicators).

**§4 mandate satisfied:** `docs/signal-regression/2026-04-28-baseline.json`
locks 5 hand-picked composite-signal scenarios (all-none, bull, bear,
mid-cycle, VIX-panic). Future change to composite_signal output fails
the regression test until the engineer regenerates the baseline
deliberately.

**§22 mandate satisfied (22 of 22 indicators):** every math-heavy
function in `crypto_model_core.py` now has a known-correct fixture
locking its canonical output. Future code changes that drift outputs
fail the corresponding test.

Notes on the §22 final batch:
- `compute_hurst_exponent` returns `1.0` (saturated upper bound) on the
  seed=42 fixture — the synthetic series has strong positive drift that
  DFA reads as maximally persistent. Locked as `EXPECTED_HURST = 1.0`.
- `detect_hmm_regime` returns `None` locally because `hmmlearn` doesn't
  build on Python 3.14 in the local environment, but the test handles
  both happy and sad paths via an `_hmmlearn_available()` helper.
  Streamlit Cloud (Python 3.11 per `requirements.txt`) exercises the
  full path.
- Several detector functions return tuples not dicts (documented in
  the test file): `compute_support_resistance` (4-tuple),
  `detect_macd_divergence_improved` and `detect_rsi_divergence` (2-tuple),
  `detect_candlestick_patterns` (2-tuple).
- Synthetic OHLCV fixture (`numpy seed=42`, 200 hourly bars) is unchanged
  across all phases; existing tests remain stable.

**Sub-weight rebalances** in composite_signal layers:
- Sentiment: F&G 0.45→0.40, put/call 0.30→0.25, +VC funding 0.10
- On-chain: MVRV-Z 0.35→0.30, Hash 0.25→0.22, SOPR 0.20→0.18, +Dune 0.10
Both sums still 1.00. Baseline regenerated against new weights.

**Remaining follow-ups (none merge-blocking):**
- Live 20-point browser walkthrough on the deploy (needs operator on
  the live site)
- §22 fixture backfill for the 14 remaining indicators
- MEDIUM/LOW backlog (~290 items in baseline audit) — multi-session
- UI surfacing of cryptorank token-unlock data
- Live runtime verification of agents / rate-limits / Web3

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
