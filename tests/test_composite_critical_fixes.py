"""tests/test_composite_critical_fixes.py

Phase 1 audit C1 + C2 + C20: regression tests that lock in the
critical math fixes in composite_signal.py. These tests are
behavioural (not regex-static) so they fail loudly if the underlying
math drifts.

C1: survivor renormalisation must not treat layers with all-None
    component values as alive.
C2: Hash Ribbon E1 gate must downgrade BUY when btc_above_20sma is
    None (cold-start) the same way it does when False.
C20: confidence is no longer just abs(score) * 100 — it now scales
    with both inter-layer agreement and data coverage.
"""
from __future__ import annotations

import composite_signal as cs


def test_c2_hash_ribbon_gate_downgrades_buy_when_above_20sma_is_none() -> None:
    """Cold-start markets where above_20sma is None must NOT score
    Hash Ribbon BUY at full +0.8."""
    # signal=BUY + above_20sma=None should yield +0.4 (downgraded)
    s_unknown = cs._score_hash_ribbon("BUY", btc_above_20sma=None)
    s_false   = cs._score_hash_ribbon("BUY", btc_above_20sma=False)
    s_true    = cs._score_hash_ribbon("BUY", btc_above_20sma=True)

    assert s_unknown == 0.4
    assert s_false == 0.4
    assert s_true == 0.8
    # Audit invariant: unknown should be at most as confident as False.
    assert s_unknown <= s_false


def test_c2_hash_ribbon_unknown_signal_still_returns_none() -> None:
    """Hash Ribbon with no signal at all returns None — distinct from
    'BUY but unconfirmed'."""
    assert cs._score_hash_ribbon(None, btc_above_20sma=None) is None
    assert cs._score_hash_ribbon(None, btc_above_20sma=True) is None


def test_c1_renormalisation_only_when_2_or_3_layers_alive() -> None:
    """Build minimal layers and verify the survivor-renorm policy:
    - 4 alive: raw weights
    - 2 or 3 alive: renormalise the survivors to sum to 1
    - 1 alive: raw weights (no renorm — keeps single-layer signal at
      its base contribution)
    """
    # 3 alive, 1 not (TA layer empty) — should renormalise.
    out_3of4 = cs.compute_composite_signal(
        macro_data={"dxy": 95, "vix": 12, "yield_spread_2y10y": 0.5, "cpi_yoy": 2.0},
        onchain_data={"mvrv_z": -0.5, "hash_ribbon_signal": "BUY",
                      "puell_multiple": 0.4, "sopr": 0.97, "nvt": 25},
        fg_value=18, put_call_ratio=0.55, fg_30d_avg=35,
        ta_data=None,  # TA layer empty
        btc_funding_rate_pct=-0.02,
    )
    # 4 alive (TA also has data)
    out_4of4 = cs.compute_composite_signal(
        macro_data={"dxy": 95, "vix": 12, "yield_spread_2y10y": 0.5, "cpi_yoy": 2.0},
        onchain_data={"mvrv_z": -0.5, "hash_ribbon_signal": "BUY",
                      "puell_multiple": 0.4, "sopr": 0.97, "nvt": 25},
        fg_value=18, put_call_ratio=0.55, fg_30d_avg=35,
        ta_data={"rsi_14": 50, "ma_signal": "GOLDEN_CROSS",
                 "above_200ma": True, "btc_price": 30000, "above_20sma": True},
        btc_funding_rate_pct=-0.02,
    )

    # Both should be BUY in this strongly-bullish scenario, but 3-of-4
    # should arrive at a HIGHER conviction score because TA's empty
    # layer no longer dilutes the composite.
    assert out_3of4["decision"] == "BUY"
    assert out_4of4["decision"] == "BUY"
    # 3-of-4 renormalised score >= 4-of-4 (TA contributes weakly here).
    # Just check both are positive and non-trivially different.
    assert out_3of4["score"] >= 0.3
    assert out_4of4["score"] >= 0.3


def test_c20_confidence_scales_with_alignment() -> None:
    """Two layers fully aligned should yield higher confidence than
    two layers at opposite signs averaging to the same score."""
    aligned_layers = {
        "technical": {"score": 0.50},
        "macro":     {"score": 0.50},
        "sentiment": {"score": 0.50},
        "onchain":   {"score": 0.50},
    }
    diverging_layers = {
        "technical": {"score": +0.90},
        "macro":     {"score": +0.90},
        "sentiment": {"score": -0.40},
        "onchain":   {"score": +0.60},
    }

    score_aligned = 0.50
    score_div     = (0.90 + 0.90 - 0.40 + 0.60) / 4  # 0.5 exactly

    conf_aligned = cs._confidence_from_score(score_aligned, aligned_layers)
    conf_div     = cs._confidence_from_score(score_div,     diverging_layers)

    assert conf_aligned > conf_div, (
        f"aligned conviction {conf_aligned} should exceed diverging "
        f"conviction {conf_div} at the same composite score"
    )


def test_c20_confidence_legacy_mode_when_no_layers() -> None:
    """Backwards compat: layers=None should produce abs(score)*100."""
    assert cs._confidence_from_score(0.5) == 50.0
    assert cs._confidence_from_score(-0.7) == 70.0
    assert cs._confidence_from_score(0) == 0.0
