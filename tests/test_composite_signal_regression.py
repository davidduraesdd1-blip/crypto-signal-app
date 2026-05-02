"""tests/test_composite_signal_regression.py

Locks the composite_signal output against a saved baseline per project
CLAUDE.md §4 mandate:

  > composite_signal.py is the gold reference for signal aggregation.
  > Any change must include a backtest diff against the prior signal
  > output, committed to docs/signal-regression/.

Whenever a future change to composite_signal.py (or any of its scoring
helpers) shifts an output, this test fails and forces the engineer to:
  1. Decide whether the drift is intentional;
  2. Re-run `python -m tests.regenerate_composite_baseline` (or the
     inline regen block at the bottom of this file) to update the
     baseline JSON;
  3. Commit BOTH the code change AND the new baseline together.

The baseline lives at `docs/signal-regression/2026-04-28-baseline.json`.
Each test case is one scenario (input dict → expected output decision +
confidence + 4 layer scores). Numerical comparison is done with a small
tolerance to allow for trivial formatting / rounding nudges.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import composite_signal


_BASELINE_PATH = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "signal-regression"
    / "2026-05-02-baseline.json"
)
_TOLERANCE = 0.05  # absolute drift allowed before the test fails


def _load_baseline() -> dict:
    if not _BASELINE_PATH.exists():
        pytest.skip(f"baseline not present at {_BASELINE_PATH}")
    with _BASELINE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _pick_layer_score(out: dict, layer_name: str) -> float | None:
    """Pull a layer's score from the composite output structure."""
    layers = out.get("layers") or {}
    layer = layers.get(layer_name) or {}
    score = layer.get("score")
    return float(score) if score is not None else None


@pytest.mark.parametrize(
    "scenario_name",
    [
        "all_none_neutral_baseline",
        "extreme_risk_on_bull",
        "extreme_risk_off_bear",
        "mid_cycle_balanced",
        "panic_vix_gate_check",
    ],
)
def test_composite_regression(scenario_name: str) -> None:
    """One test per baseline scenario. Fails on output drift."""
    baseline = _load_baseline()
    if scenario_name not in baseline:
        pytest.skip(f"scenario {scenario_name!r} missing from baseline")

    case = baseline[scenario_name]
    inputs = dict(case["inputs"])
    expected = case["output"]

    actual = composite_signal.compute_composite_signal(**inputs)

    # Decision should match exactly — it's a categorical label.
    assert actual["decision"] == expected["decision"], (
        f"{scenario_name}: decision drift "
        f"{expected['decision']} → {actual['decision']}"
    )

    # 7-state legacy label should also match.
    assert actual["signal"] == expected["signal"], (
        f"{scenario_name}: legacy signal drift "
        f"{expected['signal']} → {actual['signal']}"
    )

    # Numerical drift tolerance: composite score, confidence, and each layer.
    assert abs(actual["score"] - expected["score"]) <= _TOLERANCE, (
        f"{scenario_name}: composite score drift "
        f"{expected['score']} → {actual['score']}"
    )

    assert abs(actual["confidence"] - expected["confidence"]) <= _TOLERANCE * 100, (
        f"{scenario_name}: confidence drift "
        f"{expected['confidence']} → {actual['confidence']}"
    )

    for layer_name in ("technical", "macro", "sentiment", "onchain"):
        exp_score = _pick_layer_score(expected, layer_name)
        act_score = _pick_layer_score(actual, layer_name)
        if exp_score is None and act_score is None:
            continue
        if exp_score is None or act_score is None:
            pytest.fail(
                f"{scenario_name}: layer {layer_name} presence drift "
                f"baseline={exp_score} actual={act_score}"
            )
        assert abs(act_score - exp_score) <= _TOLERANCE, (
            f"{scenario_name}: {layer_name} layer drift "
            f"{exp_score} → {act_score}"
        )


def test_baseline_file_present() -> None:
    """Sanity: the baseline file must exist for the regression suite to mean anything."""
    assert _BASELINE_PATH.exists(), (
        f"composite signal regression baseline missing at {_BASELINE_PATH}; "
        f"regenerate via `python tests/regenerate_composite_baseline.py`"
    )


# ── Inline regeneration helper ──────────────────────────────────────────────
# Run as `python tests/test_composite_signal_regression.py` to overwrite
# the baseline JSON with the current code's outputs. Use with intent:
# baseline regeneration is the contract that says "this drift is approved."

if __name__ == "__main__":
    scenarios_inputs = {
        "all_none_neutral_baseline": {
            "macro_data": {}, "onchain_data": {}, "fg_value": None,
            "put_call_ratio": None, "ta_data": None, "fg_30d_avg": None,
            "btc_funding_rate_pct": None,
        },
        "extreme_risk_on_bull": {
            "macro_data": {"dxy": 95, "vix": 12, "yield_spread_2y10y": 0.5, "cpi_yoy": 2.0},
            "onchain_data": {"mvrv_z": -0.5, "hash_ribbon_signal": "BUY", "puell_multiple": 0.4,
                             "sopr": 0.97, "nvt": 25},
            "fg_value": 18, "put_call_ratio": 0.55, "fg_30d_avg": 35,
            "ta_data": {"btc_price": 30000, "above_20sma": True},
            "btc_funding_rate_pct": -0.02,
        },
        "extreme_risk_off_bear": {
            "macro_data": {"dxy": 110, "vix": 35, "yield_spread_2y10y": -0.6, "cpi_yoy": 9.0},
            "onchain_data": {"mvrv_z": 8.0, "hash_ribbon_signal": "NEUTRAL", "puell_multiple": 4.5,
                             "sopr": 1.08, "nvt": 110},
            "fg_value": 88, "put_call_ratio": 1.4, "fg_30d_avg": 75,
            "ta_data": {"btc_price": 95000, "above_20sma": True},
            "btc_funding_rate_pct": 0.10,
        },
        "mid_cycle_balanced": {
            "macro_data": {"dxy": 102, "vix": 18, "yield_spread_2y10y": 0.0, "cpi_yoy": 3.5},
            "onchain_data": {"mvrv_z": 2.0, "hash_ribbon_signal": "NEUTRAL", "puell_multiple": 1.5,
                             "sopr": 1.01, "nvt": 60},
            "fg_value": 50, "put_call_ratio": 0.85, "fg_30d_avg": 50,
            "ta_data": {"btc_price": 60000, "above_20sma": True},
            "btc_funding_rate_pct": 0.01,
        },
        "panic_vix_gate_check": {
            "macro_data": {"dxy": 108, "vix": 45, "yield_spread_2y10y": -0.3, "cpi_yoy": 5.0},
            "onchain_data": {"mvrv_z": 3.0, "hash_ribbon_signal": "NEUTRAL", "puell_multiple": 2.0,
                             "sopr": 1.0, "nvt": 70},
            "fg_value": 25, "put_call_ratio": 1.8, "fg_30d_avg": 40,
            "ta_data": {"btc_price": 50000, "above_20sma": False},
            "btc_funding_rate_pct": -0.05,
        },
    }

    out_baseline: dict = {}
    for name, inputs in scenarios_inputs.items():
        out_baseline[name] = {
            "inputs": inputs,
            "output": composite_signal.compute_composite_signal(**inputs),
        }

    _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _BASELINE_PATH.open("w", encoding="utf-8") as f:
        json.dump(out_baseline, f, indent=2, default=str, sort_keys=True)
    print(f"Regenerated baseline → {_BASELINE_PATH} ({len(out_baseline)} scenarios)")
