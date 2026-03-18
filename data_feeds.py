"""
data_feeds.py — External data feed helpers for Crypto Signal Model v5.9.13
Fetches supplementary market data (funding rates, on-chain proxies, open interest)
from free public APIs. No API keys required.
"""
from __future__ import annotations

import requests
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

# ──────────────────────────────────────────────
# BINANCE FUTURES FUNDING RATES
# Public endpoint — no auth required
# ──────────────────────────────────────────────

_BINANCE_PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
_BYBIT_TICKERS_URL  = "https://api.bybit.com/v5/market/tickers"
_OKX_FUNDING_URL    = "https://www.okx.com/api/v5/public/funding-rate"
_OKX_TICKERS_URL    = "https://www.okx.com/api/v5/public/instruments"
_BINANCE_FUNDING_CACHE: dict = {}
_ONCHAIN_CACHE_LOCK  = threading.Lock()
_FUNDING_CACHE_LOCK  = threading.Lock()
_OI_CACHE_LOCK       = threading.Lock()
_CACHE_TTL_SECONDS = 300  # 5-minute cache


def _binance_symbol(pair: str) -> str:
    """Convert CCXT pair format (BTC/USDT) to Binance/Bybit futures symbol (BTCUSDT)."""
    return pair.replace("/", "")


def _okx_inst_id(pair: str) -> str:
    """Convert BTC/USDT → BTC-USDT-SWAP for OKX perpetuals."""
    if "/" not in pair:
        return f"{pair}-USDT-SWAP"
    base, quote = pair.split("/", 1)
    return f"{base}-{quote}-SWAP"


def _funding_signal(rate: float) -> str:
    """Positive funding = longs paying shorts = bearish. Negative = bullish."""
    if rate > 0.0003:   return "BEARISH"
    if rate < -0.0003:  return "BULLISH"
    return "NEUTRAL"


def _parse_binance_item(item: dict, now: float) -> dict | None:
    """Parse a Binance premiumIndex item into our standard format."""
    if "lastFundingRate" not in item:
        return None
    rate = float(item["lastFundingRate"])
    return {
        "funding_rate": rate,
        "funding_rate_pct": round(rate * 100, 4),
        "next_funding_time": int(item.get("nextFundingTime", 0)),
        "mark_price": float(item.get("markPrice", 0)),
        "signal": _funding_signal(rate),
        "source": "binance",
        "error": None,
        "_ts": now,
    }


def _parse_bybit_item(item: dict, now: float) -> dict | None:
    """Parse a Bybit linear ticker item into our standard format."""
    fr_str = item.get("fundingRate")
    if fr_str is None:
        return None
    rate = float(fr_str)
    return {
        "funding_rate": rate,
        "funding_rate_pct": round(rate * 100, 4),
        "next_funding_time": int(item.get("nextFundingTime", 0)),
        "mark_price": float(item.get("markPrice", 0)),
        "signal": _funding_signal(rate),
        "source": "bybit",
        "error": None,
        "_ts": now,
    }


def _empty_result(error: str, now: float) -> dict:
    return {
        "funding_rate": 0.0, "funding_rate_pct": 0.0,
        "next_funding_time": 0, "mark_price": 0.0,
        "signal": "N/A", "source": None, "error": error, "_ts": now,
    }


def _parse_okx_item(item: dict, now: float) -> dict | None:
    """Parse an OKX funding-rate response item."""
    fr_str = item.get("fundingRate")
    if fr_str is None:
        return None
    rate = float(fr_str)
    return {
        "funding_rate": rate,
        "funding_rate_pct": round(rate * 100, 4),
        "next_funding_time": int(item.get("nextFundingTime", 0)),
        "mark_price": 0.0,
        "signal": _funding_signal(rate),
        "source": "okx",
        "error": None,
        "_ts": now,
    }


def get_funding_rate(pair: str) -> dict:
    """
    Fetch the current funding rate for a pair.
    Priority: OKX (US-accessible) → Binance → Bybit.

    Returns dict with keys:
      - funding_rate_pct: float  (e.g. 0.01 for 0.01%)
      - signal: "BULLISH" | "BEARISH" | "NEUTRAL" | "N/A"
      - source: "okx" | "binance" | "bybit" | None
      - error: str | None
    """
    now = time.time()
    with _FUNDING_CACHE_LOCK:
        cached = _BINANCE_FUNDING_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _CACHE_TTL_SECONDS:
            return cached

    symbol = _binance_symbol(pair)
    inst_id = _okx_inst_id(pair)

    # 1. OKX (US-accessible, good coverage)
    try:
        resp = requests.get(_OKX_FUNDING_URL, params={"instId": inst_id}, timeout=6)
        if resp.status_code == 429:
            logging.warning(f"OKX funding rate: rate limited (429) for {pair}")
        elif resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            if items and data.get("code") == "0":
                parsed = _parse_okx_item(items[0], now)
                if parsed:
                    with _FUNDING_CACHE_LOCK:
                        _BINANCE_FUNDING_CACHE[pair] = parsed
                    return parsed
    except Exception as _e:
        logging.debug(f"OKX funding rate fetch error for {pair}: {_e}")

    # 2. Binance
    try:
        resp = requests.get(_BINANCE_PREMIUM_URL, params={"symbol": symbol}, timeout=6)
        if resp.status_code == 429:
            logging.warning(f"Binance funding rate: rate limited (429) for {pair}")
        elif resp.status_code == 200:
            data = resp.json()
            parsed = _parse_binance_item(data, now) if isinstance(data, dict) else None
            if parsed:
                with _FUNDING_CACHE_LOCK:
                    _BINANCE_FUNDING_CACHE[pair] = parsed
                return parsed
    except Exception as _e:
        logging.debug(f"Binance funding rate fetch error for {pair}: {_e}")

    # 3. Bybit
    try:
        resp = requests.get(_BYBIT_TICKERS_URL, params={"category": "linear", "symbol": symbol}, timeout=6)
        if resp.status_code == 429:
            logging.warning(f"Bybit funding rate: rate limited (429) for {pair}")
        elif resp.status_code == 200:
            data = resp.json()
            items = data.get("result", {}).get("list", [])
            if items:
                parsed = _parse_bybit_item(items[0], now)
                if parsed:
                    with _FUNDING_CACHE_LOCK:
                        _BINANCE_FUNDING_CACHE[pair] = parsed
                    return parsed
    except Exception as _e:
        logging.debug(f"Bybit funding rate fetch error for {pair}: {_e}")

    result = _empty_result("Funding N/A (spot pair or geo-blocked)", now)
    with _FUNDING_CACHE_LOCK:
        _BINANCE_FUNDING_CACHE[pair] = result
    return result


# ──────────────────────────────────────────────
# REAL ON-CHAIN METRICS via CoinGecko (free, no key)
# ──────────────────────────────────────────────

_ONCHAIN_CACHE: dict = {}
_ONCHAIN_TTL = 300  # 5-minute cache

_COIN_MAP = {
    'BTC/USDT': 'bitcoin',    'ETH/USDT': 'ethereum',   'SOL/USDT': 'solana',
    'XRP/USDT': 'ripple',     'DOGE/USDT': 'dogecoin',  'BNB/USDT': 'binancecoin',
    'ADA/USDT': 'cardano',    'AVAX/USDT': 'avalanche-2', 'MATIC/USDT': 'matic-network',
    'LINK/USDT': 'chainlink', 'LTC/USDT': 'litecoin',   'DOT/USDT': 'polkadot',
    'UNI/USDT': 'uniswap',   'ATOM/USDT': 'cosmos',    'FIL/USDT': 'filecoin',
    'NEAR/USDT': 'near',
}

_CG_BASE = "https://api.coingecko.com/api/v3"


def _fallback_onchain() -> dict:
    return {
        'sopr': 1.0, 'mvrv_z': 0.0, 'net_flow': 0.0,
        'whale_activity': False, 'source': 'fallback',
        'vol_mcap_ratio': 0.0, 'price_24h_pct': 0.0, 'price_200d_pct': 0.0,
    }


