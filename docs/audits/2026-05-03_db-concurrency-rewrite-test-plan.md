# DB-1 / DB-4 Concurrency Rewrite — Test Plan

**Status:** test plan only. No code shipped. Approval gates the rewrite.

**Findings being closed:**
- **DB-1** (CRITICAL): default `isolation_level=""` + per-thread connection
  pool + manual `BEGIN/COMMIT` in some helpers but not others
  = sporadic "transaction within a transaction" + silent rollbacks
  via `_NoCloseConn.close()`.
- **DB-4** (CRITICAL): `save_positions` uses raw `BEGIN` outside the
  auto-tx model — same class as DB-1.

**Already shipped (separate batch):**
- DB-2 (`PRAGMA busy_timeout=5000`) — `40a473e`
- DB-3 (`_add_col` regex validation on col + col_def) — `40a473e`

---

## Why a test plan first

The DB-1/DB-4 fixes touch the connection-lifecycle model used by every
DB function in the app. The risk surface is:
- ~80 SQL helper functions in `database.py`
- Three concurrent writer processes today (FastAPI worker, agent loop,
  Streamlit during the 30-day overlap)
- Existing `_NoCloseConn` proxy converts `close()` → rollback to keep
  the connection pool alive — any code that intentionally rolls back a
  bad transaction relies on that proxy
- Mixed `executescript`, `commit()`, manual `BEGIN`, and
  `with conn:` patterns across the file

A bare rewrite without a contract-locked test suite would either
introduce regressions silently (the worst class — only surfaces on the
live deploy under load) or trap us into a months-long debugging cycle.

The plan: write the test suite first, lock the *current* behavior into
fixtures, then rewrite the connection model and confirm zero output
drift.

---

## Phase 1 — Behavior-locking tests (against current code)

These tests must pass **on the current branch** before the rewrite
starts. They serve two purposes:

1. **Regression guard:** the rewrite must keep them green.
2. **Discovery:** writing them surfaces hidden assumptions / dead
   paths before the rewrite breaks them.

### 1.1 Single-thread invariants
- ✅ `_make_conn` returns a connection with all 9 PRAGMAs set
  (already covered by `test_make_conn_sets_busy_timeout` — extend to
  cover all 9 PRAGMAs).
- ✅ Each helper writes the rows it claims to write (one regression
  test per public function — currently missing for ~30 helpers).
- ✅ `_NoCloseConn.close()` rolls back uncommitted work without
  killing the connection.
- ✅ `_add_col` rejects out-of-allowlist tables / non-identifier col
  names (already covered by P7-DB-3 regex validation).

### 1.2 Connection-pool invariants
- ❌ Two sequential calls in the same thread get the SAME connection
  object (pool hit, not a fresh _make_conn).
- ❌ Two calls from different threads get DIFFERENT connection
  objects.
- ❌ A `_NoCloseConn` close() does not destroy the underlying conn —
  the next same-thread call gets the same physical connection back.
- ❌ Pool size is bounded — N threads → N connections, no leak past
  thread death.

### 1.3 Transaction semantics (the core DB-1 question)
- ❌ Writes that should be atomic (e.g. `save_positions`,
  `log_execution`, `write_scan_results`) all-commit-or-all-rollback.
- ❌ Mid-write process kill leaves the DB consistent (use a child
  process + SIGKILL fixture).
- ❌ Concurrent-from-other-thread reads during a single-thread write
  see either pre-write or post-write state, never a half-write.

### 1.4 Concurrent-writer matrix (the core DB-2/busy_timeout
question)
- ❌ N writers, M readers, 60-second soak — zero SQLITE_BUSY errors
  bubble up to the caller (the busy_timeout retry should absorb
  them).
- ❌ N writers all complete (no starvation under the retry policy).
- ❌ Read-only callers continue serving during a long write.

### 1.5 Cross-process invariants
- ❌ Subprocess A writes → Subprocess B reads → sees A's write within
  WAL checkpoint window.
- ❌ Subprocess A and B both writing concurrently — both writes
  succeed (busy_timeout kicks in, neither caller sees an error).

---

## Phase 2 — Failure injection

Once Phase 1 is green and locked, add deliberate-failure tests:

