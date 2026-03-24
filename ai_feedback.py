"""
ai_feedback.py — Crypto Signal Model v5.9.13
Enhanced AI feedback loop: A-F accuracy grading, health score (0-100),
smart alert threshold calibration, and Kelly Criterion position sizing.

Reads from the feedback_log SQLite table populated by crypto_model_core.py.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import database as db

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_LOOKBACK_DAYS   = 30        # rolling accuracy window
_MIN_SAMPLES     = 5         # minimum records before grading activates
_EXP_HALF_LIFE   = 14.0     # exponential time-weight half-life in days

# Alert calibration bounds
_MIN_CONF_FLOOR   = 60.0    # never auto-set alert threshold below 60%
_MIN_CONF_CEILING = 90.0    # never auto-set above 90%
_SMOOTH_FACTOR    = 0.20    # 80/20 smoothing on calibration
_MIN_CALIBRATION_SAMPLES = 8

# Kelly Criterion limits
_MAX_KELLY_FRACTION = 0.25   # cap Kelly at 25% of portfolio per trade
_MIN_KELLY_WIN_RATE = 0.40   # need ≥40% win rate to take any position


# ─── Core Accuracy Computation ────────────────────────────────────────────────

def compute_accuracy(pair: str = None) -> dict:
    """
    Compute rolling accuracy metrics from the feedback_log table.

    Args:
        pair: specific pair (e.g. 'BTC/USDT') or None for overall accuracy

    Returns:
        accuracy_pct:       % of signals where direction was correct (was_correct=1)
        avg_pnl_pct:        mean actual PnL % over the window
        win_rate:           same as accuracy_pct (directional correctness)
        sample_count:       number of resolved signals
        grade:              A / B / C / D / F
        health_score:       0–100 composite for UI display
        message:            human-readable status
    """
    conn = db._get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    try:
        if pair:
            rows = conn.execute(
                """
                SELECT was_correct, actual_pnl_pct, confidence, timestamp
                FROM feedback_log
                WHERE pair = ? AND timestamp >= ?
                  AND was_correct IS NOT NULL
                ORDER BY timestamp DESC LIMIT 500
                """,
                (pair, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT was_correct, actual_pnl_pct, confidence, timestamp
                FROM feedback_log
                WHERE timestamp >= ?
                  AND was_correct IS NOT NULL
                ORDER BY timestamp DESC LIMIT 1000
                """,
                (cutoff,),
            ).fetchall()
    except Exception as e:
        logger.error(f"compute_accuracy DB read failed: {e}")
        return _empty_result(pair)
    finally:
        conn.close()

    if len(rows) < _MIN_SAMPLES:
        return {
            "pair":          pair or "all",
            "accuracy_pct":  None,
            "avg_pnl_pct":   None,
            "win_rate":      None,
            "sample_count":  len(rows),
            "grade":         "N/A",
            "health_score":  50,
            "message":       f"Building history ({len(rows)}/{_MIN_SAMPLES} resolved signals). Keep scanning.",
        }

    now_ts = datetime.now(timezone.utc)
    w_correct = 0.0
    w_total   = 0.0
    weighted_pnls: list = []

    for row in rows:
        was_correct = row[0]
        pnl         = row[1] or 0.0
        ts_str      = row[3] or now_ts.isoformat()

        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now_ts - ts).total_seconds() / 86400)
        except Exception:
            age_days = 0.0

        weight = math.exp(-age_days / _EXP_HALF_LIFE)
        w_total += weight

        if was_correct == 1:
            w_correct += weight
        weighted_pnls.append((pnl, weight))

    if w_total == 0:
        return _empty_result(pair)

    accuracy_pct = w_correct / w_total * 100
    avg_pnl = (
        sum(p * w for p, w in weighted_pnls) / w_total
        if weighted_pnls else 0.0
    )

    # Grade based on accuracy (directional signal correctness)
    if accuracy_pct >= 75:
        grade = "A"
    elif accuracy_pct >= 62:
        grade = "B"
    elif accuracy_pct >= 50:
        grade = "C"
    elif accuracy_pct >= 38:
        grade = "D"
    else:
        grade = "F"

    # Health score: 50% accuracy weighting, 30% avg PnL, 20% grade consistency
    # consistency_score: A=100, B=80, C=60, D=40, F=20
    _grade_consistency = {"A": 100, "B": 80, "C": 60, "D": 40, "F": 20}
    consistency_score = _grade_consistency.get(grade, 50)
    pnl_score = min(100, max(0, 50 + avg_pnl * 10))   # 0% PnL → 50, +5% PnL → 100
    health_score = min(100, max(0, int(
        accuracy_pct   * 0.50
        + pnl_score    * 0.30
        + consistency_score * 0.20
    )))

    return {
        "pair":          pair or "all",
        "accuracy_pct":  round(accuracy_pct, 1),
        "avg_pnl_pct":   round(avg_pnl, 2),
        "win_rate":      round(accuracy_pct, 1),
        "sample_count":  len(rows),
        "grade":         grade,
        "health_score":  health_score,
        "message":       _health_message(health_score, grade),
    }


