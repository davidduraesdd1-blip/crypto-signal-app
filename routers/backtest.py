"""
routers/backtest.py — Backtester page summary endpoint.

`/backtest/summary` was the missing piece — `api.py` already exposes
`/backtest/trades` and `/backtest/runs` as legacy `@app.get` routes,
but no endpoint produced the KPI rollup shape the Next.js Backtester
page consumes (`BacktestSummary` in web/lib/api-types.ts:421).

Adding it here unblocks the live Vercel page, which was crashing with
`TypeError: Cannot read properties of undefined (reading 'className')`
downstream of the 404 on the summary call.

Computes:
  - total_trades, win_rate_pct, avg_pnl_pct
  - max_drawdown_pct (from cumulative compounded equity curve)
  - sharpe_ratio (per-trade-unit, no rf rate — consistent with engine)
  - start_date, end_date

Fail-open with safe defaults: when the DB has no rows or the read
fails, every metric is `null` and `total_trades` is 0. The frontend
handles null/empty cleanly via `isMissing()` guards (web/app/page.tsx
:144-183).
"""

from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import APIRouter, Depends

import database as db_module

from .deps import require_api_key
from .utils import serialize

logger = logging.getLogger(__name__)

router = APIRouter()


def _summary_from_trades(df) -> dict[str, Any]:
    """Compute the BacktestSummary shape from a trades DataFrame."""
    empty = {
        "total_trades":     0,
        "win_rate_pct":     None,
        "avg_pnl_pct":      None,
        "max_drawdown_pct": None,
        "sharpe_ratio":     None,
        "start_date":       None,
        "end_date":         None,
    }
    if df is None or df.empty:
        return empty

    total = int(len(df))
    pnl = df["pnl_pct"].dropna() if "pnl_pct" in df.columns else None

    win_rate = None
    avg_pnl = None
    max_dd = None
    sharpe = None
    if pnl is not None and len(pnl) > 0:
        wins = int((pnl > 0).sum())
        win_rate = round(100.0 * wins / len(pnl), 2)
        avg_pnl = round(float(pnl.mean()), 4)

        # Cumulative compounded equity curve from per-trade pnl_pct (already
        # in percent units — convert to fractional first).
        equity = (1.0 + pnl / 100.0).cumprod()
        running_max = equity.cummax()
        drawdown = (equity / running_max) - 1.0
        max_dd = round(float(drawdown.min() * 100.0), 2)

        # Per-trade Sharpe with no risk-free rate (matches engine reporting).
        std = float(pnl.std())
        if std > 0:
            sharpe = round(float(pnl.mean()) / std, 3)

    start_date = None
    end_date = None
    if "timestamp" in df.columns and len(df) > 0:
        ts = df["timestamp"].dropna()
        if len(ts) > 0:
            start_date = str(ts.min())
            end_date = str(ts.max())

    return {
        "total_trades":     total,
        "win_rate_pct":     win_rate,
        "avg_pnl_pct":      avg_pnl,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio":     sharpe,
        "start_date":       start_date,
        "end_date":         end_date,
    }


@router.get(
    "/summary",
    summary="KPI rollup for the latest backtest run",
    dependencies=[Depends(require_api_key)],
)
def get_backtest_summary():
    try:
        df = db_module.get_backtest_df()
    except Exception as exc:
        logger.warning("[backtest] /summary read failed: %s", exc)
        df = None
    return serialize(_summary_from_trades(df))


@router.get(
    "/optuna-runs",
    summary="Top-N Optuna hyperparameter tuning runs",
    dependencies=[Depends(require_api_key)],
)
def get_optuna_runs(n: int = 10):
    """Read the top-N Optuna study runs from `optuna_studies.sqlite`.

    AUDIT-2026-05-06 (Everything-Live, item 4): pre-fix the Backtester
    OptunaTable rendered 5 fabricated rows (rsi_period=14, sharpe=4.12,
    +342.8% etc.) that had no source. Now reads the actual sqlite
    database the engine writes to during hyperparameter search.

    Returns empty list when the sqlite file doesn't exist yet (fresh
    deploy, no tuning has run) — frontend renders the truthful
    "no Optuna runs yet — run a tuning sweep to populate" empty-state.
    """
    import os
    import sqlite3
    n = max(1, min(int(n), 100))

    db_path = os.environ.get("OPTUNA_DB_PATH", "optuna_studies.sqlite")
    if not os.path.exists(db_path):
        return serialize({"count": 0, "runs": [], "source": "none", "error": "optuna_studies.sqlite not found yet"})

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            cur = conn.execute("""
                SELECT t.trial_id, t.value, t.state,
                       (SELECT GROUP_CONCAT(p.param_name || '=' || p.param_value, ', ')
                          FROM trial_params p
                         WHERE p.trial_id = t.trial_id) AS params
                  FROM trials t
                 WHERE t.state = 'COMPLETE' AND t.value IS NOT NULL
                 ORDER BY t.value DESC
                 LIMIT ?
            """, (n,))
            rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("[backtest] optuna-runs read failed: %s", exc)
        return serialize({"count": 0, "runs": [], "source": "error", "error": str(exc)})

    runs: list[dict] = []
    for rank, (trial_id, value, state, params) in enumerate(rows, start=1):
        runs.append({
            "rank":   rank,
            "trial_id": trial_id,
            "value":  round(float(value), 4) if value is not None else None,
            "state":  state,
            "params": params or "",
        })
    return serialize({"count": len(runs), "runs": runs, "source": "optuna_studies.sqlite"})


