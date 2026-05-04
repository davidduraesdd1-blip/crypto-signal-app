# §22 math findings — deferred to post-D8

**Decision date:** 2026-05-04
**Decided by:** Cowork strategic decision (Phase D cutover scoping)
**Status:** documented, not denied

## Why deferred

`tests/test_composite_signal_regression.py` is **6/6 PASS** against the
2026-05-02 §22 baseline (zero drift on the gold-reference 2023-2026 universe,
verified on the overnight audit run — see
`docs/audits/2026-05-04_overnight-audit-summary.md` line 150-178).

The three findings below describe latent issues in `composite_signal.py`. They
are *math review items*, not *behavioral regressions*: the production output
matches the baseline. Fixing any of them requires rerunning the 2023-2026
backtest, diffing against the prior committed signal output, and
**resetting the D8 cutover clock** if the diff is non-trivial. Cowork's
explicit decision on 2026-05-04 was to keep the math-review workstream
**decoupled from the D8 cutover** — ship the cutover, then schedule a
focused half-day for math sign-off.

## Findings (verbatim from `2026-05-03_phase-d-deep-dive-audit.md` line 87-105)

### CMC-1 — scalar broadcast (composite_signal.py)

When a single layer returns a scalar instead of a per-pair Series, the
broadcast inflates the layer's contribution across the universe. Hidden
edge case: rare on Tier 1-3 universes, more common on Tier 5 (top 100) when
a layer's data feed degrades. **Status:** documented; fix would require
re-running the 2023-2026 backtest baseline diff before merge.

### CMC-2 — `.shift(-1)` divergence policy

Forward-looking shift on one momentum branch creates a one-bar look-ahead
window relative to the closed-bar pivot policy fixed in P5-LA-1. Defensible
in the original design ("leading indicator") but inconsistent with the rest
of the model post-P5. **Status:** documented; same backtest protocol applies.

### CMC-3 — chandelier exit flip

Sign convention question — current code subtracts `ATR * multiplier` from
highest-high which is the industry-standard form, BUT the comment alleges
the opposite. Need to confirm the math matches the doc, then either fix the
math or fix the comment. Current backtest results validate the math, so the
fix is likely a comment update, not code.

## Review trigger

**Reopen this file (and re-prioritize the math sign-off batch) if any
future regression diff against `composite_signal.py` fails. Investigate
these three findings *first* before broader debugging** — they are the
known-but-deferred issues most likely to surface as observable drift.

Specifically:
- If `tests/test_composite_signal_regression.py` ever drops below 6/6,
  CMC-1/CMC-2/CMC-3 are the first suspects.
- If a Tier 5 (top-100) scan produces visibly off-trend confidence values
  on a single layer, CMC-1 is the first suspect.
- If P5-LA-1 (closed-bar pivot policy) is revisited, CMC-2 must be
  re-evaluated as part of that work.
- If a chandelier-exit change is proposed, confirm the comment-vs-math
  alignment in CMC-3 *before* the change.

## Hard constraint

**Do not modify `composite_signal.py` to address these three findings during
Phase D.** The §22 baseline is the cutover gate. Any change there resets
the D8 clock.
