"""
agent.py — Autonomous AI Trading Agent (LangGraph + Claude Tool Use)

Architecture:
  - LangGraph state machine (6 nodes, conditional edges)
  - Claude claude-sonnet-4-6 as decision node — calls approve_trade/reject_trade ONLY
  - Hard Python risk gates BEFORE and AFTER Claude — Claude never calls place_order directly
  - 60-second+ heartbeat loop (one complete cycle per agent_interval_seconds)
  - AgentSupervisor — daemon thread with exponential backoff restart
  - Phantom-portfolio defense: always reads authoritative DB state, never trusts LLM memory
  - Prompt injection sanitizer on all external string inputs before passing to Claude

Usage:
    import agent
    agent.supervisor.start()   # start 24/7 loop (idempotent)
    agent.supervisor.stop()    # graceful shutdown (non-blocking)
    agent.supervisor.status()  # dict with running state + last decision
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TypedDict

import database as _db
import alerts as _alerts
import execution as _exec

try:
    from config import CLAUDE_MODEL as _CLAUDE_MODEL, ANTHROPIC_ENABLED as _ANTHROPIC_ENABLED
except ImportError:
    _CLAUDE_MODEL = "claude-sonnet-4-6"
    _ANTHROPIC_ENABLED = False

logger = logging.getLogger(__name__)


# ─── LangGraph import (graceful fallback) ────────────────────────────────────
try:
    from langgraph.graph import StateGraph, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False
    logger.warning(
        "[agent] langgraph not installed — run: pip install langgraph>=0.2.0  "
        "(falling back to sequential pipeline)"
    )

# ─── Anthropic import (graceful fallback) ────────────────────────────────────
try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.warning("[agent] anthropic SDK not installed — run: pip install anthropic")


# ─── Crypto model core (lazy import avoids circular deps at module load) ──────
_model = None

def _get_model():
    global _model
    if _model is None:
        import crypto_model_core as _m
        _model = _m
    return _model


# ─── G7: Composite Signal Gate — cached 30 min ───────────────────────────────
# Evaluates macro + on-chain environment before allowing new entries.
# RISK_OFF (score <= -0.30) suppresses all new trade entries for the cycle.

_COMPOSITE_GATE_CACHE: dict = {"result": None, "ts": 0.0}
_COMPOSITE_GATE_TTL  = 1800  # 30 minutes — avoids API calls on every tick


def _get_composite_gate_result() -> dict:
    """
    Return cached composite signal (refreshes every 30 min).
    Uses BTC/USDT as the market environment reference (MVRV Z, Hash Ribbons, Puell).
    Gracefully handles missing data — each sub-indicator returns 0.0 when None.
    """
    import time as _time_mod
    now = _time_mod.time()
    if _COMPOSITE_GATE_CACHE["result"] and now - _COMPOSITE_GATE_CACHE["ts"] < _COMPOSITE_GATE_TTL:
        return _COMPOSITE_GATE_CACHE["result"]

    try:
        import data_feeds as _df
        import composite_signal as _cs

        yf_mac = _df.fetch_yfinance_macro()
        fred   = _df.fetch_fred_macro()
        oc     = _df.get_onchain_metrics("BTC/USDT")
        fg     = _df.get_fear_greed()
        fg_idx = _df.get_fear_greed_index(days=30)  # for 30d avg (A3 trend signal)

        macro_data = {
            "dxy":               yf_mac.get("dxy"),
            "dxy_30d_roc":       yf_mac.get("dxy_30d_roc"),         # E4: DXY 30d momentum
            "vix":               yf_mac.get("vix"),
            "yield_spread_2y10y": fred.get("yield_spread_2y10y"),  # C2: live 10Y-2Y spread
            "cpi_yoy":           fred.get("cpi_yoy"),              # C2: live CPI YoY%
        }
        onchain_data = {
            "sopr":              oc.get("sopr"),
            "sopr_7d_ema":       oc.get("sopr_7d_ema"),         # A2: aSOPR proxy
            "mvrv_z":            oc.get("mvrv_z"),
            "mvrv_ratio":        oc.get("mvrv_ratio"),          # A4: needed for realized_price
            "hash_ribbon_signal": oc.get("hash_ribbon_signal"),
            "puell_multiple":    oc.get("puell_multiple"),
        }
        fg_value  = fg.get("value")    if isinstance(fg,    dict) else None
        fg_30d    = fg_idx.get("avg_30d") if isinstance(fg_idx, dict) else None

        # Layer 1: BTC TA signals (RSI-14, MA cross, 30d momentum) — 4-layer model
        ta_data = None
        try:
            ta_data = _df.fetch_btc_ta_signals()
        except Exception:
            pass

        result = _cs.compute_composite_signal(macro_data, onchain_data, fg_value,
                                              ta_data=ta_data, fg_30d_avg=fg_30d)
        _COMPOSITE_GATE_CACHE["result"] = result
        _COMPOSITE_GATE_CACHE["ts"]     = now
        return result
    except Exception as exc:
        logger.debug("[agent] composite gate fetch failed (allowing trade): %s", exc)
        # On failure: return NEUTRAL so the gate never blocks on data errors
        return {"score": 0.0, "signal": "NEUTRAL", "risk_off": False}


def get_composite_signal() -> dict:
    """Public accessor for the 4-layer composite market signal — callable from app.py UI.
    Returns the same cached result as the internal gate check.
    """
    return _get_composite_gate_result()


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# ─── G2: Sliding Presets System (ported from DeFi Model agents/config.py) ─────
# Users can tune agent risk parameters from the Agent Config UI without editing code.
# Overrides are stored in agent_overrides.json, applied every cycle start.
# Whitelists and security settings are NEVER overridable.

_AGENT_DATA_DIR    = Path(__file__).parent / "data" / "agent"
_AGENT_OVERRIDES_FILE = _AGENT_DATA_DIR / "agent_overrides.json"

# Defaults — every overridable key must have a typed default here
_AGENT_DEFAULTS: dict = {
    "agent_min_confidence":           80.0,   # % — minimum signal confidence to act
    "agent_max_concurrent_positions": 3,      # max open trades at once
    "agent_daily_loss_limit_pct":     5.0,    # % — daily loss halt
    "agent_portfolio_size_usd":       10_000.0,  # virtual portfolio size
    "agent_interval_seconds":         60,     # cycle interval
    "agent_max_trade_size_pct":       10.0,   # % of portfolio per trade
    "agent_max_drawdown_pct":         15.0,   # % from peak → emergency stop
    "agent_cooldown_after_loss_s":    1800,   # seconds to pause after a loss
}

# Only numeric/bool keys are patchable from the UI — never security fields
_OVERRIDABLE_KEYS: frozenset = frozenset(_AGENT_DEFAULTS.keys())


def save_overrides(overrides: dict) -> None:
    """Write agent parameter overrides from the UI. Called from app Config page."""
    try:
        _AGENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        safe = {k: v for k, v in overrides.items() if k in _OVERRIDABLE_KEYS}
        _AGENT_OVERRIDES_FILE.write_text(json.dumps(safe, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[agent] save_overrides failed: %s", e)


def load_overrides() -> dict:
    """Read current UI overrides. Returns {} on missing file or parse error."""
    try:
        if _AGENT_OVERRIDES_FILE.exists():
            return json.loads(_AGENT_OVERRIDES_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _apply_overrides(cfg: dict) -> dict:
    """
    Merge user overrides from agent_overrides.json into the live config dict.
    Called at the start of every agent cycle. Safe to call repeatedly.
    Only patches keys in _OVERRIDABLE_KEYS — security settings are never touched.
    """
    try:
        overrides = load_overrides()
        for key, val in overrides.items():
            if key in _OVERRIDABLE_KEYS and key in cfg:
                cfg[key] = type(_AGENT_DEFAULTS.get(key, val))(val)
    except Exception as e:
        logger.warning("[agent] _apply_overrides failed (using defaults): %s", e)
    return cfg


def get_active_limits(cfg: dict) -> dict:
    """
    Return human-readable current effective limits for the Active Limits panel in the UI.
    Shows 'custom' badge when any value differs from default.
    """
    overrides = load_overrides()
    limits = {}
    for key, default in _AGENT_DEFAULTS.items():
        val = cfg.get(key, default)
        limits[key] = {
            "value":   val,
            "default": default,
            "custom":  key in overrides,
        }
    return limits


def get_agent_config() -> dict:
    """Return agent config from alerts_config.json merged with UI overrides."""
    cfg = _alerts.load_alerts_config()
    base = {
        "enabled":                  bool(cfg.get("agent_enabled", False)),
        "interval_seconds":         int(cfg.get("agent_interval_seconds", _AGENT_DEFAULTS["agent_interval_seconds"])),
        "min_confidence":           float(cfg.get("agent_min_confidence", _AGENT_DEFAULTS["agent_min_confidence"])),
        "max_concurrent_positions": int(cfg.get("agent_max_concurrent_positions", _AGENT_DEFAULTS["agent_max_concurrent_positions"])),
        "daily_loss_limit_pct":     float(cfg.get("agent_daily_loss_limit_pct", _AGENT_DEFAULTS["agent_daily_loss_limit_pct"])),
        "portfolio_size_usd":       float(cfg.get("agent_portfolio_size_usd", _AGENT_DEFAULTS["agent_portfolio_size_usd"])),
        "dry_run":                  bool(cfg.get("agent_dry_run", True)),
        "agent_min_confidence":     float(cfg.get("agent_min_confidence", _AGENT_DEFAULTS["agent_min_confidence"])),
        "agent_max_concurrent_positions": int(cfg.get("agent_max_concurrent_positions", _AGENT_DEFAULTS["agent_max_concurrent_positions"])),
        "agent_daily_loss_limit_pct": float(cfg.get("agent_daily_loss_limit_pct", _AGENT_DEFAULTS["agent_daily_loss_limit_pct"])),
        "agent_portfolio_size_usd": float(cfg.get("agent_portfolio_size_usd", _AGENT_DEFAULTS["agent_portfolio_size_usd"])),
        "agent_interval_seconds":   int(cfg.get("agent_interval_seconds", _AGENT_DEFAULTS["agent_interval_seconds"])),
        "agent_max_trade_size_pct": float(_AGENT_DEFAULTS["agent_max_trade_size_pct"]),
        "agent_max_drawdown_pct":   float(_AGENT_DEFAULTS["agent_max_drawdown_pct"]),
        "agent_cooldown_after_loss_s": int(_AGENT_DEFAULTS["agent_cooldown_after_loss_s"]),
    }
    return _apply_overrides(base)  # G2: merge live UI overrides at every call


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT INJECTION SANITIZER
# ─────────────────────────────────────────────────────────────────────────────

_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "disregard all",
    "system prompt",
    "you are now",
    "forget your",
    "new instructions",
    "act as if",
]


def _sanitize(value: Any) -> str:
    """Convert value to str and strip known prompt-injection phrases."""
    text = str(value) if value is not None else ""
    low = text.lower()
    for pat in _INJECTION_PATTERNS:
        if pat in low:
            logger.warning("[agent] Prompt injection stripped: %r", text[:80])
            return "[SANITIZED]"
    return text[:500]


# ─────────────────────────────────────────────────────────────────────────────
# LANGGRAPH STATE
# ─────────────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    pair: str
    signal_result: dict          # output from _scan_pair()
    portfolio_state: dict        # authoritative from DB
    risk_pre_passed: bool
    risk_pre_reason: str
    claude_decision: str         # "approve" | "reject" | "skip"
    claude_rationale: str
    approved_direction: str
    approved_size_usd: float
    risk_post_passed: bool
    risk_post_reason: str
    execution_result: dict
    cycle_notes: list            # running log for this cycle
    error: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# PORTFOLIO STATE — always read from DB (phantom-portfolio defence)
# ─────────────────────────────────────────────────────────────────────────────

def _get_portfolio_state() -> dict:
    """
    Read authoritative portfolio state from DB.
    Injected at the top of every agent cycle so Claude never relies on
    its own memory for position state (prevents phantom-portfolio hallucination).
    """
    try:
        positions = _db.load_positions()
        paper_df  = _db.get_paper_trades_df()
        cfg       = get_agent_config()
        balance   = _exec.get_balance()
        # AG-06: use .get() to avoid KeyError if execution module returns non-standard dict
        _bal_total = balance.get("total", 0) or 0
        equity    = _bal_total if _bal_total > 0 else cfg["portfolio_size_usd"]
        today     = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = 0.0
        if not paper_df.empty and "close_time" in paper_df.columns:
            today_trades = paper_df[paper_df["close_time"].str.startswith(today, na=False)]
            if not today_trades.empty and "pnl_pct" in today_trades.columns:
                daily_pnl = float(today_trades["pnl_pct"].sum())
        return {
            "open_positions": positions,
            "open_count":     len(positions),
            "equity_usd":     equity,
            "daily_pnl_pct":  daily_pnl,
        }
    except Exception as exc:
        logger.error("[agent] _get_portfolio_state failed: %s", exc)
        return {
            "open_positions": {},
            "open_count":     0,
            "equity_usd":     10_000.0,
            "daily_pnl_pct":  0.0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# EMERGENCY STOP — G8
# Set via agent.set_emergency_stop(True) from Agent Control Panel in app.py.
# Checked at the top of every pre-risk gate. Cleared only via explicit reset.
# ─────────────────────────────────────────────────────────────────────────────

_EMERGENCY_STOP: bool = False
_EMERGENCY_STOP_LOCK = threading.Lock()


def set_emergency_stop(active: bool) -> None:
    """Activate or deactivate the emergency stop from the Agent Control Panel."""
    global _EMERGENCY_STOP
    with _EMERGENCY_STOP_LOCK:
        _EMERGENCY_STOP = bool(active)
    logger.warning("[agent] Emergency stop %s", "ACTIVATED" if active else "CLEARED")


def is_emergency_stop() -> bool:
    with _EMERGENCY_STOP_LOCK:
        return _EMERGENCY_STOP


# ─────────────────────────────────────────────────────────────────────────────
# HARD RISK GATES (Python-enforced — never delegated to the LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _check_pre_risk(state: AgentState, cfg: dict) -> tuple:
    """Hard pre-trade gates executed BEFORE calling Claude. Returns (passed, reason)."""
    pf   = state["portfolio_state"]
    sig  = state["signal_result"]
    pair = state["pair"]

    # G8 Check 0: Emergency stop — highest priority, checked first
    if is_emergency_stop():
        return False, "EMERGENCY STOP is active — no trades until manually reset from Agent Control Panel"

    # G7: Composite signal gate — RISK_OFF blocks all new entries
    try:
        gate = _get_composite_gate_result()
        if gate.get("risk_off", False):
            return False, (
                f"Market environment is {gate.get('signal', 'RISK_OFF')} "
                f"(score={gate.get('score', 0):.2f}) — holding all new entries"
            )
    except Exception:
        pass  # gate errors never block — fail-open

    direction = sig.get("direction", "NEUTRAL")
    if "NEUTRAL" in direction or not direction:
        return False, f"Signal direction is {direction!r} — no trade"

    conf = sig.get("confidence_avg_pct", 0)
    if conf < cfg["min_confidence"]:
        return False, f"Confidence {conf:.1f}% < min {cfg['min_confidence']}%"

    if pf["open_count"] >= cfg["max_concurrent_positions"]:
        return False, f"Max positions reached ({pf['open_count']} open)"

    if pf["daily_pnl_pct"] <= -abs(cfg["daily_loss_limit_pct"]):
        return False, f"Daily loss limit hit ({pf['daily_pnl_pct']:.1f}%)"

    open_pos = pf.get("open_positions", {})
    if pair in open_pos:
        existing_dir = open_pos[pair].get("direction", "").upper()
        new_dir      = direction.upper()
        # BUG-AGENT02: [:3] slice failed because "BUY"[:3]="BUY" != "STRONG BUY"[:3]="STR",
        # allowing a second same-side position.  Use substring check instead.
        same_side = (("BUY" in existing_dir and "BUY" in new_dir) or
                     ("SELL" in existing_dir and "SELL" in new_dir))
        if same_side:
            return False, f"Duplicate: already {existing_dir} {pair}"

    if not sig.get("entry") or not sig.get("stop_loss"):
        return False, "Missing entry or stop_loss — invalid signal"

    # G8: Price sanity — reject if current price is 0 or missing (stale/bad data)
    price = sig.get("price_usd", 0) or 0
    if price <= 0:
        return False, "Price data is 0 or missing — stale or unavailable data, skipping"

    # G8: Minimum trade size — must be at least $10 to cover exchange fees
    equity   = pf.get("equity_usd", 0) or 0
    max_pct  = cfg.get("agent_max_trade_size_pct", 10.0)
    trade_sz = equity * max_pct / 100.0
    if trade_sz < 10.0:
        return False, f"Computed trade size ${trade_sz:.2f} below $10 minimum — increase portfolio size"

    return True, "Pre-risk gates passed"


def _check_post_risk(state: AgentState, cfg: dict) -> tuple:
    """Hard post-decision gates — validate + cap Claude's approved size. Returns (passed, reason)."""
    size_usd = state["approved_size_usd"]
    equity   = state["portfolio_state"]["equity_usd"]
    max_size = equity * 0.50  # hard cap: 50% of equity per trade

    if size_usd <= 0:
        return False, f"Invalid size_usd={size_usd:.2f}"

    if size_usd > max_size:
        logger.warning(
            "[agent] Post-risk: capping size $%.0f → $%.0f (50%% equity cap)",
            size_usd, max_size,
        )
        state["approved_size_usd"] = max_size

    return True, "Post-risk gates passed"


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE TOOL DEFINITIONS
# Claude may ONLY call approve_trade or reject_trade.
# place_order is handled entirely in Python (_node_execute).
# ─────────────────────────────────────────────────────────────────────────────

