# MEMORY.md — Crypto Signal App

Session continuity log. Newest entries on top. See master-template §16.

---

## 2026-05-02 (D-ext) — D-extension endpoints landed

Closed the 4 endpoint gaps surfaced by the D4 code-wire plan
(`docs/redesign/2026-05-02_phase-d-d4-code-wire-plan.md` §3) so D4
ships zero `TODO(D-ext)` stubs:

- **PUT `/settings/trading`** — Trading tab persistence (pairs,
  timeframes, TA exchange, display preferences). Extends
  `routers/settings.py`; partial-update pattern matches the existing
  signal-risk/dev-tools/execution PUTs. GET `/settings/` now returns
  a `trading` group too.
- **POST `/exchange/test-connection`** — Wraps existing
  `execution.test_connection()` for the "Test OKX Connection" button.
  Returns 503 with operator guidance when keys are unset (frontend
  renders soft warning, not stack trace) per `feedback_empty_states`.
  New router `routers/exchange.py` mounted at `/exchange`.
- **GET `/diagnostics/circuit-breakers`** — Synthesizes the 7-gate
  Level-C agent safety status from `agent.get_agent_config()` +
  `execution.check_circuit_breaker()` + `agent.is_emergency_stop()`.
  Mockup labels exact, in mockup order. Powers the Settings · Dev
  Tools card.
- **GET `/diagnostics/database`** — SQLite WAL-mode row counts +
  size, powers the 5-col KPI strip on Settings · Dev Tools. Wraps
  existing `database.get_db_stats()`.

New router `routers/diagnostics.py` mounted at `/diagnostics`.

**Test count:** 26 passes (19 D1 + 7 D-ext) on `tests/test_api_routers.py`.
Full suite **347 pass / 1 skip** — no regressions.

**Mockup audit notes (informational only — already correct):**
- Mockup labels for the 7 gates locked verbatim into the response
  payload, so the frontend renders the same strings the user
  approved during D3.
- Cooldown gate currently always reports "inactive" — the agent
  pipeline doesn't yet log the cooldown timestamp. Noted as a
  follow-up; not blocking.
- Database health uses the existing `get_db_stats()` whitelist of 13
  table names. The mockup's "18 table counts" expander is rendered
  by the frontend with a "show all" affordance; the API returns the
  curated 8 most-relevant tables for the KPI strip.

---

## 2026-05-02 (later) — Phase D batch D2 landed

D2 (Render deploy of FastAPI + keep-alive) shipped on
`phase-d/next-fastapi-cutover`. Live at
**https://crypto-signal-app-1fsi.onrender.com**.

- Render free tier: 512MB RAM, 0.1 CPU, $0/mo, autodeploy from
  `phase-d/next-fastapi-cutover`, region oregon.
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
- Env: `CRYPTO_SIGNAL_ALLOW_UNAUTH=true` (D1 temporary; flip at D6
  once Next.js handles the X-API-Key); `ANTHROPIC_ENABLED=false`;
  `DEMO_MODE=true`; `PYTHON_VERSION=3.11`.
- IaC: `render.yaml` committed (834601f) — fresh Render account can
  reproduce the deploy in one click; secret env vars marked
  `sync: false` (set in dashboard, never in git).