- **F.1** Force `executescript` mid-statement crash → DB consistent.
- **F.2** Force `OperationalError("database is locked")` mid-write →
  retry policy kicks in OR caller sees clean error (no half-state).
- **F.3** Force `IntegrityError` (FK violation) mid-transaction →
  whole transaction rolls back.
- **F.4** Force `_NoCloseConn` proxy close() raises → underlying
  connection leak detection.
- **F.5** Force WAL checkpoint mid-write → concurrent writer doesn't
  block past timeout.

---

## Phase 3 — Rewrite scope (informed by Phase 1 + 2)

Only after Phase 1 + 2 are committed and green:

1. **Switch connection factory to explicit `isolation_level="DEFERRED"`**
   instead of `""` (which puts SQLite in legacy auto-commit mode).
   This is the canonical mode for explicit transactions.

2. **Replace all manual `BEGIN`/`COMMIT` with `with conn:` blocks**.
   The `with conn:` context manager handles commit-on-success +
   rollback-on-exception correctly.

3. **Audit every function for `executescript` vs `execute`**.
   `executescript` runs in auto-commit mode regardless of
   isolation_level; reserve it for schema-init only. Data writes go
   through `execute` + explicit transaction.

4. **Replace `save_positions` raw `BEGIN`** with a `with conn:` block
   to align with the rest of the codebase (DB-4).

5. **Add `try / finally` around connection use** in every helper that
   currently relies on `_NoCloseConn.close()` for rollback. Make the
   rollback explicit.

6. **Re-run Phase 1 + 2 test suite — zero failures = ship**. Any
   failure means the rewrite changed observable behavior, which means
   we either fix the rewrite or update the test (with explicit
   reasoning in the commit message).

---

## Phase 4 — Cross-process file lock (parks-with-W-1 + P1 follow-up)

**Out of scope for this batch.** Tracked separately:
- P1's `update_alerts_config` is in-process only.
- W-1's wallet-state lock is in-process only.
- DB-1/DB-4 above is in-process only (busy_timeout helps cross-process
  but doesn't replace explicit serialization).

When Streamlit retires at D8, the cross-process surface shrinks to
FastAPI + agent. They can share the same module-level RLocks if they
import alerts.py / wallet_state.py from the same process. If they
truly run in separate processes, a `filelock`-style advisory lock is
the right fix for all three (alerts_config.json, wallet_reservations.json,
alerts.db). Defer that batch to post-D8.

---

## What I need from David

**Direction-level decisions before I start coding:**

1. **Test plan estimate:** Phase 1 alone is ~50 tests across ~80
   helper functions. ~3 days to write + verify. **Approve to proceed?**
2. **Acceptable downtime for the rewrite:** any helper change to
   `database.py` re-deploys to Render. If we want zero downtime, the
   rewrite ships behind a feature flag (env var `DB_NEW_TX_MODEL=1`)
   that defaults OFF for one deploy cycle, then ON. **Flag-gated or
   straight cutover?**
3. **Rollback policy:** if a regression surfaces post-deploy, do we
   `git revert` the commit and let auto-deploy roll back, or hold a
   pre-rewrite tag for `git checkout` recovery? **Tag the pre-state
   as `pre-db-rewrite-2026-05-XX` like the audit batches do?**

---

## Estimated wall-clock

| Phase | Effort |
|---|---|
| Phase 1 — behavior-locking tests | 2-3 days |
| Phase 2 — failure injection | 1 day |
| Phase 3 — rewrite | 1-2 days |
| Phase 4 — soak test on staging | 0.5 day |
| **Total** | **5-7 days** |

That's larger than the per-week budget; this batch likely runs across
the D7→D8 cutover window or as a post-cutover hardening pass.

---

## Cumulative DB-related contract status (end of 2026-05-03)

| Finding | Status |
|---|---|
| DB-1 (isolation_level + tx model) | TEST PLAN — this doc |
| DB-2 (PRAGMA busy_timeout) | ✅ closed `40a473e` |
| DB-3 (_add_col regex validation) | ✅ closed `40a473e` |
| DB-4 (save_positions raw BEGIN) | TEST PLAN — bundled with DB-1 |
| W-1 (wallet-state file lock) | DEFERRED — bundled into Phase 4 above |
| P1 (alerts.py race) | ✅ closed `4e72ec8` (in-process RLock; cross-process to Phase 4) |
