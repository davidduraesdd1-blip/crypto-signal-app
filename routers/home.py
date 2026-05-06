"""
routers/home.py — Home page aggregation endpoint.

Single endpoint that bundles the data the Next.js Home page needs
(hero cards + info-strip cells) into one payload, eliminating the
N waterfall fetches the front-end would otherwise pay on cold start.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

import database as db

from .deps import require_api_key
from .utils import serialize

logger = logging.getLogger(__name__)

router = APIRouter()


_HERO_DEFAULT_PAIRS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT")
_WATCHLIST_DEFAULT_PAIRS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "LINK/USDT", "NEAR/USDT")


@router.get(
    "/home/summary",
    summary="Aggregated home page payload (hero cards + info strip + scan status)",
    dependencies=[Depends(require_api_key)],
)
def get_home_summary(
    hero_count: int = Query(default=5, ge=1, le=12),
):
    """Returns a bundled payload for the Next.js Home page.

    Single round-trip replaces the N parallel fetches the v0-generated
    home page would otherwise issue. Mirrors the data shape the locked
    mockup (`docs/mockups/sibling-family-crypto-signal.html`) consumes.
    """
    try:
        results = db.read_scan_results() or []
    except Exception as exc:
        logger.warning("[home] scan results unavailable: %s", exc)
        results = []

    try:
        scan_status = db.read_scan_status() or {}
    except Exception as exc:
        logger.warning("[home] scan status unavailable: %s", exc)
        scan_status = {}

    by_pair = {r.get("pair"): r for r in results if r.get("pair")}
    hero_pairs = []
    for p in _HERO_DEFAULT_PAIRS:
        if p in by_pair:
            hero_pairs.append(p)
        if len(hero_pairs) >= hero_count:
            break
    if len(hero_pairs) < hero_count:
        for r in results:
            p = r.get("pair")
            if p and p not in hero_pairs:
                hero_pairs.append(p)
            if len(hero_pairs) >= hero_count:
                break

    hero_cards = []
    for p in hero_pairs:
        r = by_pair.get(p, {})
        hero_cards.append({
            "pair":        p,
            "direction":   r.get("direction"),
            "confidence":  r.get("confidence_avg_pct"),
            "regime":      r.get("regime") or r.get("regime_label"),
            "high_conf":   bool(r.get("high_conf", False)),
            "price":       r.get("price"),
            "change_24h":  r.get("change_24h_pct"),
        })

    total = len(results)
    counts = {"BUY": 0, "SELL": 0, "STRONG BUY": 0, "STRONG SELL": 0, "NEUTRAL": 0}
    high_conf = 0
    for r in results:
        d = (r.get("direction") or "").upper()
        if d in counts:
            counts[d] += 1
        if r.get("high_conf"):
            high_conf += 1

    return serialize({
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "hero_cards":    hero_cards,
        "info_strip": {
            "total_pairs":      total,
            "high_confidence":  high_conf,
            "direction_counts": counts,
            "scan_running":     bool(scan_status.get("running")),
            "scan_last_run":    scan_status.get("timestamp"),
            "scan_progress":    scan_status.get("progress", 0),
        },
    })


@router.get(
    "/watchlist",
    summary="Watchlist payload — top-N pairs with price + 24h change + 1h sparkline",
    dependencies=[Depends(require_api_key)],
)
def get_watchlist(n: int = Query(default=6, ge=1, le=20), sparkline_n: int = Query(default=24, ge=8, le=168)):
    """Return the watchlist payload for the Home page.

    AUDIT-2026-05-06 (Everything-Live, item 8): pre-fix the Home Watchlist
    rendered 6 hardcoded coins with hardcoded prices + hardcoded sparkline
    coordinates. Now derives from /signals scan results + live sparkline
    closes from data_feeds.fetch_sparkline_closes (OKX → Gate.io fallback,
    5-min cache).

    Returns up to `n` pairs. Default 6 to match the v0 watchlist layout.
    Each row: {pair, price, change_24h_pct, direction, sparkline: [closes]}.
    """
    import data_feeds

    try:
        results = db.read_scan_results() or []
    except Exception as exc:
        logger.warning("[home/watchlist] scan results unavailable: %s", exc)
        results = []

    by_pair = {r.get("pair"): r for r in results if r.get("pair")}

    selected: list[str] = []
    for p in _WATCHLIST_DEFAULT_PAIRS:
        if p in by_pair:
            selected.append(p)
        if len(selected) >= n:
            break
    if len(selected) < n:
        for r in results:
            p = r.get("pair")
            if p and p not in selected:
                selected.append(p)
            if len(selected) >= n:
                break

    items = []
    for p in selected:
        r = by_pair.get(p, {})
        # Sparkline closes (1h, last sparkline_n bars)
        closes: list[float] = []
        try:
            closes = data_feeds.fetch_sparkline_closes(p, n=sparkline_n) or []
        except Exception as exc:
            logger.debug("[home/watchlist] sparkline %s failed: %s", p, exc)
        items.append({
            "pair":           p,
            "ticker":         p.split("/")[0],
            "price":          r.get("price") if r else None,
            "change_24h_pct": r.get("change_24h_pct") if r else None,
            "direction":      (r.get("direction") if r else None) or "HOLD",
            "regime":         (r.get("regime") if r else None) or (r.get("regime_label") if r else None),
            "sparkline":      closes,
        })

    return serialize({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count":     len(items),
        "items":     items,
    })
