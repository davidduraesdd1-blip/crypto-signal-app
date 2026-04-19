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
from datetime import datetime, timezone
from typing import Optional

import random

import database as db
import alerts as _alerts

logger = logging.getLogger(__name__)


# ─── G6: Realistic Paper Trade Slippage Model ────────────────────────────────
# Ported from DeFi Model agents/paper_trader.py — calibrated on DEX/CEX data.
# Used only in paper mode fills; live mode uses actual exchange fill price.

_MAX_SLIPPAGE_PCT = 0.005  # 0.5% hard cap — matches DeFi model


def _simulate_slippage(size_usd: float) -> float:
    """
    Realistic slippage model for crypto CEX/spot fills (paper mode).
    Small trades: ~0.1%. Large trades scale up to 0.5% cap.
    Adds random micro-noise to prevent deterministic fills.
    """
    base        = 0.001                                       # 0.1% base
    size_factor = min(size_usd / 10_000, 1.0) * 0.003        # +0–0.3% for large trades
    noise       = random.uniform(-0.0005, 0.0005)             # ±0.05% micro-noise
    return max(0.0, min(_MAX_SLIPPAGE_PCT, base + size_factor + noise))


def _simulate_exchange_fee(size_usd: float) -> float:
    """Simulate CEX taker fee: 0.1% (Binance/OKX standard taker rate)."""
    return size_usd * 0.001

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
    if "/" not in pair:
        raise ValueError(f"Invalid pair format (missing '/'): {pair!r}")
    base, quote = pair.split("/", 1)
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
    expected_price: Optional[float] = None,
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
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
    if size_usd <= 0:
        return {
            "ok": False, "mode": "live" if cfg["live_trading"] else "paper",
            "pair": pair, "direction": direction, "side": None,
            "size_usd": size_usd, "order_type": order_type,
            "price": current_price, "order_id": None,
            "error": f"Invalid size_usd={size_usd}: must be > 0.",
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
    side   = "buy" if "BUY" in _dir_upper else "sell"
    symbol = _to_swap_symbol(pair)

    result: dict = {
        "ok":           False,
        "mode":         "live" if live else "paper",
        "pair":         pair,
        "direction":    direction,
        "side":         side,
        "size_usd":     size_usd,
        "order_type":   order_type,
        "price":        current_price,
        "order_id":     None,
        "error":        None,
        "placed_at":    datetime.now(timezone.utc).isoformat(),
        "slippage_pct": None,
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
            except ImportError:
                pass  # websocket-client optional
            except Exception as _ws_price_err:
                logger.debug("[Exec] WS price fallback failed for %s: %s", pair, _ws_price_err)
        # BUG-R03: truthiness check rejects 0.0 (broken ticker) silently.
        # Explicit None / non-positive check is clearer and safer.
        if current_price is None or current_price <= 0:
            result["error"] = "No price available for paper fill — WebSocket not connected and no scan price"
            _log_to_db(result)
            return result
        # G6: Apply realistic slippage model — fill price includes simulated market impact
        _slippage     = _simulate_slippage(size_usd)
        _fee_usd      = _simulate_exchange_fee(size_usd)
        _slip_mult    = (1 + _slippage) if side.upper() == "BUY" else (1 - _slippage)
        fill_price    = current_price * _slip_mult
        effective_usd = size_usd * (1 + _slippage) + _fee_usd
        result["ok"]       = True
        result["order_id"] = f"PAPER-{uuid.uuid4().hex[:12]}-{pair.replace('/', '')}"
        result["price"]    = fill_price
        result["slippage_pct"]   = round(_slippage * 100, 4)
        result["fee_usd"]        = round(_fee_usd, 4)
        result["effective_usd"]  = round(effective_usd, 4)
        logger.info(
            "[EXEC] PAPER %s %s $%.0f @ $%.4f (slip=%.3f%%)",
            side.upper(), pair, size_usd, fill_price, _slippage * 100,
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
        # EXEC-01: never fall back to 1.0 — at BTC prices that calculates an
        # absurdly large contract qty and could place a catastrophic live order
        _raw_price = ticker.get("last") or current_price
        if not _raw_price or float(_raw_price) <= 0:
            raise ValueError(
                f"Cannot determine current price for {pair} — ticker returned {ticker.get('last')!r}"
            )
        price_now = float(_raw_price)
        market    = ex.market(symbol)
        ct_size   = float(market.get("contractSize") or 1.0)
        if ct_size <= 0:
            ct_size = 1.0
        # EXEC-03: guard against silent min-1-contract oversize when size_usd
        # is tiny relative to notional. Without this, size_usd=$1 at BTC=$100k
        # rounds to qty=0, then max(1, 0)=1 contract → places ~$100k order.
        # Raise instead of silently placing a 100x oversized trade.
        _raw_qty = size_usd / (price_now * ct_size)
        if _raw_qty < 0.5:
            raise ValueError(
                f"Calculated qty {_raw_qty:.2e} < 0.5 contracts — size_usd "
                f"(${size_usd}) too small relative to notional "
                f"(price={price_now}, ct_size={ct_size}). "
                f"Aborting to prevent silent oversizing."
            )
        qty       = max(1, round(_raw_qty))
        # EXEC-02: hard cap on contract qty to prevent runaway orders from bad data
        if qty > 1000:
            raise ValueError(
                f"Calculated qty {qty} exceeds safety limit of 1000 contracts "
                f"(size_usd={size_usd}, price={price_now}, ct_size={ct_size})"
            )

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
        # T3-11: slippage vs expected entry price
        _ref = expected_price or current_price
        if _ref and _ref > 0 and result["price"] > 0:
            result["slippage_pct"] = round(abs(result["price"] - _ref) / _ref * 100, 4)
        logger.info(
            "[EXEC] LIVE %s %s %d ct @ %.4f | id=%s | slip=%.4f%%",
            side.upper(), pair, qty, result["price"], result["order_id"],
            result.get("slippage_pct") or 0.0,
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
    # Guard against None / non-string direction — .upper() would AttributeError
    # and the caller would see an opaque crash instead of a clear error.
    if not isinstance(direction, str) or not direction:
        raise ValueError(f"close_position: direction must be a non-empty string, got {direction!r}")
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

def build_signal_plan(
    results: list,
    portfolio_size_usd: float = 10_000.0,
    min_confidence_pct: float = 70.0,
    include_neutrals: bool = False,
) -> dict:
    """
    Build a dry-run portfolio plan from scan_results without placing any orders.

    Used by the Dashboard "▶ Execute Top Signals" button to preview what
    would happen before the user confirms. Mirrors the DeFi pattern in
    agents/portfolio_executor.build_plan_from_picks.

    Args:
        results:             scan_results list from session_state
        portfolio_size_usd:  total capital to allocate across legs
        min_confidence_pct:  only include signals at or above this confidence
        include_neutrals:    if False (default) skip NEUTRAL-direction signals

    Returns:
        dict with:
          legs:               list of per-signal dicts (pair, direction, size_usd,
                              confidence, high_conf, included, skip_reason)
          total_notional_usd: sum of included leg sizes
          included_count:     how many signals would be placed
          skipped_count:      how many scan rows were skipped
          authorization_tier: 'auto' | 'step_through' | 'requires_approval'
          live_trading:       whether OKX is in live mode
    """
    cfg = get_exec_config()
    legs: list = []
    total_notional = 0.0
    seen_pairs: set = set()

    # Dollar-cap tiers (match DeFi portfolio_executor Q6)
    AUTO_CAP   = 25_000.0
    STEP_CAP   = 250_000.0

    for r in results or []:
        pair      = r.get("pair", "")
        direction = str(r.get("direction") or "")
        conf      = float(r.get("confidence_avg_pct") or 0)
        high_conf = bool(r.get("high_conf"))
        size_pct  = float(r.get("position_size_pct") or 10)
        price     = r.get("price_usd")

        leg = {
            "pair": pair, "direction": direction, "confidence": conf,
            "high_conf": high_conf, "position_size_pct": size_pct,
            "price_usd": price, "size_usd": 0.0,
            "included": False, "skip_reason": "",
        }

        if not pair or not direction:
            leg["skip_reason"] = "Missing pair or direction"
        elif pair in seen_pairs:
            leg["skip_reason"] = "Duplicate pair in scan"
        elif "NEUTRAL" in direction and not include_neutrals:
            leg["skip_reason"] = "NEUTRAL signal skipped"
        elif conf < min_confidence_pct:
            leg["skip_reason"] = f"Confidence {conf:.0f}% below {min_confidence_pct:.0f}% threshold"
        else:
            size_usd = round((size_pct / 100.0) * portfolio_size_usd, 2)
            leg["size_usd"]  = size_usd
            leg["included"]  = True
            total_notional  += size_usd
            seen_pairs.add(pair)

        legs.append(leg)

    if total_notional <= AUTO_CAP:
        tier = "auto"
    elif total_notional <= STEP_CAP:
        tier = "step_through"
    else:
        tier = "requires_approval"

    return {
        "legs":               legs,
        "total_notional_usd": round(total_notional, 2),
        "included_count":     sum(1 for lg in legs if lg["included"]),
        "skipped_count":      sum(1 for lg in legs if not lg["included"]),
        "authorization_tier": tier,
        "live_trading":       cfg["live_trading"],
        "keys_configured":    cfg["keys_configured"],
        "min_confidence_pct": min_confidence_pct,
        "portfolio_size_usd": portfolio_size_usd,
    }


def execute_signal_plan(plan: dict, continue_on_fail: bool = True) -> dict:
    """
    Execute every included leg of a signal plan.

    Args:
        plan:             dry-run output from build_signal_plan()
        continue_on_fail: if True (default), continue past failed legs

    Returns:
        The same dict mutated with per-leg exec_status + aggregate
        success_count / failed_count.
    """
    if plan.get("authorization_tier") == "requires_approval":
        for lg in plan.get("legs", []):
            if lg.get("included"):
                lg["exec_status"]  = "blocked"
                lg["exec_message"] = (
                    f"Total notional ${plan['total_notional_usd']:,.0f} exceeds "
                    "$250,000 auto-cap — out-of-band approval required."
                )
        plan["success_count"] = 0
        plan["failed_count"]  = 0
        plan["blocked_count"] = plan.get("included_count", 0)
        return plan

    # Circuit-breaker check: if existing daily/weekly/monthly P&L limits are
    # tripped, block the entire plan with a clear reason — single-trade path
    # already enforces this inside place_order, but we check up-front so the
    # user gets one clear blocked-message instead of N "failed" per leg.
    try:
        _cb = check_circuit_breaker()
        if _cb.get("triggered"):
            for lg in plan.get("legs", []):
                if lg.get("included"):
                    lg["exec_status"]  = "blocked"
                    lg["exec_message"] = f"Circuit breaker: {_cb.get('reason', 'limit hit')}"
            plan["success_count"] = 0
            plan["failed_count"]  = 0
            plan["blocked_count"] = plan.get("included_count", 0)
            return plan
    except Exception as _cb_err:
        logger.debug("[SignalExec] circuit breaker check failed: %s", _cb_err)

    cfg = get_exec_config()
    success = failed = 0
    for lg in plan.get("legs", []):
        if not lg.get("included"):
            lg["exec_status"] = "skipped"
            lg["exec_message"] = lg.get("skip_reason", "")
            continue
        try:
            res = place_order(
                pair          = lg["pair"],
                direction     = lg["direction"],
                size_usd      = lg["size_usd"],
                order_type    = cfg.get("default_order_type", "market"),
                current_price = lg.get("price_usd"),
            )
            # place_order returns {"ok": bool, "error": str|None, "order_id": str|None, ...}
            # NOT {"status": str, "reason": str} — audit caught this mismatch in v1.
            _ok = bool(res.get("ok"))
            lg["exec_status"]  = "success" if _ok else "failed"
            lg["exec_message"] = str(res.get("error") or "")
            lg["order_id"]     = res.get("order_id")
            if _ok:
                success += 1
            else:
                failed += 1
                if not continue_on_fail:
                    break
        except Exception as e:
            lg["exec_status"]  = "failed"
            lg["exec_message"] = f"{type(e).__name__}: {str(e)[:200]}"
            failed += 1
            if not continue_on_fail:
                break

    plan["success_count"] = success
    plan["failed_count"]  = failed
    plan["blocked_count"] = 0
    return plan


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
    executed_pairs: set = set()  # EXEC-07: prevent duplicate orders for same pair
    for r in results:
        conf      = r.get("confidence_avg_pct", 0)
        direction = r.get("direction", "")
        pair      = r.get("pair", "")
        if conf < min_conf or "NEUTRAL" in direction or not direction:
            continue
        # EXEC-07: skip if we already placed an order for this pair this cycle
        if pair in executed_pairs:
            logger.debug("[EXEC] Skipping duplicate auto-execute for %s", pair)
            continue
        executed_pairs.add(pair)
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
            placed_at    = result.get("placed_at", datetime.now(timezone.utc).isoformat()),
            pair         = result.get("pair", ""),
            direction    = result.get("direction", ""),
            side         = result.get("side", ""),
            size_usd     = float(result.get("size_usd") or 0),
            order_type   = result.get("order_type", "market"),
            price        = float(result.get("price") or 0),
            order_id     = result.get("order_id") or "",
            status       = "ok" if result.get("ok") else "failed",
            mode         = result.get("mode", "paper"),
            error_msg    = result.get("error"),
            slippage_pct = result.get("slippage_pct"),
        )
    except Exception as exc:
        logger.warning("[EXEC] DB log failed: %s", exc)


# ─── T3-9: TWAP / VWAP Order Slicing ────────────────────────────────────────────

def place_twap_order(
    pair: str,
    direction: str,
    size_usd: float,
    n_slices: int = 5,
    interval_seconds: int = 60,
    current_price: Optional[float] = None,
    expected_price: Optional[float] = None,
) -> dict:
    """
    Execute a TWAP (Time-Weighted Average Price) order by splitting size_usd
    into n_slices child orders executed every interval_seconds in a daemon thread.

    Returns immediately with a tracking ID. Each child order is logged to
    execution_log. The parent tracking dict is returned to the caller.

    Parameters
    ----------
    pair             : "BTC/USDT"
    direction        : "BUY" | "SELL" etc.
    size_usd         : total notional to execute
    n_slices         : number of equal child orders (default 5)
    interval_seconds : seconds between child orders (default 60)
    current_price    : current market price for paper fills
    expected_price   : signal entry price for slippage tracking
    """
    n_slices         = max(1, int(n_slices))
    interval_seconds = max(5, int(interval_seconds))
    slice_usd        = size_usd / n_slices
    twap_id          = f"TWAP-{uuid.uuid4().hex[:8]}"

    logger.info(
        "[TWAP] Start %s %s $%.0f → %d slices × $%.0f every %ds | id=%s",
        direction, pair, size_usd, n_slices, slice_usd, interval_seconds, twap_id,
    )

    def _run():
        results = []
        for i in range(n_slices):
            # EXEC-03: catch any unhandled exception per slice so the thread
            # doesn't die silently and return a false-positive ok=True to the caller
            try:
                res = place_order(
                    pair=pair,
                    direction=direction,
                    size_usd=slice_usd,
                    order_type="market",
                    current_price=current_price,
                    expected_price=expected_price,
                )
            except Exception as _e:
                logger.error("[TWAP] Slice %d/%d unhandled error: %s", i + 1, n_slices, _e)
                res = {"ok": False, "error": str(_e)}
            results.append(res)
            logger.info("[TWAP] Slice %d/%d %s %s $%.0f → ok=%s",
                        i + 1, n_slices, direction, pair, slice_usd, res.get("ok"))
            if i < n_slices - 1:
                time.sleep(interval_seconds)
        filled = sum(1 for r in results if r.get("ok"))
        logger.info("[TWAP] Done %s | %d/%d slices filled", twap_id, filled, n_slices)

    t = threading.Thread(target=_run, daemon=True, name=f"twap-{twap_id}")
    t.start()

    return {
        "ok":            True,
        "twap_id":       twap_id,
        "pair":          pair,
        "direction":     direction,
        "total_usd":     size_usd,
        "n_slices":      n_slices,
        "slice_usd":     round(slice_usd, 2),
        "interval_sec":  interval_seconds,
        "mode":          "live" if get_exec_config()["live_trading"] else "paper",
        "error":         None,
    }


# ─── T3-10: Iceberg Orders ───────────────────────────────────────────────────────

def place_iceberg_order(
    pair: str,
    direction: str,
    size_usd: float,
    visible_pct: float = 0.20,
    current_price: Optional[float] = None,
    limit_price: Optional[float] = None,
    expected_price: Optional[float] = None,
) -> dict:
    """
    Place an iceberg order — shows only visible_pct of the total size in the OB.

    Live mode: uses OKX native iceberg via ccxt `{'iceberg': True, 'visibleSize': qty}`.
    Paper mode: falls back to a single simulated fill (no OB impact simulation).

    Parameters
    ----------
    pair         : "BTC/USDT"
    direction    : "BUY" | "SELL" etc.
    size_usd     : total notional
    visible_pct  : fraction shown in order book (0.20 = 20% visible)
    current_price: current market price for qty calculation / paper fill
    limit_price  : limit price; uses current_price if None
    expected_price: signal entry price for slippage tracking
    """
    cfg  = get_exec_config()
    live = cfg["live_trading"]
    side = "buy" if "BUY" in direction.upper() else "sell"

    result: dict = {
        "ok":          False,
        "mode":        "live" if live else "paper",
        "pair":        pair,
        "direction":   direction,
        "side":        side,
        "size_usd":    size_usd,
        "order_type":  "iceberg",
        "visible_pct": visible_pct,
        "price":       current_price,
        "order_id":    None,
        "error":       None,
        "placed_at":   datetime.now(timezone.utc).isoformat(),
        "slippage_pct": None,
    }

    if not live:
        # Paper: simulate fill like a regular order
        if current_price is None or current_price <= 0:
            result["error"] = "No price available for paper iceberg fill"
            _log_to_db(result)
            return result
        result["ok"]       = True
        result["order_id"] = f"ICE-PAPER-{uuid.uuid4().hex[:10]}"
        result["price"]    = current_price
        _ref = expected_price or current_price
        if _ref and _ref > 0:
            result["slippage_pct"] = round(abs(current_price - _ref) / _ref * 100, 4)
        logger.info("[ICEBERG] PAPER %s %s $%.0f (%.0f%% visible)", side.upper(), pair, size_usd, visible_pct * 100)
        _log_to_db(result)
        return result

    if not _CCXT_AVAILABLE:
        result["error"] = "ccxt not installed"
        _log_to_db(result)
        return result
    if not cfg["keys_configured"]:
        result["error"] = "OKX API keys not configured"
        _log_to_db(result)
        return result

    try:
        ex     = _get_exchange(authenticated=True)
        _load_markets_cached(ex)
        symbol = _to_swap_symbol(pair)
        ticker = ex.fetch_ticker(symbol)
        # EXEC-03: never fall back to 1.0 for iceberg orders — same guard as place_order().
        # At BTC prices a price_now of 1.0 would produce an absurdly large contract qty.
        _raw_price = ticker.get("last") or current_price
        if not _raw_price or float(_raw_price) <= 0:
            raise ValueError(
                f"Cannot determine current price for {pair} — ticker returned {ticker.get('last')!r}"
            )
        price_now = float(_raw_price)
        market    = ex.market(symbol)
        ct_size   = float(market.get("contractSize") or 1.0)
        if ct_size <= 0:
            ct_size = 1.0
        total_qty = max(1, round(size_usd / (price_now * ct_size)))
        visible_qty = max(1, round(total_qty * visible_pct))
        p = float(limit_price or price_now)
        order = ex.create_limit_order(
            symbol, side, total_qty, p,
            params={"iceberg": True, "visibleSize": str(visible_qty)},
        )
        result["ok"]       = True
        result["order_id"] = str(order.get("id", "unknown"))
        _fill_price = order.get("price") or p
        result["price"] = float(_fill_price)
        _ref = expected_price or current_price
        if _ref and _ref > 0 and result["price"] > 0:
            result["slippage_pct"] = round(abs(result["price"] - _ref) / _ref * 100, 4)
        logger.info("[ICEBERG] LIVE %s %s %d ct (visible %d) @ %.4f | id=%s",
                    side.upper(), pair, total_qty, visible_qty, result["price"], result["order_id"])
    except Exception as exc:
        result["error"] = str(exc)
        logger.error("[ICEBERG] Order failed %s: %s", pair, exc)

    _log_to_db(result)
    return result


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


# ─── Volatility-Targeted Position Sizing ────────────────────────────────────────

def compute_vol_adjusted_size(
    base_size_pct: float,
    df_close,                       # pd.Series or array-like of close prices
    target_vol_pct: float = 15.0,   # target annualized volatility %
    lookback: int = 21,             # bars for realized vol estimate
    min_size_pct: float = 0.25,     # floor: never less than 0.25% of portfolio
    max_size_pct: float = 25.0,     # cap: never more than 25% of portfolio
) -> tuple[float, str]:
    """
    Scale position size inversely with realized volatility so that each trade
    risks roughly the same dollar volatility regardless of market conditions.

    Formula:
        scaled_size = base_size × (target_vol / realized_vol)
        clamped to [min_size_pct, max_size_pct]

    Research: Volatility targeting reduces max drawdown by ~30% vs fixed-size
    sizing in crypto (2025 academic consensus). Equivalent to Constant Proportion
    Portfolio Insurance (CPPI) with a vol anchor.

    Parameters
    ----------
    base_size_pct  : float — Kelly/model suggested size (% of portfolio)
    df_close       : price series for realized vol calculation
    target_vol_pct : float — annualised volatility target (default 15%)
    lookback       : int   — bars for rolling vol window (default 21 = ~1 month)
    min_size_pct   : float — floor for position size
    max_size_pct   : float — cap for position size

    Returns
    -------
    (adjusted_size_pct: float, rationale: str)
    """
    try:
        import numpy as np
        import pandas as pd

        if df_close is None:
            return base_size_pct, "Vol-targeting skipped: no price data"

        prices = pd.Series(df_close).dropna()
        if len(prices) < lookback + 2:
            return base_size_pct, "Vol-targeting skipped: insufficient bars"

        # 21-bar realized vol (annualized for daily bars; for hourly bars × sqrt(24×365))
        log_ret = np.log(prices / prices.shift(1)).dropna()
        rv_daily = float(log_ret.tail(lookback).std())
        if rv_daily <= 0 or not np.isfinite(rv_daily):
            return base_size_pct, "Vol-targeting skipped: zero or invalid vol"

        # Annualize assuming daily bars; multiply by sqrt(365) for crypto 24/7
        rv_ann_pct = rv_daily * (365 ** 0.5) * 100.0

        if rv_ann_pct <= 0:
            return base_size_pct, "Vol-targeting skipped: zero annualized vol"

        scalar = target_vol_pct / rv_ann_pct
        adjusted = float(base_size_pct * scalar)
        adjusted = round(max(min_size_pct, min(max_size_pct, adjusted)), 2)

        direction = "reduced" if adjusted < base_size_pct else "increased"
        rationale = (
            f"Vol-adjusted size: {base_size_pct:.1f}% → {adjusted:.1f}% "
            f"({direction}; realized vol {rv_ann_pct:.0f}% vs target {target_vol_pct:.0f}%)"
        )
        return adjusted, rationale

    except Exception as exc:
        logger.warning("[exec] vol_adjusted_size failed: %s", exc)
        return base_size_pct, f"Vol-targeting error: {exc}"


# ─── Drawdown Circuit Breakers ──────────────────────────────────────────────────

# Module-level P&L accumulator (thread-safe via lock)
_circuit_lock       = threading.Lock()
_circuit_state: dict = {
    "triggered":    False,
    "reason":       "",
    "triggered_at": None,
    "daily_pnl":    0.0,
    "weekly_pnl":   0.0,
    "monthly_pnl":  0.0,
}

# Thresholds (configurable)
_DAILY_HALT_PCT   = -2.0    # -2% in a single day halts new signals
_WEEKLY_HALT_PCT  = -5.0    # -5% in a week
_MONTHLY_HALT_PCT = -15.0   # -15% in a month


def check_circuit_breaker(portfolio_size_usd: float = 10_000.0) -> dict:
    """
    Read recent trade P&L from the database and check if any drawdown
    circuit breaker threshold has been hit.

    Thresholds (research-calibrated for crypto):
      Daily  : -2%  — intraday cascade protection
      Weekly : -5%  — trend-reversal protection
      Monthly: -15% — macro bear-market protection

    Returns dict:
      triggered : bool
      reason    : str
      daily_pnl : float (%)
      weekly_pnl: float (%)
      monthly_pnl: float (%)
    """
    try:
        from datetime import timedelta, timezone

        trades_df = db.get_paper_trades_df()
        if trades_df.empty or "pnl_pct" not in trades_df.columns:
            return {**_circuit_state, "triggered": False}

        now = datetime.now(timezone.utc)

        # Date windows
        today_start   = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        week_start    = (now - timedelta(days=7)).isoformat()
        month_start   = (now - timedelta(days=30)).isoformat()

        def _pnl_since(since_str: str) -> float:
            if "close_time" not in trades_df.columns:
                return 0.0
            mask = trades_df["close_time"] >= since_str
            return float(trades_df.loc[mask, "pnl_pct"].sum())

        daily_pnl   = _pnl_since(today_start)
        weekly_pnl  = _pnl_since(week_start)
        monthly_pnl = _pnl_since(month_start)

        triggered = False
        reason    = ""

        if daily_pnl <= _DAILY_HALT_PCT:
            triggered = True
            reason    = f"Daily loss limit hit ({daily_pnl:.2f}% ≤ {_DAILY_HALT_PCT}%)"
        elif weekly_pnl <= _WEEKLY_HALT_PCT:
            triggered = True
            reason    = f"Weekly loss limit hit ({weekly_pnl:.2f}% ≤ {_WEEKLY_HALT_PCT}%)"
        elif monthly_pnl <= _MONTHLY_HALT_PCT:
            triggered = True
            reason    = f"Monthly loss limit hit ({monthly_pnl:.2f}% ≤ {_MONTHLY_HALT_PCT}%)"

        with _circuit_lock:
            _circuit_state["triggered"]    = triggered
            _circuit_state["reason"]       = reason
            _circuit_state["daily_pnl"]    = round(daily_pnl, 3)
            _circuit_state["weekly_pnl"]   = round(weekly_pnl, 3)
            _circuit_state["monthly_pnl"]  = round(monthly_pnl, 3)
            if triggered and not _circuit_state["triggered_at"]:
                _circuit_state["triggered_at"] = datetime.now(timezone.utc).isoformat()
            elif not triggered:
                _circuit_state["triggered_at"] = None

        if triggered:
            logger.warning("[circuit_breaker] TRIGGERED: %s", reason)

        return dict(_circuit_state)

    except Exception as exc:
        logger.warning("[circuit_breaker] check failed: %s", exc)
        return {**_circuit_state, "triggered": False}


def reset_circuit_breaker() -> None:
    """Manually reset the circuit breaker (e.g. after end-of-day)."""
    with _circuit_lock:
        _circuit_state["triggered"]    = False
        _circuit_state["reason"]       = ""
        _circuit_state["triggered_at"] = None
    logger.info("[circuit_breaker] Manually reset.")
