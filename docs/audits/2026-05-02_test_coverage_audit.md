# Test Coverage Audit — Crypto Signal App

**Date:** 2026-05-02
**Auditor:** Claude (Opus 4.7, 1M)
**Scope:** Per CLAUDE.md §4 + §24 — every Python source module, every
feature surface, every user level, dark + light mode parity.
**Source-of-truth context:** legacy-look audit in progress
(`docs/audits/2026-05-02_legacy-look-audit-in-progress.md`) is the
upcoming fix-sprint driver.

---

## 1. Executive Summary

- **264 tests collected** across 22 test files. **All pass** in **9.53s**
  (full suite), **7.02s** (fast tests). Well under the 30s §24 target.
- **0 tests** are tagged `@pytest.mark.slow`. **0 xfails**, **2
  conditional skips** (baseline-missing in regression test, optuna-not-
  installed in optimizer test).
- **The test suite is heavily UI-static** (regex grep against `app.py`
  source). It is structurally robust against text-marker regression but
  does **not** exercise:
    - Streamlit AppTest end-to-end runs (none configured).
    - Any direct unit test for **15 of 25** core source modules.
    - **Theme parity** (dark vs light) — zero coverage.
    - **User-level rendering** behavior — only static branch-existence
      checks; no rendered-output diff per level.
- **The biggest gap by line count:** `crypto_model_core.py` (5879 LOC),
  `data_feeds.py` (8464 LOC), `database.py` (3671 LOC), `ui_components.py`
  (4829 LOC), `top_bottom_detector.py` (1999 LOC). Together that's
  **24,842 LOC = 68% of total source** (36,430 LOC). Coverage on these
  is partial-to-thin.

---

## 2. Pytest Run — Real Output

### 2.1 Full test suite (`pytest tests/ -x --no-header --tb=no -q`)

```
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 81%]
................................................                         [100%]
264 passed in 9.53s
```

### 2.2 Fast tests only (`pytest tests/ -m "not slow" --no-header --tb=no -q`)

```
........................................................................ [ 27%]
........................................................................ [ 54%]
........................................................................ [ 81%]
................................................                         [100%]
264 passed in 7.02s
```

### 2.3 Slow tests (`pytest tests/ -m "slow" --collect-only -q`)

```
no tests collected (264 deselected) in 4.50s
```

**Finding:** §24 lists ML tests as `@pytest.mark.slow` candidates, but
no test is currently marked. ML tests effectively don't exist (no
`ml_predictor` direct tests).

---

## 3. Module-by-Module Coverage Matrix

Coverage % is a **structural estimate** — a dedicated test file gets
~50% credit; a smoke parse-only test gets ~5%; multiple
behavioural+regex tests get ~70%. Pure unit-tested public functions
get higher.

