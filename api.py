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
import logging
import os
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
from pydantic import BaseModel, Field, field_validator, model_validator

import alerts
import crypto_model_core as model
import database as db
import websocket_feeds as ws_feeds
import execution as exec_engine

# P0 audit fix — refuse to start the FastAPI process when live trading
# is enabled but no api_key is configured. Pre-fix the docker-compose
# stack would happily expose :8000 with /execute/order callable by any
# unauthenticated client. The check is a hard fail at process start so
# operators cannot ignore it. CRYPTO_SIGNAL_ALLOW_UNAUTH=true overrides
# only for local development (matches require_api_key).
try:
    _startup_cfg = alerts.load_alerts_config()
    _startup_live = bool(_startup_cfg.get("live_trading_enabled", False))
    _startup_key = (_startup_cfg.get("api_key") or "").strip()
    _startup_allow_unauth = (
        os.environ.get("CRYPTO_SIGNAL_ALLOW_UNAUTH", "").strip().lower() == "true"
    )
    if _startup_live and not _startup_key and not _startup_allow_unauth:
        raise RuntimeError(
            "FastAPI refusing to start: live_trading_enabled=True but no api_key "
            "is configured. Either set 'api_key' in alerts_config.json (recommended), "
            "disable live_trading_enabled, or export CRYPTO_SIGNAL_ALLOW_UNAUTH=true "
            "for local development."
        )
except RuntimeError:
    raise
except Exception as _cfg_err:
    logger.warning("Startup auth-config check skipped (non-fatal): %s", _cfg_err)

# Start WebSocket feed when API server loads
try:
    ws_feeds.start(model.PAIRS)
except Exception as _ws_err:
    logger.warning("WebSocket feed startup failed (non-fatal): %s", _ws_err)