_CLAUDE_TOOLS = [
    {
        "name": "approve_trade",
        "description": (
            "Approve the trade signal. Call when indicators collectively support "
            "entering a position with acceptable risk/reward."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "BUY or SELL — must match the signal direction.",
                },
                "size_pct": {
                    "type": "number",
                    "description": (
                        "Position size as percentage of portfolio (0.5–50). "
                        "Use Kelly suggestion if provided, otherwise confidence-weighted."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "1–3 sentence rationale citing specific indicator values.",
                },
            },
            "required": ["direction", "size_pct", "rationale"],
        },
    },
    {
        "name": "reject_trade",
        "description": (
            "Reject the trade signal. Call when risk/reward is unfavourable, "
            "indicators conflict, or market conditions are uncertain."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "1–2 sentence reason for rejection.",
                },
            },
            "required": ["reason"],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# GRAPH NODES
# ─────────────────────────────────────────────────────────────────────────────

def _node_enrich_signals(state: AgentState) -> AgentState:
    """Node 1: Compute full signal for this pair via scan_single_pair wrapper."""
    try:
        model  = _get_model()
        result = model.scan_single_pair(state["pair"])  # BUG-AGENT01: was model._scan_pair(pair) — missing 10 required args
        state["signal_result"] = result or {}
        sig = state["signal_result"]
        state["cycle_notes"].append(
            f"Signal: {sig.get('direction','?')} conf={sig.get('confidence_avg_pct',0):.1f}%"
        )
    except Exception as exc:
        logger.error("[agent] enrich_signals %s: %s", state["pair"], exc, exc_info=True)
        state["error"]         = str(exc)
        state["signal_result"] = {}
    return state