def get_onchain_metrics(pair: str) -> dict:
    """
    Real on-chain proxy metrics from CoinGecko free API.
    Returns same schema as the old simulated fetch_onchain_metrics() for compatibility.

    Fields:
      sopr          — SOPR proxy: 1 + 24h_price_change. >1 = profit-taking, <1 = capitulation.
      mvrv_z        — MVRV-Z proxy: 200d return scaled to MVRV-Z range.
      net_flow      — Exchange flow proxy: volume/mcap deviation scaled to ±400.
      whale_activity — True if volume > 10% of market cap (abnormal activity).
      vol_mcap_ratio — Raw volume/mcap ratio for display.
      price_24h_pct  — 24h price change %.
      price_200d_pct — 200-day price change %.
      source         — 'coingecko' | 'fallback'
    """
    now = time.time()
    with _ONCHAIN_CACHE_LOCK:
        cached = _ONCHAIN_CACHE.get(pair)
        if cached and (now - cached.get('_ts', 0)) < _ONCHAIN_TTL:
            return cached

    coin_id = _COIN_MAP.get(pair)
    if not coin_id:
        return _fallback_onchain()

    try:
        url = f"{_CG_BASE}/coins/{coin_id}"
        params = {
            'localization': 'false', 'tickers': 'false',
            'market_data': 'true', 'community_data': 'false',
            'developer_data': 'false', 'sparkline': 'false',
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 429:
            logging.warning(f"CoinGecko rate limited (429) for {pair} — using fallback")
            # BUG-M04: cache the fallback so we don't hammer CoinGecko on every call
            _fb = {**_fallback_onchain(), '_ts': now}
            with _ONCHAIN_CACHE_LOCK:
                _ONCHAIN_CACHE[pair] = _fb
            return _fb
        if resp.status_code != 200:
            _fb = {**_fallback_onchain(), '_ts': now}
            with _ONCHAIN_CACHE_LOCK:
                _ONCHAIN_CACHE[pair] = _fb
            return _fb

        md = resp.json().get('market_data', {})
        price_24h = md.get('price_change_percentage_24h') or 0.0
        price_200d = md.get('price_change_percentage_200d') or 0.0
        volume = (md.get('total_volume') or {}).get('usd') or 0.0
        mcap = (md.get('market_cap') or {}).get('usd') or 0.0

        # SOPR proxy: normalised 24h return, centred on 1.0
        sopr = round(max(0.85, min(1.15, 1.0 + price_24h / 100)), 3)

        # MVRV-Z proxy: 200d return scaled so +200% ≈ 3.5, -57% ≈ -1.0
        mvrv_z = round(max(-3.0, min(7.0, price_200d / 57.0)), 2)

        # Net-flow proxy: volume/mcap deviation scaled to ±400
        # BUG-RANGE-01: zero volume must be neutral (0), not extreme bearish (-400)
        vol_mcap = volume / mcap if mcap > 0 else 0.0
        net_flow = 0.0 if volume == 0 else round(max(-400.0, min(400.0, (vol_mcap - 0.05) * 8000)), 1)

        # Whale activity: volume > 10% of mcap signals unusual on-chain movement
        whale_activity = vol_mcap > 0.10

        result = {
            'sopr': sopr, 'mvrv_z': mvrv_z, 'net_flow': net_flow,
            'whale_activity': whale_activity, 'source': 'coingecko',
            'vol_mcap_ratio': round(vol_mcap, 4),
            'price_24h_pct': round(price_24h, 2),
            'price_200d_pct': round(price_200d, 2),
            '_ts': now,
        }
        with _ONCHAIN_CACHE_LOCK:
            _ONCHAIN_CACHE[pair] = result
        return result

    except Exception as e:
        logging.warning(f"CoinGecko onchain fetch failed for {pair}: {e}")
        _fb = {**_fallback_onchain(), '_ts': now}
        with _ONCHAIN_CACHE_LOCK:
            _ONCHAIN_CACHE[pair] = _fb
        return _fb


# ──────────────────────────────────────────────
# OPEN INTEREST via Bybit (free, no key, US-accessible)
# ──────────────────────────────────────────────

_OI_CACHE: dict = {}
_OI_TTL = 120  # 2-minute cache


def get_open_interest(pair: str) -> dict:
    """
    Fetch open interest from OKX (free, no key, US-accessible).
    OKX returns oiUsd directly so no mark-price conversion needed.
    Returns {'oi_usd': float, 'signal': str, 'error': str | None}
    signal: 'HIGH' (>$500M) | 'NORMAL' | 'LOW' (<$50M) | 'N/A'
    """
    now = time.time()
    with _OI_CACHE_LOCK:
        cached = _OI_CACHE.get(pair)
        if cached and (now - cached.get('_ts', 0)) < _OI_TTL:
            return cached

    inst_id = _okx_inst_id(pair)
    try:
        resp = requests.get(
            "https://www.okx.com/api/v5/public/open-interest",
            params={'instType': 'SWAP', 'instId': inst_id},
            timeout=6,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('data', [])
            if items and data.get('code') == '0':
                oi_usd = float(items[0].get('oiUsd', 0))
                if oi_usd > 500_000_000:
                    signal = 'HIGH'
                elif oi_usd < 50_000_000:
                    signal = 'LOW'
                else:
                    signal = 'NORMAL'
                result = {'oi_usd': round(oi_usd, 0), 'signal': signal, 'error': None, '_ts': now}
                with _OI_CACHE_LOCK:
                    _OI_CACHE[pair] = result
                return result
    except Exception as e:
        logging.warning(f"OI fetch failed for {pair}: {e}")

    result = {'oi_usd': 0.0, 'signal': 'N/A', 'error': 'OI unavailable', '_ts': now}
    with _OI_CACHE_LOCK:
        _OI_CACHE[pair] = result
    return result


def get_open_interest_batch(pairs: list) -> dict:
    """Fetch open interest for all pairs in parallel. Returns {pair: oi_dict}."""
    if not pairs:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(pairs), 4)) as ex:
        futures = {pair: ex.submit(get_open_interest, pair) for pair in pairs}
    return {pair: f.result() for pair, f in futures.items()}


# ──────────────────────────────────────────────
# DERIBIT OPTIONS IV (DVOL — 30-day implied vol index)
# Free public API — no key required — BTC + ETH only
# ──────────────────────────────────────────────

_DERIBIT_DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
_IV_CACHE: dict = {}
_IV_CACHE_LOCK   = threading.Lock()
_IV_TTL = 3600  # 1-hour cache (DVOL is slow-moving)
_IV_PAIRS = {'BTC/USDT': 'BTC', 'ETH/USDT': 'ETH'}


def get_options_iv(pair: str) -> dict:
    """
    Fetch Deribit DVOL (30-day implied volatility index) for BTC and ETH.
    Free public API, no key required.
    Returns {'iv': float, 'iv_percentile': float, 'signal': str, 'source': str, 'error': str|None}
    signal: 'EXTREME_FEAR' (>80) | 'FEAR' (60-80) | 'NORMAL' (40-60) | 'COMPLACENCY' (<40) | 'N/A'
    iv_percentile: 0-100, position within 30-day range.
    """
    now = time.time()
    with _IV_CACHE_LOCK:
        cached = _IV_CACHE.get(pair)
        if cached and (now - cached.get('_ts', 0)) < _IV_TTL:
            return cached

    currency = _IV_PAIRS.get(pair)
    if not currency:
        result = {'iv': 0.0, 'iv_percentile': 50.0, 'signal': 'N/A', 'source': None,
                  'error': 'Not on Deribit', '_ts': now}
        with _IV_CACHE_LOCK:
            _IV_CACHE[pair] = result
        return result

    try:
        resp = requests.get(
            _DERIBIT_DVOL_URL,
            params={'currency': currency, 'resolution': '3600', 'count': '720'},  # 30d hourly
            timeout=10,
        )
        if resp.status_code == 200:
            ticks = resp.json().get('result', {}).get('data', [])
            if ticks:
                closes = [float(t[4]) for t in ticks if len(t) > 4]
                if not closes:
                    raise ValueError("No valid IV ticks in response")
                current_iv = closes[-1]
                iv_min, iv_max = min(closes), max(closes)
                iv_pct = round((current_iv - iv_min) / (iv_max - iv_min + 1e-6) * 100, 1)
                if current_iv > 80:   signal = 'EXTREME_FEAR'
                elif current_iv > 60: signal = 'FEAR'
                elif current_iv < 40: signal = 'COMPLACENCY'
                else:                 signal = 'NORMAL'
                result = {
                    'iv': round(current_iv, 1), 'iv_percentile': iv_pct,
                    'signal': signal, 'source': 'deribit', 'error': None, '_ts': now,
                }
                with _IV_CACHE_LOCK:
                    _IV_CACHE[pair] = result
                return result
    except Exception as e:
        logging.warning(f"Deribit IV fetch failed for {pair}: {e}")

    result = {'iv': 0.0, 'iv_percentile': 50.0, 'signal': 'N/A', 'source': None,
              'error': 'IV unavailable', '_ts': now}
    with _IV_CACHE_LOCK:
        _IV_CACHE[pair] = result
    return result


def get_options_iv_batch(pairs: list) -> dict:
    """Fetch Deribit DVOL for all pairs in parallel. Returns {pair: iv_dict}. Non-BTC/ETH return N/A."""
    if not pairs:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(pairs), 4)) as ex:
        futures = {pair: ex.submit(get_options_iv, pair) for pair in pairs}
    return {pair: f.result() for pair, f in futures.items()}


# ──────────────────────────────────────────────
# ORDER BOOK DEPTH via OKX (free, US-accessible)
# Bid/ask volume imbalance as buy/sell pressure signal
# ──────────────────────────────────────────────

_OB_CACHE: dict = {}
_OB_CACHE_LOCK   = threading.Lock()
_OB_TTL = 30  # 30-second cache (order books change fast)


def get_orderbook_depth(pair: str, levels: int = 20) -> dict:
    """
    Fetch order book depth from OKX SWAP and compute bid/ask imbalance.
    Returns {'imbalance': float, 'signal': str, 'bid_vol': float, 'ask_vol': float, 'error': str|None}
    imbalance: -1.0 (pure ask pressure) to +1.0 (pure bid pressure)
    signal: 'BUY_PRESSURE' | 'SELL_PRESSURE' | 'BALANCED' | 'N/A'
    """
    now = time.time()
    with _OB_CACHE_LOCK:
        cached = _OB_CACHE.get(pair)
        if cached and (now - cached.get('_ts', 0)) < _OB_TTL:
            return cached

    inst_id = _okx_inst_id(pair)  # BTC-USDT-SWAP
    try:
        resp = requests.get(
            'https://www.okx.com/api/v5/market/books',
            params={'instId': inst_id, 'sz': str(levels)},
            timeout=6,
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('data', [])
            if items and data.get('code') == '0':
                bids = items[0].get('bids', [])   # [[price, size, _, _], ...]
                asks = items[0].get('asks', [])
                bid_vol = sum(float(b[1]) for b in bids)
                ask_vol = sum(float(a[1]) for a in asks)
                total = bid_vol + ask_vol
                imbalance = round((bid_vol - ask_vol) / total, 3) if total > 0 else 0.0
                if imbalance > 0.15:    signal = 'BUY_PRESSURE'
                elif imbalance < -0.15: signal = 'SELL_PRESSURE'
                else:                   signal = 'BALANCED'
                result = {
                    'imbalance': imbalance, 'signal': signal,
                    'bid_vol': round(bid_vol, 2), 'ask_vol': round(ask_vol, 2),
                    'error': None, '_ts': now,
                }
                with _OB_CACHE_LOCK:
                    _OB_CACHE[pair] = result
                return result
    except Exception as e:
        logging.warning(f"OB depth fetch failed for {pair}: {e}")

    result = {'imbalance': 0.0, 'signal': 'N/A', 'bid_vol': 0.0, 'ask_vol': 0.0,
              'error': 'OB unavailable', '_ts': now}
    with _OB_CACHE_LOCK:
        _OB_CACHE[pair] = result
    return result


def get_orderbook_batch(pairs: list) -> dict:
    """Fetch OB depth for all pairs in parallel. Returns {pair: ob_dict}."""
    if not pairs:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(pairs), 4)) as ex:
        futures = {pair: ex.submit(get_orderbook_depth, pair) for pair in pairs}
    return {pair: f.result() for pair, f in futures.items()}


# ──────────────────────────────────────────────
# MULTI-EXCHANGE FUNDING RATE COMPARISON
# Fetches OKX · Binance · Bybit · KuCoin in parallel
# ──────────────────────────────────────────────

_KUCOIN_FUNDING_URL = "https://api-futures.kucoin.com/api/v1/funding-rate/{symbol}/current"

# KuCoin futures symbol mapping (their naming convention differs from ccxt)
_KUCOIN_SYMBOL_MAP: dict[str, str] = {
    'BTC/USDT': 'XBTUSDTM',   'ETH/USDT': 'ETHUSDTM',   'SOL/USDT': 'SOLUSDTM',
    'XRP/USDT': 'XRPUSDTM',   'DOGE/USDT': 'DOGEUSDTM', 'BNB/USDT': 'BNBUSDTM',
    'ADA/USDT': 'ADAUSDTM',   'AVAX/USDT': 'AVAXUSDTM', 'MATIC/USDT': 'MATICUSDTM',
    'LINK/USDT': 'LINKUSDTM', 'LTC/USDT': 'LTCUSDTM',   'DOT/USDT': 'DOTUSDTM',
    'UNI/USDT': 'UNIUSDTM',   'ATOM/USDT': 'ATOMUSDTM', 'FIL/USDT': 'FILUSDTM',
    'NEAR/USDT': 'NEARUSDTM',
}