| Module | LOC | Tested by | Coverage est. | Critical gaps |
|---|---|---|---|---|
| `agent.py` | 1364 | `test_agent_c5.py` (8 tests, mostly C5 + DB plumbing) | **~25%** | Agent main loop, retry logic, multi-step LangGraph workflow, error swallowing, prompt construction |
| `ai_feedback.py` | 616 | none direct (touched only via composite tests) | **~5%** | Outcome resolution loop, weight-update math, IC calculation, drawdown decay |
| `alerts.py` | 484 | `test_alerts_c6.py` (13 tests) — schema + log_alert_fire + email dispatch hooks | **~50%** | Telegram/Discord channel adapters, throttle/dedupe, retry on transient failure |
| `allora.py` | 291 | none | **~0%** | All Allora API calls, weight blending, fallback path |
| `api.py` | 866 | none | **~0%** | FastAPI routes (project notes say "not yet wired" — but config flag still loads) |
| `arbitrage.py` | 472 | `test_segmented_control.py` (only references "arbitrage" as a nav key); no direct tests | **~3%** | Spot-spread builder, Buy On / Sell On column population (Image 5), funding-rate parser (Image 7), Hyperliquid binding |
| `chart_component.py` | 452 | none | **~0%** | OHLCV chart renderer, sparkline cache, theme-aware colors |
| `circuit_breakers.py` | 317 | none | **~0%** | Drawdown breaker, max-position breaker, kill-switch path, persistence |
| `composite_signal.py` | 1194 | `test_composite_signal_regression.py`, `test_composite_fallback.py`, `test_composite_learned_weights.py`, `test_composite_weight_optimizer.py`, `test_smoke.py` (parse) | **~65%** | Regime-conditional weight switching corner cases; new layer additions; multi-timeframe agreement gating |
| `composite_weight_optimizer.py` | 311 | `test_composite_weight_optimizer.py` (9 tests, optuna-gated) | **~60%** | Long Optuna runs (optuna `pytest.importorskip`); persistence to `optuna_studies.sqlite` |
| `crypto_model_core.py` | **5879** | `test_indicator_fixtures.py` (37 tests on 22 indicators), `test_regime_history_c8.py` (5 refs) | **~25%** | Vast: scan orchestration, risk-tier filtering, exchange fallback chain wiring, `fetch_chart_ohlcv`, `robust_fetch_ohlcv`, `run_feedback_loop`, `run_backtest`, regime detector behaviour, MTF agreement logic, on-chain composite |
| `cycle_indicators.py` | 407 | none direct (CLAUDE.md §22 specifically calls this out) | **~0%** | Cycle-indicator math (Pi-cycle top, MVRV-Z derived, etc.) — §22 SAYS each function should have a fixture; **none exist** |
| `data_feeds.py` | **8464** | `test_smoke.py` (3 cryptorank tests + parse), `test_data_wiring.py` (29 tests, mostly app.py-static checks invoking `data_feeds.*`), `conftest.py` (fixtures) | **~15%** | OHLCV cascade chain (OKX→Kraken→CoinGecko), Glassnode binding, `fetch_prices_cascade`, geo-block detector, funding-rate Hyperliquid parser, exchange-instance acquisition, on-chain `get_onchain_metrics`, news_sentiment hooks |
| `database.py` | **3671** | `test_alerts_c6.py` (alerts_log schema), `test_agent_c5.py` (agent_runs/agent_outputs tables), `test_regime_history_c8.py` (regime_history table) | **~15%** | Most tables (signals, scans, trades, paper_trades, slippage, feedback, weights, optuna_studies); migration / DDL drift detection; vacuum / pruning; `state_persistence` writes other than the audited widget keys |
| `execution.py` | 1108 | `test_agent_c5.py` (1 ref) | **~5%** | Order-placement flow, paper-trade engine, slippage modelling, cancel/replace, partial-fill handling, exchange-specific quirks |
| `llm_analysis.py` | 511 | none | **~0%** | Anthropic client wrapping, prompt caching, token-budget enforcement, fallback when ANTHROPIC_ENABLED=False |
| `ml_predictor.py` | 723 | none | **~0%** | LightGBM/XGBoost training, feature builder, persistence, lazy-load on Streamlit Cloud — §24 calls out cold-start verification specifically |
| `news_sentiment.py` | 477 | none | **~0%** | CryptoPanic adapter, sentiment scoring, fallback when CRYPTOPANIC_API_KEY missing, dedup of repeated headlines |
| `pdf_export.py` | 346 | `test_smoke.py` (parse only) | **~5%** | Layout, image embedding, multi-page handling, Unicode safety |
| `risk_metrics.py` | 511 | none direct (CLAUDE.md §22 calls this out) | **~0%** | Sharpe / Sortino / max-DD / VaR — §22 SAYS each should have a fixture; **none exist** |
| `scheduler.py` | 258 | `test_data_wiring.py` (autoscan bootstrap checks) | **~30%** | APScheduler job registration drift, missed-window catch-up, persistence |
| `top_bottom_detector.py` | **1999** | `test_smoke.py` (parse only) | **~5%** | The whole top/bottom signal engine — §22 explicitly names this as math-heavy needing fixtures |
| `ui_components.py` | **4829** | indirect via `test_topbar_polish.py`, `test_sidebar_nav.py`, `test_segmented_control.py`, `test_dashboard_c10.py`, `test_level_variants_c9.py` (all static against `app.py` or specific helpers) | **~20%** | Nearly all card components, theme-toggle internals, narrow-viewport behaviour, ds-card shells, status pills, empty-state copy, multiselect tag styling |
| `websocket_feeds.py` | 320 | `test_data_wiring.py` (sparkline-fallback test refs) | **~10%** | OKX SWAP ticker handler, reconnect-on-drop, pairs-without-perpetuals fallthrough (the very bug C-fix-16 fixed) |
| `whale_tracker.py` | 560 | none | **~0%** | All whale-detection logic, on-chain transfer parser, ambiguous "offline vs no whales" empty state (Image 8 issue) |

