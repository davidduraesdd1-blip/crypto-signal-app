"""
database.py — SQLite backend for Crypto Signal Model v5.9.13

Replaces all CSV/JSON file I/O with ACID-compliant SQLite operations.
Thread-safe: WAL mode enables concurrent reads + one writer at a time.
Write operations protected by a module-level lock (consistent with _log_lock
pattern already used in crypto_model_core.py parallel scan workers).

On first import:
  1. Creates crypto_model.db with full schema
  2. Migrates any existing CSV/JSON data (idempotent — skips if rows already exist)

Drop-in API: all functions match existing signatures in crypto_model_core.py / app.py.
"""

import sqlite3
import threading
import json
import os
import logging
import warnings
from typing import Optional
import pandas as pd
import numpy as np

# pandas 2.x warns on sqlite3 DBAPI2 connections — suppress globally for this module
warnings.filterwarnings(
    'ignore',
    message='pandas only supports SQLAlchemy connectable',
    category=UserWarning,
)
from datetime import datetime, timedelta, timezone
import concurrent.futures as _cf

try:
    from scipy.stats import spearmanr as _spearmanr
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False
    logging.warning("scipy not installed — IC Spearman correlation will use fallback")

logger = logging.getLogger(__name__)

import os as _os
from pathlib import Path as _Path

# Audit R10d: Streamlit Cloud mounts /mount/src read-only. Writing the DB
# next to __file__ would crash on first connect. Probe for a writable dir
# and fall back to /tmp (same pattern DeFi Model uses in config.py:12-23).
_BASE_DIR = _Path(__file__).resolve().parent
_PREFERRED_DATA = _BASE_DIR / "data"
try:
    _PREFERRED_DATA.mkdir(exist_ok=True)
    _write_test = _PREFERRED_DATA / ".write_test"
    _write_test.touch()
    _write_test.unlink()
    _DATA_DIR = _PREFERRED_DATA
except (PermissionError, OSError):
    _DATA_DIR = _Path("/tmp/supergrok_data")
    _DATA_DIR.mkdir(exist_ok=True, parents=True)

# Legacy DB location (next to __file__) — preserved as a fallback so existing
# local installs keep working. New/Streamlit-Cloud installs land in _DATA_DIR.
_LEGACY_DB = _BASE_DIR / "crypto_model.db"
if _LEGACY_DB.exists():
    DB_FILE = str(_LEGACY_DB)
else:
    DB_FILE = str(_DATA_DIR / "crypto_model.db")

# Single write lock — mirrors _log_lock used in crypto_model_core.py
_write_lock = threading.Lock()

# PERF: Thread-local connection pool — reuses the same connection per thread
# instead of re-opening and re-running all PRAGMAs on every _get_conn() call.
_thread_local = threading.local()


def _make_conn() -> sqlite3.Connection:
    """Create a fresh SQLite connection with all performance PRAGMAs applied."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # PERF: 64 MB page cache (default is ~2 MB) — major speedup for repeated queries
    conn.execute("PRAGMA cache_size=-65536")
    # PERF: 256 MB memory-mapped I/O — bypasses read() syscalls for sequential scans
    conn.execute("PRAGMA mmap_size=268435456")
    # PERF: keep temp tables / sort buffers in RAM instead of a temp file
    conn.execute("PRAGMA temp_store=MEMORY")
    # PERF: checkpoint WAL less aggressively (default 1000 pages is fine; keep it)
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    # PERF: update query planner statistics once per connection
    conn.execute("PRAGMA optimize")
    conn.row_factory = sqlite3.Row
    return conn


# ──────────────────────────────────────────────
# CONNECTION FACTORY
# ──────────────────────────────────────────────

class _NoCloseConn:
    """Proxy for sqlite3.Connection that converts close() into rollback().

    Every database function calls conn.close() in its finally block, which was
    silently destroying the thread-local pooled connection and forcing a full
    PRAGMA re-initialisation on the next call (7 PRAGMAs × every DB access).

    With this wrapper close() merely rolls back any uncommitted transaction,
    leaving the underlying connection alive for reuse by the same thread.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.__dict__["_conn"] = conn

    def close(self) -> None:
        """Roll back pending transaction instead of closing — pool manages lifecycle."""
        try:
            self.__dict__["_conn"].rollback()
        except Exception:
            pass

    # Dunder methods are looked up on the class, so __getattr__ misses them.
    def __enter__(self):
        return self.__dict__["_conn"].__enter__()

    def __exit__(self, *args):
        return self.__dict__["_conn"].__exit__(*args)

    def __getattr__(self, name: str):
        return getattr(self.__dict__["_conn"], name)

    def __setattr__(self, name: str, val):
        setattr(self.__dict__["_conn"], name, val)


def _get_conn() -> "_NoCloseConn":
    """Return a per-thread cached connection — eliminates PRAGMA re-init overhead."""
    wrapped = getattr(_thread_local, "conn", None)
    if wrapped is None:
        wrapped = _NoCloseConn(_make_conn())
        _thread_local.conn = wrapped
    else:
        # Verify connection is still alive (handles process restarts / DB file recreation)
        try:
            wrapped.execute("SELECT 1")
        except (sqlite3.DatabaseError, sqlite3.ProgrammingError):
            wrapped = _NoCloseConn(_make_conn())
            _thread_local.conn = wrapped
    return wrapped


# ──────────────────────────────────────────────
# SCHEMA CREATION
# ──────────────────────────────────────────────
def _check_db_integrity() -> bool:
    """Run SQLite PRAGMA quick_check on startup to catch corruption early."""
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
        result = conn.execute("PRAGMA quick_check").fetchone()
        conn.close()
        if result and result[0] == "ok":
            return True
        logger.warning("[DB] Startup integrity check failed: %s", result)
        return False
    except Exception as e:
        logger.error("[DB] Startup integrity check error: %s", e)
        return False


