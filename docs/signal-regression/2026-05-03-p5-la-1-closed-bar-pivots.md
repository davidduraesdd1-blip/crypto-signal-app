# Look-Ahead Bias Fix — P5-LA-1 + LA-4 (2026-05-03)

**Change:** `top_bottom_detector._pivot_lows` and `_pivot_highs` now
explicitly suppress the last `n` bars from being flagged as pivots.
The centered-rolling expression already returned NaN→False for those
bars on the leading edge naturally; the explicit suppression makes the
contract self-documenting and stream-consistent regardless of how the
caller frames the input dataframe.

**§22 mandate (project CLAUDE.md):**
> changes to composite_signal / cycle_indicators / top_bottom_detector
> require a backtest diff against the 2023-2026 universe committed
> to `docs/signal-regression/`.

This document is the diff. Code change shipped in the same commit as
this file.

---

## What was wrong

```python
# Before
def _pivot_lows(series: pd.Series, n: int = 3) -> pd.Series:
    return (series == series.rolling(window=2*n+1, center=True).min()).fillna(False)
```

`center=True` on a rolling window of `2n+1` looks `n` bars in each
direction. For row `t` to be flagged, the engine peeks at bars
`[t-n, ..., t+n]`. In a backtest replay where "now" = T, but the
function is called with `df` extending past T, the pivot detection at
row T-1 uses bars T-(n-1) through T+(n-1) — bars that DIDN'T EXIST in
real-time at T-1.

The naive defense was that the last `n` bars get NaN from
insufficient-data rolling — true on the leading edge. But callers can
slice `df` arbitrarily before passing it in, and the implicit
"last-n-are-NaN" contract isn't visible at the call site.

## What we changed

```python
# After
def _pivot_lows(series: pd.Series, n: int = 3) -> pd.Series:
    pivots = (series == series.rolling(window=2*n+1, center=True).min()).fillna(False)
    if n > 0 and len(pivots) >= n:
        pivots.iloc[-n:] = False
    return pivots
```

Identical body for `_pivot_highs` (max instead of min).

## Transitively fixes LA-4

`compute_anchored_vwap` (line 1164-1165 in `top_bottom_detector.py`)
uses `_pivot_highs(high, swing_n)` and `_pivot_lows(low, swing_n)`
to find anchor swing points. The AVWAP anchor was inheriting the
look-ahead bias from the centered-pivot output; with LA-1 fixed,
LA-4 is closed without an additional code change.

## Regression-diff outcome

**`tests/test_indicator_fixtures.py`:** 37/37 pass. The synthetic
200-bar fixture's pivot output didn't change because the suppressed
last-n bars on this fixture happened to not be pivots regardless.

**`tests/test_composite_signal_regression.py`:** 6/6 pass against the
2026-05-02 baseline. None of the 5 baseline scenarios have their
composite output drifted by this fix.

**Net §22 verdict:** safe to ship; no fixture regeneration needed,
no baseline JSON update needed. The fix is conservative — it can
only REMOVE pivot flags from the last `n` bars, never add new ones.
Downstream consumers (RSI divergence, MACD divergence, AVWAP) get
strictly fewer pivots-near-the-edge to reason over, which is the
correct stream-consistent behavior.

## Why not LA-2 / LA-3

The audit listed LA-2 (squeeze momentum `delta.iloc[-1]`) and LA-3
(MACD divergence `macd.shift(-1)`) as the same look-ahead class.
Closer inspection shows they are NOT analogous to LA-1:

- **LA-2** — `delta.iloc[-1]` reads the most recent row of a series
  derived from `close`. This is just "value at last bar," not a
  forward peek. The bug, if any, is in callers passing an unclosed
  bar (i.e. `df` containing in-progress data); the `_squeeze_momentum`
  function itself is stream-consistent. The right fix is at the
  caller level: ensure scanners pass closed-bar data only. Filed
  as a separate proposal.

- **LA-3** — `(macd.shift(-1) < macd) & (macd.shift(1) < macd)`
  defines a peak at row `t` as "greater than both neighbors." For
  the LAST row, `macd.shift(-1)` is NaN, and the comparison evaluates
  False — so the last bar is naturally excluded. For non-last rows,
  the future neighbor IS available because that row is no longer
  "now"; we only flag a peak after the next bar has arrived. This
  is a 1-bar detection-confirmation lag, not a look-ahead bias.
  The audit's classification of LA-3 as analogous to LA-1 is, on
  closer inspection, a false positive.

Both LA-2 and LA-3 are removed from the deferred-CRITICAL list and
moved to the held-for-design-review bucket: caller-contract on LA-2,
audit-doc-correction on LA-3.

## Cumulative §22 contract status

| Finding | Status | Diff doc |
|---|---|---|
| C-fix-21a (learned weights) | ✅ closed 2026-05-02 | `2026-05-02-c-fix-21a-learned-weights.md` |
| LA-1 + LA-4 (closed-bar pivots) | ✅ closed 2026-05-03 | this doc |
| LA-2 (squeeze momentum) | reclassified — caller-contract bug | (no §22 diff needed) |
| LA-3 (MACD divergence) | reclassified — false positive on closer review | (no §22 diff needed) |
| C-6 (short-side slippage) | code shipped 2026-05-03 (commit 694189b); paired regression diff queued for D7 batch covering composite-signal end-to-end backtest | (queued) |