### 3.1 Modules with **zero** direct test coverage (10 of 25)

These are the highest-risk modules:

1. `ai_feedback.py` — feedback loop drives weight updates; silent
   regressions here corrupt every subsequent backtest.
2. `allora.py` — third-party signal blender.
3. `api.py` — future headless API surface; if accidentally enabled in
   prod, no tests catch breakage.
4. `chart_component.py` — visible regression risk; theme-aware.
5. `circuit_breakers.py` — risk-control critical; failure here =
   uncapped drawdowns.
6. `cycle_indicators.py` — §22 explicitly mandates fixture coverage; none.
7. `llm_analysis.py` — no fallback verification, no cache-key sanity.
8. `ml_predictor.py` — §24 cold-start spec; no test.
9. `news_sentiment.py` — Layer 3 sentiment input; silent failures
   produce neutral=0 forever.
10. `risk_metrics.py` — §22 explicitly mandates fixture coverage; none.
11. `whale_tracker.py` — Layer 4 input + the Image 8 ambiguous empty
    state.

`arbitrage.py` is on the bubble — it has no direct tests but does
have one indirect reference. Counts as **~3%** above.

---

## 4. Image-1-through-8 Issue-Surface Coverage

This maps the legacy-look audit findings against existing tests:

| Image | Issue | Existing test? | Notes |
|---|---|---|---|
| **1** | Hero card cascade (XDC/SHX/ZBCN show "—" — same root cause as C-fix-19 but on a separate code path) | **NO** | `test_data_wiring.py::test_watchlist_uses_rest_cascade_for_price_fallback` covers the watchlist path only. Hero-card path on `page_dashboard` is untested. |
| **2** | Signals XRP top — clean | n/a (no bug) | |
| **3** | Signals XRP lower — ATR shows "$0" instead of "—" | **NO** | Formatter consistency for empty-state numerics is untested. |
| **4** | Regimes timeline truncated to "Regim" / bright-green pills | **PARTIAL** | `test_regime_history_c8.py` covers schema; `test_topbar_polish.py` checks topbar pill labels but not regime page pair-pills. Bright-green token usage has zero tests. |
| **5** | Arbitrage Buy On / Sell On all "—" when no arb | **NO** | `arbitrage.py` has no direct tests at all. |
| **6** | Bright-green Load Rates button + duplicated description + plain expander | **NO** | No `arbitrage.py` tests; no bright-green token-usage test; no ds-card-shell coverage check. |
| **7** | Hyperliquid funding rate parser broken / Binance/Bybit/KuCoin "None" instead of "geo-blocked" | **NO** | Funding-rate parser has zero tests. Geo-block detector has zero tests. |
| **8** | Topbar narrow-viewport wrapping ("Updat e", "Them e") | **PARTIAL** | `test_topbar_polish.py::test_overrides_css_has_intermediate_viewport_breakpoint` checks the `@media (max-width: 1200px)` rule and inner `<p>` nowrap exists. **It does not verify rendered behavior at narrow widths.** |
| **8** | Bright-green Update button | **NO** | No assertion that the topbar Update button uses `--accent-soft` instead of `--accent` filled chip. |
| **8** | Sidebar "Legal (Internal Beta)" wrapping | **NO** | No test for sidebar item label-overflow inside the 150px rail. (`test_sidebar_nav.py::test_brand_wordmark_uses_nowrap_inside_150px_rail` covers brand only.) |
| **8** | On-chain card slots all blank despite "live" pills | **PARTIAL** | `test_data_wiring.py::test_onchain_page_falls_back_to_data_feeds_get_onchain_metrics` checks the fallback wiring **exists**; no test verifies the `_oc.get("net_flow")` adapter actually returns non-empty on a real fixture. |
| **8** | Whale Activity ambiguous empty state | **NO** | `whale_tracker.py` has no tests; copy-truthfulness untested. |
| **All** | Empty-state truthfulness ("None" / "—" / silent vs "geo-blocked" / "rate-limited" / "run a scan") | **NO** | Zero direct coverage. Some tests check for specific strings ("No backtest results yet", "No backtest run yet") but no systematic coverage. |