def init_db():
    """Create all tables and indexes. Idempotent — safe to call on every startup."""
    # Run quick integrity check before opening the pooled connection
    if not _check_db_integrity():
        logger.warning("[DB] Integrity check FAILED — app will continue with caution")

    with _write_lock:
        conn = None
        try:  # BUG-C01 / BUG-H02: conn inside try so finally always has a reference to close
            conn = _get_conn()
            conn.executescript("""
                -- Per-signal feedback log (was feedback_log.csv, 12,795+ rows)
                -- F1: actual_exit/actual_pnl_pct/outcome/was_correct/resolved_at store real trade outcomes
                -- F4: vote_* columns store per-agent votes for accuracy-weighted ensemble
                CREATE TABLE IF NOT EXISTS feedback_log (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT NOT NULL,
                    pair            TEXT NOT NULL,
                    direction       TEXT,
                    entry           REAL,
                    exit_target     REAL,
                    confidence      REAL,
                    actual_exit     REAL,
                    actual_pnl_pct  REAL,
                    outcome         TEXT,
                    was_correct     INTEGER,
                    resolved_at     TEXT,
                    vote_trend      REAL,
                    vote_momentum   REAL,
                    vote_meanrev    REAL,
                    vote_sentiment  REAL,
                    vote_risk       REAL,
                    vote_lgbm       REAL,
                    -- Indicator snapshots at signal time (F-SNAP: enables LightGBM retraining)
                    snap_rsi        REAL,
                    snap_macd_hist  REAL,
                    snap_bb_pos     REAL,
                    snap_adx        REAL,
                    snap_stoch_k    REAL,
                    snap_volume_ok  INTEGER,
                    snap_regime     TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_fb_pair ON feedback_log(pair);
                CREATE INDEX IF NOT EXISTS idx_fb_ts   ON feedback_log(timestamp);

                -- Master scan results log (was daily_signals_master.csv)
                CREATE TABLE IF NOT EXISTS daily_signals (
                    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_timestamp              TEXT,
                    pair                        TEXT,
                    price_usd                   REAL,
                    confidence_avg_pct          REAL,
                    direction                   TEXT,
                    strategy_bias               TEXT,
                    mtf_alignment               REAL,
                    high_conf                   INTEGER,
                    fng_value                   REAL,
                    fng_category                TEXT,
                    entry                       REAL,
                    exit                        REAL,
                    stop_loss                   REAL,
                    risk_pct                    REAL,
                    position_size_usd           REAL,
                    position_size_pct           REAL,
                    risk_mode                   TEXT,
                    corr_with_btc               REAL,
                    corr_adjusted_size_pct      REAL,
                    regime                      TEXT,
                    sr_status                   TEXT,
                    circuit_breaker_triggered   INTEGER DEFAULT 0,
                    circuit_breaker_drawdown_pct REAL DEFAULT 0.0,
                    scan_sec                    REAL
                );
                CREATE INDEX IF NOT EXISTS idx_sig_pair ON daily_signals(pair);
                CREATE INDEX IF NOT EXISTS idx_sig_ts   ON daily_signals(scan_timestamp);
                CREATE INDEX IF NOT EXISTS idx_sig_dir  ON daily_signals(direction);
                CREATE INDEX IF NOT EXISTS idx_signals_pair_time ON daily_signals (pair, scan_timestamp DESC);

                -- Backtest trade-by-trade results (was backtest_summary.csv)
                CREATE TABLE IF NOT EXISTS backtest_trades (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id       TEXT NOT NULL,
                    timestamp    TEXT,
                    pair         TEXT,
                    direction    TEXT,
                    entry        REAL,
                    exit         REAL,
                    exit_reason  TEXT,
                    pnl_pct      REAL,
                    pnl_usd      REAL,
                    pos_pct      REAL,
                    gross_pnl_pct REAL,
                    fee_usd      REAL,
                    slippage_usd REAL
                );
                CREATE INDEX IF NOT EXISTS idx_bt_run  ON backtest_trades(run_id);
                CREATE INDEX IF NOT EXISTS idx_bt_pair ON backtest_trades(pair);

                -- Closed paper trade positions (was paper_trades_log.csv)
                CREATE TABLE IF NOT EXISTS paper_trades (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair       TEXT,
                    entry_time TEXT,
                    close_time TEXT,
                    direction  TEXT,
                    entry      REAL,
                    exit       REAL,
                    pnl_pct    REAL,
                    size_pct   REAL,
                    reason     TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pt_pair ON paper_trades(pair);

                -- Open paper trade positions (was positions.json)
                CREATE TABLE IF NOT EXISTS positions (
                    pair            TEXT PRIMARY KEY,
                    direction       TEXT,
                    entry           REAL,
                    target          REAL,
                    stop            REAL,
                    entry_time      TEXT,
                    size_pct        REAL DEFAULT 0.0,
                    current_pnl_pct REAL DEFAULT 0.0
                );

                -- Versioned indicator weights (was dynamic_weights.json)
                CREATE TABLE IF NOT EXISTS dynamic_weights (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    saved_at     TEXT NOT NULL,
                    source       TEXT DEFAULT 'manual',
                    weights_json TEXT NOT NULL
                );

                -- Weight evaluation log (was weights_log.csv)
                CREATE TABLE IF NOT EXISTS weights_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp    TEXT,
                    avg_pnl      REAL,
                    accuracy_pct REAL
                );

                -- Scan results cache (singleton row id=1)
                CREATE TABLE IF NOT EXISTS scan_cache (
                    id           INTEGER PRIMARY KEY CHECK (id = 1),
                    saved_at     TEXT,
                    results_json TEXT
                );

                -- Scan progress state (singleton row id=1)
                CREATE TABLE IF NOT EXISTS scan_status (
                    id       INTEGER PRIMARY KEY CHECK (id = 1),
                    running  INTEGER DEFAULT 0,
                    timestamp TEXT,
                    error    TEXT,
                    progress REAL DEFAULT 0,
                    pair     TEXT DEFAULT ''
                );

                -- Alert audit log
                CREATE TABLE IF NOT EXISTS alerts_log (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    sent_at   TEXT NOT NULL,
                    channel   TEXT,
                    pair      TEXT,
                    direction TEXT,
                    confidence REAL,
                    status    TEXT DEFAULT 'sent',
                    error_msg TEXT
                );

                -- Execution log (paper + live orders)
                CREATE TABLE IF NOT EXISTS execution_log (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    placed_at     TEXT NOT NULL,
                    pair          TEXT,
                    direction     TEXT,
                    side          TEXT,
                    size_usd      REAL,
                    order_type    TEXT DEFAULT 'market',
                    price         REAL,
                    order_id      TEXT,
                    status        TEXT DEFAULT 'ok',
                    mode          TEXT DEFAULT 'paper',
                    error_msg     TEXT,
                    slippage_pct  REAL
                );
                CREATE INDEX IF NOT EXISTS idx_exec_pair ON execution_log(pair);
                CREATE INDEX IF NOT EXISTS idx_exec_ts   ON execution_log(placed_at);

                -- Agent decision log (autonomous agent cycle records)
                CREATE TABLE IF NOT EXISTS agent_log (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    logged_at        TEXT NOT NULL,
                    pair             TEXT NOT NULL,
                    direction        TEXT,
                    confidence       REAL,
                    claude_decision  TEXT,
                    claude_rationale TEXT,
                    action_taken     TEXT,
                    execution_result TEXT,
                    notes            TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_agent_pair ON agent_log(pair);
                CREATE INDEX IF NOT EXISTS idx_agent_ts   ON agent_log(logged_at);

                -- Arbitrage opportunities (spot spread + funding-rate carry)
                CREATE TABLE IF NOT EXISTS arb_opportunities (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    detected_at      TEXT NOT NULL,
                    pair             TEXT NOT NULL,
                    arb_type         TEXT NOT NULL,
                    buy_exchange     TEXT,
                    sell_exchange    TEXT,
                    gross_spread_pct REAL,
                    net_spread_pct   REAL,
                    buy_price        REAL,
                    sell_price       REAL,
                    signal           TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_arb_pair ON arb_opportunities(pair);
                CREATE INDEX IF NOT EXISTS idx_arb_ts   ON arb_opportunities(detected_at);
            """)
            conn.commit()

            # ── Migrate existing feedback_log tables — add new columns if missing ──
            # Required for databases created before Phase 2 (F1 + F4 columns).
            # ALTER TABLE IF NOT EXISTS column is not valid SQLite syntax; use PRAGMA check.
            _ALLOWED_MIGRATE_TABLES = {"feedback_log", "backtest_trades", "paper_trades",
                                       "positions", "execution_log", "daily_signals"}
            def _add_col(tbl, col, col_def):
                if tbl not in _ALLOWED_MIGRATE_TABLES:
                    raise ValueError(f"[DB] _add_col: table '{tbl}' not in migration whitelist")
                existing = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
                if col not in existing:
                    conn.execute(f'ALTER TABLE "{tbl}" ADD COLUMN "{col}" {col_def}')

            for col, dfn in [
                ('actual_exit',    'REAL'),
                ('actual_pnl_pct', 'REAL'),
                ('outcome',        'TEXT'),
                ('was_correct',    'INTEGER'),
                ('resolved_at',    'TEXT'),
                ('vote_trend',     'REAL'),
                ('vote_momentum',  'REAL'),
                ('vote_meanrev',   'REAL'),
                ('vote_sentiment', 'REAL'),
                ('vote_risk',      'REAL'),
                ('vote_lgbm',      'REAL'),
                # F-SNAP: indicator snapshots for LightGBM retraining
                ('snap_rsi',        'REAL'),
                ('snap_macd_hist',  'REAL'),
                ('snap_bb_pos',     'REAL'),
                ('snap_adx',        'REAL'),
                ('snap_stoch_k',    'REAL'),
                ('snap_volume_ok',  'INTEGER'),
                ('snap_regime',     'TEXT'),
                # P8: price at signal time — enables accurate retro-evaluation months later
                ('price_at_signal', 'REAL'),
            ]:
                _add_col('feedback_log', col, dfn)

            # T3-11: slippage tracking column in execution_log
            _add_col('execution_log', 'slippage_pct', 'REAL')

            # IC + WFE metrics table  (#36)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_metrics (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    computed_at TEXT NOT NULL,
                    pair        TEXT NOT NULL,
                    timeframe   TEXT,
                    ic_30d      REAL,
                    ic_7d       REAL,
                    wfe         REAL,
                    win_rate    REAL,
                    sample_n    INTEGER
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sm_pair_ts ON signal_metrics(pair, computed_at DESC)"
            )

            # IC history table (#36 — Spearman IC per lookback window)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ic_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    computed_at  TEXT NOT NULL,
                    ic_value     REAL,
                    ic_pvalue    REAL,
                    n_samples    INTEGER,
                    lookback_days INTEGER
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ic_history_ts ON ic_history(computed_at DESC)"
            )

            # Bayesian weights table (#49)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bayesian_weights (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    updated_at TEXT NOT NULL,
                    indicator  TEXT NOT NULL,
                    weight     REAL,
                    alpha      REAL,
                    beta       REAL,
                    wins       INTEGER,
                    losses     INTEGER
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_bw_indicator ON bayesian_weights(indicator, updated_at DESC)"
            )

            # Walk-forward optimization cache (#51)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wfo_cache (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    computed_at         TEXT NOT NULL,
                    lookback_days       INTEGER,
                    n_windows           INTEGER,
                    optimal_threshold   REAL,
                    avg_oos_win_rate    REAL,
                    window_results_json TEXT
                )
            """)

            # P&L tracking table (Batch 8 — Enhanced Pair P&L Tracking)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pnl_tracking (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair          TEXT NOT NULL,
                    entry_price   REAL NOT NULL,
                    entry_signal  TEXT NOT NULL,
                    entry_time    TEXT NOT NULL,
                    confidence    REAL,
                    exit_price    REAL,
                    exit_time     TEXT,
                    pnl_pct       REAL,
                    holding_hours REAL,
                    status        TEXT DEFAULT 'open'
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pnl_pair ON pnl_tracking(pair, status)"
            )

            # Backtest schema migration — add columns added after initial release
            _add_col('backtest_trades', 'gross_pnl_pct',  'REAL')
            _add_col('backtest_trades', 'fee_usd',        'REAL')
            _add_col('backtest_trades', 'slippage_usd',   'REAL')
            _add_col('backtest_trades', 'pos_pct',        'REAL')

            # BUG-02: commit ALTER TABLE additions before index creation so a
            # crash between the two steps does not leave both uncommitted
            conn.commit()

            # Index for resolved lookups (may already exist on fresh DBs from executescript)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fb_resolved ON feedback_log(resolved_at)"
            )
            # Compound index for pair-level resolved queries (feedback loop performance)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fb_pair_resolved ON feedback_log(pair, resolved_at)"
            )
            # PERF: compound indexes for resolve + win-rate queries (covers resolved_at IS NULL + timestamp <)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fb_resolve_scan ON feedback_log(resolved_at, timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fb_pair_dir_resolved ON feedback_log(pair, direction, resolved_at)"
            )
            # PERF: compound indexes on other hot tables
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_pair_dir_ts ON daily_signals(pair, direction, scan_timestamp DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_exec_pair_ts ON execution_log(pair, placed_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_arb_pair_ts ON arb_opportunities(pair, detected_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_pair_ts ON agent_log(pair, logged_at DESC)"
            )
            conn.commit()
        finally:
            if conn is not None:
                conn.close()


# ──────────────────────────────────────────────
# MIGRATION  (CSV/JSON → SQLite, one-time)
# ──────────────────────────────────────────────
MASTER_COLS = [
    'scan_timestamp', 'pair', 'price_usd', 'confidence_avg_pct', 'direction',
    'strategy_bias', 'mtf_alignment', 'high_conf', 'fng_value', 'fng_category',
    'entry', 'exit', 'stop_loss', 'risk_pct', 'position_size_usd',
    'position_size_pct', 'risk_mode', 'corr_with_btc', 'corr_adjusted_size_pct',
    'regime', 'sr_status', 'circuit_breaker_triggered', 'circuit_breaker_drawdown_pct',
    'scan_sec',
]


_VALID_TABLES = frozenset([
    'feedback_log', 'daily_signals', 'backtest_trades', 'paper_trades',
    'positions', 'dynamic_weights', 'weights_log', 'scan_cache',
    'scan_status', 'alerts_log', 'execution_log', 'arb_opportunities',
    'agent_log', 'pnl_tracking',
])

# Pre-built COUNT(*) queries per table — eliminates f-string SQL construction (SEC-CRITICAL-01).
# SQLite does not support parameterised table names so this dict is the correct safe pattern.
_TABLE_COUNT_SQL: dict[str, str] = {t: f"SELECT COUNT(*) FROM {t}" for t in _VALID_TABLES}


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    if table not in _VALID_TABLES:
        raise ValueError(f"_row_count: unknown table '{table}'")
    return conn.execute(_TABLE_COUNT_SQL[table]).fetchone()[0]


def migrate_csv_to_db():
    """
    Import existing CSV/JSON data into SQLite.
    Idempotent: each table is only populated if it is currently empty.
    Original files are NOT deleted — they serve as a backup.

    BUG-R01: wrap entire migration in _write_lock so that the
    'check row count → write' sequence is atomic.  Without the outer lock
    two threads could both see count==0 and both import, doubling all rows.
    The inner with _write_lock blocks are removed (would deadlock a non-reentrant lock).
    """
    with _write_lock:
        conn = _get_conn()
        try:
            # ── feedback_log.csv ──────────────────────
            if os.path.exists("feedback_log.csv") and _row_count(conn, "feedback_log") == 0:
                try:
                    df = pd.read_csv("feedback_log.csv", encoding="utf-8")
                    if not df.empty:
                        # BUG-21: filter to known schema columns to avoid OperationalError
                        # on CSVs with extra/legacy columns
                        known_cols = [r[1] for r in conn.execute("PRAGMA table_info(feedback_log)").fetchall()]
                        df = df[[c for c in df.columns if c in known_cols]]
                        df.to_sql("feedback_log", conn, if_exists="append", index=False)
                        conn.commit()
                        logger.info("DB migration: imported %d rows → feedback_log", len(df))
                except Exception as e:
                    logger.warning("DB migration feedback_log failed: %s", e)

            # ── daily_signals_master.csv ──────────────
            if os.path.exists("daily_signals_master.csv") and _row_count(conn, "daily_signals") == 0:
                try:
                    df = pd.read_csv("daily_signals_master.csv", encoding="utf-8")
                    if not df.empty:
                        # Keep only known columns; fill missing with None
                        for col in MASTER_COLS:
                            if col not in df.columns:
                                df[col] = None
                        df = df[MASTER_COLS]
                        if 'high_conf' in df.columns:
                            df['high_conf'] = df['high_conf'].apply(
                                lambda x: 1 if str(x).strip().lower() in ('true', '1', 'yes') else 0
                            )
                        if 'circuit_breaker_triggered' in df.columns:
                            df['circuit_breaker_triggered'] = df['circuit_breaker_triggered'].apply(
                                lambda x: 1 if str(x).strip().lower() in ('true', '1', 'yes') else 0
                            )
                        df.to_sql("daily_signals", conn, if_exists="append", index=False)
                        conn.commit()
                        logger.info("DB migration: imported %d rows → daily_signals", len(df))
                except Exception as e:
                    logger.warning("DB migration daily_signals failed: %s", e)

            # ── backtest_summary.csv ──────────────────
            if os.path.exists("backtest_summary.csv") and _row_count(conn, "backtest_trades") == 0:
                try:
                    df = pd.read_csv("backtest_summary.csv", encoding="utf-8")
                    if not df.empty:
                        df['run_id'] = 'migrated_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
                        # BUG-21: filter to known schema columns
                        known_cols = [r[1] for r in conn.execute("PRAGMA table_info(backtest_trades)").fetchall()]
                        df = df[[c for c in df.columns if c in known_cols]]
                        df.to_sql("backtest_trades", conn, if_exists="append", index=False)
                        conn.commit()
                        logger.info("DB migration: imported %d rows → backtest_trades", len(df))
                except Exception as e:
                    logger.warning("DB migration backtest_trades failed: %s", e)

            # ── paper_trades_log.csv ──────────────────
            if os.path.exists("paper_trades_log.csv") and _row_count(conn, "paper_trades") == 0:
                try:
                    df = pd.read_csv("paper_trades_log.csv", encoding="utf-8")
                    if not df.empty:
                        # BUG-21: filter to known schema columns
                        known_cols = [r[1] for r in conn.execute("PRAGMA table_info(paper_trades)").fetchall()]
                        df = df[[c for c in df.columns if c in known_cols]]
                        df.to_sql("paper_trades", conn, if_exists="append", index=False)
                        conn.commit()
                        logger.info("DB migration: imported %d rows → paper_trades", len(df))
                except Exception as e:
                    logger.warning("DB migration paper_trades failed: %s", e)

            # ── positions.json ────────────────────────
            if os.path.exists("positions.json") and _row_count(conn, "positions") == 0:
                try:
                    with open("positions.json", encoding="utf-8") as f:
                        positions = json.load(f)
                    if positions:
                        cols = {'pair', 'direction', 'entry', 'target', 'stop',
                                'entry_time', 'size_pct', 'current_pnl_pct'}
                        rows = []
                        for pair, pos in positions.items():
                            row = {'pair': pair}
                            row.update({k: pos.get(k) for k in cols if k != 'pair'})
                            rows.append(row)
                        pd.DataFrame(rows).to_sql("positions", conn, if_exists="append", index=False)
                        conn.commit()
                        logger.info("DB migration: imported %d positions → positions", len(rows))
                except Exception as e:
                    logger.warning("DB migration positions failed: %s", e)

            # ── dynamic_weights.json ──────────────────
            if os.path.exists("dynamic_weights.json") and _row_count(conn, "dynamic_weights") == 0:
                try:
                    with open("dynamic_weights.json", encoding="utf-8") as f:
                        w = json.load(f)
                    conn.execute(
                        "INSERT INTO dynamic_weights (saved_at, source, weights_json) VALUES (?,?,?)",
                        (datetime.now(timezone.utc).isoformat(), 'migrated', json.dumps(w))
                    )
                    conn.commit()
                    logger.info("DB migration: imported dynamic_weights.json → dynamic_weights")
                except Exception as e:
                    logger.warning("DB migration dynamic_weights failed: %s", e)

            # ── weights_log.csv ───────────────────────
            if os.path.exists("weights_log.csv") and _row_count(conn, "weights_log") == 0:
                try:
                    df = pd.read_csv("weights_log.csv", encoding="utf-8")
                    if not df.empty:
                        df.to_sql("weights_log", conn, if_exists="append", index=False)
                        conn.commit()
                        logger.info("DB migration: imported %d rows → weights_log", len(df))
                except Exception as e:
                    logger.warning("DB migration weights_log failed: %s", e)

            # ── scan_results_cache.json ───────────────
            if os.path.exists("scan_results_cache.json") and _row_count(conn, "scan_cache") == 0:
                try:
                    with open("scan_results_cache.json", encoding="utf-8") as f:
                        results = json.load(f)
                    if results:
                        conn.execute(
                            "INSERT INTO scan_cache (id, saved_at, results_json) VALUES (1,?,?)",
                            (datetime.now(timezone.utc).isoformat(), json.dumps(results, default=str))
                        )
                        conn.commit()
                    logger.info("DB migration: imported scan_results_cache.json → scan_cache")
                except Exception as e:
                    logger.warning("DB migration scan_cache failed: %s", e)
        finally:
            try:
                conn.close()
            except Exception as _db_close_err:
                logger.debug("[DB] init conn close failed (non-fatal): %s", _db_close_err)


# ──────────────────────────────────────────────
# FEEDBACK LOG
# ──────────────────────────────────────────────
def log_feedback(pair: str, direction: str, entry: float,
                 exit_: float, confidence: float,
                 agent_votes: dict = None,
                 indicator_snaps: dict = None):
    """Append one signal to the feedback log. Thread-safe.

    Args:
        agent_votes:      dict with keys 'trend','momentum','meanrev','sentiment','risk','lgbm'
                          (F4) — used to compute per-agent accuracy weights.
        indicator_snaps:  dict with keys 'rsi','macd_hist','bb_pos','adx','stoch_k',
                          'volume_ok','regime' (F-SNAP) — stored for LightGBM retraining.
                          All values optional; missing keys stored as NULL.
    """
    v = agent_votes or {}
    s = indicator_snaps or {}
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO feedback_log "
                "(timestamp, pair, direction, entry, exit_target, confidence,"
                " vote_trend, vote_momentum, vote_meanrev, vote_sentiment, vote_risk, vote_lgbm,"
                " snap_rsi, snap_macd_hist, snap_bb_pos, snap_adx, snap_stoch_k,"
                " snap_volume_ok, snap_regime)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                # BUG-09: use UTC-aware timestamp so resolution cutoff comparisons are correct
                (datetime.now(timezone.utc).isoformat(), pair, direction, float(entry or 0),
                 float(exit_ or 0), float(confidence or 0),
                 v.get('trend'), v.get('momentum'), v.get('meanrev'),
                 v.get('sentiment'), v.get('risk'), v.get('lgbm'),
                 s.get('rsi'), s.get('macd_hist'), s.get('bb_pos'),
                 s.get('adx'), s.get('stoch_k'),
                 int(bool(s.get('volume_ok'))) if s.get('volume_ok') is not None else None,
                 s.get('regime'))
            )
            conn.commit()
        finally:
            conn.close()


def get_feedback_df(limit: int = None) -> pd.DataFrame:
    """Return feedback_log as a DataFrame.

    Args:
        limit: if provided, return only the most-recent N rows (ordered by
               timestamp DESC, then re-sorted ASC for callers that expect
               chronological order).  Avoids loading 12 000+ rows when only
               the recent tail is needed (e.g. UI performance tab).
    """
    conn = _get_conn()
    try:
        if limit is not None and limit > 0:
            # Fetch the N most-recent rows, then return in ascending order
            df = pd.read_sql_query(
                "SELECT * FROM ("
                "  SELECT * FROM feedback_log ORDER BY timestamp DESC LIMIT ?"
                ") ORDER BY timestamp ASC",
                conn,
                params=(int(limit),),
            )
        else:
            df = pd.read_sql_query("SELECT * FROM feedback_log ORDER BY timestamp ASC", conn)
    finally:
        conn.close()
    return df


def get_resolved_feedback_df(days: int = 90) -> pd.DataFrame:
    """Return feedback rows where actual outcome has been resolved, within last N days.

    Used by F2 (update_dynamic_weights) and F6/F7 (drift detection).
    """
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM feedback_log "
            "WHERE resolved_at IS NOT NULL AND actual_pnl_pct IS NOT NULL "
            "AND timestamp > datetime('now', ?) "
            "ORDER BY timestamp ASC",
            conn,
            # BUG-19: cast to int to prevent float producing invalid SQLite modifier like "-90.0 days"
            params=(f"-{int(days)} days",),
        )
    finally:
        conn.close()
    return df


def resolve_feedback_outcomes(fetch_price_fn, hold_days: int = 14, batch: int = 50) -> int:
    """Resolve unresolved feedback_log rows whose hold period has elapsed.

    For each unresolved row older than hold_days, fetches the actual close price
    at entry_time + hold_days via fetch_price_fn, then writes back:
    actual_exit, actual_pnl_pct, outcome ('win'/'loss'), was_correct (1/0), resolved_at.

    This converts the dead signal log into a live training dataset (F1).

    Args:
        fetch_price_fn: callable(pair: str, since_ms: int) -> float | None
                        Must return the close price at or after since_ms.
        hold_days:      Days to wait before resolution (should match BACKTEST_HOLD_DAYS).
        batch:          Max rows processed per call to avoid long API waits.

    Returns:
        Number of rows successfully resolved in this call.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=hold_days)).isoformat()
    # BUG-R05: convert sqlite3.Row objects to plain dicts BEFORE closing the
    # connection.  sqlite3.Row subscript access on a closed connection is
    # implementation-defined and can raise ProgrammingError in some versions.
    conn = _get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, pair, direction, entry, timestamp FROM feedback_log "
            "WHERE resolved_at IS NULL AND entry IS NOT NULL AND entry > 0 "
            "AND timestamp < ? ORDER BY timestamp ASC LIMIT ?",
            (cutoff, batch),
        ).fetchall()]
    finally:
        conn.close()

    if not rows:
        return 0

    # PERF-25: fetch prices concurrently — was sequential (N × API latency)
    def _fetch_one(row):
        try:
            ts = datetime.fromisoformat(row['timestamp'])
            since_ms = int((ts + timedelta(days=hold_days)).timestamp() * 1000)
            price = fetch_price_fn(row['pair'], since_ms)
            return row, price
        except Exception as _fe:
            logger.warning("resolve_feedback_outcomes fetch failed for row %s: %s",
                           row.get('id', '?'), _fe)
            return row, None

    with _cf.ThreadPoolExecutor(max_workers=8) as _ex:
        _fetch_results = list(_ex.map(_fetch_one, rows))

    # PERF-25: collect all updates, then single executemany() — no per-row DB write
    now_iso = datetime.now(timezone.utc).isoformat()
    updates = []
    for row, actual_price in _fetch_results:
        try:
            if actual_price is None:
                continue
            entry = row['entry']
            direction = str(row['direction'] or '')
            if 'BUY' in direction.upper():
                pnl_pct = (actual_price - entry) / entry * 100
            elif 'SELL' in direction.upper():
                pnl_pct = (entry - actual_price) / entry * 100
            else:
                continue  # NEUTRAL/LOW VOL — skip
            updates.append((
                float(actual_price), round(float(pnl_pct), 4),
                'win' if pnl_pct > 0 else 'loss',
                1 if pnl_pct > 0 else 0,
                now_iso,
                row['id'],
            ))
        except Exception as e:
            # BUG-28: use .get() to avoid KeyError inside exception handler
            logger.warning("resolve_feedback_outcomes failed for row %s: %s", row.get('id', '?'), e)

    if not updates:
        return 0

    with _write_lock:
        conn2 = _get_conn()
        try:
            conn2.executemany(
                "UPDATE feedback_log "
                "SET actual_exit=?, actual_pnl_pct=?, outcome=?, "
                "    was_correct=?, resolved_at=? "
                # BUG-07/08: AND resolved_at IS NULL prevents double-resolution
                "WHERE id=? AND resolved_at IS NULL",
                updates,
            )
            conn2.commit()
        finally:
            conn2.close()

    return len(updates)


