# Tier 5 — §22 Math Regression
**Date:** 2026-05-05
**Baseline:** 6/6 PASS (per CLAUDE.md §22)
**Worktree:** `.claude/worktrees/exciting-lovelace-60ae5b`
**Runner:** Python 3.14.3, pytest-9.0.3 on win32

## Regression status

- **composite_signal regression: PASS (6/6 cases)** — zero drift vs.
  `docs/signal-regression/2026-05-02-baseline.json` on the gold-reference
  scenario set; all five parametrized cases plus the baseline-presence
  sanity check pass within tolerance (composite-score Δ ≤ 0.05,
  confidence Δ ≤ 5.0, per-layer Δ ≤ 0.05, decision/signal exact match).
- **Total math-adjacent tests: 81 passed / 0 failed** in 9.25s. Nothing
  skipped, nothing xfailed. No drift, no warnings of consequence.

Breakdown of math-adjacent suite:

| Suite | Tests | Result |
|---|---|---|
| `test_composite_signal_regression.py` | 6 | 6 PASS |
| `test_composite_critical_fixes.py` | 5 | 5 PASS |
| `test_composite_fallback.py` | 6 | 6 PASS |
| `test_composite_learned_weights.py` | 10 | 10 PASS |
| `test_composite_weight_optimizer.py` | 9 | 9 PASS |
| `test_indicator_fixtures.py` | 37 | 37 PASS |
| `test_regime_history_c8.py` | 8 | 8 PASS |
| **Total** | **81** | **81 PASS** |

`test_indicator_fixtures.py` carries the canonical-output checks for the
heavy-math primitives the §22 review cares about: RSI, MACD (+ divergence),
Bollinger, ATR, ADX, Supertrend, Stochastic, Ichimoku, Hurst, Squeeze,
**Chandelier**, CVD divergence, Gaussian Channel, Support/Resistance,
RSI/MACD divergence, candlesticks (incl. bull-engulfing), Wyckoff, HMM
regime, cointegration, VWAP, Fibonacci. All canonical outputs hold.

No dedicated test files exist for `cycle_indicators.py` or
`top_bottom_detector.py` as separate modules (only smoke imports). Their
math-relevant outputs flow through the composite-signal regression and
indicator fixtures, both of which are clean.

## Deferred math findings (CMC-1 / CMC-2 / CMC-3)

Source: `docs/audits/2026-05-04_section22-math-findings-deferred.md`
(decided by Cowork strategic call on 2026-05-04; documented, not denied).

### CMC-1 — scalar broadcast in `composite_signal.py`
- **Finding.** When a single layer returns a scalar instead of a per-pair
  Series, the broadcast inflates that layer's contribution across the
  universe. Latent edge case — rare on Tier 1–3, more probable on Tier 5
  (top-100) when a layer's data feed degrades.
- **Why deferred.** Production output already matches the baseline; this is
  a math-review item, not a behavioral regression. Fixing it requires
  re-running the 2023–2026 backtest, diffing the prior committed signal
  output, and resetting the D8 cutover clock if the diff is non-trivial.
- **Addressed since 2026-05-04?** No. `composite_signal.py` has not been
  touched in this worktree (forbidden by §22 hard constraint during Phase D).
- **Mobile-launch recommendation.** Address **after** D8 cutover stabilises.
  Not a launch blocker as long as the universe is Tier ≤3 at launch and
  data-feed degradation alarms are wired. If the mobile launch ships
  Tier 5 scans on day one, raise this to a P1 fix-before-launch item and
  schedule the half-day backtest sign-off.

### CMC-2 — `.shift(-1)` divergence policy
- **Finding.** A forward-looking `.shift(-1)` on one momentum branch creates
  a one-bar look-ahead window inconsistent with the closed-bar pivot policy
  fixed in P5-LA-1. Defensible in the original "leading indicator" design
  but inconsistent with the rest of the model post-P5.
- **Why deferred.** Same backtest-diff protocol as CMC-1 — a math-policy
  reconciliation, not a baseline failure.
