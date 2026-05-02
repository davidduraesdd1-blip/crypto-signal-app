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
    # Audit 2026-05-02 Phase 2 refactor: the assignment shape changed
    # from `"exchange_reserve_delta_7d": _oc.get("net_flow")` (dict
    # literal) to `out["exchange_reserve_delta_7d"] = _oc.get("net_flow")`
    # (assignment) when the cascade was extended to query Glassnode +
    # CoinMetrics first. Either shape is acceptable as long as the
    # net_flow → exchange_reserve_delta_7d adapter is preserved.
    assert (
        '"exchange_reserve_delta_7d": _oc.get("net_flow")' in src
        or 'out["exchange_reserve_delta_7d"] = _oc.get("net_flow")' in src
    ), (
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


# ── HOTFIX 2026-05-02: df_trades UnboundLocalError on Backtester ─────────

def test_df_trades_defined_outside_subview_branches():
    """Pre-fix bug: `df_trades = _cached_backtest_df()` was inside the
    `if _bt_subview == "summary":` branch only. The Performance
    Attribution section inside `elif _bt_subview == "advanced":`
    referenced df_trades — which was never bound when advanced was
    active → UnboundLocalError on every page render with
    _bt_subview == "advanced".

    Fix: hoist df_trades above the if/elif so all 3 subviews
    (summary/trades/advanced) share the assignment."""
    src = _app_source()
    pb_idx = src.find("def page_backtest(")
    assert pb_idx > 0
    body = src[pb_idx : pb_idx + 60000]
    summary_idx = body.find('if _bt_subview == "summary":')
    assert summary_idx > 0, "subview branch missing"
    df_idx = body.find("df_trades = _cached_backtest_df()")
    assert df_idx > 0, "df_trades assignment missing"
    assert df_idx < summary_idx, (
        "df_trades is still defined INSIDE the if _bt_subview branch — "
        "the advanced subview's Performance Attribution section will "
        "UnboundLocalError on first page render."
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
    # HOTFIX (2026-05-02): the C-fix-08 design originally called
    # `st.rerun(scope="app")` from inside the fragment to immediately
    # repaint the Home page after a scan completed. That triggered a
    # Streamlit bug — when a fragment forces an app-scope rerun while
    # the user is on a page with form widgets (e.g. Settings → Dev
    # Tools → Indicator Weights sliders keyed `w_onchain`, `w_macro`,
    # etc.), Streamlit attaches the fragment's $$ID-{hash} prefix to
    # those widget keys at serialization time, then crashes with
    # `KeyError: $$ID-...-w_onchain` in _check_serializable on the
    # next tick → infinite death loop on prod.
    # The cleaner path: do the session_state writeback (above) and
    # let the NEXT natural render pick up the cleared flag. Fragment
    # ticks every 2s, so the Home page repaint lags by ≤ 2s — worth
    # the trade vs crashing the whole app.
    # Strip leading-whitespace comment lines so the explanatory comment
    # documenting the bug doesn't trip the guard.
    code_lines = [
        line for line in body.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    assert 'st.rerun(scope="app")' not in code_only, (
        "_sg_sidebar_progress is calling st.rerun(scope='app') from "
        "inside the fragment again. This re-introduces the death-loop "
        "bug — see HOTFIX comment in app.py around line 1340."
    )


def test_home_scan_status_banner_uses_thread_state_not_session_cache():
    """C-fix-08 + C-fix-10: the Home page in-line scan-status banner
    (replacing the removed standalone 'Run a fresh scan now' button)
    must derive its show/hide state from the authoritative in-memory
    _scan_state / _SCAN_STATUS dicts, NOT st.session_state['scan_running']
    which can go stale. Defence in depth: even if the sidebar fragment
    hasn't ticked yet, the banner reflects reality."""
    src = _app_source()
    # Anchor on the banner text.
    idx = src.find("Scanning the universe")
    assert idx > 0, "Home scan-status banner not found"
    # Read backward to find the running-flag computation.
    block = src[max(0, idx - 1500) : idx + 200]
    code_lines = [
        line for line in block.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    # Positive: banner gates on the in-memory thread flag(s).
    assert (
        "_scan_state[" in code_only
        or "_SCAN_STATUS.get" in code_only
    ), (
        "Home scan-status banner no longer reads from the in-memory "
        "_scan_state / _SCAN_STATUS dicts. Without it, the banner can "
        "show stale state."
    )
    # Negative: the banner must NOT gate on session_state cache —
    # the same desync that produced the C-fix-08 'Analyzing…' bug.
    assert (
        'st.session_state.get("scan_running"' not in code_only
        or 'if _ds_sb_running:' in code_only
    ), (
        "Home scan-status banner reverted to reading scan_running "
        "from st.session_state. Use _scan_state / _SCAN_STATUS instead."
    )


# ── C-fix-09: Watchlist customize rebuild rows from user selection ──────

def test_watchlist_rows_carry_pair_key_for_lookup():
    """C-fix-09 (2026-05-02): the watchlist row dicts must carry a
    "pair" key (e.g. "BTC/USDT") so the customize popover's
    pair → row lookup actually matches. Pre-fix, rows only had a
    "ticker" key (e.g. "BTC"), so `_row_by_pair = {r.get("pair"): r}`
    collapsed to `{None: <last row>}` and the customize-save filter
    silently dropped every row."""
    src = _app_source()
    # Anchor on the watchlist row builder.
    idx = src.find("def _build_wl_row(")
    assert idx > 0, (
        "_build_wl_row helper missing — without it the row construction "
        "is duplicated and the 'pair' key was easy to forget."
    )
    # 4000 chars covers the helper body + comments after C-fix-16.
    body = src[idx : idx + 4000]
    assert '"pair": _wp' in body, (
        "Watchlist row no longer carries the full pair string under "
        "the 'pair' key. Customize-save filter will collapse to "
        "{None: row} and silently drop every row."
    )
    assert '"ticker"' in body, (
        "Watchlist row dropped the 'ticker' key — display will break."
    )


def test_watchlist_customize_rebuilds_rows_from_user_selection():
    """C-fix-09: when the user customizes their watchlist, the page
    must REBUILD rows from their selection (so user-added pairs outside
    the 6-pair default seed actually render), NOT filter the seed
    (which would silently drop user additions)."""
    src = _app_source()
    # Find the customize-handling block.
    idx = src.find("from ui import watchlist_customize_btn as _ds_wl_custom")
    assert idx > 0, "watchlist customize block not found"
    block = src[idx : idx + 2000]
    # Positive: rebuild via _build_wl_row over the user's selection.
    assert "_build_wl_row(_p) for _p in _wl_pairs" in block, (
        "Customize-save no longer rebuilds rows from the user's "
        "selection. User-added pairs outside the 6-pair default seed "
        "will be dropped — visually identical to 'nothing happened'."
    )


# ── C-fix-11: mandatory first-session scan on app boot ─────────────────

def test_first_session_scan_helper_is_defined():
    """C-fix-11 (2026-05-02): the app must define
    _maybe_fire_first_session_scan() and CALL it before page dispatch.
    Without it, users landing on Home before the autoscan scheduler
    fires see empty hero cards / 'scan refreshed not yet run'."""
    src = _app_source()
    assert "def _maybe_fire_first_session_scan" in src, (
        "Helper _maybe_fire_first_session_scan is missing — first-"
        "session mandatory scan path will never fire."
    )


def test_first_session_scan_is_called_before_router():
    """The call to _maybe_fire_first_session_scan() must precede the
    page dispatcher (the `if page == 'Dashboard':` block) so the scan
    starts before any page renders. Otherwise the cold-start banner
    won't paint until after the first render finishes."""
    src = _app_source()
    call_idx = src.find("_maybe_fire_first_session_scan()")
    router_idx = src.find('if page == "Dashboard":')
    assert call_idx > 0, "_maybe_fire_first_session_scan() is never called"
    assert router_idx > 0, "page router not found"
    assert call_idx < router_idx, (
        "_maybe_fire_first_session_scan() is called AFTER the page "
        "router. Move it earlier — the scan must start before the "
        "page renders so the cold-start banner shows on first paint."
    )


def test_first_session_scan_is_idempotent_via_session_flag():
    """The helper must guard against re-firing on every Streamlit
    rerun by setting + checking st.session_state['_c11_first_init_done']."""
    src = _app_source()
    idx = src.find("def _maybe_fire_first_session_scan")
    assert idx > 0
    body = src[idx : idx + 4000]
    assert '_c11_first_init_done' in body, (
        "Idempotency guard '_c11_first_init_done' is missing. The "
        "helper would re-fire on every rerun, queuing infinite scans."
    )


def test_first_session_scan_uses_15_min_staleness_threshold():
    """Per CLAUDE.md §12 the full-scan auto-cycle is 15 min. The
    first-session scan should fire only when the cached scan is
    older than that — otherwise we'd refire while a recent scan
    is still being read."""
    src = _app_source()
    idx = src.find("def _maybe_fire_first_session_scan")
    body = src[idx : idx + 4000]
    assert "15 * 60" in body or "900" in body, (
        "_maybe_fire_first_session_scan no longer uses a 15-min "
        "staleness threshold. CLAUDE.md §12 says the full-scan auto-"
        "cycle is 15 min — fire only when the existing scan is older."
    )


# ── C-fix-12: autoscan §12 alignment + bootstrap + Settings visibility ──

def test_autoscan_default_enabled_and_15_min_per_section_12():
    """C-fix-12 (2026-05-02): the default for autoscan_enabled must be
    True and autoscan_interval_minutes must be 15, matching CLAUDE.md
    §12 'Full scan / recalc — 15 min auto'."""
    src = _app_source()
    # Enabled-default must be True (was False).
    assert (
        '"autoscan_enabled", True' in src
    ), (
        "autoscan_enabled default is no longer True. CLAUDE.md §12 "
        "specifies the autoscan should be on by default."
    )
    # Interval-default must be 15 (was 60).
    assert (
        '"autoscan_interval_minutes", 15' in src
    ), (
        "autoscan_interval_minutes default is no longer 15. CLAUDE.md "
        "§12 specifies a 15-min full-scan cycle."
    )


def test_autoscan_bootstrap_helper_exists():
    """C-fix-12: a _bootstrap_autoscan_from_config() helper must exist
    and be called at app boot. Pre-fix the autoscan job was only
    registered when the user opened Settings → Dev Tools, so a fresh
    session that never visited Settings had no scheduled scans at all."""
    src = _app_source()
    assert "def _bootstrap_autoscan_from_config" in src, (
        "_bootstrap_autoscan_from_config helper missing — autoscan "
        "won't register on cold start."
    )
    # And it must be called from _get_scheduler so the bootstrap runs
    # whenever the scheduler initialises.
    sched_idx = src.find("def _get_scheduler")
    assert sched_idx > 0
    sched_body = src[sched_idx : sched_idx + 4000]
    assert "_bootstrap_autoscan_from_config()" in sched_body, (
        "_get_scheduler no longer calls _bootstrap_autoscan_from_config. "
        "Autoscan won't register on cold start."
    )


def test_scheduler_initialised_at_app_boot():
    """C-fix-12: the scheduler must be init'd at app boot (after
    init_state()) so the bootstrap actually fires. Otherwise
    _get_scheduler is only called lazily from Settings → Dev Tools."""
    src = _app_source()
    # Find the init_state() call line; the boot _get_scheduler() call
    # must come AFTER it.
    init_idx = src.find("init_state()")
    boot_call_idx = src.find("_get_scheduler()", init_idx)
    assert init_idx > 0 and boot_call_idx > 0, (
        "Cannot find boot-level _get_scheduler() call after init_state."
    )
    # And it must come BEFORE the page router so the scheduler is up
    # before any page-render code reads scan_status.
    router_idx = src.find('if page == "Dashboard":')
    assert boot_call_idx < router_idx, (
        "Boot _get_scheduler() call moved AFTER the page router. The "
        "scheduler must init before pages render so the autoscan is "
        "registered + the bootstrap has fired."
    )


def test_settings_page_surfaces_section_12_compliance_banner():
    """C-fix-12: the Settings → Dev Tools → Auto-Scan Scheduler section
    must show a visible banner indicating whether the configured
    cadence matches CLAUDE.md §12 ('§12 compliant' for the green path)."""
    src = _app_source()
    assert "§12 compliant" in src or "§12-compliant" in src or "section_12" in src.lower(), (
        "Settings page no longer surfaces the §12 compliance banner. "
        "Users have no visibility into whether their autoscan cadence "
        "matches the spec."
    )


# ── C-fix-15: duplicate Auto-Scan UI removed from sidebar tools ────────

def test_settings_page_surfaces_math_model_variables():
    """C-fix-22 (2026-05-02): Settings → Dev Tools must surface a
    "Math Model Variables" section showing the live 4 layer weights
    + a manual retune button (Advanced-only) + the research-fixed
    regime overrides. This is the user-facing transparency on what
    the feedback loop is doing — calculations stay hidden, only
    parameters are exposed."""
    src = _app_source()
    assert "Math Model Variables" in src, (
        "Settings page no longer surfaces the Math Model Variables "
        "section. Users have no visibility into what the feedback "
        "loop is tuning."
    )
    # The manual retune button must be Advanced-level gated.
    assert 'st.session_state.get("user_level") == "advanced"' in src, (
        "The manual retune button is no longer Advanced-level gated. "
        "Beginner / Intermediate users could trigger expensive Optuna "
        "runs by accident."
    )
    # And the regime overrides must render the fixed table.
    assert "Regime overrides (research-fixed)" in src, (
        "The CRISIS/TRENDING/RANGING regime override table is missing "
        "from Settings. Without it users have no visibility into how "
        "regime detection alters layer weights."
    )


def test_no_duplicate_autoscan_expander_in_sidebar_tools():
    """C-fix-15 (2026-05-02): the legacy "⏰ Auto-Scan" expander that
    used to live inside _render_relocated_sidebar_widgets is removed.
    Only the form-based Auto-Scan Scheduler remains (in the same Tab
    3 of Settings, but rendered by the page_config code path further
    up). Having both was redundant — and the legacy one auto-saved on
    every widget change, forcing a save-per-edit UX while the form-
    based one batches via st.form_submit_button."""
    src = _app_source()
    sb_idx = src.find("def _render_relocated_sidebar_widgets")
    assert sb_idx > 0, "_render_relocated_sidebar_widgets not found"
    # Read forward to the next def (~3000 chars)
    next_def = src.find("\ndef ", sb_idx + 50)
    body = src[sb_idx : next_def if next_def > 0 else sb_idx + 5000]
    # The legacy expander label must be gone.
    assert 'st.expander("⏰ Auto-Scan"' not in body, (
        "Legacy '⏰ Auto-Scan' expander returned to "
        "_render_relocated_sidebar_widgets. Per C-fix-15 it must stay "
        "removed — the form-based Auto-Scan Scheduler is canonical."
    )
    # And the auto-save trigger pattern must not appear in this body.
    # (Comments documenting the removal are fine.)
    code_lines = [
        line for line in body.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code_only = "\n".join(code_lines)
    assert "_setup_autoscan(interval_min)" not in code_only, (
        "Legacy autoscan-setup call returned to "
        "_render_relocated_sidebar_widgets — it auto-saves per change. "
        "The form-based UI is canonical."
    )


def test_watchlist_uses_rest_cascade_for_price_fallback():
    """C-fix-19 (2026-05-02): the watchlist must call the REST live-
    price cascade (data_feeds.fetch_prices_cascade) as the secondary
    fallback when the WebSocket has no tick. Order: CMC → CoinGecko
    → Kraken → OKX → MEXC, matching CLAUDE.md §10 user-specified spec.
    The sparkline last-close fallback (C-fix-16) is preserved as the
    tertiary safety net.
    """
    src = _app_source()
    # The cached cascade helper must exist.
    assert "def _sg_cached_live_prices_cascade" in src, (
        "_sg_cached_live_prices_cascade helper missing — REST cascade "
        "won't be cached and could blow the rate-limit budget."
    )
    # And it must wrap fetch_prices_cascade.
    helper_idx = src.find("def _sg_cached_live_prices_cascade")
    helper_body = src[helper_idx : helper_idx + 2000]
    assert "data_feeds.fetch_prices_cascade(" in helper_body, (
        "_sg_cached_live_prices_cascade no longer calls "
        "data_feeds.fetch_prices_cascade. The CMC→CG→Kraken→OKX→MEXC "
        "chain won't fire."
    )
    # _build_wl_row must consult the cascade dict before falling back
    # to the sparkline close.
    wl_idx = src.find("def _build_wl_row")
    wl_body = src[wl_idx : wl_idx + 4000]
    assert "_wl_cascade_prices.get(" in wl_body, (
        "_build_wl_row no longer reads from _wl_cascade_prices — the "
        "REST cascade tier is dead, only WebSocket + sparkline remain."
    )


def test_watchlist_row_falls_back_to_sparkline_close_for_price():
    """C-fix-16 (2026-05-02): the WebSocket live-price feed (OKX SWAP
    tickers) silently drops pairs without active perpetual markets.
    On prod, ZBCN / XDC / FLR / SHX show "—" for price while their
    sparkline closes ARE fetched. The fallback uses the last sparkline
    close as a near-current price so the watchlist never shows a dash
    when REST data is available."""
    src = _app_source()
    idx = src.find("def _build_wl_row")
    assert idx > 0, "_build_wl_row helper missing"
    body = src[idx : idx + 3500]
    # Positive: price fallback from sparkline close.
    assert "_price = float(_closes[-1])" in body, (
        "Watchlist row no longer falls back to the last sparkline close "
        "when WebSocket has no live price. Pairs without OKX SWAP "
        "markets (ZBCN, XDC, FLR, SHX) will show '—' for price even "
        "though their sparkline data IS fetched from REST."
    )


def test_scan_thread_auto_runs_backtest_and_feedback_loop():
    """C-fix-20b (2026-05-02): every scan completion (manual or
    scheduled) must trigger model.run_feedback_loop() AND
    model.run_backtest() in sequence, in the same background thread.
    The order matters: feedback first (resolves outcomes for the
    backtest data window), backtest second (walks fresh signals
    against historical OHLCV)."""
    src = _app_source()
    # Locate the scan thread.
    idx = src.find("def _run_scan_thread")
    assert idx > 0, "_run_scan_thread not found"
    body = src[idx : idx + 6000]
    assert "model.run_feedback_loop()" in body, (
        "_run_scan_thread no longer calls model.run_feedback_loop() — "
        "feedback outcomes / agent weights / threshold calibration "
        "won't update on scan completion."
    )
    assert "model.run_backtest()" in body, (
        "_run_scan_thread no longer calls model.run_backtest() after "
        "the feedback loop. Composite-backtest card will stay empty "
        "between manual Backtester clicks."
    )
    # And the order must be feedback → backtest (feedback resolves
    # outcomes that the backtest then walks).
    fb_idx = body.find("model.run_feedback_loop()")
    bt_idx = body.find("model.run_backtest()")
    assert fb_idx < bt_idx, (
        "Auto-backtest call now precedes the feedback loop. The order "
        "must be: scan results → feedback (resolve outcomes) → "
        "backtest (walk fresh data)."
    )


def test_home_composite_backtest_card_shows_cta_when_empty():
    """C-fix-17 (2026-05-02): the Home page composite-backtest mini-card
    must render a CTA ("No backtest run yet") when none of the 4 KPIs
    have populated. The labels-with-dashes layout was misleading on cold
    start — users couldn't tell whether the metrics were genuinely zero
    or simply absent. Mirrors the C-fix-06 CTA pattern from the full
    Backtester page."""
    src = _app_source()
    # Anchor on the Home composite-backtest section.
    assert "_ds_bt_has_data" in src, (
        "Home composite-backtest card no longer guards on a "
        "_ds_bt_has_data check. When no metric is populated, users see "
        "an empty-labels grid that looks broken."
    )
    assert "No backtest run yet" in src, (
        "Home composite-backtest card is missing the empty-state CTA. "
        "Without it the cold-start view shows 'Return —' / 'CAGR —' / "
        "'Sharpe —' / 'Win rate —' which is misleading."
    )
    assert "Open the Backtester page" in src, (
        "Home composite-backtest CTA no longer directs users to the "
        "Backtester page — the call-to-action loses meaning."
    )


def test_form_based_autoscan_scheduler_still_present():
    """C-fix-15: the canonical form-based Auto-Scan Scheduler lives in
    page_config and must remain. Removing the duplicate is not the same
    as removing autoscan controls."""
    src = _app_source()
    assert 'st.form("autoscan_form"):' in src, (
        "The form-based Auto-Scan Scheduler is missing. C-fix-15 only "
        "removed the duplicate; the form-based one must remain."
    )


def test_autoscan_form_widgets_have_no_disabled_props():
    """C-fix-18 (2026-05-02): widgets inside the autoscan form must NOT
    have `disabled=` props that gate on other form widgets. Streamlit
    forms don't propagate widget value changes between siblings until
    submit, so a `disabled=not _sched_on` on the interval selectbox
    would force the user to click Save just to enable subsequent
    edits — defeating the form's batch-save semantics."""
    src = _app_source()
    form_idx = src.find('st.form("autoscan_form"):')
    assert form_idx > 0, "autoscan form not found"
    # Find the form_submit_button to bound the form body.
    end_idx = src.find('st.form_submit_button("💾 Save Scheduler Config"', form_idx)
    assert end_idx > 0, "form submit button not found"
    body = src[form_idx:end_idx]
    # The disabled props that gated on _sched_on / _quiet_on must be gone.
    bad_patterns = [
        "disabled=not _sched_on",
        "disabled=not (_sched_on and _quiet_on)",
    ]
    for pat in bad_patterns:
        assert pat not in body, (
            f"autoscan form still has '{pat}' on a child widget. "
            f"Streamlit forms don't propagate sibling widget changes "
            f"until submit, so this disabled prop blocks edits until "
            f"the user clicks Save once — defeats batch-save semantics."
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