def quick_resolve_feedback(fetch_ohlcv_fn, hold_hours: int = 72, batch: int = 100) -> int:
    """Accelerated feedback resolution using 3-day directional check instead of 14-day hold.

    Cuts the feedback dead zone from 14 days down to hold_hours (default 72h = 3 days).
    Resolves signals where hold_hours have elapsed by fetching a 1h OHLCV candle close
    price at entry_time + hold_hours and computing directional PnL.

    This is a 'quick win' resolution pass — full hold_days resolution still runs separately.
    Both can coexist: quick_resolve runs first, resolve_feedback_outcomes skips already-resolved rows.

    Args:
        fetch_ohlcv_fn: callable(pair: str, since_ms: int, tf: str) -> list of OHLCV candles
                        Each candle = [timestamp_ms, open, high, low, close, volume].
                        Should return the first candle at or after since_ms.
        hold_hours:     Hours to wait before 3-day resolution check (default 72).
        batch:          Max rows processed per call.

    Returns:
        Number of rows resolved in this call.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hold_hours)).isoformat()
    conn = _get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, pair, direction, entry, timestamp FROM feedback_log "
            "WHERE resolved_at IS NULL AND entry IS NOT NULL AND entry > 0 "
            "AND timestamp < ? ORDER BY timestamp ASC LIMIT ?",
            (cutoff, batch),
        ).fetchall()]
    finally:
        conn.close()

    if not rows:
        return 0

    # PERF: collect all updates first, then commit in one executemany() call
    # (was N individual UPDATE+commit per row = N+1 DB round-trips; now 1 round-trip)
    now_iso = datetime.now(timezone.utc).isoformat()
    updates = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')
                                        if row['timestamp'].endswith('Z')
                                        else row['timestamp'])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            target_ms = int((ts + timedelta(hours=hold_hours)).timestamp() * 1000)
            candles = fetch_ohlcv_fn(row['pair'], target_ms, '1h')
            if not candles:
                continue
            # Use close price of first candle at or after hold_hours mark
            actual_price = float(candles[0][4])  # index 4 = close

            entry = float(row['entry'])
            direction = str(row['direction'] or '')
            if 'BUY' in direction.upper():
                pnl_pct = (actual_price - entry) / entry * 100
            elif 'SELL' in direction.upper():
                pnl_pct = (entry - actual_price) / entry * 100
            else:
                continue  # NEUTRAL/LOW VOL — skip

            updates.append((
                actual_price, round(float(pnl_pct), 4),
                'win' if pnl_pct > 0 else 'loss',
                1 if pnl_pct > 0 else 0,
                now_iso,
                row['id'],
            ))
        except Exception as e:
            logger.warning("quick_resolve_feedback failed for row %s: %s", row.get('id'), e)

    if not updates:
        return 0

    with _write_lock:
        conn2 = _get_conn()
        try:
            conn2.executemany(
                "UPDATE feedback_log "
                "SET actual_exit=?, actual_pnl_pct=?, outcome=?, "
                "    was_correct=?, resolved_at=? "
                # BUG-07/08: AND resolved_at IS NULL prevents double-resolution
                "WHERE id=? AND resolved_at IS NULL",
                updates,
            )
            conn2.commit()
        finally:
            conn2.close()

    return len(updates)


def get_agent_accuracy_weights(days: int = 30) -> dict:
    """Compute per-agent directional accuracy over the last N days from resolved feedback.

    An agent vote is 'correct' if its sign matches the actual trade outcome:
      - vote > 0 (bullish) AND was_correct == 1  → correct (BUY signal won)
      - vote < 0 (bearish) AND was_correct == 1  → correct (SELL signal won = price fell)
      - vote == 0                                 → excluded from accuracy calc

    NOTE: was_correct == 1 means pnl_pct > 0 (trade profited), regardless of direction.
    A bearish (SELL) agent is correct when the SELL trade makes money (was_correct==1),
    NOT when the trade loses (was_correct==0). The old inverted logic rewarded bearish
    agents for bad calls, poisoning the entire feedback loop (BUG-DB01).

    Returns:
        dict: {'trend': 0.65, 'momentum': 0.52, 'meanrev': 0.48, 'sentiment': 0.61,
               'risk': 0.55, 'lgbm': 0.58}
        Falls back to 0.5 (equal weight) if <30 resolved rows available.
    """
    agents = ['trend', 'momentum', 'meanrev', 'sentiment', 'risk', 'lgbm']
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT vote_trend, vote_momentum, vote_meanrev, vote_sentiment, vote_risk, vote_lgbm, "
            "       was_correct, direction FROM feedback_log "
            "WHERE resolved_at IS NOT NULL AND was_correct IS NOT NULL "
            "AND timestamp > datetime('now', ?)",
            conn,
            # BUG-20: cast to int to prevent float producing invalid SQLite modifier
            params=(f"-{int(days)} days",),
        )
    finally:
        conn.close()

    if len(df) < 30:
        return {a: 0.5 for a in agents}

    result = {}
    for agent in agents:
        col = f'vote_{agent}'
        if col not in df.columns:
            result[agent] = 0.5
            continue
        sub = df[[col, 'was_correct', 'direction']].dropna()
        sub = sub[sub[col] != 0]  # exclude neutral/abstain votes
        if len(sub) < 10:
            result[agent] = 0.5
            continue
        # BUG-11: vote sign must match trade direction — a bullish vote is correct
        # only when a BUY trade wins; a bearish vote is correct only when a SELL wins.
        # The old two-branch OR both required was_correct==1, making vote sign irrelevant
        # and giving all agents identical accuracy scores.
        is_buy  = sub['direction'].str.contains('BUY',  na=False, case=False)
        is_sell = sub['direction'].str.contains('SELL', na=False, case=False)
        correct = (
            ((sub[col] > 0) & (sub['was_correct'] == 1) & is_buy) |
            ((sub[col] < 0) & (sub['was_correct'] == 1) & is_sell)
        )
        result[agent] = round(float(correct.mean()), 4)

    return result


# ──────────────────────────────────────────────
# DAILY SIGNALS (master log)
# ──────────────────────────────────────────────
def append_to_master(results: list):
    """Append a list of scan result dicts to the daily_signals table."""
    if not results:
        return
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    rows = []
    for r in results:
        cb = r.get('circuit_breaker', {})
        rows.append({
            'scan_timestamp':               ts,
            'pair':                         r.get('pair'),
            'price_usd':                    r.get('price_usd'),
            'confidence_avg_pct':           r.get('confidence_avg_pct'),
            'direction':                    r.get('direction'),
            'strategy_bias':                r.get('strategy_bias'),
            'mtf_alignment':                r.get('mtf_alignment'),
            'high_conf':                    1 if r.get('high_conf') else 0,
            'fng_value':                    r.get('fng_value'),
            'fng_category':                 r.get('fng_category'),
            'entry':                        r.get('entry'),
            'exit':                         r.get('exit'),
            'stop_loss':                    r.get('stop_loss'),
            'risk_pct':                     r.get('risk_pct'),
            'position_size_usd':            r.get('position_size_usd'),
            'position_size_pct':            r.get('position_size_pct'),
            'risk_mode':                    r.get('risk_mode'),
            'corr_with_btc':                r.get('corr_with_btc'),
            'corr_adjusted_size_pct':       r.get('corr_adjusted_size_pct'),
            'regime':                       r.get('regime'),
            'sr_status':                    r.get('sr_status'),
            'circuit_breaker_triggered':    1 if cb.get('triggered', False) else 0,
            'circuit_breaker_drawdown_pct': cb.get('drawdown_pct', 0.0),
            'scan_sec':                     r.get('scan_sec'),
        })
    with _write_lock:
        conn = _get_conn()
        try:
            # BUG-23: restrict to MASTER_COLS so extra keys in result dicts never
            # cause OperationalError from unknown columns
            df = pd.DataFrame(rows)
            df = df[[c for c in MASTER_COLS if c in df.columns]]
            df.to_sql("daily_signals", conn, if_exists="append", index=False)
            conn.commit()
        except Exception as e:
            logger.error("append_to_master failed: %s", e)
            raise
        finally:
            conn.close()


def get_signals_df(limit: int = 500) -> pd.DataFrame:
    """Return recent daily signals as a DataFrame sorted by scan_timestamp ASC.

    Args:
        limit: Maximum number of rows returned (default 500, newest first then re-sorted ASC).
               Pass 0 to return all rows (use only for maintenance/migration tasks).
    """
    conn = _get_conn()
    try:
        if limit and limit > 0:
            # Fetch newest N rows then sort ascending so callers see chronological order
            df = pd.read_sql_query(
                "SELECT * FROM daily_signals ORDER BY id DESC LIMIT ?",
                conn,
                params=(int(limit),),
            )
            df = df.sort_values("scan_timestamp", ascending=True).reset_index(drop=True)
        else:
            df = pd.read_sql_query("SELECT * FROM daily_signals ORDER BY scan_timestamp ASC", conn)
    finally:
        conn.close()
    return df


# ──────────────────────────────────────────────
# BACKTEST TRADES
# ──────────────────────────────────────────────
_BACKTEST_COLS = [
    'run_id', 'timestamp', 'pair', 'direction', 'entry', 'exit', 'exit_reason',
    'pnl_pct', 'pnl_usd', 'pos_pct', 'gross_pnl_pct', 'fee_usd', 'slippage_usd',
]


def save_backtest_trades(trades: list, run_id: str):
    """Persist a full backtest run's trades. run_id groups them together."""
    if not trades:
        return
    df = pd.DataFrame(trades)
    df['run_id'] = run_id
    # BUG-22: filter to known schema columns to prevent OperationalError on extra keys
    df = df[[c for c in _BACKTEST_COLS if c in df.columns]]
    with _write_lock:
        conn = _get_conn()
        try:
            df.to_sql("backtest_trades", conn, if_exists="append", index=False)
            conn.commit()
        except Exception as e:
            logger.error("save_backtest_trades failed: %s", e)
            raise
        finally:
            conn.close()


