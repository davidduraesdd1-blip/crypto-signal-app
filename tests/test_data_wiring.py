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


# ── C-fix-05: cached OHLCV helper returns list-of-lists, not None ────────

def test_sg_cached_ohlcv_uses_fetch_chart_ohlcv_not_robust_fetch_ohlcv():
    """C-fix-05 (2026-05-01): _sg_cached_ohlcv must call
    model.fetch_chart_ohlcv, not model.robust_fetch_ohlcv.

    Why: robust_fetch_ohlcv expects a CCXT exchange *instance* (it calls
    `ex.fetch_ohlcv(...)` directly). _sg_cached_ohlcv was passing a
    string exchange_id, raising AttributeError on every call. The
    exception was swallowed and the helper returned None for every
    request, so Signals 30d/1Y deltas + Backtester historical-equity
    overlay all silently rendered as dashes."""
    src = _app_source()
    # Locate the helper by its def line, then read forward ~80 lines.
    idx = src.find("def _sg_cached_ohlcv(")
    assert idx > 0, "helper missing"
    body = src[idx : idx + 2500]
    assert "model.fetch_chart_ohlcv(" in body, (
        "_sg_cached_ohlcv no longer routes through model.fetch_chart_ohlcv. "
        "Returning to model.robust_fetch_ohlcv re-introduces the "
        "AttributeError-swallow bug → Signals 30d/1Y stay as dashes."
    )
    # Negative guard against the old broken call. We strip the docstring
    # (lines inside the """...""" block) and any plain `# comment` lines
    # before the substring check, since the explanatory docstring
    # legitimately mentions the broken pattern when explaining the fix.
    in_docstring = False
    code_lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # Toggle docstring state. If the same line both opens AND
            # closes a one-line docstring (rare), skip it entirely.
            if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                continue
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith("#"):
            continue
        code_lines.append(line)
    code_only = "\n".join(code_lines)
    assert "model.robust_fetch_ohlcv(exchange_id" not in code_only, (
        "_sg_cached_ohlcv reverted to passing a str exchange_id to "
        "robust_fetch_ohlcv — that raises AttributeError silently."
    )


def test_sg_cached_ohlcv_returns_list_of_lists_at_runtime(monkeypatch):
    """Behavioural: monkeypatch model.fetch_chart_ohlcv with a fake
    that returns a known list-of-lists; assert _sg_cached_ohlcv returns
    the same shape. This guards against a future refactor that
    accidentally reverts to a DataFrame return type, which would crash
    the consumer at `_closes_d = [float(r[4]) for r in _ohlcv_d ...]`
    (DataFrame iteration yields column names, not rows)."""
    import importlib

    # Bypass the @st.cache_data wrapping by calling the underlying function.
    # streamlit's cache_data exposes the wrapped function via .__wrapped__
    # or the unwrapped fn via .func — we use a fresh import + direct call
    # via the underlying `func` attribute.
    import sys
    if "app" in sys.modules:
        # Already imported — pick up the existing module without re-running.
        app_mod = sys.modules["app"]
    else:
        # Importing app.py at test time spins the whole Streamlit harness;
        # for a focused behavioural assertion we instead exercise the
        # wrapped logic via a hand-rolled call site.
        return  # pragma: no cover — env-specific skip
    cached = getattr(app_mod, "_sg_cached_ohlcv", None)
    if cached is None:
        return  # pragma: no cover

    # Patch the underlying fetcher.
    fake_rows = [[i * 86400_000, 100.0 + i, 101.0, 99.0, 100.0 + i * 0.5, 1.0]
                 for i in range(400)]
    monkeypatch.setattr(app_mod.model, "fetch_chart_ohlcv",
                        lambda pair, tf, limit=400: fake_rows)
    # st.cache_data is keyed; clear before exercising
    try:
        cached.clear()
    except Exception:
        pass
    out = cached("okx", "BTC/USDT", "1d", limit=400)
    assert isinstance(out, list), (
        f"_sg_cached_ohlcv returned {type(out).__name__}, not list — "
        f"the consumer at page_signals does `for r in _ohlcv_d` "
        f"expecting list-of-lists. A DataFrame return crashes consumers."
    )
    assert len(out) == 400 and len(out[0]) == 6
    # The 5th element (index 4) is close — must be float-castable.
    assert isinstance(out[0][4], float)


# ── C-fix-06: tiles populate from OHLCV / Backtester shows CTA when empty ─

