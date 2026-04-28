"""
config.py — Central configuration and feature flags for SuperGrok Crypto Signal Model.
API key presence auto-enables the corresponding feature (zero code changes required).
"""
import os

# ─── API Keys (read from environment / .streamlit/secrets.toml) ───────────────
ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY")
CRYPTOPANIC_API_KEY: str | None = os.environ.get("CRYPTOPANIC_API_KEY")
COINGECKO_API_KEY: str | None = os.environ.get("SUPERGROK_COINGECKO_API_KEY")
SENTRY_DSN: str | None = os.environ.get("SUPERGROK_SENTRY_DSN", "")
COINMARKETCAP_API_KEY: str | None = os.environ.get("COINMARKETCAP_API_KEY")
ETHERSCAN_API_KEY: str | None = os.environ.get("ETHERSCAN_API_KEY", "")
ZERION_API_KEY: str | None = os.environ.get("ZERION_API_KEY", "")

# ─── Anthropic / AI master switch ────────────────────────────────────────────
# Reads from ANTHROPIC_ENABLED env var if set; defaults to True so AI features
# are live when an API key is present. Set env var to "false" to disable.
ANTHROPIC_ENABLED: bool = os.environ.get("ANTHROPIC_ENABLED", "true").lower() not in ("false", "0", "no")

# ─── LLM Model Constants ──────────────────────────────────────────────────────
# Centralised model names — update here to change everywhere.
CLAUDE_MODEL: str = "claude-sonnet-4-6"           # primary signal explanation model
CLAUDE_HAIKU_MODEL: str = "claude-haiku-4-5-20251001"  # dated snapshot (audit R7e); parity with RWA/DeFi

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

# ─── Tier 2 Pair Expansion (#88) ──────────────────────────────────────────────
# 20 mid-cap alts added as an optional toggle (lower liquidity, use with caution)
TIER2_PAIRS: list[str] = [
    "NEAR/USDT", "APT/USDT", "POL/USDT", "OP/USDT", "ARB/USDT",
    "ATOM/USDT", "FIL/USDT", "INJ/USDT", "PENDLE/USDT", "WIF/USDT",
    "PYTH/USDT", "JUP/USDT", "HBAR/USDT", "FLR/USDT", "XDC/USDT",
    "WFLR/USDT", "FXRP/USDT", "SHX/USDT", "ZBCN/USDT", "CPOOL/USDT",
    "CC/USDT",   # Canton Network — §13 must-have; Bybit primary (no Binance listing)
]

# Binance-listed Tier 2 (subset that have Binance SPOT markets)
TIER2_BINANCE_PAIRS: list[str] = [
    "NEARUSDT", "APTUSDT", "POLUSDT", "OPUSDT", "ARBUSDT",
    "ATOMUSDT", "FILUSDT", "INJUSDT", "PENDLEUSDT", "WIFUSDT",
    "PYTHUSDT", "JUPUSDT", "HBARUSDT",
    # FLR, XDC, WFLR, FXRP, SHX, ZBCN, CPOOL may be on smaller exchanges only
]

# CoinGecko IDs for Tier 2 (for price/market data fallback)
TIER2_COINGECKO_IDS: dict[str, str] = {
    "NEAR/USDT": "near", "APT/USDT": "aptos", "POL/USDT": "matic-network",
    "OP/USDT": "optimism", "ARB/USDT": "arbitrum", "ATOM/USDT": "cosmos",
    "FIL/USDT": "filecoin", "INJ/USDT": "injective-protocol",
    "PENDLE/USDT": "pendle", "WIF/USDT": "dogwifcoin",
    "PYTH/USDT": "pyth-network", "JUP/USDT": "jupiter-exchange-solana",
    "HBAR/USDT": "hedera-hashgraph", "FLR/USDT": "flare-networks",
    "XDC/USDT": "xdce-crowd-sale", "WFLR/USDT": "wrapped-flare",
    "FXRP/USDT": "fxrp", "SHX/USDT": "stronghold-token",
    "ZBCN/USDT": "zebec-protocol", "CPOOL/USDT": "clearpool",
    "CC/USDT":   "canton",         # Canton Network (§13 must-have); Bybit CC/USDT
}