def get_backtest_df(run_id: str = None) -> pd.DataFrame:
    """
    Return trades for a specific run_id, or the latest run if run_id is None.
    Drops the auto-added 'id' and 'run_id' columns so callers get the same
    shape as the old backtest_summary.csv.
    """
    conn = _get_conn()
    try:
        if run_id:
            df = pd.read_sql_query(
                "SELECT * FROM backtest_trades WHERE run_id=? ORDER BY id ASC",
                conn, params=[run_id]
            )
        else:
            row = conn.execute(
                "SELECT run_id FROM backtest_trades ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return pd.DataFrame()
            df = pd.read_sql_query(
                "SELECT * FROM backtest_trades WHERE run_id=? ORDER BY id ASC",
                conn, params=[row['run_id']]
            )
    finally:
        conn.close()
    return df.drop(columns=['id', 'run_id'], errors='ignore')


def get_all_backtest_runs() -> pd.DataFrame:
    """Returns a summary of every backtest run stored in the DB."""
    conn = _get_conn()
    try:
        df = pd.read_sql_query("""
            SELECT run_id,
                   COUNT(*)  AS trades,
                   MIN(timestamp) AS started_at,
                   ROUND(AVG(pnl_pct), 2) AS avg_pnl_pct,
                   SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) AS wins
            FROM backtest_trades
            GROUP BY run_id
            ORDER BY started_at DESC
        """, conn)
    finally:
        conn.close()
    return df


# ──────────────────────────────────────────────
# PAPER TRADES (closed positions log)
# ──────────────────────────────────────────────
def log_closed_trade(trade: dict):
    """Append one closed paper trade. Thread-safe."""
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT INTO paper_trades
                    (pair, entry_time, close_time, direction, entry, exit, pnl_pct, size_pct, reason)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                trade.get('pair'),       trade.get('entry_time'),
                trade.get('close_time'), trade.get('direction'),
                trade.get('entry'),      trade.get('exit'),
                trade.get('pnl_pct'),    trade.get('size_pct'),
                trade.get('reason')
            ))
            conn.commit()
        finally:
            conn.close()


def get_paper_trades_df() -> pd.DataFrame:
    conn = _get_conn()
    try:
        df = pd.read_sql_query("SELECT * FROM paper_trades ORDER BY close_time ASC", conn)
    finally:
        conn.close()
    return df.drop(columns=['id'], errors='ignore')


# ──────────────────────────────────────────────
# OPEN POSITIONS
# ──────────────────────────────────────────────
def load_positions() -> dict:
    """Return open positions as {pair: {direction, entry, target, stop, ...}}."""
    conn = _get_conn()
    try:
        df = pd.read_sql_query("SELECT * FROM positions", conn)
    finally:
        conn.close()
    if df.empty:
        return {}
    # PERF: set_index + to_dict is 10-50× faster than iterrows() for O(N) loops
    return df.set_index('pair').to_dict(orient='index')


def save_positions(positions: dict):
    """Overwrite the positions table atomically.

    BUG-R13: pd.DataFrame.to_sql() issues its own internal commit in pandas >= 2.0,
    which commits the manual BEGIN transaction early.  If to_sql then raises, the
    subsequent conn.rollback() can't undo the already-committed DELETE, leaving the
    positions table empty.  Fix: use conn.executemany() with raw SQL so DELETE and
    INSERTs share the same transaction without any auto-commit interference.
    """
    _POSITION_COLS = ['pair', 'direction', 'entry', 'target', 'stop',
                      'entry_time', 'size_pct', 'current_pnl_pct']
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM positions")
            if positions:
                rows_data = []
                for pair, pos in positions.items():
                    row = {'pair': pair}
                    row.update({k: v for k, v in pos.items() if k in _POSITION_COLS})
                    rows_data.append(row)
                if rows_data:
                    # Determine actual columns present across all rows
                    all_cols = list(dict.fromkeys(c for r in rows_data for c in r))
                    placeholders = ', '.join(['?'] * len(all_cols))
                    col_names = ', '.join(all_cols)
                    conn.executemany(
                        f"INSERT INTO positions ({col_names}) VALUES ({placeholders})",
                        [tuple(r.get(c) for c in all_cols) for r in rows_data]
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ──────────────────────────────────────────────
# DYNAMIC WEIGHTS
# ──────────────────────────────────────────────
def load_weights() -> dict:
    """Return the most recently saved indicator weights dict."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT weights_json FROM dynamic_weights ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row:
        try:
            return json.loads(row['weights_json'])
        except Exception as e:
            # BUG-14: log corrupt weights so operator is alerted, not silently degraded
            logger.error("load_weights: corrupt JSON in DB — returning empty weights: %s", e)
    return {}


def save_weights(weights: dict, source: str = 'manual'):
    """Append a new weights snapshot (keeps full version history)."""
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO dynamic_weights (saved_at, source, weights_json) VALUES (?,?,?)",
                (datetime.now(timezone.utc).isoformat(), source, json.dumps(weights))
            )
            conn.commit()
        finally:
            conn.close()


def clear_weights(seed_weights: dict = None):
    """Delete all weight history and optionally seed with a fresh snapshot.

    Args:
        seed_weights: If provided, inserts this dict as the new baseline weights
                      (source='reset'). Useful after a config reset.
    """
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM dynamic_weights")
            if seed_weights:
                conn.execute(
                    "INSERT INTO dynamic_weights (saved_at, source, weights_json) VALUES (?,?,?)",
                    (datetime.now(timezone.utc).isoformat(), 'reset', json.dumps(seed_weights))
                )
            conn.commit()
        finally:
            conn.close()


def get_weights_history() -> pd.DataFrame:
    """Return recent weight versions (id, saved_at, source)."""
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT id, saved_at, source FROM dynamic_weights ORDER BY id DESC LIMIT 50",
            conn
        )
    finally:
        conn.close()
    return df


# ──────────────────────────────────────────────
# WEIGHTS EVALUATION LOG
# ──────────────────────────────────────────────
def log_weights_eval(avg_pnl: float, accuracy_pct: float):
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO weights_log (timestamp, avg_pnl, accuracy_pct) VALUES (?,?,?)",
                (datetime.now(timezone.utc).isoformat(), float(avg_pnl), float(accuracy_pct))
            )
            conn.commit()
        finally:
            conn.close()





# ──────────────────────────────────────────────
# SCAN CACHE
# ──────────────────────────────────────────────
def _numpy_clean(obj):
    """Convert numpy types → native Python so json.dumps doesn't fail."""
    if isinstance(obj, np.integer):  return int(obj)
    if isinstance(obj, np.floating): return float(obj)
    if isinstance(obj, np.bool_):    return bool(obj)
    if isinstance(obj, np.ndarray):  return obj.tolist()
    return str(obj)


def write_scan_results(results: list):
    """Persist latest scan results (upsert into singleton row id=1)."""
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT INTO scan_cache (id, saved_at, results_json)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE
                    SET saved_at=excluded.saved_at,
                        results_json=excluded.results_json
            """, (datetime.now(timezone.utc).isoformat(), json.dumps(results, default=_numpy_clean)))
            conn.commit()
        finally:
            conn.close()


def read_scan_results() -> list:
    """Return the most recent scan results list, or [] if none."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT results_json FROM scan_cache WHERE id=1").fetchone()
    finally:
        conn.close()
    if row:
        try:
            return json.loads(row['results_json'])
        except Exception as e:
            # BUG-15: log corrupt scan cache so data loss is visible, not silently empty
            logger.error("read_scan_results: corrupt JSON in DB — returning []: %s", e)
    return []


# ──────────────────────────────────────────────
# SCAN STATUS
# ──────────────────────────────────────────────
def write_scan_status(running: bool, timestamp=None, error=None,
                      progress: float = 0, pair: str = ""):
    """Upsert scan progress state (singleton row id=1)."""
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT INTO scan_status (id, running, timestamp, error, progress, pair)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE
                    SET running=excluded.running,
                        timestamp=excluded.timestamp,
                        error=excluded.error,
                        progress=excluded.progress,
                        pair=excluded.pair
            """, (1 if running else 0, timestamp, error, float(progress), pair or ""))
            conn.commit()
        finally:
            conn.close()


def read_scan_status() -> dict:
    """Return current scan status dict."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM scan_status WHERE id=1").fetchone()
    finally:
        conn.close()
    if row:
        return {
            'running':   bool(row['running']),
            'timestamp': row['timestamp'],
            'error':     row['error'],
            'progress':  row['progress'],
            'pair':      row['pair'],
        }
    return {"running": False, "timestamp": None, "error": None, "progress": 0, "pair": ""}


# ──────────────────────────────────────────────
# DRAWDOWN CIRCUIT BREAKER
# ──────────────────────────────────────────────
def check_drawdown_circuit_breaker(portfolio_size: float,
                                   threshold_pct: float) -> dict:
    """
    Compute portfolio drawdown from the paper_trades table.
    Mirrors the logic in crypto_model_core.check_drawdown_circuit_breaker()
    but reads from SQLite instead of CSV.
    """
    base = {
        'triggered':    False,
        'drawdown_pct': 0.0,
        'threshold_pct': threshold_pct,
        'peak_equity':  portfolio_size,
    }
    try:
        df = get_paper_trades_df()
        if df.empty or 'pnl_pct' not in df.columns:
            return base
        df['pnl_pct'] = pd.to_numeric(df['pnl_pct'], errors='coerce').fillna(0)
        size = pd.to_numeric(
            df['size_pct'] if 'size_pct' in df.columns else pd.Series([0.0] * len(df), index=df.index),
            errors='coerce'
        # BUG-17: fillna(0) not fillna(10) — fabricating 10% size for NULL rows overstates
        # equity swings and can prevent the circuit breaker from triggering when it should
        ).fillna(0.0)
        pnl_usd      = df['pnl_pct'] / 100 * (portfolio_size * size / 100)
        equity_curve = portfolio_size + pnl_usd.cumsum()
        peak         = equity_curve.cummax()
        dd_pct       = ((equity_curve - peak) / peak * 100).iloc[-1]
        return {
            'triggered':    bool(dd_pct < -threshold_pct),
            'drawdown_pct': round(float(dd_pct), 2),
            'threshold_pct': threshold_pct,
            'peak_equity':  round(float(peak.iloc[-1]), 2),
        }
    except Exception as e:
        logger.warning("Circuit breaker check failed: %s", e)
        return base


