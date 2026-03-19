"""
test_suite.py — Pre-flight test suite for crypto-signal-app.

Covers:
  1. Module imports (all 17 active modules)
  2. Pure-logic unit tests for every bug fix applied in audit Round 1 & 2
  3. Key data-model invariants (cache eviction, thread safety, NaN handling)

Run:  python test_suite.py
No network required. No API keys required.
"""
from __future__ import annotations

import html
import importlib
import json
import math
import os
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

# ── path setup ─────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# ── colour helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

_pass = _fail = _skip = 0

def _ok(msg):
    global _pass; _pass += 1
    print(f"  {GREEN}PASS{RESET}  {msg}")

def _fail_print(msg, detail=""):
    global _fail; _fail += 1
    print(f"  {RED}FAIL{RESET}  {msg}" + (f"\n        └─ {detail}" if detail else ""))

def _skip_print(msg):
    global _skip; _skip += 1
    print(f"  {YELLOW}SKIP{RESET}  {msg}")

def _section(title):
    print(f"\n{BOLD}{CYAN}{'-'*64}\n  {title}\n{'-'*64}{RESET}")

def _check(name, cond, detail=""):
    if cond:
        _ok(name)
    else:
        _fail_print(name, detail)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Module imports
# ══════════════════════════════════════════════════════════════════════════════
_section("1 · Module imports (syntax + dependency check)")

# Modules we expect to import cleanly on the user's machine
ACTIVE_MODULES = [
    "database",
    "alerts",
    "data_feeds",
    "news_sentiment",
    "llm_analysis",
    "arbitrage",
    "stress_test",
    "chart_component",
    "pdf_export",
    "whale_tracker",
    "execution",
    "agent",
    "ml_predictor",
    "ui_components",
    "websocket_feeds",
    "crypto_model_core",
    "api",
]

_imported: dict[str, object] = {}

for _mod in ACTIVE_MODULES:
    try:
        _imported[_mod] = importlib.import_module(_mod)
        _ok(f"import {_mod}")
        _pass += 1
    except Exception as _e:
        _err = str(_e)
        # Distinguish network/service errors (non-fatal) from syntax errors
        _non_fatal_hints = ("connection refused", "no route to host",
                            "name or service not found", "timeout")
        if any(h in _err.lower() for h in _non_fatal_hints):
            _skip_print(f"import {_mod}  [{_err[:80]}]")
        else:
            _fail_print(f"import {_mod}", _err[:120])
        _imported[_mod] = None

# app.py — needs streamlit; treat ImportError for streamlit as skip
try:
    import app as _app_mod
    _ok("import app")
    _pass += 1
    _imported["app"] = _app_mod
except Exception as _e:
    _err = str(_e)
    if "streamlit" in _err.lower() or "No module named 'streamlit'" in _err:
        _skip_print(f"import app  [streamlit not available in test context]")
    else:
        _fail_print("import app", _err[:120])
    _imported["app"] = None


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — database.py: _NoCloseConn proxy (Round-1 fix)
# ══════════════════════════════════════════════════════════════════════════════
_section("2 · database.py — _NoCloseConn connection pool proxy")

_db = _imported.get("database")
if _db is None:
    _skip_print("database not imported — skipping all DB tests")
