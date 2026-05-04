"""Regression tests for the overnight 2026-05-03 audit fix batch.

Locks in:
- Tier 1 MEDIUM: idempotency cache hard cap + half-eviction
- Tier 1 MEDIUM: default_order_type lowercase normalize on read
- Tier 1 MEDIUM: settings GET emits Cache-Control no-store
- Tier 3 HIGH: data_feeds.get_funding_rate does not poison the cache
  with empty/N/A results (already in 47a6f90; explicit assertion here)
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest


# ─── Tier 1: idempotency cache hard cap ───────────────────────────────────────


def test_idempotency_cache_hard_cap_evicts_oldest_half():
    """When the cap is reached, _idempotency_store should evict the oldest
    half before inserting the new entry. This bounds memory growth even if
    TTL pruning falls behind."""
    import execution

    # Save and restore module-level state so this test does not bleed
    # into others in the same suite.
    saved_cache = dict(execution._idempotency_cache)
    saved_max = execution._IDEMPOTENCY_MAX_ENTRIES
    try:
        execution._IDEMPOTENCY_MAX_ENTRIES = 100
        execution._idempotency_cache.clear()

        # Fill the cache to the cap.
        for i in range(100):
            execution._idempotency_store(f"cid_{i}", {"i": i})
        assert len(execution._idempotency_cache) == 100

        # One more insert should trigger half-eviction.
        execution._idempotency_store("cid_overflow", {"i": "overflow"})
        # After eviction (50 removed) + 1 new insert = 51.
        assert len(execution._idempotency_cache) == 51
        # The newest entry must still be there.
        assert "cid_overflow" in execution._idempotency_cache
        # The oldest half must be gone.
        assert "cid_0" not in execution._idempotency_cache
        assert "cid_1" not in execution._idempotency_cache
        # An entry past the eviction line must remain.
        assert "cid_99" in execution._idempotency_cache
    finally:
        execution._idempotency_cache.clear()
        execution._idempotency_cache.update(saved_cache)
        execution._IDEMPOTENCY_MAX_ENTRIES = saved_max


# ─── Tier 1: default_order_type lowercase normalize ──────────────────────────


def test_default_order_type_lowercased_on_read():
    """The settings PUT validator accepts 'MARKET' (uppercase) as well as
    'market'. ccxt expects lowercase at the exchange API. get_exec_config
    must lowercase whatever the user saved before passing downstream."""
    import execution

    fake_cfg = {
        "default_order_type": "MARKET",
    }
    with patch.object(execution._alerts, "load_alerts_config", return_value=fake_cfg):
        cfg = execution.get_exec_config()
    assert cfg["default_order_type"] == "market"


def test_default_order_type_strips_whitespace_and_lowers():
    """Combined: whitespace + uppercase both normalized."""
    import execution

    fake_cfg = {
        "default_order_type": "  Limit  ",
    }
    with patch.object(execution._alerts, "load_alerts_config", return_value=fake_cfg):
        cfg = execution.get_exec_config()
    assert cfg["default_order_type"] == "limit"


def test_default_order_type_falls_back_to_market_when_blank():
    """Empty / whitespace-only value falls back to the safe default."""
    import execution

    for blank in ("", "   ", None):
        fake_cfg = {"default_order_type": blank}
        with patch.object(execution._alerts, "load_alerts_config", return_value=fake_cfg):
            cfg = execution.get_exec_config()
        assert cfg["default_order_type"] == "market"


# ─── Tier 1: settings GET Cache-Control header ───────────────────────────────


def test_settings_get_emits_cache_control_no_store():
    """Settings include redacted secrets + live config — no cache should
    retain the response. Defense in depth alongside redaction."""
    os.environ["CRYPTO_SIGNAL_ALLOW_UNAUTH"] = "true"
    try:
        from fastapi.testclient import TestClient
        from api import app

        client = TestClient(app)
        r = client.get("/settings/")
        assert r.status_code == 200
        cache_header = r.headers.get("cache-control", "").lower()
        assert "no-store" in cache_header, (
            f"Expected 'no-store' in Cache-Control, got: {cache_header!r}"
        )
    finally:
        os.environ.pop("CRYPTO_SIGNAL_ALLOW_UNAUTH", None)


# ─── Tier 3: funding cache does not poison with empty results ───────────────


def test_funding_rate_does_not_cache_empty_result():
    """When OKX + Bybit both fail, the empty/N/A result should NOT be written
    to the cache, so the next call retries the upstream instead of seeing
    a poisoned cache hit for the full TTL window."""
    import data_feeds

    # Save + restore module-level cache so we don't bleed.
    saved_cache = dict(data_feeds._BINANCE_FUNDING_CACHE)
    try:
        data_feeds._BINANCE_FUNDING_CACHE.clear()

        with patch.object(data_feeds._SESSION, "get") as mock_get:
            # Both upstreams fail with a network error.
            mock_get.side_effect = Exception("simulated network failure")
            result = data_feeds.get_funding_rate("BTC/USDT")

        # Got a fallback empty result.
        assert result.get("signal") == "N/A"
        # Cache must NOT contain BTC/USDT — that's the fix.
        assert "BTC/USDT" not in data_feeds._BINANCE_FUNDING_CACHE, (
            "empty/N/A result must NOT be persisted into the cache"
        )
    finally:
        data_feeds._BINANCE_FUNDING_CACHE.clear()
        data_feeds._BINANCE_FUNDING_CACHE.update(saved_cache)
