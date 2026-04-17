"""
evaluate_headless.py — SuperGrok Standalone Feedback Evaluator (Proposal 3)

Resolves pending feedback_log outcomes against real exchange prices and
auto-closes stale paper trade positions without needing the Streamlit app.

Usage:
    python evaluate_headless.py

Register with Windows Task Scheduler to run every 6 hours:
    Action:  "python C:\\path\\to\\SuperGrok Mathematically Model\\evaluate_headless.py"
    Trigger: Daily, repeat every 6 hours

What it does:
  1. Connects to Binance via CCXT (no API key needed for price fetch)
  2. Resolves all pending feedback_log rows whose hold period has elapsed
  3. Auto-closes stale paper positions (> 14 days old) at current prices
  4. Updates dynamic indicator weights from resolved P&L data
  5. Auto-retrains LightGBM if 50+ resolved samples available
  6. Exports a git-tracked checkpoint JSON
  7. Logs results to data/headless_evaluator.log

No Streamlit, no UI, no user interaction required.
All accumulated intelligence is saved to data/feedback_checkpoint.json
and loaded automatically when the Streamlit app next starts.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))

# ── Logging ───────────────────────────────────────────────────────────────────
_log_dir  = Path(__file__).parent / "data"
_log_dir.mkdir(exist_ok=True)
_log_file = _log_dir / "headless_evaluator.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            _log_file, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)


def run_evaluation() -> bool:
    """Run one evaluation cycle: resolve outcomes → auto-close → update weights → checkpoint."""
    start = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("HEADLESS EVALUATOR — %s", start.strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    try:
        import database as _db
        import crypto_model_core as model

        # Step 1: Run full feedback loop (resolves outcomes, updates weights, checkpoints)
        logger.info("Running feedback loop (resolve + weights + checkpoint)...")
        model.run_feedback_loop()
        logger.info("Feedback loop complete")

        # Step 2: Auto-close stale paper positions
        try:
            # Fetch current prices for position update
            ex = model.get_exchange_instance(model.TA_EXCHANGE)
            if ex:
                positions = _db.load_positions()
                if positions:
                    prices: dict = {}
                    for pos in positions:
                        pair = pos.get("pair")
                        if not pair:
                            continue
                        try:
                            ticker = ex.fetch_ticker(pair)
                            prices[pair] = float(ticker.get("last", 0))
                        except Exception as _ticker_err:
                            logger.debug("Ticker fetch failed for %s: %s", pair, _ticker_err)
                    if prices:
                        closed = _db.auto_close_stale_positions(prices, hold_days=14)
                        if closed:
                            logger.info("Auto-closed %d stale paper position(s)", closed)
        except Exception as _pe:
            logger.warning("Auto-close stale positions failed (non-critical): %s", _pe)

        # Step 3: Export checkpoint
        _db.export_feedback_checkpoint()

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        logger.info("Evaluation complete in %.1fs", elapsed)
        return True

    except Exception as e:
        logger.exception("Headless evaluation failed: %s", e)
        return False


if __name__ == "__main__":
    ok = run_evaluation()
    sys.exit(0 if ok else 1)
