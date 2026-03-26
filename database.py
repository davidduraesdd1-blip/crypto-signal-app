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
from typing import Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DB_FILE = "crypto_model.db"

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
def init_db():
    """Create all tables and indexes. Idempotent — safe to call on every startup."""
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
            def _add_col(tbl, col, col_def):
                existing = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
                if col not in existing:
                    conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def}")

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
                ('snap_rsi',       'REAL'),
                ('snap_macd_hist', 'REAL'),
                ('snap_bb_pos',    'REAL'),
                ('snap_adx',       'REAL'),
                ('snap_stoch_k',   'REAL'),
                ('snap_volume_ok', 'INTEGER'),
                ('snap_regime',    'TEXT'),
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
    'agent_log',
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
                        logger.info(f"DB migration: imported {len(df)} rows → feedback_log")
                except Exception as e:
                    logger.warning(f"DB migration feedback_log failed: {e}")

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
                        logger.info(f"DB migration: imported {len(df)} rows → daily_signals")
                except Exception as e:
                    logger.warning(f"DB migration daily_signals failed: {e}")

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
                        logger.info(f"DB migration: imported {len(df)} rows → backtest_trades")
                except Exception as e:
                    logger.warning(f"DB migration backtest_trades failed: {e}")

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
                        logger.info(f"DB migration: imported {len(df)} rows → paper_trades")
                except Exception as e:
                    logger.warning(f"DB migration paper_trades failed: {e}")

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
                        logger.info(f"DB migration: imported {len(rows)} positions → positions")
                except Exception as e:
                    logger.warning(f"DB migration positions failed: {e}")

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
                    logger.warning(f"DB migration dynamic_weights failed: {e}")

            # ── weights_log.csv ───────────────────────
            if os.path.exists("weights_log.csv") and _row_count(conn, "weights_log") == 0:
                try:
                    df = pd.read_csv("weights_log.csv", encoding="utf-8")
                    if not df.empty:
                        df.to_sql("weights_log", conn, if_exists="append", index=False)
                        conn.commit()
                        logger.info(f"DB migration: imported {len(df)} rows → weights_log")
                except Exception as e:
                    logger.warning(f"DB migration weights_log failed: {e}")

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
                    logger.warning(f"DB migration scan_cache failed: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass


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


def get_feedback_df() -> pd.DataFrame:
    conn = _get_conn()
    try:
        df = pd.read_sql("SELECT * FROM feedback_log ORDER BY timestamp ASC", conn)
    finally:
        conn.close()
    return df


def get_resolved_feedback_df(days: int = 90) -> pd.DataFrame:
    """Return feedback rows where actual outcome has been resolved, within last N days.

    Used by F2 (update_dynamic_weights) and F6/F7 (drift detection).
    """
    conn = _get_conn()
    try:
        df = pd.read_sql(
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

    # PERF: collect all updates first, then commit in one executemany() call
    # (was N individual UPDATE+commit per row = N+1 DB round-trips; now 1 round-trip)
    now_iso = datetime.now(timezone.utc).isoformat()
    updates = []
    for row in rows:
        try:
            ts = datetime.fromisoformat(row['timestamp'])
            since_ms = int((ts + timedelta(days=hold_days)).timestamp() * 1000)
            actual_price = fetch_price_fn(row['pair'], since_ms)
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
            logger.warning(f"resolve_feedback_outcomes failed for row {row.get('id', '?')}: {e}")

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
            logger.warning(f"quick_resolve_feedback failed for row {row.get('id')}: {e}")

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
        df = pd.read_sql(
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
            df = pd.read_sql(
                "SELECT * FROM daily_signals ORDER BY id DESC LIMIT ?",
                conn,
                params=(int(limit),),
            )
            df = df.sort_values("scan_timestamp", ascending=True).reset_index(drop=True)
        else:
            df = pd.read_sql("SELECT * FROM daily_signals ORDER BY scan_timestamp ASC", conn)
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
            df = pd.read_sql(
                "SELECT * FROM backtest_trades WHERE run_id=? ORDER BY id ASC",
                conn, params=[run_id]
            )
        else:
            row = conn.execute(
                "SELECT run_id FROM backtest_trades ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return pd.DataFrame()
            df = pd.read_sql(
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
        df = pd.read_sql("""
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
        df = pd.read_sql("SELECT * FROM paper_trades ORDER BY close_time ASC", conn)
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
        df = pd.read_sql("SELECT * FROM positions", conn)
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
        df = pd.read_sql(
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
        logger.warning(f"Circuit breaker check failed: {e}")
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
        df = pd.read_sql(
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
        df = pd.read_sql(
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
            df = pd.read_sql(
                "SELECT * FROM arb_opportunities WHERE arb_type=? ORDER BY detected_at DESC LIMIT ?",
                conn,
                params=(arb_type, int(limit)),
            )
        else:
            df = pd.read_sql(
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
        df = pd.read_sql(
            "SELECT * FROM agent_log ORDER BY logged_at DESC LIMIT ?",
            conn,
            params=(int(limit),),
        )
    finally:
        conn.close()
    return df.drop(columns=["id"], errors="ignore")


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
        conditions = [
            "resolved_at IS NOT NULL",
            "was_correct IS NOT NULL",
            f"timestamp > datetime('now', '-{int(days)} days')",
        ]
        params: list = []

        if pair:
            conditions.append("pair = ?")
            params.append(pair)

        if direction:
            # Match BUY/STRONG BUY or SELL/STRONG SELL
            conditions.append("direction LIKE ?")
            params.append(f"%{direction.upper()}%")

        where = " AND ".join(conditions)
        df = pd.read_sql(
            f"SELECT was_correct FROM feedback_log WHERE {where}",
            conn,
            params=params if params else None,
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
        df = pd.read_sql(
            f"""
            SELECT pair,
                   direction,
                   COUNT(*) as total,
                   SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as wins
            FROM feedback_log
            WHERE resolved_at IS NOT NULL
              AND was_correct IS NOT NULL
              AND timestamp > datetime('now', '-{int(days)} days')
            GROUP BY pair, direction
            HAVING total >= 10
            ORDER BY (wins * 1.0 / total) DESC
            LIMIT {int(n)}
            """,
            conn,
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

def compute_and_save_ic(pair: str, timeframe: str = "1h") -> dict:
    """
    Compute Information Coefficient (IC) and walk-forward efficiency (WFE) for a pair.

    IC = Pearson correlation between signal confidence and actual 24h return (from feedback_log).
    WFE = ratio of out-of-sample win rate to in-sample win rate over the last 60 resolved signals.

    Returns: {ic_30d, ic_7d, wfe, win_rate, sample_n}
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    cutoff_7d  = (now - timedelta(days=7)).isoformat()

    result = {"pair": pair, "timeframe": timeframe, "ic_30d": None, "ic_7d": None,
              "wfe": None, "win_rate": None, "sample_n": 0}

    conn = None
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT confidence_avg_pct, actual_pnl_pct, was_correct, timestamp
            FROM feedback_log
            WHERE pair = ? AND resolved_at IS NOT NULL
              AND actual_pnl_pct IS NOT NULL AND confidence_avg_pct IS NOT NULL
              AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT 200
        """, (pair, cutoff_30d)).fetchall()

        if len(rows) < 5:
            return result

        # Guard against None even though SQL filters it (defensive)
        conf_vals  = [float(r["confidence_avg_pct"]) for r in rows if r["confidence_avg_pct"] is not None]
        ret_vals   = [float(r["actual_pnl_pct"])     for r in rows if r["actual_pnl_pct"] is not None]
        correct    = [int(r["was_correct"] or 0)      for r in rows]
        # Ensure lists are aligned (parallel rows)
        min_len = min(len(conf_vals), len(ret_vals))
        conf_vals, ret_vals = conf_vals[:min_len], ret_vals[:min_len]
        if min_len < 5:
            return result

        # IC (30d)
        def _pearson(x: list, y: list) -> float:
            n = len(x)
            if n < 2:
                return 0.0
            mx, my = sum(x)/n, sum(y)/n
            num = sum((xi - mx)*(yi - my) for xi, yi in zip(x, y))
            denom = (
                (sum((xi - mx)**2 for xi in x) ** 0.5) *
                (sum((yi - my)**2 for yi in y) ** 0.5)
            )
            return round(num / denom, 4) if denom > 1e-9 else 0.0

        ic_30d = _pearson(conf_vals, ret_vals)
        win_rate_30d = sum(correct) / len(correct) if correct else 0.0

        # IC (7d) — use only recent rows
        rows_7d = [r for r in rows if r["timestamp"] >= cutoff_7d]
        if len(rows_7d) >= 5:
            ic_7d = _pearson(
                [float(r["confidence_avg_pct"]) for r in rows_7d],
                [float(r["actual_pnl_pct"])     for r in rows_7d],
            )
        else:
            ic_7d = None

        # WFE = OOS win rate / IS win rate
        # Split: first 60% = IS, last 40% = OOS
        n = len(rows)
        split = int(n * 0.6)
        is_correct  = [int(rows[i]["was_correct"] or 0) for i in range(split)] if split > 0 else []
        oos_correct = [int(rows[i]["was_correct"] or 0) for i in range(split, n)]
        is_wr  = sum(is_correct)  / max(len(is_correct),  1)
        oos_wr = sum(oos_correct) / max(len(oos_correct), 1)
        wfe = round(oos_wr / max(is_wr, 0.01), 3)

        result.update({
            "ic_30d":   ic_30d,
            "ic_7d":    ic_7d,
            "wfe":      wfe,
            "win_rate": round(win_rate_30d, 4),
            "sample_n": n,
        })

        # Persist to signal_metrics table
        conn.execute("""
            INSERT INTO signal_metrics (computed_at, pair, timeframe, ic_30d, ic_7d, wfe, win_rate, sample_n)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (now.isoformat(), pair, timeframe,
              ic_30d, ic_7d, wfe, round(win_rate_30d, 4), n))
        conn.commit()
        return result

    except Exception as e:
        logging.warning("[DB] compute_ic failed for %s: %s", pair, e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return result
    finally:
        if conn:
            conn.close()


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
# STARTUP — runs automatically on import
# ──────────────────────────────────────────────
init_db()
migrate_csv_to_db()