def _empty_result(pair) -> dict:
    return {
        "pair":          pair or "all",
        "accuracy_pct":  None,
        "avg_pnl_pct":   None,
        "win_rate":      None,
        "sample_count":  0,
        "grade":         "N/A",
        "health_score":  50,
        "message":       "No resolved signals yet — accuracy tracking begins after first exit.",
    }


def _health_message(score: int, grade: str) -> str:
    if score >= 80:
        return f"Model signals are highly accurate (Grade {grade}). Confidence in predictions is strong."
    elif score >= 60:
        return f"Model is performing well (Grade {grade}). Most directional calls are correct."
    elif score >= 40:
        return f"Model accuracy is fair (Grade {grade}). Market conditions may be choppy."
    else:
        return f"Model needs more resolved trades (Grade {grade}). Keep running scans."


# ─── Full Dashboard ────────────────────────────────────────────────────────────

def get_feedback_dashboard() -> dict:
    """
    Single call for the Streamlit AI feedback tab.

    Returns:
        overall:         compute_accuracy(pair=None) — overall metrics
        top_pairs:       list of per-pair accuracy dicts (sorted by health_score desc)
        total_signals:   total rows in feedback_log
        resolved_signals: rows with was_correct IS NOT NULL
        trend:           'improving' | 'stable' | 'declining' | 'building'
        last_updated:    ISO timestamp
    """
    overall = compute_accuracy(pair=None)

    # Top pairs by volume
    conn = db._get_conn()
    try:
        pair_rows = conn.execute(
            """
            SELECT pair, COUNT(*) as cnt
            FROM feedback_log
            WHERE was_correct IS NOT NULL
            GROUP BY pair ORDER BY cnt DESC LIMIT 10
            """,
        ).fetchall()
        pairs = [r[0] for r in pair_rows]

        counts = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN was_correct IS NOT NULL THEN 1 ELSE 0 END) FROM feedback_log"
        ).fetchone()
        total_signals    = counts[0] or 0
        resolved_signals = counts[1] or 0
    except Exception:
        pairs = []
        total_signals = resolved_signals = 0
    finally:
        conn.close()

    top_pairs = []
    for p in pairs:
        acc = compute_accuracy(pair=p)
        top_pairs.append(acc)
    top_pairs.sort(key=lambda x: x.get("health_score", 0), reverse=True)

    return {
        "overall":          overall,
        "top_pairs":        top_pairs,
        "total_signals":    total_signals,
        "resolved_signals": resolved_signals,
        "trend":            _compute_trend(),
        "last_updated":     datetime.now(timezone.utc).isoformat(),
    }


def _compute_trend() -> str:
    """Returns trend based on recent vs prior 7-day accuracy."""
    conn = db._get_conn()
    now_ts       = datetime.now(timezone.utc)
    recent_cut   = (now_ts - timedelta(days=7)).isoformat()
    previous_cut = (now_ts - timedelta(days=14)).isoformat()

    def _wr(after, before=None):
        q    = "SELECT COUNT(*), SUM(was_correct) FROM feedback_log WHERE was_correct IS NOT NULL AND timestamp >= ?"
        args = [after]
        if before:
            q += " AND timestamp < ?"
            args.append(before)
        try:
            r = conn.execute(q, args).fetchone()
            total = r[0] or 0
            wins  = r[1] or 0
            return wins / total if total >= _MIN_SAMPLES else None
        except Exception:
            return None

    try:
        recent_wr   = _wr(recent_cut)
        previous_wr = _wr(previous_cut, recent_cut)
        if recent_wr is None or previous_wr is None:
            return "building"
        if recent_wr > previous_wr * 1.05:
            return "improving"
        elif recent_wr < previous_wr * 0.95:
            return "declining"
        return "stable"
    except Exception:
        return "building"
    finally:
        conn.close()


