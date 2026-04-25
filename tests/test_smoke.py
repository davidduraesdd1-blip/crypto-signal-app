"""
Smoke tests for crypto-signal-app.

Catches the simplest failure modes — syntax errors, broken imports,
missing config constants, malformed module-level state — before they
hit the live deploy.

Run:
    pytest tests/ -v

These tests intentionally do NOT exercise:
  - Network calls (data_feeds, news_sentiment, websocket_feeds, etc.)
  - Streamlit AppTest harness for app.py (the app has heavy import-time
    work that needs proper mocks; add when integration coverage matures)
  - Signal math correctness (composite_signal, top_bottom_detector,
    risk_metrics — these need golden-fixture tests in dedicated files)

What they DO exercise:
  - Every top-level .py file parses as valid Python (no syntax errors).
  - config.py imports without crashing in a no-API-keys environment.
  - The brand/feature-flag shape of config matches expectations.
  - Key utility modules import cleanly without side effects.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── 1. Every top-level .py file parses ───────────────────────────────────────

# Discovered by walking the repo root, excluding the .claude worktree
# subtree (those are git-managed working copies of other branches and
# are tested separately under their own branch's tests/).
TOP_LEVEL_PY_FILES = sorted(
    p.name for p in REPO_ROOT.glob("*.py")
    if p.is_file()
)


@pytest.mark.parametrize("filename", TOP_LEVEL_PY_FILES)
def test_top_level_file_parses(filename: str) -> None:
    """Every top-level .py file must be syntactically valid Python."""
    path = REPO_ROOT / filename
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))


# ── 2. config.py imports and exposes expected shape ──────────────────────────

def test_config_imports() -> None:
    """config.py must import without crashing in an empty-env scenario."""
    cfg = importlib.import_module("config")
    assert cfg is not None


def test_config_has_api_key_slots() -> None:
    """
    config.py centralises API key reading. Each slot must exist as an
    attribute (value may be None when the env var is unset).
    """
    cfg = importlib.import_module("config")
    expected_slots = (
        "ANTHROPIC_API_KEY",
        "CRYPTOPANIC_API_KEY",
        "COINGECKO_API_KEY",
        "COINMARKETCAP_API_KEY",
        "ETHERSCAN_API_KEY",
    )
    for slot in expected_slots:
        assert hasattr(cfg, slot), f"config.py missing API key slot: {slot}"


def test_config_anthropic_enabled_is_bool() -> None:
    """ANTHROPIC_ENABLED is the AI master switch — must always be a bool."""
    cfg = importlib.import_module("config")
    assert isinstance(cfg.ANTHROPIC_ENABLED, bool)


def test_config_claude_model_strings() -> None:
    """
    Centralised LLM model names must be non-empty strings. Catches the
    common drift bug where the constant gets renamed without updating
    every call site.
    """
    cfg = importlib.import_module("config")
    assert isinstance(cfg.CLAUDE_MODEL, str) and cfg.CLAUDE_MODEL
    assert isinstance(cfg.CLAUDE_HAIKU_MODEL, str) and cfg.CLAUDE_HAIKU_MODEL


def test_config_tier1_pairs_well_formed() -> None:
    """
    TIER1_PAIRS must align with the CoinGecko and Binance lookup dicts.
    Every pair listed must have an entry in both maps.
    """
    cfg = importlib.import_module("config")
    pairs = set(cfg.TIER1_PAIRS)
    coingecko = set(cfg.TIER1_COINGECKO_IDS.keys())
    binance = set(cfg.TIER1_BINANCE_PAIRS.keys())
    assert pairs <= coingecko, f"pairs missing CoinGecko mapping: {pairs - coingecko}"
    assert pairs <= binance, f"pairs missing Binance mapping: {pairs - binance}"


# ── 3. Lightweight utility modules import without side effects ───────────────

@pytest.mark.parametrize(
    "module_name",
    [
        "utils_format",
        "utils_audit_schema",
        "glossary",
    ],
)
def test_pure_utility_module_imports(module_name: str) -> None:
    """
    Modules that are pure helpers (no Streamlit runtime, no network)
    must import cleanly. Catches accidental top-level side effects.
    """
    mod = importlib.import_module(module_name)
    assert mod is not None
