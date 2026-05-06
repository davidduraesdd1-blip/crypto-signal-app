"""
routers/diagnostics.py — Operator diagnostics for the Settings · Dev Tools page.

Three read-only endpoints:
  - GET /diagnostics/circuit-breakers — 7-gate Level-C agent safety status,
    matching the card on Settings · Dev Tools (mockup row labels exact)
  - GET /diagnostics/database — table row counts + DB size, matching the
    5-col KPI strip on Settings · Dev Tools
  - GET /diagnostics/feeds — Render-side reachability check for every
    upstream data source named in CLAUDE.md §10. Added 2026-05-05 (P0-10
    of Phase 0.9 audit) so "is OKX/Glassnode reachable from Render?"
    stops being log archaeology.

Pure read-side; no mutations. Endpoints fail-open with safe defaults
when downstream helpers raise (DB unavailable, agent module not imported,
etc.) so the Dev Tools page never shows a stack trace to the operator.

D-extension batch (post-D1, pre-D4): closes two of the four endpoint
gaps surfaced by the D4 code-wire plan.
"""

from __future__ import annotations

import logging
import os
import time
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


def _unmeasured(label: str, detail: str, limit: Any = None) -> dict:
    """A gate whose state cannot be computed from current engine state.

    AUDIT-2026-05-02 (MEDIUM bug fix): the previous implementation
    returned `_ok` for gates 4/5/6 even when their state was never
    actually measured — operators saw a green pill for a check that
    never ran. `_unmeasured` makes that visible to the frontend so
    the card can render an accurate "not yet wired" indicator instead
    of fail-open misleading-green.
    """
    return {"label": label, "status": "unmeasured", "detail": detail,
            "value": None, "limit": limit}


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
    # AUDIT-2026-05-02 (MEDIUM bug fix): the cooldown gate had no live
    # state to measure — `agent.py._check_pre_risk` doesn't track the
    # last-loss timestamp, so this row used to always say "inactive"
    # regardless of reality. Until the agent pipeline logs cooldown
    # state to the DB, we report the gate's threshold as configured
    # and mark it `unmeasured` so the frontend renders an honest "not
    # currently tracked" pill instead of a misleading green check.
    cooldown_s = int(cfg.get("agent_cooldown_after_loss_s", 1800))
    gate4 = _unmeasured("Cooldown after loss",
                        f"threshold {cooldown_s}s · live state not tracked",
                        limit=cooldown_s)

    # Gate 5 — Trade-size cap.
    # AUDIT-2026-05-03 (P2 — option a): flipped from `_ok` → `_unmeasured`
    # for consistency with gates 4 and 6 and per the `feedback_empty_states`
    # memory ("truthful empty states"). Gate 5 IS enforced at order time
    # inside agent._check_post_risk, but at status-read time we cannot
    # answer "is the cap currently being honored?" — only "what value is
    # configured?". Reporting `_ok` falsely implied real-time monitoring;
    # `_unmeasured` is the honest signal that lets the frontend render a
    # yellow "configured but not status-tracked" pill rather than a
    # misleading green check. Gate 4 set this precedent (cooldown after
    # loss is also enforcement-only, not status-tracked).
    max_trade_pct = float(cfg.get("agent_max_trade_size_pct", 10.0))
    gate5 = _unmeasured(
        "Trade-size cap",
        f"{max_trade_pct:.0f}% configured cap · enforced at order time, not status-tracked",
        limit=max_trade_pct,
    )

    # Gate 6 — Allowlist (TIER1 ∪ TIER2)
    # AUDIT-2026-05-02 (MEDIUM bug fix): previous implementation reported
    # "all pairs valid" regardless of whether any actual validation
    # happened. Now reports the allowlist size when configured and an
    # explicit "default universe" status when no allowlist is set.
    allowlist = alerts_cfg.get("trading_pairs") or []
    if allowlist:
        gate6 = _ok("Allowlist (TIER1 ∪ TIER2)",
                    f"{len(allowlist)} pairs configured",
                    value=len(allowlist), limit=None)
    else:
        gate6 = _unmeasured("Allowlist (TIER1 ∪ TIER2)",
                            "no explicit allowlist · using default universe",
                            limit=None)

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
    # AUDIT-2026-05-02: only treat ok-status gates as operational; an
    # `unmeasured` gate is NOT counted as healthy (the frontend can
    # render an honest yellow pill instead of misleading-green).
    all_ok = all(g["status"] == "ok" for g in gates)
    has_unmeasured = any(g["status"] == "unmeasured" for g in gates)
    last_check_ts = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "all_operational": all_ok,
        "has_unmeasured":  has_unmeasured,
        "gate_count":      len(gates),
        "gates":           gates,
        "last_check":      last_check_ts,
    }
    # AUDIT-2026-05-02 (MEDIUM bug fix): omit the resume_count and
    # session_halts placeholders until the agent supervisor actually
    # tracks them. Returning a hard-coded 0 was misleading dashboard
    # telemetry on a real-money execution path. Frontend should hide
    # the row when these fields are absent (per Agent A finding M-x).
    return serialize(payload)


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