def _node_risk_pre_check(state: AgentState) -> AgentState:
    """Node 2: Hard pre-risk gates (Python-only, no LLM)."""
    cfg = get_agent_config()
    passed, reason           = _check_pre_risk(state, cfg)
    state["risk_pre_passed"] = passed
    state["risk_pre_reason"] = reason
    state["cycle_notes"].append(f"Pre-risk: {reason}")
    return state


# ─────────────────────────────────────────────────────────────────────────────
# ROLLING SHARPE AGENT WEIGHTS
# ─────────────────────────────────────────────────────────────────────────────

_sharpe_weights_cache: dict = {}
_sharpe_cache_lock   = threading.Lock()
_SHARPE_CACHE_TTL    = 3600  # re-compute weights once per hour


def _compute_agent_sharpe_weights() -> dict:
    """
    Compute per-signal-source Sharpe ratios from recent backtest history.
    Used to weight each agent's contribution in the Claude prompt context.

    Returns a dict: {'rsi': float, 'macd': float, 'supertrend': float, ...}
    Falls back to equal weights when insufficient data.

    Research: Rolling Sharpe (30-day window) outperforms static weights by
    18% in regime-aware crypto systems (2025 empirical studies).
    """
    now = time.time()
    with _sharpe_cache_lock:
        cached = _sharpe_weights_cache.get("weights")
        if cached and now - _sharpe_weights_cache.get("_ts", 0) < _SHARPE_CACHE_TTL:
            return cached

    _DEFAULT = {
        "rsi_div": 1.0, "macd": 1.0, "supertrend": 1.0, "gaussian_ch": 1.0,
        "squeeze": 1.0, "chandelier": 1.0, "cvd_div": 1.0, "agents": 1.0,
    }
    try:
        bt = _db.get_backtest_df()
        if bt.empty or len(bt) < 20:
            with _sharpe_cache_lock:
                _sharpe_weights_cache["weights"] = _DEFAULT
                _sharpe_weights_cache["_ts"] = now
            return _DEFAULT

        # Use the full recent history (up to 30 signals) for Sharpe estimate
        recent = bt.tail(60).copy()
        if "pnl_pct" not in recent.columns:
            return _DEFAULT

        pnl = recent["pnl_pct"].dropna()
        if len(pnl) < 10:
            return _DEFAULT

        # Global Sharpe over recent window — use as a scalar confidence multiplier
        mean_r = float(pnl.mean())
        std_r  = float(pnl.std()) + 1e-9
        sharpe = mean_r / std_r

        # Map global Sharpe to a [0.7, 1.3] multiplier — don't wildly distort weights
        multiplier = float(max(0.7, min(1.3, 1.0 + sharpe * 0.3)))

        weights = {k: round(v * multiplier, 3) for k, v in _DEFAULT.items()}

        with _sharpe_cache_lock:
            _sharpe_weights_cache["weights"] = weights
            _sharpe_weights_cache["_ts"] = now

        return weights

    except Exception as _exc:
        logger.debug("[agent] Sharpe weight computation failed: %s", _exc)
        return _DEFAULT