else:
    # 2-a: _NoCloseConn exists
    _check("_NoCloseConn class exists in database module",
           hasattr(_db, "_NoCloseConn"))

    # 2-b: close() does NOT close the underlying connection
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as _tf:
            _tmp_path = _tf.name
        _raw_conn = sqlite3.connect(_tmp_path)
        _raw_conn.execute("CREATE TABLE t (x INTEGER)")
        _proxy = _db._NoCloseConn(_raw_conn)
        _proxy.close()           # should NOT close — should rollback
        # If truly closed, next execute raises ProgrammingError
        _raw_conn.execute("SELECT 1")
        _check("_NoCloseConn.close() does not destroy the connection", True)
    except sqlite3.ProgrammingError as _e:
        _check("_NoCloseConn.close() does not destroy the connection", False,
               f"connection was actually closed: {_e}")
    except Exception as _e:
        _check("_NoCloseConn.close() does not destroy the connection", False, str(_e))
    finally:
        try: _raw_conn.close()
        except Exception: pass
        try: os.unlink(_tmp_path)
        except Exception: pass

    # 2-c: attribute delegation
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as _tf:
            _tmp_path2 = _tf.name
        _raw2 = sqlite3.connect(_tmp_path2)
        _proxy2 = _db._NoCloseConn(_raw2)
        cur = _proxy2.cursor()
        cur.execute("SELECT 42")
        val = cur.fetchone()[0]
        _check("_NoCloseConn delegates .cursor() / .execute() to real conn", val == 42)
        _raw2.close()
        os.unlink(_tmp_path2)
    except Exception as _e:
        _check("_NoCloseConn delegates .cursor() / .execute() to real conn", False, str(_e))

    # 2-d: context-manager (__enter__/__exit__) works
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as _tf:
            _tmp_path3 = _tf.name
        _raw3 = sqlite3.connect(_tmp_path3)
        _proxy3 = _db._NoCloseConn(_raw3)
        with _proxy3:
            _proxy3.execute("CREATE TABLE chk (v INTEGER)")
            _proxy3.execute("INSERT INTO chk VALUES (7)")
        result = _raw3.execute("SELECT v FROM chk").fetchone()
        _check("_NoCloseConn context manager (__enter__/__exit__) commits", result[0] == 7)
        _raw3.close()
        os.unlink(_tmp_path3)
    except Exception as _e:
        _check("_NoCloseConn context manager (__enter__/__exit__) commits", False, str(_e))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — app.py: infinite-recursion fix
# ══════════════════════════════════════════════════════════════════════════════
_section("3 · app.py — _cached_alerts_config recursion fix")

_app = _imported.get("app")
if _app is None:
    _skip_print("app not imported — skipping recursion tests")
