"""
llm_analysis.py — LLM-powered signal explanation via Claude API.
Uses claude-sonnet-4-6 to generate natural language rationale for each trading signal.
Requires ANTHROPIC_API_KEY environment variable (same key used by Claude Code).
"""

import math
import os
import time
import logging
import threading

logger = logging.getLogger(__name__)

_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL  = 3600   # 1 hour — re-explain if direction or confidence bucket changes
_CACHE_MAX  = 500    # evict oldest entries when cache exceeds this size


def get_signal_explanation(pair: str, result: dict) -> str:
    """
    Generate a natural language explanation of a trading signal using Claude claude-sonnet-4-6.

    Args:
        pair:   e.g. 'BTC/USDT'
        result: scan result dict from run_scan()

    Returns:
        3-4 sentence analyst-style explanation string.
        Falls back to error message if API key missing or call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("ANTHROPIC_API_KEY", "").strip()
        except Exception:
            pass
    if not api_key:
        return (
            "AI Analysis unavailable — ANTHROPIC_API_KEY not set. "
            "Add it to your environment variables to enable this feature."
        )

    # Cache key: pair + direction + 5-point confidence bucket
    # LLM-02/03: guard against None and NaN in confidence value
    conf = result.get("confidence_avg_pct") or 0.0
    if not math.isfinite(conf):
        conf = 0.0
    direction = result.get("direction", "")
    cache_key = f"{pair}|{direction}|{int(conf // 5)}"
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and (time.time() - cached["_ts"]) < _CACHE_TTL:
            return cached["text"]

    try:
        import anthropic
    except ImportError:
        return "AI Analysis unavailable — run: pip install anthropic"

    try:
        # LLM-04: add timeout to prevent hung connection blocking the thread
        client = anthropic.Anthropic(api_key=api_key, timeout=30.0)

        # Build timeframe summary
        # LLM-01: use `or {}` so None value (not just missing key) is handled
        tf_data = result.get("timeframes") or {}
        tf_lines = []
        for tf, td in tf_data.items():
            if td.get("direction") in ("NO DATA", "LOW VOL"):
                continue
            tf_lines.append(
                f"  {tf}: {td.get('direction','?')} conf={td.get('confidence',0)}% | "
                f"RSI={td.get('rsi','?')} | ADX={td.get('adx','?')} | "
                f"SuperTrend={td.get('supertrend','?')} | Regime={td.get('regime','?')}"
            )

        # First TF context data
        first_td = list(tf_data.values())[0] if tf_data else {}
        onchain_str = first_td.get("onchain", "N/A")
        iv_str = first_td.get("options_iv", "N/A")
        ob_str = first_td.get("ob_depth", "N/A")
        funding_str = first_td.get("funding", "N/A")

        prompt = f"""You are a professional crypto trading analyst. A trader is looking at this signal on {pair}. Explain in exactly 3-4 concise sentences:
1. What the overall signal is and why (key drivers)
2. What the most important indicator(s) confirm or warn about
3. Key risk or caveat to watch

Signal Summary:
- Pair: {pair}
- Direction: {direction}
- Avg Confidence: {conf:.1f}%
- MTF Alignment: {result.get('mtf_alignment', 'N/A')}%
- Risk Mode: {result.get('risk_mode', 'N/A')}
- Entry: {result.get('entry', 'N/A')} | Stop: {result.get('stop_loss', 'N/A')} | Target: {result.get('exit', 'N/A')}
- Position Size: {result.get('position_size_pct', 'N/A')}%

Timeframe breakdown:
{chr(10).join(tf_lines) if tf_lines else '  No valid timeframe data'}

Market Context:
- On-Chain: {onchain_str}
- Options IV: {iv_str}
- Order Book: {ob_str}
- Funding Rate: {funding_str}