# AUDIT-2026-05-04 (D8 cutover, Path A): in-process scheduler.
# Render persistent disks attach to a single service, so the original
# Outcome C plan (separate worker tier with shared disk) is impossible.
# Path A runs scheduler.py's BlockingScheduler in a daemon thread inside
# uvicorn — same single $7/mo Starter tier, single disk, single SQLite
# connection pool. Eliminates cross-process WAL contention entirely
# while keeping scheduler.py / run_scan_job unchanged.
#
# Gated by CRYPTO_SIGNAL_AUTOSTART_SCHEDULER=true so tests + local dev
# don't spawn the scheduler thread on import. render.yaml sets it on
# the production web service.
#
# AUDIT-2026-05-04 (H5): single-flight guard. If uvicorn is ever started
# with --workers > 1 (Render Standard tier supports it; default is 1),
# each worker process imports api.py and would spawn its own scheduler
# thread → duplicate scans, duplicate DB writes, duplicate alerts. We
# use a file lock on the persistent disk so only one process per host
# wins. The lock file lives next to crypto_model.db so it survives
# redeploys and only one scheduler ever runs across all workers.
if os.environ.get("CRYPTO_SIGNAL_AUTOSTART_SCHEDULER", "").strip().lower() == "true":
    _scheduler_should_start = True
    _scheduler_lock_handle = None
    try:
        from pathlib import Path as _Path
        import database as _db_for_lock
        # Same parent dir as crypto_model.db, so the lock is on the
        # persistent disk on Render and tied to host (not process).
        _lock_path = _Path(_db_for_lock.DB_FILE).parent / "scheduler.lock"
        _lock_handle = open(_lock_path, "w")
        try:
            # POSIX exclusive non-blocking lock. fcntl is unix-only;
            # on Windows we fall through to msvcrt.locking which has
            # similar semantics. Tests on local Windows dev never set
            # the autostart flag, so the Windows branch is operator-only.
            try:
                import fcntl as _fcntl
                _fcntl.flock(_lock_handle.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            except ImportError:
                import msvcrt as _msvcrt
                _msvcrt.locking(_lock_handle.fileno(), _msvcrt.LK_NBLCK, 1)
            # Acquired — keep the file handle alive for the process
            # lifetime so the lock stays held.
            _scheduler_lock_handle = _lock_handle
            _lock_handle.write(str(os.getpid()))
            _lock_handle.flush()
            logger.info("[Scheduler] Acquired single-flight lock at %s (pid=%d)", _lock_path, os.getpid())
        except (BlockingIOError, OSError) as _lock_err:
            # Another worker already owns the scheduler — skip.
            _scheduler_should_start = False
            _lock_handle.close()
            logger.info(
                "[Scheduler] Lock at %s held by another worker — skipping autostart in pid=%d (%s)",
                _lock_path, os.getpid(), _lock_err,
            )
    except Exception as _lock_setup_err:
        # If lock setup fails entirely (e.g. disk not mounted), don't block
        # the API from starting — but DON'T spawn the scheduler either,
        # because we can't verify single-flight. Operator can investigate
        # via /diagnostics.
        _scheduler_should_start = False
        logger.warning(
            "[Scheduler] Single-flight lock setup failed — scheduler will NOT autostart this process: %s",
            _lock_setup_err,
        )

    if _scheduler_should_start:
        try:
            import threading as _scheduler_threading
            import scheduler as _bg_scheduler

            def _run_scheduler_in_background():
                try:
                    _bg_scheduler.start_scheduler()  # blocks inside this daemon thread
                except Exception as _bg_err:
                    logger.exception("[Scheduler] Background thread crashed: %s", _bg_err)

            _scheduler_threading.Thread(
                target=_run_scheduler_in_background,
                name="autoscan-scheduler",
                daemon=True,
            ).start()
            logger.info("[Scheduler] Autostart enabled — running in daemon thread inside uvicorn")
        except Exception as _sched_err:
            logger.warning("[Scheduler] Autostart failed (non-fatal): %s", _sched_err)

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
    # Phase D D1: include Next.js local dev (3000) so the new FastAPI
    # routers can be hit from `npm run dev` while the Streamlit fallback
    # stays addressable on 8501. Vercel preview + production domains are
    # admitted via the regex (matches https://*.vercel.app and
    # https://crypto-signal-app.vercel.app once Vercel assigns it).
    # AUDIT-2026-05-03 (Tier 1 HIGH): dropped bare `http://localhost` —
    # without a port it matches any localhost service (incl. unrelated apps
    # the user happens to run), broadening the CORS surface beyond what the
    # 8501/3000 entries already cover. Streamlit + Next.js dev are explicit.
    allow_origins=[
        "http://localhost:8501", "http://127.0.0.1:8501",
        "http://localhost:3000", "http://127.0.0.1:3000",
        # Production domains added explicitly once Vercel deploy lands in D5
    ],
    # AUDIT-2026-05-02 (HIGH security fix): previous regex
    # `https://([a-z0-9-]+\.)*vercel\.app` matched ANY subdomain of
    # vercel.app (including every other Vercel customer's preview deploy),
    # which means a malicious site at attacker.vercel.app could prompt-
    # inject a victim's browser into issuing authenticated calls if the
    # X-API-Key was ever placed in a fetchable surface. Tightened to the
    # owner-prefixed Vercel pattern only.
    #
    # AUDIT-2026-05-04 (overnight, post-D5-deploy): the v0-created Vercel
    # project assigned the canonical URL
    # `v0-davidduraesdd1-blip-crypto-signa.vercel.app` (per-deploy hashes
    # take the form `v0-davidduraesdd1-blip-crypto-signal-<hash>.vercel.app`
    # and `v0-davidduraesdd1-blip-git-<hash>-davidduraesdd1-<id>-projects
    # .vercel.app`). The previous regex only matched
    # `crypto-signal-app(...)?` and rejected every v0-prefixed URL, so the
    # browser blocked every API call from the live Vercel frontend.
    # Broadened to: any vercel.app subdomain that contains the literal
    # owner identifier `davidduraesdd1-blip`. That preserves the
    # owner-prefix-only security property (a different Vercel customer
    # cannot impersonate David) while admitting all four real URL shapes
    # this project produces.
    allow_origin_regex=(
        r"^https://"
        r"(crypto-signal-app(-[a-z0-9-]+-davidduraesdd1-blip)?"
        r"|[a-z0-9-]*davidduraesdd1-blip[a-z0-9-]*)"
        r"\.vercel\.app$"
    ),
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # PUT/DELETE added for D1 routers
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
    """Read the configured API key, env var first then alerts_config.json.

    AUDIT-2026-05-03 (CRITICAL C-1 fix): mirror routers/deps.py — read
    `CRYPTO_SIGNAL_API_KEY` from env first so the production Render
    deploy can rotate keys via dashboard env var (Render's file system
    is ephemeral, so a file-based key would disappear on every push).
    Falls back to the existing alerts_config.json path for local dev
    and Streamlit-UI compatibility.
    """
    with _api_key_lock:
        if time.time() - _api_key_cache["ts"] < _API_KEY_CACHE_TTL:
            return _api_key_cache["key"] or ""
    env_key = (os.environ.get("CRYPTO_SIGNAL_API_KEY") or "").strip()
    if env_key:
        key = env_key
    else:
        cfg = alerts.load_alerts_config()
        key = cfg.get("api_key", "")
    with _api_key_lock:
        _api_key_cache["key"] = key
        _api_key_cache["ts"] = time.time()   # timestamp after I/O for accurate TTL
    return key


def require_api_key(x_api_key: str = Header(default="")):
    """Dependency: validates X-API-Key header on auth-required endpoints.

    SEC-MEDIUM-03: uses hmac.compare_digest() to prevent timing-based
    key enumeration.

    P0 audit fix — pre-fix this was an empty no-op when `api_key` was
    unset, exposing POST /execute/order, /scan/trigger, and the
    /tradingview_webhook path to any caller who could reach :8000.
    Default is now FAIL-CLOSED: if no key is configured, every
    auth-required endpoint returns 503 with operator guidance. To
    intentionally run without auth (e.g. local-only development),
    set CRYPTO_SIGNAL_ALLOW_UNAUTH=true in the environment.
    """
    expected = _get_configured_api_key()
    if not expected:
        if os.environ.get("CRYPTO_SIGNAL_ALLOW_UNAUTH", "").strip().lower() == "true":
            return  # explicit opt-out — local-dev only
        raise HTTPException(
            status_code=503,
            detail=(
                "API key not configured. Set 'api_key' in alerts_config.json "
                "(or via the Settings page) to enable authenticated access, "
                "or export CRYPTO_SIGNAL_ALLOW_UNAUTH=true for local development."
            ),
        )
    if not hmac.compare_digest(x_api_key, expected):
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
            alerts.send_scan_email_alerts(results, cfg)
        except Exception as _e:
            logger.warning("[API] Email alert failed: %s", _e)
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


# AUDIT-2026-05-03 (P3 — input-validation slice of C-3): canonical
# vocabularies for OrderRequest fields. The full C-3 (allowlist + size
# cap + SL/TP validation) is being applied as P4 in a follow-up commit;
# this commit covers only the input-validation gate that fails fast at
# 422 before the order even reaches execution.place_order.
_ALLOWED_DIRECTIONS = {"BUY", "SELL", "STRONG BUY", "STRONG SELL"}
_ALLOWED_ORDER_TYPES = {"market", "limit"}

# 10_000 USD per-order ceiling. Conservative — the existing
# `agent_max_trade_size_usd` config is $1000, so this leaves a 10× safety
# margin for manual orders. Operators can raise it via env var if a
# larger manual order is needed (P4 will surface this as a config field
# rather than a hard constant).
_MAX_ORDER_SIZE_USD = float(os.environ.get("CRYPTO_SIGNAL_MAX_ORDER_USD", "10000"))


class OrderRequest(BaseModel):
    pair:          str            = Field(..., min_length=3, max_length=32,
                                          description="e.g. BTC/USDT or BTCUSDT")
    direction:     str            = Field(..., description=
                                          f"One of: {', '.join(sorted(_ALLOWED_DIRECTIONS))}")
    size_usd:      float          = Field(..., gt=0, le=_MAX_ORDER_SIZE_USD,
                                          description=f"Notional USD order size (0 < x ≤ {_MAX_ORDER_SIZE_USD})")
    order_type:    str            = Field("market", description=
                                          f"One of: {', '.join(sorted(_ALLOWED_ORDER_TYPES))}")
    limit_price:   Optional[float] = Field(None, gt=0,
                                           description="Price for limit orders (must be > 0 when order_type=limit)")
    current_price: Optional[float] = Field(None, gt=0,
                                           description="Hint for paper fill / contract-qty calc (must be > 0 when set)")
    # AUDIT-2026-05-03 (P4-C-4): optional caller-provided idempotency key.
    # A retry with the same value returns the cached result rather than
    # placing a duplicate order. Sanitized to alphanumeric and truncated
    # to 32 chars by execution._sanitize_clord_id (OKX clOrdId limit).
    client_order_id: Optional[str] = Field(None, max_length=64,
                                           description="Caller-provided idempotency key. Same value on retry = cached result, no duplicate order.")

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction(cls, v):
        """Accept lowercase + extra whitespace; the enum check is on the
        canonical uppercase form. Preserves the prior-call-site pattern
        `payload.direction.upper()` while making the contract explicit
        at validation time.
        """
        if not isinstance(v, str):
            return v
        normalized = v.strip().upper()
        if normalized not in _ALLOWED_DIRECTIONS:
            raise ValueError(
                f"direction {v!r} not in {sorted(_ALLOWED_DIRECTIONS)}"
            )
        return normalized

    @field_validator("order_type", mode="before")
    @classmethod
    def _normalize_order_type(cls, v):
        """Accept MARKET / Market / market; canonical lowercase is what
        ccxt expects downstream.
        """
        if not isinstance(v, str):
            return v
        normalized = v.strip().lower()
        if normalized not in _ALLOWED_ORDER_TYPES:
            raise ValueError(
                f"order_type {v!r} not in {sorted(_ALLOWED_ORDER_TYPES)}"
            )
        return normalized

    @model_validator(mode="after")
    def _limit_orders_require_limit_price(self):
        """A limit order with no `limit_price` is meaningless and would
        either crash deeper in execution.py or fall back to a market
        fill on OKX — neither is what the caller asked for.
        """
        if self.order_type == "limit" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError(
                "order_type='limit' requires limit_price > 0"
            )
        return self


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
        logger.warning("DB stats unavailable: %s", _e)
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
        # AUDIT-2026-05-06 (W2 Tier 2): emit BOTH `count` and `total`.
        # Frontend (web/app/backtester/page.tsx:133) reads `count`; the
        # original `total` is kept as alias for any external consumer.
        return {"count": 0, "total": 0, "offset": offset, "limit": limit, "trades": []}
    total = len(df)
    page = df.iloc[offset : offset + limit]
    return {
        "count": total,
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
    3. Returns a JSON confirmation

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
    # AUDIT-2026-05-02 (HIGH security fix): previously failed OPEN when
    # _expected was empty — any caller could write to alerts_log + trigger
    # downstream agent paths. Now mirrors require_api_key fail-closed
    # contract: 503 if no key is configured (unless the local-dev
    # CRYPTO_SIGNAL_ALLOW_UNAUTH escape hatch is set). Constant-time
    # compare prevents timing attacks on key guessing.
    _expected = _get_configured_api_key()
    _provided = x_api_key or token or ""
    if not _expected:
        if os.environ.get("CRYPTO_SIGNAL_ALLOW_UNAUTH", "").strip().lower() == "true":
            pass  # local dev bypass — explicit env var only
        else:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Webhook auth unavailable: API key not configured. "
                    "Set 'api_key' via the Settings page before exposing "
                    "this webhook URL publicly."
                ),
            )
    elif not hmac.compare_digest(_provided, _expected):
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

    # Inbound alert is logged to the DB above; add email dispatch here later
    # via alerts.send_email_alert if needed.
    return {
        "status": "received",
        "pair": pair,
        "action": action,
        "price": payload.price,
        "alerts_sent": {},
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
    # AUDIT-2026-05-03 (P3): payload.direction and payload.order_type are
    # already canonical (uppercase + lowercase respectively) thanks to
    # the field_validators on OrderRequest, so no further normalization
    # is needed here. The prior `.upper()` call is redundant.
    result = exec_engine.place_order(
        pair             = pair,
        direction        = payload.direction,
        size_usd         = payload.size_usd,
        order_type       = payload.order_type,
        limit_price      = payload.limit_price,
        current_price    = payload.current_price,
        client_order_id  = payload.client_order_id,
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
    """Returns recent alert dispatch records from all channels (Email, TradingView webhook).

    AUDIT-2026-05-06 (W2 Tier 2): the DB columns are `sent_at`,
    `channel`, `pair`, `direction`, `confidence`, `status`, `error_msg`,
    but the frontend (web/app/alerts/history/page.tsx) reads
    `timestamp`, `type`, `message`. Three name drifts caused every
    timestamp + every successful alert to render with empty fields.
    Aliases added on the way out so the existing TS client just works.
    """
    limit = min(limit, 500)
    df = db.get_alerts_log_df()
    if df.empty:
        return {"count": 0, "alerts": []}

    rows = df.tail(limit).to_dict(orient="records")
    aliased = []
    for r in rows:
        out = dict(r)
        # sent_at → timestamp (keep sent_at for back-compat)
        if "sent_at" in out and "timestamp" not in out:
            out["timestamp"] = out["sent_at"]
        # channel → type (frontend uses `type` to pick a badge color)
        if "channel" in out and "type" not in out:
            out["type"] = out["channel"]
        # error_msg → message (or status if no error)
        if "message" not in out:
            err = out.get("error_msg")
            status = out.get("status")
            out["message"] = (
                err if err
                else f"{out.get('direction','')} {out.get('pair','')}".strip()
                or (status or "")
            )
        aliased.append(out)
    return {
        "count": len(df),
        "alerts": _serialize(aliased),
    }


# ─── Phase D D1 — Next.js frontend gap-fill routers ────────────────────────────
# Six new routers wrapping the existing engine for the Next.js + Tailwind
# frontend (Vercel). Mounted last so they layer on top of the existing
# /signals, /backtest, /weights, /scan, /execute, /alerts/log surface
# without disturbing it.
#
# Plan:  docs/redesign/2026-05-02_phase-d-streamlit-retirement.md
# Audit: docs/redesign/2026-05-02_d1-api-audit.md

from routers import home as _home_router
from routers import regimes as _regimes_router
from routers import onchain as _onchain_router
from routers import alerts as _alerts_router_module
from routers import ai_assistant as _ai_router
from routers import settings as _settings_router
from routers import exchange as _exchange_router       # D-ext: test-connection
from routers import diagnostics as _diagnostics_router # D-ext: 7-gate + db-health
from routers import backtest as _backtest_router       # D-ext: summary/trades/runs (added 2026-05-04 — closes Backtester page 404 on live)

app.include_router(_home_router.router,            prefix="",             tags=["Home"])
app.include_router(_regimes_router.router,         prefix="/regimes",     tags=["Regimes"])
app.include_router(_onchain_router.router,         prefix="/onchain",     tags=["On-Chain"])
app.include_router(_alerts_router_module.router,   prefix="/alerts",      tags=["Alerts"])
app.include_router(_ai_router.router,              prefix="/ai",          tags=["AI Assistant"])
app.include_router(_settings_router.router,        prefix="/settings",    tags=["Settings"])
app.include_router(_exchange_router.router,        prefix="/exchange",    tags=["Exchange"])
app.include_router(_diagnostics_router.router,     prefix="/diagnostics", tags=["Diagnostics"])
app.include_router(_backtest_router.router,        prefix="/backtest",    tags=["Backtest"])
