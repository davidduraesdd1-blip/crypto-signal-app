"""
websocket_feeds.py — Real-time price feeds via OKX public WebSocket
Runs a persistent background thread; auto-reconnects on disconnect.
No API key required — uses OKX public tickers channel (SWAP instruments).

Usage:
    import websocket_feeds as _ws
    _ws.start(["BTC/USDT", "ETH/USDT"])   # idempotent — safe to call on every Streamlit rerun
    price_data = _ws.get_price("BTC/USDT") # {"price", "change_24h_pct", "bid", "ask", ...}
    all_prices = _ws.get_all_prices()
    status     = _ws.get_status()
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from typing import Optional

try:
    import websocket  # websocket-client package
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────
_OKX_WS_URL        = "wss://ws.okx.com:8443/ws/v5/public"
_RECONNECT_DELAY   = 5    # seconds between reconnect attempts
_PING_INTERVAL     = 25   # seconds between OKX keepalive pings
_STALE_THRESHOLD   = 60   # seconds before a price is considered stale
_WATCHDOG_INTERVAL = 30   # heartbeat check every 30 seconds
_WATCHDOG_TIMEOUT  = 45   # force reconnect if no message in 45 seconds

# ── Shared state (thread-safe via _lock) ───────────────────────
_lock   = threading.Lock()
_prices: dict[str, dict] = {}
_status: dict = {
    "connected":          False,
    "last_message_at":    None,
    "reconnects":         0,
    "subscribed_pairs":   [],
    "error":              None,
    "available":          _WS_AVAILABLE,
}

# ── Singleton thread handles ───────────────────────────────────
_ws_thread: Optional[threading.Thread] = None
_ws_app:    Optional[object]           = None  # websocket.WebSocketApp
_running   = False
_pairs_key: Optional[frozenset] = None  # detect pair changes
_session_id: int = 0  # incremented on each start(); old thread checks its own session


# ── Pair format helpers ────────────────────────────────────────
def _to_okx(pair: str) -> str:
    """BTC/USDT → BTC-USDT-SWAP"""
    # WS-02: guard against malformed pair strings (no slash)
    parts = pair.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid pair format for WebSocket subscription: {pair!r}")
    base, quote = parts
    return f"{base}-{quote}-SWAP"


def _from_okx(inst_id: str) -> str:
    """BTC-USDT-SWAP → BTC/USDT"""
    parts = inst_id.split("-")
    if len(parts) < 2:
        return "UNKNOWN/UNKNOWN"
    return f"{parts[0]}/{parts[1]}"


# ── WebSocket callbacks ────────────────────────────────────────
def _on_open(ws, pairs: list[str]) -> None:
    with _lock:
        _status["connected"]        = True
        _status["error"]            = None
        _status["subscribed_pairs"] = list(pairs)
    # WS-02: skip any pairs that fail format conversion rather than crashing the connection
    args = []
    for p in pairs:
        try:
            args.append({"channel": "tickers", "instId": _to_okx(p)})
        except ValueError as e:
            logger.warning("[WS] Skipping malformed pair %r: %s", p, e)
    if args:
        ws.send(json.dumps({"op": "subscribe", "args": args}))
    logger.info("[WS] Subscribed to tickers for %s", pairs)


def _on_message(ws, message: str) -> None:
    # Update last_message_at on every frame, before parsing, so is_stale()
    # never false-positives while the connection is actually alive.
    with _lock:
        _status["last_message_at"] = time.time()
    try:
        data = json.loads(message)
        # Ignore event confirmations and pongs
        if "event" in data or "data" not in data:
            return
        for item in data["data"]:
            inst_id   = item.get("instId", "")
            last_str   = str(item.get("last") or "").strip()  # str(…or"") handles JSON null same as open24h below
            open24_str = str(item.get("open24h") or "0").strip()  # BUG-R25: .get() returns None when key exists with JSON null; str(…or"0") handles that
            if not last_str or not inst_id.endswith("-SWAP"):
                continue
            last   = float(last_str)
            open24 = float(open24_str) if open24_str else last
            # BUG-WS01: reject ticks with NaN/Inf in core price fields —
            # these propagate silently into signal calculations and charts.
            if not (math.isfinite(last) and math.isfinite(open24)):
                logger.debug("[WS] skipping tick with non-finite price: %s last=%s", inst_id, last_str)
                continue
            # WS-03: require open24 > 0 to avoid divide-by-zero and negative-price corruption
            change = ((last - open24) / open24 * 100) if open24 > 0 else 0.0
            pair   = _from_okx(inst_id)
            # WS-03: use `or last` pattern — handles None (JSON null) and empty string safely
            # without calling float("None") which raises ValueError
            entry  = {
                "price":           last,
                "change_24h_pct":  round(change, 3),
                "bid":             float(item.get("bidPx")  or last),
                "ask":             float(item.get("askPx")  or last),
                "high_24h":        float(item.get("high24h") or last),
                "low_24h":         float(item.get("low24h")  or last),
                "volume_24h":      float(item.get("vol24h")  or 0),
                "timestamp":       time.time(),
            }
            with _lock:
                _prices[pair] = entry
    except Exception as exc:
        logger.debug("[WS] message parse error: %s", exc)


def _on_error(ws, error) -> None:
    with _lock:
        _status["connected"] = False
        _status["error"]     = str(error)
    logger.warning("[WS] error: %s", error)


def _on_close(ws, close_code, close_msg) -> None:
    with _lock:
        _status["connected"] = False
    logger.info("[WS] closed (code=%s)", close_code)


# ── Background loop ────────────────────────────────────────────
def _run_loop(pairs: list[str], session: int) -> None:
    """Loop only while _running AND our session_id hasn't been superseded."""
    global _ws_app
    while _running and _session_id == session:
        try:
            # WS-04: protect the write to _ws_app with the shared lock so the watchdog
            # thread (which reads _ws_app under _lock) cannot see a partial write
            new_app = websocket.WebSocketApp(
                _OKX_WS_URL,
                on_open=lambda ws: _on_open(ws, pairs),
                on_message=_on_message,
                on_error=_on_error,
                on_close=_on_close,
            )
            with _lock:
                _ws_app = new_app
            # Use local ref so a concurrent start() replacing _ws_app doesn't affect this run
            new_app.run_forever(ping_interval=_PING_INTERVAL, ping_timeout=10)
        except Exception as exc:
            logger.warning("[WS] loop exception: %s", exc)
        if _running and _session_id == session:
            with _lock:
                _status["reconnects"] += 1
                _status["connected"]   = False
            time.sleep(_RECONNECT_DELAY)