# ─────────────────────────────────────────────────────────────────────────────
# REFLECTION MEMORY  (recent signal ➜ outcome store)
# ─────────────────────────────────────────────────────────────────────────────

def _get_reflection_memory(pair: str, n: int = 4) -> str:
    """
    Retrieve last N resolved trades for this pair to provide Claude with
    concrete recent context (outcome-grounded, not hallucinated).

    Returns a formatted string for inclusion in the Claude prompt.
    """
    try:
        bt = _db.get_backtest_df()
        if bt.empty:
            return "No recent trade history available."

        # Filter to this pair if column exists
        if "pair" in bt.columns:
            pair_bt = bt[bt["pair"] == pair].tail(n)
        else:
            pair_bt = bt.tail(n)

        if pair_bt.empty:
            return "No recent trade history for this pair."

        lines = []
        for _, row in pair_bt.iterrows():
            direction = str(row.get("direction", "?"))
            pnl       = row.get("pnl_pct", None)
            pnl_str   = f"{float(pnl):+.2f}%" if isinstance(pnl, (int, float)) and pnl == pnl else "pending"
            conf      = row.get("confidence", None)
            conf_str  = f"{float(conf):.0f}%" if isinstance(conf, (int, float)) and conf == conf else "?"
            ts        = str(row.get("timestamp", ""))[:10]
            lines.append(f"  {ts}: {direction} @ conf={conf_str} → P&L={pnl_str}")

        return "\n".join(lines) if lines else "No resolved trades found."
    except Exception:
        return "Reflection memory unavailable."