# ── /diagnostics/feeds — Render-side data feed reachability ─────────────────
# AUDIT-2026-05-05 (P0-10, Tier 4): Render Oregon datacenter IPs are
# geo-blocked by OKX (CLAUDE.md §10) and possibly Binance US. There was
# no way to verify which sources are reachable from inside Render
# without log archaeology. This endpoint pings every documented source
# from inside the worker process and caches the result for 60 seconds
# so the Dev Tools page can show a green/yellow/red strip per feed.

# 60-second result cache. Probing every feed on every request would be
# rude to the upstreams; cache lasts long enough that the Dev Tools
# page can refresh repeatedly without DDoSing OKX.
_FEED_CACHE_TTL_S = 60.0
_feed_cache: dict[str, Any] = {"ts": 0.0, "result": None}

# Per-feed probe spec: hostname, a known-good cheap path, and the
# expected status. Public endpoints only — no auth required for any of
# these. Probes use HEAD where possible, GET for hosts that 405 on HEAD.
_FEED_PROBES: list[dict[str, Any]] = [
    # OHLCV chain (CLAUDE.md §10)
    {"name": "Kraken (CCXT)", "url": "https://api.kraken.com/0/public/Time", "method": "GET", "category": "ohlcv"},
    {"name": "Gate.io REST", "url": "https://api.gateio.ws/api/v4/spot/time", "method": "GET", "category": "ohlcv"},
    {"name": "Bybit REST (time)", "url": "https://api.bybit.com/v5/market/time", "method": "GET", "category": "ohlcv"},
    # AUDIT-2026-05-06 (W2 Tier 4): added the load-bearing Bybit paths
    # so we know whether funding-rate primary (commit 41e6a8c) and
    # OHLCV are blocked, not just /v5/market/time.
    {"name": "Bybit funding", "url": "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT", "method": "GET", "category": "funding"},
    {"name": "Bybit kline", "url": "https://api.bybit.com/v5/market/kline?category=spot&symbol=BTCUSDT&interval=60&limit=1", "method": "GET", "category": "ohlcv"},
    {"name": "MEXC REST", "url": "https://api.mexc.com/api/v3/time", "method": "GET", "category": "ohlcv"},
    # AUDIT-2026-05-06 (W2 Tier 4): expanded OKX probes. Previous /public/time
    # was 200 from Render but commit 0940681's geo-block claim was about
    # the OHLCV/funding paths. Probing the actually-load-bearing endpoints
    # to know whether the chain reorder can be reverted.
    {"name": "OKX time", "url": "https://www.okx.com/api/v5/public/time", "method": "GET", "category": "ohlcv"},
    {"name": "OKX kline", "url": "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar=1H&limit=1", "method": "GET", "category": "ohlcv"},
    {"name": "OKX funding", "url": "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP", "method": "GET", "category": "funding"},
    {"name": "OKX open-interest", "url": "https://www.okx.com/api/v5/public/open-interest?instType=SWAP&instId=BTC-USDT-SWAP", "method": "GET", "category": "open-interest"},
    {"name": "CoinGecko", "url": "https://api.coingecko.com/api/v3/ping", "method": "GET", "category": "ohlcv"},
    # Sentiment / market data
    {"name": "alternative.me F&G", "url": "https://api.alternative.me/fng/?limit=1", "method": "GET", "category": "sentiment"},
    # Macro — fred.stlouisfed.org/graph/fredgraph.csv matches the actual
    # macro-fetcher path; SPA root hangs on Akamai edge.
    {"name": "FRED", "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", "method": "GET", "category": "macro"},
]