- **Addressed since 2026-05-04?** No.
- **Mobile-launch recommendation.** Address before mobile launch **if**
  any new feature surfaces leading-indicator confidence to the user. The
  one-bar window does not affect historical backtest values but it does
  affect forward-printed confidence between bar close and next-bar print.
  For a 5-min-cache crypto app this is a small window, but on mobile it is
  visible to the user. Recommend tying this to the same half-day math
  sign-off as CMC-1.

### CMC-3 — chandelier exit flip (sign convention)
- **Finding.** Code subtracts `ATR * multiplier` from highest-high (industry
  standard). The inline comment alleges the opposite. Need to confirm math
  matches the doc and either fix the math or fix the comment.
- **Why deferred.** Backtest results already validate the math, so the
  fix is almost certainly a comment update — not a code change. But it
  still touches `composite_signal.py`, which is the §22 cutover gate.
- **Addressed since 2026-05-04?** No. `test_indicator_fixtures.py::test_chandelier_canonical`
  passes today, which is consistent with the math being correct and only
  the comment being wrong.
- **Mobile-launch recommendation.** Trivial pre-launch — it is a comment
  fix, no math change, no backtest reset. Do this in the same commit as
  the half-day math sign-off and clear the entire CMC-1/2/3 row in one go.

## Test runner output

```
$ python -m pytest tests/test_composite_signal_regression.py -v
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.0.3, pluggy-1.6.0 -- Python 3.14
cachedir: .pytest_cache
rootdir: C:\dev\Cowork\crypto-signal-app\.claude\worktrees\exciting-lovelace-60ae5b
plugins: anyio-4.12.1, langsmith-0.7.17
collected 6 items

tests/test_composite_signal_regression.py::test_composite_regression[all_none_neutral_baseline] PASSED [ 16%]
tests/test_composite_signal_regression.py::test_composite_regression[extreme_risk_on_bull]      PASSED [ 33%]
tests/test_composite_signal_regression.py::test_composite_regression[extreme_risk_off_bear]     PASSED [ 50%]
tests/test_composite_signal_regression.py::test_composite_regression[mid_cycle_balanced]        PASSED [ 66%]
tests/test_composite_signal_regression.py::test_composite_regression[panic_vix_gate_check]      PASSED [ 83%]
tests/test_composite_signal_regression.py::test_baseline_file_present                           PASSED [100%]

============================== 6 passed in 2.78s ==============================
```

Combined run across all math-adjacent suites:

```
$ python -m pytest tests/test_composite_signal_regression.py \
    tests/test_composite_critical_fixes.py \
    tests/test_composite_fallback.py \
    tests/test_composite_learned_weights.py \
    tests/test_composite_weight_optimizer.py \
    tests/test_indicator_fixtures.py \
    tests/test_regime_history_c8.py -v
...
============================== 81 passed in 9.25s =============================
```

## Recommendation

**PASS, no P0 action needed for the §22 cutover gate.**

- Composite-signal regression remains 6/6 against the 2026-05-02 baseline.
  Phase D D8 cutover (2026-05-04, in-process scheduler change) introduced
  zero drift in the gold-reference scenarios.
- All 81 math-adjacent tests are green. Indicator fixtures, learned-weight
  loader, optimizer, fallback path, regime history — all clean.
- `composite_signal.py` is correctly untouched in this worktree (per §22
  hard constraint).

**Deferred-findings posture for mobile launch:**
- **CMC-3 (comment fix):** trivial — bundle into the next math touch-up
  commit, no backtest reset.
- **CMC-1 (scalar broadcast):** P1-before-mobile **only** if mobile ships
  with Tier 5 (top-100) scans on day one. Otherwise post-launch.
- **CMC-2 (`.shift(-1)` policy):** P1-before-mobile **only** if the mobile
  UI surfaces leading-indicator confidence between bar closes. Otherwise
  post-launch.
- **All three together:** schedule the half-day math sign-off batch
  (backtest 2023–2026, diff vs. committed baseline, regenerate baseline if
  approved, single atomic commit) once D8 cutover is fully ratified and
  the cutover-clock concern from the 2026-05-04 deferral note no longer
  applies.

No P0 fix is required to ship the current Phase D state.
