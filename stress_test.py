"""
stress_test.py — Historical scenario stress testing

Replays actual OHLCV data through specific crisis periods to estimate
portfolio performance under extreme conditions.

Scenarios:
  FTX_COLLAPSE  : Nov 2022 — FTX bankruptcy, sector-wide contagion
  COVID_CRASH   : Mar 2020 — Global market panic, crypto -55%
  BEAR_2022     : Jan–Jun 2022 — Fed tightening bear market, BTC -60%
  LUNA_CRASH    : May 2022 — UST/LUNA de-peg, $40B wiped
  BULL_2024     : Q1 2024 — BTC spot ETF approval, surge to ATH
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Scenario definitions ───────────────────────────────────────────────────────
STRESS_SCENARIOS: dict[str, dict] = {
    "FTX_COLLAPSE": {
        "label":       "FTX Collapse (Nov 2022)",
        "start":       "2022-11-01",
        "end":         "2022-11-30",
        "description": "FTX exchange bankruptcy, $8B hole, contagion across sector",
        "known_btc_drawdown": -24.0,
    },
    "COVID_CRASH": {
        "label":       "COVID Market Crash (Mar 2020)",
        "start":       "2020-03-01",
        "end":         "2020-03-31",
        "description": "Global pandemic panic, crypto flash-crashed with all assets",
        "known_btc_drawdown": -50.0,
    },
    "BEAR_2022": {
        "label":       "2022 Bear Market (Jan–Jun 2022)",
        "start":       "2022-01-01",
        "end":         "2022-06-30",
        "description": "Fed rate hike cycle, risk-off rotation, BTC -60% from ATH",
        "known_btc_drawdown": -58.0,
    },
    "LUNA_CRASH": {
        "label":       "LUNA/UST Collapse (May 2022)",
        "start":       "2022-05-01",
        "end":         "2022-05-31",
        "description": "UST algorithmic stablecoin de-peg, LUNA hyperinflation, $40B erased",
        "known_btc_drawdown": -32.0,
    },
    "BULL_2024": {
        "label":       "BTC Spot ETF Approval Bull Run (Q1 2024)",
        "start":       "2024-01-01",
        "end":         "2024-03-31",
        "description": "SEC approval of spot BTC ETFs, institutional inflows, BTC to $73k ATH",
        "known_btc_drawdown": 0.0,
    },
}


def _fetch_scenario_ohlcv(pair: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for a specific date range using ccxt.
    Returns DataFrame with columns: open, high, low, close, volume.
    """
    try:
        import ccxt
        ex = ccxt.kraken({"enableRateLimit": True})
        since_ts = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
        end_ts   = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)

        all_bars = []
        cur_ts = since_ts
        while cur_ts < end_ts:
            bars = ex.fetch_ohlcv(pair, "1d", since=cur_ts, limit=200)
            if not bars:
                break
            all_bars.extend(bars)
            last_ts = bars[-1][0]
            if last_ts >= end_ts:
                break
            cur_ts = last_ts + 86_400_000  # next day
            time.sleep(0.4)

        if not all_bars:
            return None

        df = pd.DataFrame(all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df[df["timestamp"] <= pd.Timestamp(end, tz="UTC")]
        df = df.set_index("timestamp")
        return df
    except Exception as e:
        logger.warning("Scenario OHLCV fetch failed for %s [%s-%s]: %s", pair, start, end, e)
        return None


def _compute_scenario_metrics(
    df: pd.DataFrame,
    position_pct: float,
    direction: str,
    initial_equity: float = 10_000.0,
) -> dict:
    """
    Simulate holding a position through a scenario period.

    Parameters
    ----------
    df             : OHLCV for the scenario period
    position_pct   : position size as % of portfolio (e.g. 20.0)
    direction      : 'BUY' or 'SELL'
    initial_equity : portfolio starting value

    Returns
    -------
    dict with scenario P&L metrics
    """
    if df is None or df.empty:
        return {"error": "No OHLCV data"}

    entry_price = float(df["close"].iloc[0])
    exit_price  = float(df["close"].iloc[-1])

    price_return = (exit_price - entry_price) / entry_price
    if direction in ("SELL", "STRONG SELL"):
        price_return = -price_return   # short position

    position_usd  = initial_equity * (position_pct / 100.0)
    pnl_usd       = position_usd * price_return
    pnl_pct       = price_return * 100

    # Max drawdown during scenario
    cumulative_returns = (1 + df["close"].pct_change().fillna(0)).cumprod()
    if direction in ("SELL", "STRONG SELL"):
        cumulative_returns = 2 - cumulative_returns   # approximate inverse for short
    equity_curve = initial_equity + position_usd * (cumulative_returns - 1)
    rolling_max  = equity_curve.cummax()
    drawdowns    = (equity_curve - rolling_max) / rolling_max
    max_drawdown = float(drawdowns.min()) * 100

    # Peak equity, trough equity
    peak_equity   = float(equity_curve.max())
    trough_equity = float(equity_curve.min())

    # Volatility (annualized)
    daily_rets = df["close"].pct_change().dropna()
    vol_ann    = float(daily_rets.std() * np.sqrt(365) * 100) if len(daily_rets) > 1 else 0.0

    return {
        "entry_price":     round(entry_price, 4),
        "exit_price":      round(exit_price, 4),
        "price_return_pct": round(price_return * 100, 2),
        "pnl_usd":         round(pnl_usd, 2),
        "pnl_pct":         round(pnl_pct, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "peak_equity":     round(peak_equity, 2),
        "trough_equity":   round(trough_equity, 2),
        "vol_ann_pct":     round(vol_ann, 2),
        "bars":            len(df),
        "error":           None,
    }


def run_stress_test(
    pairs: list[str],
    scenario_key: str,
    position_pct: float    = 20.0,
    initial_equity: float  = 10_000.0,
    default_direction: str = "BUY",
) -> dict:
    """
    Run a historical stress test scenario across a list of pairs.

    Parameters
    ----------
    pairs             : list of trading pairs e.g. ['BTC/USDT', 'ETH/USDT']
    scenario_key      : key from STRESS_SCENARIOS dict
    position_pct      : assumed position size per pair (%)
    initial_equity    : portfolio starting value (USD)
    default_direction : 'BUY' or 'SELL' (assumed direction for all pairs)

    Returns
    -------
    dict with keys:
      scenario       : scenario metadata dict
      results        : {pair: metrics_dict}
      portfolio      : aggregate portfolio metrics
    """
    scenario = STRESS_SCENARIOS.get(scenario_key)
    if not scenario:
        return {"error": f"Unknown scenario: {scenario_key}"}

    start, end = scenario["start"], scenario["end"]
    logger.info("Running stress test: %s [%s → %s] on %d pairs", scenario["label"], start, end, len(pairs))

    pair_results: dict[str, dict] = {}
    for pair in pairs:
        df = _fetch_scenario_ohlcv(pair, start, end)
        if df is None or df.empty:
            pair_results[pair] = {"error": f"No data available for {pair} in [{start}, {end}]"}
        else:
            pair_results[pair] = _compute_scenario_metrics(
                df, position_pct, default_direction, initial_equity
            )

    # Aggregate portfolio-level metrics
    valid_results = [r for r in pair_results.values() if r.get("error") is None]
    if valid_results:
        total_pnl_usd   = sum(r["pnl_usd"] for r in valid_results)
        avg_return_pct  = sum(r["price_return_pct"] for r in valid_results) / len(valid_results)
        worst_dd_pct    = min(r["max_drawdown_pct"] for r in valid_results)
        best_return     = max(r["pnl_pct"] for r in valid_results)
        worst_return    = min(r["pnl_pct"] for r in valid_results)
        winning_pairs   = sum(1 for r in valid_results if r["pnl_usd"] > 0)
        win_rate        = winning_pairs / len(valid_results) * 100
    else:
        total_pnl_usd   = 0.0
        avg_return_pct  = 0.0
        worst_dd_pct    = 0.0
        best_return     = 0.0
        worst_return    = 0.0
        win_rate        = 0.0
        winning_pairs   = 0

    portfolio_final   = initial_equity + total_pnl_usd
    portfolio_return  = (portfolio_final - initial_equity) / initial_equity * 100

    portfolio = {
        "initial_equity":    initial_equity,
        "final_equity":      round(portfolio_final, 2),
        "total_pnl_usd":     round(total_pnl_usd, 2),
        "portfolio_return":  round(portfolio_return, 2),
        "avg_pair_return":   round(avg_return_pct, 2),
        "worst_drawdown_pct": round(worst_dd_pct, 2),
        "best_return_pct":   round(best_return, 2),
        "worst_return_pct":  round(worst_return, 2),
        "win_rate":          round(win_rate, 1),
        "winning_pairs":     winning_pairs,
        "total_pairs":       len(valid_results),
    }

    return {
        "scenario":  scenario,
        "results":   pair_results,
        "portfolio": portfolio,
    }


def run_all_scenarios(
    pairs: list[str],
    position_pct: float   = 20.0,
    initial_equity: float = 10_000.0,
) -> dict[str, dict]:
    """
    Run all defined stress scenarios and return combined results.
    """
    all_results = {}
    for key in STRESS_SCENARIOS:
        try:
            all_results[key] = run_stress_test(
                pairs=pairs,
                scenario_key=key,
                position_pct=position_pct,
                initial_equity=initial_equity,
            )
        except Exception as e:
            logger.error("Stress test failed for scenario %s: %s", key, e)
            all_results[key] = {"error": str(e)}
    return all_results


def get_scenario_summary_df(stress_results: dict) -> pd.DataFrame:
    """
    Convert stress test results dict into a summary DataFrame for display.
    Rows = scenarios, columns = key portfolio metrics.
    """
    rows = []
    for key, res in stress_results.items():
        if "error" in res and not res.get("portfolio"):
            rows.append({
                "Scenario":            res.get("scenario", {}).get("label", key),
                "Period":              f"{res.get('scenario', {}).get('start','')} → {res.get('scenario', {}).get('end','')}",
                "Portfolio Return %":  "N/A",
                "Total P&L ($)":       "N/A",
                "Worst Drawdown %":    "N/A",
                "Win Rate %":          "N/A",
                "Known BTC DD %":      "N/A",
            })
            continue
        scen = res.get("scenario", {})
        port = res.get("portfolio", {})
        rows.append({
            "Scenario":            scen.get("label", key),
            "Period":              f"{scen.get('start','')} → {scen.get('end','')}",
            "Portfolio Return %":  port.get("portfolio_return", 0.0),
            "Total P&L ($)":       port.get("total_pnl_usd", 0.0),
            "Worst Drawdown %":    port.get("worst_drawdown_pct", 0.0),
            "Win Rate %":          port.get("win_rate", 0.0),
            "Known BTC DD %":      scen.get("known_btc_drawdown", 0.0),
        })
    return pd.DataFrame(rows)