def _probe_feed(spec: dict[str, Any]) -> dict[str, Any]:
    """Single probe — bounded to 3s, fail-open with status='unreachable'.

    AUDIT-2026-05-06 (W2 Tier 3): timeout dropped 5s → 3s. Worst case
    8 probes × 5s = 40s exceeds Render's 30s proxy read-timeout. At 3s
    worst case is 24s with comfort margin.
    """
    import urllib.request
    import urllib.error

    started = time.time()
    try:
        req = urllib.request.Request(spec["url"], method=spec.get("method", "GET"))
        # Polaris Edge UA so upstream rate-limiters can identify our traffic
        # (and so cf-blocks that key on missing/empty UA don't trigger).
        req.add_header("User-Agent", "PolarisEdge-DiagnosticsProbe/1.0")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            elapsed_ms = int((time.time() - started) * 1000)
            return {
                "name": spec["name"],
                "category": spec["category"],
                "status": "ok" if 200 <= resp.status < 400 else "warn",
                "http_code": resp.status,
                "elapsed_ms": elapsed_ms,
                "error": None,
            }
    except urllib.error.HTTPError as e:
        # Non-2xx — record the code but treat as warn (host reachable, route maybe wrong)
        return {
            "name": spec["name"],
            "category": spec["category"],
            "status": "warn",
            "http_code": e.code,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": f"HTTP {e.code}",
        }
    except Exception as e:
        # Network / DNS / timeout / geo-block — host unreachable from this worker
        return {
            "name": spec["name"],
            "category": spec["category"],
            "status": "unreachable",
            "http_code": None,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": type(e).__name__ + ": " + str(e)[:100],
        }


@router.get(
    "/feeds",
    summary="Render-side data feed reachability — pings every documented source",
    dependencies=[Depends(require_api_key)],
)
def get_feeds_health():
    """Probes every public data feed from inside the worker process.

    Result is cached for 60 seconds so repeated dashboard refreshes
    don't hammer the upstreams. The probe runs SEQUENTIALLY (not in
    parallel) so it can't accidentally exhaust file descriptors during
    cold start. Total probe budget: 8 feeds × 5s timeout = 40s worst
    case, but typical run is under 5s when nothing is broken.

    Returns:
      - generated_at: ISO timestamp of THIS result (cached or fresh)
      - cached: bool — true if served from the 60s cache
      - feeds: list of {name, category, status, http_code, elapsed_ms, error}
      - summary: {ok: N, warn: N, unreachable: N, total: N}
    """
    now = time.time()
    cached = _feed_cache["result"]
    if cached is not None and (now - _feed_cache["ts"]) < _FEED_CACHE_TTL_S:
        cached = dict(cached)
        cached["cached"] = True
        return serialize(cached)

    feeds = [_probe_feed(spec) for spec in _FEED_PROBES]
    counts = {"ok": 0, "warn": 0, "unreachable": 0}
    for f in feeds:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    counts["total"] = len(feeds)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cached":       False,
        "render_region": os.environ.get("RENDER_REGION", "unknown"),
        "feeds":        feeds,
        "summary":      counts,
    }
    _feed_cache["ts"] = now
    _feed_cache["result"] = payload
    return serialize(payload)