# ── Public API ─────────────────────────────────────────────────
def start(pairs: list[str]) -> None:
    """Start the WebSocket feed (idempotent — safe to call on every Streamlit rerun)."""
    global _ws_thread, _running, _pairs_key, _ws_app, _session_id
    if not _WS_AVAILABLE:
        return
    new_key = frozenset(pairs)
    ws_to_close = None
    with _lock:
        if _running and _pairs_key == new_key:
            return  # already running for these exact pairs
        # Bump session_id BEFORE setting _running=True so the old thread
        # sees the invalidation on its next `_session_id == session` check.
        _session_id += 1
        my_session = _session_id
        if _running:
            ws_to_close = _ws_app
            _status["connected"] = False
        _running   = True
        _pairs_key = new_key
    # Close the old socket outside the lock — may block briefly
    if ws_to_close:
        try:
            ws_to_close.close()
        except Exception as _ws_close_err:
            logger.debug("[WS] old socket close failed (non-fatal): %s", _ws_close_err)
    _ws_thread = threading.Thread(
        target=_run_loop,
        args=(pairs, my_session),
        daemon=True,
        name="ws-okx-tickers",
    )
    _ws_thread.start()
    _start_watchdog(pairs)   # ensure heartbeat watchdog is running
    logger.info("[WS] Started feed for %s", pairs)