- Keep-alive: cron-job.org (David's account) pings `/health` every
  10 min — eliminates the 50s cold-start the free-tier doc warns
  about. First ping scheduled 2026-05-02 18:50 PT.

**14 endpoints smoke-tested live, all 200:**
- `/health` returned in 263ms (warm); 29 of 33 OKX pairs live, 4
  stale (FLR/XDC/SHX/ZBCN — not on OKX, expected fallback per §10).
- `/openapi.json` confirms 36 total endpoints (22 existing + 14 new
  D1 paths / 15 operations).
- `/onchain/dashboard?pair=BTC-USDT` returned **real Binance data**
  in 4.4s: sopr=1.005, mvrv_z=-0.51, hash_ribbon=CAPITULATION,
  puell_signal=ACCUMULATION. Engine wrap is end-to-end live.
- Empty payloads on `/home/summary`, `/regimes/`, `/ai/decisions`
  are correct (no scan has run on this fresh Render instance —
  populates on first scan).

**Cost so far:** $0/mo. (Render free tier indefinite, cron-job.org
free tier indefinite, GitHub free.)

**Next blocking action — David:** D3 (interactive, ~2-3 days).
Subscribe to v0.dev Premium ($20/mo, cancellable end of D3),
then drive v0 to convert the 13 mockups in
`docs/mockups/sibling-family-crypto-signal-*.html` into Next.js +
Tailwind + shadcn/ui components. Export each generated page to
the `web/` directory via v0's GitHub panel as PRs against
`phase-d/next-fastapi-cutover`. Once all 8 pages are in `web/app/`,
ping me — D4 (Code wires Tanstack Query against the live FastAPI)
runs autonomously after.

Streamlit fallback unchanged at
https://cryptosignal-ddb1.streamlit.app/. Tag baseline
`redesign-ui-2026-05-shipped` -> 20587d2 still the rollback point.

### D2 commits
- 834601f chore(phase-d-2): add render.yaml infra-as-code blueprint

---

## 2026-05-02 (later) — Phase D batch D1 landed

D1 (FastAPI gap-fill, 6 new routers) shipped on
`phase-d/next-fastapi-cutover` off `main`. Existing 22 endpoints in
`api.py` untouched; 6 new routers add 15 endpoints for Home,
Regimes, On-Chain, Alerts CRUD, AI Assistant, Settings.

- 9 new modules: `routers/{__init__,utils,deps,home,regimes,onchain,
  alerts,ai_assistant,settings}.py`
- `api.py` minimal-touch: 6 `include_router` calls + CORS extended for
  `localhost:3000` (Next.js dev) + `*.vercel.app` regex (preview/prod)
  + PUT/DELETE methods (alerts/configure DELETE, settings PUTs)
- 19 new smoke tests in `tests/test_api_routers.py` (TestClient-based,
  network-hermetic via monkeypatch on `fetch_onchain_metrics`,
  `generate_signal_story`, `save_alerts_config`)
- pytest **340 passed, 1 skipped** in 40s (baseline 321 + 19 new = 340)
- §4 regression diff NOT required at D1 (presentation/transport only;
  composite_signal output unchanged) — runs at D7 per plan §6.

**Next blocking action — David:** D2 start. Create a free Render
account at https://render.com (no credit card), then provide the
deploy hook URL so Code can wire `render.yaml` + Cron-job.org
keep-alive. Streamlit fallback unchanged at
https://cryptosignal-ddb1.streamlit.app/.

---

## 2026-05-02 (later) — Phase D approved + handed off to Code

**Approvals locked** (David, via AskUserQuestion):
1. Framework pivot to Next.js + Tailwind + FastAPI: **Approved**
2. Cost arc ($0 → ~$20/mo build → $0 steady / shelf): **Approved**
3. Fold c-stabilization-sprint into Phase D: **Fold** (don't fix
   Streamlit code we're retiring)

**Plan:** `docs/redesign/2026-05-02_phase-d-streamlit-retirement.md`
(11 sections, D1-D8 batches, full architecture + cost + risks).

**D1 audit done in this session.** Discovery: existing `api.py` already
exposes 22 endpoints covering signals/backtest/weights/execution/
alerts-log/scan. **D1 work for Code is gap-fill, not from-scratch
scaffold** — 6 new routers (Home, Regimes, On-Chain, Alerts CRUD, AI
Assistant, Settings). Spec at
`docs/redesign/2026-05-02_d1-api-audit.md`.

**Hand-off to Code:** comprehensive briefing at
`docs/redesign/2026-05-02_phase-d-handoff-to-code.md`. Code resumes from
cold via §16 protocol; David's autonomy preference honored (no
mid-batch check-ins, escalate only on plan-scope deviation or §4
regression failure).

**David's blocking actions for Code (in order):**
- D2 start: create Render account, give Code the deploy hook
- D3: subscribe v0 Premium ($20), drive interactive generation, export
  to `web/` via GitHub panel
- D5 start: create Vercel account, connect GitHub repo
- D7: walk the preview deploy at 3 levels + 2 themes
- D8 final: verify Vercel production URL

### Phase D task list (8 batches, IDs 25-32)
- 25. D1 FastAPI gap-fill (Code, in flight after handoff)
- 26. D2 Render deploy (David + Code)
- 27. D3 v0 generation pass (David)
- 28. D4 Wire Next.js to FastAPI (Code)
- 29. D5 Vercel deploy (David + Code)
- 30. D6 Security + perf pass (Code)
- 31. D7 §4 regression + parity (Code + David)
- 32. D8 Cutover + 30-day Streamlit overlap (Code + David)

### Resume point

**Cowork session ends here.** Code on Windows resumes by reading
CLAUDE.md → MEMORY.md → phase-d-streamlit-retirement.md → d1-api-audit.md
→ phase-d-handoff-to-code.md, then starts D1 implementation on a fresh
`phase-d/next-fastapi-cutover` branch off `main`.

---

## 2026-05-02 — Post-deploy audit + Phase D pre-planning

**Context:** Phase C shipped to main 2026-05-01. Browser walk via
Claude in Chrome (Beginner level, dark theme, Home/Signals/Backtester
sampled) revealed 7 issues triaged into `c-stabilization-sprint`.

### Audit findings

| ID | Sev | Issue | Scope |
|---|---|---|---|
| C-fix-01 | CRIT | Topbar buttons render as wide-wrapped Streamlit defaults (~280px tall, text wraps mid-word: "Beginn / er", "Upda / te", "The / me") | All 8 pages |
| C-fix-02 | HIGH | Sidebar wordmark "Signal.app" wraps to two lines | Global sidebar |
| C-fix-03 | HIGH | Sidebar active-state lags page nav by one click | Global nav |
| C-fix-04 | HIGH | Signals timeframe strip shows 4 cells; mockup specifies 8 | Signals page |
| C-fix-05 | MED | Signals 30d / 1Y deltas show "—" instead of values | Signals hero |
| C-fix-06 | MED | Signals indicator tiles + Backtester KPI strip empty values | Data layer |
| C-fix-07 | LOW | Sidebar Glossary expander wraps awkwardly | Sidebar |

Full audit: `docs/redesign/2026-05-01_post-deploy-audit.md`. None touch
`composite_signal.py` — §4 regression diff not required for this batch.

### Re-examination — Streamlit framework mismatch

After 3 unsuccessful Code-driven attempts on C-fix-01, root cause
identified: Streamlit injects `primaryColor` at the inline-style level
which beats our CSS overrides. The mockups are already pixel-locked,
so the bottleneck isn't design — it's the framework fighting the
design. Decision queued: evaluate pivot to Next.js + Tailwind frontend
+ FastAPI backend (Path B) for Phase D.

### User priorities locked for Phase D

- **Cost:** $20-30/mo acceptable during build; must support "shelf
  mode" — pause-able to $0/mo if funds tighten without losing the
  build.
- **Domain:** keep `cryptosignal-ddb1.streamlit.app` (default
  Streamlit subdomain) for now; custom domain later.
- **Agents:** on-demand for now, but architect for future 24/7.
- **Secrets:** copy-paste OK; if there's a more secure / faster
  pattern, plan it in now.
- **Autonomy:** approve initial plan, then full autonomy through ship.

### Resume point

Phase D draft pending at
`docs/redesign/2026-05-02_phase-d-streamlit-retirement.md`. Sequence:
(1) §5 research pass on v0 / Lovable / Bolt.new for mockup-to-code
conversion, (2) draft plan with batch sequence + cost-architecture +
shelf-mode wiring, (3) user approval, (4) execute (Code-driven).

`c-stabilization-sprint` may be **folded into Phase D** rather than
shipped standalone — folding avoids fixing Streamlit CSS we're about
to retire.

---

## 2026-05-01 — Phase C: redesign-2026-05 shipped to main (29 commits)

**Tag baseline:** `redesign-ui-2026-05-shipped` → `20587d2`.
**Deploy:** https://cryptosignal-ddb1.streamlit.app/ — green.

### Scope (C1-C11 batches)

11 sequential batches per
`docs/redesign/2026-04-29_phase-c-implementation-plan.md`, handed off
to Claude Code on the Windows side after Linux-mount file-truncation
issues on multi-line edits to large Python files (sidebar.py 1346
lines).

- C1: Sidebar architecture (8 nav items, rail 240→150px, brand
  block, glossary popover)
- C2: Topbar (level-group, refresh/theme buttons, layout primitives)
- C3: Signals page (8-cell timeframe strip, hero card, indicator
  tiles)
- C4: Backtester (primary `[Backtest][Arbitrage]` + secondary
  `[Summary][Trade History][Advanced]` segmented controls)
- C5: Regimes (8 regime cards + selected state)
- C6: On-Chain (3 per-card swap dropdowns)
- C7: Alerts (Configure + 10-row History log)
- C8: AI Assistant (12 sections + Recent Decisions log)
- C9: Settings (Signal-Risk + Dev-Tools + Execution sub-pages)
- C10: Mobile defenses — universal `min-width: 0`, `max-width: 100vw`,
  `overflow-x: hidden`, `minmax(0, 1fr)` on all grid columns,
  `min(640px, 100%)` subtitle cap
- C11: Plotly template alignment + legacy widget removal

### Verification at merge

- pytest: **88/88 pass** (carried from 2026-04-28 follow-ups; no
  regressions added by C-batches)
- `tests/verify_deployment.py --env prod`: **5/5 pass** (HTTP,
  content, pages, health, error-free)
- Manual desktop walk: above-fold content rendering on all 8 pages
- Manual mobile walk (post nuclear-defense fixes): no horizontal
  overflow on iPhone-class viewport

### Known issues at merge → triaged 2026-05-02

7-item `c-stabilization-sprint` queued from post-deploy browser walk
(see entry above).

---

## 2026-04-29 to 2026-05-01 — Phase B: 13 mockups across 6 batches

**Output:** 13 HTML mockups in
`docs/mockups/sibling-family-crypto-signal-*.html` covering all 8
pages + sub-views. Design tokens locked, mobile defenses validated
against iPhone-class viewport.

### Mockup inventory (13 files)

1. `sibling-family-crypto-signal.html` (Home, ~24KB)
2. `-SIGNALS.html` (8-cell timeframe strip + More+28 dropdown)
3. `-BACKTESTER.html` (primary `[Backtest][Arbitrage]` + secondary
   `[Summary][Trade History][Advanced]`)
4. `-BACKTESTER-ARBITRAGE.html` (Arbitrage view)
5. `-REGIMES.html` (8 regime cards + selected-state + More+25)
6. `-ON-CHAIN.html` (3 per-card swap dropdowns)
7. `-ALERTS.html` (Configure)
8. `-ALERTS-HISTORY.html` (10-row alert log)
9. `-AI-ASSISTANT.html` (12 sections + Recent Decisions log)
10. `-SETTINGS.html` (overview)
11. `-SETTINGS-SIGNAL-RISK.html`
12. `-SETTINGS-DEV-TOOLS.html`
13. `-SETTINGS-EXECUTION.html`

### Design system locked

- **Sibling-family palette:** signal-green `#22d36f` (this app),
  flare-blue `#1d4ed8` (DeFi sibling), rwa-amber `#d4a54c` (RWA
  sibling). One accent per app, all share neutrals.
- **Tokens:** `--rail-w: 150px`, `--topbar-h: 56px`, `--bg`, `--card`,
  `--text-primary`, `--text-muted`, `--border`, `--accent`.
- **Mobile defenses (lessons from C10):** `* { min-width: 0 }`,
  `html, body { max-width: 100vw; overflow-x: hidden }`,
  `.app { max-width: 100vw; overflow-x: hidden }`,
  `minmax(0, 1fr)` on all grid template columns,
  `min(640px, 100%)` on hero subtitles.
- **Tap targets:** ≥44px desktop + mobile.
- **No sub-11px font literals** (§8 floor).

### Per-batch sign-off

Six batches, each with `looks great` / `love this` style approvals.
Final: "the mobile is good as well" + "ok everything looks go move on
to the next step" → Phase C handoff to Code.

---

## 2026-04-29 — Phase A: page + tab inventory + UX research

**Outputs:**
- `docs/redesign/2026-04-29_page-and-tab-inventory.md` — all 8 pages
  cataloged, sub-views enumerated, Q1-Q10 resolutions documented.
- `docs/redesign/2026-04-29_ux-research-tab-vs-flat.md` — 35-source
  synthesis recommending hybrid pattern (sidebar = top-level nav,
  in-page segmented controls for sub-views).

### Q1-Q10 resolutions

- **Q1** mockups revisable mid-Phase-B
- **Q2** worktrees → per-app folder migration
- **Q3-Q7** option a across the board (sidebar 8 items, topbar
  level-group + refresh/theme, segmented controls for sub-views)
- **Q8** option b
- **Q9** active state on sidebar
- **Q10** per-app folder structure

### UX research outcome

35 sources surveyed: Streamlit docs, Next.js dashboards, fintech
patterns (Bloomberg Terminal, Glassnode, Messari), Plotly Dash
examples, Material/HIG/Carbon design system specs. Recommendation:
**hybrid** — sidebar for app-level nav (8 items), segmented control
in-page for sub-views (Backtester primary/secondary, Settings 4 tabs).

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