# Default equal weights for Tier 2 — P1 audit fix: was hard-coded `1.0 / 20`
# even after CC/USDT was added (TIER2_PAIRS has 21 entries), so weights
# summed to 1.05 — the comment "20 mid-cap alts added" was stale.
# Derive the divisor from the actual pair count so future additions stay
# normalized.
TIER2_DEFAULT_WEIGHTS: dict[str, float] = {
    pair: 1.0 / len(TIER2_PAIRS) for pair in TIER2_PAIRS
}

# ─── Feature Flags ────────────────────────────────────────────────────────────
# auto-enabled when the corresponding key is set — no code changes needed
FEATURES: dict = {
    # AI / LLM
    "ai_analysis":       bool(ANTHROPIC_API_KEY),
    "anthropic_ai":      bool(ANTHROPIC_API_KEY),
    # News
    "cryptopanic_news":  bool(CRYPTOPANIC_API_KEY),
    # Market data
    "coingecko_pro":     bool(COINGECKO_API_KEY) or bool(os.environ.get("SUPERGROK_COINGECKO_PRO_KEY", "")),
    # CMC global metrics — requires free API key
    "coinmarketcap":     bool(COINMARKETCAP_API_KEY),
    # Error monitoring
    "sentry":            bool(SENTRY_DSN),
    # Zerion DeFi portfolio
    "zerion":            bool(ZERION_API_KEY),
    # Optional libraries — updated at runtime after import checks
    "ccxt":              False,   # updated at runtime after import check
    "hmmlearn":          False,   # updated at runtime after import check
    "scipy":             False,   # updated at runtime after import check
    # Always-on free APIs
    "binance":           True,
    "bybit":             True,
    "coingecko_free":    True,
    "fear_greed":        True,
    "fred_m2":           True,
    # Always-on: 10 new ccxt exchanges (free public funding rate data)
    "bitfinex":          True,
    "mexc":              True,
    "htx":               True,
    "phemex":            True,
    "woo":               True,
    "bithumb":           True,
    "cryptocom":         True,
    "ascendex":          True,
    "lbank":             True,
    "coinex":            True,
    # Always-on: extra data sources (free public APIs)
    "deribit":           True,   # public endpoint, no key needed
    "deribit_options":   True,
    "regional_premiums": True,
    "tier2_pairs":       True,   # available by default
}

# ─── Runtime library checks ───────────────────────────────────────────────────
# Update FEATURES flags based on whether optional libraries are installed.
try:
    import ccxt as _ccxt_check  # noqa: F401
    FEATURES["ccxt"] = True
except ImportError:
    pass

try:
    import hmmlearn as _hmmlearn_check  # noqa: F401
    FEATURES["hmmlearn"] = True
except ImportError:
    pass

try:
    import scipy as _scipy_check  # noqa: F401
    FEATURES["scipy"] = True
except ImportError:
    pass


def feature_enabled(name: str) -> bool:
    """Return True if the named feature is available (key present or built-in free)."""
    return FEATURES.get(name, False)


# ─── Branding ─────────────────────────────────────────────────────────────────
# Set env vars to activate: SUPERGROK_BRAND_NAME="My App"  SUPERGROK_BRAND_LOGO_PATH="logo.png"
# When unset (default), the app shows a clean placeholder header.
# 2-line rebrand when ready — no restructuring required.
BRAND_NAME: str = os.environ.get("SUPERGROK_BRAND_NAME", "Family Office · Signal Intelligence")
BRAND_LOGO_PATH: str = os.environ.get("SUPERGROK_BRAND_LOGO_PATH", "")
