"""
C3 follow-up verification (handoff: 2026-04-28_redesign_port_handoff.md).

The Signals → BTC detail composite-score card and the Regimes / BTC
detail layer breakdown both pulled `layer_technical / layer_macro /
layer_sentiment / layer_onchain` from the latest scan result. When no
scan had run yet (cold cache, fresh deploy), every layer was None and
the composite_score_card rendered four empty bars + score "—".

Fix: when the result lacks all four layer fields, the page now falls
back to `_sg_cached_composite_per_pair(pair)` which composes the proven
fetchers (macro, on-chain, F&G, funding, BTC TA) and calls
`composite_signal.compute_composite_signal(...)` directly, then maps
the [-1, +1] layer scores to the card's 0-100 scale.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _app_source() -> str:
    return APP_PY.read_text(encoding="utf-8")


def test_composite_fallback_helper_defined():
    """`_sg_cached_composite_per_pair` must exist and call
    compute_composite_signal — without it, the C3 fallback can't fire."""
    src = _app_source()
    assert "def _sg_cached_composite_per_pair(pair: str)" in src, (
        "Cached composite-per-pair helper is missing — the C3 fallback "
        "won't fire and Signals/Regimes detail pages will render empty "
        "composite bars on cold cache."
    )
    assert "compute_composite_signal" in src, (
        "Helper no longer calls compute_composite_signal — the math "
        "layer's primary entry point is bypassed."
    )


def test_composite_fallback_called_from_signals_page():
    """The Signals page composite-score card block must reach for the
    helper when all four layers are None on the result."""
    src = _app_source()
    # Locate the C3 fallback marker we added in app.py.
    assert "C3 fallback (2026-04-29)" in src, (
        "Signals page composite-card block missing the C3 fallback "
        "marker comment. Verify the fallback to _sg_cached_composite_"
        "per_pair fires when _l_tech / _l_macro / _l_sent / _l_onch "
        "are all None."
    )
    # And the actual call site must be present.
    assert "_sg_cached_composite_per_pair(_pair)" in src, (
        "Signals page composite block no longer invokes "
        "_sg_cached_composite_per_pair — fallback is wired but never "
        "called."
    )


def test_composite_fallback_scale_mapping():
    """compute_composite_signal returns layer scores in [-1, +1] but
    composite_score_card expects 0-100. The fallback must map the scale
    or the bars render at min/max regardless of actual values."""
    src = _app_source()
    # Look for the mapping formula. We allow either of two equivalent
    # shapes: (v + 1.0) * 50.0 or (v + 1.0) / 2.0 * 100.
    has_mapping = (
        "(float(v) + 1.0) * 50.0" in src
        or "(float(v) + 1.0) / 2.0 * 100" in src
        or "(float(v) + 1) * 50" in src
    )
    assert has_mapping, (
        "Signals page composite fallback no longer maps the [-1, +1] "
        "score scale from compute_composite_signal to the 0-100 scale "
        "expected by composite_score_card. Without the mapping, all "
        "four bars render at 0% (negative score) or 100% (positive)."
    )


def test_composite_fallback_handles_missing_macro_gracefully():
    """If get_macro_enrichment fails, the helper must continue with an
    empty dict so the per-layer renormalisation in
    compute_composite_signal (P1 audit fix) takes over rather than
    crashing the whole page."""
    src = _app_source()
    # The helper must have a try/except around the macro fetch.
    helper_idx = src.find("def _sg_cached_composite_per_pair")
    assert helper_idx > 0
    helper_body = src[helper_idx:helper_idx + 4000]
    assert "get_macro_enrichment" in helper_body
    assert "_macro_enr = {}" in helper_body, (
        "Helper no longer falls back to an empty dict when "
        "get_macro_enrichment raises — a single transient FRED outage "
        "would now fail the entire composite fallback."
    )


def test_composite_fallback_btc_ta_only_for_btc_pairs():
    """fetch_btc_ta_signals is BTC-specific. For non-BTC pairs the
    helper must skip TA so it doesn't pollute alts with BTC-derived
    technical scores."""
    src = _app_source()
    helper_idx = src.find("def _sg_cached_composite_per_pair")
    helper_body = src[helper_idx:helper_idx + 4000]
    assert 'pair.upper().startswith("BTC")' in helper_body, (
        "Helper no longer gates the fetch_btc_ta_signals call on the "
        "pair being BTC — non-BTC pairs would receive BTC technicals."
    )


def test_refresh_handler_clears_composite_cache():
    """The Refresh button must drop _sg_cached_composite_per_pair so
    pressing it doesn't leave a 5-minute-stale composite displayed."""
    src = _app_source()
    refresh_idx = src.find("def _refresh_all_data")
    assert refresh_idx > 0
    refresh_body = src[refresh_idx:refresh_idx + 4000]
    assert "_sg_cached_composite_per_pair" in refresh_body, (
        "_refresh_all_data does not clear _sg_cached_composite_per_pair "
        "— pressing the topbar Refresh button leaves stale composite "
        "scores on detail pages for up to 5 more minutes."
    )