Write 3-4 sentences only. No bullet points, no headers, no markdown. Sound like a Bloomberg analyst."""

        # Prompt caching: cache_control on the system prompt prefix achieves
        # up to 85% latency reduction and 90% cost reduction for repeated analysis
        # (Anthropic docs: cache hit latency drops from 11.5s → 2.4s on long prompts)
        system_content = [
            {
                "type": "text",
                "text": (
                    "You are a professional crypto trading analyst. "
                    "You analyze trading signals and explain them in clear, concise Bloomberg-style prose. "
                    "Always be specific about the indicators and their values. "
                    "Never use bullet points or headers — write in flowing sentences only."
                ),
                "cache_control": {"type": "ephemeral"},  # cache this system block
            }
        ]
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=system_content,
            messages=[{"role": "user", "content": prompt}],
        )

        if not message.content or not hasattr(message.content[0], 'text'):
            return "AI analysis unavailable: empty response from model."
        text = message.content[0].text.strip()
        with _CACHE_LOCK:
            _CACHE[cache_key] = {"text": text, "_ts": time.time()}
            # Evict oldest half when cache is full
            if len(_CACHE) > _CACHE_MAX:
                oldest = sorted(_CACHE, key=lambda k: _CACHE[k]["_ts"])
                for k in oldest[:_CACHE_MAX // 2]:
                    del _CACHE[k]
        return text

    except Exception as e:
        logging.warning(f"LLM explanation failed for {pair}: {e}")
        return f"AI Analysis temporarily unavailable: {str(e)[:500]}"


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURED JSON OUTPUT — indicator_weights adjustment  (#31)
# ─────────────────────────────────────────────────────────────────────────────
# Claude receives market context and returns JSON with indicator_weights deltas.
# Uses Anthropic tool_use to guarantee schema compliance.
# ─────────────────────────────────────────────────────────────────────────────

_WEIGHT_SCHEMA = {
    "name": "set_indicator_weights",
    "description": (
        "Return adjusted indicator weight multipliers for this market context. "
        "Values are multipliers (1.0 = unchanged, 1.2 = 20% boost, 0.8 = 20% reduction). "
        "Only include weights you want to change from baseline."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "core":         {"type": "number", "description": "EMA/trend core weight mult"},
            "momentum":     {"type": "number", "description": "Momentum/MACD weight mult"},
            "funding_rate": {"type": "number", "description": "Funding rate signal weight mult"},
            "onchain":      {"type": "number", "description": "On-chain metrics weight mult"},
            "fng":          {"type": "number", "description": "Fear & Greed index weight mult"},
            "regime":       {"type": "number", "description": "Market regime signal weight mult"},
            "cvd_div":      {"type": "number", "description": "CVD divergence weight mult"},
            "rationale":    {"type": "string", "description": "1-2 sentence reasoning for these adjustments"},
        },
        "required": ["rationale"],
    },
}

_W_CACHE: dict = {}
_W_CACHE_LOCK = threading.Lock()
_W_CACHE_TTL  = 1800   # 30-min cache — weights re-evaluated on significant regime shifts


def get_claude_weight_adjustments(market_ctx: dict) -> dict:
    """
    Ask Claude to return structured indicator_weight multipliers for the current regime.

    Args:
        market_ctx: dict with keys like regime, fear_greed_value, m2_signal,
                    global_m2_signal, mvrv_signal, funding_rate_pct, nupl_signal.

    Returns:
        dict of {indicator_name: multiplier} — e.g. {"onchain": 1.2, "fng": 0.9}
        Returns empty dict on error or no API key.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("ANTHROPIC_API_KEY", "").strip()
        except Exception:
            pass
    if not api_key:
        return {}

    cache_key = (
        f"{market_ctx.get('regime','?')}|"
        f"{market_ctx.get('fear_greed_value', 50) // 10}|"
        f"{market_ctx.get('m2_signal','?')}|"
        f"{market_ctx.get('mvrv_signal','?')}"
    )
    with _W_CACHE_LOCK:
        cached = _W_CACHE.get(cache_key)
        if cached and (time.time() - cached["_ts"]) < _W_CACHE_TTL:
            return cached["weights"]

    try:
        import anthropic
    except ImportError:
        return {}

    try:
        client  = anthropic.Anthropic(api_key=api_key, timeout=20.0)
        prompt  = (
            f"Current crypto market context:\n"
            f"- Macro regime: {market_ctx.get('regime', 'UNKNOWN')}\n"
            f"- Fear & Greed: {market_ctx.get('fear_greed_value', 50)} "
            f"({market_ctx.get('fear_greed_label', 'Neutral')})\n"
            f"- Global M2 signal: {market_ctx.get('m2_signal', 'N/A')}\n"
            f"- MVRV-Z signal: {market_ctx.get('mvrv_signal', 'N/A')}\n"
            f"- NUPL: {market_ctx.get('nupl_signal', 'N/A')}\n"
            f"- BTC funding rate: {market_ctx.get('funding_rate_pct', 0):.3f}%\n"
            f"- Pi Cycle Top: {market_ctx.get('pi_cycle_signal', 'NORMAL')}\n\n"
            "Based on this context, call set_indicator_weights to adjust the model's "
            "indicator weights. Be conservative — only move weights ±20-30%."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",   # Haiku: fast + cheap for structured calls
            max_tokens=256,
            tools=[_WEIGHT_SCHEMA],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": prompt}],
        )
        weights: dict = {}
        for block in response.content:
            if block.type == "tool_use" and block.name == "set_indicator_weights":
                inp = block.input or {}
                for k, v in inp.items():
                    if k != "rationale" and isinstance(v, (int, float)):
                        # Clamp multipliers to 0.5–2.0 to prevent runaway adjustments
                        weights[k] = max(0.5, min(2.0, float(v)))
                logging.info("[LLM Weights] %s | %s", cache_key, inp.get("rationale", ""))
                break

        if weights:
            with _W_CACHE_LOCK:
                _W_CACHE[cache_key] = {"weights": weights, "_ts": time.time()}
        return weights

    except Exception as e:
        logging.debug("[LLM Weights] failed: %s", e)
        return {}
