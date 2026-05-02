"""tests/test_hyperliquid_funding_parser.py

Phase 5 audit C6 (Image 7): Hyperliquid funding annualisation was
8x too low (× 3 × 365 instead of × 24 × 365 — the API returns hourly
rate, not 8h). Plus the batch warming only cached pairs[0], so a
10-pair batch fired 10 identical POSTs.

These tests:
1. Lock the corrected annualisation factor.
2. Verify batch mode populates the cache for ALL response coins, not
   just pairs[0].
3. Verify the legacy funding_rate_8h alias is preserved AND equals
   funding_rate_1h * 8 for backwards compat.
"""
from __future__ import annotations

from unittest import mock

import pytest


def _fake_payload() -> list:
    """A two-asset Hyperliquid /info metaAndAssetCtxs response."""
    return [
        {
            "universe": [
                {"name": "BTC"},
                {"name": "ETH"},
            ],
        },
        [
            {"markPx": "60000", "openInterest": "5000", "funding": "0.00005"},   # 0.005% / hr
            {"markPx": "3000",  "openInterest": "20000", "funding": "-0.00002"}, # -0.002% / hr
        ],
    ]


def test_hyperliquid_annualisation_uses_hourly_factor() -> None:
    import data_feeds
    data_feeds._HL_CACHE.clear()

    fake_resp = mock.Mock()
    fake_resp.raise_for_status = mock.Mock()
    fake_resp.json.return_value = _fake_payload()

    with mock.patch.object(data_feeds._SESSION, "post", return_value=fake_resp):
        out = data_feeds.get_hyperliquid_stats("BTC/USDT")

    assert out.get("error") is None
    # 0.00005 (hourly) * 24 * 365 * 100 = 43.8 % annualised
    assert out["funding_rate_1h"] == pytest.approx(5e-5, rel=1e-6)
    assert out["funding_annualised_pct"] == pytest.approx(43.8, abs=0.05)


def test_hyperliquid_legacy_8h_alias_preserved() -> None:
    """Backwards compat: funding_rate_8h must still be present and
    equal to funding_rate_1h * 8."""
    import data_feeds
    data_feeds._HL_CACHE.clear()

    fake_resp = mock.Mock()
    fake_resp.raise_for_status = mock.Mock()
    fake_resp.json.return_value = _fake_payload()

    with mock.patch.object(data_feeds._SESSION, "post", return_value=fake_resp):
        out = data_feeds.get_hyperliquid_stats("BTC/USDT")

    assert "funding_rate_8h" in out
    assert "funding_rate_1h" in out
    assert out["funding_rate_8h"] == pytest.approx(out["funding_rate_1h"] * 8, rel=1e-6)


def test_hyperliquid_batch_caches_all_coins_in_one_post() -> None:
    """Audit C6: batch warming used to cache pairs[0] only. The dict
    comprehension then re-POSTed for each subsequent pair. Now the
    single warming POST should populate the cache for EVERY coin
    in the response."""
    import data_feeds
    data_feeds._HL_CACHE.clear()

    fake_resp = mock.Mock()
    fake_resp.raise_for_status = mock.Mock()
    fake_resp.json.return_value = _fake_payload()

    post_call_count = {"n": 0}

    def _counting_post(*args, **kwargs):
        post_call_count["n"] += 1
        return fake_resp

    with mock.patch.object(data_feeds._SESSION, "post", side_effect=_counting_post):
        out = data_feeds.get_hyperliquid_batch(["BTC", "ETH"])

    assert post_call_count["n"] == 1, (
        f"Expected exactly 1 /info POST for the whole batch; got "
        f"{post_call_count['n']} — batch caching regression."
    )
    # Both coins resolved and have non-error data
    assert out["BTC"].get("error") is None
    assert out["ETH"].get("error") is None
    assert out["BTC"]["funding_rate_1h"] == pytest.approx(5e-5, rel=1e-6)
    assert out["ETH"]["funding_rate_1h"] == pytest.approx(-2e-5, rel=1e-6)
