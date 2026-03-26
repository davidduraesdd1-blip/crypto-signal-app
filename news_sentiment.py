"""
news_sentiment.py — Real-time crypto news sentiment scoring

Sources:
  - CryptoPanic free API (no auth token needed for public posts)
  - CoinDesk RSS feed
  - Cointelegraph RSS feed
Analysis: Claude Haiku via Anthropic SDK for fast NLP classification
Cache: 15-minute TTL per pair
"""
from __future__ import annotations

import logging
import os
import threading
import time
import xml.etree.ElementTree as ET
from typing import Optional

from concurrent.futures import ThreadPoolExecutor
import requests

logger = logging.getLogger(__name__)

# PERF: reuse TCP connections across all news/sentiment fetches
_SESSION = requests.Session()
_SESSION.headers.update({"Accept-Encoding": "gzip, deflate", "Connection": "keep-alive"})

# PERF: singleton Anthropic client — avoids repeated SSL handshake + object init
_anthropic_client = None
_anthropic_lock = threading.Lock()


def _get_anthropic_client():
    """Return or create the module-level Anthropic client (thread-safe)."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    with _anthropic_lock:
        if _anthropic_client is None:
            try:
                import anthropic
                _anthropic_client = anthropic.Anthropic(api_key=api_key, timeout=15.0)
            except Exception:
                return None
    return _anthropic_client

# ─── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {}          # {pair: result_dict}
_cache_lock = threading.Lock()
_CACHE_TTL = 900           # 15 minutes

# ─── Coin → currency ticker mapping ────────────────────────────────────────────
_PAIR_TO_CURRENCIES: dict[str, list[str]] = {
    "BTC/USDT":  ["BTC", "bitcoin"],
    "ETH/USDT":  ["ETH", "ethereum"],
    "SOL/USDT":  ["SOL", "solana"],
    "XRP/USDT":  ["XRP", "ripple"],
    "DOGE/USDT": ["DOGE", "dogecoin"],
    "BNB/USDT":  ["BNB", "binance"],
}

_CRYPTOPANIC_BASE  = "https://cryptopanic.com/api/v1/posts/"
_COINDESK_RSS      = "https://feeds.feedburner.com/CoinDesk"
_COINTELEGRAPH_RSS = "https://cointelegraph.com/rss"
_LUNARCRUSH_BASE   = "https://lunarcrush.com/api4/public/coins"

# Ticker → LunarCrush coin slug mapping
_LC_SLUG_MAP: dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "XRP": "xrp",     "DOGE": "dogecoin", "BNB": "bnb",
}

_REQUEST_TIMEOUT = 8  # seconds


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _fetch_cryptopanic(currencies: list[str]) -> list[str]:
    """Fetch recent headlines from CryptoPanic for given currency tickers."""
    # NEWS-04: guard against empty list to prevent IndexError
    if not currencies:
        return []
    ticker = currencies[0]  # use the short ticker (e.g. BTC)
    try:
        resp = _SESSION.get(
            _CRYPTOPANIC_BASE,
            params={"public": "true", "currencies": ticker, "kind": "news"},
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = data.get("results", [])
        headlines = []
        for item in results[:15]:
            title = item.get("title", "")
            # CryptoPanic includes its own sentiment; use as hint
            votes = item.get("votes") or {}
            sentiment_hint = ""
            if votes.get("positive", 0) > votes.get("negative", 0):
                sentiment_hint = " [positive votes]"
            elif votes.get("negative", 0) > votes.get("positive", 0):
                sentiment_hint = " [negative votes]"
            if title:
                headlines.append(f"{title}{sentiment_hint}")
        return headlines
    except Exception as e:
        logger.debug("CryptoPanic fetch failed for %s: %s", ticker, e)
        return []


def _fetch_lunarcrush(ticker: str) -> list[str]:
    """
    Fetch social sentiment headlines/signals from LunarCrush free public API.
    LunarCrush Galaxy Score blends social volume + sentiment + market momentum.
    A Galaxy Score > 60 is bullish social momentum; < 40 is bearish.
    Research: LunarCrush social signals front-run price moves by 4-12 hours.
    """
    slug = _LC_SLUG_MAP.get(ticker.upper())
    if not slug:
        return []
    try:
        url  = f"{_LUNARCRUSH_BASE}/{slug}/v1"
        resp = _SESSION.get(url, timeout=_REQUEST_TIMEOUT,
                            headers={"User-Agent": "CryptoBot/1.0"})
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", {})
        if not data:
            return []

        galaxy_score = data.get("galaxy_score", 50)
        alt_rank     = data.get("alt_rank", 500)
        sentiment    = data.get("sentiment", 3)       # 1-5 scale (3=neutral)
        social_vol   = data.get("social_volume_24h", 0)

        headlines = []
        # Galaxy Score signals
        if galaxy_score >= 65:
            headlines.append(f"{ticker} LunarCrush Galaxy Score {galaxy_score}/100 — strong bullish social momentum [positive votes]")
        elif galaxy_score >= 55:
            headlines.append(f"{ticker} LunarCrush Galaxy Score {galaxy_score}/100 — mild positive social sentiment")
        elif galaxy_score <= 35:
            headlines.append(f"{ticker} LunarCrush Galaxy Score {galaxy_score}/100 — bearish social momentum [negative votes]")
        elif galaxy_score <= 45:
            headlines.append(f"{ticker} LunarCrush Galaxy Score {galaxy_score}/100 — mild negative social sentiment")

        # AltRank signals (lower = better social ranking relative to market cap)
        if isinstance(alt_rank, (int, float)):
            if alt_rank <= 10:
                headlines.append(f"{ticker} AltRank #{alt_rank} — top social/market momentum [positive votes]")
            elif alt_rank >= 200:
                headlines.append(f"{ticker} AltRank #{alt_rank} — low social traction [negative votes]")

        # Raw sentiment score (1-5)
        if isinstance(sentiment, (int, float)):
            if sentiment >= 4.0:
                headlines.append(f"{ticker} crowd sentiment {sentiment:.1f}/5 — bullish community mood [positive votes]")
            elif sentiment <= 2.0:
                headlines.append(f"{ticker} crowd sentiment {sentiment:.1f}/5 — bearish community mood [negative votes]")

        # High social volume = unusual activity
        if isinstance(social_vol, (int, float)) and social_vol > 10000:
            headlines.append(f"{ticker} social volume {social_vol:,} posts/24h — elevated community activity")

        return headlines
    except Exception as e:
        logger.debug("LunarCrush fetch failed for %s: %s", ticker, e)
        return []


def _fetch_rss(url: str, keywords: list[str], max_items: int = 10) -> list[str]:
    """Fetch and filter RSS headlines by keyword relevance."""
    try:
        resp = _SESSION.get(url, timeout=_REQUEST_TIMEOUT,
                            headers={"User-Agent": "CryptoBot/1.0"})
        if resp.status_code != 200:
            return []
        # NEWS-05: reject oversized responses to prevent memory exhaustion
        if len(resp.content) > 512 * 1024:
            logger.debug("RSS response from %s too large (%d bytes), skipping", url, len(resp.content))
            return []
        root = ET.fromstring(resp.text)
        headlines = []
        for item in root.iter("item"):
            title_el = item.find("title")
            if title_el is None or not title_el.text:
                continue
            title = title_el.text.strip()
            lower = title.lower()
            if any(kw.lower() in lower for kw in keywords):
                headlines.append(title)
            if len(headlines) >= max_items:
                break
        return headlines
    except Exception as e:
        logger.debug("RSS fetch failed %s: %s", url, e)
        return []


def _classify_with_claude(headlines: list[str], pair: str) -> dict:
    """
    Send headlines to Claude Haiku for fast sentiment classification.
    Returns {'sentiment': str, 'score': float, 'bullish': int, 'bearish': int, 'neutral': int}
    Falls back to rule-based if API key missing.
    """
    if not headlines:
        return {"sentiment": "NEUTRAL", "score": 0.0, "bullish": 0, "bearish": 0, "neutral": 0,
                "articles_analyzed": 0, "source": "no_headlines"}

    client = _get_anthropic_client()
    if client is None:
        return _rule_based_classify(headlines, pair)

    try:
        headlines_text = "\n".join(f"- {h}" for h in headlines[:20])
        prompt = (
            f"You are a crypto market analyst. Analyze these recent news headlines about {pair.split('/')[0]} "
            f"and classify the overall market sentiment.\n\nHeadlines:\n{headlines_text}\n\n"
            "Respond in exactly this JSON format (no extra text):\n"
            '{"bullish": <count>, "bearish": <count>, "neutral": <count>, '
            '"overall": "<BULLISH|BEARISH|NEUTRAL>", "confidence": <0.0-1.0>, '
            '"key_theme": "<one short phrase summarizing the dominant story>"}'
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        raw = msg.content[0].text.strip()
        # strip markdown code fences if present
        # NEWS-03: case-insensitive check for ```json fence
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.lower().startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        # NEWS-02: use .get() with defaults to avoid KeyError on incomplete Claude response
        bullish = result.get("bullish", 0) or 0
        bearish = result.get("bearish", 0) or 0
        neutral = result.get("neutral", 0) or 0
        total = bullish + bearish + neutral
        if total == 0:
            total = 1
        score = (bullish - bearish) / total
        return {
            "sentiment":         result.get("overall", "NEUTRAL"),
            "score":             round(score, 3),
            "bullish":           bullish,
            "bearish":           bearish,
            "neutral":           neutral,
            "key_theme":         result.get("key_theme", ""),
            "confidence":        result.get("confidence", 0.5),
            "articles_analyzed": len(headlines),
            "source":            "claude_haiku",
        }
    except Exception as e:
        logger.warning("Claude sentiment classification failed: %s", e)
        return _rule_based_classify(headlines, pair)


_BEARISH_WORDS = {
    "crash", "dump", "collapse", "ban", "hack", "exploit", "scam", "fraud",
    "sell", "sell-off", "bearish", "warning", "risk", "concern", "fear",
    "regulation", "crackdown", "lawsuit", "sec", "fine", "penalty", "decline",
    "plunge", "drop", "fall", "sink", "tumble", "slide", "loss", "losses",
}
_BULLISH_WORDS = {
    "rally", "surge", "bull", "bullish", "breakout", "adoption", "etf",
    "approval", "record", "ath", "all-time high", "institutional", "buy",
    "accumulate", "upgrade", "partnership", "launch", "integration", "growth",
    "rising", "gains", "profit", "positive", "strong", "bounce", "recover",
}


def _rule_based_classify(headlines: list[str], pair: str) -> dict:
    """Keyword-based fallback when Claude API is unavailable."""
    bullish = bearish = neutral = 0
    for h in headlines:
        lower = h.lower()
        b_hits = sum(1 for w in _BULLISH_WORDS if w in lower)
        bear_hits = sum(1 for w in _BEARISH_WORDS if w in lower)
        if b_hits > bear_hits:
            bullish += 1
        elif bear_hits > b_hits:
            bearish += 1
        else:
            neutral += 1
    total = bullish + bearish + neutral or 1
    score = (bullish - bearish) / total
    if score > 0.15:
        sentiment = "BULLISH"
    elif score < -0.15:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"
    return {
        "sentiment":         sentiment,
        "score":             round(score, 3),
        "bullish":           bullish,
        "bearish":           bearish,
        "neutral":           neutral,
        "key_theme":         "",
        "confidence":        abs(score),
        "articles_analyzed": len(headlines),
        "source":            "rule_based",
    }


# ─── Public API ─────────────────────────────────────────────────────────────────

_NEUTRAL_RESULT = {
    "sentiment": "NEUTRAL",
    "score": 0.0,
    "bullish": 0,
    "bearish": 0,
    "neutral": 0,
    "key_theme": "",
    "confidence": 0.0,
    "articles_analyzed": 0,
    "source": "unavailable",
    "error": None,
}


def get_news_sentiment(pair: str) -> dict:
    """
    Fetch and score recent news sentiment for a trading pair.

    Returns:
        dict with keys:
          sentiment  : 'BULLISH' | 'BEARISH' | 'NEUTRAL'
          score      : float in [-1, +1] (positive = bullish)
          bullish    : count of bullish headlines
          bearish    : count of bearish headlines
          key_theme  : dominant story phrase (from Claude)
          confidence : float [0, 1]
          source     : 'claude_haiku' | 'rule_based' | 'unavailable'
    """
    now = time.time()
    with _cache_lock:
        cached = _cache.get(pair)
        if cached and now - cached.get("_ts", 0) < _CACHE_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    currencies = _PAIR_TO_CURRENCIES.get(pair, [pair.split("/")[0]])
    keywords   = currencies + [pair.split("/")[0]]

    # PERF-NEWS: fetch all 4 sources simultaneously instead of sequentially.
    # Previous pattern: each source only fetched if len(headlines) < 10, meaning
    # worst-case all 4 fetches ran serially (~32s total at 8s timeout each).
    # New pattern: all 4 start in parallel; total wall-clock time = slowest source.
    def _src_cryptopanic():
        return _fetch_cryptopanic(currencies)

    def _src_coindesk():
        return _fetch_rss(_COINDESK_RSS, keywords, max_items=8)

    def _src_cointelegraph():
        return _fetch_rss(_COINTELEGRAPH_RSS, keywords, max_items=8)

    def _src_lunarcrush():
        return _fetch_lunarcrush(currencies[0]) if currencies else []

    _sources = [_src_cryptopanic, _src_coindesk, _src_cointelegraph, _src_lunarcrush]
    _source_results: list[list[str]] = [[] for _ in _sources]

    with ThreadPoolExecutor(max_workers=4) as _news_ex:
        _news_futures = {_news_ex.submit(fn): i for i, fn in enumerate(_sources)}
        for _fut in _news_futures:
            idx = _news_futures[_fut]
            try:
                _source_results[idx] = _fut.result()
            except Exception as _e:
                logger.debug("News source %d failed: %s", idx, _e)

    # Merge: CryptoPanic first (highest relevance), then supplementary sources.
    # Deduplicate while preserving order.
    _seen: set = set()
    headlines: list[str] = []
    for _batch in _source_results:
        for _h in _batch:
            if _h not in _seen:
                _seen.add(_h)
                headlines.append(_h)

    # Apply the original < 10 threshold: if total merged result is still thin,
    # this is surfaced to the caller via articles_analyzed count (no hard gate needed
    # since all sources already ran in parallel).

    if not headlines:
        result = {**_NEUTRAL_RESULT, "error": "No headlines found"}
        with _cache_lock:
            _cache[pair] = {**result, "_ts": now}
        return result

    result = _classify_with_claude(headlines, pair)
    result["error"] = None
    result["pair"]  = pair

    with _cache_lock:
        _cache[pair] = {**result, "_ts": now}

    return result


def get_news_sentiment_batch(pairs: list[str]) -> dict[str, dict]:
    """Fetch sentiment for multiple pairs concurrently."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pair: pool.submit(get_news_sentiment, pair) for pair in pairs}
        # NEWS-06: catch per-pair exceptions individually so one failure does not abort all
        results = {}
        for pair, f in futures.items():
            try:
                results[pair] = f.result()
            except Exception as e:
                logger.warning("Batch sentiment failed for %s: %s", pair, e)
                results[pair] = {**_NEUTRAL_RESULT, "error": str(e)}
        return results


def get_sentiment_score_bias(pair: str) -> float:
    """
    Returns a confidence score bias in points (-10 to +10) based on news sentiment.
    Positive = bullish bias, negative = bearish bias.
    Used in calculate_signal_confidence() as an additive adjustment.
    """
    try:
        data = get_news_sentiment(pair)
        score = data.get("score", 0.0)
        confidence = data.get("confidence", 0.0)
        # Scale: strong confident sentiment → ±10 pts, weak → near 0
        return round(score * confidence * 10.0, 1)
    except Exception:
        return 0.0
