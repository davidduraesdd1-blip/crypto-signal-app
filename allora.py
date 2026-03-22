"""
allora.py — Allora Network price prediction integration
Crypto Signal Model v5.9.13

Allora Network is a decentralized inference marketplace where AI models compete
to produce accurate price predictions. Consumer access to the aggregated inference
data is free (no token purchase required).

API: Upshot consumer interface for Allora inferences
  https://api.upshot.xyz/v2/allora/consumer/price/ethereum/{topic_id}

Topic IDs (5-minute price predictions):
  1  = BTC/USD
  2  = ETH/USD
  3  = BNB/USD
  7  = SOL/USD
  8  = XRP/USD
  13 = DOGE/USD

Usage:
  bias = get_allora_price_bias("BTC/USDT", current_price=95000)
  # Returns float in [-10, +10] — positive = bullish vs Allora prediction

Cache: 15-minute TTL to avoid hammering the API.
Fallback: returns 0.0 bias if API unavailable.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "Accept": "application/json",
    "User-Agent": "CryptoSignalModel/5.9.13",
})

# Allora consumer API via Upshot (Allora's official consumer interface)
_ALLORA_BASE = "https://api.upshot.xyz/v2/allora/consumer/price/ethereum"

# Fallback: Allora's own inference API
_ALLORA_INFERENCE_BASE = "https://api.allora.network/emissions/v1/inferences"

# Topic ID → (pair_key, name)
_TOPIC_MAP: dict[int, tuple[str, str]] = {
    1:  ("BTC/USDT",  "Bitcoin"),
    2:  ("ETH/USDT",  "Ethereum"),
    3:  ("BNB/USDT",  "BNB"),
    7:  ("SOL/USDT",  "Solana"),
    8:  ("XRP/USDT",  "XRP"),
    13: ("DOGE/USDT", "Dogecoin"),
}

# Reverse: pair_key → topic_id
_PAIR_TO_TOPIC: dict[str, int] = {v[0]: k for k, v in _TOPIC_MAP.items()}

_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL  = 900   # 15 minutes


def _fetch_allora_inference(topic_id: int) -> Optional[float]:
    """
    Fetch the aggregated Allora price prediction for a given topic ID.
    Tries the Upshot consumer API first, then falls back to the inference API.

    Returns:
        Predicted price as float, or None on failure.
    """
    # Primary: Upshot consumer interface
    try:
        url  = f"{_ALLORA_BASE}/{topic_id}"
        resp = _SESSION.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Response format: {"data": {"inference_data": {"network_inference": "95000.50", ...}}}
            if "data" in data:
                inf = data["data"]
                # Try nested inference_data first
                if isinstance(inf, dict) and "inference_data" in inf:
                    val = inf["inference_data"].get("network_inference") or \
                          inf["inference_data"].get("combined_value")
                else:
                    # Flat format: {"data": {"value": "95000.50"}}
                    val = inf.get("value") or inf.get("network_inference") or \
                          inf.get("inference")
                if val is not None:
                    return float(val)
            # Some responses return {"prediction": float}
            if "prediction" in data:
                return float(data["prediction"])
    except Exception as e:
        logger.debug("[Allora] Upshot API error for topic %d: %s", topic_id, e)

    # Fallback: Allora native inference API
    try:
        url  = f"{_ALLORA_INFERENCE_BASE}/{topic_id}"
        resp = _SESSION.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Format: {"inferences": [{"value": "95000.50"}, ...]}
            inferences = data.get("inferences") or data.get("data", [])
            if inferences and isinstance(inferences, list):
                val = inferences[0].get("value") or inferences[0].get("inference")
                if val is not None:
                    return float(val)
    except Exception as e:
        logger.debug("[Allora] Inference API error for topic %d: %s", topic_id, e)

    return None


def get_allora_prediction(pair: str) -> dict:
    """
    Get Allora's aggregated price prediction for a trading pair.

    Args:
        pair: Trading pair string, e.g. "BTC/USDT"

    Returns:
        dict with:
          pair              : str
          topic_id          : int | None
          predicted_price   : float | None
          source            : 'allora' | 'cached' | 'unavailable'
          fetched_at        : float (epoch seconds)
          error             : str | None
    """
    now = time.time()
    cache_key = f"allora:{pair}"

    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached.get("fetched_at", 0) < _CACHE_TTL:
            result = {k: v for k, v in cached.items()}
            result["source"] = "cached"
            return result

    topic_id = _PAIR_TO_TOPIC.get(pair)
    result = {
        "pair":            pair,
        "topic_id":        topic_id,
        "predicted_price": None,
        "source":          "unavailable",
        "fetched_at":      now,
        "error":           None,
    }

    if topic_id is None:
        result["error"] = f"No Allora topic mapped for pair: {pair}"
        return result

    predicted = _fetch_allora_inference(topic_id)
    if predicted is not None:
        result["predicted_price"] = round(predicted, 6)
        result["source"]          = "allora"
    else:
        result["error"] = "Allora API unavailable"

    with _cache_lock:
        _cache[cache_key] = dict(result)

    return result


def get_allora_price_bias(pair: str, current_price: float) -> float:
    """
    Return a confidence score bias based on how Allora's prediction compares to
    the current price.

    Logic:
      - If Allora predicts significantly higher than current → bullish bias (+)
      - If Allora predicts significantly lower → bearish bias (-)
      - Small differences or unavailable data → 0.0

    Args:
        pair          : Trading pair, e.g. "BTC/USDT"
        current_price : Current market price

    Returns:
        float in range [-10.0, +10.0]
        Positive = bullish (Allora sees upside), Negative = bearish.
    """
    if not current_price or current_price <= 0:
        return 0.0

    try:
        data = get_allora_prediction(pair)
        predicted = data.get("predicted_price")
        if predicted is None or predicted <= 0:
            return 0.0

        # Percentage difference: predicted vs current
        pct_diff = (predicted - current_price) / current_price * 100

        # Scale: ±5% diff → ±10 bias, linear interpolation in between
        bias = round(pct_diff * 2.0, 1)
        return max(-10.0, min(10.0, bias))
    except Exception as e:
        logger.debug("[Allora] bias calculation error: %s", e)
        return 0.0


def get_allora_bias_batch(pairs: list[str], prices: dict[str, float]) -> dict[str, float]:
    """
    Get Allora price bias for multiple pairs.

    Args:
        pairs : list of pair strings
        prices: {pair: current_price}

    Returns:
        {pair: bias_float}
    """
    results: dict[str, float] = {}
    for pair in pairs:
        current = prices.get(pair, 0.0)
        results[pair] = get_allora_price_bias(pair, current)
    return results


def get_allora_summary() -> dict:
    """
    Return a status summary of Allora predictions for all supported pairs.
    Useful for displaying in the UI dashboard.

    Returns:
        dict with:
          available      : bool — True if any predictions fetched
          predictions    : list of {pair, predicted_price, topic_id}
          n_live         : count of live (non-cached, non-unavailable) predictions
          last_checked   : epoch timestamp
    """
    summary = {
        "available":   False,
        "predictions": [],
        "n_live":      0,
        "last_checked": time.time(),
    }

    for topic_id, (pair, name) in _TOPIC_MAP.items():
        data = get_allora_prediction(pair)
        entry = {
            "pair":          pair,
            "name":          name,
            "topic_id":      topic_id,
            "predicted_price": data.get("predicted_price"),
            "source":        data.get("source"),
        }
        summary["predictions"].append(entry)
        if data.get("source") in ("allora", "cached") and data.get("predicted_price") is not None:
            summary["available"] = True
            if data.get("source") == "allora":
                summary["n_live"] += 1

    return summary


def invalidate_cache():
    """Clear the Allora prediction cache."""
    with _cache_lock:
        _cache.clear()
