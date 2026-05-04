"""Regression tests for the overnight 2026-05-03 audit fix batch.

Locks in:
- Tier 1 MEDIUM: idempotency cache hard cap + half-eviction
- Tier 1 MEDIUM: default_order_type lowercase normalize on read
- Tier 1 MEDIUM: settings GET emits Cache-Control no-store
- Tier 3 HIGH: data_feeds.get_funding_rate does not poison the cache
  with empty/N/A results (already in 47a6f90; explicit assertion here)
- Tier 1 HIGH: api.py CORS allow_origins drops bare `http://localhost`
- Tier 1 HIGH: api.py CORS regex admits the v0-prefixed Vercel URL
- Tier 5 MEDIUM: ai_feedback.calibrate_alert_thresholds wraps via
  update_alerts_config (RLock-protected)
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


# ─── Tier 1: CORS allowlist + regex ──────────────────────────────────────────


def test_cors_allow_origins_drops_bare_localhost():
    """The 47a6f90 fix removed the port-less `http://localhost` entry from
    allow_origins. The 8501 (Streamlit) and 3000 (Next.js) ports remain.
    Locks in the narrowing so a future regen of api.py from a v0/older
    template can't silently re-add the over-broad entry."""
    import re
    api_text = open(
        os.path.join(os.path.dirname(__file__), "..", "api.py"),
        encoding="utf-8",
    ).read()

    # The CORSMiddleware allow_origins block.
    block = re.search(r"allow_origins=\[(.+?)\]", api_text, re.DOTALL)
    assert block, "could not locate allow_origins literal in api.py"
    origins = block.group(1)

    # Bare `http://localhost"` (no port, with closing quote) must NOT appear.
    assert '"http://localhost"' not in origins, (
        'allow_origins re-introduced bare port-less "http://localhost" — '
        "this matches every localhost service the user runs and was "
        "explicitly removed in commit 47a6f90"
    )
    # The two scoped dev origins remain.
    assert '"http://localhost:8501"' in origins
    assert '"http://localhost:3000"' in origins


def test_cors_regex_admits_v0_vercel_urls_and_blocks_attackers():
    """The CORS regex was broadened to admit v0-prefixed Vercel URLs (the
    v0 project assigned `v0-davidduraesdd1-blip-crypto-signa.vercel.app`,
    which the original `crypto-signal-app(...)?` regex rejected). Verify
    real URLs match + adversarial ones don't."""
    import re
    os.environ["CRYPTO_SIGNAL_ALLOW_UNAUTH"] = "true"
    try:
        from api import app as fastapi_app
    finally:
        os.environ.pop("CRYPTO_SIGNAL_ALLOW_UNAUTH", None)

    # Pull the live regex out of the CORSMiddleware kwargs.
    cors_mw = next(
        m for m in fastapi_app.user_middleware if m.cls.__name__ == "CORSMiddleware"
    )
    pattern = cors_mw.kwargs["allow_origin_regex"]
    assert "vercel" in pattern

    admit = [
        "https://v0-davidduraesdd1-blip-crypto-signa.vercel.app",
        "https://v0-davidduraesdd1-blip-crypto-signal-cap56cwr8.vercel.app",
        "https://v0-davidduraesdd1-blip-git-9788da-davidduraesdd1-3056s-projects.vercel.app",
        "https://crypto-signal-app.vercel.app",
        "https://crypto-signal-app-abc-davidduraesdd1-blip.vercel.app",
    ]
    block = [
        "https://attacker.vercel.app",
        "https://crypto-signal-app-some-other-user.vercel.app",
        "https://malicious-davidduraesdd1-bli.vercel.app",
    ]
    for url in admit:
        assert re.match(pattern, url), f"regex must admit live URL: {url!r}"
    for url in block:
        assert not re.match(pattern, url), f"regex must reject attacker URL: {url!r}"


# ─── Tier 5: ai_feedback calibration uses RLock-wrapped helper ──────────────


def test_calibrate_alert_thresholds_uses_update_alerts_config():
    """The P1 fix added `alerts.update_alerts_config` as the canonical
    transactional API for any caller modifying the config. Calibration was
    bypassing it (load + save directly), reintroducing the read-modify-
    write race when calibration runs concurrently with a Settings PUT.
    47a6f90 wrapped it. Lock that in."""
    import ai_feedback
    import alerts as alerts_module
    from datetime import datetime, timezone, timedelta

    # Build enough fake DB rows to clear the _MIN_CALIBRATION_SAMPLES gate.
    fake_rows = [(70.0 + i * 0.1,) for i in range(ai_feedback._MIN_CALIBRATION_SAMPLES + 5)]

    class _FakeConn:
        def execute(self, sql, params):
            class _Result:
                def fetchall(_self):
                    return fake_rows
            return _Result()
        def close(self):
            pass

    with patch.object(ai_feedback.db, "_get_conn", return_value=_FakeConn()), \
         patch.object(alerts_module, "update_alerts_config", wraps=alerts_module.update_alerts_config) as spy_update, \
         patch.object(alerts_module, "load_alerts_config", return_value={"min_confidence": 70.0}), \
         patch.object(alerts_module, "save_alerts_config") as spy_save:
        result = ai_feedback.calibrate_alert_thresholds()

    assert result.get("calibrated") is True
    # update_alerts_config must have been called (RLock path).
    assert spy_update.call_count == 1, (
        "calibration must go through update_alerts_config to serialize "
        "with Settings PUTs under the P1 RLock"
    )
    # save_alerts_config is called only inside update_alerts_config (once).
    assert spy_save.call_count == 1
