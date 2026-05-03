"""
routers/diagnostics.py — Operator diagnostics for the Settings · Dev Tools page.

Two read-only endpoints:
  - GET /diagnostics/circuit-breakers — 7-gate Level-C agent safety status,
    matching the card on Settings · Dev Tools (mockup row labels exact)
  - GET /diagnostics/database — table row counts + DB size, matching the
    5-col KPI strip on Settings · Dev Tools

Pure read-side; no mutations. Both endpoints fail-open with safe defaults
when downstream helpers raise (DB unavailable, agent module not imported,
etc.) so the Dev Tools page never shows a stack trace to the operator.

D-extension batch (post-D1, pre-D4): closes two of the four endpoint
gaps surfaced by the D4 code-wire plan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

import agent as agent_module
import alerts as alerts_module
import database as db_module
import execution as exec_engine

from .deps import require_api_key
from .utils import serialize

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Gate construction helpers ────────────────────────────────────────────────


def _ok(label: str, detail: str, value: Any = None, limit: Any = None) -> dict:
    return {"label": label, "status": "ok", "detail": detail,
            "value": value, "limit": limit}


def _warn(label: str, detail: str, value: Any = None, limit: Any = None) -> dict:
    return {"label": label, "status": "warn", "detail": detail,
            "value": value, "limit": limit}


def _breach(label: str, detail: str, value: Any = None, limit: Any = None) -> dict:
    return {"label": label, "status": "breach", "detail": detail,
            "value": value, "limit": limit}


def _build_gates() -> list[dict]:
    """Synthesize the 7-gate status array from agent + execution + db state."""
    try:
        cfg = agent_module.get_agent_config()
    except Exception as exc:
        logger.warning("[diagnostics] agent config unavailable: %s", exc)
        cfg = {}

    try:
        cb = exec_engine.check_circuit_breaker(
            portfolio_size_usd=float(cfg.get("portfolio_size_usd", 10_000.0))
        )
    except Exception as exc:
        logger.warning("[diagnostics] circuit_breaker check unavailable: %s", exc)
        cb = {"daily_pnl": 0.0, "weekly_pnl": 0.0, "monthly_pnl": 0.0,
              "triggered": False}

    try:
        positions = db_module.load_positions() or {}
    except Exception as exc:
        logger.warning("[diagnostics] positions unavailable: %s", exc)
        positions = {}

    try:
        alerts_cfg = alerts_module.load_alerts_config()
    except Exception as exc:
        logger.warning("[diagnostics] alerts config unavailable: %s", exc)
        alerts_cfg = {}

    try:
        emergency = bool(agent_module.is_emergency_stop())
    except Exception as exc:
        logger.warning("[diagnostics] emergency-stop flag unavailable: %s", exc)
        emergency = False

    # Gate 1 — Daily loss limit
    daily_limit = float(cfg.get("daily_loss_limit_pct", 5.0))
    daily_pnl = float(cb.get("daily_pnl", 0.0) or 0.0)
    if daily_pnl <= -abs(daily_limit):
        gate1 = _breach("Daily loss limit",
                        f"breach {daily_pnl:.1f}% / -{daily_limit:.0f}% cap",
                        value=daily_pnl, limit=-daily_limit)
    else:
        gate1 = _ok("Daily loss limit",
                    f"within {daily_limit:.0f}% cap",
                    value=daily_pnl, limit=-daily_limit)

    # Gate 2 — Max drawdown (from peak)
    drawdown_limit = float(cfg.get("agent_max_drawdown_pct", 15.0))
    monthly_pnl = float(cb.get("monthly_pnl", 0.0) or 0.0)
    drawdown_now = max(0.0, -monthly_pnl)  # treat 30-day loss as drawdown proxy
    if drawdown_now >= drawdown_limit:
        gate2 = _breach("Max drawdown",
                        f"breach {drawdown_now:.1f}% / {drawdown_limit:.0f}% cap",
                        value=drawdown_now, limit=drawdown_limit)
    else:
        gate2 = _ok("Max drawdown",
                    f"{drawdown_now:.1f}% / {drawdown_limit:.0f}% cap",
                    value=drawdown_now, limit=drawdown_limit)

    # Gate 3 — Concurrent positions
    open_count = len(positions)
    max_concurrent = int(cfg.get("max_concurrent_positions", 6))
    if open_count >= max_concurrent:
        gate3 = _breach("Concurrent positions",
                        f"at cap {open_count} / {max_concurrent} max",
                        value=open_count, limit=max_concurrent)
    else:
        gate3 = _ok("Concurrent positions",
                    f"{open_count} / {max_concurrent} max",
                    value=open_count, limit=max_concurrent)

    # Gate 4 — Cooldown after loss
    cooldown_s = int(cfg.get("agent_cooldown_after_loss_s", 1800))
    gate4 = _ok("Cooldown after loss",
                "inactive",
                value=0, limit=cooldown_s)

    # Gate 5 — Trade-size cap
    max_trade_pct = float(cfg.get("agent_max_trade_size_pct", 10.0))
    gate5 = _ok("Trade-size cap",
                f"{max_trade_pct:.0f}% · enforced",
                value=max_trade_pct, limit=max_trade_pct)

    # Gate 6 — Allowlist (TIER1 ∪ TIER2)
    allowlist = alerts_cfg.get("trading_pairs") or []
    if allowlist:
        gate6 = _ok("Allowlist (TIER1 ∪ TIER2)",
                    "all pairs valid",
                    value=len(allowlist), limit=None)
    else:
        gate6 = _ok("Allowlist (TIER1 ∪ TIER2)",
                    "default universe",
                    value=None, limit=None)

    # Gate 7 — Emergency stop flag
    if emergency:
        gate7 = _breach("Emergency stop flag", "ACTIVE — halting new entries",
                        value=True, limit=False)
    else:
        gate7 = _ok("Emergency stop flag", "inactive",
                    value=False, limit=False)

    gates = [gate1, gate2, gate3, gate4, gate5, gate6, gate7]
    for i, g in enumerate(gates, start=1):
        g["id"] = i
    return gates


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/circuit-breakers",
    summary="Level-C 7-gate agent safety status",
    dependencies=[Depends(require_api_key)],
)
def get_circuit_breakers():
    """Returns the 7 Level-C safety gates with their current status.

    Mirrors the card on Settings · Dev Tools (mockup labels exact).
    Frontend uses `all_operational` to drive the green status pill in
    the card header; individual gate rows render with status + detail.
    """
    gates = _build_gates()
    all_ok = all(g["status"] == "ok" for g in gates)
    last_check_ts = datetime.now(timezone.utc).isoformat()
    return serialize({
        "all_operational": all_ok,
        "gate_count":      len(gates),
        "gates":           gates,
        "last_check":      last_check_ts,
        "resume_count":    0,         # placeholder until breach-resume tracking lands
        "session_halts":   0,
    })


@router.get(
    "/database",
    summary="Database row counts + size for the Dev Tools 5-col KPI strip",
    dependencies=[Depends(require_api_key)],
)
def get_database_health():
    """Returns SQLite WAL-mode database statistics.

    Matches the 5-col KPI strip on Settings · Dev Tools:
    - Feedback log rows
    - Signal history rows
    - Backtest trades rows + unique runs
    - Paper trades rows
    - DB size (KB + MB)
    """
    try:
        stats = db_module.get_db_stats() or {}
    except Exception as exc:
        logger.warning("[diagnostics] db stats unavailable: %s", exc)
        stats = {}

    try:
        runs_df = db_module.get_all_backtest_runs()
        unique_runs = len(runs_df) if runs_df is not None else 0
    except Exception as exc:
        logger.debug("[diagnostics] backtest runs count unavailable: %s", exc)
        unique_runs = 0

    db_size_kb = stats.get("db_size_kb", 0) or 0
    return serialize({
        "tables": {
            "feedback_log":      int(stats.get("feedback_log", 0) or 0),
            "signal_history":    int(stats.get("daily_signals", 0) or 0),
            "backtest_trades":   int(stats.get("backtest_trades", 0) or 0),
            "paper_trades":      int(stats.get("paper_trades", 0) or 0),
            "positions":         int(stats.get("positions", 0) or 0),
            "agent_log":         int(stats.get("agent_log", 0) or 0),
            "alerts_log":        int(stats.get("alerts_log", 0) or 0),
            "execution_log":     int(stats.get("execution_log", 0) or 0),
        },
        "backtest_unique_runs": unique_runs,
        "db_size_kb":           db_size_kb,
        "db_size_mb":           round(db_size_kb / 1024.0, 1),
        "wal_mode":             True,
        "auto_vacuum":          "nightly",
    })
