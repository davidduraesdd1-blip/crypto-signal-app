"""
config.py — Central configuration and feature flags for SuperGrok Crypto Signal Model.
API key presence auto-enables the corresponding feature (zero code changes required).
"""
import os

# ─── API Keys (read from environment / .streamlit/secrets.toml) ───────────────
ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY")
CRYPTOPANIC_API_KEY: str | None = os.environ.get("CRYPTOPANIC_API_KEY")
COINGECKO_API_KEY: str | None = os.environ.get("SUPERGROK_COINGECKO_API_KEY")
SENTRY_DSN: str | None = os.environ.get("SUPERGROK_SENTRY_DSN")
COINMARKETCAP_API_KEY: str | None = os.environ.get("COINMARKETCAP_API_KEY")

# ─── Tier 1 Pair Expansion (#40) ──────────────────────────────────────────────
# 9 new assets added to the tracked pairs list (HYPE excluded — DEX-only, no CEX listing).
# CoinGecko IDs used by data_feeds.py batch fetch functions.
# Binance trading pairs used by OHLCV and websocket feeds.
TIER1_PAIRS: list[str] = [
    "TRX/USDT", "ADA/USDT", "BCH/USDT", "LINK/USDT", "LTC/USDT",
    "AVAX/USDT", "XLM/USDT", "SUI/USDT", "TAO/USDT",
    # HYPE: Hyperliquid DEX only — no CEX listing; handled by DEX scanner in Defi Model
]

TIER1_COINGECKO_IDS: dict[str, str] = {
    "TRX/USDT":   "tron",
    "ADA/USDT":   "cardano",
    "BCH/USDT":   "bitcoin-cash",
    "LINK/USDT":  "chainlink",
    "LTC/USDT":   "litecoin",
    "AVAX/USDT":  "avalanche-2",
    "XLM/USDT":   "stellar",
    "SUI/USDT":   "sui",
    "TAO/USDT":   "bittensor",
}

TIER1_BINANCE_PAIRS: dict[str, str] = {
    "TRX/USDT":   "TRXUSDT",
    "ADA/USDT":   "ADAUSDT",
    "BCH/USDT":   "BCHUSDT",
    "LINK/USDT":  "LINKUSDT",
    "LTC/USDT":   "LTCUSDT",
    "AVAX/USDT":  "AVAXUSDT",
    "XLM/USDT":   "XLMUSDT",
    "SUI/USDT":   "SUIUSDT",
    "TAO/USDT":   "TAOUSDT",
}

# Default weight allocation in the model (1.0 = same as core pairs)
TIER1_DEFAULT_WEIGHTS: dict[str, float] = {
    "TRX/USDT":  1.0,
    "ADA/USDT":  1.0,
    "BCH/USDT":  0.9,
    "LINK/USDT": 1.0,
    "LTC/USDT":  0.9,
    "AVAX/USDT": 1.0,
    "XLM/USDT":  0.8,
    "SUI/USDT":  0.9,
    "TAO/USDT":  0.9,
}

# ─── Feature Flags ────────────────────────────────────────────────────────────
# auto-enabled when the corresponding key is set — no code changes needed
FEATURES: dict = {
    # AI / LLM
    "ai_analysis":      bool(ANTHROPIC_API_KEY),
    # News
    "cryptopanic_news": bool(CRYPTOPANIC_API_KEY),
    # Market data
    "coingecko_pro":    bool(COINGECKO_API_KEY),
    # CMC global metrics — requires free API key
    "coinmarketcap":    bool(COINMARKETCAP_API_KEY),
    # Error monitoring
    "sentry":           bool(SENTRY_DSN),
    # Always-on free APIs
    "binance":          True,
    "bybit":            True,
    "coingecko_free":   True,
    "fear_greed":       True,
    "fred_m2":          True,
    # Always-on: 10 new ccxt exchanges (free public funding rate data)
    "bitfinex":         True,
    "mexc":             True,
    "htx":              True,
    "phemex":           True,
    "woo":              True,
    "bithumb":          True,
    "cryptocom":        True,
    "ascendex":         True,
    "lbank":            True,
    "coinex":           True,
    # Always-on: extra data sources (free public APIs)
    "deribit_options":  True,
    "regional_premiums": True,
}


def feature_enabled(name: str) -> bool:
    """Return True if the named feature is available (key present or built-in free)."""
    return FEATURES.get(name, False)
