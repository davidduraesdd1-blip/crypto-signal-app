"""
scheduler.py — Crypto Signal Model v5.9.13

Standalone background scheduler — runs auto-scans and the AI feedback loop
independently of the Streamlit UI. The UI becomes a pure read-only dashboard
that can restart freely without losing any accumulated data.

Usage:
    python scheduler.py            # run on schedule forever
    python scheduler.py --now      # run one scan immediately and exit

Schedule is driven by the same alerts_config.json that the UI uses:
    autoscan_interval_minutes  (default 30)
    autoscan_quiet_hours_enabled / autoscan_quiet_start / autoscan_quiet_end
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Load .env before any project imports ──────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional

sys.path.insert(0, str(Path(__file__).parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

import database as _db
import crypto_model_core as model
import alerts as _alerts

# ── Logging ───────────────────────────────────────────────────────────────────
_log_dir = Path(__file__).parent / "data"
_log_dir.mkdir(exist_ok=True)
_log_file = _log_dir / "scheduler.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            _log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
DEFAULT_INTERVAL_MINUTES = 30
_scan_lock = threading.Lock()

# AUDIT-2026-05-03 (HIGH bug fix S-1): scheduler must re-read interval
# on every tick so live edits to autoscan_interval_minutes via the
# Settings page take effect without a process restart. We hold a
# module-level reference to the live scheduler + the current interval
# so run_scan_job can detect drift and reschedule itself.
_scheduler: "BlockingScheduler | None" = None
_current_interval_minutes: int = DEFAULT_INTERVAL_MINUTES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _in_quiet_hours(now_str: str, start_str: str, end_str: str) -> bool:
    """Return True if now_str (HH:MM UTC) falls in the [start, end) quiet window.
    Handles overnight wrap (e.g. 22:00–06:00)."""
    try:
        h, m   = map(int, now_str.split(":"))
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        now_m = h * 60 + m
        s_m   = sh * 60 + sm
        e_m   = eh * 60 + em
        if s_m <= e_m:            # same-day window e.g. 09:00–17:00
            return s_m <= now_m < e_m
        return now_m >= s_m or now_m < e_m   # overnight e.g. 22:00–06:00
    except Exception as _e:
        # AUDIT-2026-05-03 (LOW S-5): use the named module logger for parity
        # with the rest of the file (was `logging.debug` — module-level).
        logger.debug("[Scheduler] quiet_hours parse error: %s", _e)
        return False


def _get_interval() -> int:
    """Read autoscan_interval_minutes from alerts config; fall back to default."""
    try:
        cfg = _alerts.load_alerts_config()
        return int(cfg.get("autoscan_interval_minutes", DEFAULT_INTERVAL_MINUTES))
    except Exception as e:
        logger.debug("[Scheduler] Could not read interval from alerts config: %s", e)
        return DEFAULT_INTERVAL_MINUTES


# ── Scan job ──────────────────────────────────────────────────────────────────

def run_scan_job() -> None:
    """Full scan + feedback loop. Thread-safe — skips if already running."""
    if not _scan_lock.acquire(blocking=False):
        logger.warning("[Scheduler] Previous scan still running — skipping this trigger.")
        return

    try:
        # AUDIT-2026-05-03 (MEDIUM perf fix S-4): load alerts config once
        # at the top of the job and reuse for quiet-hours, the alerts
        # channels, and the interval re-read. Was calling
        # load_alerts_config() twice (line 106 + 152) despite the
        # explicit "load once, reuse" comment on what's now line 173.
        try:
            cfg = _alerts.load_alerts_config()
        except Exception as _e:
            logger.warning("[Scheduler] Failed to load alerts config (continuing with empty): %s", _e)
            cfg = {}

        # Quiet hours check
        try:
            if cfg.get("autoscan_quiet_hours_enabled"):
                now_str = datetime.now(timezone.utc).strftime("%H:%M")
                qs = cfg.get("autoscan_quiet_start", "22:00")
                qe = cfg.get("autoscan_quiet_end",   "06:00")
                if _in_quiet_hours(now_str, qs, qe):
                    logger.info("[Scheduler] Skipped — quiet hours active (%s–%s UTC)", qs, qe)
                    return
        except Exception as _qh_err:
            logger.debug("[Scheduler] quiet hours check failed (continuing): %s", _qh_err)

        logger.info("=" * 60)
        logger.info("SCAN STARTED — %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        logger.info("=" * 60)

        _db.write_scan_status(True, progress=0, pair="Starting scan...")

        # ── Run scan ──────────────────────────────────────────────────────────
        results = model.run_scan()
        model.append_to_master(results)

        # ── AI feedback loop ──────────────────────────────────────────────────
        try:
            model.run_feedback_loop()
        except Exception as _fb:
            logger.warning("[Scheduler] Feedback loop error (non-critical): %s", _fb)

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        _db.write_scan_results(results)
        _db.write_scan_status(False, timestamp=ts, error=None, progress=100)

        # ── Update paper positions ────────────────────────────────────────────
        try:
            # AUDIT-2026-05-03 (LOW S-6): defensive accessors. The previous
            # `{r["pair"]: r.get("price_usd", 0) for r in results if r.get("price_usd")}`
            # raised KeyError if a result row was missing the pair key, and
            # the truthy filter `if r.get("price_usd")` silently dropped
            # legitimate `0.0` prices (failed-fetch edge case where 0 is the
            # actual fetched value vs missing).
            prices = {
                r.get("pair"): r["price_usd"]
                for r in results
                if r.get("pair") and r.get("price_usd") is not None
            }
            if prices:
                model.update_positions(prices)
                # P6: Auto-close any paper positions older than 14 days at current prices
                closed = _db.auto_close_stale_positions(prices, hold_days=14)
                if closed:
                    logger.info("[Scheduler] Auto-closed %d stale paper position(s)", closed)
        except Exception as _pe:
            logger.warning("[Scheduler] Position update error (non-critical): %s", _pe)

        # ── Send alerts ───────────────────────────────────────────────────────
        # AUDIT-2026-05-03 (MEDIUM perf S-4): reuse the cfg loaded at the top
        # of run_scan_job rather than reloading. Was a redundant disk read.
        try:
            _alerts.send_scan_email_alerts(results, cfg)
        except Exception as _e:
            logger.warning("[Scheduler] Email alert failed (non-critical): %s", _e)
        try:
            _alerts.check_watchlist_alerts(results, cfg)
        except Exception as _e:
            logger.warning("[Scheduler] Watchlist alert failed (non-critical): %s", _e)

        logger.info("SCAN COMPLETE — %d pair(s) processed", len(results))
        logger.info("=" * 60)

        # AUDIT-2026-05-03 (HIGH bug S-1): re-read interval from the live
        # config and reschedule the autoscan job if the operator changed it
        # via the Settings page. This closes the "config edits never take
        # effect until process restart" gap. Done at the bottom of the job
        # so the change applies to the NEXT trigger, not this one.
        try:
            global _current_interval_minutes
            new_interval = int(cfg.get("autoscan_interval_minutes", _current_interval_minutes))
            if _scheduler is not None and new_interval != _current_interval_minutes and new_interval > 0:
                _scheduler.reschedule_job(
                    "autoscan",
                    trigger=IntervalTrigger(minutes=new_interval),
                )
                logger.info(
                    "[Scheduler] Interval reschedule: %d → %d minutes (live config edit)",
                    _current_interval_minutes, new_interval,
                )
                _current_interval_minutes = new_interval
        except Exception as _re_err:
            logger.warning("[Scheduler] Interval reschedule failed (non-fatal): %s", _re_err)

    except Exception as e:
        logger.exception("[Scheduler] Scan failed: %s", e)
        try:
            _db.write_scan_status(False, error=str(e), progress=0)
        except Exception as _status_err:
            logger.debug("[Scheduler] scan status write failed: %s", _status_err)
    finally:
        _scan_lock.release()


# ── Graceful resume ───────────────────────────────────────────────────────────

def _resume_from_db() -> None:
    """Log current DB state so we know what data has already been collected."""
    try:
        status = _db.read_scan_status()
        last_ts = status.get("timestamp")
        if last_ts:
            logger.info("[Scheduler] Resuming — last scan: %s", last_ts)
        else:
            logger.info("[Scheduler] No prior scan found — starting fresh.")

        positions = _db.load_positions()
        logger.info("[Scheduler] Open positions loaded: %d", len(positions))

        weights = _db.load_weights()
        if weights:
            logger.info("[Scheduler] Model weights loaded: %d weight(s)", len(weights))
        else:
            logger.info("[Scheduler] No saved model weights — will build from scratch.")
    except Exception as e:
        logger.warning("[Scheduler] Resume check failed (non-critical): %s", e)

    # P1: Startup catch-up — resolve any pending feedback outcomes right away
    try:
        model.run_feedback_loop()
        logger.info("[Scheduler] Startup feedback catch-up complete")
    except Exception as e:
        logger.debug("[Scheduler] Startup feedback catch-up (non-critical): %s", e)


# ── Scheduler entry point ─────────────────────────────────────────────────────

def start_scheduler() -> None:
    """Start the blocking scheduler — runs forever until Ctrl+C."""
    _resume_from_db()

    global _scheduler, _current_interval_minutes
    _current_interval_minutes = _get_interval()
    logger.info("[Scheduler] Auto-scan interval: %d minutes", _current_interval_minutes)

    _scheduler = BlockingScheduler(
        job_defaults={
            "coalesce":          True,
            "max_instances":     1,
            "misfire_grace_time": 300,
        },
        timezone="UTC",
    )

    _scheduler.add_job(
        run_scan_job,
        trigger=IntervalTrigger(minutes=_current_interval_minutes),
        id="autoscan",
        name=f"Crypto Signal Auto-Scan (every {_current_interval_minutes}m)",
    )

    logger.info("[Scheduler] Running standalone. Press Ctrl+C to stop.")
    logger.info("[Scheduler] Running initial scan immediately...")

    # Initial scan before the scheduler loop starts
    # Join with timeout so a hung initial scan cannot block scheduler startup forever
    _t = threading.Thread(target=run_scan_job, daemon=True)
    _t.start()
    _t.join(timeout=1800)  # 30-minute hard cap; scheduler proceeds regardless

    try:
        _scheduler.start()
    except KeyboardInterrupt:
        logger.info("[Scheduler] Stopped by user.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        # python scheduler.py --now  (run once and exit)
        _resume_from_db()
        run_scan_job()
    else:
        # python scheduler.py  (run on schedule forever)
        start_scheduler()