---

## 5. Theme-Parity Coverage (Dark vs Light Mode)

**Finding: ZERO direct theme-parity tests.**

- `test_topbar_polish.py::test_render_top_bar_uses_on_click_callbacks`
  asserts the theme button uses `on_click=_on_topbar_theme` — i.e.
  **the trigger exists**.
- No test verifies that:
    - Each card renders with appropriate background tokens in both modes.
    - WCAG AA contrast minimums are met (CLAUDE.md §8 mandates this).
    - Chart colors swap correctly (matplotlib/plotly default to dark
      backgrounds; light mode requires explicit overrides).
    - Status-pill / signal-badge colors stay shape-encoded
      (▲/▼/■) per §8 accessibility rule.

Risk: a refactor that only tests in one mode passes CI. Light mode
regressions only surface in manual review.

---

## 6. User-Level Scaling Tests (Beginner / Intermediate / Advanced)

**Existing coverage** (8 test files reference user_level / Beginner /
Intermediate / Advanced):

- `test_user_level_persistence.py` (5) — session-state default,
  invalid-value rejection, capitalization, page reads.
- `test_level_variants_c9.py` (4) — verifies all 3 branches **exist** in
  `page_signals` / `page_regimes` / `page_onchain` source, and contain
  level-distinct strings (e.g. "wait-and-see zone" for Beginner,
  "RSI(14)" for Advanced).
- `test_topbar_polish.py` — unified Update label across levels.
- `test_segmented_control.py` — used in level switching.
- `test_settings_c7.py` — Settings tab labels.

**Gaps:**
- No test verifies that the **rendered output** at each level differs as
  expected (just that the source contains 3 branches).
- No test for tooltip visibility scaling (always-visible Beginner →
  on-demand Intermediate → collapsed Advanced).
- No test for plain-English-vs-jargon ratio in error messages by level
  (CLAUDE.md §8 mandates error message detail scales with level).
- No test for `page_dashboard` / `page_alerts` / `page_backtest` /
  `page_config` level-aware variations beyond the topbar refresh label.

---

## 7. Skip / xfail / Flaky Inventory

**No xfail tests.**

**Conditional skips (2):**
- `tests/test_composite_signal_regression.py:45` — `pytest.skip` if
  baseline JSON missing at `docs/signal-regression/baseline.json`.
- `tests/test_composite_signal_regression.py:72` — `pytest.skip` per
  scenario if missing from baseline.
- `tests/test_composite_weight_optimizer.py:120` — `pytest.importorskip("optuna")`.

**Env-specific skip (no marker, just `return`):**
- `tests/test_data_wiring.py:169` — `test_sg_cached_ohlcv_returns_list_of_lists_at_runtime`
  silently `return`s if `app` already in `sys.modules`. **This is a
  hidden no-op skip** — looks pass-green but never asserts the
  behavior. Should be marked properly or restructured.

