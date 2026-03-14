"""
execution.py — Live/Paper order execution via ccxt (OKX)

Paper-safe by default: live_trading_enabled must be explicitly True in
alerts_config.json to submit real orders.  All orders (paper and live)
are logged to the database execution_log table.

Paper mode  — simulates fill at the current live/scan price.
Live mode   — submits real market or limit orders to OKX USDT-M perp futures.

Usage (from app.py / api.py):
    import execution as _exec
    result = _exec.place_order("BTC/USDT", "BUY", size_usd=500)
    status = _exec.get_status()
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

import database as db
import alerts as _alerts

logger = logging.getLogger(__name__)

try:
    import ccxt
    _CCXT_AVAILABLE = True
except ImportError:
    _CCXT_AVAILABLE = False


# ─── Config helpers ────────────────────────────────────────────────────────────

def get_exec_config() -> dict:
    """Return execution settings from alerts_config.json (merged with defaults).
    SEC-CRITICAL-02: OKX API credentials are read with environment variable fallback so
    production deployments can avoid storing secrets in alerts_config.json:
        export OKX_API_KEY=xxx OKX_SECRET=xxx OKX_PASSPHRASE=xxx
    Environment variables take precedence over the JSON config file.
    """
    import os
    cfg = _alerts.load_alerts_config()
    # Env vars take precedence — allows secret-free config files in production
    api_key     = os.environ.get("OKX_API_KEY")     or cfg.get("okx_api_key", "")
    secret      = os.environ.get("OKX_SECRET")      or cfg.get("okx_secret", "")
    passphrase  = os.environ.get("OKX_PASSPHRASE")  or cfg.get("okx_passphrase", "")
    return {
        "live_trading":       bool(cfg.get("live_trading_enabled", False)),
        "auto_execute":       bool(cfg.get("auto_execute_enabled", False)),
        "auto_min_conf":      float(cfg.get("auto_execute_min_confidence", 80)),
        "okx_api_key":        api_key,
        "okx_secret":         secret,
        "okx_passphrase":     passphrase,
        "default_order_type": (cfg.get("default_order_type", "") or "").strip() or "market",
        "keys_configured":    bool(api_key and secret and passphrase),
    }


# ─── Exchange factory ───────────────────────────────────────────────────────────

# BUG-R12: module-level exchange singleton cache — avoids creating a new ccxt.okx()
# instance on every call to _get_exchange(). Invalidated after 5 minutes or when
# API key config changes (key_hash mismatch).
_exchange_cache: dict = {}
_EXCHANGE_TTL = 300.0  # 5 minutes
_exchange_cache_lock = threading.Lock()  # BUG-C07: protects TOCTOU race on cache check+write


def _get_exchange(authenticated: bool = True):
    """
    Return a ccxt.okx instance for USDT-margined perpetual swaps.
    If authenticated=True and keys are present, returns an authed session.
    Cached for _EXCHANGE_TTL seconds per (auth, keys) combination.
    """
    if not _CCXT_AVAILABLE:
        raise RuntimeError("ccxt not installed — run: pip install ccxt")
    cfg = get_exec_config()
    import hashlib as _hashlib
    _key_digest = _hashlib.sha256(cfg['okx_api_key'].encode()).hexdigest()[:16] if cfg['okx_api_key'] else ''
    key_hash = f"{authenticated}:{cfg['keys_configured']}:{_key_digest}"
    now = time.time()
    with _exchange_cache_lock:  # BUG-C07: atomic check-then-create
        if (
            _exchange_cache.get("instance") is not None
            and _exchange_cache.get("key_hash") == key_hash
            and now - _exchange_cache.get("ts", 0.0) < _EXCHANGE_TTL
        ):
            return _exchange_cache["instance"]
        params: dict = {
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if authenticated and cfg["keys_configured"]:
            params["apiKey"]   = cfg["okx_api_key"]
            params["secret"]   = cfg["okx_secret"]
            params["password"] = cfg["okx_passphrase"]
        ex = ccxt.okx(params)
        _exchange_cache.update({"instance": ex, "ts": now, "key_hash": key_hash})
        return ex


_markets_cache: dict = {}  # {"ts": float, "markets": dict}
_MARKETS_TTL = 3600.0  # 1 hour between market reloads
_markets_lock = threading.Lock()


def _load_markets_cached(ex) -> None:
    """Call ex.load_markets() at most once per hour — avoids a round-trip on every order.
    Thread-safe: only one caller loads markets; others wait and reuse the result."""
    with _markets_lock:
        cached = _markets_cache.get("ts", 0.0)
        if time.time() - cached < _MARKETS_TTL and _markets_cache.get("markets"):
            ex.markets = _markets_cache["markets"]
            return
        ex.load_markets()
        _markets_cache["ts"]      = time.time()
        _markets_cache["markets"] = ex.markets


def _to_swap_symbol(pair: str) -> str:
    """BTC/USDT → BTC/USDT:USDT  (ccxt OKX perpetual swap format)."""
    if ":" in pair:
        return pair
    base, quote = pair.split("/")
    return f"{base}/{quote}:{quote}"


# ─── Balance / connection check ─────────────────────────────────────────────────

def get_balance() -> dict:
    """
    Fetch USDT balance from OKX.
    Returns {"total": float, "free": float, "used": float, "error": str|None}.
    """
    try:
        ex      = _get_exchange(authenticated=True)
        balance = ex.fetch_balance()
        usdt    = balance.get("USDT", {})
        return {
            "total": round(float(usdt.get("total") or 0), 2),
            "free":  round(float(usdt.get("free")  or 0), 2),
            "used":  round(float(usdt.get("used")  or 0), 2),
            "error": None,
        }
    except Exception as exc:
        return {"total": 0.0, "free": 0.0, "used": 0.0, "error": str(exc)}


def test_connection() -> dict:
    """
    Validate OKX API credentials.
    Returns {"ok": bool, "balance_usdt": float, "error": str|None}.
    """
    b = get_balance()
    if b["error"]:
        return {"ok": False, "balance_usdt": 0.0, "error": b["error"]}
    return {"ok": True, "balance_usdt": b["total"], "error": None}


# ─── Core order placement ───────────────────────────────────────────────────────

def place_order(
    pair: str,
    direction: str,
    size_usd: float,
    order_type: str = "market",
    limit_price: Optional[float] = None,
    current_price: Optional[float] = None,
) -> dict:
    """
    Place a buy or sell order.

    Paper mode (live_trading_enabled = False):
        Simulates an instant fill at current_price.
        Logs to execution_log with mode='paper'.
        Returns immediately with ok=True.

    Live mode (live_trading_enabled = True):
        Submits a real market or limit order to OKX perpetual futures via ccxt.
        Calculates contract quantity from size_usd automatically.

    Parameters
    ----------
    pair          : "BTC/USDT" style
    direction     : "BUY" | "STRONG BUY" | "SELL" | "STRONG SELL"
    size_usd      : notional USD value of the order
    order_type    : "market" | "limit"
    limit_price   : price for limit orders (ignored for market)
    current_price : used as paper fill price and contract-qty calculation fallback

    Returns
    -------
    dict with keys: ok, mode, pair, direction, side, size_usd,
                    order_type, price, order_id, error, placed_at
    """
    cfg    = get_exec_config()
    live   = cfg["live_trading"]
    _dir_upper = direction.upper()
    if not any(v in _dir_upper for v in ("BUY", "SELL")):
        return {
            "ok": False, "mode": "live" if cfg["live_trading"] else "paper",
            "pair": pair, "direction": direction, "side": None,
            "size_usd": size_usd, "order_type": order_type,
            "price": current_price, "order_id": None,
            "error": f"Invalid direction: {direction!r}. Must contain BUY or SELL.",
            "placed_at": datetime.now().isoformat(),
        }
    if size_usd <= 0:
        return {
            "ok": False, "mode": "live" if cfg["live_trading"] else "paper",
            "pair": pair, "direction": direction, "side": None,
            "size_usd": size_usd, "order_type": order_type,
            "price": current_price, "order_id": None,
            "error": f"Invalid size_usd={size_usd}: must be > 0.",
            "placed_at": datetime.now().isoformat(),
        }
    side   = "buy" if "BUY" in _dir_upper else "sell"
    symbol = _to_swap_symbol(pair)

    result: dict = {
        "ok":         False,
        "mode":       "live" if live else "paper",
        "pair":       pair,
        "direction":  direction,
        "side":       side,
        "size_usd":   size_usd,
        "order_type": order_type,
        "price":      current_price,
        "order_id":   None,
        "error":      None,
        "placed_at":  datetime.now().isoformat(),
    }

    # ── PAPER MODE ────────────────────────────────────────────────────────────
    if not live:
        # BUG-EXEC02: try live WebSocket price if scan price is missing/zero.
        if current_price is None or current_price <= 0:
            try:
                import websocket_feeds as _ws_feeds
                ws_tick = _ws_feeds.get_price(pair)
                if ws_tick:
                    current_price = ws_tick["price"]
            except Exception:
                pass
        # BUG-R03: truthiness check rejects 0.0 (broken ticker) silently.
        # Explicit None / non-positive check is clearer and safer.
        if current_price is None or current_price <= 0:
            result["error"] = "No price available for paper fill — WebSocket not connected and no scan price"
            _log_to_db(result)
            return result
        fill_price         = current_price
        result["ok"]       = True
        result["order_id"] = f"PAPER-{uuid.uuid4().hex[:12]}-{pair.replace('/', '')}"
        result["price"]    = fill_price
        logger.info(
            "[EXEC] PAPER %s %s $%.0f @ $%.4f",
            side.upper(), pair, size_usd, fill_price,
        )
        _log_to_db(result)
        return result

    # ── LIVE MODE ─────────────────────────────────────────────────────────────
    if not _CCXT_AVAILABLE:
        result["error"] = "ccxt not installed — run: pip install ccxt"
        _log_to_db(result)
        return result

    if not cfg["keys_configured"]:
        result["error"] = "OKX API keys not configured"
        _log_to_db(result)
        return result

    try:
        ex = _get_exchange(authenticated=True)
        _load_markets_cached(ex)

        # Resolve price → contract quantity
        ticker    = ex.fetch_ticker(symbol)
        price_now = float(ticker.get("last") or current_price or 1.0)
        market    = ex.market(symbol)
        ct_size   = float(market.get("contractSize") or 1.0)
        qty       = max(1, round(size_usd / (price_now * ct_size)))

        if order_type == "market":
            order = ex.create_market_order(symbol, side, qty)
        else:
            p = float(limit_price or price_now)
            order = ex.create_limit_order(symbol, side, qty, p)

        result["ok"]       = True
        result["order_id"] = str(order.get("id", "unknown"))
        _fill_price = order.get("price") or order.get("average")
        if not _fill_price:
            logger.warning("[EXEC] Fill price missing from exchange response — falling back to ticker price %.4f", price_now)
        result["price"]    = float(_fill_price or price_now)
        logger.info(
            "[EXEC] LIVE %s %s %d ct @ %.4f | id=%s",
            side.upper(), pair, qty, result["price"], result["order_id"],
        )
    except Exception as exc:
        result["error"] = str(exc)
        logger.error("[EXEC] Order failed %s: %s", pair, exc)

    _log_to_db(result)
    return result


def close_position(
    pair: str,
    direction: str,
    size_usd: float,
    current_price: Optional[float] = None,
    order_type: Optional[str] = None,
) -> dict:
    """
    Close/flatten an open position (opposite-side order).
    direction = direction of the open position (BUY → close with SELL).
    order_type defaults to the configured default_order_type (usually 'market').
    """
    close_dir = "SELL" if "BUY" in direction.upper() else "BUY"
    if order_type is None:
        order_type = get_exec_config().get("default_order_type", "market")
    return place_order(
        pair=pair,
        direction=close_dir,
        size_usd=size_usd,
        order_type=order_type,
        current_price=current_price,
    )


# ─── Auto-execute ───────────────────────────────────────────────────────────────

def auto_execute_signals(
    results: list,
    portfolio_size_usd: float = 10_000.0,
) -> list[dict]:
    """
    Optionally called after a scan completes.
    Places orders for HIGH_CONF signals that exceed auto_min_conf.
    Works in both paper and live modes (controlled by live_trading_enabled).

    Returns list of execution result dicts.
    """
    cfg = get_exec_config()
    if not cfg["auto_execute"]:
        return []

    min_conf = cfg["auto_min_conf"]
    executed = []
    for r in results:
        conf      = r.get("confidence_avg_pct", 0)
        direction = r.get("direction", "")
        pair      = r.get("pair", "")
        if conf < min_conf or "NEUTRAL" in direction or not direction:
            continue
        if not r.get("high_conf"):
            continue  # only execute HIGH_CONF signals automatically
        size_usd = (float(r.get("position_size_pct") or 10) / 100) * portfolio_size_usd
        res = place_order(
            pair=pair,
            direction=direction,
            size_usd=size_usd,
            order_type=cfg["default_order_type"],
            current_price=r.get("price_usd"),
        )
        executed.append(res)
    return executed


# ─── DB persistence ─────────────────────────────────────────────────────────────

def _log_to_db(result: dict) -> None:
    """Persist execution result to database.execution_log (best-effort)."""
    try:
        db.log_execution(
            placed_at  = result.get("placed_at", datetime.now().isoformat()),
            pair       = result.get("pair", ""),
            direction  = result.get("direction", ""),
            side       = result.get("side", ""),
            size_usd   = float(result.get("size_usd") or 0),
            order_type = result.get("order_type", "market"),
            price      = float(result.get("price") or 0),
            order_id   = result.get("order_id") or "",
            status     = "ok" if result.get("ok") else "failed",
            mode       = result.get("mode", "paper"),
            error_msg  = result.get("error"),
        )
    except Exception as exc:
        logger.warning("[EXEC] DB log failed: %s", exc)


# ─── Status ─────────────────────────────────────────────────────────────────────

def get_status() -> dict:
    """Return current execution config summary (no secrets)."""
    cfg = get_exec_config()
    return {
        "ccxt_available":     _CCXT_AVAILABLE,
        "live_trading":       cfg["live_trading"],
        "auto_execute":       cfg["auto_execute"],
        "auto_min_conf":      cfg["auto_min_conf"],
        "keys_configured":    cfg["keys_configured"],
        "default_order_type": cfg["default_order_type"],
    }
