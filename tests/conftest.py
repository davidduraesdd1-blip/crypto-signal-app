"""
Session-level test setup for crypto-signal-app.

pytest evaluates conftest.py before any test module imports. We use that
window to:

  1. Make the repo root importable (so tests can `import config`,
     `import data_feeds`, etc. exactly the way app.py does).
  2. Set safe-default environment variables so config.py doesn't blow up
     in an empty CI environment.
  3. Guard against accidental network hits during smoke tests by leaving
     real API keys unset (config.py is designed to gracefully no-op when
     keys are missing).

This is a minimal smoke-level harness. Heavier integration mocks
(stubbing yfinance, OKX, news_sentiment, etc.) belong in dedicated
test files when those modules grow real coverage.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure repo root is importable for `import config`, `import data_feeds`, etc.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Safe defaults for any env vars the app reads. Tests should NEVER hit
# real APIs, so leaving secrets unset is correct — config.py is designed
# to detect absence and disable downstream features.
os.environ.setdefault("ANTHROPIC_ENABLED", "false")
os.environ.setdefault("DEMO_MODE", "true")