# ──────────────────────────────────────────────
# ALERTS AUDIT LOG
# ──────────────────────────────────────────────
def log_alert_sent(channel: str, pair: str, direction: str,
                   confidence: float, status: str = 'sent', error_msg: str = None):
    """Record that an alert was dispatched (or failed)."""
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT INTO alerts_log (sent_at, channel, pair, direction, confidence, status, error_msg)
                VALUES (?,?,?,?,?,?,?)
            """, (datetime.now(timezone.utc).isoformat(), channel, pair, direction,
                  float(confidence or 0), status, error_msg))
            conn.commit()
        finally:
            conn.close()


def get_alerts_log_df() -> pd.DataFrame:
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM alerts_log ORDER BY sent_at DESC LIMIT 500", conn
        )
    finally:
        conn.close()
    return df.drop(columns=['id'], errors='ignore')


# ──────────────────────────────────────────────
# EXECUTION LOG  (paper + live orders)
# ──────────────────────────────────────────────
def log_execution(placed_at: str, pair: str, direction: str, side: str,
                  size_usd: float, order_type: str, price: float,
                  order_id: str, status: str, mode: str,
                  error_msg: str = None, slippage_pct: float = None):
    """Append one execution record. Thread-safe."""
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT INTO execution_log
                    (placed_at, pair, direction, side, size_usd, order_type,
                     price, order_id, status, mode, error_msg, slippage_pct)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (placed_at, pair, direction, side, float(size_usd or 0),
                  order_type, float(price or 0), order_id or "",
                  status, mode, error_msg,
                  float(slippage_pct) if slippage_pct is not None else None))
            conn.commit()
        finally:
            conn.close()


def get_execution_log_df(limit: int = 200) -> pd.DataFrame:
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM execution_log ORDER BY placed_at DESC LIMIT ?",
            conn,
            params=(int(limit),),
        )
    finally:
        conn.close()
    return df.drop(columns=['id'], errors='ignore')


# ──────────────────────────────────────────────
# ARBITRAGE LOG
# ──────────────────────────────────────────────

def log_arb_opportunity(
    pair: str,
    arb_type: str,
    buy_exchange: str,
    sell_exchange: str,
    gross_spread_pct: float,
    net_spread_pct: float,
    buy_price: Optional[float],
    sell_price: Optional[float],
    signal: str,
):
    """Insert one arbitrage opportunity record. Thread-safe."""
    detected_at = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT INTO arb_opportunities
                    (detected_at, pair, arb_type, buy_exchange, sell_exchange,
                     gross_spread_pct, net_spread_pct, buy_price, sell_price, signal)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                detected_at, pair, arb_type, buy_exchange or "", sell_exchange or "",
                float(gross_spread_pct or 0), float(net_spread_pct or 0),
                float(buy_price) if buy_price is not None else None,
                float(sell_price) if sell_price is not None else None,
                signal,
            ))
            conn.commit()
        finally:
            conn.close()


def get_arb_opportunities_df(limit: int = 200, arb_type: str = None) -> pd.DataFrame:
    """
    Return recent arbitrage opportunities as a DataFrame.
    Optional arb_type filter: 'SPOT' or 'FUNDING'.
    """
    conn = _get_conn()
    try:
        if arb_type:
            df = pd.read_sql_query(
                "SELECT * FROM arb_opportunities WHERE arb_type=? ORDER BY detected_at DESC LIMIT ?",
                conn,
                params=(arb_type, int(limit)),
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM arb_opportunities ORDER BY detected_at DESC LIMIT ?",
                conn,
                params=(int(limit),),
            )
    finally:
        conn.close()
    return df.drop(columns=["id"], errors="ignore")


# ──────────────────────────────────────────────
# AGENT LOG
# ──────────────────────────────────────────────

def log_agent_decision(
    pair: str,
    direction: str,
    confidence: float,
    claude_decision: str,
    claude_rationale: str,
    action_taken: str,
    execution_result: str,
    notes: str = "",
):
    """Persist one agent decision cycle to agent_log. Thread-safe."""
    logged_at = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO agent_log
                       (logged_at, pair, direction, confidence, claude_decision,
                        claude_rationale, action_taken, execution_result, notes)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    logged_at, pair, direction, float(confidence or 0),
                    claude_decision, claude_rationale, action_taken,
                    execution_result, notes,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def get_agent_log_df(limit: int = 200) -> "pd.DataFrame":
    """Return recent agent decision records as a DataFrame."""
    conn = _get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM agent_log ORDER BY logged_at DESC LIMIT ?",
            conn,
            params=(int(limit),),
        )
    finally:
        conn.close()
    return df.drop(columns=["id"], errors="ignore")


def recent_agent_decisions(limit: int = 10) -> list[dict]:
    """C5 (Phase C plan §C5.3): return the most-recent agent decisions
    in the spec-shaped form for the AI Assistant page's Recent
    Decisions log.

    The spec proposed a fresh `agent_decisions` table; this codebase
    already has `agent_log` (added pre-redesign) which records the
    exact same fields under slightly different names. Rather than
    duplicate the schema + the per-cycle insert path, this helper
    queries `agent_log` and maps the columns to the spec shape:

        timestamp, pair, decision, confidence, rationale,
        status, cycle_id (optional)

    Mapping:
        logged_at        → timestamp
        pair             → pair
        claude_decision  → decision (approve/reject/skip/null)
        confidence       → confidence
        claude_rationale → rationale
        action_taken     → status (executed/dry_run/skipped/error)

    Returns a list of dicts (not a DataFrame) so the caller can render
    the rows directly without pandas-shape assumptions.
    """
    conn = _get_conn()
    try:
        cur = conn.execute(
            """SELECT logged_at, pair, claude_decision, confidence,
                      claude_rationale, action_taken, execution_result, notes
                 FROM agent_log
                 ORDER BY logged_at DESC
                 LIMIT ?""",
            (int(limit),),
        )
        rows = []
        for r in cur.fetchall():
            (logged_at, pair, decision, confidence, rationale,
             action_taken, execution_result, notes) = r
            rows.append({
                "timestamp":   logged_at,
                "pair":        pair,
                "decision":    (decision or "").lower() or None,
                "confidence":  float(confidence) if confidence is not None else None,
                "rationale":   rationale or "",
                "status":      action_taken or "",
                "execution":   execution_result or "",
                "notes":       notes or "",
            })
        return rows
    except Exception:
        return []
    finally:
        conn.close()


# ──────────────────────────────────────────────
# DB STATS  (used by Config Editor / health check)
# ──────────────────────────────────────────────
def get_db_stats() -> dict:
    """Return row counts for all tables — displayed in Config Editor."""
    # Whitelist table names — never interpolate user input into SQL (SEC-CRITICAL-01)
    _ALLOWED_TABLES = frozenset([
        'feedback_log', 'daily_signals', 'backtest_trades', 'paper_trades',
        'positions', 'dynamic_weights', 'weights_log', 'scan_cache',
        'scan_status', 'alerts_log', 'execution_log', 'arb_opportunities',
        'agent_log',
    ])
    conn = _get_conn()
    stats = {}
    try:
        for t in _ALLOWED_TABLES:
            try:
                # BUG-13: remove unsafe f-string fallback; _TABLE_COUNT_SQL covers all tables in _VALID_TABLES
                sql = _TABLE_COUNT_SQL.get(t)
                if sql is None:
                    logger.error("get_db_stats: no pre-built COUNT query for table %r — skipping", t)
                    stats[t] = 0
                    continue
                stats[t] = conn.execute(sql).fetchone()[0]
            except Exception:
                stats[t] = 0
    finally:
        conn.close()
    try:
        size_bytes = os.path.getsize(DB_FILE)
        stats['db_size_kb'] = round(size_bytes / 1024, 1)
    except Exception:
        stats['db_size_kb'] = 0
    return stats


# ──────────────────────────────────────────────
# SIGNAL ACCURACY  (for UI accuracy badge)
# ──────────────────────────────────────────────

def get_signal_win_rate(pair: str = None, direction: str = None,
                        days: int = 90) -> dict:
    """
    Compute historical win rate (accuracy) for signals, optionally filtered
    by pair and/or direction.  Powers the ui_components.signal_accuracy_badge_html().

    Returns:
        {'win_rate': float [0,1], 'sample_size': int, 'pair': pair, 'direction': direction}

    Win = trade where was_correct == 1 (pnl_pct > 0).
    Requires at least 5 resolved trades to return a meaningful estimate.
    Falls back to {'win_rate': 0.5, 'sample_size': 0} when insufficient data.
    """
    conn = _get_conn()
    try:
        # P1 audit fix — was f-string interpolating int(days) into the
        # WHERE clause. The int() cast made it injection-safe in
        # practice, but it deviated from the project's own SEC-CRITICAL-01
        # standard (parameterised via `?` placeholders). Use a `?`
        # placeholder + cast at parameter time so future maintainers
        # can't accidentally append a raw caller-supplied filter.
        conditions = [
            "resolved_at IS NOT NULL",
            "was_correct IS NOT NULL",
            "timestamp > datetime('now', ?)",
        ]
        params: list = [f"-{int(days)} days"]

        if pair:
            conditions.append("pair = ?")
            params.append(pair)

        if direction:
            # Match BUY/STRONG BUY or SELL/STRONG SELL
            conditions.append("direction LIKE ?")
            params.append(f"%{direction.upper()}%")

        where = " AND ".join(conditions)
        df = pd.read_sql_query(
            f"SELECT was_correct FROM feedback_log WHERE {where}",
            conn,
            params=params,
        )
    except Exception as exc:
        logger.warning("get_signal_win_rate failed: %s", exc)
        return {"win_rate": 0.5, "sample_size": 0, "pair": pair, "direction": direction}
    finally:
        conn.close()

    if len(df) < 5:
        return {"win_rate": 0.5, "sample_size": len(df), "pair": pair, "direction": direction}

    win_rate = float(df["was_correct"].mean())
    return {
        "win_rate":    round(win_rate, 4),
        "sample_size": len(df),
        "pair":        pair,
        "direction":   direction,
    }


def get_top_signals_by_accuracy(n: int = 5, days: int = 60) -> list[dict]:
    """
    Return the top N most accurate (pair, direction) combinations by win rate,
    requiring at least 10 resolved trades each.  Used in UI performance leaderboard.
    """
    conn = _get_conn()
    try:
        # P1 audit fix — was f-string interpolating int(days) and int(n).
        # Same SEC-CRITICAL-01 deviation as get_signal_win_rate above;
        # `?` placeholders fixes both the standard-compliance issue and
        # makes the query plan cacheable by SQLite.
        df = pd.read_sql_query(
            """
            SELECT pair,
                   direction,
                   COUNT(*) as total,
                   SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as wins
            FROM feedback_log
            WHERE resolved_at IS NOT NULL
              AND was_correct IS NOT NULL
              AND timestamp > datetime('now', ?)
            GROUP BY pair, direction
            HAVING total >= 10
            ORDER BY (wins * 1.0 / total) DESC
            LIMIT ?
            """,
            conn,
            params=[f"-{int(days)} days", int(n)],
        )
    except Exception:
        return []
    finally:
        conn.close()

    if df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        result.append({
            "pair":        row["pair"],
            "direction":   row["direction"],
            "win_rate":    round(float(row["wins"]) / float(row["total"]), 4),
            "sample_size": int(row["total"]),
        })
    return result


# ──────────────────────────────────────────────
# IC + WFE METRICS  (#36)
# ──────────────────────────────────────────────

def get_signal_metrics(pair: str, limit: int = 30) -> list[dict]:
    """Return last `limit` IC/WFE metric rows for a pair."""
    conn = None
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT computed_at, pair, timeframe, ic_30d, ic_7d, wfe, win_rate, sample_n
            FROM signal_metrics WHERE pair = ?
            ORDER BY computed_at DESC LIMIT ?
        """, (pair, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logging.warning("[DB] get_signal_metrics failed: %s", e)
        return []
    finally:
        if conn:
            conn.close()


# ──────────────────────────────────────────────
# IC (SPEARMAN) + WFE FUNCTIONS  (#36 — batch 3)
# ──────────────────────────────────────────────

def compute_and_save_ic(lookback_days: int = 30) -> dict:
    """
    Compute Information Coefficient (IC) using Spearman rank correlation between
    predicted signal direction (+1 BUY / -1 SELL / 0 HOLD) and actual 24h return.

    Queries feedback_log for the last `lookback_days` of resolved signals.
    Saves result to ic_history table.

    Returns:
        {"ic": float, "ic_pvalue": float, "n_samples": int, "lookback_days": int,
         "skill": "STRONG"|"MODERATE"|"WEAK"}
    """
    _default = {"ic": None, "ic_pvalue": None, "n_samples": 0,
                "lookback_days": lookback_days, "skill": "WEAK",
                "ic_note": "insufficient data"}

    conn = None
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT direction, confidence, actual_pnl_pct
            FROM feedback_log
            WHERE resolved_at IS NOT NULL
              AND actual_pnl_pct IS NOT NULL
              AND direction IS NOT NULL
              AND timestamp >= datetime('now', ?)
            ORDER BY timestamp DESC
            """,
            (f"-{int(lookback_days)} days",),
        ).fetchall()

        if len(rows) < 10:
            return _default

        # Map direction → predicted direction integer
        def _dir_to_int(d: str) -> int:
            d_up = str(d).upper()
            if "BUY" in d_up:  return 1
            if "SELL" in d_up: return -1
            return 0

        pred_dirs = [_dir_to_int(r["direction"]) for r in rows]
        act_rets   = [float(r["actual_pnl_pct"]) for r in rows]

        # Remove HOLDs (0) for clean correlation
        pairs_filtered = [(p, a) for p, a in zip(pred_dirs, act_rets) if p != 0]
        if len(pairs_filtered) < 10:
            return _default

        pred_clean = [p for p, _ in pairs_filtered]
        ret_clean  = [a for _, a in pairs_filtered]
        n = len(pred_clean)

        # Compute Spearman correlation
        if _SCIPY_AVAILABLE:
            ic_val, ic_p = _spearmanr(pred_clean, ret_clean)
            ic_val = float(ic_val) if ic_val is not None and not np.isnan(ic_val) else 0.0
            ic_p   = float(ic_p)   if ic_p   is not None and not np.isnan(ic_p)   else 1.0
        else:
            # Fallback: manual Spearman via rank correlation
            def _rank(lst):
                sorted_lst = sorted(enumerate(lst), key=lambda x: x[1])
                ranks = [0.0] * len(lst)
                for rank, (idx, _) in enumerate(sorted_lst, start=1):
                    ranks[idx] = float(rank)
                return ranks
            pred_ranks = _rank(pred_clean)
            ret_ranks  = _rank(ret_clean)
            n_r = len(pred_ranks)
            mean_p = sum(pred_ranks) / n_r
            mean_r = sum(ret_ranks) / n_r
            num    = sum((p - mean_p) * (r - mean_r) for p, r in zip(pred_ranks, ret_ranks))
            denom  = (
                sum((p - mean_p) ** 2 for p in pred_ranks) ** 0.5 *
                sum((r - mean_r) ** 2 for r in ret_ranks)  ** 0.5
            )
            ic_val = round(num / denom, 4) if denom > 1e-9 else 0.0
            ic_p   = 1.0  # Can't compute p-value without scipy

        ic_val = round(ic_val, 4)
        abs_ic = abs(ic_val)
        if abs_ic > 0.1:    skill = "STRONG"
        elif abs_ic > 0.05: skill = "MODERATE"
        else:               skill = "WEAK"

        # Persist to ic_history
        computed_at = datetime.now(timezone.utc).isoformat()
        with _write_lock:
            conn2 = _get_conn()
            try:
                conn2.execute(
                    "INSERT INTO ic_history (computed_at, ic_value, ic_pvalue, n_samples, lookback_days) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (computed_at, ic_val, ic_p, n, int(lookback_days)),
                )
                conn2.commit()
            finally:
                conn2.close()

        return {
            "ic": ic_val, "ic_pvalue": round(ic_p, 4), "n_samples": n,
            "lookback_days": int(lookback_days), "skill": skill, "ic_note": None,
        }
    except Exception as e:
        logger.warning("[DB] compute_and_save_ic failed: %s", e)
        return _default
    finally:
        if conn:
            conn.close()


def compute_wfe() -> dict:
    """
    Walk-Forward Efficiency (WFE) = IS Sharpe / OOS Sharpe.
    Uses last 90 days of backtest_trades, split 70% IS / 30% OOS.

    Returns:
        {"wfe": float, "is_sharpe": float, "oos_sharpe": float,
         "grade": "EXCELLENT"|"GOOD"|"FAIR"|"POOR"}
    """
    _default = {"wfe": None, "is_sharpe": None, "oos_sharpe": None, "grade": "POOR",
                "note": "insufficient data"}

    def _sharpe(returns: list) -> float:
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=float)
        std = float(np.std(arr, ddof=1))
        if std < 1e-9:
            return 0.0
        return round(float(np.mean(arr)) / std, 4)

    conn = None
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT pnl_pct, timestamp
            FROM backtest_trades
            WHERE pnl_pct IS NOT NULL
              AND timestamp >= datetime('now', '-90 days')
            ORDER BY timestamp ASC
            """
        ).fetchall()

        if len(rows) < 10:
            return _default

        all_pnl = [float(r["pnl_pct"]) for r in rows]
        n = len(all_pnl)
        split = max(1, int(n * 0.70))
        is_returns  = all_pnl[:split]
        oos_returns = all_pnl[split:]

        if len(is_returns) < 2 or len(oos_returns) < 2:
            return _default

        is_sharpe  = _sharpe(is_returns)
        oos_sharpe = _sharpe(oos_returns)

        if abs(is_sharpe) < 1e-9:
            wfe = 0.0
        else:
            wfe = round(oos_sharpe / is_sharpe, 4)

        if wfe > 0.9:   grade = "EXCELLENT"
        elif wfe > 0.7: grade = "GOOD"
        elif wfe > 0.5: grade = "FAIR"
        else:           grade = "POOR"

        return {
            "wfe": wfe, "is_sharpe": round(is_sharpe, 4),
            "oos_sharpe": round(oos_sharpe, 4), "grade": grade,
            "n_samples": n, "is_n": split, "oos_n": n - split,
        }
    except Exception as e:
        logger.warning("[DB] compute_wfe failed: %s", e)
        return _default
    finally:
        if conn:
            conn.close()


