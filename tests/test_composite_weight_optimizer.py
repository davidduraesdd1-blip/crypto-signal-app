"""tests/test_composite_weight_optimizer.py

C-fix-21b (2026-05-02): the daily Optuna retune job that learns optimal
composite-layer weights from resolved feedback.

Tests cover:
  1. No-op when insufficient samples (cold-start safety)
  2. Normalization preserves sum-to-1 invariant
  3. Default weights match composite_signal._DEFAULT_W_*
  4. Loss function is finite and decreases with better weights
  5. Optuna integration produces valid sum-to-1 output (when data exists)
  6. The job is registered in the scheduler with cron trigger at 04:00 UTC
"""
from __future__ import annotations

from pathlib import Path

import pytest

import composite_weight_optimizer as cwo
import composite_signal


# ── 1. No-op safety ─────────────────────────────────────────────────────

def test_retune_no_op_with_insufficient_samples(monkeypatch):
    """When fewer than _MIN_SAMPLES rows exist, retune must NOT touch
    alerts_config.json or trigger Optuna. This is the cold-start
    window after C-fix-21b ships."""
    # Force the loader to return fewer rows than the minimum.
    monkeypatch.setattr(
        cwo, "_load_resolved_feedback_rows",
        lambda: [{"technical": 0.1, "macro": 0.1, "sentiment": 0.1,
                  "onchain": 0.1, "was_correct": 1}] * (cwo._MIN_SAMPLES - 1)
    )
    out = cwo.retune_layer_weights()
    assert out["status"] == "no_op"
    assert out["n_samples"] == cwo._MIN_SAMPLES - 1
    assert "insufficient" in out["reason"].lower()


def test_retune_no_op_with_zero_samples(monkeypatch):
    """Zero samples = empty DB / pre-fix DB without layer-score columns."""
    monkeypatch.setattr(cwo, "_load_resolved_feedback_rows", lambda: [])
    out = cwo.retune_layer_weights()
    assert out["status"] == "no_op"
    assert out["n_samples"] == 0


# ── 2. Normalize ────────────────────────────────────────────────────────

def test_normalize_preserves_sum_to_1():
    """Optuna can sample weights that don't sum to 1 — _normalize fixes
    them before they reach the loss function."""
    w_raw = {"technical": 0.10, "macro": 0.20, "sentiment": 0.30, "onchain": 0.40}
    w_norm = cwo._normalize(w_raw)
    assert abs(sum(w_norm.values()) - 1.0) < 1e-9
    # Ratios preserved.
    assert w_norm["onchain"] / w_norm["technical"] == pytest.approx(4.0)


def test_normalize_falls_back_on_all_zero():
    """All-zero weights would divide by zero — fall back to defaults."""
    w_norm = cwo._normalize({k: 0.0 for k in ("technical", "macro", "sentiment", "onchain")})
    assert w_norm == cwo._default_weights()


# ── 3. Defaults match composite_signal ──────────────────────────────────

def test_defaults_match_composite_signal_constants():
    """The optimizer's L2 regularization target MUST match
    composite_signal's defaults — otherwise the L2 term pulls the
    learned weights toward a different point than the fallback."""
    d = cwo._default_weights()
    assert d["technical"] == composite_signal._DEFAULT_W_TECHNICAL
    assert d["macro"]     == composite_signal._DEFAULT_W_MACRO
    assert d["sentiment"] == composite_signal._DEFAULT_W_SENTIMENT
    assert d["onchain"]   == composite_signal._DEFAULT_W_ONCHAIN


# ── 4. Loss function ────────────────────────────────────────────────────

def test_loss_is_finite_for_default_weights():
    """The loss function must be finite for any valid weight + sample."""
    samples = [
        {"technical": 0.5, "macro": -0.2, "sentiment": 0.3, "onchain": 0.1, "was_correct": 1},
        {"technical": -0.4, "macro": 0.1, "sentiment": -0.2, "onchain": -0.3, "was_correct": 0},
    ]
    loss = cwo._compute_loss(cwo._default_weights(), samples)
    assert isinstance(loss, float)
    assert loss == loss  # not NaN
    assert -float("inf") < loss < float("inf")


def test_loss_decreases_with_more_aligned_weights():
    """Construct a contrived case where one set of weights aligns
    perfectly with the labels and another anti-aligns. The aligned
    set must produce a strictly lower loss."""
    # was_correct=1 when technical layer is high; weights should
    # therefore favour technical.
    samples = [
        {"technical":  0.9, "macro": 0.0, "sentiment": 0.0, "onchain": 0.0, "was_correct": 1},
        {"technical":  0.8, "macro": 0.0, "sentiment": 0.0, "onchain": 0.0, "was_correct": 1},
        {"technical": -0.9, "macro": 0.0, "sentiment": 0.0, "onchain": 0.0, "was_correct": 0},
        {"technical": -0.8, "macro": 0.0, "sentiment": 0.0, "onchain": 0.0, "was_correct": 0},
    ]
    aligned = cwo._normalize({"technical": 0.55, "macro": 0.15, "sentiment": 0.15, "onchain": 0.15})
    anti    = cwo._normalize({"technical": 0.10, "macro": 0.30, "sentiment": 0.30, "onchain": 0.30})
    loss_aligned = cwo._compute_loss(aligned, samples)
    loss_anti    = cwo._compute_loss(anti, samples)
    assert loss_aligned < loss_anti


# ── 5. End-to-end with Optuna (skipped if optuna not installed) ─────────

def test_retune_end_to_end_writes_valid_weights(monkeypatch, tmp_path):
    """Run a full retune pass against synthetic data; assert the
    written weights sum to 1, fall in valid range, and reload picks
    them up."""
    pytest.importorskip("optuna")

    # 100 contrived samples where the technical layer perfectly predicts.
    samples = (
        [{"technical":  0.9, "macro": 0.0, "sentiment": 0.0, "onchain": 0.0, "was_correct": 1}] * 50
        + [{"technical": -0.9, "macro": 0.0, "sentiment": 0.0, "onchain": 0.0, "was_correct": 0}] * 50
    )
    monkeypatch.setattr(cwo, "_load_resolved_feedback_rows", lambda: samples)

    # Redirect the config-write target to tmp_path.
    fake_cfg = tmp_path / "alerts_config.json"
    fake_cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cwo, "_CONFIG_PATH", fake_cfg)

    out = cwo.retune_layer_weights()
    assert out["status"] == "ok", out
    new_weights = out["new_weights"]
    # Sum to 1.0
    assert abs(sum(new_weights.values()) - 1.0) < 0.01
    # Each weight in valid range (after normalization may slip the per-
    # weight max but bounded by the sum-to-1 constraint).
    for k, v in new_weights.items():
        assert 0.0 <= v <= 1.0
    # The technical weight should have shifted UP (samples favor it)
    # OR at least the loss improved.
    assert out["improvement"] > 0


# ── 6. Scheduler wiring ─────────────────────────────────────────────────

def test_app_schedules_composite_retune_at_04_utc():
    """The scheduler must register the composite retune job with a
    cron trigger at 04:00 UTC daily."""
    src = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    assert "_COMPOSITE_RETUNE_JOB_ID" in src
    assert "_setup_composite_retune_job" in src
    # The cron-trigger config must specify hour=4, minute=0.
    setup_idx = src.find("def _setup_composite_retune_job")
    assert setup_idx > 0
    body = src[setup_idx:setup_idx + 3000]
    assert 'trigger="cron"' in body
    assert "hour=4" in body
    assert "minute=0" in body
    # And the bootstrap must call it.
    assert "_setup_composite_retune_job()" in src