_MULTI_FR_CACHE: dict = {}
_MULTI_FR_LOCK = threading.Lock()
_MULTI_FR_TTL  = 300  # 5-minute cache


def _fetch_okx_fr(pair: str, now: float) -> dict:
    """Fetch OKX funding rate for a single pair."""
    try:
        inst_id = _okx_inst_id(pair)
        resp = requests.get(_OKX_FUNDING_URL, params={"instId": inst_id}, timeout=6)
        if resp.status_code == 200:
            data  = resp.json()
            items = data.get("data", [])
            if items and data.get("code") == "0":
                parsed = _parse_okx_item(items[0], now)
                if parsed:
                    return parsed
    except Exception as _e:
        logging.debug("_fetch_okx_fr %s: %s", pair, _e)  # BUG-R24: was silent pass
    return _empty_result("OKX N/A", now)


def _fetch_binance_fr(pair: str, now: float) -> dict:
    """Fetch Binance funding rate for a single pair."""
    try:
        symbol = _binance_symbol(pair)
        resp = requests.get(_BINANCE_PREMIUM_URL, params={"symbol": symbol}, timeout=6)
        if resp.status_code == 200:
            data   = resp.json()
            parsed = _parse_binance_item(data, now) if isinstance(data, dict) else None
            if parsed:
                return parsed
    except Exception as _e:
        logging.debug("_fetch_binance_fr %s: %s", pair, _e)  # BUG-R24: was silent pass
    return _empty_result("Binance N/A", now)


def _fetch_bybit_fr(pair: str, now: float) -> dict:
    """Fetch Bybit funding rate for a single pair."""
    try:
        symbol = _binance_symbol(pair)
        resp = requests.get(
            _BYBIT_TICKERS_URL,
            params={"category": "linear", "symbol": symbol},
            timeout=6,
        )
        if resp.status_code == 200:
            data  = resp.json()
            items = data.get("result", {}).get("list", [])
            if items:
                parsed = _parse_bybit_item(items[0], now)
                if parsed:
                    return parsed
    except Exception as _e:
        logging.debug("_fetch_bybit_fr %s: %s", pair, _e)  # BUG-R24: was silent pass
    return _empty_result("Bybit N/A", now)


def _fetch_kucoin_fr(pair: str, now: float) -> dict:
    """Fetch KuCoin futures funding rate for a single pair."""
    try:
        sym = _KUCOIN_SYMBOL_MAP.get(pair)
        if not sym:
            return _empty_result("KuCoin: no symbol mapping", now)
        url  = _KUCOIN_FUNDING_URL.format(symbol=sym)
        resp = requests.get(url, timeout=6)
        if resp.status_code == 429:
            logging.warning(f"KuCoin funding rate: rate limited (429) for {pair}")
            return _empty_result("KuCoin: rate limited", now)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "200000":
                item = data.get("data", {})
                rate = float(item.get("value", 0))
                return {
                    "funding_rate":     rate,
                    "funding_rate_pct": round(rate * 100, 4),
                    "next_funding_time": int(item.get("timePoint", 0)) if item.get("timePoint") else 0,
                    "mark_price":  0.0,
                    "signal":      _funding_signal(rate),
                    "source":      "kucoin",
                    "error":       None,
                    "_ts":         now,
                }
    except Exception as _e:
        logging.debug("_fetch_kucoin_fr %s: %s", pair, _e)  # BUG-R24: was silent pass
    return _empty_result("KuCoin N/A", now)


def get_multi_exchange_funding_rates(pair: str) -> dict[str, dict]:
    """
    Fetch funding rates from OKX, Binance, Bybit, and KuCoin for a single pair
    using 4 parallel threads. Always returns all 4 keys; failed exchanges get an
    error-flagged result dict. 5-minute cache.

    Returns: {"okx": {...}, "binance": {...}, "bybit": {...}, "kucoin": {...}}
    """
    import concurrent.futures

    now = time.time()
    with _MULTI_FR_LOCK:
        cached = _MULTI_FR_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _MULTI_FR_TTL:
            return cached["data"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            "okx":     ex.submit(_fetch_okx_fr,     pair, now),
            "binance": ex.submit(_fetch_binance_fr,  pair, now),
            "bybit":   ex.submit(_fetch_bybit_fr,    pair, now),
            "kucoin":  ex.submit(_fetch_kucoin_fr,   pair, now),
        }
        result = {name: f.result() for name, f in futs.items()}

    with _MULTI_FR_LOCK:
        _MULTI_FR_CACHE[pair] = {"data": result, "_ts": now}
    return result


def get_carry_trade_opportunities(
    pairs: list[str],
    threshold_pct: float = 0.01,
) -> list[dict]:
    """
    Scan pairs for funding-rate carry trade opportunities.

    Carry trade = pair a perp position against the opposite spot position so
    the delta is neutral and you collect the funding payment every 8 hours.

    • Positive funding (longs pay shorts) → Short Perp + Long Spot
    • Negative funding (shorts pay longs) → Long Perp + Short Spot

    threshold_pct: minimum |funding_rate_pct| to flag (default 0.01% ≈ 11% annualised).

    Returns list sorted by abs(funding_rate_pct) descending, with keys:
      pair, exchange, funding_rate_pct, direction, strategy, annualized_yield
    """
    import concurrent.futures

    def _scan_one(pair: str) -> list[dict]:
        opps: list[dict] = []
        try:
            multi = get_multi_exchange_funding_rates(pair)
            for exch, rd in multi.items():
                if rd.get("error") or rd.get("source") is None:
                    continue
                rate_pct = rd.get("funding_rate_pct", 0.0)
                if abs(rate_pct) < threshold_pct:
                    continue
                # 8-hour intervals → 3 payments/day → 1 095 per year
                ann_yield = round(abs(rate_pct) * 1095, 2)
                opps.append({
                    "pair":             pair,
                    "exchange":         exch.upper(),
                    "funding_rate_pct": rate_pct,
                    "direction":        "POSITIVE" if rate_pct > 0 else "NEGATIVE",
                    "strategy": (
                        "Short Perp + Long Spot"
                        if rate_pct > 0 else
                        "Long Perp + Short Spot"
                    ),
                    "annualized_yield": ann_yield,
                })
        except Exception:
            pass
        return opps

    all_opps: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for opps in ex.map(_scan_one, pairs):
            all_opps.extend(opps)

    all_opps.sort(key=lambda x: abs(x["funding_rate_pct"]), reverse=True)
    return all_opps


