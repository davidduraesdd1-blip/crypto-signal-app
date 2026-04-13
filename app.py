"""
app.py — Crypto Signal Model v5.9.13 | Streamlit Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import html as _html
import json
import logging
import os
import threading
import time
import requests
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
    for key in list(event.get("extra", {}).keys()):
        if any(x in key.upper() for x in ["KEY", "SECRET", "TOKEN", "PASSWORD", "DSN"]):
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

# PERF: module-level Session reuses TCP connections for all requests.get() calls in this file
_http = requests.Session()
_http.headers.update({"Accept-Encoding": "gzip, deflate", "Connection": "keep-alive"})

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


def _cached_global_market() -> dict:
    """Return CoinGecko global market stats. data_feeds.py has its own 5-min in-memory
    cache so this does not hit the network on every Streamlit re-run. @st.cache_data is
    intentionally NOT used here — it would lock in the $0M fallback for 5 minutes when
    CoinGecko rate-limits the first cold-start call, preventing retry on subsequent renders."""
    import data_feeds as _df
    return _df.get_global_market()


def _cached_trending_coins() -> list:
    """Return CoinGecko trending coins. data_feeds.py has its own in-memory cache.
    @st.cache_data removed for same reason as _cached_global_market — avoids locking
    in empty-list fallback when CoinGecko rate-limits on first cold-start call."""
    import data_feeds as _df
    return _df.get_trending_coins()


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


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_api_health() -> dict:
    """Cache API health check pings — 5-min TTL (#17 security hardening)."""
    return data_feeds.validate_api_keys()


@st.cache_data(ttl=120, show_spinner=False, max_entries=3)
def _cached_arb_opportunities_df(limit: int = 100) -> "pd.DataFrame":
    """Cache arb_opportunities read — 2-min TTL."""
    return _db.get_arb_opportunities_df(limit=limit)


@st.cache_data(ttl=300, show_spinner=False, max_entries=1)
def _cached_resolved_feedback_df(days: int = 365) -> "pd.DataFrame":
    """Cache resolved feedback — calendar heatmap, 5-min TTL."""
    return _db.get_resolved_feedback_df(days=days)


@st.cache_data(ttl=300, show_spinner=False, max_entries=30)
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
    except Exception:
        pass


# ── PERF: @st.cache_data wrappers for slow external module calls ──────────────
@st.cache_data(ttl=900, show_spinner=False, max_entries=24)
def _cached_news_sentiment(pair: str) -> dict:
    """Streamlit-level cache for news sentiment — 15 min TTL, cross-worker dedup.
    Module-level _cache in news_sentiment.py is per-process; this bridges workers."""
    if _news_mod is None:
        return {}
    return _news_mod.get_news_sentiment(pair)


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
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.start()
        # Start alert threshold calibration job (runs every 6 hours)
        _setup_calibration_job()
        # P1: Startup catch-up — resolve any pending feedback outcomes immediately
        # so intelligence is never lost after a Streamlit restart/idle shutdown.
        def _startup_feedback_catchup():
            try:
                model.run_feedback_loop()
                logging.info("[Startup] Feedback catch-up complete")
            except Exception as _e:
                logging.debug(f"[Startup] Feedback catch-up (non-critical): {_e}")
        import threading as _t
        _t.Thread(target=_startup_feedback_catchup, name="StartupFeedbackCatchup", daemon=True).start()
    return _scheduler


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


def _in_quiet_hours(now_str: str, start_str: str, end_str: str) -> bool:
    """Return True if now_str (HH:MM UTC) falls in the [start, end) quiet window.
    Handles overnight wrap (e.g. 22:00–06:00)."""
    try:
        h, m     = map(int, now_str.split(":"))
        sh, sm   = map(int, start_str.split(":"))
        eh, em   = map(int, end_str.split(":"))
        now_mins = h  * 60 + m
        s_mins   = sh * 60 + sm
        e_mins   = eh * 60 + em
        if s_mins <= e_mins:           # same-day window e.g. 09:00–17:00
            return s_mins <= now_mins < e_mins
        else:                          # overnight wrap e.g. 22:00–06:00
            return now_mins >= s_mins or now_mins < e_mins
    except Exception:
        return False

# ── Page config must be first ──
st.set_page_config(
    page_title="Crypto Signal Model v5.9.13",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Professional CSS design system (must come before any st.* calls) ──
_ui.inject_css()

# ── #59 UI/UX Refresh — global signal/card color variables ────────────────────
SIGNAL_CSS = """
<style>
.signal-buy  { color: #00C853; font-weight: bold; }
.signal-sell { color: #D50000; font-weight: bold; }
.signal-hold { color: #FF6D00; font-weight: bold; }
.metric-positive { color: #00C853; }
.metric-negative { color: #D50000; }
.card-container  { background: #1E1E1E; border-radius: 8px; padding: 12px; margin-bottom: 8px; }
</style>
"""
st.markdown(SIGNAL_CSS, unsafe_allow_html=True)

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
                    except Exception:
                        pass
        except Exception:
            pass
    threading.Thread(target=_ohlcv_prewarm, daemon=True, name="ohlcv-prewarm").start()

# Auto-start autonomous agent if enabled in config (idempotent)
if _agent is not None:
    _agent_cfg_boot = _cached_alerts_config()
    if _agent_cfg_boot.get("agent_enabled", False):
        _agent.supervisor.start()

# ──────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ──────────────────────────────────────────────
_ui.sidebar_header(model.VERSION, model.TA_EXCHANGE, len(model.PAIRS))

# ── Paper / Live mode persistent badge ───────────────────────────────────────
try:
    _exec_mode_cfg = _cached_alerts_config()
    _is_live_mode  = _exec_mode_cfg.get("live_trading_enabled", False)
    if _is_live_mode:
        st.sidebar.markdown(
            '<div style="background:rgba(246,70,93,0.15);border:1px solid rgba(246,70,93,0.4);'
            'border-radius:8px;padding:7px 12px;text-align:center;margin-bottom:8px">'
            '<span style="color:#f6465d;font-size:11px;font-weight:800;letter-spacing:0.8px">'
            '🔴 LIVE TRADING ACTIVE — Real money at risk</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            '<div style="background:rgba(99,102,241,0.1);border:1px solid rgba(99,102,241,0.25);'
            'border-radius:8px;padding:6px 12px;text-align:center;margin-bottom:8px">'
            '<span style="color:#818cf8;font-size:11px;font-weight:700;letter-spacing:0.5px">'
            '📄 Paper Mode — Simulated trades only</span></div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass

# ── 3-Level Experience selector (Phase 1) ─────────────────────────────────────
# Beginner = default; persists across all pages via session_state.
# beginner_mode kept for backward compat with inject_beginner_mode_js().
st.sidebar.markdown(
    '<span style="font-size:11px;color:rgba(168,180,200,0.5);'
    'font-weight:600;text-transform:uppercase;letter-spacing:0.8px">'
    'Experience Level</span>',
    unsafe_allow_html=True,
)
_LEVEL_OPTIONS = ["beginner", "intermediate", "advanced"]
_LEVEL_LABELS  = {
    "beginner":     "🟢 Beginner",
    "intermediate": "🟡 Intermediate",
    "advanced":     "🔴 Advanced",
}
_cur_sg_level = st.session_state.get("user_level", "beginner")
_sg_level_val = st.sidebar.radio(
    "User Level",
    options=_LEVEL_OPTIONS,
    format_func=lambda lv: _LEVEL_LABELS[lv],
    index=_LEVEL_OPTIONS.index(_cur_sg_level) if _cur_sg_level in _LEVEL_OPTIONS else 0,
    key="sg_user_level_radio",
    label_visibility="collapsed",
    help=(
        "Beginner: plain-English view, tooltips always visible, simplified signals. "
        "Intermediate: key numbers + condensed explanations. "
        "Advanced: full technical detail, all raw numbers."
    ),
)
st.session_state["user_level"]    = _sg_level_val
# Backward compat: beginner_mode = True when NOT Advanced (drives inject_beginner_mode_js)
_bm_val = (_sg_level_val != "advanced")
st.session_state["beginner_mode"] = _bm_val
_ui.inject_beginner_mode_js(_bm_val)

# ── Demo / Sandbox mode toggle (#67) ─────────────────────────────────────────
_demo_val = st.sidebar.toggle(
    "Demo / Sandbox",
    value=st.session_state.get("demo_mode", False),
    key="demo_mode_toggle",
    help="Demo mode: shows synthetic placeholder data — no real API calls. Safe for screenshots and onboarding.",
)
st.session_state["demo_mode"] = _demo_val
if _demo_val:
    st.sidebar.markdown(
        '<div style="background:#1c1200;border:1px solid rgba(251,191,36,0.3);border-radius:6px;'
        'padding:6px 10px;font-size:11px;color:#FBBF24;margin-top:-6px">⚠️ DEMO MODE — synthetic data</div>',
        unsafe_allow_html=True,
    )
_demo_mode = _demo_val

# ── Crypto Glossary (always visible in sidebar) ───────────────────────────────
st.sidebar.markdown("")
_ui.glossary_popover(user_level=st.session_state.get("user_level", "beginner"))

# ── Theme toggle (item 18 — light/dark mode) ──────────────────────────────────
_ui.render_theme_toggle_sg()

# ── Refresh All Data (item 27) ────────────────────────────────────────────────
st.sidebar.markdown(
    '<span style="font-size:11px;color:rgba(168,180,200,0.5);'
    'font-weight:600;text-transform:uppercase;letter-spacing:0.8px">'
    'Data</span>',
    unsafe_allow_html=True,
)
if st.sidebar.button("🔄 Refresh All Data", help="Clear all caches and reload fresh data from all sources", width="stretch"):
    try:
        st.cache_data.clear()
    except Exception:
        for _fn in [
            _cached_signals_df, _cached_paper_trades_df, _cached_feedback_df,
            _cached_backtest_df, _cached_scan_results, _cached_execution_log_df,
            _cached_agent_log_df, _cached_api_health, _cached_arb_opportunities_df,
            _cached_resolved_feedback_df, _cached_alerts_config, _cached_news_sentiment,
            _cached_whale_activity,
        ]:
            try:
                _fn.clear()
            except Exception:
                pass
    # Also clear module-level cache dicts in data_feeds — not covered by st.cache_data.clear()
    try:
        data_feeds.clear_all_module_caches()
    except Exception:
        pass
    st.rerun()

st.sidebar.markdown("---")

# ── Navigation — level-aware page list (Item 3) ───────────────────────────────
# Beginner:     3 pages (signals, trades, AI assistant)
# Intermediate: 5 pages (+ performance + opportunities)
# Advanced:     all 6 pages
_NAV_BEGINNER = [
    "📊 My Signals",
    "🤖 AI Assistant",
]
_NAV_INTERMEDIATE = [
    "📊 My Signals",
    "🤖 AI Assistant",
    "📈 Performance",
    "⚡ Opportunities",
]
_NAV_ADVANCED = [
    "📊 My Signals",
    "⚙️ Settings",
    "📈 Performance",
    "⚡ Opportunities",
    "🤖 AI Assistant",
]
_nav_by_level = {
    "beginner":     _NAV_BEGINNER,
    "intermediate": _NAV_INTERMEDIATE,
    "advanced":     _NAV_ADVANCED,
}
_nav_options = _nav_by_level.get(_sg_level_val, _NAV_BEGINNER)

page = st.sidebar.radio(
    "Navigate",
    _nav_options,
    label_visibility="collapsed",
)

# Normalise page name — map display labels to internal page keys
_PAGE_MAP = {
    "📊 My Signals":    "Dashboard",
    "📊 Dashboard":     "Dashboard",
    "⚙️ Settings":      "Config Editor",
    "📈 Performance":   "Backtest Viewer",
    "📈 Performance History": "Backtest Viewer",
    "⚡ Opportunities": "Arbitrage",
    "⚡ Arbitrage":     "Arbitrage",
    "🤖 AI Assistant":  "Agent",
    "🤖 AI Agent":      "Agent",
}
# Override page if a programmatic navigation target was set (e.g. "Configure Alerts" button)
_nav_override = st.session_state.pop("_nav_target", None)
if _nav_override:
    page = _nav_override
else:
    page = _PAGE_MAP.get(page, page)

# ──────────────────────────────────────────────
# SIDEBAR: AUTO-SCAN (Item 4 — compact for beginners)
# ──────────────────────────────────────────────
st.sidebar.markdown("---")
# CQ-10: Load alerts config once per sidebar render; reused by all expander sections.
# Each expander that needs to mutate gets its own .copy() or re-reads when saving.
_sidebar_alerts_cfg = _cached_alerts_config()

# Item 4: beginners see a simple ON/OFF toggle; intermediate/advanced get full expander.
_is_beginner_sidebar = (_sg_level_val == "beginner")

with st.sidebar.expander("⏰ Auto-Scan", expanded=False):
    _alert_cfg = _sidebar_alerts_cfg.copy()

    autoscan_on = st.toggle(
        "Enable Auto-Scan",
        value=_alert_cfg.get("autoscan_enabled", False),
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
                key=lambda v: abs(v - _alert_cfg.get("autoscan_interval_minutes", 60)))
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

    # Apply scheduler changes only when job doesn't exist or interval has changed
    # (avoid resetting next_run_time on every Streamlit rerun, which prevents the job from ever firing)
    if autoscan_on:
        _job_exists = bool(_get_scheduler().get_job(_AUTOSCAN_JOB_ID))
        _interval_changed = interval_min != _alert_cfg.get("autoscan_interval_minutes")
        if not _job_exists or _interval_changed:
            _setup_autoscan(interval_min)
        next_t = _get_next_autoscan_time()
        if next_t:
            # Use timezone-aware comparison (APScheduler may return tz-aware)
            try:
                if next_t.tzinfo is None:
                    next_t = next_t.replace(tzinfo=timezone.utc)
                delta = next_t - datetime.now(timezone.utc)
            except Exception:
                delta = timedelta(0)
            total_secs = delta.total_seconds()
            # BUG-L05: clamp negative deltas (overdue jobs) before computing mins/secs
            total_secs = max(0.0, total_secs)
            mins_left = int(total_secs // 60)
            secs_left = int(total_secs % 60)
            st.caption(f"Next scan in: {mins_left}m {secs_left}s")
    else:
        _stop_autoscan()
        st.caption("Auto-scan is off.")

    # Save autoscan config when changed
    if (autoscan_on  != _alert_cfg.get("autoscan_enabled")
            or interval_min != _alert_cfg.get("autoscan_interval_minutes")
            or quiet_on      != _alert_cfg.get("autoscan_quiet_hours_enabled")
            or quiet_start   != _alert_cfg.get("autoscan_quiet_start")
            or quiet_end     != _alert_cfg.get("autoscan_quiet_end")):
        _alert_cfg["autoscan_enabled"]            = autoscan_on
        _alert_cfg["autoscan_interval_minutes"]   = interval_min
        _alert_cfg["autoscan_quiet_hours_enabled"] = quiet_on
        _alert_cfg["autoscan_quiet_start"]        = quiet_start.strip()
        _alert_cfg["autoscan_quiet_end"]          = quiet_end.strip()
        _save_alerts_config_and_clear(_alert_cfg)

# ──────────────────────────────────────────────
# SIDEBAR: ALERT TOGGLES (compact — full config in Settings → Alerts)
# ──────────────────────────────────────────────
st.sidebar.markdown(
    '<span style="font-size:11px;color:rgba(168,180,200,0.5);'
    'font-weight:600;text-transform:uppercase;letter-spacing:0.8px">'
    'Alerts</span>',
    unsafe_allow_html=True,
)
_alert_cfg_sidebar = _sidebar_alerts_cfg.copy()
_alerts_changed = False

_tg_on = st.sidebar.toggle(
    "🔔 Telegram",
    value=_alert_cfg_sidebar.get("telegram_enabled", False),
    key="sb_tg_toggle",
    help="Enable Telegram alerts for high-confidence signals. Configure token/chat ID in Settings → Alerts.",
)
if _tg_on != _alert_cfg_sidebar.get("telegram_enabled", False):
    _alert_cfg_sidebar["telegram_enabled"] = _tg_on
    _alerts_changed = True

_em_on = st.sidebar.toggle(
    "📧 Email",
    value=_alert_cfg_sidebar.get("email_enabled", False),
    key="sb_em_toggle",
    help="Enable email alerts. Configure in Settings → Alerts.",
)
if _em_on != _alert_cfg_sidebar.get("email_enabled", False):
    _alert_cfg_sidebar["email_enabled"] = _em_on
    _alerts_changed = True

_dc_on = st.sidebar.toggle(
    "💬 Discord",
    value=_alert_cfg_sidebar.get("discord_enabled", False),
    key="sb_dc_toggle",
    help="Enable Discord webhook alerts. Configure in Settings → Alerts.",
)
if _dc_on != _alert_cfg_sidebar.get("discord_enabled", False):
    _alert_cfg_sidebar["discord_enabled"] = _dc_on
    _alerts_changed = True

if _alerts_changed:
    _save_alerts_config_and_clear(_alert_cfg_sidebar)

if st.sidebar.button("⚙️ Configure Alerts", key="sb_cfg_alerts_btn", width="stretch"):
    st.session_state["_nav_target"] = "Config Editor"
    st.session_state["_settings_tab"] = "Alerts"
    st.rerun()



# ──────────────────────────────────────────────
# SIDEBAR: API HEALTH CHECK (#17 security hardening)
# ──────────────────────────────────────────────
with st.sidebar.expander("🔌 API Health", expanded=False):
    _api_health = _cached_api_health()
    _health_rows = []
    for _svc, _status in _api_health.items():
        _dot = "🟢" if _status in ("ok", "configured") else "🟠" if _status.startswith("HTTP") else "🔴"
        _health_rows.append(f"{_dot} **{_svc.capitalize()}** — {_status}")
    st.markdown("\n\n".join(_health_rows) if _health_rows else "No results")
    if st.button("Recheck", key="api_health_recheck", width="stretch"):
        _cached_api_health.clear()
        st.rerun()

# ──────────────────────────────────────────────
# SIDEBAR: WALLET PORTFOLIO IMPORT (#110 / #111)
# ──────────────────────────────────────────────
with st.sidebar.expander("🔗 Wallet Import (Beta)", expanded=False):
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
        # Also offer full Zerion portfolio
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

# ──────────────────────────────────────────────
# SIDEBAR: PERSONAL API KEYS (#18)
# Stored in session state only — never written to disk.
# ──────────────────────────────────────────────
with st.sidebar.expander("🔑 API Keys (Session Only)", expanded=False):
    st.caption("Keys stored in session only — never saved to disk.")
    _user_cg = st.text_input("CoinGecko Pro Key", type="password", key="user_cg_key")
    _user_ant = st.text_input("Anthropic Key (override)", type="password", key="user_anthropic_key")
    if st.button("Apply", key="btn_apply_user_keys"):
        if _user_cg:
            st.session_state["runtime_coingecko_key"] = _user_cg
        if _user_ant:
            st.session_state["runtime_anthropic_key"] = _user_ant
        st.success("Applied for this session")

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
    # Early-return when not scanning — keeps fragment registered without rendering anything.
    if not st.session_state.get("scan_running", False) and not _SCAN_STATUS.get("running", False):
        with _scan_lock:
            if not _scan_state["running"]:
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

    # Simple text progress counter + PERF-A6: live partial results preview
    _n_done = _prog
    if _n_done > 0:
        st.markdown(
            f'<div style="font-size:12px;color:rgba(0,212,170,0.8);'
            f'font-weight:600;margin:4px 0 8px 0;">'
            f'⚡ {_n_done} of {_total} coins scanned</div>',
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


def page_dashboard():
    # ── Welcome banner (item 19 — beginner only, once per session) ────────────
    _ui.render_welcome_banner()

    st.markdown(
        '<h1 style="color:#e8ecf1;font-size:26px;font-weight:700;'
        'letter-spacing:-0.5px;margin-bottom:0">🎯 Crypto Signals — What To Do Today</h1>',
        unsafe_allow_html=True,
    )
    # PERF-28: read all WS prices once at the top of the render — was called 3+ times per render
    _live_prices = _ws.get_all_prices()
    # Animated live price ticker strip — top of dashboard
    try:
        _ticker_prices = []
        _all_ws = _live_prices
        for _pair in model.PAIRS:
            _tick = _all_ws.get(_pair)
            if _tick:
                _ticker_prices.append({
                    "symbol":     _pair.replace("/USDT", ""),
                    "price":      _tick.get("price", 0),
                    "change_pct": _tick.get("change_24h_pct", 0),
                })
        if _ticker_prices:
            st.markdown(_ui.price_ticker_strip_html(_ticker_prices), unsafe_allow_html=True)
    except Exception:
        pass

    # FNG chip + scan controls
    col_btn, col_fng, col_ts = st.columns([2, 2, 4])
    with col_btn:
        with _scan_lock:
            _scan_running_now = _scan_state["running"]
        # BUG-R28: use .get() for all session_state accesses — prevents KeyError if
        # init_state() is ever bypassed (e.g. session reset mid-run).
        scan_disabled = st.session_state.get("scan_running", False) or _scan_running_now
        _btn_label = "⏳ Analyzing... (this takes ~15-30s)" if scan_disabled else "🔍 Analyze All Coins Now"
        if st.button(_btn_label, disabled=scan_disabled, type="primary", width="stretch"):
            st.session_state["scan_results"] = []
            st.session_state["scan_error"] = None
            _start_scan()
    with col_fng:
        if st.session_state.get("scan_results"):
            r0 = st.session_state["scan_results"][0]
            fv, fc = r0.get("fng_value", 50), r0.get("fng_category", "Neutral")
            if fv <= 20:
                _fng_emoji = "😱"
            elif fv <= 40:
                _fng_emoji = "😟"
            elif fv <= 60:
                _fng_emoji = "😐"
            elif fv <= 80:
                _fng_emoji = "🤩"
            else:
                _fng_emoji = "🤑"
            _fng_color = "#f6465d" if fv < 40 else "#00c076" if fv > 60 else "#f0a500"  # APP-05: fear=red, greed=green
            st.markdown(
                f'<span style="color:rgba(255,255,255,0.4);font-size:11px;'
                f'text-transform:uppercase;letter-spacing:0.8px">Market Mood</span><br/>'
                f'<span style="font-size:20px">{_fng_emoji}</span> '
                f'<span style="color:{_fng_color};font-weight:700;font-size:16px">'
                f'{fv}</span> '
                f'<span style="color:rgba(255,255,255,0.55);font-size:13px">{fc}</span>',
                unsafe_allow_html=True,
            )
    with col_ts:
        if st.session_state.get("scan_timestamp"):
            st.caption(f"Last scan: {st.session_state['scan_timestamp']}")

    # ── Fear & Greed trend — Now / 7-day avg / 30-day avg (item 26) ──────────
    _ui.render_fear_greed_trend_sg(user_level=st.session_state.get("user_level", "beginner"))

    # Progress bar while scanning — check in-memory state first (PERF-30), fall back to SQLite
    with _scan_lock:
        _scan_running_now2 = _scan_state["running"]
    _mem_running = _SCAN_STATUS.get("running", False)
    if _mem_running or _scan_running_now2:
        status = {}  # PERF-30: skip SQLite read when in-memory already shows running
    else:
        status = _read_scan_status()
    is_scanning = st.session_state.get("scan_running", False) or _scan_running_now2 or _mem_running or status.get("running", False)

    # PERF-FRAGMENT: _scan_progress is defined at module level (above page_dashboard) so its
    # fragment session-state key ($$ID-...-None) stays registered across rerenders, preventing
    # the KeyError that occurred when the fragment was defined inside this conditional block.
    _scan_progress()  # always called — early-returns immediately when not scanning
    if is_scanning:
        return  # Don't render the results section while scan is in progress

    # On page load, always try to restore results from cache file if session is empty
    if not st.session_state.get("scan_results"):
        cached = _read_scan_results()
        status = _read_scan_status()
        if cached:
            st.session_state["scan_results"] = cached
            st.session_state["scan_timestamp"] = status.get("timestamp")

    # Show scan error if one occurred
    if st.session_state.get("scan_error"):
        logger.warning("[Scan] error shown to user: %s", st.session_state["scan_error"])
        st.error("Scan encountered an error — market data may be temporarily unavailable. Try running another scan or refreshing the page.")

    # Demo mode (#67) — inject synthetic results so no real API needed
    if st.session_state.get("demo_mode"):
        results = [
            {"pair": "BTC/USDT", "direction": "STRONG BUY", "confidence_avg_pct": 82, "high_conf": True,
             "entry": 65000, "stop_loss": 61000, "exit": 72000, "tp1": 72000, "position_size_pct": 10,
             "price_usd": 65000, "fng_value": 72, "fng_category": "Greed", "strategy_bias": "Trend",
             "timeframes": {"1h": {"rsi": 58, "confidence": 82, "direction": "STRONG BUY", "regime": "Trending: Bull"}},
             "trending": True, "consensus": 0.83},
            {"pair": "ETH/USDT", "direction": "BUY", "confidence_avg_pct": 71, "high_conf": True,
             "entry": 3200, "stop_loss": 2950, "exit": 3600, "tp1": 3600, "position_size_pct": 8,
             "price_usd": 3200, "fng_value": 72, "fng_category": "Greed", "strategy_bias": "Momentum",
             "timeframes": {"1h": {"rsi": 54, "confidence": 71, "direction": "BUY", "regime": "Trending: Bull"}},
             "trending": False, "consensus": 0.67},
            {"pair": "SOL/USDT", "direction": "SELL", "confidence_avg_pct": 63, "high_conf": False,
             "entry": 145, "stop_loss": 158, "exit": 128, "tp1": 128, "position_size_pct": 5,
             "price_usd": 145, "fng_value": 72, "fng_category": "Greed", "strategy_bias": "Reversion",
             "timeframes": {"1h": {"rsi": 68, "confidence": 63, "direction": "SELL", "regime": "Ranging"}},
             "trending": False, "consensus": 0.50},
        ]
    else:
        results = st.session_state.get("scan_results", [])
    if not results:
        if st.session_state.get("user_level", "beginner") == "beginner" and not st.session_state.get("scan_run"):
            st.markdown(_ui.beginner_welcome_html(), unsafe_allow_html=True)
        else:
            st.info("No scan results yet — click **Run Scan** in the sidebar to begin.")
        return  # A4: guard — always return on empty results, prevents results[0] IndexError

    # PERF-A8: Inject live WebSocket prices into scan results before rendering.
    # Scan results may be minutes old; WS prices are real-time → always show the
    # freshest price without re-running the scan.
    if _live_prices:
        for _r in results:
            _ws_tick = _live_prices.get(_r.get("pair", ""))
            if _ws_tick and _ws_tick.get("price"):
                _r["price_usd"] = _ws_tick["price"]

    if st.session_state.get("scan_timestamp"):
        st.success(f"Scan complete — {len(results)} pairs | {st.session_state['scan_timestamp']}")

    # ── Market stat bar (top strip with live market stats) ───────────────────
    _stat_bar_data = {}
    if results:
        _fv = results[0].get("fng_value", 50)
        _fc = results[0].get("fng_category", "Neutral")
        _stat_bar_data["Fear & Greed"] = f"{_fv} — {_fc}"
        _avg_c_raw = sum(r.get("confidence_avg_pct") or 0 for r in results) / len(results)
        _avg_c = round(_avg_c_raw if _avg_c_raw == _avg_c_raw else 0.0, 1)  # APP-21: NaN guard
        _stat_bar_data["Avg Confidence"] = f"{_avg_c}%"
        _buy_n  = sum(1 for r in results if "BUY"  in r.get("direction", ""))
        _sell_n = sum(1 for r in results if "SELL" in r.get("direction", ""))
        _stat_bar_data["Signals"] = f"▲{_buy_n} / ▼{_sell_n}"
        _hc_n = sum(1 for r in results if r.get("high_conf"))
        _stat_bar_data["High-Conf"] = f"⚡ {_hc_n}"
        for _top_pair in ["BTC/USDT", "ETH/USDT"]:
            _tick = _ws.get_price(_top_pair)
            if _tick:
                _sym = _top_pair.replace("/USDT", "")
                _stat_bar_data[_sym] = f"${_tick['price']:,.2f}"
        _ts = st.session_state.get("scan_timestamp", "—")
        _stat_bar_data["Last Scan"] = _ts.split(" ")[1] if _ts and " " in str(_ts) else str(_ts)
    if _stat_bar_data:
        _ui.market_stat_bar(_stat_bar_data)

    # Drawdown circuit breaker banner (check once from first result)
    cb = results[0].get('circuit_breaker', {}) if results else {}
    if cb.get('triggered'):
        st.error(
            f"🛑 **Safety Stop Active** — The portfolio has dropped "
            f"{cb.get('drawdown_pct', 0):.1f}% from its peak "  # APP-26: .get() avoids KeyError on schema mismatch
            f"(threshold: {cb.get('threshold_pct', 0):.0f}%). To protect your account, all new trade signals are paused. "
            f"Consider reviewing your positions before resuming. Peak equity was ${cb.get('peak_equity', 0):,.0f}."
        )

    # F6/F7: Concept drift warning banner — shown when recent win rate decays vs historical baseline
    _drift = model.get_drift_status() or {}  # APP-25: guard None return when no feedback data
    if _drift.get('drift_detected'):
        st.warning(
            f"⚠️ **Model Accuracy Alert** — The model's recent win rate "
            f"({_drift.get('win_rate_30d', 0):.0%} last 30 days) "  # APP-27: .get() avoids KeyError
            f"has dropped below its historical baseline ({_drift.get('win_rate_90d', 0):.0%} over 90 days). "
            f"Signals may be less reliable than usual. The model is auto-retuning. Use extra caution."
        )

    # ── #26 Pi Cycle Top Kill-Switch banner ──────────────────────────────────
    # Check if any result carries the active flag (all results share the same pi_cycle state)
    _pi_active_any = any(r.get("pi_cycle_active", False) for r in results)
    if _pi_active_any:
        # Guard: gap_pct may be None if fallback path was taken in fetch_pi_cycle_top()
        _pi_gap = results[0].get("pi_cycle_gap_pct") if results else None
        _pi_gap = float(_pi_gap) if _pi_gap is not None else 0.0
        st.error(
            "🔴 **Pi Cycle Top Active** — The 111-day moving average has crossed above "
            "the 350-day MA × 2. This indicator has signalled every Bitcoin cycle top "
            f"within 3 days (2013, 2017, 2021). Gap: {_pi_gap:+.2f}%. "
            "All BUY signals are capped at 30% confidence. Consider reducing exposure or taking profits."
        )
    elif any(r.get("pi_cycle_signal") == "CAUTION" for r in results):
        _pi_gap = results[0].get("pi_cycle_gap_pct") if results else None
        _pi_gap = float(_pi_gap) if _pi_gap is not None else 0.0
        st.warning(
            f"⚠️ **Pi Cycle Top Approaching** — Gap between 111DMA and 350DMA×2 is only "
            f"{abs(_pi_gap):.1f}%. Historically this precedes cycle tops — use caution with new BUY entries."
        )

    # High-confidence alert banner (advanced/intermediate — beginners see hero cards instead)
    hc = [r for r in results if r.get("high_conf")]
    _user_lv = st.session_state.get("user_level", "beginner")
    if hc and _user_lv != "beginner":
        pairs_str = ", ".join(r["pair"] for r in hc)
        st.success(f"⚡ Top Picks this scan — the model's highest-confidence opportunities: **{pairs_str}**")
    # Pre-compute shared variables used across multiple tabs
    sorted_results = sorted(results, key=lambda r: (r.get("high_conf", False), r.get("confidence_avg_pct", 0)), reverse=True)
    _exec_status = _exec.get_status()
    _exec_cfg    = _exec.get_exec_config()

    # ─── 5-TAB DASHBOARD STRUCTURE ───────────────────────────────────────────
    _dash_tab1, _dash_tab2, _dash_tab3, _dash_tab4, _dash_tab5 = st.tabs([
        "🎯 Today",
        "📊 All Coins",
        "🔍 Coin Detail",
        "🌐 Market Intel",
        "🔬 Analysis",
    ])

    with _dash_tab1:
        # ── Item 9: 3-step micro-tutorial (beginner first visit) ─────────────────
        _ui.render_micro_tutorial()

        # ── Item 17: Data freshness dot ───────────────────────────────────────────
        _scan_ts_str = st.session_state.get("scan_timestamp")
        _scan_ts_unix: float | None = None
        if _scan_ts_str:
            try:
                import datetime as _dt
                _scan_ts_unix = _dt.datetime.fromisoformat(str(_scan_ts_str)).timestamp()
            except Exception:
                pass
        st.markdown(
            _ui.freshness_dot_html(_scan_ts_unix, max_age_sec=900, label="Scan data"),
            unsafe_allow_html=True,
        )

        # ── Items 1 & 2: Today's Top Picks Hero Panel (beginner first, always) ───
        st.markdown(
            _ui.top_picks_hero_html(results, ws_prices=_live_prices),
            unsafe_allow_html=True,
        )

        # ── Item 11: How This Model Works trust card (collapsible) ───────────────
        if _user_lv in ("beginner", "intermediate"):
            with st.expander("🔬 How does this model work?", expanded=False):
                _bt_df  = _cached_backtest_df()
                _wr_raw = 0.0
                if not _bt_df.empty and "result" in _bt_df.columns:
                    _wins = (_bt_df["result"] == "WIN").sum()
                    _wr_raw = _wins / max(len(_bt_df), 1) * 100
                st.markdown(
                    _ui.how_it_works_html(win_rate=_wr_raw, n_months=3, n_indicators=24),
                    unsafe_allow_html=True,
                )

        st.markdown("---")

        # ── F&G visual gauge + summary metrics ────────────────────────────────────
        _fng_r0     = results[0] if results else {}   # A4: guard (belt-and-suspenders — return above should fire first)
        _fng_val    = _fng_r0.get("fng_value", 50)
        _fng_cat    = _fng_r0.get("fng_category", "Neutral")
        _ac_raw  = sum(r.get("confidence_avg_pct") or 0 for r in results) / max(len(results), 1)
        avg_conf = round(_ac_raw if _ac_raw == _ac_raw else 0.0, 1)  # APP-21: NaN guard
        buy_count   = sum(1 for r in results if "BUY"  in r.get("direction", ""))
        sell_count  = sum(1 for r in results if "SELL" in r.get("direction", ""))

        _fng_col, _metrics_col = st.columns([2, 3])
        with _fng_col:
            st.markdown(_ui.fng_gauge_html(_fng_val, _fng_cat), unsafe_allow_html=True)
        with _metrics_col:
            mc = st.columns(4)
            mc[0].metric("Coins Scanned", len(results), help=_ui.HELP_PAIRS_SCANNED)
            mc[1].metric("Top Picks ⚡", len(hc),       help=_ui.HELP_HIGH_CONF)
            mc[2].metric("Avg Strength", f"{avg_conf}%", help=_ui.HELP_AVG_CONF)
            _signal_label = f"▲{buy_count} Buy · ▼{sell_count} Sell"
            mc[3].metric("Signals", _signal_label,
                         help=_ui.HELP_BUY_SIGNALS + " " + _ui.HELP_SELL_SIGNALS)

        # ── Action CTA — best opportunity card (beginner-focused) ─────────────────
        if hc:
            _best = hc[0]
            _ui.scan_action_cta(
                pair      = _best["pair"],
                direction = _best.get("direction", ""),
                conf      = _best.get("confidence_avg_pct", 0),
                entry     = _best.get("entry"),
                stop      = _best.get("stop_loss"),
                exit_     = _best.get("exit"),
            )

        # ── Market regime banner + Hurst / Squeeze context ────────────────────────
        try:
            _r0_tf_vals = list(results[0].get("timeframes", {}).values()) if results else []
            _r0_tf = _r0_tf_vals[0] if _r0_tf_vals else {}
            _regime_str = _r0_tf.get("regime", "Neutral: Unknown")
            _regime_key = _regime_str.split(":")[0].strip().split(" ")[-1] if ":" in _regime_str else "Neutral"
            # Map HMM regime strings to 4-state keys
            _regime_map = {"Trending": "BULL", "Ranging": "RANGING", "Neutral": "RANGING", "Volatile": "CRISIS"}
            _regime_4 = _regime_map.get(_regime_key, "RANGING")
            _hurst_val = _r0_tf.get("hurst", None)
            _squeeze_sig = _r0_tf.get("squeeze_signal", "NO_SQUEEZE")
            st.markdown(
                _ui.regime_banner_html(
                    regime=_regime_4,
                    hurst=float(_hurst_val) if _hurst_val is not None else None,
                    squeeze_active=("SQUEEZE" in str(_squeeze_sig)),
                ),
                unsafe_allow_html=True,
            )
        except Exception as _e:
            logging.debug("[Panel] regime_banner failed: %s", _e)

        # ── Top Movers bento card (3 gainers / 3 losers from CoinGecko) ──────────
        # PERF-20: route through cached wrapper (2-min TTL) instead of direct API call
        try:
            _movers = _cached_top_movers(top_n=3)
            _gainers = _movers.get("gainers", [])
            _losers  = _movers.get("losers", [])
            if _gainers or _losers:
                st.markdown(_ui.top_movers_card_html(_gainers, _losers), unsafe_allow_html=True)
        except Exception as _e:
            logging.debug("[Panel] top_movers failed: %s", _e)

        st.markdown("---")


    with _dash_tab4:
        # ── Blood in the Streets · DCA Multiplier · Macro Overlay (Group 3) ──────
        # F6 — data freshness badges for macro panels
        _fb_cols = st.columns(3)
        with _fb_cols[0]:
            st.markdown(_freshness_badge("fred_macro",      3600, "FRED Macro"),     unsafe_allow_html=True)
        with _fb_cols[1]:
            st.markdown(_freshness_badge("yfinance_macro",  3600, "YF Macro"),       unsafe_allow_html=True)
        with _fb_cols[2]:
            st.markdown(_freshness_badge("coinalyze_funding", 300, "Funding Rates"), unsafe_allow_html=True)

        try:
            _fg_val3   = results[0].get("fng_value", 50) if results else 50
            _btc_res   = next((r for r in results if r.get("pair") == "BTC/USDT"), {})
            _btc_rsi3  = (_btc_res.get("timeframes", {}).get("1d", {}) or {}).get("rsi", None)
            _bits3     = _cached_blood_in_streets(_fg_val3, _btc_rsi3)
            _dca_m3    = _bits3["dca_multiplier"]
            _macro3    = _cached_macro_signal_adjustment()
            # Only render if signal is notable (not all-normal)
            if _bits3["signal"] != "NORMAL" or _macro3["adjustment"] != 0.0:
                _bc3    = {"BLOOD_IN_STREETS": "#ef4444", "EXTREME_FEAR": "#f59e0b", "NORMAL": "#6b7280"}.get(_bits3["signal"], "#6b7280")
                _bg3    = {"BLOOD_IN_STREETS": "#1f0000",  "EXTREME_FEAR": "#1c1200", "NORMAL": "#111827"}.get(_bits3["signal"], "#111827")
                _dc3    = {0.0: "#ef4444", 0.5: "#f97316", 1.0: "#9ca3af", 2.0: "#10b981", 3.0: "#00d4aa"}.get(_dca_m3, "#9ca3af")
                _dl3    = {0.0: "HOLD", 0.5: "0.5× reduce", 1.0: "1× base", 2.0: "2× accumulate", 3.0: "3× max accumulate"}.get(_dca_m3, f"{_dca_m3}×")
                _rc3    = {"MACRO_HEADWIND": "#ef4444", "MILD_HEADWIND": "#f97316", "MACRO_NEUTRAL": "#6b7280", "MILD_TAILWIND": "#10b981", "MACRO_TAILWIND": "#00d4aa"}.get(_macro3["regime"], "#6b7280")
                _sk3    = _cached_deribit_options_skew("BTC")
                _skc3   = {"BEARISH": "#ef4444", "MILD_BEARISH": "#f97316", "NEUTRAL": "#6b7280", "MILD_BULLISH": "#10b981", "BULLISH": "#00d4aa"}.get(_sk3.get("signal", "N/A"), "#6b7280")
                _b1, _b2, _b3, _b4 = st.columns(4)
                with _b1:
                    st.markdown(f"""
    <div style="background:{_bg3};border:1px solid {_bc3};border-top:3px solid {_bc3};border-radius:10px;padding:16px">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">Blood in Streets</div>
      <div style="font-size:18px;font-weight:700;color:{_bc3}">{_bits3["signal"].replace("_", " ")}</div>
      <div style="font-size:12px;color:#9ca3af;margin-top:4px">{_bits3["strength"]} · {_bits3["criteria_met"]}/3 criteria</div>
      <div style="font-size:11px;color:#6b7280;margin-top:8px">{_bits3["description"]}</div>
      <div style="margin-top:10px;font-size:11px;color:#6b7280">
        {"✅" if _bits3["criteria"]["extreme_fear"] else "❌"} F&amp;G≤25 &nbsp;
        {"✅" if _bits3["criteria"]["rsi_oversold"] else "❌"} RSI≤30 &nbsp;
        {"✅" if _bits3["criteria"]["exchange_outflow"] else "❌"} Outflow
      </div>
    </div>
    """, unsafe_allow_html=True)
                with _b2:
                    st.markdown(f"""
    <div style="background:#111827;border:1px solid #1f2937;border-top:3px solid {_dc3};border-radius:10px;padding:16px">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">DCA Multiplier</div>
      <div style="font-size:36px;font-weight:700;color:{_dc3}">{_dca_m3}×</div>
      <div style="font-size:13px;color:#9ca3af;margin-top:4px">{_dl3}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:8px">F&amp;G: {_fg_val3}/100 · BTC RSI-1D: {f"{_btc_rsi3:.1f}" if _btc_rsi3 else "—"}</div>
    </div>
    """, unsafe_allow_html=True)
                with _b3:
                    st.markdown(f"""
    <div style="background:#111827;border:1px solid #1f2937;border-top:3px solid {_rc3};border-radius:10px;padding:16px">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">Macro Overlay</div>
      <div style="font-size:18px;font-weight:700;color:{_rc3}">{_macro3["regime"].replace("_", " ")}</div>
      <div style="font-size:12px;color:#9ca3af;margin-top:4px">Confidence adj: {_macro3["adjustment"]:+.0f} pts</div>
      <div style="font-size:11px;color:#6b7280;margin-top:8px">DXY {_macro3["dxy"]:.1f} ({_macro3["dxy_signal"]}) · 10Y {_macro3["ten_yr"]:.2f}% ({_macro3["yr_signal"]})</div>
    </div>
    """, unsafe_allow_html=True)
                with _b4:
                    st.markdown(f"""
    <div style="background:#111827;border:1px solid #1f2937;border-top:3px solid {_skc3};border-radius:10px;padding:16px">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">Options Skew (Deribit)</div>
      <div style="font-size:18px;font-weight:700;color:{_skc3}">{_sk3.get("signal", "N/A")}</div>
      <div style="font-size:12px;color:#9ca3af;margin-top:4px">Skew: {f"{_sk3['skew']:+.1f}%" if "skew" in _sk3 else "—"}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:8px">
        Put IV {f"{_sk3['put_iv']:.1f}%" if "put_iv" in _sk3 else "—"} · Call IV {f"{_sk3['call_iv']:.1f}%" if "call_iv" in _sk3 else "—"}
      </div>
      {f'<div style="font-size:10px;color:#4b5563;margin-top:4px">Expiry: {_sk3["expiry"]}</div>' if "expiry" in _sk3 else ""}
    </div>
    """, unsafe_allow_html=True)
        except Exception:
            pass

        # ── S25: Macro Intelligence — always-visible scorecard ───────────────────
        try:
            _me = _cached_macro_enrichment()
            _ui.render_macro_scorecard_panel(_me, _sg_level_val)
        except Exception as _me_err:
            logger.warning("[App] macro panel failed: %s", _me_err)
            st.caption("Macro panel temporarily unavailable — try refreshing.")

        # ── 4-Layer Composite Market Environment Signal ─────────────────────────
        try:
            import agent as _sg_agent
            _csig_sg = _sg_agent.get_composite_signal()
            if _csig_sg and _csig_sg.get("score", 0) != 0.0:
                _sg_score  = _csig_sg.get("score", 0.0)
                _sg_signal = _csig_sg.get("signal", "NEUTRAL").replace("_", " ")
                _sg_layers = _csig_sg.get("layers", {})
                _sg_risk   = _csig_sg.get("risk_off", False)

                if _sg_score >= 0.3:   _sg_c, _sg_bg = "#22c55e", "rgba(34,197,94,0.07)"
                elif _sg_score >= 0.1: _sg_c, _sg_bg = "#00d4aa", "rgba(0,212,170,0.07)"
                elif _sg_score >= -0.1: _sg_c, _sg_bg = "#f59e0b", "rgba(245,158,11,0.07)"
                elif _sg_score >= -0.3: _sg_c, _sg_bg = "#f97316", "rgba(249,115,22,0.07)"
                else:                  _sg_c, _sg_bg = "#ef4444", "rgba(239,68,68,0.07)"

                def _sgf(v): return f"+{v:.2f}" if v >= 0 else f"{v:.2f}"
                _sg_shape  = "▲" if _sg_score >= 0.10 else ("▼" if _sg_score <= -0.10 else "■")
                _sg_wts    = _csig_sg.get("weights_applied", {"technical": 0.20, "macro": 0.20, "sentiment": 0.25, "onchain": 0.35})
                _ta_s   = _sg_layers.get("technical", {}).get("score", 0)
                _mac_s  = _sg_layers.get("macro",     {}).get("score", 0)
                _sent_s = _sg_layers.get("sentiment", {}).get("score", 0)
                _oc_s   = _sg_layers.get("onchain",   {}).get("score", 0)
                _sg_xai = [("Technical", _ta_s,   _sg_wts.get("technical", 0.20)),
                           ("Macro",     _mac_s,  _sg_wts.get("macro",     0.20)),
                           ("Sentiment", _sent_s, _sg_wts.get("sentiment", 0.25)),
                           ("On-Chain",  _oc_s,   _sg_wts.get("onchain",   0.35))]
                _sg_dir   = 1 if _sg_score > 0 else (-1 if _sg_score < 0 else 0)
                _sg_agree = sum(1 for _, s, _ in _sg_xai if (s > 0.05) == (_sg_dir > 0) and _sg_dir != 0)
                _sg_conf  = {4: "HIGH", 3: "HIGH", 2: "MEDIUM", 1: "LOW", 0: "LOW"}.get(_sg_agree, "MEDIUM")
                _sg_conf_c = {"HIGH": "#22c55e", "MEDIUM": "#f59e0b", "LOW": "#ef4444"}[_sg_conf]

                if _sg_level_val == "beginner":
                    _sg_summary = _csig_sg.get("beginner_summary", "")
                    st.html(
                        f"<div style='background:{_sg_bg};border:1px solid {_sg_c}33;"
                        f"border-left:4px solid {_sg_c};border-radius:8px;padding:10px 16px;margin:8px 0;'>"
                        f"<span style='color:{_sg_c};font-weight:700;'>{_sg_shape} Market Environment</span>"
                        f"<span style='color:#94a3b8;font-size:0.85rem;margin-left:12px;'>{_sg_summary}</span>"
                        f"<span style='margin-left:16px;background:{_sg_conf_c}22;color:{_sg_conf_c};"
                        f"font-size:0.72rem;font-weight:700;padding:2px 8px;border-radius:10px;"
                        f"border:1px solid {_sg_conf_c}44;'>{_sg_conf} CONFIDENCE</span>"
                        f"</div>"
                    )
                else:
                    _gate_t = " · ⚠️ Risk Gate Active" if _sg_risk else ""
                    st.html(
                        f"<div style='background:{_sg_bg};border:1px solid {_sg_c}33;"
                        f"border-left:4px solid {_sg_c};border-radius:8px;padding:8px 16px;margin:8px 0;"
                        f"display:flex;align-items:center;gap:20px;flex-wrap:wrap;'>"
                        f"<div><span style='color:#64748b;font-size:0.72rem;text-transform:uppercase;'>Composite Signal</span>"
                        f"<div style='color:{_sg_c};font-weight:800;font-size:0.95rem;'>{_sg_shape} {_sg_signal}{_gate_t}</div>"
                        f"<div style='color:#64748b;font-size:0.75rem;'>Score {_sgf(_sg_score)} &nbsp;·&nbsp; "
                        f"<span style='color:{_sg_conf_c};font-weight:600;'>{_sg_conf} CONFIDENCE</span></div></div>"
                        f"<div style='color:#475569;font-size:0.78rem;border-left:1px solid #1e293b;padding-left:16px;'>"
                        f"<div>TA <span style='color:{'#22c55e' if _ta_s>=0 else '#ef4444'};font-weight:600;'>{_sgf(_ta_s)}</span>"
                        f" · Macro <span style='color:{'#22c55e' if _mac_s>=0 else '#ef4444'};font-weight:600;'>{_sgf(_mac_s)}</span>"
                        f" · Sentiment <span style='color:{'#22c55e' if _sent_s>=0 else '#ef4444'};font-weight:600;'>{_sgf(_sent_s)}</span>"
                        f" · On-Chain <span style='color:{'#22c55e' if _oc_s>=0 else '#ef4444'};font-weight:600;'>{_sgf(_oc_s)}</span></div>"
                        f"</div></div>"
                    )

                # XAI breakdown expander
                with st.expander("🔍 Why this signal? — Signal driver breakdown", expanded=False):
                    _xai_rows = ""
                    for _xn, _xs, _xw in _sg_xai:
                        _xwc = _xs * _xw
                        _xbar_w = min(abs(_xwc) * 250, 100)
                        _xbar_c = "#22c55e" if _xwc >= 0 else "#ef4444"
                        _xai_rows += (
                            f"<div style='display:flex;align-items:center;gap:10px;margin:5px 0;'>"
                            f"<div style='width:90px;font-size:0.78rem;color:#cbd5e1;'>{_xn}</div>"
                            f"<div style='width:40px;font-size:0.7rem;color:#64748b;text-align:right;'>{_xw*100:.0f}%</div>"
                            f"<div style='flex:1;background:#1e293b;border-radius:3px;height:14px;overflow:hidden;'>"
                            f"<div style='width:{_xbar_w:.0f}%;background:{_xbar_c};height:100%;border-radius:3px;'></div></div>"
                            f"<div style='width:55px;font-size:0.78rem;font-weight:600;color:{_xbar_c};text-align:right;'>{_xwc*100:+.1f}%</div>"
                            f"</div>"
                        )
                    _sg_note = ("Each bar shows how much that factor pushed the signal bullish (+) or bearish (−)."
                                if _sg_level_val == "beginner"
                                else f"Weighted contributions · regime: {_csig_sg.get('regime', 'N/A')} · weights are regime-adjusted.")
                    st.html(f"<div style='padding:4px 0 8px;'>"
                            f"<div style='font-size:0.72rem;color:#64748b;margin-bottom:8px;'>{_sg_note}</div>"
                            f"{_xai_rows}</div>")
        except Exception as _sg_cs_err:
            logger.debug("[App] composite signal banner skipped: %s", _sg_cs_err)

        st.markdown("---")

        # ── Wyckoff Phase Summary (item 23) ─────────────────────────────────────────
        _wyck_results = [(r.get("pair",""), r.get("wyckoff_phase","Unknown"), r.get("wyckoff_conf",0),
                          r.get("wyckoff_desc",""), r.get("wyckoff_plain",""),
                          r.get("wyckoff_spring",False), r.get("wyckoff_upthrust",False))
                         for r in results if r.get("wyckoff_phase","Unknown") != "Unknown"]
        if _wyck_results:
            _user_level_wyck = st.session_state.get("user_level", "beginner")
            _ui.section_header("Wyckoff Phase Analysis",
                               "Richard Wyckoff's 4-phase market cycle: Accumulation → Markup → Distribution → Markdown. "
                               "Identifies where institutional money is flowing.",
                               icon="🔄")
            _WYCK_COLOR = {
                "Accumulation": "#00d4aa", "Markup": "#22c55e",
                "Distribution": "#f59e0b", "Markdown": "#ef4444",
            }
            _WYCK_BG = {
                "Accumulation": "rgba(0,212,170,0.08)", "Markup": "rgba(34,197,94,0.08)",
                "Distribution": "rgba(245,158,11,0.08)", "Markdown": "rgba(239,68,68,0.08)",
            }
            _WYCK_ICON = {
                "Accumulation": "🏦", "Markup": "📈",
                "Distribution": "🏧", "Markdown": "📉",
            }
            if _user_level_wyck == "beginner":
                # Show the top 3 cards with plain English
                _wc = st.columns(min(3, len(_wyck_results)))
                for _ci, (_wp, _wph, _wco, _wd, _wpl, _wsp, _wup) in enumerate(_wyck_results[:3]):
                    with _wc[_ci]:
                        _wcc = _WYCK_COLOR.get(_wph, "#64748b")
                        _wcb = _WYCK_BG.get(_wph, "rgba(100,116,139,0.08)")
                        _wico = _WYCK_ICON.get(_wph, "⬜")
                        _extra = " 🔔 SPRING" if _wsp else (" 🔔 UPTHRUST" if _wup else "")
                        st.markdown(
                            f"<div style='background:{_wcb};border:1px solid {_wcc}33;"
                            f"border-top:3px solid {_wcc};border-radius:10px;padding:14px'>"
                            f"<div style='font-size:10px;color:#6b7280;text-transform:uppercase;"
                            f"letter-spacing:0.8px'>{_wp.replace('/USDT','')}</div>"
                            f"<div style='font-size:16px;font-weight:700;color:{_wcc};margin-top:2px'>"
                            f"{_wico} {_wph}{_extra}</div>"
                            f"<div style='font-size:11px;color:#9ca3af;margin-top:6px'>{_wpl}</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
            else:
                # Table view for intermediate/advanced
                _phase_counts: dict = {}
                for _, _wph, _, _, _, _wsp, _wup in _wyck_results:
                    _phase_counts[_wph] = _phase_counts.get(_wph, 0) + 1
                _pc = st.columns(4)
                for _pi, _ph in enumerate(["Accumulation", "Markup", "Distribution", "Markdown"]):
                    with _pc[_pi]:
                        _cnt = _phase_counts.get(_ph, 0)
                        _wcc = _WYCK_COLOR.get(_ph, "#64748b")
                        _wico = _WYCK_ICON.get(_ph, "⬜")
                        st.markdown(
                            f"<div style='text-align:center;background:{_WYCK_BG.get(_ph,'rgba(100,116,139,0.08)')};"
                            f"border:1px solid {_wcc}33;border-radius:8px;padding:12px'>"
                            f"<div style='font-size:12px;color:#6b7280'>{_wico} {_ph}</div>"
                            f"<div style='font-size:28px;font-weight:700;color:{_wcc}'>{_cnt}</div>"
                            f"<div style='font-size:10px;color:#4b5563'>pairs</div></div>",
                            unsafe_allow_html=True,
                        )
                if _user_level_wyck == "advanced":
                    # Detailed table
                    _spring_pairs   = [_wp for _wp, _, _, _, _, _wsp, _ in _wyck_results if _wsp]
                    _upthrust_pairs = [_wp for _wp, _, _, _, _, _, _wup in _wyck_results if _wup]
                    if _spring_pairs:
                        st.markdown(
                            f"<div style='margin-top:8px;font-size:12px;color:#00d4aa'>"
                            f"🔔 Springs: {', '.join(p.replace('/USDT','') for p in _spring_pairs)}</div>",
                            unsafe_allow_html=True,
                        )
                    if _upthrust_pairs:
                        st.markdown(
                            f"<div style='font-size:12px;color:#f59e0b'>"
                            f"🔔 Upthrusts: {', '.join(p.replace('/USDT','') for p in _upthrust_pairs)}</div>",
                            unsafe_allow_html=True,
                        )

        # ── S24: Liquidation Pressure Monitor ────────────────────────────────────
        with st.expander("💥 Liquidation Pressure Monitor — OI + Funding Rate Squeeze Risk", expanded=False):
            st.caption(
                "Estimates squeeze risk per pair by combining open interest (OKX, free) and "
                "funding rates (Binance). High OI + extreme funding = more capital at risk of "
                "cascade liquidation. Data is fetched on demand."
            )
            _liq_pairs = model.PAIRS[:12]
            _liq_load  = st.button("🔄 Load Liquidation Data", key="btn_liq_load")
            if _liq_load:
                with st.spinner("Fetching OI + funding from OKX & Binance…", show_time=True):
                    _liq_data = data_feeds.get_liquidation_pressure(_liq_pairs)
                st.session_state["liq_data"] = _liq_data

            _liq_data = st.session_state.get("liq_data")
            if _liq_data:
                _liq_rows = []
                for d in _liq_data:
                    _sq = d["squeeze_signal"]
                    _sq_icon = {"HIGH_RISK": "🔴", "ELEVATED": "🟡", "NORMAL": "🟢"}.get(_sq, "⚪")
                    _bias_icon = {"LONGS_HEAVY": "▲ Longs", "SHORTS_HEAVY": "▼ Shorts", "BALANCED": "■ Balanced"}.get(d["funding_bias"], "—")
                    _liq_rows.append({
                        "Pair":            d["pair"].replace("/USDT", ""),
                        "OI (USD)":        f"${d['oi_usd']/1e6:.0f}M" if d["oi_usd"] > 0 else "—",
                        "OI Level":        d["oi_signal"],
                        "Funding %":       f"{d['funding_rate_pct']:+.4f}%",
                        "Bias":            _bias_icon,
                        "Squeeze Score":   f"{d['squeeze_score']:.4f}",
                        "Squeeze Risk":    f"{_sq_icon} {_sq}",
                    })
                _liq_df = pd.DataFrame(_liq_rows)

                def _color_sq(val: str) -> str:
                    if "HIGH_RISK" in val: return "color:#ef4444;font-weight:bold"
                    if "ELEVATED"  in val: return "color:#f59e0b"
                    return "color:#22c55e"

                st.dataframe(
                    _liq_df.style.map(_color_sq, subset=["Squeeze Risk"]),
                    width='stretch', hide_index=True,
                )

                # Bar chart of squeeze scores
                _top = [d for d in _liq_data if d["squeeze_score"] > 0][:10]
                if _top:
                    _bar_pairs  = [d["pair"].replace("/USDT","") for d in _top]
                    _bar_scores = [d["squeeze_score"] for d in _top]
                    _bar_colors = ["#ef4444" if d["squeeze_signal"] == "HIGH_RISK" else
                                   "#f59e0b" if d["squeeze_signal"] == "ELEVATED" else
                                   "#22c55e" for d in _top]
                    _liq_fig = go.Figure(go.Bar(
                        x=_bar_pairs, y=_bar_scores,
                        marker_color=_bar_colors,
                        hovertemplate="%{x}: %{y:.4f}<extra></extra>",
                    ))
                    _liq_fig.update_layout(
                        height=220, margin=dict(l=0, r=0, t=10, b=0),
                        xaxis_title="", yaxis_title="Squeeze Score",
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(_liq_fig, width='stretch')
                    st.caption(
                        "Score = √(OI/1B) × |funding %| × 100. "
                        "🔴 High Risk: large OI + extreme funding → cascade risk if price moves against dominant side."
                    )

                if st.session_state.get("user_level", "beginner") == "beginner":
                    st.caption(
                        "**What this means:** When lots of traders borrow money to bet in one direction "
                        "(e.g., all betting price goes up), a sudden price drop can force them all to sell at once, "
                        "causing a bigger crash — called a 'liquidation cascade.' This panel shows which coins are "
                        "most at risk of that happening right now."
                    )
            else:
                st.info("Press **Load Liquidation Data** to analyse squeeze risk across pairs.")

        st.markdown("---")
        # ── Autonomous Agent Status Panel ─────────────────────────────────────────
        _agent_cfg = _cached_alerts_config()
        if _agent_cfg.get("agent_enabled", False):
            # Auto-start supervisor if enabled in config and not already running
            try:
                if _agent is not None and not _agent.supervisor.is_running():
                    _agent.supervisor.start()
            except Exception as _e:
                logging.warning("[Agent] supervisor start failed: %s", _e)
            st.markdown("---")
            _ui.section_header("Autonomous Agent", "24/7 AI trading agent status", icon="🤖")
            try:
                _ag_st = _agent.supervisor.status() if _agent is not None else {}
            except Exception:
                _ag_st = {}
            # ── agent status metrics ──────────────────────────────────────────────
            import crypto_model_core as _cmc_ag
            _ag_n_pairs   = len(_cmc_ag.PAIRS)
            _ag_cur_pair  = _ag_st.get("current_pair", "") or ""   # pair in-flight right now
            _ag_last_pair = _ag_st.get("last_pair", "")  or ""     # last completed pair

            _ag_c1, _ag_c2, _ag_c3, _ag_c4 = st.columns(4)
            _ag_c1.metric(
                "Status",
                "🟢 RUNNING" if _ag_st.get("running") else "🔴 STOPPED",
                delta="LangGraph" if _ag_st.get("langgraph") else "Fallback pipeline",
                delta_color="normal",
            )
            _ag_c2.metric(
                "Pairs in Scope",
                _ag_n_pairs,
                delta="all pairs every cycle",
                delta_color="normal",
                help=f"Agent scans all {_ag_n_pairs} pairs in model.PAIRS every cycle — not just BTC. "
                     f"Pairs: {', '.join(_cmc_ag.PAIRS)}",
            )
            _ag_c3.metric(
                "Now Analyzing",
                _ag_cur_pair.replace("/USDT", "") if _ag_cur_pair else "—",
                delta="in-flight" if _ag_cur_pair else "between cycles",
                delta_color="normal",
                help="The pair the agent is currently running signal analysis on. Updates live.",
            )
            _ag_c4.metric(
                "Total Pair Scans",
                _ag_st.get("cycles_total", 0),
                delta=f"restarts: {_ag_st.get('restart_count', 0)}",
                delta_color="normal",
                help="Total number of individual pair evaluations since the agent started.",
            )
            if (_ag_st.get("last_run_ts") or 0) > 0:
                _last_ago = int(time.time() - _ag_st["last_run_ts"])
                _last_decision = _ag_st.get("last_decision") or "—"
                st.caption(
                    f"Last completed: **{_ag_last_pair}** → {_last_decision} | {_last_ago}s ago "
                    f"| Dry-run: {'ON' if _agent_cfg.get('agent_dry_run', True) else 'OFF'} "
                    f"| Scanning all {_ag_n_pairs} pairs each cycle"
                )
            with st.expander(f"Recent Agent Decisions (all {_ag_n_pairs} pairs)", expanded=False):
                try:
                    _ag_log_df = _cached_agent_log_df(limit=50)
                    if _ag_log_df.empty:
                        st.caption("No decisions recorded yet.")
                    else:
                        _show_cols = [c for c in ["logged_at", "pair", "direction",
                                                  "confidence", "claude_decision",
                                                  "action_taken", "claude_rationale"]
                                      if c in _ag_log_df.columns]
                        # Sort by logged_at desc so newest pair decisions are at top
                        _disp_df = _ag_log_df[_show_cols]
                        if "logged_at" in _disp_df.columns:
                            _disp_df = _disp_df.sort_values("logged_at", ascending=False)
                        st.dataframe(_disp_df, width='stretch', hide_index=True)
                        # Show unique pairs covered this session
                        if "pair" in _ag_log_df.columns:
                            _seen_pairs = sorted(_ag_log_df["pair"].dropna().unique().tolist())
                            st.caption(f"Pairs with decisions logged: {', '.join(_seen_pairs)}")
                except Exception as _ae:
                    logger.warning("[Agent] log display error: %s", _ae)
                    st.caption("Agent activity log temporarily unavailable.")
        else:
            # Config was disabled — stop the running supervisor if active
            try:
                if _agent is not None and _agent.supervisor.is_running():
                    _agent.supervisor.stop()
            except Exception as _e:
                logging.warning("[Agent] supervisor stop failed: %s", _e)

        # ── Connected Wallet Panel (#110 / #111) ──────────────────────────────────
        _wh = st.session_state.get("wallet_holdings")
        _zp = st.session_state.get("zerion_portfolio")
        if _wh or _zp:
            st.markdown("---")
            _ui.section_header("Connected Wallet", "Read-only portfolio import", icon="🔗")
            _portfolio = _zp or _wh  # prefer full Zerion portfolio when available
            _wh_c1, _wh_c2, _wh_c3 = st.columns(3)
            _wh_c1.metric("Total Value", f"${_portfolio.get('total_value_usd', 0):,.2f}")
            _wh_c2.metric("Address", (_portfolio.get('address', '') or '')[:10] + "…")
            _wh_c3.metric("Source", (_portfolio.get('source') or 'zerion').upper())

            # 24h change (Zerion only)
            if _zp and _zp.get("change_24h_pct") is not None:
                _chg = _zp.get("change_24h_pct", 0.0)
                st.metric("24h Change", f"{_chg:+.2f}%", delta=f"{_chg:+.2f}%")

            # Top holdings
            _tokens = _portfolio.get("tokens") or _portfolio.get("positions") or []
            if _tokens:
                with st.expander("Top Holdings", expanded=True):
                    _top5 = sorted(_tokens, key=lambda x: x.get("value_usd") or 0, reverse=True)[:5]
                    _tok_rows = []
                    for _tok in _top5:
                        try:
                            _bal  = float(_tok.get("balance")  or 0)
                            _val  = float(_tok.get("value_usd") or 0)
                            _chg  = _tok.get("change_pct_1d")
                            _chg_fmt = f"{float(_chg):+.2f}%" if _chg is not None else "—"
                        except (TypeError, ValueError):
                            _bal, _val, _chg_fmt = 0.0, 0.0, "—"
                        _tok_rows.append({
                            "Symbol":     _tok.get("symbol", ""),
                            "Balance":    f"{_bal:,.4f}",
                            "Value USD":  f"${_val:,.2f}",
                            "24h %":      _chg_fmt,
                            "Chain":      _tok.get("chain") or "Ethereum",
                        })
                    if _tok_rows:
                        st.dataframe(pd.DataFrame(_tok_rows), width='stretch', hide_index=True)

            # Chain breakdown (Zerion full portfolio)
            if _zp and _zp.get("chains"):
                with st.expander("Chain Breakdown", expanded=False):
                    _chain_data = _zp["chains"]
                    _chain_rows = [{"Chain": c, "Value USD": f"${v:,.2f}"} for c, v in _chain_data.items()]
                    if _chain_rows:
                        st.dataframe(pd.DataFrame(_chain_rows), width='stretch', hide_index=True)


    with _dash_tab2:
        # ── Signal Heatmap — pairs × timeframes (Item 8: card list for beginners) ──
        if _user_lv in ("beginner", "intermediate"):
            _ui.section_header(
                "All Signals — Ranked by Strength",
                "Coins sorted from strongest to weakest signal. ▲ = potential buy, ▼ = potential sell, ■ = wait/unclear.",
                icon="🏆",
            )
            st.markdown(_ui.signal_rank_list_html(results), unsafe_allow_html=True)
            st.markdown("---")
        else:
            _ui.section_header("Signal Heatmap",
                               "Color grid of all coins across time periods. 🟢 Green = potential buy, 🔴 Red = potential sell, ⬜ Grey = no clear signal. Numbers = model confidence %.",
                               icon="🗺️")
            _tf_list  = model.TIMEFRAMES
            _hm_pairs = [r["pair"] for r in results]
            _hm_conf  = []
            _hm_text  = []
            _hm_dir   = []
            for r in results:
                _tfd      = r.get("timeframes", {})
                _row_conf = []
                _row_text = []
                _row_dir  = []
                for tf in _tf_list:
                    _cell = _tfd.get(tf, {})
                    _c    = float(_cell.get("confidence", 0) or 0)
                    _d    = str(_cell.get("direction", "NO DATA") or "NO DATA")
                    _row_conf.append(_c)
                    _row_text.append(f"{int(_c)}%\n{_d[:3]}")
                    _row_dir.append(_d)
                _hm_conf.append(_row_conf)
                _hm_text.append(_row_text)
                _hm_dir.append(_row_dir)

            def _dir_to_val(d: str) -> float:
                d = d.upper()
                if "STRONG BUY"  in d: return  1.0
                if "BUY"         in d: return  0.5
                if "STRONG SELL" in d: return -1.0
                if "SELL"        in d: return -0.5
                return 0.0

            _hm_color = [[_dir_to_val(d) for d in row] for row in _hm_dir]
            _hm_fig   = go.Figure(data=go.Heatmap(
                z            = _hm_color,
                x            = _tf_list,
                y            = _hm_pairs,
                text         = _hm_text,
                texttemplate = "%{text}",
                textfont     = {"size": 9},
                colorscale   = [
                    [0.0,  "#ff4b4b"],
                    [0.25, "#ffaaaa"],
                    [0.5,  "#888888"],
                    [0.75, "#99e6cc"],
                    [1.0,  "#00d4aa"],
                ],
                zmin=-1, zmax=1,
                showscale=False,
                hovertemplate="<b>%{y}</b> / %{x}<br>%{text}<extra></extra>",
            ))
            _hm_fig.update_layout(
                height=max(250, 32 * len(_hm_pairs) + 60),
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                font=dict(color="#fafafa", size=9),
                xaxis=dict(side="top", tickfont=dict(size=9)),
                yaxis=dict(autorange="reversed", tickfont=dict(size=9)),
            )
            st.plotly_chart(_hm_fig, width='stretch',
                            config={"displayModeBar": False, "staticPlot": True})
            st.markdown("---")

        # ── Quick-View Card Grid — all coins at a glance (teen-friendly) ──────────
        _ui.section_header(
            "What To Do Right Now",
            "Each card shows whether to BUY, SELL, or WAIT — score out of 10 shows how strong the signal is",
            icon="🎯",
        )
        # PERF-28: use the single _live_prices fetched at the top of page_dashboard()
        _all_ws_prices = _live_prices
        # Sort: high-conf first, then by confidence descending for card grid
        _grid_results = sorted(results, key=lambda r: (r.get("high_conf", False), r.get("confidence_avg_pct", 0)), reverse=True)
        # Fetch liquidation pressure for cascade risk badges (uses cached OI + funding data)
        _squeeze_data: dict = {}
        try:
            _sq_list = data_feeds.get_liquidation_pressure([r["pair"] for r in _grid_results[:15]])
            _squeeze_data = {s["pair"]: s.get("squeeze_signal", "NORMAL") for s in _sq_list}
        except Exception as _e:
            logging.debug("[Panel] liquidation_pressure fetch failed: %s", _e)
        st.markdown(
            _ui.coin_cards_grid_html(_grid_results, ws_prices=_all_ws_prices,
                                     squeeze_data=_squeeze_data),
            unsafe_allow_html=True,
        )

        # Quick-glance summary table (advanced users)
        with st.expander("📋 Full Summary Table", expanded=False):
            summary_rows = []
            for r in results:
                _st = _all_ws_prices.get(r["pair"])
                _live_str = (
                    f"${_st['price']:,.4f} ({_st['change_24h_pct']:+.2f}%)" if _st else "—"
                )
                _tp1 = r.get("tp1")
                summary_rows.append({
                    "Coin": r["pair"],
                    "Price": _live_str,
                    "Signal": r.get("direction", "N/A"),
                    "Strength": f"{r.get('confidence_avg_pct', 0)}%",
                    "Entry Price": f"${r['entry']:,.4f}" if r.get("entry") else "N/A",
                    "Take Profit": f"${_tp1:,.4f}" if _tp1 else "N/A",
                    "Stop Loss": f"${r['stop_loss']:,.4f}" if r.get("stop_loss") else "N/A",
                    "Top Pick":   "⚡ Yes" if r.get("high_conf") else "—",
                })
                _pair_key = r["pair"]
                _cyc = st.session_state.get(f"tb_score_{_pair_key}")
                summary_rows[-1]["Cycle Score"] = f"{_cyc}/100" if _cyc is not None else "—"
            st.dataframe(pd.DataFrame(summary_rows).set_index("Coin"), width='stretch')
        st.markdown("---")


        # ── Scan Overview — Sparkline Mini-Grid (#60) ─────────────────────────────
        _ui.section_header("Scan Overview", "Mini sparklines — 24h price trend for each pair at a glance. Green = up, Red = down.", icon="📈")
        # #59 Mobile-responsive layout: 2-column grid on wide screens; note if only 1 result
        _spk_n_results = len(sorted_results)
        if _spk_n_results == 1:
            st.caption("Single result — showing in single-column layout.")
            _spk_n_cols = 1
        else:
            _spk_n_cols = min(_spk_n_results, 4)  # up to 4 columns; CSS grid handles responsive wrap
        _spk_cols = st.columns(_spk_n_cols)
        _spk_pairs_12 = [_sr["pair"] for _sr in sorted_results[:12]]
        # PERF-27: fetch all sparklines in parallel (was sequential — N × round-trip latency)
        try:
            from concurrent.futures import ThreadPoolExecutor as _SpkTEx
            def _fetch_spk(pair_):
                try:
                    return data_feeds.fetch_sparkline_closes(pair_, n=24)
                except Exception:
                    return []
            with _SpkTEx(max_workers=min(len(_spk_pairs_12), 12)) as _spk_ex:
                _spk_results = dict(zip(_spk_pairs_12, _spk_ex.map(_fetch_spk, _spk_pairs_12)))
        except Exception:
            _spk_results = {}
        for _si, _sr in enumerate(sorted_results[:12]):  # max 12 cards in grid
            _col_idx = _si % _spk_n_cols
            with _spk_cols[_col_idx]:
                _spk_closes = _spk_results.get(_sr["pair"], [])
                _spk_html = _ui.scan_sparkline_card_html(
                    pair      = _sr["pair"],
                    direction = _sr.get("direction", "—"),
                    conf      = _sr.get("confidence_avg_pct", 0),
                    closes    = _spk_closes,
                )
                st.markdown(_spk_html, unsafe_allow_html=True)
                st.markdown("<div style='margin-bottom:6px'></div>", unsafe_allow_html=True)
        st.markdown("---")

        # ── S1-S10 Advanced Analytics Panels ─────────────────────────────────────
        _s_macro_regime = results[0].get("macro_regime", "MACRO_NEUTRAL") if results else "MACRO_NEUTRAL"
        _s_altcoin      = results[0].get("altcoin_season", "MIXED") if results else "MIXED"

        # S10 — Market Regime Banner (BULL / BEAR / SIDEWAYS from buy/sell majority + F&G)
        try:
            _ui.render_market_regime_banner(results, _fng_val, _s_macro_regime, _s_altcoin)
        except Exception as _e:
            logging.debug("[Panel S10] market_regime_banner failed: %s", _e)

        # S1 — TTM Squeeze Momentum Panel
        try:
            _ui.render_ttm_squeeze_panel(_spk_results, results, _sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S1] ttm_squeeze failed: %s", _e)

        # S2 — Hurst Exponent Panel
        try:
            _ui.render_hurst_exponent_panel(_spk_results, results, _sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S2] hurst_exponent failed: %s", _e)

        # S3 — RSI / MACD Divergence Panel
        try:
            _ui.render_rsi_macd_divergence_panel(results, _sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S3] rsi_macd_divergence failed: %s", _e)

        # S4 — Funding Rate Arbitrage Panel
        try:
            _ui.render_funding_rate_arb_panel(results, _sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S4] funding_rate_arb failed: %s", _e)

        # S5 — Liquidation Heatmap Panel (real Binance events + OI cluster model)
        try:
            _liq_hm_data = data_feeds.build_liquidation_heatmap_data(
                [r["pair"] for r in results[:12]], _live_prices
            )
            _ui.render_liquidation_overlay_panel(results, _sg_level_val, liq_data=_liq_hm_data)
        except Exception as _e:
            logging.debug("[Panel S5] liquidation_overlay failed: %s", _e)

        # S6 — Social Momentum Panel
        try:
            _ui.render_social_momentum_panel(results, _sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S6] social_momentum failed: %s", _e)

        # S7 — GitHub Developer Activity Panel
        try:
            _ui.render_github_dev_activity_panel(_sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S7] github_dev_activity failed: %s", _e)

        # S8 — Trader vs Investor Split Panel
        try:
            _ui.render_trader_investor_split(results, _sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S8] trader_investor_split failed: %s", _e)

        # S9 — Threshold Alerts Panel
        try:
            _ui.render_threshold_alerts_panel(results, _sg_level_val)
        except Exception as _e:
            logging.debug("[Panel S9] threshold_alerts failed: %s", _e)

        st.markdown("---")
        # ── Signal Heatmap (Phase 9) — all 29 pairs at a glance ──────────────────
        if results:
            st.markdown("---")
            _ui.section_header("Signal Heatmap", "All pairs — color = signal strength (green=BUY, red=SELL, grey=HOLD)", icon="🗺️")

            from crypto_model_core import SECTOR_MAP, PAIRS as _ALL_PAIRS

            # Map pair → signal score for color coding
            _sig_map = {}
            for _r in results:
                _p   = _r.get("pair", "")
                _dir = _r.get("direction", "")
                _sc  = _r.get("score", 0.0) or 0.0
                _sig_map[_p] = (_dir, _sc)

            # Build grid ordered by sector then pair name
            _sector_order = ["store_of_value", "layer1", "payments", "defi", "exchange", "layer2", "infrastructure", "ai", "meme", "other"]
            _by_sector: dict = {}
            for _pp in _ALL_PAIRS:
                _s = SECTOR_MAP.get(_pp, "other")
                _by_sector.setdefault(_s, []).append(_pp)

            _heat_html = "<div style='display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;'>"
            for _sec in _sector_order:
                _sec_pairs = _by_sector.get(_sec, [])
                if not _sec_pairs:
                    continue
                # Sector label
                _heat_html += (
                    f"<div style='width:100%;font-size:10px;text-transform:uppercase;"
                    f"letter-spacing:0.8px;color:#6b7280;margin:8px 0 4px;font-weight:600;'>"
                    f"{_sec.replace('_', ' ')}</div>"
                )
                _heat_html += "<div style='display:flex;flex-wrap:wrap;gap:6px;'>"
                for _pp in _sec_pairs:
                    _base = _pp.split("/")[0]
                    _dir, _sc = _sig_map.get(_pp, ("HOLD", 0.0))
                    if "BUY" in _dir:
                        _bg   = f"rgba(0,212,170,{min(0.85, 0.25 + abs(_sc)/100)})"
                        _border = "#00d4aa"
                        _tc   = "#e2e8f0"
                    elif "SELL" in _dir:
                        _bg   = f"rgba(246,70,93,{min(0.85, 0.25 + abs(_sc)/100)})"
                        _border = "#f6465d"
                        _tc   = "#e2e8f0"
                    else:
                        _bg   = "rgba(107,114,128,0.15)"
                        _border = "#374151"
                        _tc   = "#6b7280"
                    _sc_str = f"{_sc:+.0f}" if _sc != 0 else "—"
                    _heat_html += (
                        f"<div style='background:{_bg};border:1px solid {_border};"
                        f"border-radius:8px;padding:6px 10px;min-width:64px;text-align:center;"
                        f"cursor:default;'>"
                        f"<div style='font-size:12px;font-weight:700;color:{_tc};'>{_base}</div>"
                        f"<div style='font-size:10px;color:{_border};margin-top:2px;font-weight:600;'>"
                        f"{_dir.replace('STRONG_', '').replace('_BIAS', '')} {_sc_str}</div>"
                        f"</div>"
                    )
                _heat_html += "</div>"
            _heat_html += "</div>"

            st.markdown(_heat_html, unsafe_allow_html=True)
            _buys  = sum(1 for d, _ in _sig_map.values() if "BUY"  in d)
            _sells = sum(1 for d, _ in _sig_map.values() if "SELL" in d)
            _holds = len(_sig_map) - _buys - _sells
            st.caption(f"Signal summary: {_buys} BUY · {_sells} SELL · {_holds} HOLD · Score = composite signal strength (higher = stronger)")

        # ── Global Market Context (folded in from Market Overview) ─────────────────
        with st.expander("🌍 Global Market Context", expanded=False):
            _gm  = _cached_global_market()
            _gtr = _cached_trending_coins()

            def _fmt_cap_d(v):
                if v >= 1e12: return f"${v/1e12:.2f}T"
                if v >= 1e9:  return f"${v/1e9:.1f}B"
                return f"${v/1e6:.0f}M"

            _tm   = _gm.get("total_market_cap_usd", 0)
            _bd   = _gm.get("btc_dominance", 0.0)
            _ed   = _gm.get("eth_dominance", 0.0)
            _mchg = _gm.get("market_cap_change_24h", 0.0)
            _vol  = _gm.get("total_volume_24h_usd", 0)
            _alt  = _gm.get("altcoin_season_label", "N/A")
            _gdc  = "#00c076" if _mchg >= 0 else "#f6465d"
            _ga   = "▲" if _mchg >= 0 else "▼"
            _gc1, _gc2, _gc3, _gc4, _gc5 = st.columns(5)
            with _gc1:
                st.metric("Total Market Cap", _fmt_cap_d(_tm),
                          delta=f"{_ga} {abs(_mchg):.2f}% 24h", delta_color="normal")
            with _gc2:
                st.metric("BTC Dominance", f"{_bd:.1f}%")
            with _gc3:
                st.metric("ETH Dominance", f"{_ed:.1f}%")
            with _gc4:
                st.metric("24h Volume", _fmt_cap_d(_vol))
            with _gc5:
                st.metric("Market Regime", _alt.replace("_", " "))

            if _gtr:
                _chips = " ".join(
                    f'<span style="display:inline-block;padding:3px 10px;border-radius:20px;'
                    f'background:rgba(0,212,170,0.12);border:1px solid rgba(0,212,170,0.3);'
                    f'color:#00d4aa;font-size:12px;font-weight:600;margin:2px">{s}</span>'
                    for s in _gtr[:10]
                )
                st.markdown(
                    f'<div style="margin:4px 0 12px">'
                    f'<span style="color:rgba(255,255,255,0.45);font-size:11px;'
                    f'text-transform:uppercase;letter-spacing:0.8px;margin-right:10px">🔥 Trending</span>'
                    + _chips + '</div>',
                    unsafe_allow_html=True,
                )



    with _dash_tab3:
        # ── Coin Selector Dropdown ─────────────────────────────────────────────────
        _ui.section_header("Dive Deeper — Pick a Coin", "Choose a coin below to see the full breakdown: entry price, stop loss, AI prediction, news sentiment, and more", icon="🔬")

        def _pair_label(r):
            _d  = r.get("direction", "N/A")
            _c  = r.get("confidence_avg_pct", 0)
            _ic = direction_color(_d)
            _hc = "  ⚡ TOP PICK" if r.get("high_conf") else ""
            _tr = "  🔥" if r.get("trending") else ""
            # Risk indicator for the dropdown label
            _pos = r.get("position_size_pct") or 10
            if _c >= 70 and _pos <= 15:
                _risk = "🟢 Low Risk"
            elif _c >= 55 and _pos <= 25:
                _risk = "🟡 Med Risk"
            else:
                _risk = "🔴 Higher Risk"
            return f"{_ic}  {r['pair']}  ·  {_c:.0f}% strength  ·  {_d}  ·  {_risk}{_hc}{_tr}"

        _pair_labels  = [_pair_label(r) for r in sorted_results]
        _label_to_r   = dict(zip(_pair_labels, sorted_results))

        _selected_label = st.selectbox(
            "Choose a coin to inspect",
            options=_pair_labels,
            index=0,
            label_visibility="collapsed",
            key="coin_selector",
        )
        r = _label_to_r[_selected_label]
        # PERF-24: prefer full result from module-level store (avoids session_state serialization)
        pair = r["pair"]
        r = _SCAN_RESULTS_STORE.get(pair, r)  # fall back to session_state copy if store not populated

        # ── Selected Coin Detail Panel ─────────────────────────────────────────────
        pair        = r["pair"]
        conf        = r.get("confidence_avg_pct", 0)
        direction   = r.get("direction", "N/A")
        bias        = r.get("strategy_bias", "N/A")
        mtf         = r.get("mtf_alignment", 0)
        price       = r.get("price_usd")
        entry       = r.get("entry")
        exit_       = r.get("exit")
        stop        = r.get("stop_loss")
        pos_pct     = r.get("position_size_pct")
        is_hc       = r.get("high_conf", False)
        is_trending = r.get("trending", False)

        # ── DECISIVE TRADE ACTION CARD (always first — beginner to advanced) ─────
        _d_up    = "BUY"  in direction.upper()
        _d_down  = "SELL" in direction.upper()
        _d_color = "#22c55e" if _d_up else ("#ef4444" if _d_down else "#f59e0b")
        _d_shape = "▲" if _d_up else ("▼" if _d_down else "■")
        _d_label = direction.replace("STRONG ", "STRONG ")  # preserve as-is
        _tp1_act = r.get("tp1") or exit_
        _conf_10 = max(1, min(10, round(conf / 10)))

        # Per-timeframe signal breakdown (MTF table)
        _tf_data    = r.get("timeframes", {})
        _tf_order   = ["1h", "4h", "1d", "1w"]
        _tf_labels  = {"1h": "1 Hour", "4h": "4 Hour", "1d": "Daily", "1w": "Weekly"}
        _tf_rows_html = ""
        _tf_agree_buy  = 0
        _tf_agree_sell = 0
        for _tf in _tf_order:
            _tfc = _tf_data.get(_tf, {})
            if not _tfc:
                continue
            _tfd  = str(_tfc.get("direction", "NO DATA"))
            _tfpc = float(_tfc.get("confidence", 0) or 0)
            _tf_is_buy  = "BUY"  in _tfd.upper()
            _tf_is_sell = "SELL" in _tfd.upper()
            if _tf_is_buy:  _tf_agree_buy  += 1
            if _tf_is_sell: _tf_agree_sell += 1
            _tf_color = "#22c55e" if _tf_is_buy else ("#ef4444" if _tf_is_sell else "#f59e0b")
            _tf_shape = "▲" if _tf_is_buy else ("▼" if _tf_is_sell else "■")
            _tf_bar_w = int(min(100, _tfpc))
            _tf_rows_html += (
                f"<tr>"
                f"<td style='padding:3px 10px 3px 4px;color:#94a3b8;font-size:0.79rem;white-space:nowrap'>{_tf_labels.get(_tf,'')}</td>"
                f"<td style='padding:3px 8px;color:{_tf_color};font-weight:700;font-size:0.82rem'>{_tf_shape} {_tfd}</td>"
                f"<td style='padding:3px 8px;min-width:90px'>"
                f"<div style='background:rgba(255,255,255,0.06);border-radius:4px;height:8px;overflow:hidden'>"
                f"<div style='background:{_tf_color};width:{_tf_bar_w}%;height:100%;border-radius:4px'></div>"
                f"</div></td>"
                f"<td style='padding:3px 4px;color:{_tf_color};font-size:0.78rem'>{int(_tfpc)}%</td>"
                f"</tr>"
            )

        _mtf_total = _tf_agree_buy + _tf_agree_sell
        if _tf_agree_buy >= 3:
            _mtf_verdict = "✅ STRONG ALIGNMENT — Multiple timeframes confirm BUY"
            _mtf_vc = "#22c55e"
        elif _tf_agree_sell >= 3:
            _mtf_verdict = "✅ STRONG ALIGNMENT — Multiple timeframes confirm SELL"
            _mtf_vc = "#ef4444"
        elif _tf_agree_buy == 2:
            _mtf_verdict = "⚡ PARTIAL BUY — 2 timeframes bullish, mixed overall"
            _mtf_vc = "#86efac"
        elif _tf_agree_sell == 2:
            _mtf_verdict = "⚠️ PARTIAL SELL — 2 timeframes bearish, mixed overall"
            _mtf_vc = "#f97316"
        else:
            _mtf_verdict = "⬛ MIXED — Timeframes disagree. Wait for clarity."
            _mtf_vc = "#94a3b8"

        # Cycle timing from session state (populated by top/bottom widget below)
        _cycle_score = st.session_state.get(f"tb_score_{pair}", None)
        if _cycle_score is not None:
            if _cycle_score >= 80:    _cycle_text, _cycle_color = f"✅ EXCELLENT TIMING — Cycle Score {_cycle_score}/100 (Bottom Zone)", "#22c55e"
            elif _cycle_score >= 65:  _cycle_text, _cycle_color = f"👍 GOOD TIMING — Cycle Score {_cycle_score}/100 (Buy Zone)", "#86efac"
            elif _cycle_score >= 35:  _cycle_text, _cycle_color = f"⏳ NEUTRAL TIMING — Cycle Score {_cycle_score}/100 (Wait)", "#f59e0b"
            elif _cycle_score >= 20:  _cycle_text, _cycle_color = f"⚠️ CAUTION — Cycle Score {_cycle_score}/100 (Top Zone)", "#f97316"
            else:                     _cycle_text, _cycle_color = f"🛑 POOR TIMING — Cycle Score {_cycle_score}/100 (Extreme Top)", "#ef4444"
            _cycle_row = (f"<tr><td style='padding:6px 10px 6px 4px;color:#64748b;font-size:0.79rem;font-weight:600'>CYCLE TIMING</td>"
                          f"<td colspan='3' style='padding:6px 4px;color:{_cycle_color};font-size:0.82rem;font-weight:700'>{_cycle_text}</td></tr>")
        else:
            _cycle_row = ""

        st.markdown(
            f"<div style='background:linear-gradient(135deg,rgba({('34,197,94' if _d_up else ('239,68,68' if _d_down else '245,158,11'))},0.08) 0%,rgba(0,0,0,0.2) 100%);"
            f"border:1px solid {_d_color}44;border-left:5px solid {_d_color};"
            f"border-radius:12px;padding:18px 22px;margin-bottom:16px'>"
            f"<div style='display:flex;align-items:center;gap:16px;margin-bottom:14px;flex-wrap:wrap'>"
            f"<div style='font-size:2.2rem;font-weight:900;color:{_d_color};line-height:1'>{_d_shape} {_d_label}</div>"
            f"<div style='background:{_d_color}22;border:1px solid {_d_color}66;border-radius:20px;padding:4px 14px;"
            f"color:{_d_color};font-size:0.85rem;font-weight:700'>{_conf_10}/10 strength · {conf:.0f}%</div>"
            f"<div style='color:#64748b;font-size:0.8rem;margin-left:auto'>{pair} · {bias}</div>"
            f"</div>"
            f"<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px'>"
            f"<div style='background:rgba(255,255,255,0.04);border-radius:8px;padding:10px 14px'>"
            f"<div style='color:#475569;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px'>Entry Zone</div>"
            f"<div style='color:#e2e8f0;font-size:1rem;font-weight:700'>${entry:,.4f}</div>" if entry else
            f"<div style='color:#e2e8f0;font-size:1rem;font-weight:700'>—</div>"
            f"</div>"
            f"<div style='background:rgba(239,68,68,0.06);border-radius:8px;padding:10px 14px'>"
            f"<div style='color:#475569;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px'>Stop Loss</div>"
            f"<div style='color:#ef4444;font-size:1rem;font-weight:700'>${stop:,.4f}</div>" if stop else
            f"<div style='color:#ef4444;font-size:1rem;font-weight:700'>—</div>"
            f"</div>"
            f"<div style='background:rgba(34,197,94,0.06);border-radius:8px;padding:10px 14px'>"
            f"<div style='color:#475569;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:2px'>Take Profit</div>"
            f"<div style='color:#22c55e;font-size:1rem;font-weight:700'>${_tp1_act:,.4f}</div>" if _tp1_act else
            f"<div style='color:#22c55e;font-size:1rem;font-weight:700'>—</div>"
            f"</div>"
            f"</div>"
            f"<div style='font-size:0.75rem;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:6px'>Timeframe Breakdown</div>"
            f"<table style='width:100%;border-collapse:collapse'>"
            f"{_tf_rows_html}"
            f"<tr><td colspan='4' style='padding:6px 4px;color:{_mtf_vc};font-size:0.82rem;font-weight:700;border-top:1px solid rgba(255,255,255,0.06)'>{_mtf_verdict}</td></tr>"
            f"{_cycle_row}"
            f"</table>"
            f"</div>",
            unsafe_allow_html=True,
        )

        _ui.signal_card_header(
            pair=pair, direction=direction, conf=conf,
            bias=bias, regime=r.get("regime", "N/A"), is_hc=is_hc,
        )

        # Signal strength visual dots + risk badge — beginner at-a-glance indicators
        _str_dots  = _ui.signal_strength_stars(conf)
        _risk_chip = _ui.risk_level_badge_html(conf, pos_pct)
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:16px;margin:-6px 0 10px 0">'
            f'{_str_dots}'
            f'<span style="opacity:0.3">|</span>'
            f'{_risk_chip}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Plain English summary — designed for users unfamiliar with trading terms
        _plain_summary = _ui.signal_plain_english(
            pair=pair, direction=direction, conf=conf, mtf=mtf,
            regime=r.get("regime", ""), entry=entry, stop=stop, exit_=exit_,
        )
        _ui.plain_english_box(_plain_summary, direction)

        if is_trending:
            st.markdown(
                '<span style="display:inline-block;padding:2px 10px;border-radius:20px;'
                'background:rgba(0,212,170,0.12);border:1px solid rgba(0,212,170,0.3);'
                'color:#00d4aa;font-size:11px;font-weight:600;margin-bottom:6px">'
                '🔥 Trending on CoinGecko right now</span>',
                unsafe_allow_html=True,
            )

        # #26 Pi Cycle Top warning on the coin detail card
        _r_pi_flags = r.get("signal_flags", [])
        if "PI_CYCLE_TOP_WARNING" in _r_pi_flags:
            st.warning(
                "⚠️ **PI_CYCLE_TOP_WARNING** — Confidence capped at 30% (cycle top indicator active). "
                "Exercise extreme caution with new BUY entries."
            )

        # ── Row 1: Price · Entry · Stop Loss ──────────────────────────────────────
        top_cols = st.columns(3)
        _live_tick = _ws.get_price(pair)
        if _live_tick and "price" in _live_tick and "change_24h_pct" in _live_tick:
            top_cols[0].metric(
                "Current Price ⬤ LIVE",
                f"${_live_tick['price']:,.4f}",
                delta=f"{_live_tick['change_24h_pct']:+.2f}% today",
                help="Live price from OKX.",
            )
        else:
            top_cols[0].metric("Current Price", f"${price:,.4f}" if price else "N/A")
        _entry_label = "Buy At" if "BUY" in direction.upper() else ("Sell At" if "SELL" in direction.upper() else "Entry Price")
        top_cols[1].metric(_entry_label, f"${entry:,.4f}" if entry else "N/A",
                           help="The price to enter this trade. Try to get close to this level.")
        top_cols[2].metric("Stop Loss — Exit If Wrong", f"${stop:,.4f}" if stop else "N/A",
                           help="If price hits this level, exit the trade to limit your loss.")

        # ── Row 2: Take Profit · Signal Strength · Trade Size ─────────────────────
        bot_cols = st.columns(3)
        _tp1_val = r.get("tp1") or exit_
        bot_cols[0].metric("🎯 Cash-Out Price", f"${_tp1_val:,.4f}" if _tp1_val else "N/A",
                           help="This is your TARGET — the price to sell at and take your profit. Think of it as the finish line.")
        # Macro Trend Score — weighted average across all 4 timeframes (1H:10%, 4H:20%, 1D:35%, 1W:35%)
        # Renamed from "Confidence Score" to "Macro Trend Score" to clarify it is the combined view.
        _score_10 = max(1, min(10, round(conf / 10)))
        bot_cols[1].metric("📈 Macro Trend Score", f"{_score_10}/10  ({conf:.0f}%)",
                           help=(
                               "The Macro Trend Score combines all timeframes into one number — "
                               "think of it as the overall direction of the boat. "
                               "Weights: 1H=10%, 4H=20%, Daily=35%, Weekly=35%. "
                               "Above 65% = actionable signal. 7+/10 = strong conviction. "
                               "5 or below = mixed — wait for clarity."
                           ))
        # #50 Fractional Kelly position sizing — display recommended size from Kelly formula
        _kelly_pos_pct = pos_pct   # default to model-computed size
        try:
            import risk_metrics as _risk_mod
            # Use cached backtest DF — avoids an expensive uncached DB read on every card render
            _bt_kelly = _cached_backtest_df()
            if not _bt_kelly.empty:
                _bt_valid = _bt_kelly[_bt_kelly['pnl_pct'].notna()]
                if len(_bt_valid) >= 20:
                    _wins_k   = _bt_valid[_bt_valid['pnl_pct'] > 0]
                    _losses_k = _bt_valid[_bt_valid['pnl_pct'] <= 0]
                    if len(_wins_k) > 0 and len(_losses_k) > 0:
                        _wr  = len(_wins_k) / len(_bt_valid)
                        _aw  = float(_wins_k['pnl_pct'].mean()) / 100
                        _al  = float(abs(_losses_k['pnl_pct'].mean())) / 100
                        _kf  = _risk_mod.compute_kelly_fraction(_wr, _aw, _al, fraction=0.25)
                        _kelly_pos_pct = _kf.get("recommended_position_pct", pos_pct)
        except Exception:
            pass
        bot_cols[2].metric(
            "Suggested Trade Size",
            f"{_kelly_pos_pct}% of funds" if _kelly_pos_pct else "N/A",
            help=(
                "Recommended position size as % of portfolio based on historical win rate. "
                "Fractional Kelly (25%) reduces risk of ruin. "
                "If you have $1,000 and it says 10%, use $100."
            ),
        )

        # Item 7: "What Does This Mean For Me?" — beginner/intermediate contextual dollar summary
        if _user_lv in ("beginner", "intermediate"):
            try:
                _portfolio_sz = float(_cached_alerts_config().get("portfolio_size", 1000))
            except Exception:
                _portfolio_sz = 1000.0
            st.markdown(
                _ui.wdtmfm_html(direction, entry, stop, exit_, conf, _portfolio_sz),
                unsafe_allow_html=True,
            )

        # Gradient confidence bar (#62) — signal-aware color-coded bar
        st.markdown(_ui.render_confidence_bar(conf, direction), unsafe_allow_html=True)

        # ── #59 Key metrics row with beginner tooltips ─────────────────────────────
        _km_tf1 = (list(r.get("timeframes", {}).values()) or [{}])[0]
        try:
            _km_rsi_raw = _km_tf1.get("rsi")
            _km_rsi = float(_km_rsi_raw) if _km_rsi_raw is not None else None
        except (TypeError, ValueError):
            _km_rsi = None
        try:
            _km_adx_raw = _km_tf1.get("adx")
            _km_adx = float(_km_adx_raw) if _km_adx_raw is not None else None
        except (TypeError, ValueError):
            _km_adx = None
        try:
            _km_fr_raw = r.get("funding_rate_pct") or (r.get("timeframes", {}).get("1h", {}) or {}).get("funding")
            _km_fr = float(_km_fr_raw) if _km_fr_raw is not None else None
        except (TypeError, ValueError):
            _km_fr = None
        _km_chg = (_ws.get_price(pair) or {}).get("change_24h_pct")
        _km_c1, _km_c2, _km_c3, _km_c4 = st.columns(4)
        _km_c1.metric(
            "Current Price",
            f"${price:,.4f}" if price else "N/A",
            delta=f"{_km_chg:+.2f}% 24h" if _km_chg is not None else None,
        )
        _km_c2.metric(
            "RSI (1h)",
            f"{_km_rsi:.1f}" if _km_rsi is not None else "N/A",
            help="RSI above 70 = overbought, below 30 = oversold. Best range: 40-60 for entries.",
        )
        _km_c3.metric(
            "ADX (1h)",
            f"{_km_adx:.1f}" if _km_adx is not None else "N/A",
            help="Trend strength indicator. Above 25 = strong trend. Below 20 = choppy/ranging.",
        )
        _km_c4.metric(
            "Funding Rate",
            f"{_km_fr:+.4f}%" if _km_fr is not None else "N/A",
            help="Positive = longs pay shorts (bullish market). Negative = shorts pay longs (bearish market). Extreme values warn of reversals.",
        )

        # AI agent agreement count — "X of 6 AI models agree" is more readable than a raw score
        _consensus     = r.get("consensus", 0.0)
        _agents_agree  = round(_consensus * 6)   # consensus = fraction of 6 agents with abs(vote)>70
        _agree_color   = "#00d4aa" if _agents_agree >= 4 else ("#f59e0b" if _agents_agree >= 2 else "#f6465d")

        # Signal accuracy badge — shows historical win rate for this pair/direction
        try:
            _acc_data = _cached_signal_win_rate(pair=pair, direction=direction, days=90)
            _acc_badge = _ui.signal_accuracy_badge_html(
                win_rate    = _acc_data.get("win_rate", 0.5),
                sample_size = _acc_data.get("sample_size", 0),
                signal_type = direction.replace("STRONG ", ""),
            )
        except Exception:
            _acc_badge = ""

        st.markdown(
            f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:12px;'
            f'font-size:12px;color:rgba(168,180,200,0.6);margin:-4px 0 10px 0">'
            f'<span>'
            f'<span style="color:{_agree_color};font-weight:700">{_agents_agree} of 6</span>'
            f' AI models agree on this signal'
            f'</span>'
            f'{_acc_badge}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Item 6 Tier 2: "Why this signal?" plain-English reasoning ─────────────
        if _user_lv in ("beginner", "intermediate"):
            with st.expander("🔍 Why this signal? — Plain-English reasons", expanded=False):
                st.markdown(
                    _ui.why_signal_html(
                        direction     = direction,
                        conf          = conf,
                        rsi           = _km_rsi,
                        adx           = _km_adx,
                        mtf           = mtf,
                        consensus     = r.get("consensus", 0.0),
                        regime        = r.get("regime", ""),
                        bias          = r.get("strategy_bias", ""),
                        funding_rate  = _km_fr,
                    ),
                    unsafe_allow_html=True,
                )

        # ── Top/Bottom Score widget ────────────────────────────────────────────────
        try:
            from top_bottom_detector import compute_composite_top_bottom_score, render_top_bottom_widget as _rtbw

            @st.cache_data(ttl=3600, show_spinner=False, max_entries=120)
            def _sg_fetch_ohlcv_df(p: str, tf: str, limit: int = 180):
                """Fetch OHLCV via exchange fallback chain → DataFrame.

                max_entries=120 caps memory at ~37 pairs × 3 TFs = 111 slots max.
                Uses the top-level `model` alias (crypto_model_core) — NOT a separate
                `import model` which would fail (no model.py exists in this directory).
                """
                try:
                    raw = model.fetch_chart_ohlcv(p, tf, limit=limit)
                    if not raw:
                        return None
                    _df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    _df[["open", "high", "low", "close", "volume"]] = (
                        _df[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
                    )
                    return _df.dropna(subset=["close"]).reset_index(drop=True)
                except Exception as _e:
                    logging.warning("top_bottom ohlcv fetch %s %s: %s", p, tf, _e)
                    return None

            with st.spinner(f"Computing top/bottom score for {pair}..."):
                _tb_df_d  = _sg_fetch_ohlcv_df(pair, "1d",  180)
                _tb_df_4h = _sg_fetch_ohlcv_df(pair, "4h",  120)
                _tb_df_1h = _sg_fetch_ohlcv_df(pair, "1h",  100)

                # Macro + sentiment from existing scan result
                _tb_macro = {}
                _tb_sent  = {}
                _tb_oc = r.get("onchain_data") or {}
                if _tb_oc:
                    _tb_macro["mvrv_z_score"]       = _tb_oc.get("mvrv_z")
                    _tb_macro["sopr"]               = _tb_oc.get("sopr")
                    _tb_macro["hash_ribbons_signal"] = _tb_oc.get("hash_ribbon_signal")
                if r.get("pi_cycle_ratio"):
                    _tb_macro["pi_cycle_ratio"] = r.get("pi_cycle_ratio")
                _tb_fng = r.get("fng_value")
                if _tb_fng is not None:
                    _tb_sent["fear_greed_value"] = float(_tb_fng)
                _tb_fr = r.get("funding_rate_pct")
                if _tb_fr is not None:
                    _tb_sent["funding_rate_annualized"] = float(_tb_fr) * 365 * 3  # 8h rate → annualized approx

                _tb_result = None
                if _tb_df_d is not None:
                    _tb_result = compute_composite_top_bottom_score(
                        df=_tb_df_d,
                        macro_data=_tb_macro or None,
                        sentiment_data=_tb_sent or None,
                        df_1h=_tb_df_1h,
                        df_4h=_tb_df_4h,
                        symbol=pair.replace("/USDT", "").replace("/USD", ""),
                    )

            if _tb_result:
                # Save score to session state so the Trade Action Card (above) can show cycle timing
                st.session_state[f"tb_score_{pair}"] = _tb_result.get("score", 50)
                st.markdown("---")
                _ui.section_header("Top / Bottom Timing Score", "Where is this coin in its current cycle?", icon="📈")
                _rtbw(_tb_result, user_level=_user_lv)
                if _user_lv == "beginner":
                    st.caption(
                        "ⓘ This score uses 5 layers of analysis: On-Chain Macro · Sentiment · "
                        "RSI/MACD Divergence · Market Structure (BOS/CHoCH, Order Blocks) · "
                        "Volatility (Chandelier Exit, Squeeze). Score 80–100 = historical bottom zone."
                    )
        except ImportError:
            pass
        except Exception as _tb_exc:
            logging.warning("Top/Bottom widget error for %s: %s", pair, _tb_exc)

        # ── Advanced Details (collapsed by default) ────────────────────────────────
        _adv_label = "📊 Technical Details" if _user_lv == "beginner" else "📊 More Details — Timeframes & Technicals"
        with st.expander(_adv_label, expanded=False):
            tp2       = r.get("tp2")
            tp3       = r.get("tp3")
            lev_rec   = r.get("leverage_rec") or {}
            lev_label = lev_rec.get("label", "N/A")
            lev_basis = lev_rec.get("basis", "")
            mtf_conf  = r.get("mtf_confirmed", True)
            rr        = r.get("rr_ratios") or {}

            adv_cols = st.columns(4)
            # Show "N/A" when mtf_alignment is 0 and no valid timeframes had data
            _mtf_display = "N/A" if mtf == 0 and not any(
                td.get("direction") not in ("NO DATA", "N/A", "LOW VOL")
                for td in r.get("timeframes", {}).values()
            ) else f"{mtf}%"
            adv_cols[0].metric("Timeframes Agreeing", _mtf_display, help=_ui.HELP_MTF_ALIGN)
            adv_cols[1].metric("Target 2", f"${tp2:,.4f}" if tp2 else "N/A",
                               delta=rr.get("tp2", ""), help="Second profit target — sell another 40% here.")
            adv_cols[2].metric("Target 3", f"${tp3:,.4f}" if tp3 else "N/A",
                               delta=rr.get("tp3", ""), help="Final ambitious target — hold last 20% here.")
            adv_cols[3].metric(
                "Leverage (Futures Only)",
                lev_label,
                delta="✓ All timeframes agree" if mtf_conf else "⚠️ Mixed signals",
                delta_color="normal" if mtf_conf else "inverse",
                help=(f"For futures trading only. Basis: {lev_basis}. " if lev_basis else "") +
                     "Use 1× for spot trading. Never use leverage you don't understand.",
            )

            tf_data = r.get("timeframes", {})
            if tf_data:
                # ── Shape + color badge helper (CLAUDE.md §8: never color alone) ───────
                _DIR_SHAPE = {
                    "STRONG BUY":  "▲▲",
                    "BUY":         "▲",
                    "HOLD":        "■",
                    "NEUTRAL":     "■",
                    "SELL":        "▽",
                    "STRONG SELL": "▼▼",
                    "LOW VOL":     "◌",
                    "NO DATA":     "—",
                }
                _DIR_COLOR = {
                    "STRONG BUY":  "#22c55e",
                    "BUY":         "#00d4aa",
                    "HOLD":        "#94a3b8",
                    "NEUTRAL":     "#94a3b8",
                    "SELL":        "#f97316",
                    "STRONG SELL": "#ef4444",
                    "LOW VOL":     "#6b7280",
                    "NO DATA":     "#6b7280",
                }

                # ── Alignment indicator — count bullish / bearish / hold timeframes ─────
                _TF_ORDER  = ["1h", "4h", "1d", "1w"]
                _TF_PLAIN  = {"1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W"}
                _TF_FULL   = {"1h": "1 Hour", "4h": "4 Hours", "1d": "Daily", "1w": "Weekly"}
                _bull_tfs, _bear_tfs, _hold_tfs = [], [], []
                for _atf in _TF_ORDER:
                    _adir = tf_data.get(_atf, {}).get("direction", "NO DATA")
                    if "BUY" in _adir:    _bull_tfs.append(_TF_PLAIN[_atf])
                    elif "SELL" in _adir: _bear_tfs.append(_TF_PLAIN[_atf])
                    else:                 _hold_tfs.append(_TF_PLAIN[_atf])

                _n_bull = len(_bull_tfs); _n_bear = len(_bear_tfs); _n_tot = len(tf_data)
                if _n_bull >= 3:
                    _align_color = "#22c55e"
                    _align_text  = f"▲ {_n_bull} of {_n_tot} timeframes BULLISH ({', '.join(_bull_tfs)})"
                elif _n_bear >= 3:
                    _align_color = "#ef4444"
                    _align_text  = f"▼ {_n_bear} of {_n_tot} timeframes BEARISH ({', '.join(_bear_tfs)})"
                elif _n_bull > _n_bear:
                    _align_color = "#00d4aa"
                    _align_text  = f"▲ Leaning bullish — {_n_bull} buy, {_n_bear} sell" + (f" ({', '.join(_hold_tfs)} neutral)" if _hold_tfs else "")
                elif _n_bear > _n_bull:
                    _align_color = "#f97316"
                    _align_text  = f"▽ Leaning bearish — {_n_bear} sell, {_n_bull} buy"
                else:
                    _align_color = "#94a3b8"
                    _align_text  = f"■ Mixed signals — {_n_bull} buy, {_n_bear} sell, {len(_hold_tfs)} hold"

                # ── Section header row ────────────────────────────────────────────────
                _tf_head_col, _tf_info_col = st.columns([5, 1])
                with _tf_head_col:
                    st.markdown(
                        f'<div style="margin:8px 0 2px 0">'
                        f'<span style="font-weight:700;font-size:14px">⏱ Micro Trends — What Each Timeframe Says</span>'
                        f'</div>'
                        f'<div style="font-size:12px;color:{_align_color};font-weight:600;margin-bottom:6px">'
                        f'{_align_text}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _tf_info_col:
                    _ui.tf_column_guide_popover()

                # ── Beginner: simplified cards (shape + plain English only) ───────────
                if _user_lv == "beginner":
                    _beg_cols = st.columns(len(tf_data))
                    for _ci, (_btf, _btd) in enumerate(tf_data.items()):
                        _bdir  = _btd.get("direction", "NO DATA")
                        _bconf = _btd.get("confidence", 0)
                        _bshp  = _DIR_SHAPE.get(_bdir, "—")
                        _bclr  = _DIR_COLOR.get(_bdir, "#94a3b8")
                        _bno   = _bdir in ("NO DATA", "N/A", "LOW VOL")
                        _brsi  = _btd.get("rsi", None)
                        try:
                            _brsi_str = f"RSI {float(_brsi):.0f}" if _brsi is not None else ""
                        except (TypeError, ValueError):
                            _brsi_str = ""
                        _plain_action = {
                            "STRONG BUY": "Strong signal to buy",
                            "BUY": "Signal to buy",
                            "HOLD": "Hold — no action",
                            "NEUTRAL": "Hold — no action",
                            "SELL": "Signal to sell",
                            "STRONG SELL": "Strong signal to sell",
                            "LOW VOL": "Low volume — skip",
                            "NO DATA": "No data",
                        }.get(_bdir, _bdir)
                        with _beg_cols[_ci]:
                            st.markdown(
                                f'<div style="border:1px solid rgba(255,255,255,0.08);border-radius:10px;'
                                f'padding:12px 10px;text-align:center;background:rgba(255,255,255,0.03)">'
                                f'<div style="font-size:11px;color:#94a3b8;font-weight:600;'
                                f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px">'
                                f'{_TF_FULL.get(_btf, _btf)}</div>'
                                f'<div style="font-size:22px;font-weight:800;color:{_bclr};'
                                f'letter-spacing:0.02em;margin-bottom:4px">{_bshp}</div>'
                                f'<div style="font-size:12px;color:{_bclr};font-weight:700;'
                                f'margin-bottom:4px">{_bdir.replace("_", " ")}</div>'
                                f'<div style="font-size:11px;color:#64748b">'
                                f'{"—" if _bno else f"{_bconf:.0f}% confidence"}'
                                f'</div>'
                                f'<div style="font-size:10px;color:#475569;margin-top:2px">'
                                f'{_brsi_str}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                    # Plain-English alignment summary for beginners
                    st.markdown(
                        f'<div style="font-size:12px;color:#94a3b8;margin:8px 0 4px 0;'
                        f'padding:8px 12px;background:rgba(255,255,255,0.03);border-radius:8px;'
                        f'border-left:3px solid {_align_color}">'
                        f'<b>What does this mean?</b> Each box shows one time period — '
                        f'1 Hour is the shortest view (like today\'s weather), '
                        f'Weekly is the longest view (like the season). '
                        f'When most show ▲ BUY, the overall direction is bullish. '
                        f'When they disagree, wait for clarity before acting.'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                else:
                    # ── Intermediate + Advanced: full table with badges + confidence bars ─
                    _tf_rows = []
                    for tf in _TF_ORDER:
                        if tf not in tf_data:
                            continue
                        td = tf_data[tf]
                        _td_dir  = td.get("direction", "N/A")
                        _no_data = _td_dir in ("NO DATA", "N/A")
                        _td_conf = td.get("confidence", 0)
                        _td_shp  = _DIR_SHAPE.get(_td_dir, "—")
                        _rsi_raw = td.get("rsi", "N/A")
                        try:
                            _rsi_v = float(_rsi_raw)
                            if _rsi_v >= 70:   _rsi_str = f"🔥 Overheated ({_rsi_v:.0f})"
                            elif _rsi_v <= 30: _rsi_str = f"🧊 Very Cool ({_rsi_v:.0f})"
                            elif _rsi_v >= 55: _rsi_str = f"Warm ({_rsi_v:.0f})"
                            elif _rsi_v <= 45: _rsi_str = f"Cool ({_rsi_v:.0f})"
                            else:              _rsi_str = f"Neutral ({_rsi_v:.0f})"
                        except (ValueError, TypeError):
                            _rsi_str = str(_rsi_raw)

                        _row = {
                            "Timeframe":       _TF_FULL.get(tf, tf),
                            "Signal":          f"{_td_shp} {_td_dir}",
                            "Confidence":      "—" if _no_data else f"{_td_conf:.0f}%",
                            "Heat (RSI)":      _rsi_str,
                            "Trend (ADX)":     td.get("adx", "N/A"),
                            "Direction":       td.get("supertrend", "N/A"),
                            "Market Mode":     _ui.regime_label(td.get("regime", "")),
                        }
                        # Advanced: also show strategy bias
                        if _user_lv == "advanced":
                            _row["Strategy"] = _ui.bias_label(td.get("strategy_bias", ""))
                            _row["Agents"]   = f"{td.get('agent_vote', 'N/A')}"
                        _tf_rows.append(_row)

                    if _tf_rows:
                        _tf_df = pd.DataFrame(_tf_rows).set_index("Timeframe")
                        st.dataframe(_tf_df, width='stretch')

        # ── Liquidation Cascade Risk card (inside signal card) ───────────────────
        try:
            _casc = _cached_liquidation_cascade(pair)
            if _casc and not _casc.get("error"):
                st.markdown(
                    _ui.cascade_risk_card_html(
                        score      = _casc.get("score", 0),
                        risk_level = _casc.get("risk_level", "LOW"),
                        direction  = _casc.get("direction", "NEUTRAL"),
                        components = _casc.get("components"),
                    ),
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

        # ── News Sentiment ─────────────────────────────────────────────────────────
        if _news_mod is not None:
            try:
                _news = _cached_news_sentiment(pair)
                _nsig = _news.get("sentiment", "NEUTRAL")
                _nscore = _news.get("score", 0.0)
                _nsig_color = "🟢" if _nsig == "BULLISH" else "🔴" if _nsig == "BEARISH" else "⚪"
                with st.expander(f"📰 News Sentiment — {_nsig_color} {_nsig}", expanded=False):
                    _nc0, _nc1, _nc2, _nc3 = st.columns(4)
                    _nc0.metric("Sentiment", f"{_nsig_color} {_nsig}")
                    _nc1.metric("Score", f"{_nscore:+.2f}")
                    _nc2.metric("Bullish Headlines", _news.get("bullish", 0))
                    _nc3.metric("Bearish Headlines", _news.get("bearish", 0))
                    _theme = _news.get("key_theme", "")
                    if _theme:
                        st.caption(f"Key theme: {_theme}")
                    st.caption(f"Source: {_news.get('source','—')} · {_news.get('articles_analyzed',0)} articles analyzed")
            except Exception as _ne:
                logger.debug("[News] display error: %s", _ne)
                st.caption("News sentiment temporarily unavailable — try refreshing in 30 seconds.")

        # ── Whale Tracker ───────────────────────────────────────────────────────────
        if _whale_mod is not None:
            try:
                _whale = _cached_whale_activity(pair, float(price or 0))
                _wsig = _whale.get("signal", "NEUTRAL")
                if _wsig != "NEUTRAL" or _whale.get("whale_count", 0) > 0:
                    _wemoji = "🐋" if "ACCUMULATION" in _wsig else "🔴" if "DISTRIBUTION" in _wsig else "⚪"
                    with st.expander(f"{_wemoji} Whale Activity — {_wsig}", expanded=False):
                        _wc1, _wc2, _wc3, _wc4 = st.columns(4)
                        _wc1.metric("Signal", _wsig.replace("_", " ").title())
                        _wc2.metric("Whale Txns", _whale.get("whale_count", 0))
                        _wc3.metric("Large Whales", _whale.get("large_whale_count", 0))
                        _total_usd = _whale.get("total_usd", 0)
                        _wc4.metric("Total Volume", f"${_total_usd/1e6:.1f}M" if _total_usd >= 1e6 else f"${_total_usd:,.0f}")
            except Exception:
                pass

        # ── ML Price Prediction ─────────────────────────────────────────────────────
        # PERF-22: run get_enriched_df() in a background thread with 10s timeout so
        # TA computation (RSI/MACD/BB/Ichimoku/SuperTrend etc.) doesn't block the main render thread.
        if _ml_mod is not None:
            try:
                _ml_tf = model.TIMEFRAMES[0] if model.TIMEFRAMES else "1h"
                import concurrent.futures as _cf22
                with st.spinner("Calculating signals..."):
                    # CRITICAL: Do NOT use 'with ThreadPoolExecutor as ex' here.
                    # The context manager calls shutdown(wait=True) on exit, which
                    # blocks until get_enriched_df() finishes even after TimeoutError
                    # — causing the exact 60-second 503 health-check failures seen
                    # when switching pairs. Use shutdown(wait=False) in finally instead.
                    _ex22 = _cf22.ThreadPoolExecutor(max_workers=1)
                    try:
                        _ml_future = _ex22.submit(
                            model.get_enriched_df,
                            model.get_exchange_instance(model.TA_EXCHANGE),
                            pair,
                            _ml_tf,
                        )
                        try:
                            _ml_df = _ml_future.result(timeout=10)
                        except _cf22.TimeoutError:
                            _ml_df = None
                    finally:
                        _ex22.shutdown(wait=False)
                if _ml_df is not None and not _ml_df.empty:
                    _ml = _ml_mod.get_ml_prediction(pair, _ml_tf, _ml_df)
                    _ml_pred = _ml.get("prediction", "UNCERTAIN")
                    _ml_prob = _ml.get("probability", 0.5)
                    _ml_acc  = _ml.get("model_accuracy", 0.0)
                    _ml_sig  = _ml.get("signal", "NEUTRAL")
                    _ml_col  = "#00d4aa" if _ml_sig == "BUY" else "#ff4b4b" if _ml_sig == "SELL" else "#f59e0b"
                    _ml_emoji = "📈" if _ml_sig == "BUY" else ("📉" if _ml_sig == "SELL" else "😐")
                    _ml_plain = (
                        "The AI thinks the price will go UP in the next few hours."
                        if _ml_sig == "BUY" else
                        "The AI thinks the price will go DOWN in the next few hours."
                        if _ml_sig == "SELL" else
                        "The AI isn't sure which way the price will go."
                    )
                    st.markdown(
                        f'<div style="background:rgba(26,31,46,0.8);border-radius:10px;'
                        f'padding:12px 16px;margin:8px 0;border-left:3px solid {_ml_col};">'
                        f'<div style="font-size:13px;font-weight:700;color:#e8ecf4;margin-bottom:4px;">'
                        f'{_ml_emoji} AI Price Prediction — Next Few Hours</div>'
                        f'<div style="font-size:12px;color:#a8b4c8;">{_ml_plain}</div>'
                        f'<div style="font-size:11px;color:rgba(168,180,200,0.5);margin-top:6px;">'
                        f'Confidence: <span style="color:{_ml_col};font-weight:700;">{_ml_prob:.0%}</span>'
                        f' &nbsp;·&nbsp; Model accuracy: {_ml_acc:.0%}'
                        f' &nbsp;·&nbsp; <span style="color:{_ml_col};">{_ml_pred}</span></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # ── #48 HMM Regime — displayed alongside existing macro regime ────────
                    try:
                        if pair == "BTC/USDT" and not _ml_df.empty and "close" in _ml_df.columns:
                            _hmm_prices = list(_ml_df["close"].dropna().tail(400))
                            _hmm_res    = _ml_mod.fit_hmm_regime(_hmm_prices)
                            _hmm_state  = _hmm_res.get("current_state", "UNKNOWN")
                            _hmm_conf   = _hmm_res.get("confidence", 0.0)
                            _hmm_probs  = _hmm_res.get("state_probabilities", [0.0, 0.0, 0.0])
                            if _hmm_state != "UNKNOWN" and not _hmm_res.get("error"):
                                _hmm_col = (
                                    "#00d4aa" if _hmm_state == "Bull" else
                                    "#ef4444" if _hmm_state == "Bear" else
                                    "#f59e0b"
                                )
                                # Build state-probability mini-bar chart labels
                                _labels = ["Bear", "Neutral", "Bull"]
                                _bar_parts = ""
                                for _lbl, _pb in zip(_labels, _hmm_probs):
                                    _bw = int(round(_pb * 100))
                                    _bc = "#00d4aa" if _lbl == "Bull" else "#ef4444" if _lbl == "Bear" else "#f59e0b"
                                    _bar_parts += (
                                        f'<div style="margin-bottom:3px">'
                                        f'<div style="display:flex;align-items:center;gap:6px">'
                                        f'<span style="font-size:10px;color:#9ca3af;width:44px">{_lbl}</span>'
                                        f'<div style="flex:1;background:#1f2937;border-radius:3px;height:6px">'
                                        f'<div style="background:{_bc};width:{_bw}%;height:6px;border-radius:3px"></div>'
                                        f'</div>'
                                        f'<span style="font-size:10px;color:#9ca3af;width:32px;text-align:right">{_pb:.0%}</span>'
                                        f'</div></div>'
                                    )
                                st.markdown(
                                    f'<div style="background:rgba(26,31,46,0.8);border-radius:10px;'
                                    f'padding:12px 16px;margin:8px 0;border-left:3px solid {_hmm_col};">'
                                    f'<div style="font-size:13px;font-weight:700;color:#e8ecf4;margin-bottom:6px;">'
                                    f'🧬 HMM Regime — Current State: '
                                    f'<span style="color:{_hmm_col}">{_hmm_state}</span>'
                                    f' ({_hmm_conf:.0%} confidence)</div>'
                                    f'{_bar_parts}'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                    except Exception:
                        pass
            except Exception:
                pass

        # ── #61 Signal Story — 1-2 plain English sentences below the signal card ──
        if _llm is not None:
            try:
                _story_indicators = {}
                _story_tf_data = r.get("timeframes", {})
                _story_first_td = (list(_story_tf_data.values()) or [{}])[0]
                _story_indicators["rsi"]             = _story_first_td.get("rsi")
                _story_indicators["adx"]             = _story_first_td.get("adx")
                _story_indicators["macd_div"]        = _story_first_td.get("macd_div")
                _story_indicators["supertrend"]      = _story_first_td.get("supertrend")
                _story_indicators["regime"]          = _story_first_td.get("regime", "")
                _story_indicators["funding_rate_pct"] = (
                    r.get("funding_rate_pct") or
                    (r.get("timeframes", {}).get("1h", {}) or {}).get("funding", "")
                )
                _story_text = _llm.generate_signal_story(pair, direction, conf, _story_indicators)
                if _story_text:
                    _story_sig_col = (
                        "#00d4aa" if "BUY" in direction.upper() else
                        "#ef4444" if "SELL" in direction.upper() else
                        "#f59e0b"
                    )
                    st.markdown(
                        f'<div style="background:rgba(17,24,39,0.7);border-radius:8px;'
                        f'padding:10px 14px;margin:4px 0 10px 0;border-left:2px solid {_story_sig_col};">'
                        f'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;'
                        f'letter-spacing:0.6px;margin-bottom:4px">Signal Story</div>'
                        f'<div style="font-size:13px;color:#c8d4e8;line-height:1.5">{_html.escape(str(_story_text))}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            except Exception:
                pass

        # APP-30: sanitise pair for widget keys — '/' in key crashes Streamlit's
        # session-state serialiser (_check_serializable KeyError on FLR/USDT etc.)
        _pk = pair.replace("/", "_")

        # APP-31: reset advanced-order limit price default when selected coin changes
        # Prevents stale price from prior coin showing in the iceberg limit-price input.
        # Also eliminates orphaned $$ID- widget tracking keys (Streamlit 1.56 bug) that
        # caused repeated KeyError crashes in _check_serializable when pair changed.
        if st.session_state.get("_adv_last_pair") != pair:
            for _stale in ("adv_ice_lim", "adv_twap_dir", "adv_ice_dir"):
                st.session_state.pop(_stale, None)
            st.session_state["_adv_last_pair"] = pair

        # ── AI Analysis — st.dialog renders in modal overlay, outside page diff cycle ──
        ai_key = f"ai_explanation_{pair}"

        @st.dialog(f"AI Analysis — {pair}", width="large")
        def _show_ai_dialog():
            if _llm is None:
                st.warning("LLM analysis module not available — check llm_analysis.py installation.")
                return
            cached = st.session_state.get(ai_key)
            if cached:
                st.info(cached)
            else:
                with st.spinner("Asking Claude...", show_time=True):
                    explanation = _llm.get_signal_explanation(pair, r)
                st.session_state[ai_key] = explanation
                st.info(explanation)

        if st.button("🤖 AI Analysis", key=f"btn_ai_{_pk}", width="stretch"):
            _show_ai_dialog()

        # ── Order Execution ────────────────────────────────────────────────────────
        st.markdown("---")
        _ui.risk_disclaimer_banner()
        if not _exec_status.get("ccxt_available", False):
            st.caption("ccxt not installed — run: pip install ccxt")
        else:
            _mode_label = "🔴 LIVE" if _exec_cfg.get("live_trading", False) else "📄 Paper"
            _cur_price  = (_ws.get_price(pair) or {}).get("price") or price
            _exec_size  = (float(pos_pct or 10) / 100) * float(
                getattr(model, "PORTFOLIO_SIZE_USD", 10000)
            )
            ex_c0, ex_c1, ex_c2, ex_c3 = st.columns([2, 2, 2, 2])
            with ex_c0:
                st.caption(f"Mode: {_mode_label}")
                st.caption(f"Order size: ${_exec_size:,.0f}")
            with ex_c1:
                if st.button(f"▲ BUY {pair.split('/')[0]}", key=f"exec_buy_{_pk}",
                             type="primary" if "BUY" in direction else "secondary",
                             width="stretch"):
                    _res = _exec.place_order(pair, "BUY", _exec_size, current_price=_cur_price)
                    if _res["ok"]:
                        st.success(f"{'PAPER' if _res['mode']=='paper' else 'LIVE'} BUY placed — ID: {_res['order_id']}")
                    else:
                        logger.warning("[Execution] BUY order failed for %s: %s", pair, _res['error'])
                        st.error("Order failed — check your API keys and connection, then try again.")
            with ex_c2:
                if st.button(f"▼ SELL {pair.split('/')[0]}", key=f"exec_sell_{_pk}",
                             type="primary" if "SELL" in direction else "secondary",
                             width="stretch"):
                    _res = _exec.place_order(pair, "SELL", _exec_size, current_price=_cur_price)
                    if _res["ok"]:
                        st.success(f"{'PAPER' if _res['mode']=='paper' else 'LIVE'} SELL placed — ID: {_res['order_id']}")
                    else:
                        logger.warning("[Execution] SELL order failed for %s: %s", pair, _res['error'])
                        st.error("Order failed — check your API keys and connection, then try again.")
            with ex_c3:
                _open_pos = _db.load_positions()
                if pair in _open_pos:
                    _pos_dir = _open_pos[pair].get("direction", "BUY")
                    if st.button(f"✕ Close {pair.split('/')[0]}", key=f"exec_close_{_pk}",
                                 width="stretch"):
                        _res = _exec.close_position(pair, _pos_dir, _exec_size, current_price=_cur_price)
                        if _res["ok"]:
                            st.success(f"Position closed — ID: {_res['order_id']}")
                        else:
                            logger.warning("[Execution] Close position failed for %s: %s", pair, _res['error'])
                            st.error("Close failed — check your API keys and connection, then try again.")
                else:
                    st.caption("No open position")

            # ── Advanced Order Types (T3-9/T3-10) ────────────────────────────────
            with st.expander("⚙ Advanced Orders", expanded=False):
                _adv_c1, _adv_c2 = st.columns(2)
                with _adv_c1:
                    st.caption("**TWAP** — split into equal time slices")
                    _twap_dir  = st.selectbox("Direction", ["BUY", "SELL"], key="adv_twap_dir")
                    _twap_slices = st.number_input("Slices", 2, 20, 5, key="adv_twap_slices")
                    _twap_interval = st.number_input("Interval (sec)", 10, 3600, 60, key="adv_twap_int")
                    if st.button(f"▶ TWAP {pair.split('/')[0]}", key="adv_twap_btn", width="stretch"):
                        _tr = _exec.place_twap_order(
                            pair, _twap_dir, _exec_size,
                            n_slices=int(_twap_slices),
                            interval_seconds=int(_twap_interval),
                            current_price=_cur_price,
                            expected_price=r.get("entry"),
                        )
                        if _tr.get("ok"):  # APP-24: mirror iceberg pattern — check ok before accessing keys
                            st.success(f"TWAP started — ID: {_tr['twap_id']} ({_twap_slices} slices)")
                        else:
                            logger.warning("[Execution] TWAP failed for %s: %s", pair, _tr.get('error'))
                            st.error("TWAP order failed — check your API keys and connection, then try again.")
                with _adv_c2:
                    st.caption("**Iceberg** — hide order size in OB")
                    _ice_dir  = st.selectbox("Direction", ["BUY", "SELL"], key="adv_ice_dir")
                    _ice_vis  = st.slider("Visible %", 10, 50, 20, step=5, key="adv_ice_vis") / 100.0
                    _ice_limit = st.number_input("Limit Price (0=market)", 0.0, 1e9,
                                                 float(r.get("entry") or 0), step=0.01, format="%.4f",
                                                 key="adv_ice_lim")
                    if st.button(f"🧊 Iceberg {pair.split('/')[0]}", key="adv_ice_btn", width="stretch"):
                        _ir = _exec.place_iceberg_order(
                            pair, _ice_dir, _exec_size,
                            visible_pct=_ice_vis,
                            current_price=_cur_price,
                            limit_price=_ice_limit if _ice_limit > 0 else None,
                            expected_price=r.get("entry"),
                        )
                        if _ir["ok"]:
                            st.success(f"Iceberg placed — ID: {_ir['order_id']}")
                        else:
                            logger.warning("[Execution] Iceberg failed for %s: %s", pair, _ir['error'])
                            st.error("Iceberg order failed — check your API keys and connection, then try again.")

        # ── Confidence History (Pro Mode only) ─────────────────────────────────
        if not st.session_state.get("beginner_mode", True):
            try:
                _ch_history = _cached_confidence_history(pair, days=30)
                if _ch_history:
                    _ch_ts    = [h["timestamp"] for h in _ch_history]
                    _ch_conf  = [h["confidence"] for h in _ch_history]
                    _ch_sigs  = [h["signal"] for h in _ch_history]
                    _ch_colors = [
                        "#00C853" if s == "BUY" else "#D50000" if s == "SELL" else "#9E9E9E"
                        for s in _ch_sigs
                    ]
                    _ch_fig = go.Figure()
                    _ch_fig.add_trace(go.Scatter(
                        x=_ch_ts,
                        y=_ch_conf,
                        mode="lines+markers",
                        name="Confidence %",
                        line=dict(color="#818cf8", width=1.5),
                        marker=dict(color=_ch_colors, size=6),
                        hovertemplate="%{x}<br>Confidence: %{y:.1f}%<extra></extra>",
                    ))
                    _ch_fig.update_layout(
                        height=160,
                        margin=dict(l=0, r=0, t=24, b=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        title=dict(
                            text=f"Confidence History — {pair} (last 30 days)  "
                                 '<span style="color:#00C853">● BUY</span> '
                                 '<span style="color:#D50000">● SELL</span> '
                                 '<span style="color:#9E9E9E">● HOLD</span>',
                            font=dict(size=11),
                            x=0,
                        ),
                        yaxis=dict(
                            range=[0, 100],
                            ticksuffix="%",
                            gridcolor="#222",
                            tickfont=dict(size=9),
                        ),
                        xaxis=dict(gridcolor="#222", tickfont=dict(size=9)),
                        showlegend=False,
                    )
                    st.plotly_chart(_ch_fig, width='stretch', key=f"conf_hist_{_pk}")
            except Exception:
                pass

        st.markdown("---")

        # ── Live Chart ──────────────────────────────────────────────────────────
        _ui.section_header("Live Chart", "Candlestick chart with entry / target / stop overlays", icon="📈")
        ch_c1, ch_c2, ch_c3 = st.columns([3, 2, 2])
        with ch_c1:
            # Merge scan results (first, so last-scanned pairs appear at top) with
            # the full static universe — always chartable regardless of scan state.
            _scan_pairs = [r["pair"] for r in sorted_results]
            _extra_pairs = [
                p for p in (
                    model.PAIRS
                    + ['WFLR/USDT', 'FXRP/USDT']   # chart-only pairs (not in scan)
                )
                if p not in _scan_pairs
            ]
            chart_pair_opts = _scan_pairs + sorted(_extra_pairs)
            chart_pair = st.selectbox("Pair", chart_pair_opts, key="chart_pair_select")
        with ch_c2:
            _default_tf_idx = (
                model.TIMEFRAMES.index("1h") if "1h" in model.TIMEFRAMES else 0
            )
            chart_tf = st.selectbox(
                "Timeframe", model.TIMEFRAMES, index=_default_tf_idx, key="chart_tf_select"
            )
        with ch_c3:
            st.write("")
            load_chart = st.button(
                "Load Chart", type="primary", width="stretch", key="btn_load_chart"
            )

        if load_chart:
            try:
                with st.spinner(f"Fetching {chart_pair} {chart_tf}...", show_time=True):
                    ohlcv = model.fetch_chart_ohlcv(chart_pair, chart_tf, limit=250)
                if ohlcv:
                    r_sel = next((r for r in results if r["pair"] == chart_pair), {})
                    st.session_state["chart_html"] = _chart.build_chart_html(
                        ohlcv, chart_pair, chart_tf,
                        entry=r_sel.get("entry"),
                        stop=r_sel.get("stop_loss"),
                        target=r_sel.get("exit"),
                    )
                    st.session_state["chart_pair_label"] = f"{chart_pair} · {chart_tf}"
                else:
                    st.warning(
                        f"No chart data available for **{chart_pair}** on {chart_tf}. "
                        "This pair may have very low liquidity on all exchanges. "
                        "Try a different timeframe or pair."
                    )
            except Exception as e:
                logging.warning("[chart] %s %s: %s", chart_pair, chart_tf, e)
                st.warning(
                    f"Chart data couldn't load for **{chart_pair}** right now — "
                    "this is usually temporary. Try refreshing in 30 seconds."
                )

        _chart_html = st.session_state.get("chart_html")
        if _chart_html:
            _chart_label = st.session_state.get("chart_pair_label", "")
            if _chart_label:
                st.caption(
                    f"Showing: **{_chart_label}** — teal = entry, blue = target, red = stop (from last scan)"
                )
            st.iframe(_chart_html, height=560)

        st.markdown("---")

        # Export buttons
        if results:
            col_csv, col_json, col_pdf = st.columns(3)
            with col_csv:
                st.download_button(
                    "📥 Export CSV",
                    data=_export_scan_results(results, "csv"),
                    file_name=f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    width="stretch",
                    key="dl_scan_csv",
                )
            with col_json:
                st.download_button(
                    "📥 Export JSON",
                    data=_export_scan_results(results, "json"),
                    file_name=f"scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    width="stretch",
                    key="dl_scan_json",
                )
            with col_pdf:
                ts_str = st.session_state.get("scan_timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Cache PDF — only regenerate when scan_timestamp changes (not on every auto-refresh tick)
                try:  # APP-08: catch generate_scan_pdf failure; never pass None to st.download_button
                    if _pdf is None:
                        raise ImportError("pdf_export module not available")
                    if st.session_state.get("_scan_pdf_ts") != ts_str:
                        st.session_state["_scan_pdf_bytes"] = _pdf.generate_scan_pdf(results, scan_timestamp=ts_str)
                        st.session_state["_scan_pdf_ts"] = ts_str
                    _pdf_data = st.session_state.get("_scan_pdf_bytes")
                    if _pdf_data:
                        st.download_button(
                            "⬇ Download PDF",
                            data=_pdf_data,
                            file_name=f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            width="stretch",
                            key="dl_scan_pdf",
                        )
                    else:
                        st.caption("PDF unavailable")
                except Exception as _pdf_err:
                    logger.warning("[App] PDF generation failed: %s", _pdf_err)
                    st.caption("PDF generation failed — please try again.")


    with _dash_tab5:
        _analysis_lv = st.session_state.get("user_level", "beginner")
        if _analysis_lv == "beginner":
            st.markdown(
                '<div style="background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);'
                'border-radius:12px;padding:28px 24px;text-align:center;margin:20px 0">'
                '<div style="font-size:32px;margin-bottom:10px">\U0001f52c</div>'
                '<div style="font-size:18px;font-weight:700;color:#e8ecf4;margin-bottom:8px">'
                'Advanced Analysis Tools</div>'
                '<div style="font-size:13px;color:#9ca3af;line-height:1.6;max-width:380px;margin:0 auto">'
                'Correlation matrix, volatility rankings, and pair trade scanner are available at '
                '<strong style="color:#818cf8">Intermediate</strong> or '
                '<strong style="color:#a78bfa">Advanced</strong> level.<br><br>'
                'Switch your experience level in the sidebar to unlock these tools.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            with st.expander("📊 Market Analysis Tools — Correlation · Volatility · Pair Trades", expanded=False):
                st.caption(
                    "Correlation: which assets move together (diversification guide). "
                    "Vol Rankings: 7-day realized volatility. "
                    "Pair Trading: cointegrated pairs with z-score signals."
                )

                # ── Correlation Matrix ──
                _ui.section_header("Asset Correlation Matrix",
                                   "Pairwise Pearson correlation of daily returns — Red = strong positive · Blue = negative",
                                   icon="🔥")

                col_lk, col_tf, col_run = st.columns([2, 2, 2])
                with col_lk:
                    lookback = st.slider("Lookback (days)", min_value=7, max_value=90,
                                         value=30, step=7, key="corr_lookback")
                with col_tf:
                    corr_tf = st.selectbox("Timeframe", ["1d", "4h", "1h"], index=0, key="corr_tf")
                with col_run:
                    st.write("")
                    run_corr = st.button("Compute Correlation", type="primary", width="stretch", key="run_corr")

                if run_corr:
                    with st.spinner("Fetching OHLCV data...", show_time=True):
                        corr_matrix, err = model.compute_correlation_matrix(
                            pairs=model.PAIRS, lookback_days=lookback, tf=corr_tf
                        )
                    if err:
                        logger.warning("[app] correlation fetch error: %s", err)
                        st.error("Correlation data unavailable — could not fetch price data. Try again in a moment.")
                        st.session_state["corr_matrix_data"] = None
                        st.session_state["corr_error"] = err
                    else:
                        # PERF: store DataFrame directly — was .to_dict() + pd.DataFrame() round-trip on every render
                        st.session_state["corr_matrix_data"] = corr_matrix
                        st.session_state["corr_error"] = None

                cached = st.session_state.get("corr_matrix_data")
                if cached is not None:
                    corr_df = cached
                    pairs_list = list(corr_df.columns)

                    fig_corr = go.Figure(data=go.Heatmap(
                        z=corr_df.values,
                        x=corr_df.columns.tolist(),
                        y=corr_df.index.tolist(),
                        colorscale="RdBu_r",
                        zmin=-1, zmax=1,
                        text=[[f"{v:.2f}" for v in row] for row in corr_df.values],
                        texttemplate="%{text}",
                        hoverongaps=False,
                    ))
                    fig_corr.update_layout(
                        height=450,
                        margin=dict(l=0, r=0, t=10, b=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig_corr, width='stretch',
                                    config={"displayModeBar": False, "staticPlot": True})

                    # Highlight high-correlation pairs — PERF: NumPy upper-triangle mask (was O(N²) nested loop)
                    st.markdown("**Highly correlated pairs** (|corr| > 0.75):")
                    _corr_arr = corr_df.values
                    _rows_idx, _cols_idx = np.where(
                        (np.abs(np.triu(_corr_arr, k=1)) > 0.75)
                    )
                    high_corr_rows = []
                    try:
                        high_corr_rows = [
                            {"Pair A": pairs_list[i], "Pair B": pairs_list[j], "Correlation": round(_corr_arr[i, j], 3)}
                            for i, j in zip(_rows_idx, _cols_idx)
                        ]
                    except Exception:
                        pass
                    if high_corr_rows:
                        st.dataframe(pd.DataFrame(high_corr_rows), width='stretch', hide_index=True)
                    else:
                        st.info("No pairs exceed the 0.75 correlation threshold for this period.")
                elif st.session_state.get("corr_error"):
                    st.error("Correlation data unavailable — could not fetch price data. Try again in a moment.")


                st.markdown("---")

                # ── Realized Volatility Rankings (Phase 11) ───────────────────────────────
                _ui.section_header(
                    "Realized Volatility Rankings",
                    "7-day annualized realized volatility across all pairs — rank from calmest to most explosive",
                    icon="📉",
                )
                st.caption("Load 7-day daily closes from the exchange to compute annualized realized vol. Updates on each run.")

                if st.button("Compute Vol Rankings", key="run_vol_rank", type="primary"):
                    import statistics as _stat
                    with st.spinner("Fetching 7-day OHLCV data for all pairs…", show_time=True):
                        _vol_rows = []
                        _first_err = None
                        _exchange = model.get_exchange_instance(model.TA_EXCHANGE)
                        if _exchange:
                            for _vp in model.PAIRS:
                                try:
                                    _df_ohlcv = model.robust_fetch_ohlcv(_exchange, _vp, "1d", limit=9)
                                    if len(_df_ohlcv) >= 3:
                                        _cls = [v for v in _df_ohlcv["close"].tolist() if v and v > 0]
                                        _rets = [
                                            (_cls[i] - _cls[i - 1]) / _cls[i - 1]
                                            for i in range(1, len(_cls))
                                            if _cls[i - 1] > 0
                                        ]
                                        if len(_rets) >= 2:
                                            _daily_vol = _stat.stdev(_rets)
                                            _ann_vol   = round(_daily_vol * (252 ** 0.5) * 100, 1)
                                            _sector    = model.SECTOR_MAP.get(_vp, "other")
                                            _vol_rows.append({
                                                "Asset":    _vp.replace("/USDT", ""),
                                                "Sector":   _sector.replace("_", " ").title(),
                                                "Ann. Vol%": _ann_vol,
                                                "7d Close": round(_cls[-1], 4),
                                            })
                                except Exception as _e:
                                    if _first_err is None:
                                        _first_err = str(_e)[:100]
                        else:
                            _first_err = "Exchange unavailable"
                        st.session_state["vol_rank_data"] = _vol_rows
                        st.session_state["vol_rank_err"]  = _first_err

                _vol_data = st.session_state.get("vol_rank_data")
                if _vol_data:
                    _vol_df = pd.DataFrame(_vol_data).sort_values("Ann. Vol%", ascending=False).reset_index(drop=True)

                    # Rank chips — color by volatility tier
                    _chips_vol = ""
                    _vmax = _vol_df["Ann. Vol%"].max() if not _vol_df.empty else 1
                    for _, _vr in _vol_df.iterrows():
                        _v = _vr["Ann. Vol%"]
                        _pct = _v / max(_vmax, 1)
                        _vc = "#f6465d" if _pct > 0.7 else ("#f59e0b" if _pct > 0.4 else "#00d4aa")
                        _chips_vol += (
                            f'<span style="display:inline-flex;flex-direction:column;align-items:center;'
                            f'padding:5px 9px;border-radius:8px;background:{_vc}18;'
                            f'border:1px solid {_vc}50;margin:2px;min-width:52px">'
                            f'<span style="font-size:11px;font-weight:700;color:#e2e8f0">{_vr["Asset"]}</span>'
                            f'<span style="font-size:10px;color:{_vc};font-weight:600">{_v:.0f}%</span>'
                            f'</span>'
                        )
                    st.markdown(
                        f'<div style="display:flex;flex-wrap:wrap;gap:2px;margin:8px 0">{_chips_vol}</div>',
                        unsafe_allow_html=True,
                    )
                    st.caption("🔴 High vol (>70th pct) · 🟡 Medium · 🟢 Low — annualized, based on 7-day daily returns")

                    with st.expander("Full volatility table"):
                        st.dataframe(
                            _vol_df,
                            width='stretch', hide_index=True,
                            column_config={
                                "Ann. Vol%": st.column_config.NumberColumn(format="%.1f%%"),
                                "7d Close":  st.column_config.NumberColumn(format="$%.4f"),
                            },
                        )
                elif _vol_data is not None and len(_vol_data) == 0:
                    _vol_err = st.session_state.get("vol_rank_err")
                    logger.warning("[App] volatility data failed: %s", _vol_err)
                    st.warning("No volatility data returned — check exchange connectivity and try again.")


                st.markdown("---")

                # ── Pair Trade Scanner (Cointegration) ───────────────────────────────────
                _ui.section_header(
                    "Pair Trade Scanner",
                    "Finds cryptocurrency pairs that move together — then signals when one is unusually cheap or expensive vs the other",
                    icon="⚖️",
                )
                st.caption(
                    "A pair trade buys the underpriced coin and sells the overpriced one, profiting when prices converge. "
                    "Only pairs with a statistically significant relationship (p < 0.05) are shown."
                )

                _coint_col1, _coint_col2, _coint_col3 = st.columns([2, 2, 2])
                with _coint_col1:
                    _coint_tf = st.selectbox("Timeframe", ["1d", "4h", "1h"], index=0, key="coint_tf")
                with _coint_col2:
                    _coint_lb = st.slider("Lookback (bars)", min_value=60, max_value=200, value=100, step=10, key="coint_lb")
                with _coint_col3:
                    st.write("")
                    _run_coint = st.button("Scan for Pair Trades", type="primary", width="stretch", key="run_coint")

                if _run_coint:
                    with st.spinner(f"Testing {len(model.PAIRS) * (len(model.PAIRS) - 1) // 2} pair combinations...", show_time=True):
                        _coint_results, _coint_err = model.run_cointegration_scan(
                            pairs=model.PAIRS, tf=_coint_tf, lookback=_coint_lb
                        )
                    if _coint_err:
                        logger.warning("[App] cointegration scan error: %s", _coint_err)
                        st.error("Scan encountered an issue — try again or reduce the number of pairs.")
                        st.session_state["coint_results"] = None
                    else:
                        st.session_state["coint_results"] = _coint_results
                        st.session_state["coint_err"] = None

                _coint_data = st.session_state.get("coint_results")
                if _coint_data is not None:
                    if not _coint_data:
                        st.info("No cointegrated pairs found — try a longer lookback or different timeframe.")
                    else:
                        # Signal color map
                        _COINT_COLORS = {
                            "LONG_SPREAD":  "#00d4aa",
                            "SHORT_SPREAD": "#f6465d",
                            "EXIT_SPREAD":  "#f59e0b",
                            "NEUTRAL":      "#64748b",
                        }

                        # Summary banner
                        _actionable = [r for r in _coint_data if r["signal"] not in ("NEUTRAL", "EXIT_SPREAD")]
                        if _actionable:
                            st.success(
                                f"⚖️ **{len(_actionable)} actionable pair trade{'s' if len(_actionable) != 1 else ''}** found "
                                f"out of {len(_coint_data)} cointegrated pairs."
                            )

                        # Render cards for top pairs
                        for _cr in _coint_data[:12]:
                            _sig_color = _COINT_COLORS.get(_cr["signal"], "#64748b")
                            _z         = _cr["zscore"]
                            _z_bar_pct = min(abs(_z) / 3.0 * 100, 100)

                            # Plain English signal label
                            _sig_labels = {
                                "LONG_SPREAD":  "BUY SPREAD",
                                "SHORT_SPREAD": "SELL SPREAD",
                                "EXIT_SPREAD":  "CLOSE POSITION",
                                "NEUTRAL":      "NEUTRAL",
                            }
                            _sig_label = _sig_labels.get(_cr["signal"], _cr["signal"])

                            st.markdown(
                                f"""
                                <div style="
                                    background:linear-gradient(rgba(14,18,30,0.8),rgba(14,18,30,0.8)) padding-box,
                                               linear-gradient(135deg,{_sig_color}30,rgba(99,102,241,0.15)) border-box;
                                    border:1px solid transparent;border-radius:12px;
                                    padding:14px 18px;margin-bottom:8px;
                                    backdrop-filter:blur(12px)">
                                    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
                                        <div>
                                            <span style="font-size:15px;font-weight:800;color:#e8ecf4;
                                                         font-family:'JetBrains Mono',monospace">
                                                {_cr['pair_a'].replace('/USDT','')} / {_cr['pair_b'].replace('/USDT','')}
                                            </span>
                                            <span style="font-size:11px;color:rgba(168,180,200,0.5);margin-left:10px">
                                                hedge ratio {_cr['hedge_ratio']:.4f} · p={_cr['pvalue']:.4f}
                                            </span>
                                        </div>
                                        <span style="background:{_sig_color};color:#06101c;padding:4px 13px;
                                                     border-radius:999px;font-size:11px;font-weight:800;
                                                     letter-spacing:0.5px">{_sig_label}</span>
                                    </div>
                                    <div style="margin:10px 0 6px">
                                        <div style="display:flex;justify-content:space-between;
                                                    font-size:11px;color:rgba(168,180,200,0.5);margin-bottom:4px">
                                            <span>Z-Score: <strong style="color:{_sig_color}">{_z:+.2f}</strong></span>
                                            <span>±2σ threshold</span>
                                        </div>
                                        <div style="background:rgba(255,255,255,0.06);border-radius:4px;height:6px;position:relative">
                                            <div style="
                                                position:absolute;
                                                {'left:50%;' if _z >= 0 else f'right:{50}%;'}
                                                width:{_z_bar_pct/2:.1f}%;
                                                height:6px;border-radius:4px;
                                                background:{_sig_color};
                                                transition:width 0.4s ease"></div>
                                            <div style="position:absolute;left:50%;top:-2px;
                                                        width:1px;height:10px;background:rgba(255,255,255,0.25)"></div>
                                        </div>
                                    </div>
                                    <div style="font-size:12px;color:#c4cedd;line-height:1.5;
                                                border-left:3px solid {_sig_color};padding-left:10px;margin-top:8px">
                                        {_cr['signal_plain']}
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                        if len(_coint_data) > 12:
                            st.caption(f"Showing top 12 of {len(_coint_data)} cointegrated pairs ranked by |z-score|.")




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
    """Send Telegram / email / Discord alerts for each closed paper position.

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
        # Telegram
        if cfg.get("telegram_enabled"):
            try:
                _alerts.send_telegram(
                    cfg.get("telegram_token", ""),
                    cfg.get("telegram_chat_id", ""),
                    _msg,
                )
            except Exception as _e:
                logging.warning("[ExitAlert] Telegram failed: %s", _e)
        # Email
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
        # Discord
        if cfg.get("discord_enabled"):
            try:
                _alerts.send_discord(
                    cfg.get("discord_webhook_url", ""),
                    _msg,
                )
            except Exception as _e:
                logging.warning("[ExitAlert] Discord failed: %s", _e)


def _run_scan_thread():
    """Background scan thread — writes results to JSON file (survives Streamlit reloads)."""
    with _scan_lock:
        _scan_state["running"] = True
        _scan_state["progress"] = 0
        _scan_state["progress_pair"] = f"Connecting to {model.TA_EXCHANGE.upper()}..."
    # PERF-30: update in-memory status on scan start
    _SCAN_STATUS["running"]  = True
    _SCAN_STATUS["progress"] = 0
    _SCAN_STATUS["current"]  = f"Connecting to {model.TA_EXCHANGE.upper()}..."
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
            logging.warning(f"Feedback loop error: {_fb_err}")
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
            _alerts.send_scan_alerts(results, cfg)
        except Exception as _e:
            logging.warning("[App] Telegram alert failed: %s", _e)
        try:
            _alerts.send_scan_email_alerts(results, cfg)
        except Exception as _e:
            logging.warning("[App] Email alert failed: %s", _e)
        try:
            _alerts.send_scan_discord_alerts(results, cfg)
        except Exception as _e:
            logging.warning("[App] Discord alert failed: %s", _e)
        try:
            _alerts.check_watchlist_alerts(results, cfg)
        except Exception as _e:
            logging.warning("[App] Watchlist alert check failed: %s", _e)
    except Exception as e:
        audit("scan_error", error=str(e))
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
    except Exception:
        pass
    t = threading.Thread(target=_run_scan_thread, daemon=True)
    t.start()

# ──────────────────────────────────────────────
# PAGE 2: CONFIG EDITOR
# ──────────────────────────────────────────────
def page_config():
    _cfg_lv = st.session_state.get("user_level", "beginner")
    _cfg_title = "⚙️ Settings" if _cfg_lv in ("beginner", "intermediate") else "⚙️ Config Editor"
    st.markdown(
        f'<h1 style="color:#e8ecf1;font-size:26px;font-weight:700;'
        f'letter-spacing:-0.5px;margin-bottom:0">{_cfg_title}</h1>',
        unsafe_allow_html=True,
    )
    st.caption("Changes are saved to config_overrides.json and applied on next scan.")

    # ── Item 14: Beginner simplified settings — 3 controls only ──────────────
    if _cfg_lv == "beginner":
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

        with st.expander("🔧 Advanced Settings (for experienced users)", expanded=False):
            st.info("These are technical settings. Leave them as-is unless you know what you're doing.")
        return  # beginners only see the 3-control view above

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

    # ── Auto-jump to Alerts tab when navigated from sidebar
    _cfg_initial_tab = 0
    _st_tab_override = st.session_state.pop("_settings_tab", None)
    _cfg_tab_names = ["📊 Trading", "⚡ Signal & Risk", "🔔 Alerts", "🛠️ Dev Tools", "⚙️ Execution"]
    if _st_tab_override and _st_tab_override in _cfg_tab_names:
        _cfg_initial_tab = _cfg_tab_names.index(_st_tab_override)

    _cfg_t1, _cfg_t2, _cfg_t3, _cfg_t4, _cfg_t5 = st.tabs(_cfg_tab_names)

    # ── ALERTS TAB content definition (full config moved from sidebar)
    def _render_alerts_tab():
        """Full alert configuration — Telegram, Email, Discord."""
        _at_cfg = _cached_alerts_config()

        with st.expander("🔔 Telegram Alerts", expanded=_at_cfg.get("telegram_enabled", False)):
            _at_cfg2 = _at_cfg.copy()
            tg_enabled = st.toggle("Enable Telegram", value=_at_cfg2.get("telegram_enabled", False), key="cfg_tg_enabled")
            tg_token   = st.text_input("Bot Token", value=_at_cfg2.get("telegram_token", ""), type="password",
                                       placeholder="123456:ABC-DEF...", key="cfg_tg_token", disabled=not tg_enabled)
            tg_chat_id = st.text_input("Chat ID", value=_at_cfg2.get("telegram_chat_id", ""),
                                       placeholder="-1001234567890", key="cfg_tg_chat", disabled=not tg_enabled)
            tg_min_conf = st.slider("Alert threshold (%)", 50, 95, int(_at_cfg2.get("min_confidence", 70)),
                                    step=5, key="cfg_tg_thresh", disabled=not tg_enabled)
            cst, ctest = st.columns(2)
            with cst:
                if st.button("Save Telegram", key="cfg_tg_save", width="stretch"):
                    _at_cfg2.update({"telegram_enabled": tg_enabled, "telegram_token": tg_token.strip(),
                                     "telegram_chat_id": tg_chat_id.strip(), "min_confidence": tg_min_conf})
                    _save_alerts_config_and_clear(_at_cfg2)
                    st.success("Saved!")
            with ctest:
                if st.button("Test", key="cfg_tg_test", width="stretch", disabled=not tg_enabled):
                    ok, err = _alerts.send_telegram(tg_token.strip(), tg_chat_id.strip(),
                                                    "\u2705 Telegram test — connection successful!")
                    st.success("Message sent!") if ok else st.error(err or "Test failed — check your bot token and chat ID.")
            st.caption("Get bot token from @BotFather · Chat ID from @userinfobot")

        with st.expander("📧 Email Alerts", expanded=_at_cfg.get("email_enabled", False)):
            _at_em = _at_cfg.copy()
            em_on   = st.toggle("Enable Email", value=_at_em.get("email_enabled", False), key="cfg_em_on")
            em_to   = st.text_input("Recipient", value=_at_em.get("email_to", ""), placeholder="you@example.com",
                                    key="cfg_em_to", disabled=not em_on)
            em_from = st.text_input("Sender (Gmail)", value=_at_em.get("email_from", ""),
                                    placeholder="yourbot@gmail.com", key="cfg_em_from", disabled=not em_on)
            em_pass = st.text_input("App Password", value=_at_em.get("email_pass", ""), type="password",
                                    key="cfg_em_pass", disabled=not em_on)
            em_min  = st.slider("Alert threshold (%)", 50, 95, int(_at_em.get("email_min_confidence", 70)),
                                step=5, key="cfg_em_thresh", disabled=not em_on)
            cse, cte = st.columns(2)
            with cse:
                if st.button("Save Email", key="cfg_em_save", width="stretch"):
                    _at_em.update({"email_enabled": em_on, "email_to": em_to.strip(),
                                   "email_from": em_from.strip(), "email_pass": em_pass,
                                   "email_min_confidence": em_min})
                    _save_alerts_config_and_clear(_at_em)
                    st.success("Saved!")
            with cte:
                if st.button("Test", key="cfg_em_test", width="stretch", disabled=not em_on):
                    ok, err = _alerts.send_email_alert(em_from.strip(), em_pass, em_to.strip(),
                                                       "Crypto Signal Model — Test Alert",
                                                       "\u2705 Email alert test successful.")
                    st.success("Email sent!") if ok else st.error(err or "Test failed — check your Gmail App Password and email settings.")
            st.caption("Use a Gmail App Password (Settings → Security → 2FA → App passwords)")

        with st.expander("💬 Discord Alerts", expanded=_at_cfg.get("discord_enabled", False)):
            _at_dc = _at_cfg.copy()
            dc_on  = st.toggle("Enable Discord", value=_at_dc.get("discord_enabled", False), key="cfg_dc_on")
            dc_wh  = st.text_input("Webhook URL", value=_at_dc.get("discord_webhook_url", ""), type="password",
                                   placeholder="https://discord.com/api/webhooks/...",
                                   key="cfg_dc_wh", disabled=not dc_on)
            dc_min = st.slider("Alert threshold (%)", 50, 95, int(_at_dc.get("discord_min_confidence", 70)),
                               step=5, key="cfg_dc_thresh", disabled=not dc_on)
            csd, ctd = st.columns(2)
            with csd:
                if st.button("Save Discord", key="cfg_dc_save", width="stretch"):
                    _at_dc.update({"discord_enabled": dc_on, "discord_webhook_url": dc_wh.strip(),
                                   "discord_min_confidence": dc_min})
                    _save_alerts_config_and_clear(_at_dc)
                    st.success("Saved!")
            with ctd:
                if st.button("Test", key="cfg_dc_test", width="stretch", disabled=not dc_on):
                    ok, err = _alerts.send_discord(dc_wh.strip(),
                                                   "\u2705 **Crypto Signal Model** — Discord test!")
                    st.success("Message sent!") if ok else st.error(err or "Test failed — check your webhook URL and try again.")
            st.caption("Create webhook: Channel → Edit → Integrations → Webhooks → New")

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
                        st.success(f"Weights recalibrated. Reload app to apply.")
                        _bay_detail = _db.get_bayesian_weights_detail()
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

        if st.button("Run Optuna Optimization", type="primary", width="stretch"):
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



    # ── Tab 3: Alerts (full config + notifications)
    with _cfg_t3:
        _render_alerts_tab()
        st.markdown('---')
        st.markdown('#### Notifications & Scheduler')
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
        if st.button("Save API Keys", width="stretch"):
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
        with st.form("autoscan_form"):
            _sc1, _sc2 = st.columns(2)
            with _sc1:
                _sched_on = st.toggle(
                    "Enable Auto-Scan",
                    value=_sched_cfg.get("autoscan_enabled", False),
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
                            key=lambda v: abs(v - _sched_cfg.get("autoscan_interval_minutes", 60)))
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
            if st.button("💾 Save Config", type="primary", width="stretch"):
                _save_config(overrides)
        with reset_col:
            if st.button("↺ Reset to Defaults", width="stretch"):
                _reset_config()



    # ── Tab 4: Dev Tools
    with _cfg_t4:
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
    with _cfg_t5:
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
            _okx_key  = _ek1.text_input("API Key",     value=_exec_ui_cfg.get("okx_api_key", ""),
                                        type="password", placeholder="OKX API Key")
            _okx_sec  = _ek2.text_input("Secret",      value=_exec_ui_cfg.get("okx_secret", ""),
                                        type="password", placeholder="OKX Secret")
            _okx_pass = _ek3.text_input("Passphrase",  value=_exec_ui_cfg.get("okx_passphrase", ""),
                                        type="password", placeholder="API Passphrase")
            _ord_type = st.selectbox(
                "Default Order Type", ["market", "limit"],
                index=0 if _exec_ui_cfg.get("default_order_type", "market") == "market" else 1,
            )
            if st.form_submit_button("💾 Save Execution Config", type="primary"):
                _exec_ui_cfg.update({
                    "live_trading_enabled":        _live_on,
                    "auto_execute_enabled":        _auto_on,
                    "auto_execute_min_confidence": _auto_conf,
                    "okx_api_key":                 _okx_key.strip(),
                    "okx_secret":                  _okx_sec.strip(),
                    "okx_passphrase":              _okx_pass.strip(),
                    "default_order_type":          _ord_type,
                })
                _save_alerts_config_and_clear(_exec_ui_cfg)
                st.success("Execution config saved.")

        if st.button("🔌 Test OKX Connection", width="content"):
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

        # ── Autonomous Agent Settings ──────────────────────────────────────────────
        st.markdown("---")
        _ui.section_header(
            "Autonomous AI Agent",
            "24/7 LangGraph + Claude reasoning loop — approve/reject trades without human interaction",
            icon="🤖",
        )
        st.caption(
            "The agent runs independently in a background thread, scanning all pairs every "
            "**interval_seconds** and asking Claude to approve or reject each signal. "
            "Hard Python risk gates fire before AND after Claude — Claude never calls place_order directly. "
            "**Dry-run mode** (recommended) logs all decisions without placing orders."
        )
        st.warning(
            "⚠ Enabling live trading via the agent means real orders will be placed 24/7 "
            "without your review. Start with Dry-run=ON and monitor the Agent Decisions log "
            "in the Dashboard for at least a few days before disabling dry-run."
        )

        _ag_ui_cfg = _cached_alerts_config()
        with st.form("agent_config_form"):
            _ag_enabled = st.toggle(
                "🤖 Enable Autonomous Agent",
                value=bool(_ag_ui_cfg.get("agent_enabled", False)),
                help="Start the 24/7 agent loop. Pairs are cycled every interval_seconds.",
            )
            _ag_dry = st.toggle(
                "Dry-run (log only — no orders placed)",
                value=bool(_ag_ui_cfg.get("agent_dry_run", True)),
                help="When ON, agent logs approve/reject decisions but never calls place_order.",
            )
            if _ag_enabled and not _ag_dry:
                st.error("DRY-RUN IS OFF — approved signals will place real/paper orders.")

            _ag_col1, _ag_col2 = st.columns(2)
            _ag_interval = _ag_col1.number_input(
                "Interval (seconds per cycle)",
                min_value=30, max_value=3600,
                value=int(_ag_ui_cfg.get("agent_interval_seconds", 60)),
                step=30,
                help="Time between complete pair-scan cycles. Min 30s to respect API rate limits.",
            )
            _ag_min_conf = _ag_col2.slider(
                "Min Confidence to Consider (%)",
                min_value=60, max_value=95,
                value=int(_ag_ui_cfg.get("agent_min_confidence", 80)),
                step=5,
                help="Signals below this threshold are skipped before calling Claude.",
            )
            _ag_col3, _ag_col4 = st.columns(2)
            _ag_max_pos = _ag_col3.number_input(
                "Max Concurrent Positions",
                min_value=1, max_value=10,
                value=int(_ag_ui_cfg.get("agent_max_concurrent_positions", 3)),
                step=1,
            )
            _ag_loss_limit = _ag_col4.number_input(
                "Daily Loss Limit (%)",
                min_value=1.0, max_value=20.0,
                value=float(_ag_ui_cfg.get("agent_daily_loss_limit_pct", 5.0)),
                step=0.5,
                help="Agent stops trading for the day when cumulative PnL hits this loss.",
            )
            _ag_portfolio = st.number_input(
                "Portfolio Size (USD)",
                min_value=100.0,
                value=float(_ag_ui_cfg.get("agent_portfolio_size_usd", 10_000.0)),
                step=500.0,
                help="Used to calculate position sizes when balance cannot be fetched from OKX.",
            )
            if st.form_submit_button("💾 Save Agent Config", type="primary"):
                _ag_ui_cfg.update({
                    "agent_enabled":                  _ag_enabled,
                    "agent_dry_run":                  _ag_dry,
                    "agent_interval_seconds":         int(_ag_interval),
                    "agent_min_confidence":           float(_ag_min_conf),
                    "agent_max_concurrent_positions": int(_ag_max_pos),
                    "agent_daily_loss_limit_pct":     float(_ag_loss_limit),
                    "agent_portfolio_size_usd":       float(_ag_portfolio),
                })
                _save_alerts_config_and_clear(_ag_ui_cfg)
                if _agent is not None:
                    if _ag_enabled and not _agent.supervisor.is_running():
                        _agent.supervisor.start()
                    elif not _ag_enabled and _agent.supervisor.is_running():
                        _agent.supervisor.stop()
                st.success("Agent config saved. Refresh Dashboard to see status panel.")

        # Agent runtime controls
        if _agent is None:
            st.error("agent.py failed to import — check logs.")
        else:
            _ag_c1, _ag_c2 = st.columns(2)
            with _ag_c1:
                if st.button("▶ Start Agent Now", width="stretch",
                             disabled=_agent.supervisor.is_running()):
                    _agent.supervisor.start()
                    st.success("Agent started.")
                    st.rerun()
            with _ag_c2:
                if st.button("⏹ Stop Agent", width="stretch",
                             disabled=not _agent.supervisor.is_running()):
                    _agent.supervisor.stop()
                    st.warning("Agent stop requested.")
                    st.rerun()

            # Live status summary
            try:  # APP-10: status() may raise or return partial dict during agent init
                _ag_live = _agent.supervisor.status() or {}
            except Exception:
                _ag_live = {}
            st.markdown(
                f"**Agent status:** {'🟢 Running' if _ag_live.get('running') else '🔴 Stopped'} "
                f"| Cycles: {_ag_live.get('cycles_total', 0)} "
                f"| Last decision: {_ag_live.get('last_decision') or '—'} "
                f"| Restarts: {_ag_live.get('restart_count', 0)} "
                f"| Engine: {'LangGraph' if _ag_live.get('langgraph') else 'Fallback pipeline'}"
            )


        # ── Watchlist Alerts ───────────────────────────────────────────────────────
        st.markdown("---")
        _ui.section_header(
            "Watchlist Alerts",
            "Get notified when a specific coin hits a signal you care about — fires on every scan",
            icon="🔔",
        )
        st.caption(
            "Each rule fires via Telegram, Discord, and/or Email (whichever channels you have enabled above). "
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
                    "#f6465d" if "SELL" in _wl_rule.get("condition", "") else
                    "#6366f1"
                )
                _wl_status = "🟢 ON" if _wl_rule.get("enabled", True) else "⚫ OFF"
                _wl_rc1, _wl_rc2, _wl_rc3 = st.columns([5, 1, 1])
                with _wl_rc1:
                    st.markdown(
                        f"""<div style="background:rgba(14,18,30,0.7);border:1px solid rgba(255,255,255,0.07);
                        border-radius:10px;padding:10px 14px;margin-bottom:4px">
                        <span style="font-weight:700;color:#e8ecf4">{_wl_rule.get('name','—')}</span>
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
@st.fragment(run_every=1)
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
    _bt_title = "Performance History" if _bt_lv in ("beginner", "intermediate") else "Backtest Viewer"
    st.markdown(
        f'<h1 style="color:#e8ecf1;font-size:26px;font-weight:700;'
        f'letter-spacing:-0.5px;margin-bottom:0">{_bt_title}</h1>',
        unsafe_allow_html=True,
    )
    if _bt_lv == "beginner":
        st.caption("See how the model has performed in the past — like a report card for the AI signals.")

    run_col, _ = st.columns([2, 6])
    with run_col:
        bt_disabled = st.session_state.get("backtest_running", False)
        if st.button("▶ Run Backtest", disabled=bt_disabled, type="primary", width="stretch"):
            _start_backtest()

    # _backtest_progress is defined at module level (above page_backtest) — always called
    # here so its fragment key stays registered across rerenders (prevents $$ID KeyError).
    _backtest_progress()

    _bt_t1, _bt_t2, _bt_t3 = st.tabs([
        "📊 Summary",
        "📋 Trade History",
        "🔬 Advanced Backtests",
    ])

    with _bt_t1:
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
            _wr = m['win_rate']

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
                    f"{m['total_return']}%",
                    help="If you had followed every signal since the start, this is the total gain or loss on your portfolio.",
                )
                bm[2].metric(
                    "🛡️ Worst Drawdown",
                    f"{m['max_drawdown']}%",
                    help="The biggest drop from a high point before recovering. Think of it as the worst losing patch. Lower is safer.",
                )
                with st.expander("📊 Full Performance Stats", expanded=False):
                    mc = st.columns(6)
                    mc[0].metric("Trades Simulated", m["total_trades"], help=_ui.HELP_TOTAL_TRADES)
                    mc[1].metric("Profitable Trades", f"{_wr}%", delta=f"{round(_wr - 50, 1):+.1f}% vs coin-flip", help=_ui.HELP_WIN_RATE)
                    mc[2].metric("Avg Gain per Trade", f"{m['avg_pnl']}%", help=_ui.HELP_AVG_PNL)
                    mc[3].metric("Profit vs Loss Ratio", m["profit_factor"], help=_ui.HELP_PROFIT_FACTOR)
                    mc[4].metric("Performance Quality", m["sharpe"], help=_ui.HELP_SHARPE)
                    mc[5].metric("Worst Losing Streak", f"{m['max_drawdown']}%", help=_ui.HELP_MAX_DRAWDOWN)
                    mc2 = st.columns(5)
                    mc2[0].metric("Total Return", f"{m['total_return']}%")
                    mc2[1].metric("Risk-Adj Return", m.get("sortino", "N/A"), help=_ui.HELP_SORTINO)
                    mc2[2].metric("Recovery Speed", m.get("calmar", "N/A"), help=_ui.HELP_CALMAR)
                    mc2[3].metric("Longest Losing Run", m.get("max_consec_losses", "N/A"), help="How many trades in a row lost money at worst.")
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
                    f'<div style="font-size:13px;color:#a8b4c8;line-height:1.65">'
                    f'{_btm_msg}<br><br>{_btm_risk}<br><br>'
                    f'<em>Past performance does not guarantee future results. '
                    f'Always treat signals as one input in your decision — not a guarantee.</em>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                # Intermediate / Advanced — full metric grids
                mc = st.columns(6)
                mc[0].metric("Trades Simulated", m["total_trades"],
                             help=_ui.HELP_TOTAL_TRADES)
                mc[1].metric(f"Profitable Trades", f"{_wr}%",
                             delta=f"{round(_wr - 50, 1):+.1f}% vs coin-flip",
                             help=_ui.HELP_WIN_RATE)
                mc[2].metric("Avg Gain per Trade", f"{m['avg_pnl']}%",
                             help=_ui.HELP_AVG_PNL)
                mc[3].metric("Profit vs Loss Ratio", m["profit_factor"],
                             help=_ui.HELP_PROFIT_FACTOR)
                mc[4].metric("Performance Quality", m["sharpe"],
                             help=_ui.HELP_SHARPE)
                mc[5].metric("Worst Losing Streak", f"{m['max_drawdown']}%",
                             help=_ui.HELP_MAX_DRAWDOWN)

                mc2 = st.columns(5)
                mc2[0].metric("Total Return", f"{m['total_return']}%")
                mc2[1].metric("Risk-Adj Return", m.get("sortino", "N/A"),
                              help=_ui.HELP_SORTINO)
                mc2[2].metric("Recovery Speed", m.get("calmar", "N/A"),
                              help=_ui.HELP_CALMAR)
                mc2[3].metric("Longest Losing Run", m.get("max_consec_losses", "N/A"),
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
            _efig.add_hline(y=_init_eq, line_dash="dot", line_color="#888888",
                            annotation_text=f"Start ${_init_eq:,.0f}",
                            annotation_position="bottom right", row=1, col=1)
            if _win_x:
                _efig.add_trace(go.Scatter(
                    x=_win_x, y=_win_y, mode="markers", name="Win",
                    marker=dict(color="#00cc96", size=5, symbol="circle"),
                ), row=1, col=1)
            if _loss_x:
                _efig.add_trace(go.Scatter(
                    x=_loss_x, y=_loss_y, mode="markers", name="Loss",
                    marker=dict(color="#ff4b4b", size=5, symbol="circle"),
                ), row=1, col=1)

            # Row 2: drawdown % (filled red below 0)
            _efig.add_trace(go.Scatter(
                x=_x, y=_dd.tolist(), mode="lines", name="Drawdown %",
                line=dict(color="#ff4b4b", width=1),
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
                                    color_discrete_sequence=['#636EFA'],
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
                        marker_color='#636EFA',
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


    with _bt_t2:
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
                    m4.metric("Avg Confidence", f"{avg_conf:.1f}%" if pd.notna(avg_conf) else "N/A")

                st.markdown("---")

                # Confidence trend per pair
                if 'scan_timestamp' in df.columns and 'confidence_avg_pct' in df.columns and 'pair' in df.columns:
                    st.subheader("Confidence Trend by Pair")
                    pair_filter = st.multiselect("Select pairs", options=df['pair'].unique().tolist(),
                                                  default=df['pair'].unique().tolist()[:3], key="master_pair_filter")
                    df_plot = df[df['pair'].isin(pair_filter)] if pair_filter else df
                    fig = px.line(df_plot, x='scan_timestamp', y='confidence_avg_pct',
                                  color='pair', markers=True,
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
                logging.warning(f"load_positions failed: {_e}")
                positions = {}

            # ── Portfolio Heat Strip ──────────────────────────────────────────────
            if positions:
                _total_exp  = sum(float(p.get("size_pct") or 0) for p in positions.values())  # APP-16: or 0 handles explicit None
                _buy_exp    = sum(float(p.get("size_pct") or 0) for p in positions.values() if "BUY"  in str(p.get("direction", "")))
                _sell_exp   = sum(float(p.get("size_pct") or 0) for p in positions.values() if "SELL" in str(p.get("direction", "")))
                _n_pos      = len(positions)
                # Heat color: green < 30%, amber 30–60%, red > 60%
                _heat_color = "#00d4aa" if _total_exp < 30 else ("#f59e0b" if _total_exp < 60 else "#f6465d")
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
                    f'<div style="font-size:20px;font-weight:700;color:#e8ecf4">{_n_pos}</div>'
                    f'<div style="font-size:10px;color:rgba(168,180,200,0.4)">trades active</div></div>'
                    f'<div style="background:rgba(0,212,170,0.06);border:1px solid rgba(0,212,170,0.2);'
                    f'border-radius:10px;padding:10px 18px;text-align:center">'
                    f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">BUY EXPOSURE</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#00d4aa">{_buy_exp:.1f}%</div>'
                    f'<div style="font-size:10px;color:rgba(168,180,200,0.4)">long trades</div></div>'
                    f'<div style="background:rgba(246,70,93,0.06);border:1px solid rgba(246,70,93,0.2);'
                    f'border-radius:10px;padding:10px 18px;text-align:center">'
                    f'<div style="font-size:9px;color:rgba(168,180,200,0.45);text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">SELL EXPOSURE</div>'
                    f'<div style="font-size:20px;font-weight:700;color:#f6465d">{_sell_exp:.1f}%</div>'
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
                        except Exception:
                            pass

                    # Render position card
                    _pnl_sign  = "+" if _pnl_pct >= 0 else ""
                    _dir_emoji = "🟢" if "BUY" in _direction else "🔴"
                    _pnl_color = "#00d4aa" if _pnl_pct >= 0 else "#ff4b4b"

                    st.markdown(
                        f'<div style="background:#1a1f2e;border-radius:10px;padding:14px 18px;'
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
                    import time as _time_pos
                    _pos_ts_key = "_pos_live_ts"
                    _now_pos    = _time_pos.time()
                    if _now_pos - st.session_state.setdefault(_pos_ts_key, _now_pos - 4.9) >= 5:  # APP-14: default near-now prevents immediate fire
                        st.session_state[_pos_ts_key] = _now_pos
                        _time_pos.sleep(0.1)
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
                    p2.metric("Win Rate", f"{wins/len(df_closed)*100:.1f}%" if len(df_closed) > 0 else "N/A")
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
                    f2.metric("Avg Confidence Logged", f"{avg_fb_conf:.1f}%" if pd.notna(avg_fb_conf) else "N/A")

                if 'confidence' in df_fb.columns and 'timestamp' in df_fb.columns:
                    fig = px.scatter(df_fb, x='timestamp', y='confidence', color='direction',
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


    with _bt_t3:
        if _bt_lv == 'beginner':
            st.markdown(
                '<div style="background:rgba(99,102,241,0.08);border:1px solid rgba(99,102,241,0.25);'
                'border-radius:12px;padding:28px 24px;text-align:center;margin:20px 0">'
                '<div style="font-size:32px;margin-bottom:10px">\U0001f52c</div>'
                '<div style="font-size:18px;font-weight:700;color:#e8ecf4;margin-bottom:8px">'
                'Advanced Analysis Tools</div>'
                '<div style="font-size:13px;color:#9ca3af;line-height:1.6;max-width:380px;margin:0 auto">'
                'Walk-Forward Validation, Deep Backtest, and Signal Calibration are available at '
                '<strong style="color:#818cf8">Intermediate</strong> or '
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
                                      f"{wf_r['mean_accuracy']}%" if wf_r['mean_accuracy'] else "N/A",
                                      help="Average directional accuracy across all out-of-sample test windows")
                    wf_cols[1].metric("Std Dev",
                                      f"±{wf_r['std_accuracy']}%" if wf_r['std_accuracy'] is not None else "N/A",
                                      help="Lower = more consistent across market regimes")
                    wf_df = pd.DataFrame(wf_r['windows'])
                    wf_df['accuracy_pct'] = wf_df['accuracy_pct'].apply(
                        lambda x: f"{x}%" if x is not None else "N/A"
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
                        f'<div style="font-size:13px;color:#a8b4c8;line-height:1.6">'
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
                            template='plotly_dark', title=f"Deep Backtest Equity Curve — {db_pair} {db_tf}",
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
                        "#00d4aa" if float(r["win_rate_pct"]) >= float(r["conf_bucket"]) + 5 else "#ff4b4b"
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
                    template="plotly_dark", height=340,
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
                    _pnl_c4.metric(
                        "Est. Annualised Return",
                        f"{_pnl_sum.get('annualized_return_pct', 0):+.1f}%",
                        help="Rough CAGR-style estimate based on average holding period",
                    )
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
                    _ic_label = _ic_r.get("ic_label", "N/A")
                    _ic_n     = _ic_r.get("n_samples", 0)
                    _ic_p     = _ic_r.get("p_value")
                    _ic_color = "#10b981" if _ic_val > 0.05 else ("#ef4444" if _ic_val < 0 else "#f59e0b")
                    _ic_cols  = st.columns(4)
                    _ic_cols[0].metric("IC Score", f"{_ic_val:.4f}")
                    _ic_cols[1].metric("Signal Quality", _ic_label)
                    _ic_cols[2].metric("Samples", _ic_n)
                    _ic_cols[3].metric("p-value", f"{_ic_p:.4f}" if _ic_p is not None else "N/A")
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
                    _wfe_label = _wfe_r.get("wfe_label", "N/A")
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
                                       f"{_avg_oos:.1f}%" if _avg_oos is not None else "N/A",
                                       help="Average win rate in out-of-sample test periods")
                        _wfo_m3.metric("Windows Used", _wfo_r.get("n_windows", "N/A"))
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
                            _wfv_m1.metric("Avg WFE", f"{_wfv_avg_wfe:.3f}" if _wfv_avg_wfe is not None else "N/A",
                                           help="Average Walk-Forward Efficiency across all windows. >0.7 = good.")
                            _wfv_m2.metric("Grade", _wfv_grade,
                                           help="EXCELLENT≥0.9 · GOOD≥0.7 · FAIR≥0.5 · POOR<0.5")
                            _wfv_m3.metric("Stability Score", f"{_wfv_stab:.3f}" if _wfv_stab is not None else "N/A",
                                           help="Std dev of WFE across windows. Lower = more consistent.")
                            _wfv_m4.metric("Avg OOS Win Rate", f"{_wfv_oos_wr:.1f}%" if _wfv_oos_wr is not None else "N/A")

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
                                    line=dict(color="#60a5fa", width=2),
                                    marker=dict(size=7),
                                ))
                                _wfv_line.add_trace(go.Scatter(
                                    x=_wfv_ids, y=_wfv_oos_sh2,
                                    name="OOS Sharpe",
                                    mode="lines+markers",
                                    line=dict(color="#34d399", width=2, dash="dot"),
                                    marker=dict(size=7),
                                ))
                                _wfv_line.update_layout(
                                    title="IS Sharpe vs OOS Sharpe per Window",
                                    height=240,
                                    margin=dict(l=10, r=10, t=36, b=10),
                                    paper_bgcolor="#0e1117",
                                    plot_bgcolor="#0e1117",
                                    font=dict(color="#fafafa", size=11),
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
                                    paper_bgcolor="#0e1117",
                                    plot_bgcolor="#0e1117",
                                    font=dict(color="#fafafa", size=11),
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
                            _pair_rows.append({"Pair": _pr, "Return %": "N/A", "P&L $": "N/A",
                                               "Max DD %": "N/A", "Vol Ann %": "N/A", "Status": "No data"})
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
                        f'<div style="font-size:13px;color:#a8b4c8;line-height:1.6">'
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
    _arb_lv = st.session_state.get("user_level", "beginner")
    _arb_title = "⚡ Opportunities" if _arb_lv in ("beginner", "intermediate") else "⚡ Arbitrage Scanner"
    st.title(_arb_title)
    if _arb_lv == "beginner":
        st.caption(
            "Sometimes the same coin costs different amounts on different exchanges. "
            "This scanner finds those gaps — you buy cheap on one exchange and sell higher on another. "
            "Each card below tells you exactly what to do in plain English."
        )
    else:
        st.caption(
            "Cross-exchange spot price spreads and funding-rate carry trades. "
            "Net spread = gross spread − round-trip taker fees."
        )

    # ── Controls ──
    col_btn, col_thresh, col_spacer = st.columns([1, 1, 4])
    with col_btn:
        run_scan = st.button("🔍 Scan Now", width="stretch", type="primary")
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
        m2.metric("Opportunities",    len(opp_rows), delta=f"+{len(opp_rows)}" if opp_rows else None)
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
            if "MARGINAL"    in val: return "color: #f0b429"
            return "color: #888"

        def _color_net(val: str) -> str:
            try:
                v = float(val.replace("%", ""))
                if v >= _arb.MIN_NET_SPREAD_PCT: return "color: #00d4aa; font-weight:bold"
                if v >= 0:                        return "color: #f0b429"
                return "color: #ff4b4b"
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
                    multi = data_feeds.get_multi_exchange_funding_rates(pair)
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
                        row["Best Rate"] = "N/A"
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
                    return "color: #555555"
                if val >  0.05: return "color: #ff4b4b; font-weight: bold"
                if val >  0.01: return "color: #ffa500"
                if val < -0.05: return "color: #00d4aa; font-weight: bold"
                if val < -0.01: return "color: #7ecb9a"
                return "color: #888888"

            def _color_ann(val):
                if not isinstance(val, (int, float)):
                    return ""
                if val >= 30: return "color: #00d4aa; font-weight: bold"
                if val >= 10: return "color: #7ecb9a"
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
                    if val >= 20: return "color: #7ecb9a"
                    if val >= 10: return "color: #ffa500"
                    return ""

                def _color_rate(val):
                    if not isinstance(val, (int, float)):
                        return ""
                    if val >  0.05: return "color: #ff4b4b; font-weight: bold"
                    if val >  0.01: return "color: #ffa500"
                    if val < -0.05: return "color: #00d4aa; font-weight: bold"
                    if val < -0.01: return "color: #7ecb9a"
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
def page_agent():
    _ag_lv = st.session_state.get("user_level", "beginner")
    _ag_title = "🤖 AI Assistant" if _ag_lv in ("beginner", "intermediate") else "🤖 Autonomous Agent"
    st.title(_ag_title)
    if _ag_lv == "beginner":
        st.caption(
            "Your AI assistant watches the markets 24/7 and tells you when it thinks there's an opportunity. "
            "It never makes trades for you — it only gives you advice, and you decide what to do."
        )
    else:
        st.caption(
            "LangGraph + Claude claude-sonnet-4-6 autonomous trading agent. "
            "Hard Python risk gates before and after every Claude decision. "
            "Claude may only approve or reject — never place orders directly."
        )

    if _agent is None:
        st.error("agent.py failed to import. Check logs for details.")
        return

    # ── Live status ──
    try:  # APP-09: status() may raise or return partial dict during startup
        status = _agent.supervisor.status() or {}
    except Exception:
        status = {}
    is_running = status.get("running", False)

    col_status, col_start, col_stop, col_spacer = st.columns([2, 1, 1, 3])
    with col_status:
        if is_running:
            _run_label = "✅ AI is watching the market" if _ag_lv == "beginner" else "▲ RUNNING"
            st.success(_run_label)
        elif status.get("kill_requested", False):
            st.warning("⏳ Stopping…" if _ag_lv == "beginner" else "■ STOPPING…")
        else:
            _stop_label = "⏸ AI is paused — click Start to activate" if _ag_lv == "beginner" else "▼ STOPPED"
            st.error(_stop_label)
    with col_start:
        if st.button("▶ Start", width="stretch", type="primary",
                     disabled=is_running, key="agent_start_btn"):
            _ac = _cached_alerts_config()
            _ac["agent_enabled"] = True
            _save_alerts_config_and_clear(_ac)
            _agent.supervisor.start()
            st.rerun()
    with col_stop:
        if st.button("■ Stop", width="stretch",
                     disabled=not is_running, key="agent_stop_btn"):
            _ac = _cached_alerts_config()
            _ac["agent_enabled"] = False
            _save_alerts_config_and_clear(_ac)
            _agent.supervisor.stop()
            st.rerun()

    # ── Metrics ──
    st.markdown("---")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Cycles", status.get("cycles_total", 0))
    with m2:
        last_ts = status.get("last_run_ts")
        if last_ts:
            age_s = int(time.time() - last_ts)
            age_str = f"{age_s // 60}m {age_s % 60}s ago" if age_s >= 60 else f"{age_s}s ago"
        else:
            age_str = "Never"
        st.metric("Last Cycle", age_str)
    with m3:
        st.metric("Last Pair", status.get("last_pair") or "—")
    with m4:
        _dec_icon = {"approve": "🟢", "reject": "🔴", "skip": "⚪"}.get(
            status.get("last_decision"), "⚪"
        )
        st.metric("Last Decision", f"{_dec_icon} {status.get('last_decision') or '—'}")

    m5, m6 = st.columns([1, 3])
    with m5:
        st.metric("Crash Restarts", status.get("restart_count", 0))
    with m6:
        _lg = "LangGraph state machine" if status.get("langgraph") else "Sequential pipeline (LangGraph not installed)"
        st.metric("Engine", _lg)

    # Show in-progress indicator when a cycle is actively running
    _cur = status.get("current_pair", "")
    _elapsed = status.get("cycle_elapsed_s", 0)
    if is_running and _cur:
        st.info(f"⏳ Processing {_cur} — cycle running for {_elapsed}s")

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
    except Exception:
        pass

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
# ROUTER
# ──────────────────────────────────────────────
audit("page_view", page=page, level=st.session_state.get("user_level", "beginner"))
if page == "Dashboard":
    page_dashboard()
elif page == "Config Editor":
    page_config()
elif page == "Backtest Viewer":
    page_backtest()
elif page == "Arbitrage":
    page_arbitrage()
elif page == "Agent":
    page_agent()