# ─── Smart Alert Threshold Calibration ────────────────────────────────────────

def calibrate_alert_thresholds() -> dict:
    """
    Auto-calibrate min_confidence alert threshold using accurate historical signals.

    Strategy:
      - Collect confidence values for all signals where was_correct=1.
      - Set min_confidence to the 75th percentile of those values.
      - Apply 80/20 smoothing against the current threshold.
      - Save back to alerts_config.json.

    Returns a summary dict for UI display.
    """
    from alerts import load_alerts_config, save_alerts_config

    conn = db._get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    try:
        rows = conn.execute(
            """
            SELECT confidence FROM feedback_log
            WHERE was_correct = 1 AND timestamp >= ?
              AND confidence IS NOT NULL
            ORDER BY confidence
            """,
            (cutoff,),
        ).fetchall()
    except Exception as e:
        logger.error(f"Calibration DB read failed: {e}")
        return {"calibrated": False, "reason": str(e), "samples": 0}
    finally:
        conn.close()

    confident_vals = [float(r[0]) for r in rows if r[0] is not None]

    if len(confident_vals) < _MIN_CALIBRATION_SAMPLES:
        return {
            "calibrated":    False,
            "reason":        f"Need {_MIN_CALIBRATION_SAMPLES} accurate signals, have {len(confident_vals)}.",
            "samples":       len(confident_vals),
            "new_threshold": None,
        }

    confident_vals.sort()
    p75_idx  = int(0.75 * (len(confident_vals) - 1))
    p75_conf = confident_vals[p75_idx]
    p75_conf = max(_MIN_CONF_FLOOR, min(_MIN_CONF_CEILING, p75_conf))

    config     = load_alerts_config()
    old_thresh = float(config.get("min_confidence", 70))

    new_thresh = round(old_thresh * (1 - _SMOOTH_FACTOR) + p75_conf * _SMOOTH_FACTOR, 1)
    new_thresh = max(_MIN_CONF_FLOOR, min(_MIN_CONF_CEILING, new_thresh))

    config["min_confidence"]          = new_thresh
    config["_calibrated_at"]          = datetime.now(timezone.utc).isoformat()
    config["_calibration_samples"]    = len(confident_vals)
    config["_raw_p75_confidence"]     = round(p75_conf, 1)
    save_alerts_config(config)

    delta     = new_thresh - old_thresh
    direction = "raised" if delta > 0.5 else ("lowered" if delta < -0.5 else "unchanged")
    logger.info(
        f"Smart Alert Calibration: threshold {direction} {old_thresh:.1f}% → {new_thresh:.1f}% "
        f"(p75={p75_conf:.1f}%, n={len(confident_vals)})"
    )
    return {
        "calibrated":    True,
        "old_threshold": old_thresh,
        "new_threshold": new_thresh,
        "p75_confidence": round(p75_conf, 1),
        "direction":     direction,
        "samples":       len(confident_vals),
        "reason":        f"75th-percentile of {len(confident_vals)} accurate signal confidences = {p75_conf:.1f}%",
    }


def get_calibration_report() -> dict:
    """Return the latest calibration metadata for UI display."""
    from alerts import load_alerts_config
    config = load_alerts_config()
    return {
        "min_confidence":       config.get("min_confidence", 70),
        "calibrated_at":        config.get("_calibrated_at"),
        "calibration_samples":  config.get("_calibration_samples"),
        "raw_p75_confidence":   config.get("_raw_p75_confidence"),
    }


# ─── Kelly Criterion Position Sizing ──────────────────────────────────────────