**No tests are marked `@pytest.mark.slow`.** §24 calls out ML tests
specifically as slow-marked candidates, but none exist in the first
place.

**No tests appear flaky** — the suite ran clean back-to-back and there
are no time-based assertions in the existing tests (they use static
file regex against `app.py`).

---

## 8. New Test Files Needed for the Legacy-Look Fix Sprint

One test file per Image-1-through-8 fix bucket, plus systemic coverage:

### Priority 1 — Functional (data-binding) bugs in flight

| # | New test file | Purpose | Image |
|---|---|---|---|
| 1 | `tests/test_hero_card_cascade.py` | Hero cards (XDC/SHX/ZBCN) on `page_dashboard` route through `_sg_cached_live_prices_cascade` and fall back to sparkline last-close. | 1 |
| 2 | `tests/test_arbitrage_buy_sell_on.py` | Arbitrage Spot-Spread table populates `Buy On` (min-price exchange) and `Sell On` (max-price exchange) even when `Signal == NO_ARB`. | 5 |
| 3 | `tests/test_funding_rate_parser.py` | Hyperliquid funding-rate parser returns non-zero for sample fixture; geo-blocked exchanges return labelled "geo-blocked" not "None". | 7 |
| 4 | `tests/test_onchain_data_binding.py` | Glassnode + Native RPC bindings: when status pills say "live", the data dict actually populates the card slots; when source is rate-limited, status pill flips to truthful label. | 8 |
| 5 | `tests/test_whale_tracker_empty_state.py` | Whale Activity resolves to one definite state; copy says "tracker offline" XOR "no whales in 24h" never both. | 8 |

### Priority 2 — Visual / token consistency

| # | New test file | Purpose | Image |
|---|---|---|---|
| 6 | `tests/test_accent_token_usage.py` | No `kind="primary"` button outside whitelisted CTAs; multiselect tag chips use `--accent-soft`; active pair pills use `--accent-soft`. | 4, 6, 7, 8 |
| 7 | `tests/test_ds_card_shell_coverage.py` | Funding Rate Monitor + Hyperliquid DEX expanders + arbitrage controls live inside a `ds-card` shell. | 6 |
| 8 | `tests/test_narrow_viewport_topbar.py` | Topbar Update + Theme buttons collapse to icon-only or truncate-with-ellipsis below ~600px (CLAUDE.md §8 mobile breakpoint). Render via Streamlit AppTest with viewport hint, OR static check that nowrap+ellipsis CSS rules cover all three button selectors. | 8 |
| 9 | `tests/test_sidebar_legal_no_wrap.py` | Sidebar nav items (especially "Legal (Internal Beta)") use single-line truncation with help-tooltip overflow; never wrap mid-word vertically. | 8 |

### Priority 3 — Empty-state truthfulness systemic

| # | New test file | Purpose |
|---|---|---|
| 10 | `tests/test_empty_state_truthfulness.py` | Sweeps every "—" / "None" / "—%" usage in `app.py` + `ui_components.py`; assert each is paired with either a status-pill label or a CTA card. Add allowlist for whitelisted "data not yet" cases. |
| 11 | `tests/test_atr_zero_vs_dash.py` | Specifically: ATR formatter renders "—" not "$0" when source value is unavailable. (Image 3 nit.) |

### Priority 4 — Theme + level (overdue gap fill)

| # | New test file | Purpose |
|---|---|---|
| 12 | `tests/test_theme_parity.py` | For each ds-card style, verify both `--bg-card-dark` and `--bg-card-light` paths exist and tokens swap. Verify chart components honor theme. |
| 13 | `tests/test_user_level_render_diff.py` | Beyond branch-existence, render Beginner / Intermediate / Advanced via a fake-Streamlit harness (like `test_segmented_control.py`) and assert the **output strings differ** in expected ways (jargon ratio, tooltip presence, raw-number visibility). |