# ──────────────────────────────────────────────
# BAYESIAN WEIGHT RECALIBRATION  (#49)
# ──────────────────────────────────────────────

# Base weights for Bayesian prior (indicators and their prior win probability)
_BAYESIAN_BASE_WEIGHTS: dict = {
    "rsi":          0.20,
    "macd":         0.15,
    "supertrend":   0.15,
    "adx":          0.12,
    "funding_rate": 0.10,
    "on_chain":     0.10,
    "sentiment":    0.08,
    "volume":       0.10,
}


def bayesian_recalibrate_weights(prior_strength: float = 10.0) -> dict:
    """
    Update indicator weights using Bayesian Beta distribution update.

    For each indicator, uses the historical signal_correct data in feedback_log
    to compute wins/losses, then updates a Beta prior.

    Prior: Beta(alpha=prior_strength * base_weight, beta=prior_strength * (1-base_weight))
    Posterior mean: (alpha + wins) / (alpha + wins + beta + losses)

    Returns: dict of {indicator: weight} normalized to sum to 1.0
    """
    _fallback = dict(_BAYESIAN_BASE_WEIGHTS)

    conn = None
    try:
        conn = _get_conn()

        # Count wins and losses across all resolved signals (proxy per indicator via snap columns)
        # For indicators without dedicated snap columns, use overall win/loss from was_correct
        rows = conn.execute(
            """
            SELECT was_correct, snap_rsi, snap_macd_hist, snap_adx,
                   snap_volume_ok, direction, confidence
            FROM feedback_log
            WHERE resolved_at IS NOT NULL AND was_correct IS NOT NULL
            ORDER BY timestamp DESC LIMIT 500
            """
        ).fetchall()

        if len(rows) < 20:
            logger.info("[Bayesian] Insufficient resolved feedback (%d rows) — using defaults", len(rows))
            return _fallback

        # Compute per-indicator wins/losses
        # For RSI: snap_rsi present → use directional correctness
        # For MACD: snap_macd_hist (>0 = bullish signal)
        # For ADX: snap_adx > 25 = trending (trustworthy signal)
        # For volume: snap_volume_ok = 1
        # For all: use was_correct as win proxy

        def _indicator_wins_losses(indicator: str) -> tuple:
            wins = 0
            losses = 0
            for r in rows:
                wc = r["was_correct"]
                if wc is None:
                    continue
                if indicator == "rsi":
                    rsi = r["snap_rsi"]
                    if rsi is None: continue
                    # RSI signal was useful if in overbought/oversold territory
                    relevant = (rsi < 35 or rsi > 65)
                    if not relevant: continue
                elif indicator == "macd":
                    macd_h = r["snap_macd_hist"]
                    if macd_h is None: continue
                    dir_str = str(r["direction"] or "").upper()
                    # MACD histogram sign should match trade direction
                    is_aligned = (macd_h > 0 and "BUY" in dir_str) or (macd_h < 0 and "SELL" in dir_str)
                    if not is_aligned: continue
                elif indicator == "adx":
                    adx = r["snap_adx"]
                    if adx is None: continue
                    if float(adx) < 20: continue  # ADX only relevant in trending markets
                elif indicator == "volume":
                    vol_ok = r["snap_volume_ok"]
                    if vol_ok is None or int(vol_ok) != 1: continue
                elif indicator == "funding_rate":
                    # Use high-confidence signals as proxy for funding rate agreement
                    conf = r["confidence"]
                    if conf is None or float(conf) < 65: continue
                # For all other indicators (supertrend, on_chain, sentiment): use all rows
                if int(wc) == 1:
                    wins += 1
                else:
                    losses += 1
            return wins, losses

        updated_weights = {}
        for indicator, base_w in _BAYESIAN_BASE_WEIGHTS.items():
            wins, losses = _indicator_wins_losses(indicator)
            alpha = prior_strength * base_w
            beta  = prior_strength * (1.0 - base_w)
            posterior_mean = (alpha + wins) / (alpha + wins + beta + losses)
            updated_weights[indicator] = round(float(posterior_mean), 6)

        # Normalize to sum to 1.0
        total = sum(updated_weights.values())
        if total > 0:
            updated_weights = {k: round(v / total, 6) for k, v in updated_weights.items()}
        else:
            updated_weights = _fallback

        # Save to bayesian_weights table
        computed_at = datetime.now(timezone.utc).isoformat()
        with _write_lock:
            conn2 = _get_conn()
            try:
                for indicator, base_w in _BAYESIAN_BASE_WEIGHTS.items():
                    wins, losses = _indicator_wins_losses(indicator)
                    alpha = prior_strength * base_w
                    beta  = prior_strength * (1.0 - base_w)
                    w = updated_weights.get(indicator, base_w)
                    conn2.execute(
                        "INSERT INTO bayesian_weights "
                        "(updated_at, indicator, weight, alpha, beta, wins, losses) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (computed_at, indicator, w,
                         round(alpha + wins, 4), round(beta + losses, 4),
                         wins, losses),
                    )
                conn2.commit()
            finally:
                conn2.close()

        return updated_weights

    except Exception as e:
        logger.warning("[DB] bayesian_recalibrate_weights failed: %s", e)
        return _fallback
    finally:
        if conn:
            conn.close()


