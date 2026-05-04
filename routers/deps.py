"""
routers/deps.py — FastAPI dependencies for the Phase D routers.

Mirrors api.py.require_api_key without importing api.py (which would
trigger module-level WebSocket startup + circular import). Reads from
the same alerts_config.json source of truth, so a key set via the
existing Settings page or env var is honored identically by both
api.py routes and the new routers.
"""

from __future__ import annotations

import hmac
import os
import threading
import time

from fastapi import Header, HTTPException

import alerts


_api_key_cache: dict = {"key": None, "ts": 0.0}
_API_KEY_CACHE_TTL = 30.0
_api_key_lock = threading.Lock()


def _get_configured_api_key() -> str:
    """Read the configured API key with a 30s cache.

    Resolution order:
      1. `CRYPTO_SIGNAL_API_KEY` env var — used in production on Render
         where the file system is ephemeral (every deploy resets
         alerts_config.json, so a file-based key would silently
         disappear).
      2. `api_key` field in alerts_config.json — used in local dev and
         backwards compatibility with the existing Streamlit UI.

    AUDIT-2026-05-03 (CRITICAL C-1 fix): the env-var path was added so
    David can rotate the production key through the Render dashboard
    without committing secrets or pushing code. Both paths feed the
    same 30s cache + same hmac.compare_digest contract.
    """
    with _api_key_lock:
        if time.time() - _api_key_cache["ts"] < _API_KEY_CACHE_TTL:
            return _api_key_cache["key"] or ""
    env_key = (os.environ.get("CRYPTO_SIGNAL_API_KEY") or "").strip()
    if env_key:
        key = env_key
    else:
        cfg = alerts.load_alerts_config()
        key = cfg.get("api_key", "")
    with _api_key_lock:
        _api_key_cache["key"] = key
        _api_key_cache["ts"] = time.time()
    return key


def require_api_key(x_api_key: str = Header(default="")):
    """Validate X-API-Key header on auth-required endpoints.

    Mirrors api.py.require_api_key:
    - hmac.compare_digest to prevent timing-based key enumeration.
    - Fails CLOSED if no key is configured (returns 503 with operator
      guidance) unless CRYPTO_SIGNAL_ALLOW_UNAUTH=true.
    """
    expected = _get_configured_api_key()
    if not expected:
        if os.environ.get("CRYPTO_SIGNAL_ALLOW_UNAUTH", "").strip().lower() == "true":
            return
        raise HTTPException(
            status_code=503,
            detail=(
                "API key not configured. Set 'api_key' in alerts_config.json "
                "(or via the Settings page) to enable authenticated access, "
                "or export CRYPTO_SIGNAL_ALLOW_UNAUTH=true for local development."
            ),
        )
    if not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