### Priority 5 — Long-overdue §22 / §24 mandated fixtures

| # | New test file | Purpose |
|---|---|---|
| 14 | `tests/test_cycle_indicators_fixtures.py` | §22-mandated fixture coverage — Pi-cycle top, MVRV-Z derived, etc. Each function with a known-correct golden value. |
| 15 | `tests/test_risk_metrics_fixtures.py` | §22-mandated fixture coverage — Sharpe, Sortino, max-DD, VaR against a synthetic equity curve. |
| 16 | `tests/test_top_bottom_detector_fixtures.py` | §22-mandated coverage on the 1999-LOC top/bottom engine. |
| 17 | `tests/test_ml_predictor_smoke.py` (`@pytest.mark.slow`) | §24 cold-start spec: lazy-load LightGBM under 60s; predict on a synthetic feature row returns a valid probability; falls back gracefully when model file missing. |
| 18 | `tests/test_news_sentiment_fallback.py` | Returns neutral payload when CRYPTOPANIC_API_KEY unset, network unreachable, or rate-limited. Mirrors the pattern in `test_smoke.py::test_fetch_vc_funding_signal_returns_neutral_payload`. |
| 19 | `tests/test_circuit_breakers.py` | Drawdown breaker triggers at threshold; max-position breaker rejects oversized order; persistence across session restart. |
| 20 | `tests/test_chart_component_theme.py` | Chart renderer respects current theme (dark vs light); axis/grid/text colors swap. |

---

## 9. Priority Order — What to Write First

The legacy-look fix sprint hasn't started yet. Tests should land
**alongside or just before** each fix so each fix has a regression
guard committed in the same atomic unit (per CLAUDE.md §3).

### Phase A — write before / during the upcoming sprint (in this order)

1. **`test_hero_card_cascade.py`** (Image 1) — quick win, mirrors
   existing C-fix-19 watchlist test. ~30 min.
2. **`test_arbitrage_buy_sell_on.py`** (Image 5) — `arbitrage.py`
   currently has zero coverage; even a thin test is a 100x improvement.
3. **`test_funding_rate_parser.py`** (Image 7) — parser bug needs
   fixture-level verification before the fix lands.
4. **`test_onchain_data_binding.py`** (Image 8) — the headline bug per
   user feedback ("nothing is shown here").
5. **`test_accent_token_usage.py`** (Images 4, 6, 7, 8) — single CSS
   pass + single test sweep across the codebase.
6. **`test_narrow_viewport_topbar.py`** (Image 8) — extends existing
   `test_topbar_polish.py` patterns.
7. **`test_sidebar_legal_no_wrap.py`** (Image 8).
8. **`test_empty_state_truthfulness.py`** — systemic, catches both
   "—" and "None" patterns.
9. **`test_whale_tracker_empty_state.py`** (Image 8) + smoke test
   for `whale_tracker.py`.
10. **`test_ds_card_shell_coverage.py`** (Image 6).
11. **`test_atr_zero_vs_dash.py`** (Image 3 nit).

### Phase B — long-overdue §22 / §24 fixture mandate

12. **`test_cycle_indicators_fixtures.py`** — §22 explicit gap.
13. **`test_risk_metrics_fixtures.py`** — §22 explicit gap.
14. **`test_top_bottom_detector_fixtures.py`** — §22 explicit gap on
    1999-LOC math engine.

### Phase C — overdue cross-cutting infra

15. **`test_theme_parity.py`** — establishes the missing dark/light
    contract.
16. **`test_user_level_render_diff.py`** — closes the level-rendering
    gap.
17. **`test_news_sentiment_fallback.py`** — mirrors VC funding test.
18. **`test_circuit_breakers.py`** — risk-critical untested module.
19. **`test_ml_predictor_smoke.py`** — first `@pytest.mark.slow` test;
    establishes the pattern §24 calls for.
