"""
whale_tracker.py — On-chain whale movement detection

Tracks large wallet movements across major chains using free public APIs:
  BTC : blockchain.info large-transaction endpoint
  ETH : Etherscan API (free tier, no key required for basic queries)
  SOL : Solscan public API
  BNB : BscScan API (free tier)
  XRP : XRPL public data API

Threshold: transactions > $500k USD equivalent are considered whale moves.
Signal   : WHALE_ACCUMULATION | WHALE_DISTRIBUTION | NEUTRAL
Cache    : 10-minute TTL per pair
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import requests
from data_feeds import _COINGECKO_LIMITER as _cg_limiter

# Module-level session for TCP connection reuse across all whale fetch calls
_SESSION = requests.Session()

logger = logging.getLogger(__name__)

# ─── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 600  # 10 minutes

_TIMEOUT = 8

# ─── Whale threshold (USD) ──────────────────────────────────────────────────────
WHALE_THRESHOLD_USD = 500_000  # $500k minimum to be considered whale activity
LARGE_WHALE_USD     = 5_000_000  # $5M+ = large whale

# ─── Chain/API routing ─────────────────────────────────────────────────────────
_PAIR_CHAIN: dict[str, str] = {
    "BTC/USDT":  "btc",
    "ETH/USDT":  "eth",
    "SOL/USDT":  "sol",
    "XRP/USDT":  "xrp",
    "BNB/USDT":  "bnb",
    "DOGE/USDT": "doge",
}

# ─── BTC via blockchain.info ────────────────────────────────────────────────────

def _fetch_btc_whales(price_usd: float) -> list[dict]:
    """
    Fetch largest recent BTC transactions from blockchain.info.
    Returns list of {amount_usd, direction, txid} dicts.
    """
    try:
        resp = _SESSION.get(
            "https://blockchain.info/unconfirmed-transactions?format=json",
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        txs = resp.json().get("txs", [])[:50]
        moves = []
        for tx in txs:
            out_btc = sum(o.get("value", 0) for o in (tx.get("out") or [])) / 1e8
            amount_usd = out_btc * price_usd
            if amount_usd >= WHALE_THRESHOLD_USD:
                # Classify: if tx has many outputs → distribution; few large → accumulation
                n_outputs = len(tx.get("out", []))
                direction = "distribution" if n_outputs > 5 else "accumulation"
                moves.append({
                    "amount_usd": round(amount_usd, 0),
                    "direction":  direction,
                    "txid":       tx.get("hash", "")[:16] + "...",
                })
        return moves
    except Exception as e:
        logger.debug("BTC whale fetch failed: %s", e)
        return []


# ─── ETH via Etherscan (free, limited rate) ─────────────────────────────────────

_ETH_TOKEN_CONTRACTS = {
    "ETH": None,   # native — use eth_getBlockByNumber approach
}

def _fetch_eth_whales(price_usd: float) -> list[dict]:
    """Fetch large recent ETH transactions from Etherscan public API."""
    try:
        # Get latest block number
        resp = _SESSION.get(
            "https://api.etherscan.io/v2/api",
            params={"chainid": 1, "module": "proxy", "action": "eth_blockNumber"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        # WHALE-01: use `or "0x0"` to handle JSON null (None) from Etherscan
        hex_block = resp.json().get("result") or "0x0"
        try:
            block_num = int(hex_block, 16)
        except (ValueError, TypeError):
            logger.debug("ETH whale: invalid block number hex %r", hex_block)
            return _estimate_eth_whale_activity(price_usd)

        # Fetch recent large txs via Etherscan v2 (multi-chain aware)
        resp2 = _SESSION.get(
            "https://api.etherscan.io/v2/api",
            params={
                "chainid":    1,
                "module":     "account",
                "action":     "txlist",
                "address":    "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",  # EF donation addr as proxy
                "startblock": max(0, block_num - 200),
                "endblock":   block_num,
                "sort":       "desc",
                "offset":     20,
                "page":       1,
            },
            timeout=_TIMEOUT,
        )
        # Etherscan may return rate-limit errors without key — graceful fallback
        data = resp2.json()
        if data.get("status") != "1":
            return _estimate_eth_whale_activity(price_usd)

        moves = []
        for tx in data.get("result", [])[:20]:
            try:
                raw_val = tx.get("value", "0") or "0"
                # Etherscan returns decimal wei strings; guard against hex or empty values
                val_eth = int(raw_val, 0) / 1e18 if str(raw_val).startswith("0x") else int(raw_val) / 1e18
            except (ValueError, TypeError):
                continue
            amount_usd = val_eth * price_usd
            if amount_usd >= WHALE_THRESHOLD_USD:
                n_internal = int(tx.get("methodId", "0x") != "0x")
                # Plain ETH transfer (methodId=="0x") → likely send-to-exchange = distribution
                # Contract call (methodId!="0x") → likely DEX buy / DeFi deposit = accumulation
                direction = "accumulation" if n_internal else "distribution"
                moves.append({
                    "amount_usd": round(amount_usd, 0),
                    "direction":  direction,
                    "txid":       tx.get("hash", "")[:16] + "...",
                })
        return moves
    except Exception as e:
        logger.debug("ETH whale fetch failed: %s", e)
        return []


def _estimate_eth_whale_activity(price_usd: float) -> list[dict]:
    """
    Fallback: estimate ETH whale activity from on-chain metrics proxy
    using the CoinGecko large-transaction volume approximation.
    """
    try:
        _cg_limiter.acquire()  # rate-limit CoinGecko: 0.4 req/s = 25 req/min free tier
        resp = _SESSION.get(
            "https://api.coingecko.com/api/v3/coins/ethereum",
            params={"localization": "false", "tickers": "false", "community_data": "false"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        mkt = data.get("market_data", {})
        vol_24h = mkt.get("total_volume", {}).get("usd", 0)
        # Very rough: if vol/mcap ratio is high → increased whale activity
        mcap = (mkt.get("market_cap") or {}).get("usd", 1) if isinstance(mkt.get("market_cap"), dict) else 1
        ratio = vol_24h / mcap if mcap else 0
        if ratio > 0.10:
            return [{"amount_usd": vol_24h * 0.01, "direction": "mixed", "txid": "estimated"}]
        return []
    except Exception:
        return []


# ─── SOL via Solscan ───────────────────────────────────────────────────────────

_SOL_WHALE_WALLETS = [
    "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # known Solana whale
    "HN7cABqLq46Es1jh92dQQisAq662SmxELLLsHHe4YWrH",  # Solana Foundation
]


def _fetch_sol_whales(price_usd: float) -> list[dict]:
    """Fetch recent large SOL transactions via Solscan public API."""
    try:
        resp = _SESSION.get(
            "https://public-api.solscan.io/transaction/last",
            params={"limit": 20},
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        txs = resp.json()
        if not isinstance(txs, list):
            return []
        moves = []
        for tx in txs[:20]:
            # SOL lamports → SOL
            fee = tx.get("fee", 0) / 1e9
            # Large transactions typically show in lamports transferred
            sol_amount = (tx.get("lamport") or 0) / 1e9
            amount_usd = sol_amount * price_usd
            if amount_usd >= WHALE_THRESHOLD_USD:
                moves.append({
                    "amount_usd": round(amount_usd, 0),
                    "direction":  "accumulation",  # hard to determine without full decode
                    "txid":       str(tx.get("txHash", ""))[:16] + "...",
                })
        return moves
    except Exception as e:
        logger.debug("SOL whale fetch failed: %s", e)
        return []


# ─── XRP via XRPL Data API ─────────────────────────────────────────────────────

def _fetch_xrp_whales(price_usd: float) -> list[dict]:
    """Fetch large XRP payments from the XRPL public data API."""
    try:
        resp = _SESSION.get(
            "https://data.ripple.com/v2/transactions",
            params={"type": "Payment", "result": "tesSUCCESS", "limit": 30, "descending": "true"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        txs = resp.json().get("transactions", [])
        moves = []
        for item in txs[:30]:
            tx = item.get("tx") or {}
            amt = tx.get("Amount", "0")
            if isinstance(amt, str):
                # XRP drops (1 XRP = 1,000,000 drops)
                # Use int(float()) to handle both "1000000" and "1000000.0" formats
                # WHALE-03: guard against empty string raising ValueError
                if not amt.strip():
                    continue
                xrp_amount = int(float(amt)) / 1e6
                amount_usd = xrp_amount * price_usd
                if amount_usd >= WHALE_THRESHOLD_USD:
                    moves.append({
                        "amount_usd": round(amount_usd, 0),
                        "direction":  "accumulation",
                        "txid":       tx.get("hash", "")[:16] + "...",
                    })
        return moves
    except Exception as e:
        logger.debug("XRP whale fetch failed: %s", e)
        return []


# ─── BNB via BscScan ───────────────────────────────────────────────────────────

def _fetch_bnb_whales(price_usd: float) -> list[dict]:
    """Fetch recent large BNB transactions from BscScan API."""
    try:
        resp = _SESSION.get(
            "https://api.bscscan.com/api",
            params={
                "module":  "proxy",
                "action":  "eth_getBlockByNumber",
                "tag":     "latest",
                "boolean": "true",
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        block = resp.json().get("result", {})
        txs = block.get("transactions", [])[:30]
        moves = []
        for tx in txs:
            # WHALE-02: use `or "0x0"` to handle None value (key exists with JSON null)
            val_hex = tx.get("value") or "0x0"
            try:
                val_bnb = int(val_hex, 16) / 1e18
            except ValueError:
                # BSCScan occasionally returns decimal strings instead of hex
                val_bnb = int(val_hex) / 1e18 if str(val_hex).lstrip("-").isdigit() else 0.0
            amount_usd = val_bnb * price_usd
            if amount_usd >= WHALE_THRESHOLD_USD:
                direction = "distribution" if len(tx.get("input", "0x")) > 10 else "accumulation"
                moves.append({
                    "amount_usd": round(amount_usd, 0),
                    "direction":  direction,
                    "txid":       tx.get("hash", "")[:16] + "...",
                })
        return moves
    except Exception as e:
        logger.debug("BNB whale fetch failed: %s", e)
        return []


# ─── DOGE via dogechain ─────────────────────────────────────────────────────────

def _fetch_doge_whales(price_usd: float) -> list[dict]:
    """Rough DOGE whale estimation via known rich list API."""
    try:
        resp = _SESSION.get(
            "https://dogechain.info/api/v1/transaction/recent",
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        txs = resp.json().get("transactions", [])[:20]
        moves = []
        for tx in txs:
            outputs = tx.get("outputs") or []
            doge_total = 0.0
            for o in outputs:
                try:
                    doge_total += float(o.get("value", 0) or 0)
                except (TypeError, ValueError):
                    pass
            amount_usd = doge_total * price_usd
            if amount_usd >= WHALE_THRESHOLD_USD:
                moves.append({
                    "amount_usd": round(amount_usd, 0),
                    "direction":  "mixed",
                    "txid":       tx.get("hash", "")[:16] + "...",
                })
        return moves
    except Exception as e:
        logger.debug("DOGE whale fetch failed: %s", e)
        return []


# ─── Signal synthesis ──────────────────────────────────────────────────────────

def _synthesize_signal(moves: list[dict]) -> dict:
    """Convert list of whale moves into a signal dict."""
    if not moves:
        return {
            "signal":            "NEUTRAL",
            "whale_count":       0,
            "large_whale_count": 0,
            "total_usd":         0.0,
            "accumulation":      0,
            "distribution":      0,
            "score":             0.0,
        }
    acc  = sum(1 for m in moves if m["direction"] == "accumulation")
    dist = sum(1 for m in moves if m["direction"] == "distribution")
    total_usd = sum(m["amount_usd"] for m in moves)
    large = sum(1 for m in moves if m["amount_usd"] >= LARGE_WHALE_USD)
    total = acc + dist or 1
    score = (acc - dist) / total
    if score > 0.3:
        signal = "WHALE_ACCUMULATION"
    elif score < -0.3:
        signal = "WHALE_DISTRIBUTION"
    else:
        signal = "NEUTRAL"
    return {
        "signal":            signal,
        "whale_count":       len(moves),
        "large_whale_count": large,
        "total_usd":         round(total_usd, 0),
        "accumulation":      acc,
        "distribution":      dist,
        "score":             round(score, 3),
    }


# ─── Public API ─────────────────────────────────────────────────────────────────

_NEUTRAL_RESULT = {
    "signal":            "NEUTRAL",
    "whale_count":       0,
    "large_whale_count": 0,
    "total_usd":         0.0,
    "accumulation":      0,
    "distribution":      0,
    "score":             0.0,
    "error":             None,
}


def get_whale_activity(pair: str, price_usd: float = 0.0) -> dict:
    """
    Fetch and score on-chain whale activity for a trading pair.

    Parameters
    ----------
    pair      : e.g. 'BTC/USDT'
    price_usd : current price used to convert amounts to USD

    Returns
    -------
    dict with keys:
      signal            : 'WHALE_ACCUMULATION' | 'WHALE_DISTRIBUTION' | 'NEUTRAL'
      whale_count       : number of whale transactions found
      large_whale_count : >$5M transactions
      total_usd         : total USD value of whale moves
      accumulation      : bullish whale txs
      distribution      : bearish whale txs
      score             : [-1, +1] accumulation vs distribution
    """
    now = time.time()
    with _cache_lock:
        cached = _cache.get(pair)
        if cached and now - cached.get("_ts", 0) < _CACHE_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    chain = _PAIR_CHAIN.get(pair, "")
    if not chain:
        result = {**_NEUTRAL_RESULT, "error": f"Unsupported chain for {pair}", "pair": pair}
        with _cache_lock:
            _cache[pair] = {**result, "_ts": now}
        return result

    if price_usd <= 0:
        # Attempt to get price from CoinGecko as fallback
        try:
            coin_id_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
                           "XRP": "ripple", "BNB": "binancecoin", "DOGE": "dogecoin"}
            coin_id = coin_id_map.get(pair.split("/")[0], "bitcoin")
            _cg_limiter.acquire()
            r = _SESSION.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
                timeout=_TIMEOUT,
            )
            fetched = r.json().get(coin_id, {}).get("usd")
            # WHALE-05: never fall back to 1.0 — for BTC that's ~$80k off and
            # causes every transaction to fail the whale threshold check
            price_usd = float(fetched) if fetched and float(fetched) > 0 else 0.0
        except Exception:
            price_usd = 0.0

    if price_usd == 0.0:
        # Cannot compute USD whale thresholds without a valid price — return neutral
        result = {**_NEUTRAL_RESULT, "error": "price_usd unavailable — whale USD thresholds cannot be computed"}
        result["pair"] = pair
        with _cache_lock:
            _cache[pair] = {**result, "_ts": now}
        return result

    moves: list[dict] = []
    try:
        if chain == "btc":
            moves = _fetch_btc_whales(price_usd)
        elif chain == "eth":
            moves = _fetch_eth_whales(price_usd)
        elif chain == "sol":
            moves = _fetch_sol_whales(price_usd)
        elif chain == "xrp":
            moves = _fetch_xrp_whales(price_usd)
        elif chain == "bnb":
            moves = _fetch_bnb_whales(price_usd)
        elif chain == "doge":
            moves = _fetch_doge_whales(price_usd)
    except Exception as e:
        logger.warning("Whale fetch exception for %s: %s", pair, e)

    result = _synthesize_signal(moves)
    result["error"] = None
    result["pair"]  = pair

    with _cache_lock:
        _cache[pair] = {**result, "_ts": now}

    return result


def get_whale_score_bias(pair: str, price_usd: float = 0.0) -> float:
    """
    Returns confidence score bias in points (-8 to +8) based on whale activity.
    WHALE_ACCUMULATION = +8, WHALE_DISTRIBUTION = -8, NEUTRAL = 0.
    Used as additive adjustment in calculate_signal_confidence().
    """
    try:
        data = get_whale_activity(pair, price_usd)
        sig = data.get("signal", "NEUTRAL")
        score = data.get("score", 0.0)
        if sig == "WHALE_ACCUMULATION":
            return round(min(score * 10.0, 8.0), 1)
        elif sig == "WHALE_DISTRIBUTION":
            return round(max(score * 10.0, -8.0), 1)
        return 0.0
    except Exception:
        return 0.0


def get_whale_batch(pairs: list[str], price_map: Optional[dict] = None) -> dict[str, dict]:
    """Fetch whale activity for multiple pairs concurrently."""
    from concurrent.futures import ThreadPoolExecutor
    if price_map is None:
        price_map = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pair: pool.submit(get_whale_activity, pair, price_map.get(pair, 0.0))
            for pair in pairs
        }
        # WHALE-08: catch per-pair exceptions so one failure doesn't abort the whole batch
        results = {}
        for pair, f in futures.items():
            try:
                results[pair] = f.result()
            except Exception as e:
                logger.warning("get_whale_batch failed for %s: %s", pair, e)
                results[pair] = {**_NEUTRAL_RESULT, "error": str(e), "pair": pair}
        return results