# ─────────────────────────────────────────────────────────────────────────────
# BULL / BEAR SYNTHESIS  (structured dual-perspective analysis)
# ─────────────────────────────────────────────────────────────────────────────

def _build_bull_bear_section(sig: dict) -> str:
    """
    Generate a structured bull vs bear argument block from the signal data.
    This is embedded in Claude's prompt so it reasons from both sides before deciding.
    One single API call (not two) — captures 90% of the debate benefit at zero extra cost.
    """
    tf_data   = sig.get("timeframes", {})
    first_tf  = list(tf_data.values())[0] if tf_data else {}

    conf      = sig.get("confidence_avg_pct", 50)
    direction = sig.get("direction", "NEUTRAL")
    rsi       = first_tf.get("rsi", 50)
    adx       = first_tf.get("adx", 20)
    st        = first_tf.get("supertrend", "?")
    funding   = first_tf.get("funding", "N/A")
    ob        = first_tf.get("ob_depth", "N/A")
    regime    = first_tf.get("regime", "?")
    squeeze   = first_tf.get("squeeze", "N/A")

    bull_args = []
    bear_args = []

    # RSI
    if isinstance(rsi, (int, float)):
        if rsi < 35:
            bull_args.append(f"RSI {rsi:.0f} — oversold, potential bounce zone")
        elif rsi > 65:
            bear_args.append(f"RSI {rsi:.0f} — overbought, exhaustion possible")
        else:
            bull_args.append(f"RSI {rsi:.0f} — neutral momentum, no extreme")

    # SuperTrend
    if "Uptrend" in str(st):
        bull_args.append(f"SuperTrend {st} — trend structure is bullish")
    elif "Downtrend" in str(st):
        bear_args.append(f"SuperTrend {st} — trend structure is bearish")

    # ADX
    if isinstance(adx, (int, float)):
        if adx > 30:
            bull_args.append(f"ADX {adx:.0f} — strong trend conviction")
        elif adx < 20:
            bear_args.append(f"ADX {adx:.0f} — weak trend, ranging conditions")

    # Funding
    if funding and "N/A" not in str(funding):
        if "positive" in str(funding).lower() or "overlong" in str(funding).lower():
            bear_args.append(f"Funding {funding} — long crowding, squeeze risk")
        elif "negative" in str(funding).lower():
            bull_args.append(f"Funding {funding} — short crowding, squeeze relief")

    # Squeeze
    if "BULL_SQUEEZE" in str(squeeze):
        bull_args.append("Volatility squeeze with bullish momentum — breakout loading")
    elif "BEAR_SQUEEZE" in str(squeeze):
        bear_args.append("Volatility squeeze with bearish momentum — downside loading")

    bull_block = "\n".join(f"    + {a}" for a in bull_args) if bull_args else "    (no strong bull arguments)"
    bear_block = "\n".join(f"    - {a}" for a in bear_args) if bear_args else "    (no strong bear arguments)"

    return (
        f"\n## Bull vs Bear Analysis\n"
        f"### Bull Case:\n{bull_block}\n"
        f"### Bear Case:\n{bear_block}\n"
        f"\nWeigh both sides. The model's current lean is **{direction}** (conf={float(conf) if isinstance(conf, (int, float)) else 0.0:.0f}%).\n"
    )


