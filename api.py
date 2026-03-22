"""
api.py — FastAPI REST layer for the Crypto Signal Engine v5.9.13

Run:  uvicorn api:app --host 0.0.0.0 --port 8000 --reload
Docs: http://localhost:8000/docs (Swagger UI)
      http://localhost:8000/redoc (ReDoc)

Authentication
--------------
Set an API key in Config Editor → API Server section.
Pass it as the `X-API-Key` header.  Leave blank to disable auth (local use).

TradingView Webhook
-------------------
In TradingView alert → Webhook URL: http://<your-ip>:8000/webhook/tradingview?token=<your-api-key>
(TradingView cannot send custom headers, so pass your API key as the ?token= query param)
Alert message (JSON):
    {
        "pair": "BTCUSDT",
        "action": "BUY",
        "price": {{close}},
        "timeframe": "1h",
        "strategy": "MyStrategy",
        "message": "RSI oversold"
    }
"""

from __future__ import annotations

import hmac
import html as _html
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

import alerts
import crypto_model_core as model
import database as db
import websocket_feeds as ws_feeds
import execution as exec_engine

# Start WebSocket feed when API server loads
try:
    ws_feeds.start(model.PAIRS)
except Exception as _ws_err:
    logger.warning("WebSocket feed startup failed (non-fatal): %s", _ws_err)

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Crypto Signal Engine API",
    description=(
        "REST endpoints for scan signals, positions, backtest results, "
        "indicator weights, and TradingView strategy webhooks."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
    allow_credentials=False,  # SEC-HIGH-02: explicit
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """SEC-HIGH-02: Add hardening headers to every response."""
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["X-XSS-Protection"]        = "1; mode=block"
    response.headers["Referrer-Policy"]          = "no-referrer"
    response.headers["Cache-Control"]            = "no-store"
    return response


# ─── Authentication ────────────────────────────────────────────────────────────

_api_key_cache: dict = {"key": None, "ts": 0.0}
_API_KEY_CACHE_TTL = 30.0  # seconds
_api_key_lock = threading.Lock()


def _get_configured_api_key() -> str:
    with _api_key_lock:
        if time.time() - _api_key_cache["ts"] < _API_KEY_CACHE_TTL:
            return _api_key_cache["key"] or ""
    cfg = alerts.load_alerts_config()
    key = cfg.get("api_key", "")
    with _api_key_lock:
        _api_key_cache["key"] = key
        _api_key_cache["ts"] = time.time()   # timestamp after I/O for accurate TTL
    return key


def require_api_key(x_api_key: str = Header(default="")):
    """Dependency: validates X-API-Key header if a key is configured.
    SEC-MEDIUM-03: uses hmac.compare_digest() to prevent timing-based key enumeration.
    """
    expected = _get_configured_api_key()
    if expected and not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ─── JSON serialisation helpers ───────────────────────────────────────────────

def _clean_scalar(obj: Any) -> Any:
    """Convert numpy/pandas scalars to native Python types.

    NaN and Inf are replaced with None so consumers can distinguish
    "missing data" from "zero" — consistent with app.py's _numpy_serializer.
    """
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


def _serialize(obj: Any) -> Any:
    """Recursively make a dict/list JSON-safe."""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, pd.DataFrame):
        return _serialize(obj.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return _serialize(obj.tolist())
    return _clean_scalar(obj)


# ─── Pair normalisation ───────────────────────────────────────────────────────

def _normalize_pair(raw: str) -> str:
    """
    Accept BTCUSDT, BTC-USDT, BTC_USDT, BTC/USDT, BTC-USDT-SWAP → BTC/USDT.
    Raises ValueError if the result does not look like a valid BASE/QUOTE pair.
    """
    # Strip OKX / Binance futures suffixes before normalising
    s = raw.upper().strip()
    for suffix in ("-SWAP", ":USDT", ":USDC", "PERP", "_PERP"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    s = s.replace("_", "/").replace("-", "/")
    if "/" not in s:
        for quote in ("USDT", "USDC", "BTC", "ETH", "BNB"):
            if s.endswith(quote) and len(s) > len(quote):
                s = s[: -len(quote)] + "/" + quote
                break
    # Validate: must be BASE/QUOTE with non-empty parts, letters only
    if "/" not in s:
        raise ValueError(f"Cannot normalise pair: {raw!r}")
    base, quote = s.split("/", 1)
    if not base or not quote or not all(c.isalnum() for c in base) or not quote.isalpha():
        raise ValueError(f"Invalid pair after normalisation: {s!r} (from {raw!r})")
    return s


# ─── Background scan ──────────────────────────────────────────────────────────

_scan_thread: Optional[threading.Thread] = None
_scan_lock = threading.Lock()


def _run_scan_bg():
    """Worker executed in a daemon thread when /scan/trigger is called."""
    try:
        db.write_scan_status(
            running=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=None,
            progress=0,
            pair="",
        )
        results = model.run_scan()
        db.write_scan_results(results)
        db.write_scan_status(
            running=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=None,
            progress=100,
            pair="",
        )
        # BUG-R20/R29: fire alerts on each channel independently so one failure
        # does not silently suppress the others.  Log warnings on failure.
        cfg = alerts.load_alerts_config()
        try:
            alerts.send_scan_alerts(results, cfg)
        except Exception as _e:
            logger.warning("[API] Telegram alert failed: %s", _e)
        try:
            alerts.send_scan_email_alerts(results, cfg)
        except Exception as _e:
            logger.warning("[API] Email alert failed: %s", _e)
        try:
            alerts.send_scan_discord_alerts(results, cfg)
        except Exception as _e:
            logger.warning("[API] Discord alert failed: %s", _e)
    except Exception as exc:
        logger.error("[API] Background scan failed: %s", exc, exc_info=True)
        db.write_scan_status(
            running=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
            progress=0,
            pair="",
        )


# ─── Pydantic request models ──────────────────────────────────────────────────

class TradingViewWebhook(BaseModel):
    pair: str = Field(..., description="Symbol, e.g. BTCUSDT, BTC/USDT, BTC-USDT")
    action: str = Field(..., description="BUY | SELL | STRONG BUY | STRONG SELL | NEUTRAL | CLOSE")
    price: Optional[float] = Field(None, description="Current price at alert trigger")
    timeframe: Optional[str] = Field(None, description="Chart timeframe, e.g. 1h")
    strategy: Optional[str] = Field(None, description="Strategy name from TradingView")
    message: Optional[str] = Field(None, description="Free-text alert message")


class OrderRequest(BaseModel):
    pair:          str            = Field(..., description="e.g. BTC/USDT or BTCUSDT")
    direction:     str            = Field(..., description="BUY | SELL | STRONG BUY | STRONG SELL")
    size_usd:      float          = Field(..., description="Notional USD order size", gt=0)
    order_type:    str            = Field("market", description="market | limit")
    limit_price:   Optional[float] = Field(None, description="Price for limit orders")
    current_price: Optional[float] = Field(None, description="Hint for paper fill / contract-qty calc")


# ─── Routes — System ──────────────────────────────────────────────────────────

@app.get("/", tags=["System"], summary="API root")
def root():
    """Confirms the API is running. Visit /docs for full documentation."""
    return {
        "service": "Crypto Signal Engine API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["System"], summary="Health check + DB stats + feed status")
def health():
    """
    Comprehensive health check: DB stats, scan status, WebSocket feed health,
    and data source freshness. Safe for load-balancer / UptimeRobot probes.
    No authentication required.
    """
    import time as _time
    try:
        stats = db.get_db_stats()
    except Exception as _e:
        logger.warning(f"DB stats unavailable: {_e}")
        stats = {"error": "unavailable"}
    status = db.read_scan_status()

    # WebSocket feed health
    try:
        ws_status   = ws_feeds.get_status()
        ws_prices   = ws_feeds.get_all_prices()
        feed_health = {
            "connected":        ws_status.get("connected", False),
            "reconnects":       ws_status.get("reconnects", 0),
            "pairs_live":       list(ws_prices.keys()),
            "pairs_stale":      [p for p in model.PAIRS if ws_feeds.is_stale(p)],
            # API-07: use .get() consistently in both condition and value expression
            "last_message_age": (
                round(_time.time() - ws_status.get("last_message_at"), 1)
                if ws_status.get("last_message_at") else None
            ),
        }
        feed_health["status"] = "OK" if not feed_health["pairs_stale"] else "DEGRADED"
    except Exception as _fe:
        feed_health = {"status": "ERROR", "error": str(_fe)}

    # API-08: only treat explicit "OK" as healthy; None/missing/unknown → degraded
    overall_status = "ok" if feed_health.get("status") == "OK" else "degraded"

    return {
        "status":    overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "db":        _serialize(stats),
        "scan":      _serialize(status),
        "feeds":     feed_health,
    }


# ─── Routes — Signals ─────────────────────────────────────────────────────────

@app.get(
    "/signals",
    tags=["Signals"],
    dependencies=[Depends(require_api_key)],
    summary="Latest scan results",
)
def get_signals(
    min_confidence: float = 0.0,
    direction: Optional[str] = None,
    high_conf_only: bool = False,
):
    """
    Returns the most recent scan results from the DB cache.

    **Filters (all optional):**
    - `min_confidence` — e.g. `65` returns only signals ≥ 65% confidence
    - `direction` — e.g. `STRONG BUY`, `BUY`, `SELL`, `STRONG SELL`, `NEUTRAL`
    - `high_conf_only` — if `true`, return only signals flagged as high-confidence
    """
    results = db.read_scan_results()
    if not results:
        return {"count": 0, "results": []}

    if min_confidence > 0:
        results = [r for r in results if float(r.get("confidence_avg_pct") or 0) >= min_confidence]
    if direction:
        results = [r for r in results if r.get("direction", "").upper() == direction.upper()]
    if high_conf_only:
        results = [r for r in results if r.get("high_conf")]

    return {"count": len(results), "results": _serialize(results)}


@app.get(
    "/signals/history",
    tags=["Signals"],
    dependencies=[Depends(require_api_key)],
    summary="Historical signal log",
)
def get_signal_history(pair: Optional[str] = None, limit: int = 100):
    """
    Returns historical signals from the `daily_signals` table (persistent log).

    - `pair` — optional filter (same flexible format as `/signals/{pair}`)
    - `limit` — max rows returned (default 100, max 1000)
    """
    limit = min(limit, 1000)
    df = db.get_signals_df()
    if df.empty:
        return {"count": 0, "results": []}
    if pair:
        try:
            normalized = _normalize_pair(pair)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        df = df[df["pair"] == normalized]
    df = df.tail(limit)
    return {"count": len(df), "results": _serialize(df.to_dict(orient="records"))}


@app.get(
    "/signals/{pair}",
    tags=["Signals"],
    dependencies=[Depends(require_api_key)],
    summary="Signal for a single pair",
)
def get_signal_pair(pair: str):
    """
    Returns the latest cached signal for one trading pair.

    Accepts any of: `BTCUSDT`, `BTC-USDT`, `BTC_USDT`, `BTC/USDT`.
    """
    try:
        normalized = _normalize_pair(pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # API-02: guard against read_scan_results() returning None on DB error
    results = db.read_scan_results() or []
    for r in results:
        if r.get("pair", "") == normalized:
            return _serialize(r)
    raise HTTPException(status_code=404, detail=f"No cached signal found for {normalized}")


# ─── Routes — Positions ───────────────────────────────────────────────────────

@app.get(
    "/positions",
    tags=["Positions"],
    dependencies=[Depends(require_api_key)],
    summary="Open paper trade positions",
)
def get_positions():
    """Returns all currently open paper trade positions."""
    positions = db.load_positions()
    return {"count": len(positions), "positions": _serialize(positions)}


@app.get(
    "/paper-trades",
    tags=["Positions"],
    dependencies=[Depends(require_api_key)],
    summary="Closed paper trade history",
)
def get_paper_trades(limit: int = 100):
    """
    Returns the most recent closed paper trades.

    - `limit` — number of rows (default 100, max 500)
    """
    limit = min(limit, 500)
    df = db.get_paper_trades_df()
    if df.empty:
        return {"count": 0, "trades": []}
    return {"count": len(df), "trades": _serialize(df.tail(limit).to_dict(orient="records"))}


# ─── Routes — Backtest ────────────────────────────────────────────────────────

_backtest_cache: dict = {"result": None, "ts": 0.0}
_BACKTEST_CACHE_TTL = 300.0  # BUG-L04: cache backtest result for 5 min to avoid re-fetching OHLCV on every call
_backtest_cache_lock = threading.Lock()


@app.get(
    "/backtest",
    tags=["Backtest"],
    dependencies=[Depends(require_api_key)],
    summary="Latest backtest metrics",
)
def get_backtest_summary():
    """
    Returns aggregate backtest metrics.
    BUG-L04: result is cached for 5 minutes; full OHLCV re-fetch only happens
    when cache is stale, not on every API call.
    """
    now = time.time()
    with _backtest_cache_lock:
        if _backtest_cache["result"] is not None and now - _backtest_cache["ts"] < _BACKTEST_CACHE_TTL:
            return {"metrics": _serialize(_backtest_cache["result"].get("metrics", {}))}
    result = model.run_backtest()
    if result is None:
        with _backtest_cache_lock:
            _backtest_cache["result"] = None  # invalidate stale cache
            _backtest_cache["ts"] = 0
        raise HTTPException(
            status_code=404,
            detail="No backtest data available. Run a scan first.",
        )
    with _backtest_cache_lock:
        _backtest_cache["result"] = result
        _backtest_cache["ts"] = now
    return {"metrics": _serialize(result.get("metrics", {}))}


@app.get(
    "/backtest/trades",
    tags=["Backtest"],
    dependencies=[Depends(require_api_key)],
    summary="Backtest trade log (paginated)",
)
def get_backtest_trades(limit: int = 50, offset: int = 0):
    """
    Returns individual trade records from the most recent backtest run.

    - `limit` — page size (default 50)
    - `offset` — skip first N records
    """
    df = db.get_backtest_df()
    if df.empty:
        return {"total": 0, "offset": offset, "limit": limit, "trades": []}
    total = len(df)
    page = df.iloc[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "trades": _serialize(page.to_dict(orient="records")),
    }


@app.get(
    "/backtest/runs",
    tags=["Backtest"],
    dependencies=[Depends(require_api_key)],
    summary="All backtest run summaries",
)
def get_backtest_runs():
    """Returns a summary row for every stored backtest run (run_id, trade count, avg PnL, win rate)."""
    df = db.get_all_backtest_runs()
    if df.empty:
        return {"count": 0, "runs": []}
    return {"count": len(df), "runs": _serialize(df.to_dict(orient="records"))}


# ─── Routes — Weights ─────────────────────────────────────────────────────────

@app.get(
    "/weights",
    tags=["Weights"],
    dependencies=[Depends(require_api_key)],
    summary="Current indicator weights",
)
def get_weights():
    """Returns the currently active dynamic indicator weights."""
    weights = db.load_weights()
    return {"weights": _serialize(weights)}


@app.get(
    "/weights/history",
    tags=["Weights"],
    dependencies=[Depends(require_api_key)],
    summary="Weight change history",
)
def get_weights_history():
    """Returns the last 50 weight snapshots (id, saved_at, source)."""
    df = db.get_weights_history()
    if df.empty:
        return {"count": 0, "history": []}
    return {"count": len(df), "history": _serialize(df.to_dict(orient="records"))}


# ─── Routes — Scan ────────────────────────────────────────────────────────────

@app.get("/scan/status", tags=["Scan"], summary="Current scan status")
def get_scan_status():
    """
    Returns the current scan state: running, last timestamp, progress, and any error.
    No authentication required — safe to poll frequently.
    """
    return _serialize(db.read_scan_status())


@app.post(
    "/scan/trigger",
    tags=["Scan"],
    dependencies=[Depends(require_api_key)],
    summary="Trigger a background scan",
)
def trigger_scan():
    """
    Starts a full market scan in the background (all configured pairs × timeframes).

    Returns immediately with `status: started`.
    Poll `GET /scan/status` to track progress.
    Raises `409 Conflict` if a scan is already running.
    """
    global _scan_thread
    # Both checks are inside the lock to avoid TOCTOU race condition
    with _scan_lock:
        if _scan_thread and _scan_thread.is_alive():
            raise HTTPException(status_code=409, detail="A scan is already running")
        status = db.read_scan_status()
        if status.get("running"):
            raise HTTPException(status_code=409, detail="A scan is already running")
        _scan_thread = threading.Thread(target=_run_scan_bg, daemon=True)
        _scan_thread.start()
    return {
        "status": "started",
        "message": "Scan triggered. Poll GET /scan/status for progress.",
    }


# ─── Routes — Webhooks ────────────────────────────────────────────────────────

@app.post(
    "/webhook/tradingview",
    tags=["Webhooks"],
    summary="Receive TradingView strategy alerts",
)
def tradingview_webhook(
    payload: TradingViewWebhook,
    x_api_key: str = Header(default=""),
    token: str = Query(default=""),
):
    """
    Accepts JSON alerts from TradingView strategy or study webhooks.

    **TradingView alert message setup:**
    Set the alert message body to (copy-paste):
    ```json
    {
        "pair": "{{ticker}}",
        "action": "BUY",
        "price": {{close}},
        "timeframe": "{{interval}}",
        "strategy": "My Strategy",
        "message": "{{strategy.order.comment}}"
    }
    ```

    **What this endpoint does:**
    1. Normalises the pair symbol (BTCUSDT → BTC/USDT)
    2. Logs the webhook to the `alerts_log` table
    3. Forwards the notification to Telegram + Discord (if configured)
    4. Returns a JSON confirmation

    **Authentication:** requires `X-API-Key` header or `?token=` query param (SEC-03).
    Configure a key in Config Editor → API Server.
    TradingView cannot send custom headers — use the `?token=` query param in the webhook URL.
    """
    # SEC-HIGH-03: TradingView cannot send custom headers, so we support
    # both X-API-Key header (for API clients) AND ?token= query param
    # (for TradingView webhook URL: http://host:8000/webhook/tradingview?token=xxx).
    # Uses hmac.compare_digest for both paths to prevent timing attacks.
    # NOTE: sync def — FastAPI runs it in a thread pool, so blocking I/O (sqlite3,
    # requests.post) is safe here and will not block the event loop.

    # API-03: enforce authentication — this was accepted but never validated
    _expected = _get_configured_api_key()
    _provided = x_api_key or token
    if _expected and not hmac.compare_digest(_provided, _expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    try:
        pair = _normalize_pair(payload.pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    action = payload.action.upper().strip()

    valid_actions = {"BUY", "SELL", "STRONG BUY", "STRONG SELL", "NEUTRAL", "CLOSE", "LONG", "SHORT"}
    if action not in valid_actions:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown action '{payload.action}'. Expected one of: {sorted(valid_actions)}",
        )

    # Normalise LONG/SHORT to BUY/SELL
    if action == "LONG":
        action = "BUY"
    elif action == "SHORT":
        action = "SELL"

    # Persist to audit log
    db.log_alert_sent(
        channel="tradingview_webhook",
        pair=pair,
        direction=action,
        confidence=0.0,
        status="received",
        error_msg=payload.message or "",
    )

    # Build human-readable notification using HTML (send_telegram uses parse_mode="HTML")
    lines = [
        "📡 <b>TradingView Alert</b>",
        f"Pair: <code>{pair}</code>",
        f"Action: <code>{action}</code>",
    ]
    if payload.price is not None:
        lines.append(f"Price: <code>{payload.price:,.4f}</code>")
    if payload.timeframe:
        lines.append(f"TF: <code>{payload.timeframe}</code>")
    if payload.strategy:
        lines.append(f"Strategy: <code>{payload.strategy}</code>")
    if payload.message:
        lines.append(f"Note: {_html.escape(str(payload.message))}")

    notification = "\n".join(lines)

    # Dispatch to configured channels
    cfg = alerts.load_alerts_config()
    tg_ok, tg_err = False, None
    if cfg.get("telegram_enabled") and cfg.get("telegram_token") and cfg.get("telegram_chat_id"):
        tg_ok, tg_err = alerts.send_telegram(
            cfg["telegram_token"], cfg["telegram_chat_id"], notification
        )

    dc_ok, dc_err = False, None
    if cfg.get("discord_enabled") and cfg.get("discord_webhook_url"):
        dc_ok, dc_err = alerts.send_discord(cfg["discord_webhook_url"], notification)

    return {
        "status": "received",
        "pair": pair,
        "action": action,
        "price": payload.price,
        "alerts_sent": {
            "telegram": tg_ok,
            "discord": dc_ok,
        },
    }


# ─── Routes — Live Prices (WebSocket feed) ────────────────────────────────────

@app.get(
    "/prices/live",
    tags=["Signals"],
    dependencies=[Depends(require_api_key)],
    summary="Real-time prices from OKX WebSocket feed",
)
def get_live_prices():
    """
    Returns the latest real-time tick data for all configured pairs, sourced from
    the persistent OKX public WebSocket feed.

    Each entry includes: `price`, `change_24h_pct`, `bid`, `ask`,
    `high_24h`, `low_24h`, `volume_24h`, `timestamp`.

    Stale prices (>60 s old) are excluded.  An empty `prices` dict means
    the WebSocket has not yet received its first tick.
    """
    status = ws_feeds.get_status()
    prices = ws_feeds.get_all_prices()
    return {
        "connected": status.get("connected", False),
        "reconnects": status.get("reconnects", 0),
        "pair_count": len(prices),
        "prices": _serialize(prices),
    }


@app.get(
    "/prices/live/{pair}",
    tags=["Signals"],
    dependencies=[Depends(require_api_key)],
    summary="Real-time price for a single pair",
)
def get_live_price_pair(pair: str):
    """
    Returns the latest real-time tick for one pair.
    Accepts `BTCUSDT`, `BTC-USDT`, `BTC_USDT`, or `BTC/USDT`.
    Returns 404 if no fresh tick is available.
    """
    try:
        normalized = _normalize_pair(pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    tick = ws_feeds.get_price(normalized)
    if tick is None:
        raise HTTPException(
            status_code=404,
            detail=f"No live price available for {normalized} (WebSocket not connected or stale)",
        )
    return _serialize({"pair": normalized, **tick})


# ─── Routes — Execution ───────────────────────────────────────────────────────

@app.get(
    "/execute/status",
    tags=["Execution"],
    dependencies=[Depends(require_api_key)],
    summary="Execution engine status",
)
def get_execution_status():
    """
    Returns current execution engine settings (no secrets):
    live_trading flag, auto_execute flag, keys_configured, ccxt availability.
    """
    return _serialize(exec_engine.get_status())


@app.get(
    "/execute/balance",
    tags=["Execution"],
    dependencies=[Depends(require_api_key)],
    summary="Fetch OKX USDT balance",
)
def get_exchange_balance():
    """
    Fetches the live USDT balance from the configured OKX account.
    Requires OKX API keys to be set in Config Editor → Live Execution.
    Returns 503 if keys are not configured or connection fails.
    """
    status = exec_engine.get_status()
    if not status["keys_configured"]:
        raise HTTPException(status_code=503, detail="OKX API keys not configured")
    result = exec_engine.get_balance()
    if result.get("error"):
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@app.post(
    "/execute/order",
    tags=["Execution"],
    dependencies=[Depends(require_api_key)],
    summary="Place a buy or sell order",
)
def place_order(payload: OrderRequest):
    """
    Place a market or limit order.

    **Modes:**
    - Paper (default) — simulates a fill, logs to execution_log, no real funds used.
    - Live — sends a real order to OKX perpetual futures.
      Requires `live_trading_enabled = true` in Config Editor + valid API keys.

    **Symbol format:** accepts `BTCUSDT`, `BTC-USDT`, `BTC_USDT`, or `BTC/USDT`.
    """
    try:
        pair = _normalize_pair(payload.pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = exec_engine.place_order(
        pair          = pair,
        direction     = payload.direction.upper(),
        size_usd      = payload.size_usd,
        order_type    = payload.order_type,
        limit_price   = payload.limit_price,
        current_price = payload.current_price,
    )
    return _serialize(result)


@app.get(
    "/execute/log",
    tags=["Execution"],
    dependencies=[Depends(require_api_key)],
    summary="Execution audit log",
)
def get_execution_log(limit: int = 100):
    """
    Returns recent paper and live order records from the execution_log table.
    `limit` — number of records (default 100, max 500).
    """
    limit = min(limit, 500)
    df = db.get_execution_log_df(limit=limit)
    if df.empty:
        return {"count": 0, "orders": []}
    return {"count": len(df), "orders": _serialize(df.to_dict(orient="records"))}


# ─── Routes — Alerts log ──────────────────────────────────────────────────────

@app.get(
    "/alerts/log",
    tags=["System"],
    dependencies=[Depends(require_api_key)],
    summary="Alert dispatch audit log",
)
def get_alerts_log(limit: int = 100):
    """
    Returns recent alert dispatch records from all channels
    (Telegram, Email, Discord, TradingView webhook).
    """
    limit = min(limit, 500)
    df = db.get_alerts_log_df()
    if df.empty:
        return {"count": 0, "alerts": []}
    return {
        "count": len(df),
        "alerts": _serialize(df.tail(limit).to_dict(orient="records")),
    }
