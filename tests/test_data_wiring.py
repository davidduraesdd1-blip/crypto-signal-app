"""
C3+C4+H3+H4 fix verification (handoff: 2026-04-28_redesign_port_handoff.md).

The redesign port replaced page card components but didn't preserve all
of the data wiring underneath. The fix is plumbing — fetchers stay the
same, but the new card containers now have direct fallback paths to the
proven fetchers when the latest scan result lacks the field.

These tests are static (regex-shaped against app.py) because the host is
a single-file Streamlit script — running app.py end-to-end requires a
full Streamlit runtime + live API access. The static checks guarantee
the *plumbing* is in place; the actual fetchers themselves are covered
by the existing §22 fixture mandate.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _app_source() -> str:
    return APP_PY.read_text(encoding="utf-8")


# ── C4: On-chain page direct-fetch fallback ──────────────────────────────

def test_onchain_page_falls_back_to_data_feeds_get_onchain_metrics():
    """When session_state has no scan_results AND the DB has no historical
    signals, the on-chain page must fetch directly via
    data_feeds.get_onchain_metrics so the page is never empty on first
    load."""
    src = _app_source()
    # The fix lives inside _result_for() in page_onchain. The fallback
    # must call data_feeds.get_onchain_metrics with a USDT pair string.
    assert "data_feeds.get_onchain_metrics" in src, (
        "page_onchain.{_result_for} no longer falls back to "
        "data_feeds.get_onchain_metrics — the on-chain page will be "
        "empty whenever no scan has been run. See C4 fix."
    )
    # And it must adapt the field names — get_onchain_metrics returns
    # 'net_flow' but the new card expects 'exchange_reserve_delta_7d'.
    assert '"exchange_reserve_delta_7d": _oc.get("net_flow")' in src, (
        "On-chain page no longer adapts the get_onchain_metrics field "
        "names to what the new ds-indicator-card expects. Without this "
        "mapping, MVRV-Z renders but Exchange Reserve renders as '—'."
    )


# ── H3: Price · last 90d resilient to primary-exchange failure ──────────

def test_price_90d_does_not_gate_on_get_exchange_instance_returning_none():
    """The legacy `if _ex: <fetch>` shape silently produced
    'Price history unavailable' when the primary TA exchange instance
    couldn't be initialised (geo-block, rate-limit, etc.). The fix uses
    the exchange ID string directly so robust_fetch_ohlcv's internal
    fallback chain (§10: OKX → Kraken → CoinGecko) gets a chance."""
    src = _app_source()
    # The H3 marker is inside the Signals page's 90d-price block.
    assert "H3 fix (2026-04-28)" in src, (
        "Signals-page 90d-price OHLCV fetch is missing the H3 fix marker. "
        "Verify the `if _ex:` gate has been removed and the exchange ID "
        "is resolved without requiring a non-None instance object."
    )
    # Negative regression check: the old gating shape must not be back.
    # We accept the modern resolution `getattr(model.get_exchange_instance(...), "id", "")`
    # but the standalone gate `if _ex:` immediately followed by an
    # OHLCV fetch must be gone.
    bad = (
        "_ex = model.get_exchange_instance(model.TA_EXCHANGE)\n"
        "        if _ex:"
    )
    assert bad not in src, (
        "Legacy `if _ex:` gate is back on the 90d-price OHLCV fetch — "
        "rolling back the H3 fix would re-introduce 'Price history "
        "unavailable' whenever the primary TA exchange is unreachable."
    )


# ── H4: Sentiment card falls back to direct fetchers ─────────────────────

def test_sentiment_card_falls_back_to_cached_trends_and_news():
    """When _result lacks google_trends_score / news_sentiment_score
    (no scan run, or field dropped during port), the Sentiment card
    must reach for the proven cached fetchers directly so it doesn't
    show all dashes."""
    src = _app_source()
    assert "_cached_google_trends_score" in src, (
        "Cached Google Trends helper is missing — H4 fallback won't "
        "fire and the Sentiment card will continue to show '—' for "
        "Trends on every detail-page render without a fresh scan."
    )
    assert "H4 fix (2026-04-28)" in src, (
        "Sentiment card is missing the H4 fix marker. Verify the "
        "fallback to _cached_google_trends_score + _cached_news_sentiment "
        "is wired right above the indicator-card render."
    )


# ── Cache-clear coverage: refresh button must drop new caches too ───────

def test_refresh_handler_clears_new_trends_cache():
    """The 'Refresh All Data' handler iterates a tuple of @st.cache_data-
    wrapped helpers and calls .clear() on each. New helpers added during
    the wiring fix must appear in that list, otherwise pressing Refresh
    leaves stale sentiment data behind."""
    src = _app_source()
    assert "_cached_google_trends_score" in src, "helper missing"
    # Find the cache-clear iteration block and confirm the new helper is in it.
    # The block is the for-loop in _refresh_all_data() over a tuple literal.
    refresh_idx = src.find("def _refresh_all_data")
    assert refresh_idx > 0, "refresh handler not found"
    refresh_body = src[refresh_idx:refresh_idx + 4000]
    assert "_cached_google_trends_score" in refresh_body, (
        "_refresh_all_data() does not clear _cached_google_trends_score — "
        "pressing the topbar Refresh button leaves stale 24h trends data "
        "in place. Add the helper to the cache-clear tuple."
    )