def kelly_position_size(
    pair: str,
    portfolio_size_usd: float,
    avg_win_pct: float = None,
    avg_loss_pct: float = None,
) -> dict:
    """
    Calculate Kelly Criterion position size for a given pair.

    Uses empirical win rate from feedback_log. If avg_win_pct / avg_loss_pct
    are not provided, derives them from the feedback history.

    Args:
        pair:               e.g. 'BTC/USDT'
        portfolio_size_usd: total portfolio value in USD
        avg_win_pct:        optional override for average win size %
        avg_loss_pct:       optional override for average loss size %

    Returns:
        fraction:     Kelly fraction (capped at _MAX_KELLY_FRACTION)
        position_usd: recommended position size in USD
        win_rate:     empirical win rate used
        basis:        human-readable explanation
    """
    acc = compute_accuracy(pair=pair)
    win_rate = acc.get("win_rate")

    if win_rate is None or win_rate < _MIN_KELLY_WIN_RATE * 100:
        return {
            "fraction":     0.0,
            "position_usd": 0.0,
            "win_rate":     win_rate,
            "basis":        f"Insufficient win rate ({win_rate or 'N/A'}%) for Kelly sizing — minimum {_MIN_KELLY_WIN_RATE*100:.0f}% required.",
        }

    w = win_rate / 100   # decimal win rate

    # Derive win/loss sizes from DB if not provided
    if avg_win_pct is None or avg_loss_pct is None:
        conn = db._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).isoformat()
        try:
            wins  = conn.execute(
                "SELECT AVG(actual_pnl_pct) FROM feedback_log WHERE pair=? AND was_correct=1 AND timestamp>=? AND actual_pnl_pct IS NOT NULL",
                (pair, cutoff),
            ).fetchone()[0]
            losses = conn.execute(
                "SELECT AVG(ABS(actual_pnl_pct)) FROM feedback_log WHERE pair=? AND was_correct=0 AND timestamp>=? AND actual_pnl_pct IS NOT NULL",
                (pair, cutoff),
            ).fetchone()[0]
        except Exception:
            wins = losses = None
        finally:
            conn.close()

        avg_win_pct  = float(wins  or 2.0)    # default 2% win
        avg_loss_pct = float(losses or 1.5)   # default 1.5% loss

    b = avg_win_pct / max(avg_loss_pct, 0.01)   # reward:risk ratio
    kelly = (w * b - (1 - w)) / b               # Kelly formula
    kelly = max(0.0, kelly)                      # never go negative
    kelly = round(min(kelly, _MAX_KELLY_FRACTION), 4)   # cap at max

    position_usd = round(kelly * portfolio_size_usd, 2)

    return {
        "fraction":     kelly,
        "position_usd": position_usd,
        "win_rate":     round(win_rate, 1),
        "avg_win_pct":  round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "reward_risk":  round(b, 2),
        "basis":        (
            f"Kelly({w:.0%} win, {b:.2f}R:R) → {kelly:.1%} of portfolio = ${position_usd:,.0f}"
        ),
    }


def get_all_pair_kelly_sizes(portfolio_size_usd: float) -> dict:
    """
    Compute Kelly position sizes for all pairs that have sufficient feedback history.
    Returns {pair: kelly_result_dict}.
    """
    conn = db._get_conn()
    try:
        pairs = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT pair FROM feedback_log WHERE was_correct IS NOT NULL"
            ).fetchall()
        ]
    except Exception:
        pairs = []
    finally:
        conn.close()

    results = {}
    for p in pairs:
        results[p] = kelly_position_size(p, portfolio_size_usd)
    return results


# ─── Win Rates Export ─────────────────────────────────────────────────────────

def get_pair_win_rates() -> dict:
    """
    Return empirical win rates as decimals {pair: win_rate_decimal}.
    Used for confidence-weighted ensemble and Kelly sizing.
    """
    conn = db._get_conn()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    try:
        rows = conn.execute(
            """
            SELECT pair,
                   COUNT(*) as total,
                   SUM(was_correct) as wins
            FROM feedback_log
            WHERE was_correct IS NOT NULL AND timestamp >= ?
            GROUP BY pair HAVING total >= ?
            """,
            (cutoff, _MIN_SAMPLES),
        ).fetchall()
        return {r[0]: round(float(r[2] or 0) / float(r[1]), 4) for r in rows if r[1]}
    except Exception as e:
        logger.error(f"get_pair_win_rates failed: {e}")
        return {}
    finally:
        conn.close()
