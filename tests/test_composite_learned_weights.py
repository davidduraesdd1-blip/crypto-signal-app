"""tests/test_composite_learned_weights.py

C-fix-21a (2026-05-02): composite_signal.py reads learned 4-layer
weights from alerts_config.json["composite_layer_weights"] when
present and valid, falling back to research defaults otherwise.

These tests cover:
  1. Default weights match historical research baseline (no drift
     when alerts_config.json has no learned weights)
  2. Valid learned weights override the defaults at signal-compute time
  3. Invalid learned weights (don't sum to 1, out of [0,1], non-numeric)
     fail validation cleanly and fall back to defaults
  4. The 30s in-memory cache prevents thrashing the disk on every call
  5. reload_layer_weights() force-invalidates the cache for the
     post-Optuna retune writeback path
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import composite_signal


_DEFAULT = {
    "technical": 0.20,
    "macro":     0.20,
    "sentiment": 0.25,
    "onchain":   0.35,
}


def _reset_cache():
    """Clear the layer-weight cache so each test starts fresh."""
    composite_signal._layer_weight_cache["ts"] = 0.0
    composite_signal._layer_weight_cache["weights"] = None


@pytest.fixture(autouse=True)
def _isolate_layer_weight_cache():
    """Reset the layer-weight cache BEFORE and AFTER each test so
    polluted cache state can't leak across tests (or contaminate
    test_composite_signal_regression.py which runs in the same
    pytest session)."""
    _reset_cache()
    yield
    _reset_cache()


# ── 1. Defaults preserved when no learned weights exist ──────────────────

def test_default_weights_match_research_baseline(tmp_path, monkeypatch):
    """When alerts_config.json has no composite_layer_weights key, the
    function must return the research baseline (0.20/0.20/0.25/0.35).
    This guarantees zero math drift on a fresh deployment."""
    _reset_cache()
    # Default constants match the research baseline.
    assert composite_signal._DEFAULT_W_TECHNICAL == 0.20
    assert composite_signal._DEFAULT_W_MACRO     == 0.20
    assert composite_signal._DEFAULT_W_SENTIMENT == 0.25
    assert composite_signal._DEFAULT_W_ONCHAIN   == 0.35

    # When alerts_config.json exists but lacks the key, the function
    # falls back to the defaults.
    cfg = tmp_path / "alerts_config.json"
    cfg.write_text(json.dumps({"some_other_key": True}), encoding="utf-8")
    fake_module = tmp_path / "composite_signal.py"
    fake_module.write_text("# placeholder", encoding="utf-8")
    monkeypatch.setattr(composite_signal, "__file__", str(fake_module))
    out = composite_signal._current_layer_weights()
    assert out == _DEFAULT


# ── 2. Valid learned weights override defaults ──────────────────────────

def test_valid_learned_weights_are_applied(tmp_path, monkeypatch):
    """When alerts_config.json has a valid composite_layer_weights
    dict (sums to 1.0, each value in [0,1]), it should be returned
    instead of the defaults."""
    _reset_cache()
    cfg = tmp_path / "alerts_config.json"
    cfg.write_text(json.dumps({
        "composite_layer_weights": {
            "technical": 0.30,
            "macro":     0.10,
            "sentiment": 0.20,
            "onchain":   0.40,
        }
    }), encoding="utf-8")
    # Monkeypatch the path-resolution. The function reads
    # `Path(__file__).resolve().parent / "alerts_config.json"`. Patch
    # composite_signal.__file__ to point at the temp dir.
    fake_module = tmp_path / "composite_signal.py"
    fake_module.write_text("# placeholder", encoding="utf-8")
    monkeypatch.setattr(composite_signal, "__file__", str(fake_module))
    out = composite_signal._current_layer_weights()
    assert out["technical"] == 0.30
    assert out["macro"]     == 0.10
    assert out["sentiment"] == 0.20
    assert out["onchain"]   == 0.40


# ── 3. Invalid learned weights fall back to defaults ────────────────────

@pytest.mark.parametrize("bad_weights", [
    # Sum != 1.0
    {"technical": 0.50, "macro": 0.50, "sentiment": 0.50, "onchain": 0.50},
    # Out of [0, 1]
    {"technical": -0.10, "macro": 0.30, "sentiment": 0.40, "onchain": 0.40},
    {"technical": 1.50, "macro": -0.50, "sentiment": 0.0, "onchain": 0.0},
    # Missing key
    {"technical": 0.30, "macro": 0.30, "sentiment": 0.40},
    # Non-numeric
    {"technical": "high", "macro": 0.30, "sentiment": 0.20, "onchain": 0.20},
])
def test_invalid_learned_weights_fall_back_to_defaults(
    tmp_path, monkeypatch, bad_weights
):
    """Bad learned weights must fail validation cleanly and the
    function must return the research defaults — never crash, never
    let bad math through."""
    _reset_cache()
    cfg = tmp_path / "alerts_config.json"
    cfg.write_text(json.dumps({
        "composite_layer_weights": bad_weights
    }), encoding="utf-8")
    fake_module = tmp_path / "composite_signal.py"
    fake_module.write_text("# placeholder", encoding="utf-8")
    monkeypatch.setattr(composite_signal, "__file__", str(fake_module))
    out = composite_signal._current_layer_weights()
    assert out == _DEFAULT, (
        f"Bad weights {bad_weights} should have failed validation "
        f"and returned defaults, got {out}"
    )


# ── 4. 30s in-memory cache ──────────────────────────────────────────────

def test_cache_prevents_disk_read_within_ttl(tmp_path, monkeypatch):
    """The 30s cache means after a successful read, subsequent calls
    return the cached value without hitting disk. Critical for perf
    in the per-pair × per-tf scan inner loop."""
    _reset_cache()
    cfg = tmp_path / "alerts_config.json"
    cfg.write_text(json.dumps({
        "composite_layer_weights": {
            "technical": 0.30, "macro": 0.10, "sentiment": 0.20, "onchain": 0.40,
        }
    }), encoding="utf-8")
    fake_module = tmp_path / "composite_signal.py"
    fake_module.write_text("# placeholder", encoding="utf-8")
    monkeypatch.setattr(composite_signal, "__file__", str(fake_module))

    out1 = composite_signal._current_layer_weights()
    # Mutate the file on disk between calls — within TTL the cache
    # should still return the original value.
    cfg.write_text(json.dumps({
        "composite_layer_weights": {
            "technical": 0.99, "macro": 0.005, "sentiment": 0.0, "onchain": 0.005,
        }
    }), encoding="utf-8")
    out2 = composite_signal._current_layer_weights()
    assert out1 == out2, (
        "Cache failed to return the same value within TTL — every "
        "compute_composite_signal() call would re-read alerts_config.json"
    )


# ── 5. reload_layer_weights() invalidates the cache ─────────────────────

def test_reload_invalidates_cache(tmp_path, monkeypatch):
    """The Optuna retuning job calls reload_layer_weights() after
    writing new weights to the config. The next signal-compute call
    must pick up the new values immediately, not wait for the 30s
    TTL to expire."""
    _reset_cache()
    cfg = tmp_path / "alerts_config.json"
    cfg.write_text(json.dumps({
        "composite_layer_weights": {
            "technical": 0.30, "macro": 0.10, "sentiment": 0.20, "onchain": 0.40,
        }
    }), encoding="utf-8")
    fake_module = tmp_path / "composite_signal.py"
    fake_module.write_text("# placeholder", encoding="utf-8")
    monkeypatch.setattr(composite_signal, "__file__", str(fake_module))

    out1 = composite_signal._current_layer_weights()
    assert out1["technical"] == 0.30

    # Optuna writes new weights.
    cfg.write_text(json.dumps({
        "composite_layer_weights": {
            "technical": 0.40, "macro": 0.20, "sentiment": 0.10, "onchain": 0.30,
        }
    }), encoding="utf-8")
    # Force-invalidate (the Optuna job calls this after its writeback).
    out2 = composite_signal.reload_layer_weights()
    assert out2["technical"] == 0.40, (
        "reload_layer_weights() didn't invalidate the cache — "
        "post-Optuna retune writeback won't propagate to the next signal."
    )


# ── 6. _regime_weights() applies learned NORMAL ─────────────────────────

def test_regime_weights_normal_uses_learned(tmp_path, monkeypatch):
    """The NORMAL regime in the regime-weight table must reflect the
    learned weights from _current_layer_weights(). CRISIS/TRENDING/
    RANGING are research-fixed and don't auto-tune."""
    _reset_cache()
    cfg = tmp_path / "alerts_config.json"
    cfg.write_text(json.dumps({
        "composite_layer_weights": {
            "technical": 0.40, "macro": 0.10, "sentiment": 0.20, "onchain": 0.30,
        }
    }), encoding="utf-8")
    fake_module = tmp_path / "composite_signal.py"
    fake_module.write_text("# placeholder", encoding="utf-8")
    monkeypatch.setattr(composite_signal, "__file__", str(fake_module))
    table = composite_signal._regime_weights()
    assert table["NORMAL"]["technical"] == 0.40, (
        "NORMAL regime didn't pick up the learned technical weight"
    )
    # CRISIS / TRENDING / RANGING must remain at their fixed values.
    assert table["CRISIS"]["technical"] == 0.10
    assert table["TRENDING"]["technical"] == 0.30
    assert table["RANGING"]["technical"] == 0.10