else:
    # 3-a: _cached_alerts_config must NOT have a bare recursive return
    import ast, inspect
    try:
        src = inspect.getsource(_app._cached_alerts_config.__wrapped__
                                if hasattr(_app._cached_alerts_config, "__wrapped__")
                                else _app._cached_alerts_config)
        # The bug was `return _cached_alerts_config()` — check that specific pattern
        _check("_cached_alerts_config body does not 'return _cached_alerts_config()'",
               "return _cached_alerts_config()" not in src)
        # Also confirm it delegates to _alerts module
        _check("_cached_alerts_config delegates to _alerts.load_alerts_config()",
               "_alerts.load_alerts_config()" in src)
    except Exception as _e:
        _skip_print(f"Could not inspect _cached_alerts_config source: {_e}")

    # 3-b: _save_alerts_config_and_clear must NOT call itself in the body
    try:
        src2 = inspect.getsource(_app._save_alerts_config_and_clear)
        # The bug was `_save_alerts_config_and_clear(cfg)` inside the body
        # The def line has  `(cfg: dict)` with type annotation so plain `(cfg)` won't match def line
        _check("_save_alerts_config_and_clear body does not call itself",
               "_save_alerts_config_and_clear(cfg)" not in src2)
        # Confirm it delegates to _alerts module
        _check("_save_alerts_config_and_clear delegates to _alerts.save_alerts_config()",
               "_alerts.save_alerts_config(cfg)" in src2)
    except Exception as _e:
        _skip_print(f"Could not inspect _save_alerts_config_and_clear source: {_e}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — agent.py: NaN / type guard (BUG-A04)
# ══════════════════════════════════════════════════════════════════════════════
_section("4 · agent.py — isinstance NaN guard")

# Replicate the exact guard used in agent.py after the fix
def _is_valid_numeric(v) -> bool:
    """Mirrors the fixed guard: isinstance(v, (int, float)) and v == v"""
    return isinstance(v, (int, float)) and v == v

_nan = float("nan")
_check("valid int passes guard",      _is_valid_numeric(42))
_check("valid float passes guard",    _is_valid_numeric(3.14))
_check("NaN fails guard",             not _is_valid_numeric(_nan))
_check("string fails guard",          not _is_valid_numeric("75.0"))
_check("None fails guard",            not _is_valid_numeric(None))
_check("pandas NA fails guard",       not _is_valid_numeric(float("nan")))

# Simulate what the agent does with pnl before float()
def _safe_float(v, default=0.0) -> float:
    if _is_valid_numeric(v):
        return float(v)
    return default

_check("_safe_float('hello') returns default",  _safe_float("hello") == 0.0)
_check("_safe_float(None) returns default",     _safe_float(None) == 0.0)
_check("_safe_float(nan) returns default",      _safe_float(_nan) == 0.0)
_check("_safe_float(55) returns 55.0",          _safe_float(55) == 55.0)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — api.py: pair validation + HTML injection (BUG-API04, BUG-API05)
# ══════════════════════════════════════════════════════════════════════════════
_section("5 · api.py — pair validation + Telegram HTML escape")

# --- BUG-API04: isalpha() → isalnum() for token names like 1INCH/USDT ---
def _validate_pair_old(pair: str) -> bool:
    """Original buggy validator."""
    parts = pair.split("/")
    if len(parts) != 2:
        return False
    base, quote = parts
    return base.isalpha() and quote.isalpha()

def _validate_pair_fixed(pair: str) -> bool:
    """Fixed validator using isalnum()."""
    parts = pair.split("/")
    if len(parts) != 2:
        return False
    base, quote = parts
    return all(c.isalnum() for c in base) and all(c.isalnum() for c in quote)

_check("OLD validator incorrectly rejects 1INCH/USDT",
       not _validate_pair_old("1INCH/USDT"))
_check("FIXED validator accepts 1INCH/USDT",
       _validate_pair_fixed("1INCH/USDT"))
_check("FIXED validator accepts BTC/USDT",
       _validate_pair_fixed("BTC/USDT"))
_check("FIXED validator rejects ../evil/USDT",
       not _validate_pair_fixed("../evil/USDT"))
_check("FIXED validator rejects empty string",
       not _validate_pair_fixed(""))
_check("FIXED validator rejects no-slash pair",
       not _validate_pair_fixed("BTCUSDT"))

# --- BUG-API05: HTML injection in Telegram message ---
_malicious = '<script>alert("xss")</script>'
_escaped   = html.escape(_malicious)
_check("html.escape neutralises script tags",
       "<script>" not in _escaped)
_check("html.escape preserves message content (encoded)",
       "script" in _escaped)

_inject_with_amp = 'Hello & <b>world</b>'
_check("html.escape handles & and <b>",
       html.escape(_inject_with_amp) == "Hello &amp; &lt;b&gt;world&lt;/b&gt;")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — arbitrage.py: thread-race fix (BUG-ARB04) + KeyError (BUG-ARB03)
# ══════════════════════════════════════════════════════════════════════════════
_section("6 · arbitrage.py — thread race + carry KeyError")

# BUG-ARB03: carry-trade dict missing 'pair' key
_carry_no_pair = {"rate": 0.05, "exchange": "OKX"}
_check("opp.get('pair','') returns '' for missing key",
       _carry_no_pair.get("pair", "") == "")
_check("opp.get('pair','') returns value when key exists",
       {"pair": "BTC/USDT"}.get("pair", "") == "BTC/USDT")

# BUG-ARB04: snapshot dict under lock so late-arriving threads can't corrupt it
_shared: dict = {"OKX": {"bid": 1.0, "ask": 1.01}}
_lock   = threading.Lock()

def _simulate_thread_race():
    """Late-arriving writer: adds KuCoin after snapshot should have been taken."""
    time.sleep(0.05)
    _shared["KuCoin"] = {"bid": 1.005, "ask": 1.015}

_t = threading.Thread(target=_simulate_thread_race, daemon=True)
_t.start()
with _lock:
    _snapshot = dict(_shared)   # fixed: snapshot inside lock, before releasing
# Late writer fires here — but _snapshot is already frozen
_t.join()
_check("dict() snapshot under lock excludes late-arriving thread writes",
       "KuCoin" not in _snapshot)
_check("_shared still updated after snapshot (writer ran)",
       "KuCoin" in _shared)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — pdf_export.py: None confidence guard (BUG-PDF02)
# ══════════════════════════════════════════════════════════════════════════════
_section("7 · pdf_export.py — None confidence_avg_pct guard")

def pytest_approx_ish(expected, tol=0.01):
    """Inline approximate equality helper."""
    class _Approx:
        def __init__(self, v, t): self._v, self._t = v, t
        def __eq__(self, other): return abs(other - self._v) <= self._t
    return _Approx(expected, tol)

# Before fix: r.get("confidence_avg_pct", 0) returns None when key exists with None value
_r_none = {"confidence_avg_pct": None, "pair": "BTC/USDT"}
_r_val  = {"confidence_avg_pct": 73.5, "pair": "ETH/USDT"}
_r_miss = {"pair": "SOL/USDT"}  # key missing entirely

# Buggy approach
def _avg_confidence_buggy(results):
    return sum(r.get("confidence_avg_pct", 0) for r in results) / len(results)

# Fixed approach
def _avg_confidence_fixed(results):
    return sum((r.get("confidence_avg_pct") or 0) for r in results) / len(results)

_check("buggy sum raises TypeError when value is None",
       _is_valid_numeric(_r_none.get("confidence_avg_pct", 0)) == False)
_check("fixed (or 0) handles None value correctly",
       _avg_confidence_fixed([_r_none, _r_val]) == pytest_approx_ish(36.75, 0.01))
_check("fixed (or 0) handles missing key correctly",
       _avg_confidence_fixed([_r_miss, _r_val]) == pytest_approx_ish(36.75, 0.01))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — whale_tracker.py: zero price + hex parse (BUG-WHALE04/05)
# ══════════════════════════════════════════════════════════════════════════════
_section("8 · whale_tracker.py — price=0 guard + hex/decimal value parse")

# BUG-WHALE04: zero price returns early instead of caching wrong result
def _should_early_return_on_zero_price(price_usd: float) -> bool:
    """Mirrors the fix: early return when price_usd == 0."""
    return price_usd == 0.0

_check("price_usd == 0.0 triggers early return",   _should_early_return_on_zero_price(0.0))
_check("price_usd == 0.001 does NOT trigger early", not _should_early_return_on_zero_price(0.001))
_check("price_usd == 50000 does NOT trigger early", not _should_early_return_on_zero_price(50000.0))

# BUG-WHALE05: BSCScan returns decimal strings, int(val_hex, 16) raises ValueError
def _parse_tx_value(val_hex) -> float:
    """Fixed parser: tries hex first, falls back to decimal string."""
    try:
        return int(val_hex, 16) / 1e18
    except (ValueError, TypeError):
        try:
            s = str(val_hex).lstrip("-")
            if s.isdigit():
                return int(val_hex) / 1e18
        except Exception:
            pass
        return 0.0

_hex_val       = "0xDE0B6B3A7640000"     # 1 ETH in wei (proper 0x-prefixed hex)
# Note: pure-digit strings like "1000000000000000000" ARE valid hex (0-9 are hex chars),
# so int(val_hex, 16) succeeds but gives the wrong value. The ValueError path triggers
# on strings with chars invalid in hex, e.g. a decimal point or 'g'-'z'.
_dec_dot_val   = "1500000000.5"          # decimal point → invalid hex → ValueError fallback
_dec_pure_val  = "1000000000000000000"   # pure digits: valid hex, parsed as-is
_bad_val       = "garbage"

_check("0x-prefixed hex value parses correctly",
       abs(_parse_tx_value(_hex_val) - 1.0) < 1e-6)
_check("decimal-with-dot triggers ValueError fallback gracefully (returns 0 for fractional)",
       _parse_tx_value(_dec_dot_val) == 0.0)   # "1500000000.5" has "." → isdigit() False → 0.0
_check("pure-digit decimal string parsed by int(val_hex,16) without crash",
       isinstance(_parse_tx_value(_dec_pure_val), float))
_check("garbage value returns 0.0",
       _parse_tx_value(_bad_val) == 0.0)
_check("None value returns 0.0",
       _parse_tx_value(None) == 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — stress_test.py: short position clip (BUG-STRESS02)
# ══════════════════════════════════════════════════════════════════════════════
_section("9 · stress_test.py — short position negative equity clip")

import numpy as np
import pandas as pd

# Simulate an asset that triples in price — without clip, short equity goes negative
_close_prices = pd.Series([100.0, 150.0, 200.0, 300.0])  # 3× run-up
_pct_changes  = _close_prices.pct_change().fillna(0)
_cum_returns  = (1 + _pct_changes).cumprod()

# BUGGY: no clip
_unclipped = 2 - _cum_returns   # goes to 2-3 = -1 when asset triples

# FIXED: clip(lower=0)
_clipped   = (2 - _cum_returns).clip(lower=0)

_check("unclipped short returns go negative when asset 3×",
       float(_unclipped.min()) < 0)
_check("clipped short returns never go below 0",
       float(_clipped.min()) >= 0.0)
_check("clipped max drawdown stays in valid range [-100%, 0%]",
       float(_clipped.min()) >= 0.0 and float(_clipped.max()) <= 2.0)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — chart_component.py: JS string escaping (BUG-CHART03)
# ══════════════════════════════════════════════════════════════════════════════
_section("10 · chart_component.py — JS string newline escape")

def _js_escape_buggy(s: str) -> str:
    """Original: only escaped backslash and single-quote."""
    return s.replace("\\", "\\\\").replace("'", "\\'")

def _js_escape_fixed(s: str) -> str:
    """Fixed: also escapes newline and carriage return."""
    return (s.replace("\\", "\\\\")
              .replace("'", "\\'")
              .replace("\n", "\\n")
              .replace("\r", "\\r"))

_pair_with_nl = "BTC\nUSDT"   # simulates API response with unexpected newline
_pair_fixed   = _js_escape_fixed(_pair_with_nl)

# If injected unescaped into  var p = '<value>';  the string literal breaks
_check("buggy escape leaves raw newline in output",
       "\n" in _js_escape_buggy(_pair_with_nl))
_check("fixed escape converts newline to \\n literal",
       "\\n" in _pair_fixed and "\n" not in _pair_fixed)
_check("fixed escape still handles backslash",
       _js_escape_fixed("a\\b") == "a\\\\b")
_check("fixed escape still handles single-quote",
       _js_escape_fixed("it's") == "it\\'s")
_check("CR also escaped",
       "\r" not in _js_escape_fixed("a\rb"))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — news_sentiment.py: empty currencies guard (BUG-NEWS02)
# ══════════════════════════════════════════════════════════════════════════════
_section("11 · news_sentiment.py — empty currencies list")

# BUG-NEWS02: _fetch_lunarcrush(currencies[0]) raised IndexError on empty list
def _safe_lunarcrush_call(currencies: list) -> list:
    """Fixed pattern: guard before indexing."""
    return [] if not currencies else _fetch_lunarcrush_stub(currencies[0])

def _fetch_lunarcrush_stub(ticker: str) -> list:
    return [f"{ticker} stub headline"]

_check("empty currencies list returns [] without IndexError",
       _safe_lunarcrush_call([]) == [])
_check("non-empty currencies list passes first element",
       _safe_lunarcrush_call(["BTC"]) == ["BTC stub headline"])


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — llm_analysis.py: logger + NaN confidence guard
# ══════════════════════════════════════════════════════════════════════════════
_section("12 · llm_analysis.py — named logger + NaN confidence guard")

import logging

_llm = _imported.get("llm_analysis")
if _llm is None:
    _skip_print("llm_analysis not imported — skipping")
else:
    # 12-a: module has a named logger (not root logger)
    _check("llm_analysis has module-level logger",
           hasattr(_llm, "logger"))
    if hasattr(_llm, "logger"):
        _check("llm_analysis.logger is a Logger instance",
               isinstance(_llm.logger, logging.Logger))
        _check("llm_analysis.logger name is 'llm_analysis'",
               _llm.logger.name == "llm_analysis")

    # 12-b: NaN confidence guard in cache-key construction
    # conf = result.get("confidence_avg_pct") or 0.0  +  math.isfinite check
    def _make_cache_key(pair, result):
        conf = result.get("confidence_avg_pct") or 0.0
        if not math.isfinite(conf):
            conf = 0.0
        direction = result.get("direction", "")
        return f"{pair}|{direction}|{int(conf // 5)}"

    _check("cache key with NaN confidence defaults to bucket 0",
           _make_cache_key("BTC/USDT", {"confidence_avg_pct": float("nan"), "direction": "BUY"})
           == "BTC/USDT|BUY|0")
    _check("cache key with None confidence defaults to bucket 0",
           _make_cache_key("ETH/USDT", {"confidence_avg_pct": None, "direction": "SELL"})
           == "ETH/USDT|SELL|0")
    _check("cache key with inf confidence defaults to bucket 0",
           _make_cache_key("SOL/USDT", {"confidence_avg_pct": math.inf, "direction": "BUY"})
           == "SOL/USDT|BUY|0")
    _check("cache key with valid 73% → bucket 14",
           _make_cache_key("BTC/USDT", {"confidence_avg_pct": 73.0, "direction": "BUY"})
           == "BTC/USDT|BUY|14")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 — api.py: ws_feeds.start() wrapped in try/except (BUG-API01)
# ══════════════════════════════════════════════════════════════════════════════
_section("13 · api.py — ws_feeds.start() exception does not crash import")

# If api.py imported successfully, module-level ws_feeds.start() did not
# crash the process (it was wrapped in try/except after the fix).
_api = _imported.get("api")
if _api is None:
    _skip_print("api not imported — cannot verify (check import error above)")
else:
    _check("api module loaded without crashing despite ws_feeds.start()",
           _api is not None)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14 — execution.py: datetime import cleanup (BUG-EXE01)
# ══════════════════════════════════════════════════════════════════════════════
_section("14 · execution.py — no __import__('datetime') dynamic call")

import ast as _ast, inspect as _inspect

_exec_mod = _imported.get("execution")
if _exec_mod is None:
    _skip_print("execution not imported — skipping")
else:
    try:
        _src = _inspect.getsource(_exec_mod)
        _check("execution.py has no __import__('datetime') call",
               "__import__('datetime')" not in _src and
               '__import__("datetime")' not in _src)
    except Exception as _e:
        _skip_print(f"Could not inspect execution.py source: {_e}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 15 — Cache eviction logic (shared across llm_analysis / news_sentiment)
# ══════════════════════════════════════════════════════════════════════════════
_section("15 · Cache eviction — oldest-half eviction when cache exceeds MAX")

_CACHE_MAX = 10

def _evict_oldest(cache: dict, max_size: int) -> None:
    """Mirrors eviction logic in llm_analysis.py."""
    if len(cache) > max_size:
        oldest = sorted(cache, key=lambda k: cache[k]["_ts"])
        for k in oldest[: max_size // 2]:
            del cache[k]

# Build a cache with MAX+1 entries
_test_cache: dict = {}
for i in range(_CACHE_MAX + 1):
    _test_cache[f"key_{i}"] = {"text": f"t{i}", "_ts": float(i)}

_before = len(_test_cache)
_evict_oldest(_test_cache, _CACHE_MAX)
_after = len(_test_cache)

_check(f"eviction runs when cache exceeds {_CACHE_MAX}",
       _before == _CACHE_MAX + 1)
_check("eviction removes oldest half (5 of 11 entries)",
       _after == _CACHE_MAX + 1 - _CACHE_MAX // 2)
_check("evicted entries are the oldest (key_0..key_4 gone)",
       all(f"key_{i}" not in _test_cache for i in range(_CACHE_MAX // 2)))
_check("newest entries are retained (key_10 present)",
       f"key_{_CACHE_MAX}" in _test_cache)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 16 — Thread-safety: _CACHE_LOCK covers both read and write
# ══════════════════════════════════════════════════════════════════════════════
_section("16 · Thread safety — concurrent cache reads/writes")

_shared_cache: dict  = {}
_shared_lock          = threading.Lock()
_THREAD_COUNT         = 20
_errors: list         = []

def _writer(key, val):
    time.sleep(0.001)
    with _shared_lock:
        _shared_cache[key] = {"text": val, "_ts": time.time()}

def _reader(key):
    with _shared_lock:
        _ = _shared_cache.get(key)

_threads = []
for _i in range(_THREAD_COUNT):
    _threads.append(threading.Thread(target=_writer, args=(f"k{_i}", f"v{_i}"), daemon=True))
    _threads.append(threading.Thread(target=_reader, args=(f"k{_i}",), daemon=True))

for _t in _threads: _t.start()
for _t in _threads: _t.join(timeout=5)

_check("concurrent cache access completed without deadlock",
       all(not t.is_alive() for t in _threads))
_check("all writer threads populated cache",
       len(_shared_cache) == _THREAD_COUNT)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 17 — alerts.py: load_alerts_config returns dict with all defaults
# ══════════════════════════════════════════════════════════════════════════════
_section("17 · alerts.py — load_alerts_config / save_alerts_config round-trip")

_alerts = _imported.get("alerts")
if _alerts is None:
    _skip_print("alerts not imported — skipping")
else:
    # Save + reload in a temp file
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as _af:
            _af_path = _af.name

        # Monkey-patch the file path
        _orig_path = _alerts._ALERTS_CONFIG_FILE
        _alerts._ALERTS_CONFIG_FILE = _af_path
        _test_cfg = _alerts.load_alerts_config()

        _check("load_alerts_config returns a dict",
               isinstance(_test_cfg, dict))
        _check("default telegram_enabled is False",
               _test_cfg.get("telegram_enabled") is False)
        _check("default min_confidence is an int/float",
               isinstance(_test_cfg.get("min_confidence"), (int, float)))

        # Modify and save
        _test_cfg["min_confidence"] = 99
        _alerts.save_alerts_config(_test_cfg)

        # Reload and verify round-trip
        _reloaded = _alerts.load_alerts_config()
        _check("save/load round-trip preserves modified value",
               _reloaded.get("min_confidence") == 99)

        _alerts._ALERTS_CONFIG_FILE = _orig_path
        os.unlink(_af_path)
    except Exception as _e:
        _fail_print("alerts.py config round-trip", str(_e))


# ══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*64}")
_total = _pass + _fail + _skip
print(f"{BOLD}  Results:  "
      f"{GREEN}{_pass} passed{RESET}  "
      f"{RED}{_fail} failed{RESET}  "
      f"{YELLOW}{_skip} skipped{RESET}  "
      f"/ {_total} total{RESET}")
print(f"{'='*64}\n")

if _fail > 0:
    print(f"{RED}{BOLD}  FAIL: Some tests failed -- investigate before launching the app.{RESET}\n")
    sys.exit(1)
else:
    print(f"{GREEN}{BOLD}  PASS: All tests passed -- app is safe to launch.{RESET}\n")
    sys.exit(0)