def get_bayesian_weights(latest_only: bool = True) -> dict:
    """
    Load most recent Bayesian weights from DB.
    Returns dict of {indicator: weight} or empty dict if none saved yet.
    """
    conn = None
    try:
        conn = _get_conn()
        if latest_only:
            # Get the most recent computed_at timestamp
            row = conn.execute(
                "SELECT updated_at FROM bayesian_weights ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return {}
            latest_ts = row["updated_at"]
            rows = conn.execute(
                "SELECT indicator, weight FROM bayesian_weights WHERE updated_at = ?",
                (latest_ts,),
            ).fetchall()
            return {r["indicator"]: float(r["weight"]) for r in rows}
        else:
            rows = conn.execute(
                "SELECT indicator, weight FROM bayesian_weights ORDER BY id DESC LIMIT 100"
            ).fetchall()
            return {r["indicator"]: float(r["weight"]) for r in rows}
    except Exception as e:
        logger.warning("[DB] get_bayesian_weights failed: %s", e)
        return {}
    finally:
        if conn:
            conn.close()


def get_bayesian_weights_detail() -> list:
    """Return all indicator rows from the latest Bayesian calibration run."""
    conn = None
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT updated_at FROM bayesian_weights ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return []
        latest_ts = row["updated_at"]
        rows = conn.execute(
            """SELECT indicator, weight, alpha, beta, wins, losses, updated_at
               FROM bayesian_weights WHERE updated_at = ?
               ORDER BY weight DESC""",
            (latest_ts,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[DB] get_bayesian_weights_detail failed: %s", e)
        return []
    finally:
        if conn:
            conn.close()


# ──────────────────────────────────────────────
# DETAILED WALK-FORWARD EFFICIENCY VALIDATION  (#90)
# ──────────────────────────────────────────────

_WFE_DETAIL_CACHE: dict = {}
_WFE_DETAIL_CACHE_LOCK = threading.Lock()
_WFE_DETAIL_CACHE_TTL  = 21600  # 6 hours


def run_detailed_wfe_validation(n_windows: int = 8) -> dict:
    """
    Detailed Walk-Forward Efficiency (WFE) validation across N rolling windows.

    Divides all available backtest_trades history into n_windows rolling windows.
    For each window:
      - IS (in-sample):  first 70% → find optimal confidence threshold, compute IS Sharpe + win rate
      - OOS (out-of-sample): last 30% → compute OOS Sharpe + win rate at IS-optimal threshold
      - WFE for window = OOS Sharpe / IS Sharpe (clamped to [0, 2])

    Returns full per-window breakdown + aggregate metrics + grade + recommendation.
    Cached for 6 hours at module level (computation is expensive).
    """
    _default = {
        "windows": [],
        "avg_wfe": None,
        "avg_oos_sharpe": None,
        "avg_oos_win_rate": None,
        "stability_score": None,
        "grade": "POOR",
        "recommendation": f"Insufficient backtest data for WFE validation (need ≥ {max(n_windows * 8, 40)} trades for {n_windows} windows).",
        "error": "insufficient data",
    }

    # Check module-level cache (6-hour TTL)
    _cache_key = int(n_windows)
    with _WFE_DETAIL_CACHE_LOCK:
        _cached = _WFE_DETAIL_CACHE.get(_cache_key)
        if _cached and (datetime.now(timezone.utc).timestamp() - _cached.get("_ts", 0)) < _WFE_DETAIL_CACHE_TTL:
            result = dict(_cached)
            result.pop("_ts", None)
            return result

    def _sharpe(returns: list) -> float:
        if len(returns) < 2:
            return 0.0
        arr = np.array(returns, dtype=float)
        std = float(np.std(arr, ddof=1))
        if std < 1e-9:
            return 0.0
        return round(float(np.mean(arr)) / std, 4)

    def _win_rate(returns: list) -> float:
        if not returns:
            return 0.0
        return round(sum(1 for r in returns if r > 0) / len(returns) * 100, 2)

    def _find_optimal_threshold(trades: list) -> tuple:
        """Find threshold (50–80) that maximises Sharpe on IS subset. Returns (threshold, sharpe, win_rate)."""
        thresholds = [50, 55, 60, 65, 70, 75, 80]
        best_thresh = 65.0
        best_sharpe = -999.0
        best_wr = 0.0
        for thresh in thresholds:
            sub = [float(t["pnl_pct"]) for t in trades
                   if float(t.get("confidence", 0) or 0) >= thresh]
            if len(sub) < 3:
                continue
            sh = _sharpe(sub)
            if sh > best_sharpe:
                best_sharpe = sh
                best_thresh = float(thresh)
                best_wr = _win_rate(sub)
        return best_thresh, max(best_sharpe, 0.0), best_wr

    conn = None
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT bt.pnl_pct, bt.timestamp, bt.pair, bt.direction,
                   COALESCE(fl.confidence, 65.0) AS confidence
            FROM backtest_trades bt
            LEFT JOIN feedback_log fl
              ON fl.pair = bt.pair
             AND fl.direction = bt.direction
             AND DATE(fl.timestamp) = DATE(bt.timestamp)
            WHERE bt.pnl_pct IS NOT NULL
              AND bt.timestamp IS NOT NULL
            ORDER BY bt.timestamp ASC
            """
        ).fetchall()

        if len(rows) < max(n_windows * 8, 40):
            return _default

        rows_list = [dict(r) for r in rows]
        n_total   = len(rows_list)
        window_sz = n_total // n_windows

        windows_out = []
        wfe_vals    = []
        oos_sharpes = []
        oos_wrs     = []

        for i in range(n_windows):
            w_start = i * window_sz
            w_end   = (w_start + window_sz) if i < n_windows - 1 else n_total
            window  = rows_list[w_start:w_end]
            w_n     = len(window)
            if w_n < 8:
                continue

            # IS = first 70%, OOS = last 30%
            is_end  = max(1, int(w_n * 0.70))
            is_data  = window[:is_end]
            oos_data = window[is_end:]

            if len(is_data) < 3 or len(oos_data) < 2:
                continue

            # Dates
            start_date = str(is_data[0].get("timestamp", ""))[:10]
            end_date   = str(oos_data[-1].get("timestamp", ""))[:10]

            # IS: find optimal threshold
            opt_thresh, is_sharpe, is_wr = _find_optimal_threshold(is_data)

            # IS returns at optimal threshold
            is_returns = [float(t["pnl_pct"]) for t in is_data
                          if float(t.get("confidence", 0) or 0) >= opt_thresh]
            if len(is_returns) < 2:
                # Fall back to all IS returns
                is_returns = [float(t["pnl_pct"]) for t in is_data]
            is_sharpe_final = _sharpe(is_returns)
            is_wr_final     = _win_rate(is_returns)

            # OOS: apply IS-optimal threshold
            oos_returns = [float(t["pnl_pct"]) for t in oos_data
                           if float(t.get("confidence", 0) or 0) >= opt_thresh]
            if len(oos_returns) < 2:
                oos_returns = [float(t["pnl_pct"]) for t in oos_data]

            oos_sharpe_raw = _sharpe(oos_returns)
            oos_wr_raw     = _win_rate(oos_returns)

            # WFE = OOS Sharpe / IS Sharpe, clamped to [0, 2]
            if abs(is_sharpe_final) < 1e-9:
                wfe_window = 0.0
            else:
                wfe_window = float(np.clip(oos_sharpe_raw / is_sharpe_final, 0.0, 2.0))

            wfe_vals.append(wfe_window)
            oos_sharpes.append(oos_sharpe_raw)
            oos_wrs.append(oos_wr_raw)

            windows_out.append({
                "window_id":          i + 1,
                "start_date":         start_date,
                "end_date":           end_date,
                "is_sharpe":          round(is_sharpe_final, 4),
                "oos_sharpe":         round(oos_sharpe_raw, 4),
                "wfe":                round(wfe_window, 4),
                "is_win_rate":        round(is_wr_final, 2),
                "oos_win_rate":       round(oos_wr_raw, 2),
                "optimal_threshold":  opt_thresh,
                "n_trades_is":        len(is_returns),
                "n_trades_oos":       len(oos_returns),
            })

        if not windows_out:
            return _default

        avg_wfe      = round(float(np.mean(wfe_vals)), 4)
        avg_oos_sh   = round(float(np.mean(oos_sharpes)), 4)
        avg_oos_wr   = round(float(np.mean(oos_wrs)), 2)
        stability    = round(float(np.std(wfe_vals, ddof=1)) if len(wfe_vals) > 1 else 0.0, 4)

        # Grade based on avg WFE
        if avg_wfe >= 0.9:
            grade = "EXCELLENT"
        elif avg_wfe >= 0.7:
            grade = "GOOD"
        elif avg_wfe >= 0.5:
            grade = "FAIR"
        else:
            grade = "POOR"

        # Recommendation — use modal optimal threshold across windows
        thresh_votes: dict = {}
        for w in windows_out:
            t = w["optimal_threshold"]
            thresh_votes[t] = thresh_votes.get(t, 0) + 1
        modal_thresh = max(thresh_votes, key=lambda k: thresh_votes[k])

        if grade in ("EXCELLENT", "GOOD"):
            rec = (
                f"Model is stable (WFE={avg_wfe:.2f}, {grade}). "
                f"Use threshold {int(modal_thresh)}% for BUY signals. "
                f"Avg OOS Sharpe {avg_oos_sh:.2f}, OOS win rate {avg_oos_wr:.1f}%."
            )
        elif grade == "FAIR":
            rec = (
                f"Model shows moderate stability (WFE={avg_wfe:.2f}). "
                f"Use threshold {int(modal_thresh)}% for BUY signals with extra caution. "
                f"Consider reducing position size in low-confidence windows."
            )
        else:
            rec = (
                f"Model may be overfitting (WFE={avg_wfe:.2f}, {grade}). "
                f"OOS performance lags IS significantly. "
                f"Reduce indicator complexity or increase lookback period."
            )

        result = {
            "windows":         windows_out,
            "avg_wfe":         avg_wfe,
            "avg_oos_sharpe":  avg_oos_sh,
            "avg_oos_win_rate": avg_oos_wr,
            "stability_score": stability,
            "grade":           grade,
            "recommendation":  rec,
        }

        # Store in module-level cache with timestamp
        with _WFE_DETAIL_CACHE_LOCK:
            _WFE_DETAIL_CACHE[_cache_key] = {**result, "_ts": datetime.now(timezone.utc).timestamp()}

        return result

    except Exception as e:
        logger.warning("[DB] run_detailed_wfe_validation failed: %s", e)
        return _default
    finally:
        if conn:
            conn.close()


# ──────────────────────────────────────────────
# WALK-FORWARD ROLLING WINDOW OPTIMIZATION  (#51)
# ──────────────────────────────────────────────

_WFO_CACHE: dict = {}
_WFO_CACHE_LOCK = threading.Lock()
_WFO_CACHE_TTL  = 86400  # 24 hours


def run_walkforward_optimization(lookback_days: int = 90, n_windows: int = 4) -> dict:
    """
    Walk-forward rolling window optimization for confidence threshold.

    Splits last `lookback_days` of resolved feedback into `n_windows` windows.
    For each window: finds optimal BUY threshold on IS period, evaluates on OOS.

    Thresholds tested: 50, 55, 60, 65, 70, 75, 80 (%)

    Returns:
        {"optimal_threshold": float, "avg_oos_win_rate": float, "n_windows": int,
         "window_results": [...], "recommendation": str}
    """
    _default = {
        "optimal_threshold": 65.0, "avg_oos_win_rate": None,
        "n_windows": n_windows, "window_results": [],
        "recommendation": "Use default threshold 65% for BUY signals (insufficient data for WFO)",
        "error": "insufficient data",
    }

    # Check cache first
    cache_key = (int(lookback_days), int(n_windows))
    with _WFO_CACHE_LOCK:
        cached = _WFO_CACHE.get(cache_key)
        if cached and (datetime.now(timezone.utc).timestamp() - cached.get("_ts", 0)) < _WFO_CACHE_TTL:
            result = dict(cached)
            result.pop("_ts", None)
            return result

    conn = None
    try:
        conn = _get_conn()
        rows = conn.execute(
            """
            SELECT confidence, direction, was_correct, timestamp
            FROM feedback_log
            WHERE resolved_at IS NOT NULL
              AND was_correct IS NOT NULL
              AND confidence IS NOT NULL
              AND direction IS NOT NULL
              AND timestamp >= datetime('now', ?)
            ORDER BY timestamp ASC
            """,
            (f"-{int(lookback_days)} days",),
        ).fetchall()

        if len(rows) < n_windows * 10:
            return _default

        rows_list = [dict(r) for r in rows]
        n_total   = len(rows_list)
        window_size = n_total // n_windows
        thresholds  = [50, 55, 60, 65, 70, 75, 80]

        window_results = []
        oos_win_rates  = []

        for i in range(n_windows):
            start_idx = i * window_size
            end_idx   = start_idx + window_size if i < n_windows - 1 else n_total
            window    = rows_list[start_idx:end_idx]
            w_n       = len(window)
            if w_n < 8:
                continue

            # IS = first 60% of window, OOS = last 40%
            is_split = max(1, int(w_n * 0.60))
            is_data  = window[:is_split]
            oos_data = window[is_split:]

            if len(is_data) < 4 or len(oos_data) < 4:
                continue

            # Find best IS threshold for BUY signals
            best_thresh = 65.0
            best_is_wr  = 0.0
            for thresh in thresholds:
                buys = [r for r in is_data
                        if "BUY" in str(r.get("direction", "")).upper()
                        and float(r.get("confidence", 0)) >= thresh]
                if len(buys) < 2:
                    continue
                wr = sum(1 for r in buys if int(r.get("was_correct", 0)) == 1) / len(buys)
                if wr > best_is_wr:
                    best_is_wr  = wr
                    best_thresh = float(thresh)

            # Evaluate on OOS using best IS threshold
            oos_buys = [r for r in oos_data
                        if "BUY" in str(r.get("direction", "")).upper()
                        and float(r.get("confidence", 0)) >= best_thresh]
            if len(oos_buys) >= 2:
                oos_wr = sum(1 for r in oos_buys if int(r.get("was_correct", 0)) == 1) / len(oos_buys)
                oos_win_rates.append(oos_wr)
            else:
                oos_wr = None

            window_results.append({
                "window":          i + 1,
                "is_n":            len(is_data),
                "oos_n":           len(oos_data),
                "optimal_thresh":  best_thresh,
                "is_win_rate":     round(best_is_wr * 100, 1),
                "oos_win_rate":    round(oos_wr * 100, 1) if oos_wr is not None else None,
                "oos_buy_signals": len(oos_buys),
            })

        if not window_results:
            return _default

        # Aggregate optimal threshold (mode of window optima)
        thresh_votes: dict = {}
        for wr in window_results:
            t = wr["optimal_thresh"]
            thresh_votes[t] = thresh_votes.get(t, 0) + 1
        best_global_thresh = max(thresh_votes, key=lambda k: thresh_votes[k])

        avg_oos = (sum(oos_win_rates) / len(oos_win_rates)) if oos_win_rates else None

        result = {
            "optimal_threshold": float(best_global_thresh),
            "avg_oos_win_rate":  round(avg_oos * 100, 1) if avg_oos is not None else None,
            "n_windows":         len(window_results),
            "window_results":    window_results,
            "recommendation":    (
                f"Use threshold {int(best_global_thresh)}% for BUY signals "
                f"(avg OOS win rate: {avg_oos*100:.1f}%)" if avg_oos is not None
                else f"Use threshold {int(best_global_thresh)}% for BUY signals"
            ),
        }

        # Persist to DB
        computed_at = datetime.now(timezone.utc).isoformat()
        with _write_lock:
            conn2 = _get_conn()
            try:
                conn2.execute(
                    "INSERT INTO wfo_cache "
                    "(computed_at, lookback_days, n_windows, optimal_threshold, "
                    " avg_oos_win_rate, window_results_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (computed_at, int(lookback_days), len(window_results),
                     float(best_global_thresh),
                     round(avg_oos * 100, 1) if avg_oos is not None else None,
                     json.dumps(window_results)),
                )
                conn2.commit()
            finally:
                conn2.close()

        # Update in-memory cache
        with _WFO_CACHE_LOCK:
            _WFO_CACHE[cache_key] = {**result, "_ts": datetime.now(timezone.utc).timestamp()}

        return result

    except Exception as e:
        logger.warning("[DB] run_walkforward_optimization failed: %s", e)
        return _default
    finally:
        if conn:
            conn.close()


def get_latest_wfo_result() -> dict:
    """Return the most recent WFO result from DB cache."""
    conn = None
    try:
        conn = _get_conn()
        row = conn.execute(
            """SELECT computed_at, optimal_threshold, avg_oos_win_rate,
                      n_windows, window_results_json
               FROM wfo_cache ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return {}
        wr = json.loads(row["window_results_json"] or "[]") if row["window_results_json"] else []
        return {
            "computed_at":       row["computed_at"],
            "optimal_threshold": row["optimal_threshold"],
            "avg_oos_win_rate":  row["avg_oos_win_rate"],
            "n_windows":         row["n_windows"],
            "window_results":    wr,
            "recommendation":    (
                f"Use threshold {int(row['optimal_threshold'] or 65)}% for BUY signals"
            ),
        }
    except Exception as e:
        logger.warning("[DB] get_latest_wfo_result failed: %s", e)
        return {}
    finally:
        if conn:
            conn.close()


# ──────────────────────────────────────────────
# P&L TRACKING  (Batch 8 — Enhanced Pair P&L)
# ──────────────────────────────────────────────

def record_pnl_entry(pair: str, signal: str, price: float, confidence: float = None) -> Optional[int]:
    """Record a BUY signal entry into the P&L tracking table.

    If an open entry already exists for this pair it is left as-is (deduplication).
    Only the most recent open entry per pair is used when recording exits.

    Returns:
        int row id of the newly inserted row, or None if deduplication skipped the insert
        or an error occurred.
    """
    entry_time = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = None
        try:
            conn = _get_conn()
            # Only insert if there is no open position for this pair already
            existing = conn.execute(
                "SELECT id FROM pnl_tracking WHERE pair=? AND status='open' ORDER BY id DESC LIMIT 1",
                (pair,),
            ).fetchone()
            if existing is None:
                cur = conn.execute(
                    """INSERT INTO pnl_tracking
                       (pair, entry_price, entry_signal, entry_time, confidence, status)
                       VALUES (?, ?, ?, ?, ?, 'open')""",
                    (pair, float(price), signal, entry_time, confidence),
                )
                conn.commit()
                return cur.lastrowid
            return None
        except Exception as e:
            logger.warning("[DB] record_pnl_entry failed: %s", e)
            return None
        finally:
            if conn is not None:
                conn.close()


def record_pnl_exit(pair: str, price: float) -> Optional[dict]:
    """Close the most recent open P&L entry for *pair* and compute P&L.

    Returns a dict with the closed trade details, or None if no open entry exists.
    P&L formula: pnl_pct = (exit_price - entry_price) / entry_price * 100  (BUY entries).
    """
    exit_time = datetime.now(timezone.utc).isoformat()
    with _write_lock:
        conn = None
        try:
            conn = _get_conn()
            row = conn.execute(
                """SELECT id, entry_price, entry_signal, entry_time, confidence
                   FROM pnl_tracking
                   WHERE pair=? AND status='open'
                   ORDER BY id DESC LIMIT 1""",
                (pair,),
            ).fetchone()
            if row is None:
                return None

            entry_price = row["entry_price"]
            entry_time_str = row["entry_time"]
            pnl_pct = (float(price) - entry_price) / entry_price * 100 if entry_price else 0.0

            # Compute holding hours
            try:
                entry_dt = datetime.fromisoformat(entry_time_str)
                exit_dt  = datetime.fromisoformat(exit_time)
                holding_hours = (exit_dt - entry_dt).total_seconds() / 3600.0
            except Exception:
                holding_hours = None

            conn.execute(
                """UPDATE pnl_tracking
                   SET exit_price=?, exit_time=?, pnl_pct=?, holding_hours=?, status='closed'
                   WHERE id=?""",
                (float(price), exit_time, round(pnl_pct, 4), holding_hours, row["id"]),
            )
            conn.commit()

            return {
                "pair":          pair,
                "entry_price":   entry_price,
                "entry_signal":  row["entry_signal"],
                "entry_time":    entry_time_str,
                "exit_price":    float(price),
                "exit_time":     exit_time,
                "pnl_pct":       round(pnl_pct, 4),
                "holding_hours": holding_hours,
            }
        except Exception as e:
            logger.warning("[DB] record_pnl_exit failed: %s", e)
            return None
        finally:
            if conn is not None:
                conn.close()


def get_pnl_summary() -> dict:
    """Return aggregate P&L statistics for all closed trades.

    Returns:
        dict with keys:
            total_trades     — number of closed P&L entries
            win_rate_pct     — % of trades with pnl_pct > 0
            avg_pnl_pct      — mean P&L per trade
            best_trade_pct   — highest single-trade P&L
            worst_trade_pct  — lowest single-trade P&L
            total_pnl_pct    — sum of all P&L values
            annualized_return_pct — rough annualised estimate (CAGR-style)
            open_positions   — count of still-open entries
    """
    conn = None
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT pnl_pct, holding_hours, entry_time, exit_time FROM pnl_tracking WHERE status='closed'"
        ).fetchall()
        open_count = conn.execute(
            "SELECT COUNT(*) FROM pnl_tracking WHERE status='open'"
        ).fetchone()[0]

        if not rows:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "avg_pnl_pct": 0.0,
                "best_trade_pct": 0.0,
                "worst_trade_pct": 0.0,
                "total_pnl_pct": 0.0,
                "annualized_return_pct": 0.0,
                "open_positions": open_count,
            }

        pnls    = [r["pnl_pct"] for r in rows if r["pnl_pct"] is not None]
        hours   = [r["holding_hours"] for r in rows if r["holding_hours"] is not None]

        n       = len(pnls)
        wins    = sum(1 for p in pnls if p > 0)
        avg_pnl = sum(pnls) / n if n else 0.0
        total   = sum(pnls)

        # Annualised return (CAGR-style) — compound factor over actual calendar span.
        #
        # BUG FIX: the old formula used avg_hours × n as the time denominator.
        # With 2 trades held 2.2h each → total_hours=4.4 → years≈0.0005 →
        # exponent=1/0.0005=2000 → 1.057^2000 ≈ 10^48 (nonsense).
        #
        # Correct approach:
        # 1. Use the ACTUAL calendar span (first entry_time → last exit_time).
        # 2. Floor the span at 30 days (720h) so a handful of short-term trades
        #    can't produce astronomical exponents.
        # 3. Require ≥5 trades for a meaningful estimate; return 0.0 otherwise.
        compound_factor = 1.0
        for p in pnls:
            compound_factor *= (1 + p / 100.0)

        # Derive actual calendar span from timestamps
        try:
            entry_times = [r["entry_time"] for r in rows if r["entry_time"]]
            exit_times  = [r["exit_time"]  for r in rows if r["exit_time"]]
            if entry_times and exit_times:
                from datetime import datetime as _dt
                def _parse(ts):
                    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z"):
                        try:
                            return _dt.strptime(ts[:26], fmt[:len(ts)])
                        except Exception:
                            pass
                    return None
                _first = min(t for t in (_parse(s) for s in entry_times) if t)
                _last  = max(t for t in (_parse(s) for s in exit_times)  if t)
                # strip tzinfo for naive arithmetic if mixed
                if hasattr(_first, "tzinfo") and _first.tzinfo and hasattr(_last, "tzinfo") and _last.tzinfo:
                    span_hours = (_last - _first).total_seconds() / 3600.0
                else:
                    _first = _first.replace(tzinfo=None) if hasattr(_first, "replace") else _first
                    _last  = _last.replace(tzinfo=None)  if hasattr(_last,  "replace") else _last
                    span_hours = (_last - _first).total_seconds() / 3600.0
            else:
                span_hours = sum(hours) if hours else 24.0
        except Exception:
            span_hours = sum(hours) if hours else 24.0

        # Floor at 30 days — prevents exponent blow-up with sparse short-term samples
        _MIN_SPAN_HOURS = 30 * 24  # 720 h
        span_hours = max(span_hours, _MIN_SPAN_HOURS)
        years = span_hours / 8760.0

        if n >= 5 and years > 0 and compound_factor > 0:
            annualized = (compound_factor ** (1.0 / years) - 1) * 100
            annualized = max(-999.9, min(9999.9, annualized))  # hard cap for display
        else:
            # Too few trades for a reliable annualized figure
            annualized = 0.0

        return {
            "total_trades":           n,
            "win_rate_pct":           round(wins / n * 100, 1) if n else 0.0,
            "avg_pnl_pct":            round(avg_pnl, 3),
            "best_trade_pct":         round(max(pnls), 3),
            "worst_trade_pct":        round(min(pnls), 3),
            "total_pnl_pct":          round(total, 3),
            "annualized_return_pct":  round(annualized, 1),
            "open_positions":         open_count,
        }
    except Exception as e:
        logger.warning("[DB] get_pnl_summary failed: %s", e)
        return {
            "total_trades": 0, "win_rate_pct": 0.0, "avg_pnl_pct": 0.0,
            "best_trade_pct": 0.0, "worst_trade_pct": 0.0, "total_pnl_pct": 0.0,
            "annualized_return_pct": 0.0, "open_positions": 0,
        }
    finally:
        if conn is not None:
            conn.close()


def get_pnl_trades_df(limit: int = 200) -> "pd.DataFrame":
    """Return closed P&L trades as a DataFrame for display in the UI."""
    conn = None
    try:
        conn = _get_conn()
        df = pd.read_sql_query(
            """SELECT pair, entry_signal, entry_price, exit_price, pnl_pct,
                      holding_hours, entry_time, exit_time
               FROM pnl_tracking
               WHERE status='closed'
               ORDER BY id DESC
               LIMIT ?""",
            conn,
            params=(limit,),
        )
        return df
    except Exception as e:
        logger.warning("[DB] get_pnl_trades_df failed: %s", e)
        return pd.DataFrame()
    finally:
        if conn is not None:
            conn.close()


# ──────────────────────────────────────────────
# CONFIDENCE HISTORY  (Batch 9 — signal confidence trend chart)
# ──────────────────────────────────────────────

def get_confidence_history(pair: str, days: int = 30) -> list:
    """Return the last *days* of confidence scores for *pair* from daily_signals.

    Each element is a dict:
        {"timestamp": str, "confidence": float, "signal": str}

    The list is ordered chronologically (oldest first) so callers can plot it
    directly as a time-series.  Returns an empty list when no rows exist.
    """
    conn = None
    try:
        conn = _get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        rows = conn.execute(
            """
            SELECT scan_timestamp, confidence_avg_pct, direction
            FROM   daily_signals
            WHERE  pair = ?
              AND  scan_timestamp >= ?
            ORDER  BY scan_timestamp ASC
            """,
            (pair, cutoff),
        ).fetchall()

        result = []
        for row in rows:
            ts_raw = row[0] or ""
            conf_raw = row[1]
            direction_raw = row[2] or "HOLD"
            try:
                conf_val = float(conf_raw) if conf_raw is not None else 0.0
            except (TypeError, ValueError):
                conf_val = 0.0
            # Normalise direction to BUY / SELL / HOLD for colour coding
            d_upper = direction_raw.upper()
            if "BUY" in d_upper:
                sig = "BUY"
            elif "SELL" in d_upper:
                sig = "SELL"
            else:
                sig = "HOLD"
            result.append({
                "timestamp":  ts_raw,
                "confidence": conf_val,
                "signal":     sig,
            })
        return result
    except Exception as e:
        logger.warning("[DB] get_confidence_history(%s) failed: %s", pair, e)
        return []
    finally:
        if conn is not None:
            conn.close()


# ──────────────────────────────────────────────
# PERSISTENT FEEDBACK CHECKPOINT (Proposals 4 / 8)
# ──────────────────────────────────────────────

_CHECKPOINT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "feedback_checkpoint.json")


