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
from typing import Any, Optional, TypedDict

import database as _db
import alerts as _alerts
import execution as _exec

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


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def get_agent_config() -> dict:
    """Return agent config from alerts_config.json (merged with defaults)."""
    cfg = _alerts.load_alerts_config()
    return {
        "enabled":                  bool(cfg.get("agent_enabled", False)),
        "interval_seconds":         int(cfg.get("agent_interval_seconds", 60)),
        "min_confidence":           float(cfg.get("agent_min_confidence", 80.0)),
        "max_concurrent_positions": int(cfg.get("agent_max_concurrent_positions", 3)),
        "daily_loss_limit_pct":     float(cfg.get("agent_daily_loss_limit_pct", 5.0)),
        "portfolio_size_usd":       float(cfg.get("agent_portfolio_size_usd", 10_000.0)),
        "dry_run":                  bool(cfg.get("agent_dry_run", True)),
    }


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
# HARD RISK GATES (Python-enforced — never delegated to the LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _check_pre_risk(state: AgentState, cfg: dict) -> tuple:
    """Hard pre-trade gates executed BEFORE calling Claude. Returns (passed, reason)."""
    pf   = state["portfolio_state"]
    sig  = state["signal_result"]
    pair = state["pair"]

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
        state["cycle_notes"].append(
            f"Signal: {result.get('direction','?')} conf={result.get('confidence_avg_pct',0):.1f}%"
        )
    except Exception as exc:
        logger.error("[agent] enrich_signals %s: %s", state["pair"], exc)
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

## Current Portfolio (authoritative — do not assume from memory)
- Open Positions: {_sanitize(pf["open_count"])} / {_sanitize(cfg["max_concurrent_positions"])}
- Portfolio Equity: ${_sanitize(pf["equity_usd"])}
- Today's PnL: {_sanitize(pf["daily_pnl_pct"])}%

Call approve_trade if the signal is clear and risk is acceptable.
Call reject_trade if indicators conflict, momentum is weak, or risk is too high.
You MUST call exactly one tool."""

    try:
        # AG-14: add timeout to prevent a hung API call from stalling the agent
        # loop for up to 10 minutes (SDK default) — 45s is sufficient for Claude
        client   = _anthropic.Anthropic(api_key=api_key, timeout=45.0)
        response = client.messages.create(
            model      = "claude-sonnet-4-6",
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
        self._restart_count = 0
        self._last_run_ts   = 0.0
        self._last_pair     = ""
        self._last_decision = ""
        self._cycles_total  = 0
        self._lock          = threading.Lock()

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
            return {
                "running":         self.is_running(),
                "restart_count":   self._restart_count,
                "last_run_ts":     self._last_run_ts,
                "last_pair":       self._last_pair,
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
                        self._last_run_ts  = time.time()
                        self._last_pair    = pair
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
