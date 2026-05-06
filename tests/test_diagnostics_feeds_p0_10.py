"""P0-10 regression test for /diagnostics/feeds.

Doesn't actually hit the network in the test — uses monkeypatch to
verify the probe loop, cache, and response shape. Network probes are
covered by the smoke test in CI / by the operator hitting the live
endpoint after deploy.
"""
import time
from unittest.mock import patch


def test_probe_feed_returns_expected_shape():
    """A successful probe returns the documented dict shape."""
    from routers import diagnostics

    fake_resp = type("R", (), {"status": 200})()
    fake_cm = type("CM", (), {
        "__enter__": lambda self: fake_resp,
        "__exit__": lambda self, *a: None,
    })()

    with patch("urllib.request.urlopen", return_value=fake_cm):
        result = diagnostics._probe_feed(
            {"name": "Test", "url": "https://x", "method": "GET", "category": "ohlcv"}
        )
    assert result["status"] == "ok"
    assert result["http_code"] == 200
    assert result["category"] == "ohlcv"
    assert result["name"] == "Test"
    assert result["error"] is None
    assert isinstance(result["elapsed_ms"], int)


def test_probe_feed_handles_unreachable():
    """Network errors mark the probe as 'unreachable', not 'ok'."""
    from routers import diagnostics

    with patch("urllib.request.urlopen", side_effect=ConnectionError("simulated")):
        result = diagnostics._probe_feed(
            {"name": "Dead", "url": "https://x", "method": "GET", "category": "ohlcv"}
        )
    assert result["status"] == "unreachable"
    assert result["http_code"] is None
    assert "ConnectionError" in result["error"]


def test_probe_feed_handles_http_error():
    """Non-2xx HTTP responses mark probe as 'warn' with the actual code."""
    import urllib.error
    from routers import diagnostics

    err = urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        result = diagnostics._probe_feed(
            {"name": "FlakyHost", "url": "https://x", "method": "GET", "category": "macro"}
        )
    assert result["status"] == "warn"
    assert result["http_code"] == 503
    assert "503" in result["error"]


def test_feeds_cache_60s():
    """Second call within TTL returns cached payload (cached=True)."""
    from routers import diagnostics

    # Reset cache for a clean test
    diagnostics._feed_cache["ts"] = 0.0
    diagnostics._feed_cache["result"] = None

    fake_resp = type("R", (), {"status": 200})()
    fake_cm = type("CM", (), {
        "__enter__": lambda self: fake_resp,
        "__exit__": lambda self, *a: None,
    })()

    with patch("urllib.request.urlopen", return_value=fake_cm):
        first = diagnostics.get_feeds_health()
        second = diagnostics.get_feeds_health()

    assert first["cached"] is False
    assert second["cached"] is True
    # Same generated_at (the cache returns the original payload's timestamp)
    assert first["generated_at"] == second["generated_at"]


def test_feeds_response_shape():
    """Endpoint returns the documented top-level keys."""
    from routers import diagnostics

    diagnostics._feed_cache["ts"] = 0.0
    diagnostics._feed_cache["result"] = None

    fake_resp = type("R", (), {"status": 200})()
    fake_cm = type("CM", (), {
        "__enter__": lambda self: fake_resp,
        "__exit__": lambda self, *a: None,
    })()

    with patch("urllib.request.urlopen", return_value=fake_cm):
        result = diagnostics.get_feeds_health()

    assert "generated_at" in result
    assert "cached" in result
    assert "render_region" in result
    assert "feeds" in result
    assert "summary" in result
    assert isinstance(result["feeds"], list)
    assert len(result["feeds"]) == len(diagnostics._FEED_PROBES)
    assert result["summary"]["total"] == len(result["feeds"])


def test_feed_probe_specs_documented_sources():
    """Per CLAUDE.md §10, the probe list must cover the OHLCV chain
    + sentiment + macro feeds. This test guards against accidental
    deletion of probes during a future refactor."""
    from routers import diagnostics

    names = [p["name"] for p in diagnostics._FEED_PROBES]
    # OHLCV chain — every primary in CLAUDE.md §10
    for required in ("Kraken", "Gate.io", "Bybit", "MEXC", "OKX", "CoinGecko"):
        assert any(required in n for n in names), f"missing {required} probe"
    # Sentiment + macro
    assert any("alternative.me" in n for n in names)
    assert any("FRED" in n for n in names)