def export_feedback_checkpoint() -> bool:
    """Export compact feedback metrics to a git-tracked JSON file (Proposal 4).

    Written after every feedback resolution cycle so the accumulated model
    intelligence survives fresh deploys, Streamlit resets, and idle shutdowns.
    """
    import json as _json
    try:
        conn = _get_conn()
        # Overall resolved metrics
        try:
            stats = conn.execute(
                """SELECT COUNT(*), AVG(actual_pnl_pct),
                          SUM(CASE WHEN was_correct=1 THEN 1 ELSE 0 END)
                   FROM feedback_log WHERE resolved_at IS NOT NULL"""
            ).fetchone()
            total_resolved  = int(stats[0] or 0)
            avg_pnl         = round(float(stats[1] or 0), 4)
            total_wins      = int(stats[2] or 0)
            win_rate_overall = round(total_wins / total_resolved * 100, 1) if total_resolved > 0 else None
        finally:
            conn.close()

        # Recent resolved signals (last 30)
        conn2 = _get_conn()
        try:
            rows = conn2.execute(
                """SELECT pair, direction, timestamp, actual_pnl_pct, outcome, resolved_at
                   FROM feedback_log
                   WHERE resolved_at IS NOT NULL
                   ORDER BY resolved_at DESC LIMIT 30"""
            ).fetchall()
            recent_signals = [
                {"pair": r[0], "direction": r[1], "timestamp": r[2],
                 "actual_pnl_pct": r[3], "outcome": r[4], "resolved_at": r[5]}
                for r in rows
            ]
        finally:
            conn2.close()

        # Open paper positions
        conn3 = _get_conn()
        try:
            pos_rows = conn3.execute(
                "SELECT pair, direction, entry, entry_time FROM positions"
            ).fetchall()
            open_positions = [
                {"pair": r[0], "direction": r[1], "entry": r[2], "entry_time": r[3]}
                for r in pos_rows
            ]
        finally:
            conn3.close()

        checkpoint = {
            "version":        2,
            "app":            "supergrok",
            "last_updated":   datetime.now(timezone.utc).isoformat(),
            "total_resolved": total_resolved,
            "win_rate_pct":   win_rate_overall,
            "avg_pnl_pct":    avg_pnl,
            "total_wins":     total_wins,
            "open_positions": len(open_positions),
            "recent_signals": recent_signals,
            "open_pos_list":  open_positions,
        }

        # P2 audit fix — was a non-atomic open(_CHECKPOINT_FILE, "w") write.
        # If the process crashed mid-write the JSON file would be corrupt /
        # truncated and the next startup couldn't restore the checkpoint.
        # Atomic-rename pattern: write to a temp file in the same directory,
        # then os.replace() onto the real path. os.replace is atomic on
        # POSIX and Windows (Python's os.replace docs are explicit on this).
        import tempfile as _tempfile
        os.makedirs(os.path.dirname(_CHECKPOINT_FILE), exist_ok=True)
        _ckpt_dir = os.path.dirname(os.path.abspath(_CHECKPOINT_FILE))
        with _tempfile.NamedTemporaryFile(
            "w", dir=_ckpt_dir, suffix=".tmp", delete=False, encoding="utf-8"
        ) as _tmp:
            _json.dump(checkpoint, _tmp, indent=2, default=str)
            _tmp_path = _tmp.name
        os.replace(_tmp_path, _CHECKPOINT_FILE)

        logger.info("[DB] Feedback checkpoint exported — %d resolved, %.1f%% win rate",
                    total_resolved, win_rate_overall or 0)
        return True
    except Exception as e:
        logger.warning("[DB] Feedback checkpoint export failed (non-critical): %s", e)
        return False


def auto_close_stale_positions(current_prices: dict, hold_days: int = 14) -> int:
    """Retroactively close paper positions older than hold_days using current prices (Proposal 6).

    Any open position in the `positions` table older than hold_days days is
    closed at the current price, logged to `paper_trades`, and removed from `positions`.

    Args:
        current_prices: {pair: float} — current market prices from the last scan.
        hold_days:      Maximum age before auto-close (default 14 days).

    Returns:
        Number of positions auto-closed.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=hold_days)).isoformat()
    conn = _get_conn()
    try:
        stale = [dict(r) for r in conn.execute(
            "SELECT pair, direction, entry, entry_time, target, stop, size_pct "
            "FROM positions WHERE entry_time < ?",
            (cutoff,),
        ).fetchall()]
    finally:
        conn.close()

    if not stale:
        return 0

    closed = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    for pos in stale:
        pair = pos["pair"]
        current_price = current_prices.get(pair)
        if current_price is None:
            continue
        try:
            entry     = float(pos["entry"] or 0)
            direction = str(pos["direction"] or "")
            if entry <= 0:
                continue
            if "BUY" in direction.upper():
                pnl_pct = (current_price - entry) / entry * 100
            elif "SELL" in direction.upper():
                pnl_pct = (entry - current_price) / entry * 100
            else:
                continue

            with _write_lock:
                conn2 = _get_conn()
                try:
                    conn2.execute(
                        """INSERT INTO paper_trades
                           (pair, entry_time, close_time, direction, entry, exit, pnl_pct, size_pct, reason)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (pair, pos["entry_time"], now_iso, direction,
                         entry, current_price, round(pnl_pct, 4),
                         pos.get("size_pct", 0), "auto_close_stale"),
                    )
                    conn2.execute("DELETE FROM positions WHERE pair = ?", (pair,))
                    conn2.commit()
                finally:
                    conn2.close()
            closed += 1
            logger.info("[DB] Auto-closed stale position %s %s: pnl=%.2f%%", direction, pair, pnl_pct)
        except Exception as e:
            logger.warning("[DB] auto_close_stale_positions failed for %s: %s", pair, e)

    return closed


# ──────────────────────────────────────────────
# DB INTEGRITY CHECK  (#14 security hardening)
# ──────────────────────────────────────────────

def check_db_integrity() -> bool:
    """Run PRAGMA quick_check on the database.  Returns True if the DB is healthy.
    Called automatically on startup — logs a warning but never crashes the app."""
    try:
        with _get_conn() as conn:
            result = conn.execute("PRAGMA quick_check").fetchone()
            return bool(result and result[0] == "ok")
    except Exception as e:
        logging.warning("DB integrity check error: %s", e)
        return False


# ──────────────────────────────────────────────
# STARTUP — schema setup eager (cheap CREATE IF NOT EXISTS); CSV
# migration is now LAZY (P1 audit fix). The audit flagged that on
# Streamlit Cloud every worker thread re-ran the full migration
# scan on import, blowing the §12 60s cold-start budget. The schema
# step is fast and harmless to repeat, so it stays at import. The
# CSV migration scan (which can read multi-MB legacy files and runs
# Pandas parse loops) is now gated behind ensure_csv_migrated() so
# only the worker that actually needs DB-backed history pays the
# cost — and only once per process. Other workers (e.g., the
# WebSocket feed thread) skip it entirely.
# ──────────────────────────────────────────────

init_db()  # cheap; safe to repeat per worker

_MIGRATION_LOCK = threading.Lock()
_MIGRATION_DONE = False


def ensure_csv_migrated() -> None:
    """Run the legacy-CSV→SQLite migration once per process. Lazy.

    Callers that need DB-backed history (e.g., backtester, signal
    history page) call this on first use. Cheap on subsequent calls
    (a single boolean read).
    """
    global _MIGRATION_DONE
    if _MIGRATION_DONE:
        return
    with _MIGRATION_LOCK:
        if _MIGRATION_DONE:
            return
        try:
            migrate_csv_to_db()
        except Exception as e:
            logging.error("[database] CSV migration failed: %s", e)
        finally:
            _MIGRATION_DONE = True


# Run integrity check after init — log warning only, never crash
if not check_db_integrity():
    logging.warning(
        "[database] PRAGMA quick_check failed — DB may be corrupted. "
        "Consider deleting crypto_model.db and restarting."
    )
