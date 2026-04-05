"""
arbitrage.py — Cross-exchange spot + funding-rate arbitrage scanner.

Spot arb:
  • Fetches spot bid/ask from OKX, KuCoin, Kraken, Gate.io in parallel
  • Computes best gross spread (%) between cheapest ask and highest bid
  • Subtracts round-trip taker fees
  • Flags NET_SPREAD >= MIN_NET_SPREAD_PCT as OPPORTUNITY, >= 0 as MARGINAL

Funding-rate carry arb:
  • Delegates to data_feeds.get_carry_trade_opportunities() (already implemented)
  • Logs STRONG_CARRY / CARRY signals to DB

Results persisted to SQLite arb_opportunities table via database.log_arb_opportunity().
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import requests

# Module-level session for TCP connection reuse across all exchange fetches
_SESSION = requests.Session()

import database as _db
import data_feeds as _df

logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────────────────────
# Round-trip taker fees per exchange (buy taker + sell taker)
EXCHANGE_FEES: dict[str, dict] = {
    "OKX":     {"maker": 0.0008, "taker": 0.0010},
    "KuCoin":  {"maker": 0.0006, "taker": 0.0010},
    "Kraken":  {"maker": 0.0016, "taker": 0.0026},
    "Gate.io": {"maker": 0.0002, "taker": 0.0004},
}

# Minimum net spread (%) to flag as OPPORTUNITY (default 0.10%)
MIN_NET_SPREAD_PCT: float = 0.10

# HTTP timeout per exchange fetch (seconds)
_TIMEOUT: int = 6

# Spot price cache TTL (seconds)
_CACHE_TTL: int = 15

# ─── Thread-safe price cache ───────────────────────────────────────────────────
_spot_cache: dict = {}          # {pair: {"OKX": {bid,ask,price}, ..., "_ts": float}}
_cache_lock = threading.Lock()

# ─── Exchange price fetchers ───────────────────────────────────────────────────

def _fetch_okx_spot(pair: str) -> Optional[dict]:
    """Return {bid, ask, price} from OKX spot ticker or None on failure."""
    try:
        symbol = pair.replace("/", "-")   # BTC/USDT → BTC-USDT
        r = _SESSION.get(
            f"https://www.okx.com/api/v5/market/ticker?instId={symbol}",
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            logger.debug("OKX spot %s HTTP %s", pair, r.status_code)
            return None
        items = r.json().get("data", [])
        if not items:
            return None
        d = items[0]
        bid = float(d.get("bidPx") or 0)
        ask = float(d.get("askPx") or 0)
        if not bid or not ask:
            return None
        return {"bid": bid, "ask": ask, "price": (bid + ask) / 2}
    except Exception as e:
        logger.debug("OKX spot %s: %s", pair, e)
        return None


def _fetch_kucoin_spot(pair: str) -> Optional[dict]:
    """Return {bid, ask, price} from KuCoin spot level-1 orderbook or None."""
    try:
        symbol = pair.replace("/", "-")   # BTC/USDT → BTC-USDT
        r = _SESSION.get(
            f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}",
            timeout=_TIMEOUT,
        )
        if r.status_code == 429:
            logger.warning("KuCoin spot %s: rate limited (429)", pair)
            return None
        if r.status_code != 200:
            logger.debug("KuCoin spot %s HTTP %s", pair, r.status_code)
            return None
        d = (r.json().get("data") or {})
        bid = float(d.get("bestBid") or 0)
        ask = float(d.get("bestAsk") or 0)
        if not bid or not ask:
            return None
        return {"bid": bid, "ask": ask, "price": (bid + ask) / 2}
    except Exception as e:
        logger.debug("KuCoin spot %s: %s", pair, e)
        return None


# Kraken symbol map — only pairs available on Kraken spot
_KRAKEN_MAP: dict[str, str] = {
    "BTC/USDT":   "XBTUSDT",
    "ETH/USDT":   "ETHUSDT",
    "SOL/USDT":   "SOLUSDT",
    "ADA/USDT":   "ADAUSDT",
    "DOGE/USDT":  "XDGUSDT",
    "AVAX/USDT":  "AVAXUSDT",
    "DOT/USDT":   "DOTUSDT",
    "LINK/USDT":  "LINKUSDT",
    "XRP/USDT":   "XRPUSDT",
    "MATIC/USDT": "MATICUSDT",
    "LTC/USDT":   "LTCUSDT",
    "UNI/USDT":   "UNIUSDT",
}


def _fetch_kraken_spot(pair: str) -> Optional[dict]:
    """Return {bid, ask, price} from Kraken REST ticker or None."""
    try:
        k_pair = _KRAKEN_MAP.get(pair)
        if not k_pair:
            return None
        r = _SESSION.get(
            f"https://api.kraken.com/0/public/Ticker?pair={k_pair}",
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            logger.debug("Kraken spot %s HTTP %s", pair, r.status_code)
            return None
        result = r.json().get("result", {})
        if not result:
            return None
        ticker  = next(iter(result.values()))
        _b_list = ticker.get("b", [])
        _a_list = ticker.get("a", [])
        if not _b_list or not _a_list:
            return None
        bid = float(_b_list[0])
        ask = float(_a_list[0])
        return {"bid": bid, "ask": ask, "price": (bid + ask) / 2}
    except Exception as e:
        logger.debug("Kraken spot %s: %s", pair, e)
        return None


def _fetch_gateio_spot(pair: str) -> Optional[dict]:
    """Return {bid, ask, price} from Gate.io spot ticker or None."""
    try:
        symbol = pair.replace("/", "_")   # BTC/USDT → BTC_USDT
        r = _SESSION.get(
            f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={symbol}",
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            logger.debug("Gate.io spot %s HTTP %s", pair, r.status_code)
            return None
        data = r.json()
        if not data:
            return None
        d = data[0]
        bid = float(d.get("highest_bid") or 0)
        ask = float(d.get("lowest_ask") or 0)
        if not bid or not ask:
            return None
        return {"bid": bid, "ask": ask, "price": (bid + ask) / 2}
    except Exception as e:
        logger.debug("Gate.io spot %s: %s", pair, e)
        return None


def _fetch_htx_spot(pair: str) -> Optional[dict]:
    """Return {bid, ask, price} from HTX (formerly Huobi) REST ticker or None."""
    try:
        symbol = pair.replace("/", "").lower()   # BTC/USDT → btcusdt
        r = _SESSION.get(
            f"https://api.huobi.pro/market/detail/merged?symbol={symbol}",
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            logger.debug("HTX spot %s HTTP %s", pair, r.status_code)
            return None
        tick = r.json().get("tick", {})
        bid = float((tick.get("bid") or [0])[0])
        ask = float((tick.get("ask") or [0])[0])
        if not bid or not ask:
            return None
        return {"bid": bid, "ask": ask, "price": (bid + ask) / 2}
    except Exception as e:
        logger.debug("HTX spot %s: %s", pair, e)
        return None


def _fetch_bitstamp_spot(pair: str) -> Optional[dict]:
    """Return {bid, ask, price} from Bitstamp ticker or None."""
    try:
        # Bitstamp uses lowercase with no separator: BTC/USD → btcusd
        # For USDT pairs, use the USD proxy: BTC/USDT → btcusd
        base, quote = pair.split("/")
        q = "usd" if quote.upper() == "USDT" else quote.lower()
        symbol = f"{base.lower()}{q}"
        r = _SESSION.get(
            f"https://www.bitstamp.net/api/v2/ticker/{symbol}/",
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            logger.debug("Bitstamp spot %s HTTP %s", pair, r.status_code)
            return None
        d = r.json()
        bid = float(d.get("bid") or 0)
        ask = float(d.get("ask") or 0)
        if not bid or not ask:
            return None
        return {"bid": bid, "ask": ask, "price": (bid + ask) / 2}
    except Exception as e:
        logger.debug("Bitstamp spot %s: %s", pair, e)
        return None


def _fetch_bitget_spot(pair: str) -> Optional[dict]:
    """Return {bid, ask, price} from Bitget REST ticker or None."""
    try:
        symbol = pair.replace("/", "")   # BTC/USDT → BTCUSDT
        r = _SESSION.get(
            f"https://api.bitget.com/api/v2/spot/market/tickers?symbol={symbol}SPBL",
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            logger.debug("Bitget spot %s HTTP %s", pair, r.status_code)
            return None
        data = (r.json().get("data") or [])
        if not data:
            return None
        d = data[0]
        bid = float(d.get("bidPr") or 0)
        ask = float(d.get("askPr") or 0)
        if not bid or not ask:
            return None
        return {"bid": bid, "ask": ask, "price": (bid + ask) / 2}
    except Exception as e:
        logger.debug("Bitget spot %s: %s", pair, e)
        return None


_FETCHERS: dict = {
    "OKX":      _fetch_okx_spot,
    "KuCoin":   _fetch_kucoin_spot,
    "Kraken":   _fetch_kraken_spot,
    "Gate.io":  _fetch_gateio_spot,
    # New CeFi exchanges (#41)
    "HTX":      _fetch_htx_spot,
    "Bitstamp": _fetch_bitstamp_spot,
    "Bitget":   _fetch_bitget_spot,
}

EXCHANGE_FEES.update({
    "HTX":      {"maker": 0.0002, "taker": 0.0002},
    "Bitstamp": {"maker": 0.0030, "taker": 0.0040},
    "Bitget":   {"maker": 0.0002, "taker": 0.0006},
})


# ─── Price aggregator ─────────────────────────────────────────────────────────

def get_spot_prices(pair: str) -> dict[str, dict]:
    """
    Return {exchange: {bid, ask, price}} for all reachable exchanges.
    Results cached for _CACHE_TTL seconds.
    """
    now = time.time()
    with _cache_lock:
        cached = _spot_cache.get(pair, {})
        if cached.get("_ts", 0) + _CACHE_TTL > now:
            return {k: v for k, v in cached.items() if k != "_ts"}

    results: dict = {}
    lock = threading.Lock()

    def _fetch_and_store(name: str, fn):
        r = fn(pair)
        if r:
            with lock:
                results[name] = r

    threads = [
        threading.Thread(target=_fetch_and_store, args=(name, fn), daemon=True)
        for name, fn in _FETCHERS.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_TIMEOUT + 1)

    # Snapshot results before caching — late-arriving threads could write after
    # the cache dict is captured, producing a corrupted cached entry.
    with _cache_lock:
        results_snapshot = dict(results)
        _spot_cache[pair] = {**results_snapshot, "_ts": now}

    return results_snapshot


# ─── Spread calculator ────────────────────────────────────────────────────────

def compute_spot_spread(pair: str) -> dict:
    """
    Compute best cross-exchange spot arb opportunity for one pair.

    Strategy: buy at the cheapest ask, sell at the highest bid on a
    different exchange.  Net spread = gross spread − round-trip taker fees.

    Returns dict with keys:
      pair, buy_exchange, sell_exchange, buy_price, sell_price,
      gross_spread_pct, fees_pct, net_spread_pct, signal,
      prices {exchange: mid}, n_exchanges
    """
    prices = get_spot_prices(pair)

    _empty = {
        "pair": pair,
        "buy_exchange": None, "sell_exchange": None,
        "buy_price": None,    "sell_price": None,
        "gross_spread_pct": 0.0, "fees_pct": 0.0, "net_spread_pct": 0.0,
        "signal": "NO_ARB",
        "prices": {k: v["price"] for k, v in prices.items()},
        "n_exchanges": len(prices),
    }

    if len(prices) < 2:
        return _empty

    # Enumerate all distinct (buy_ex, sell_ex) pairs, pick best net spread
    best_net = float("-inf")
    best_buy_ex = best_sell_ex = None

    exchanges = list(prices.keys())
    for buy_ex in exchanges:  # BUG-R17: removed dead enumerate — index i was never used
        for sell_ex in exchanges:
            if buy_ex == sell_ex:
                continue
            buy_p  = prices[buy_ex]["ask"]
            sell_p = prices[sell_ex]["bid"]
            if buy_p <= 0 or sell_p <= buy_p:
                continue
            gross = (sell_p - buy_p) / buy_p * 100
            fees  = (
                EXCHANGE_FEES.get(buy_ex,  {}).get("taker", 0.001) +
                EXCHANGE_FEES.get(sell_ex, {}).get("taker", 0.001)
            ) * 100
            net = gross - fees
            if net > best_net:
                best_net = net
                best_buy_ex, best_sell_ex = buy_ex, sell_ex

    if best_buy_ex is None:
        return _empty

    buy_price    = prices[best_buy_ex]["ask"]
    sell_price   = prices[best_sell_ex]["bid"]
    gross_spread = (sell_price - buy_price) / buy_price * 100
    fees_pct     = (
        EXCHANGE_FEES.get(best_buy_ex,  {}).get("taker", 0.001) +
        EXCHANGE_FEES.get(best_sell_ex, {}).get("taker", 0.001)
    ) * 100
    net_spread   = gross_spread - fees_pct

    if net_spread >= MIN_NET_SPREAD_PCT:
        signal = "OPPORTUNITY"
    elif net_spread >= 0:
        signal = "MARGINAL"
    else:
        signal = "NO_ARB"

    return {
        "pair":             pair,
        "buy_exchange":     best_buy_ex,
        "sell_exchange":    best_sell_ex,
        "buy_price":        round(buy_price,    8),
        "sell_price":       round(sell_price,   8),
        "gross_spread_pct": round(gross_spread, 4),
        "fees_pct":         round(fees_pct,     4),
        "net_spread_pct":   round(net_spread,   4),
        "signal":           signal,
        "prices":           {k: v["price"] for k, v in prices.items()},
        "n_exchanges":      len(prices),
    }


# ─── Scanners ─────────────────────────────────────────────────────────────────

def scan_spot_arb(pairs: list) -> list:
    """
    Parallel spot-arb scan across all pairs.
    Logs OPPORTUNITY results to DB.  Returns list sorted by net_spread_pct desc.
    """
    results: list = []
    lock = threading.Lock()

    def _worker(pair: str):
        r = compute_spot_spread(pair)
        with lock:
            results.append(r)
        if r["signal"] == "OPPORTUNITY":
            _db.log_arb_opportunity(
                pair=pair,
                arb_type="SPOT",
                buy_exchange=r["buy_exchange"] or "",
                sell_exchange=r["sell_exchange"] or "",
                gross_spread_pct=r["gross_spread_pct"],
                net_spread_pct=r["net_spread_pct"],
                buy_price=r["buy_price"],
                sell_price=r["sell_price"],
                signal=r["signal"],
            )

    threads = [
        threading.Thread(target=_worker, args=(pair,), daemon=True)
        for pair in pairs
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    results.sort(key=lambda x: x["net_spread_pct"], reverse=True)
    return results


def scan_funding_arb(pairs: list) -> list:
    """
    Funding-rate carry trade scan.
    Uses data_feeds.get_carry_trade_opportunities().
    Logs STRONG_CARRY / CARRY results to DB.
    Returns list sorted by annualized_yield desc.
    """
    # ARB-05: guard against None return from data_feeds on error
    opportunities = _df.get_carry_trade_opportunities(pairs) or []
    for opp in opportunities:
        ann_yield = opp.get("annualized_yield", 0)
        sig = "STRONG_CARRY" if ann_yield >= 50 else "CARRY"
        _db.log_arb_opportunity(
            pair=opp.get("pair", ""),
            arb_type="FUNDING",
            buy_exchange=opp.get("exchange", ""),
            sell_exchange="SPOT",
            gross_spread_pct=abs(opp.get("funding_rate_pct", 0)),
            net_spread_pct=ann_yield,
            buy_price=None,
            sell_price=None,
            signal=sig,
        )
    return opportunities


def scan_all_arb(pairs: list) -> dict:
    """
    Full arbitrage scan: spot + funding-rate carry.
    Returns {"spot": [...], "funding": [...], "timestamp": str}.
    """
    spot_results    = scan_spot_arb(pairs)
    funding_results = scan_funding_arb(pairs)
    return {
        "spot":      spot_results,
        "funding":   funding_results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