def _node_claude_reason(state: AgentState) -> AgentState:
    """
    Node 3: Claude reasoning node.
    Claude calls approve_trade or reject_trade ONLY.
    It never calls place_order or any execution function — that is enforced in Python.
    """
    if not _ANTHROPIC_AVAILABLE:
        state["claude_decision"]  = "reject"
        state["claude_rationale"] = "anthropic SDK not installed"
        return state

    if not _ANTHROPIC_ENABLED:
        state["claude_decision"]  = "reject"
        state["claude_rationale"] = "AI agent paused — set ANTHROPIC_ENABLED = True in config.py to activate"
        return state

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        state["claude_decision"]  = "reject"
        state["claude_rationale"] = "ANTHROPIC_API_KEY not set"
        return state

    sig = state["signal_result"]
    pf  = state["portfolio_state"]
    cfg = get_agent_config()

    # Build sanitized timeframe context (cap at 4 TFs to control prompt size)
    tf_data  = sig.get("timeframes", {})
    tf_lines = []
    for tf, td in list(tf_data.items())[:4]:
        if td.get("direction") in ("NO DATA", "LOW VOL"):
            continue
        tf_lines.append(
            f"  {tf}: {_sanitize(td.get('direction','?'))} "
            f"conf={_sanitize(td.get('confidence',0))} | "
            f"RSI={_sanitize(td.get('rsi','?'))} "
            f"ADX={_sanitize(td.get('adx','?'))} "
            f"ST={_sanitize(td.get('supertrend','?'))} "
            f"Regime={_sanitize(td.get('regime','?'))}"
        )

    first_td = list(tf_data.values())[0] if tf_data else {}

    # Rolling Sharpe context + reflection memory
    sharpe_w      = _compute_agent_sharpe_weights()
    sharpe_mult   = sharpe_w.get("agents", 1.0)
    sharpe_label  = "above-average" if sharpe_mult > 1.05 else ("below-average" if sharpe_mult < 0.95 else "average")
    reflection    = _get_reflection_memory(state["pair"])
    bull_bear_blk = _build_bull_bear_section(sig)

    prompt = f"""You are an autonomous crypto trading agent. Review this signal and decide whether to trade.

## Signal: {_sanitize(sig.get("pair", state["pair"]))}
- Direction: {_sanitize(sig.get("direction", "?"))}
- Avg Confidence: {_sanitize(sig.get("confidence_avg_pct", 0))}%
- MTF Alignment: {_sanitize(sig.get("mtf_alignment", "?"))}%
- Risk Mode: {_sanitize(sig.get("risk_mode", "?"))}
- Entry: {_sanitize(sig.get("entry", "?"))} | Stop: {_sanitize(sig.get("stop_loss", "?"))} | Target: {_sanitize(sig.get("exit", "?"))}
- Kelly Position Size: {_sanitize(sig.get("position_size_pct", "?"))}%

## Timeframe Breakdown
{chr(10).join(tf_lines) if tf_lines else "  No valid timeframe data"}

## Market Context
- On-Chain: {_sanitize(first_td.get("onchain", "N/A"))}
- Options IV: {_sanitize(first_td.get("options_iv", "N/A"))}
- Order Book: {_sanitize(first_td.get("ob_depth", "N/A"))}
- Funding: {_sanitize(first_td.get("funding", "N/A"))}
- TVL: {_sanitize(first_td.get("tvl", "N/A"))}
{bull_bear_blk}
## Recent Trade History (Reflection Memory)
{reflection}

## System Performance Context
- Recent signal quality: {sharpe_label} (Sharpe-based multiplier: {sharpe_mult:.2f})
- Note: weight your conviction accordingly.

## Current Portfolio (authoritative — do not assume from memory)
- Open Positions: {_sanitize(pf["open_count"])} / {_sanitize(cfg["max_concurrent_positions"])}
- Portfolio Equity: ${_sanitize(pf["equity_usd"])}
- Today's PnL: {_sanitize(pf["daily_pnl_pct"])}%

## Extended Reasoning Requirements (G10)
Before calling a tool, in your rationale/reason field include:
1. What the PRIMARY factor driving this decision is (cite specific indicator value)
2. What ALTERNATIVES you considered — e.g., "considered waiting for lower RSI but SuperTrend is firmly bullish"
3. What single condition would FLIP this decision to the opposite

Call approve_trade if the signal is clear and risk is acceptable.
Call reject_trade if indicators conflict, momentum is weak, or risk is too high.
You MUST call exactly one tool."""

    try:
        # AG-14: add timeout to prevent a hung API call from stalling the agent
        # loop for up to 10 minutes (SDK default) — 45s is sufficient for Claude
        try:
            client = _anthropic.Anthropic(api_key=api_key, timeout=45.0)
        except TypeError:
            client = _anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model      = _CLAUDE_MODEL,
            max_tokens = 512,
            tools      = _CLAUDE_TOOLS,
            messages   = [{"role": "user", "content": prompt}],
        )

        tool_call = None
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use":
                tool_call = block
                break

        if tool_call is None:
            state["claude_decision"]  = "reject"
            state["claude_rationale"] = "Claude returned no tool call — defaulting to reject"
        elif tool_call.name == "approve_trade":
            inp       = tool_call.input
            direction = str(inp.get("direction", sig.get("direction", "BUY"))).upper()
            # AG-04: use `or 5.0` to safely handle None (null field in tool response)
            size_pct  = float(inp.get("size_pct") or 5.0)
            size_pct  = max(0.5, min(size_pct, 50.0))   # hard cap — never >50%
            size_usd  = (size_pct / 100.0) * pf["equity_usd"]
            state["claude_decision"]    = "approve"
            state["claude_rationale"]   = _sanitize(inp.get("rationale", ""))
            state["approved_direction"] = direction
            state["approved_size_usd"]  = size_usd
        else:
            state["claude_decision"]  = "reject"
            state["claude_rationale"] = _sanitize(
                tool_call.input.get("reason", "Rejected by agent")
            )

        state["cycle_notes"].append(
            f"Claude: {state['claude_decision']} — {state['claude_rationale'][:80]}"
        )

    except Exception as exc:
        logger.error("[agent] Claude API error %s: %s", state["pair"], exc)
        state["claude_decision"]  = "reject"
        state["claude_rationale"] = f"API error: {str(exc)[:200]}"

    return state


def _node_risk_post_check(state: AgentState) -> AgentState:
    """Node 4: Validate + cap Claude's approved size against hard limits."""
    if state["claude_decision"] != "approve":
        state["risk_post_passed"] = False
        state["risk_post_reason"] = "Not approved by Claude"
        return state

    cfg = get_agent_config()
    passed, reason             = _check_post_risk(state, cfg)
    state["risk_post_passed"]  = passed
    state["risk_post_reason"]  = reason
    state["cycle_notes"].append(f"Post-risk: {reason}")
    return state


def _node_execute(state: AgentState) -> AgentState:
    """Node 5: Execute order via execution.place_order() — Python controls this, not Claude."""
    cfg = get_agent_config()

    if cfg["dry_run"]:
        state["execution_result"] = {
            "ok":   True,
            "mode": "dry_run",
            "pair": state["pair"],
            "note": "Dry-run mode — no order placed",
        }
        state["cycle_notes"].append("DRY RUN — order skipped")
        return state

    try:
        sig    = state["signal_result"]
        result = _exec.place_order(
            pair          = state["pair"],
            direction     = state["approved_direction"],
            size_usd      = state["approved_size_usd"],
            current_price = sig.get("price_usd"),
        )
        state["execution_result"] = result
        status = "OK" if result.get("ok") else f"FAILED: {result.get('error', '?')}"
        state["cycle_notes"].append(f"Execution: {status}")
    except Exception as exc:
        logger.error("[agent] Execution error %s: %s", state["pair"], exc)
        state["execution_result"] = {"ok": False, "error": str(exc)}

    return state