def get_funding_rates_batch(pairs: list[str]) -> dict[str, dict]:
    """
    Fetch funding rates for all pairs efficiently.
    1. OKX per-symbol (US-accessible, no bulk needed — fast enough for 6-20 pairs)
    2. Binance bulk fallback
    3. Per-symbol fallback
    Returns {pair: funding_dict}.
    """
    results = {}
    now = time.time()

    # 1. OKX — per-symbol (simple, US-accessible, ~100ms each)
    try:
        okx_success = 0
        for pair in pairs:
            inst_id = _okx_inst_id(pair)
            resp = requests.get(_OKX_FUNDING_URL, params={"instId": inst_id}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", [])
                if items and data.get("code") == "0":
                    parsed = _parse_okx_item(items[0], now)
                    if parsed:
                        results[pair] = parsed
                        with _FUNDING_CACHE_LOCK:
                            _BINANCE_FUNDING_CACHE[pair] = parsed
                        okx_success += 1
        if okx_success > 0:
            for pair in pairs:
                if pair not in results:
                    results[pair] = _empty_result("Not on OKX futures", now)
            return results
    except Exception:
        pass

    # 2. Binance bulk
    symbols_needed = {_binance_symbol(p): p for p in pairs}
    try:
        resp = requests.get(_BINANCE_PREMIUM_URL, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                bulk_map = {item["symbol"]: item for item in data}
                for symbol, pair in symbols_needed.items():
                    item = bulk_map.get(symbol)
                    parsed = _parse_binance_item(item, now) if item else None
                    results[pair] = parsed if parsed else _empty_result("Not on Binance futures", now)
                    with _FUNDING_CACHE_LOCK:
                        _BINANCE_FUNDING_CACHE[pair] = results[pair]
                return results
    except Exception:
        pass

    # 3. Per-symbol fallback
    for pair in pairs:
        if pair not in results:
            results[pair] = get_funding_rate(pair)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# PAID API STUBS
# ──────────────────────────────────────────────────────────────────────────────
# These functions are pre-wired and ready to activate.
# To enable: add your API key to alerts_config.json (Config Editor → API Keys tab).
# When a key is absent the function returns a neutral "not configured" result
# identical in schema to a live response, so the rest of the model is unaffected.
# ══════════════════════════════════════════════════════════════════════════════

import json as _json
import os as _os
import threading as _threading

_API_KEYS_FILE = "alerts_config.json"
_paid_key_cache: dict = {}
_paid_key_cache_ts: float = 0.0
_PAID_KEY_TTL = 30  # re-read keys every 30s so UI saves are picked up quickly
_cache_lock = _threading.Lock()  # BUG-20: protect cache reads/writes from concurrent scan workers


def _load_api_keys() -> dict:
    """Load API keys from alerts_config.json with a short TTL cache. Thread-safe."""
    global _paid_key_cache, _paid_key_cache_ts
    now = time.time()
    with _cache_lock:
        if now - _paid_key_cache_ts < _PAID_KEY_TTL:
            return dict(_paid_key_cache)
        try:
            if _os.path.exists(_API_KEYS_FILE):
                with open(_API_KEYS_FILE, "r") as f:
                    _paid_key_cache = _json.load(f)
            # DF-14: update timestamp regardless of file presence so TTL applies
            _paid_key_cache_ts = now
        except Exception:
            _paid_key_cache_ts = now  # DF-14: also stamp on parse error
        return dict(_paid_key_cache)


def _no_key_result(service: str, description: str) -> dict:
    """Standard 'not configured' return value for all paid stubs."""
    return {
        "signal": "N/A",
        "value": None,
        "source": service,
        "error": f"API key not configured — add {service}_key to Config Editor → API Keys",
        "description": description,
        "_ts": time.time(),
    }


# ──────────────────────────────────────────────
# LUNARCRUSH — Social Sentiment
# Provides: social volume, galaxy score, alt rank, sentiment score
# Docs: https://lunarcrush.com/developers/api/coins
# Key: lunarcrush_key in alerts_config.json
# Free tier: 10 req/min, 1 coin/call
# ──────────────────────────────────────────────

_LC_CACHE: dict = {}
_LC_CACHE_LOCK = threading.Lock()
_LC_TTL = 600  # 10-minute cache

_LC_COIN_MAP = {
    'BTC/USDT': 'bitcoin',    'ETH/USDT': 'ethereum',   'SOL/USDT': 'solana',
    'XRP/USDT': 'xrp',        'DOGE/USDT': 'dogecoin',  'BNB/USDT': 'binancecoin',
    'ADA/USDT': 'cardano',    'AVAX/USDT': 'avalanche', 'MATIC/USDT': 'polygon',
    'LINK/USDT': 'chainlink', 'LTC/USDT': 'litecoin',   'DOT/USDT': 'polkadot',
    'UNI/USDT': 'uniswap',   'ATOM/USDT': 'cosmos',    'FIL/USDT': 'filecoin',
    'NEAR/USDT': 'near',
}


def get_lunarcrush_sentiment(pair: str) -> dict:
    """
    Fetch social sentiment from LunarCrush API v3.
    Returns galaxy_score (0-100), alt_rank, sentiment ('BULLISH'/'BEARISH'/'NEUTRAL').
    Requires lunarcrush_key in alerts_config.json.

    Schema: {'signal': str, 'galaxy_score': float, 'alt_rank': int,
             'social_volume': int, 'source': str, 'error': str|None}
    """
    keys = _load_api_keys()
    api_key = keys.get("lunarcrush_key", "").strip()
    if not api_key:
        return _no_key_result("lunarcrush", "Social sentiment: galaxy score, alt rank, social volume")

    now = time.time()
    with _LC_CACHE_LOCK:
        cached = _LC_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _LC_TTL:
            return cached

    coin = _LC_COIN_MAP.get(pair)
    if not coin:
        result = _no_key_result("lunarcrush", "Pair not in LunarCrush coin map")
        result["error"] = f"Pair {pair} not mapped to a LunarCrush coin slug"
        return result

    try:
        resp = requests.get(
            f"https://lunarcrush.com/api4/public/coins/{coin}/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            galaxy_score  = float(data.get("galaxy_score", 50))
            alt_rank      = int(data.get("alt_rank", 999))
            social_volume = int(data.get("social_volume_24h", 0))
            # Galaxy score > 60 = bullish social; < 40 = bearish
            if galaxy_score >= 60:   signal = "BULLISH"
            elif galaxy_score <= 40: signal = "BEARISH"
            else:                    signal = "NEUTRAL"
            result = {
                "signal": signal, "galaxy_score": galaxy_score,
                "alt_rank": alt_rank, "social_volume": social_volume,
                "source": "lunarcrush", "error": None, "_ts": now,
            }
            with _LC_CACHE_LOCK:
                _LC_CACHE[pair] = result
            return result
        # DF-15: cache non-200 to avoid hammering API on repeated calls
        err_result = {**_no_key_result("lunarcrush", f"HTTP {resp.status_code}"), "_ts": now}
        with _LC_CACHE_LOCK:
            _LC_CACHE[pair] = err_result
        return err_result
    except Exception as e:
        logging.warning(f"LunarCrush fetch failed for {pair}: {e}")
        err_result = {**_no_key_result("lunarcrush", str(e)), "_ts": now}
        with _LC_CACHE_LOCK:
            _LC_CACHE[pair] = err_result
        return err_result


# ──────────────────────────────────────────────
# COINGLASS — Liquidation Data
# Provides: 24h liquidation volume (longs vs shorts), large liquidation events
# Docs: https://coinglass.com/api
# Key: coinglass_key in alerts_config.json
# ──────────────────────────────────────────────

_CG_LIQ_CACHE: dict = {}
_CG_LIQ_LOCK = threading.Lock()
_CG_LIQ_TTL = 300  # 5-minute cache


def get_coinglass_liquidations(pair: str) -> dict:
    """
    Fetch 24h liquidation data from Coinglass API.
    Returns long_liq_usd, short_liq_usd, dominant_side, signal.
    Requires coinglass_key in alerts_config.json.

    Schema: {'signal': str, 'long_liq_usd': float, 'short_liq_usd': float,
             'dominant_side': str, 'source': str, 'error': str|None}
    signal: 'LONG_SQUEEZE' (shorts winning) | 'SHORT_SQUEEZE' (longs winning) | 'NEUTRAL'
    """
    keys = _load_api_keys()
    api_key = keys.get("coinglass_key", "").strip()
    if not api_key:
        return _no_key_result("coinglass", "Liquidations: 24h long/short liquidation volume")

    now = time.time()
    with _CG_LIQ_LOCK:
        cached = _CG_LIQ_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _CG_LIQ_TTL:
            return cached

    symbol = pair.split("/")[0]  # BTC/USDT → BTC
    try:
        resp = requests.get(
            "https://open-api.coinglass.com/public/v2/liquidation_chart",
            params={"symbol": symbol, "interval": "24h"},
            headers={"coinglassSecret": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            long_liq  = float(data.get("longLiquidationUsd", 0))
            short_liq = float(data.get("shortLiquidationUsd", 0))
            # More longs liquidated = bearish event (short squeeze in reverse = long squeeze)
            if long_liq > short_liq * 1.5:   signal, dominant = "LONG_SQUEEZE",  "longs"
            elif short_liq > long_liq * 1.5: signal, dominant = "SHORT_SQUEEZE", "shorts"
            else:                              signal, dominant = "NEUTRAL",       "balanced"
            result = {
                "signal": signal, "long_liq_usd": long_liq,
                "short_liq_usd": short_liq, "dominant_side": dominant,
                "source": "coinglass", "error": None, "_ts": now,
            }
            with _CG_LIQ_LOCK:
                _CG_LIQ_CACHE[pair] = result
            return result
        # DF-16: cache non-200 to avoid hammering API on repeated calls
        err_result = {**_no_key_result("coinglass", f"HTTP {resp.status_code}"), "_ts": now}
        with _CG_LIQ_LOCK:
            _CG_LIQ_CACHE[pair] = err_result
        return err_result
    except Exception as e:
        logging.warning(f"Coinglass liquidation fetch failed for {pair}: {e}")
        err_result = {**_no_key_result("coinglass", str(e)), "_ts": now}
        with _CG_LIQ_LOCK:
            _CG_LIQ_CACHE[pair] = err_result
        return err_result


# ──────────────────────────────────────────────
# CRYPTOQUANT — Exchange Flow
# Provides: exchange inflow/outflow, miner flow, reserve changes
# Docs: https://docs.cryptoquant.com
# Key: cryptoquant_key in alerts_config.json
# Supported pairs: BTC, ETH (most data is BTC-centric)
# ──────────────────────────────────────────────

_CQ_CACHE: dict = {}
_CQ_LOCK = threading.Lock()
_CQ_TTL = 600  # 10-minute cache
_CQ_PAIRS = {'BTC/USDT', 'ETH/USDT'}


def get_cryptoquant_exchange_flow(pair: str) -> dict:
    """
    Fetch exchange net flow from CryptoQuant API.
    Negative net flow (more leaving exchanges) = bullish (hodling).
    Positive net flow (more entering exchanges) = bearish (selling pressure).
    Requires cryptoquant_key in alerts_config.json.

    Schema: {'signal': str, 'net_flow_usd': float, 'inflow_usd': float,
             'outflow_usd': float, 'source': str, 'error': str|None}
    """
    keys = _load_api_keys()
    api_key = keys.get("cryptoquant_key", "").strip()
    if not api_key:
        return _no_key_result("cryptoquant", "Exchange flow: inflow/outflow, net flow signal")

    if pair not in _CQ_PAIRS:
        result = _no_key_result("cryptoquant", "CryptoQuant flow only for BTC and ETH")
        result["error"] = f"CryptoQuant exchange flow not available for {pair}"
        return result

    now = time.time()
    with _CQ_LOCK:
        cached = _CQ_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _CQ_TTL:
            return cached

    asset = pair.split("/")[0].lower()  # btc or eth
    try:
        resp = requests.get(
            f"https://api.cryptoquant.com/v1/{asset}/exchange-flows/netflow",
            params={"window": "day", "limit": 1},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            _body = resp.json()
            items = (_body.get("result", {}) if isinstance(_body, dict) else {}).get("data", [])
            if items:
                row = items[-1]
                inflow  = float(row.get("inflow_usd", 0))
                outflow = float(row.get("outflow_usd", 0))
                net     = inflow - outflow
                if net < -10_000_000:   signal = "BULLISH"   # coins leaving exchanges
                elif net > 10_000_000:  signal = "BEARISH"   # coins entering exchanges
                else:                   signal = "NEUTRAL"
                result = {
                    "signal": signal, "net_flow_usd": round(net, 0),
                    "inflow_usd": round(inflow, 0), "outflow_usd": round(outflow, 0),
                    "source": "cryptoquant", "error": None, "_ts": now,
                }
                with _CQ_LOCK:
                    _CQ_CACHE[pair] = result
                return result
        # DF-17: cache non-200 / missing-data responses
        err_result = {**_no_key_result("cryptoquant", f"HTTP {resp.status_code}"), "_ts": now}
        with _CQ_LOCK:
            _CQ_CACHE[pair] = err_result
        return err_result
    except Exception as e:
        logging.warning(f"CryptoQuant flow fetch failed for {pair}: {e}")
        err_result = {**_no_key_result("cryptoquant", str(e)), "_ts": now}
        with _CQ_LOCK:
            _CQ_CACHE[pair] = err_result
        return err_result


# ──────────────────────────────────────────────
# GLASSNODE — On-Chain Metrics (premium)
# Provides: SOPR, MVRV-Z, NVT, NUPL, realized price, active addresses
# Docs: https://docs.glassnode.com
# Key: glassnode_key in alerts_config.json
# Supported: BTC, ETH natively; other assets limited
# ──────────────────────────────────────────────

_GN_CACHE: dict = {}
_GN_LOCK = threading.Lock()
_GN_TTL = 3600  # 1-hour cache (on-chain is daily resolution)
_GN_PAIRS = {'BTC/USDT': 'BTC', 'ETH/USDT': 'ETH'}


def get_glassnode_onchain(pair: str) -> dict:
    """
    Fetch real on-chain metrics from Glassnode API (replaces CoinGecko proxies).
    Returns SOPR, MVRV-Z score, NVT signal, active addresses signal.
    Requires glassnode_key in alerts_config.json.

    Schema: {'signal': str, 'sopr': float, 'mvrv_z': float, 'nvt_signal': str,
             'active_addr_signal': str, 'source': str, 'error': str|None}
    """
    keys = _load_api_keys()
    api_key = keys.get("glassnode_key", "").strip()
    if not api_key:
        return _no_key_result("glassnode", "On-chain: real SOPR, MVRV-Z, NVT, active addresses")

    asset = _GN_PAIRS.get(pair)
    if not asset:
        result = _no_key_result("glassnode", "Glassnode native on-chain for BTC/ETH only")
        result["error"] = f"Glassnode on-chain not available for {pair}"
        return result

    now = time.time()
    with _GN_LOCK:
        cached = _GN_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _GN_TTL:
            return cached

    try:
        base = "https://api.glassnode.com/v1/metrics"
        headers = {"X-Api-Key": api_key}
        params  = {"a": asset, "i": "24h", "f": "JSON", "timestamp_format": "humanized"}

        sopr_resp = requests.get(f"{base}/indicators/sopr", params=params, headers=headers, timeout=10)
        mvrv_resp = requests.get(f"{base}/market/mvrv_z_score", params=params, headers=headers, timeout=10)

        sopr = mvrv_z = None
        try:
            if sopr_resp.status_code == 200:
                d = sopr_resp.json()
                if d and isinstance(d, list) and d[-1].get("v") is not None:
                    sopr = round(float(d[-1]["v"]), 3)
        except Exception as _e:
            logging.warning("Glassnode SOPR parse error: %s", _e)
        try:
            if mvrv_resp.status_code == 200:
                d = mvrv_resp.json()
                if d and isinstance(d, list) and d[-1].get("v") is not None:
                    mvrv_z = round(float(d[-1]["v"]), 2)
        except Exception as _e:
            logging.warning("Glassnode MVRV-Z parse error: %s", _e)

        # Composite signal: SOPR < 1 (capitulation) + MVRV-Z < 0 (undervalued) = BULLISH
        if sopr is not None and mvrv_z is not None:
            if sopr < 0.99 and mvrv_z < 0:    signal = "STRONG_BULLISH"
            elif sopr < 1.0 or mvrv_z < 0.5:  signal = "BULLISH"
            elif sopr > 1.02 and mvrv_z > 3:  signal = "BEARISH"
            elif sopr > 1.01 or mvrv_z > 2:   signal = "CAUTION"
            else:                               signal = "NEUTRAL"
        else:
            signal = "N/A"

        result = {
            "signal": signal, "sopr": sopr, "mvrv_z": mvrv_z,
            "source": "glassnode", "error": None, "_ts": now,
        }
        with _GN_LOCK:
            _GN_CACHE[pair] = result
        return result
    except Exception as e:
        logging.warning(f"Glassnode fetch failed for {pair}: {e}")
        return _no_key_result("glassnode", str(e))


# ──────────────────────────────────────────────
# TOKEN UNLOCK SCHEDULE (Tokenomist.ai / Vesting)
# Provides: upcoming token unlock events, cliff dates, % supply unlocking
# Key: None required for basic data; tokenomist_key for full history
# Note: Most token unlocks only apply to non-BTC/ETH Layer-1s and DeFi tokens
# ──────────────────────────────────────────────

_UNLOCK_CACHE: dict = {}
_UNLOCK_CACHE_LOCK = threading.Lock()
_UNLOCK_TTL = 3600  # 1-hour cache


# ──────────────────────────────────────────────
# DEFILLAMA TVL (free, no key required)
# Provides chain-level TVL and 7-day change
# ──────────────────────────────────────────────

_TVL_CHAIN_MAP = {
    'ETH/USDT':  'Ethereum',   'BNB/USDT':  'BSC',
    'SOL/USDT':  'Solana',     'AVAX/USDT': 'Avalanche',
    'MATIC/USDT':'Polygon',    'BTC/USDT':  'Bitcoin',
    'ATOM/USDT': 'CosmosHub',  'DOT/USDT':  'Polkadot',
    'NEAR/USDT': 'Near',       'ADA/USDT':  'Cardano',
    'UNI/USDT':  'Ethereum',   'LINK/USDT': 'Ethereum',
    'XRP/USDT':  'XRP Ledger', 'DOGE/USDT': None,
    'LTC/USDT':  None,         'FIL/USDT':  None,
}

_TVL_CACHE: dict = {}
_TVL_CACHE_LOCK = threading.Lock()   # BUG-R09: protect against parallel scan workers
_TVL_TTL = 300  # 5-minute cache


def get_defillama_tvl(pair: str) -> dict:
    """
    Fetch chain TVL + 7-day change for the given pair from DefiLlama free API (no key required).
    Uses /v2/historicalChainTvl/{chain} to compute real 7d change.
    Returns {'tvl_usd': float, 'change_7d': float, 'signal': str, 'chain': str, 'error': str|None}
    signal: 'GROWING' (>+5% 7d) | 'DECLINING' (<-5% 7d) | 'STABLE' | 'N/A'
    """
    _neutral = {'tvl_usd': 0.0, 'change_7d': 0.0, 'signal': 'N/A', 'chain': None, 'error': 'N/A'}
    chain_name = _TVL_CHAIN_MAP.get(pair)
    if not chain_name:
        return {**_neutral, 'error': 'No chain mapping'}

    now = time.time()
    with _TVL_CACHE_LOCK:
        cached = _TVL_CACHE.get(pair)
        if cached and (now - cached.get('_ts', 0)) < _TVL_TTL:
            return cached

    try:
        resp = requests.get(
            f"https://api.llama.fi/v2/historicalChainTvl/{chain_name}",
            timeout=10,
        )
        if resp.status_code != 200:
            result = {**_neutral, 'chain': chain_name, 'error': f'HTTP {resp.status_code}', '_ts': now}
            with _TVL_CACHE_LOCK:
                _TVL_CACHE[pair] = result
            return result

        history = resp.json()  # [{date: unix, tvl: float}, ...]
        if not history or len(history) < 2:
            result = {**_neutral, 'chain': chain_name, 'error': 'No TVL history', '_ts': now}
            with _TVL_CACHE_LOCK:
                _TVL_CACHE[pair] = result
            return result

        current_tvl = float(history[-1].get('tvl') or 0.0)
        # Find the data point closest to 7 days ago
        target_ts = now - 7 * 86400
        week_ago = min(history, key=lambda x: abs((x.get('date') or 0) - target_ts))
        tvl_7d_ago = float(week_ago.get('tvl') or 0.0)
        change_7d = ((current_tvl - tvl_7d_ago) / tvl_7d_ago * 100) if tvl_7d_ago > 0 else 0.0

        if change_7d > 5:    signal = 'GROWING'
        elif change_7d < -5: signal = 'DECLINING'
        else:                 signal = 'STABLE'

        result = {
            'tvl_usd': current_tvl, 'change_7d': round(change_7d, 2),
            'signal': signal, 'chain': chain_name, 'error': None, '_ts': now,
        }
        with _TVL_CACHE_LOCK:
            _TVL_CACHE[pair] = result
        return result

    except Exception as e:
        logging.warning(f"DefiLlama TVL fetch failed for {pair}: {e}")
        result = {**_neutral, 'chain': chain_name, 'error': str(e)[:80], '_ts': now}
        with _TVL_CACHE_LOCK:
            _TVL_CACHE[pair] = result
        return result


def get_token_unlock_schedule(pair: str) -> dict:
    """
    Check for upcoming token unlock events via Tokenomist.ai free API.
    Unlocks > 1% of supply within 7 days = bearish supply pressure.
    No API key required for basic lookups.

    Schema: {'signal': str, 'next_unlock_days': int|None, 'unlock_pct_supply': float|None,
             'source': str, 'error': str|None}
    signal: 'UNLOCK_IMMINENT' (<3d, >1%) | 'UNLOCK_SOON' (<7d) | 'NO_UNLOCK' | 'N/A'
    Note: BTC and LTC have no token unlocks (no VC vesting).
    """
    # No unlocks for PoW coins or coins with no vesting schedules
    _NO_UNLOCK_PAIRS = {'BTC/USDT', 'LTC/USDT', 'DOGE/USDT'}
    if pair in _NO_UNLOCK_PAIRS:
        return {
            "signal": "NO_UNLOCK", "next_unlock_days": None, "unlock_pct_supply": None,
            "source": "n/a", "error": None, "_ts": time.time(),
        }

    now = time.time()
    with _UNLOCK_CACHE_LOCK:
        cached = _UNLOCK_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _UNLOCK_TTL:
            return cached

    # Map to Tokenomist project slugs (best-effort)
    _SLUG_MAP = {
        'ETH/USDT': 'ethereum', 'SOL/USDT': 'solana', 'XRP/USDT': 'ripple',
        'BNB/USDT': 'bnb', 'ADA/USDT': 'cardano', 'AVAX/USDT': 'avalanche',
        'MATIC/USDT': 'polygon', 'LINK/USDT': 'chainlink', 'DOT/USDT': 'polkadot',
        'UNI/USDT': 'uniswap', 'ATOM/USDT': 'cosmos', 'FIL/USDT': 'filecoin',
        'NEAR/USDT': 'near',
    }
    slug = _SLUG_MAP.get(pair)
    if not slug:
        result = {
            "signal": "N/A", "next_unlock_days": None, "unlock_pct_supply": None,
            "source": "tokenomist", "error": f"No unlock data for {pair}", "_ts": now,
        }
        with _UNLOCK_CACHE_LOCK:
            _UNLOCK_CACHE[pair] = result
        return result

    try:
        resp = requests.get(
            f"https://api.tokenomist.ai/v1/projects/{slug}/unlocks",
            timeout=10,
        )
        if resp.status_code == 200:
            events = resp.json().get("upcoming", [])
            if not events:
                result = {
                    "signal": "NO_UNLOCK", "next_unlock_days": None, "unlock_pct_supply": None,
                    "source": "tokenomist", "error": None, "_ts": now,
                }
            else:
                next_event = events[0]
                days_away  = int((next_event.get("timestamp", now + 9999999) - now) / 86400)
                pct_supply = float(next_event.get("percent_supply", 0))
                if days_away <= 3 and pct_supply >= 1.0:
                    signal = "UNLOCK_IMMINENT"
                elif days_away <= 7:
                    signal = "UNLOCK_SOON"
                else:
                    signal = "NO_UNLOCK"
                result = {
                    "signal": signal, "next_unlock_days": days_away,
                    "unlock_pct_supply": round(pct_supply, 2),
                    "source": "tokenomist", "error": None, "_ts": now,
                }
            with _UNLOCK_CACHE_LOCK:
                _UNLOCK_CACHE[pair] = result
            return result

        # Tokenomist may not cover all tokens — return neutral not error
        result = {
            "signal": "N/A", "next_unlock_days": None, "unlock_pct_supply": None,
            "source": "tokenomist", "error": f"HTTP {resp.status_code}", "_ts": now,
        }
        with _UNLOCK_CACHE_LOCK:
            _UNLOCK_CACHE[pair] = result
        return result
    except Exception as e:
        logging.warning(f"Token unlock fetch failed for {pair}: {e}")
        result = {
            "signal": "N/A", "next_unlock_days": None, "unlock_pct_supply": None,
            "source": "tokenomist", "error": str(e), "_ts": now,
        }
        with _UNLOCK_CACHE_LOCK:
            _UNLOCK_CACHE[pair] = result
        return result


# ──────────────────────────────────────────────
# COINGECKO TRENDING COINS
# Free endpoint — no API key required. 15-min cache.
# ──────────────────────────────────────────────

_TRENDING_CACHE: dict = {}          # {"symbols": list[str], "_ts": float}
_TRENDING_TTL = 900                 # 15 minutes
_TRENDING_LOCK = threading.Lock()


def get_trending_coins() -> list[str]:
    """
    Fetch the top-7 trending coins from CoinGecko (no API key required).
    Returns a list of uppercase base symbols, e.g. ['BTC', 'SOL', 'PEPE'].
    15-minute in-memory cache; returns last cached list on error.
    """
    with _TRENDING_LOCK:
        cached = _TRENDING_CACHE.get("symbols")
        if cached is not None and (time.time() - _TRENDING_CACHE.get("_ts", 0)) < _TRENDING_TTL:
            return cached

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            timeout=10,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            coins = resp.json().get("coins", [])
            symbols = [c["item"]["symbol"].upper() for c in coins]
            with _TRENDING_LOCK:
                _TRENDING_CACHE["symbols"] = symbols
                _TRENDING_CACHE["_ts"]     = time.time()
            return symbols
        elif resp.status_code == 429:
            logging.debug("[Trending] CoinGecko rate-limited — reusing cached list")
    except Exception as e:
        logging.debug(f"[Trending] fetch failed: {e}")

    # Return last known list (may be empty on first call with error)
    with _TRENDING_LOCK:
        return _TRENDING_CACHE.get("symbols", [])


def is_trending(pair: str) -> bool:
    """Return True if the base currency of *pair* is in the current CoinGecko trending list."""
    base = pair.split("/")[0].upper() if "/" in pair else pair.upper()
    return base in get_trending_coins()


# ──────────────────────────────────────────────
# COINGECKO GLOBAL MARKET STATS
# Free endpoint — no API key required. 5-min cache.
# ──────────────────────────────────────────────

_GLOBAL_CACHE: dict = {}            # full result dict cached in-memory
_GLOBAL_TTL   = 300                 # 5 minutes
_GLOBAL_LOCK  = threading.Lock()

_GLOBAL_NEUTRAL = {
    "total_market_cap_usd":    0.0,
    "btc_dominance":           50.0,
    "eth_dominance":           18.0,
    "market_cap_change_24h":   0.0,
    "total_volume_24h_usd":    0.0,
    "altcoin_season":          False,
    "altcoin_season_label":    "N/A",
    "source":                  "fallback",
    "error":                   None,
    "_ts":                     0.0,
}


def get_global_market() -> dict:
    """
    Fetch global crypto market stats from CoinGecko (no API key required).

    Schema:
      total_market_cap_usd   — total crypto market cap in USD
      btc_dominance          — BTC % of total market cap
      eth_dominance          — ETH % of total market cap
      market_cap_change_24h  — 24h market cap % change
      total_volume_24h_usd   — 24h total trading volume USD
      altcoin_season         — True when BTC dominance < 42%
      altcoin_season_label   — 'ALTSEASON' | 'MIXED' | 'BTC_DOMINANT'
      source                 — 'coingecko' | 'fallback'
      error                  — error string or None

    Altcoin season logic:
      BTC dom < 42%  → ALTSEASON   (alts strongly outperform BTC)
      BTC dom 42–50% → MIXED       (neither clearly leading)
      BTC dom > 50%  → BTC_DOMINANT (capital concentrated in BTC)
    Signal use: BTC_DOMINANT → dampen altcoin BUY confidence by ~5 pts.
                ALTSEASON    → boost altcoin BUY confidence by ~5 pts.
    """
    with _GLOBAL_LOCK:
        if _GLOBAL_CACHE and (time.time() - _GLOBAL_CACHE.get("_ts", 0)) < _GLOBAL_TTL:
            return dict(_GLOBAL_CACHE)

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/global",
            timeout=10,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            data  = resp.json().get("data", {})
            mcaps = data.get("market_cap_percentage", {})
            btc_dom = round(float(mcaps.get("btc", 50.0)), 2)
            eth_dom = round(float(mcaps.get("eth", 18.0)), 2)

            total_mcap = float(
                data.get("total_market_cap", {}).get("usd", 0) or 0
            )
            total_vol  = float(
                data.get("total_volume", {}).get("usd", 0) or 0
            )
            mcap_change = round(float(
                data.get("market_cap_change_percentage_24h_usd", 0) or 0
            ), 2)

            if btc_dom < 42.0:
                alt_season       = True
                alt_season_label = "ALTSEASON"
            elif btc_dom <= 50.0:
                alt_season       = False
                alt_season_label = "MIXED"
            else:
                alt_season       = False
                alt_season_label = "BTC_DOMINANT"

            result = {
                "total_market_cap_usd":  total_mcap,
                "btc_dominance":         btc_dom,
                "eth_dominance":         eth_dom,
                "market_cap_change_24h": mcap_change,
                "total_volume_24h_usd":  total_vol,
                "altcoin_season":        alt_season,
                "altcoin_season_label":  alt_season_label,
                "source":                "coingecko",
                "error":                 None,
                "_ts":                   time.time(),
            }
            with _GLOBAL_LOCK:
                _GLOBAL_CACHE.update(result)
            return result

        elif resp.status_code == 429:
            logging.debug("[GlobalMkt] CoinGecko rate-limited — reusing cache")
            with _GLOBAL_LOCK:
                if _GLOBAL_CACHE:
                    return dict(_GLOBAL_CACHE)

    except Exception as e:
        logging.debug(f"[GlobalMkt] fetch failed: {e}")
        with _GLOBAL_LOCK:
            if _GLOBAL_CACHE:
                return dict(_GLOBAL_CACHE)

    return dict(_GLOBAL_NEUTRAL)


# ──────────────────────────────────────────────
# CUMULATIVE VOLUME DELTA (CVD) via OKX SWAP trades
# Free public endpoint — no auth required
# CVD = cumulative (buy_vol - sell_vol) over recent trades
# Positive and rising → buy pressure (bullish); falling → sell pressure (bearish)
# ──────────────────────────────────────────────

_CVD_CACHE: dict = {}
_CVD_LOCK  = threading.Lock()
_CVD_TTL   = 60  # 60-second cache

_CVD_NEUTRAL = {
    "cvd":             0.0,
    "cvd_change_pct":  0.0,
    "buy_vol":         0.0,
    "sell_vol":        0.0,
    "imbalance":       0.0,
    "signal":          "N/A",
    "source":          "fallback",
    "error":           "CVD not available",
}


def get_cvd(pair: str, limit: int = 500) -> dict:
    """Compute Cumulative Volume Delta for a pair using OKX recent trades.

    Fetches the last `limit` trades from OKX SWAP (USDT-margined perp) and
    computes:
      - buy_vol:    total volume of taker-buy trades (aggressive buyers)
      - sell_vol:   total volume of taker-sell trades (aggressive sellers)
      - cvd:        buy_vol - sell_vol (absolute CVD for this window)
      - imbalance:  (buy_vol - sell_vol) / (buy_vol + sell_vol) in [-1, +1]
      - signal:     'BUY_PRESSURE' (imb > 0.10), 'SELL_PRESSURE' (imb < -0.10), 'BALANCED'
      - cvd_change_pct: relative change vs prior half of window (momentum proxy)

    Args:
        pair:  Trading pair in CCXT format (e.g. 'BTC/USDT')
        limit: Number of recent trades to fetch (default 500; OKX max 500)

    Returns:
        dict: {cvd, cvd_change_pct, buy_vol, sell_vol, imbalance, signal, source, error}
    """
    cache_key = pair
    with _CVD_LOCK:
        cached = _CVD_CACHE.get(cache_key, {})
        if cached.get("_ts", 0) + _CVD_TTL > time.time():
            return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        okx_symbol = pair.replace("/", "-") + "-SWAP"  # BTC/USDT → BTC-USDT-SWAP
        url = f"https://www.okx.com/api/v5/market/trades?instId={okx_symbol}&limit={limit}"
        resp = requests.get(url, timeout=8)

        if resp.status_code == 429:
            logging.debug(f"[CVD] OKX rate limited for {pair}")
            return dict(_CVD_NEUTRAL)
        if resp.status_code != 200:
            return {**_CVD_NEUTRAL, "error": f"HTTP {resp.status_code}"}

        data = resp.json().get("data", [])
        if not data:
            return {**_CVD_NEUTRAL, "error": "No trade data"}

        buy_vol = 0.0
        sell_vol = 0.0
        half = len(data) // 2
        buy_vol_first = 0.0
        sell_vol_first = 0.0

        for i, trade in enumerate(data):
            sz = float(trade.get("sz") or 0)
            side = str(trade.get("side", "")).lower()
            # OKX: side == 'buy' = taker buy (aggressive buyer hitting ask)
            if side == "buy":
                buy_vol += sz
                if i >= half:
                    buy_vol_first += sz
            else:
                sell_vol += sz
                if i >= half:
                    sell_vol_first += sz

        total_vol = buy_vol + sell_vol
        cvd = buy_vol - sell_vol
        imbalance = cvd / total_vol if total_vol > 0 else 0.0

        # CVD momentum: compare first half vs second half of window
        # data[0] is most recent trade; data[-1] is oldest
        cvd_recent = (buy_vol - buy_vol_first) - (sell_vol - sell_vol_first)  # second (newer) half
        cvd_older  = (buy_vol_first - sell_vol_first)                         # first (older) half
        cvd_change_pct = ((cvd_recent - cvd_older) / (abs(cvd_older) + 1e-6)) * 100

        # Signal classification
        if imbalance > 0.10:
            signal = "BUY_PRESSURE"
        elif imbalance < -0.10:
            signal = "SELL_PRESSURE"
        else:
            signal = "BALANCED"

        result = {
            "cvd":            round(cvd, 4),
            "cvd_change_pct": round(cvd_change_pct, 2),
            "buy_vol":        round(buy_vol, 4),
            "sell_vol":       round(sell_vol, 4),
            "imbalance":      round(imbalance, 4),
            "signal":         signal,
            "source":         "okx_trades",
            "error":          None,
            "_ts":            time.time(),
        }
        with _CVD_LOCK:
            _CVD_CACHE[cache_key] = result

        return {k: v for k, v in result.items() if k != "_ts"}

    except Exception as e:
        logging.debug(f"[CVD] {pair}: {e}")
        return {**_CVD_NEUTRAL, "error": str(e)}


def get_cvd_batch(pairs: list) -> dict:
    """Fetch CVD for all pairs in parallel. Returns {pair: cvd_dict}."""
    if not pairs:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(pairs), 4)) as ex:
        futures = {pair: ex.submit(get_cvd, pair) for pair in pairs}
    return {pair: f.result() for pair, f in futures.items()}


# ══════════════════════════════════════════════════════════════════════════════
# FEAR & GREED INDEX  (alternative.me — free, no key required)
# The single most powerful free macro-timing signal:
#   Score < 20 = Extreme Fear → historically strong buy zone (78% win rate, 30d)
#   Score > 80 = Extreme Greed → historically strong trim zone (contrarian)
# Updates daily at midnight UTC.  15-minute in-memory cache.
# ══════════════════════════════════════════════════════════════════════════════

_FNG_CACHE: dict = {}
_FNG_LOCK  = threading.Lock()
_FNG_TTL   = 900   # 15-minute cache (index only updates daily but we cache shorter so first load is fast)

_FNG_NEUTRAL = {
    "value": 50,
    "classification": "Neutral",
    "signal": "NEUTRAL",
    "score_bias": 0.0,       # additive confidence adjustment (-10 to +10)
    "history_7d": [],        # list of (value, classification) for last 7 days
    "source": "fallback",
    "error": "Fear & Greed unavailable",
}


def get_fear_greed_index(days: int = 7) -> dict:
    """
    Fetch the Crypto Fear & Greed Index from alternative.me (free, no API key).

    Returns:
        value           : int 0-100
        classification  : 'Extreme Fear' | 'Fear' | 'Neutral' | 'Greed' | 'Extreme Greed'
        signal          : 'STRONG_BUY' | 'BUY' | 'NEUTRAL' | 'SELL' | 'STRONG_SELL'
        score_bias      : float [-10, +10] — additive confidence adjustment
        history_7d      : list of last 7 days [{value, classification}]
        source          : 'alternative.me' | 'fallback'

    Signal mapping (research-validated thresholds):
        0-15   Extreme Fear  → STRONG_BUY  (+10 bias)   78% hit rate in 30d
        16-30  Fear          → BUY         (+5  bias)
        31-55  Neutral       → NEUTRAL     (0   bias)
        56-74  Greed         → SELL        (-5  bias)
        75-100 Extreme Greed → STRONG_SELL (-10 bias)
    """
    with _FNG_LOCK:
        cached = _FNG_CACHE.get("data")
        if cached and (time.time() - _FNG_CACHE.get("_ts", 0)) < _FNG_TTL:
            return cached

    try:
        resp = requests.get(
            f"https://api.alternative.me/fng/?limit={max(days, 7)}",
            timeout=8,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            data_list = resp.json().get("data", [])
            if data_list:
                current = data_list[0]
                value   = int(current.get("value", 50))
                classif = current.get("value_classification", "Neutral")

                # Signal + bias mapping
                if value <= 15:
                    signal, bias = "STRONG_BUY",  +10.0
                elif value <= 30:
                    signal, bias = "BUY",          +5.0
                elif value <= 55:
                    signal, bias = "NEUTRAL",       0.0
                elif value <= 74:
                    signal, bias = "SELL",          -5.0
                else:
                    signal, bias = "STRONG_SELL", -10.0

                history = [
                    {"value": int(d.get("value", 50)),
                     "classification": d.get("value_classification", "Neutral")}
                    for d in data_list[:7]
                ]

                result = {
                    "value":          value,
                    "classification": classif,
                    "signal":         signal,
                    "score_bias":     bias,
                    "history_7d":     history,
                    "source":         "alternative.me",
                    "error":          None,
                }
                with _FNG_LOCK:
                    _FNG_CACHE["data"] = result
                    _FNG_CACHE["_ts"]  = time.time()
                return result

        elif resp.status_code == 429:
            logging.debug("[F&G] rate limited — reusing cache")

    except Exception as e:
        logging.debug(f"[F&G] fetch failed: {e}")

    # Return stale cache if available, else neutral
    with _FNG_LOCK:
        return _FNG_CACHE.get("data", dict(_FNG_NEUTRAL))


# ══════════════════════════════════════════════════════════════════════════════
# LIQUIDATION CASCADE RISK SCORE
# Combines funding rate extremity + open interest level + orderbook imbalance
# to produce a 0-100 risk score.  No API key required.
#
# Research basis (2024-2025):
#   Persistent positive funding (>0.1%/8h for 7+ days) + OI growth + price
#   stagnation predicted 6/7 major BTC corrections in 2023-2024.
#   Score > 70 = high cascade risk within 24-48 hours.
# ══════════════════════════════════════════════════════════════════════════════

_CASCADE_CACHE: dict = {}
_CASCADE_LOCK  = threading.Lock()
_CASCADE_TTL   = 120   # 2-minute cache (fast-moving signal)


def get_liquidation_cascade_risk(pair: str) -> dict:
    """
    Compute a 0-100 Liquidation Cascade Risk score from freely available data.

    Components:
      1. Funding rate extremity (0-40 pts)
         |funding_rate| maps to 0-40 pts; >0.1%/8h → max bearish risk
      2. OI signal (0-30 pts)
         HIGH OI + rising funding → elevated liquidation cluster
      3. Orderbook imbalance (0-20 pts)
         Heavy ask pressure alongside elevated funding amplifies risk
      4. IV (volatility) boost (0-10 pts)
         High options IV → market expects large move → cascade more likely

    Returns:
        score        : int 0-100
        risk_level   : 'LOW' | 'MODERATE' | 'HIGH' | 'EXTREME'
        direction    : 'LONG_CASCADE' | 'SHORT_CASCADE' | 'NEUTRAL'
        signal       : 'CAUTION' | 'WARNING' | 'DANGER' | 'SAFE'
        components   : dict of sub-scores for transparency
        source       : 'computed'
    """
    now = time.time()
    with _CASCADE_LOCK:
        cached = _CASCADE_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _CASCADE_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    try:
        # Fetch components in parallel
        with ThreadPoolExecutor(max_workers=3) as ex:
            fr_fut  = ex.submit(get_funding_rate, pair)
            oi_fut  = ex.submit(get_open_interest, pair)
            ob_fut  = ex.submit(get_orderbook_depth, pair)

        fr_data = fr_fut.result()
        oi_data = oi_fut.result()
        ob_data = ob_fut.result()

        # ── Component 1: Funding rate extremity (0-40 pts) ───────────────────
        fr_pct  = abs(fr_data.get("funding_rate_pct", 0.0))
        fr_raw  = fr_data.get("funding_rate", 0.0)
        # Scale: 0% → 0 pts, 0.1% → 40 pts (cap)
        fr_score = min(40.0, fr_pct / 0.1 * 40.0)

        # ── Component 2: OI level (0-30 pts) ─────────────────────────────────
        oi_signal = oi_data.get("signal", "NORMAL")
        oi_score  = {"HIGH": 30.0, "NORMAL": 10.0, "LOW": 0.0, "N/A": 5.0}.get(oi_signal, 5.0)

        # ── Component 3: Orderbook imbalance (0-20 pts) ───────────────────────
        ob_imb   = ob_data.get("imbalance", 0.0)
        ob_signal = ob_data.get("signal", "BALANCED")
        # If funding is positive (longs heavy) + ask pressure → long cascade risk
        # If funding is negative (shorts heavy) + bid pressure → short cascade risk
        if (fr_raw > 0 and ob_signal == "SELL_PRESSURE") or \
           (fr_raw < 0 and ob_signal == "BUY_PRESSURE"):
            ob_score = min(20.0, abs(ob_imb) * 200.0)   # amplified agreement
        else:
            ob_score = min(10.0, abs(ob_imb) * 100.0)   # partial disagreement

        # ── Component 4: IV boost (0-10 pts) ─────────────────────────────────
        try:
            iv_data  = get_options_iv(pair)
            iv_sig   = iv_data.get("signal", "NORMAL")
            iv_score = {"EXTREME_FEAR": 10.0, "FEAR": 7.0, "NORMAL": 3.0,
                        "COMPLACENCY": 0.0, "N/A": 3.0}.get(iv_sig, 3.0)
        except Exception:
            iv_score = 3.0

        total_score = int(min(100, fr_score + oi_score + ob_score + iv_score))

        # Risk level
        if total_score >= 75:
            risk_level, signal_label = "EXTREME", "DANGER"
        elif total_score >= 55:
            risk_level, signal_label = "HIGH",    "WARNING"
        elif total_score >= 35:
            risk_level, signal_label = "MODERATE","CAUTION"
        else:
            risk_level, signal_label = "LOW",     "SAFE"

        # Direction — are longs or shorts at risk?
        if fr_raw > 0.0003:
            direction = "LONG_CASCADE"    # longs overpaying → if price drops they get wiped
        elif fr_raw < -0.0003:
            direction = "SHORT_CASCADE"   # shorts overpaying → if price rises they get wiped
        else:
            direction = "NEUTRAL"

        result = {
            "score":       total_score,
            "risk_level":  risk_level,
            "direction":   direction,
            "signal":      signal_label,
            "components":  {
                "funding_score": round(fr_score, 1),
                "oi_score":      round(oi_score, 1),
                "ob_score":      round(ob_score, 1),
                "iv_score":      round(iv_score, 1),
            },
            "funding_pct": fr_data.get("funding_rate_pct", 0.0),
            "source":      "computed",
            "error":       None,
            "_ts":         now,
        }
        with _CASCADE_LOCK:
            _CASCADE_CACHE[pair] = result
        return {k: v for k, v in result.items() if k != "_ts"}

    except Exception as e:
        logging.debug(f"[CascadeRisk] {pair}: {e}")
        result = {
            "score": 25, "risk_level": "LOW", "direction": "NEUTRAL",
            "signal": "SAFE", "components": {}, "funding_pct": 0.0,
            "source": "fallback", "error": str(e), "_ts": now,
        }
        with _CASCADE_LOCK:
            _CASCADE_CACHE[pair] = result
        return {k: v for k, v in result.items() if k != "_ts"}


def get_cascade_risk_batch(pairs: list) -> dict:
    """Fetch liquidation cascade risk for all pairs in parallel."""
    if not pairs:
        return {}
    with ThreadPoolExecutor(max_workers=min(len(pairs), 4)) as ex:
        futures = {pair: ex.submit(get_liquidation_cascade_risk, pair) for pair in pairs}
    return {pair: f.result() for pair, f in futures.items()}


# ══════════════════════════════════════════════════════════════════════════════
# COINGECKO TOP MOVERS  (free, no key)
# Returns top gainers and losers for the current 24h period.
# Used by the dashboard "Top Movers" bento card.
# 5-minute cache.
# ══════════════════════════════════════════════════════════════════════════════

_MOVERS_CACHE: dict = {}
_MOVERS_LOCK  = threading.Lock()
_MOVERS_TTL   = 300   # 5-minute cache

_WATCHED_IDS = [
    "bitcoin", "ethereum", "solana", "ripple", "dogecoin",
    "binancecoin", "cardano", "avalanche-2", "matic-network",
    "chainlink", "litecoin", "polkadot", "uniswap", "cosmos",
    "near", "filecoin",
]


def get_top_movers(top_n: int = 3) -> dict:
    """
    Return top N gainers and losers (by 24h % change) among the watched pairs.

    Returns:
        gainers  : list of {symbol, name, price_change_24h_pct, current_price}
        losers   : list of {symbol, name, price_change_24h_pct, current_price}
        source   : 'coingecko' | 'fallback'
        error    : str | None
    """
    now = time.time()
    with _MOVERS_LOCK:
        cached = _MOVERS_CACHE.get("data")
        if cached and (now - _MOVERS_CACHE.get("_ts", 0)) < _MOVERS_TTL:
            return cached

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency":    "usd",
                "ids":            ",".join(_WATCHED_IDS),
                "order":          "market_cap_desc",
                "per_page":       str(len(_WATCHED_IDS)),
                "page":           "1",
                "sparkline":      "false",
                "price_change_percentage": "24h",
            },
            timeout=10,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            coins = resp.json()
            ranked = sorted(
                [c for c in coins if c.get("price_change_percentage_24h") is not None],
                key=lambda c: c["price_change_percentage_24h"],
                reverse=True,
            )
            def _fmt(c: dict) -> dict:
                return {
                    "symbol":              c.get("symbol", "").upper(),
                    "name":                c.get("name", ""),
                    "price_change_24h_pct":round(float(c.get("price_change_percentage_24h", 0)), 2),
                    "current_price":       float(c.get("current_price", 0)),
                }
            result = {
                "gainers": [_fmt(c) for c in ranked[:top_n]],
                "losers":  [_fmt(c) for c in ranked[-top_n:][::-1]],
                "source":  "coingecko",
                "error":   None,
            }
            with _MOVERS_LOCK:
                _MOVERS_CACHE["data"] = result
                _MOVERS_CACHE["_ts"]  = now
            return result
        elif resp.status_code == 429:
            logging.debug("[Movers] CoinGecko rate limited — reusing cache")
    except Exception as e:
        logging.debug(f"[Movers] fetch failed: {e}")

    with _MOVERS_LOCK:
        return _MOVERS_CACHE.get("data", {
            "gainers": [], "losers": [], "source": "fallback",
            "error": "Top movers unavailable",
        })


# ──────────────────────────────────────────────
# CRYPTOPANIC — Free News Sentiment
# Free API token required (sign up at cryptopanic.com — free tier)
# Returns recent headlines + bullish/bearish vote breakdown
# ──────────────────────────────────────────────

_NEWS_CACHE: dict  = {}   # {pair: {result..., "_ts": float}}
_NEWS_CACHE_LOCK   = threading.Lock()
_NEWS_CACHE_TTL    = 900  # 15-minute cache

# Map base currency to CryptoPanic currency code
_CP_COIN_MAP: dict[str, str] = {
    "BTC": "BTC", "ETH": "ETH", "SOL": "SOL", "BNB": "BNB",
    "XRP": "XRP", "ADA": "ADA", "DOGE": "DOGE", "AVAX": "AVAX",
    "DOT": "DOT", "LINK": "LINK", "MATIC": "MATIC", "LTC": "LTC",
    "UNI": "UNI", "ATOM": "ATOM",
}


def get_news_sentiment(pair: str, max_articles: int = 5) -> dict:
    """
    Fetch recent CryptoPanic news and compute bullish/bearish sentiment for a pair.

    Requires `cryptopanic_key` in alerts_config.json (free at cryptopanic.com).
    Returns:
        signal:       'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'N/A'
        bullish_pct:  float (0-100), percentage of positive votes
        bearish_pct:  float (0-100)
        total_votes:  int
        articles:     list[dict] with title, url, published_at, kind, domain
        source:       'CryptoPanic'
    """
    now = time.time()
    with _NEWS_CACHE_LOCK:
        cached = _NEWS_CACHE.get(pair, {})
        if cached.get("_ts", 0) + _NEWS_CACHE_TTL > now:
            return {k: v for k, v in cached.items() if k != "_ts"}

    # Get API key
    keys = _load_api_keys()
    token = keys.get("cryptopanic_key", "")
    if not token:
        return _no_key_result("cryptopanic",
                              "News sentiment: CryptoPanic free token — sign up at cryptopanic.com")

    # Resolve coin symbol from pair (e.g. "BTC/USDT" → "BTC")
    base = pair.split("/")[0].upper()
    coin = _CP_COIN_MAP.get(base, base)

    try:
        resp = requests.get(
            "https://cryptopanic.com/api/free/v1/posts/",
            params={
                "auth_token": token,
                "currencies": coin,
                "filter":     "hot",
                "public":     "true",
                "kind":       "news",
            },
            timeout=8,
        )
        if resp.status_code == 403:
            result = _no_key_result("cryptopanic", "Invalid or expired API token")
            with _NEWS_CACHE_LOCK:
                _NEWS_CACHE[pair] = {**result, "_ts": now}
            return result
        if resp.status_code != 200:
            logging.debug("CryptoPanic %s HTTP %s", pair, resp.status_code)
            result = _no_key_result("cryptopanic", f"HTTP {resp.status_code}")
            with _NEWS_CACHE_LOCK:
                _NEWS_CACHE[pair] = {**result, "_ts": now}
            return result

        posts = resp.json().get("results", [])
        if not posts:
            result = {
                "signal": "NEUTRAL", "bullish_pct": 50.0, "bearish_pct": 50.0,
                "total_votes": 0, "articles": [], "source": "CryptoPanic",
            }
            with _NEWS_CACHE_LOCK:
                _NEWS_CACHE[pair] = {**result, "_ts": now}
            return result

        # Aggregate votes across recent posts
        total_pos = 0
        total_neg = 0
        articles  = []
        for p in posts[:20]:   # use up to 20 posts for vote aggregation
            v = p.get("votes", {}) or {}
            total_pos += int(v.get("positive", 0) or 0)
            total_neg += int(v.get("negative", 0) or 0)
            if len(articles) < max_articles:
                articles.append({
                    "title":        p.get("title", ""),
                    "url":          p.get("url", ""),
                    "published_at": (p.get("published_at") or "")[:16],
                    "kind":         p.get("kind", "news"),
                    "domain":       p.get("domain", ""),
                })

        total_votes = total_pos + total_neg
        if total_votes > 0:
            bullish_pct = round(total_pos / total_votes * 100, 1)
            bearish_pct = round(total_neg / total_votes * 100, 1)
        else:
            bullish_pct = bearish_pct = 50.0

        if   bullish_pct >= 60: signal = "BULLISH"
        elif bearish_pct >= 60: signal = "BEARISH"
        else:                   signal = "NEUTRAL"

        result = {
            "signal":      signal,
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "total_votes": total_votes,
            "articles":    articles,
            "source":      "CryptoPanic",
        }
        with _NEWS_CACHE_LOCK:
            _NEWS_CACHE[pair] = {**result, "_ts": now}
        return result

    except Exception as _e:
        logging.debug("CryptoPanic %s: %s", pair, _e)
        result = _no_key_result("cryptopanic", str(_e))
        with _NEWS_CACHE_LOCK:
            _NEWS_CACHE[pair] = {**result, "_ts": now}
        return result


# ──────────────────────────────────────────────
# FEAR & GREED INDEX — Free, no API key
# Source: alternative.me — updates daily, contrarian signal
# ──────────────────────────────────────────────

_FNG2_CACHE: dict = {"value": None, "label": None, "_ts": 0.0}
_FNG2_LOCK = threading.Lock()
_FNG2_TTL  = 3600  # 1-hour cache (index updates daily — no need to hammer)


def get_fear_greed() -> dict:
    """
    Fetch the current Crypto Fear & Greed Index from Alternative.me (free, no auth).
    Returns {'value': int, 'label': str, 'bias': float, 'signal': str, 'error': str|None}

    Contrarian interpretation (research-backed):
      - Extreme Fear (0-20)  → market oversold → BUY bias
      - Fear (21-40)         → mild BUY bias
      - Neutral (41-59)      → no bias
      - Greed (60-79)        → mild SELL bias
      - Extreme Greed (80+)  → market overbought → SELL bias

    bias: float in [-10, +10] for confidence score adjustment.
    Positive = bullish bias, negative = bearish bias.
    """
    now = time.time()
    with _FNG2_LOCK:
        if _FNG2_CACHE["value"] is not None and now - _FNG2_CACHE["_ts"] < _FNG2_TTL:
            c = _FNG2_CACHE
            return {
                "value":  c["value"],
                "label":  c["label"],
                "bias":   c["bias"],
                "signal": c["signal"],
                "error":  None,
            }

    try:
        resp = requests.get(
            "https://api.alternative.me/fng/",
            params={"limit": 1},
            timeout=8,
        )
        if resp.status_code != 200:
            return {"value": 50, "label": "Neutral", "bias": 0.0, "signal": "NEUTRAL",
                    "error": f"HTTP {resp.status_code}"}
        # DF-03: guard against missing/empty "data" key from malformed API response
        _fng_items = resp.json().get("data", [])
        if not _fng_items:
            return {"value": 50, "label": "Neutral", "bias": 0.0, "signal": "NEUTRAL",
                    "error": "Empty data from alternative.me"}
        data  = _fng_items[0]
        value = int(data.get("value", 50))
        label = data.get("value_classification", "Neutral")

        # Contrarian bias calculation
        if value <= 20:
            bias, signal = +10.0, "EXTREME_FEAR_BUY"
        elif value <= 40:
            bias, signal = +5.0,  "FEAR_BUY"
        elif value <= 59:
            bias, signal = 0.0,   "NEUTRAL"
        elif value <= 79:
            bias, signal = -5.0,  "GREED_SELL"
        else:
            bias, signal = -10.0, "EXTREME_GREED_SELL"

        result = {"value": value, "label": label, "bias": bias, "signal": signal, "error": None}
        with _FNG2_LOCK:
            _FNG2_CACHE.update({**result, "_ts": now})
        return result
    except Exception as e:
        logging.warning("Fear & Greed fetch failed: %s", e)
        return {"value": 50, "label": "Neutral", "bias": 0.0, "signal": "NEUTRAL", "error": str(e)}


def get_fear_greed_bias() -> float:
    """
    Returns a confidence score bias in points (-10 to +10) from the Fear & Greed Index.
    Positive = bullish contrarian bias (extreme fear → buy), negative = bearish (extreme greed → sell).
    Used as an additive adjustment in calculate_signal_confidence() and agent scoring.
    """
    try:
        return get_fear_greed()["bias"]
    except Exception:
        return 0.0


# ──────────────────────────────────────────────
# EXPONENTIAL BACKOFF RETRY WRAPPER
# ──────────────────────────────────────────────

def _with_retry(fn, *args, max_attempts: int = 3, base_delay: float = 1.0, **kwargs):
    """
    Call fn(*args, **kwargs) with exponential backoff on exception.
    Retries up to max_attempts times: delays 1s, 2s, 4s, ...

    Use this wrapper on any external API call that needs resilience:
      result = _with_retry(requests.get, url, params=params, timeout=8)

    Raises the last exception if all attempts fail.
    Circuit-breaker note: callers should handle None / error dicts from their own
    functions instead of using this for functions that return neutral fallbacks.
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logging.debug("_with_retry: attempt %d/%d failed (%s) — retrying in %.1fs",
                              attempt + 1, max_attempts, e, delay)
                time.sleep(delay)
    raise last_exc