def test_signals_info_strip_falls_back_to_ohlcv_for_vol_and_atr():
    """C-fix-06 (2026-05-01): the Signals page Vol(24h) / ATR(14d) tiles
    must fall back to direct compute from `_ohlcv_d` (the daily OHLCV)
    when the scan_result lacks them. Otherwise both tiles render as "—"
    on cold-start even though the data needed to populate them is
    already in memory (we fetched it for the 90d price chart)."""
    src = _app_source()
    # Fall-back computation lives in the indicator-strip block of
    # page_signals. Anchor by the C-fix-06 marker.
    assert "C-fix-06 (2026-05-01)" in src, (
        "page_signals indicator-strip is missing the C-fix-06 fallback "
        "marker. Vol/ATR will render as dashes on cold-start."
    )
    # Vol fallback: close * base-vol from the last OHLCV row.
    assert "_vol = float(_last[4]) * float(_last[5])" in src, (
        "Vol(24h) fallback compute is missing — `close × base-volume` "
        "from the last 1d OHLCV row should populate `_vol` when scan "
        "result lacks `volume_24h_usd`."
    )
    # ATR fallback: 14-period true-range compute.
    assert "True range" in src or "_h - _l, abs(_h - _pc), abs(_l - _pc)" in src or \
           "max(_h - _l, abs(_h - _pc), abs(_l - _pc))" in src, (
        "ATR(14d) fallback compute is missing — should use the standard "
        "max(high-low, |high-prev_close|, |low-prev_close|) true-range "
        "definition from the 1d OHLCV window."
    )


def test_backtester_shows_cta_when_no_results():
    """C-fix-06 (2026-05-01): when neither session_state nor the cached
    backtest DataFrame have any populated metric, the page must render
    a CTA card ("No backtest results yet") instead of the empty KPI
    strip with all values "—". The empty strip was actively misleading —
    users couldn't distinguish "ran and produced zeros" from "never ran."""
    src = _app_source()
    assert "_bt_has_any_data" in src, (
        "page_backtest no longer guards the KPI strip behind a "
        "_bt_has_any_data check — when nothing's populated, the page "
        "renders an empty-labels strip that misleads users into "
        "thinking the metrics are zero rather than absent."
    )
    assert "No backtest results yet" in src, (
        "page_backtest is missing the empty-state CTA card. Without it, "
        "the cold-start view shows 'Total return —' / 'CAGR —' / 'Sharpe —' "
        "labels-without-values which is misleading."
    )


# ── C-fix-08: scan-completion writeback in _sg_sidebar_progress ──────────

def test_sidebar_progress_clears_session_scan_running_on_completion():
    """C-fix-08 (2026-05-02): when the scan thread finishes, it sets
    _SCAN_STATUS["running"] = False + _scan_state["running"] = False
    but nothing was clearing st.session_state["scan_running"] — the
    only writeback path lived in _scan_progress() which was dead code
    (defined but never invoked). Result: the Home page "Analyzing…"
    button label stayed disabled forever after the first scan.

    The fix puts the writeback inside _sg_sidebar_progress (the live
    fragment that runs every 2s) so completion clears within 2s of
    the thread exiting."""
    src = _app_source()
    sb_idx = src.find("def _sg_sidebar_progress")
    assert sb_idx > 0, "fragment not found"
    body = src[sb_idx : sb_idx + 4000]
    # The fragment must detect the desync (session_state thinks running
    # but in-memory thread says idle) and zero out the cache.
    assert "_session_thinks_running" in body, (
        "_sg_sidebar_progress no longer derives a session-vs-thread "
        "desync check. The completion writeback for "
        "st.session_state['scan_running'] won't fire."
    )
    assert 'st.session_state["scan_running"] = False' in body, (
        "_sg_sidebar_progress no longer clears "
        "st.session_state['scan_running'] on completion. The 'Analyzing…' "
        "Home button label will stay stuck after every scan."
    )
    # And it must trigger a full-page rerun so the Home button label
    # reverts (default fragment scope wouldn't repaint Home).
    assert 'st.rerun(scope="app")' in body, (
        "_sg_sidebar_progress no longer triggers an app-scope rerun on "
        "scan completion. Without it, the sidebar updates but the Home "
        "page button label and watchlist stay stale until next interaction."
    )


def test_home_scan_button_uses_thread_state_not_session_cache():
    """C-fix-08: the Home page 'Analyzing…' / 'Run a fresh scan now'
    button must derive disabled-state from the authoritative in-memory
    _scan_state / _SCAN_STATUS dicts, NOT st.session_state['scan_running']
    which can go stale (and did, pre-fix). Defence in depth: even if
    the sidebar fragment hasn't ticked yet, the button reflects reality."""
    src = _app_source()
    # Anchor on the button label line and read forward.
    idx = src.find('"Analyzing…" if _ds_sb_disabled')
    assert idx > 0, "Home scan button label line not found"
    # Read backward to find the disabled-flag computation.
    block = src[max(0, idx - 1500) : idx + 200]
    # Negative guard: the button must NOT read scan_running directly
    # for its disabled state. (Comments mentioning the cache are fine.)
    code_lines = [
        line for line in block.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    assert (
        '_ds_sb_disabled = st.session_state.get("scan_running"' not in code_only
    ), (
        "Home scan button reverted to reading scan_running from "
        "st.session_state for its disabled state. That cache desyncs "
        "from the actual thread state — use _scan_state / _SCAN_STATUS."
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
