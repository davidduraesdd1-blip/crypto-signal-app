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

# ─── Feature Flags ────────────────────────────────────────────────────────────
# auto-enabled when the corresponding key is set — no code changes needed
FEATURES: dict = {
    # AI / LLM
    "ai_analysis":      bool(ANTHROPIC_API_KEY),
    # News
    "cryptopanic_news": bool(CRYPTOPANIC_API_KEY),
    # Market data
    "coingecko_pro":    bool(COINGECKO_API_KEY),
    # Error monitoring
    "sentry":           bool(SENTRY_DSN),
    # Always-on free APIs
    "binance":          True,
    "bybit":            True,
    "coingecko_free":   True,
    "fear_greed":       True,
    "fred_m2":          True,
}


def feature_enabled(name: str) -> bool:
    """Return True if the named feature is available (key present or built-in free)."""
    return FEATURES.get(name, False)