20. **`test_chart_component_theme.py`** — feeds into theme-parity work.

---

## 10. Suite-Level Recommendations

1. **Keep §22 fixture coverage discipline.** `test_indicator_fixtures.py`
   is the gold-standard pattern (37 deterministic golden-value tests).
   Replicate to `cycle_indicators`, `risk_metrics`,
   `top_bottom_detector`. **All three are §22-mandated and currently
   have zero direct tests.**

2. **Add a `slow` marker policy.** Per §24 the fast-test target is
   under 30s; we're currently at 9.5s with zero slow tests. Adding ML
   tests will push toward 30s. Establish the pattern with the first
   `@pytest.mark.slow` test (item 19 in priority list) so the budget
   stays clean.

3. **Fix the hidden no-op skip in `test_data_wiring.py:169`.** Replace
   the silent `return` with `pytest.skip(reason=...)` so the suite
   reports it as skipped rather than passing.

4. **Add a CI guard against bare-string passes.** Several existing
   tests use `assert "string" in src` — extending this is fine, but
   start tagging which tests are "structural-only" so future engineers
   know they need a behavioural counterpart.

5. **Establish a fake-Streamlit harness** (similar to
   `test_segmented_control.py`'s `_FakeSt`) as a shared fixture in
   `conftest.py`. Several future tests (theme parity, level-render
   diff, narrow-viewport) need it.

6. **Wire `pytest --cov`** into CI and check in a `.coveragerc` so the
   "% covered" estimates above become real numbers. Currently this
   audit relies on structural inspection.

---

## Appendix A — Module → Test File Index (raw)

```
agent.py               → test_agent_c5.py
ai_feedback.py         → (none)
alerts.py              → test_alerts_c6.py, test_composite_learned_weights.py
allora.py              → (none)
api.py                 → (none)
arbitrage.py           → test_segmented_control.py (string-ref only),
                         test_indicator_fixtures.py (string-ref only),
                         test_backtester_c4.py (nav-only)
chart_component.py     → (none)
circuit_breakers.py    → (none)
composite_signal.py    → test_smoke.py (parse), test_composite_*.py (4 files)
composite_weight_optimizer.py → test_composite_weight_optimizer.py
crypto_model_core.py   → test_indicator_fixtures.py, test_regime_history_c8.py
cycle_indicators.py    → (none)  — §22 violation
data_feeds.py          → test_smoke.py, test_data_wiring.py, conftest.py
database.py            → test_alerts_c6.py, test_agent_c5.py, test_regime_history_c8.py
execution.py           → test_agent_c5.py (1 ref)
llm_analysis.py        → (none)
ml_predictor.py        → (none)  — §24 cold-start spec violation
news_sentiment.py      → (none)
pdf_export.py          → test_smoke.py (parse only)
risk_metrics.py        → (none)  — §22 violation
scheduler.py           → test_data_wiring.py
top_bottom_detector.py → test_smoke.py (parse only)  — §22 violation
ui_components.py       → indirect via 5+ files
websocket_feeds.py     → test_data_wiring.py
whale_tracker.py       → (none)
```

## Appendix B — Test Counts by File

```
42  test_smoke.py
37  test_indicator_fixtures.py
29  test_data_wiring.py
20  test_state_persistence_audit.py
19  test_pair_selection.py
13  test_alerts_c6.py
10  test_composite_learned_weights.py
 9  test_topbar_polish.py
 9  test_composite_weight_optimizer.py
 8  test_segmented_control.py
 8  test_regime_history_c8.py
 8  test_agent_c5.py
 7  test_sidebar_nav.py
 7  test_backtester_c4.py
 6  test_config_editor.py
 6  test_composite_signal_regression.py
 6  test_composite_fallback.py
 5  test_user_level_persistence.py
 4  test_settings_c7.py
 4  test_level_variants_c9.py
 4  test_dashboard_c10.py
 3  test_backtester_buttons.py
---
264 total
```
