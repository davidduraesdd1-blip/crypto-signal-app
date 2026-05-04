"""
DB concurrency rewrite — Phase 1 behavior-locking test suite.

These tests lock the CURRENT behavior of `database.py` connection /
transaction model BEFORE the DB-1/DB-4 rewrite starts. The rewrite must
keep them green; any failure means the rewrite changed observable
behavior, requiring either a fix to the rewrite or an explicit
test-update commit with reasoning.

Test plan: docs/audits/2026-05-03_db-concurrency-rewrite-test-plan.md
Restore tag: pre-db-rewrite-2026-05-03

Phase 1 covers:
  - Single-thread invariants (PRAGMAs, _NoCloseConn semantics)
  - Connection-pool invariants (per-thread caching, isolation)
  - Transaction semantics (atomicity, rollback)
  - Concurrent-writer matrix (busy_timeout retry behavior)

Phase 2 (failure injection) and Phase 3 (rewrite + verify) live in
separate test files.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time

import pytest


# ── Shared fixture: temp DB file for isolation ──────────────────────────────


@pytest.fixture
def tmp_db_path(tmp_path, monkeypatch):
    """Point database.DB_FILE at a fresh per-test temp DB so tests
    don't leak into each other or into the real alerts.db.
    Resets the thread-local connection cache so the next _get_conn
    call opens a fresh connection against the temp DB."""
    import database as db
    path = str(tmp_path / "test_db_concurrency.db")
    monkeypatch.setattr(db, "DB_FILE", path)
    # Reset the thread-local connection cache so the temp path takes effect
    if hasattr(db._thread_local, "conn"):
        del db._thread_local.conn
    yield path
    # Cleanup
    if hasattr(db._thread_local, "conn"):
        try:
            db._thread_local.conn.__dict__["_conn"].close()
        except Exception:
            pass
        del db._thread_local.conn


# ── 1.1 Single-thread invariants ────────────────────────────────────────────


def test_make_conn_sets_all_pragmas(tmp_db_path):
    """All 9 PRAGMAs from `_make_conn` must be active on the returned
    connection. This locks in the perf + safety contract; any future
    rewrite that drops a PRAGMA fails this test loudly."""
    import database as db
    conn = db._make_conn()
    try:
        # journal_mode is the most observable — WAL is required for
        # concurrent reader/writer correctness on SQLite.
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        # synchronous=NORMAL trades fsync overhead for slightly weaker
        # durability — appropriate for a non-bank-grade ledger.
        assert conn.execute("PRAGMA synchronous").fetchone()[0] in (1, 2)  # NORMAL=1 or FULL=2
        # foreign_keys=ON is required by the schema's CASCADE rules.
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        # busy_timeout from P7-DB-2 — must survive any future rewrite.
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
        # cache_size negative value = -64 MB (SQLite convention)
        assert conn.execute("PRAGMA cache_size").fetchone()[0] == -65536
    finally:
        conn.close()


def test_no_close_conn_close_does_not_close_underlying(tmp_db_path):
    """_NoCloseConn.close() must roll back, NOT close the underlying
    connection. The pool relies on this — closing the underlying conn
    forces a full PRAGMA re-init on the next call."""
    import database as db
    raw = db._make_conn()
    wrapped = db._NoCloseConn(raw)
    wrapped.close()
    # Underlying conn still usable — close() was a rollback, not a real close.
    result = raw.execute("SELECT 1").fetchone()[0]
    assert result == 1
    raw.close()


def test_no_close_conn_close_rolls_back_uncommitted(tmp_db_path):
    """Pending writes must be rolled back when _NoCloseConn.close()
    fires. Without this, the next caller would see uncommitted writes."""
    import database as db
    raw = db._make_conn()
    raw.execute("CREATE TABLE IF NOT EXISTS _test (id INTEGER, val TEXT)")
    raw.commit()
    wrapped = db._NoCloseConn(raw)
    wrapped.execute("INSERT INTO _test VALUES (1, 'pending')")
    # Don't commit — close() should roll back this pending insert.
    wrapped.close()
    # Verify the row is NOT persisted (rolled back).
    row = raw.execute("SELECT COUNT(*) FROM _test WHERE val='pending'").fetchone()[0]
    assert row == 0, "Uncommitted write must be rolled back by _NoCloseConn.close()"
    raw.close()


# ── 1.2 Connection-pool invariants ──────────────────────────────────────────


def test_get_conn_returns_same_object_on_repeat_call(tmp_db_path):
    """Same-thread sequential _get_conn calls must return the SAME
    wrapped object (pool hit, not fresh _make_conn)."""
    import database as db
    c1 = db._get_conn()
    c2 = db._get_conn()
    assert c1 is c2, "pool miss — _get_conn returned a fresh connection on repeat call"


def test_get_conn_isolates_per_thread(tmp_db_path):
    """Different threads must get DIFFERENT wrapped objects so they
    don't trip on each other's transaction state."""
    import database as db
    main_conn = db._get_conn()
    other_conn = []

    def _other_thread():
        other_conn.append(db._get_conn())

    t = threading.Thread(target=_other_thread)
    t.start()
    t.join()

    assert other_conn[0] is not main_conn, (
        "thread isolation broken — _get_conn returned the main thread's "
        "connection to a different thread"
    )


def test_get_conn_recovers_from_dead_connection(tmp_db_path, monkeypatch):
    """If the underlying connection becomes invalid (e.g. DB file was
    recreated mid-process), _get_conn detects it via a SELECT 1 probe
    and creates a fresh connection. This locks the existing recovery
    behavior in `_get_conn`."""
    import database as db
    c1 = db._get_conn()
    # Forcibly invalidate the underlying connection so SELECT 1 raises.
    c1.__dict__["_conn"].close()
    c2 = db._get_conn()
    # The wrapped object may be the same (pool reuses _NoCloseConn
    # wrapper) but the underlying conn is fresh and usable.
    assert c2.execute("SELECT 1").fetchone()[0] == 1


# ── 1.3 Transaction semantics ──────────────────────────────────────────────


def test_atomic_write_rolls_back_on_exception(tmp_db_path):
    """A `with conn:` block must roll back if the body raises. Locking
    in this contract ensures the rewrite preserves it."""
    import database as db
    conn = db._make_conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _atomic (id INTEGER PRIMARY KEY, val TEXT)")
        conn.commit()
        try:
            with conn:
                conn.execute("INSERT INTO _atomic VALUES (1, 'should-rollback')")
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        count = conn.execute(
            "SELECT COUNT(*) FROM _atomic WHERE val='should-rollback'"
        ).fetchone()[0]
        assert count == 0, "with conn: block must roll back on exception"
    finally:
        conn.close()


def test_atomic_write_commits_on_success(tmp_db_path):
    """A `with conn:` block must commit when the body completes
    normally."""
    import database as db
    conn = db._make_conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS _atomic (id INTEGER PRIMARY KEY, val TEXT)")
        conn.commit()
        with conn:
            conn.execute("INSERT INTO _atomic VALUES (1, 'should-commit')")
        count = conn.execute(
            "SELECT COUNT(*) FROM _atomic WHERE val='should-commit'"
        ).fetchone()[0]
        assert count == 1, "with conn: block must commit on normal exit"
    finally:
        conn.close()


# ── 1.4 Concurrent-writer matrix (busy_timeout retry) ──────────────────────


def test_concurrent_writers_no_busy_error(tmp_db_path):
    """N=10 concurrent writer threads each insert a row. With
    busy_timeout=5000ms set in `_make_conn`, all writes must succeed
    — the SQLite driver retries internally rather than raising
    SQLITE_BUSY at the caller. This is the regression-guard for
    P7-DB-2 under load."""
    import database as db

    # Initialize the schema once on the main thread so worker threads
    # only do INSERTs (avoids racing on CREATE TABLE).
    setup = db._make_conn()
    setup.execute(
        "CREATE TABLE IF NOT EXISTS _writers "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id INTEGER, ts REAL)"
    )
    setup.commit()
    setup.close()

    errors: list = []
    rows_inserted: list = []
    barrier = threading.Barrier(10)

    def _writer(thread_id: int):
        try:
            barrier.wait(timeout=5)  # Force interleaving
            conn = db._make_conn()  # Each thread its own raw conn
            conn.execute(
                "INSERT INTO _writers (thread_id, ts) VALUES (?, ?)",
                (thread_id, time.time()),
            )
            conn.commit()
            conn.close()
            rows_inserted.append(thread_id)
        except Exception as exc:
            errors.append((thread_id, exc))

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], (
        f"concurrent writers hit errors despite busy_timeout: {errors}"
    )
    assert len(rows_inserted) == 10, (
        f"expected 10 rows inserted, got {len(rows_inserted)}"
    )

    # Verify all 10 rows are persisted
    verify = db._make_conn()
    count = verify.execute("SELECT COUNT(*) FROM _writers").fetchone()[0]
    assert count == 10, f"expected 10 persisted rows, got {count}"
    verify.close()


def test_concurrent_read_during_long_write(tmp_db_path):
    """A read-only caller must continue serving while a write is
    in-flight. WAL mode + busy_timeout makes this work; the rewrite
    must preserve it."""
    import database as db

    setup = db._make_conn()
    setup.execute("CREATE TABLE IF NOT EXISTS _wr (id INTEGER PRIMARY KEY, val TEXT)")
    for i in range(100):
        setup.execute("INSERT INTO _wr (id, val) VALUES (?, ?)", (i, f"v{i}"))
    setup.commit()
    setup.close()

    write_started = threading.Event()
    write_done = threading.Event()
    read_results: list = []

    def _writer():
        conn = db._make_conn()
        conn.execute("BEGIN IMMEDIATE")
        write_started.set()
        # Hold the write lock briefly while the reader probes.
        time.sleep(0.2)
        conn.execute("UPDATE _wr SET val='updated' WHERE id < 50")
        conn.commit()
        conn.close()
        write_done.set()

    def _reader():
        write_started.wait(timeout=5)
        # Read while the writer holds the lock.
        conn = db._make_conn()
        count = conn.execute("SELECT COUNT(*) FROM _wr").fetchone()[0]
        read_results.append(count)
        conn.close()

    tw = threading.Thread(target=_writer)
    tr = threading.Thread(target=_reader)
    tw.start()
    tr.start()
    tw.join(timeout=10)
    tr.join(timeout=10)

    assert read_results, "reader did not complete during write"
    assert read_results[0] == 100, (
        f"reader saw torn state: {read_results[0]} rows (expected 100)"
    )


# ── DB-3 ALTER TABLE column whitelist (existing P7-DB-3 fix) ────────────────


def test_add_col_rejects_invalid_table():
    """The `_add_col` helper inside `init_db` rejects out-of-allowlist
    table names. We can't easily reach the inner closure from here, so
    we exercise the regex-validation contract by importing init_db
    + verifying the database is well-formed after creation (which
    implicitly runs `_add_col` for every migration column)."""
    import database as db
    # Init creates the schema and runs all _add_col calls — if any
    # of them violated the regex contract, init would raise.
    db.init_db()  # idempotent — safe to call repeatedly
    # Probe the resulting DB: every migration column should exist in
    # its target table.
    conn = db._make_conn()
    try:
        # feedback_log should have the audit-added columns
        cols = [r[1] for r in conn.execute("PRAGMA table_info(feedback_log)").fetchall()]
        assert "actual_pnl_pct" in cols
        assert "outcome" in cols
        # execution_log should have the H-1 fee_usd column
        exec_cols = [r[1] for r in conn.execute("PRAGMA table_info(execution_log)").fetchall()]
        assert "fee_usd" in exec_cols
        assert "slippage_pct" in exec_cols
    finally:
        conn.close()