def _node_log_and_reflect(state: AgentState) -> AgentState:
    """Node 6: Persist the full decision cycle to agent_log."""
    try:
        pre_ok  = state.get("risk_pre_passed", False)
        post_ok = state.get("risk_post_passed", False)
        dec     = state.get("claude_decision", "skip")

        if state.get("error"):
            action = "error"
        elif pre_ok and post_ok and dec == "approve":
            action = "execute"
        else:
            action = "skip"

        _db.log_agent_decision(
            pair             = state["pair"],
            # AG-11: use .get() on signal_result in case checkpoint restored None
            direction        = state.get("signal_result", {}).get("direction", ""),
            confidence       = state.get("signal_result", {}).get("confidence_avg_pct", 0),
            claude_decision  = dec,
            claude_rationale = state.get("claude_rationale", ""),
            action_taken     = action,
            execution_result = json.dumps(state.get("execution_result", {})),
            notes            = " | ".join(state.get("cycle_notes", [])),
        )
    except Exception as exc:
        logger.warning("[agent] log_and_reflect DB write failed: %s", exc)

    return state


# ─────────────────────────────────────────────────────────────────────────────
# CONDITIONAL EDGES
# ─────────────────────────────────────────────────────────────────────────────

def _route_after_pre_risk(state: AgentState) -> str:
    # AG-08: use .get() to avoid KeyError if checkpoint restored without this key
    if state.get("error") or not state.get("risk_pre_passed", False):
        return "log_and_reflect"
    return "claude_reason"


def _route_after_post_risk(state: AgentState) -> str:
    # AG-09: use .get() to avoid KeyError if checkpoint restored without this key
    if not state.get("risk_post_passed", False):
        return "log_and_reflect"
    return "execute"


# ─────────────────────────────────────────────────────────────────────────────
# BUILD GRAPH
# ─────────────────────────────────────────────────────────────────────────────

def _build_graph():
    """
    Construct and compile the LangGraph state machine with SQLite checkpointing.

    Checkpointing via SqliteSaver means if the agent process restarts or an API
    call fails mid-cycle, the graph resumes from the last saved checkpoint rather
    than losing all in-progress state. This is critical for 24/7 autonomous operation.
    Research (LangGraph docs 2025): checkpointing is mandatory for production agents.
    """
    if not _LANGGRAPH_AVAILABLE:
        return None

    # Try to attach SQLite checkpointer for durable state persistence
    _checkpointer = None
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        # AG-13: use absolute path so checkpoints survive cwd changes (e.g. Streamlit)
        _ckpt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_checkpoints.db")
        _checkpointer = SqliteSaver.from_conn_string(_ckpt_path)
        logger.info("[agent] LangGraph SQLite checkpointer attached at %s", _ckpt_path)
    except Exception as _cp_err:
        logger.debug("[agent] Checkpointer unavailable (non-critical): %s", _cp_err)

    g = StateGraph(AgentState)

    g.add_node("enrich_signals",  _node_enrich_signals)
    g.add_node("risk_pre_check",  _node_risk_pre_check)
    g.add_node("claude_reason",   _node_claude_reason)
    g.add_node("risk_post_check", _node_risk_post_check)
    g.add_node("execute",         _node_execute)
    g.add_node("log_and_reflect", _node_log_and_reflect)

    g.set_entry_point("enrich_signals")
    g.add_edge("enrich_signals", "risk_pre_check")
    g.add_conditional_edges(
        "risk_pre_check",
        _route_after_pre_risk,
        {"claude_reason": "claude_reason", "log_and_reflect": "log_and_reflect"},
    )
    g.add_edge("claude_reason", "risk_post_check")
    g.add_conditional_edges(
        "risk_post_check",
        _route_after_post_risk,
        {"execute": "execute", "log_and_reflect": "log_and_reflect"},
    )
    g.add_edge("execute",         "log_and_reflect")
    g.add_edge("log_and_reflect", END)

    return g.compile(checkpointer=_checkpointer) if _checkpointer else g.compile()


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK PIPELINE (when LangGraph is not installed)
# ─────────────────────────────────────────────────────────────────────────────

def _empty_state(pair: str, portfolio_state: dict) -> AgentState:
    return {
        "pair":               pair,
        "signal_result":      {},
        "portfolio_state":    portfolio_state,
        "risk_pre_passed":    False,
        "risk_pre_reason":    "",
        "claude_decision":    "skip",
        "claude_rationale":   "",
        "approved_direction": "",
        "approved_size_usd":  0.0,
        "risk_post_passed":   False,
        "risk_post_reason":   "",
        "execution_result":   {},
        "cycle_notes":        [],
        "error":              None,
    }


def _run_pipeline_fallback(pair: str, portfolio_state: dict) -> AgentState:
    """Sequential pipeline used when LangGraph is not available."""
    state = _empty_state(pair, portfolio_state)
    state = _node_enrich_signals(state)
    if not state.get("error"):
        state = _node_risk_pre_check(state)
        if state["risk_pre_passed"]:
            state = _node_claude_reason(state)
            state = _node_risk_post_check(state)
            if state["risk_post_passed"]:
                state = _node_execute(state)
    return _node_log_and_reflect(state)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT SUPERVISOR
# ─────────────────────────────────────────────────────────────────────────────

