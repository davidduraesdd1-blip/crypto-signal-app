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