@router.get(
    "/equity-curve",
    summary="Cumulative equity curve from backtest_trades",
    dependencies=[Depends(require_api_key)],
)
def get_equity_curve():
    """Replay backtest_trades in close_time order to compute the
    cumulative compounded equity curve.

    AUDIT-2026-05-06 (Everything-Live, item 5): pre-fix the EquityCurve
    component on the Backtester page rendered a static SVG path with
    fabricated coordinates. Now derives the curve from real trade PnLs.

    Returns:
      points: [{timestamp_iso, equity, drawdown_pct}, ...]
      summary: {start, end, total_pnl_pct, max_dd_pct, n_trades}

    Empty payload when no trades exist (fresh deploy).
    """
    try:
        df = db_module.get_backtest_df()
    except Exception as exc:
        logger.warning("[backtest] equity-curve read failed: %s", exc)
        return serialize({"points": [], "summary": {"n_trades": 0}, "error": str(exc)})

    if df is None or df.empty or "pnl_pct" not in df.columns:
        return serialize({"points": [], "summary": {"n_trades": 0}})

    # Sort chronologically — prefer close_time, fall back to timestamp
    sort_col = "close_time" if "close_time" in df.columns else (
        "timestamp" if "timestamp" in df.columns else None
    )
    if sort_col is not None:
        df = df.sort_values(sort_col)

    pnl = df["pnl_pct"].fillna(0.0).astype(float).values
    equity = 100.0  # start at 100 (= 100%)
    running_max = 100.0
    points: list[dict] = []
    for i, p in enumerate(pnl):
        equity = equity * (1.0 + p / 100.0)
        running_max = max(running_max, equity)
        dd = (equity / running_max - 1.0) * 100.0 if running_max > 0 else 0.0
        ts_value = None
        if sort_col is not None:
            try:
                ts_value = str(df.iloc[i][sort_col])
            except Exception:
                ts_value = None
        points.append({
            "timestamp": ts_value,
            "equity":    round(equity, 4),
            "drawdown_pct": round(dd, 2),
        })

    n = len(points)
    summary = {
        "n_trades":      n,
        "start":         points[0]["timestamp"] if points else None,
        "end":           points[-1]["timestamp"] if points else None,
        "total_pnl_pct": round(equity - 100.0, 2),
        "max_dd_pct":    round(min(p["drawdown_pct"] for p in points), 2) if points else 0.0,
        "final_equity":  round(equity, 4),
    }
    return serialize({"points": points, "summary": summary})


@router.get(
    "/arbitrage",
    summary="Recent arbitrage opportunities (spot + funding-carry)",
    dependencies=[Depends(require_api_key)],
)
def get_backtest_arbitrage(limit: int = 50):
    """Returns the most recent rows from `arb_opportunities`. Empty list
    when no scan has populated the table yet — matches the
    `ArbitrageList` shape the frontend (web/lib/api-types.ts:484)
    expects."""
    try:
        df = db_module.get_arb_opportunities_df(limit=max(1, min(int(limit), 500)))
    except Exception as exc:
        logger.warning("[backtest] /arbitrage read failed: %s", exc)
        return serialize({"count": 0, "opportunities": []})

    if df is None or df.empty:
        return serialize({"count": 0, "opportunities": []})

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        d = row.to_dict()
        cleaned = {
            k: (None if isinstance(v, float) and math.isnan(v) else v)
            for k, v in d.items()
        }
        rows.append(cleaned)

    return serialize({"count": len(rows), "opportunities": rows})