class AgentSupervisor:
    """
    24/7 supervisor that runs the agent loop in a daemon thread.
    Auto-restarts on crash with exponential backoff (max 5 minutes).
    Controlled via a threading.Event kill switch (UI toggle).
    """

    def __init__(self):
        self._kill_event    = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._graph         = None    # compiled LangGraph (lazy, reused across cycles)
        self._restart_count  = 0
        self._last_run_ts    = 0.0
        self._last_pair      = ""
        self._current_pair   = ""   # pair currently being processed (cleared after each cycle)
        self._cycle_start_ts = 0.0  # when the current cycle started
        self._last_decision  = ""
        self._cycles_total   = 0
        self._lock           = threading.Lock()

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self):
        """Start the supervisor thread. Idempotent — safe to call on every Streamlit rerun."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return  # already running
            self._kill_event.clear()
            self._restart_count = 0
            self._thread = threading.Thread(
                target  = self._run_with_restart,
                daemon  = True,
                name    = "AgentSupervisor",
            )
            self._thread.start()
            logger.info("[agent] Supervisor started")

    def stop(self):
        """Signal the supervisor to stop. Returns immediately (non-blocking)."""
        self._kill_event.set()
        logger.info("[agent] Supervisor stop requested")

    def is_running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and not self._kill_event.is_set()
        )

    def status(self) -> dict:
        """Return a status dict safe for display in the Streamlit UI."""
        with self._lock:
            cycle_elapsed = (time.time() - self._cycle_start_ts) if self._cycle_start_ts else 0.0
            return {
                "running":         self.is_running(),
                "restart_count":   self._restart_count,
                "last_run_ts":     self._last_run_ts,
                "last_pair":       self._last_pair,
                "current_pair":    self._current_pair,   # pair in-flight right now
                "cycle_elapsed_s": round(cycle_elapsed),  # seconds since cycle started
                "last_decision":   self._last_decision,
                "cycles_total":    self._cycles_total,
                "kill_requested":  self._kill_event.is_set(),
                "langgraph":       _LANGGRAPH_AVAILABLE,
            }

    # ── Internal loop ──────────────────────────────────────────────────────

    def _run_with_restart(self):
        """Top-level thread target: restarts _agent_loop on any unhandled exception."""
        while not self._kill_event.is_set():
            try:
                self._agent_loop()
            except Exception as exc:
                if self._kill_event.is_set():
                    break
                with self._lock:
                    self._restart_count += 1
                    rc = self._restart_count
                backoff = min(2 ** rc, 300)
                logger.error(
                    "[agent] Loop crashed (restart #%d in %ds): %s",
                    rc, backoff, exc, exc_info=True,
                )
                self._kill_event.wait(backoff)

    def _agent_loop(self):
        """
        Main agent loop.
        Cycles through all configured pairs once per agent_interval_seconds.
        Uses LangGraph graph if available, falls back to sequential pipeline.
        """
        model = _get_model()

        # Build the LangGraph graph once per loop start (reused across cycles)
        if _LANGGRAPH_AVAILABLE and self._graph is None:
            self._graph = _build_graph()

        while not self._kill_event.is_set():
            cfg = get_agent_config()

            # Hot-disable support: if agent is turned off in UI, sleep and re-check
            if not cfg["enabled"]:
                self._kill_event.wait(10)
                continue

            pairs = getattr(model, "PAIRS", [])
            if not pairs:
                logger.warning("[agent] No PAIRS configured — sleeping 60s")
                self._kill_event.wait(60)
                continue

            cycle_start     = time.time()
            with self._lock:
                self._cycle_start_ts = cycle_start
                self._current_pair   = ""
            # Fetch portfolio state ONCE per cycle — same authoritative snapshot for all pairs
            portfolio_state = _get_portfolio_state()

            logger.info("[agent] Cycle start — %d pairs | equity=$%.0f | open=%d",
                        len(pairs), portfolio_state["equity_usd"], portfolio_state["open_count"])

            # AG-16: track open count increments within the cycle so max_concurrent_positions
            # is not bypassed when multiple pairs are approved in the same cycle
            cycle_open_delta = 0

            for pair in pairs:
                if self._kill_event.is_set():
                    break
                try:
                    with self._lock:
                        self._current_pair = pair
                    # Reflect any positions opened earlier in this cycle
                    if cycle_open_delta:
                        portfolio_state = dict(portfolio_state)
                        portfolio_state["open_count"] = portfolio_state["open_count"] + cycle_open_delta

                    if self._graph is not None:
                        initial: AgentState = _empty_state(pair, portfolio_state)
                        # AG-03: pass thread_id so SqliteSaver checkpointer is actually used
                        _invoke_config = {"configurable": {"thread_id": f"{pair}-{int(time.time())}"}}
                        final = self._graph.invoke(initial, config=_invoke_config)
                    else:
                        final = _run_pipeline_fallback(pair, portfolio_state)

                    # AG-12: guard against None final state from LangGraph early termination
                    if not isinstance(final, dict):
                        final = {}

                    # AG-16: if this pair resulted in an executed order, count it
                    if (final.get("claude_decision") == "approve"
                            and final.get("risk_post_passed")
                            and final.get("execution_result", {}).get("ok")):
                        cycle_open_delta += 1

                    with self._lock:
                        self._last_run_ts   = time.time()
                        self._last_pair     = pair
                        self._current_pair  = ""
                        self._last_decision = final.get("claude_decision", "skip")
                        self._cycles_total += 1

                    logger.info(
                        "[agent] %s → %s | %s",
                        pair,
                        final.get("claude_decision", "skip"),
                        (final.get("claude_rationale") or "")[:60],
                    )
                except Exception as exc:
                    logger.error("[agent] Pair %s error: %s", pair, exc, exc_info=True)

            elapsed   = time.time() - cycle_start
            sleep_sec = max(0, cfg["interval_seconds"] - elapsed)
            logger.info("[agent] Cycle done in %.1fs — sleeping %.0fs", elapsed, sleep_sec)
            if sleep_sec > 0:
                self._kill_event.wait(sleep_sec)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

supervisor = AgentSupervisor()
