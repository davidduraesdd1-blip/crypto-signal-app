"""
app.py — Crypto Signal Model v5.9.13 | Streamlit Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np

# ── pandas Copy-on-Write (perf: 30% memory reduction, avoids silent DF copies) ──
try:
    if tuple(int(x) for x in pd.__version__.split(".")[:2]) < (3, 0):
        pd.options.mode.copy_on_write = True
except Exception:
    pass
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import html as _html
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

# ─── Sentry error monitoring (free tier — only loads when DSN is set) ──────────

def _scrub_sentry_event(event, hint):
    """Remove API keys, PII, and expected-noise events from Sentry before sending."""
    _msg = str(event.get("message", "") or "")
    _exc_values = (event.get("exception") or {}).get("values") or []
    _exc_msgs = " ".join(str((v.get("value") or "")) for v in _exc_values)
    _combined = (_msg + " " + _exc_msgs).lower()
    # Anthropic credit exhaustion — billing issue, handled in code
    if "credit balance" in _combined and ("anthropic" in _combined or "400" in _combined):
        return None
    # WebSocket disconnect noise — expected on idle/reconnect
    if "connection to remote host was lost" in _combined:
        return None
    if "request" in event:
        event["request"].pop("cookies", None)
        event["request"].pop("headers", None)
    # Audit R1c/R1f: broaden token list (OKX PASSPHRASE, AUTH, etc.)
    _SENSITIVE = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASSPHRASE",
                  "DSN", "AUTH", "BEARER", "CREDENTIAL", "PRIVATE", "MNEMONIC")
    for key in list(event.get("extra", {}).keys()):
        if any(x in key.upper() for x in _SENSITIVE):
            event["extra"][key] = "[REDACTED]"
    return event


try:
    import sentry_sdk as _sentry_sdk
    _SENTRY_DSN = os.environ.get("SUPERGROK_SENTRY_DSN", "")
    if _SENTRY_DSN:
        _sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.05,
            profiles_sample_rate=0.0,
            before_send=_scrub_sentry_event,
            ignore_errors=["MediaFileStorageError"],
        )
except ImportError:
    pass


# ─── Input validation helpers (#13 security hardening) ──────────────────────
import re as _re


def _sanitize_input(value: str, max_len: int = 100) -> str:
    """Strip characters that are not alphanumeric, whitespace, dash, dot, or slash.
    Prevents injection of shell metacharacters or SQL-injection fragments into
    API call parameters and DB queries coming from user-controlled text inputs."""
    return _re.sub(r"[^\w\s\-\./]", "", str(value))[:max_len].strip()


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a numeric UI value to [min_val, max_val] to prevent out-of-range inputs."""
    return max(min_val, min(max_val, float(value)))


# ─── Security Audit Logger (#15) ────────────────────────────────────────────
# Dedicated logger for security-relevant events; does NOT propagate to root.
_audit_handler = logging.FileHandler(
    os.path.join(os.path.dirname(__file__), "supergrok_audit.log"),
    encoding="utf-8",
)
_audit_handler.setFormatter(logging.Formatter(
    "%(asctime)s [AUDIT] %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ"
))
_audit_log = logging.getLogger("supergrok.audit")
_audit_log.addHandler(_audit_handler)
_audit_log.setLevel(logging.INFO)
_audit_log.propagate = False

logger = logging.getLogger(__name__)

# Suppress "Connection pool is full" warnings from urllib3 — these come from CCXT's
# internal HTTP sessions during concurrent agent scans and are benign (connections are
# discarded, not failed). Raising to ERROR hides noise without masking real failures.
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)


def audit(event: str, **ctx) -> None:
    """Log a security-relevant user action to the audit trail."""
    extra = " ".join(f"{k}={v!r}" for k, v in ctx.items())
    _audit_log.info("%s %s", event, extra)

from apscheduler.schedulers.background import BackgroundScheduler
import alerts as _alerts
import chart_component as _chart
import database as _db
import websocket_feeds as _ws
import execution as _exec
import ui_components as _ui
import arbitrage as _arb
import data_feeds
# PERF-LAZY: optional/feature-gated modules loaded with try/except so a missing
# dependency never crashes the dashboard.  Sentinel = None → each call site
# already guards with "if _mod is not None" or a wrapping try/except.
try:
    import pdf_export as _pdf
except Exception as _e:
    logging.debug("[App] pdf_export unavailable: %s", _e)
    _pdf = None
try:
    import llm_analysis as _llm
except Exception as _e:
    logging.debug("[App] llm_analysis unavailable: %s", _e)
    _llm = None
try:
    import news_sentiment as _news_mod
except Exception as _e:
    logging.debug("[App] news_sentiment unavailable: %s", _e)
    _news_mod = None
try:
    import whale_tracker as _whale_mod
except Exception as _e:
    logging.debug("[App] whale_tracker unavailable: %s", _e)
    _whale_mod = None
try:
    import ml_predictor as _ml_mod
except Exception as _e:
    logging.debug("[App] ml_predictor unavailable: %s", _e)
    _ml_mod = None
try:
    import stress_test as _stress_mod
except Exception as _e:
    logging.debug("[App] stress_test unavailable: %s", _e)
    _stress_mod = None
try:
    import agent as _agent
except Exception as _e:
    logging.debug("[App] agent unavailable: %s", _e)
    _agent = None

# ── Sentry second init removed — duplicate of the module-level init at lines 22-55.
# The first init already has the full noise filter and runs earlier for better coverage.


def _numpy_serializer(obj):
    """JSON serializer for numpy scalar types (used by json.dumps in download buttons)."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        v = float(obj)
        # nan/inf are invalid JSON — convert to None
        if v != v or v == float("inf") or v == float("-inf"):
            return None
        return v
    if isinstance(obj, float):
        if obj != obj or obj == float("inf") or obj == float("-inf"):
            return None
        return obj
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def _export_scan_results(results: list, format: str = "csv") -> bytes:
    """Export scan results to CSV or JSON bytes."""
    import json as _json_mod

    if not results:
        return b""

    df_rows = [{
        "pair":         r.get("pair"),
        "signal":       r.get("direction") or r.get("signal"),
        "confidence":   r.get("confidence_avg_pct") or r.get("confidence"),
        "price":        r.get("price_usd") or r.get("price"),
        "rsi":          r.get("rsi"),
        "funding_rate": r.get("funding_rate"),
        "timestamp":    r.get("timestamp") or r.get("scan_timestamp"),
    } for r in results]

    if format == "csv":
        df_out = pd.DataFrame(df_rows)
        return df_out.to_csv(index=False).encode("utf-8")
    else:
        return _json_mod.dumps(results, default=_numpy_serializer, indent=2).encode("utf-8")


# ──────────────────────────────────────────────
# SCAN CACHE FILE — survives Streamlit reloads and browser refresh
# ──────────────────────────────────────────────
_SCAN_CACHE_FILE = "scan_results_cache.json"  # legacy — only used for cleanup on scan start

def _write_scan_status(running, timestamp=None, error=None, progress=0, pair=""):
    try:
        _db.write_scan_status(running, timestamp=timestamp, error=error,
                              progress=progress, pair=pair or "")
    except Exception as _e:
        logging.warning("[App] scan status write failed: %s", _e)  # APP-17: log DB errors

def _read_scan_status():
    try:
        return _db.read_scan_status()
    except Exception as _e:
        logging.warning("[App] scan_status DB read failed: %s", _e)
    return {"running": False, "timestamp": None, "error": None, "progress": 0, "pair": ""}

def _write_scan_results(results):
    try:
        _db.write_scan_results(results)
    except Exception as _e:
        logging.warning("[App] scan_results DB write failed: %s", _e)

def _read_scan_results():
    try:
        results = _db.read_scan_results()
        return results if results else None
    except Exception as _e:
        logging.warning("[App] scan_results DB read failed: %s", _e)
    return None


# ──────────────────────────────────────────────
# PERF: @st.cache_data wrappers for expensive DB reads and API calls
# Streamlit re-runs the full script on every user interaction; without caching
# every rerun hits SQLite and external APIs, adding 1-5+ seconds of latency.
# ──────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False, max_entries=3)
def _cached_signals_df(limit: int = 500) -> "pd.DataFrame":
    """Cache daily_signals DB read — 500 rows × ~30 cols, 60s TTL."""
    return _db.get_signals_df(limit=limit)


@st.cache_data(ttl=120, show_spinner=False, max_entries=1)
def _cached_paper_trades_df() -> "pd.DataFrame":
    """Cache paper_trades DB read — all closed trades, 2-min TTL."""
    return _db.get_paper_trades_df()


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_feedback_df() -> "pd.DataFrame":
    """Cache feedback_log DB read — limited to 500 most-recent rows, 5-min TTL.
    PERF: was loading 12 000+ rows on every rerun; now capped at 500 rows
    (~96% reduction in data transferred from SQLite) while still covering all
    meaningful recent performance history for UI charts and VaR calculations."""
    return _db.get_feedback_df(limit=500)


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_global_market() -> dict:
    """Return CoinGecko global market stats, cached 5 minutes.
    data_feeds.py also has its own in-memory cache per process; this Streamlit-layer cache
    prevents N concurrent worker processes each hitting CoinGecko independently.
    try/except ensures a rate-limit failure doesn't lock in {} for 5 min — raises and
    lets the next render retry against the module-level cache."""
    import data_feeds as _df
    try:
        return _df.get_global_market()
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_trending_coins() -> list:
    """Return CoinGecko trending coins, cached 5 minutes.
    Same rationale as _cached_global_market — prevents per-worker duplicate API calls."""
    import data_feeds as _df
    try:
        return _df.get_trending_coins()
    except Exception:
        return []


@st.cache_data(ttl=60, show_spinner=False, max_entries=5)
def _cached_backtest_df(run_id: str = None) -> "pd.DataFrame":
    """Cache backtest trades read — 60s TTL."""
    return _db.get_backtest_df(run_id=run_id)


@st.cache_data(ttl=60, show_spinner=False, max_entries=1)
def _cached_scan_results() -> list:
    """Cache scan_cache JSON read — large JSON parse, 60s TTL."""
    try:
        return _db.read_scan_results() or []
    except Exception:
        return []


@st.cache_data(ttl=120, show_spinner=False, max_entries=3)
def _cached_execution_log_df(limit: int = 300) -> "pd.DataFrame":
    """Cache execution_log read — frequent re-renders in Execution tab, 2-min TTL."""
    return _db.get_execution_log_df(limit=limit)


@st.cache_data(ttl=120, show_spinner=False, max_entries=3)
def _cached_agent_log_df(limit: int = 200) -> "pd.DataFrame":
    """Cache agent_log read — 2-min TTL."""
    return _db.get_agent_log_df(limit=limit)


@st.cache_data(ttl=420, show_spinner=False, max_entries=1)
def _cached_api_health() -> dict:
    """Cache API health check pings — 7-min TTL (staggered from 5-min caches to avoid
    simultaneous cache-miss HTTP storm at the 300-second mark that contributed to 503s)."""
    return data_feeds.validate_api_keys()


@st.cache_data(ttl=120, show_spinner=False, max_entries=3)
def _cached_arb_opportunities_df(limit: int = 100) -> "pd.DataFrame":
    """Cache arb_opportunities read — 2-min TTL."""
    return _db.get_arb_opportunities_df(limit=limit)


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_resolved_feedback_df(days: int = 365) -> "pd.DataFrame":
    """Cache resolved feedback — calendar heatmap, 5-min TTL.

    P1 audit fix — ensure the legacy CSV→SQLite migration has run
    before reading. database.ensure_csv_migrated() is a thread-safe
    one-shot from the lazy-init refactor (commit 82c1ccf).
    """
    try:
        _db.ensure_csv_migrated()
    except Exception as _mig_err:
        logger.debug("[App] ensure_csv_migrated failed: %s", _mig_err)
    # P1 audit also flagged days=365 as too large for hot-path reads;
    # cap at 180 to keep cold renders under the 60s budget. Callers
    # that genuinely need a full year can pass an explicit larger value.
    if days > 180:
        days = 180
    return _db.get_resolved_feedback_df(days=days)


@st.cache_data(ttl=300, show_spinner=False, max_entries=50)
def _cached_confidence_history(pair: str, days: int = 30) -> list:
    """Cache confidence history per pair — 5-min TTL."""
    return _db.get_confidence_history(pair, days=days)


@st.cache_data(ttl=60, show_spinner=False, max_entries=1)
def _cached_db_stats() -> dict:
    """Cache DB stats summary — 60s TTL."""
    return _db.get_db_stats()


# ── PERF: Single cached read for alerts config — replaces 16+ disk reads per rerun ──
@st.cache_data(ttl=30, show_spinner=False, max_entries=1)
def _cached_alerts_config() -> dict:
    """Cache alerts_config.json — 30s TTL (was 2s). Alerts rarely change mid-session;
    _save_alerts_config_and_clear() always calls .clear() on write so freshness is maintained."""
    return _alerts.load_alerts_config()


def _save_alerts_config_and_clear(cfg: dict) -> None:
    """Save alerts config and immediately invalidate the in-process cache."""
    _alerts.save_alerts_config(cfg)
    try:
        _cached_alerts_config.clear()
    except Exception as _clr_err:
        logger.debug("[App] alerts config cache clear failed: %s", _clr_err)


# ── PERF: @st.cache_data wrappers for slow external module calls ──────────────
@st.cache_data(ttl=3600, show_spinner=False, max_entries=24)
def _cached_news_sentiment(pair: str) -> dict:
    """Streamlit-level cache for news sentiment — 1 hr TTL per §12 (news/sentiment = 60 min).
    Module-level _cache in news_sentiment.py is per-process; this bridges workers."""
    if _news_mod is None:
        return {}
    return _news_mod.get_news_sentiment(pair)


@st.cache_data(ttl=300, show_spinner=False, max_entries=12)
def _sg_cached_composite_per_pair(pair: str) -> dict:
    """Compute the 4-layer composite signal for a single pair on demand.

    C3 follow-up (2026-04-29): the Signals → BTC detail composite-score
    card and the Regimes / BTC detail layer breakdown both pulled
    `layer_technical / layer_macro / layer_sentiment / layer_onchain`
    from the latest scan_result. When no scan had run yet (cold cache,
    fresh deploy), every layer was None and the composite_score_card
    rendered four empty bars + score "—". This wrapper fills the gap
    by composing the proven fetchers (proven by §22 fixtures + §4
    regression baseline) and calling `composite_signal.compute_composite_
    signal(...)` directly.

    5-minute TTL matches the §12 composite-signal recompute cycle.

    Returns:
      The full compute_composite_signal output dict, or {} on failure
      so the caller can graceful-fall to its existing "—" rendering.
    """
    try:
        from composite_signal import compute_composite_signal as _cs
    except Exception as _e:
        logger.debug("[App] composite_signal import failed: %s", _e)
        return {}

    # Macro is global (DXY / VIX / yield spread / CPI) — same for every pair.
    try:
        _macro_enr = data_feeds.get_macro_enrichment() or {}
    except Exception as _e:
        logger.debug("[App] macro fetch for composite failed: %s", _e)
        _macro_enr = {}
    macro_data = {
        "dxy":                 _macro_enr.get("dxy"),
        "vix":                 _macro_enr.get("vix"),
        "yield_spread_2y10y":  _macro_enr.get("yield_spread_pp"),
        # cpi_yoy isn't in get_macro_enrichment — leave None so the
        # composite layer renormalises over surviving sub-signals
        # (P1 audit fix in compute_composite_signal handles this).
        "cpi_yoy":             None,
    }

    # On-chain — per-pair via the proven (and now cache-warmed by C4) helper.
    try:
        onchain_data = data_feeds.get_onchain_metrics(pair) or {}
    except Exception as _e:
        logger.debug("[App] onchain fetch for composite %s failed: %s", pair, _e)
        onchain_data = {}

    # Fear & Greed (24h cache).
    try:
        _fng = _sg_cached_fear_greed() or {}
        fg_value = _fng.get("value")
    except Exception:
        fg_value = None

    # Per-pair BTC funding rate (10min cache). For non-BTC pairs we still
    # fetch the BTC funding because the sentiment layer treats it as a
    # market-wide crowding signal, not a per-pair one.
    try:
        _fr = _sg_cached_funding_rate("BTC/USDT") or {}
        btc_fund_pct = _fr.get("funding_rate_pct") or _fr.get("rate_pct")
    except Exception:
        btc_fund_pct = None

    # TA — for BTC use the dedicated fetcher; for other pairs we just
    # let it fall to {} so compute_composite_signal renormalises across
    # the surviving 3 layers (Macro/Sentiment/On-chain). Per-pair TA
    # would require a fresh OHLCV fetch + indicator computation; out of
    # scope for this fallback (it's what the scanner does in batch).
    ta_data: dict = {}
    if pair.upper().startswith("BTC"):
        try:
            ta_data = data_feeds.fetch_btc_ta_signals() or {}
        except Exception as _e:
            logger.debug("[App] BTC TA fetch for composite failed: %s", _e)
            ta_data = {}

    try:
        return _cs(
            macro_data=macro_data,
            onchain_data=onchain_data,
            fg_value=fg_value,
            put_call_ratio=None,
            ta_data=ta_data,
            fg_30d_avg=None,
            btc_funding_rate_pct=btc_fund_pct,
        ) or {}
    except Exception as _e:
        logger.debug("[App] compute_composite_signal for %s failed: %s", pair, _e)
        return {}


@st.cache_data(ttl=300, show_spinner=False, max_entries=48)
def _sg_cached_composite_per_pair_tf(pair: str, tf_view_payload: tuple) -> dict:
    """Open-item #3 (2026-04-30): per-timeframe composite. Same shape
    as `_sg_cached_composite_per_pair(pair)` but accepts a TF-specific
    `ta_data` overlay so the composite + 4-layer scores recompute
    when the user picks a different timeframe on the Signals page.

    Args:
        pair:            e.g. "BTC/USDT"
        tf_view_payload: a tuple of `(rsi, adx, supertrend, macd_div,
                         vwap, ichimoku, ...)` extracted from
                         `_result["timeframes"][tf]`. Tuple (not dict)
                         so it's hashable and Streamlit can cache it.

    Cache: 5min TTL (same as the non-TF helper) and 48 entries
    (4 timeframes × 12 pairs).

    The Macro / Sentiment / On-chain layer inputs are identical to
    the non-TF helper since those are not per-TF concepts. Only TA
    layer changes per timeframe.
    """
    try:
        from composite_signal import compute_composite_signal as _cs
    except Exception:
        return {}

    # Reconstruct ta_data dict from the hashable tuple payload.
    # The tuple shape mirrors what's in _result["timeframes"][tf]:
    #   (rsi, adx, macd_div, vwap, ichimoku, supertrend, sr_status,
    #    regime, strategy_bias, agent_vote, consensus, funding,
    #    open_interest, onchain, options_iv, ob_depth, cvd, tvl)
    # Most of these aren't read by score_ta_layer but it's
    # forward-compat to pass them through.
    keys = ("rsi", "adx", "macd_div", "vwap", "ichimoku",
            "supertrend", "sr_status", "regime", "strategy_bias",
            "agent_vote", "consensus", "funding", "open_interest",
            "onchain", "options_iv", "ob_depth", "cvd", "tvl")
    ta_data: dict = {}
    for k, v in zip(keys, tf_view_payload):
        if v not in (None, "N/A", ""):
            ta_data[k] = v
    # score_ta_layer reads `rsi` directly; it accepts numeric or
    # string. The other fields populate sub-signals.

    # Same global / per-pair fetchers as the non-TF helper.
    try:
        _macro_enr = data_feeds.get_macro_enrichment() or {}
    except Exception:
        _macro_enr = {}
    macro_data = {
        "dxy":                _macro_enr.get("dxy"),
        "vix":                _macro_enr.get("vix"),
        "yield_spread_2y10y": _macro_enr.get("yield_spread_pp"),
        "cpi_yoy":            None,
    }
    try:
        onchain_data = data_feeds.get_onchain_metrics(pair) or {}
    except Exception:
        onchain_data = {}
    try:
        fg_value = (_sg_cached_fear_greed() or {}).get("value")
    except Exception:
        fg_value = None
    try:
        _fr = _sg_cached_funding_rate("BTC/USDT") or {}
        btc_fund_pct = _fr.get("funding_rate_pct") or _fr.get("rate_pct")
    except Exception:
        btc_fund_pct = None

    try:
        return _cs(
            macro_data=macro_data,
            onchain_data=onchain_data,
            fg_value=fg_value,
            put_call_ratio=None,
            ta_data=ta_data,
            fg_30d_avg=None,
            btc_funding_rate_pct=btc_fund_pct,
        ) or {}
    except Exception as _e:
        logger.debug("[App] compute_composite_signal_tf %s/%s failed: %s",
                     pair, tf_view_payload[:2], _e)
        return {}


@st.cache_data(ttl=24 * 3600, show_spinner=False, max_entries=24)
def _cached_google_trends_score(keyword: str) -> dict:
    """Streamlit-level cache for Google Trends — 24 hr TTL.

    H4 fix (2026-04-28): the Sentiment indicator card on detail pages
    showed "—" for Google Trends because the result it pulled from
    `_result.get("google_trends_score")` was None whenever the page
    loaded without a fresh scan in session_state. This wrapper lets
    the card fall back to a direct (cached) trends fetch when no scan
    result is available. pytrends is rate-limited and slow, so a 24h
    TTL is plenty — sentiment doesn't move that fast.
    """
    try:
        return data_feeds.fetch_google_trends_score(keyword) or {}
    except Exception as _e:
        logger.debug("[App] cached trends fetch %s failed: %s", keyword, _e)
        return {}


@st.cache_data(ttl=300, show_spinner=False, max_entries=24)
def _cached_whale_activity(pair: str, price: float) -> dict:
    """Cache whale tracker HTTP calls — 5 min TTL."""
    if _whale_mod is None:
        return {}
    return _whale_mod.get_whale_activity(pair, price)


@st.cache_data(ttl=300, show_spinner=False, max_entries=24)
def _cached_liquidation_cascade(pair: str) -> dict:
    """Cache Coinglass liquidation cascade risk — 5 min TTL."""
    return data_feeds.get_liquidation_cascade_risk(pair)


@st.cache_data(ttl=120, show_spinner=False, max_entries=1)
def _cached_top_movers(top_n: int = 3) -> list:
    """Cache CoinGecko top movers — 2 min TTL."""
    return data_feeds.get_top_movers(top_n=top_n)


# PERF-21: cached wrappers for expensive dashboard-level calls that were
# previously invoked uncached on every Streamlit rerun.
@st.cache_data(ttl=300, show_spinner=False, max_entries=10)
def _cached_blood_in_streets(fng_value: int, btc_rsi) -> dict:
    """Cache compute_blood_in_streets() — expensive composite signal, 5-min TTL."""
    return data_feeds.compute_blood_in_streets(fng_value, btc_rsi)


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_macro_signal_adjustment() -> dict:
    """Cache get_macro_signal_adjustment() — HTTP call to FRED/DXY, 5-min TTL."""
    return data_feeds.get_macro_signal_adjustment()


@st.cache_data(ttl=300, show_spinner=False, max_entries=5)
def _cached_deribit_options_skew(currency: str) -> dict:
    """Cache get_deribit_options_skew() — Deribit API call, 5-min TTL."""
    return data_feeds.get_deribit_options_skew(currency)


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_macro_enrichment() -> dict:
    """Cache get_macro_enrichment() — yfinance HTTP calls (DXY/VIX/M2/rates), 5-min TTL.
    Without this cache, every Dashboard render triggered 4+ yfinance network requests."""
    return data_feeds.get_macro_enrichment()


@st.cache_data(ttl=300, show_spinner=False, max_entries=60)
def _cached_signal_win_rate(pair: str, direction: str, days: int = 90) -> dict:
    """Cache get_signal_win_rate() DB read — 5-min TTL per pair+direction."""
    return _db.get_signal_win_rate(pair=pair, direction=direction, days=days)


# ── P1 audit fix (P1-25) — wrappers for hot-path data_feeds calls that
# were previously invoked uncached on render-path hits, violating the
# §12 cache-window matrix. Each wrapper's TTL matches the §12 spec.
# Rendering code should call the _sg_cached_* helpers, not data_feeds
# directly.
@st.cache_data(ttl=86_400, show_spinner=False, max_entries=2)
def _sg_cached_fear_greed() -> dict:
    """Fear & Greed index — 24h TTL per CLAUDE.md §12."""
    try:
        return data_feeds.get_fear_greed() or {}
    except Exception as _e:
        logger.debug("[App] cached F&G fetch failed: %s", _e)
        return {}


@st.cache_data(ttl=600, show_spinner=False, max_entries=120)
def _sg_cached_funding_rate(pair: str) -> dict:
    """Funding rate for a single pair — 10-min TTL per CLAUDE.md §12."""
    try:
        return data_feeds.get_funding_rate(pair) or {}
    except Exception as _e:
        logger.debug("[App] cached funding fetch %s failed: %s", pair, _e)
        return {}


@st.cache_data(ttl=600, show_spinner=False, max_entries=20)
def _sg_cached_multi_exchange_funding(pair: str) -> dict:
    """Multi-exchange funding aggregator — 10-min TTL per CLAUDE.md §12.

    The audit flagged the Funding Rates scan page firing up to ~32
    sequential HTTP calls per click (8 pairs × 4 exchanges). With this
    wrapper, repeated clicks within a 10-minute window cost zero
    network round-trips.
    """
    try:
        return data_feeds.get_multi_exchange_funding_rates(pair) or {}
    except Exception as _e:
        logger.debug("[App] cached multi-fr fetch %s failed: %s", pair, _e)
        return {}


@st.cache_data(ttl=300, show_spinner=False, max_entries=200)
def _sg_cached_ohlcv(exchange_id: str, pair: str, timeframe: str, limit: int = 400):
    """OHLCV — 5-min TTL per CLAUDE.md §12 (intraday).

    Returns ccxt-format raw list-of-lists:
        [[ts_ms, open, high, low, close, volume], ...]

    C-fix-05 (2026-05-01): the previous implementation called
    model.robust_fetch_ohlcv(exchange_id, ...) passing a string, but
    that function expects a CCXT exchange instance — it calls
    `ex.fetch_ohlcv(...)` directly, which raises AttributeError on
    a str arg. The exception was swallowed and the helper returned
    None for every call, so Signals + Backtester period-changes (30d,
    1Y) and the historical-equity overlay all silently rendered as
    dashes / empty.

    The fix uses model.fetch_chart_ohlcv(pair, timeframe, limit), which
    is the right tool for this job:
      - returns ccxt-format list-of-lists (matches both consumers)
      - has a 6-exchange fallback chain (Kraken → OKX → Gate.io →
        Bybit → MEXC → CoinGecko) per crypto_model_core.py:526
      - doesn't need an exchange instance — the chain handles unreachable
        primaries internally

    `exchange_id` is preserved as the first positional arg so both
    cache keys stay distinct from the old (broken) entries and the
    call sites don't have to change their signature.
    """
    try:
        return model.fetch_chart_ohlcv(pair, timeframe, limit=limit)
    except Exception as _e:
        logger.debug("[App] cached OHLCV %s %s %s failed: %s",
                     exchange_id, pair, timeframe, _e)
        return None


@st.cache_data(ttl=8 * 3600, show_spinner=False, max_entries=120)
def _sg_cached_token_unlocks(pair: str) -> dict:
    """Token unlock schedule per pair — 8h TTL (matches cryptorank
    primary cache window in data_feeds._CRYPTORANK_UNLOCKS_TTL).

    Wraps `data_feeds.get_token_unlock_schedule(pair)` which uses
    cryptorank as PRIMARY (P1-26) + Tokenomist as fallback. Returns
    {"signal", "next_unlock_days", "unlock_pct_supply", "source",
    "error", "_ts"} or an empty dict on hard failure.
    """
    try:
        return data_feeds.get_token_unlock_schedule(pair) or {}
    except Exception as _e:
        logger.debug("[App] cached token-unlock fetch %s failed: %s", pair, _e)
        return {}


# ──────────────────────────────────────────────
# MODULE-LEVEL THREAD STATE (progress only — results go to file)
# ──────────────────────────────────────────────
_scan_lock = threading.Lock()
_scan_state = {
    "running": False,
    "progress": 0,
    "progress_pair": "Connecting to exchange...",
}

# PERF-30: module-level scan status dict — scan thread updates this directly
# so the progress fragment reads from memory instead of polling SQLite every 0.5s.
# SQLite is still written on completion (for persistence across restarts).
_SCAN_STATUS: dict = {
    "progress": 0,
    "current":  "",
    "total":    0,
    "running":  False,
}

# PERF-24: module-level full scan results store — keeps the large nested scan output dict
# out of st.session_state (which Streamlit re-serializes on every rerun).
# st.session_state["scan_results"] will store only lightweight summary dicts;
# full result accessed via _SCAN_RESULTS_STORE[pair] when a coin is selected.
_SCAN_RESULTS_STORE: dict = {}   # {pair: full_result_dict}

_bt_lock = threading.Lock()
_bt_state = {
    "running": False,
    "results": None,
    "error": None,
}

# ──────────────────────────────────────────────
# AUTO-SCAN SCHEDULER (module-level singleton)
# ──────────────────────────────────────────────
_scheduler: BackgroundScheduler | None = None
_AUTOSCAN_JOB_ID = "autoscan_job"


_CALIBRATION_JOB_ID = "calibration_job"


def _get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        # Audit R2g: job_defaults prevents autoscan + calibration + startup-
        # catchup jobs from stacking when the host pauses threads (laptop
        # sleep, Streamlit Cloud container scaling). Standalone scheduler.py
        # already has this — in-app copy was missing it.
        _scheduler = BackgroundScheduler(
            daemon=True,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 60,
            },
        )
        _scheduler.start()
        # Start alert threshold calibration job (runs every 6 hours)
        _setup_calibration_job()
        # C-fix-12 (2026-05-02): bootstrap the autoscan job from saved
        # config on first scheduler init. Without this, autoscan was
        # only registered when the user opened Settings → Dev Tools,
        # so fresh sessions had no scheduled scans at all.
        try:
            _bootstrap_autoscan_from_config()
        except Exception as _e_boot:
            logger.debug("[App] autoscan bootstrap failed: %s", _e_boot)
        # P1: Startup catch-up — delayed 90 seconds so the initial Streamlit render
        # completes and all @st.cache_data caches warm up before the feedback thread
        # acquires _exchange_cache_lock for load_markets(). Running immediately caused
        # the lock to be held for up to 60s during the 10-minute cache-expiry window,
        # which blocked concurrent render threads and triggered 503 health-check timeouts.
        _scheduler.add_job(
            _run_startup_feedback_catchup,
            trigger="date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=90),
            id="startup_feedback_catchup",
            replace_existing=True,
        )
    return _scheduler


def _run_startup_feedback_catchup():
    """Delayed startup feedback catch-up (runs 90s after first render via APScheduler)."""
    try:
        model.run_feedback_loop()
        logging.info("[Startup] Feedback catch-up complete")
    except Exception as _e:
        logging.debug("[Startup] Feedback catch-up (non-critical): %s", _e)


def _setup_calibration_job():
    """Schedule AI feedback loop calibration to run every 6 hours."""
    def _run_calibration():
        try:
            from ai_feedback import calibrate_alert_thresholds
            result = calibrate_alert_thresholds()
            if result.get("calibrated"):
                logging.info(
                    "[Calibration] Threshold %s → %.1f%% (n=%d)",
                    result.get("direction"), result.get("new_threshold", 0), result.get("samples", 0),
                )
        except Exception as e:
            logging.info("[Calibration] Failed: %s", e)

    sched = _scheduler
    if sched and not sched.get_job(_CALIBRATION_JOB_ID):
        sched.add_job(
            _run_calibration,
            trigger="interval",
            hours=6,
            id=_CALIBRATION_JOB_ID,
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )


def _bootstrap_autoscan_from_config() -> None:
    """C-fix-12 (2026-05-02): start the autoscan job at app boot if the
    saved config has it enabled. Pre-fix the job was only registered
    when the user navigated to Settings → Dev Tools — meaning a fresh
    session that never opens Settings would have NO automatic scans
    despite §12 spec, defeating the autoscan entirely. This is now
    called once during scheduler init so the job lives as long as the
    Streamlit process. Safe to call repeatedly: _setup_autoscan uses
    replace_existing=True."""
    try:
        _cfg = _cached_alerts_config() or {}
    except Exception as _e:
        logger.debug("[Bootstrap] alerts_config read for autoscan failed: %s", _e)
        _cfg = {}
    # Match the same defaults the Settings UI uses — §12 compliant.
    _enabled = bool(_cfg.get("autoscan_enabled", True))
    _interval = int(_cfg.get("autoscan_interval_minutes", 15) or 15)
    if _enabled:
        try:
            _setup_autoscan(_interval)
            logger.info("[Bootstrap] Autoscan registered: every %d min", _interval)
        except Exception as _e:
            logger.debug("[Bootstrap] autoscan registration failed: %s", _e)


def _setup_autoscan(interval_minutes: int):
    """Start or replace the auto-scan job with a new interval."""
    sched = _get_scheduler()
    sched.remove_job(_AUTOSCAN_JOB_ID) if sched.get_job(_AUTOSCAN_JOB_ID) else None
    # PERF-32: coalesce=True collapses missed/overlapping runs into one execution;
    # max_instances=1 prevents concurrent scans; misfire_grace_time=60 gives a
    # 60-second window to still run a missed job before discarding it.
    sched.add_job(
        lambda: _scheduled_scan(),
        trigger="interval",
        minutes=interval_minutes,
        id=_AUTOSCAN_JOB_ID,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=60,
        max_instances=1,
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=interval_minutes),
    )


def _stop_autoscan():
    """Remove the auto-scan job if it exists."""
    sched = _get_scheduler()
    if sched.get_job(_AUTOSCAN_JOB_ID):
        sched.remove_job(_AUTOSCAN_JOB_ID)


def _get_next_autoscan_time() -> datetime | None:
    """Return next scheduled run time, or None."""
    sched = _get_scheduler()
    job = sched.get_job(_AUTOSCAN_JOB_ID)
    return job.next_run_time if job else None


from scheduler import _in_quiet_hours  # canonical definition lives in scheduler.py

# ── Page config must be first ──
st.set_page_config(
    page_title="Family Office · Signal Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 2026-05 redesign: design-system theme injection (sibling-family left-rail
#    layout, token-based theming, Streamlit widget overrides). Runs BEFORE the
#    legacy inject_css() so the design tokens are the base and the legacy
#    overrides only affect components we haven't yet ported. All existing
#    logic (data feeds, signals, scheduler, ML) is preserved — only the
#    presentation layer changes.
try:
    from ui import (
        inject_theme as _ds_inject_theme,
        inject_streamlit_overrides as _ds_inject_overrides,
        register_plotly_template as _ds_register_plotly,
    )
    _ds_theme_pref = st.session_state.get("theme", "dark")
    _ds_inject_theme("crypto-signal-app", theme=_ds_theme_pref)
    _ds_inject_overrides()
    # Register the design-system Plotly template + set as default so every
    # chart inherits it. Per-chart update_layout(...) calls still win where
    # specific overrides are needed (transparent bg + tight margins, etc.).
    _ds_register_plotly(theme=_ds_theme_pref)
except Exception as _ds_err:
    logger.debug("[App] design-system theme injection failed: %s", _ds_err)

# ── Professional CSS design system (must come before any st.* calls) ──
_ui.inject_css()

# ── Signal/card color tokens come from ui/design_system.py (P0 audit fix) ─────
# Removed legacy SIGNAL_CSS that hard-coded dark hex over the design tokens —
# `.signal-buy/.signal-sell/.signal-hold` now use `var(--success)/--danger/
# --warning` defined by ui/design_system.inject_theme. `.card-container`
# rendering should use the `.ds-card` class from design_system.
st.markdown(
    """
    <style>
    .signal-buy      { color: var(--success); font-weight: 600; }
    .signal-sell     { color: var(--danger);  font-weight: 600; }
    .signal-hold     { color: var(--warning); font-weight: 600; }
    .metric-positive { color: var(--success); }
    .metric-negative { color: var(--danger); }
    .card-container  { background: var(--bg-1); border: 1px solid var(--border);
                       border-radius: var(--card-radius); padding: 12px;
                       margin-bottom: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Beginner / Advanced mode toggle (persisted in session state) ──────────────
if "beginner_mode" not in st.session_state:
    st.session_state["beginner_mode"] = True   # default: Simple view for new users

# ── Import model (after page config) ──
import sys
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
import crypto_model_core as model

# ──────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ──────────────────────────────────────────────
def init_state():
    defaults = {
        "scan_results": [],
        "scan_running": False,
        "scan_timestamp": None,
        "scan_error": None,
        "backtest_results": None,
        "backtest_running": False,
        "backtest_error": None,
        "chart_html": None,
        "chart_pair_label": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# C-fix-12 (2026-05-02): initialise the BackgroundScheduler at app boot
# so the autoscan job registers from saved config (defaults: enabled,
# 15 min interval per §12). Pre-fix _get_scheduler() was only called
# from _setup_autoscan / _render_relocated_sidebar_widgets, neither of
# which fires during a normal Home-page render — meaning the autoscan
# never ran at all unless the user manually opened Settings → Dev Tools.
# _get_scheduler() is idempotent (singleton guarded by `if _scheduler is None`).
try:
    _get_scheduler()
except Exception as _e_sched_boot:
    logger.debug("[App] scheduler boot failed: %s", _e_sched_boot)


# ──────────────────────────────────────────────
# C-fix-11 (2026-05-02): MANDATORY FIRST-SESSION SCAN — definition only
#
# On first session startup, if no scan has been run recently (< 15 min
# old per CLAUDE.md §12), kick one off automatically. Without this,
# users landing on Home before the autoscan scheduler had a chance to
# run saw empty hero cards / "scan refreshed not yet run" / blank
# composite — exactly the cold-start gap the post-deploy audit flagged.
#
# The CALL is placed later in the file (right before page dispatch)
# because it depends on `_start_scan`, which is defined further down.
# Gated by:
#   - st.session_state["_c11_first_init_done"] — fires ONCE per session
#     so navigation between pages doesn't re-trigger
#   - the existing thread-state re-entry guard — no second scan if one
#     is already running (e.g. fired by the autoscan scheduler)
#
# Staleness check: prefer the in-session scan_timestamp; fall back to
# the DB-stored scan_status so a fresh process attaching to a recent
# scan doesn't refire. > 15 min stale OR no timestamp at all → scan.
# ──────────────────────────────────────────────
def _maybe_fire_first_session_scan() -> None:
    if st.session_state.get("_c11_first_init_done"):
        return
    st.session_state["_c11_first_init_done"] = True

    # If a scan is already running we have nothing to do — the sidebar
    # progress fragment + in-line banner already show feedback.
    _running = (
        _SCAN_STATUS.get("running", False)
        or _scan_state.get("running", False)
    )
    if _running:
        return

    # Compute staleness. Try session timestamp first, then DB.
    _ts = st.session_state.get("scan_timestamp")
    _ts_dt: datetime | None = None
    if _ts is not None:
        if isinstance(_ts, datetime):
            _ts_dt = _ts
        else:
            try:
                _ts_dt = datetime.fromisoformat(str(_ts))
            except Exception:
                _ts_dt = None
    if _ts_dt is None:
        try:
            _db_status = _read_scan_status() or {}
            _db_ts_raw = _db_status.get("timestamp")
            if isinstance(_db_ts_raw, datetime):
                _ts_dt = _db_ts_raw
            elif _db_ts_raw:
                try:
                    _ts_dt = datetime.fromisoformat(str(_db_ts_raw))
                except Exception:
                    _ts_dt = None
        except Exception as _e_ts:
            logger.debug("[Init] scan-timestamp DB read failed: %s", _e_ts)

    _stale = True
    if _ts_dt is not None:
        try:
            # Tolerate naive or aware timestamps — assume UTC for naive.
            _now = datetime.now(timezone.utc)
            _age_s = (_now - (_ts_dt if _ts_dt.tzinfo else _ts_dt.replace(tzinfo=timezone.utc))).total_seconds()
            _stale = _age_s > 15 * 60
        except Exception:
            _stale = True

    if _stale:
        try:
            _start_scan()
            logger.info("[Init] First-session mandatory scan started (data was stale or absent)")
        except Exception as _e_init_scan:
            logger.debug("[Init] first-session scan start failed: %s", _e_init_scan)


# Start WebSocket live price feed (idempotent — safe on every Streamlit rerun)
_ws.start(model.PAIRS)

# PERF-A7: Pre-warm OHLCV cache in background on first process start.
# Runs once per Streamlit worker process (module-level flag, not session_state).
# When user clicks "Run Scan", all 116 pair×TF OHLCV calls hit the warm cache
# instead of making live API requests — saves ~12-15s on the first scan.
if not globals().get("_OHLCV_PREWARM_STARTED"):
    globals()["_OHLCV_PREWARM_STARTED"] = True
    def _ohlcv_prewarm():
        try:
            _pw_ex = model.get_exchange_instance(model.TA_EXCHANGE)
            if not _pw_ex:
                return
            for _pw_pair in model.PAIRS:
                for _pw_tf in model.TIMEFRAMES:
                    try:
                        model.robust_fetch_ohlcv(
                            _pw_ex, _pw_pair, _pw_tf,
                            limit=model._TF_OHLCV_LIMIT.get(_pw_tf, model.SCAN_OHLCV_LIMIT),
                        )
                    except Exception as _pw_pair_err:
                        logging.debug("[Prewarm] %s/%s fetch failed: %s", _pw_pair, _pw_tf, _pw_pair_err)
        except Exception as _pw_err:
            logging.debug("[Prewarm] OHLCV prewarm thread failed: %s", _pw_err)
    threading.Thread(target=_ohlcv_prewarm, daemon=True, name="ohlcv-prewarm").start()

# Auto-start autonomous agent if enabled in config (idempotent)
# P0-19 follow-up — route through agent.ensure_supervisor_running() instead
# of supervisor.start() directly. The helper is exception-safe and returns
# bool, so a transient init failure no longer takes down the whole app
# startup path; we just log + carry on.
if _agent is not None:
    _agent_cfg_boot = _cached_alerts_config()
    if _agent_cfg_boot.get("agent_enabled", False):
        if not _agent.ensure_supervisor_running():
            logger.warning("[App] agent.ensure_supervisor_running returned False at startup")

# ──────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ──────────────────────────────────────────────
# 2026-05 redesign: render the new sibling-family brand block at the top of
# the sidebar. Matches shared-docs/design-mockups/sibling-family-crypto-signal.html.
# The legacy sidebar_header is kept below as a diagnostic block (version +
# exchange + pair count) inside a collapsed expander for advanced users.
try:
    from ui.design_system import ACCENTS as _DS_ACCENTS
    _ds_accent = _DS_ACCENTS["crypto-signal-app"]
    # Mockup brand block — wordmark only. Version / exchange / pair-count
    # diagnostic line was removed in 2026-04-25 redesign; that info is
    # available in Settings → Dev Tools when needed.
    st.sidebar.markdown(
        f'<div class="ds-rail-brand">'
        f'<div class="ds-brand-dot" style="background:{_ds_accent["accent"]};color:{_ds_accent["accent_ink"]};">◈</div>'
        f'<div class="ds-brand-wm">Signal<span style="color:var(--text-muted);">.app</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
except Exception as _ds_brand_err:
    logger.debug("[App] design-system brand block failed, falling back: %s", _ds_brand_err)
    _ui.sidebar_header(model.VERSION, model.TA_EXCHANGE, len(model.PAIRS))

# ── Module-level status flags (consumed by topbar status pills) ──────────────
# These used to render as full-width banners in the sidebar; now they fold into
# small pills next to the breadcrumb in render_top_bar (see _topbar_pills below).
try:
    _exec_mode_cfg = _cached_alerts_config()
    _is_live_mode  = _exec_mode_cfg.get("live_trading_enabled", False)
except Exception as _mode_badge_err:
    logger.debug("[App] paper/live mode flag read failed: %s", _mode_badge_err)
    _is_live_mode = False

try:
    from config import ANTHROPIC_ENABLED as _sg_ai_enabled, ANTHROPIC_API_KEY as _sg_ai_key
    _sg_ai_key_present = bool(_sg_ai_key)
except Exception as _ai_flag_err:
    logger.debug("[App] AI status flag read failed: %s", _ai_flag_err)
    _sg_ai_enabled, _sg_ai_key_present = False, False

def _topbar_pills() -> list[dict]:
    """Compact status pills for the topbar — Paper/Live + Claude AI status.

    Returns a list of {label, icon, tone} dicts. tone ∈ {info, success,
    warning, danger, muted}. render_top_bar maps tone → CSS class.
    """
    pills: list[dict] = []
    if _is_live_mode:
        pills.append({"label": "Live", "icon": "🔴", "tone": "danger"})
    else:
        pills.append({"label": "Paper", "icon": "📄", "tone": "info"})
    if _sg_ai_enabled and _sg_ai_key_present:
        pills.append({"label": "Claude", "icon": "✅", "tone": "success"})
    elif _sg_ai_enabled and not _sg_ai_key_present:
        pills.append({"label": "Claude", "icon": "🔴", "tone": "danger"})
    else:
        pills.append({"label": "Claude", "icon": "⚫", "tone": "muted"})
    if st.session_state.get("demo_mode"):
        pills.append({"label": "Demo", "icon": "⚠️", "tone": "warning"})
    return pills


# ── Compact live scan-progress (sidebar) ────────────────────────────────────
# Mirrors the DeFi / RWA pattern: a slim progress block that renders near the
# top of the sidebar only while a scan is active. The full rich treatment
# (SVG ring + partial results + fun facts) lives further down the main
# dashboard in _scan_progress; this is the "something is happening" signal
# that's always in view no matter where the user is on the page.
@st.fragment(run_every=2)
def _sg_sidebar_progress():
    # Authoritative scan-state lives in the in-memory _SCAN_STATUS +
    # _scan_state dicts (the scan thread writes both at start, end, and
    # error). st.session_state["scan_running"] is a session-scoped CACHE
    # that the UI button reads — it MUST track the in-memory flag.
    _thread_running = (
        _SCAN_STATUS.get("running", False)
        or _scan_state.get("running", False)
    )
    _session_thinks_running = st.session_state.get("scan_running", False)

    # C-fix-08 (2026-05-02): completion writeback. The scan thread sets
    # _SCAN_STATUS / _scan_state running=False on completion + error
    # (lines 2624-2625), but nothing was clearing st.session_state
    # ["scan_running"] — the dead `_scan_progress()` fragment used to
    # do it on line 1891 but is never invoked. Result: the Home page
    # "Analyzing…" button label and any other code reading scan_running
    # via session_state stayed stuck on True forever after the first
    # scan completed. Detect the desync here and clean it up — runs
    # every 2s so completion clears within 2s of the thread exit.
    if _session_thinks_running and not _thread_running:
        st.session_state["scan_running"] = False
        # Persist the latest results into session_state so consumers
        # don't have to re-read SQLite. Use the same writeback shape
        # as the dead _scan_progress fragment did.
        try:
            _final_st = _read_scan_status() or {}
            _cached = _read_scan_results()
            if _cached is not None:
                st.session_state["scan_results"] = _cached
                st.session_state["scan_error"]     = _final_st.get("error")
                st.session_state["scan_timestamp"] = _final_st.get("timestamp")
        except Exception as _wb_err:
            logger.debug("[App] scan-completion writeback failed: %s", _wb_err)
        # Trigger a full-page rerun so the Home button label reverts to
        # "🔍 Run a fresh scan now" and watchlist / hero cards re-read
        # the fresh scan_results from session_state. scope="app" because
        # this runs inside @st.fragment — the default scope="fragment"
        # would only re-render this sidebar block, leaving the stale
        # button label in the main column.
        try:
            st.rerun(scope="app")
        except TypeError:
            # Streamlit < 1.36 doesn't accept the scope kwarg; fall back
            # to the bare rerun (still triggers the rerun, may need a
            # second tick to propagate fully).
            st.rerun()
        return  # rerun aborts current pass; defensive

    _running = _thread_running or _session_thinks_running
    if not _running:
        return
    _prog = (
        _scan_state.get("progress")
        or _SCAN_STATUS.get("progress", 0)
    )
    try:
        _prog = int(_prog)
    except (TypeError, ValueError):
        _prog = 0
    _pair = (
        _scan_state.get("progress_pair")
        or _SCAN_STATUS.get("current", "")
        or "Working…"
    )
    _total = 0
    try:
        import crypto_model_core as _model
        _total = len(getattr(_model, "PAIRS", []) or [])
    except Exception:
        _total = 0
    _pct = 0
    if _total > 0:
        _pct = min(100, int(round(100.0 * _prog / _total)))
    _eta_str = ""
    _start_ts = _SCAN_STATUS.get("start_time")
    if _start_ts and _prog > 0 and _total > 0:
        _elapsed = time.time() - float(_start_ts)
        _rate = _prog / max(_elapsed, 0.1)
        _remaining = max(0.0, (_total - _prog) / _rate)
        if _remaining > 60:
            _eta_str = f"~{int(_remaining // 60)}m {int(_remaining % 60)}s left"
        elif _remaining > 3:
            _eta_str = f"~{int(_remaining)}s left"
        else:
            _eta_str = "almost done…"
    _pair_escaped = _html.escape(str(_pair))
    _eta_escaped = _html.escape(_eta_str)
    # IMPORTANT (fixed 2026-04-20): must use st.markdown here (NOT
    # st.sidebar.markdown). Streamlit raises StreamlitAPIException when a
    # @st.fragment calls st.sidebar.* directly — the prescribed pattern is
    # to wrap the fragment *call* in a `with st.sidebar:` context (done
    # below) and have the fragment body emit to the current container.
    st.markdown(
        f"""
<div style="margin:8px 0 12px 0; padding:10px 12px; border-radius:8px;
            border:1px solid rgba(0,212,170,0.25);
            background:rgba(0,212,170,0.06);">
  <div style="display:flex;align-items:center;justify-content:space-between;
              gap:8px;font-size:0.72rem;color:rgba(168,180,200,0.65);font-weight:600;
              letter-spacing:0.3px;text-transform:uppercase;margin-bottom:6px;">
    <span>⏳ SCANNING</span><span>{_prog}/{_total}</span>
  </div>
  <div style="font-size:0.78rem;color:#00d4aa;font-weight:700;line-height:1.25;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
    {_pair_escaped}
  </div>
  <div style="margin-top:6px;height:6px;background:rgba(100,116,139,0.25);
              border-radius:3px;overflow:hidden;">
    <div style="height:100%;width:{_pct}%;background:#00d4aa;
                transition:width 0.4s ease-out;"></div>
  </div>
  <div style="margin-top:4px;font-size:0.68rem;color:rgba(168,180,200,0.55);
              display:flex;justify-content:space-between;">
    <span>{_pct}%</span><span>{_eta_escaped}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


try:
    # Call the fragment inside a sidebar context so its markdown output lands
    # in the sidebar (see fragment body note above).
    with st.sidebar:
        _sg_sidebar_progress()
except Exception as _sg_sp_err:
    logger.debug("[App] sidebar progress render failed: %s", _sg_sp_err)


# ── 3-Level Experience selector (Phase 1) ─────────────────────────────────────
# Beginner = default; persists across all pages via session_state.
# 2026-04-24 redesign: the visible level selector lives in the topbar (see
# render_top_bar). The sidebar radio has been removed so there's a single
# control surface. We still init the session-state default + beginner_mode
# side-effect here so first-render code paths and inject_beginner_mode_js()
# behave identically.
_LEVEL_OPTIONS = ["beginner", "intermediate", "advanced"]
if st.session_state.get("user_level") not in _LEVEL_OPTIONS:
    st.session_state["user_level"] = "beginner"
_sg_level_val = st.session_state["user_level"]
# Backward compat: beginner_mode = True when NOT Advanced (drives inject_beginner_mode_js)
_bm_val = (_sg_level_val != "advanced")
st.session_state["beginner_mode"] = _bm_val
_ui.inject_beginner_mode_js(_bm_val)

# Demo / Sandbox mode toggle relocated to Settings → Dev Tools.
# st.session_state["demo_mode"] is the single source of truth (defaults to
# False); the topbar shows a "Demo" pill when on (see _topbar_pills above).
st.session_state.setdefault("demo_mode", False)

# Note: the Crypto Glossary popover used to live here (always-visible top-of-
# sidebar slot). It's been moved to the sidebar footer (see render_legal_footer
# below) — the topbar handles the primary controls now, and the footer group
# is the right home for reference / legal links.

# ── Theme-toggle handler (shared by topbar ☾ Theme button) ───────────────────
# 2026-04-24 redesign: the visible theme toggle now lives in the topbar.
# The sidebar render_theme_toggle_sg() call has been removed. Both keys
# ("_sg_theme" used by ui_components/Plotly templates and "theme" used by
# ui.design_system.inject_theme) are kept in sync here.
def _toggle_theme() -> None:
    cur = st.session_state.get("_sg_theme", "dark")
    new = "light" if cur != "light" else "dark"
    st.session_state["_sg_theme"] = new
    st.session_state["theme"]     = new
    # Reset CSS injection guard so inject_css() re-fires on next rerun.
    st.session_state["_css_injected"] = False
    # Flip the Plotly default template so every chart created on the next
    # rerun picks up the new theme automatically.
    try:
        from ui import register_plotly_template as _ds_reset_plotly
        _ds_reset_plotly(theme=new)
    except Exception as _e_plt:
        logger.debug("[App] Plotly template re-register failed: %s", _e_plt)

# ── Refresh-All-Data handler (shared by topbar ↻ Refresh button) ─────────────
# C5 (Phase C plan §C5.5, 2026-04-30): agent status pill — visible in
# the topbar's status_pills slot on every page that wants it. Lets a
# user tell at a glance whether the autonomous agent is running, even
# when they're not on the AI Assistant page. Returns a list shaped
# for render_top_bar's `status_pills` parameter (each pill: dict with
# `tone`, `icon`, `label`).
def _render_alerts_configure() -> None:
    """C6 (Phase C plan §C6, 2026-04-30): Email-alerts configuration
    block — was nested inside `page_config` as `_render_alerts_tab`,
    lifted here so the new `page_alerts()` route can reuse it without
    importing through page_config. Body kept identical to the legacy
    nested helper so behaviour matches one-for-one."""
    _at_cfg = _cached_alerts_config()

    with st.expander("📧 Email Alerts",
                     expanded=_at_cfg.get("email_enabled", False)):
        _at_em = _at_cfg.copy()
        em_on = st.toggle(
            "Enable Email",
            value=_at_em.get("email_enabled", False),
            key="cfg_em_on_v2",
        )
        em_to = st.text_input(
            "Recipient",
            value=_at_em.get("email_to", ""),
            placeholder="you@example.com",
            key="cfg_em_to_v2",
            disabled=not em_on,
        )
        em_from = st.text_input(
            "Sender (Gmail)",
            value=_at_em.get("email_from", ""),
            placeholder="yourbot@gmail.com",
            key="cfg_em_from_v2",
            disabled=not em_on,
        )
        # Audit R2f: never pre-fill a password into text_input — DOM
        # leak every rerun. Blank on load; empty submit = keep stored.
        _em_pass_has_value = bool(_at_em.get("email_pass"))
        em_pass = st.text_input(
            "App Password",
            value="",
            type="password",
            key="cfg_em_pass_v2",
            disabled=not em_on,
            placeholder="●●●● (saved)" if _em_pass_has_value else "",
            help="Leave blank to keep the stored app password.",
        )
        em_min = st.slider(
            "Alert threshold (%)",
            50, 95,
            int(_at_em.get("email_min_confidence", 70)),
            step=5,
            key="cfg_em_thresh_v2",
            disabled=not em_on,
        )
        cse, cte = st.columns(2)
        with cse:
            if st.button("Save Email", key="cfg_em_save_v2",
                         width="stretch"):
                _new_em_pass = em_pass if em_pass else _at_em.get("email_pass", "")
                _at_em.update({
                    "email_enabled": em_on,
                    "email_to": em_to.strip(),
                    "email_from": em_from.strip(),
                    "email_pass": _new_em_pass,
                    "email_min_confidence": em_min,
                })
                _save_alerts_config_and_clear(_at_em)
                st.success("Saved!")
        with cte:
            if st.button("Test", key="cfg_em_test_v2",
                         width="stretch", disabled=not em_on):
                _test_em_pass = em_pass if em_pass else _at_em.get("email_pass", "")
                ok, err = _alerts.send_email_alert(
                    em_from.strip(), _test_em_pass, em_to.strip(),
                    "Crypto Signal Model — Test Alert",
                    "✓ Email alert test successful.",
                )
                if ok:
                    st.success("Email sent!")
                else:
                    st.error(err or "Test failed — check your Gmail "
                             "App Password and email settings.")
        st.caption(
            "Use a Gmail App Password (Settings → Security → 2FA → "
            "App passwords)"
        )


def _agent_topbar_pills() -> list[dict]:
    """Return the topbar-pill list reflecting the autonomous agent's
    runtime state. Empty list when agent.py couldn't import or the
    supervisor's status raises (defensive — the topbar must NEVER
    crash a page on a transient agent backend hiccup)."""
    if _agent is None:
        return []
    try:
        s = _agent.supervisor.status() or {}
    except Exception as _e:
        logger.debug("[topbar] agent status() failed: %s", _e)
        return []
    if s.get("running"):
        return [{
            "tone":  "success",
            "icon":  "●",
            "label": f"Agent · running · cycle {int(s.get('cycles_total') or 0)}",
        }]
    if s.get("kill_requested"):
        return [{"tone": "warning", "icon": "■", "label": "Agent · stopping"}]
    return [{"tone": "info", "icon": "○", "label": "Agent · stopped"}]


# 2026-04-24 redesign: the visible refresh trigger now lives in the topbar
# (see render_top_bar). The sidebar "Refresh All Data" button has been
# removed so the topbar ↻ chip is the single control surface. Both the
# topbar button and any future programmatic call invoke this handler.
def _refresh_all_data() -> None:
    """Single unified update action: clear ALL caches AND run a fresh
    full scan. Used by the topbar "↻ Update" button on every page,
    every user level. Caller is responsible for st.rerun() if needed
    (Streamlit auto-reruns on the click frame).

    C-fix-10 (2026-05-02): unified across all levels. The previous
    C8-fix implementation gated the auto-scan on
    `user_level == "beginner"` so Intermediate/Advanced users had to
    distinguish "↻ Refresh" (cache clear) from "▶ Run Scan" (recompute
    signals) — a power-user distinction that David explicitly rejected
    ("i really just want A single button that does a full scan and
    updates the entire UI/UX regardless of the level expertize").
    Now every click of ↻ Update at every level: clears all caches
    AND kicks off a scan. The level label on the button is unified to
    "↻ Update" everywhere (was "↻ Update" for beginners, "↻ Refresh"
    for int/adv).

    Re-entry guard: if a scan is already running, no second start
    (the cache-clear still happens — the user pressed it for a
    reason — but we don't queue a second scan thread).
    """
    try:
        st.cache_data.clear()
    except Exception:
        for _fn in [
            _cached_signals_df, _cached_paper_trades_df, _cached_feedback_df,
            _cached_backtest_df, _cached_scan_results, _cached_execution_log_df,
            _cached_agent_log_df, _cached_api_health, _cached_arb_opportunities_df,
            _cached_resolved_feedback_df, _cached_alerts_config, _cached_news_sentiment,
            _cached_whale_activity, _cached_google_trends_score,
            _sg_cached_composite_per_pair,
        ]:
            try:
                _fn.clear()
            except Exception as _fc_err:
                logger.debug("[App] cache clear failed for %s: %s", _fn, _fc_err)
    # Module-level cache dicts in data_feeds aren't covered by st.cache_data.clear()
    try:
        data_feeds.clear_all_module_caches()
    except Exception as _df_clr_err:
        logger.debug("[App] data_feeds module cache clear failed: %s", _df_clr_err)
    try:
        from cycle_indicators import clear_cycle_caches as _ccc
        _ccc()
    except Exception as _ci_clr_err:
        logger.debug("[App] cycle_indicators cache clear failed: %s", _ci_clr_err)

    # C-fix-10 (2026-05-02): always kick off a scan after the cache
    # clear, regardless of user level. The Update button is a unified
    # "make everything fresh" action across Beginner / Intermediate /
    # Advanced. Re-entry guard: no second scan if one is already
    # running.
    try:
        _already_scanning = (
            _SCAN_STATUS.get("running", False)
            or _scan_state.get("running", False)
        )
        if not _already_scanning:
            _start_scan()
    except Exception as _e_auto_scan:
        logger.debug("[App] auto-scan after refresh failed: %s", _e_auto_scan)

st.sidebar.markdown("---")

# ── 2026-05 redesign: grouped sidebar nav (Markets / Research / Account) ─────
# Matches shared-docs/design-mockups/sibling-family-crypto-signal.html rail.
# Each mockup nav item maps to an existing page_* function — preserves all
# existing app logic, only relabels + regroups.
#
# Same nav for every user level — the level controls main-column content
# density, not which pages exist. Home / Signals / Regimes / On-chain all
# resolve to the Dashboard page (different sections of it). Alerts opens
# Config Editor pre-pivoted to its Alerts tab via _ds_nav_after_select.
# AI Agent and Arbitrage are kept reachable since they're real pages even
# though the static mockup doesn't list them.
_DS_NAV: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Markets", [
        ("home",     "Home",       "Dashboard"),
        ("signals",  "Signals",    "Signals"),
        ("regimes",  "Regimes",    "Regimes"),
    ]),
    ("Research", [
        ("backtester", "Backtester", "Backtest Viewer"),
        ("onchain",    "On-chain",   "On-chain"),
    ]),
    ("Account", [
        # C6 (2026-04-30): Alerts is now a first-class page — was
        # previously routed to Config Editor → Alerts tab.
        ("alerts",       "Alerts",       "Alerts"),
        # C1 reconcile (2026-04-29): nav key is `ai_assistant` per Phase C
        # plan §C1 (not `agent` — that name is reserved for the
        # autonomous-agent runtime namespace). Page-router target stays
        # "Agent" since page_agent() is the existing entry point.
        ("ai_assistant", "AI Assistant", "Agent"),
        ("settings",     "Settings",     "Config Editor"),
        # C4 (2026-04-29): "Arbitrage" was promoted into a primary
        # segmented control on the Backtester page. The standalone nav
        # entry is removed so users land on Arbitrage via Backtester →
        # Arbitrage segment. The legacy `page == "Arbitrage"` route is
        # kept alive in the dispatcher (page_arbitrage stub sets
        # bt_view=arbitrage and renders Backtester) so any inbound
        # deep links / programmatic jumps still work.
    ]),
]
_ds_nav_current = _DS_NAV

# Flatten for the hidden radio fallback (preserves keyboard nav + Streamlit
# state consistency). We render the visible buttons separately.
_ds_nav_flat_labels = []
_ds_nav_label_to_page = {}
for _grp_name, _grp_items in _ds_nav_current:
    for _k, _lbl, _page_key in _grp_items:
        _ds_nav_flat_labels.append(_lbl)
        _ds_nav_label_to_page[_lbl] = _page_key

# Render the grouped nav — styled headers + st.sidebar.button per item.
# The overrides.css file styles these to look like the mockup.
_ds_current_label = st.session_state.get("_ds_current_nav_label", _ds_nav_flat_labels[0] if _ds_nav_flat_labels else "")
if _ds_current_label not in _ds_nav_flat_labels:
    _ds_current_label = _ds_nav_flat_labels[0] if _ds_nav_flat_labels else ""
    st.session_state["_ds_current_nav_label"] = _ds_current_label

# C-fix-03 (2026-05-01): nav buttons use the on_click=callback pattern
# instead of the legacy `if st.sidebar.button(...): write_state()` shape.
#
# Why this matters: with the legacy pattern, the buttons render with
# `type=("primary" if _is_active else "secondary")` based on the
# pre-click `_ds_current_nav_label`. The click is processed AFTER the
# buttons have already emitted their type, so the highlight reflects
# OLD state for one render. Two clicks were required to see the
# highlight catch up — the exact two-render lag H5 fixed in the
# (unused) ui.sidebar.render_sidebar function. app.py's inlined nav
# never received the same fix and continued to exhibit the bug.
#
# Streamlit invokes on_click callbacks BEFORE the script body re-runs,
# so by the time the buttons render this turn, `_ds_current_nav_label`
# is already the new value and the active highlight tracks correctly
# on the first click.
def _ds_select_nav(label: str, key: str) -> None:
    st.session_state["_ds_current_nav_label"] = label
    st.session_state["_ds_current_nav_key"] = key

for _grp_name, _grp_items in _ds_nav_current:
    # Section header — visual styling lives entirely in ui/overrides.py
    # under .ds-nav-group-header. Keeping inline style here would beat the
    # class rule and revert the section headers to tiny/muted.
    st.sidebar.markdown(
        f'<div class="ds-nav-group-header">{_grp_name}</div>',
        unsafe_allow_html=True,
    )
    for _k, _lbl, _page_key in _grp_items:
        _is_active = (_lbl == _ds_current_label)
        st.sidebar.button(
            _lbl,
            key=f"ds_nav_btn_{_k}",
            use_container_width=True,
            type=("primary" if _is_active else "secondary"),
            on_click=_ds_select_nav,
            args=(_lbl, _k),
        )

# Re-read after callbacks have fired (they ran before this body re-rendered,
# but `_ds_current_label` was captured above before the buttons rendered).
_ds_current_label = st.session_state.get("_ds_current_nav_label", _ds_current_label)

page = _ds_nav_label_to_page.get(_ds_current_label, "Dashboard")

# Programmatic navigation override (e.g. "Configure Alerts" button sets _nav_target)
_nav_override = st.session_state.pop("_nav_target", None)
if _nav_override:
    page = _nav_override

# Backwards compat: keep the legacy radio mapping available for any code that
# still reads page via the old label strings.
_PAGE_MAP = {
    "📊 My Signals":    "Dashboard",
    "📊 Dashboard":     "Dashboard",
    "⚙️ Settings":      "Config Editor",
    "📈 Performance":   "Backtest Viewer",
    "📈 Performance History": "Backtest Viewer",
    "📈 Backtest Viewer":     "Backtest Viewer",
    "⚡ Opportunities": "Arbitrage",
    "⚡ Arbitrage":     "Arbitrage",
    "🤖 AI Assistant":  "Agent",
    "🤖 AI Agent":      "Agent",
}

# ──────────────────────────────────────────────
# RELOCATED LEGACY SIDEBAR WIDGETS
# ──────────────────────────────────────────────
# 2026-04-25 redesign: the sidebar now matches the mockup (brand → Markets /
# Research / Account → footer). The legacy widgets that lived under the nav
# (Auto-Scan, Email Alerts toggle, API Health, Wallet Import, API Keys, plus
# the Demo / Sandbox toggle removed above) are exposed inside Settings →
# Dev Tools via _render_relocated_sidebar_widgets() instead.
def _render_relocated_sidebar_widgets() -> None:
    """Render the legacy sidebar widgets in the main column.

    Called from page_config()'s Dev Tools tab. Each widget keeps the same
    session-state key as before so the saved settings survived the move.
    Email Alerts toggle is dropped entirely — Settings → Alerts has the
    full email config and the sidebar quick-toggle was a duplicate.
    """
    _legacy_alerts_cfg = _cached_alerts_config()

    with st.expander("⏰ Auto-Scan", expanded=False):
        _alert_cfg = _legacy_alerts_cfg.copy()
        autoscan_on = st.toggle(
            "Enable Auto-Scan",
            # C-fix-12 (2026-05-02): default True to match CLAUDE.md §12
            # spec ("Full scan / recalc — 15 min auto").
            value=_alert_cfg.get("autoscan_enabled", True),
            key="autoscan_toggle",
        )
        interval_options = {
            "15 minutes": 15, "30 minutes": 30, "1 hour": 60,
            "2 hours": 120, "4 hours": 240, "8 hours": 480, "24 hours": 1440,
        }
        interval_label = st.selectbox(
            "Scan Interval",
            options=list(interval_options.keys()),
            index=list(interval_options.values()).index(
                min(interval_options.values(),
                    # C-fix-12: default 15 min per §12 (was 60).
                    key=lambda v: abs(v - _alert_cfg.get("autoscan_interval_minutes", 15)))
            ),
            key="autoscan_interval",
            disabled=not autoscan_on,
        )
        interval_min = interval_options[interval_label]

        quiet_on = st.toggle(
            "Quiet Hours (UTC)",
            value=_alert_cfg.get("autoscan_quiet_hours_enabled", False),
            key="autoscan_quiet_on",
            disabled=not autoscan_on,
            help="Skip scheduled scans during these hours (times are UTC).",
        )
        _qc1, _qc2 = st.columns(2)
        with _qc1:
            quiet_start = st.text_input(
                "Start HH:MM", value=_alert_cfg.get("autoscan_quiet_start", "22:00"),
                key="autoscan_quiet_start", disabled=not (autoscan_on and quiet_on),
            )
        with _qc2:
            quiet_end = st.text_input(
                "End HH:MM", value=_alert_cfg.get("autoscan_quiet_end", "06:00"),
                key="autoscan_quiet_end", disabled=not (autoscan_on and quiet_on),
            )

        if autoscan_on:
            _job_exists = bool(_get_scheduler().get_job(_AUTOSCAN_JOB_ID))
            _interval_changed = interval_min != _alert_cfg.get("autoscan_interval_minutes")
            if not _job_exists or _interval_changed:
                _setup_autoscan(interval_min)
            next_t = _get_next_autoscan_time()
            if next_t:
                try:
                    if next_t.tzinfo is None:
                        next_t = next_t.replace(tzinfo=timezone.utc)
                    delta = next_t - datetime.now(timezone.utc)
                except Exception:
                    delta = timedelta(0)
                total_secs = max(0.0, delta.total_seconds())
                mins_left = int(total_secs // 60)
                secs_left = int(total_secs % 60)
                st.caption(f"Next scan in: {mins_left}m {secs_left}s")
        else:
            _stop_autoscan()
            st.caption("Auto-scan is off.")

        if (autoscan_on  != _alert_cfg.get("autoscan_enabled")
                or interval_min != _alert_cfg.get("autoscan_interval_minutes")
                or quiet_on      != _alert_cfg.get("autoscan_quiet_hours_enabled")
                or quiet_start   != _alert_cfg.get("autoscan_quiet_start")
                or quiet_end     != _alert_cfg.get("autoscan_quiet_end")):
            _alert_cfg["autoscan_enabled"]             = autoscan_on
            _alert_cfg["autoscan_interval_minutes"]    = interval_min
            _alert_cfg["autoscan_quiet_hours_enabled"] = quiet_on
            _alert_cfg["autoscan_quiet_start"]         = quiet_start.strip()
            _alert_cfg["autoscan_quiet_end"]           = quiet_end.strip()
            _save_alerts_config_and_clear(_alert_cfg)

    with st.expander("🎭 Demo / Sandbox mode", expanded=False):
        _demo_val = st.toggle(
            "Demo / Sandbox",
            value=st.session_state.get("demo_mode", False),
            key="demo_mode_toggle",
            help="Demo mode: shows synthetic placeholder data — no real API calls. "
                 "Safe for screenshots and onboarding.",
        )
        st.session_state["demo_mode"] = _demo_val
        if _demo_val:
            st.caption("⚠️ DEMO MODE — synthetic data, no live calls.")

    with st.expander("🔌 API Health", expanded=False):
        _api_health = _cached_api_health()
        _health_rows = []
        for _svc, _status in _api_health.items():
            _dot = "🟢" if _status in ("ok", "configured") else "🟠" if _status.startswith("HTTP") else "🔴"
            _health_rows.append(f"{_dot} **{_svc.capitalize()}** — {_status}")
        st.markdown("\n\n".join(_health_rows) if _health_rows else "No results")
        if st.button("Recheck", key="api_health_recheck", width="stretch"):
            _cached_api_health.clear()
            st.rerun()

    with st.expander("🔗 Wallet Import (Beta)", expanded=False):
        _wallet_addr = st.text_input(
            "EVM Wallet Address",
            placeholder="0x...",
            key="wallet_address",
            help="Read-only portfolio import. We never request signing or private keys.",
        )
        if _wallet_addr and len(_wallet_addr) == 42 and _wallet_addr.startswith("0x"):
            st.caption("✓ Valid Ethereum address")
            if st.button("Import Positions", key="btn_import_wallet"):
                with st.spinner("Fetching wallet holdings..."):
                    try:
                        _wallet_data = data_feeds.fetch_wallet_holdings(_wallet_addr)
                        if _wallet_data:
                            st.session_state["wallet_holdings"] = _wallet_data
                            st.success(f"Imported {len(_wallet_data.get('tokens', []))} positions")
                        else:
                            st.warning("No holdings found or fetch failed.")
                    except Exception as _we:
                        logger.warning("[Wallet] import error: %s", _we)
                        st.error("Could not import wallet data — check the address is valid and try again.")
            if st.button("Full Portfolio (Zerion)", key="btn_zerion_portfolio"):
                with st.spinner("Fetching full portfolio..."):
                    try:
                        _zerion_data = data_feeds.fetch_zerion_portfolio(_wallet_addr)
                        if _zerion_data:
                            st.session_state["zerion_portfolio"] = _zerion_data
                            st.success(f"Loaded portfolio: ${_zerion_data.get('total_value_usd', 0):,.2f}")
                        else:
                            st.warning("No portfolio data found.")
                    except Exception as _ze:
                        logger.warning("[Zerion] fetch error: %s", _ze)
                        st.error("Portfolio data temporarily unavailable — try again in a moment.")
        elif _wallet_addr:
            st.error("Invalid Ethereum address format")

    with st.expander("🔑 API Keys (Session Only)", expanded=False):
        st.caption("Keys stored in session only — never saved to disk.")
        _user_cg = st.text_input("CoinGecko Pro Key", type="password", key="user_cg_key")
        _user_ant = st.text_input("Anthropic Key (override)", type="password", key="user_anthropic_key")
        if st.button("Apply", key="btn_apply_user_keys"):
            if _user_cg:
                st.session_state["runtime_coingecko_key"] = _user_cg
            if _user_ant:
                st.session_state["runtime_anthropic_key"] = _user_ant
            st.success("Applied for this session")

    with st.expander("🛠️ Build Info", expanded=False):
        st.caption(f"v{model.VERSION} · {str(model.TA_EXCHANGE).upper()} · {len(model.PAIRS)} pairs")

    # Open-item #4 (2026-04-30): legacy 5-tab Dashboard view toggle
    # removed. The legacy tab body was deleted in C10 — leaving the
    # toggle behind would just be an inert switch that did nothing.
    # The animated price-ticker toggle stays since that block still
    # has implementation behind it.
    with st.expander("🧪 Legacy views (advanced)", expanded=False):
        st.caption(
            "The 2026-05 redesign moved per-coin detail, regime detail, and "
            "backtest detail to dedicated pages (Signals / Regimes / Backtester). "
            "The legacy 5-tab Dashboard view was retired in Phase C; the "
            "animated price-ticker strip below is the only remaining toggle."
        )
        _legacy_ticker_on = st.toggle(
            "Show animated price-ticker strip on Home",
            value=st.session_state.get("show_legacy_price_ticker", False),
            key="show_legacy_price_ticker_toggle",
        )
        st.session_state["show_legacy_price_ticker"] = _legacy_ticker_on


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def direction_color(d):
    if "STRONG BUY" in d: return "🟢"
    if "BUY" in d: return "🟩"
    if "STRONG SELL" in d: return "🔴"
    if "SELL" in d: return "🟥"
    return "🟡"

def conf_color(c):
    if c is None: return "red"
    try:
        c = float(c)
    except (TypeError, ValueError):
        return "red"
    if c >= model.HIGH_CONF_THRESHOLD: return "green"
    if c >= 55: return "orange"
    return "red"

def conf_badge(c):
    if c is None:
        return "🔴 N/A"
    try:
        c = float(c)
    except (TypeError, ValueError):
        return "🔴 N/A"
    col = "🟢" if c >= model.HIGH_CONF_THRESHOLD else "🟡" if c >= 55 else "🔴"
    return f"{col} {c:.0f}%"


def _freshness_badge(cache_key: str, ttl_seconds: int, label: str = "") -> str:
    """
    F6 — Return HTML freshness badge for a data panel.
    Green = fresh (<50% TTL), Amber = aging (50-90%), Red = stale (>90% or never).
    """
    age = data_feeds.get_cache_age_seconds(cache_key)
    if age is None:
        color, text = "#6B7280", "No data yet"
    else:
        age_min = int(age // 60)
        age_str = (
            "< 1 min ago" if age_min < 1 else
            "1 min ago"   if age_min == 1 else
            f"{age_min} min ago" if age_min < 60 else
            f"{age_min // 60}h {age_min % 60}m ago"
        )
        ratio = age / max(ttl_seconds, 1)
        color = "#22c55e" if ratio < 0.5 else "#f59e0b" if ratio < 0.9 else "#ef4444"
        text  = age_str

    prefix = f"{label} · " if label else ""
    return (
        f'<span style="font-size:11px;color:{color};font-family:monospace;'
        f'background:rgba(0,0,0,0.15);border-radius:4px;padding:1px 6px;">'
        f'⏱ {prefix}{text}</span>'
    )


def _csv_button(df: "pd.DataFrame", filename: str, label: str = "⬇ Export CSV",
                key: str | None = None) -> None:
    """F5 — Render a CSV download button for *df*. No-op if df is empty."""
    if df is None or df.empty:
        return
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=label,
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
        key=key or f"csv_{filename}_{id(df)}",
    )


# ──────────────────────────────────────────────
# PAGE 1: DASHBOARD
# ──────────────────────────────────────────────
@st.fragment(run_every=30)
def _ws_health_fragment():
    """
    Auto-refreshing WebSocket health status — updates every 30 seconds independently.
    Shows stale pairs and reconnect count without triggering a full page rerun.
    """
    ws_status  = _ws.get_status()
    stale      = [p for p in model.PAIRS if _ws.is_stale(p)]
    last_msg   = ws_status.get("last_message_at")
    age        = round(time.time() - last_msg, 0) if last_msg else None
    reconnects = ws_status.get("reconnects", 0)

    if stale:
        st.warning(f"⚠️ Stale feeds: {', '.join(p.split('/')[0] for p in stale)}")
    if reconnects > 0:
        st.caption(f"Reconnects: {reconnects}")
    if age is not None and age > 30:
        st.caption(f"Last tick: {age:.0f}s ago")




# ── Scan progress fragment — defined at module level so its session-state key is ──
# stable across rerenders. Defining @st.fragment inside a conditional block causes
# Streamlit's _check_serializable to throw KeyError($$ID-...-None) on the rerender
# where the condition is False, because the key was registered in the previous run.
@st.fragment(run_every=3)
def _scan_progress():
    # Early-return when not scanning — lock-free fast path avoids contention with the
    # scan thread that holds _scan_lock for long periods; _SCAN_STATUS is a plain dict
    # written atomically so reading it without a lock is safe for this boolean check.
    if (not st.session_state.get("scan_running", False)
            and not _SCAN_STATUS.get("running", False)
            and not _scan_state.get("running", False)):
        return
    # PERF-30: read from in-memory _SCAN_STATUS first (no DB round-trip per tick)
    # Only fall back to SQLite if in-memory says not running (e.g. fresh restart)
    _mem_prog = _SCAN_STATUS.get("progress", 0)
    _mem_pair = _SCAN_STATUS.get("current", "")
    _mem_run  = _SCAN_STATUS.get("running", False)
    if not _mem_run:
        _st = _read_scan_status()  # fallback to DB only when in-memory shows idle
    else:
        _st = {}
    with _scan_lock:
        _prog      = _scan_state.get("progress") or _mem_prog or _st.get("progress", 0)
        _pair      = _scan_state.get("progress_pair") or _mem_pair or _st.get("pair", "")
        _running   = _scan_state["running"]
    _total = len(model.PAIRS)

    # Engaging loading screen: SVG progress ring + rotating crypto fun facts
    _fact_idx = int(time.time() / 4) % 15
    st.markdown(
        _ui.loading_screen_html(_prog, _total, _pair, fact_index=_fact_idx),
        unsafe_allow_html=True,
    )

    # B4: ETA calculation — elapsed / done * remaining
    _n_done = _prog
    _eta_str = ""
    if _n_done > 0:
        _start_ts = _SCAN_STATUS.get("start_time")
        if _start_ts:
            _elapsed  = time.time() - _start_ts
            _rate     = _n_done / max(_elapsed, 0.1)          # pairs per second
            _remaining = max(0, (_total - _n_done) / _rate)   # seconds left
            if _remaining > 60:
                _eta_str = f" · ~{int(_remaining // 60)}m {int(_remaining % 60)}s remaining"
            elif _remaining > 3:
                _eta_str = f" · ~{int(_remaining)}s remaining"
            else:
                _eta_str = " · almost done…"

    # Simple text progress counter + PERF-A6: live partial results preview
    if _n_done > 0:
        st.markdown(
            f'<div style="font-size:12px;color:rgba(0,212,170,0.8);'
            f'font-weight:600;margin:4px 0 8px 0;">'
            f'⚡ {_n_done} of {_total} coins scanned{_eta_str}</div>',
            unsafe_allow_html=True,
        )
        # PERF-A6: Progressive scan — show top BUY signals found so far
        _partial = model.get_partial_scan_results()
        if _partial:
            _buys = sorted(
                [r for r in _partial if "BUY" in r.get("direction", "")],
                key=lambda x: x.get("confidence_avg_pct", 0), reverse=True,
            )
            if _buys:
                _rows = []
                for _pr in _buys[:5]:
                    _sym  = _pr.get("pair", "").replace("/USDT", "")
                    _dir  = _pr.get("direction", "")
                    _conf = _pr.get("confidence_avg_pct", 0)
                    _px   = _pr.get("price_usd", 0)
                    _rows.append(
                        f'<span style="color:#00d4aa;font-weight:700">{_sym}</span> '
                        f'<span style="color:#22c55e">▲ {_dir}</span> '
                        f'<span style="color:rgba(255,255,255,0.5)">{_conf:.0f}%</span>'
                        + (f' <span style="color:rgba(255,255,255,0.35);font-size:11px">${_px:,.4g}</span>' if _px else "")
                    )
                st.markdown(
                    '<div style="background:rgba(0,212,170,0.06);border:1px solid rgba(0,212,170,0.2);'
                    'border-radius:8px;padding:8px 12px;margin-bottom:8px;font-size:13px;line-height:1.9">'
                    '<span style="font-size:11px;color:rgba(0,212,170,0.6);text-transform:uppercase;'
                    'letter-spacing:0.6px;font-weight:600">Top BUY signals so far</span><br>'
                    + "<br>".join(_rows) + "</div>",
                    unsafe_allow_html=True,
                )

    # Detect completion → trigger full-page rerun to show final results
    if not _st.get("running", False) and not _running:
        cached = _read_scan_results()
        if cached is not None:
            st.session_state["scan_results"] = cached
            st.session_state["scan_error"]     = _st.get("error")
            st.session_state["scan_timestamp"] = _st.get("timestamp")
        st.session_state["scan_running"] = False
        st.rerun()  # Full page rerun — shows complete results


# ─── Legal / Compliance Copy (R3h Tier-1 ship for April 20) ────────────────────

_PAST_PERF_DISCLAIMER = (
    "Past performance does not guarantee future results. Backtest and "
    "signal confidence scores are hypothetical, assume zero-latency "
    "execution at modelled prices, and do not reflect actual trading. "
    "Real-world results may differ materially due to slippage, exchange "
    "fees, funding rates, liquidity, and market volatility. Not investment "
    "advice."
)

_LEGAL_TOS = """\
**Terms of Service — Internal Beta**

This application is an internal beta tool operated by David for evaluation
purposes. It is not a production service and is not available to the public.

- No formal Terms of Service have been established yet.
- Use is at the operator's sole discretion and risk.
- All features are subject to change without notice.
- No warranty of any kind, express or implied.

Effective: April 2026.
"""

_LEGAL_PRIVACY = """\
**Privacy Policy — Internal Beta**

This application is an internal beta tool. It does not collect personally
identifiable information beyond what the operator voluntarily configures
(OKX API keys, email settings) for the purpose of operating the tool.

- Credentials are stored locally (see `alerts_config.json` — gitignored).
  Nothing is transmitted to third parties except via explicit,
  user-configured API calls (OKX, CoinGecko, Anthropic, etc.) governed
  by those providers' own privacy policies.
- No marketing, no analytics, no tracking pixels.
- Audit logs remain on the operator's local disk.

Effective: April 2026.
"""


def render_past_performance_disclaimer(context: str = "") -> None:
    """Compact past-performance disclaimer under backtest / signal tables.
    `context` is an optional short prefix."""
    _prefix = (context + " ") if context else ""
    st.caption(f"{_prefix}{_PAST_PERF_DISCLAIMER}")


def render_legal_footer() -> None:
    """Render the sidebar footer cluster — Glossary popover + Legal stub.

    Both items are explicitly scoped to st.sidebar via the `with st.sidebar:`
    context. The previous version called _ui.glossary_popover(...) outside any
    sidebar context, so the popover dropdown rendered at the bottom of the
    main page area below the legal disclaimer instead of in the sidebar.
    Depth of glossary content scales with user_level.
    """
    with st.sidebar:
        try:
            _ui.glossary_popover(user_level=st.session_state.get("user_level", "beginner"))
        except Exception as _gloss_err:
            logger.debug("[App] sidebar glossary render failed: %s", _gloss_err)
        with st.expander("📜 Legal (Internal Beta)", expanded=False):
            st.markdown(_LEGAL_TOS)
            st.markdown("---")
            st.markdown(_LEGAL_PRIVACY)


def page_dashboard():
    # ── 2026-05 redesign: mockup-style top bar (breadcrumb + level pills) ────
    try:
        from ui import (
            render_top_bar as _ds_top_bar,
            page_header as _ds_page_header,
            macro_strip as _ds_macro_strip,
        )
        _ds_level = st.session_state.get("user_level", "beginner")
        _ds_top_bar(breadcrumb=("Markets", "Home"), user_level=_ds_level, on_refresh=_refresh_all_data, on_theme=_toggle_theme, status_pills=_agent_topbar_pills())
        _ds_page_header(
            title="Market home",
            subtitle="Composite signals + regime state across the top-cap set.",
            data_sources=[
                (str(model.TA_EXCHANGE).upper(), "live"),
                ("Glassnode", "live"),
                ("News sentiment", "cached"),
            ],
        )
        # Macro strip — mirrors the mockup's 5-col strip with real data.
        # Pulls from LIVE data-source functions directly (each already cached
        # at the data_feeds module level) — no dependency on a scan having
        # been run. Fills BTC Dom / F&G / DXY / Funding / Regime on page
        # load for every user, every visit.
        try:
            _gm = _cached_global_market() or {}
            _me = _cached_macro_enrichment() or {}

            # Direct live feeds (bypass scan-only enrichment cache)
            _fng_dict = {}
            _dxy_val = None
            _dxy_30d = None
            _funding_val = None
            try:
                # P1-25 audit fix — was uncached F&G fetch on every Dashboard
                # render. §12 says 24h cache.
                _fng_dict = _sg_cached_fear_greed()
            except Exception as _e_fng:
                logger.debug("[Dashboard] F&G live fetch failed: %s", _e_fng)
            try:
                _yf = data_feeds.fetch_yfinance_macro() or {}
                _dxy_val = _yf.get("dxy")
                _dxy_30d = _yf.get("dxy_30d_change_pct") or _yf.get("dxy_30d_ret_pct")
            except Exception as _e_yf:
                logger.debug("[Dashboard] yfinance macro fetch failed: %s", _e_yf)
            try:
                # P1-25 audit fix — funding was uncached at render time. §12: 10min.
                _fr = _sg_cached_funding_rate("BTC/USDT")
                _funding_val = _fr.get("funding_rate_pct") or _fr.get("rate_pct")
            except Exception as _e_fr:
                logger.debug("[Dashboard] funding rate fetch failed: %s", _e_fr)

            _btc_dom = _gm.get("btc_dominance_pct", _gm.get("btc_dominance"))
            _btc_dom_7d = _gm.get("btc_dominance_7d_change_pct", _gm.get("btc_dominance_7d_ppt"))

            # F&G from direct feed first, fall back to macro enrichment
            _fng = _fng_dict.get("value")
            _fng_cat = _fng_dict.get("label")
            if _fng is None:
                _fng = _me.get("fng_value")
                _fng_cat = _me.get("fng_category", _me.get("fng_classification", ""))

            # DXY fallback chain: yfinance → macro enrichment
            if _dxy_val is None:
                _dxy_val = _me.get("dxy")
            if _dxy_30d is None:
                _dxy_30d = _me.get("dxy_30d_change_pct")

            # Funding fallback chain: direct → macro enrichment
            if _funding_val is None:
                _funding_val = _me.get("btc_funding_rate_pct", _me.get("funding_btc"))

            _dxy = _dxy_val
            _funding = _funding_val
            _macro_regime = _me.get("macro_regime", _me.get("macro_regime_label", "—"))
            _macro_conf = _me.get("macro_regime_confidence_pct", _me.get("macro_confidence"))

            # Derive macro regime from raw indicators if enrichment hasn't run
            if (_macro_regime in (None, "—", "")) or _macro_conf is None:
                try:
                    _risk_score = 0
                    if _fng is not None:
                        _risk_score += 1 if int(_fng) >= 55 else (-1 if int(_fng) <= 30 else 0)
                    if _dxy_30d is not None:
                        _risk_score += 1 if float(_dxy_30d) < 0 else -1
                    if _funding is not None:
                        _risk_score += 1 if float(_funding) > 0 else -1
                    if _risk_score >= 2:
                        _macro_regime, _macro_conf = "Risk-on", 72
                    elif _risk_score <= -2:
                        _macro_regime, _macro_conf = "Risk-off", 68
                    else:
                        _macro_regime, _macro_conf = "Mixed", 55
                except Exception:
                    pass
            def _fmt_pct(v, decimals=2, prefix=True):
                if v is None:
                    return "—"
                try:
                    fv = float(v)
                    sign = "+ " if (fv > 0 and prefix) else ("− " if fv < 0 else "")
                    return f"{sign}{abs(fv):.{decimals}f}%"
                except Exception:
                    return "—"
            def _fmt_num(v, decimals=1, suffix=""):
                if v is None:
                    return "—"
                try:
                    return f"{float(v):.{decimals}f}{suffix}"
                except Exception:
                    return "—"
            # Build the macro strip rows here but DON'T render yet — the
            # mockup order is hero cards first, macro strip second. The
            # actual _ds_macro_strip(...) call happens after the hero row,
            # below.
            _ds_macro_strip_rows = [
                ("BTC Dominance", _fmt_num(_btc_dom, 1, "%"),
                 f"{_fmt_pct(_btc_dom_7d, 2)} · 7d" if _btc_dom_7d is not None else "7d"),
                ("Fear & Greed",  str(int(_fng)) if _fng is not None else "—",
                 _fng_cat or ""),
                ("DXY",           _fmt_num(_dxy, 2),
                 f"{_fmt_pct(_dxy_30d, 2)} · 30d" if _dxy_30d is not None else "30d"),
                ("Funding (BTC)", _fmt_pct(_funding, 3),
                 "8h avg"),
                ("Regime (macro)", str(_macro_regime).title(),
                 f"confidence {int(_macro_conf)}%" if _macro_conf is not None else ""),
            ]
        except Exception as _ds_strip_err:
            logger.debug("[App] macro strip prep failed: %s", _ds_strip_err)
            _ds_macro_strip_rows = None
    except Exception as _ds_tb_err:
        logger.debug("[App] top bar render failed: %s", _ds_tb_err)
        _ds_macro_strip_rows = None

    # PERF-28: read all WS prices once at the top of the render — was called 3+ times per render
    _live_prices = _ws.get_all_prices()

    # ── 2026-05 redesign: mockup-fidelity hero signal cards + regime mini-grid
    #    + watchlist + backtest preview. Pulls live WS prices for BTC/ETH/XRP
    #    plus the latest scan_results for signal/regime overlay. Matches
    #    shared-docs/design-mockups/sibling-family-crypto-signal.html.
    try:
        from ui import (
            hero_signal_cards_row as _ds_hero_row,
            watchlist_card as _ds_watchlist,
            backtest_preview_card as _ds_bt_preview,
            regime_cards_grid as _ds_regimes,
        )

        # Lazy-load recent signals from DB so the hero cards have signal +
        # regime info even on a fresh page load where no scan has been
        # triggered in the current session. _cached_signals_df is already
        # st.cache_data-wrapped (TTL controlled upstream).
        _ds_db_signals = None
        try:
            _ds_db_signals = _cached_signals_df(500)
        except Exception as _e_sig:
            logger.debug("[Dashboard] could not load signals DF for hero cards: %s", _e_sig)

        def _ds_latest_result_for_pair(target_pair: str) -> dict:
            """Return the most recent scan result for a given pair (case-insensitive, slash or dash).
            Falls back to the daily_signals DB when session state is empty."""
            norm = target_pair.upper().replace("/", "").replace("-", "")
            # 1. Current session scan results
            for r in (st.session_state.get("scan_results") or []):
                pr = str(r.get("pair") or r.get("symbol") or "").upper().replace("/", "").replace("-", "")
                if pr.startswith(norm):
                    return r
            # 2. DB fallback — most recent row for the pair
            if _ds_db_signals is not None and not _ds_db_signals.empty:
                try:
                    _df = _ds_db_signals
                    _df_pair_norm = _df["pair"].astype(str).str.upper().str.replace("/", "", regex=False).str.replace("-", "", regex=False)
                    _hits = _df[_df_pair_norm.str.startswith(norm)]
                    if not _hits.empty:
                        _row = _hits.sort_values("scan_timestamp", ascending=False).iloc[0].to_dict()
                        return _row
                except Exception as _e_db:
                    logger.debug("[Dashboard] signals DB lookup for %s failed: %s", target_pair, _e_db)
            return {}

        def _ds_signal_label(r: dict) -> str:
            d = (r.get("direction") or r.get("signal") or r.get("composite_direction") or "").upper()
            if d in ("LONG", "BUY"):
                return "BUY"
            if d in ("SHORT", "SELL"):
                return "SELL"
            return "HOLD" if r else ""

        def _ds_regime_label(r: dict) -> str:
            """Return a clean regime label for mockup display.
            Strips legacy "Regime " / "Regime: " prefixes and maps the
            scan's Trending/Ranging/Trending:Bull taxonomy into the mockup's
            Bull/Bear/Transition/Accumulation/Distribution vocabulary."""
            raw = str(r.get("regime") or r.get("regime_label") or "").strip()
            if not raw:
                return ""
            low = raw.lower()
            # Strip "Regime " / "Regime: " prefix the scan writes
            for prefix in ("regime: ", "regime:", "regime "):
                if low.startswith(prefix):
                    raw = raw[len(prefix):]
                    low = raw.lower()
                    break
            # Map internal taxonomy → mockup states (Bull / Bear / Transition / Accumulation / Distribution)
            if "bull" in low and "bear" not in low:
                return "Bull"
            if "bear" in low:
                return "Bear"
            if "accum" in low:
                return "Accumulation"
            if "dist" in low:
                return "Distribution"
            if "trans" in low or "rang" in low or "chop" in low:
                return "Transition"
            if "trend" in low:
                return "Bull"  # Generic trending → lean bull (scan default when no direction)
            return raw.title()

        def _ds_regime_conf(r: dict):
            for k in ("regime_confidence", "regime_conf_pct", "regime_confidence_pct"):
                v = r.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except Exception:
                        pass
            return None

        def _ds_build_hero(pair_key: str, display: str) -> dict:
            tick = (_live_prices or {}).get(pair_key) or {}
            price = tick.get("price") or tick.get("last") or None
            chg = tick.get("change_24h_pct") or tick.get("change_pct") or None
            r = _ds_latest_result_for_pair(pair_key)
            return {
                "ticker": display,
                "price": price,
                "change_pct": chg,
                "signal": _ds_signal_label(r) if r else None,
                "regime_label": _ds_regime_label(r),
                "regime_confidence": _ds_regime_conf(r),
            }

        # C3 §C3.4: per-card swap — each hero slot is independently
        # bound to a ticker_pill_button. Defaults to BTC/ETH/XRP for
        # backwards compat; swaps persist across reruns.
        try:
            from ui import ticker_pill_button as _ds_ticker_pill
            _hero_universe_pairs = list(model.PAIRS or [])
            _hero_slot_keys = [
                ("home_hero_slot_1", "BTC/USDT"),
                ("home_hero_slot_2", "ETH/USDT"),
                ("home_hero_slot_3", "XRP/USDT"),
            ]
            for _k, _default in _hero_slot_keys:
                if st.session_state.get(_k) not in _hero_universe_pairs:
                    st.session_state[_k] = _default
            _hero_picker_cols = st.columns(3)
            for _i, (_k, _default) in enumerate(_hero_slot_keys):
                with _hero_picker_cols[_i]:
                    _ds_ticker_pill(
                        st.session_state[_k],
                        pairs=_hero_universe_pairs,
                        key=_k,
                        label_override=f"Hero {_i+1}: {st.session_state[_k]}  ▾",
                    )
        except Exception as _hero_pick_err:
            logger.debug("[Home] hero ticker-pill row failed: %s", _hero_pick_err)
            # Fall through to the static layout below.

        _hero_pair_1 = st.session_state.get("home_hero_slot_1", "BTC/USDT")
        _hero_pair_2 = st.session_state.get("home_hero_slot_2", "ETH/USDT")
        _hero_pair_3 = st.session_state.get("home_hero_slot_3", "XRP/USDT")

        def _hero_label(p: str) -> str:
            t = p.split("/")[0].split("-")[0]
            return f"{t} / USD"

        _ds_hero_row([
            _ds_build_hero(_hero_pair_1, _hero_label(_hero_pair_1)),
            _ds_build_hero(_hero_pair_2, _hero_label(_hero_pair_2)),
            _ds_build_hero(_hero_pair_3, _hero_label(_hero_pair_3)),
        ])

        # Macro strip — rendered AFTER hero cards to match the mockup order.
        # Rows were prepped earlier inside the topbar try block.
        _ds_strip_rows = locals().get("_ds_macro_strip_rows")
        if _ds_strip_rows:
            try:
                from ui import macro_strip as _ds_macro_strip
                _ds_macro_strip(_ds_strip_rows)
            except Exception as _ds_strip_render_err:
                logger.debug("[App] macro strip render failed: %s", _ds_strip_render_err)

        # Regime mini-grid — 4-col, up to 8 assets
        try:
            _ds_regime_rows = []
            for _rp in model.PAIRS[:8]:
                _r = _ds_latest_result_for_pair(_rp)
                if _r:
                    _state = _ds_regime_label(_r) or "Transition"
                    _conf = _ds_regime_conf(_r)
                    _ds_regime_rows.append({
                        "ticker": _rp.replace("/USDT", "").replace("/USD", ""),
                        "state": _state,
                        "confidence": _conf,
                        "since": "",
                    })
            if _ds_regime_rows:
                st.markdown(
                    '<div class="ds-section-title" style="font-size:11px;color:var(--text-muted);'
                    'text-transform:uppercase;letter-spacing:0.08em;font-weight:500;'
                    'margin:8px 0 10px 2px;">Regime · per asset</div>',
                    unsafe_allow_html=True,
                )
                _ds_regimes(_ds_regime_rows, cols=4)
        except Exception as _ds_rg_err:
            logger.debug("[App] regime mini-grid render failed: %s", _ds_rg_err)

        # Two-col: watchlist + backtest preview
        try:
            # Sparkline points come from real 24×1h OHLCV closes
            # (data_feeds.fetch_sparkline_closes — OKX → Gate.io fallback,
            # cached 5 minutes per pair via the module-level _SPARKLINE_CACHE).
            # If the fetch fails the row simply omits spark_points and the
            # watchlist card renders an empty SVG — never fake data.
            def _spark_points_from_closes(closes, width: int = 80, height: int = 22):
                if not closes or len(closes) < 2:
                    return None
                lo, hi = min(closes), max(closes)
                span = hi - lo
                n = len(closes)
                pad_top, pad_bot = 2.0, 2.0
                inner = height - pad_top - pad_bot  # 18
                pts = []
                for _idx, _c in enumerate(closes):
                    _x = (_idx / (n - 1)) * width
                    if span <= 0:
                        _y_pt = pad_top + inner / 2
                    else:
                        # Invert: high price → low y (SVG y=0 is top)
                        _y_pt = pad_top + (1.0 - (_c - lo) / span) * inner
                    pts.append((round(_x, 1), round(_y_pt, 1)))
                return pts

            # C-fix-09 (2026-05-02): factor row construction so the
            # Customize popover can rebuild rows for arbitrary user-
            # selected pairs (not just the default 6-pair seed). Each
            # row carries BOTH "ticker" (display) AND "pair" (lookup
            # key) so the customize-filter dict can match correctly —
            # the previous code only wrote "ticker" and the filter
            # keyed on r.get("pair") which always returned None,
            # collapsing the dict to `{None: <last row>}` and dropping
            # every row on every customize-save.
            def _build_wl_row(_wp: str) -> dict:
                _tick = (_live_prices or {}).get(_wp) or {}
                _price = _tick.get("price") or _tick.get("last")
                _chg = _tick.get("change_24h_pct") or _tick.get("change_pct")
                try:
                    _closes = data_feeds.fetch_sparkline_closes(_wp, n=24)
                except Exception as _spark_err:
                    logger.debug("[Dashboard] sparkline fetch failed for %s: %s", _wp, _spark_err)
                    _closes = []
                _pts = _spark_points_from_closes(_closes)
                if _chg is None and _closes and len(_closes) >= 2 and _closes[0]:
                    try:
                        _chg = (_closes[-1] - _closes[0]) / _closes[0] * 100.0
                    except Exception:
                        pass
                _row = {
                    "pair": _wp,  # full "BTC/USDT" — lookup key
                    "ticker": _wp.replace("/USDT", "").replace("/USD", ""),
                    "price": _price,
                    "change_pct": _chg,
                }
                if _pts:
                    _row["spark_points"] = _pts
                return _row

            _ds_wl_rows = [_build_wl_row(_wp) for _wp in model.PAIRS[:6]]
            # Last scan timestamp
            _scan_ts_label = "not yet run"
            _ts = st.session_state.get("scan_timestamp")
            if _ts:
                try:
                    _delta = (datetime.now(timezone.utc) - _ts).total_seconds()
                    if _delta < 60:
                        _scan_ts_label = "just now"
                    elif _delta < 3600:
                        _scan_ts_label = f"{int(_delta // 60)}m ago"
                    else:
                        _scan_ts_label = f"{int(_delta // 3600)}h ago"
                except Exception:
                    _scan_ts_label = "recent"

            # Backtest KPIs — session_state first, then compute from the
            # backtest_trades DB table so the preview card fills in even
            # without a manual run triggered this session.
            _bt_sess = st.session_state.get("backtest_results") or {}
            _bt_m = (_bt_sess or {}).get("metrics") or {}
            _bt_tr = _bt_m.get("total_return")
            _bt_dd = _bt_m.get("max_drawdown")
            _bt_sh = _bt_m.get("sharpe")
            _bt_wr = _bt_m.get("win_rate")
            _bt_ntr = _bt_m.get("total_trades", 0)

            if _bt_tr is None:
                try:
                    _bt_df = _cached_backtest_df()
                    if _bt_df is not None and not _bt_df.empty:
                        _pnl = _bt_df.get("pnl_pct")
                        if _pnl is not None and len(_pnl) > 0:
                            _bt_tr = float(_pnl.sum())
                            _bt_wr = float((_pnl > 0).mean() * 100.0)
                            _bt_ntr = int(len(_pnl))
                            # Equity-curve-based max drawdown (rough)
                            _eq = (1.0 + _pnl / 100.0).cumprod()
                            _peak = _eq.cummax()
                            _bt_dd = float(((_eq - _peak) / _peak * 100.0).min())
                            # Sharpe approx — mean/std of per-trade returns
                            _std = float(_pnl.std())
                            if _std > 0:
                                _bt_sh = float(_pnl.mean() / _std)
                except Exception as _e_bt:
                    logger.debug("[Dashboard] backtest DB fallback failed: %s", _e_bt)
            def _ds_pct(v, signed=False):
                if v is None:
                    return "—"
                try:
                    fv = float(v)
                    if signed:
                        sign = "+ " if fv > 0 else ("− " if fv < 0 else "")
                        return f"{sign}{abs(fv):.1f}%"
                    return f"{fv:.1f}%"
                except Exception:
                    return "—"
            _ds_kpis = [
                ("Return", _ds_pct(_bt_tr, signed=True),
                 "cumulative across all trades" if _bt_tr is not None else "Run backtest to populate",
                 "up" if (_bt_tr is not None and float(_bt_tr) > 0) else ("down" if _bt_tr is not None and float(_bt_tr) < 0 else "")),
                ("Max drawdown", _ds_pct(_bt_dd, signed=True), "peak → trough", ""),
                ("Sharpe", f"{float(_bt_sh):.2f}" if _bt_sh is not None else "—", "per-trade basis", ""),
                ("Win rate", _ds_pct(_bt_wr), f"n={int(_bt_ntr)} trades" if _bt_ntr else "no runs yet", ""),
            ]

            _ds_col1, _ds_col2 = st.columns(2)
            with _ds_col1:
                # C3 §C3.4: watchlist customize button — opens an
                # add/remove panel, persisted to
                # st.session_state["watchlist_pairs"]. The watchlist
                # card render below uses the customised list when
                # present; otherwise falls through to the legacy top-
                # cap scan (`_ds_wl_rows`) as the default seed.
                try:
                    from ui import watchlist_customize_btn as _ds_wl_custom
                    _wl_universe_pairs = list(model.PAIRS or [])
                    _wl_default_pairs = [r.get("pair") for r in (_ds_wl_rows or [])
                                         if r.get("pair")]
                    _wl_pairs = _ds_wl_custom(
                        available=_wl_universe_pairs,
                        current=_wl_default_pairs,
                        key="watchlist_pairs",
                    )
                    # C-fix-09 (2026-05-02): when the user has a custom
                    # watchlist, REBUILD the rows from their selection
                    # rather than filtering the 6-pair seed. The seed
                    # only contains model.PAIRS[:6] (BTC/ETH/...); a
                    # user adding XRP or SOL or anything else outside
                    # those 6 had their selection silently dropped by
                    # the filter — visually identical to "nothing
                    # happened on save". Now we call _build_wl_row for
                    # every selected pair so user-added entries always
                    # render with whatever live data we can pull.
                    if _wl_pairs:
                        _ds_wl_rows = [_build_wl_row(_p) for _p in _wl_pairs]
                except Exception as _wl_custom_err:
                    logger.debug("[Home] watchlist customize failed: %s",
                                 _wl_custom_err)
                _ds_watchlist(
                    title="Watchlist · top-cap",
                    subtitle=f"scan refreshed {_scan_ts_label}",
                    rows=_ds_wl_rows,
                )
            with _ds_col2:
                _ds_bt_preview(
                    title="Composite backtest",
                    subtitle="latest run — Run Backtest to update",
                    kpis=_ds_kpis,
                )
        except Exception as _ds_wl_err:
            logger.debug("[App] watchlist/backtest preview render failed: %s", _ds_wl_err)
    except Exception as _ds_hero_err:
        logger.debug("[App] hero signal cards render failed: %s", _ds_hero_err)

    # ── 2026-05 redesign: pure-mockup Home for beginners ─────────────────
    # Beginners get exactly what the shared-docs/design-mockups/
    # sibling-family-crypto-signal.html Home shows: hero cards + macro
    # strip + regime grid + watchlist + backtest preview. Nothing else.
    # 2026-04-25: extended the gate from beginner-only to ALL levels by
    # default. The legacy 5-tab dashboard structure (Today / All Coins /
    # Coin Detail / Market Intel / Analysis) duplicates content that now
    # lives on the dedicated SIGNALS / REGIMES / BACKTESTER pages, and
    # was making Home read as cluttered for every user. Power users who
    # explicitly want the legacy view can flip
    #   st.session_state["show_legacy_scan_view"] = True
    # from Settings → Dev Tools.
    # Open-item #4 (2026-04-30): the `if not show_legacy_scan_view:`
    # guard around the scan CTA was a holdover from the C10 deletion —
    # the legacy tab body it was guarding is gone, so the conditional
    # is always true. Unwrapped here so the scan CTA renders
    # unconditionally. The session-state key is no longer read; the
    # Settings → Dev Tools toggle that wrote it is also removed.
    _ds_lvl_hide = st.session_state.get("user_level", "beginner")

    # C-fix-10 (2026-05-02): the standalone Home "🔍 Run a fresh scan
    # now" CTA is removed. The topbar "↻ Update" button (every page,
    # every level) is now the canonical scan trigger — clears caches +
    # runs full scan + updates the UI. Keeping a redundant Home-only
    # button created two divergent control surfaces that drifted (the
    # Home button skipped the cache clear, the topbar button skipped
    # the scan for non-beginners pre-fix).
    #
    # While a scan is in progress we surface a compact in-line status
    # banner so the user has feedback they can see without scrolling
    # back to the topbar — but it's NOT a button. The sidebar progress
    # fragment is the live indicator.
    with _scan_lock:
        _ds_sb_running = _scan_state["running"]
    _ds_sb_running = _ds_sb_running or _SCAN_STATUS.get("running", False)
    if _ds_sb_running:
        st.markdown(
            '<div class="ds-card" style="margin-top:8px;padding:10px 14px;'
            'display:flex;align-items:center;gap:10px;'
            'background:rgba(0,212,170,0.06);'
            'border:1px solid rgba(0,212,170,0.25);">'
            '<span style="color:#00d4aa;font-weight:600;font-size:13px;">'
            '⚡ Scanning the universe…</span>'
            '<span style="color:var(--text-muted);font-size:12px;">'
            'live progress in the sidebar — page repaints when complete</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── _LEGACY_REMOVED_C10 (2026-04-30) ─────────────────────────────────
    # The legacy 5-tab Dashboard stack (Today / All Coins / Coin Detail /
    # Market Intel / Analysis) used to live here — ~2800 lines of
    # `_dash_tab1..5 = st.tabs([...])` + 5 `with _dash_tabN:` blocks.
    # Removed per Phase C plan §C10: every unique surface is now on a
    # dedicated page (Signals / Regimes / On-chain / Backtester / AI
    # Assistant) per the redesign mockups, so the tabs were duplicating
    # navigation. The mockup-content sections above (hero cards + macro
    # strip + regime mini-grid + watchlist + backtest preview) carry the
    # entire Home surface now. The `show_legacy_scan_view` Dev-Tools
    # toggle is also obsolete — kept in session_state only as a no-op
    # for any external scripts that reference it. To recover the deleted
    # block (e.g. for archaeology), git blame this sentinel line.
def _progress_cb(done, total, pair_name):
    """Called from background thread — updates module-level dict (in-memory, no DB write per tick).
    PERF-30: only write to SQLite at scan completion; per-tick writes were O(N) DB round-trips."""
    with _scan_lock:
        _scan_state["progress"] = done
        _scan_state["progress_pair"] = pair_name
    # PERF-30: update in-memory status — fragment reads this directly
    _SCAN_STATUS["progress"] = done
    _SCAN_STATUS["current"]  = pair_name
    _SCAN_STATUS["total"]    = total
    _SCAN_STATUS["running"]  = True
    # No SQLite write here — only at completion to avoid N DB writes per scan


def _send_exit_alerts(closed: list, cfg: dict | None = None) -> None:
    """Send email alerts for each closed paper position.

    Called after model.update_positions() returns a non-empty closed list, both
    from the automated scan thread and from the manual 'Check Exits & Refresh' button.
    """
    if not closed:
        return
    if cfg is None:
        cfg = _cached_alerts_config()
    for _pos in closed:
        _pair   = _pos.get("pair", "?")
        _dir    = _pos.get("direction", "?")
        _reason = _pos.get("reason", "?")
        _pnl    = float(_pos.get("pnl_pct") or 0.0)
        _entry  = float(_pos.get("entry") or 0.0)
        _exit_p = float(_pos.get("exit") or 0.0)
        _emoji  = "✅" if _pnl >= 0 else "❌"
        _msg = (
            f"{_emoji} Position Closed — {_pair}\n"
            f"Direction: {_dir} | Reason: {_reason}\n"
            f"Entry: {_entry:,.5g}  →  Exit: {_exit_p:,.5g}\n"
            f"P&L: {_pnl:+.2f}%"
        )
        if cfg.get("email_enabled"):
            try:
                _alerts.send_email_alert(
                    cfg.get("email_from", ""),
                    cfg.get("email_pass", ""),
                    cfg.get("email_to", ""),
                    f"[Crypto Signal] Position Closed: {_pair} {_pnl:+.2f}%",
                    _msg,
                )
            except Exception as _e:
                logging.warning("[ExitAlert] Email failed: %s", _e)


def _run_scan_thread():
    """Background scan thread — writes results to JSON file (survives Streamlit reloads)."""
    with _scan_lock:
        _scan_state["running"] = True
        _scan_state["progress"] = 0
        _scan_state["progress_pair"] = f"Connecting to {model.TA_EXCHANGE.upper()}..."
    # PERF-30: update in-memory status on scan start
    _SCAN_STATUS["running"]    = True
    _SCAN_STATUS["progress"]   = 0
    _SCAN_STATUS["current"]    = f"Connecting to {model.TA_EXCHANGE.upper()}..."
    _SCAN_STATUS["start_time"] = time.time()   # B4: ETA calculation base
    _write_scan_status(running=True, progress=0, pair=f"Connecting to {model.TA_EXCHANGE.upper()}...")
    try:
        # st.session_state is only available in the Streamlit request context;
        # background threads (APScheduler) have no session — use safe fallback.
        results = model.run_scan(progress_callback=_progress_cb, include_tier2=False)
        model.append_to_master(results)
        # F1/F2/F4/F6/F7: resolve past outcomes, update weights, check drift
        try:
            model.run_feedback_loop()
        except Exception as _fb_err:
            logging.warning("Feedback loop error: %s", _fb_err)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        _write_scan_results(results)
        audit("scan_complete", pairs=len(results), timestamp=ts)
        # PERF-30: mark in-memory status as done; SQLite write happens here (completion only)
        _SCAN_STATUS["running"] = False
        _write_scan_status(running=False, timestamp=ts, error=None)
        # PERF-24: populate module-level store with full results;
        # only lightweight summary goes into session_state to reduce rerun overhead.
        for _rr in results:
            _rr_pair = _rr.get("pair")
            if _rr_pair:
                _SCAN_RESULTS_STORE[_rr_pair] = _rr
        # ── P&L entry/exit recording (Batch 8) ────────────────────────────────
        # On BUY: open a P&L entry. On SELL: close the matching open entry.
        try:
            for _r in results:
                _pair_pnl = _r.get("pair")
                _dir_pnl  = _r.get("direction", "")
                _px_pnl   = _r.get("price_usd") or _r.get("price") or 0
                _conf_pnl = _r.get("confidence_avg_pct") or _r.get("confidence") or 0
                if not _pair_pnl or not _px_pnl:
                    continue
                if "BUY" in str(_dir_pnl).upper():
                    _db.record_pnl_entry(_pair_pnl, _dir_pnl, float(_px_pnl), float(_conf_pnl))
                elif "SELL" in str(_dir_pnl).upper():
                    _db.record_pnl_exit(_pair_pnl, float(_px_pnl))
        except Exception as _pnl_err:
            logging.warning("[App] P&L recording error: %s", _pnl_err)
        # Check paper position exits using fresh scan prices
        _scan_closed = []  # APP-01: initialize before try so it's always defined
        try:
            _scan_px = {r["pair"]: r.get("price_usd", 0) for r in results if r.get("price_usd")}
            if _scan_px:
                _scan_closed = model.update_positions(_scan_px) or []
                if _scan_closed:
                    logging.info("[App] Auto-closed %d position(s) from scan prices", len(_scan_closed))
        except Exception as _pos_err:
            logging.warning("[App] Position exit check error: %s", _pos_err)
            _scan_closed = []
        # BUG-H06: each alert channel in its own try/except so one failure doesn't kill the others
        cfg = _cached_alerts_config()
        # Send exit alerts for positions closed above
        if _scan_closed:
            try:
                _send_exit_alerts(_scan_closed, cfg)
            except Exception as _e:
                logging.warning("[App] Exit alert failed: %s", _e)
        try:
            _alerts.send_scan_email_alerts(results, cfg)
        except Exception as _e:
            logging.warning("[App] Email alert failed: %s", _e)
        try:
            _alerts.check_watchlist_alerts(results, cfg)
        except Exception as _e:
            logging.warning("[App] Watchlist alert check failed: %s", _e)
    except Exception as e:
        # Audit R1f: log exception TYPE only — raw str(e) can echo API keys
        # or URLs depending on which library raised.
        audit("scan_error", error=type(e).__name__)
        # Don't overwrite good prior results — only update status with error
        _SCAN_STATUS["running"] = False  # PERF-30: mark in-memory as done on error
        _write_scan_status(running=False, error=str(e))
    finally:
        with _scan_lock:
            _scan_state["running"] = False
        _SCAN_STATUS["running"] = False  # PERF-30: ensure always cleared


def _scheduled_scan():
    """Entry point for APScheduler — enforces quiet hours, then delegates to _run_scan_thread."""
    cfg = _cached_alerts_config()
    if cfg.get("autoscan_quiet_hours_enabled"):
        now_str = datetime.now(timezone.utc).strftime("%H:%M")
        qs = cfg.get("autoscan_quiet_start", "22:00")
        qe = cfg.get("autoscan_quiet_end", "06:00")
        if _in_quiet_hours(now_str, qs, qe):
            logging.info("[AutoScan] Skipped — quiet hours active (%s–%s UTC)", qs, qe)
            return
    _run_scan_thread()


def _start_scan():
    # BUG-C06: guard against duplicate threads from multiple browser tabs
    with _scan_lock:
        if _scan_state["running"]:
            return
        _scan_state["running"] = True
    st.session_state["scan_running"] = True
    st.session_state["scan_run"] = True   # mark that at least one scan has been triggered
    st.session_state["scan_error"] = None
    st.session_state["scan_results"] = []
    audit("scan_start", pairs=len(model.PAIRS))
    # Clear old cache so stale results don't show during new scan
    _write_scan_status(running=True, progress=0, pair=f"Connecting to {model.TA_EXCHANGE.upper()}...")
    try:
        if os.path.exists(_SCAN_CACHE_FILE):
            os.remove(_SCAN_CACHE_FILE)
    except Exception as _cache_del_err:
        logger.debug("[App] scan cache file delete failed (non-fatal): %s", _cache_del_err)
    t = threading.Thread(target=_run_scan_thread, daemon=True)
    t.start()

# ──────────────────────────────────────────────
# PAGE 2: CONFIG EDITOR
# ──────────────────────────────────────────────
def page_config():
    _cfg_lv = st.session_state.get("user_level", "beginner")
    _cfg_title = "Settings" if _cfg_lv in ("beginner", "intermediate") else "Config Editor"
    # ── 2026-05 redesign: mockup-style top bar + page header ──
    try:
        from ui import render_top_bar as _ds_top_bar, page_header as _ds_page_header
        _ds_top_bar(breadcrumb=("Account", _cfg_title), user_level=_cfg_lv, on_refresh=_refresh_all_data, on_theme=_toggle_theme, status_pills=_agent_topbar_pills())
        _ds_page_header(
            title=_cfg_title,
            subtitle="Changes are saved to config_overrides.json and applied on next scan.",
        )
    except Exception as _ds_cfg_err:
        logger.debug("[App] config top bar failed: %s", _ds_cfg_err)
        st.markdown(
            f'<h1 style="color:#e2e8f0;font-size:26px;font-weight:700;'
            f'letter-spacing:-0.5px;margin-bottom:0">⚙️ {_cfg_title}</h1>',
            unsafe_allow_html=True,
        )
        st.caption("Changes are saved to config_overrides.json and applied on next scan.")

    # ── Item 14: Beginner simplified settings — 3 controls only ──────────────
    if _cfg_lv == "beginner":
        # C7 (Phase C plan §C7.1, 2026-04-30): wrap the panel in a
        # keyed container so overrides.py can target its inputs with
        # the mockup's `.beg-panel input` styling — bg-0 / border-
        # strong / 15px / mono / 500 weight. Streamlit 1.42+ exposes
        # the container's `key` as a `data-stkey` attribute on the
        # rendered DOM node, which is a stable CSS hook.
        with st.container(key="ds_beg_panel"):
            st.markdown("### The 3 things that matter most")
            _beg_overrides = {}
            bc1, bc2 = st.columns(2)
            with bc1:
                _beg_port = st.number_input(
                    "💰 How much money are you trading with? (USD)",
                    min_value=100.0, max_value=10_000_000.0,
                    value=float(model.PORTFOLIO_SIZE_USD), step=100.0,
                    help="This sets the dollar amount used to calculate trade sizes and risk. Example: if you have $1,000 to trade, enter 1000.",
                )
                _beg_overrides["PORTFOLIO_SIZE_USD"] = _beg_port
            with bc2:
                _beg_risk = st.number_input(
                    "🛡️ Max risk per trade (%)",
                    min_value=0.1, max_value=5.0,
                    value=float(model.RISK_PER_TRADE_PCT), step=0.1,
                    help="The maximum % of your portfolio to risk on any single trade. 1-2% is a safe starting range. Higher = bigger possible gains AND bigger possible losses.",
                )
                _beg_overrides["RISK_PER_TRADE_PCT"] = _beg_risk

            # API key quick-entry (most-needed for beginners to get live data)
            with st.expander("🔑 API Keys", expanded=False):
                st.caption("Enter your exchange API keys to enable live price data and alerts. You can skip this for now — the app works without them using public data.")
                _ak1, _ak2 = st.columns(2)
                with _ak1:
                    _beg_ok_key = st.text_input("OKX API Key", type="password", key="beg_okx_key",
                                                 help="Get your free API key from okx.com → Account → API.")
                with _ak2:
                    _beg_ok_sec = st.text_input("OKX Secret Key", type="password", key="beg_okx_sec")

            _beg_saved_col, _ = st.columns([1, 3])
            with _beg_saved_col:
                if st.button("💾 Save Settings", type="primary", width="stretch", key="beg_save_cfg"):
                    try:
                        import json as _json, os as _os
                        _ov_path = "config_overrides.json"
                        _existing = {}
                        if _os.path.exists(_ov_path):
                            with open(_ov_path) as _f:
                                _existing = _json.load(_f)
                        _existing.update(_beg_overrides)
                        with open(_ov_path, "w") as _f:
                            _json.dump(_existing, _f, indent=2)
                        st.success("✅ Settings saved! They'll apply on the next scan.")
                    except Exception as _e:
                        logger.warning("[app] settings save error: %s", _e)
                        st.error("Settings could not be saved — check file permissions and try again.")

        # C5 fix (2026-04-28): the previous shape rendered an empty
        # "Advanced Settings" expander then `return`'d immediately, so
        # beginner-tier users could NEVER reach the Trading / Signal &
        # Risk / Alerts / Dev Tools / Execution tabs even though those
        # tabs were fully wired below. The handoff doc described this
        # as "Config Editor appears wiring-stripped" — the wiring was
        # intact, but unreachable for the default user level. We now
        # fall through to the full tab-stack below; the simplified 3-
        # control view above stays as a quick-edit shortcut, and a
        # clearly labelled section header introduces the deeper tabs
        # so beginners aren't surprised by the additional surface.
        st.markdown('<div style="height:18px;"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="border-top:1px solid var(--border);padding-top:14px;'
            'margin-top:6px;">'
            '<div style="font-size:13px;color:var(--text-muted);'
            'letter-spacing:0.04em;text-transform:uppercase;font-weight:600;'
            'margin-bottom:4px;">More settings</div>'
            '<div style="font-size:14px;color:var(--text-muted);">'
            'Optional — leave these as defaults unless you want fine '
            'control over pairs, signal weights, alert rules, dev tools, '
            'or execution.</div></div>',
            unsafe_allow_html=True,
        )
        # No early return — fall through to the full tab-stack below.

    overrides = {}

    def _save_config(overrides):
        weights_override = overrides.pop("_weights", {})
        try:
            with open(model._CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(overrides, f, indent=4)
            # Save weights separately
            if weights_override:
                model.weights.update(weights_override)
                model.save_weights()
            model.load_config_overrides()
            # INT-07: restart WebSocket feed with updated PAIRS list (idempotent)
            _ws.start(model.PAIRS)
            st.success("Config saved. Changes applied to next scan.")
        except Exception as e:
            logger.error("[Config] save failed: %s", e)
            st.error("Could not save config — check file permissions and try again.")

    def _reset_config():
        try:
            if os.path.exists(model._CONFIG_FILE):
                os.remove(model._CONFIG_FILE)
            if os.path.exists(model.DYNAMIC_WEIGHTS_FILE):
                os.remove(model.DYNAMIC_WEIGHTS_FILE)
            # Clear weights from DB and re-seed with defaults via public API (BUG-15)
            _db.clear_weights(seed_weights=model.DEFAULT_WEIGHTS)
            model.weights = model.DEFAULT_WEIGHTS.copy()
            st.success("Config reset to defaults.")
        except Exception as e:
            logger.error("[Config] reset failed: %s", e)
            st.error("Could not reset config — check file permissions and try again.")

    # C6 (Phase C plan §C6.4-5, 2026-04-30): "🔔 Alerts" removed from
    # Settings tabs — alerts now have a first-class page (page_alerts).
    # Tab vars renumbered: _cfg_t3 used to be Alerts (now Dev Tools);
    # _cfg_t4 used to be Dev Tools (now Execution); the legacy fifth
    # var is gone.
    # Audit Issue #2 (2026-05-01): the legacy `_settings_tab` deep-link
    # session_state key — set by the sidebar nav handler when "alerts"
    # was clicked — was removed in C6 (the alerts entry now routes to
    # page_alerts directly). No code writes that key anymore, so the
    # earlier `pop("_settings_tab", None)` always returned None. Dead
    # read + dead conditional removed below.
    _cfg_tab_names = ["📊 Trading", "⚡ Signal & Risk", "🛠️ Dev Tools", "⚙️ Execution"]

    _cfg_t1, _cfg_t2, _cfg_t3, _cfg_t4 = st.tabs(_cfg_tab_names)

    # ── ALERTS TAB content definition (full config moved from sidebar)
    def _render_alerts_tab():
        """Alert configuration — Email only."""
        _at_cfg = _cached_alerts_config()

        with st.expander("📧 Email Alerts", expanded=_at_cfg.get("email_enabled", False)):
            _at_em = _at_cfg.copy()
            em_on   = st.toggle("Enable Email", value=_at_em.get("email_enabled", False), key="cfg_em_on")
            em_to   = st.text_input("Recipient", value=_at_em.get("email_to", ""), placeholder="you@example.com",
                                    key="cfg_em_to", disabled=not em_on)
            em_from = st.text_input("Sender (Gmail)", value=_at_em.get("email_from", ""),
                                    placeholder="yourbot@gmail.com", key="cfg_em_from", disabled=not em_on)
            # Audit R2f: never pre-fill a password into text_input — DOM-leak
            # every rerun. Blank on load; empty submit = keep stored value.
            _em_pass_has_value = bool(_at_em.get("email_pass"))
            em_pass = st.text_input(
                "App Password",
                value="",
                type="password",
                key="cfg_em_pass",
                disabled=not em_on,
                placeholder="●●●● (saved)" if _em_pass_has_value else "",
                help="Leave blank to keep the stored app password.",
            )
            em_min  = st.slider("Alert threshold (%)", 50, 95, int(_at_em.get("email_min_confidence", 70)),
                                step=5, key="cfg_em_thresh", disabled=not em_on)
            cse, cte = st.columns(2)
            with cse:
                if st.button("Save Email", key="cfg_em_save", width="stretch"):
                    # Blank-preserve: empty input means "don't overwrite".
                    _new_em_pass = em_pass if em_pass else _at_em.get("email_pass", "")
                    _at_em.update({"email_enabled": em_on, "email_to": em_to.strip(),
                                   "email_from": em_from.strip(), "email_pass": _new_em_pass,
                                   "email_min_confidence": em_min})
                    _save_alerts_config_and_clear(_at_em)
                    st.success("Saved!")
            with cte:
                if st.button("Test", key="cfg_em_test", width="stretch", disabled=not em_on):
                    # Use entered value if present, else fall back to stored.
                    _test_em_pass = em_pass if em_pass else _at_em.get("email_pass", "")
                    ok, err = _alerts.send_email_alert(em_from.strip(), _test_em_pass, em_to.strip(),
                                                       "Crypto Signal Model — Test Alert",
                                                       "\u2705 Email alert test successful.")
                    st.success("Email sent!") if ok else st.error(err or "Test failed — check your Gmail App Password and email settings.")
            st.caption("Use a Gmail App Password (Settings → Security → 2FA → App passwords)")

    # ── Tab 1: Trading Parameters
    with _cfg_t1:
        # ── Trading Pairs ──
        _ui.section_header("Trading Pairs", "Select which crypto pairs to include in each scan", icon="🪙")
        _common_pairs = [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'BNB/USDT',
            'ADA/USDT', 'AVAX/USDT', 'MATIC/USDT', 'LINK/USDT', 'LTC/USDT',
            'DOT/USDT', 'UNI/USDT', 'ATOM/USDT', 'FIL/USDT', 'NEAR/USDT',
        ]
        # Include any currently active pairs not in the preset list so they appear in the options
        _extra_active = [p for p in model.PAIRS if p not in _common_pairs]
        _pair_options = _common_pairs + _extra_active + [
            p for p in st.session_state.get("_custom_pairs_added", [])
            if p not in _common_pairs and p not in _extra_active
        ]
        _default_pairs = [p for p in model.PAIRS if p in _pair_options]
        selected_pairs = st.multiselect(
            "Select pairs to scan", options=_pair_options,
            default=_default_pairs, key="cfg_pairs"
        )
        # Custom pair entry — add any SYMBOL/USDT not in the predefined list
        _cp1, _cp2 = st.columns([3, 1])
        with _cp1:
            _custom_pair_input = st.text_input(
                "Add custom pair (e.g. PEPE/USDT)", value="",
                placeholder="TOKEN/USDT", key="cfg_custom_pair_input",
                help="Type any SYMBOL/QUOTE pair and click Add. It will be added to the list above.",
            )
        with _cp2:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            if st.button("Add Pair", key="cfg_add_custom_pair", width="stretch"):
                # #13: sanitize user-supplied pair string before using in API / DB calls
                _cp_val = _sanitize_input(_custom_pair_input, max_len=20).upper().replace(" ", "")
                if "/" not in _cp_val:
                    _cp_val = _cp_val + "/USDT"
                if _cp_val and _cp_val not in _pair_options:
                    _added = list(st.session_state.get("_custom_pairs_added", []))
                    _added.append(_cp_val)
                    st.session_state["_custom_pairs_added"] = _added
                    st.rerun()
                elif _cp_val in _pair_options:
                    st.info(f"{_cp_val} is already in the list.")
        # #13: validate selected_pairs against known TIER1 + TIER2 + model.PAIRS allowlist
        import config as _cfg_val
        _known_pairs = set(model.PAIRS) | set(_cfg_val.TIER1_PAIRS) | set(_cfg_val.TIER2_PAIRS) | set(_pair_options)
        overrides["PAIRS"] = [p for p in selected_pairs if p in _known_pairs]

        # ── Timeframes ──
        _ui.section_header("Timeframes", "Timeframes used for multi-timeframe signal analysis", icon="⏱️")
        tf_options = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M']
        selected_tfs = st.multiselect(
            "Select timeframes", options=tf_options,
            default=model.TIMEFRAMES, key="cfg_tfs"
        )
        overrides["TIMEFRAMES"] = selected_tfs

        # ── TA Exchange ──
        _ui.section_header("Data Source Exchange", "OHLCV data provider for technical analysis", icon="🔗")
        exchange_options = ['kraken', 'binance', 'coinbase', 'kucoin', 'okx', 'gemini', 'bitstamp']
        ta_ex = st.selectbox("TA Exchange (OHLCV source)", exchange_options,
                             index=exchange_options.index(model.TA_EXCHANGE) if model.TA_EXCHANGE in exchange_options else 0)
        overrides["TA_EXCHANGE"] = ta_ex

        # ── Display Preferences (ToS #10) ─────────────────────────────────
        st.markdown("---")
        _ui.section_header("Display Preferences", "Regional gain/loss color convention for international markets", icon="🎨")
        try:
            _ui.render_regional_color_toggle()
        except Exception as _rc_err:
            logger.debug("[Settings] regional color toggle render failed: %s", _rc_err)



    # ── Tab 2: Signal & Risk
    with _cfg_t2:
        # ── Risk Parameters ──
        _ui.section_header("Risk Parameters", "Position sizing, Kelly Criterion inputs, and exposure limits", icon="⚖️")
        r1, r2, r3 = st.columns(3)
        with r1:
            portfolio = st.number_input("Portfolio Size (USD)", min_value=100.0, max_value=10_000_000.0,
                                        value=float(model.PORTFOLIO_SIZE_USD), step=500.0,
                                        help=_ui.HELP_PORTFOLIO_SIZE)
            overrides["PORTFOLIO_SIZE_USD"] = portfolio
        with r2:
            risk_pct = st.number_input("Risk Per Trade (%)", min_value=0.1, max_value=10.0,
                                       value=float(model.RISK_PER_TRADE_PCT), step=0.1,
                                       help=_ui.HELP_RISK_PER_TRADE)
            overrides["RISK_PER_TRADE_PCT"] = risk_pct
        with r3:
            max_exp = st.number_input("Max Total Exposure (%)", min_value=10.0, max_value=100.0,
                                      value=float(model.MAX_TOTAL_EXPOSURE_PCT), step=5.0,
                                      help=_ui.HELP_MAX_EXPOSURE)
            overrides["MAX_TOTAL_EXPOSURE_PCT"] = max_exp

        r4, r5 = st.columns(2)
        with r4:
            max_pos_cap = st.number_input("Max Position Cap (%)", min_value=5.0, max_value=100.0,
                                          value=float(model.MAX_POSITION_PCT_CAP), step=5.0,
                                          help=_ui.HELP_MAX_POS_CAP)
            overrides["MAX_POSITION_PCT_CAP"] = max_pos_cap
        with r5:
            max_per_pair = st.number_input("Max Open Per Pair", min_value=1, max_value=5,
                                           value=int(model.MAX_OPEN_PER_PAIR),
                                           help=_ui.HELP_MAX_PER_PAIR)
            overrides["MAX_OPEN_PER_PAIR"] = max_per_pair

        # ── Signal Thresholds ──
        _ui.section_header("Signal Thresholds", "Confidence and alignment thresholds for HIGH-CONF flag and alerts", icon="🎯")
        t1, t2 = st.columns(2)
        with t1:
            hc_thresh = st.slider("High-Confidence Threshold (%)", 50, 90,
                                  int(model.HIGH_CONF_THRESHOLD), step=1,
                                  help=_ui.HELP_HIGH_CONF_THRESH)
            overrides["HIGH_CONF_THRESHOLD"] = _clamp(float(hc_thresh), 50.0, 90.0)
        with t2:
            mtf_thresh = st.slider("MTF Alignment Threshold (%)", 10, 80,
                                   int(model.HIGH_MTF_THRESHOLD), step=5,
                                   help=_ui.HELP_MTF_THRESH)
            overrides["HIGH_MTF_THRESHOLD"] = float(mtf_thresh)

        # ── Indicator Weights ──
        _ui.section_header("Indicator Weights", "How much each component contributes to the confidence score (0–1 scale, or 0–30 for bonus components)", icon="🧮")
        w_cols = st.columns(3)
        new_weights = {}
        weight_defs = [
            ("core", "Core (RSI/MACD/BB)", 0.0, 1.0, 0.01),
            ("momentum", "Momentum", 0.0, 1.0, 0.01),
            ("stoch", "Stochastic", 0.0, 1.0, 0.01),
            ("adx", "ADX", 0.0, 1.0, 0.01),
            ("vwap_ich", "VWAP/Ichimoku", 0.0, 1.0, 0.01),
            ("fib", "Fibonacci", 0.0, 1.0, 0.01),
            ("div", "MACD Divergence", 0.0, 1.0, 0.01),
            ("supertrend", "SuperTrend", 0.0, 30.0, 0.5),
            ("sr_breakout", "S/R Breakout", 0.0, 30.0, 0.5),
            ("regime", "Regime", 0.0, 30.0, 0.5),
            ("bonus", "Bonus", 0.0, 5.0, 0.1),
            ("fng", "Fear & Greed", 0.0, 1.0, 0.01),
            ("onchain", "On-Chain", 0.0, 1.0, 0.01),
            ("agents", "Multi-Agent", 0.0, 1.0, 0.01),
            ("stat_arb", "Stat Arb", 0.0, 1.0, 0.01),
        ]
        for idx, (key, label, mn, mx, step) in enumerate(weight_defs):
            with w_cols[idx % 3]:
                cur = float(model.weights.get(key, model.DEFAULT_WEIGHTS.get(key, 0)))
                new_weights[key] = st.slider(label, mn, mx, cur, step=step, key=f"w_{key}")
        overrides["_weights"] = new_weights

        # ── Correlation Filter ──
        _ui.section_header("Correlation Filter", "Reduces position size for assets highly correlated with BTC", icon="🔗")
        cr1, cr2 = st.columns(2)
        with cr1:
            corr_thresh = st.slider("BTC Correlation Threshold", 0.0, 1.0,
                                    float(model.CORR_THRESHOLD), step=0.05,
                                    help=_ui.HELP_CORR_THRESH)
            overrides["CORR_THRESHOLD"] = corr_thresh
        with cr2:
            corr_lb = st.number_input("Correlation Lookback (days)", 5, 90,
                                      int(model.CORR_LOOKBACK_DAYS),
                                      help=_ui.HELP_CORR_LB)
            overrides["CORR_LOOKBACK_DAYS"] = corr_lb

        # ── Backtest Settings ──
        _ui.section_header("Backtest Settings", "Fee model, slippage, holding period, and stop mode for historical simulation", icon="🔬")
        b1, _ = st.columns(2)
        with b1:
            hold_days = st.number_input("Backtest Hold Days", 1, 60,
                                        int(model.BACKTEST_HOLD_DAYS),
                                        help=_ui.HELP_HOLD_DAYS)
            overrides["BACKTEST_HOLD_DAYS"] = hold_days

        st.caption("OKX defaults: Taker 0.05%, Maker 0.02%, Slippage 0.05% per side.")
        b_fee1, b_fee2, b_fee3 = st.columns(3)
        with b_fee1:
            taker_fee = st.number_input("Taker Fee (fraction)", 0.0, 0.005,
                                        float(model.TAKER_FEE_PCT), step=0.0001, format="%.4f",
                                        help="Market order / stop fill fee. OKX default: 0.0005")
            overrides["TAKER_FEE_PCT"] = taker_fee
        with b_fee2:
            maker_fee = st.number_input("Maker Fee (fraction)", 0.0, 0.005,
                                        float(model.MAKER_FEE_PCT), step=0.0001, format="%.4f",
                                        help="Limit order / target fill fee. OKX default: 0.0002")
            overrides["MAKER_FEE_PCT"] = maker_fee
        with b_fee3:
            slippage = st.number_input("Slippage (fraction)", 0.0, 0.01,
                                       float(model.SLIPPAGE_PCT), step=0.0001, format="%.4f",
                                       help="Market impact per side. Conservative default: 0.0005")
            overrides["SLIPPAGE_PCT"] = slippage

        b3, b4 = st.columns(2)
        with b3:
            trailing_on = st.checkbox("Enable Trailing Stops in Backtest",
                                      value=bool(model.TRAILING_STOP_ENABLED),
                                      help="Stop loss advances with price to lock in profits. "
                                           "More realistic than fixed stops.")
            overrides["TRAILING_STOP_ENABLED"] = trailing_on
        with b4:
            dd_threshold = st.number_input(
                "Drawdown Circuit Breaker (%)", 5.0, 50.0,
                float(model.DRAWDOWN_CIRCUIT_BREAKER_PCT), step=1.0,
                help="If paper trade portfolio drawdown exceeds this %, "
                     "all new scan signals are downgraded to NEUTRAL (no entries)."
            )
            overrides["DRAWDOWN_CIRCUIT_BREAKER_PCT"] = dd_threshold

        st.markdown("---")

        # ── Indicator Weights — Bayesian Calibration (#49) ──
        st.markdown("---")
        _ui.section_header(
            "Indicator Weights (Bayesian Calibration)",
            "Beta-distribution Bayesian update of indicator weights based on resolved trade outcomes",
            icon="⚖️",
        )
        try:
            _bay_detail = _db.get_bayesian_weights_detail()
            _bay_c1, _bay_c2 = st.columns([2, 3])
            with _bay_c1:
                if st.button("Recalibrate Bayesian Weights", type="secondary",
                             width="stretch", key="btn_bayesian_recal"):
                    with st.spinner("Running Bayesian weight recalibration...", show_time=True):
                        _new_bw = _db.bayesian_recalibrate_weights(prior_strength=10.0)
                        st.session_state["bayesian_new_weights"] = _new_bw
                        # P2 audit fix — was telling users to manually
                        # reload the app. st.rerun() applies the new
                        # weights immediately without breaking session
                        # state (it's a soft re-execute, not a full reload).
                        st.success("Weights recalibrated — applying now…")
                        _bay_detail = _db.get_bayesian_weights_detail()
                        st.rerun()
            with _bay_c2:
                _cur_bw = st.session_state.get("bayesian_new_weights", {})
                if not _bay_detail and not _cur_bw:
                    st.caption("No Bayesian weights saved yet. Click **Recalibrate** to compute from feedback log.")
                else:
                    _display_bw = _bay_detail if _bay_detail else [
                        {"indicator": k, "weight": v, "wins": "—", "losses": "—"}
                        for k, v in (_cur_bw or {}).items()
                    ]
                    if _display_bw:
                        _bw_df_raw = pd.DataFrame(_display_bw)
                        _bw_df = _bw_df_raw[[c for c in ["indicator", "weight", "wins", "losses"] if c in _bw_df_raw.columns]]
                        _bw_df = _bw_df.rename(columns={"indicator": "Indicator", "weight": "Weight", "wins": "Wins", "losses": "Losses"})
                        if "Weight" in _bw_df.columns:
                            _bw_df["Weight %"] = (_bw_df["Weight"].astype(float) * 100).round(1).astype(str) + "%"
                        st.dataframe(_bw_df, width='stretch', hide_index=True)
                        # Horizontal bar chart of weights
                        if _display_bw and "weight" in _display_bw[0]:
                            _bw_fig = go.Figure(go.Bar(
                                x=[round(float(r.get("weight", 0)) * 100, 1) for r in _display_bw],
                                y=[r.get("indicator", "") for r in _display_bw],
                                orientation="h",
                                marker_color="#00d4aa",
                            ))
                            _bw_fig.update_layout(
                                height=220, margin=dict(l=0, r=0, t=10, b=0),
                                xaxis_title="Weight (%)",
                            )
                            st.plotly_chart(_bw_fig, width='stretch')
        except Exception as _bay_err:
            logger.warning("[App] Bayesian weights card error: %s", _bay_err)
            st.caption("Bayesian weights temporarily unavailable.")

        # ── ML Weight Optimizer ──
        _ui.section_header("ML Weight Optimizer", "Bayesian optimization finds indicator weights that maximize directional accuracy on historical data", icon="🤖")
        st.caption(
            "Bayesian optimization over 300 bars of historical OHLCV. "
            "Finds weights that maximize directional accuracy (signal vs next-5-bar price move). "
            "Optimizes: core, momentum, stoch, adx, vwap_ich, supertrend, regime, bonus. "
            "Other weights remain unchanged. Saves result to dynamic_weights.json."
        )
        opt_c1, opt_c2, opt_c3 = st.columns(3)
        with opt_c1:
            opt_trials = st.number_input("Trials", min_value=10, max_value=500,
                                         value=50, step=10, key="opt_trials")
        with opt_c2:
            opt_pair = st.selectbox("Training pair", model.PAIRS,
                                    index=0, key="opt_pair")
        with opt_c3:
            opt_tf = st.selectbox("Timeframe", model.TIMEFRAMES,
                                  index=0, key="opt_tf")

        if st.button("Run Optuna Optimization", key="opt_btn_run_optuna", type="primary", width="stretch"):
            with st.spinner(f"Running {opt_trials} Optuna trials on {opt_pair} {opt_tf}...", show_time=True):
                result = model.run_optuna_weight_optimization(
                    n_trials=int(opt_trials), pair=opt_pair, tf=opt_tf
                )
            if 'error' in result:
                logger.warning("[Optuna] Optimization failed: %s", result['error'])
                st.error("Optimization failed — exchange data unavailable or insufficient history. Try a different pair or timeframe.")
            else:
                st.success(
                    f"Optimization complete — Best Sharpe score: **{result['best_score']}** "
                    f"over {result['train_bars']} training bars ({opt_trials} trials)"
                )
                st.json(result['best_weights'])
                st.info("Weights saved to dynamic_weights.json and applied immediately. "
                        "Reload this page to see updated sliders.")

        # ── LightGBM Feedback Retrain ──
        st.markdown("---")
        _ui.section_header("LightGBM Feedback Retrain",
                           "Retrain the LightGBM agent using real resolved trade outcomes (was_correct) instead of in-sample price prediction",
                           icon="🧠")
        st.caption(
            "Requires ≥50 resolved feedback rows (signals with actual outcome written back). "
            "Run the Feedback Loop first to resolve pending outcomes. "
            "The retrained model is cached for 24h and used automatically in the next scan."
        )
        lgbm_info = model.get_lgbm_feedback_cache_info() if hasattr(model, 'get_lgbm_feedback_cache_info') else {}
        if lgbm_info.get("trained_at"):
            st.info(f"Current model: trained {lgbm_info['trained_at']} on {lgbm_info['n_samples']} samples")

        if st.button("Retrain LightGBM from Feedback", type="secondary", width="stretch", key="btn_lgbm_retrain"):
            with st.spinner("Retraining LightGBM on resolved trade outcomes...", show_time=True):
                lgbm_r = model.retrain_lgbm_from_feedback()
            if lgbm_r.get("success"):
                st.success(lgbm_r["message"])
            else:
                logger.warning("[LightGBM] Retrain skipped: %s", lgbm_r.get('message'))
                st.warning("Model retrain skipped — insufficient resolved trade data. Complete more trades to generate feedback.")



    # ── Tab 3: Dev Tools (consolidated — Alerts moved to page_alerts in C6)
    with _cfg_t3:
        # ── Paid API Keys ──
        st.markdown("---")
        _ui.section_header("API Keys", "Add keys to unlock premium data feeds", icon="🔑")
        st.caption(
            "Add keys here to activate premium data feeds. "
            "Keys are stored in alerts_config.json (local only, never sent anywhere). "
            "Leave blank to use free-tier fallbacks."
        )
        _api_cfg = _cached_alerts_config()
        ak1, ak2 = st.columns(2)
        with ak1:
            lc_key = st.text_input(
                "LunarCrush Key", value=_api_cfg.get("lunarcrush_key", ""),
                type="password", placeholder="Social sentiment: galaxy score, alt rank",
                key="lc_key"
            )
            cq_key = st.text_input(
                "CryptoQuant Key", value=_api_cfg.get("cryptoquant_key", ""),
                type="password", placeholder="BTC/ETH exchange flow (inflow/outflow)",
                key="cq_key"
            )
            cp_key = st.text_input(
                "CryptoPanic Key", value=_api_cfg.get("cryptopanic_key", ""),
                type="password", placeholder="Free news sentiment — sign up at cryptopanic.com",
                key="cp_key"
            )
        with ak2:
            cgl_key = st.text_input(
                "Coinglass Key", value=_api_cfg.get("coinglass_key", ""),
                type="password", placeholder="Liquidation data (longs vs shorts)",
                key="cgl_key"
            )
            gn_key = st.text_input(
                "Glassnode Key", value=_api_cfg.get("glassnode_key", ""),
                type="password", placeholder="Real SOPR, MVRV-Z, active addresses",
                key="gn_key"
            )
        if st.button("Save API Keys", key="api_btn_save_keys", width="stretch"):
            _api_cfg.update({
                "lunarcrush_key":   lc_key.strip(),
                "coinglass_key":    cgl_key.strip(),
                "cryptoquant_key":  cq_key.strip(),
                "glassnode_key":    gn_key.strip(),
                "cryptopanic_key":  cp_key.strip(),
            })
            _save_alerts_config_and_clear(_api_cfg)
            st.success("API keys saved.")
        st.caption(
            "Token unlock data (Tokenomist.ai) requires no key — automatically checked. "
            "CryptoPanic: free token (cryptopanic.com). "
            "LunarCrush free tier: 10 req/min. Coinglass/CryptoQuant/Glassnode require paid plans."
        )

        # ── Auto-Scan Scheduler ────────────────────────────────────────────────────
        st.markdown("---")
        _ui.section_header(
            "Auto-Scan Scheduler",
            "Automatic background scanning on a configurable interval with optional UTC quiet hours",
            icon="⏰",
        )
        _sched_cfg = _cached_alerts_config()

        # C-fix-12 (2026-05-02): visible §12-compliance summary before the
        # form. The user explicitly asked "when does the app run an
        # autoscan on a regular schedule?" — this banner answers that
        # by surfacing the spec, the configured value, and (when active)
        # the next-scheduled-run countdown + last-scan age in one place.
        _c12_spec_min = 15
        _c12_cur_enabled = bool(_sched_cfg.get("autoscan_enabled", True))
        _c12_cur_interval = int(_sched_cfg.get("autoscan_interval_minutes", _c12_spec_min) or _c12_spec_min)
        _c12_compliant = _c12_cur_enabled and _c12_cur_interval == _c12_spec_min
        # Last scan age (from session OR DB) so users can see whether the
        # scheduler has actually fired recently.
        _c12_last_scan_label = "—"
        try:
            _ts_obj = st.session_state.get("scan_timestamp")
            if _ts_obj is None:
                _db_st = _read_scan_status() or {}
                _ts_obj = _db_st.get("timestamp")
            if isinstance(_ts_obj, str):
                try:
                    _ts_obj = datetime.fromisoformat(_ts_obj)
                except Exception:
                    _ts_obj = None
            if isinstance(_ts_obj, datetime):
                _aware_ts = _ts_obj if _ts_obj.tzinfo else _ts_obj.replace(tzinfo=timezone.utc)
                _age_s = (datetime.now(timezone.utc) - _aware_ts).total_seconds()
                if _age_s < 60:
                    _c12_last_scan_label = f"{int(_age_s)}s ago"
                elif _age_s < 3600:
                    _c12_last_scan_label = f"{int(_age_s // 60)}m ago"
                else:
                    _c12_last_scan_label = f"{int(_age_s // 3600)}h ago"
        except Exception:
            pass

        if _c12_compliant:
            st.success(
                f"✅ **§12 compliant** — auto-scan enabled, every "
                f"**{_c12_cur_interval} min** (spec: {_c12_spec_min} min full-scan cycle). "
                f"Last scan: {_c12_last_scan_label}."
            )
        elif not _c12_cur_enabled:
            st.warning(
                f"⚠️ Auto-scan is **disabled** — CLAUDE.md §12 specifies a "
                f"{_c12_spec_min}-min full-scan cycle. Enable below for the "
                f"app to refresh signals automatically. Last scan: {_c12_last_scan_label}."
            )
        else:
            st.info(
                f"ℹ️ Auto-scan runs every **{_c12_cur_interval} min** — CLAUDE.md "
                f"§12 specifies a {_c12_spec_min}-min cycle. Tighten below to "
                f"match spec, or keep your current cadence. Last scan: {_c12_last_scan_label}."
            )

        with st.form("autoscan_form"):
            _sc1, _sc2 = st.columns(2)
            with _sc1:
                _sched_on = st.toggle(
                    "Enable Auto-Scan",
                    # C-fix-12: default to True so fresh installs match
                    # CLAUDE.md §12 "Full scan / recalc — 15 min auto".
                    # Existing users with explicit `autoscan_enabled: false`
                    # in their saved config keep their setting (.get with
                    # default applies only when the key is absent).
                    value=_sched_cfg.get("autoscan_enabled", True),
                )
                _sched_interval_opts = {
                    "15 minutes": 15, "30 minutes": 30, "1 hour": 60,
                    "2 hours": 120, "4 hours": 240, "8 hours": 480, "24 hours": 1440,
                }
                _sched_interval_label = st.selectbox(
                    "Scan Interval",
                    options=list(_sched_interval_opts.keys()),
                    index=list(_sched_interval_opts.values()).index(
                        min(_sched_interval_opts.values(),
                            # C-fix-12: default 15 min per §12 (was 60 min).
                            key=lambda v: abs(v - _sched_cfg.get("autoscan_interval_minutes", 15)))
                    ),
                    disabled=not _sched_on,
                )
            with _sc2:
                _quiet_on = st.toggle(
                    "Quiet Hours (UTC)",
                    value=_sched_cfg.get("autoscan_quiet_hours_enabled", False),
                    disabled=not _sched_on,
                    help="Scheduled scans are skipped during this UTC time window.",
                )
                _sqc1, _sqc2 = st.columns(2)
                with _sqc1:
                    _quiet_start = st.text_input(
                        "Start HH:MM",
                        value=_sched_cfg.get("autoscan_quiet_start", "22:00"),
                        disabled=not (_sched_on and _quiet_on),
                    )
                with _sqc2:
                    _quiet_end = st.text_input(
                        "End HH:MM",
                        value=_sched_cfg.get("autoscan_quiet_end", "06:00"),
                        disabled=not (_sched_on and _quiet_on),
                    )
            if st.form_submit_button("💾 Save Scheduler Config", type="primary"):
                _sched_cfg.update({
                    "autoscan_enabled":            _sched_on,
                    "autoscan_interval_minutes":   _sched_interval_opts[_sched_interval_label],
                    "autoscan_quiet_hours_enabled": _quiet_on,
                    "autoscan_quiet_start":        _quiet_start.strip(),
                    "autoscan_quiet_end":          _quiet_end.strip(),
                })
                _save_alerts_config_and_clear(_sched_cfg)
                st.success("Scheduler config saved. Toggle will apply on next Streamlit rerun.")

        _next_t = _get_next_autoscan_time()
        if _next_t:
            try:
                if _next_t.tzinfo is None:
                    _next_t = _next_t.replace(tzinfo=timezone.utc)
                _delta = _next_t - datetime.now(timezone.utc)
            except Exception:
                _delta = timedelta(0)
            _total_secs_cfg = max(0.0, _delta.total_seconds())  # APP-04: clamp before modulo to avoid -1%60=59
            _m = int(_total_secs_cfg // 60)
            _s = int(_total_secs_cfg % 60)
            st.info(f"Scheduler active — next auto-scan fires in **{_m}m {_s}s**")
        else:
            st.caption("Scheduler inactive — enable via the sidebar ⏰ Auto-Scan toggle.")

        st.markdown("---")
        save_col, reset_col = st.columns(2)
        with save_col:
            if st.button("💾 Save Config", key="cfg_btn_save", type="primary", width="stretch"):
                _save_config(overrides)
        with reset_col:
            if st.button("↺ Reset to Defaults", key="cfg_btn_reset", width="stretch"):
                _reset_config()



    # ── Tab 3 (cont.): the rest of the legacy Dev Tools content,
    #    re-entering the same tab via Streamlit's tab-context API.
    with _cfg_t3:
        # ── Sidebar legacy widgets (relocated from sidebar in 2026-04-25 redesign)
        _ui.section_header("Sidebar tools", "Auto-Scan, Demo / Sandbox, API Health, Wallet Import, API Keys, Build Info", icon="🧰")
        try:
            _render_relocated_sidebar_widgets()
        except Exception as _rsl_err:
            logger.warning("[Settings] relocated sidebar widgets failed: %s", _rsl_err)
            st.warning("Sidebar tools temporarily unavailable.")

        st.markdown("---")
        # ── Circuit Breakers (4A-5) ──────────────────────────────────────
        _ui.section_header("Circuit Breakers", "Level-C 7-gate safety system", icon="🛑")
        try:
            from circuit_breakers import get_state as _cb_state, resume as _cb_resume
            _cb = _cb_state()
            if _cb.get("halted"):
                st.error(
                    f"**HALTED** by {_cb.get('halted_gate', '—')}\n\n"
                    f"{_cb.get('halted_reason', '')}"
                )
                st.caption(f"Halted at: {_cb.get('halted_at', '—')}")
                if st.button("▶ Resume agent", key="cb_resume_btn", type="primary"):
                    _cb_resume("manual UI resume")
                    st.success("Circuit cleared — agent resumes on next cycle")
                    st.rerun()
            else:
                st.success("All 7 gates operational")
                st.caption(f"Last check: {_cb.get('last_check_at', '—')}")
                st.caption(f"Resume count (lifetime): {_cb.get('resume_count', 0)}")
        except Exception as _cb_err:
            logging.debug("[Settings] circuit breaker UI load failed: %s", _cb_err)

        # ── SQLite Database Stats ──────────────────────────────────────────────
        st.markdown("---")
        _ui.section_header("Database Health", "SQLite WAL-mode database — row counts and disk usage", icon="🗄️")
        try:
            stats = _cached_db_stats()
            dc1, dc2, dc3, dc4, dc5 = st.columns(5)
            dc1.metric("Feedback Log",    f"{stats.get('feedback_log', 0):,} rows")
            dc2.metric("Signal History",  f"{stats.get('daily_signals', 0):,} rows")
            dc3.metric("Backtest Trades", f"{stats.get('backtest_trades', 0):,} rows")
            dc4.metric("Paper Trades",    f"{stats.get('paper_trades', 0):,} rows")
            dc5.metric("DB Size",         f"{stats.get('db_size_kb', 0):,} KB")
            with st.expander("All table counts"):
                st.json({k: v for k, v in stats.items() if k != 'db_size_kb'})
        except Exception as e:
            logger.warning("[Settings] DB stats error: %s", e)
            st.warning("Database statistics temporarily unavailable.")

        # ── FastAPI REST Server ────────────────────────────────────────────────────
        st.markdown("---")
        _ui.section_header("REST API Server", "FastAPI + Uvicorn — 14 endpoints for external integrations, TradingView webhooks", icon="🚀")
        st.caption(
            "Run `python -m uvicorn api:app --host 0.0.0.0 --port 8000` alongside the Streamlit app. "
            "Interactive docs at **http://localhost:8000/docs**."
        )

        _api_cfg = _cached_alerts_config()
        with st.form("api_server_form"):
            api_key_val = st.text_input(
                "API Key",
                value=_api_cfg.get("api_key", ""),
                type="password",
                help="Clients must pass this as the `X-API-Key` header. Leave blank to disable auth (local dev only).",
            )
            ac1, ac2 = st.columns(2)
            api_host_val = ac1.text_input(
                "Host",
                value=_api_cfg.get("api_host", "0.0.0.0"),
                help="0.0.0.0 = all interfaces. Use 127.0.0.1 for local-only.",
            )
            api_port_val = ac2.number_input(
                "Port",
                min_value=1024,
                max_value=65535,
                value=int(_api_cfg.get("api_port", 8000)),
                step=1,
            )
            if st.form_submit_button("💾 Save API Config", type="primary"):
                _api_cfg.update({
                    "api_key": api_key_val.strip(),
                    "api_host": api_host_val.strip(),
                    "api_port": int(api_port_val),
                })
                _save_alerts_config_and_clear(_api_cfg)
                st.success("API config saved.")

        _host = _api_cfg.get("api_host", "0.0.0.0")
        _port = int(_api_cfg.get("api_port", 8000))
        _display_host = "localhost" if _host == "0.0.0.0" else _host
        with st.expander("Start command + endpoint reference"):
            config_dir = os.path.dirname(os.path.abspath(model._CONFIG_FILE)) or "."
            st.code(
                f"cd \"{config_dir}\"\n"
                f"python -m uvicorn api:app --host {_host} --port {_port} --reload",
                language="bash",
            )
            st.markdown(f"""
    | Method | Endpoint | Auth | Description |
    |--------|----------|------|-------------|
    | GET | `/health` | No | DB stats + scan status |
    | GET | `/signals` | Yes | Latest scan results (filterable) |
    | GET | `/signals/{{pair}}` | Yes | Single-pair signal |
    | GET | `/signals/history` | Yes | Historical signal log |
    | GET | `/positions` | Yes | Open paper trade positions |
    | GET | `/paper-trades` | Yes | Closed paper trade history |
    | GET | `/backtest` | Yes | Latest backtest metrics |
    | GET | `/backtest/trades` | Yes | Trade log (paginated) |
    | GET | `/backtest/runs` | Yes | All backtest run summaries |
    | GET | `/weights` | Yes | Current indicator weights |
    | GET | `/scan/status` | No | Scan progress |
    | POST | `/scan/trigger` | Yes | Start a background scan |
    | POST | `/webhook/tradingview` | Yes | TradingView strategy webhook |
    | GET | `/alerts/log` | Yes | Alert dispatch audit log |

    Swagger UI: **http://{_display_host}:{_port}/docs**
    """)




    # ── Tab 5: Live Execution
    with _cfg_t4:  # was _cfg_t5 before C6 dropped the Alerts tab
        # ── Live Execution Settings ────────────────────────────────────────────────
        st.markdown("---")
        _ui.section_header("Live Execution (OKX)", "Connect OKX API keys to place real or paper orders directly from the dashboard", icon="⚡")
        st.caption(
            "Connect OKX API keys to enable order execution directly from the dashboard. "
            "Paper mode is always on by default — real orders only fire when "
            "**LIVE TRADING MODE** is explicitly enabled below."
        )
        _exec_ui_cfg = _cached_alerts_config()
        with st.form("exec_config_form"):
            _live_on = st.toggle(
                "🔴 LIVE TRADING MODE",
                value=bool(_exec_ui_cfg.get("live_trading_enabled", False)),
                help="OFF = paper simulation only. ON = real orders sent to OKX with real funds.",
            )
            if _live_on:
                st.error("LIVE MODE ENABLED — orders placed here use real funds.")
            _auto_on = st.toggle(
                "Auto-Execute on Scan (HIGH_CONF signals only)",
                value=bool(_exec_ui_cfg.get("auto_execute_enabled", False)),
                help="After each scan, automatically place orders for HIGH_CONF signals "
                     "above the threshold. Respects paper/live mode toggle above.",
            )
            _auto_conf = st.slider(
                "Auto-Execute Confidence Threshold (%)",
                min_value=70, max_value=95,
                value=int(_exec_ui_cfg.get("auto_execute_min_confidence", 80)),
                step=5,
                disabled=not _auto_on,
            )
            st.markdown("**OKX API Keys**")
            st.caption(
                "Create a key at okx.com → API Management. "
                "Grant: Read + Trade + Futures. Never grant Withdrawal permission."
            )
            st.warning(
                "Security note: API keys are stored in alerts_config.json in plain text. "
                "Do not commit this file to version control. "
                "Add alerts_config.json to your .gitignore."
            )
            _ek1, _ek2, _ek3 = st.columns(3)
            # Audit R2f: the 3 OKX credentials were pre-filled from config on
            # every render — each value shipped into the HTML DOM on every
            # rerun (even type="password" renders the literal value attr).
            # Blank fields on load; on save, empty input = keep stored value.
            _okx_key_has  = bool(_exec_ui_cfg.get("okx_api_key"))
            _okx_sec_has  = bool(_exec_ui_cfg.get("okx_secret"))
            _okx_pass_has = bool(_exec_ui_cfg.get("okx_passphrase"))
            _okx_key  = _ek1.text_input(
                "API Key", value="", type="password",
                placeholder="●●●● (saved)" if _okx_key_has else "OKX API Key",
            )
            _okx_sec  = _ek2.text_input(
                "Secret", value="", type="password",
                placeholder="●●●● (saved)" if _okx_sec_has else "OKX Secret",
            )
            _okx_pass = _ek3.text_input(
                "Passphrase", value="", type="password",
                placeholder="●●●● (saved)" if _okx_pass_has else "API Passphrase",
            )
            st.caption("Leave a field blank to keep the currently saved value.")
            _ord_type = st.selectbox(
                "Default Order Type", ["market", "limit"],
                index=0 if _exec_ui_cfg.get("default_order_type", "market") == "market" else 1,
            )
            if st.form_submit_button("💾 Save Execution Config", type="primary"):
                # Blank-preserve for each OKX credential.
                _new_okx_key  = _okx_key.strip()  if _okx_key.strip()  else _exec_ui_cfg.get("okx_api_key", "")
                _new_okx_sec  = _okx_sec.strip()  if _okx_sec.strip()  else _exec_ui_cfg.get("okx_secret", "")
                _new_okx_pass = _okx_pass.strip() if _okx_pass.strip() else _exec_ui_cfg.get("okx_passphrase", "")
                _exec_ui_cfg.update({
                    "live_trading_enabled":        _live_on,
                    "auto_execute_enabled":        _auto_on,
                    "auto_execute_min_confidence": _auto_conf,
                    "okx_api_key":                 _new_okx_key,
                    "okx_secret":                  _new_okx_sec,
                    "okx_passphrase":              _new_okx_pass,
                    "default_order_type":          _ord_type,
                })
                _save_alerts_config_and_clear(_exec_ui_cfg)
                st.success("Execution config saved.")

        if st.button("🔌 Test OKX Connection", key="exec_btn_test_okx", width="content"):
            _es = _exec.get_status()
            if not _es.get("keys_configured", False):
                st.warning("No API keys saved — enter and save keys first.")
            else:
                import concurrent.futures as _cf_okx
                with st.spinner("Connecting to OKX...", show_time=True):
                    _okx_ex = _cf_okx.ThreadPoolExecutor(max_workers=1)
                    try:
                        _okx_fut = _okx_ex.submit(_exec.test_connection)
                        try:
                            _conn = _okx_fut.result(timeout=12)
                        except _cf_okx.TimeoutError:
                            _conn = {"ok": False, "balance_usdt": 0.0, "error": "timeout"}
                    finally:
                        _okx_ex.shutdown(wait=False)
                if _conn["ok"]:
                    st.success(f"Connected! USDT Balance: ${_conn['balance_usdt']:,.2f}")
                elif _conn.get("error") == "timeout":
                    st.error("OKX did not respond in time — check your internet connection and try again.")
                else:
                    logger.warning("[Execution] OKX connection failed: %s", _conn['error'])
                    st.error("Connection failed — check your OKX API key, secret, and passphrase in Settings.")

        # ── Autonomous Agent (link card — moved to AI Assistant page) ────────
        # C5 (Phase C plan §C5.4, 2026-04-30): the autonomous agent's
        # config + start/stop controls + status panel were duplicated
        # here AND on the AI Assistant page (page_agent). Per the plan
        # the AI Assistant page is now the canonical home; this slot
        # is reduced to a small link card so users on Settings →
        # Execution still see the agent exists but get redirected
        # rather than presented with a competing config form.
        st.markdown("---")
        _ui.section_header(
            "Autonomous AI Agent",
            "Configuration + start/stop + decision log live on the AI Assistant page.",
            icon="🤖",
        )
        st.markdown(
            '<div style="padding:14px 16px;border:1px solid var(--border);'
            'border-radius:12px;background:var(--bg-1);">'
            '<div style="font-weight:600;color:var(--text-primary);'
            'margin-bottom:6px;">Where to find agent settings</div>'
            '<div style="color:var(--text-muted);font-size:13.5px;'
            'line-height:1.6;">All agent runtime controls — Dry-run, '
            'cycle interval, min-confidence threshold, max concurrent '
            'positions, daily-loss limit, portfolio size, max trade '
            'size, max drawdown, cooldown after loss, emergency stop, '
            'and the live decision log — are now on the '
            '<b>AI Assistant</b> page (sidebar → Account → '
            'AI Assistant). The agent and its execution settings '
            'share runtime state, so consolidating them on one page '
            'avoids the two-form-of-truth bug that used to ship '
            'whenever this Settings → Execution form was edited '
            'while the AI Assistant page was open in another tab.'
            '</div></div>',
            unsafe_allow_html=True,
        )
        # Tiny "jump to AI Assistant" button — uses the same routing
        # mechanism as the deprecated Arbitrage stub: write _nav_target
        # and rerun, the sidebar router picks it up and lands on Agent.
        if st.button("Open AI Assistant →", key="cfg_exec_open_agent",
                     type="primary"):
            st.session_state["_nav_target"] = "Agent"
            st.session_state["_ds_current_nav_label"] = "AI Assistant"
            st.rerun()

        # All legacy agent config form, runtime controls, and live
        # status display were removed here in C5 (Phase C plan §C5.4).
        # They lived from the now-deleted block of ~120 lines that
        # duplicated the AI Assistant page's surfaces. Removed
        # outright per the plan ("REMOVE the Autonomous Agent
        # block ... replace with a small link card").
        # The link card above is now the entire Settings → Execution
        # agent surface; AI Assistant is the canonical home.
        # ── _LEGACY_REMOVED_C5 (2026-04-30) ─────────────────────────────────
        # The Settings → Execution Autonomous-Agent block previously
        # rendered a duplicate of the AI Assistant page's config form,
        # Start/Stop runtime controls, and live status summary. ~120
        # lines deleted here per Phase C plan §C5.4: "REMOVE the
        # Autonomous Agent block ... replace with a small link card".
        # The link card above is the entire surface now; AI Assistant
        # is the canonical home for all agent config + control.
        # Search this sentinel in git blame to recover the deleted code.


        # ── Watchlist Alerts ───────────────────────────────────────────────────────
        st.markdown("---")
        _ui.section_header(
            "Watchlist Alerts",
            "Get notified when a specific coin hits a signal you care about — fires on every scan",
            icon="🔔",
        )
        st.caption(
            "Each rule fires via Email (if enabled above). "
            "Use 'ALL' in the coin field to watch every coin in the scan list."
        )

        _wl_cfg = _cached_alerts_config()
        _watchlist = _wl_cfg.get("watchlist", [])

        # Add new rule form
        with st.expander("➕ Add New Watchlist Rule", expanded=False):
            with st.form("wl_add_form", clear_on_submit=True):
                _wl_c1, _wl_c2, _wl_c3 = st.columns([2, 2, 1])
                with _wl_c1:
                    _wl_name = st.text_input("Rule Name", placeholder="e.g. BTC Strong Buy Alert")
                    _wl_pair_opts = ["ALL"] + model.PAIRS
                    _wl_pair = st.selectbox("Coin", _wl_pair_opts, index=0)
                with _wl_c2:
                    _wl_cond = st.selectbox(
                        "Signal Condition",
                        ["ANY", "BUY", "STRONG BUY", "SELL", "STRONG SELL"],
                        index=0,
                        help="Alert fires when this coin's signal matches this direction",
                    )
                    _wl_min_conf = st.slider("Min Confidence %", min_value=40, max_value=95, value=70, step=5)
                with _wl_c3:
                    st.write("")
                    st.write("")
                    _wl_enabled = st.checkbox("Enabled", value=True)
                _wl_submitted = st.form_submit_button("Add Rule", type="primary", width="stretch")
                if _wl_submitted:
                    if not _wl_name.strip():
                        st.warning("Please enter a rule name.")
                    else:
                        _watchlist.append({
                            "name":           _wl_name.strip(),
                            "pair":           _wl_pair,
                            "condition":      _wl_cond,
                            "min_confidence": _wl_min_conf,
                            "enabled":        _wl_enabled,
                        })
                        _wl_cfg["watchlist"] = _watchlist
                        _save_alerts_config_and_clear(_wl_cfg)
                        st.success(f"Rule '{_wl_name.strip()}' added.")
                        st.rerun()

        # Display + manage existing rules
        if not _watchlist:
            st.info("No watchlist rules yet — add your first rule above.")
        else:
            for _wl_idx, _wl_rule in enumerate(_watchlist):
                _wl_pill_color = (
                    "#00d4aa" if "BUY" in _wl_rule.get("condition", "") else
                    "#ef4444" if "SELL" in _wl_rule.get("condition", "") else
                    "#8b5cf6"
                )
                _wl_status = "🟢 ON" if _wl_rule.get("enabled", True) else "⚫ OFF"
                _wl_rc1, _wl_rc2, _wl_rc3 = st.columns([5, 1, 1])
                with _wl_rc1:
                    st.markdown(
                        f"""<div style="background:rgba(14,18,30,0.7);border:1px solid rgba(255,255,255,0.07);
                        border-radius:10px;padding:10px 14px;margin-bottom:4px">
                        <span style="font-weight:700;color:#e2e8f0">{_wl_rule.get('name','—')}</span>
                        <span style="background:{_wl_pill_color}22;color:{_wl_pill_color};
                              border:1px solid {_wl_pill_color}55;border-radius:999px;
                              font-size:10px;font-weight:700;padding:1px 9px;margin:0 6px">
                              {_wl_rule.get('condition','ANY')}</span>
                        <span style="color:rgba(168,180,200,0.55);font-size:12px">
                            {_wl_rule.get('pair','ALL')} · ≥{_wl_rule.get('min_confidence',70):.0f}% conf · {_wl_status}
                        </span></div>""",
                        unsafe_allow_html=True,
                    )
                with _wl_rc2:
                    _toggle_label = "Disable" if _wl_rule.get("enabled", True) else "Enable"
                    if st.button(_toggle_label, key=f"wl_toggle_{_wl_idx}", width="stretch"):
                        _watchlist[_wl_idx]["enabled"] = not _wl_rule.get("enabled", True)
                        _wl_cfg["watchlist"] = _watchlist
                        _save_alerts_config_and_clear(_wl_cfg)
                        st.rerun()
                with _wl_rc3:
                    if st.button("Delete", key=f"wl_del_{_wl_idx}", width="stretch"):
                        _watchlist.pop(_wl_idx)
                        _wl_cfg["watchlist"] = _watchlist
                        _save_alerts_config_and_clear(_wl_cfg)
                        st.rerun()



# ── Backtest progress fragment — module level to keep session-state key stable ──
# run_every=5: 5-second poll is responsive enough for a 2-5 minute backtest while
# cutting event-loop scheduling pressure 5× vs the former run_every=1.
@st.fragment(run_every=5)
def _backtest_progress():
    # Early-return when not running — keeps fragment registered without rendering anything.
    if not st.session_state.get("backtest_running", False) and not _bt_state["running"]:
        return
    with _bt_lock:
        _still_running = _bt_state["running"]
        _bt_results    = _bt_state["results"]
        _bt_error      = _bt_state["error"]
    if not _still_running and st.session_state.get("backtest_running", False):
        st.session_state["backtest_results"] = _bt_results
        st.session_state["backtest_error"]   = _bt_error
        st.session_state["backtest_running"] = False
        st.rerun()
    else:
        st.info("Running backtest — fetching historical candles for each signal... (2–5 min)")


# ──────────────────────────────────────────────
# PAGE 3: BACKTEST VIEWER
# ──────────────────────────────────────────────
def page_backtest():
    _bt_lv = st.session_state.get("user_level", "beginner")
    # C4 (2026-04-29): Backtester now hosts two views via primary
    # segmented control — "backtest" (default) and "arbitrage" (was
    # the standalone Arbitrage page; merged in per §C4).
    _bt_view = st.session_state.get("bt_view", "backtest")
    if _bt_view not in ("backtest", "arbitrage"):
        _bt_view = "backtest"
    _bt_title = "Arbitrage" if _bt_view == "arbitrage" else "Backtester"
    _bt_sub = (
        "Cross-exchange spot price spreads and funding-rate carry trades."
        if _bt_view == "arbitrage"
        else "Composite signal backtested across the historical universe. "
             "Optuna-tuned hyperparams."
    )
    # ── 2026-05 redesign: mockup-style top bar + page header (matches
    #    shared-docs/design-mockups/sibling-family-crypto-signal-BACKTESTER.html)
    try:
        from ui import render_top_bar as _ds_top_bar, page_header as _ds_page_header
        _ds_top_bar(breadcrumb=("Research", _bt_title), user_level=_bt_lv, on_refresh=_refresh_all_data, on_theme=_toggle_theme, status_pills=_agent_topbar_pills())
        _ds_page_header(title=_bt_title, subtitle=_bt_sub)
    except Exception as _ds_bt_err:
        logger.debug("[App] backtest top bar failed: %s", _ds_bt_err)
        st.markdown(
            f'<h1 style="color:#e2e8f0;font-size:26px;font-weight:700;'
            f'letter-spacing:-0.5px;margin-bottom:0">{_bt_title}</h1>',
            unsafe_allow_html=True,
        )

    # C4: primary segmented control swaps Backtester ↔ Arbitrage. Both
    # views share the page surface (topbar + page_header above) and
    # the run-time URL — so deep-link `?bt_view=arbitrage` lands on
    # Arbitrage without changing the page slot.
    try:
        from ui import segmented_control as _ds_seg
        _bt_view = _ds_seg(
            [("backtest", "Backtest"), ("arbitrage", "Arbitrage")],
            active=_bt_view,
            key="bt_view",
            variant="primary",
        )
    except Exception as _e_seg_primary:
        logger.debug("[Backtest] primary segmented control failed: %s",
                     _e_seg_primary)

    # If the user has flipped to the Arbitrage view, hand off to the
    # extracted helper and skip the rest of the Backtester body.
    if _bt_view == "arbitrage":
        try:
            _render_arbitrage_view()
        except Exception as _e_arb_render:
            logger.error("[Backtest] arbitrage view render failed: %s",
                         _e_arb_render)
            st.error("Arbitrage scanner failed to load — check logs.")
        return

    # ── C4: Universe selector — drives every backtest query below.
    # Persists in st.session_state["bt_universe"]. Items match the
    # spec: per-pair singles + Top 10 / Top 25 / All 33 / Custom.
    try:
        _bt_uni_universe = list(model.PAIRS or [])
        _bt_uni_options = (
            [f"{p} only" for p in _bt_uni_universe[:8]]
            + ["Top 10 cap", "Top 25 cap", "All 33", "Custom multi-select"]
        )
        _bt_uni_default = st.session_state.get("bt_universe", "Top 10 cap")
        if _bt_uni_default not in _bt_uni_options:
            _bt_uni_default = "Top 10 cap"
            st.session_state["bt_universe"] = _bt_uni_default
        _bt_uni_l, _bt_uni_r = st.columns([3, 5])
        with _bt_uni_l:
            _bt_uni_picked = st.selectbox(
                "Universe",
                options=_bt_uni_options,
                index=_bt_uni_options.index(_bt_uni_default),
                key="bt_universe_select",
                help="Filters every backtest metric, KPI, equity curve, "
                     "Optuna result and trade row below to the chosen scope.",
            )
            if _bt_uni_picked != st.session_state.get("bt_universe"):
                st.session_state["bt_universe"] = _bt_uni_picked
        with _bt_uni_r:
            if _bt_uni_picked == "Custom multi-select":
                _bt_custom = st.multiselect(
                    "Custom pairs",
                    options=_bt_uni_universe,
                    default=st.session_state.get(
                        "bt_universe_custom",
                        _bt_uni_universe[:5],
                    ),
                    key="bt_universe_custom",
                    label_visibility="collapsed",
                )
    except Exception as _e_uni:
        logger.debug("[Backtest] universe selector failed: %s", _e_uni)

    # ── Controls row (Universe / Period / Initial / Rebalance / Costs) + Run button
    try:
        from ui import (
            backtest_controls_row as _ds_bt_controls,
            backtest_kpi_strip as _ds_bt_kpis,
            optuna_top_card as _ds_bt_optuna,
            recent_trades_card as _ds_bt_trades,
        )
        # Pull config-driven values where available; fall back to sensible defaults.
        _bt_cfg = _cached_alerts_config() or {}
        # C4-fix (2026-04-30): the legacy controls-row pill was reading
        # `backtest_universe` from alerts_config, while the new C4
        # selectbox above writes to `st.session_state["bt_universe"]`.
        # When the user picked "All 33" but alerts_config still said
        # "Top 10 cap", the page showed two competing universes and
        # users couldn't tell which one was active. Now the pill reads
        # the session-state key first so both surfaces always agree.
        _bt_universe = (
            st.session_state.get("bt_universe")
            or _bt_cfg.get("backtest_universe", "Top 10 cap")
        )
        _bt_period = _bt_cfg.get("backtest_period", "2023-01-01 → today")
        _bt_initial = _bt_cfg.get("backtest_initial_usd", "$100,000")
        _bt_rebalance = _bt_cfg.get("backtest_rebalance", "Weekly")
        _bt_costs = _bt_cfg.get("backtest_costs", "12 bps · realistic slippage")
        st.markdown(
            _ds_bt_controls(
                [
                    ("Universe", str(_bt_universe)),
                    ("Period", str(_bt_period)),
                    ("Initial", str(_bt_initial)),
                    ("Rebalance", str(_bt_rebalance)),
                    ("Costs", str(_bt_costs)),
                ],
                run_button_label="Re-run backtest →",
            ),
            unsafe_allow_html=True,
        )
    except Exception as _e_ctrl:
        logger.debug("[Backtest] controls row failed: %s", _e_ctrl)

    # C2 fix (2026-04-28): the run trigger is a real Streamlit button.
    # Earlier the controls row above also rendered an HTML `<button>`
    # labelled "Re-run backtest →" inside an `st.markdown` block, which
    # captured user clicks but couldn't trigger any Python handler — so
    # users who clicked it saw nothing happen. The decorative button has
    # been suppressed in `backtest_controls_row` (see show_decorative_
    # button=False), and this Streamlit button now uses on_click= so the
    # state write + thread spawn happen BEFORE the script re-renders
    # (immediate "running" feedback on the very next paint).
    def _on_run_backtest_click():
        _start_backtest()
        try:
            st.toast("Backtest started — running in background", icon="⏱")
        except Exception:
            pass

    run_col, _ = st.columns([2, 6])
    with run_col:
        bt_disabled = st.session_state.get("backtest_running", False)
        st.button(
            "▶ Run Backtest",
            key="bt_btn_run",
            disabled=bt_disabled,
            type="primary",
            width="stretch",
            on_click=_on_run_backtest_click,
        )

    # _backtest_progress is defined at module level (above page_backtest) — always called
    # here so its fragment key stays registered across rerenders (prevents $$ID KeyError).
    _backtest_progress()

    # ── 2026-05 redesign: mockup-style backtester sections (matches
    # sibling-family-crypto-signal-BACKTESTER.html: 5-col KPI strip +
    # 2-col equity-vs-BTC + Optuna top-5 + recent-trades table). Renders
    # above the existing tabs so users land on the mockup view first;
    # tabs below carry the deeper Trade History / Advanced views.
    try:
        _bt_df = _cached_backtest_df()
        _bt_sess = st.session_state.get("backtest_results") or {}
        _bt_m = (_bt_sess or {}).get("metrics") or {}
        _bt_equity = (_bt_sess or {}).get("equity")

        # Derive metrics from DB if session state is empty
        _bt_total = _bt_m.get("total_return")
        _bt_cagr = _bt_m.get("cagr")
        _bt_sharpe = _bt_m.get("sharpe")
        _bt_dd = _bt_m.get("max_drawdown")
        _bt_wr = _bt_m.get("win_rate")
        _bt_n = _bt_m.get("total_trades", 0)
        _bt_btc_total = _bt_m.get("btc_return", _bt_m.get("buy_hold_return"))
        _bt_btc_cagr = _bt_m.get("btc_cagr")
        _bt_btc_dd = _bt_m.get("btc_max_drawdown", _bt_m.get("benchmark_max_drawdown"))

        if _bt_total is None and _bt_df is not None and not _bt_df.empty:
            _pnl = _bt_df.get("pnl_pct")
            if _pnl is not None and len(_pnl) > 0:
                _bt_total = float(_pnl.sum())
                _bt_wr = float((_pnl > 0).mean() * 100.0)
                _bt_n = int(len(_pnl))
                _eq = (1.0 + _pnl / 100.0).cumprod()
                _peak = _eq.cummax()
                _bt_dd = float(((_eq - _peak) / _peak * 100.0).min())
                _std = float(_pnl.std())
                if _std > 0:
                    _bt_sharpe = float(_pnl.mean() / _std)

        def _pct(v, d=1, signed=True):
            if v is None:
                return "—"
            try:
                fv = float(v)
                if signed:
                    sign = "+ " if fv > 0 else ("− " if fv < 0 else "")
                    return f"{sign}{abs(fv):.{d}f}%"
                return f"{fv:.{d}f}%"
            except Exception:
                return "—"

        # C-fix-06 (2026-05-01): render a CTA card when there's nothing
        # to summarise. The labels-without-values state ("TOTAL RETURN: —",
        # "CAGR: —", "SHARPE: —" ...) was actively misleading on cold-
        # start — users couldn't tell whether the backtest had run and
        # produced zeros, or hadn't run at all. A guided CTA tells them
        # exactly what to do, with the same visual weight as the strip.
        _bt_has_any_data = any(v is not None for v in (
            _bt_total, _bt_cagr, _bt_sharpe, _bt_dd, _bt_wr,
        ))
        if not _bt_has_any_data:
            st.markdown(
                '<div class="ds-card" style="text-align:center;padding:28px 20px;">'
                '<div style="font-size:14px;font-weight:600;color:var(--text-primary);'
                'margin-bottom:6px;">No backtest results yet</div>'
                '<div style="font-size:12.5px;color:var(--text-muted);'
                'max-width:520px;margin:0 auto 14px;">'
                'Configure parameters below and run a backtest to populate the '
                'KPI strip with total return, CAGR, Sharpe, max drawdown and '
                'win rate.'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # 5-col KPI strip
            _ds_bt_kpis([
                ("Total return",
                 _pct(_bt_total, 1),
                 f"vs BTC {_pct(_bt_btc_total, 1)}" if _bt_btc_total is not None else "over backtest window",
                 "success" if (_bt_total is not None and float(_bt_total) > 0) else ("danger" if _bt_total is not None and float(_bt_total) < 0 else "")),
                ("CAGR",
                 _pct(_bt_cagr, 1),
                 f"vs BTC {_pct(_bt_btc_cagr, 1)}" if _bt_btc_cagr is not None else "annualised",
                 ""),
                ("Sharpe",
                 f"{float(_bt_sharpe):.2f}" if _bt_sharpe is not None else "—",
                 "risk-free 4.5%",
                 "accent" if (_bt_sharpe is not None and float(_bt_sharpe) >= 1.5) else ""),
                ("Max drawdown",
                 _pct(_bt_dd, 1),
                 f"BTC {_pct(_bt_btc_dd, 1)}" if _bt_btc_dd is not None else "peak → trough",
                 "danger" if (_bt_dd is not None and float(_bt_dd) != 0) else ""),
                ("Win rate",
                 _pct(_bt_wr, 0, signed=False) if _bt_wr is not None else "—",
                 f"n = {int(_bt_n)} trades" if _bt_n else "no runs yet",
                 ""),
            ])

        # 2-col: equity curve + Optuna top-5
        _bt_col_l, _bt_col_r = st.columns([2, 1])
        with _bt_col_l:
            st.markdown(
                '<div class="ds-card">'
                '<div class="ds-card-hd">'
                '<div class="ds-card-title">Equity curve · signal vs BTC</div>'
                f'<div style="color:var(--text-muted);font-size:12px;">{str(_bt_period) if "_bt_period" in dir() else ""}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            try:
                if _bt_df is not None and not _bt_df.empty and "pnl_pct" in _bt_df.columns:
                    _eq_signal = (1.0 + _bt_df["pnl_pct"].fillna(0) / 100.0).cumprod() * 100.0
                    _x = list(range(len(_eq_signal)))
                    import plotly.graph_objects as _go
                    _fig = _go.Figure()
                    _fig.add_trace(_go.Scatter(
                        x=_x, y=_eq_signal.tolist(), mode="lines",
                        name="Composite signal",
                        line=dict(color="#22d36f", width=2),
                        fill="tozeroy", fillcolor="rgba(34,211,111,0.18)",
                        hovertemplate="%{y:.1f}<extra>signal</extra>",
                    ))
                    # BTC benchmark line if available
                    try:
                        _ex = model.get_exchange_instance(model.TA_EXCHANGE)
                        if _ex:
                            # P1-25 audit fix — was uncached on every Backtester
                            # render. §12 5min cache via _sg_cached_ohlcv.
                            _ex_id = getattr(_ex, "id", str(model.TA_EXCHANGE))
                            _btc_o = _sg_cached_ohlcv(
                                _ex_id, "BTC/USDT", "1d",
                                limit=max(200, len(_eq_signal) or 0),
                            )
                            if _btc_o:
                                _btc_closes = [float(r[4]) for r in _btc_o if len(r) >= 5]
                                if _btc_closes:
                                    _b0 = _btc_closes[0]
                                    _btc_eq = [c / _b0 * 100.0 for c in _btc_closes][-len(_eq_signal):]
                                    _fig.add_trace(_go.Scatter(
                                        x=list(range(len(_btc_eq))),
                                        y=_btc_eq, mode="lines",
                                        name="BTC buy-and-hold",
                                        line=dict(color="#8a8a9d", width=1.5, dash="dash"),
                                    ))
                    except Exception as _e_btc:
                        logger.debug("[Backtest] BTC benchmark fetch failed: %s", _e_btc)
                    _fig.update_layout(
                        height=280, margin=dict(l=0, r=0, t=10, b=0),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(visible=False),
                        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                        legend=dict(
                            orientation="h", yanchor="bottom", y=1.02,
                            xanchor="left", x=0,
                            font=dict(color="#8a8a9d", size=12),
                            bgcolor="rgba(0,0,0,0)",
                        ),
                    )
                    st.plotly_chart(_fig, width='stretch', config={"displayModeBar": False})
                else:
                    st.caption("Equity curve unavailable — run a backtest to populate.")
            except Exception as _e_eq:
                logger.debug("[Backtest] equity curve render failed: %s", _e_eq)
                st.caption("Equity curve render failed — see logs.")
            st.markdown('</div>', unsafe_allow_html=True)

        with _bt_col_r:
            # Optuna top-5 — read from optuna_studies.sqlite if available
            _opt_rows = []
            try:
                import optuna as _opt
                _study_name = getattr(model, "OPTUNA_STUDY_NAME", "optuna_cpx")
                _study_storage = getattr(model, "OPTUNA_STORAGE", "sqlite:///optuna_studies.sqlite")
                try:
                    _study = _opt.load_study(study_name=_study_name, storage=_study_storage)
                    _trials = sorted(
                        [t for t in _study.trials if t.value is not None and t.state.name == "COMPLETE"],
                        key=lambda t: t.value,
                        reverse=True,
                    )[:5]
                    for _i, _t in enumerate(_trials, start=1):
                        _params_str = ", ".join(f"{k}={v}" for k, v in list(_t.params.items())[:4])
                        _opt_rows.append({
                            "rank": _i,
                            "star": (_i == 1),
                            "params": _params_str,
                            "sharpe": _t.value,
                            "return_pct": _t.user_attrs.get("total_return") if hasattr(_t, "user_attrs") else None,
                        })
                except Exception as _e_load:
                    logger.debug("[Backtest] Optuna study load failed: %s", _e_load)
            except ImportError:
                pass
            _ds_bt_optuna(
                _opt_rows,
                title="Optuna studies · top 5 hyperparam sets",
                footer=f"Study: {getattr(model, 'OPTUNA_STUDY_NAME', '—')} · TPE sampler" if _opt_rows else "",
            )

        # Recent trades table (last 8)
        _trade_rows = []
        try:
            if _bt_df is not None and not _bt_df.empty:
                _df_recent = _bt_df.sort_values(_bt_df.columns[0], ascending=False).head(8) if len(_bt_df.columns) else _bt_df.head(8)
                for _, _row in _df_recent.iterrows():
                    _date_v = _row.get("entry_time") or _row.get("date") or _row.get("timestamp")
                    try:
                        _date_str = str(_date_v)[:10] if _date_v is not None else "—"
                    except Exception:
                        _date_str = "—"
                    _side = str(_row.get("side") or _row.get("direction") or "").upper()
                    _trade_rows.append({
                        "date": _date_str,
                        "side": "BUY" if _side in ("LONG", "BUY") else ("SELL" if _side in ("SHORT", "SELL") else _side),
                        "reason": str(_row.get("reason") or _row.get("rationale") or _row.get("pair") or "")[:80],
                        "return_pct": _row.get("pnl_pct") or _row.get("return_pct"),
                        "duration": _row.get("duration") or _row.get("hold_days") or "—",
                    })
        except Exception as _e_tr:
            logger.debug("[Backtest] trades table prep failed: %s", _e_tr)
        _ds_bt_trades(
            _trade_rows,
            title="Recent trades · signal-driven",
            subtitle=f"last {len(_trade_rows)} of {int(_bt_n) if _bt_n else len(_trade_rows)}" if _trade_rows else "",
        )
        st.markdown('<div style="height:24px;"></div>', unsafe_allow_html=True)
    except Exception as _e_mockup:
        logger.debug("[Backtest] mockup sections failed: %s", _e_mockup)

    # C4 §C4.2: secondary segmented control replaces the legacy
    # `st.tabs([Summary, Trade History, Advanced])`. Per Q8 Option B —
    # segmented controls give first-click highlight (no two-click lag)
    # and let us conditionally skip the heavy Advanced render unless
    # the user actually opens that view.
    try:
        from ui import segmented_control as _ds_seg2
        _bt_subview = st.session_state.get("bt_subview", "summary")
        if _bt_subview not in ("summary", "trades", "advanced"):
            _bt_subview = "summary"
        _bt_subview = _ds_seg2(
            [("summary", "Summary"),
             ("trades", "Trade History"),
             ("advanced", "Advanced")],
            active=_bt_subview,
            key="bt_subview",
            variant="small",
        )
    except Exception as _e_seg2:
        logger.debug("[Backtest] secondary segmented control failed: %s", _e_seg2)
        _bt_subview = "summary"

    if _bt_subview == "summary":
        if st.session_state.get("backtest_error"):
            logger.warning("[Backtest] error: %s", st.session_state["backtest_error"])
            st.error("Backtest could not complete — try running the scan first to generate signal history.")

        # Show existing results — from session state (fresh run) or DB (prior run)
        bt_res = st.session_state.get("backtest_results")
        df_trades = _cached_backtest_df()

        if bt_res is None and df_trades.empty:
            st.info("No backtest data yet. Run **▶ Run Backtest** or ensure the daily signals DB table has entries.")
            return

        # Use session results if available, otherwise load from file
        metrics = None
        equity = None
        if bt_res and isinstance(bt_res, dict):
            metrics = bt_res.get("metrics")
            equity = bt_res.get("equity")
            df_trades = bt_res.get("trades", df_trades)

        if metrics:
            m = metrics
            _wr = m.get('win_rate', 0)

            # ── 2026-05 redesign: mockup-style 5-col KPI grid ────────────────
            # Mirrors the top strip of
            # shared-docs/design-mockups/sibling-family-crypto-signal-BACKTESTER.html.
            # Renders above the existing level-specific metric grids so users
            # get the signature look at every level while the existing
            # beginner/intermediate/advanced panels below stay intact.
            try:
                _tr = m.get("total_return", 0)
                _bt_btc_ret = m.get("btc_return", m.get("buy_hold_return", None))
                _bt_cagr = m.get("cagr", None)
                _bt_btc_cagr = m.get("btc_cagr", None)
                _bt_sharpe = m.get("sharpe", 0)
                _bt_dd = m.get("max_drawdown", 0)
                _bt_btc_dd = m.get("btc_max_drawdown", m.get("benchmark_max_drawdown", None))
                _bt_ntrades = m.get("total_trades", 0)

                def _bt_fmt_pct(v, decimals=1):
                    if v is None:
                        return "—"
                    try:
                        fv = float(v)
                        sign = "+ " if fv > 0 else ("− " if fv < 0 else "")
                        return f"{sign}{abs(fv):.{decimals}f}%"
                    except Exception:
                        return "—"

                _tr_color = "var(--success)" if (_tr is not None and float(_tr) > 0) else ("var(--danger)" if (_tr is not None and float(_tr) < 0) else "var(--text-primary)")
                _dd_color = "var(--danger)" if (_bt_dd is not None and float(_bt_dd) != 0) else "var(--text-primary)"
                _sh_color = "var(--accent)" if (_bt_sharpe is not None and float(_bt_sharpe) >= 1.5) else "var(--text-primary)"

                _bt_sub_tr = f'<div class="sub up">vs BTC {_bt_fmt_pct(_bt_btc_ret)}</div>' if _bt_btc_ret is not None else '<div class="sub">over backtest window</div>'
                _bt_sub_cagr = f'<div class="sub">vs BTC {_bt_fmt_pct(_bt_btc_cagr)}</div>' if _bt_btc_cagr is not None else '<div class="sub">annualised</div>'
                _bt_sub_dd = f'<div class="sub down">BTC {_bt_fmt_pct(_bt_btc_dd)}</div>' if _bt_btc_dd is not None else '<div class="sub">peak → trough</div>'

                _bt_kpi_html = f"""
                <style>
                .ds-bt-kpis {{ display: grid; grid-template-columns: repeat(5, 1fr);
                               gap: var(--gap); margin: 8px 0 20px 0; }}
                .ds-bt-kpis .card {{ background: var(--bg-1); border: 1px solid var(--border);
                                      border-radius: var(--card-radius); padding: var(--card-pad); }}
                .ds-bt-kpis .lbl {{ font-size: 11px; color: var(--text-muted);
                                     text-transform: uppercase; letter-spacing: 0.06em; }}
                .ds-bt-kpis .val {{ font-size: 22px; font-weight: 600; font-family: var(--font-mono);
                                     line-height: 1.1; margin-top: 4px; color: var(--text-primary); }}
                .ds-bt-kpis .sub {{ font-size: 11.5px; color: var(--text-muted);
                                     margin-top: 4px; font-family: var(--font-mono); }}
                .ds-bt-kpis .sub.up {{ color: var(--success); }}
                .ds-bt-kpis .sub.down {{ color: var(--danger); }}
                @media (max-width: 1024px) {{ .ds-bt-kpis {{ grid-template-columns: repeat(2, 1fr); }} }}
                @media (max-width: 600px) {{ .ds-bt-kpis {{ grid-template-columns: 1fr; }} }}
                </style>
                <div class="ds-bt-kpis">
                  <div class="card">
                    <div class="lbl">Total return</div>
                    <div class="val" style="color:{_tr_color};">{_bt_fmt_pct(_tr)}</div>
                    {_bt_sub_tr}
                  </div>
                  <div class="card">
                    <div class="lbl">CAGR</div>
                    <div class="val">{_bt_fmt_pct(_bt_cagr) if _bt_cagr is not None else _bt_fmt_pct(_tr)}</div>
                    {_bt_sub_cagr}
                  </div>
                  <div class="card">
                    <div class="lbl">Sharpe</div>
                    <div class="val" style="color:{_sh_color};">{float(_bt_sharpe):.2f}</div>
                    <div class="sub">risk-free 4.5%</div>
                  </div>
                  <div class="card">
                    <div class="lbl">Max drawdown</div>
                    <div class="val" style="color:{_dd_color};">{_bt_fmt_pct(_bt_dd)}</div>
                    {_bt_sub_dd}
                  </div>
                  <div class="card">
                    <div class="lbl">Win rate</div>
                    <div class="val">{float(_wr):.0f}%</div>
                    <div class="sub">n = {int(_bt_ntrades)} trades</div>
                  </div>
                </div>
                """
                st.markdown(_bt_kpi_html, unsafe_allow_html=True)
            except Exception as _bt_kpi_err:
                logger.debug("[App] backtest KPI strip render failed: %s", _bt_kpi_err)

            # ── Item 12: Beginner simplified view — 3 big metrics ─────────────────
            if _bt_lv == "beginner":
                bm = st.columns(3)
                bm[0].metric(
                    "✅ Win Rate",
                    f"{_wr}%",
                    delta=f"{round(_wr - 50, 1):+.1f}% better than a coin flip",
                    help="Out of every 100 signals the model gave, this percentage made money. Above 50% means it's right more often than wrong.",
                )
                bm[1].metric(
                    "💰 Total Return",
                    f"{m.get('total_return', 0)}%",
                    help="If you had followed every signal since the start, this is the total gain or loss on your portfolio.",
                )
                bm[2].metric(
                    "🛡️ Worst Drawdown",
                    f"{m.get('max_drawdown', 0)}%",
                    help="The biggest drop from a high point before recovering. Think of it as the worst losing patch. Lower is safer.",
                )
                with st.expander("📊 Full Performance Stats", expanded=False):
                    mc = st.columns(6)
                    mc[0].metric("Trades Simulated", m.get("total_trades", 0), help=_ui.HELP_TOTAL_TRADES)
                    mc[1].metric("Profitable Trades", f"{_wr}%", delta=f"{round(_wr - 50, 1):+.1f}% vs coin-flip", help=_ui.HELP_WIN_RATE)
                    mc[2].metric("Avg Gain per Trade", f"{m.get('avg_pnl', 0)}%", help=_ui.HELP_AVG_PNL)
                    mc[3].metric("Profit vs Loss Ratio", m.get("profit_factor", 0), help=_ui.HELP_PROFIT_FACTOR)
                    mc[4].metric("Performance Quality", m.get("sharpe", 0), help=_ui.HELP_SHARPE)
                    mc[5].metric("Worst Losing Streak", f"{m.get('max_drawdown', 0)}%", help=_ui.HELP_MAX_DRAWDOWN)
                    mc2 = st.columns(5)
                    mc2[0].metric("Total Return", f"{m.get('total_return', 0)}%")
                    mc2[1].metric("Risk-Adj Return", m.get("sortino", "—"), help=_ui.HELP_SORTINO)
                    mc2[2].metric("Recovery Speed", m.get("calmar", "—"), help=_ui.HELP_CALMAR)
                    mc2[3].metric("Longest Losing Run", m.get("max_consec_losses", "—"), help="How many trades in a row lost money at worst.")
                    mc2[4].metric("Edge per Trade", f"{m.get('expectancy', 0)}%", help=_ui.HELP_EXPECTANCY)

                # ── Beginner "What does this mean for me?" panel ──────────────
                _wr_v  = float(_wr)
                _ret_v = float(m.get('total_return', 0))
                _dd_v  = abs(float(m.get('max_drawdown', 0)))
                if _wr_v >= 60 and _ret_v > 0:
                    _btm_color  = "rgba(0,212,170,0.10)"; _btm_border = "rgba(0,212,170,0.35)"
                    _btm_icon   = "✅"; _btm_grade = "Strong Performance"
                    _btm_msg    = (
                        f"The model has been right <strong>{_wr_v:.0f}%</strong> of the time — "
                        f"well above the 50% you'd get from random guessing. "
                        f"Following every signal would have returned <strong>{_ret_v:+.1f}%</strong> overall."
                    )
                elif _wr_v >= 50 and _ret_v >= 0:
                    _btm_color  = "rgba(245,158,11,0.10)"; _btm_border = "rgba(245,158,11,0.35)"
                    _btm_icon   = "📊"; _btm_grade = "Decent Performance"
                    _btm_msg    = (
                        f"The model wins more often than it loses (<strong>{_wr_v:.0f}%</strong> win rate) "
                        f"and the total return is <strong>{_ret_v:+.1f}%</strong>. "
                        f"This is an acceptable result, though there's room to improve."
                    )
                else:
                    _btm_color  = "rgba(239,68,68,0.10)"; _btm_border = "rgba(239,68,68,0.35)"
                    _btm_icon   = "⚠️"; _btm_grade = "Challenging Period"
                    _btm_msg    = (
                        f"The model's win rate is <strong>{_wr_v:.0f}%</strong> and total return is "
                        f"<strong>{_ret_v:+.1f}%</strong> over this backtest period. "
                        f"This reflects past data — real-time performance may differ."
                    )
                _btm_risk = (
                    "The worst losing patch was small — the model has managed risk well so far."
                    if _dd_v < 20 else
                    f"The worst losing patch was <strong>{_dd_v:.1f}%</strong> — keep your position sizes small to limit your exposure during downturns."
                )
                st.markdown(
                    f'<div style="background:{_btm_color};border:1px solid {_btm_border};'
                    f'border-radius:12px;padding:18px 22px;margin:14px 0">'
                    f'<div style="font-size:13px;font-weight:700;color:#00d4aa;margin-bottom:8px">'
                    f'{_btm_icon} What does this mean for me? — {_btm_grade}</div>'
                    f'<div style="font-size:13px;color:#94a3b8;line-height:1.65">'
                    f'{_btm_msg}<br><br>{_btm_risk}<br><br>'
                    f'<em>Past performance does not guarantee future results. '
                    f'Always treat signals as one input in your decision — not a guarantee.</em>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                # Intermediate / Advanced — full metric grids
                mc = st.columns(6)
                mc[0].metric("Trades Simulated", m.get("total_trades", 0),
                             help=_ui.HELP_TOTAL_TRADES)
                mc[1].metric(f"Profitable Trades", f"{_wr}%",
                             delta=f"{round(_wr - 50, 1):+.1f}% vs coin-flip",
                             help=_ui.HELP_WIN_RATE)
                mc[2].metric("Avg Gain per Trade", f"{m.get('avg_pnl', 0)}%",
                             help=_ui.HELP_AVG_PNL)
                mc[3].metric("Profit vs Loss Ratio", m.get("profit_factor", 0),
                             help=_ui.HELP_PROFIT_FACTOR)
                mc[4].metric("Performance Quality", m.get("sharpe", 0),
                             help=_ui.HELP_SHARPE)
                mc[5].metric("Worst Losing Streak", f"{m.get('max_drawdown', 0)}%",
                             help=_ui.HELP_MAX_DRAWDOWN)

                mc2 = st.columns(5)
                mc2[0].metric("Total Return", f"{m.get('total_return', 0)}%")
                mc2[1].metric("Risk-Adj Return", m.get("sortino", "—"),
                              help=_ui.HELP_SORTINO)
                mc2[2].metric("Recovery Speed", m.get("calmar", "—"),
                              help=_ui.HELP_CALMAR)
                mc2[3].metric("Longest Losing Run", m.get("max_consec_losses", "—"),
                              help="How many trades in a row lost money at worst. Lower = more consistent.")
                mc2[4].metric("Edge per Trade", f"{m.get('expectancy', 0)}%",
                              help=_ui.HELP_EXPECTANCY)

                mc3 = st.columns(3)
                mc3[0].metric("Bad-Day Loss (VaR)", f"{m.get('var_95', 'N/A')}%",
                              help="On a bad day (worst 5% of trades), how much could you lose on a single trade?")
                mc3[1].metric("CVaR (95%)", f"{m.get('cvar_95', 'N/A')}%",
                              help="Conditional VaR: average loss when VaR threshold is breached (expected shortfall).")
                trailing_label = "Trailing Stops" if model.TRAILING_STOP_ENABLED else "Fixed Stops"
                mc3[2].metric("Stop Mode", trailing_label,
                              help="Trailing: stop advances with price to lock in profits. Fixed: stop stays at initial level.")

            # ── Fee & slippage breakdown — intermediate/advanced only ──
            if _bt_lv != "beginner" and m.get("total_fees_usd") is not None:
                st.markdown("**Fee & Slippage Breakdown**")
                mf = st.columns(5)
                mf[0].metric("Gross Return", f"{m.get('gross_return', 'N/A')}%",
                             help="Total return before exchange fees and slippage.")
                mf[1].metric("Net Return", f"{m.get('total_return', 'N/A')}%",
                             help="Total return after fees and slippage. This is what you actually keep.")
                fee_drag = m.get('fee_drag_pct', 0)
                mf[2].metric("Fee Drag", f"{fee_drag}%",
                             delta=f"-{abs(fee_drag)}%" if fee_drag else None,
                             delta_color="inverse",
                             help="Gross Return minus Net Return. Total performance lost to exchange fees and slippage.")
                mf[3].metric("Total Fees ($)", f"${m.get('total_fees_usd', 0):,.2f}",
                             help=f"Sum of taker ({model.TAKER_FEE_PCT*100:.3f}%) + maker ({model.MAKER_FEE_PCT*100:.3f}%) fees across all trades.")
                mf[4].metric("Total Slippage ($)", f"${m.get('total_slippage_usd', 0):,.2f}",
                             help=f"Market impact cost ({model.SLIPPAGE_PCT*100:.3f}% per side) applied to market-order fills.")
            st.markdown("---")

        # Enhanced Equity Curve with drawdown subplot and win/loss markers
        if equity and len(equity) > 1:
            _ui.section_header("Equity Curve", "Portfolio value with drawdown — green dots=wins, red dots=losses", icon="📈")

            _eq = np.array(equity, dtype=float)
            _x  = list(range(len(_eq)))

            # Compute running peak and drawdown %
            _peak = np.maximum.accumulate(_eq)
            _dd   = np.where(_peak != 0, (_eq - _peak) / _peak * 100, 0.0)  # APP-22: guard zero equity start

            # Win/loss markers from trade log
            _win_x, _win_y, _loss_x, _loss_y = [], [], [], []
            if not df_trades.empty and "pnl_pct" in df_trades.columns:
                for _ti, (_tidx, _trow) in enumerate(df_trades.iterrows()):
                    if _ti < len(_eq):
                        _pnl_val = float(_trow.get("pnl_pct", 0) or 0)
                        if _pnl_val > 0:
                            _win_x.append(_ti); _win_y.append(_eq[_ti])
                        elif _pnl_val < 0:
                            _loss_x.append(_ti); _loss_y.append(_eq[_ti])

            _efig = make_subplots(
                rows=2, cols=1,
                row_heights=[0.65, 0.35],
                shared_xaxes=True,
                vertical_spacing=0.04,
            )

            # Row 1: equity curve + initial equity line + win/loss dots
            _init_eq = float(_eq[0])
            _efig.add_trace(go.Scatter(
                x=_x, y=_eq.tolist(), mode="lines", name="Portfolio",
                line=dict(color="#00d4aa", width=2),
            ), row=1, col=1)
            _efig.add_hline(y=_init_eq, line_dash="dot", line_color="#94a3b8",
                            annotation_text=f"Start ${_init_eq:,.0f}",
                            annotation_position="bottom right", row=1, col=1)
            if _win_x:
                _efig.add_trace(go.Scatter(
                    x=_win_x, y=_win_y, mode="markers", name="Win",
                    marker=dict(color="#22c55e", size=5, symbol="circle"),
                ), row=1, col=1)
            if _loss_x:
                _efig.add_trace(go.Scatter(
                    x=_loss_x, y=_loss_y, mode="markers", name="Loss",
                    marker=dict(color="#ef4444", size=5, symbol="circle"),
                ), row=1, col=1)

            # Row 2: drawdown % (filled red below 0)
            _efig.add_trace(go.Scatter(
                x=_x, y=_dd.tolist(), mode="lines", name="Drawdown %",
                line=dict(color="#ef4444", width=1),
                fill="tozeroy", fillcolor="rgba(255,75,75,0.2)",
            ), row=2, col=1)

            _efig.update_layout(
                height=480,
                margin=dict(l=10, r=10, t=20, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=1.08, font=dict(size=9)),
                showlegend=True,
            )
            _efig.update_yaxes(title_text="Portfolio ($)", row=1, col=1,
                               gridcolor="#222", tickformat="$,.0f")
            _efig.update_yaxes(title_text="Drawdown %", row=2, col=1,
                               gridcolor="#222")
            _efig.update_xaxes(title_text="Trade #", row=2, col=1,
                               gridcolor="#222")
            _efig.update_xaxes(gridcolor="#222", row=1, col=1)
            st.plotly_chart(_efig, width='stretch')
        elif os.path.exists("backtest_equity_curve.png"):
            st.image("backtest_equity_curve.png", caption="Equity Curve (static)")

        # Trade table
        if not df_trades.empty:
            st.subheader("Trade Log")

            # Filters
            f1, f2, f3 = st.columns(3)
            with f1:
                pair_filter = st.multiselect("Filter by Pair",
                                             options=df_trades['pair'].unique().tolist() if 'pair' in df_trades.columns else [],
                                             default=[])
            with f2:
                dir_filter = st.multiselect("Filter by Direction",
                                            options=['BUY', 'STRONG BUY', 'SELL', 'STRONG SELL'],
                                            default=[])
            with f3:
                reason_filter = st.multiselect("Exit Reason",
                                               options=df_trades['exit_reason'].unique().tolist() if 'exit_reason' in df_trades.columns else [],
                                               default=[])

            filtered = df_trades.copy()
            if pair_filter and 'pair' in filtered.columns:
                filtered = filtered[filtered['pair'].isin(pair_filter)]
            if dir_filter and 'direction' in filtered.columns:
                filtered = filtered[filtered['direction'].isin(dir_filter)]
            if reason_filter and 'exit_reason' in filtered.columns:
                filtered = filtered[filtered['exit_reason'].isin(reason_filter)]

            st.dataframe(
                filtered,
                width='stretch', height=400,
                column_config={
                    "pnl_pct": st.column_config.NumberColumn("PNL %", format="%.2f%%"),
                    "pnl_usd": st.column_config.NumberColumn("PNL $", format="$%.2f"),
                },
            )

            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                st.download_button(
                    "⬇ Download Trade Log (CSV)",
                    data=filtered.to_csv(index=False),
                    file_name="backtest_trades.csv",
                    mime="text/csv",
                    width="stretch",
                    key="dl_backtest_csv",
                )
            with dl_col2:
                if _pdf is not None:
                    try:
                        bt_pdf_bytes = _pdf.generate_backtest_pdf(
                            metrics=metrics,
                            trades_df=filtered,
                            scan_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        )
                        st.download_button(
                            "⬇ Download Report (PDF)",
                            data=bt_pdf_bytes,
                            file_name=f"backtest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            width="stretch",
                            key="dl_backtest_pdf",
                        )
                    except Exception as _bt_pdf_err:
                        logger.warning("[App] backtest PDF failed: %s", _bt_pdf_err)
                        st.caption("PDF generation failed — please try again.")
                else:
                    st.caption("PDF export unavailable")

            # PnL distribution
            if 'pnl_pct' in df_trades.columns and len(df_trades) > 3:
                st.subheader("PnL Distribution")
                fig2 = px.histogram(df_trades, x='pnl_pct', nbins=20,
                                    color_discrete_sequence=['#8b5cf6'],
                                    labels={'pnl_pct': 'PnL %'})
                fig2.add_vline(x=0, line_dash="dash", line_color="red")
                fig2.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig2, width='stretch')

            # Monte Carlo simulation — advanced only (Item 12)
            if _bt_lv != "beginner" and 'pnl_pct' in df_trades.columns and len(df_trades) >= 5:
                _ui.section_header("Monte Carlo Simulation",
                                   "Bootstrap resamples trade sequence to estimate distribution of equity outcomes and max drawdown", icon="🎲")
                mc_c1, mc_c2 = st.columns([1, 4])
                with mc_c1:
                    n_mc = st.number_input("Simulations", 100, 5000, 1000, step=100,
                                           key="n_mc_sims")
                    if st.button("Run Monte Carlo", type="secondary", width="stretch",
                                 key="btn_monte_carlo"):
                        with st.spinner(f"Running {int(n_mc)} Monte Carlo simulations...", show_time=True):
                            mc_res = model.run_monte_carlo(df_trades, n_sim=int(n_mc))
                        st.session_state["mc_result"] = mc_res

                mc_r = st.session_state.get("mc_result")
                if mc_r and 'error' not in mc_r:
                    with mc_c2:
                        mc_m = st.columns(4)
                        mc_m[0].metric("Profitable Runs", f"{mc_r['pct_profitable']}%",
                                       help="% of simulations where final equity > starting equity")
                        mc_m[1].metric("Median Equity", f"${mc_r['equity_p50']:,.0f}",
                                       help="50th percentile final equity across all simulations")
                        mc_m[2].metric("Worst 5% Equity", f"${mc_r['equity_p5']:,.0f}",
                                       help="5th percentile — tail risk floor")
                        mc_m[3].metric("Median Max DD", f"{mc_r['mdd_p50']}%",
                                       help="Median max drawdown across all simulations")

                    fig_mc = go.Figure()
                    fig_mc.add_trace(go.Histogram(
                        x=mc_r['all_final_equities'],
                        nbinsx=60,
                        name="Final Equity",
                        marker_color='#8b5cf6',
                        opacity=0.75,
                    ))
                    fig_mc.add_vline(x=mc_r['initial_equity'], line_dash="dash",
                                     line_color="white", annotation_text="Start")
                    fig_mc.add_vline(x=mc_r['equity_p5'], line_dash="dot",
                                     line_color="red", annotation_text="P5")
                    fig_mc.add_vline(x=mc_r['equity_p95'], line_dash="dot",
                                     line_color="green", annotation_text="P95")
                    fig_mc.update_layout(
                        xaxis_title="Final Equity (USD)",
                        yaxis_title="Frequency",
                        height=300, margin=dict(l=0, r=0, t=10, b=0),
                    )
                    st.plotly_chart(fig_mc, width='stretch')
                elif mc_r and 'error' in mc_r:
                    st.warning(mc_r['error'])


    elif _bt_subview == "trades":
        tab_master, tab_paper, tab_feedback, tab_exec, tab_slip = st.tabs([
            "Signal Master Log", "Paper Trades", "Feedback Log", "Execution Log", "Slippage Analytics"
        ])

        # ── Tab 1: Master Log ──
        with tab_master:
            df = _cached_signals_df()
            if df.empty:
                st.info("No master log data yet. Run a scan first.")
            else:
                # Summary metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Records", len(df))
                if 'direction' in df.columns:
                    buys = df['direction'].str.contains("BUY", na=False).sum()
                    sells = df['direction'].str.contains("SELL", na=False).sum()
                    m2.metric("Total Buy Signals", int(buys))
                    m3.metric("Total Sell Signals", int(sells))
                if 'confidence_avg_pct' in df.columns:
                    avg_conf = pd.to_numeric(df['confidence_avg_pct'], errors='coerce').mean()
                    m4.metric("Avg Confidence", f"{avg_conf:.1f}%" if pd.notna(avg_conf) else "—")

                st.markdown("---")

                # Confidence trend per pair
                if 'scan_timestamp' in df.columns and 'confidence_avg_pct' in df.columns and 'pair' in df.columns:
                    st.subheader("Confidence Trend by Pair")
                    pair_filter = st.multiselect("Select pairs", options=df['pair'].unique().tolist(),
                                                  default=df['pair'].unique().tolist()[:3], key="master_pair_filter")
                    df_plot = df[df['pair'].isin(pair_filter)] if pair_filter else df
                    fig = px.line(df_plot, x='scan_timestamp', y='confidence_avg_pct',
                                  color='pair', markers=True, render_mode='webgl',
                                  labels={'confidence_avg_pct': 'Confidence (%)', 'scan_timestamp': 'Scan Time'})
                    fig.add_hline(y=model.HIGH_CONF_THRESHOLD, line_dash="dash", line_color="green",
                                  annotation_text=f"High-Conf ({model.HIGH_CONF_THRESHOLD}%)")
                    fig.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig, width='stretch')

                # Searchable table
                st.subheader("All Records")
                search = st.text_input("Search (pair, direction...)", key="master_search")
                if search:
                    _search_cols = [c for c in ['pair', 'direction', 'strategy_bias', 'regime'] if c in df.columns]
                    _mask = df[_search_cols].astype(str).apply(lambda r: r.str.contains(search, case=False, na=False)).any(axis=1)
                    display_df = df[_mask]
                else:
                    display_df = df

                # Rename columns to human-readable labels for display
                col_labels = {
                    'scan_timestamp': 'Scan Time', 'pair': 'Pair', 'price_usd': 'Price (USD)',
                    'confidence_avg_pct': 'Confidence %', 'direction': 'Direction',
                    'strategy_bias': 'Strategy Bias', 'mtf_alignment': 'MTF Alignment',
                    'high_conf': 'High Conf', 'fng_value': 'Fear & Greed', 'fng_category': 'F&G Label',
                    'entry': 'Entry', 'exit': 'Target', 'stop_loss': 'Stop Loss',
                    'risk_pct': 'Risk %', 'position_size_usd': 'Position USD',
                    'position_size_pct': 'Position %', 'risk_mode': 'Risk Mode',
                    'corr_with_btc': 'BTC Corr', 'corr_adjusted_size_pct': 'Corr-Adj Size %',
                    'regime': 'Regime', 'sr_status': 'S/R Status',
                    'circuit_breaker_triggered': 'CB Triggered',
                    'circuit_breaker_drawdown_pct': 'CB Drawdown %', 'scan_sec': 'Scan Sec',
                }
                display_df = display_df.rename(columns={k: v for k, v in col_labels.items() if k in display_df.columns})
                st.dataframe(display_df, width='stretch', height=400)
                st.download_button("⬇ Download Master Log", data=df.to_csv(index=False),
                                   file_name="daily_signals_master.csv", mime="text/csv",
                                   key="dl_master_log")

        # ── Tab 2: Paper Trades ──
        with tab_paper:
            df_closed = _cached_paper_trades_df()
            try:
                positions = model.load_positions()
            except Exception as _e:
                logging.warning("load_positions failed: %s", _e)
                positions = {}

            # ── Portfolio Heat Strip ──────────────────────────────────────────────
            if positions:
                _total_exp  = sum(float(p.get("size_pct") or 0) for p in positions.values())  # APP-16: or 0 handles explicit None
                _buy_exp    = sum(float(p.get("size_pct") or 0) for p in positions.values() if "BUY"  in str(p.get("direction", "")))
                _sell_exp   = sum(float(p.get("size_pct") or 0) for p in positions.values() if "SELL" in str(p.get("direction", "")))
                _n_pos      = len(positions)
                # Heat color: green < 30%, amber 30–60%, red > 60%
                _heat_color = "#00d4aa" if _total_exp < 30 else ("#f59e0b" if _total_exp < 60 else "#ef4444")
                _heat_label = "Low" if _total_exp < 30 else ("Medium" if _total_exp < 60 else "High")
                st.markdown(
                    f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">'
                    f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);'
                    f'border-radius:10px;padding:10px 18px;text-align:center">'
                    f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">PORTFOLIO HEAT</div>'
                    f'<div style="font-size:20px;font-weight:700;color:{_heat_color}">{_heat_label}</div>'
                    f'<div style="font-size:10px;color:rgba(168,180,200,0.4)">Total exposure</div></div>'
                    f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);'
                    f'border-radius:10px;padding:10px 18px;text-align:center">'
                    f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">FUNDS IN TRADES</div>'
                    f'<div style="font-size:20px;font-weight:700;color:{_heat_color}">{_total_exp:.1f}%</div>'
                    f'<div style="font-size:10px;color:rgba(168,180,200,0.4)">of portfolio</div></div>'
                    f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);'
                    f'border-radius:10px;padding:10px 18px;text-align:center">'
                    f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">OPEN POSITIONS</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#e2e8f0">{_n_pos}</div>'
                    f'<div style="font-size:10px;color:rgba(168,180,200,0.4)">trades active</div></div>'
                    f'<div style="background:rgba(0,212,170,0.06);border:1px solid rgba(0,212,170,0.2);'
                    f'border-radius:10px;padding:10px 18px;text-align:center">'
                    f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">BUY EXPOSURE</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#00d4aa">{_buy_exp:.1f}%</div>'
                    f'<div style="font-size:10px;color:rgba(168,180,200,0.4)">long trades</div></div>'
                    f'<div style="background:rgba(246,70,93,0.06);border:1px solid rgba(246,70,93,0.2);'
                    f'border-radius:10px;padding:10px 18px;text-align:center">'
                    f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">SELL EXPOSURE</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#ef4444">{_sell_exp:.1f}%</div>'
                    f'<div style="font-size:10px;color:rgba(168,180,200,0.4)">short trades</div></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.subheader("Open Positions")
            if positions:
                # ── Price resolution: WS first, scan fallback ──────────────────
                _live_ticks  = _ws.get_all_prices() or {}  # APP-03/15: guard None return when WS not connected
                _scan_prices = {
                    r['pair']: r.get('price_usd')
                    for r in st.session_state.get("scan_results", [])
                    if r.get("price_usd")
                }
                _ws_ok = _ws.get_status().get("connected", False)
                _price_src_label = "● LIVE (WebSocket)" if _ws_ok else "◎ Last Scan Price"
                st.caption(f"Price source: {_price_src_label}  ·  {len(positions)} open position(s)")

                for _pair, _pos in positions.items():
                    _entry     = _pos.get('entry')
                    _direction = _pos.get('direction', 'BUY')
                    _target    = _pos.get('target')
                    _stop      = _pos.get('stop')
                    _size_pct  = _pos.get('size_pct')
                    _entry_time = _pos.get('entry_time')

                    # Current price
                    _tick = _live_ticks.get(_pair)
                    _cur  = float(_tick['price']) if _tick else (
                        float(_scan_prices[_pair]) if _pair in _scan_prices else None
                    )
                    _src_tag = "● LIVE" if _tick else ("◎ scan" if _cur else "—")

                    # Unrealized P&L
                    if _cur is not None and _entry and float(_entry) > 0:
                        _ef = float(_entry)
                        if "BUY" in _direction:
                            _pnl_pct = (_cur - _ef) / _ef * 100
                        else:
                            _pnl_pct = (_ef - _cur) / _ef * 100
                    else:
                        _pnl_pct = float(_pos.get('current_pnl_pct', 0))
                        _cur = None

                    # Distance to stop / target  (as % of entry)
                    _stop_dist = _tgt_dist = None
                    if _cur is not None and _entry and float(_entry) > 0:
                        _ef = float(_entry)
                        if _stop:
                            _stop_dist = abs(_cur - float(_stop)) / _ef * 100
                        if _target:
                            _tgt_dist  = abs(float(_target) - _cur) / _ef * 100

                    # Time in trade
                    _dur_str = "—"
                    if _entry_time:
                        try:
                            from datetime import timezone as _tz
                            _et  = pd.to_datetime(_entry_time, utc=True)
                            _dur = datetime.now(_tz.utc) - _et.to_pydatetime()
                            _h, _rem = divmod(int(_dur.total_seconds()), 3600)
                            _dur_str = f"{_h}h {_rem // 60}m"
                        except Exception as _dur_err:
                            logger.debug("[App] position duration parse failed: %s", _dur_err)

                    # Render position card
                    _pnl_sign  = "+" if _pnl_pct >= 0 else ""
                    _dir_emoji = "🟢" if "BUY" in _direction else "🔴"
                    _pnl_color = "#00d4aa" if _pnl_pct >= 0 else "#ef4444"

                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:10px;padding:14px 18px;'
                        f'margin-bottom:10px;border-left:4px solid {_pnl_color}">'
                        f'<span style="font-size:15px;font-weight:700">{_dir_emoji} {_pair}</span>'
                        f'&nbsp;&nbsp;<code style="font-size:12px">{_direction}</code>'
                        f'&nbsp;&nbsp;<span style="color:#888;font-size:11px">{_src_tag}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    _pc1, _pc2, _pc3, _pc4, _pc5 = st.columns(5)
                    _pc1.metric("Entry Price",   f"{float(_entry):,.5g}" if _entry else "—")
                    _pc2.metric("Current Price", f"{_cur:,.5g}"          if _cur   else "—")
                    _pc3.metric(
                        "Unrealized P&L",
                        f"{_pnl_sign}{_pnl_pct:.2f}%",
                        delta=f"{_pnl_sign}{_pnl_pct:.2f}%",
                        delta_color="normal",
                    )
                    _pc4.metric("Time In Trade", _dur_str)
                    _pc5.metric("Size", f"{_size_pct}%" if _size_pct else "—")

                    _dc1, _dc2, _dc3 = st.columns(3)
                    _dc1.caption(
                        f"Stop: {float(_stop):,.5g}  ({_stop_dist:.2f}% away)"
                        if _stop and _stop_dist is not None
                        else f"Stop: {float(_stop):,.5g}" if _stop else "Stop: —"
                    )
                    _dc2.caption(
                        f"Target: {float(_target):,.5g}  ({_tgt_dist:.2f}% to go)"
                        if _target and _tgt_dist is not None
                        else f"Target: {float(_target):,.5g}" if _target else "Target: —"
                    )
                    _dc3.caption(f"Entry time: {_entry_time}" if _entry_time else "")
                    st.markdown("")

                # ── Actions ────────────────────────────────────────────────────
                _btn_col, _auto_col, _ = st.columns([1.5, 1.5, 3])
                with _btn_col:
                    if st.button("Check Exits & Refresh", key="refresh_pos"):
                        _all_prices = dict(_scan_prices)
                        _all_prices.update({p: v['price'] for p, v in _live_ticks.items()})
                        if _all_prices:
                            _closed = model.update_positions(_all_prices)
                            if _closed:
                                st.success(f"Closed {len(_closed)} position(s) at stop/target.")
                                try:
                                    _send_exit_alerts(_closed)
                                except Exception as _ae:
                                    logging.warning("[App] Exit alert (manual) failed: %s", _ae)
                            st.rerun()
                        else:
                            st.warning("Run a scan first to get current prices.")
                with _auto_col:
                    _auto_pos = st.toggle("Auto-update (5s)", key="pos_auto_refresh",
                                          value=_ws_ok, help="Auto-refresh live P&L every 5 seconds")

                # Auto-rerun every 5s when toggle is on
                if _auto_pos:
                    # P0 audit fix — was: time.sleep(0.1) + st.rerun() blocking
                    # the worker thread on every tick. Under Streamlit Cloud
                    # health-check timeouts this could compound into 503s.
                    # The full @st.fragment(run_every=5) refactor (hoisting the
                    # live-P&L block out of page_dashboard) is queued for a P2
                    # follow-up; for now, drop the sleep — the rerun timestamp
                    # gate above already throttles to ~5s cadence without
                    # blocking the render thread.
                    import time as _time_pos
                    _pos_ts_key = "_pos_live_ts"
                    _now_pos    = _time_pos.time()
                    if _now_pos - st.session_state.setdefault(_pos_ts_key, _now_pos - 4.9) >= 5:  # APP-14: default near-now prevents immediate fire
                        st.session_state[_pos_ts_key] = _now_pos
                        st.rerun()
            else:
                st.info("No open positions.")

            st.subheader("Closed Trades History")
            if df_closed.empty:
                st.info("No closed paper trades yet.")
            else:
                p1, p2, p3 = st.columns(3)
                if 'pnl_pct' in df_closed.columns:
                    df_closed['pnl_pct'] = pd.to_numeric(df_closed['pnl_pct'], errors='coerce')
                    total_pnl = df_closed['pnl_pct'].sum()
                    wins = (df_closed['pnl_pct'] > 0).sum()
                    p1.metric("Total Trades", len(df_closed))
                    p2.metric("Win Rate", f"{wins/len(df_closed)*100:.1f}%" if len(df_closed) > 0 else "—")
                    p3.metric("Cumulative PnL %", f"{total_pnl:.2f}%")

                st.dataframe(df_closed, width='stretch', height=350)
                st.download_button("⬇ Download Paper Trades", data=df_closed.to_csv(index=False),
                                   file_name="paper_trades_log.csv", mime="text/csv",
                                   key="dl_paper_trades")

        # ── Tab 3: Feedback Log ──
        with tab_feedback:
            df_fb = _cached_feedback_df()
            if df_fb.empty:
                st.info("No feedback log data yet.")
            else:
                f1, f2 = st.columns(2)
                f1.metric("Logged Signals", len(df_fb))
                if 'confidence' in df_fb.columns:
                    avg_fb_conf = pd.to_numeric(df_fb['confidence'], errors='coerce').mean()
                    f2.metric("Avg Confidence Logged", f"{avg_fb_conf:.1f}%" if pd.notna(avg_fb_conf) else "—")

                if 'confidence' in df_fb.columns and 'timestamp' in df_fb.columns:
                    fig = px.scatter(df_fb, x='timestamp', y='confidence', color='direction',
                                     render_mode='webgl',
                                     labels={'confidence': 'Confidence (%)', 'timestamp': 'Time'})
                    fig.add_hline(y=model.HIGH_CONF_THRESHOLD, line_dash="dash", line_color="green")
                    fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0))
                    st.plotly_chart(fig, width='stretch')

                st.dataframe(df_fb, width='stretch', height=350)
                st.download_button("⬇ Download Feedback Log", data=df_fb.to_csv(index=False),
                                   file_name="feedback_log.csv", mime="text/csv",
                                   key="dl_feedback_log")

        # ── Tab 4: Execution Log ──
        with tab_exec:
            _exec_st = _exec.get_status()
            _mode_disp = "🔴 LIVE" if _exec_st.get("live_trading", False) else "📄 Paper"
            ec1, ec2, ec3 = st.columns(3)
            ec1.metric("Execution Mode", _mode_disp)
            ec2.metric("Auto-Execute", "ON" if _exec_st.get("auto_execute", False) else "OFF")
            ec3.metric("Keys Configured", "Yes" if _exec_st.get("keys_configured", False) else "No")
            st.caption("Configure execution in Config Editor → Live Execution section.")
            st.markdown("---")

            df_exec_log = _cached_execution_log_df(limit=300)
            if df_exec_log.empty:
                st.info(
                    "No execution records yet. "
                    "Use the BUY/SELL buttons in the Dashboard to place orders."
                )
            else:
                ex_m1, ex_m2, ex_m3 = st.columns(3)
                ex_m1.metric("Total Orders", len(df_exec_log))
                if "mode" in df_exec_log.columns:
                    live_cnt  = (df_exec_log["mode"] == "live").sum()
                    paper_cnt = (df_exec_log["mode"] == "paper").sum()
                    ex_m2.metric("Live Orders", int(live_cnt))
                    ex_m3.metric("Paper Orders", int(paper_cnt))

                st.dataframe(df_exec_log, width='stretch', height=400)
                st.download_button(
                    "⬇ Download Execution Log",
                    data=df_exec_log.to_csv(index=False),
                    file_name=f"execution_log_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="dl_exec_log",
                )

        # ── Tab 5: Slippage Analytics ─────────────────────────────────────────────
        with tab_slip:
            st.subheader("Post-Trade Slippage Analytics")
            st.caption("Tracks fill price vs. expected signal entry price. Lower slippage = better execution quality.")
            df_slip = _cached_execution_log_df(limit=500)
            if df_slip.empty or "slippage_pct" not in df_slip.columns:
                st.info("No slippage data yet. Slippage is tracked after each order fill.")
            else:
                df_slip_valid = df_slip[df_slip["slippage_pct"].notna()].copy()
                if df_slip_valid.empty:
                    st.info("Orders recorded but no slippage data yet. Make sure expected_price is passed when placing orders.")
                else:
                    sm1, sm2, sm3, sm4 = st.columns(4)
                    _avg_slip = df_slip_valid["slippage_pct"].mean()
                    _max_slip = df_slip_valid["slippage_pct"].max()
                    _med_slip = df_slip_valid["slippage_pct"].median()
                    _orders_n = len(df_slip_valid)
                    sm1.metric("Orders Tracked", _orders_n)
                    sm2.metric("Avg Slippage", f"{_avg_slip:.4f}%")
                    sm3.metric("Median Slippage", f"{_med_slip:.4f}%")
                    sm4.metric("Max Slippage", f"{_max_slip:.4f}%")

                    # Slippage distribution histogram
                    fig_slip = px.histogram(
                        df_slip_valid, x="slippage_pct", nbins=30,
                        title="Slippage Distribution (%)",
                        color_discrete_sequence=["#00d4aa"],
                        labels={"slippage_pct": "Slippage (%)"},
                    )
                    fig_slip.update_layout(height=280, margin=dict(l=0, r=0, t=30, b=0))
                    st.plotly_chart(fig_slip, width='stretch')

                    # Slippage by pair
                    if "pair" in df_slip_valid.columns:
                        _slip_by_pair = (
                            df_slip_valid.groupby("pair")["slippage_pct"]
                            .agg(["mean", "max", "count"])
                            .reset_index()
                            .rename(columns={"mean": "Avg %", "max": "Max %", "count": "Orders"})
                            .sort_values("Avg %", ascending=True)
                        )
                        st.dataframe(_slip_by_pair, hide_index=True, width='stretch')

                    st.download_button(
                        "⬇ Download Slippage Data",
                        data=df_slip_valid.to_csv(index=False),
                        file_name=f"slippage_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key="dl_slippage",
                    )


    elif _bt_subview == "advanced":
        if _bt_lv == 'beginner':
            st.markdown(
                '<div style="background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);'
                'border-radius:12px;padding:28px 24px;text-align:center;margin:20px 0">'
                '<div style="font-size:32px;margin-bottom:10px">\U0001f52c</div>'
                '<div style="font-size:18px;font-weight:700;color:#e2e8f0;margin-bottom:8px">'
                'Advanced Analysis Tools</div>'
                '<div style="font-size:13px;color:#9ca3af;line-height:1.6;max-width:380px;margin:0 auto">'
                'Walk-Forward Validation, Deep Backtest, and Signal Calibration are available at '
                '<strong style="color:#a78bfa">Intermediate</strong> or '
                '<strong style="color:#a78bfa">Advanced</strong> level.<br><br>'
                'Switch your experience level in the sidebar to unlock these tools.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            # Walk-forward out-of-sample validation
            st.markdown("---")
            _ui.section_header("Walk-Forward Validation",
                               "Splits OHLCV into N windows · First 60% warm-up · Last 40% out-of-sample test · Checks signal predictiveness across regimes",
                               icon="🔄")
            wf_c1, wf_c2, wf_c3 = st.columns(3)
            with wf_c1:
                wf_splits = st.number_input("Windows", 2, 8, 4, step=1, key="wf_splits")
            with wf_c2:
                wf_pair = st.selectbox("Pair", model.PAIRS, index=0, key="wf_pair")
            with wf_c3:
                wf_tf = st.selectbox("Timeframe", model.TIMEFRAMES, index=0, key="wf_tf")

            if st.button("Run Walk-Forward Validation", type="secondary", width="stretch",
                         key="btn_wf"):
                with st.spinner(f"Running {int(wf_splits)}-split walk-forward on {wf_pair} {wf_tf}... (~2 min)", show_time=True):
                    wf_res = model.run_walk_forward(n_splits=int(wf_splits), pair=wf_pair, tf=wf_tf)
                st.session_state["wf_result"] = wf_res

            wf_r = st.session_state.get("wf_result")
            if wf_r:
                if 'error' in wf_r:
                    st.error(wf_r['error'])
                else:
                    wf_cols = st.columns(2)
                    wf_cols[0].metric("Mean OOS Accuracy",
                                      f"{wf_r['mean_accuracy']}%" if wf_r['mean_accuracy'] else "—",
                                      help="Average directional accuracy across all out-of-sample test windows")
                    wf_cols[1].metric("Std Dev",
                                      f"±{wf_r['std_accuracy']}%" if wf_r['std_accuracy'] is not None else "—",
                                      help="Lower = more consistent across market regimes")
                    wf_df = pd.DataFrame(wf_r['windows'])
                    wf_df['accuracy_pct'] = wf_df['accuracy_pct'].apply(
                        lambda x: f"{x}%" if x is not None else "—"
                    )
                    st.dataframe(wf_df.rename(columns={
                        'window': 'Window', 'period': 'Period',
                        'test_signals': 'Test Signals', 'accuracy_pct': 'OOS Accuracy'
                    }).set_index('Window'), width='stretch')

                    # ── "What does this mean?" panel ───────────────────────
                    _wf_acc = wf_r.get('mean_accuracy') or 0.0
                    _wf_std = wf_r.get('std_accuracy') or 0.0
                    if _wf_acc >= 60:
                        _wfm_color = "rgba(0,212,170,0.08)"; _wfm_border = "rgba(0,212,170,0.30)"
                        _wfm_icon  = "✅"; _wfm_verdict = "Strong out-of-sample accuracy"
                        _wfm_msg   = (
                            f"Across {int(wf_splits)} separate time windows, the model correctly called direction "
                            f"<strong>{_wf_acc:.0f}%</strong> of the time on data it had never seen before. "
                            f"This is a strong result — it suggests the model isn't just memorising past data."
                        )
                    elif _wf_acc >= 50:
                        _wfm_color = "rgba(245,158,11,0.08)"; _wfm_border = "rgba(245,158,11,0.30)"
                        _wfm_icon  = "📊"; _wfm_verdict = "Acceptable accuracy"
                        _wfm_msg   = (
                            f"The model was right <strong>{_wf_acc:.0f}%</strong> of the time on unseen data — "
                            f"slightly better than random. This is acceptable but not exceptional."
                        )
                    else:
                        _wfm_color = "rgba(239,68,68,0.08)"; _wfm_border = "rgba(239,68,68,0.30)"
                        _wfm_icon  = "⚠️"; _wfm_verdict = "Below random on unseen data"
                        _wfm_msg   = (
                            f"The model only got <strong>{_wf_acc:.0f}%</strong> accuracy on unseen data — "
                            f"below the 50% you'd expect from random guessing. "
                            f"This may indicate overfitting to the training period."
                        )
                    _wf_std_msg = (
                        f"Consistency score: ±{_wf_std:.1f}% variation across windows. "
                        + ("Very consistent — the model performs reliably across different market phases."
                           if _wf_std < 8 else
                           "Some variation between windows — the model works better in some market conditions than others.")
                    )
                    st.markdown(
                        f'<div style="background:{_wfm_color};border:1px solid {_wfm_border};'
                        f'border-radius:12px;padding:16px 20px;margin:10px 0">'
                        f'<div style="font-size:13px;font-weight:700;color:#00d4aa;margin-bottom:6px">'
                        f'{_wfm_icon} What does this mean? — {_wfm_verdict}</div>'
                        f'<div style="font-size:13px;color:#94a3b8;line-height:1.6">'
                        f'{_wfm_msg}<br><br>{_wf_std_msg}'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

            # Deep OHLCV-replay backtest
            st.markdown("---")
            _ui.section_header("Deep OHLCV-Replay Backtest",
                               "True bar-by-bar simulation using paginated historical data · No lookahead bias · Proper entry/stop/target replay",
                               icon="🔬")
            db_c1, db_c2, db_c3, db_c4 = st.columns(4)
            with db_c1:
                db_pair = st.selectbox("Pair", model.PAIRS, index=0, key="db_pair")
            with db_c2:
                db_tf = st.selectbox("Timeframe", model.TIMEFRAMES, index=0, key="db_tf")
            with db_c3:
                db_years = st.number_input("Years of History", 0.5, 5.0, 2.0, step=0.5, key="db_years")
            with db_c4:
                db_pos = st.number_input("Position Size %", 2.0, 25.0, 10.0, step=1.0, key="db_pos")

            if st.button("Run Deep Backtest", type="primary", width="stretch", key="btn_deep_bt"):
                with st.spinner(f"Fetching {db_years}y of {db_pair} {db_tf} data and replaying bar-by-bar... (may take 1-3 min)", show_time=True):
                    deep_r = model.run_deep_backtest(
                        pair=db_pair, tf=db_tf, years=float(db_years), pos_pct=float(db_pos)
                    )
                st.session_state["deep_backtest_result"] = deep_r

            deep_r = st.session_state.get("deep_backtest_result")
            if deep_r:
                if deep_r.get("error"):
                    logger.warning("[Backtest] Deep backtest failed: %s", deep_r['error'])
                    st.error("Backtest failed — exchange data unavailable or insufficient history. Try a different pair, timeframe, or shorter history.")
                else:
                    m = deep_r.get("metrics", {})
                    d_cols = st.columns(5)
                    d_cols[0].metric("Total Trades",    str(m.get("total_trades", 0)))
                    d_cols[1].metric("Win Rate",         f"{m.get('win_rate', 0)}%")
                    d_cols[2].metric("Avg PnL/Trade",    f"{m.get('avg_pnl', 0)}%")
                    d_cols[3].metric("Total Return",     f"{m.get('total_return', 0)}%")
                    d_cols[4].metric("Sharpe Ratio",     str(m.get("sharpe", 0)))
                    d_cols2 = st.columns(4)
                    d_cols2[0].metric("Max Drawdown",    f"{m.get('max_drawdown', 0)}%")
                    d_cols2[1].metric("Profit Factor",   str(m.get("profit_factor", 0)))
                    d_cols2[2].metric("Final Equity",    f"${m.get('final_equity', 0):,.0f}")
                    d_cols2[3].metric("Years Tested",    str(m.get("years_tested", 0)))

                    df_dbt = deep_r.get("trades", pd.DataFrame())
                    if not df_dbt.empty:
                        # Equity curve chart
                        fig_dbt = go.Figure()
                        fig_dbt.add_trace(go.Scatter(
                            x=df_dbt['timestamp'], y=df_dbt['equity'],
                            mode='lines', name='Equity', line=dict(color='#00d4aa', width=2)
                        ))
                        fig_dbt.update_layout(
                            template=('plotly_white' if st.session_state.get("_sg_theme") == "light" else 'plotly_dark'),
                            title=f"Deep Backtest Equity Curve — {db_pair} {db_tf}",
                            height=350, showlegend=True,
                            xaxis_title="Date", yaxis_title="Equity ($)",
                        )
                        st.plotly_chart(fig_dbt, width='stretch')

                        # Trade log (first 100 rows)
                        with st.expander(f"Trade Log ({len(df_dbt)} trades)", expanded=False):
                            st.dataframe(
                                df_dbt[['timestamp', 'direction', 'confidence', 'entry', 'exit',
                                         'exit_reason', 'pnl_pct', 'pnl_usd']].head(100),
                                width='stretch'
                            )
                            csv_dbt = df_dbt.to_csv(index=False)
                            st.download_button("📥 Download Full Deep Backtest CSV", csv_dbt,
                                               f"deep_backtest_{db_pair.replace('/','')}_{db_tf}.csv",
                                               "text/csv", key="dl_deep_bt")

            # ── Signal Calibration Analytics ────────────────────────────────────────
            st.divider()
            _ui.section_header(
                "Signal Calibration",
                "How well does predicted confidence match actual win rate? Perfect calibration = diagonal line.",
                icon="🎯",
            )
            _cal_df = _cached_resolved_feedback_df(days=365)
            _cal_has = (
                not _cal_df.empty
                and "confidence" in _cal_df.columns
                and "was_correct" in _cal_df.columns
                and _cal_df["was_correct"].notna().any()
            )
            if not _cal_has:
                st.info(
                    "No resolved feedback data yet. Run scans over time — outcomes are auto-resolved "
                    "after the hold period and used to calibrate confidence scores."
                )
            else:
                _cal_df = _cal_df.dropna(subset=["confidence", "was_correct"]).copy()
                _cal_df["conf_bucket"] = ((_cal_df["confidence"] // 10) * 10).clip(0, 90).astype(int)
                _cal_summary = (
                    _cal_df.groupby("conf_bucket")
                    .agg(count=("was_correct", "count"), win_rate=("was_correct", "mean"))
                    .reset_index()
                )
                _cal_summary["win_rate_pct"] = (_cal_summary["win_rate"] * 100).round(1)
                _cal_summary["label"] = _cal_summary["conf_bucket"].astype(str) + "–" + (_cal_summary["conf_bucket"] + 10).astype(str) + "%"

                # Brier score = mean squared error between predicted prob and actual outcome
                _brier = float(((_cal_df["confidence"] / 100 - _cal_df["was_correct"]) ** 2).mean())
                # Expected Calibration Error (ECE) weighted by bucket size
                _ece_rows = []
                for _, _r in _cal_summary.iterrows():
                    _mid = (_r["conf_bucket"] + 5) / 100
                    _ece_rows.append(abs(_mid - _r["win_rate"]) * _r["count"])
                _ece = sum(_ece_rows) / len(_cal_df) if len(_cal_df) > 0 else 0.0

                _cm1, _cm2, _cm3, _cm4 = st.columns(4)
                _cm1.metric("Signals Resolved", len(_cal_df))
                _cm2.metric("Overall Win Rate", f"{_cal_df['was_correct'].mean() * 100:.1f}%")
                _cm3.metric("Brier Score", f"{_brier:.4f}", help="Lower = better. 0 = perfect, 0.25 = random")
                _cm4.metric("Calibration Error (ECE)", f"{_ece * 100:.1f}%", help="Mean absolute deviation between predicted and actual win rate")

                # Calibration bar chart
                _fig_cal = go.Figure()
                _fig_cal.add_trace(go.Bar(
                    x=_cal_summary["label"],
                    y=_cal_summary["win_rate_pct"],
                    name="Actual Win Rate",
                    marker_color=[
                        "#00d4aa" if float(r["win_rate_pct"]) >= float(r["conf_bucket"]) + 5 else "#ef4444"
                        for _, r in _cal_summary.iterrows()
                    ],
                    text=_cal_summary.apply(lambda r: f"{r['win_rate_pct']:.0f}%<br>n={int(r['count'])}", axis=1),
                    textposition="outside",
                ))
                # Perfect calibration diagonal
                _diag_x = _cal_summary["label"].tolist()
                _diag_y = [(_r["conf_bucket"] + 5) for _, _r in _cal_summary.iterrows()]
                _fig_cal.add_trace(go.Scatter(
                    x=_diag_x, y=_diag_y,
                    mode="lines", name="Perfect Calibration",
                    line=dict(color="#ffffff", width=1, dash="dot"),
                ))
                _fig_cal.update_layout(
                    template=("plotly_white" if st.session_state.get("_sg_theme") == "light" else "plotly_dark"),
                    height=340,
                    title="Confidence Bucket vs Actual Win Rate (teal = over-performing, red = under-performing)",
                    xaxis_title="Predicted Confidence", yaxis_title="Actual Win Rate (%)",
                    yaxis=dict(range=[0, 110]),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(_fig_cal, width='stretch')

                # Per-pair calibration breakdown
                with st.expander("Per-Pair Calibration Breakdown", expanded=False):
                    _pair_cal = (
                        _cal_df.groupby("pair")
                        .agg(signals=("was_correct", "count"), win_rate=("was_correct", "mean"),
                             avg_conf=("confidence", "mean"))
                        .reset_index()
                    )
                    _pair_cal["win_rate"] = (_pair_cal["win_rate"] * 100).round(1)
                    _pair_cal["avg_conf"] = _pair_cal["avg_conf"].round(1)
                    _pair_cal["diff"] = (_pair_cal["win_rate"] - _pair_cal["avg_conf"]).round(1)
                    _pair_cal.columns = ["Pair", "Signals", "Win Rate %", "Avg Confidence %", "Conf − Win Rate"]
                    st.dataframe(
                        _pair_cal.sort_values("Win Rate %", ascending=False),
                        width='stretch', hide_index=True,
                    )

            # ── Performance Attribution ────────────────────────────────────────────────
            # ── IC & WFE Quick Card (DB-based, Batch 3 #36) ───────────────────────────
            try:
                st.divider()
                _ui.section_header(
                    "IC & WFE Metrics",
                    "Information Coefficient (Spearman) and Walk-Forward Efficiency from resolved trade feedback",
                    icon="🎯",
                )
                _ic_wfe_c1, _ic_wfe_c2 = st.columns(2)
                with _ic_wfe_c1:
                    st.markdown("**Information Coefficient (IC)**")
                    if st.button("Compute IC from Feedback Log", key="btn_ic_db", width="stretch"):
                        with st.spinner("Computing Spearman IC...", show_time=True):
                            st.session_state["ic_db_result"] = _db.compute_and_save_ic(lookback_days=30)
                    _ic_db = st.session_state.get("ic_db_result")
                    if _ic_db:
                        _ic_db_val = _ic_db.get("ic")
                        _ic_db_note = _ic_db.get("ic_note")
                        if _ic_db_val is not None:
                            _ic_color = "#10b981" if _ic_db_val > 0.05 else ("#ef4444" if _ic_db_val < 0 else "#f59e0b")
                            _ic_skill = _ic_db.get("skill", "WEAK")
                            _ic_n     = _ic_db.get("n_samples", 0)
                            _ic_p     = _ic_db.get("ic_pvalue")
                            _ic_cols  = st.columns(3)
                            _ic_cols[0].metric("IC (30d)", f"{_ic_db_val:+.4f}")
                            _ic_cols[1].metric("Skill", _ic_skill)
                            _ic_cols[2].metric("n", _ic_n)
                            st.markdown(
                                f"<div style='border:1px solid {_ic_color};border-radius:8px;"
                                f"padding:8px 12px;margin-top:4px;font-size:12px;color:{_ic_color};'>"
                                f"IC = {_ic_db_val:+.4f} · <b>{_ic_skill}</b>"
                                f"{' · p=' + f'{_ic_p:.4f}' if _ic_p is not None else ''}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        elif _ic_db_note:
                            st.caption(f"IC: {_ic_db_note}")
                with _ic_wfe_c2:
                    st.markdown("**Walk-Forward Efficiency (WFE)**")
                    if st.button("Compute WFE from Backtest DB", key="btn_wfe_db", width="stretch"):
                        with st.spinner("Computing WFE from backtest trades...", show_time=True):
                            st.session_state["wfe_db_result"] = _db.compute_wfe()
                    _wfe_db = st.session_state.get("wfe_db_result")
                    if _wfe_db:
                        _wfe_db_val = _wfe_db.get("wfe")
                        _wfe_db_note = _wfe_db.get("note")
                        if _wfe_db_val is not None:
                            _wfe_grade = _wfe_db.get("grade", "POOR")
                            _wfe_color = "#10b981" if _wfe_db_val > 0.9 else ("#f59e0b" if _wfe_db_val > 0.7 else ("#f59e0b" if _wfe_db_val > 0.5 else "#ef4444"))
                            _wfe_cols2 = st.columns(3)
                            _wfe_cols2[0].metric("WFE", f"{_wfe_db_val:.3f}")
                            _wfe_cols2[1].metric("Grade", _wfe_grade)
                            _wfe_is_sharpe  = _wfe_db.get("is_sharpe")  or 0.0
                            _wfe_oos_sharpe = _wfe_db.get("oos_sharpe") or 0.0
                            _wfe_cols2[2].metric("IS Sharpe", f"{_wfe_is_sharpe:.3f}")
                            st.markdown(
                                f"<div style='border:1px solid {_wfe_color};border-radius:8px;"
                                f"padding:8px 12px;margin-top:4px;font-size:12px;color:{_wfe_color};'>"
                                f"WFE = {_wfe_db_val:.3f} · <b>{_wfe_grade}</b> · "
                                f"OOS Sharpe {_wfe_oos_sharpe:.3f}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                        elif _wfe_db_note:
                            st.caption(f"WFE: {_wfe_db_note}")
            except Exception as _ic_wfe_err:
                logger.warning("[App] IC/WFE card error: %s", _ic_wfe_err)
                st.caption("IC & WFE metrics temporarily unavailable.")

            # ── P&L Tracking Summary (Batch 8) ────────────────────────────────────────
            try:
                st.divider()
                _ui.section_header(
                    "Live P&L Tracking",
                    "Real-time signal entry/exit P&L tracked across BUY/SELL signal pairs. "
                    "Entries recorded on BUY signals; exits on matching SELL signals.",
                    icon="💰",
                )
                _pnl_sum = _db.get_pnl_summary()
                _pnl_n = _pnl_sum.get("total_trades", 0)
                if _pnl_n == 0:
                    st.info(
                        "No closed P&L trades yet. P&L entries are recorded automatically when "
                        "BUY signals are generated, and closed when matching SELL signals are detected."
                    )
                else:
                    _pnl_c1, _pnl_c2, _pnl_c3, _pnl_c4 = st.columns(4)
                    _pnl_c1.metric("Closed Trades", _pnl_n)
                    _pnl_c2.metric(
                        "Win Rate",
                        f"{_pnl_sum.get('win_rate_pct', 0):.1f}%",
                        help="% of closed trades with positive P&L",
                    )
                    _pnl_c3.metric(
                        "Avg P&L / Trade",
                        f"{_pnl_sum.get('avg_pnl_pct', 0):+.2f}%",
                        help="Mean P&L per closed trade",
                    )
                    _ann_pct = _pnl_sum.get("annualized_return_pct", 0)
                    _ann_n   = _pnl_sum.get("total_trades", 0)
                    # Show N/A when < 5 trades — CAGR is statistically unreliable below that threshold
                    _ann_val = f"{_ann_pct:+.1f}%" if _ann_n >= 5 else "—"
                    _ann_help = (
                        "CAGR over the actual calendar span of all closed trades, "
                        "floored at 30 days. Requires ≥5 closed trades to display."
                    )
                    _pnl_c4.metric("Est. Annualised Return", _ann_val, help=_ann_help)
                    _pnl_c5, _pnl_c6, _pnl_c7 = st.columns(3)
                    _pnl_c5.metric("Best Trade", f"{_pnl_sum.get('best_trade_pct', 0):+.2f}%")
                    _pnl_c6.metric("Worst Trade", f"{_pnl_sum.get('worst_trade_pct', 0):+.2f}%")
                    _pnl_c7.metric("Open Positions", _pnl_sum.get("open_positions", 0))

                    with st.expander("P&L Trade Log", expanded=False):
                        _pnl_df = _db.get_pnl_trades_df(limit=200)
                        if not _pnl_df.empty:
                            _pnl_df_disp = _pnl_df.rename(columns={
                                "pair": "Pair", "entry_signal": "Entry Signal",
                                "entry_price": "Entry $", "exit_price": "Exit $",
                                "pnl_pct": "P&L %", "holding_hours": "Held (h)",
                                "entry_time": "Entry Time", "exit_time": "Exit Time",
                            })
                            st.dataframe(
                                _pnl_df_disp.style.format({
                                    "P&L %": "{:+.2f}", "Held (h)": "{:.1f}",
                                    "Entry $": "{:.4f}", "Exit $": "{:.4f}",
                                }, na_rep="—"),
                                width='stretch',
                                hide_index=True,
                            )
                        else:
                            st.caption("No closed P&L trades in log.")
            except Exception as _pnl_err:
                logger.warning("[App] P&L card error: %s", _pnl_err)
                st.caption("P&L tracking temporarily unavailable.")

            if not df_trades.empty and "exit_reason" in df_trades.columns:
                st.divider()
                _ui.section_header(
                    "Performance Attribution",
                    "Where do wins and losses actually come from? Breaks down results by exit type, direction, and coin.",
                    icon="🔬",
                )
                _pat_col1, _pat_col2, _pat_col3 = st.columns(3)

                # ── Exit reason breakdown ────────────────────────────────────────────
                with _pat_col1:
                    st.markdown("**How did trades exit?**")
                    _exit_grp = (
                        df_trades.groupby("exit_reason")
                        .agg(
                            Trades=("pnl_pct", "count"),
                            WinRate=("pnl_pct", lambda x: round((x > 0).mean() * 100, 1)),
                            AvgPnL=("pnl_pct", lambda x: round(x.mean(), 2)),
                        )
                        .reset_index()
                        .sort_values("AvgPnL", ascending=False)
                    )
                    _exit_grp.columns = ["How It Exited", "# Trades", "Win Rate %", "Avg P&L %"]
                    _exit_label_map = {
                        "Target":       "✅ Hit Profit Target",
                        "Stop":         "❌ Hit Stop Loss",
                        "TrailingStop": "🔒 Trailing Stop",
                        "Timeout":      "⏰ Time Expired",
                    }
                    _exit_grp["How It Exited"] = _exit_grp["How It Exited"].map(
                        lambda v: _exit_label_map.get(v, v)
                    )
                    st.dataframe(_exit_grp, hide_index=True, width='stretch')
                    st.caption("Target = profitable exit. Stop = loss. Trailing Stop = stop that moved with price. Timeout = held too long.")

                # ── Buy vs Sell breakdown ───────────────────────────────────────────
                with _pat_col2:
                    st.markdown("**Buy signals vs Sell signals**")
                    _df_dir = df_trades.copy()
                    _df_dir["Signal Type"] = _df_dir["direction"].apply(
                        lambda d: "📈 Buy / Long" if "BUY" in str(d).upper() else "📉 Sell / Short"
                    )
                    _dir_grp = (
                        _df_dir.groupby("Signal Type")
                        .agg(
                            Trades=("pnl_pct", "count"),
                            WinRate=("pnl_pct", lambda x: round((x > 0).mean() * 100, 1)),
                            AvgPnL=("pnl_pct", lambda x: round(x.mean(), 2)),
                            TotalPnL=("pnl_pct", lambda x: round(x.sum(), 1)),
                        )
                        .reset_index()
                    )
                    _dir_grp.columns = ["Signal Type", "# Trades", "Win Rate %", "Avg P&L %", "Total P&L %"]
                    st.dataframe(_dir_grp, hide_index=True, width='stretch')
                    st.caption("Shows whether the model performs better on buy or sell signals historically.")

                # ── Per-coin breakdown ──────────────────────────────────────────────
                with _pat_col3:
                    st.markdown("**Which coins performed best?**")
                    _coin_grp = (
                        df_trades.groupby("pair")
                        .agg(
                            Trades=("pnl_pct", "count"),
                            WinRate=("pnl_pct", lambda x: round((x > 0).mean() * 100, 1)),
                            AvgPnL=("pnl_pct", lambda x: round(x.mean(), 2)),
                        )
                        .reset_index()
                        .sort_values("AvgPnL", ascending=False)
                    )
                    _coin_grp.columns = ["Coin", "# Trades", "Win Rate %", "Avg P&L %"]
                    st.dataframe(_coin_grp, hide_index=True, width='stretch', height=220)
                    st.caption("Sorted by average P&L per trade. Top = best historical performers for this model.")

            # ── IC Score (Information Coefficient) ────────────────────────────────────
            st.markdown("---")
            _ui.section_header("Signal Quality — Information Coefficient (IC)",
                               "Spearman rank correlation between signal confidence scores and actual future returns. "
                               "IC > 0.05 = modest edge · IC > 0.10 = strong signal quality",
                               icon="🎯")
            _ic_c1, _ic_c2, _ic_c3 = st.columns(3)
            with _ic_c1:
                _ic_pair = st.selectbox("Pair", model.PAIRS, index=0, key="ic_pair")
            with _ic_c2:
                _ic_tf = st.selectbox("Timeframe", model.TIMEFRAMES, index=0, key="ic_tf")
            with _ic_c3:
                _ic_hold = st.number_input("Hold Bars", 1, 20, 5, step=1, key="ic_hold",
                                           help="How many bars ahead to measure the return")
            if st.button("Compute IC Score", type="secondary", width="stretch", key="btn_ic"):
                with st.spinner(f"Computing IC on {_ic_pair} {_ic_tf}... (~1 min)", show_time=True):
                    _ic_res = model.compute_ic_score(pair=_ic_pair, tf=_ic_tf, hold_bars=int(_ic_hold))
                st.session_state["ic_result"] = _ic_res
            _ic_r = st.session_state.get("ic_result")
            if _ic_r:
                if "error" in _ic_r and not _ic_r.get("ic"):
                    logger.warning("[IC] IC score failed: %s", _ic_r['error'])
                    st.error("IC computation failed — insufficient data or exchange unavailable. Try a different pair or timeframe.")
                else:
                    _ic_val   = _ic_r.get("ic", 0) or 0
                    _ic_label = _ic_r.get("ic_label", "—")
                    _ic_n     = _ic_r.get("n_samples", 0)
                    _ic_p     = _ic_r.get("p_value")
                    _ic_color = "#10b981" if _ic_val > 0.05 else ("#ef4444" if _ic_val < 0 else "#f59e0b")
                    _ic_cols  = st.columns(4)
                    _ic_cols[0].metric("IC Score", f"{_ic_val:.4f}")
                    _ic_cols[1].metric("Signal Quality", _ic_label)
                    _ic_cols[2].metric("Samples", _ic_n)
                    _ic_cols[3].metric("p-value", f"{_ic_p:.4f}" if _ic_p is not None else "—")
                    st.markdown(
                        f"<div style='border:1px solid {_ic_color};border-radius:8px;"
                        f"padding:10px 14px;margin-top:8px;font-size:13px;color:{_ic_color};'>"
                        f"<b>{_ic_label}</b> — IC = {_ic_val:+.4f} "
                        f"({'p < 0.05 — statistically significant' if (_ic_p or 1) < 0.05 else 'not statistically significant'})</div>",
                        unsafe_allow_html=True,
                    )

            # ── WFE Score (Walk Forward Efficiency) ───────────────────────────────────
            st.markdown("---")
            _ui.section_header("Signal Quality — Walk Forward Efficiency (WFE)",
                               "OOS accuracy ÷ IS accuracy across N time windows. "
                               "WFE > 0.8 = excellent generalisation · WFE < 0.5 = likely overfit",
                               icon="🔄")
            _wfe_c1, _wfe_c2, _wfe_c3 = st.columns(3)
            with _wfe_c1:
                _wfe_pair = st.selectbox("Pair", model.PAIRS, index=0, key="wfe_pair")
            with _wfe_c2:
                _wfe_tf = st.selectbox("Timeframe", model.TIMEFRAMES, index=0, key="wfe_tf")
            with _wfe_c3:
                _wfe_splits = st.number_input("Splits", 2, 6, 4, step=1, key="wfe_splits",
                                              help="Number of time windows to walk forward through")
            if st.button("Compute WFE Score", type="secondary", width="stretch", key="btn_wfe"):
                with st.spinner(f"Computing WFE on {_wfe_pair} {_wfe_tf} ({int(_wfe_splits)} splits)... (~2 min)", show_time=True):
                    _wfe_res = model.compute_wfe_score(pair=_wfe_pair, tf=_wfe_tf, n_splits=int(_wfe_splits))
                st.session_state["wfe_result"] = _wfe_res
            _wfe_r = st.session_state.get("wfe_result")
            if _wfe_r:
                if "error" in _wfe_r and not _wfe_r.get("wfe"):
                    logger.warning("[WFE] WFE score failed: %s", _wfe_r['error'])
                    st.error("Walk-forward efficiency computation failed — insufficient data or exchange unavailable. Try a different pair or timeframe.")
                else:
                    _wfe_val   = _wfe_r.get("wfe", 0) or 0
                    _wfe_label = _wfe_r.get("wfe_label", "—")
                    _wfe_is    = _wfe_r.get("is_accuracy", 0)
                    _wfe_oos   = _wfe_r.get("oos_accuracy", 0)
                    _wfe_color = "#10b981" if _wfe_val >= 0.8 else ("#f59e0b" if _wfe_val >= 0.5 else "#ef4444")
                    _wfe_cols  = st.columns(4)
                    _wfe_cols[0].metric("WFE", f"{_wfe_val:.3f}")
                    _wfe_cols[1].metric("Assessment", _wfe_label.replace("_", " "))
                    _wfe_cols[2].metric("IS Accuracy", f"{_wfe_is:.1f}%")
                    _wfe_cols[3].metric("OOS Accuracy", f"{_wfe_oos:.1f}%")
                    st.markdown(
                        f"<div style='border:1px solid {_wfe_color};border-radius:8px;"
                        f"padding:10px 14px;margin-top:8px;font-size:13px;color:{_wfe_color};'>"
                        f"<b>{_wfe_label.replace('_',' ')}</b> — WFE = {_wfe_val:.3f} "
                        f"(OOS {_wfe_oos:.1f}% / IS {_wfe_is:.1f}%) · "
                        f"{'Model generalises well to unseen data.' if _wfe_val >= 0.8 else 'Acceptable generalisation.' if _wfe_val >= 0.5 else 'Potential overfit — reduce indicator complexity.'}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            # ── Walk-Forward Rolling Window Optimization (#51) ─────────────────────────
            st.markdown("---")
            _ui.section_header(
                "Walk-Forward Rolling Window Optimization",
                "Finds optimal BUY confidence threshold by testing 50–80% across rolling windows of resolved signals",
                icon="⚙️",
            )
            try:
                _wfo_c1, _wfo_c2 = st.columns([1, 3])
                with _wfo_c1:
                    _wfo_lb = st.number_input("Lookback Days", min_value=30, max_value=180,
                                              value=90, step=10, key="wfo_lookback_days")
                    _wfo_nw = st.number_input("Windows", min_value=2, max_value=8,
                                              value=4, step=1, key="wfo_n_windows")
                    if st.button("Run WFO", type="primary", width="stretch", key="btn_wfo_db"):
                        with st.spinner(f"Running {int(_wfo_nw)}-window WFO ({int(_wfo_lb)}d lookback)...", show_time=True):
                            st.session_state["wfo_opt_result"] = _db.run_walkforward_optimization(
                                lookback_days=int(_wfo_lb), n_windows=int(_wfo_nw)
                            )
                with _wfo_c2:
                    # Show cached result if available, or try to load from DB
                    _wfo_r = st.session_state.get("wfo_opt_result")
                    if _wfo_r is None:
                        _wfo_r = _db.get_latest_wfo_result()
                    if _wfo_r and not _wfo_r.get("error"):
                        _opt_t   = _wfo_r.get("optimal_threshold", 65.0)
                        _avg_oos = _wfo_r.get("avg_oos_win_rate")
                        _rec     = _wfo_r.get("recommendation", "")
                        _wfo_m1, _wfo_m2, _wfo_m3 = st.columns(3)
                        _wfo_m1.metric("Optimal BUY Threshold", f"{int(_opt_t)}%",
                                       help="Confidence threshold that maximized win rate in IS periods")
                        _wfo_m2.metric("Avg OOS Win Rate",
                                       f"{_avg_oos:.1f}%" if _avg_oos is not None else "—",
                                       help="Average win rate in out-of-sample test periods")
                        _wfo_m3.metric("Windows Used", _wfo_r.get("n_windows", "—"))
                        if _rec:
                            st.info(_rec)
                        _wfo_wr_data = _wfo_r.get("window_results", [])
                        if _wfo_wr_data:
                            _wfo_df = pd.DataFrame(_wfo_wr_data)
                            _disp_cols = [c for c in ["window", "optimal_thresh", "is_win_rate", "oos_win_rate", "oos_buy_signals"] if c in _wfo_df.columns]
                            if _disp_cols:
                                st.dataframe(
                                    _wfo_df[_disp_cols].rename(columns={
                                        "window": "Window", "optimal_thresh": "IS Best Threshold (%)",
                                        "is_win_rate": "IS Win Rate (%)", "oos_win_rate": "OOS Win Rate (%)",
                                        "oos_buy_signals": "OOS BUY Signals",
                                    }),
                                    width='stretch', hide_index=True,
                                )
                    elif _wfo_r and _wfo_r.get("error"):
                        st.caption(f"WFO: {_wfo_r.get('recommendation', _wfo_r.get('error', ''))}")
                    else:
                        st.caption("Click **Run WFO** to find the optimal confidence threshold for BUY signals.")
            except Exception as _wfo_err:
                logger.warning("[App] WFO card error: %s", _wfo_err)
                st.caption("Walk-Forward Optimization temporarily unavailable.")

            # ── Walk-Forward Validation Details (#90) ─────────────────────────────────
            st.markdown("---")
            with st.expander("Walk-Forward Validation Details", expanded=False):
                try:
                    _wfv_c1, _wfv_c2 = st.columns([1, 3])
                    with _wfv_c1:
                        _wfv_nw = st.number_input(
                            "Windows", min_value=4, max_value=12, value=8, step=1,
                            key="wfv_n_windows",
                            help="Number of rolling windows to divide backtest history into",
                        )
                        if st.button("Run WFE Validation", type="primary",
                                     width="stretch", key="btn_wfv"):
                            with st.spinner("Computing WFE validation across windows...", show_time=True):
                                st.session_state["wfv_result"] = _db.run_detailed_wfe_validation(
                                    n_windows=int(_wfv_nw)
                                )
                    with _wfv_c2:
                        _wfv_r = st.session_state.get("wfv_result")
                        if _wfv_r is None:
                            st.caption("Click **Run WFE Validation** to analyse model stability across rolling windows.")
                        elif _wfv_r.get("error"):
                            st.caption(f"WFE Validation: {_wfv_r.get('recommendation', _wfv_r.get('error', ''))}")
                        else:
                            # ── Summary badges ────────────────────────────────────────
                            _wfv_grade   = _wfv_r.get("grade", "POOR")
                            _wfv_avg_wfe = _wfv_r.get("avg_wfe")
                            _wfv_stab    = _wfv_r.get("stability_score")
                            _wfv_oos_sh  = _wfv_r.get("avg_oos_sharpe")
                            _wfv_oos_wr  = _wfv_r.get("avg_oos_win_rate")
                            _grade_color = {
                                "EXCELLENT": "#10b981",
                                "GOOD":      "#10b981",
                                "FAIR":      "#f59e0b",
                                "POOR":      "#ef4444",
                            }.get(_wfv_grade, "#6b7280")

                            _wfv_m1, _wfv_m2, _wfv_m3, _wfv_m4 = st.columns(4)
                            _wfv_m1.metric("Avg WFE", f"{_wfv_avg_wfe:.3f}" if _wfv_avg_wfe is not None else "—",
                                           help="Average Walk-Forward Efficiency across all windows. >0.7 = good.")
                            _wfv_m2.metric("Grade", _wfv_grade,
                                           help="EXCELLENT≥0.9 · GOOD≥0.7 · FAIR≥0.5 · POOR<0.5")
                            _wfv_m3.metric("Stability Score", f"{_wfv_stab:.3f}" if _wfv_stab is not None else "—",
                                           help="Std dev of WFE across windows. Lower = more consistent.")
                            _wfv_m4.metric("Avg OOS Win Rate", f"{_wfv_oos_wr:.1f}%" if _wfv_oos_wr is not None else "—")

                            # Recommendation banner
                            _wfv_rec = _wfv_r.get("recommendation", "")
                            if _wfv_rec:
                                st.markdown(
                                    f"<div style='border:1px solid {_grade_color};border-radius:8px;"
                                    f"padding:10px 14px;margin:8px 0;font-size:13px;color:{_grade_color};'>"
                                    f"<b>{_wfv_grade}</b> — {_wfv_rec}"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )

                            _wfv_windows = _wfv_r.get("windows", [])
                            if _wfv_windows:
                                _wfv_ids     = [w["window_id"]   for w in _wfv_windows]
                                _wfv_is_sh   = [w["is_sharpe"]   for w in _wfv_windows]
                                _wfv_oos_sh2 = [w["oos_sharpe"]  for w in _wfv_windows]
                                _wfv_wfes    = [w["wfe"]         for w in _wfv_windows]

                                # ── Line chart: IS Sharpe vs OOS Sharpe ──────────────
                                _wfv_line = go.Figure()
                                _wfv_line.add_trace(go.Scatter(
                                    x=_wfv_ids, y=_wfv_is_sh,
                                    name="IS Sharpe",
                                    mode="lines+markers",
                                    line=dict(color="#00d4aa", width=2),
                                    marker=dict(size=7),
                                ))
                                _wfv_line.add_trace(go.Scatter(
                                    x=_wfv_ids, y=_wfv_oos_sh2,
                                    name="OOS Sharpe",
                                    mode="lines+markers",
                                    line=dict(color="#2dd4bf", width=2, dash="dot"),
                                    marker=dict(size=7),
                                ))
                                _wfv_line.update_layout(
                                    title="IS Sharpe vs OOS Sharpe per Window",
                                    height=240,
                                    margin=dict(l=10, r=10, t=36, b=10),
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    font=dict(color="#f8fafc", size=11),
                                    legend=dict(orientation="h", y=1.12, x=0),
                                    xaxis=dict(title="Window", dtick=1, gridcolor="#1f2937"),
                                    yaxis=dict(title="Sharpe", gridcolor="#1f2937"),
                                )
                                st.plotly_chart(_wfv_line, width='stretch',
                                                config={"displayModeBar": False})

                                # ── Bar chart: WFE ratio per window ──────────────────
                                _wfv_bar_colors = [
                                    "#10b981" if w >= 0.7 else ("#f59e0b" if w >= 0.5 else "#ef4444")
                                    for w in _wfv_wfes
                                ]
                                _wfv_bar = go.Figure(go.Bar(
                                    x=_wfv_ids,
                                    y=_wfv_wfes,
                                    marker_color=_wfv_bar_colors,
                                    text=[f"{w:.2f}" for w in _wfv_wfes],
                                    textposition="outside",
                                ))
                                _wfv_bar.add_hline(y=0.7, line_dash="dot", line_color="#10b981",
                                                   annotation_text="Good (0.7)", annotation_position="right")
                                _wfv_bar.add_hline(y=0.5, line_dash="dot", line_color="#f59e0b",
                                                   annotation_text="Fair (0.5)", annotation_position="right")
                                _wfv_bar.update_layout(
                                    title="WFE Ratio per Window  (green ≥0.7 · yellow ≥0.5 · red <0.5)",
                                    height=220,
                                    margin=dict(l=10, r=80, t=36, b=10),
                                    paper_bgcolor="rgba(0,0,0,0)",
                                    plot_bgcolor="rgba(0,0,0,0)",
                                    font=dict(color="#f8fafc", size=11),
                                    xaxis=dict(title="Window", dtick=1, gridcolor="#1f2937"),
                                    yaxis=dict(title="WFE", range=[0, max(max(_wfv_wfes) * 1.2, 1.1)],
                                               gridcolor="#1f2937"),
                                    showlegend=False,
                                )
                                st.plotly_chart(_wfv_bar, width='stretch',
                                                config={"displayModeBar": False})

                                # ── Per-window detail table ───────────────────────────
                                _wfv_tbl = pd.DataFrame([{
                                    "Window":       w["window_id"],
                                    "Start":        w["start_date"],
                                    "End":          w["end_date"],
                                    "IS Sharpe":    w["is_sharpe"],
                                    "OOS Sharpe":   w["oos_sharpe"],
                                    "WFE":          w["wfe"],
                                    "IS Win %":     w["is_win_rate"],
                                    "OOS Win %":    w["oos_win_rate"],
                                    "Opt Thresh %": int(w["optimal_threshold"]),
                                    "IS Trades":    w["n_trades_is"],
                                    "OOS Trades":   w["n_trades_oos"],
                                } for w in _wfv_windows])
                                st.dataframe(_wfv_tbl, hide_index=True, width='stretch')

                except Exception as _wfv_err:
                    logger.warning("[App] WFE validation error: %s", _wfv_err)
                    st.caption("WFE validation temporarily unavailable.")

            # ── Stress Test ────────────────────────────────────────────────────────────
            # _render_stress_test defined immediately below (must precede its call)
            def _render_stress_test():
                """Render the historical stress test section inside Backtest Viewer."""
                if _stress_mod is None:
                    st.caption("stress_test.py not available")
                    return

                st.markdown("---")
                _ui.section_header("Historical Stress Test", "Replay actual crisis periods to estimate portfolio performance", icon="🔥")

                _sc1, _sc2, _sc3 = st.columns([3, 2, 2])
                with _sc1:
                    _scenario_opts = list(_stress_mod.STRESS_SCENARIOS.keys())
                    _scenario_labels = {k: v["label"] for k, v in _stress_mod.STRESS_SCENARIOS.items()}
                    _sel_scenario = st.selectbox(
                        "Select Scenario",
                        options=_scenario_opts,
                        format_func=lambda k: _scenario_labels[k],
                        key="stress_scenario_select",
                    )
                with _sc2:
                    _stress_pos_pct = st.number_input(
                        "Position Size (%)", min_value=1.0, max_value=100.0, value=20.0, step=1.0,
                        key="stress_pos_pct",
                    )
                with _sc3:
                    _stress_dir = st.selectbox("Assumed Direction", ["BUY", "SELL"], key="stress_dir")

                _sc_meta = _stress_mod.STRESS_SCENARIOS.get(_sel_scenario, {})
                st.caption(
                    f"**Period:** {_sc_meta.get('start','')} → {_sc_meta.get('end','')}  |  "
                    f"**Known BTC DD:** {_sc_meta.get('known_btc_drawdown',0):.1f}%  |  "
                    f"{_sc_meta.get('description','')}"
                )

                if st.button("▶ Run Stress Test", key="run_stress_btn", type="primary"):
                    with st.spinner("Fetching historical OHLCV and simulating...", show_time=True):
                        try:
                            import crypto_model_core as _cm
                            _stress_res = _stress_mod.run_stress_test(
                                pairs=_cm.PAIRS,
                                scenario_key=_sel_scenario,
                                position_pct=_stress_pos_pct,
                                default_direction=_stress_dir,
                            )
                            st.session_state["stress_results"] = _stress_res
                        except Exception as _se:
                            logger.warning("[Stress] test failed: %s", _se)
                            st.error("Stress test could not complete — try a different scenario or refresh the page.")

                _stress_data = st.session_state.get("stress_results")
                if _stress_data and isinstance(_stress_data, dict) and "portfolio" in _stress_data:
                    _p = _stress_data["portfolio"]
                    _s = _stress_data.get("scenario", {})
                    st.subheader(f"Results: {_s.get('label', _sel_scenario)}")

                    _sp1, _sp2, _sp3, _sp4, _sp5 = st.columns(5)
                    _sp1.metric("Portfolio Return", f"{_p.get('portfolio_return', 0):+.2f}%")
                    _sp2.metric("Total P&L", f"${_p.get('total_pnl_usd', 0):+,.0f}")
                    _sp3.metric("Worst Drawdown", f"{_p.get('worst_drawdown_pct', 0):.2f}%")
                    _sp4.metric("Win Rate", f"{_p.get('win_rate', 0):.1f}%")
                    _sp5.metric("Pairs Tested", _p.get("total_pairs", 0))

                    # Per-pair results table
                    _pair_rows = []
                    for _pr, _metrics in _stress_data.get("results", {}).items():
                        if _metrics.get("error"):
                            _pair_rows.append({"Pair": _pr, "Return %": "—", "P&L $": "—",
                                               "Max DD %": "—", "Vol Ann %": "—", "Status": "No data"})
                        else:
                            _pair_rows.append({
                                "Pair": _pr,
                                "Return %": round(_metrics.get("price_return_pct", 0), 2),
                                "P&L $": round(_metrics.get("pnl_usd", 0), 2),
                                "Max DD %": round(_metrics.get("max_drawdown_pct", 0), 2),
                                "Vol Ann %": round(_metrics.get("vol_ann_pct", 0), 2),
                                "Status": "OK",
                            })
                    if _pair_rows:
                        _stress_df = pd.DataFrame(_pair_rows)
                        st.dataframe(_stress_df, hide_index=True, width='stretch')

                    # ── "What does this mean?" panel (all levels) ─────────────
                    _st_ret  = float(_p.get('portfolio_return', 0))
                    _st_dd   = abs(float(_p.get('worst_drawdown_pct', 0)))
                    _st_wr   = float(_p.get('win_rate', 0))
                    _st_lbl  = _s.get('label', _sel_scenario)
                    if _st_ret > 0:
                        _stm_color = "rgba(0,212,170,0.08)"; _stm_border = "rgba(0,212,170,0.30)"
                        _stm_icon  = "✅"; _stm_verdict = "The model would have stayed profitable"
                        _stm_msg   = f"Your simulated portfolio <strong>gained {_st_ret:+.1f}%</strong> during the {_st_lbl} crisis. This suggests the model can generate positive returns even in severe market downturns."
                    elif _st_ret > -10:
                        _stm_color = "rgba(245,158,11,0.08)"; _stm_border = "rgba(245,158,11,0.30)"
                        _stm_icon  = "📊"; _stm_verdict = "The model held up reasonably well"
                        _stm_msg   = f"Your portfolio <strong>lost {abs(_st_ret):.1f}%</strong> during {_st_lbl}. Losses were limited — the model helped reduce the impact compared to holding through the crash."
                    else:
                        _stm_color = "rgba(239,68,68,0.08)"; _stm_border = "rgba(239,68,68,0.30)"
                        _stm_icon  = "⚠️"; _stm_verdict = "The model took significant losses"
                        _stm_msg   = f"Your portfolio <strong>lost {abs(_st_ret):.1f}%</strong> during {_st_lbl}. This was a severe crisis — even most professional funds lost heavily. Consider smaller position sizes during extreme uncertainty."
                    _st_risk_msg = (
                        f"The worst single drawdown was <strong>{_st_dd:.1f}%</strong>. "
                        + ("That's manageable — the model recovered well." if _st_dd < 20
                           else "That's significant — in real trading, keep position sizes small in volatile markets.")
                    )
                    _stm_lv = st.session_state.get("user_level", "beginner")
                    st.markdown(
                        f'<div style="background:{_stm_color};border:1px solid {_stm_border};'
                        f'border-radius:12px;padding:16px 20px;margin:12px 0">'
                        f'<div style="font-size:13px;font-weight:700;color:#00d4aa;margin-bottom:6px">'
                        f'{_stm_icon} What does this mean? — {_stm_verdict}</div>'
                        f'<div style="font-size:13px;color:#94a3b8;line-height:1.6">'
                        f'{_stm_msg}<br><br>{_st_risk_msg}'
                        + (f'<br><br><em>Win rate of <strong>{_st_wr:.0f}%</strong> means the model picked the right direction '
                           f'on {_st_wr:.0f}% of pairs during this period.</em>'
                           if _stm_lv != "beginner" else "")
                        + f'</div></div>',
                        unsafe_allow_html=True,
                    )

            _render_stress_test()


def _run_backtest_thread():
    """Background backtest thread — writes only to _bt_state (never st.session_state)."""
    with _bt_lock:
        _bt_state["running"] = True
        _bt_state["results"] = None
        _bt_state["error"] = None
    try:
        result = model.run_backtest()
        with _bt_lock:
            _bt_state["results"] = result
    except Exception as e:
        with _bt_lock:
            _bt_state["error"] = str(e)
    finally:
        with _bt_lock:
            _bt_state["running"] = False


def _start_backtest():
    st.session_state["backtest_running"] = True
    st.session_state["backtest_error"] = None
    t = threading.Thread(target=_run_backtest_thread, daemon=True)
    t.start()

# ──────────────────────────────────────────────
# PAGE 4: TRADE LOG & HISTORY
# ──────────────────────────────────────────────
# ──────────────────────────────────────────────
# PAGE: ARBITRAGE
# ──────────────────────────────────────────────
def page_arbitrage():
    """C4 (2026-04-29): Arbitrage is now a sub-view of the Backtester
    page (per Phase C plan §C4). This function is kept alive as a
    deprecation stub so any inbound deep links / programmatic jumps to
    `page=="Arbitrage"` still land somewhere sensible — it sets the
    Backtester view state to `arbitrage` and renders Backtester, which
    detects the state and pivots to the Arbitrage view."""
    st.session_state["bt_view"] = "arbitrage"
    page_backtest()


def _render_arbitrage_view():
    """Arbitrage scanner content (formerly page_arbitrage). Called from
    page_backtest when the primary segmented control is on Arbitrage.

    Note: this helper does NOT render its own topbar / page_header —
    those are owned by page_backtest now since Arbitrage shares the
    Backtester page surface.
    """
    _arb_lv = st.session_state.get("user_level", "beginner")

    # ── Controls ──
    col_btn, col_thresh, col_spacer = st.columns([1, 1, 4])
    with col_btn:
        run_scan = st.button("🔍 Scan Now", key="watch_btn_scan_now", width="stretch", type="primary")
    with col_thresh:
        min_net = st.number_input(
            "Min Net Spread %",
            min_value=0.0, max_value=5.0,
            value=_arb.MIN_NET_SPREAD_PCT,
            step=0.05, format="%.2f",
        )
        _arb.MIN_NET_SPREAD_PCT = min_net

    # ── Run scan ──
    if run_scan:
        with st.spinner("Fetching prices from OKX, KuCoin, Kraken, Gate.io …", show_time=True):
            arb_results = _arb.scan_all_arb(model.PAIRS)
        st.session_state["arb_results"]    = arb_results
        st.session_state["arb_run_ts"]     = time.time()
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        st.session_state["arb_ts"] = ts
        st.success(f"Scan complete — {ts}")

    # Item 17: Freshness dot for arb data
    _arb_run_ts = st.session_state.get("arb_run_ts")
    st.markdown(
        _ui.freshness_dot_html(_arb_run_ts, max_age_sec=300, label="Opportunity data"),
        unsafe_allow_html=True,
    )

    arb_results = st.session_state.get("arb_results")
    if not arb_results:
        st.info("Press **Scan Now** to detect arbitrage opportunities across exchanges.")
        # Show DB history if any
        hist_df = _cached_arb_opportunities_df(limit=50)
        if not hist_df.empty:
            st.subheader("Recent Opportunities (DB)")
            st.dataframe(hist_df, width='stretch', hide_index=True)
        return

    # ── Spot Arbitrage ──
    st.subheader("📊 Spot Price Spread")
    spot = arb_results.get("spot", [])
    if spot:
        opp_rows = [r for r in spot if r["signal"] == "OPPORTUNITY"]
        mar_rows = [r for r in spot if r["signal"] == "MARGINAL"]
        no_rows  = [r for r in spot if r["signal"] == "NO_ARB"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Pairs Scanned",    len(spot))
        # P2 audit fix — was `delta=f"+{len(opp_rows)}"` which is just
        # the count of itself; rendered a green up-arrow that didn't
        # convey any information. Removed the delta (single-value
        # metric is cleaner).
        m2.metric("Opportunities",    len(opp_rows))
        m3.metric("Marginal",         len(mar_rows))
        m4.metric("No Arb",           len(no_rows))

        # Build display table
        rows = []
        for r in spot:
            sig_icon = {"OPPORTUNITY": "🟢", "MARGINAL": "🟡", "NO_ARB": "🔴"}.get(r["signal"], "")
            prices_str = " | ".join(
                f"{ex}: ${p:,.2f}" for ex, p in sorted(r["prices"].items())
            ) if r["prices"] else "—"
            rows.append({
                "Pair":            r["pair"],
                "Signal":          f"{sig_icon} {r['signal']}",
                "Buy On":          r["buy_exchange"] or "—",
                "Sell On":         r["sell_exchange"] or "—",
                "Buy Price":       f"${r['buy_price']:,.4f}"  if r["buy_price"]  else "—",
                "Sell Price":      f"${r['sell_price']:,.4f}" if r["sell_price"] else "—",
                "Gross Spread %":  f"{r['gross_spread_pct']:.4f}%",
                "Fees %":          f"{r['fees_pct']:.4f}%",
                "Net Spread %":    f"{r['net_spread_pct']:.4f}%",
                "Exchanges Live":  r["n_exchanges"],
                "All Prices":      prices_str,
            })

        spot_df = pd.DataFrame(rows)

        def _color_signal(val: str) -> str:
            if "OPPORTUNITY" in val: return "color: #00d4aa; font-weight:bold"
            if "MARGINAL"    in val: return "color: #f59e0b"
            return "color: #888"

        def _color_net(val: str) -> str:
            try:
                v = float(val.replace("%", ""))
                if v >= _arb.MIN_NET_SPREAD_PCT: return "color: #00d4aa; font-weight:bold"
                if v >= 0:                        return "color: #f59e0b"
                return "color: #ef4444"
            except Exception:
                return ""

        st.dataframe(
            spot_df.style
                .map(_color_signal, subset=["Signal"])
                .map(_color_net,    subset=["Net Spread %"]),
            width='stretch',
            hide_index=True,
        )
        _csv_button(spot_df, "arb_spot_spreads.csv", key="csv_arb_spot")

        # Detail expanders for each opportunity
        if opp_rows:
            if _arb_lv in ("beginner", "intermediate"):
                # Item 13: plain-English story cards
                st.markdown("#### 🟢 Active Opportunities")
                for r in opp_rows:
                    st.markdown(
                        _ui.arb_opportunity_story_html(
                            pair          = r["pair"],
                            buy_ex        = r["buy_exchange"] or "?",
                            sell_ex       = r["sell_exchange"] or "?",
                            net_spread_pct= r["net_spread_pct"],
                            buy_price     = r["buy_price"] or 0,
                            sell_price    = r["sell_price"] or 0,
                        ),
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown("#### Active Opportunities")
                for r in opp_rows:
                    with st.expander(
                        f"🟢 {r['pair']}  →  Buy {r['buy_exchange']}  Sell {r['sell_exchange']}  "
                        f"| Net {r['net_spread_pct']:.4f}%",
                        expanded=True,
                    ):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Buy Exchange",  r["buy_exchange"])
                        c2.metric("Sell Exchange", r["sell_exchange"])
                        c3.metric("Gross Spread",  f"{r['gross_spread_pct']:.4f}%")
                        c4.metric("Net Spread",    f"{r['net_spread_pct']:.4f}%")
                        st.caption(
                            f"Buy at ${r['buy_price']:,.4f} on {r['buy_exchange']}, "
                            f"sell at ${r['sell_price']:,.4f} on {r['sell_exchange']}. "
                            f"Round-trip fees: {r['fees_pct']:.4f}%."
                        )
    else:
        st.info("No spot prices returned — check network connectivity.")

    st.markdown("---")

    # ── Funding-Rate Carry Trades ──
    st.subheader("💰 Funding-Rate Carry Trades")
    funding = arb_results.get("funding", [])
    if funding:
        f_rows = []
        for opp in funding:
            rate = opp.get("funding_rate_pct", 0)
            f_rows.append({
                "Pair":             opp["pair"],
                "Exchange":         opp.get("exchange", "—").upper(),
                "Funding Rate %":   f"{rate:+.4f}%",
                "Direction":        opp.get("direction", "—"),
                "Strategy":         opp.get("strategy", "—"),
                "Annualized Yield": f"{opp.get('annualized_yield', 0):.1f}%",
            })
        f_df = pd.DataFrame(f_rows)

        st.dataframe(f_df, width='stretch', hide_index=True)
        _csv_button(f_df, "arb_funding_carry.csv", key="csv_arb_funding")
        st.caption(
            "**Strategy**: Collect funding payments by holding opposite spot + perp positions. "
            "Positive funding → Short Perp + Long Spot. "
            "Negative funding → Long Perp + Short Spot. "
            "Net-delta-neutral; no directional exposure."
        )
    else:
        st.info("No funding-rate opportunities found above threshold.")

    st.markdown("---")

    # ── Historical log ──
    with st.expander("📋 Historical Arbitrage Log (DB)", expanded=False):
        hist_df = _cached_arb_opportunities_df(limit=100)
        if not hist_df.empty:
            st.dataframe(hist_df, width='stretch', hide_index=True)
            csv_data = hist_df.to_csv(index=False)
            st.download_button(
                "⬇ Download CSV",
                data=csv_data,
                file_name="arb_opportunities.csv",
                mime="text/csv",
                key="dl_arb_csv",
            )
        else:
            st.info("No historical records yet — run a scan to populate.")

    with st.expander("📡 Funding Rate Monitor", expanded=False):
        st.caption(
            "Compare perpetual funding rates across OKX, Binance, Bybit, KuCoin. "
            "Positive = longs paying shorts (bearish). Negative = bullish. "
            "High rates signal carry trade opportunities."
        )
        _df = data_feeds

        # ── Funding Rate Monitor ─────────────────────────────────────────────────
        _ui.section_header(
            "Funding Rate Monitor",
            "Compare perpetual funding rates across OKX · Binance · Bybit · KuCoin — "
            "positive = longs paying shorts (bearish); negative = bullish",
            icon="📡",
        )

        fr_col1, fr_col2 = st.columns([4, 1])
        with fr_col1:
            fr_pairs_sel = st.multiselect(
                "Pairs to monitor",
                model.PAIRS,
                default=model.PAIRS[:8],
                key="fr_pairs_select",
            )
        with fr_col2:
            st.write("")
            st.write("")
            run_fr = st.button(
                "🔍 Load Rates", type="primary",
                width="stretch", key="run_fr_btn",
            )

        if run_fr and fr_pairs_sel:
            with st.spinner("Fetching rates from 4 exchanges…", show_time=True):
                fr_rows: list[dict] = []
                for pair in fr_pairs_sel:
                    # P1-25 audit fix — was uncached; repeated "Load Rates"
                    # clicks within a 10-min window now cost 0 round-trips.
                    multi = _sg_cached_multi_exchange_funding(pair)
                    row: dict = {"Pair": pair}
                    for exch in ("okx", "binance", "bybit", "kucoin"):
                        rd   = multi.get(exch, {})
                        rate = rd.get("funding_rate_pct", 0.0)
                        row[exch.upper()] = None if rd.get("error") else rate
                    # best carry = exchange with largest |rate|
                    valid = {
                        exch: multi[exch]["funding_rate_pct"]
                        for exch in multi
                        if not multi[exch].get("error")
                        and multi[exch].get("source")
                        and multi[exch].get("funding_rate_pct") is not None  # APP-27: None → abs(None) TypeError
                    }
                    if valid:
                        best_exch = max(valid, key=lambda e: abs(valid[e]))
                        best_rate = valid[best_exch]
                        row["Best Rate"] = f"{best_rate:+.4f}% ({best_exch.upper()})"
                        row["Ann. Yield%"] = round(abs(best_rate) * 1095, 1)
                    else:
                        row["Best Rate"] = "—"
                        row["Ann. Yield%"] = 0.0
                    fr_rows.append(row)

                carry_opps = data_feeds.get_carry_trade_opportunities(fr_pairs_sel, threshold_pct=0.01)
                st.session_state["fr_table"]   = fr_rows
                st.session_state["carry_opps"] = carry_opps

        fr_table = st.session_state.get("fr_table")
        if fr_table:
            fr_df = pd.DataFrame(fr_table)

            def _color_fr(val):
                if not isinstance(val, (int, float)):
                    return "color: #64748b"
                if val >  0.05: return "color: #ef4444; font-weight: bold"
                if val >  0.01: return "color: #f59e0b"
                if val < -0.05: return "color: #00d4aa; font-weight: bold"
                if val < -0.01: return "color: #22c55e"
                return "color: #94a3b8"

            def _color_ann(val):
                if not isinstance(val, (int, float)):
                    return ""
                if val >= 30: return "color: #00d4aa; font-weight: bold"
                if val >= 10: return "color: #22c55e"
                return ""

            exch_cols = [c for c in ["OKX", "BINANCE", "BYBIT", "KUCOIN"] if c in fr_df.columns]
            ann_cols  = ["Ann. Yield%"] if "Ann. Yield%" in fr_df.columns else []

            st.dataframe(
                fr_df.style
                    .map(_color_fr,  subset=exch_cols)
                    .map(_color_ann, subset=ann_cols),
                width='stretch',
                hide_index=True,
            )
            st.caption(
                "Rates are % per 8-hour interval. "
                "Ann. Yield% = |rate| × 1 095 (assumes 3 payments/day). "
                "N/A = geo-blocked or pair not listed on that exchange."
            )

            # ── Carry Trade Opportunities ──────────────────────────────────────
            carry_opps = st.session_state.get("carry_opps", [])
            if carry_opps:
                st.markdown("#### 🏦 Carry Trade Opportunities (|rate| > 0.01%)")
                st.caption(
                    "Market-neutral strategy: hold opposite positions on perp + spot "
                    "to collect funding payments without directional exposure."
                )
                carry_df = pd.DataFrame(carry_opps).rename(columns={
                    "pair":             "Pair",
                    "exchange":         "Exchange",
                    "funding_rate_pct": "Rate %",
                    "direction":        "Direction",
                    "strategy":         "Strategy",
                    "annualized_yield": "Ann. Yield %",
                })

                def _color_carry_yield(val):
                    if not isinstance(val, (int, float)):
                        return ""
                    if val >= 50: return "color: #00d4aa; font-weight: bold"
                    if val >= 20: return "color: #22c55e"
                    if val >= 10: return "color: #f59e0b"
                    return ""

                def _color_rate(val):
                    if not isinstance(val, (int, float)):
                        return ""
                    if val >  0.05: return "color: #ef4444; font-weight: bold"
                    if val >  0.01: return "color: #f59e0b"
                    if val < -0.05: return "color: #00d4aa; font-weight: bold"
                    if val < -0.01: return "color: #22c55e"
                    return ""

                st.dataframe(
                    carry_df[["Pair", "Exchange", "Rate %", "Strategy", "Ann. Yield %"]].style
                        .map(_color_rate,        subset=["Rate %"])
                        .map(_color_carry_yield, subset=["Ann. Yield %"]),
                    width='stretch',
                    hide_index=True,
                )
            else:
                st.info("No carry trade opportunities above 0.01% threshold for the selected pairs.")

    # ── E1: Hyperliquid DEX Funding Rates ────────────────────────────────────
    with st.expander("🔷 Hyperliquid DEX — Funding Rates & Open Interest", expanded=False):
        st.caption(
            "Hyperliquid is the largest on-chain perp DEX. "
            "Funding rates > 0.03% (8h) = longs paying shorts — BULLISH signal. "
            "Rates < −0.01% = shorts paying longs — BEARISH. "
            "Data is public, no API key required."
        )
        _hl_pairs = [p.replace("/USDT", "") for p in model.PAIRS[:10]]
        _hl_load = st.button("🔄 Load Hyperliquid Data", key="btn_hl_load")
        if _hl_load:
            with st.spinner("Fetching Hyperliquid funding rates…", show_time=True):
                _hl_data = data_feeds.get_hyperliquid_batch(_hl_pairs)
            st.session_state["hl_data"] = _hl_data

        _hl_data = st.session_state.get("hl_data")
        if _hl_data:
            _hl_rows = []
            for coin, d in _hl_data.items():
                if d.get("error"):
                    continue
                _sig = d.get("signal", "NEUTRAL")
                _sig_icon = {"BULLISH": "▲", "BEARISH": "▼", "NEUTRAL": "■"}.get(_sig, "■")
                _hl_rows.append({
                    "Coin":            coin,
                    "Mark Price":      f"${d.get('mark_price', 0):,.4f}" if d.get("mark_price") else "—",
                    "Funding 8h":      f"{d.get('funding_rate_pct', 0):+.4f}%",
                    "Open Interest":   f"${d.get('open_interest_usd', 0):,.0f}" if d.get("open_interest_usd") else "—",
                    "Signal":          f"{_sig_icon} {_sig}",
                })
            if _hl_rows:
                _hl_df = pd.DataFrame(_hl_rows)

                def _color_hl_sig(val: str) -> str:
                    if "BULLISH"  in val: return "color:#00d4aa;font-weight:bold"
                    if "BEARISH"  in val: return "color:#ef4444;font-weight:bold"
                    return "color:#6b7280"

                st.dataframe(
                    _hl_df.style.map(_color_hl_sig, subset=["Signal"]),
                    width='stretch', hide_index=True,
                )
                _csv_button(_hl_df, "hyperliquid_funding.csv", key="csv_hl_funding")
            else:
                st.info("No Hyperliquid data returned for the selected pairs.")
        else:
            st.info("Press **Load Hyperliquid Data** to fetch on-chain DEX funding rates.")


# ──────────────────────────────────────────────
# PAGE: AUTONOMOUS AGENT
# ──────────────────────────────────────────────
def page_alerts():
    """C6 (Phase C plan §C6, 2026-04-30): Alerts is now a first-class
    page (was a tab inside Settings → Config Editor). Two views via
    primary segmented control:
      - Configure: email-config form (lifted from the old Alerts tab
        body — see _render_alerts_configure)
      - History:   filter row + table from the new alerts_log DB
    """
    _al_lv = st.session_state.get("user_level", "beginner")
    try:
        from ui import (
            render_top_bar as _ds_top_bar,
            page_header as _ds_page_header,
            segmented_control as _ds_seg,
        )
    except Exception as _e_imp:
        logger.error("[Alerts] import failed: %s", _e_imp)
        st.error("Alerts page failed to load — check logs.")
        return

    _ds_top_bar(
        breadcrumb=("Account", "Alerts"),
        user_level=_al_lv,
        on_refresh=_refresh_all_data,
        on_theme=_toggle_theme,
        status_pills=_agent_topbar_pills(),
    )
    _ds_page_header(
        title="Alerts",
        subtitle="Configure email + watchlist alerts and review the dispatch history.",
    )

    _al_view = st.session_state.get("alerts_view", "configure")
    if _al_view not in ("configure", "history"):
        _al_view = "configure"
    _al_view = _ds_seg(
        [("configure", "Configure"), ("history", "History")],
        active=_al_view,
        key="alerts_view",
        variant="primary",
    )

    if _al_view == "configure":
        _render_alerts_configure()
        return

    # ── History view ──────────────────────────────────────────────────
    # C6 (Phase C plan §C6.3): filter row + alert log table backed by
    # the new alerts_log DB table. Filters cascade as ANDs.
    try:
        from database import recent_alerts as _recent_alerts
    except Exception as _e_ra:
        logger.error("[Alerts] recent_alerts import failed: %s", _e_ra)
        st.error("Alert history database helper unavailable — check logs.")
        return

    _f1, _f2, _f3, _f4 = st.columns(4)
    with _f1:
        _flt_type = st.selectbox(
            "Type",
            options=["(all)", "email_signal", "watchlist", "agent_decision",
                     "scan_error"],
            index=0,
            key="alerts_hist_type",
        )
    with _f2:
        _flt_status = st.selectbox(
            "Status",
            options=["(all)", "sent", "failed", "suppressed"],
            index=0,
            key="alerts_hist_status",
        )
    with _f3:
        _flt_channel = st.selectbox(
            "Channel",
            options=["(all)", "email", "webhook", "slack", "tradingview"],
            index=0,
            key="alerts_hist_channel",
        )
    with _f4:
        _flt_limit = st.selectbox(
            "Show",
            options=[25, 50, 100, 250, 500],
            index=2,
            key="alerts_hist_limit",
        )

    _flt_kwargs: dict = {}
    if _flt_type != "(all)":
        _flt_kwargs["alert_type"] = _flt_type
    if _flt_status != "(all)":
        _flt_kwargs["status"] = _flt_status
    if _flt_channel != "(all)":
        _flt_kwargs["channel"] = _flt_channel
    rows = _recent_alerts(limit=int(_flt_limit), **_flt_kwargs)

    if not rows:
        st.info("No alerts have fired yet — once an email or webhook "
                "dispatches, the row appears here.")
        return

    # Render a compact table. Status gets a colour tag for at-a-glance
    # scan; everything else stays plain text.
    _hist_rows = []
    for r in rows:
        _status_icon = {"sent": "🟢", "failed": "🔴",
                        "suppressed": "⚪"}.get(r.get("status"), "")
        _hist_rows.append({
            "Time": r.get("time_str", ""),
            "Type": r.get("type", ""),
            "Asset": r.get("asset", "") or "—",
            "Channel": r.get("channel", "") or "—",
            "Status": f"{_status_icon} {r.get('status', '')}",
            "Message": (r.get("message") or "")[:140],
        })
    st.dataframe(_hist_rows, width="stretch", hide_index=True)
    st.caption(f"{len(rows)} of last {int(_flt_limit)} dispatches shown.")


def page_agent():
    _ag_lv = st.session_state.get("user_level", "beginner")
    _ag_title = "AI Assistant" if _ag_lv in ("beginner", "intermediate") else "Autonomous Agent"
    _ag_sub = (
        "Your AI assistant watches the markets 24/7 while the app is running and tells you when it thinks there's an opportunity. "
        "It never makes trades for you — it only gives you advice, and you decide what to do."
        if _ag_lv == "beginner"
        else "LangGraph + Claude Sonnet 4.6 autonomous trading agent. "
             "Hard Python risk gates before and after every Claude decision. "
             "Claude may only approve or reject — never place orders directly."
    )
    # ── 2026-05 redesign: top bar + page header ──
    try:
        from ui import render_top_bar as _ds_top_bar, page_header as _ds_page_header
        _ds_top_bar(breadcrumb=("Account", _ag_title), user_level=_ag_lv, on_refresh=_refresh_all_data, on_theme=_toggle_theme, status_pills=_agent_topbar_pills())
        _ds_page_header(title=_ag_title, subtitle=_ag_sub)
    except Exception as _ds_ag_err:
        logger.debug("[App] agent top bar failed: %s", _ds_ag_err)
        st.title(f"🤖 {_ag_title}")
        st.caption(_ag_sub)

    if _agent is None:
        st.error("agent.py failed to import. Check logs for details.")
        return

    # ── Live status ──
    try:  # APP-09: status() may raise or return partial dict during startup
        status = _agent.supervisor.status() or {}
    except Exception:
        status = {}
    is_running = status.get("running", False)

    # Open-item #2 (2026-04-30): status row matches the
    # docs/mockups/sibling-family-crypto-signal-AI-ASSISTANT.html
    # `.status-row` shape — single card with badge + Start/Stop.
    if is_running:
        _badge_cls = ""
        _badge_txt = (
            "✅ AI is watching the market"
            if _ag_lv == "beginner"
            else f"RUNNING · cycle {int(status.get('cycles_total') or 0)}"
        )
    elif status.get("kill_requested", False):
        _badge_cls = " warning"
        _badge_txt = ("⏳ Stopping…" if _ag_lv == "beginner"
                      else "STOPPING…")
    else:
        _badge_cls = " stopped"
        _badge_txt = ("⏸ AI is paused — click Start to activate"
                      if _ag_lv == "beginner" else "STOPPED")

    # Render the badge + Start/Stop in a single grid via wrapper div.
    # The Streamlit columns inside the wrapper provide the actual
    # button widgets; CSS positions them right of the badge.
    st.markdown(
        f'<div class="ds-agent-status-row">'
        f'<div class="ds-agent-status-badge{_badge_cls}">'
        f'<span class="dot"></span>{_badge_txt}'
        f'</div>'
        f'<div></div><div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    _btn_cs, _btn_start, _btn_stop, _btn_spacer = st.columns([2, 1, 1, 3])
    with _btn_start:
        if st.button("▶ Start", width="stretch", type="primary",
                     disabled=is_running, key="agent_start_btn"):
            _ac = _cached_alerts_config()
            _ac["agent_enabled"] = True
            _save_alerts_config_and_clear(_ac)
            _agent.supervisor.start()
            st.rerun()
    with _btn_stop:
        if st.button("■ Stop", width="stretch",
                     disabled=not is_running, key="agent_stop_btn"):
            _ac = _cached_alerts_config()
            _ac["agent_enabled"] = False
            _save_alerts_config_and_clear(_ac)
            _agent.supervisor.stop()
            st.rerun()

    # ── Metrics — 4-card strip (mockup `.grid.cols-4`) ──
    last_ts = status.get("last_run_ts")
    if last_ts:
        age_s = int(time.time() - last_ts)
        age_str = (f"{age_s // 60}m {age_s % 60}s ago"
                   if age_s >= 60 else f"{age_s}s ago")
        last_sub = f"interval {int(status.get('interval_s') or 60)}s"
    else:
        age_str = "Never"
        last_sub = "no cycle yet"
    _dec_raw = status.get("last_decision") or ""
    _dec_icon = {"approve": "🟢", "reject": "🔴",
                 "skip": "⚪"}.get(_dec_raw.lower(), "⚪")
    _dec_label = (_dec_raw.title() if _dec_raw else "—")
    _last_pair = status.get("last_pair") or "—"
    _last_tf = status.get("last_timeframe") or "1h"

    def _metric_card(lbl: str, val: str, sub: str = "",
                     val_color: str = "") -> str:
        _style = f"color:{val_color};" if val_color else ""
        return (
            f'<div class="ds-agent-metric-card">'
            f'<div class="ds-agent-metric-lbl">{_html.escape(lbl)}</div>'
            f'<div class="ds-agent-metric-val" style="{_style}">{val}</div>'
            f'<div class="ds-agent-metric-sub">{_html.escape(sub)}</div>'
            f'</div>'
        )

    _cycles = int(status.get("cycles_total") or 0)
    _since = status.get("session_started_at") or ""
    _since_short = (_since[:10] if _since else "this session")
    st.markdown(
        '<div class="ds-agent-metric-grid cols-4">'
        + _metric_card("Total Cycles", f"{_cycles:,}", f"since {_since_short}")
        + _metric_card("Last Cycle", age_str, last_sub)
        + _metric_card(
            "Last Pair",
            f'<span style="font-size:18px;">{_html.escape(str(_last_pair))}</span>',
            f"timeframe {_last_tf}",
        )
        + _metric_card(
            "Last Decision",
            f'<span style="font-size:18px;">{_dec_icon} {_dec_label}</span>',
            f"size {status.get('last_size_pct', '—')}% · "
            f"conf {status.get('last_confidence', '—')}%",
            val_color=("var(--success)" if _dec_raw.lower() == "approve"
                       else "var(--danger)" if _dec_raw.lower() == "reject"
                       else "var(--text-secondary)"),
        )
        + '</div>',
        unsafe_allow_html=True,
    )

    # ── 2-card row: Engine + Crash Restarts ──
    _engine_label = (
        "LangGraph state machine"
        if status.get("langgraph")
        else "Sequential pipeline (LangGraph not installed)"
    )
    _engine_sub = (
        "graph: 7 nodes · 12 edges · sequential fallback ready"
        if status.get("langgraph")
        else "fallback active — LangGraph optional dep"
    )
    _restarts = int(status.get("restart_count") or 0)
    _uptime_s = int(status.get("uptime_s") or 0)
    if _uptime_s:
        _udays = _uptime_s // 86400
        _uhours = (_uptime_s % 86400) // 3600
        _uptime_str = f"supervisor active · uptime {_udays}d {_uhours}h"
    else:
        _uptime_str = "supervisor idle"
    st.markdown(
        '<div class="ds-agent-metric-grid cols-2">'
        + _metric_card(
            "Engine",
            f'<span style="font-size:15px;">{_html.escape(_engine_label)}</span>',
            _engine_sub,
        )
        + _metric_card("Crash Restarts", f"{_restarts}", _uptime_str)
        + '</div>',
        unsafe_allow_html=True,
    )

    # In-progress indicator — mockup-styled chip.
    _cur = status.get("current_pair", "")
    _elapsed = status.get("cycle_elapsed_s", 0)
    if is_running and _cur:
        st.markdown(
            f'<div class="ds-agent-in-progress">'
            f'⏳ Processing {_html.escape(str(_cur))} — cycle running '
            f'for {int(_elapsed)}s'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Config form ──
    st.markdown("---")
    _ui.section_header("Agent Configuration",
                       "Saved to alerts_config.json — takes effect on next cycle")
    with st.form("agent_config_form"):
        _cfg = _agent.get_agent_config()
        ac1, ac2 = st.columns(2)
        with ac1:
            _dry_run  = st.toggle("Dry Run (no real orders)", value=_cfg["dry_run"])
            _interval = st.number_input(
                "Cycle Interval (seconds)", min_value=30, max_value=3600,
                value=_cfg["interval_seconds"], step=30,
            )
            _min_conf = st.slider(
                "Min Confidence to Act (%)", min_value=50.0, max_value=99.0,
                value=float(_cfg["min_confidence"]), step=1.0,
            )
            _max_trade = st.slider(
                "Max Trade Size (% of portfolio)", min_value=1.0, max_value=50.0,
                value=float(_cfg.get("agent_max_trade_size_pct", 10.0)), step=0.5,
                help="Hard cap on any single trade as a % of total portfolio equity",
            )
        with ac2:
            _max_pos  = st.number_input(
                "Max Concurrent Positions", min_value=1, max_value=10,
                value=_cfg["max_concurrent_positions"], step=1,
            )
            _loss_lim = st.number_input(
                "Daily Loss Limit (%)", min_value=0.5, max_value=50.0,
                value=float(_cfg["daily_loss_limit_pct"]), step=0.5, format="%.1f",
            )
            _port_sz  = st.number_input(
                "Portfolio Size (USD)", min_value=100.0, max_value=1_000_000.0,
                value=float(_cfg["portfolio_size_usd"]), step=500.0, format="%.0f",
            )
            _max_dd = st.slider(
                "Max Drawdown from Peak (%)", min_value=5.0, max_value=50.0,
                value=float(_cfg.get("agent_max_drawdown_pct", 15.0)), step=1.0,
                help="Agent halts all new entries if portfolio drawdown exceeds this level",
            )
            _cooldown = st.number_input(
                "Cooldown After Loss (seconds)", min_value=0, max_value=86400,
                value=int(_cfg.get("agent_cooldown_after_loss_s", 1800)), step=300,
                help="Pause period before next trade after a losing cycle",
            )
        if st.form_submit_button("💾 Save Agent Config", type="secondary",
                                  width="stretch"):
            _saved = _cached_alerts_config()
            _saved["agent_dry_run"]                  = _dry_run
            _saved["agent_interval_seconds"]         = int(_interval)
            _saved["agent_min_confidence"]           = float(_min_conf)
            _saved["agent_max_concurrent_positions"] = int(_max_pos)
            _saved["agent_daily_loss_limit_pct"]     = float(_loss_lim)
            _saved["agent_portfolio_size_usd"]       = float(_port_sz)
            _save_alerts_config_and_clear(_saved)
            # G2: also persist all override params to agent_overrides.json
            _agent.save_overrides({
                "agent_min_confidence":           float(_min_conf),
                "agent_max_concurrent_positions": int(_max_pos),
                "agent_daily_loss_limit_pct":     float(_loss_lim),
                "agent_portfolio_size_usd":       float(_port_sz),
                "agent_interval_seconds":         int(_interval),
                "agent_max_trade_size_pct":       float(_max_trade),
                "agent_max_drawdown_pct":         float(_max_dd),
                "agent_cooldown_after_loss_s":    int(_cooldown),
            })
            st.success("Agent config saved.")

    # G2: Active Limits panel — shows current effective values with custom badges
    with st.expander("📋 Active Limits (current effective values)", expanded=False):
        _limits = _agent.get_active_limits(_agent.get_agent_config())
        _lim_col1, _lim_col2 = st.columns(2)
        for i, (key, info) in enumerate(_limits.items()):
            _col = _lim_col1 if i % 2 == 0 else _lim_col2
            with _col:
                _badge = " 🔧 custom" if info["custom"] else ""
                _label = key.replace("agent_", "").replace("_", " ").title()
                st.metric(_label + _badge, info["value"], delta=None)

    # G8: Emergency Stop — highest-priority kill switch
    st.markdown("---")
    _ui.section_header("Emergency Controls", "Overrides all other config — instant effect")
    _emg_col1, _emg_col2 = st.columns(2)
    with _emg_col1:
        _is_emg = _agent.is_emergency_stop()
        _emg_label = "🔴 EMERGENCY STOP ACTIVE — agent will reject all new trades" if _is_emg else "⚪ No emergency stop"
        st.markdown(f"**Status:** {_emg_label}")
    with _emg_col2:
        if not _agent.is_emergency_stop():
            if st.button("🚨 Activate Emergency Stop", key="btn_emg_activate", type="primary"):
                _agent.set_emergency_stop(True)
                st.error("Emergency stop activated — agent will skip all new entries until cleared.")
                st.rerun()
        else:
            if st.button("✅ Clear Emergency Stop", key="btn_emg_clear", type="secondary"):
                _agent.set_emergency_stop(False)
                st.success("Emergency stop cleared — agent will resume normal operation.")
                st.rerun()

    # ── Architecture notes ──
    st.markdown("---")
    _ui.section_header("Pipeline Architecture",
                       "Hard risk gates prevent Claude from ever executing without validation")
    st.code(
        "fetch signal → pre-risk check → Claude approve/reject → post-risk check → execute → log",
        language=None,
    )
    st.markdown("""
**Safety guarantees:**
- Claude may only call `approve_trade` or `reject_trade` — never `place_order` directly
- **pre-risk check**: position count limit, min confidence, daily loss limit, circuit breaker
- **post-risk check**: size cap re-validation, direction mismatch guard
- All cycles logged to `agent_log` SQLite table regardless of outcome
- Prompt injection sanitizer strips jailbreak phrases from exchange data before Claude sees it
""")

    # ── Decision log ──
    st.markdown("---")
    # G3: Dual-window accuracy panel (7-day vs 30-day with trend)
    st.markdown("---")
    _ui.section_header("Agent Accuracy", "30-day vs 7-day win rate comparison")
    try:
        from ai_feedback import get_dual_window_accuracy
        _dwa = get_dual_window_accuracy()
        _acc30 = _dwa.get("acc_30d", {})
        _acc7  = _dwa.get("acc_7d",  {})
        _trend = _dwa.get("trend", "stable")
        _wr30  = _acc30.get("win_rate", 0) or 0
        _wr7   = _acc7.get("win_rate",  0) or 0
        _trend_icon = {"improving": "📈", "degrading": "📉", "stable": "➡️"}.get(_trend, "➡️")
        _trend_color = {"improving": "#22c55e", "degrading": "#ef4444", "stable": "#9CA3AF"}.get(_trend, "#9CA3AF")
        _g3c1, _g3c2, _g3c3 = st.columns(3)
        _g3c1.metric("30-Day Win Rate", f"{_wr30:.0%}",
                     delta=None, help="Fraction of signal outcomes resolved as correct over the past 30 days")
        _g3c2.metric("7-Day Win Rate", f"{_wr7:.0%}",
                     delta=f"{(_wr7 - _wr30) * 100:+.1f}pp vs 30d",
                     help="Fraction of signal outcomes resolved as correct over the past 7 days")
        _g3c3.metric("Accuracy Trend", f"{_trend_icon} {_trend.title()}",
                     help="Improving = 7-day win rate at least 5pp above 30-day baseline")
        if st.session_state.get("user_level", "beginner") == "beginner":
            st.caption(
                f"This shows how well the model's signals have performed recently. "
                f"The 7-day rate gives the latest picture; the 30-day rate is the longer-run baseline. "
                f"A {_trend} trend means recent accuracy is {'better' if _trend == 'improving' else ('worse' if _trend == 'degrading' else 'similar')} than the baseline."
            )
    except Exception as _g3e:
        logger.debug("[Accuracy] display error: %s", _g3e)
        st.caption("Accuracy metrics not yet available — run a scan to generate signal history.")

    # F1 — Rolling 7-day win rate chart (30-day lookback)
    try:
        from ai_feedback import get_rolling_win_rate_history as _get_wr_hist
        _wr_hist = _get_wr_hist(window_days=30, rolling_window=7)
        if _wr_hist:
            _wr_df = pd.DataFrame(_wr_hist)
            _avg_wr = _wr_df["win_rate"].mean()
            _wr_fig = go.Figure()
            _wr_fig.add_trace(go.Scatter(
                x=_wr_df["date"], y=_wr_df["win_rate"],
                mode="lines+markers",
                line=dict(color="#00d4aa", width=2),
                marker=dict(size=5),
                name="Rolling 7-day Win Rate",
                hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
            ))
            _wr_fig.add_hline(
                y=_avg_wr, line_dash="dash", line_color="#f59e0b",
                annotation_text=f"30d avg {_avg_wr:.1f}%",
                annotation_position="bottom right",
            )
            _wr_fig.update_layout(
                height=220, margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="Date", yaxis_title="Win Rate %",
                yaxis=dict(range=[0, 100]),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            _ui.section_header("Rolling Win Rate", "7-day rolling window over past 30 days")
            st.plotly_chart(_wr_fig, width='stretch')
    except Exception as _wr_err:
        logger.debug("[App] agent rolling win rate chart failed: %s", _wr_err)

    st.markdown("---")
    _ui.section_header("Recent Agent Decisions", "Last 200 cycles from agent_log table")
    _log_df = _cached_agent_log_df(limit=200)
    if _log_df.empty:
        st.info("No decisions recorded yet. Start the agent to begin logging.")
    else:
        st.dataframe(_log_df, width='stretch', hide_index=True)
        st.download_button(
            "⬇ Download Agent Log CSV",
            data=_log_df.to_csv(index=False),
            file_name="agent_log.csv",
            mime="text/csv",
            key="dl_agent_log_csv",
        )


# ──────────────────────────────────────────────
# PAGE: SIGNALS (sibling-family-crypto-signal-SIGNALS.html)
# ──────────────────────────────────────────────
def page_signals():
    """Per-coin signal detail — hero + composite + indicators + history.

    Pulls data from latest scan_results (in-session) → daily_signals DB
    fallback. Where a metric isn't available, the cell shows "—" so the
    layout is preserved and the user gets a clear "no data yet" state
    rather than a missing card.
    """
    try:
        from ui import (
            render_top_bar as _ds_top_bar,
            page_header as _ds_page_header,
            pair_dropdown as _ds_pair_dropdown,
            multi_timeframe_strip as _ds_tf_strip,
            signal_hero_detail_card as _ds_signal_hero,
            composite_score_card as _ds_composite,
            indicator_card as _ds_ind_card,
            signal_history_table as _ds_sig_hist,
        )
    except Exception as _e_imp:
        logger.error("[Signals] import failed: %s", _e_imp)
        st.error("Signal page failed to load — check logs.")
        return

    _ds_level = st.session_state.get("user_level", "beginner")
    _ds_top_bar(
        breadcrumb=("Markets", "Signals"),
        user_level=_ds_level,
        on_refresh=_refresh_all_data,
        on_theme=_toggle_theme,
        status_pills=_agent_topbar_pills(),
    )

    # C3 (Phase C plan §C3.1): pair_dropdown — 5 quick pills + "More ▾ +28"
    # popover backed by the full model.PAIRS universe. Persists in
    # st.session_state["selected_pair"] (per the plan's spec).
    # Migrated from the legacy 5-button row that used the if-button-rerun
    # pattern (which had the two-click highlight bug class).
    _signals_universe = list(model.PAIRS) or ["BTC/USDT", "ETH/USDT"]
    # Keep the pre-redesign session_state key alive for back-compat —
    # any downstream code reading "signals_active_coin" still works.
    _legacy_active = st.session_state.get("signals_active_coin")
    _selected_pair = st.session_state.get("selected_pair")
    if _selected_pair is None and _legacy_active:
        _selected_pair = f"{_legacy_active}/USDT"
        st.session_state["selected_pair"] = _selected_pair
    if _selected_pair is None or _selected_pair not in _signals_universe:
        _selected_pair = _signals_universe[0]
        st.session_state["selected_pair"] = _selected_pair

    _ds_page_header(
        title="Signal detail",
        subtitle="Layer-by-layer composite signal breakdown for a single coin.",
        data_sources=[
            (str(model.TA_EXCHANGE).upper(), "live"),
            ("Glassnode", "live"),
            ("News sentiment", "cached"),
        ],
    )
    _selected_pair = _ds_pair_dropdown(
        _signals_universe,
        active=_selected_pair,
        key="selected_pair",
    )

    # Multi-timeframe strip — visible selector backed by
    # st.session_state["selected_timeframe"].
    #
    # C-fix-04 (2026-05-01): always render the canonical 8-cell set
    # (1m/5m/15m/30m/1h/4h/1d/1w) per the Signals mockup spec. The
    # engine may scan only a subset (e.g. model.TIMEFRAMES =
    # ["1h","4h","1d","1w"]) — those un-scanned cells render disabled
    # with a tooltip pointing to Settings → Trading → Timeframes so the
    # user sees the full spec without being able to click into an empty
    # timeframe. Per-timeframe signals dict is computed below from
    # whatever per-tf data the latest scan_result carries; cells without
    # data render bare label only. The active timeframe drives the
    # composite_score_card and indicator selection further down.
    from ui.sidebar import CANONICAL_TIMEFRAMES as _DS_CANON_TFS
    _signals_tfs_render = list(_DS_CANON_TFS)
    _signals_tfs_enabled = list(getattr(model, "TIMEFRAMES", ["1h", "4h", "1d", "1w"]))
    _selected_tf = st.session_state.get("selected_timeframe")
    if _selected_tf not in _signals_tfs_enabled:
        _selected_tf = "1d" if "1d" in _signals_tfs_enabled else _signals_tfs_enabled[0]
        st.session_state["selected_timeframe"] = _selected_tf
    _selected_tf = _ds_tf_strip(
        _signals_tfs_render,
        active=_selected_tf,
        key="selected_timeframe",
        enabled_timeframes=_signals_tfs_enabled,
    )

    # Maintain back-compat: keep `signals_active_coin` in sync with
    # the new `selected_pair` so any unmigrated readers below still
    # see the current selection.
    _coin = _selected_pair.split("/")[0].split("-")[0]
    _pair = _selected_pair
    st.session_state["signals_active_coin"] = _coin

    # ── Pull data: latest scan result (or DB fallback) for the active pair ──
    _result = {}
    try:
        for _r in (st.session_state.get("scan_results") or []):
            _pr = str(_r.get("pair") or _r.get("symbol") or "").upper().replace("/", "").replace("-", "")
            if _pr.startswith(_coin):
                _result = _r
                break
        if not _result:
            _df_sig = _cached_signals_df(500)
            if _df_sig is not None and not _df_sig.empty:
                _df_pair_norm = _df_sig["pair"].astype(str).str.upper().str.replace("/", "", regex=False).str.replace("-", "", regex=False)
                _hits = _df_sig[_df_pair_norm.str.startswith(_coin)]
                if not _hits.empty:
                    _result = _hits.sort_values("scan_timestamp", ascending=False).iloc[0].to_dict()
    except Exception as _e_lookup:
        logger.debug("[Signals] result lookup failed: %s", _e_lookup)

    # Live price + 24h change from WebSocket
    _live = _ws.get_all_prices() or {}
    _tick = _live.get(_pair) or {}
    _price = _tick.get("price") or _tick.get("last") or _result.get("price")
    _chg_24h = _tick.get("change_24h_pct") or _tick.get("change_pct") or _result.get("change_24h_pct")

    # 30d / 1Y change from OHLCV
    _chg_30d = None
    _chg_1y = None
    _closes_90d = []
    try:
        # H3 fix (2026-04-28): the previous shape `if _ex: <fetch>` gated
        # the entire OHLCV fetch on `model.get_exchange_instance(...)`
        # returning a non-None object. When the primary TA exchange was
        # unreachable (OKX rate-limit, datacenter-IP block, etc.), _ex
        # was None and no fetch was attempted at all — the user saw
        # "Price history unavailable" with no fallback. We now pass the
        # configured exchange ID directly to `_sg_cached_ohlcv` (which
        # wraps `model.robust_fetch_ohlcv` and handles the §10 fallback
        # chain internally: OKX → Kraken → CoinGecko). The instance
        # object is no longer required.
        _ex_id = str(getattr(model.get_exchange_instance(model.TA_EXCHANGE), "id", "")
                     or model.TA_EXCHANGE or "okx")
        _ohlcv_d = _sg_cached_ohlcv(_ex_id, _pair, "1d", limit=400)
        if _ohlcv_d:
            _closes_d = [float(r[4]) for r in _ohlcv_d if len(r) >= 5]
            if _closes_d:
                if _price is None:
                    _price = _closes_d[-1]
                if len(_closes_d) >= 30 and _closes_d[-30]:
                    _chg_30d = (_closes_d[-1] - _closes_d[-30]) / _closes_d[-30] * 100.0
                if len(_closes_d) >= 365 and _closes_d[-365]:
                    _chg_1y = (_closes_d[-1] - _closes_d[-365]) / _closes_d[-365] * 100.0
                elif len(_closes_d) >= 2:
                    _chg_1y = (_closes_d[-1] - _closes_d[0]) / _closes_d[0] * 100.0
                _closes_90d = _closes_d[-90:]
    except Exception as _e_ohlcv:
        logger.debug("[Signals] OHLCV fetch for %s failed: %s", _pair, _e_ohlcv)

    # Signal + regime from result
    _sig_raw = (_result.get("direction") or _result.get("signal") or _result.get("composite_direction") or "").upper()
    _signal_letter = "BUY" if _sig_raw in ("LONG", "BUY") else ("SELL" if _sig_raw in ("SHORT", "SELL") else ("HOLD" if _result else None))
    _conf = _result.get("confidence") or _result.get("composite_confidence")
    _strength = ""
    try:
        _conf_f = float(_conf) if _conf is not None else None
        if _conf_f is not None:
            _strength = "strong" if _conf_f >= 75 else ("moderate" if _conf_f >= 60 else "weak")
    except Exception:
        pass
    _regime_raw = str(_result.get("regime") or _result.get("regime_label") or "").strip()
    _regime_clean = _regime_raw
    for _p in ("Regime: ", "Regime:", "Regime "):
        if _regime_clean.lower().startswith(_p.lower()):
            _regime_clean = _regime_clean[len(_p):].strip()
            break
    _regime_conf = _result.get("regime_confidence") or _result.get("regime_conf_pct")

    _coin_full = {"BTC": "Bitcoin", "ETH": "Ethereum", "XRP": "Ripple", "SOL": "Solana", "AVAX": "Avalanche"}.get(_coin, _coin)

    st.markdown(
        _ds_signal_hero(
            ticker=f"{_coin} / USD",
            name=_coin_full,
            price=_price,
            change_24h=_chg_24h,
            change_30d=_chg_30d,
            change_1y=_chg_1y,
            signal=_signal_letter,
            signal_strength=_strength,
            regime_label=_regime_clean.title() if _regime_clean else "",
            regime_confidence=_regime_conf,
            regime_since="",
        ),
        unsafe_allow_html=True,
    )

    # C9 (Phase C plan §C9, 2026-04-30): level-aware rationale block
    # under the hero card. Beginner gets plain English; Intermediate
    # gets the composite + 4-layer summary; Advanced gets the raw
    # numbers (RSI, MACD, regime confidence). Per CLAUDE.md §7.
    try:
        _l_tech = _result.get("layer_technical") or _result.get("tech_score")
        _l_macro = _result.get("layer_macro") or _result.get("macro_score")
        _l_sent = _result.get("layer_sentiment") or _result.get("sentiment_score")
        _l_onch = _result.get("layer_onchain") or _result.get("onchain_score")
        _composite_score = _result.get("composite_score") or _conf
        _rsi = _result.get("rsi_14") or _result.get("rsi")
        _macd_line = _result.get("macd_line") or _result.get("macd")
        _macd_sig = _result.get("macd_signal")
        _adx = _result.get("adx_14") or _result.get("adx")

        if _ds_level == "beginner":
            # Plain English, no jargon. Ground the description in the
            # current direction + regime + 24h change so it's specific
            # to what the user sees.
            if _signal_letter == "BUY":
                _rat = (
                    f"{_coin_full} is showing positive momentum — the model "
                    f"sees more upside signals than downside. Regime: "
                    f"{_regime_clean.title() or 'Transition'}."
                )
            elif _signal_letter == "SELL":
                _rat = (
                    f"{_coin_full} is showing weakness — the model is leaning "
                    f"toward a defensive posture. Regime: "
                    f"{_regime_clean.title() or 'Transition'}."
                )
            else:
                _rat = (
                    f"{_coin_full} is in a wait-and-see zone — no strong "
                    f"directional edge right now. Regime: "
                    f"{_regime_clean.title() or 'Transition'}."
                )
            st.markdown(
                f'<div class="ds-card" style="margin-top:12px;'
                f'background:var(--bg-1);">'
                f'<div style="font-size:13px;color:var(--text-muted);'
                f'text-transform:uppercase;letter-spacing:0.06em;'
                f'margin-bottom:6px;">What this means</div>'
                f'<div style="font-size:14px;line-height:1.5;'
                f'color:var(--text-primary);">{_html.escape(_rat)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif _ds_level == "intermediate":
            # Condensed signal interpretation with key numbers visible.
            _layers_alignment = sum(
                1 for v in (_l_tech, _l_macro, _l_sent, _l_onch)
                if v is not None and float(v) >= 50
            )
            _comp_str = (f"{float(_composite_score):.0f}"
                         if _composite_score is not None else "—")
            _rat = (
                f"Composite signal: **{_signal_letter or 'HOLD'}** · "
                f"score {_comp_str} · "
                f"{_layers_alignment}/4 layers above neutral · "
                f"regime {_regime_clean.title() or '—'}."
            )
            st.markdown(
                f'<div class="ds-card" style="margin-top:12px;">'
                f'<div style="font-size:13px;color:var(--text-muted);'
                f'text-transform:uppercase;letter-spacing:0.06em;'
                f'margin-bottom:6px;">Signal summary</div>'
                f'<div style="font-size:14px;line-height:1.5;">{_rat}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:  # advanced
            # Raw numbers: RSI / MACD / ADX / per-layer scores / regime
            # confidence. Mono font for the number column.
            _adv_lines = []
            if _rsi is not None:
                _adv_lines.append(f"RSI(14)={float(_rsi):.1f}")
            if _macd_line is not None:
                if _macd_sig is not None:
                    _adv_lines.append(
                        f"MACD={float(_macd_line):.3f} / "
                        f"signal={float(_macd_sig):.3f}"
                    )
                else:
                    _adv_lines.append(f"MACD={float(_macd_line):.3f}")
            if _adx is not None:
                _adv_lines.append(f"ADX(14)={float(_adx):.1f}")
            if _composite_score is not None:
                _adv_lines.append(f"composite={float(_composite_score):.1f}")
            if _regime_conf is not None:
                _adv_lines.append(
                    f"regime={_regime_clean.title() or '—'} "
                    f"(HMM conf {float(_regime_conf):.0f}%)"
                )
            _layer_str = " · ".join(
                f"{name}={(float(v)):.0f}" for name, v in (
                    ("TA",     _l_tech),
                    ("Macro",  _l_macro),
                    ("Sent",   _l_sent),
                    ("OnCh",   _l_onch),
                ) if v is not None
            )
            if _layer_str:
                _adv_lines.append(f"layers: {_layer_str}")
            _rat_html = (
                ("<br>".join(_html.escape(s) for s in _adv_lines))
                or "Insufficient indicator data — run a scan to populate."
            )
            st.markdown(
                f'<div class="ds-card" style="margin-top:12px;">'
                f'<div style="font-size:13px;color:var(--text-muted);'
                f'text-transform:uppercase;letter-spacing:0.06em;'
                f'margin-bottom:6px;">Advanced diagnostics</div>'
                f'<div class="num" style="font-size:13px;line-height:1.6;'
                f'color:var(--text-secondary);">{_rat_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    except Exception as _e_rat:
        logger.debug("[Signals] level-aware rationale render failed: %s", _e_rat)

    # ── Two-col: price chart + composite score ──
    _col1, _col2 = st.columns([1.2, 1])
    with _col1:
        st.markdown(
            f'<div class="ds-card">'
            f'<div class="ds-card-hd"><div class="ds-card-title">Price · last 90d</div>'
            f'<div style="color:var(--text-muted);font-size:12px;">{str(model.TA_EXCHANGE).upper()} · live</div></div>',
            unsafe_allow_html=True,
        )
        if _closes_90d:
            try:
                import plotly.graph_objects as _go
                _x = list(range(len(_closes_90d)))
                _fig = _go.Figure()
                _fig.add_trace(_go.Scatter(
                    x=_x, y=_closes_90d, mode="lines",
                    line=dict(color="#22d36f", width=2),
                    fill="tozeroy", fillcolor="rgba(34,211,111,0.10)",
                    showlegend=False, hovertemplate="%{y:,.2f}<extra></extra>",
                ))
                _fig.update_layout(
                    height=200, margin=dict(l=0, r=0, t=0, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(visible=False),
                    yaxis=dict(visible=False, range=[min(_closes_90d) * 0.98, max(_closes_90d) * 1.02]),
                )
                st.plotly_chart(_fig, width='stretch', config={"displayModeBar": False})
            except Exception as _e_plot:
                logger.debug("[Signals] price chart render failed: %s", _e_plot)
                st.caption("Chart unavailable — try refreshing.")
        else:
            st.caption("Price history unavailable — try refreshing.")

        # 4-cell info strip below the chart (Vol / ATR / Beta / Funding)
        try:
            _vol = _result.get("volume_24h_usd") or _result.get("vol_24h")
            _atr = _result.get("atr_14") or _result.get("atr")
            _beta = _result.get("beta_spy")
            _fund = None
            try:
                # P1-25 audit fix — Signals page funding fetch now cached 10min.
                _fr = _sg_cached_funding_rate(_pair)
                _fund = _fr.get("funding_rate_pct") or _fr.get("rate_pct")
            except Exception:
                pass

            # C-fix-06 (2026-05-01): fall back to direct compute from the
            # 1d OHLCV we already fetched above (C-fix-05 now actually
            # returns real data here). Without this, Vol/ATR render as
            # "—" on cold-start until the first scan completes — but the
            # data needed to populate them is already in `_ohlcv_d`.
            # ccxt row format: [ts_ms, open, high, low, close, volume]
            if _vol is None and _ohlcv_d:
                try:
                    _last = _ohlcv_d[-1]
                    if len(_last) >= 6:
                        _vol = float(_last[4]) * float(_last[5])  # close * base-vol
                except Exception:
                    pass
            if _atr is None and _ohlcv_d and len(_ohlcv_d) >= 15:
                try:
                    _trs: list[float] = []
                    for _i in range(len(_ohlcv_d) - 14, len(_ohlcv_d)):
                        _row = _ohlcv_d[_i]
                        _prev = _ohlcv_d[_i - 1]
                        if len(_row) < 5 or len(_prev) < 5:
                            continue
                        _h, _l, _pc = float(_row[2]), float(_row[3]), float(_prev[4])
                        _trs.append(max(_h - _l, abs(_h - _pc), abs(_l - _pc)))
                    if _trs:
                        _atr = sum(_trs) / len(_trs)
                except Exception:
                    pass
            # P1 follow-up — cryptorank token unlock surfacing (8h cache).
            # Shows the next unlock signal as the 5th info-strip cell so
            # users see imminent supply pressure inline with vol/ATR/beta/
            # funding. PoW pairs (BTC/LTC/DOGE) return signal=NO_UNLOCK and
            # the cell renders "—".
            _unlock_signal = "—"
            _unlock_sub = ""
            try:
                _ul = _sg_cached_token_unlocks(_pair)
                _us = (_ul or {}).get("signal") or "N/A"
                _udays = (_ul or {}).get("next_unlock_days")
                _upct = (_ul or {}).get("unlock_pct_supply")
                if _us == "UNLOCK_IMMINENT":
                    _unlock_signal = f"⚠ {_udays}d"
                    _unlock_sub = f"{_upct:.1f}% supply" if _upct is not None else "imminent"
                elif _us == "UNLOCK_SOON":
                    _unlock_signal = f"{_udays}d"
                    _unlock_sub = f"{_upct:.1f}% supply" if _upct is not None else "soon"
                elif _us == "NO_UNLOCK":
                    _unlock_signal = "None"
                    _unlock_sub = "no vesting"
                elif _us == "N/A":
                    _unlock_signal = "—"
                    _unlock_sub = ""
                else:
                    _unlock_signal = str(_us)
            except Exception as _e_ul:
                logger.debug("[Signals] token unlock fetch failed: %s", _e_ul)
            def _fmt_vol(v):
                if v is None:
                    return "—"
                v = float(v)
                if v >= 1e9:
                    return f"${v/1e9:.1f}B"
                if v >= 1e6:
                    return f"${v/1e6:.0f}M"
                return f"${v:,.0f}"
            def _fmt_pct(v, decimals=3):
                if v is None:
                    return "—"
                try:
                    fv = float(v)
                    sign = "+" if fv > 0 else ("−" if fv < 0 else "")
                    return f"{sign}{abs(fv):.{decimals}f}%"
                except Exception:
                    return "—"
            _ind_html = (
                '<div class="ds-ind-grid" style="margin-top:16px;">'
                f'<div class="ds-ind"><div class="ds-ind-lbl">Vol (24h)</div><div class="ds-ind-val">{_fmt_vol(_vol)}</div><div class="ds-ind-sub"></div></div>'
                f'<div class="ds-ind"><div class="ds-ind-lbl">ATR (14d)</div><div class="ds-ind-val">{("$" + f"{float(_atr):,.0f}") if _atr is not None else "—"}</div><div class="ds-ind-sub"></div></div>'
                f'<div class="ds-ind"><div class="ds-ind-lbl">Beta vs S&amp;P</div><div class="ds-ind-val">{(f"{float(_beta):.2f}") if _beta is not None else "—"}</div><div class="ds-ind-sub">90d rolling</div></div>'
                f'<div class="ds-ind"><div class="ds-ind-lbl">Funding (8h)</div><div class="ds-ind-val">{_fmt_pct(_fund)}</div><div class="ds-ind-sub"></div></div>'
                f'<div class="ds-ind"><div class="ds-ind-lbl">Next Unlock</div><div class="ds-ind-val">{_unlock_signal}</div><div class="ds-ind-sub">{_unlock_sub}</div></div>'
                '</div>'
            )
            st.markdown(_ind_html, unsafe_allow_html=True)
        except Exception as _e_strip:
            logger.debug("[Signals] info strip failed: %s", _e_strip)
        st.markdown('</div>', unsafe_allow_html=True)

    with _col2:
        # Layer scores from result; if absent, derive composite from confidence
        _l_tech = _result.get("layer_technical") or _result.get("tech_score")
        _l_macro = _result.get("layer_macro") or _result.get("macro_score")
        _l_sent = _result.get("layer_sentiment") or _result.get("sentiment_score")
        _l_onch = _result.get("layer_onchain") or _result.get("onchain_score")
        _composite = _result.get("composite_score") or _conf

        # C3 fallback (2026-04-29): when no scan result has populated
        # the layer scores yet, compute them on demand via the cached
        # per-pair composite helper. Without this, the four progress
        # bars and the score in the composite_score_card all render
        # empty on cold load — the bug the handoff doc described as
        # "All 4 composite layers + technical indicators + on-chain
        # values empty". The helper has a 5-min TTL so repeated detail-
        # page renders don't re-run compute_composite_signal each time.
        # Open-item #3 (2026-04-30): per-timeframe composite. When
        # the user selects a non-1d timeframe in the strip and the
        # scan_result has a `timeframes[tf]` view, recompute the
        # composite using that view's TA inputs. Macro / Sentiment /
        # On-chain layer inputs stay the same since those are not
        # per-TF concepts. Falls back to the legacy non-TF helper
        # when the per-TF view is missing.
        _tf_view_for_composite = (_result.get("timeframes", {}) or {}).get(
            _selected_tf, {}
        ) or {}
        if (
            _l_tech is None and _l_macro is None
            and _l_sent is None and _l_onch is None
        ):
            try:
                if _tf_view_for_composite:
                    # Pack tf_view as a hashable tuple for st.cache_data.
                    _payload = tuple(
                        _tf_view_for_composite.get(k)
                        for k in (
                            "rsi", "adx", "macd_div", "vwap", "ichimoku",
                            "supertrend", "sr_status", "regime",
                            "strategy_bias", "agent_vote", "consensus",
                            "funding", "open_interest", "onchain",
                            "options_iv", "ob_depth", "cvd", "tvl",
                        )
                    )
                    _cs_out = _sg_cached_composite_per_pair_tf(_pair, _payload) or {}
                else:
                    _cs_out = _sg_cached_composite_per_pair(_pair) or {}
                _layers = (_cs_out or {}).get("layers") or {}
                # compute_composite_signal returns layer scores in
                # [-1.0, +1.0] (each "score" key inside the per-layer
                # dict). The composite_score_card expects 0-100 scale,
                # so we map: display = (score + 1.0) / 2.0 * 100.
                def _to_card_scale(v):
                    if v is None:
                        return None
                    try:
                        return max(0.0, min(100.0, (float(v) + 1.0) * 50.0))
                    except Exception:
                        return None
                _l_tech  = _to_card_scale((_layers.get("technical") or {}).get("score"))
                _l_macro = _to_card_scale((_layers.get("macro")     or {}).get("score"))
                _l_sent  = _to_card_scale((_layers.get("sentiment") or {}).get("score"))
                _l_onch  = _to_card_scale((_layers.get("onchain")   or {}).get("score"))
                # The card's `score` field is also 0-100; map the
                # full composite score the same way.
                if _composite is None:
                    _comp_raw = _cs_out.get("score")
                    if _comp_raw is not None:
                        _composite = (float(_comp_raw) + 1.0) * 50.0
            except Exception as _e_csf:
                logger.debug("[Signals] C3 composite fallback failed: %s", _e_csf)

        try:
            _composite_f = float(_composite) if _composite is not None else None
        except Exception:
            _composite_f = None
        _ds_composite(
            score=_composite_f,
            layers=[
                ("Layer 1 · Technical", float(_l_tech) if _l_tech is not None else None),
                ("Layer 2 · Macro",     float(_l_macro) if _l_macro is not None else None),
                ("Layer 3 · Sentiment", float(_l_sent) if _l_sent is not None else None),
                ("Layer 4 · On-chain",  float(_l_onch) if _l_onch is not None else None),
            ],
            weights_note=("Composite = weighted avg per regime-adjusted weights. "
                         "Weights are config-driven and tuned by Optuna."),
        )

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── Three-col: Technical / On-chain / Sentiment indicator cards ──
    _ic1, _ic2, _ic3 = st.columns(3)
    with _ic1:
        # C9-fix (2026-04-30): the multi-timeframe strip now drives the
        # per-TF indicator values. Scan results already store per-TF
        # data under `_result["timeframes"][tf]` (rsi/adx/supertrend/
        # confidence/direction), so we overlay that view onto the
        # legacy top-level `_result.get("rsi_14") ...` reads. Falls
        # back to the top-level value (1d-canonical) when no per-TF
        # entry exists.
        _tf_view = (_result.get("timeframes", {}) or {}).get(
            _selected_tf, {}
        ) or {}

        def _tf_or_top(top_keys: list[str], tf_key: str | None = None):
            """Prefer the per-TF value when present + numeric; else
            fall back to the first non-None top-level key."""
            if tf_key and tf_key in _tf_view:
                v = _tf_view.get(tf_key)
                if v not in (None, "N/A", ""):
                    return v
            for k in top_keys:
                v = _result.get(k)
                if v is not None:
                    return v
            return None

        _rsi = _tf_or_top(["rsi_14", "rsi"], "rsi")
        _macd_h = _result.get("macd_hist")  # not in per-TF dict shape
        _supert = _tf_or_top(
            ["supertrend_signal", "supertrend"], "supertrend"
        )
        _adx = _tf_or_top(["adx_14", "adx"], "adx")
        # Surface "showing X data" caption so users can tell which
        # timeframe the values below reflect — avoids the impression
        # that the strip click did nothing if the per-TF values
        # happen to be missing for the selected TF.
        st.caption(
            f"Showing {_selected_tf} data" if _tf_view else
            f"Showing 1d data ({_selected_tf} not available — run a "
            f"scan that includes {_selected_tf}.)"
        )
        def _v(x, fmt="{:.1f}"):
            if x is None:
                return "—"
            try:
                return fmt.format(float(x))
            except Exception:
                return str(x)
        _rsi_tone = "warning" if (_rsi is not None and float(_rsi) >= 70) else ("danger" if (_rsi is not None and float(_rsi) <= 30) else "")
        _macd_tone = "success" if (_macd_h is not None and float(_macd_h) > 0) else ("danger" if (_macd_h is not None and float(_macd_h) < 0) else "")
        _supert_str = (str(_supert).title() if _supert is not None else "—")
        _supert_tone = "success" if str(_supert).upper() in ("BUY", "LONG", "BULL") else ("danger" if str(_supert).upper() in ("SELL", "SHORT", "BEAR") else "")
        _ds_ind_card(
            "Technical indicators",
            [
                ("RSI (14)",   _v(_rsi),    "overbought" if _rsi_tone == "warning" else ("oversold" if _rsi_tone == "danger" else ""),  _rsi_tone),
                ("MACD hist",  _v(_macd_h, "{:+.0f}") if _macd_h is not None else "—", "bullish cross" if _macd_tone == "success" else ("bearish cross" if _macd_tone == "danger" else ""), _macd_tone),
                ("Supertrend", _supert_str, "",                                                                                  _supert_tone),
                ("ADX (14)",   _v(_adx),    "strong trend" if (_adx is not None and float(_adx) >= 25) else "no trend",          ""),
            ],
        )
    with _ic2:
        _mvrv = _result.get("mvrv_z") or _result.get("mvrv")
        _sopr = _result.get("sopr")
        _exch = _result.get("exchange_reserve_delta_7d")
        _addr = _result.get("active_addresses_24h")
        _ds_ind_card(
            "On-chain",
            [
                ("MVRV-Z",        _v(_mvrv, "{:.2f}"),                                "mid-cycle" if (_mvrv is not None and 1 < float(_mvrv) < 5) else "",       ""),
                ("SOPR",          _v(_sopr, "{:.3f}"),                                "profit taking" if (_sopr is not None and float(_sopr) > 1) else "",        ""),
                ("Exch. reserve", _v(_exch, "{:+,.0f}") if _exch is not None else "—", "outflow 7d" if (_exch is not None and float(_exch) < 0) else "inflow 7d", "success" if (_exch is not None and float(_exch) < 0) else ""),
                ("Active addr.",  _v(_addr, "{:,.0f}") if _addr is not None else "—",  "",                                                                       ""),
            ],
        )
    with _ic3:
        # P1-25 audit fix — F&G + funding via cached helpers (24h / 10min).
        _fng_d = _sg_cached_fear_greed() if hasattr(data_feeds, "get_fear_greed") else {}
        _fng_v = _fng_d.get("value")
        _fund_v = None
        try:
            _fr = _sg_cached_funding_rate(_pair)
            _fund_v = _fr.get("funding_rate_pct") or _fr.get("rate_pct")
        except Exception:
            pass
        _trends = _result.get("google_trends_score") or _result.get("trends_score")
        _news = _result.get("news_sentiment_score") or _result.get("news_sent")
        # H4 fix (2026-04-28): when the latest scan didn't populate
        # sentiment scores (no scan run yet, or the field was dropped
        # during the redesign port), fall back to the direct cached
        # fetchers so the Sentiment card isn't all dashes on first load.
        if _trends is None:
            try:
                _kw = (str(_coin or "bitcoin")).lower()
                _gt = _cached_google_trends_score(_kw)
                _trends = (_gt or {}).get("score")
            except Exception as _e_gt:
                logger.debug("[Signals] trends fallback failed: %s", _e_gt)
        if _news is None:
            try:
                _ns = _cached_news_sentiment(_pair)
                _news = (_ns or {}).get("score") or (_ns or {}).get("sentiment_score")
            except Exception as _e_ns:
                logger.debug("[Signals] news fallback failed: %s", _e_ns)
        _ds_ind_card(
            "Sentiment",
            [
                ("Fear & Greed",  _v(_fng_v, "{:.0f}"),                                 (_fng_d.get("label") or "").lower(),          "warning" if (_fng_v is not None and float(_fng_v) >= 60) else ("danger" if (_fng_v is not None and float(_fng_v) <= 30) else "")),
                ("Funding",       _v(_fund_v, "{:+.3f}%") if _fund_v is not None else "—", "neutral",                                  ""),
                ("Google trends", _v(_trends, "{:.0f}"),                                "",                                          ""),
                ("News sent.",    _v(_news, "{:+.2f}"),                                 "positive" if (_news is not None and float(_news) > 0) else ("negative" if (_news is not None and float(_news) < 0) else ""), "success" if (_news is not None and float(_news) > 0) else ("danger" if (_news is not None and float(_news) < 0) else "")),
            ],
        )

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── Recent signal history table ──
    try:
        _df_sig = _cached_signals_df(50)
        _hist_rows: list[dict] = []
        if _df_sig is not None and not _df_sig.empty:
            _df_pair_norm = _df_sig["pair"].astype(str).str.upper().str.replace("/", "", regex=False).str.replace("-", "", regex=False)
            _hits = _df_sig[_df_pair_norm.str.startswith(_coin)].sort_values("scan_timestamp", ascending=False).head(8)
            for _, _row in _hits.iterrows():
                _ts = _row.get("scan_timestamp", "")
                try:
                    _t_str = str(_ts)[:16].replace("T", " ")
                except Exception:
                    _t_str = "—"
                _d = str(_row.get("direction") or "").upper()
                _sig = "BUY" if _d in ("LONG", "BUY") else ("SELL" if _d in ("SHORT", "SELL") else "HOLD")
                _hist_rows.append({
                    "time": _t_str,
                    "signal": _sig,
                    "note": (_row.get("rationale") or _row.get("note") or "")[:80],
                    "return_pct": _row.get("return_pct") or _row.get("realized_return_pct"),
                })
        _ds_sig_hist(_hist_rows, title=f"Recent signal history · {_coin}", subtitle="last 8 state transitions")
    except Exception as _e_hist:
        logger.debug("[Signals] history table failed: %s", _e_hist)
        _ds_sig_hist([], title=f"Recent signal history · {_coin}", subtitle="No history available yet.")


# ──────────────────────────────────────────────
# PAGE: REGIMES (sibling-family-crypto-signal-REGIMES.html)
# ──────────────────────────────────────────────
def page_regimes():
    """Per-asset regime grid + macro overlay + per-regime weights.

    Pulls regime state per asset from latest scan_results / DB. Macro
    overlay rows pulled live from data_feeds. Regime-weight grid pulled
    from the model's REGIME_WEIGHTS config (or defaults if absent).
    """
    try:
        from ui import (
            render_top_bar as _ds_top_bar,
            page_header as _ds_page_header,
            regime_cards_grid as _ds_regimes,
            regime_state_bar as _ds_state_bar,
            macro_regime_overlay_card as _ds_macro_overlay,
            regime_weights_grid as _ds_weights_grid,
        )
    except Exception as _e_imp:
        logger.error("[Regimes] import failed: %s", _e_imp)
        st.error("Regimes page failed to load — check logs.")
        return

    _ds_level = st.session_state.get("user_level", "beginner")
    _ds_top_bar(
        breadcrumb=("Markets", "Regimes"),
        user_level=_ds_level,
        on_refresh=_refresh_all_data,
        on_theme=_toggle_theme,
        status_pills=_agent_topbar_pills(),
    )
    _ds_page_header(
        title="Regimes",
        subtitle="HMM-inferred market regime per asset + macro overlay. Regime-specific signal weights auto-adjust.",
        data_sources=[
            (str(model.TA_EXCHANGE).upper(), "live"),
            ("Glassnode", "live"),
            ("FRED", "cached"),
        ],
    )

    # C3 §C3.2: Regimes header — "Showing 8 of 33 pairs · click any to
    # drill in · More ▾ +25" with the More popover backed by the full
    # universe. Selected pair from the popover is added to
    # `regimes_visible_pairs` so it appears in the 8-card grid.
    _regimes_universe = list(model.PAIRS or [])
    _universe_n = len(_regimes_universe)
    try:
        from ui import pair_dropdown as _ds_pair_dropdown
    except Exception:
        _ds_pair_dropdown = None  # type: ignore[assignment]

    # Header text on its own row — full width — then the pair_dropdown
    # gets the entire row below. Open #1 fix (2026-04-30): the previous
    # [4, 2] split crammed pair_dropdown's 6 columns (5 quick + More)
    # into 1/3 of the page width, producing char-by-char vertical
    # wrapping on the BTC/USDT/etc. pills. Stacking the rows gives the
    # dropdown its full width and the pills render flat.
    st.markdown(
        f'<div style="font-size:13px;color:var(--text-muted);'
        f'margin:0 0 10px 2px;">Showing 8 of {_universe_n} pairs · '
        f'click any to drill in · use the dropdown to swap any pair into '
        f'the visible 8.</div>',
        unsafe_allow_html=True,
    )
    if _ds_pair_dropdown is not None and _regimes_universe:
        _ds_pair_dropdown(
            _regimes_universe,
            active=st.session_state.get(
                "regimes_focus_pair", _regimes_universe[0]
            ),
            key="regimes_focus_pair",
            label=f"More ▾  +{max(0, _universe_n - 5)}",
        )

    # ── Top: 8-card regime grid ──
    try:
        _df_sig = _cached_signals_df(500)
        _seen_pairs: set[str] = set()
        _regime_rows: list[dict] = []
        # Prefer current session results, then fall back to DB
        for _r in (st.session_state.get("scan_results") or []):
            _p = str(_r.get("pair") or _r.get("symbol") or "").upper()
            _ticker = _p.split("/")[0].split("-")[0]
            if not _ticker or _ticker in _seen_pairs:
                continue
            _state_raw = str(_r.get("regime") or _r.get("regime_label") or "").strip()
            for _pre in ("Regime: ", "Regime:", "Regime "):
                if _state_raw.lower().startswith(_pre.lower()):
                    _state_raw = _state_raw[len(_pre):].strip()
                    break
            _conf = _r.get("regime_confidence") or _r.get("regime_conf_pct")
            _regime_rows.append({
                "ticker": _ticker,
                "state": _state_raw or "Transition",
                "confidence": _conf,
                "since": "",
            })
            _seen_pairs.add(_ticker)
            if len(_regime_rows) >= 8:
                break
        # DB fallback if scan results don't fill 8
        if len(_regime_rows) < 8 and _df_sig is not None and not _df_sig.empty:
            _df_sorted = _df_sig.sort_values("scan_timestamp", ascending=False)
            for _, _row in _df_sorted.iterrows():
                _p = str(_row.get("pair") or "").upper()
                _ticker = _p.split("/")[0].split("-")[0]
                if not _ticker or _ticker in _seen_pairs:
                    continue
                _state_raw = str(_row.get("regime") or _row.get("regime_label") or "").strip()
                for _pre in ("Regime: ", "Regime:", "Regime "):
                    if _state_raw.lower().startswith(_pre.lower()):
                        _state_raw = _state_raw[len(_pre):].strip()
                        break
                _regime_rows.append({
                    "ticker": _ticker,
                    "state": _state_raw or "Transition",
                    "confidence": _row.get("regime_confidence") or _row.get("regime_conf_pct"),
                    "since": "",
                })
                _seen_pairs.add(_ticker)
                if len(_regime_rows) >= 8:
                    break
        if not _regime_rows:
            # No data yet — show placeholder cards for the must-have set
            for _t in ["BTC", "ETH", "XRP", "SOL", "AVAX", "LINK", "DOGE", "BNB"]:
                _regime_rows.append({"ticker": _t, "state": "Transition", "confidence": None, "since": "no scan yet"})
        _ds_regimes(_regime_rows[:8], cols=4)
    except Exception as _e_rgrid:
        logger.debug("[Regimes] regime grid render failed: %s", _e_rgrid)

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── 2-col: state-bar timeline (BTC) + macro overlay ──
    _col_l, _col_r = st.columns([1.2, 1])

    with _col_l:
        # Compute approximate state-bar segments for BTC over the last 90d.
        # If we have a regime_history table or per-day regimes in scan_results,
        # use it. Otherwise show a representative example using the latest
        # known state (single 100% segment) so the layout still renders.
        try:
            # C8-fix (2026-04-30): focus the placeholder lookup on the
            # currently-selected focus pair (set by the C3 More
            # dropdown), not hardcoded BTC. Was a real bug — picking
            # SOL kept the bar showing BTC's state because the loop
            # below only matched `_p.startswith("BTC")`.
            _focus_pair = st.session_state.get(
                "regimes_focus_pair", "BTC/USDT",
            )
            _focus_short = (_focus_pair.split("/")[0].split("-")[0]
                            or "BTC").upper()
            _state_now = "bull"
            _conf_now = None
            for _r in (st.session_state.get("scan_results") or []):
                _p = str(_r.get("pair") or "").upper()
                if _p.startswith(_focus_short):
                    _state_raw = str(_r.get("regime") or _r.get("regime_label") or "").strip()
                    for _pre in ("Regime: ", "Regime:", "Regime "):
                        if _state_raw.lower().startswith(_pre.lower()):
                            _state_raw = _state_raw[len(_pre):].strip()
                            break
                    _state_now = (_state_raw or "bull").lower()
                    _conf_now = _r.get("regime_confidence")
                    break
            # C8 (Phase C plan §C8): real segmented 90d history from
            # regime_history table when available. Fall back to a
            # single 100%-current-state segment when the table has no
            # rows for this focus pair (fresh deploy, no scans run).
            _segments: list[tuple[str, float]] = []
            _hist_count = 0
            try:
                from database import (
                    regime_history_segments as _rh_segs,
                    regime_history_count as _rh_count,
                )
                _segments = _rh_segs(_focus_pair, days=90)
                _hist_count = _rh_count(_focus_pair, days=90)
            except Exception as _e_rh:
                logger.debug("[Regimes] regime_history fetch failed: %s",
                             _e_rh)
                _segments = []
            if not _segments:
                _segments = [(_state_now, 100.0)]
            # Build a 90d label scale for the bar's date row when we
            # have real history. Three labels: -90d / -45d / today.
            _date_labels = ["-90d", "-45d", "today"] if len(_segments) > 1 else None
            # C8-fix (2026-04-30): the bar visual is identical when
            # there are 0 DB rows vs N rows that all share the same
            # state. Surface the actual snapshot count in the note so
            # users can tell whether their scans are landing in the
            # regime_history table even when the bar still looks like
            # a single segment.
            if _hist_count == 0:
                _hist_msg = (
                    "No regime history recorded for "
                    f"{_focus_short}/USDT yet — run a scan that includes "
                    "this pair and the bar will start segmenting."
                )
            elif len(_segments) == 1:
                _hist_msg = (
                    f"{_hist_count} scan snapshot{'s' if _hist_count != 1 else ''} "
                    f"recorded for {_focus_short}/USDT, all in the "
                    f"{_segments[0][0].title()} state — bar will segment "
                    "once the regime changes across scans."
                )
            else:
                _hist_msg = (
                    f"{_hist_count} scan snapshots over the last 90d, "
                    f"{len(_segments)} distinct regime bands."
                )
            # C9 (2026-04-30): level-aware note. Beginner gets plain
            # English; Intermediate the standard HMM line; Advanced
            # the full HMM diagnostic + snapshot count.
            if _ds_level == "beginner":
                _note = (
                    f"Right now, {_focus_short} looks {_state_now.title()} "
                    f"to the model. The bar above shows how the regime has "
                    f"moved over the last 90 days. {_hist_msg}"
                )
            elif _ds_level == "intermediate":
                _note = (
                    f"HMM regime: {_state_now.title()}"
                    f"{f' · confidence {int(_conf_now)}%' if _conf_now is not None else ''}. "
                    f"{_hist_msg}"
                )
            else:  # advanced
                _note = (
                    f"HMM 4-state model over composite score + on-chain + "
                    f"macro features. Current state: {_state_now.title()}"
                    f"{f', confidence {int(_conf_now)}%' if _conf_now is not None else ''}. "
                    f"{_hist_msg}"
                )
            _ds_state_bar(
                _segments,
                title=f"{_focus_short} regime state · last 90d",
                date_labels=_date_labels,
                note=_note,
            )
        except Exception as _e_sbar:
            logger.debug("[Regimes] state bar render failed: %s", _e_sbar)

    with _col_r:
        # Macro overlay card — pulls live values
        try:
            _gm = _cached_global_market() or {}
            _me = _cached_macro_enrichment() or {}
            _btc_dom = _gm.get("btc_dominance_pct", _gm.get("btc_dominance"))
            _btc_dom_7d = _gm.get("btc_dominance_7d_change_pct", _gm.get("btc_dominance_7d_ppt"))
            _yf = {}
            try:
                _yf = data_feeds.fetch_yfinance_macro() or {}
            except Exception:
                pass
            _dxy = _yf.get("dxy") or _me.get("dxy")
            _dxy_30d = _yf.get("dxy_30d_change_pct") or _yf.get("dxy_30d_ret_pct") or _me.get("dxy_30d_change_pct")
            _vix = _yf.get("vix") or _me.get("vix")
            _vix_30d = _yf.get("vix_30d_change_pct") or _me.get("vix_30d_change_pct")
            _ust10 = _yf.get("treasury_10y") or _me.get("treasury_10y")
            _ust10_7d = _yf.get("treasury_10y_7d_change_bps") or _me.get("treasury_10y_7d_change_bps")
            # P1-25 audit fix — On-chain page F&G now via cached helper (24h).
            _fng_d = _sg_cached_fear_greed()
            _fng_v = _fng_d.get("value")
            _fng_7d = _fng_d.get("change_7d") or _me.get("fng_7d_change")
            _hy = _yf.get("hy_spread_bps") or _me.get("hy_spread_bps")
            _hy_30d = _yf.get("hy_spread_30d_change_bps") or _me.get("hy_spread_30d_change_bps")

            def _fmt_pct(v, decimals=1, suffix=" ppts"):
                if v is None:
                    return ""
                try:
                    fv = float(v)
                    sign = "+" if fv > 0 else ("−" if fv < 0 else "")
                    return f"{sign}{abs(fv):.{decimals}f}{suffix}"
                except Exception:
                    return ""
            def _delta_dir(v):
                if v is None:
                    return ""
                try:
                    return "up" if float(v) > 0 else ("down" if float(v) < 0 else "")
                except Exception:
                    return ""

            _rows = []
            if _btc_dom is not None:
                _rows.append({
                    "name": "BTC Dominance",
                    "value": f"{float(_btc_dom):.1f}%",
                    "delta_text": f"{_fmt_pct(_btc_dom_7d, 1, ' ppts · 7d')}" if _btc_dom_7d is not None else "",
                    "delta_dir": _delta_dir(_btc_dom_7d),
                    "sentiment": "bull" if (_btc_dom_7d is not None and float(_btc_dom_7d) > 0) else "neut",
                    "sentiment_label": "bullish" if (_btc_dom_7d is not None and float(_btc_dom_7d) > 0) else "neutral",
                })
            if _dxy is not None:
                _rows.append({
                    "name": "DXY",
                    "value": f"{float(_dxy):.2f}",
                    "delta_text": f"{_fmt_pct(_dxy_30d, 1, '% · 30d')}" if _dxy_30d is not None else "",
                    "delta_dir": _delta_dir(_dxy_30d),
                    "sentiment": "bull" if (_dxy_30d is not None and float(_dxy_30d) < 0) else "bear",
                    "sentiment_label": "risk-on" if (_dxy_30d is not None and float(_dxy_30d) < 0) else "risk-off",
                })
            if _vix is not None:
                _rows.append({
                    "name": "VIX",
                    "value": f"{float(_vix):.1f}",
                    "delta_text": f"{_fmt_pct(_vix_30d, 0, '% · 30d')}" if _vix_30d is not None else "",
                    "delta_dir": _delta_dir(_vix_30d),
                    "sentiment": "bull" if (_vix_30d is not None and float(_vix_30d) < 0) else "bear",
                    "sentiment_label": "risk-on" if (_vix_30d is not None and float(_vix_30d) < 0) else "risk-off",
                })
            if _ust10 is not None:
                _rows.append({
                    "name": "10Y yield",
                    "value": f"{float(_ust10):.2f}%",
                    "delta_text": f"{_fmt_pct(_ust10_7d, 0, 'bps · 7d')}" if _ust10_7d is not None else "",
                    "delta_dir": _delta_dir(_ust10_7d),
                    "sentiment": "bull" if (_ust10_7d is not None and float(_ust10_7d) < 0) else "bear",
                    "sentiment_label": "tailwind" if (_ust10_7d is not None and float(_ust10_7d) < 0) else "headwind",
                })
            if _fng_v is not None:
                _rows.append({
                    "name": "Fear & Greed",
                    "value": str(int(_fng_v)),
                    "delta_text": f"{_fmt_pct(_fng_7d, 0, ' · 7d')}" if _fng_7d is not None else "",
                    "delta_dir": _delta_dir(_fng_7d),
                    "sentiment": "neut" if 35 <= float(_fng_v) <= 65 else ("bull" if float(_fng_v) > 65 else "bear"),
                    "sentiment_label": _fng_d.get("label") or "",
                })
            if _hy is not None:
                _rows.append({
                    "name": "HY spreads",
                    "value": f"{int(float(_hy))} bps",
                    "delta_text": f"{_fmt_pct(_hy_30d, 0, ' bps · 30d')}" if _hy_30d is not None else "",
                    "delta_dir": _delta_dir(_hy_30d),
                    "sentiment": "bull" if (_hy_30d is not None and float(_hy_30d) < 0) else "bear",
                    "sentiment_label": "tightening" if (_hy_30d is not None and float(_hy_30d) < 0) else "widening",
                })

            # Overall macro regime label
            _macro_regime = _me.get("macro_regime") or _me.get("macro_regime_label") or ""
            _macro_conf = _me.get("macro_regime_confidence_pct") or _me.get("macro_confidence")
            _ds_macro_overlay(
                _rows,
                title="Macro regime · overlay",
                overall_label=str(_macro_regime).title() if _macro_regime else "",
                overall_confidence=_macro_conf,
            )
        except Exception as _e_macro:
            logger.debug("[Regimes] macro overlay failed: %s", _e_macro)

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # ── Signal weights by regime ──
    try:
        # Try to read REGIME_WEIGHTS from model; fall back to mockup defaults.
        _weights = getattr(model, "REGIME_WEIGHTS", None)
        if not isinstance(_weights, dict) or not _weights:
            _weights = {
                "Bull":         {"Tech": 0.30, "Macro": 0.15, "Sent": 0.20, "On-chain": 0.35},
                "Accumulation": {"Tech": 0.20, "Macro": 0.15, "Sent": 0.15, "On-chain": 0.50},
                "Distribution": {"Tech": 0.35, "Macro": 0.25, "Sent": 0.25, "On-chain": 0.15},
                "Bear":         {"Tech": 0.40, "Macro": 0.35, "Sent": 0.15, "On-chain": 0.10},
            }
        _tone_for = {
            "Bull": "success", "bull": "success",
            "Accumulation": "info", "accum": "info", "accumulation": "info",
            "Distribution": "warning", "dist": "warning", "distribution": "warning",
            "Bear": "danger", "bear": "danger",
            "Transition": "warning", "trans": "warning", "transition": "warning",
        }
        _entries = []
        for _name, _w in _weights.items():
            if isinstance(_w, dict):
                _entries.append((_name, _tone_for.get(_name, _tone_for.get(str(_name).lower(), "warning")), _w))
        if _entries:
            _ds_weights_grid(_entries[:4])
    except Exception as _e_wgrid:
        logger.debug("[Regimes] weights grid failed: %s", _e_wgrid)


# ──────────────────────────────────────────────
# PAGE: ON-CHAIN (thin design-system pass — no dedicated mockup)
# ──────────────────────────────────────────────
def page_onchain():
    """On-chain metrics page — thin design-system pass per Cowork directive.

    No dedicated mockup exists for ON-CHAIN; this page applies the design-
    system topbar + page header + ds-card primitives over the existing
    on-chain data sources. Content surface stays close to the existing
    on-chain section that used to live inside the Dashboard tabs — we
    don't redesign the data, just the chrome around it.
    """
    try:
        from ui import (
            render_top_bar as _ds_top_bar,
            page_header as _ds_page_header,
            indicator_card as _ds_ind_card,
            ticker_pill_button as _ds_ticker_pill,
        )
    except Exception as _e_imp:
        logger.error("[On-chain] import failed: %s", _e_imp)
        st.error("On-chain page failed to load — check logs.")
        return

    _oc_lv = st.session_state.get("user_level", "beginner")
    _ds_top_bar(
        breadcrumb=("Research", "On-chain"),
        user_level=_oc_lv,
        on_refresh=_refresh_all_data,
        on_theme=_toggle_theme,
        status_pills=_agent_topbar_pills(),
    )
    # C9 (Phase C plan §C9, 2026-04-30): level-aware page subtitle.
    # Beginner gets a plain-English description of what on-chain
    # metrics actually measure; Intermediate gets a condensed
    # technical line; Advanced gets the original full reference.
    if _oc_lv == "beginner":
        _oc_sub = ("These numbers come straight from the blockchain itself — "
                   "they show what holders are actually doing with their coins, "
                   "not just what the price chart says. Useful for spotting "
                   "long-cycle inflection points.")
    elif _oc_lv == "intermediate":
        _oc_sub = ("On-chain valuation + flow metrics for major pairs: "
                   "MVRV-Z, SOPR, exchange reserve deltas, active addresses.")
    else:  # advanced
        _oc_sub = ("Glassnode + Dune metrics for the major majors. "
                   "MVRV-Z, SOPR, exchange flows, active addresses.")
    _ds_page_header(
        title="On-chain",
        subtitle=_oc_sub,
        data_sources=[
            ("Glassnode", "live"),
            ("Dune", "cached"),
            ("Native RPC", "live"),
        ],
    )

    # C3 §C3.3: each card slot is independently swappable to any pair
    # in the universe. Default slots are BTC / ETH / XRP (matching the
    # legacy hardcoded layout). Selections persist across reruns under
    # the per-slot keys so a user's swap on slot 1 doesn't move slot 2.
    _oc_universe_tickers = sorted({p.split("/")[0].split("-")[0]
                                   for p in (model.PAIRS or [])}) or ["BTC", "ETH", "XRP"]
    _oc_slot_keys = [
        ("onchain_slot_1_ticker", "BTC"),
        ("onchain_slot_2_ticker", "ETH"),
        ("onchain_slot_3_ticker", "XRP"),
    ]
    for _k, _default in _oc_slot_keys:
        if st.session_state.get(_k) not in _oc_universe_tickers:
            st.session_state[_k] = _default
    _oc_picker_cols = st.columns(3)
    for _i, (_k, _default) in enumerate(_oc_slot_keys):
        with _oc_picker_cols[_i]:
            _ds_ticker_pill(
                st.session_state[_k],
                pairs=_oc_universe_tickers,
                key=_k,
                label_override=f"Slot {_i+1}: {st.session_state[_k]}  ▾",
            )

    # Pull on-chain data per coin from the latest scan result (or DB fallback,
    # or — C4 fix, 2026-04-28 — a direct on-chain fetch as last resort so the
    # page is never empty when the user lands on it without having run a scan
    # first). The redesigned indicator cards expect mvrv_z/sopr/
    # exchange_reserve_delta_7d/active_addresses_24h, but data_feeds.
    # get_onchain_metrics returns mvrv_z/sopr/net_flow/vol_mcap_ratio. We
    # adapt the field names here so the cards populate correctly without
    # touching the fetcher (proven healthy by §22 fixtures + §4 baseline).
    def _result_for(ticker: str) -> dict:
        for _r in (st.session_state.get("scan_results") or []):
            _p = str(_r.get("pair") or _r.get("symbol") or "").upper()
            if _p.startswith(ticker):
                return _r
        try:
            _df = _cached_signals_df(500)
            if _df is not None and not _df.empty:
                _df_pn = _df["pair"].astype(str).str.upper().str.replace("/", "", regex=False).str.replace("-", "", regex=False)
                _hits = _df[_df_pn.str.startswith(ticker)]
                if not _hits.empty:
                    return _hits.sort_values("scan_timestamp", ascending=False).iloc[0].to_dict()
        except Exception as _e:
            logger.debug("[On-chain] DB lookup for %s failed: %s", ticker, _e)
        # Direct on-chain fetch fallback — keeps the page from being
        # data-less on first load. get_onchain_metrics is cached
        # (_ONCHAIN_TTL in data_feeds), so repeated page renders won't
        # hammer the upstream APIs.
        try:
            _pair = f"{ticker}/USDT"
            _oc = data_feeds.get_onchain_metrics(_pair) or {}
            if _oc:
                # Field-name adapter — map fetcher output → card expectations.
                return {
                    "pair": _pair,
                    "mvrv_z": _oc.get("mvrv_z"),
                    "mvrv": _oc.get("mvrv_z"),  # legacy alias used by some cards
                    "sopr": _oc.get("sopr"),
                    # Approximate exchange_reserve_delta_7d from net_flow.
                    # get_onchain_metrics returns net_flow as a ±400-scaled
                    # proxy; we surface it directly. The card displays
                    # outflow/inflow tone correctly off the sign alone.
                    "exchange_reserve_delta_7d": _oc.get("net_flow"),
                    # Active addresses isn't in the free Binance ticker —
                    # leave None so the card renders the "—" graceful empty.
                    "active_addresses_24h": None,
                    "_source": _oc.get("source", "fallback"),
                }
        except Exception as _e_oc:
            logger.debug("[On-chain] direct fetch for %s failed: %s", ticker, _e_oc)
        return {}

    def _v(x, fmt="{:.2f}"):
        if x is None:
            return "—"
        try:
            return fmt.format(float(x))
        except Exception:
            return str(x)

    # C3 §C3.3: 3 indicator card slots, each independently bound to its
    # own ticker_pill_button selection. Was previously hardcoded BTC /
    # ETH / XRP — now reads from session_state per slot so the user can
    # swap any slot to any pair in the universe.
    _slot_tickers = [st.session_state[k] for k, _ in _oc_slot_keys]
    _slot_data = [_result_for(t) for t in _slot_tickers]

    _c1, _c2, _c3 = st.columns(3)
    for _slot_col, _slot_ticker, _slot_d in zip(
        (_c1, _c2, _c3), _slot_tickers, _slot_data
    ):
        with _slot_col:
            _ds_ind_card(
                f"{_slot_ticker} · valuation & flows",
                [
                    ("MVRV-Z",
                     _v(_slot_d.get("mvrv_z") or _slot_d.get("mvrv"), "{:.2f}"),
                     ("mid-cycle" if (_slot_d.get("mvrv_z")
                                      and 1 < float(_slot_d.get("mvrv_z") or 0) < 5)
                      else ""),
                     ""),
                    ("SOPR",
                     _v(_slot_d.get("sopr"), "{:.3f}"),
                     ("profit taking" if (_slot_d.get("sopr")
                                          and float(_slot_d.get("sopr") or 0) > 1)
                      else ""),
                     ""),
                    ("Exch. reserve",
                     (_v(_slot_d.get("exchange_reserve_delta_7d"), "{:+,.0f}")
                      if _slot_d.get("exchange_reserve_delta_7d") is not None
                      else "—"),
                     ("outflow 7d" if (_slot_d.get("exchange_reserve_delta_7d")
                                       and float(_slot_d.get("exchange_reserve_delta_7d") or 0) < 0)
                      else "inflow 7d"),
                     ("success" if (_slot_d.get("exchange_reserve_delta_7d")
                                    and float(_slot_d.get("exchange_reserve_delta_7d") or 0) < 0)
                      else "")),
                    ("Active addr.",
                     (_v(_slot_d.get("active_addresses_24h"), "{:,.0f}")
                      if _slot_d.get("active_addresses_24h") is not None
                      else "—"),
                     "24h",
                     ""),
                ],
            )

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # Whale activity / large transfers (using existing whale_tracker if available)
    # P0 audit fix — was calling _cached_whale_activity() with no arguments
    # (signature requires pair: str, price: float) so On-chain page silently
    # crashed into the outer try/except on every load and the entire whale
    # section was dead. whale_tracker.get_whale_activity returns a dict; the
    # legacy isinstance(list) check was always False even when the call shape
    # was right. Pass a sane default pair + price=0.0 (the tracker handles
    # both shapes), then accept either dict-with-events or bare-list returns.
    try:
        _whale_raw = _cached_whale_activity("BTC/USDT", 0.0)
        _whale = []
        if isinstance(_whale_raw, dict):
            _whale = (_whale_raw.get("events")
                      or _whale_raw.get("transfers")
                      or _whale_raw.get("recent")
                      or [])
        elif isinstance(_whale_raw, list):
            _whale = _whale_raw
        if _whale and isinstance(_whale, list) and len(_whale) > 0:
            st.markdown(
                '<div class="ds-card">'
                '<div class="ds-card-hd">'
                '<div class="ds-card-title">Whale activity · large transfers (last 24h)</div>'
                f'<div style="color:var(--text-muted);font-size:12px;">{len(_whale)} events</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            for _w in _whale[:8]:
                _amt = _w.get("amount_usd") or _w.get("value_usd") or 0
                _coin = _w.get("symbol") or _w.get("coin") or "—"
                _direction = _w.get("direction") or _w.get("flow") or ""
                _time = str(_w.get("timestamp") or "")[:16]
                st.markdown(
                    f'<div style="display:grid;grid-template-columns:110px 60px 1fr 100px;gap:12px;'
                    f'padding:8px 4px;border-bottom:1px solid var(--border);font-size:12.5px;">'
                    f'<span style="font-family:var(--font-mono);color:var(--text-muted);">{_time}</span>'
                    f'<span style="font-weight:600;">{_coin}</span>'
                    f'<span style="color:var(--text-secondary);">{_direction}</span>'
                    f'<span style="font-family:var(--font-mono);text-align:right;">${float(_amt):,.0f}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="ds-card">'
                '<div class="ds-card-hd"><div class="ds-card-title">Whale activity</div></div>'
                '<div style="color:var(--text-muted);font-size:13px;padding:12px 4px;">'
                'No large transfers in the last 24h, or whale tracker is offline.'
                '</div></div>',
                unsafe_allow_html=True,
            )
    except Exception as _e_w:
        logger.debug("[On-chain] whale activity render failed: %s", _e_w)

    st.markdown('<div style="height:20px;"></div>', unsafe_allow_html=True)

    # Footnote about data freshness
    st.markdown(
        '<div class="ds-card" style="background:rgba(99,102,241,0.06);'
        'border:1px solid rgba(99,102,241,0.20);font-size:12px;color:var(--text-muted);'
        'padding:12px 16px;">'
        'On-chain data is rate-limited on Glassnode\'s free tier (cached 1h). '
        'A dedicated On-chain page mockup is on the design backlog; this thin pass '
        'applies the design-system tokens to the existing data sources.'
        '</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────
# ROUTER
# ──────────────────────────────────────────────
# C-fix-11 (2026-05-02): fire the mandatory first-session scan right
# before page render. Defined far above (after init_state) but called
# here because it depends on `_start_scan` which lives mid-file. Idempotent
# via session_state["_c11_first_init_done"] — only fires once per session.
_maybe_fire_first_session_scan()

audit("page_view", page=page, level=st.session_state.get("user_level", "beginner"))
if page == "Dashboard":
    page_dashboard()
elif page == "Signals":
    page_signals()
elif page == "Regimes":
    page_regimes()
elif page == "On-chain":
    page_onchain()
elif page == "Config Editor":
    page_config()
elif page == "Backtest Viewer":
    page_backtest()
elif page == "Arbitrage":
    page_arbitrage()
elif page == "Agent":
    page_agent()
elif page == "Alerts":
    # C6 (Phase C plan §C6, 2026-04-30): Alerts is now a first-class
    # page — used to deep-link into Settings → Alerts tab via the
    # _settings_tab=Alerts side-effect (now removed).
    page_alerts()

# ── Persistent footer: past-performance disclaimer + legal (R3h Tier-1) ───────
# Audit R3c HIGH: every main page must carry the disclaimer (compliance red flag
# for a TAMP demo if absent). Rendered once at the bottom of whichever page
# just ran above.
st.markdown("---")
render_past_performance_disclaimer()
try:
    render_legal_footer()
except Exception:
    pass
