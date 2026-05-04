# Scheduler inventory — 2026-05-04

Source of truth: `scheduler.py` @ HEAD `f0499a8` on `phase-d/next-fastapi-cutover`.

## Jobs

**One distinct job** registered with APScheduler `BlockingScheduler`:

- **`autoscan`** — `run_scan_job()` (`scheduler.py:128`).
  Full pipeline: load alerts config → quiet-hours check → `model.run_scan()` →
  `model.append_to_master(results)` → `model.run_feedback_loop()` →
  `db.write_scan_results` / `write_scan_status` → `model.update_positions(prices)`
  → `db.auto_close_stale_positions(hold_days=14)` → `alerts.send_scan_email_alerts`
  → `alerts.check_watchlist_alerts` → live re-read of interval and self-reschedule.
  Plus a one-time startup `model.run_feedback_loop()` catch-up in `_resume_from_db()`.

## Cadence

- Configured via `autoscan_interval_minutes` in `alerts_config.json`. **Default 30 min**.
- Re-read on every tick — live edits via Settings page take effect on the *next* trigger.
- Operator-settable: nothing in the UI/config layer hard-floors at 15 min, so a user
  could set `autoscan_interval_minutes: 5` (or 1) — **flagged as a sub-15-min risk**.

## API-vs-direct

- `run_scan_job` calls Python functions directly — it does **not** hit any HTTP endpoint.
- An HTTP endpoint `POST /scan/trigger` exists in `api.py:713` and runs
  `_run_scan_bg` (`api.py:289`), but `_run_scan_bg` is a **strict subset** of
  `run_scan_job`. It does:
  `run_scan` → `write_scan_results` → `write_scan_status` → `send_scan_email_alerts`.
  It does **NOT** do: `append_to_master`, `run_feedback_loop`, `update_positions`,
  `auto_close_stale_positions`, `check_watchlist_alerts`, quiet-hours check, or
  startup feedback catch-up.
  → A naïve cron that curls `/scan/trigger` will break the AI feedback loop,
  paper-position tracking, master CSV continuity, and watchlist alerts.

## Shared state

- `_scan_lock` (`threading.Lock`, in-process) — prevents concurrent runs.
  Irrelevant under cron (each invocation is a fresh process; concurrency would need
  a DB / file lock).
- `_scheduler` and `_current_interval_minutes` (module-level) — only used so the job
  can self-reschedule when the interval config changes. Moot under cron.
- DB-backed: scan_status, scan_results, master CSV, paper positions, model weights,
  feedback rows. **All persistent — cron-safe.**
- `data/scheduler.log` rotating file handler (5 MB × 3) — file-based, cron-safe but
  needs the persistent disk mount to survive Render redeploys.

## Where it runs now

- `render.yaml` declares **only** the `crypto-signal-api` web service
  (`uvicorn api:app`). No `worker` service. No `cron` block.
- No `Procfile` at repo root.
- `runtime.txt` = `python-3.11`.
- → `scheduler.py` is **not currently running on Render**. The autoscan loop has
  been dormant on the FastAPI deploy.

## Sub-15-min flag

- Default 30 min is fine for any cron tier. **Risk:** any operator change of
  `autoscan_interval_minutes` to <15 silently exceeds Render Cron's 15-min
  minimum (Cron tier limit) and would no-op until raised.
