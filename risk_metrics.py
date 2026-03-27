"""
risk_metrics.py — Crypto Signal Model v5.9.13
Value at Risk (VaR) and Conditional VaR (CVaR/Expected Shortfall) for signal portfolios.
Fractional Kelly position sizing (#50).

Two methods:
  1. Historical VaR  — uses actual_pnl_pct from feedback_log (most accurate, data-driven)
  2. Parametric VaR  — Gaussian assumption (used when feedback history is insufficient)

Also provides portfolio-level position risk aggregation.
"""

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

import database as db

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_VAR_CONFIDENCE   = [0.90, 0.95, 0.99]   # confidence levels
_MIN_HIST_SAMPLES = 20                    # minimum resolved trades for historical VaR
_LOOKBACK_DAYS    = 90                    # rolling window for historical VaR


# ─── Historical VaR / CVaR ─────────────────────────────────────────────────────

def compute_historical_var(
    pair: str = None,
    confidence: float = 0.95,
    portfolio_size_usd: float = 10_000.0,
    position_pct: float = 10.0,
) -> dict:
    """
    Historical simulation VaR using actual PnL from the feedback_log.

    Args:
        pair:               specific pair or None for all pairs combined
        confidence:         VaR confidence level (0.90, 0.95, 0.99)
        portfolio_size_usd: total portfolio in USD for dollar VaR
        position_pct:       % of portfolio per position (for dollar conversion)

    Returns:
        var_pct:   VaR as % (potential loss at confidence level)
        cvar_pct:  CVaR/Expected Shortfall as % (average of tail losses)
        var_usd:   VaR in USD
        cvar_usd:  CVaR in USD
        n_samples: number of historical trades used
        method:    'historical' or 'parametric_fallback'
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    conn = None
    try:
        conn = db._get_conn()
        if pair:
            rows = conn.execute(
                "SELECT actual_pnl_pct FROM feedback_log WHERE pair=? AND timestamp>=? AND actual_pnl_pct IS NOT NULL",
                (pair, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT actual_pnl_pct FROM feedback_log WHERE timestamp>=? AND actual_pnl_pct IS NOT NULL",
                (cutoff,),
            ).fetchall()
    except Exception as e:
        logger.error(f"Historical VaR DB read failed: {e}")
        rows = []
    finally:
        if conn is not None:
            conn.close()

    pnl_returns = np.array([float(r[0]) for r in rows])
    position_usd = portfolio_size_usd * position_pct / 100

    if len(pnl_returns) >= _MIN_HIST_SAMPLES:
        # Historical simulation: sort losses, take percentile
        sorted_pnl = np.sort(pnl_returns)
        idx        = int((1 - confidence) * len(sorted_pnl))
        idx        = max(0, min(idx, len(sorted_pnl) - 1))

        var_pct  = float(-sorted_pnl[idx])           # VaR = loss at threshold
        var_pct  = max(0.0, var_pct)
        tail     = sorted_pnl[:idx]                  # losses worse than VaR threshold
        cvar_pct = float(-np.mean(tail)) if len(tail) > 0 else var_pct
        cvar_pct = max(0.0, cvar_pct)

        return {
            "pair":          pair or "all",
            "confidence":    confidence,
            "var_pct":       round(var_pct, 2),
            "cvar_pct":      round(cvar_pct, 2),
            "var_usd":       round(var_pct / 100 * position_usd, 2),
            "cvar_usd":      round(cvar_pct / 100 * position_usd, 2),
            "n_samples":     len(pnl_returns),
            "method":        "historical",
            "position_usd":  round(position_usd, 2),
        }
    else:
        # Parametric fallback: use mean/std of available data or defaults
        if len(pnl_returns) >= 3:
            mu  = float(np.mean(pnl_returns))
            std = float(np.std(pnl_returns))
        else:
            mu  = 0.0
            std = 5.0   # default 5% position volatility

        return _parametric_var(pair, confidence, mu, std, position_usd, len(pnl_returns))


def _parametric_var(
    pair, confidence: float, mu: float, std: float,
    position_usd: float, n_samples: int,
) -> dict:
    """Gaussian parametric VaR (fallback when insufficient historical data)."""
    z_scores = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}
    z = z_scores.get(confidence, 1.645)

    var_pct  = max(0.0, -(mu - z * std))
    # CVaR for normal distribution: phi(z) / (1-c) * std - mu
    from math import exp, pi, sqrt
    phi_z    = exp(-z**2 / 2) / sqrt(2 * pi)
    cvar_pct = max(0.0, -(mu - phi_z / (1 - confidence) * std))

    return {
        "pair":          pair or "all",
        "confidence":    confidence,
        "var_pct":       round(var_pct, 2),
        "cvar_pct":      round(cvar_pct, 2),
        "var_usd":       round(var_pct / 100 * position_usd, 2),
        "cvar_usd":      round(cvar_pct / 100 * position_usd, 2),
        "n_samples":     n_samples,
        "method":        "parametric_fallback",
        "position_usd":  round(position_usd, 2),
    }


# ─── Multi-Confidence VaR Summary ─────────────────────────────────────────────

def compute_var_summary(
    pair: str = None,
    portfolio_size_usd: float = 10_000.0,
    position_pct: float = 10.0,
) -> dict:
    """
    Compute VaR and CVaR at 90%, 95%, and 99% confidence levels.

    Returns:
        var_90, var_95, var_99: VaR dicts at each confidence level
        cvar_90, cvar_95, cvar_99: CVaR dicts
        sharpe_ratio: signal return / signal volatility
        sortino_ratio: signal return / downside deviation
        max_drawdown_pct: maximum observed drawdown in feedback_log
    """
    # PERF-VAR: fetch the return data once and compute all confidence levels
    # in-memory.  Previous code called compute_historical_var() 3× (3 separate
    # DB round-trips) then made a 4th query for Sharpe/Sortino/drawdown.
    # New code: 1 query → compute all 3 VaR levels + risk metrics in-memory.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    conn = None
    try:
        conn = db._get_conn()
        if pair:
            rows = conn.execute(
                "SELECT actual_pnl_pct FROM feedback_log "
                "WHERE pair=? AND timestamp>=? AND actual_pnl_pct IS NOT NULL",
                (pair, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT actual_pnl_pct FROM feedback_log "
                "WHERE timestamp>=? AND actual_pnl_pct IS NOT NULL",
                (cutoff,),
            ).fetchall()
    except Exception as _e:
        logger.error(f"VaR summary DB read failed: {_e}")
        rows = []
    finally:
        if conn is not None:
            conn.close()

    pnl_returns = np.array([float(r[0]) for r in rows])
    position_usd = portfolio_size_usd * position_pct / 100

    def _var_from_data(confidence: float) -> dict:
        """Compute historical VaR/CVaR from the already-fetched pnl_returns array."""
        if len(pnl_returns) >= _MIN_HIST_SAMPLES:
            sorted_pnl = np.sort(pnl_returns)
            idx        = int((1 - confidence) * len(sorted_pnl))
            idx        = max(0, min(idx, len(sorted_pnl) - 1))
            var_pct    = float(max(0.0, -sorted_pnl[idx]))
            tail       = sorted_pnl[:idx]
            cvar_pct   = float(max(0.0, -np.mean(tail))) if len(tail) > 0 else var_pct
            return {
                "pair":          pair or "all",
                "confidence":    confidence,
                "var_pct":       round(var_pct, 2),
                "cvar_pct":      round(cvar_pct, 2),
                "var_usd":       round(var_pct / 100 * position_usd, 2),
                "cvar_usd":      round(cvar_pct / 100 * position_usd, 2),
                "n_samples":     len(pnl_returns),
                "method":        "historical",
                "position_usd":  round(position_usd, 2),
            }
        else:
            # Parametric fallback using the same shared data
            if len(pnl_returns) >= 3:
                mu  = float(np.mean(pnl_returns))
                std = float(np.std(pnl_returns))
            else:
                mu  = 0.0
                std = 5.0
            return _parametric_var(pair, confidence, mu, std, position_usd, len(pnl_returns))

    var_90 = _var_from_data(0.90)
    var_95 = _var_from_data(0.95)
    var_99 = _var_from_data(0.99)

    pnl = pnl_returns  # alias for Sharpe/Sortino/drawdown block below

    if len(pnl) >= 5:
        mu       = float(np.mean(pnl))
        std      = float(np.std(pnl))
        down_std = float(np.std(pnl[pnl < 0])) if (pnl < 0).any() else std

        sharpe  = round(mu / std, 3) if std > 0 else 0.0
        sortino = round(mu / down_std, 3) if down_std > 0 else 0.0

        # Max drawdown: max cumulative loss in equity curve
        equity = np.cumprod(1 + pnl / 100)
        roll_max = np.maximum.accumulate(equity)
        # Guard against division by zero when roll_max reaches 0 (catastrophic loss)
        safe_roll_max = np.where(roll_max == 0, np.nan, roll_max)
        drawdowns = (roll_max - equity) / safe_roll_max * 100
        max_dd = float(np.nanmax(drawdowns)) if len(drawdowns) > 0 else 0.0
    else:
        sharpe = sortino = max_dd = 0.0

    return {
        "pair":             pair or "all",
        "var_90":           var_90,
        "var_95":           var_95,
        "var_99":           var_99,
        "sharpe_ratio":     sharpe,
        "sortino_ratio":    sortino,
        "max_drawdown_pct": round(max_dd, 2),
        "n_samples":        len(pnl),
        "lookback_days":    _LOOKBACK_DAYS,
        "portfolio_size_usd": portfolio_size_usd,
    }


# ─── Portfolio-Level Risk Aggregation ─────────────────────────────────────────

def compute_portfolio_risk(
    open_positions: list,
    portfolio_size_usd: float,
    correlation_assumption: float = 0.30,
) -> dict:
    """
    Aggregate VaR across multiple open positions.

    Args:
        open_positions: list of {'pair': str, 'position_usd': float}
        portfolio_size_usd: total portfolio
        correlation_assumption: assumed pairwise correlation (0-1, default 0.3)

    Returns:
        total_var_usd:      portfolio VaR (95%) in USD
        total_cvar_usd:     portfolio CVaR (95%) in USD
        position_vars:      per-position VaR
        concentration_pct:  largest single position as % of portfolio
        risk_utilization:   total position risk / portfolio (%)
    """
    if not open_positions:
        return {
            "total_var_usd":      0.0,
            "total_cvar_usd":     0.0,
            "position_vars":      [],
            "concentration_pct":  0.0,
            "risk_utilization":   0.0,
        }

    position_vars = []
    individual_vars = []

    for pos in open_positions:
        pair     = pos.get("pair", "all")
        pos_usd  = float(pos.get("position_usd", 0))
        pos_pct  = pos_usd / portfolio_size_usd * 100 if portfolio_size_usd > 0 else 0

        v = compute_historical_var(
            pair=pair,
            confidence=0.95,
            portfolio_size_usd=portfolio_size_usd,
            position_pct=pos_pct,
        )
        position_vars.append({
            "pair":         pair,
            "position_usd": round(pos_usd, 2),
            "var_usd":      v["var_usd"],
            "cvar_usd":     v["cvar_usd"],
            "var_pct":      v["var_pct"],
        })
        individual_vars.append(v["var_usd"])

    # Portfolio VaR with correlation adjustment (sqrt of sum of squares * corr)
    n = len(individual_vars)
    if n == 0:
        portfolio_var = 0.0
    elif n == 1:
        portfolio_var = individual_vars[0]
    else:
        # Simplified: undiversified VaR * diversification factor
        undiversified = sum(individual_vars)
        # Correlation-adjusted: sqrt(n * (1 + (n-1) * rho)) / n = diversification factor
        div_factor = math.sqrt(1 + (n - 1) * correlation_assumption) / math.sqrt(n)
        portfolio_var = undiversified * div_factor

    # CVaR scales roughly 1.25x VaR for normal distributions
    portfolio_cvar = portfolio_var * 1.25

    # Concentration: largest position
    if open_positions:
        max_pos = max(float(p.get("position_usd", 0)) for p in open_positions)
        concentration_pct = max_pos / portfolio_size_usd * 100 if portfolio_size_usd > 0 else 0
    else:
        concentration_pct = 0.0

    total_positions_usd = sum(float(p.get("position_usd", 0)) for p in open_positions)
    risk_utilization = total_positions_usd / portfolio_size_usd * 100 if portfolio_size_usd > 0 else 0

    return {
        "total_var_usd":      round(portfolio_var, 2),
        "total_cvar_usd":     round(portfolio_cvar, 2),
        "position_vars":      position_vars,
        "concentration_pct":  round(concentration_pct, 1),
        "risk_utilization":   round(risk_utilization, 1),
        "n_positions":        n,
        "portfolio_size_usd": portfolio_size_usd,
    }


# ─── Fractional Kelly Position Sizing (#50) ───────────────────────────────────

_KELLY_MAX_POSITION = 0.20   # 20% hard cap (20% of portfolio regardless of edge)


def compute_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    fraction: float = 0.25,
) -> dict:
    """
    Compute fractional Kelly position size from historical win/loss stats.

    Standard Kelly formula: f* = (win_rate * b - (1 - win_rate)) / b
    where b = avg_win / avg_loss (reward-to-risk ratio).

    Fractional Kelly applies a conservative multiplier (default 25%) to reduce
    variance while retaining most of the geometric growth benefit.

    Args:
        win_rate:  Historical win rate (0.0–1.0), e.g. 0.55 for 55% winners.
        avg_win:   Average winning trade return (positive float, e.g. 0.08 for 8%).
        avg_loss:  Average losing trade return (positive float, e.g. 0.04 for 4%).
        fraction:  Fractional Kelly multiplier (default 0.25 = 25% = conservative).

    Returns:
        dict with:
            full_kelly:               float — unconstrained Kelly fraction
            fractional_kelly:         float — full_kelly × fraction
            fraction_used:            float — the multiplier applied (0.25 by default)
            recommended_position_pct: float — final position size as % of portfolio (capped at 20%)

    Edge cases:
        - Returns zeros if win_rate, avg_win, avg_loss are invalid/zero.
        - full_kelly is clamped to [0, 1.0] before fractional scaling.
        - recommended_position_pct is clamped to [0, 20.0].
    """
    try:
        if (
            not isinstance(win_rate, (int, float))
            or not isinstance(avg_win, (int, float))
            or not isinstance(avg_loss, (int, float))
            or avg_win <= 0
            or avg_loss <= 0
            or not (0.0 <= win_rate <= 1.0)
        ):
            return {
                "full_kelly": 0.0,
                "fractional_kelly": 0.0,
                "fraction_used": fraction,
                "recommended_position_pct": 0.0,
                "error": "Invalid inputs (win_rate must be 0-1, avg_win/avg_loss must be >0)",
            }

        b = avg_win / avg_loss   # reward-to-risk ratio
        # Standard Kelly: (b × p − (1 − p)) / b
        full_kelly = (b * win_rate - (1 - win_rate)) / b

        # Clamp full Kelly to [0.0, 1.0]: negative Kelly = no edge; >1.0 = theoretically
        # impossible with typical win rates but guard against extreme inputs.
        full_kelly = max(0.0, min(full_kelly, 1.0))

        # Apply fractional multiplier (default 25% of full Kelly — conservative)
        fractional_kelly = full_kelly * fraction

        # Hard cap: never exceed 20% of portfolio regardless of computed edge
        recommended = round(min(fractional_kelly, _KELLY_MAX_POSITION) * 100, 2)

        return {
            "full_kelly":               round(full_kelly, 4),
            "fractional_kelly":         round(fractional_kelly, 4),
            "fraction_used":            fraction,
            "recommended_position_pct": recommended,   # as % of portfolio (e.g. 12.5 = 12.5%)
        }

    except Exception as e:
        logger.warning("compute_kelly_fraction failed: %s", e)
        return {
            "full_kelly": 0.0,
            "fractional_kelly": 0.0,
            "fraction_used": fraction,
            "recommended_position_pct": 0.0,
            "error": str(e),
        }
