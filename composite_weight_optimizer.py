"""composite_weight_optimizer.py

C-fix-21b (2026-05-02): daily background job that retunes the 4-layer
composite-signal weights from resolved feedback outcomes. Closes the
last open gap in the AI feedback loop.

Architecture:

  1. SOURCE       — feedback_log rows where:
                      - was_correct IS NOT NULL (resolved trades only)
                      - layer_ta_score, layer_macro_score, layer_sent_score,
                        layer_onchain_score are all NOT NULL (rows logged
                        post-C-fix-21b)
                      - resolved_at within the last 90 days

  2. OBJECTIVE    — minimize negative log-loss + L2 regularization
                    toward the research-baseline defaults.

                    Loss(w) = -mean( y * log(s_w) + (1-y) * log(1-s_w) )
                              + lambda * Σ (w_i - w_default_i)²

                    where:
                      y     = was_correct (binary outcome)
                      s_w   = sigmoid(Σ w_i * layer_score_i)
                              (clamped to [1e-6, 1-1e-6] for log safety)
                      w_default_i = research baseline (0.20/0.20/0.25/0.35)
                      lambda = 0.10  (10% L2 penalty — prevents the
                                     learned weights from drifting more
                                     than ~10% from defaults per retune)

  3. CONSTRAINTS  — each w_i ∈ [0.05, 0.60]   (avoid zero-weighting any
                                              layer; cap at 60% to avoid
                                              over-concentration)
                    Σ w_i = 1.0               (enforced by normalization
                                              after Optuna sampling)

  4. SAMPLER      — Optuna TPESampler, 100 trials. Default seed for
                    reproducibility per retune (so two consecutive runs
                    on the same data converge to the same result).

  5. WRITEBACK    — alerts_config.json["composite_layer_weights"] dict.
                    Calls composite_signal.reload_layer_weights() to
                    invalidate the 30s cache so the next signal-compute
                    call picks up the new weights.

  6. SAFETY       — when fewer than _MIN_SAMPLES resolved rows have
                    layer scores, the job is a NO-OP. The Optuna study
                    isn't even created. This is the cold-start window
                    after C-fix-21b ships — rows accumulate over 2-4
                    weeks before the optimizer engages meaningfully.

The job is wired into app.py's BackgroundScheduler at 04:00 UTC daily
(low-activity window). It can also be invoked manually via the Settings
→ Dev Tools page for testing — see C-fix-22.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Minimum resolved-feedback rows with non-null layer scores required to
# attempt a retune. Below this, the job is a no-op. 50 was chosen as
# the smallest sample where Optuna can reliably distinguish a 5%
# weight shift from random noise.
_MIN_SAMPLES = 50

# Optuna trial budget. 100 trials × ~50ms/trial = ~5s wall-clock.
# Well within the 90s "expensive job" budget the scheduler reserves.
_N_TRIALS = 100

# L2 regularization strength toward defaults.
_L2_LAMBDA = 0.10

# Per-weight bounds during sampling. The normalize-to-sum-1 step after
# sampling can push individual weights beyond these bounds slightly,
# but the post-normalization values are bounded too because at least
# one weight remains in the per-weight bound.
_W_MIN = 0.05
_W_MAX = 0.60

# Where to persist the learned weights.
# AUDIT-2026-05-06 (W2 Tier 8 P1): align with alerts.py — write to the
# persistent-disk path so optimizer-tuned weights survive Render
# redeploys. Falls back to the legacy cwd-adjacent path if the
# alerts module can't be imported (e.g. unit-test isolation).
def _resolve_config_path() -> Path:
    try:
        from alerts import _ALERTS_CONFIG_FILE as _disk_path
        return Path(_disk_path)
    except Exception:
        return Path(__file__).resolve().parent / "alerts_config.json"


_CONFIG_PATH = _resolve_config_path()


def _default_weights() -> dict:
    """Research baseline — must match composite_signal._DEFAULT_W_*."""
    return {
        "technical": 0.20,
        "macro":     0.20,
        "sentiment": 0.25,
        "onchain":   0.35,
    }


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid clamped to [1e-6, 1-1e-6] for log safety."""
    if x >= 0:
        z = math.exp(-x)
        s = 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        s = z / (1.0 + z)
    return max(1e-6, min(1.0 - 1e-6, s))


def _normalize(w: dict) -> dict:
    """Scale a 4-weight dict so values sum to 1.0. Defends against
    Optuna-sampled values that don't naturally sum to 1."""
    _total = sum(w.values())
    if _total <= 0:
        return _default_weights()
    return {k: v / _total for k, v in w.items()}


def _load_resolved_feedback_rows():
    """Pull resolved rows from feedback_log with non-null layer scores.

    Returns a list of dicts: each dict has keys
    `technical`, `macro`, `sentiment`, `onchain`, `was_correct`.
    """
    try:
        import database as _db
    except Exception as _e:
        logger.warning("[Optuna] cannot import database module: %s", _e)
        return []
    try:
        df = _db.get_resolved_feedback_df(days=90)
    except Exception as _e:
        logger.warning("[Optuna] get_resolved_feedback_df failed: %s", _e)
        return []
    if df is None or df.empty:
        return []
    # Filter rows where ALL 4 layer scores are present.
    cols = ["layer_ta_score", "layer_macro_score",
            "layer_sent_score", "layer_onchain_score", "was_correct"]
    if not all(c in df.columns for c in cols):
        # Schema migration hasn't run yet on this DB.
        return []
    df = df.dropna(subset=cols)
    if df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "technical": float(r["layer_ta_score"]),
            "macro":     float(r["layer_macro_score"]),
            "sentiment": float(r["layer_sent_score"]),
            "onchain":   float(r["layer_onchain_score"]),
            "was_correct": int(r["was_correct"]),
        })
    return rows


