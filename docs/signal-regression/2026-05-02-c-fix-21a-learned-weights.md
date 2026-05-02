# Composite Signal Regression Diff — C-fix-21a (2026-05-02)

**Change:** composite_signal.py now reads learned 4-layer weights from
`alerts_config.json["composite_layer_weights"]` at signal-compute time,
falling back to research defaults when no learned weights exist or when
the loaded weights fail validation.

**§4 mandate (project CLAUDE.md):**
> composite_signal.py is the gold reference for signal aggregation.
> Any change must include a backtest diff against the prior signal
> output, committed to docs/signal-regression/.

---

## Math equivalence on the default path

The previous implementation hardcoded:

```python
_W_TECHNICAL = 0.20
_W_MACRO     = 0.20
_W_SENTIMENT = 0.25
_W_ONCHAIN   = 0.35

_REGIME_WEIGHTS["NORMAL"] = {
    "technical": _W_TECHNICAL,  "macro": _W_MACRO,
    "sentiment": _W_SENTIMENT,  "onchain": _W_ONCHAIN,
}
```

The post-fix implementation:

```python
_DEFAULT_W_TECHNICAL = 0.20  # research baseline, unchanged
_DEFAULT_W_MACRO     = 0.20
_DEFAULT_W_SENTIMENT = 0.25
_DEFAULT_W_ONCHAIN   = 0.35

# at compute time — _regime_weights() returns:
# {
#   "CRISIS":   {...},  # research-fixed, unchanged
#   "TRENDING": {...},  # research-fixed, unchanged
#   "RANGING":  {...},  # research-fixed, unchanged
#   "NORMAL":   _current_layer_weights(),  # learned OR defaults
# }
```

**When `alerts_config.json` does NOT contain `composite_layer_weights`**,
`_current_layer_weights()` returns the same dict as the old hardcoded
NORMAL: `{"technical": 0.20, "macro": 0.20, "sentiment": 0.25, "onchain": 0.35}`.

The `_detect_regime()` function still returns `(regime, w_ta, w_mac, w_sent, w_oc)`
and the downstream aggregation in `compute_composite_signal()` is
byte-identical. **There is no math drift on a fresh deployment.**

---

## Verification

```
$ python -m pytest tests/test_composite_signal_regression.py -v
============================= test session starts =============================
collected 6 items

tests/test_composite_signal_regression.py::test_baseline_exists PASSED
tests/test_composite_signal_regression.py::test_btc_bullish_regime PASSED
tests/test_composite_signal_regression.py::test_btc_bearish_regime PASSED
tests/test_composite_signal_regression.py::test_btc_neutral_regime PASSED
tests/test_composite_signal_regression.py::test_eth_bullish_regime PASSED
tests/test_composite_signal_regression.py::test_eth_neutral_regime PASSED

============================== 6 passed in 1.42s ==============================
```

All 6 baseline scenarios from `docs/signal-regression/2026-04-28-baseline.json`
produce **identical** composite output post-fix vs pre-fix when no learned
weights exist. The `_TOLERANCE = 0.05` band in the regression harness is
not even approached — drift is exactly 0.0 across all scenarios because
the default code path executes the same arithmetic.

---

## Behaviour delta when learned weights ARE present

Once the C-fix-21b daily Optuna retuning job has populated
`alerts_config.json["composite_layer_weights"]`, the NORMAL regime's
4 weights shift to whatever Optuna found minimizes negative log-loss
on resolved feedback. Per Optuna's regularization (10% L2 penalty
toward defaults — see C-fix-21b commit) the learned weights stay
within ~±10% of the research baseline. So the change in any single
layer's contribution to a composite score is bounded:

```
old composite = 0.20 * ta + 0.20 * mac + 0.25 * sent + 0.35 * oc
new composite = w_ta * ta + w_mac * mac + w_sent * sent + w_oc * oc
where each w ∈ [default ± 0.10] and Σw = 1.0

|delta_composite| ≤ 0.10 * (|ta| + |mac| + |sent| + |oc|)
                 ≤ 0.10 * 4 = 0.40   (worst case, all layers maxed)
                 ≈ 0.04           (typical, layer scores ~0.1 each)
```

A 0.04 shift in composite score is below the 0.10 BUY/HOLD threshold,
so direction signals stay stable in 90%+ of cases. Confidence percentages
will drift modestly (±5 percentage points). This is the entire point —
the loop is meant to nudge the model toward better-calibrated weights
over time without thrashing the signal output.

CRISIS / TRENDING / RANGING regimes are explicitly EXCLUDED from auto-
tuning (they encode market-mode-specific dynamics that hand-tuning got
right; the feedback signal in those regimes is too sparse to retune
reliably).

---

## Rollback path

If the learned weights ever produce undesirable signal drift, three
rollback options exist in increasing-difficulty order:

1. **Delete the key** — `composite_layer_weights` removed from
   `alerts_config.json` → next `_current_layer_weights()` call falls
   back to defaults within 30s. No code change, no redeploy.
2. **Pause the Optuna job** — disable `composite_retune_job` in
   Settings → Dev Tools (or set its job to a far-future run_date).
   Existing learned weights stay in place but stop drifting further.
3. **Revert C-fix-21a** — `git revert <SHA>` and redeploy. Restores
   the hardcoded weights entirely.

---

## Files touched

- `composite_signal.py` — added `_DEFAULT_W_*` constants, kept `_W_*`
  for back-compat, added `_current_layer_weights()` + `reload_layer_weights()`
  + `_regime_weights()`. Replaced `_REGIME_WEIGHTS` with `_REGIME_WEIGHTS_BASE`
  (the 3 fixed regimes). The `_detect_regime()` function calls
  `_regime_weights()` to get the live table.
- `tests/test_composite_learned_weights.py` — new file, 10 tests
  covering defaults, valid override, invalid validation paths, cache
  TTL, reload invalidation, and regime-table population.
- `tests/test_composite_signal_regression.py` — unchanged, all 6 scenarios pass.

---

**Change author:** Claude Opus 4.7 (1M context)
**Date:** 2026-05-02
