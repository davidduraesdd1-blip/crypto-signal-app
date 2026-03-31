"""
data_feeds.py — External data feed helpers for Crypto Signal Model v5.9.13
Fetches supplementary market data (funding rates, on-chain proxies, open interest)
from free public APIs. No API keys required.
"""
from __future__ import annotations

import base64
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    import ccxt
    _CCXT_AVAILABLE = True
except ImportError:
    _CCXT_AVAILABLE = False
    logging.warning("ccxt not installed — new exchange funding rates will be unavailable")

# ─── HTTP Session with retry adapter (#12 security hardening) ────────────────
def _build_session() -> requests.Session:
    """Build a requests.Session with exponential backoff retry and browser User-Agent."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=30, pool_connections=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    })
    return session


_SESSION = _build_session()

# ─── FRED-specific session: low retries, short timeout (FRED is non-critical) ─
def _build_fred_session() -> requests.Session:
    """Minimal-retry session for FRED CSV endpoints — non-critical macro data."""
    session = requests.Session()
    retry = Retry(
        total=1,
        read=0,                          # never retry on ReadTimeout
        backoff_factor=0,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=5, pool_connections=2)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"})
    return session

_FRED_SESSION = _build_fred_session()

# ─── Rate Limiter (token bucket — #11 security hardening) ────────────────────
class RateLimiter:
    """Token bucket rate limiter for API calls."""
    def __init__(self, calls_per_second: float = 1.0):
        if calls_per_second <= 0:
            raise ValueError(
                f"RateLimiter: calls_per_second must be > 0, got {calls_per_second!r}. "
                "A zero rate would cause acquire() to busy-loop until timeout."
            )
        self._rate = calls_per_second
        self._tokens = calls_per_second
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                now = time.time()
                elapsed = now - self._last_refill
                self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            time.sleep(0.05)
        return False


# Keep legacy alias for backwards compat
_RateLimiter = RateLimiter

_BINANCE_LIMITER   = RateLimiter(calls_per_second=5.0)   # Binance allows ~1200/min
_COINGECKO_LIMITER = RateLimiter(calls_per_second=0.4)   # 25 req/min free
_DERIBIT_LIMITER   = RateLimiter(calls_per_second=2.0)   # Deribit: generous
_EXCHANGE_LIMITER  = RateLimiter(calls_per_second=1.0)   # Generic for other exchanges

# Legacy module-level limiters (kept for any callers that reference them)
_bybit_limiter    = _BINANCE_LIMITER
_binance_limiter  = _BINANCE_LIMITER
_coingecko_limiter = _COINGECKO_LIMITER
_default_limiter  = _EXCHANGE_LIMITER

# SSRF allowlist — only fetch from these known-safe domains
_ALLOWED_HOSTS: frozenset = frozenset({
    "api.alternative.me", "api.bybit.com", "www.okx.com", "api.kucoin.com",
    "api-futures.kucoin.com", "api.coingecko.com", "api.binance.com",
    "api.binance.us", "api.stlouisfed.org", "api.coinalyze.net",
    "lunarcrush.com", "cryptopanic.com", "dogechain.info",
    "fapi.binance.com",  # kept for reference, geo-blocked but safe
    # Phase 9 additions
    "api.mexc.com", "bitso.com", "api.bitso.com", "api.coindcx.com",  # regional exchanges (#89)
    "price.jup.ag", "indexer.dydx.trade", "api.raydium.io",  # DEX feeds (#91)
    # Phase 13 additions — new exchanges and data sources
    "www.deribit.com",                          # Deribit options OI + IV
    "api.exchangerate-api.com",                 # FX rates for regional premiums
    "pro-api.coinmarketcap.com",                # CoinMarketCap global metrics
    "api.mercadobitcoin.net",                   # Mercado Bitcoin (BRL)
    "api.upbit.com",                            # Upbit (KRW)
    "api.bitfinex.com",                         # Bitfinex
    "api.phemex.com",                           # Phemex
    "api.woox.io",                              # WOO X
    "api.bithumb.com",                          # Bithumb
    "api.crypto.com",                           # Crypto.com
    "ascendex.com",                             # AscendEX
    "api.lbank.info",                           # LBank
    "api.coinex.com",                           # CoinEx
    # Batch 3 additions (#41) — new CeFi exchanges
    "api.huobi.pro",                            # HTX (formerly Huobi)
    "www.bitstamp.net",                         # Bitstamp
    "api.bitget.com",                           # Bitget
    # Batch 7 additions (#110/#111) — wallet portfolio
    "api.zerion.io",                            # Zerion portfolio API
    "api.etherscan.io",                         # Etherscan token list fallback
})


def _ssrf_check(url: str) -> bool:
    """Return True if the URL hostname is on the allowlist."""
    try:
        host = urlparse(url).hostname or ""
        return any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS)
    except Exception:
        return False

# ──────────────────────────────────────────────
# BINANCE FUTURES FUNDING RATES
# Public endpoint — no auth required
# ──────────────────────────────────────────────

_BINANCE_PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"  # geo-blocked for US; kept for reference only — not called
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
        resp = _SESSION.get(_OKX_FUNDING_URL, params={"instId": inst_id}, timeout=6)
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

    # 2. Bybit (no US geo-block — replaces fapi.binance.com)
    try:
        resp = _SESSION.get(_BYBIT_TICKERS_URL, params={"category": "linear", "symbol": symbol}, timeout=6)
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
    # Core
    'BTC/USDT': 'bitcoin',       'ETH/USDT': 'ethereum',       'SOL/USDT': 'solana',
    'XRP/USDT': 'ripple',        'DOGE/USDT': 'dogecoin',      'BNB/USDT': 'binancecoin',
    # Tier 1
    'TRX/USDT': 'tron',          'ADA/USDT': 'cardano',        'BCH/USDT': 'bitcoin-cash',
    'LINK/USDT': 'chainlink',    'LTC/USDT': 'litecoin',       'AVAX/USDT': 'avalanche-2',
    'XLM/USDT': 'stellar',       'SUI/USDT': 'sui',            'TAO/USDT': 'bittensor',
    # Tier 2
    'NEAR/USDT': 'near',         'APT/USDT': 'aptos',          'POL/USDT': 'matic-network',
    'OP/USDT': 'optimism',       'ARB/USDT': 'arbitrum',       'ATOM/USDT': 'cosmos',
    'FIL/USDT': 'filecoin',      'INJ/USDT': 'injective-protocol', 'PENDLE/USDT': 'pendle',
    'WIF/USDT': 'dogwifcoin',    'PYTH/USDT': 'pyth-network',  'JUP/USDT': 'jupiter-exchange-solana',
    'HBAR/USDT': 'hedera-hashgraph', 'FLR/USDT': 'flare-networks',
    # Legacy (kept for backwards compat)
    'MATIC/USDT': 'matic-network', 'DOT/USDT': 'polkadot',    'UNI/USDT': 'uniswap',
}

_CG_BASE = "https://api.coingecko.com/api/v3"
_BINANCE_SPOT_BASE = "https://api.binance.com/api/v3"


# ──────────────────────────────────────────────
# BINANCE PUBLIC API — spot klines + 24hr ticker
# Free, unlimited, no API key required
# ──────────────────────────────────────────────

def fetch_binance_klines(symbol: str, interval: str = "1h", limit: int = 100) -> list:
    """
    Fetch OHLCV candlestick data from Binance spot public API.
    symbol: e.g. "BTCUSDT", interval: "1m","5m","15m","1h","4h","1d","1w"
    Returns list of [open_ts, open, high, low, close, volume, close_ts, ...] rows.
    Free, no API key, no rate-limit issues for reasonable usage.
    """
    try:
        r = _SESSION.get(
            f"{_BINANCE_SPOT_BASE}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=8,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logging.debug("[Binance klines] %s/%s failed: %s", symbol, interval, e)
    return []


def fetch_bybit_klines(symbol: str, interval: str = "1h", limit: int = 100) -> list:
    """
    Fetch OHLCV candlestick data from Bybit V5 spot public API.
    Not geo-blocked from US servers (unlike Binance which returns HTTP 451).
    symbol: e.g. "BTCUSDT"
    interval: "1h", "4h", "1d", "1w" (mapped to Bybit values: 60, 240, D, W)
    Returns list of [startTime, open, high, low, close, volume] rows (oldest-first).
    """
    _interval_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30",
                     "1h": "60", "4h": "240", "1d": "D", "1w": "W"}
    bybit_interval = _interval_map.get(interval, "60")
    try:
        r = _SESSION.get(
            "https://api.bybit.com/v5/market/kline",
            params={"category": "spot", "symbol": symbol,
                    "interval": bybit_interval, "limit": limit},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            rows = data.get("result", {}).get("list", [])
            # Bybit returns newest-first; reverse to oldest-first for consistency
            rows = list(reversed(rows))
            # fields: [startTime, open, high, low, close, volume, turnover]
            # Return as [startTime(int), open, high, low, close, volume] to match Binance format
            return [[int(row[0]), row[1], row[2], row[3], row[4], row[5]]
                    for row in rows if len(row) >= 6]
    except Exception as e:
        logging.debug("[Bybit klines] %s/%s failed: %s", symbol, interval, e)
    return []


def _fetch_binance_24hr(symbol: str) -> dict | None:
    """Fetch 24hr stats from Binance spot API. Returns raw dict or None."""
    try:
        r = _SESSION.get(
            f"{_BINANCE_SPOT_BASE}/ticker/24hr",
            params={"symbol": symbol},
            timeout=6,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logging.debug("[Binance 24hr] %s failed: %s", symbol, e)
    return None


def _fallback_onchain() -> dict:
    return {
        'sopr': 1.0, 'mvrv_z': 0.0, 'net_flow': 0.0,
        'whale_activity': False, 'source': 'fallback',
        'vol_mcap_ratio': 0.0, 'price_24h_pct': 0.0, 'price_200d_pct': 0.0,
    }


def get_onchain_metrics(pair: str) -> dict:
    """
    On-chain proxy metrics. Primary: Binance spot 24hr ticker (free, unlimited).
    Fallback: CoinGecko free API (rate-limited, used for 200d price change only).

    Fields:
      sopr          — SOPR proxy: 1 + 24h_price_change. >1 = profit-taking, <1 = capitulation.
      mvrv_z        — MVRV-Z proxy: 200d return scaled to MVRV-Z range.
      net_flow      — Exchange flow proxy: volume/mcap deviation scaled to ±400.
      whale_activity — True if volume > 10% of market cap (abnormal activity).
      vol_mcap_ratio — Raw volume/mcap ratio for display.
      price_24h_pct  — 24h price change %.
      price_200d_pct — 200-day price change %.
      source         — 'binance' | 'coingecko' | 'fallback'
    """
    now = time.time()
    with _ONCHAIN_CACHE_LOCK:
        cached = _ONCHAIN_CACHE.get(pair)
        if cached and (now - cached.get('_ts', 0)) < _ONCHAIN_TTL:
            return cached

    # ── Try Binance spot 24hr ticker (primary — free, unlimited) ──────────────
    binance_sym = pair.replace("/", "")  # BTC/USDT → BTCUSDT
    ticker = _fetch_binance_24hr(binance_sym)
    if ticker and "priceChangePercent" in ticker:
        try:
            price_24h  = float(ticker.get("priceChangePercent", 0))
            volume_usd = float(ticker.get("quoteVolume", 0))  # already in USDT
            price_now  = float(ticker.get("lastPrice", 0))
            # Estimate market cap via circulating supply proxy (not available from Binance,
            # so we use volume/price ratio as a relative proxy instead)
            # net_flow uses volume directly scaled to ±400 relative to a $1B baseline
            vol_mcap   = volume_usd / 1e9 if volume_usd else 0.0  # normalised to $1B units
            net_flow   = 0.0 if volume_usd == 0 else round(
                max(-400.0, min(400.0, (vol_mcap - 0.05) * 8000)), 1
            )
            sopr       = round(max(0.85, min(1.15, 1.0 + price_24h / 100)), 3)
            # 200d proxy: fetch 200 daily klines from Binance, compute % change
            price_200d = 0.0
            klines_200 = fetch_binance_klines(binance_sym, interval="1d", limit=201)
            if len(klines_200) >= 2:
                first_close = float(klines_200[0][4])
                last_close  = float(klines_200[-1][4])
                if first_close > 0:
                    price_200d = round((last_close - first_close) / first_close * 100, 2)
            mvrv_z     = round(max(-3.0, min(7.0, price_200d / 57.0)), 2)
            whale_activity = vol_mcap > 0.10

            result = {
                'sopr': sopr, 'mvrv_z': mvrv_z, 'net_flow': net_flow,
                'whale_activity': whale_activity, 'source': 'binance',
                'vol_mcap_ratio': round(vol_mcap, 4),
                'price_24h_pct': round(price_24h, 2),
                'price_200d_pct': price_200d,
                '_ts': now,
            }
            with _ONCHAIN_CACHE_LOCK:
                _ONCHAIN_CACHE[pair] = result
            return result
        except Exception as e:
            logging.debug("[Binance onchain] parse error for %s: %s", pair, e)

    # ── Fallback: CoinGecko (rate-limited — only used when Binance fails) ─────
    coin_id = _COIN_MAP.get(pair)
    if not coin_id:
        return _fallback_onchain()

    try:
        _COINGECKO_LIMITER.acquire()
        url = f"{_CG_BASE}/coins/{coin_id}"
        params = {
            'localization': 'false', 'tickers': 'false',
            'market_data': 'true', 'community_data': 'false',
            'developer_data': 'false', 'sparkline': 'false',
        }
        resp = _SESSION.get(url, params=params, timeout=10)
        if resp.status_code == 429:
            logging.warning(f"CoinGecko rate limited (429) for {pair} — using fallback")
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

        sopr = round(max(0.85, min(1.15, 1.0 + price_24h / 100)), 3)
        mvrv_z = round(max(-3.0, min(7.0, price_200d / 57.0)), 2)
        vol_mcap = volume / mcap if mcap > 0 else 0.0
        net_flow = 0.0 if volume == 0 else round(max(-400.0, min(400.0, (vol_mcap - 0.05) * 8000)), 1)
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
        resp = _SESSION.get(
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
        resp = _SESSION.get(
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
        resp = _SESSION.get(
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
        resp = _SESSION.get(_OKX_FUNDING_URL, params={"instId": inst_id}, timeout=6)
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
    """Fetch funding rate via Bybit v5 (no US geo-block — replaces fapi.binance.com)."""
    try:
        symbol = _binance_symbol(pair)
        resp = _SESSION.get(_BYBIT_TICKERS_URL, params={"category": "linear", "symbol": symbol}, timeout=6)
        if resp.status_code == 200:
            items = resp.json().get("result", {}).get("list", [])
            if items:
                parsed = _parse_bybit_item(items[0], now)
                if parsed:
                    return parsed
    except Exception as _e:
        logging.debug("_fetch_binance_fr (bybit) %s: %s", pair, _e)
    return _empty_result("Bybit N/A", now)


def _fetch_bybit_fr(pair: str, now: float) -> dict:
    """Fetch Bybit funding rate for a single pair."""
    try:
        symbol = _binance_symbol(pair)
        resp = _SESSION.get(
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
        resp = _SESSION.get(url, timeout=6)
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


# ──────────────────────────────────────────────
# CCXT-BASED FUNDING RATE FETCHERS
# 10 new exchanges: Bitfinex, MEXC, HTX, Phemex, WOO X,
# Bithumb, Crypto.com, AscendEX, LBank, CoinEx
# All use free public endpoints — no API key required
# ──────────────────────────────────────────────

# ccxt exchange singleton cache — avoid recreating on every call
_ccxt_exchange_cache: dict = {}
_ccxt_exchange_lock = threading.Lock()


def _get_ccxt_exchange(exchange_id: str):
    """Return a cached ccxt exchange instance (public mode, rate-limit enabled)."""
    if not _CCXT_AVAILABLE:
        return None
    with _ccxt_exchange_lock:
        if exchange_id not in _ccxt_exchange_cache:
            try:
                exchange_class = getattr(ccxt, exchange_id, None)
                if exchange_class is None:
                    return None
                _ccxt_exchange_cache[exchange_id] = exchange_class({
                    "enableRateLimit": True,
                    "timeout": 10000,
                })
            except Exception as _e:
                logging.debug("ccxt exchange init failed (%s): %s", exchange_id, _e)
                return None
        return _ccxt_exchange_cache[exchange_id]


def _fetch_ccxt_fr(exchange_id: str, pair: str, now: float) -> dict:
    """
    Fetch funding rate from a ccxt-supported exchange using fetch_funding_rate().
    Returns standard funding rate dict compatible with _empty_result() schema.
    Falls back to fetch_funding_rates() (bulk) if per-symbol call fails.
    """
    if not _CCXT_AVAILABLE:
        return _empty_result(f"{exchange_id}: ccxt not installed", now)
    ex = _get_ccxt_exchange(exchange_id)
    if ex is None:
        return _empty_result(f"{exchange_id}: not available in ccxt", now)

    # Determine which symbol format this exchange uses.
    # Most ccxt perpetual markets use "BTC/USDT:USDT" (unified margin format).
    # Build the perp symbol from the spot pair; fall back to spot if BadSymbol.
    if "/" in pair:
        base_asset, quote_asset = pair.split("/", 1)
        # Strip any existing settle suffix so we don't double-append
        quote_clean = quote_asset.split(":")[0]
        perp_symbol = f"{base_asset}/{quote_clean}:{quote_clean}"
    else:
        perp_symbol = pair
    base = pair.split("/")[0] if "/" in pair else pair

    try:
        # Attempt per-symbol fetch_funding_rate (most exchanges support this)
        fr_data = ex.fetch_funding_rate(perp_symbol)
        rate = float(fr_data.get("fundingRate") or 0.0)
        if rate == 0.0:
            # Some exchanges store it as fundingRates list or different key
            rate = float(fr_data.get("rate") or fr_data.get("funding_rate") or 0.0)
        _next_raw = fr_data.get("fundingDatetime") or fr_data.get("nextFundingDatetime") or 0
        try:
            # ccxt may return an ISO datetime string or a numeric ms timestamp
            next_ts = int(_next_raw) if not isinstance(_next_raw, str) else 0
        except (TypeError, ValueError):
            next_ts = 0
        mark_price = float(fr_data.get("markPrice") or fr_data.get("mark") or 0.0)
        return {
            "funding_rate":      rate,
            "funding_rate_pct":  round(rate * 100, 4),
            "next_funding_time": next_ts,
            "mark_price":        mark_price,
            "signal":            _funding_signal(rate),
            "source":            exchange_id,
            "error":             None,
            "_ts":               now,
        }
    except ccxt.BadSymbol:
        # Exchange doesn't list this pair — not an error, just N/A
        return _empty_result(f"{exchange_id}: pair not listed", now)
    except ccxt.NotSupported:
        # fetch_funding_rate not implemented — try fetch_funding_rates (bulk)
        try:
            rates_dict = ex.fetch_funding_rates([perp_symbol])
            fr_data = rates_dict.get(perp_symbol) or {}
            rate = float(fr_data.get("fundingRate") or fr_data.get("rate") or 0.0)
            return {
                "funding_rate":      rate,
                "funding_rate_pct":  round(rate * 100, 4),
                "next_funding_time": 0,
                "mark_price":        0.0,
                "signal":            _funding_signal(rate),
                "source":            exchange_id,
                "error":             None,
                "_ts":               now,
            }
        except Exception as _e2:
            logging.debug("_fetch_ccxt_fr bulk fallback %s %s: %s", exchange_id, pair, _e2)
            return _empty_result(f"{exchange_id} N/A", now)
    except Exception as _e:
        logging.debug("_fetch_ccxt_fr %s %s: %s", exchange_id, pair, _e)
        return _empty_result(f"{exchange_id} N/A", now)


def get_multi_exchange_funding_rates(pair: str) -> dict[str, dict]:
    """
    Fetch funding rates from OKX, Binance, Bybit, KuCoin, and 10 new ccxt exchanges
    for a single pair using parallel threads. Always returns all exchange keys;
    failed exchanges get an error-flagged result dict. 5-minute cache.

    Returns: {
      "okx": {...}, "binance": {...}, "bybit": {...}, "kucoin": {...},
      "bitfinex": {...}, "mexc": {...}, "htx": {...}, "phemex": {...},
      "woo": {...}, "bithumb": {...}, "cryptocom": {...}, "ascendex": {...},
      "lbank": {...}, "coinex": {...}
    }
    """
    now = time.time()
    with _MULTI_FR_LOCK:
        cached = _MULTI_FR_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _MULTI_FR_TTL:
            return cached["data"]

    # Core exchanges (direct REST — proven reliable)
    core_futs: dict = {}
    # New ccxt exchanges
    ccxt_exchanges = [
        "bitfinex", "mexc", "htx", "phemex", "woo",
        "bithumb", "cryptocom", "ascendex", "lbank", "coinex",
    ]

    with ThreadPoolExecutor(max_workers=14) as ex:
        core_futs = {
            "okx":     ex.submit(_fetch_okx_fr,    pair, now),
            "binance": ex.submit(_fetch_binance_fr, pair, now),
            "bybit":   ex.submit(_fetch_bybit_fr,   pair, now),
            "kucoin":  ex.submit(_fetch_kucoin_fr,  pair, now),
        }
        ccxt_futs = {
            exch_id: ex.submit(_fetch_ccxt_fr, exch_id, pair, now)
            for exch_id in ccxt_exchanges
        }
        result = {name: f.result() for name, f in {**core_futs, **ccxt_futs}.items()}

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

    # PERF-CARRY: pre-warm the multi-exchange funding rate cache for all pairs
    # in one parallel pass so each _scan_one() worker hits the in-memory cache
    # instead of making live HTTP calls.  get_multi_exchange_funding_rates() has
    # a 5-minute TTL and internal parallelism — pre-fetching here means each
    # _scan_one() call returns instantly from cache.
    with ThreadPoolExecutor(max_workers=min(len(pairs), 8)) as _pre_ex:
        list(_pre_ex.map(get_multi_exchange_funding_rates, pairs))

    all_opps: list[dict] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
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

    # 1. OKX — parallel per-symbol (PERF: was sequential loop; now concurrent)
    def _fetch_one_okx(pair: str) -> tuple[str, dict | None]:
        try:
            inst_id = _okx_inst_id(pair)
            resp = _SESSION.get(_OKX_FUNDING_URL, params={"instId": inst_id}, timeout=6)
            if resp.status_code == 200:
                data  = resp.json()
                items = data.get("data", [])
                if items and data.get("code") == "0":
                    return pair, _parse_okx_item(items[0], now)
        except Exception:
            pass
        return pair, None

    try:
        with ThreadPoolExecutor(max_workers=min(len(pairs), 8)) as ex:
            okx_results = dict(ex.map(_fetch_one_okx, pairs))
        okx_success = sum(1 for v in okx_results.values() if v is not None)
        if okx_success > 0:
            for pair, parsed in okx_results.items():
                if parsed:
                    results[pair] = parsed
                    with _FUNDING_CACHE_LOCK:
                        _BINANCE_FUNDING_CACHE[pair] = parsed
                else:
                    results[pair] = _empty_result("Not on OKX futures", now)
            return results
    except Exception:
        pass

    # 2. Per-symbol fallback (fapi.binance.com bulk removed — geo-blocked for US users)
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
                with open(_API_KEYS_FILE, "r", encoding="utf-8") as f:
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
    api_key = (
        os.environ.get("LUNARCRUSH_API_KEY", "").strip()
        or keys.get("lunarcrush_key", "").strip()
    )
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
        resp = _SESSION.get(
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
        resp = _SESSION.get(
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
        resp = _SESSION.get(
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

        # PERF: fetch SOPR and MVRV-Z in parallel instead of sequentially
        with ThreadPoolExecutor(max_workers=2) as _ex:
            _sopr_fut = _ex.submit(_SESSION.get, f"{base}/indicators/sopr",   params=params, headers=headers, timeout=10)
            _mvrv_fut = _ex.submit(_SESSION.get, f"{base}/market/mvrv_z_score", params=params, headers=headers, timeout=10)
            sopr_resp = _sopr_fut.result()
            mvrv_resp = _mvrv_fut.result()

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
        resp = _SESSION.get(
            f"https://api.llama.fi/v2/historicalChainTvl/{chain_name}",
            timeout=10,
        )
        if resp.status_code != 200:
            result = {**_neutral, 'chain': chain_name, 'error': f'HTTP {resp.status_code}', '_ts': now}
            with _TVL_CACHE_LOCK:
                _TVL_CACHE[pair] = result
            return result

        if not resp.text or not resp.text.strip():
            result = {**_neutral, 'chain': chain_name, 'error': 'Empty response', '_ts': now}
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
        resp = _SESSION.get(
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
        _cg_key = _get_runtime_key("coingecko_key", "")
        _cg_headers: dict = {"Accept": "application/json"}
        if _cg_key:
            _cg_headers["x-cg-pro-api-key"] = _cg_key
        resp = _SESSION.get(
            "https://api.coingecko.com/api/v3/search/trending",
            timeout=10,
            headers=_cg_headers,
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
        _cg_key = _get_runtime_key("coingecko_key", "")
        _cg_hdrs: dict = {"Accept": "application/json"}
        if _cg_key:
            _cg_hdrs["x-cg-pro-api-key"] = _cg_key
        resp = _SESSION.get(
            "https://api.coingecko.com/api/v3/global",
            timeout=10,
            headers=_cg_hdrs,
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
        resp = _SESSION.get(url, timeout=8)

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


# ─────────────────────────────────────────────────────────────────────────────
# CVD DIVERGENCE DETECTION  (#33)
# Uses last 24 hourly OHLCV candles (Binance free public klines).
# Approximates buy/sell volume from candle direction (close>open = buy candle).
# Detects bearish/bullish divergences between price and cumulative volume delta.
# 73% reversal rate on bearish divergence (research-backed).
# ─────────────────────────────────────────────────────────────────────────────

_CVD_DIV_CACHE: dict = {}
_CVD_DIV_LOCK  = threading.Lock()
_CVD_DIV_TTL   = 900   # 15-minute cache


def fetch_cvd_divergence(symbol: str = "BTC") -> dict:
    """
    Detect CVD (Cumulative Volume Delta) divergence using 24 hourly candles.

    Approximation: if close > open → bullish candle (buy_volume ≈ volume),
    else bearish candle (sell_volume ≈ volume). CVD = cumsum(buy_vol - sell_vol).

    Divergence rules:
      BEARISH: price makes new high but CVD makes lower high → 73% reversal rate
      BULLISH: price makes new low  but CVD makes higher low → bullish absorption

    Args:
        symbol: Base currency (e.g. "BTC") — appends "USDT" for Binance fetch.

    Returns:
        {
            "divergence":   "BEARISH" | "BULLISH" | "NONE",
            "price_trend":  str — description of price direction,
            "cvd_trend":    str — description of CVD direction,
            "confidence":   float 0.0–1.0 — divergence conviction,
            "signal":       "BEARISH_DIVERGENCE" | "BULLISH_DIVERGENCE" | "NO_DIVERGENCE",
            "source":       "binance_klines",
            "error":        str | None,
        }
    """
    cache_key = symbol.upper()
    now = time.time()
    with _CVD_DIV_LOCK:
        cached = _CVD_DIV_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _CVD_DIV_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    _neutral = {
        "divergence": "NONE", "price_trend": "UNKNOWN", "cvd_trend": "UNKNOWN",
        "confidence": 0.0, "signal": "NO_DIVERGENCE", "source": "fallback", "error": None,
    }

    try:
        binance_sym = f"{symbol.upper()}USDT"
        klines = fetch_binance_klines(binance_sym, interval="1h", limit=24)
        if not klines or len(klines) < 12:
            result = {**_neutral, "error": f"Insufficient candle data (got {len(klines)} candles, need ≥12)", "_ts": now}
            with _CVD_DIV_LOCK:
                _CVD_DIV_CACHE[cache_key] = result
            return {k: v for k, v in result.items() if k != "_ts"}

        closes:    list[float] = []
        cvd_vals:  list[float] = []
        cum_cvd = 0.0

        for k in klines:
            # k = [open_ts, open, high, low, close, volume, ...]
            open_p  = float(k[1])
            close_p = float(k[4])
            vol     = float(k[5])
            closes.append(close_p)
            # Candle direction → buy or sell approximation
            if close_p >= open_p:
                cum_cvd += vol   # bullish candle → buy pressure
            else:
                cum_cvd -= vol   # bearish candle → sell pressure
            cvd_vals.append(cum_cvd)

        # Split into two halves for divergence comparison
        half      = len(closes) // 2
        p_first   = closes[:half]
        p_second  = closes[half:]
        cvd_first = cvd_vals[:half]
        cvd_second = cvd_vals[half:]

        p_max_1, p_max_2   = max(p_first),   max(p_second)
        p_min_1, p_min_2   = min(p_first),   min(p_second)
        cvd_max_1, cvd_max_2 = max(cvd_first), max(cvd_second)
        cvd_min_1, cvd_min_2 = min(cvd_first), min(cvd_second)

        divergence = "NONE"
        price_trend = ""
        cvd_trend   = ""
        confidence  = 0.0
        signal      = "NO_DIVERGENCE"

        # Bearish divergence: price higher high + CVD lower high
        if p_max_2 > p_max_1 and cvd_max_2 < cvd_max_1:
            divergence  = "BEARISH"
            signal      = "BEARISH_DIVERGENCE"
            price_trend = f"Higher high ({p_max_2:,.2f} > {p_max_1:,.2f})"
            cvd_trend   = "Lower high (buy-side exhaustion)"
            # Confidence scales with size of price divergence vs CVD divergence
            p_diff   = (p_max_2 - p_max_1) / (p_max_1 + 1e-9)
            cvd_diff = abs(cvd_max_1 - cvd_max_2) / (abs(cvd_max_1) + 1e-9)
            confidence = min(1.0, (p_diff + cvd_diff) / 2)

        # Bullish divergence: price lower low + CVD higher low
        elif p_min_2 < p_min_1 and cvd_min_2 > cvd_min_1:
            divergence  = "BULLISH"
            signal      = "BULLISH_DIVERGENCE"
            price_trend = f"Lower low ({p_min_2:,.2f} < {p_min_1:,.2f})"
            cvd_trend   = "Higher low (sell-side absorption)"
            p_diff   = (p_min_1 - p_min_2) / (p_min_1 + 1e-9)
            cvd_diff = abs(cvd_min_2 - cvd_min_1) / (abs(cvd_min_1) + 1e-9)
            confidence = min(1.0, (p_diff + cvd_diff) / 2)

        else:
            # No divergence — describe current direction (guard against empty slice)
            if p_second and p_first:
                price_trend = "Rising" if p_second[-1] > p_first[-1] else "Falling" if p_second[-1] < p_first[-1] else "Flat"
            else:
                price_trend = "Flat"
            cvd_trend   = "Accumulation" if cvd_vals[-1] > cvd_vals[0] else "Distribution" if cvd_vals[-1] < cvd_vals[0] else "Neutral"
            confidence  = 0.0

        result = {
            "divergence":  divergence,
            "price_trend": price_trend,
            "cvd_trend":   cvd_trend,
            "confidence":  round(confidence, 3),
            "signal":      signal,
            "source":      "binance_klines",
            "error":       None,
            "_ts":         now,
        }
        with _CVD_DIV_LOCK:
            _CVD_DIV_CACHE[cache_key] = result
        return {k: v for k, v in result.items() if k != "_ts"}

    except Exception as e:
        logging.warning("[CVD-Div] %s: %s", symbol, e)
        result = {**_neutral, "error": str(e)[:120], "_ts": now}
        with _CVD_DIV_LOCK:
            _CVD_DIV_CACHE[cache_key] = result
        return {k: v for k, v in result.items() if k != "_ts"}


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
        resp = _SESSION.get(
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
        resp = _SESSION.get(
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
        resp = _SESSION.get(
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
        resp = _SESSION.get(
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

# ──────────────────────────────────────────────
# GECKOTERMINAL — FREE DEX POOL DATA (no API key)
# ──────────────────────────────────────────────

_GECKO_CACHE: dict = {}
_GECKO_LOCK = threading.Lock()
_GECKO_TTL = 120  # 2-minute cache


def fetch_geckoterminal_trending(network: str = "eth") -> list[dict]:
    """
    Fetch trending DEX pools from GeckoTerminal — FREE, no API key required.
    Returns list of top pools with volume, price change, and liquidity.
    Supported networks: eth, bsc, polygon, arbitrum, base, solana, flare
    """
    now = time.time()
    cache_key = f"gecko_trending_{network}"
    with _GECKO_LOCK:
        cached = _GECKO_CACHE.get(cache_key, {})
        if cached and now - cached.get("_ts", 0) < _GECKO_TTL:
            return cached.get("data", [])
    try:
        url = f"https://api.geckoterminal.com/api/v2/networks/{network}/trending_pools"
        headers = {"Accept": "application/json;version=20230302"}
        resp = _SESSION.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            pools = resp.json().get("data", [])
            results = []
            for pool in pools[:10]:
                attr = pool.get("attributes", {})
                results.append({
                    "name":             attr.get("name", ""),
                    "address":          attr.get("address", ""),
                    "price_usd":        float(attr.get("base_token_price_usd", 0) or 0),
                    "volume_24h":       float((attr.get("volume_usd") or {}).get("h24", 0) or 0),
                    "price_change_24h": float((attr.get("price_change_percentage") or {}).get("h24", 0) or 0),
                    "liquidity_usd":    float(attr.get("reserve_in_usd", 0) or 0),
                    "data_source":      "geckoterminal_live",
                    "network":          network,
                })
            with _GECKO_LOCK:
                _GECKO_CACHE[cache_key] = {"data": results, "_ts": now}
            return results
    except Exception as e:
        logging.debug("GeckoTerminal trending fetch failed (%s): %s", network, e)
    return []


def fetch_geckoterminal_ohlcv(network: str, pool_address: str, timeframe: str = "hour", limit: int = 24) -> list[dict]:
    """
    Fetch OHLCV candles for a specific pool from GeckoTerminal — FREE.
    timeframe options: minute, hour, day
    """
    try:
        url = f"https://api.geckoterminal.com/api/v2/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
        headers = {"Accept": "application/json;version=20230302"}
        params = {"limit": min(limit, 1000), "currency": "usd"}
        resp = _SESSION.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            ohlcv_list = resp.json().get("data", {}).get("attributes", {}).get("ohlcv_list", [])
            return [
                {"timestamp": int(c[0]), "open": float(c[1]), "high": float(c[2]),
                 "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])}
                for c in ohlcv_list
            ]
    except Exception as e:
        logging.debug("GeckoTerminal OHLCV failed: %s", e)
    return []


# ──────────────────────────────────────────────
# DEFILLAMA — FREE YIELD DATA (no API key)
# ──────────────────────────────────────────────

_LLAMA_CACHE: dict = {}
_LLAMA_LOCK = threading.Lock()
_LLAMA_TTL = 300  # 5-minute cache


def fetch_defillama_top_yields(min_apy: float = 5.0, max_apy: float = 50.0, top_n: int = 20) -> list[dict]:
    """
    Fetch top yield pools from DeFiLlama — FREE, no API key.
    Filters for realistic, credible yields (>$1M TVL, 5–50% APY range).
    """
    now = time.time()
    with _LLAMA_LOCK:
        cached = _LLAMA_CACHE.get("top_yields", {})
        if cached and now - cached.get("_ts", 0) < _LLAMA_TTL:
            return cached.get("data", [])
    try:
        resp = _SESSION.get("https://yields.llama.fi/pools", timeout=15)
        if resp.status_code == 200:
            pools = resp.json().get("data", [])
            filtered = [
                p for p in pools
                if p.get("apy") and min_apy <= p["apy"] <= max_apy
                and p.get("tvlUsd", 0) > 1_000_000
                and p.get("ilRisk") != "yes"  # skip high-IL pools for signal purity
            ]
            filtered.sort(key=lambda x: x.get("tvlUsd", 0), reverse=True)
            result = filtered[:top_n]
            with _LLAMA_LOCK:
                _LLAMA_CACHE["top_yields"] = {"data": result, "_ts": now}
            return result
    except Exception as e:
        logging.debug("DeFiLlama yields fetch failed: %s", e)
    return []


def fetch_defillama_protocol_tvl(protocol_slug: str) -> dict:
    """
    Fetch TVL history for a specific protocol — FREE.
    Example slugs: 'aave', 'uniswap', 'hyperliquid'
    """
    try:
        resp = _SESSION.get(f"https://api.llama.fi/protocol/{protocol_slug}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            tvl_list = data.get("tvl", [])
            current_tvl = tvl_list[-1].get("totalLiquidityUSD", 0) if tvl_list else 0
            return {
                "protocol":    protocol_slug,
                "current_tvl": current_tvl,
                "name":        data.get("name", protocol_slug),
                "category":    data.get("category", ""),
                "chains":      data.get("chains", []),
            }
    except Exception as e:
        logging.debug("DeFiLlama protocol TVL failed (%s): %s", protocol_slug, e)
    return {}


# ──────────────────────────────────────────────
# COIN METRICS — FREE COMMUNITY ON-CHAIN DATA
# ──────────────────────────────────────────────

_CM_CACHE: dict = {}
_CM_LOCK = threading.Lock()
_CM_TTL = 3600  # 1-hour cache (daily metrics don't change faster)


def fetch_coin_metrics_onchain(assets: str = "btc,eth", metrics: str = "AdrActCnt,TxCnt") -> list[dict]:
    """
    Fetch on-chain metrics from Coin Metrics Community API — FREE, no API key.
    AdrActCnt = daily active addresses
    TxCnt     = daily transaction count
    Returns last 7 days of data per asset.
    """
    now = time.time()
    cache_key = f"cm_{assets}_{metrics}"
    with _CM_LOCK:
        cached = _CM_CACHE.get(cache_key, {})
        if cached and now - cached.get("_ts", 0) < _CM_TTL:
            return cached.get("data", [])
    try:
        url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
        params = {
            "assets":          assets,
            "metrics":         metrics,
            "frequency":       "1d",
            "limit_per_asset": 7,
        }
        resp = _SESSION.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            result = resp.json().get("data", [])
            with _CM_LOCK:
                _CM_CACHE[cache_key] = {"data": result, "_ts": now}
            return result
    except Exception as e:
        logging.debug("Coin Metrics community API failed: %s", e)
    return []


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


# ──────────────────────────────────────────────────────────────
# LONG-SHORT RATIO  (Binance → OKX → Bybit fallback)
# Free public endpoints — no auth required
# ──────────────────────────────────────────────────────────────

_LS_RATIO_CACHE: dict = {}
_LS_RATIO_LOCK = threading.Lock()


def get_long_short_ratio(pair: str) -> dict:
    """
    Fetch the global long/short account ratio for a perpetual pair.
    Falls back: Binance → OKX → Bybit.

    Returns a dict with keys: long_pct, short_pct, ratio, signal, source, cached_at
    Signal: CROWDED_LONG | CROWDED_SHORT | BALANCED
    """
    symbol = pair.replace("/", "")
    now = time.time()
    with _LS_RATIO_LOCK:
        cached = _LS_RATIO_CACHE.get(symbol)
        if cached and now - cached.get("cached_at", 0) < _CACHE_TTL_SECONDS:
            return cached

    result = None

    # --- OKX (US-accessible, no geo-block — Binance fapi removed) ---
    if result is None:
        try:
            inst_id = _okx_inst_id(pair)
            resp = _SESSION.get(
                "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio",
                params={"instId": inst_id, "period": "5m"},
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                row = data[0]
                long_pct  = float(row[1])  # OKX: [ts, longRatio, shortRatio]
                short_pct = float(row[2])
                ratio     = long_pct / short_pct if short_pct else 0.0
                signal    = "CROWDED_LONG" if long_pct > 0.65 else ("CROWDED_SHORT" if long_pct < 0.35 else "BALANCED")
                result = {
                    "long_pct": round(long_pct, 4),
                    "short_pct": round(short_pct, 4),
                    "ratio": round(ratio, 3),
                    "signal": signal,
                    "source": "okx",
                    "cached_at": now,
                }
        except Exception as e:
            logging.debug("OKX LS ratio failed for %s: %s", pair, e)

    # --- Bybit fallback ---
    if result is None:
        try:
            resp = _SESSION.get(
                "https://api.bybit.com/v5/market/account-ratio",
                params={"category": "linear", "symbol": symbol, "period": "5min", "limit": 1},
                timeout=6,
            )
            resp.raise_for_status()
            rows = resp.json().get("result", {}).get("list", [])
            if rows:
                row = rows[0]
                buy_ratio  = float(row.get("buyRatio", 0.5))
                sell_ratio = float(row.get("sellRatio", 0.5))
                ratio      = buy_ratio / sell_ratio if sell_ratio else 0.0
                signal     = "CROWDED_LONG" if buy_ratio > 0.65 else ("CROWDED_SHORT" if buy_ratio < 0.35 else "BALANCED")
                result = {
                    "long_pct": round(buy_ratio, 4),
                    "short_pct": round(sell_ratio, 4),
                    "ratio": round(ratio, 3),
                    "signal": signal,
                    "source": "bybit",
                    "cached_at": now,
                }
        except Exception as e:
            logging.debug("Bybit LS ratio failed for %s: %s", symbol, e)

    if result is None:
        result = {"error": "all sources failed", "signal": "UNKNOWN", "cached_at": now}

    with _LS_RATIO_LOCK:
        _LS_RATIO_CACHE[symbol] = result
    return result


def get_long_short_ratio_batch(pairs: list) -> dict:
    """Fetch long/short ratio for multiple pairs in parallel. Returns {pair: result}."""
    with ThreadPoolExecutor(max_workers=min(len(pairs), 6)) as ex:
        futures = {ex.submit(get_long_short_ratio, p): p for p in pairs}
        return {futures[f]: f.result() for f in futures}


# ──────────────────────────────────────────────────────────────
# TAKER BUY/SELL RATIO  (Binance futures — no auth required)
# ──────────────────────────────────────────────────────────────

_TAKER_RATIO_CACHE: dict = {}
_TAKER_RATIO_LOCK = threading.Lock()


def get_taker_buy_sell_ratio(pair: str) -> dict:
    """
    Fetch taker buy/sell volume ratio.
    Primary: Bybit v5 (no US geo-block). fapi.binance.com removed — geo-blocked.
    Reflects aggressive order flow: >0.55 buy_pct = buy-side pressure.

    Returns: buy_pct, sell_pct, signal, source, cached_at
    Signal: BUY_DOMINANT | SELL_DOMINANT | BALANCED
    """
    symbol = pair.replace("/", "")
    now = time.time()
    with _TAKER_RATIO_LOCK:
        cached = _TAKER_RATIO_CACHE.get(symbol)
        if cached and now - cached.get("cached_at", 0) < _CACHE_TTL_SECONDS:
            return cached

    result = None

    # --- Bybit v5 (primary — no US geo-block) ---
    try:
        resp = _SESSION.get(
            "https://api.bybit.com/v5/market/taker-volume",
            params={"category": "linear", "symbol": symbol, "period": "5min", "limit": 1},
            timeout=6,
        )
        resp.raise_for_status()
        rows = resp.json().get("result", {}).get("list", [])
        if rows:
            row = rows[0]
            buy_ratio  = float(row.get("buyRatio", 0.5))
            sell_ratio = float(row.get("sellRatio", 0.5))
            total      = buy_ratio + sell_ratio
            buy_pct    = buy_ratio / total if total > 0 else 0.5
            sell_pct   = 1.0 - buy_pct
            signal     = "BUY_DOMINANT" if buy_pct > 0.55 else ("SELL_DOMINANT" if buy_pct < 0.45 else "BALANCED")
            result = {
                "buy_pct": round(buy_pct, 4),
                "sell_pct": round(sell_pct, 4),
                "signal": signal,
                "source": "bybit",
                "cached_at": now,
            }
    except Exception as e:
        logging.debug("Bybit taker buy/sell ratio failed for %s: %s", symbol, e)

    if result is None:
        result = {"error": "all sources failed", "signal": "UNKNOWN", "cached_at": now}

    with _TAKER_RATIO_LOCK:
        _TAKER_RATIO_CACHE[symbol] = result
    return result


# ──────────────────────────────────────────────────────────────
# KIMCHI PREMIUM  (Upbit KRW + open.er-api.com + Binance)
# Free public endpoints — no auth required
# ──────────────────────────────────────────────────────────────

_KIMCHI_CACHE: dict = {}
_KIMCHI_LOCK = threading.Lock()


def get_kimchi_premium() -> dict:
    """
    Calculate the Kimchi Premium: Upbit BTC/KRW vs (Binance BTC/USDT × USD/KRW rate).
    Premium > 3% historically correlates with Korean retail FOMO; discount = fear.

    Returns: premium_pct, signal, upbit_btc_krw, binance_btc_usd, usd_krw, cached_at
    Signal: EXTREME_PREMIUM (>5%) | PREMIUM (>2%) | NEUTRAL | DISCOUNT (<-2%)
    """
    now = time.time()
    with _KIMCHI_LOCK:
        cached = _KIMCHI_CACHE.get("btc")
        if cached and now - cached.get("cached_at", 0) < _CACHE_TTL_SECONDS:
            return cached

    upbit_btc_krw = None
    binance_btc_usd = None
    usd_krw = None

    # Upbit BTC/KRW
    try:
        resp = _SESSION.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": "KRW-BTC"},
            timeout=6,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            upbit_btc_krw = float(data[0]["trade_price"])
    except Exception as e:
        logging.debug("Upbit BTC/KRW failed: %s", e)

    # Binance BTC/USDT spot
    try:
        resp = _SESSION.get(
            "https://api.binance.us/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=6,
        )
        resp.raise_for_status()
        binance_btc_usd = float(resp.json()["price"])
    except Exception as e:
        logging.debug("Binance BTC/USDT failed: %s", e)

    # USD/KRW exchange rate
    try:
        resp = _SESSION.get("https://open.er-api.com/v6/latest/USD", timeout=6)
        resp.raise_for_status()
        usd_krw = float(resp.json()["rates"]["KRW"])
    except Exception as e:
        logging.debug("USD/KRW exchange rate failed: %s", e)

    if upbit_btc_krw and binance_btc_usd and usd_krw:
        btc_usd_via_krw = upbit_btc_krw / usd_krw
        premium_pct = (btc_usd_via_krw - binance_btc_usd) / binance_btc_usd * 100
        if premium_pct > 5:
            signal = "EXTREME_PREMIUM"
        elif premium_pct > 2:
            signal = "PREMIUM"
        elif premium_pct < -2:
            signal = "DISCOUNT"
        else:
            signal = "NEUTRAL"
        result = {
            "premium_pct":     round(premium_pct, 3),
            "signal":          signal,
            "upbit_btc_krw":   upbit_btc_krw,
            "binance_btc_usd": binance_btc_usd,
            "usd_krw":         usd_krw,
            "cached_at":       now,
        }
    else:
        result = {"error": "incomplete data", "signal": "UNKNOWN", "cached_at": now}

    with _KIMCHI_LOCK:
        _KIMCHI_CACHE["btc"] = result
    return result


# ──────────────────────────────────────────────────────────────
# HYPERLIQUID ON-CHAIN PERP STATS
# Public API — no auth required
# ──────────────────────────────────────────────────────────────

_HL_CACHE: dict = {}
_HL_LOCK = threading.Lock()
_HL_CACHE_TTL = 120  # 2-minute cache (on-chain data updates frequently)


def get_hyperliquid_stats(pair: str) -> dict:
    """
    Fetch open interest and funding rate for a pair on Hyperliquid.
    Uses the /info endpoint with metaAndAssetCtxs action.

    Returns: open_interest_usd, funding_rate_8h, funding_annualised_pct, mark_price, signal, cached_at
    Signal: HIGH_OI_POSITIVE_FUNDING | HIGH_OI_NEGATIVE_FUNDING | NORMAL
    """
    coin = pair.replace("/USDT", "").replace("/USDC", "").replace("USDT", "").replace("USDC", "")
    now = time.time()
    with _HL_LOCK:
        cached = _HL_CACHE.get(coin)
        if cached and now - cached.get("cached_at", 0) < _HL_CACHE_TTL:
            return cached

    try:
        resp = _SESSION.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "metaAndAssetCtxs"},
            timeout=8,
        )
        resp.raise_for_status()
        payload = resp.json()
        # payload = [meta_dict, [assetCtx, ...]]
        assets = payload[0].get("universe", [])
        ctxs   = payload[1]
        result = None
        for i, asset in enumerate(assets):
            if asset.get("name", "").upper() == coin.upper() and i < len(ctxs):
                ctx      = ctxs[i]
                mark_px  = float(ctx.get("markPx") or 0)
                oi       = float(ctx.get("openInterest") or 0) * mark_px
                fund     = float(ctx.get("funding") or 0)
                fund_ann = fund * 3 * 365 * 100  # 8h rate → annualised %
                signal   = "NORMAL"
                if oi > 50_000_000:
                    signal = "HIGH_OI_POSITIVE_FUNDING" if fund > 0 else "HIGH_OI_NEGATIVE_FUNDING"
                result = {
                    "coin":                   coin,
                    "open_interest_usd":      round(oi),
                    "funding_rate_8h":        round(fund, 6),
                    "funding_annualised_pct": round(fund_ann, 2),
                    "mark_price":             mark_px,
                    "signal":                 signal,
                    "source":                 "hyperliquid",
                    "cached_at":              now,
                }
                break
        if result is None:
            result = {"error": f"{coin} not found on Hyperliquid", "signal": "UNKNOWN", "cached_at": now}
    except Exception as e:
        logging.debug("Hyperliquid stats failed for %s: %s", coin, e)
        result = {"error": str(e), "signal": "UNKNOWN", "cached_at": now}

    with _HL_LOCK:
        _HL_CACHE[coin] = result
    return result


def get_hyperliquid_batch(pairs: list) -> dict:
    """
    Fetch Hyperliquid stats for multiple coins efficiently.
    The first call fetches all assets in one API request; subsequent calls are cache hits.
    """
    if pairs:
        get_hyperliquid_stats(pairs[0])  # warms the full cache in one call
    return {p: get_hyperliquid_stats(p) for p in pairs}


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 2: MACRO DATA LAYER
# FRED: DGS10 (10Y yield), M2SL (M2 money supply), NAPM (ISM proxy)
# yfinance: DXY, VIX, Gold, SPX, Oil — free, no API key required
# ─────────────────────────────────────────────────────────────────────────────

_FRED_MACRO_SERIES_SG = {
    "m2_supply_bn":      "M2SL",
    "ten_yr_yield":      "DGS10",
    "ism_manufacturing": "NAPM",
}

_FRED_MACRO_FALLBACKS_SG = {
    "m2_supply_bn":      21_500.0,
    "ten_yr_yield":          4.35,
    "ism_manufacturing":    52.0,
}

_MACRO_CACHE_SG: dict = {}
_MACRO_CACHE_LOCK_SG = threading.Lock()
_MACRO_INFLIGHT: dict = {}   # key → threading.Event sentinel (TOCTOU guard)
_MACRO_TTL = 3600  # 1 hour


def _macro_cached_get(key: str, ttl: int, fetch_fn):
    """TTL cache wrapper for macro data with TOCTOU guard.

    Only one thread fetches for a given key at a time; concurrent callers
    block on a threading.Event until the fetcher finishes, then read from cache.
    """
    import time
    my_event: threading.Event | None = None
    wait_event: threading.Event | None = None

    with _MACRO_CACHE_LOCK_SG:
        cached = _MACRO_CACHE_SG.get(key)
        if cached and (time.time() - cached["_ts"]) < ttl:
            return cached["data"]
        if key in _MACRO_INFLIGHT:
            wait_event = _MACRO_INFLIGHT[key]
        else:
            my_event = threading.Event()
            _MACRO_INFLIGHT[key] = my_event

    if wait_event is not None:
        wait_event.wait(timeout=90)
        with _MACRO_CACHE_LOCK_SG:
            cached = _MACRO_CACHE_SG.get(key)
            return cached["data"] if cached else None

    # This thread is the designated fetcher
    try:
        data = fetch_fn()
        if data:
            with _MACRO_CACHE_LOCK_SG:
                _MACRO_CACHE_SG[key] = {"data": data, "_ts": time.time()}
        return data
    except Exception as e:
        logging.debug("[MacroCache] %s fetch failed: %s", key, e)
        with _MACRO_CACHE_LOCK_SG:
            cached = _MACRO_CACHE_SG.get(key)
            return cached["data"] if cached else None
    finally:
        my_event.set()
        with _MACRO_CACHE_LOCK_SG:
            _MACRO_INFLIGHT.pop(key, None)


def fetch_fred_macro() -> dict:
    """
    Fetch macro series from FRED public CSV: M2SL, DGS10, NAPM.
    No API key required (uses public CSV endpoint).
    Returns fallback values on error.
    """
    def _fetch():
        result = {}
        for key, series_id in _FRED_MACRO_SERIES_SG.items():
            try:
                url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
                resp = _FRED_SESSION.get(url, timeout=5)
                if resp.status_code == 200:
                    lines = resp.text.strip().split("\n")
                    for line in reversed(lines[1:]):
                        parts = line.split(",")
                        if len(parts) == 2 and parts[1].strip() not in (".", ""):
                            result[key] = round(float(parts[1].strip()), 4)
                            break
            except Exception as e:
                logging.debug("[FRED] %s failed: %s", series_id, e)
        if len(result) < 1:
            return None
        for k, v in _FRED_MACRO_FALLBACKS_SG.items():
            result.setdefault(k, v)
        result["source"] = "FRED"
        import datetime as _dt
        result["timestamp"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return result

    cached = _macro_cached_get("fred_macro", _MACRO_TTL, _fetch)
    if cached is None:
        fb = dict(_FRED_MACRO_FALLBACKS_SG)
        fb["source"] = "fallback"
        import datetime as _dt
        fb["timestamp"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return fb
    return cached


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL M2 COMPOSITE — 70–110 day forward shift  (#24)
# ─────────────────────────────────────────────────────────────────────────────
# Methodology (Michael Howell / CrossBorderCapital):
#   Global M2 ≈ US M2 + China M2 + Euro-area M3 + Japan M2 (FRED free series)
#   Forward shift: BTC price tends to lag Global M2 inflections by ~90 days.
#   Signal: compare current M2 rate-of-change to the 90-day-lagged value.
#   BULLISH if trailing 30d M2 growth > 0 AND current M2 > 90d-ago level.
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_M2_SERIES = {
    "us_m2":     "M2SL",            # US M2 (billions USD)
    "china_m2":  "MYAGM2CNM189N",   # China M2 (100M CNY → converted to USD at ~7.2)
    "euro_m3":   "MABMM301EZM189S", # Euro area M3 (millions EUR → USD at ~1.08)
    "japan_m2":  "MYAGM2JPM189N",   # Japan M2 (billions JPY → USD at ~150)
}

_GLOBAL_M2_FX = {
    "china_m2":  1 / 7.2 / 100,    # 100M CNY → billions USD
    "euro_m3":   1.08 / 1_000,     # millions EUR → billions USD
    "japan_m2":  1 / 150,          # billions JPY → billions USD
    "us_m2":     1.0,              # already billions USD
}

_G_M2_CACHE: dict = {}
_G_M2_LOCK = threading.Lock()
_G_M2_INFLIGHT: threading.Event | None = None
_G_M2_INFLIGHT_LOCK = threading.Lock()


def fetch_global_m2_composite(lag_days: int = 90) -> dict:
    """
    Fetch Global M2 composite and return the 90-day-lagged forward signal.

    Returns:
        global_m2_bn       — current global M2 in billions USD
        m2_pct_change_90d  — % change vs 90 days ago (trailing)
        signal             — BULLISH / NEUTRAL / BEARISH
        lag_days           — the lag applied (default 90)
        source             — "FRED" | "fallback"
    """
    import datetime as _dt

    def _fetch_csv(series_id: str, months: int = 6) -> list:
        """Return last `months` monthly observations as floats."""
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        try:
            resp = _FRED_SESSION.get(url, timeout=5)
            if resp.status_code != 200:
                return []
            lines = resp.text.strip().split("\n")[1:]  # skip header
            vals = []
            for line in reversed(lines):
                parts = line.split(",")
                if len(parts) == 2 and parts[1].strip() not in (".", ""):
                    try:
                        vals.append(float(parts[1].strip()))
                    except ValueError:
                        pass
                if len(vals) >= months:
                    break
            return vals  # newest first
        except Exception:
            return []

    def _fetch():
        # Fetch 7 months of central bank M2/M3 series so the 90-day lag is accurate
        components = {}
        for key, sid in _GLOBAL_M2_SERIES.items():
            vals = _fetch_csv(sid, months=7)
            if vals:
                fx = _GLOBAL_M2_FX.get(key, 1.0)
                components[key] = [v * fx for v in vals]

        if len(components) < 2:
            return None  # not enough data — use fallback

        # Require at least 2 data points per component
        min_len = min(len(v) for v in components.values())
        if min_len < 2:
            return None

        current_total = sum(v[0] for v in components.values())

        # 90-day lag ≈ 3 monthly observations ago (index 3); fall back to oldest available
        lag_idx   = min(3, min_len - 1)
        old_total = sum(v[lag_idx] for v in components.values())
        pct_change = round((current_total - old_total) / max(old_total, 1e-6) * 100, 2)

        if pct_change > 1.5:
            signal = "BULLISH"
        elif pct_change > 0:
            signal = "NEUTRAL"
        else:
            signal = "BEARISH"

        return {
            "global_m2_bn":      round(current_total, 0),
            "m2_pct_change_90d": pct_change,
            "signal":            signal,
            "lag_days":          lag_days,
            "components_bn":     {k: round(v[0], 0) for k, v in components.items()},
            "source":            "FRED",
            "timestamp":         _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }

    global _G_M2_INFLIGHT
    _my_event: threading.Event | None = None
    _wait_event: threading.Event | None = None

    with _G_M2_INFLIGHT_LOCK:
        cached = _G_M2_CACHE.get("global_m2")
        if cached and (time.time() - cached["_ts"]) < 3600:
            return cached["data"]
        if _G_M2_INFLIGHT is not None:
            _wait_event = _G_M2_INFLIGHT
        else:
            _my_event = threading.Event()
            _G_M2_INFLIGHT = _my_event

    if _wait_event is not None:
        _wait_event.wait(timeout=90)
        with _G_M2_INFLIGHT_LOCK:
            cached = _G_M2_CACHE.get("global_m2")
            if cached:
                return cached["data"]
    elif _my_event is not None:
        try:
            data = _fetch()
            if data:
                with _G_M2_INFLIGHT_LOCK:
                    _G_M2_CACHE["global_m2"] = {"data": data, "_ts": time.time()}
                return data
        except Exception as e:
            logging.debug("[GlobalM2] fetch failed: %s", e)
        finally:
            _my_event.set()
            with _G_M2_INFLIGHT_LOCK:
                _G_M2_INFLIGHT = None

    # Fallback
    return {
        "global_m2_bn":      84_000.0,
        "m2_pct_change_90d": 1.2,
        "signal":            "NEUTRAL",
        "lag_days":          lag_days,
        "components_bn":     {"us_m2": 21500, "china_m2": 38000, "euro_m3": 17000, "japan_m2": 7500},
        "source":            "fallback",
        "timestamp":         __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


def fetch_yfinance_macro() -> dict:
    """
    Fetch macro market data: DXY, VIX, Gold, SPX, Oil.
    Primary: yfinance (free, traditional markets).
    Fallback: Binance spot for Gold proxy (PAXG/USDT), static values for others.
    """
    _YF_FALLBACKS = {
        "dxy": 104.0, "vix": 18.0, "gold_spot": 2900.0,
        "spx": 5800.0, "oil": 67.5,
    }

    def _fetch():
        result = {}

        # ── Try yfinance (primary for traditional market data) ─────────────────
        try:
            import yfinance as yf
            _MAP = {
                "dxy":       "DX-Y.NYB",
                "vix":       "^VIX",
                "gold_spot": "GC=F",
                "spx":       "^GSPC",
                "oil":       "CL=F",
            }
            for key, symbol in _MAP.items():
                try:
                    hist = yf.Ticker(symbol).history(period="5d")
                    if not hist.empty:
                        result[key] = round(float(hist["Close"].iloc[-1]), 2)
                except Exception as e:
                    logging.debug("[yfinance] %s failed: %s", symbol, e)
        except ImportError:
            logging.debug("[yfinance] not installed — using Binance/fallback only")

        # ── Binance fallback for gold (PAXG = PAX Gold, 1:1 troy oz) ──────────
        if "gold_spot" not in result:
            try:
                paxg = _fetch_binance_24hr("PAXGUSDT")
                if paxg and "lastPrice" in paxg:
                    result["gold_spot"] = round(float(paxg["lastPrice"]), 2)
                    logging.debug("[Binance] PAXG gold proxy: %s", result["gold_spot"])
            except Exception as e:
                logging.debug("[Binance gold fallback] failed: %s", e)

        if not result:
            return None
        import datetime as _dt
        result["source"] = "yfinance" if "dxy" in result else "binance_partial"
        result["timestamp"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return result

    cached = _macro_cached_get("yfinance_macro", _MACRO_TTL, _fetch)
    if cached is None:
        fb = dict(_YF_FALLBACKS)
        fb["source"] = "fallback"
        import datetime as _dt
        fb["timestamp"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return fb
    return cached


def fetch_macro_timeseries(days: int = 90) -> dict:
    """
    Fetch historical daily close prices for macro correlation analysis.
    Returns {symbol_key: {date_str: price}} for BTC, VIX, Gold, SPX, DXY, Oil.
    Cached 30 minutes. Returns {} if yfinance not installed.
    """
    def _fetch():
        try:
            import yfinance as yf
        except ImportError:
            return {}
        _SYMBOLS = {
            "BTC":  "BTC-USD",
            "VIX":  "^VIX",
            "Gold": "GC=F",
            "SPX":  "^GSPC",
            "DXY":  "DX-Y.NYB",
            "Oil":  "CL=F",
        }
        result = {}
        for key, symbol in _SYMBOLS.items():
            try:
                hist = yf.Ticker(symbol).history(period=f"{days}d")
                if not hist.empty:
                    result[key] = {
                        str(dt)[:10]: round(float(v), 4)
                        for dt, v in hist["Close"].items()
                    }
            except Exception as e:
                logging.debug("[MacroTS] %s failed: %s", symbol, e)
        import datetime as _dt
        result["_days"]      = days
        result["_timestamp"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        return result

    cached = _macro_cached_get(f"macro_ts_{days}", 1800, _fetch)
    return cached if cached else {}


def fetch_coinalyze_funding(symbols: list | None = None) -> dict:
    """
    Fetch aggregated perpetual funding rates from Coinalyze (Binance+Bybit+OKX).
    Returns {symbol: {funding_rate, funding_rate_pct, open_interest_usd, signal}}.
    Falls back to {} if unavailable or API key not set.
    """
    if symbols is None:
        symbols = ["BTCUSDT_PERP.A", "ETHUSDT_PERP.A", "SOLUSDT_PERP.A"]
    import os
    api_key = os.environ.get("SUPERGROK_COINALYZE_API_KEY") or os.environ.get("COINALYZE_API_KEY")

    def _fetch():
        headers = {}
        if api_key:
            headers["api_key"] = api_key
        url = "https://api.coinalyze.net/v1/funding-rate"
        try:
            resp = _SESSION.get(
                url,
                params={"symbols": ",".join(symbols)},
                headers=headers,
                timeout=8,
            )
            if resp.status_code == 200:
                data = resp.json()
                result = {}
                for item in (data if isinstance(data, list) else []):
                    sym  = item.get("symbol", "")
                    rate = float(item.get("last_funding_rate", 0))
                    result[sym] = {
                        "funding_rate":      rate,
                        "funding_rate_pct":  round(rate * 100, 4),
                        "open_interest_usd": item.get("open_interest_usd"),
                        "signal": (
                            "BEARISH" if rate > 0.0003
                            else ("BULLISH" if rate < -0.0003 else "NEUTRAL")
                        ),
                        "source": "coinalyze",
                    }
                return result if result else None
        except Exception as e:
            logging.debug("[Coinalyze] funding fetch failed: %s", e)
        return None

    cached = _macro_cached_get("coinalyze_funding", 300, _fetch)
    return cached if cached else {}


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 3: BLOOD IN THE STREETS · DCA MULTIPLIER · MACRO OVERLAY · DERIBIT SKEW
# ─────────────────────────────────────────────────────────────────────────────

def get_dca_multiplier(fg_value: int) -> float:
    """
    DCA position-size multiplier based on Fear & Greed zone.

    Extreme Fear (0-15)    → 3.0×   max accumulation
    Fear         (16-30)   → 2.0×   heavy accumulation
    Neutral      (31-55)   → 1.0×   base size
    Greed        (56-74)   → 0.5×   reduce size
    Extreme Greed(75-100)  → 0.0×   hold, no new buys
    """
    if fg_value <= 15:  return 3.0
    if fg_value <= 30:  return 2.0
    if fg_value <= 55:  return 1.0
    if fg_value <= 74:  return 0.5
    return 0.0


def compute_blood_in_streets(
    fg_value: int,
    rsi_14: float | None = None,
    net_flow: float | None = None,
) -> dict:
    """
    Composite "Blood in the Streets" buy signal — fires on multi-factor capitulation.

    Criteria (independent, additive):
      1. Fear & Greed ≤ 25       extreme fear / mass panic
      2. RSI-14 (daily) ≤ 30     technical oversold / capitulation bottom
      3. Exchange net outflow     smart money accumulating (optional proxy)

    Historical hit rate (BTC, 30d forward): ~78% when criteria 1+2 both met.
    """
    criteria = {
        "extreme_fear":     fg_value <= 25,
        "rsi_oversold":     rsi_14 is not None and rsi_14 <= 30,
        "exchange_outflow": net_flow is not None and net_flow < -50.0,
    }
    met_count    = sum(1 for v in criteria.values() if v)
    core_trigger = criteria["extreme_fear"] and criteria["rsi_oversold"]

    if core_trigger and criteria["exchange_outflow"]:
        signal, strength = "BLOOD_IN_STREETS", "CONFIRMED"
    elif core_trigger:
        signal, strength = "BLOOD_IN_STREETS", "PROBABLE"
    elif criteria["extreme_fear"]:
        signal, strength = "EXTREME_FEAR", "WATCH"
    else:
        signal, strength = "NORMAL", "NORMAL"

    return {
        "signal":         signal,
        "strength":       strength,
        "triggered":      signal == "BLOOD_IN_STREETS",
        "criteria_met":   met_count,
        "criteria":       criteria,
        "fg_value":       fg_value,
        "rsi_14":         rsi_14,
        "dca_multiplier": get_dca_multiplier(fg_value),
        "description": (
            "Extreme fear + oversold — 78% hit rate for 30d rally (historical BTC)."
            if signal == "BLOOD_IN_STREETS"
            else f"F&G={fg_value}. {met_count}/3 criteria met."
        ),
    }


def get_macro_signal_adjustment() -> dict:
    """
    Compute a confidence-point adjustment from macro conditions.

    DXY > 105 and/or 10Y yield > 4.5% = crypto headwind (negative pts).
    DXY < 100 and/or 10Y yield < 4.0% = crypto tailwind (positive pts).

    Returns {adjustment: float, regime: str, dxy: float, ten_yr: float,
             dxy_signal: str, yr_signal: str}
    """
    fred   = fetch_fred_macro()
    yf_mac = fetch_yfinance_macro()
    dxy    = yf_mac.get("dxy",         104.0)
    ten_yr = fred.get("ten_yr_yield",    4.35)

    dxy_head = dxy    > 105.0
    dxy_tail = dxy    < 100.0
    yr_head  = ten_yr >   4.5
    yr_tail  = ten_yr <   4.0

    headwinds = int(dxy_head) + int(yr_head)
    tailwinds = int(dxy_tail) + int(yr_tail)

    if headwinds == 2:   adjustment, regime = -8.0, "MACRO_HEADWIND"
    elif headwinds == 1: adjustment, regime = -4.0, "MILD_HEADWIND"
    elif tailwinds == 2: adjustment, regime = +8.0, "MACRO_TAILWIND"
    elif tailwinds == 1: adjustment, regime = +4.0, "MILD_TAILWIND"
    else:                adjustment, regime =  0.0, "MACRO_NEUTRAL"

    return {
        "adjustment": adjustment,
        "regime":     regime,
        "dxy":        dxy,
        "ten_yr":     ten_yr,
        "dxy_signal": "headwind" if dxy_head else ("tailwind" if dxy_tail else "neutral"),
        "yr_signal":  "headwind" if yr_head  else ("tailwind" if yr_tail  else "neutral"),
    }


def get_deribit_options_skew(currency: str = "BTC") -> dict:
    """
    Compute 25-delta put/call IV skew from Deribit front-month options.

    Skew = put_iv - call_iv
      > +5  → BEARISH (market paying premium for downside protection)
      > +2  → MILD_BEARISH
      0±2   → NEUTRAL
      < -2  → MILD_BULLISH
      < -5  → BULLISH (market pricing in upside / calls cheap)

    Returns {skew, put_iv, call_iv, expiry, signal, source}.
    Cached 30 min.  Falls back to {"signal": "N/A", "error": ...} on failure.
    """
    def _fetch():
        try:
            url  = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
            resp = _SESSION.get(
                url,
                params={"currency": currency, "kind": "option"},
                timeout=12,
            )
            if resp.status_code != 200:
                return None
            data = resp.json().get("result", [])

            import datetime as _dt
            now = _dt.datetime.now(_dt.timezone.utc)
            puts, calls = [], []
            for item in data:
                name = item.get("instrument_name", "")
                parts = name.split("-")
                if len(parts) < 4:
                    continue
                try:
                    exp = _dt.datetime.strptime(parts[1], "%d%b%y").replace(tzinfo=_dt.timezone.utc)
                except ValueError:
                    try:
                        exp = _dt.datetime.strptime(parts[1], "%d%b%Y").replace(tzinfo=_dt.timezone.utc)
                    except ValueError:
                        continue
                days_to_exp = (exp - now).days
                if not (20 <= days_to_exp <= 60):
                    continue
                option_type = parts[3].upper()
                mark_iv     = item.get("mark_iv")
                delta       = item.get("greeks", {}).get("delta") if item.get("greeks") else None
                if mark_iv is None or delta is None:
                    continue
                delta = float(delta)
                mark_iv = float(mark_iv)
                if option_type == "P" and abs(abs(delta) - 0.25) < 0.08:
                    puts.append((abs(abs(delta) - 0.25), mark_iv, exp.strftime("%Y-%m-%d")))
                elif option_type == "C" and abs(abs(delta) - 0.25) < 0.08:
                    calls.append((abs(abs(delta) - 0.25), mark_iv, exp.strftime("%Y-%m-%d")))

            if not puts or not calls:
                return {"signal": "N/A", "error": "insufficient options data", "source": "deribit"}

            puts.sort(key=lambda x: x[0])
            calls.sort(key=lambda x: x[0])
            put_iv, expiry = puts[0][1], puts[0][2]
            call_iv = calls[0][1]
            skew    = round(put_iv - call_iv, 2)

            if skew > 5:     signal = "BEARISH"
            elif skew > 2:   signal = "MILD_BEARISH"
            elif skew < -5:  signal = "BULLISH"
            elif skew < -2:  signal = "MILD_BULLISH"
            else:            signal = "NEUTRAL"

            return {
                "skew":    skew,
                "put_iv":  round(put_iv, 2),
                "call_iv": round(call_iv, 2),
                "expiry":  expiry,
                "signal":  signal,
                "source":  "deribit",
            }
        except Exception as e:
            logging.debug("[Deribit] options skew failed: %s", e)
            return {"signal": "N/A", "error": str(e), "source": "deribit"}

    cached = _macro_cached_get(f"deribit_skew_{currency}", 1800, _fetch)
    return cached if cached else {"signal": "N/A", "error": "cache miss", "source": "deribit"}


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 4: ON-CHAIN DASHBOARD — MVRV Z-SCORE · SOPR · EXCHANGE NET FLOW
# ─────────────────────────────────────────────────────────────────────────────

_CM_OC_CACHE: dict = {}
_CM_OC_LOCK = threading.Lock()
_CM_OC_TTL  = 3600   # 1-hour — CoinMetrics data is daily resolution


def fetch_coinmetrics_onchain(days: int = 400) -> dict:
    """
    Fetch real BTC on-chain metrics from CoinMetrics Community API (no key required).
    Cached 1 hour.

    Returns: mvrv_ratio, mvrv_z, mvrv_signal, realized_cap, sopr, sopr_signal,
             active_addresses, mvrv_history, sopr_history, source, timestamp, error
    """
    import datetime as _dt
    import statistics as _stats
    start     = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
    cache_key = f"cm_onchain_{days}"

    def _fetch():
        try:
            url    = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
            params = {
                "assets":     "btc",
                "metrics":    "CapMrktCurUSD,CapRealUSD,SoprNtv,AdrActCnt",
                "start_time": start,
                "frequency":  "1d",
                "page_size":  days + 10,
            }
            resp = _SESSION.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "source": "coinmetrics"}
            rows = resp.json().get("data", [])
            if not rows:
                return {"error": "empty response", "source": "coinmetrics"}

            mvrv_vals, mvrv_dates = [], []
            sopr_vals, sopr_dates = [], []
            real_caps, active_addrs = [], []

            for row in rows:
                t  = row.get("time", "")[:10]
                mc = row.get("CapMrktCurUSD")
                rc = row.get("CapRealUSD")
                sp = row.get("SoprNtv")
                aa = row.get("AdrActCnt")
                if mc and rc:
                    try:
                        mvrv_vals.append(float(mc) / float(rc))
                        mvrv_dates.append(t)
                        real_caps.append(float(rc))
                    except (ValueError, ZeroDivisionError):
                        pass
                if sp:
                    try:
                        sopr_vals.append(float(sp))
                        sopr_dates.append(t)
                    except ValueError:
                        pass
                if aa:
                    try:
                        active_addrs.append(int(float(aa)))
                    except ValueError:
                        pass

            if not mvrv_vals:
                return {"error": "no MVRV data", "source": "coinmetrics"}

            window   = min(365, len(mvrv_vals))
            trailing = mvrv_vals[-window:]
            mean_mv  = _stats.mean(trailing)
            std_mv   = _stats.stdev(trailing) if len(trailing) > 1 else 1.0
            cur_mvrv = mvrv_vals[-1]
            mvrv_z   = round((cur_mvrv - mean_mv) / max(std_mv, 1e-6), 2)

            if mvrv_z < -0.5:  mvrv_signal = "UNDERVALUED"
            elif mvrv_z < 1.5: mvrv_signal = "FAIR_VALUE"
            elif mvrv_z < 3.0: mvrv_signal = "OVERVALUED"
            else:               mvrv_signal = "EXTREME_HEAT"

            sopr = sopr_vals[-1] if sopr_vals else None
            if sopr is None:    sopr_signal = "N/A"
            elif sopr < 0.99:   sopr_signal = "CAPITULATION"
            elif sopr < 1.0:    sopr_signal = "MILD_LOSS"
            elif sopr < 1.02:   sopr_signal = "NORMAL"
            else:               sopr_signal = "PROFIT_TAKING"

            # NUPL = (Market Cap - Realized Cap) / Market Cap  (#25)
            market_cap = float(rows[-1].get("CapMrktCurUSD", 0) or 0)
            realized_cap_cur = real_caps[-1] if real_caps else 0
            nupl = None
            nupl_signal = "N/A"
            if market_cap > 0 and realized_cap_cur > 0:
                nupl = round((market_cap - realized_cap_cur) / market_cap, 4)
                if nupl < 0:         nupl_signal = "CAPITULATION"
                elif nupl < 0.25:    nupl_signal = "HOPE_FEAR"
                elif nupl < 0.50:    nupl_signal = "OPTIMISM"
                elif nupl < 0.75:    nupl_signal = "BELIEF_THRILL"
                else:                nupl_signal = "EUPHORIA"

            return {
                "mvrv_ratio":       round(cur_mvrv, 3),
                "mvrv_z":           mvrv_z,
                "mvrv_signal":      mvrv_signal,
                "realized_cap":     real_caps[-1] if real_caps else None,
                "sopr":             round(sopr, 4) if sopr else None,
                "sopr_signal":      sopr_signal,
                "active_addresses": active_addrs[-1] if active_addrs else None,
                "nupl":             nupl,
                "nupl_signal":      nupl_signal,
                "mvrv_history":     {mvrv_dates[i]: round(mvrv_vals[i], 3) for i in range(len(mvrv_dates))},
                "sopr_history":     {sopr_dates[i]: round(sopr_vals[i], 4) for i in range(len(sopr_dates))},
                "source":           "coinmetrics_community",
                "timestamp":        _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "error":            None,
            }
        except Exception as e:
            logging.debug("[CoinMetrics] onchain fetch failed: %s", e)
            return {"error": str(e), "source": "coinmetrics"}

    with _CM_OC_LOCK:
        hit = _CM_OC_CACHE.get(cache_key)
        if hit and (time.time() - hit.get("_ts", 0)) < _CM_OC_TTL:
            return hit

    result = _fetch()
    if result and not result.get("error"):
        result["_ts"] = time.time()
        with _CM_OC_LOCK:
            _CM_OC_CACHE[cache_key] = result
    return result if result else {"error": "fetch failed", "source": "coinmetrics"}


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 5: DERIBIT OPTIONS CHAIN — OI by Strike · P/C Ratio · IV Term Structure
# ─────────────────────────────────────────────────────────────────────────────

def fetch_deribit_options_chain(currency: str = "BTC") -> dict:
    """
    Fetch full options chain from Deribit public API (no key required).
    Computes OI by strike, put/call ratio, max pain, and IV term structure.
    Cached 15 min.

    Returns: put_call_ratio, max_pain, total_put_oi, total_call_oi,
             oi_by_strike (top 20), term_structure, signal, spot_price,
             source, timestamp, error.
    """
    import datetime as _dt5

    def _fetch():
        try:
            resp = _SESSION.get(
                "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
                params={"currency": currency, "kind": "option"},
                timeout=15,
            )
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "source": "deribit"}
            data = resp.json().get("result", [])
            if not data:
                return {"error": "empty response", "source": "deribit"}

            now  = _dt5.datetime.now(_dt5.timezone.utc)
            spot = None
            oi_by_strike: dict = {}
            expiry_data:  dict = {}

            for item in data:
                name  = item.get("instrument_name", "")
                parts = name.split("-")
                if len(parts) < 4:
                    continue
                try:
                    exp = _dt5.datetime.strptime(parts[1], "%d%b%y").replace(tzinfo=_dt5.timezone.utc)
                except ValueError:
                    try:
                        exp = _dt5.datetime.strptime(parts[1], "%d%b%Y").replace(tzinfo=_dt5.timezone.utc)
                    except ValueError:
                        continue
                dte = (exp - now).days
                if dte < 0:
                    continue
                try:
                    strike = float(parts[2])
                except ValueError:
                    continue
                opt_type = parts[3].upper()
                oi       = float(item.get("open_interest") or 0)
                mark_iv  = item.get("mark_iv")
                if spot is None:
                    spot = item.get("underlying_price")

                if strike not in oi_by_strike:
                    oi_by_strike[strike] = {"put_oi": 0.0, "call_oi": 0.0}
                if opt_type == "P":
                    oi_by_strike[strike]["put_oi"] += oi
                else:
                    oi_by_strike[strike]["call_oi"] += oi

                exp_str = exp.strftime("%Y-%m-%d")
                if exp_str not in expiry_data:
                    expiry_data[exp_str] = {"dte": dte, "put_oi": 0.0, "call_oi": 0.0, "atm_data": []}
                if opt_type == "P":
                    expiry_data[exp_str]["put_oi"] += oi
                else:
                    expiry_data[exp_str]["call_oi"] += oi
                if mark_iv and spot:
                    expiry_data[exp_str]["atm_data"].append((abs(strike - float(spot)), float(mark_iv), opt_type))

            if not oi_by_strike:
                return {"error": "no options data parsed", "source": "deribit"}

            total_put_oi  = sum(v["put_oi"]  for v in oi_by_strike.values())
            total_call_oi = sum(v["call_oi"] for v in oi_by_strike.values())
            pc_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None

            # Max pain: strike minimising total payout to option buyers
            max_pain_strike = None
            min_pain = None
            for s in sorted(oi_by_strike.keys()):
                pain = sum(
                    max(s - k, 0) * v["call_oi"] + max(k - s, 0) * v["put_oi"]
                    for k, v in oi_by_strike.items()
                )
                if min_pain is None or pain < min_pain:
                    min_pain = pain
                    max_pain_strike = s

            # Top 20 strikes by total OI
            oi_list = [
                {"strike": k, "put_oi": round(v["put_oi"], 1),
                 "call_oi": round(v["call_oi"], 1),
                 "total_oi": round(v["put_oi"] + v["call_oi"], 1)}
                for k, v in oi_by_strike.items() if v["put_oi"] + v["call_oi"] > 0
            ]
            oi_list.sort(key=lambda x: x["total_oi"], reverse=True)
            top20 = sorted(oi_list[:20], key=lambda x: x["strike"])

            # IV term structure: ATM call IV per expiry
            term_structure = []
            for exp_str, ed in sorted(expiry_data.items()):
                atm_iv = None
                if ed["atm_data"]:
                    calls_atm = sorted([(d, iv) for d, iv, t in ed["atm_data"] if t == "C"])[:3]
                    puts_atm  = sorted([(d, iv) for d, iv, t in ed["atm_data"] if t == "P"])[:3]
                    src = calls_atm or puts_atm
                    if src:
                        atm_iv = round(sum(iv for _, iv in src) / len(src), 1)
                term_structure.append({
                    "expiry":  exp_str,
                    "dte":     ed["dte"],
                    "atm_iv":  atm_iv,
                    "put_oi":  round(ed["put_oi"], 1),
                    "call_oi": round(ed["call_oi"], 1),
                })

            if pc_ratio is None:      signal = "N/A"
            elif pc_ratio > 1.5:      signal = "EXTREME_PUTS"
            elif pc_ratio > 1.1:      signal = "BEARISH"
            elif pc_ratio < 0.6:      signal = "EXTREME_CALLS"
            elif pc_ratio < 0.9:      signal = "BULLISH"
            else:                     signal = "NEUTRAL"

            return {
                "put_call_ratio":  pc_ratio,
                "max_pain":        max_pain_strike,
                "total_put_oi":    round(total_put_oi, 1),
                "total_call_oi":   round(total_call_oi, 1),
                "oi_by_strike":    top20,
                "term_structure":  term_structure,
                "signal":          signal,
                "spot_price":      spot,
                "source":          "deribit",
                "timestamp":       _dt5.datetime.now(_dt5.timezone.utc).isoformat(),
                "error":           None,
            }
        except Exception as e:
            logging.debug("[Deribit] options chain failed: %s", e)
            return {"error": str(e), "source": "deribit"}

    cached = _macro_cached_get(f"deribit_chain_{currency}", 900, _fetch)
    return cached if cached else {"error": "cache miss", "source": "deribit"}


# ─────────────────────────────────────────────────────────────────────────────
# PI CYCLE TOP INDICATOR  (#26)
# ─────────────────────────────────────────────────────────────────────────────
# Uses 111-day SMA and 350-day SMA × 2 from BTC daily closes (Binance free).
# Signal: when 111DMA ≥ 350DMA×2 → BUY suppressor / CYCLE_TOP warning.
# Historically accurate to within 3 days at the 2013, 2017, 2021 cycle tops.
# ─────────────────────────────────────────────────────────────────────────────

_PI_CACHE: dict = {}
_PI_LOCK = threading.Lock()


def fetch_pi_cycle_top() -> dict:
    """
    Compute Pi Cycle Top indicator from Binance BTC/USDT daily klines (free, no key).

    Returns:
        sma_111     — 111-day simple moving average
        sma_350x2   — 350-day SMA × 2
        gap_pct     — % gap between sma_111 and sma_350x2 (negative = approaching top)
        signal      — NORMAL | CAUTION | CYCLE_TOP
        source      — "binance" | "fallback"
    """
    import datetime as _dt

    def _fetch():
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": "BTCUSDT", "interval": "1d", "limit": 500}
            resp = _SESSION.get(url, params=params, timeout=15)
            if resp.status_code != 200:
                return None
            data = resp.json()
            closes = [float(k[4]) for k in data if k[4]]
            if len(closes) < 380:   # 30-point buffer beyond 350 required
                return None

            sma_111  = sum(closes[-111:]) / 111
            sma_350  = sum(closes[-350:]) / 350
            sma_350x2 = sma_350 * 2
            gap_pct   = round((sma_111 - sma_350x2) / sma_350x2 * 100, 2)

            if gap_pct >= 0:
                signal = "CYCLE_TOP"        # 111DMA crossed above 350DMA×2
            elif gap_pct >= -5:
                signal = "CAUTION"          # within 5% — approaching top zone
            else:
                signal = "NORMAL"

            return {
                "sma_111":    round(sma_111, 0),
                "sma_350x2":  round(sma_350x2, 0),
                "gap_pct":    gap_pct,
                "signal":     signal,
                "source":     "binance",
                "timestamp":  _dt.datetime.now(_dt.timezone.utc).isoformat(),
            }
        except Exception as e:
            logging.debug("[PiCycle] fetch failed: %s", e)
            return None

    with _PI_LOCK:
        cached = _PI_CACHE.get("pi_cycle")
        if cached and (time.time() - cached["_ts"]) < 3600:
            return cached["data"]
    data = _fetch()
    if data:
        with _PI_LOCK:
            _PI_CACHE["pi_cycle"] = {"data": data, "_ts": time.time()}
        return data
    import datetime as _dt6
    return {"signal": "NORMAL", "gap_pct": None, "sma_111": None, "sma_350x2": None,
            "source": "fallback", "timestamp": _dt6.datetime.now(_dt6.timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# SPARKLINE DATA  (#60)
# Fetch last N 1-hour close prices for a pair — used for mini sparkline charts
# ─────────────────────────────────────────────────────────────────────────────

_SPARKLINE_CACHE: dict = {}
_SPARKLINE_LOCK = threading.Lock()
_SPARKLINE_TTL  = 300  # 5 min


def fetch_sparkline_closes(pair: str, n: int = 24) -> list[float]:
    """
    Return the last `n` 1-hour close prices for `pair` (e.g. "BTC/USDT").
    Uses Binance public klines endpoint; returns empty list on error.
    Results cached 5 minutes per pair.
    """
    cache_key = f"{pair}_{n}"
    with _SPARKLINE_LOCK:
        entry = _SPARKLINE_CACHE.get(cache_key)
        if entry and (time.time() - entry["_ts"]) < _SPARKLINE_TTL:
            return entry["data"]

    try:
        symbol = pair.replace("/", "")
        url = (
            f"https://api.binance.com/api/v3/klines"
            f"?symbol={symbol}&interval=1h&limit={n}"
        )
        resp = _SESSION.get(url, timeout=6)
        resp.raise_for_status()
        closes = [float(k[4]) for k in resp.json() if k[4]]
        with _SPARKLINE_LOCK:
            _SPARKLINE_CACHE[cache_key] = {"data": closes, "_ts": time.time()}
        return closes
    except Exception as e:
        logging.debug("[Sparkline] %s fetch failed: %s", pair, e)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# REGIONAL EXCHANGE PRICE FEEDS  (#89)
# MEXC (Asia), Bitso (LatAm/MXN), CoinDCX (India/INR)
# Shows regional price premium/discount vs Binance global benchmark
# ─────────────────────────────────────────────────────────────────────────────

_REGIONAL_CACHE: dict = {}
_REGIONAL_LOCK = threading.Lock()
_REGIONAL_TTL  = 120  # 2 min


def fetch_regional_exchange_prices(pair: str = "BTC/USDT") -> dict:
    """
    Fetch prices from MEXC, Bitso (MXN), and CoinDCX (INR) for regional premium signals.

    Returns dict with:
        pair, binance_price, mexc_price, mexc_premium_pct,
        bitso_mxn, bitso_usd_equiv, coindcx_inr, coindcx_usd_equiv, errors
    """
    cache_key = pair
    with _REGIONAL_LOCK:
        entry = _REGIONAL_CACHE.get(cache_key)
        if entry and (time.time() - entry["_ts"]) < _REGIONAL_TTL:
            return entry["data"]

    symbol = pair.replace("/", "")   # "BTCUSDT"
    base   = pair.split("/")[0]      # "BTC"

    result: dict = {
        "pair": pair, "binance_price": None, "mexc_price": None,
        "mexc_premium_pct": None, "bitso_mxn": None, "bitso_usd_equiv": None,
        "coindcx_inr": None, "coindcx_usd_equiv": None, "errors": [],
    }

    # 1. Binance baseline
    try:
        r = _SESSION.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
            timeout=5,
        )
        if r.status_code == 200:
            result["binance_price"] = float(r.json().get("price", 0) or 0)
    except Exception as e:
        result["errors"].append(f"binance:{e}")

    # 2. MEXC — same symbol format, no auth required
    try:
        r = _SESSION.get(
            f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}",
            timeout=5,
        )
        if r.status_code == 200:
            mexc_price = float(r.json().get("price", 0) or 0)
            result["mexc_price"] = mexc_price
            bp = result["binance_price"]
            if bp and bp > 0:
                result["mexc_premium_pct"] = round((mexc_price - bp) / bp * 100, 4)
    except Exception as e:
        result["errors"].append(f"mexc:{e}")

    # 3. Bitso — BTC/MXN or ETH/MXN book
    try:
        book = f"{base.lower()}_mxn"
        r = _SESSION.get(f"https://bitso.com/api/v3/ticker/?book={book}", timeout=5)
        if r.status_code == 200:
            last_mxn = float((r.json().get("payload") or {}).get("last", 0) or 0)
            result["bitso_mxn"] = last_mxn
            # MXN→USD conversion: Binance has no MXN spot pairs (USDCMXN / USDTMXN
            # are not listed), so use a hardcoded fallback rate.
            mxn_rate = 17.5
            result["bitso_usd_equiv"] = round(last_mxn / mxn_rate, 2) if mxn_rate > 0 else None
    except Exception as e:
        result["errors"].append(f"bitso:{e}")

    # 4. CoinDCX — INR markets
    try:
        r = _SESSION.get("https://api.coindcx.com/exchange/ticker", timeout=6)
        if r.status_code == 200:
            tickers = r.json()
            target_market = f"B-{base}_INR"
            for t in tickers:
                if t.get("market") == target_market:
                    last_inr = float(t.get("last_price", 0) or 0)
                    result["coindcx_inr"] = last_inr
                    try:
                        r2 = _SESSION.get(
                            "https://api.binance.com/api/v3/ticker/price?symbol=USDTINR",
                            timeout=4,
                        )
                        inr_rate = float(r2.json().get("price", 83.5) or 83.5) if r2.status_code == 200 else 83.5
                    except Exception:
                        inr_rate = 83.5
                    result["coindcx_usd_equiv"] = round(last_inr / inr_rate, 2) if inr_rate > 0 else None
                    break
    except Exception as e:
        result["errors"].append(f"coindcx:{e}")

    with _REGIONAL_LOCK:
        _REGIONAL_CACHE[cache_key] = {"data": result, "_ts": time.time()}

    return result


# ─────────────────────────────────────────────────────────────────────────────
# DEX PRICE FEEDS  (#91)
# Jupiter (Solana aggregator), dYdX v4 (Cosmos chain), Raydium (Solana AMM)
# Provides on-chain prices for Solana-native and perp pairs
# ─────────────────────────────────────────────────────────────────────────────

_DEX_PRICE_CACHE: dict = {}
_DEX_PRICE_LOCK = threading.Lock()
_DEX_PRICE_TTL  = 60  # 1 min

# Solana token mint addresses for Jupiter price API
_JUPITER_MINTS: dict = {
    "SOL":  "So11111111111111111111111111111111111111112",
    "JUP":  "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "WIF":  "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
    "RAY":  "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
}

# dYdX v4 market IDs for perp oracle prices
_DYDX_MARKETS: dict = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
    "JUP": "JUP-USD", "WIF": "WIF-USD", "AVAX": "AVAX-USD",
    "LINK": "LINK-USD", "XRP": "XRP-USD",
}

# Raydium token mints (subset — primary Solana tokens)
_RAYDIUM_MINTS: dict = {
    "SOL": "So11111111111111111111111111111111111111112",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
}


def fetch_dex_prices(tokens: list = None) -> dict:
    """
    Fetch token prices from DEX aggregators.

    Priority order per token:
      1. Jupiter (best for Solana-native tokens)
      2. dYdX v4 oracle (good for BTC/ETH/SOL/major pairs)
      3. Raydium (fallback for Solana tokens)

    Args:
        tokens: list of token symbols (e.g. ["JUP", "WIF", "SOL"])

    Returns:
        dict keyed by symbol: {"price": float, "source": str, "dex": str}
    """
    _defaults = ["JUP", "WIF", "PYTH", "SOL", "RAY"]
    targets = {t.upper() for t in (tokens or _defaults)}

    cache_key = ",".join(sorted(targets))
    with _DEX_PRICE_LOCK:
        entry = _DEX_PRICE_CACHE.get(cache_key)
        if entry and (time.time() - entry["_ts"]) < _DEX_PRICE_TTL:
            return entry["data"]

    prices: dict = {}

    # 1. Jupiter Price API (Solana-native tokens)
    jup_targets = {sym: mint for sym, mint in _JUPITER_MINTS.items() if sym in targets}
    if jup_targets:
        try:
            ids_str = ",".join(jup_targets.values())
            r = _SESSION.get(f"https://price.jup.ag/v6/price?ids={ids_str}", timeout=6)
            if r.status_code == 200:
                jup_data = r.json().get("data", {})
                for sym, mint in jup_targets.items():
                    if mint in jup_data:
                        prices[sym] = {
                            "price": float(jup_data[mint].get("price", 0) or 0),
                            "source": "jupiter",
                            "dex": "Jupiter Aggregator",
                        }
        except Exception as e:
            logging.debug("[DEX] Jupiter fetch failed: %s", e)

    # 2. dYdX v4 Indexer — oracle mark prices
    dydx_targets = {sym: mkt for sym, mkt in _DYDX_MARKETS.items()
                    if sym in targets and sym not in prices}
    if dydx_targets:
        try:
            r = _SESSION.get("https://indexer.dydx.trade/v4/markets", timeout=6)
            if r.status_code == 200:
                markets = r.json().get("markets", {})
                for sym, mkt_id in dydx_targets.items():
                    mkt = markets.get(mkt_id, {})
                    oracle_price = float(mkt.get("oraclePrice") or 0)
                    if oracle_price > 0:
                        prices[sym] = {
                            "price": oracle_price,
                            "source": "dydx_v4",
                            "dex": "dYdX v4 (Cosmos)",
                        }
        except Exception as e:
            logging.debug("[DEX] dYdX fetch failed: %s", e)

    # 3. Raydium — fallback for Solana tokens not yet priced
    ray_targets = {sym: mint for sym, mint in _RAYDIUM_MINTS.items()
                   if sym in targets and sym not in prices}
    if ray_targets:
        try:
            ids_str = ",".join(ray_targets.values())
            r = _SESSION.get(f"https://api.raydium.io/v2/main/price?ids={ids_str}", timeout=6)
            if r.status_code == 200:
                ray_data = r.json()
                for sym, mint in ray_targets.items():
                    p = ray_data.get(mint)
                    if p and float(p) > 0:
                        prices[sym] = {
                            "price": float(p),
                            "source": "raydium",
                            "dex": "Raydium AMM",
                        }
        except Exception as e:
            logging.debug("[DEX] Raydium fetch failed: %s", e)

    with _DEX_PRICE_LOCK:
        _DEX_PRICE_CACHE[cache_key] = {"data": prices, "_ts": time.time()}

    return prices


# ══════════════════════════════════════════════════════════════════════════════
# DERIBIT OPTIONS OPEN INTEREST + IMPLIED VOLATILITY
# Free public API — no auth required — BTC and ETH options only
# GET https://www.deribit.com/api/v2/public/get_book_summary_by_currency
# ══════════════════════════════════════════════════════════════════════════════

_DERIBIT_OI_CACHE: dict = {"ts": 0.0, "data": None}
_DERIBIT_OI_LOCK  = threading.Lock()
_DERIBIT_OI_TTL   = 300  # 5-minute cache

_DERIBIT_OI_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"


def fetch_deribit_options_data() -> dict:
    """
    Fetch BTC and ETH options open interest and implied volatility from Deribit.
    Uses the free public endpoint — no API key required.

    Returns:
        btc_oi        : float  — total BTC options open interest (in BTC)
        eth_oi        : float  — total ETH options open interest (in ETH)
        btc_iv_30d    : float  — weighted average mark IV across BTC options (%)
        eth_iv_30d    : float  — weighted average mark IV across ETH options (%)
        btc_oi_usd    : float  — BTC OI in approximate USD (OI * mark price)
        eth_oi_usd    : float  — ETH OI in approximate USD
        source        : str    — 'deribit'
        error         : str | None
    """
    now = time.time()
    with _DERIBIT_OI_LOCK:
        if _DERIBIT_OI_CACHE["data"] is not None and (now - _DERIBIT_OI_CACHE["ts"]) < _DERIBIT_OI_TTL:
            return dict(_DERIBIT_OI_CACHE["data"])

    _neutral = {
        "btc_oi": 0.0, "eth_oi": 0.0,
        "btc_iv_30d": 0.0, "eth_iv_30d": 0.0,
        "btc_oi_usd": 0.0, "eth_oi_usd": 0.0,
        "source": "deribit", "error": "Deribit OI unavailable",
    }

    def _fetch_currency(currency: str) -> tuple[float, float, float]:
        """Returns (total_oi, weighted_iv, oi_usd)."""
        try:
            resp = _SESSION.get(
                _DERIBIT_OI_URL,
                params={"currency": currency, "kind": "option"},
                timeout=10,
            )
            if resp.status_code != 200:
                return 0.0, 0.0, 0.0
            instruments = resp.json().get("result", [])
            if not instruments:
                return 0.0, 0.0, 0.0

            total_oi = 0.0
            iv_weighted_sum = 0.0
            iv_weight_total = 0.0
            oi_usd = 0.0

            for inst in instruments:
                oi = float(inst.get("open_interest") or 0.0)
                mark_price = float(inst.get("mark_price") or 0.0)
                underlying_price = float(inst.get("underlying_price") or 0.0)
                mark_iv = float(inst.get("mark_iv") or 0.0)

                total_oi += oi
                if mark_iv > 0 and oi > 0:
                    iv_weighted_sum += mark_iv * oi
                    iv_weight_total += oi
                if underlying_price > 0:
                    oi_usd += oi * underlying_price
                elif mark_price > 0:
                    oi_usd += oi * mark_price

            weighted_iv = iv_weighted_sum / iv_weight_total if iv_weight_total > 0 else 0.0
            return round(total_oi, 2), round(weighted_iv, 2), round(oi_usd, 0)
        except Exception as _e:
            logging.debug("[DeribitOI] %s fetch failed: %s", currency, _e)
            return 0.0, 0.0, 0.0

    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            btc_fut = ex.submit(_fetch_currency, "BTC")
            eth_fut = ex.submit(_fetch_currency, "ETH")
            btc_oi, btc_iv, btc_oi_usd = btc_fut.result()
            eth_oi, eth_iv, eth_oi_usd = eth_fut.result()

        result = {
            "btc_oi":      btc_oi,
            "eth_oi":      eth_oi,
            "btc_iv_30d":  btc_iv,
            "eth_iv_30d":  eth_iv,
            "btc_oi_usd":  btc_oi_usd,
            "eth_oi_usd":  eth_oi_usd,
            "source":      "deribit",
            "error":       None,
        }
        with _DERIBIT_OI_LOCK:
            _DERIBIT_OI_CACHE["data"] = result
            _DERIBIT_OI_CACHE["ts"]   = now
        return result
    except Exception as e:
        logging.warning("[DeribitOI] fetch failed: %s", e)
        return {**_neutral, "error": str(e)[:120]}


# ══════════════════════════════════════════════════════════════════════════════
# REGIONAL EXCHANGE PREMIUMS
# Fetches BTC price from regional exchanges and computes premium vs Binance.
# Regional exchanges: Bitso (MXN), Mercado Bitcoin (BRL), CoinDCX (INR), Upbit (KRW)
# FX rates from exchangerate-api.com (free, no key)
# ══════════════════════════════════════════════════════════════════════════════

_REGPREM_CACHE: dict = {"ts": 0.0, "data": None}
_REGPREM_LOCK  = threading.Lock()
_REGPREM_TTL   = 300  # 5-minute cache

_FX_CACHE: dict = {"ts": 0.0, "rates": None}
_FX_LOCK  = threading.Lock()
_FX_TTL   = 3600  # 1-hour cache for FX rates


def _fetch_fx_rates() -> dict:
    """Fetch USD FX rates from exchangerate-api.com (free, no key). Returns {currency: rate_to_usd}."""
    now = time.time()
    with _FX_LOCK:
        if _FX_CACHE["rates"] is not None and (now - _FX_CACHE["ts"]) < _FX_TTL:
            return dict(_FX_CACHE["rates"])

    try:
        resp = _SESSION.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=10)
        if resp.status_code == 200:
            rates = resp.json().get("rates", {})
            with _FX_LOCK:
                _FX_CACHE["rates"] = rates
                _FX_CACHE["ts"]    = now
            return rates
    except Exception as e:
        logging.debug("[FX] exchangerate-api fetch failed: %s", e)

    # Fallback: approximate rates as of early 2025
    return {"MXN": 17.5, "BRL": 5.0, "INR": 84.0, "KRW": 1350.0, "USD": 1.0}


def _fetch_binance_btc_price() -> float:
    """Fetch current BTC/USDT price from Binance spot."""
    try:
        r = _SESSION.get(
            f"{_BINANCE_SPOT_BASE}/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=6,
        )
        if r.status_code == 200:
            return float(r.json().get("price", 0))
    except Exception as e:
        logging.debug("[RegionalPrem] Binance BTC price failed: %s", e)
    return 0.0


def fetch_regional_premiums() -> dict:
    """
    Fetch BTC premiums on regional exchanges vs Binance global price.
    Computes premium as: ((regional_price_usd / binance_price) - 1) * 100

    Regional exchanges:
      - Bitso (Mexico, MXN): BTC/MXN
      - Mercado Bitcoin (Brazil, BRL): BTC/BRL via REST API
      - CoinDCX (India, INR): BTC/INR
      - Upbit (South Korea, KRW): BTC/KRW

    Returns:
        {
          "mexico_pct":  float,   # Bitso BTC/MXN premium vs Binance (%)
          "brazil_pct":  float,   # Mercado Bitcoin premium (%)
          "india_pct":   float,   # CoinDCX premium (%)
          "korea_pct":   float,   # Upbit premium / kimchi premium (%)
          "binance_btc_usd": float,
          "source": "regional_exchanges",
          "error": str | None
        }
    """
    now = time.time()
    with _REGPREM_LOCK:
        if _REGPREM_CACHE["data"] is not None and (now - _REGPREM_CACHE["ts"]) < _REGPREM_TTL:
            return dict(_REGPREM_CACHE["data"])

    _neutral = {
        "mexico_pct": 0.0, "brazil_pct": 0.0,
        "india_pct":  0.0, "korea_pct":  0.0,
        "binance_btc_usd": 0.0,
        "source": "regional_exchanges", "error": "Regional premiums unavailable",
    }

    try:
        # Fetch FX rates and Binance reference price in parallel
        with ThreadPoolExecutor(max_workers=2) as _ex:
            fx_fut  = _ex.submit(_fetch_fx_rates)
            btc_fut = _ex.submit(_fetch_binance_btc_price)
            fx_rates   = fx_fut.result()
            binance_btc = btc_fut.result()

        if binance_btc <= 0:
            return {**_neutral, "error": "Binance BTC price unavailable"}

        premiums: dict[str, float] = {}

        # ── Bitso (Mexico) — BTC/MXN ─────────────────────────────────────────
        try:
            r = _SESSION.get("https://bitso.com/api/v3/ticker/?book=btc_mxn", timeout=10)
            if r.status_code == 200:
                last_mxn = float(r.json().get("payload", {}).get("last", 0) or 0)
                mxn_rate = fx_rates.get("MXN", 17.5)
                if last_mxn > 0 and mxn_rate > 0:
                    btc_usd_bitso = last_mxn / mxn_rate
                    premiums["mexico_pct"] = round((btc_usd_bitso / binance_btc - 1) * 100, 3)
        except Exception as _e:
            logging.debug("[RegionalPrem] Bitso failed: %s", _e)
        premiums.setdefault("mexico_pct", 0.0)

        # ── Mercado Bitcoin (Brazil) — BTC/BRL ───────────────────────────────
        try:
            r = _SESSION.get("https://www.mercadobitcoin.net/api/BTC/ticker/", timeout=10)
            if r.status_code == 200:
                last_brl = float(r.json().get("ticker", {}).get("last", 0) or 0)
                brl_rate = fx_rates.get("BRL", 5.0)
                if last_brl > 0 and brl_rate > 0:
                    btc_usd_mb = last_brl / brl_rate
                    premiums["brazil_pct"] = round((btc_usd_mb / binance_btc - 1) * 100, 3)
        except Exception as _e:
            logging.debug("[RegionalPrem] MercadoBitcoin failed: %s", _e)
        premiums.setdefault("brazil_pct", 0.0)

        # ── CoinDCX (India) — BTC/INR ─────────────────────────────────────────
        try:
            r = _SESSION.get("https://api.coindcx.com/exchange/ticker", timeout=10)
            if r.status_code == 200:
                tickers = r.json()
                btc_inr_ticker = next(
                    (t for t in tickers if t.get("market") in ("BTCINR", "BTC_INR")), None
                )
                if btc_inr_ticker:
                    last_inr = float(btc_inr_ticker.get("last_price", 0) or 0)
                    inr_rate = fx_rates.get("INR", 84.0)
                    if last_inr > 0 and inr_rate > 0:
                        btc_usd_dcx = last_inr / inr_rate
                        premiums["india_pct"] = round((btc_usd_dcx / binance_btc - 1) * 100, 3)
        except Exception as _e:
            logging.debug("[RegionalPrem] CoinDCX failed: %s", _e)
        premiums.setdefault("india_pct", 0.0)

        # ── Upbit (South Korea) — BTC/KRW (kimchi premium) ───────────────────
        try:
            r = _SESSION.get(
                "https://api.upbit.com/v1/ticker",
                params={"markets": "KRW-BTC"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                last_krw = float(data[0].get("trade_price", 0) if data else 0)
                krw_rate = fx_rates.get("KRW", 1350.0)
                if last_krw > 0 and krw_rate > 0:
                    btc_usd_upbit = last_krw / krw_rate
                    premiums["korea_pct"] = round((btc_usd_upbit / binance_btc - 1) * 100, 3)
        except Exception as _e:
            logging.debug("[RegionalPrem] Upbit failed: %s", _e)
        premiums.setdefault("korea_pct", 0.0)

        result = {
            "mexico_pct":      premiums["mexico_pct"],
            "brazil_pct":      premiums["brazil_pct"],
            "india_pct":       premiums["india_pct"],
            "korea_pct":       premiums["korea_pct"],
            "binance_btc_usd": round(binance_btc, 2),
            "source":          "regional_exchanges",
            "error":           None,
        }
        with _REGPREM_LOCK:
            _REGPREM_CACHE["data"] = result
            _REGPREM_CACHE["ts"]   = now
        return result

    except Exception as e:
        logging.warning("[RegionalPrem] fetch failed: %s", e)
        return {**_neutral, "error": str(e)[:120]}


# ══════════════════════════════════════════════════════════════════════════════
# COINMARKETCAP GLOBAL METRICS
# Requires COINMARKETCAP_API_KEY env var (free tier at coinmarketcap.com)
# Returns total market cap, BTC dominance, ETH dominance, 24h volume
# ══════════════════════════════════════════════════════════════════════════════

_CMC_CACHE: dict = {"ts": 0.0, "data": None}
_CMC_LOCK  = threading.Lock()
_CMC_TTL   = 600  # 10-minute cache

_CMC_GLOBAL_URL = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"


def fetch_cmc_global_metrics() -> dict:
    """
    Fetch global crypto market metrics from CoinMarketCap.
    Requires COINMARKETCAP_API_KEY environment variable (free tier: 333 req/day).

    Returns:
        total_market_cap_usd  : float — total crypto market cap in USD
        btc_dominance_pct     : float — BTC % of total market cap
        eth_dominance_pct     : float — ETH % of total market cap
        total_volume_24h      : float — 24h total trading volume USD
        active_cryptocurrencies: int  — number of active cryptocurrencies
        active_exchanges      : int   — number of active exchanges
        source                : str   — 'coinmarketcap'
        error                 : str | None

    Returns empty dict (with error key) if COINMARKETCAP_API_KEY is not set.
    """
    api_key = _os.environ.get("COINMARKETCAP_API_KEY", "").strip()
    if not api_key:
        # Also check alerts_config.json (same pattern as other paid APIs)
        try:
            keys = _load_api_keys()
            api_key = keys.get("coinmarketcap_key", "").strip()
        except Exception:
            pass

    if not api_key:
        return {
            "total_market_cap_usd": 0.0, "btc_dominance_pct": 0.0,
            "eth_dominance_pct": 0.0, "total_volume_24h": 0.0,
            "active_cryptocurrencies": 0, "active_exchanges": 0,
            "source": "coinmarketcap",
            "error": "COINMARKETCAP_API_KEY not set — add to env or alerts_config.json",
        }

    now = time.time()
    with _CMC_LOCK:
        if _CMC_CACHE["data"] is not None and (now - _CMC_CACHE["ts"]) < _CMC_TTL:
            return dict(_CMC_CACHE["data"])

    try:
        resp = _SESSION.get(
            _CMC_GLOBAL_URL,
            headers={"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 401:
            return {
                "total_market_cap_usd": 0.0, "btc_dominance_pct": 0.0,
                "eth_dominance_pct": 0.0, "total_volume_24h": 0.0,
                "active_cryptocurrencies": 0, "active_exchanges": 0,
                "source": "coinmarketcap", "error": "Invalid CMC API key (401)",
            }
        if resp.status_code != 200:
            return {
                "total_market_cap_usd": 0.0, "btc_dominance_pct": 0.0,
                "eth_dominance_pct": 0.0, "total_volume_24h": 0.0,
                "active_cryptocurrencies": 0, "active_exchanges": 0,
                "source": "coinmarketcap",
                "error": f"CMC API HTTP {resp.status_code}",
            }

        body = resp.json()
        data = body.get("data", {})
        quote = data.get("quote", {}).get("USD", {})

        total_mcap   = float(quote.get("total_market_cap", 0) or 0)
        btc_dom      = float(data.get("btc_dominance", 0) or 0)
        eth_dom      = float(data.get("eth_dominance", 0) or 0)
        total_vol    = float(quote.get("total_volume_24h", 0) or 0)
        active_coins = int(data.get("active_cryptocurrencies", 0) or 0)
        active_exch  = int(data.get("active_exchanges", 0) or 0)

        result = {
            "total_market_cap_usd":   round(total_mcap, 0),
            "btc_dominance_pct":      round(btc_dom, 2),
            "eth_dominance_pct":      round(eth_dom, 2),
            "total_volume_24h":       round(total_vol, 0),
            "active_cryptocurrencies": active_coins,
            "active_exchanges":        active_exch,
            "source":                 "coinmarketcap",
            "error":                  None,
        }
        with _CMC_LOCK:
            _CMC_CACHE["data"] = result
            _CMC_CACHE["ts"]   = now
        return result

    except Exception as e:
        logging.warning("[CMC] global metrics fetch failed: %s", e)
        return {
            "total_market_cap_usd": 0.0, "btc_dominance_pct": 0.0,
            "eth_dominance_pct": 0.0, "total_volume_24h": 0.0,
            "active_cryptocurrencies": 0, "active_exchanges": 0,
            "source": "coinmarketcap", "error": str(e)[:120],
        }


# ══════════════════════════════════════════════════════════════════════════════
# #34 — DERIBIT PUT/CALL RATIO SIGNAL
# Fetches open interest split by option type (PUT vs CALL) for BTC and ETH.
# PCR = put_OI / call_OI.  Contrarian signal: crowded puts = potential rally.
# Cached 15 minutes — Deribit public API, no key required.
# ══════════════════════════════════════════════════════════════════════════════

_PCR_CACHE: dict = {"ts": 0.0, "data": None}
_PCR_LOCK  = threading.Lock()
_PCR_TTL   = 900  # 15 minutes


def _pcr_signal(pcr: float) -> str:
    """Contrarian PCR signal thresholds.  pcr == 0.0 means fetch failed → NEUTRAL."""
    if pcr <= 0.0:
        return "NEUTRAL"
    if pcr > 1.2:
        return "BEARISH_SENTIMENT"
    if pcr < 0.7:
        return "BULLISH_SENTIMENT"
    return "NEUTRAL"


def _fetch_pcr_for_currency(currency: str) -> float:
    """
    Fetch put/call OI ratio for a single Deribit currency.
    Returns PCR float or 0.0 on failure.
    """
    try:
        resp = _SESSION.get(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
            params={"currency": currency, "kind": "option"},
            timeout=15,
        )
        if resp.status_code != 200:
            return 0.0
        instruments = resp.json().get("result", [])
        if not instruments:
            return 0.0
        put_oi  = 0.0
        call_oi = 0.0
        for item in instruments:
            name = item.get("instrument_name", "")
            parts = name.split("-")
            if len(parts) < 4:
                continue
            opt_type = parts[3].upper()
            oi       = float(item.get("open_interest") or 0.0)
            if opt_type == "P":
                put_oi  += oi
            elif opt_type == "C":
                call_oi += oi
        if call_oi <= 0:
            return 0.0
        return round(put_oi / call_oi, 3)
    except Exception as _e:
        logging.debug("[PCR] %s fetch failed: %s", currency, _e)
        return 0.0


def fetch_deribit_pcr(currency: str = "BTC") -> dict:
    """
    #34 — Deribit Put/Call Ratio signal for BTC and ETH.

    Fetches full options chain and computes aggregate OI-based P/C ratio.
    Contrarian logic: heavy put buying (PCR > 1.2) = BEARISH_SENTIMENT (crowds fear).
    Light put buying (PCR < 0.7) = BULLISH_SENTIMENT (overconfidence / squeeze risk).

    Returns:
        btc_pcr     : float — BTC put/call OI ratio
        eth_pcr     : float — ETH put/call OI ratio
        btc_signal  : str   — BEARISH_SENTIMENT | BULLISH_SENTIMENT | NEUTRAL
        eth_signal  : str   — same
        timestamp   : str   — ISO timestamp
        source      : str
        error       : str | None
    """
    now = time.time()
    with _PCR_LOCK:
        if _PCR_CACHE["data"] is not None and (now - _PCR_CACHE["ts"]) < _PCR_TTL:
            return dict(_PCR_CACHE["data"])

    _neutral = {
        "btc_pcr": 0.0, "eth_pcr": 0.0,
        "btc_signal": "NEUTRAL", "eth_signal": "NEUTRAL",
        "timestamp": "", "source": "deribit", "error": "PCR unavailable",
    }

    try:
        import datetime as _dt34
        with ThreadPoolExecutor(max_workers=2) as _ex:
            btc_fut = _ex.submit(_fetch_pcr_for_currency, "BTC")
            eth_fut = _ex.submit(_fetch_pcr_for_currency, "ETH")
            btc_pcr = btc_fut.result()
            eth_pcr = eth_fut.result()

        if btc_pcr == 0.0 and eth_pcr == 0.0:
            return {**_neutral, "error": "No options data from Deribit"}

        ts = _dt34.datetime.now(_dt34.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = {
            "btc_pcr":    btc_pcr,
            "eth_pcr":    eth_pcr,
            "btc_signal": _pcr_signal(btc_pcr),
            "eth_signal": _pcr_signal(eth_pcr),
            "timestamp":  ts,
            "source":     "deribit",
            "error":      None,
        }
        with _PCR_LOCK:
            _PCR_CACHE["data"] = result
            _PCR_CACHE["ts"]   = now
        return result
    except Exception as e:
        logging.warning("[PCR] fetch_deribit_pcr failed: %s", e)
        return {**_neutral, "error": str(e)[:120]}


# ══════════════════════════════════════════════════════════════════════════════
# #52 — KIMCHI PREMIUM SIGNAL (spec-compliant wrapper)
# Thin wrapper over get_kimchi_premium() that returns the exact key schema
# specified in upgrade #52 and applies the KOREAN_PREMIUM / KOREAN_DISCOUNT
# signal labels used in confidence scoring.
# ══════════════════════════════════════════════════════════════════════════════

def fetch_kimchi_premium() -> dict:
    """
    #52 — Kimchi Premium: BTC price on Upbit (KRW) vs Binance (USD).

    premium_pct = (upbit_btc_usd - binance_btc_usd) / binance_btc_usd × 100

    Signal thresholds:
      >  3% → KOREAN_PREMIUM  (retail FOMO, late-cycle contrarian BEARISH lean)
      < -1% → KOREAN_DISCOUNT (Korean fear / global > local)
      else  → NEUTRAL

    Returns:
        kimchi_premium_pct : float
        signal             : str   — KOREAN_PREMIUM | KOREAN_DISCOUNT | NEUTRAL
        upbit_btc_usd      : float — Upbit BTC price converted to USD
        binance_btc_usd    : float
        error              : str | None
    """
    raw = get_kimchi_premium()
    if raw.get("error") and not raw.get("upbit_btc_krw"):
        return {
            "kimchi_premium_pct": 0.0, "signal": "NEUTRAL",
            "upbit_btc_usd": 0.0, "binance_btc_usd": 0.0,
            "error": raw.get("error"),
        }

    upbit_krw   = raw.get("upbit_btc_krw", 0.0) or 0.0
    usd_krw     = raw.get("usd_krw", 1350.0) or 1350.0
    binance_usd = raw.get("binance_btc_usd", 0.0) or 0.0
    upbit_usd   = (upbit_krw / usd_krw) if usd_krw > 0 else 0.0

    pct = raw.get("premium_pct", 0.0) or 0.0
    if pct > 3.0:
        signal = "KOREAN_PREMIUM"
    elif pct < -1.0:
        signal = "KOREAN_DISCOUNT"
    else:
        signal = "NEUTRAL"

    return {
        "kimchi_premium_pct": round(pct, 3),
        "signal":             signal,
        "upbit_btc_usd":      round(upbit_usd, 2),
        "binance_btc_usd":    round(binance_usd, 2),
        "error":              None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# #41 — NEW CeFi EXCHANGE DATA SOURCES (Batch 3)
# HTX (formerly Huobi), Bitstamp, Bitget — direct REST, no CCXT required
# 5-minute cache on each fetcher
# ══════════════════════════════════════════════════════════════════════════════

_HTX_PRICE_CACHE: dict = {}
_HTX_CACHE_LOCK  = threading.Lock()
_BITSTAMP_PRICE_CACHE: dict = {}
_BITSTAMP_CACHE_LOCK  = threading.Lock()
_BITGET_PRICE_CACHE: dict = {}
_BITGET_CACHE_LOCK    = threading.Lock()
_EXCH_COMPARE_CACHE: dict = {}
_EXCH_COMPARE_LOCK    = threading.Lock()
_CEFI_PRICE_TTL = 300  # 5 minutes


def fetch_htx_price(symbol: str) -> "Optional[float]":
    """
    Fetch last price from HTX (Huobi) public API.
    symbol: CCXT format e.g. "BTC/USDT" or raw "btcusdt"
    Returns float price or None on error.
    """
    # Normalise to HTX format: lowercase, no slash
    htx_sym = symbol.lower().replace("/", "")
    cache_key = htx_sym
    now = time.time()
    with _HTX_CACHE_LOCK:
        cached = _HTX_PRICE_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _CEFI_PRICE_TTL:
            return cached.get("price")
    try:
        resp = _SESSION.get(
            "https://api.huobi.pro/market/detail/merged",
            params={"symbol": htx_sym},
            timeout=6,
        )
        if resp.status_code == 200:
            tick = resp.json().get("tick", {})
            price = float(tick.get("close") or 0.0)
            if price > 0:
                with _HTX_CACHE_LOCK:
                    _HTX_PRICE_CACHE[cache_key] = {"price": price, "_ts": now}
                return price
    except Exception as e:
        logging.debug("[HTX] price fetch failed for %s: %s", symbol, e)
    with _HTX_CACHE_LOCK:
        _HTX_PRICE_CACHE[cache_key] = {"price": None, "_ts": now}
    return None


def fetch_bitstamp_price(pair: str) -> "Optional[float]":
    """
    Fetch last price from Bitstamp public API.
    pair: CCXT format e.g. "BTC/USDT" or "BTC/USD"; converted to "btcusd" or "btcusdt".
    Returns float price or None on error.
    """
    # Normalise: BTC/USDT → btcusdt, BTC/USD → btcusd
    bitstamp_pair = pair.lower().replace("/", "")
    cache_key = bitstamp_pair
    now = time.time()
    with _BITSTAMP_CACHE_LOCK:
        cached = _BITSTAMP_PRICE_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _CEFI_PRICE_TTL:
            return cached.get("price")
    try:
        resp = _SESSION.get(
            f"https://www.bitstamp.net/api/v2/ticker/{bitstamp_pair}/",
            timeout=6,
        )
        if resp.status_code == 200:
            price_str = resp.json().get("last", "0")
            price = float(price_str) if price_str else 0.0
            if price > 0:
                with _BITSTAMP_CACHE_LOCK:
                    _BITSTAMP_PRICE_CACHE[cache_key] = {"price": price, "_ts": now}
                return price
    except Exception as e:
        logging.debug("[Bitstamp] price fetch failed for %s: %s", pair, e)
    with _BITSTAMP_CACHE_LOCK:
        _BITSTAMP_PRICE_CACHE[cache_key] = {"price": None, "_ts": now}
    return None


def fetch_bitget_price(symbol: str) -> "Optional[float]":
    """
    Fetch last price from Bitget public spot API.
    symbol: e.g. "BTC/USDT" or "BTCUSDT"; Bitget uses uppercase e.g. "BTCUSDT".
    Returns float price or None on error.
    """
    bitget_sym = symbol.upper().replace("/", "")
    cache_key = bitget_sym
    now = time.time()
    with _BITGET_CACHE_LOCK:
        cached = _BITGET_PRICE_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _CEFI_PRICE_TTL:
            return cached.get("price")
    try:
        resp = _SESSION.get(
            "https://api.bitget.com/api/v2/spot/market/tickers",
            params={"symbol": bitget_sym},
            timeout=6,
        )
        if resp.status_code == 200:
            data_list = resp.json().get("data", [])
            if data_list:
                price_str = data_list[0].get("lastPr", "0") or "0"
                price = float(price_str) if price_str else 0.0
                if price > 0:
                    with _BITGET_CACHE_LOCK:
                        _BITGET_PRICE_CACHE[cache_key] = {"price": price, "_ts": now}
                    return price
    except Exception as e:
        logging.debug("[Bitget] price fetch failed for %s: %s", symbol, e)
    with _BITGET_CACHE_LOCK:
        _BITGET_PRICE_CACHE[cache_key] = {"price": None, "_ts": now}
    return None


def _fetch_binance_spot_price(symbol: str) -> "Optional[float]":
    """Fetch last price from Binance spot public API. symbol = e.g. 'BTCUSDT'."""
    try:
        resp = _SESSION.get(
            f"https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol.upper().replace("/", "")},
            timeout=6,
        )
        if resp.status_code == 200:
            price = float(resp.json().get("price", 0) or 0)
            return price if price > 0 else None
    except Exception as e:
        logging.debug("[Binance spot] price fetch failed for %s: %s", symbol, e)
    return None


def fetch_exchange_price_comparison(base_pair: str = "BTC/USDT") -> dict:
    """
    Fetch current price from Binance, HTX, Bitstamp, and Bitget for the given pair.
    Computes spread between highest and lowest price.

    Returns:
        {"binance": float|None, "htx": float|None, "bitstamp": float|None, "bitget": float|None,
         "spread_pct": float, "cheapest": str, "most_expensive": str,
         "pair": str, "error": str|None}

    5-minute cache.
    """
    cache_key = base_pair
    now = time.time()
    with _EXCH_COMPARE_LOCK:
        cached = _EXCH_COMPARE_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _CEFI_PRICE_TTL:
            result = dict(cached)
            result.pop("_ts", None)
            return result

    _neutral = {
        "pair": base_pair, "binance": None, "htx": None,
        "bitstamp": None, "bitget": None,
        "spread_pct": 0.0, "cheapest": "N/A", "most_expensive": "N/A",
        "error": None,
    }

    # Normalise symbol formats
    symbol_no_slash = base_pair.replace("/", "")  # BTCUSDT
    # Bitstamp uses lowercase and may need USD instead of USDT
    bitstamp_pair = base_pair.lower().replace("/", "")  # btcusdt — bitstamp supports usdt pairs

    # Fetch in parallel
    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            f_binance  = ex.submit(_fetch_binance_spot_price, symbol_no_slash)
            f_htx      = ex.submit(fetch_htx_price,           symbol_no_slash)
            f_bitstamp = ex.submit(fetch_bitstamp_price,      bitstamp_pair)
            f_bitget   = ex.submit(fetch_bitget_price,        symbol_no_slash)
        prices = {
            "binance":  f_binance.result(),
            "htx":      f_htx.result(),
            "bitstamp": f_bitstamp.result(),
            "bitget":   f_bitget.result(),
        }
    except Exception as e:
        logging.warning("[ExchCompare] parallel fetch failed for %s: %s", base_pair, e)
        result = {**_neutral, "error": str(e)[:80], "_ts": now}
        with _EXCH_COMPARE_LOCK:
            _EXCH_COMPARE_CACHE[cache_key] = result
        r = dict(result)
        r.pop("_ts", None)
        return r

    valid = {k: v for k, v in prices.items() if v is not None and v > 0}

    spread_pct   = 0.0
    cheapest     = "N/A"
    most_exp     = "N/A"

    if len(valid) >= 2:
        min_ex   = min(valid, key=lambda k: valid[k])
        max_ex   = max(valid, key=lambda k: valid[k])
        min_p    = valid[min_ex]
        max_p    = valid[max_ex]
        spread_pct = round((max_p - min_p) / min_p * 100, 4) if min_p > 0 else 0.0
        cheapest   = min_ex
        most_exp   = max_ex

    result = {
        "pair":            base_pair,
        "binance":         prices["binance"],
        "htx":             prices["htx"],
        "bitstamp":        prices["bitstamp"],
        "bitget":          prices["bitget"],
        "spread_pct":      spread_pct,
        "cheapest":        cheapest,
        "most_expensive":  most_exp,
        "error":           None if valid else "All exchanges unavailable",
        "_ts":             now,
    }

    with _EXCH_COMPARE_LOCK:
        _EXCH_COMPARE_CACHE[cache_key] = result

    r = dict(result)
    r.pop("_ts", None)
    return r


# ══════════════════════════════════════════════════════════════════════════════
# BATCH 4 — #89 REGIONAL EXCHANGE INDIVIDUAL FETCHERS
# Standalone wrappers used by fetch_regional_price_comparison()
# ══════════════════════════════════════════════════════════════════════════════

_MEXC_PRICE_CACHE: dict = {}
_MEXC_PRICE_LOCK = threading.Lock()
_BITSO_PRICE_CACHE: dict = {}
_BITSO_PRICE_LOCK = threading.Lock()
_COINDCX_PRICE_CACHE: dict = {}
_COINDCX_PRICE_LOCK = threading.Lock()
_REGIONAL_COMP_CACHE: dict = {}
_REGIONAL_COMP_LOCK = threading.Lock()
_REGIONAL_COMP_TTL = 300  # 5-min cache


def fetch_mexc_price(symbol: str) -> "Optional[float]":
    """
    Fetch last price from MEXC public spot API.
    symbol: Binance-format string e.g. 'BTCUSDT'.
    Returns float or None on error. 5-min cache.
    """
    sym = symbol.upper().replace("/", "")
    now = time.time()
    with _MEXC_PRICE_LOCK:
        cached = _MEXC_PRICE_CACHE.get(sym)
        if cached and (now - cached.get("_ts", 0)) < _REGIONAL_COMP_TTL:
            return cached.get("price")
    try:
        resp = _SESSION.get(
            f"https://api.mexc.com/api/v3/ticker/price",
            params={"symbol": sym},
            timeout=6,
        )
        if resp.status_code == 200:
            price = float(resp.json().get("price", 0) or 0)
            if price > 0:
                with _MEXC_PRICE_LOCK:
                    _MEXC_PRICE_CACHE[sym] = {"price": price, "_ts": now}
                return price
    except Exception as e:
        logging.debug("[MEXC] price fetch failed for %s: %s", symbol, e)
    with _MEXC_PRICE_LOCK:
        _MEXC_PRICE_CACHE[sym] = {"price": None, "_ts": now}
    return None


def fetch_bitso_price(book: str = "btc_mxn") -> "Optional[float]":
    """
    Fetch last price from Bitso public API for a given book (e.g. 'btc_mxn').
    Converts from MXN to USD using Binance USDTMXN rate (fallback: 17.0).
    Note: Binance does not list USDCMXN — USDTMXN is also unavailable on Binance
    spot (MXN pairs not offered), so the hardcoded fallback of 17.0 is always used.
    Returns float price in USD or None on error. 5-min cache.
    """
    now = time.time()
    with _BITSO_PRICE_LOCK:
        cached = _BITSO_PRICE_CACHE.get(book)
        if cached and (now - cached.get("_ts", 0)) < _REGIONAL_COMP_TTL:
            return cached.get("price")
    try:
        resp = _SESSION.get(
            f"https://api.bitso.com/v3/ticker/",
            params={"book": book},
            timeout=6,
        )
        if resp.status_code == 200:
            last_str = (resp.json().get("payload") or {}).get("last", "0") or "0"
            last_local = float(last_str)
            if last_local > 0:
                # Determine currency from book name (e.g. btc_mxn → MXN)
                currency = book.split("_")[-1].upper()
                # Binance has no MXN spot pairs (USDTMXN is not listed) so use
                # a hardcoded fallback rate.  For other currencies (e.g. future books
                # in BRL, ARS) a live Binance USDT{currency} fetch is attempted first.
                mxn_rate = 17.0  # hardcoded fallback for MXN
                if currency != "MXN":
                    try:
                        fx_sym = f"USDT{currency}"
                        r2 = _SESSION.get(
                            "https://api.binance.com/api/v3/ticker/price",
                            params={"symbol": fx_sym},
                            timeout=4,
                        )
                        if r2.status_code == 200:
                            _fx_price = float(r2.json().get("price", 0) or 0)
                            if _fx_price > 0:
                                mxn_rate = _fx_price
                    except Exception:
                        pass
                price_usd = round(last_local / mxn_rate, 2) if mxn_rate > 0 else None
                if price_usd and price_usd > 0:
                    with _BITSO_PRICE_LOCK:
                        _BITSO_PRICE_CACHE[book] = {"price": price_usd, "_ts": now}
                    return price_usd
    except Exception as e:
        logging.debug("[Bitso] price fetch failed for %s: %s", book, e)
    with _BITSO_PRICE_LOCK:
        _BITSO_PRICE_CACHE[book] = {"price": None, "_ts": now}
    return None


def fetch_coindcx_price(pair: str = "BTCINR") -> "Optional[float]":
    """
    Fetch last price from CoinDCX public API for a given pair (e.g. 'BTCINR').
    CoinDCX uses 'B-{BASE}_{QUOTE}' market format internally.
    Converts from INR to USD using Binance USDTINR rate (fallback: 83.0).
    Returns float price in USD or None on error. 5-min cache.
    """
    now = time.time()
    with _COINDCX_PRICE_LOCK:
        cached = _COINDCX_PRICE_CACHE.get(pair)
        if cached and (now - cached.get("_ts", 0)) < _REGIONAL_COMP_TTL:
            return cached.get("price")
    try:
        # Normalize: "BTCINR" → base="BTC", quote="INR"
        pair_upper = pair.upper()
        if pair_upper.endswith("INR"):
            base = pair_upper[:-3]
            quote = "INR"
        else:
            base, quote = pair_upper[:-4], pair_upper[-4:]
        target_market = f"B-{base}_{quote}"

        resp = _SESSION.get("https://api.coindcx.com/exchange/ticker", timeout=8)
        if resp.status_code == 200:
            _ticker_list = resp.json()
            if not isinstance(_ticker_list, list):
                raise ValueError(f"CoinDCX ticker API returned unexpected type: {type(_ticker_list)}")
            for ticker in _ticker_list:
                if not isinstance(ticker, dict):
                    continue
                if ticker.get("market") == target_market:
                    last_local = float(ticker.get("last_price", 0) or 0)
                    if last_local > 0:
                        # Fetch INR/USD rate
                        inr_rate = 83.0
                        try:
                            r2 = _SESSION.get(
                                "https://api.binance.com/api/v3/ticker/price",
                                params={"symbol": "USDTINR"},
                                timeout=4,
                            )
                            if r2.status_code == 200:
                                inr_rate = float(r2.json().get("price", 83.0) or 83.0)
                        except Exception:
                            pass
                        price_usd = round(last_local / inr_rate, 2) if inr_rate > 0 else None
                        if price_usd and price_usd > 0:
                            with _COINDCX_PRICE_LOCK:
                                _COINDCX_PRICE_CACHE[pair] = {"price": price_usd, "_ts": now}
                            return price_usd
                        break
    except Exception as e:
        logging.debug("[CoinDCX] price fetch failed for %s: %s", pair, e)
    with _COINDCX_PRICE_LOCK:
        _COINDCX_PRICE_CACHE[pair] = {"price": None, "_ts": now}
    return None


def fetch_regional_price_comparison(base: str = "BTC") -> dict:
    """
    Fetch BTC (or given base) price from MEXC, Bitso, CoinDCX, and Binance.
    Computes arbitrage spread across all sources vs Binance global price.

    Returns:
        {
          "mexc_usd":      float | None,
          "bitso_usd":     float | None,
          "coindcx_usd":   float | None,
          "binance_usd":   float | None,
          "max_spread_pct": float,
          "errors":        list[str],
        }
    5-min cache.
    """
    cache_key = base.upper()
    now = time.time()
    with _REGIONAL_COMP_LOCK:
        cached = _REGIONAL_COMP_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _REGIONAL_COMP_TTL:
            r = dict(cached)
            r.pop("_ts", None)
            return r

    sym = f"{base.upper()}USDT"
    errors: list = []

    binance_usd = None
    try:
        _resp = _SESSION.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": sym},
            timeout=6,
        )
        if _resp.status_code == 200:
            binance_usd = float(_resp.json().get("price", 0) or 0) or None
    except Exception as e:
        errors.append(f"binance:{e}")

    mexc_usd = None
    try:
        mexc_usd = fetch_mexc_price(sym)
    except Exception as e:
        errors.append(f"mexc:{e}")

    bitso_usd = None
    try:
        bitso_usd = fetch_bitso_price(f"{base.lower()}_mxn")
    except Exception as e:
        errors.append(f"bitso:{e}")

    coindcx_usd = None
    try:
        coindcx_usd = fetch_coindcx_price(f"{base.upper()}INR")
    except Exception as e:
        errors.append(f"coindcx:{e}")

    # Compute max spread across all valid prices
    _prices = [p for p in [mexc_usd, bitso_usd, coindcx_usd, binance_usd] if p and p > 0]
    max_spread_pct = 0.0
    if len(_prices) >= 2:
        _min_p = min(_prices)
        _max_p = max(_prices)
        max_spread_pct = round((_max_p - _min_p) / _min_p * 100, 4) if _min_p > 0 else 0.0

    _result = {
        "mexc_usd":       mexc_usd,
        "bitso_usd":      bitso_usd,
        "coindcx_usd":    coindcx_usd,
        "binance_usd":    binance_usd,
        "max_spread_pct": max_spread_pct,
        "errors":         errors,
        "_ts":            now,
    }
    with _REGIONAL_COMP_LOCK:
        _REGIONAL_COMP_CACHE[cache_key] = _result

    _out = dict(_result)
    _out.pop("_ts", None)
    return _out


# ══════════════════════════════════════════════════════════════════════════════
# BATCH 4 — #91 DEX INDIVIDUAL FETCHERS + DEX vs CEX SPREAD
# Standalone wrappers for dYdX v4 and Jupiter; DEX vs CEX comparison function
# ══════════════════════════════════════════════════════════════════════════════

_DYDX_PRICE_CACHE: dict = {}
_DYDX_PRICE_LOCK = threading.Lock()
_JUP_PRICE_CACHE: dict = {}
_JUP_PRICE_LOCK = threading.Lock()
_DEX_CEX_CACHE: dict = {}
_DEX_CEX_LOCK = threading.Lock()
_DEX_INDIVIDUAL_TTL = 300  # 5-min cache


def fetch_dydx_price(market: str = "BTC-USD") -> "Optional[float]":
    """
    Fetch index price from dYdX v4 indexer for a given market (e.g. 'BTC-USD').
    Returns indexPrice as float or None on error. 5-min cache.
    """
    now = time.time()
    with _DYDX_PRICE_LOCK:
        cached = _DYDX_PRICE_CACHE.get(market)
        if cached and (now - cached.get("_ts", 0)) < _DEX_INDIVIDUAL_TTL:
            return cached.get("price")
    try:
        resp = _SESSION.get("https://indexer.dydx.trade/v4/markets", timeout=8)
        if resp.status_code == 200:
            mkt_data = resp.json().get("markets", {}).get(market, {})
            index_price = float(mkt_data.get("indexPrice") or mkt_data.get("oraclePrice") or 0)
            if index_price > 0:
                with _DYDX_PRICE_LOCK:
                    _DYDX_PRICE_CACHE[market] = {"price": index_price, "_ts": now}
                return index_price
    except Exception as e:
        logging.debug("[dYdX] price fetch failed for %s: %s", market, e)
    with _DYDX_PRICE_LOCK:
        _DYDX_PRICE_CACHE[market] = {"price": None, "_ts": now}
    return None


def fetch_jupiter_price(token_mint: str) -> "Optional[float]":
    """
    Fetch token price from Jupiter Price API v6 by token mint address.
    Common mints: SOL = 'So11111111111111111111111111111111111111112'
    Returns float price in USD or None on error. 5-min cache.
    """
    now = time.time()
    with _JUP_PRICE_LOCK:
        cached = _JUP_PRICE_CACHE.get(token_mint)
        if cached and (now - cached.get("_ts", 0)) < _DEX_INDIVIDUAL_TTL:
            return cached.get("price")
    try:
        resp = _SESSION.get(
            "https://price.jup.ag/v6/price",
            params={"ids": token_mint},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            token_data = data.get(token_mint, {})
            price = float(token_data.get("price", 0) or 0)
            if price > 0:
                with _JUP_PRICE_LOCK:
                    _JUP_PRICE_CACHE[token_mint] = {"price": price, "_ts": now}
                return price
    except Exception as e:
        logging.debug("[Jupiter] price fetch failed for %s: %s", token_mint, e)
    with _JUP_PRICE_LOCK:
        _JUP_PRICE_CACHE[token_mint] = {"price": None, "_ts": now}
    return None


def fetch_dex_vs_cex_spread(symbol: str = "BTC") -> dict:
    """
    Compare dYdX v4 oracle/index price vs Binance spot price for BTC or ETH.

    Returns:
        {
          "symbol":       str,
          "binance_spot": float | None,
          "dydx_oracle":  float | None,
          "spread_pct":   float,
          "basis":        float,   # dYdX − Binance in USD
        }
    5-min cache.
    """
    sym_upper = symbol.upper()
    cache_key = sym_upper
    now = time.time()
    with _DEX_CEX_LOCK:
        cached = _DEX_CEX_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _DEX_INDIVIDUAL_TTL:
            _cached_out = dict(cached)
            _cached_out.pop("_ts", None)
            return _cached_out

    dydx_market = f"{sym_upper}-USD"
    binance_sym = f"{sym_upper}USDT"

    dydx_price = None
    binance_price = None

    try:
        dydx_price = fetch_dydx_price(dydx_market)
    except Exception as e:
        logging.debug("[DEX vs CEX] dYdX fetch failed: %s", e)

    try:
        _resp = _SESSION.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": binance_sym},
            timeout=6,
        )
        if _resp.status_code == 200:
            binance_price = float(_resp.json().get("price", 0) or 0) or None
    except Exception as e:
        logging.debug("[DEX vs CEX] Binance fetch failed: %s", e)

    spread_pct = 0.0
    basis = 0.0
    if dydx_price and binance_price and binance_price > 0:
        basis = round(dydx_price - binance_price, 4)
        spread_pct = round(basis / binance_price * 100, 4)

    _result = {
        "symbol":       sym_upper,
        "binance_spot": binance_price,
        "dydx_oracle":  dydx_price,
        "spread_pct":   spread_pct,
        "basis":        basis,
        "_ts":          now,
    }
    with _DEX_CEX_LOCK:
        _DEX_CEX_CACHE[cache_key] = _result

    _out = dict(_result)
    _out.pop("_ts", None)
    return _out


# ──────────────────────────────────────────────
# CCXT OHLCV + TICKER  (#35)
# Optional enhancement — available when ccxt is installed.
# Falls back gracefully if not available.
# ──────────────────────────────────────────────

# Caches keyed on (exchange_id, symbol, timeframe) for OHLCV
# and (exchange_id, symbol) for ticker
_CCXT_OHLCV_CACHE: dict = {}
_CCXT_OHLCV_LOCK  = threading.Lock()
_CCXT_OHLCV_TTL   = 300  # 5 minutes

_CCXT_TICKER_CACHE: dict = {}
_CCXT_TICKER_LOCK  = threading.Lock()
_CCXT_TICKER_TTL   = 60   # 1 minute


def fetch_ccxt_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1h",
    limit: int = 100,
) -> "list | None":
    """
    Fetch OHLCV candles via CCXT for any supported exchange.

    Returns a list of [timestamp_ms, open, high, low, close, volume] candles,
    or None if CCXT is not installed or the request fails.

    5-minute cache keyed on (exchange_id, symbol, timeframe).
    """
    if not _CCXT_AVAILABLE:
        return None

    _cache_key = (exchange_id, symbol, timeframe, limit)
    _now = time.time()
    with _CCXT_OHLCV_LOCK:
        _hit = _CCXT_OHLCV_CACHE.get(_cache_key)
        if _hit and (_now - _hit["ts"]) < _CCXT_OHLCV_TTL:
            return _hit["data"]

    ex = _get_ccxt_exchange(exchange_id)
    if ex is None:
        return None

    try:
        candles = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
        if candles:
            with _CCXT_OHLCV_LOCK:
                _CCXT_OHLCV_CACHE[_cache_key] = {"data": candles, "ts": _now}
        return candles if candles else None
    except ccxt.NetworkError as _ne:
        logging.debug("[CCXT OHLCV] NetworkError %s %s: %s", exchange_id, symbol, _ne)
        return None
    except ccxt.ExchangeError as _ee:
        logging.debug("[CCXT OHLCV] ExchangeError %s %s: %s", exchange_id, symbol, _ee)
        return None
    except Exception as _e:
        logging.debug("[CCXT OHLCV] %s %s failed: %s", exchange_id, symbol, _e)
        return None


def fetch_ccxt_ticker(exchange_id: str, symbol: str) -> "dict | None":
    """
    Fetch a ticker dict via CCXT for any supported exchange.

    Returns a ccxt ticker dict with keys: 'last', 'bid', 'ask', 'volume', 'change',
    or None if CCXT is not installed or the request fails.

    1-minute cache keyed on (exchange_id, symbol).
    """
    if not _CCXT_AVAILABLE:
        return None

    _cache_key = (exchange_id, symbol)
    _now = time.time()
    with _CCXT_TICKER_LOCK:
        _hit = _CCXT_TICKER_CACHE.get(_cache_key)
        if _hit and (_now - _hit["ts"]) < _CCXT_TICKER_TTL:
            return _hit["data"]

    ex = _get_ccxt_exchange(exchange_id)
    if ex is None:
        return None

    try:
        ticker = ex.fetch_ticker(symbol)
        if ticker:
            _result = {
                "last":   ticker.get("last"),
                "bid":    ticker.get("bid"),
                "ask":    ticker.get("ask"),
                "volume": ticker.get("baseVolume") or ticker.get("quoteVolume"),
                "change": ticker.get("change") or ticker.get("percentage"),
            }
            with _CCXT_TICKER_LOCK:
                _CCXT_TICKER_CACHE[_cache_key] = {"data": _result, "ts": _now}
            return _result
        return None
    except ccxt.NetworkError as _ne:
        logging.debug("[CCXT Ticker] NetworkError %s %s: %s", exchange_id, symbol, _ne)
        return None
    except ccxt.ExchangeError as _ee:
        logging.debug("[CCXT Ticker] ExchangeError %s %s: %s", exchange_id, symbol, _ee)
        return None
    except Exception as _e:
        logging.debug("[CCXT Ticker] %s %s failed: %s", exchange_id, symbol, _e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# API KEY VALIDATION ON STARTUP  (#17 security hardening)
# Lightweight connectivity checks — no auth needed for public endpoints.
# ─────────────────────────────────────────────────────────────────────────────

def _get_runtime_key(key_name: str, default: str = "") -> str:
    """Return a per-session API key override stored in st.session_state.

    Priority: session_state (UI paste) → environment variable → default.
    The UI expander (#18) lets users paste a personal key (e.g. CoinGecko Pro)
    that is stored as ``runtime_<key_name>`` in Streamlit session state for the
    duration of the browser session — never written to disk.
    Falls back to the env var (e.g. SUPERGROK_COINGECKO_API_KEY for coingecko_key)
    so that keys set at deploy time are used automatically without manual paste.
    """
    import os as _os
    _ENV_MAP = {
        "coingecko_key":  "SUPERGROK_COINGECKO_API_KEY",
        "lunarcrush_key": "LUNARCRUSH_API_KEY",
        "tiingo_key":     "SUPERGROK_TIINGO_API_KEY",
    }
    try:
        import streamlit as st
        val = st.session_state.get(f"runtime_{key_name}", "")
        if val:
            return val
    except Exception:
        pass
    env_key = _ENV_MAP.get(key_name, "")
    env_val = _os.environ.get(env_key, "") if env_key else ""
    return env_val if env_val else default


def validate_api_keys() -> dict:
    """Test each configured API key with a lightweight connectivity check.

    Returns a dict mapping service name to status string:
      "ok"         — endpoint responded 200
      "HTTP <N>"   — endpoint responded with unexpected status
      "error"      — connection failure / timeout
      "configured" — key is set (Anthropic — not pinged to avoid charges)
      "no key"     — key is missing
    """
    results: dict = {}

    # Binance public API (no key needed)
    try:
        r = _SESSION.get("https://api.binance.com/api/v3/ping", timeout=5)
        results["binance"] = "ok" if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception:
        results["binance"] = "error"

    # CoinGecko
    try:
        r = _SESSION.get("https://api.coingecko.com/api/v3/ping", timeout=5)
        results["coingecko"] = "ok" if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception:
        results["coingecko"] = "error"

    # Deribit (public, no key)
    try:
        r = _SESSION.get("https://www.deribit.com/api/v2/public/get_time", timeout=5)
        results["deribit"] = "ok" if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception:
        results["deribit"] = "error"

    # Anthropic — just check API key is configured (don't make a call)
    try:
        from config import ANTHROPIC_API_KEY
        results["anthropic"] = "configured" if ANTHROPIC_API_KEY else "no key"
    except Exception:
        results["anthropic"] = "no key"

    return results


# ─────────────────────────────────────────────────────────────────────────────
# WALLET HOLDINGS IMPORT (#110 / #111)
# Read-only portfolio fetch via Zerion public API with Etherscan fallback.
# ─────────────────────────────────────────────────────────────────────────────

_WALLET_CACHE: dict = {}
_WALLET_CACHE_LOCK = threading.Lock()
_WALLET_CACHE_TTL = 300  # 5-minute TTL


def fetch_wallet_holdings(address: str) -> dict:
    """
    Fetch EVM wallet token holdings from Zerion (public API, no key needed for basic).
    Falls back to Etherscan token list if Zerion returns 401 or fails.

    Returns:
        {
            "address": str,
            "total_value_usd": float,
            "tokens": [{"symbol": str, "balance": float, "value_usd": float,
                         "contract": str, "chain": str, "change_pct_1d": float | None}],
            "source": str,
        }
    5-minute TTL cache keyed on address (lowercased).
    """
    _addr_key = address.lower()
    _now = time.time()
    with _WALLET_CACHE_LOCK:
        _hit = _WALLET_CACHE.get(f"holdings:{_addr_key}")
        if _hit and (_now - _hit.get("_ts", 0)) < _WALLET_CACHE_TTL:
            return {k: v for k, v in _hit.items() if k != "_ts"}

    # Build Zerion auth header: Basic base64("api_key:") per Zerion API docs.
    # Falls back to unauthenticated (public free tier) when key is absent.
    try:
        from config import ZERION_API_KEY as _zerion_api_key  # type: ignore[import]
    except ImportError:
        _zerion_api_key = ""
    _zerion_api_key = _zerion_api_key or ""
    if _zerion_api_key:
        _zerion_auth = "Basic " + base64.b64encode(f"{_zerion_api_key}:".encode()).decode()
        _zerion_headers = {"Accept": "application/json", "Authorization": _zerion_auth}
    else:
        _zerion_headers = {"Accept": "application/json"}

    # 1. Try Zerion public portfolio endpoint
    _zerion_url = f"https://api.zerion.io/v1/wallets/{address}/portfolio?currency=usd"
    if _ssrf_check(_zerion_url):
        try:
            resp = _SESSION.get(
                _zerion_url,
                headers=_zerion_headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                attrs = (data.get("data") or {}).get("attributes") or {}
                total_val = float(attrs.get("total", {}).get("positions") or 0)

                # Fetch positions for token breakdown
                _pos_url = (
                    f"https://api.zerion.io/v1/wallets/{address}/positions"
                    "?filter[position_types]=wallet,deposit,staked&currency=usd&sort=value"
                )
                tokens = []
                if _ssrf_check(_pos_url):
                    try:
                        pos_resp = _SESSION.get(
                            _pos_url,
                            headers=_zerion_headers,
                            timeout=10,
                        )
                        if pos_resp.status_code == 200:
                            pos_data = pos_resp.json()
                            for item in (pos_data.get("data") or []):
                                item_attrs = (item.get("attributes") or {})
                                qty_obj = item_attrs.get("quantity") or {}
                                qty = float(qty_obj.get("float") or 0)
                                val = float(item_attrs.get("value") or 0)
                                chg = (item_attrs.get("changes") or {}).get("percent_1d")
                                chain_id = ((item.get("relationships") or {})
                                            .get("chain", {})
                                            .get("data", {})
                                            .get("id") or "ethereum")
                                tokens.append({
                                    "symbol":       item_attrs.get("name") or "",
                                    "balance":      qty,
                                    "value_usd":    val,
                                    "contract":     "",
                                    "chain":        chain_id,
                                    "change_pct_1d": float(chg) if chg is not None else None,
                                })
                    except Exception as _pe:
                        logging.debug("[Zerion] positions fetch error: %s", _pe)

                result = {
                    "address":         address,
                    "total_value_usd": total_val,
                    "tokens":          tokens,
                    "source":          "zerion",
                    "_ts":             _now,
                }
                with _WALLET_CACHE_LOCK:
                    _WALLET_CACHE[f"holdings:{_addr_key}"] = result
                return {k: v for k, v in result.items() if k != "_ts"}
            elif resp.status_code not in (401, 403):
                logging.debug("[Zerion] portfolio HTTP %s for %s", resp.status_code, address)
        except Exception as _ze:
            logging.debug("[Zerion] portfolio fetch error for %s: %s", address, _ze)

    # 2. Fallback: Etherscan token list
    try:
        from config import ETHERSCAN_API_KEY  # type: ignore[import]
        _eth_key = ETHERSCAN_API_KEY or ""
    except ImportError:
        _eth_key = ""

    _eth_url = (
        f"https://api.etherscan.io/v2/api"
        f"?chainid=1&module=account&action=tokenlist"
        f"&address={address}&apikey={_eth_key}"
    )
    # Etherscan is a known-safe domain — add inline guard
    if "api.etherscan.io" in _eth_url:
        try:
            resp = _SESSION.get(_eth_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                tokens = []
                for tok in (data.get("result") or []):
                    decimals = int(tok.get("tokenDecimal") or 18)
                    raw_bal = int(tok.get("balance") or 0)
                    bal = raw_bal / (10 ** decimals) if decimals else raw_bal
                    tokens.append({
                        "symbol":       tok.get("tokenSymbol") or "",
                        "balance":      bal,
                        "value_usd":    0.0,  # Etherscan doesn't provide USD value
                        "contract":     tok.get("contractAddress") or "",
                        "chain":        "ethereum",
                        "change_pct_1d": None,
                    })
                result = {
                    "address":         address,
                    "total_value_usd": 0.0,
                    "tokens":          tokens,
                    "source":          "etherscan",
                    "_ts":             _now,
                }
                with _WALLET_CACHE_LOCK:
                    _WALLET_CACHE[f"holdings:{_addr_key}"] = result
                return {k: v for k, v in result.items() if k != "_ts"}
        except Exception as _ee:
            logging.debug("[Etherscan] token list error for %s: %s", address, _ee)

    return {}


def fetch_zerion_portfolio(address: str) -> dict:
    """
    Fetch full portfolio breakdown from Zerion API.

    Returns:
        {
            "address": str,
            "total_value_usd": float,
            "change_24h_pct": float | None,
            "positions": [{"symbol": str, "balance": float, "value_usd": float,
                            "price": float, "change_pct_1d": float | None, "chain": str}],
            "chains": {chain_id: value_usd},
            "source": "zerion",
        }
    5-minute TTL cache keyed on address.
    """
    _addr_key = address.lower()
    _now = time.time()
    with _WALLET_CACHE_LOCK:
        _hit = _WALLET_CACHE.get(f"zerion:{_addr_key}")
        if _hit and (_now - _hit.get("_ts", 0)) < _WALLET_CACHE_TTL:
            return {k: v for k, v in _hit.items() if k != "_ts"}

    _portfolio_url = f"https://api.zerion.io/v1/wallets/{address}/portfolio?currency=usd"
    _positions_url = (
        f"https://api.zerion.io/v1/wallets/{address}/positions"
        "?filter[position_types]=wallet,deposit,staked&currency=usd&sort=value"
    )

    # Build Zerion auth header: Basic base64("api_key:") per Zerion API docs.
    try:
        from config import ZERION_API_KEY as _zp_api_key  # type: ignore[import]
    except ImportError:
        _zp_api_key = ""
    _zp_api_key = _zp_api_key or ""
    if _zp_api_key:
        _zp_auth = "Basic " + base64.b64encode(f"{_zp_api_key}:".encode()).decode()
        _zp_headers = {"Accept": "application/json", "Authorization": _zp_auth}
    else:
        _zp_headers = {"Accept": "application/json"}

    total_val = 0.0
    change_24h_pct = None
    positions: list = []
    chains: dict = {}

    if _ssrf_check(_portfolio_url):
        try:
            resp = _SESSION.get(
                _portfolio_url,
                headers=_zp_headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                attrs = (data.get("data") or {}).get("attributes") or {}
                total_val = float((attrs.get("total") or {}).get("positions") or 0)
                chg = (attrs.get("changes") or {}).get("percent_1d")
                if chg is not None:
                    change_24h_pct = float(chg)
        except Exception as _pe:
            logging.debug("[Zerion] portfolio overview error for %s: %s", address, _pe)

    if _ssrf_check(_positions_url):
        try:
            pos_resp = _SESSION.get(
                _positions_url,
                headers=_zp_headers,
                timeout=10,
            )
            if pos_resp.status_code == 200:
                pos_data = pos_resp.json()
                for item in (pos_data.get("data") or []):
                    item_attrs = item.get("attributes") or {}
                    qty_obj = item_attrs.get("quantity") or {}
                    qty = float(qty_obj.get("float") or 0)
                    val = float(item_attrs.get("value") or 0)
                    price = float(item_attrs.get("price") or 0)
                    chg = (item_attrs.get("changes") or {}).get("percent_1d")
                    chain_id = ((item.get("relationships") or {})
                                .get("chain", {})
                                .get("data", {})
                                .get("id") or "ethereum")
                    chains[chain_id] = chains.get(chain_id, 0.0) + val
                    positions.append({
                        "symbol":       item_attrs.get("name") or "",
                        "balance":      qty,
                        "value_usd":    val,
                        "price":        price,
                        "change_pct_1d": float(chg) if chg is not None else None,
                        "chain":        chain_id,
                        "contract":     "",
                    })
        except Exception as _qe:
            logging.debug("[Zerion] positions error for %s: %s", address, _qe)

    if not positions and not total_val:
        return {}

    result = {
        "address":         address,
        "total_value_usd": total_val,
        "change_24h_pct":  change_24h_pct,
        "positions":       positions,
        "tokens":          positions,  # alias for wallet holdings compat
        "chains":          chains,
        "source":          "zerion",
        "_ts":             _now,
    }
    with _WALLET_CACHE_LOCK:
        _WALLET_CACHE[f"zerion:{_addr_key}"] = result
    return {k: v for k, v in result.items() if k != "_ts"}