def _compute_loss(w_norm: dict, samples: list) -> float:
    """Weighted log-loss + L2 regularization toward defaults."""
    _defaults = _default_weights()
    # Log-loss term.
    _ll = 0.0
    for s in samples:
        _z = (
            w_norm["technical"] * s["technical"]
            + w_norm["macro"]    * s["macro"]
            + w_norm["sentiment"]* s["sentiment"]
            + w_norm["onchain"]  * s["onchain"]
        )
        _p = _sigmoid(_z)
        _y = s["was_correct"]
        _ll -= _y * math.log(_p) + (1 - _y) * math.log(1.0 - _p)
    _ll /= len(samples)
    # L2 toward defaults.
    _l2 = sum((w_norm[k] - _defaults[k]) ** 2 for k in w_norm)
    return _ll + _L2_LAMBDA * _l2


def retune_layer_weights() -> dict:
    """Run one retune pass.

    Returns:
        {
            "status":        "ok" | "no_op" | "error",
            "n_samples":     int,
            "old_weights":   dict | None,
            "new_weights":   dict | None,
            "loss_old":      float | None,
            "loss_new":      float | None,
            "improvement":   float | None,   # loss_old - loss_new
            "reason":        str (when status != "ok"),
        }
    """
    samples = _load_resolved_feedback_rows()
    if len(samples) < _MIN_SAMPLES:
        return {
            "status":     "no_op",
            "n_samples":  len(samples),
            "reason":     f"insufficient samples ({len(samples)} < {_MIN_SAMPLES})",
            "old_weights": None,
            "new_weights": None,
            "loss_old":   None,
            "loss_new":   None,
            "improvement": None,
        }

    try:
        import optuna
    except ImportError:
        return {
            "status":     "error",
            "n_samples":  len(samples),
            "reason":     "optuna not installed",
            "old_weights": None,
            "new_weights": None,
            "loss_old":   None,
            "loss_new":   None,
            "improvement": None,
        }

    # Suppress Optuna's per-trial logging — the job runs daily and would
    # otherwise spam logs with 100 lines.
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # Load current weights as the starting point + comparison baseline.
    try:
        _existing_cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8")) if _CONFIG_PATH.exists() else {}
    except Exception:
        _existing_cfg = {}
    _old_weights = _existing_cfg.get("composite_layer_weights") or _default_weights()
    # Validate _old_weights structure; fall back to defaults if malformed.
    if (
        not isinstance(_old_weights, dict)
        or set(_old_weights) != {"technical", "macro", "sentiment", "onchain"}
    ):
        _old_weights = _default_weights()
    _loss_old = _compute_loss(_normalize(_old_weights), samples)

    def _objective(trial):
        w_raw = {
            "technical": trial.suggest_float("technical", _W_MIN, _W_MAX),
            "macro":     trial.suggest_float("macro",     _W_MIN, _W_MAX),
            "sentiment": trial.suggest_float("sentiment", _W_MIN, _W_MAX),
            "onchain":   trial.suggest_float("onchain",   _W_MIN, _W_MAX),
        }
        w_norm = _normalize(w_raw)
        return _compute_loss(w_norm, samples)

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(_objective, n_trials=_N_TRIALS, show_progress_bar=False)

    _best = _normalize(study.best_params)
    _loss_new = study.best_value

    # Only persist if the new weights actually improved on the existing.
    if _loss_new >= _loss_old:
        return {
            "status":     "no_op",
            "n_samples":  len(samples),
            "reason":     f"new loss {_loss_new:.4f} >= old loss {_loss_old:.4f}; preserving existing weights",
            "old_weights": _old_weights,
            "new_weights": _old_weights,
            "loss_old":   _loss_old,
            "loss_new":   _loss_new,
            "improvement": 0.0,
        }

    # Writeback to alerts_config.json.
    try:
        _existing_cfg["composite_layer_weights"] = _best
        _CONFIG_PATH.write_text(
            json.dumps(_existing_cfg, indent=2, sort_keys=True), encoding="utf-8"
        )
    except Exception as _e:
        return {
            "status":     "error",
            "n_samples":  len(samples),
            "reason":     f"alerts_config.json writeback failed: {_e}",
            "old_weights": _old_weights,
            "new_weights": _best,
            "loss_old":   _loss_old,
            "loss_new":   _loss_new,
            "improvement": _loss_old - _loss_new,
        }

    # Force composite_signal to drop its 30s cache so the next signal
    # compute call picks up the new weights immediately.
    try:
        import composite_signal
        composite_signal.reload_layer_weights()
    except Exception as _e:
        logger.debug("[Optuna] composite_signal.reload_layer_weights failed: %s", _e)

    logger.info(
        "[Optuna] retune complete: n=%d, loss %.4f → %.4f (Δ=%.4f), weights=%s",
        len(samples), _loss_old, _loss_new, _loss_old - _loss_new, _best
    )

    return {
        "status":     "ok",
        "n_samples":  len(samples),
        "old_weights": _old_weights,
        "new_weights": _best,
        "loss_old":   _loss_old,
        "loss_new":   _loss_new,
        "improvement": _loss_old - _loss_new,
    }