def stop() -> None:
    """Gracefully stop the WebSocket feed."""
    global _running, _ws_app, _watchdog_running
    ws_to_close = None
    with _lock:
        _running = False
        ws_to_close = _ws_app
        _status["connected"] = False
    # WS-06: stop the watchdog so it doesn't keep running after stop()
    _watchdog_running = False
    # Close outside the lock to avoid blocking other readers
    if ws_to_close:
        try:
            ws_to_close.close()
        except Exception as _ws_stop_err:
            logger.debug("[WS] stop() socket close failed (non-fatal): %s", _ws_stop_err)


def get_price(pair: str) -> Optional[dict]:
    """Return the latest tick for `pair`, or None if unavailable / stale."""
    with _lock:
        entry = _prices.get(pair)
    if entry and (time.time() - entry["timestamp"]) < _STALE_THRESHOLD:
        return entry
    return None


def get_all_prices() -> dict[str, dict]:
    """Return all non-stale live prices."""
    now = time.time()
    with _lock:
        return {
            p: dict(v)
            for p, v in _prices.items()
            if (now - v["timestamp"]) < _STALE_THRESHOLD
        }


def get_status() -> dict:
    """Return connection status dict (safe copy)."""
    with _lock:
        return dict(_status)


def is_stale(pair: str) -> bool:
    """True if no fresh tick received for `pair` within _STALE_THRESHOLD seconds."""
    return get_price(pair) is None


# ── Heartbeat Watchdog ────────────────────────────────────────
_watchdog_thread: Optional[threading.Thread] = None
_watchdog_running = False


def _watchdog_loop(pairs: list[str]) -> None:
    """
    Background thread that monitors WebSocket message recency.
    If no message has been received in _WATCHDOG_TIMEOUT seconds, forces a
    full reconnect by closing the current socket (the _run_loop will restart it).

    This provides a second layer of resilience beyond the built-in reconnect:
    the WS library may consider the connection "open" while messages have silently stopped
    (e.g. OKX server-side issue). The watchdog catches this silent-stale state.
    Research: 99.99% uptime requires detecting silent feed failures, not just disconnects.
    """
    global _watchdog_running
    while _watchdog_running:
        time.sleep(_WATCHDOG_INTERVAL)
        if not _watchdog_running:
            break
        with _lock:
            last_msg = _status.get("last_message_at")
            connected = _status.get("connected", False)
        if connected and last_msg is not None:
            elapsed = time.time() - last_msg
            if elapsed > _WATCHDOG_TIMEOUT:
                logger.warning(
                    "[WS-Watchdog] No message in %.0fs (threshold=%ds) — forcing reconnect",
                    elapsed, _WATCHDOG_TIMEOUT,
                )
                with _lock:
                    ws_to_close = _ws_app
                if ws_to_close:
                    try:
                        ws_to_close.close()
                    except Exception as _wd_close_err:
                        logger.debug("[WS] watchdog reconnect close failed (non-fatal): %s", _wd_close_err)


def _start_watchdog(pairs: list[str]) -> None:
    """Start the heartbeat watchdog thread (idempotent)."""
    global _watchdog_thread, _watchdog_running
    if _watchdog_thread and _watchdog_thread.is_alive():
        return
    _watchdog_running = True
    _watchdog_thread = threading.Thread(
        target=_watchdog_loop,
        args=(pairs,),
        daemon=True,
        name="ws-watchdog",
    )
    _watchdog_thread.start()
    logger.info("[WS-Watchdog] Started heartbeat monitor (check every %ds, timeout %ds)",
                _WATCHDOG_INTERVAL, _WATCHDOG_TIMEOUT)
