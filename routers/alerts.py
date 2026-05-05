"""
routers/alerts.py — Alerts page CRUD endpoints (configure side).

Persists watchlist alert rules through the existing
`alerts.load_alerts_config` / `alerts.save_alerts_config` round-trip,
so rules added here are honored by the same `check_watchlist_alerts`
path the Streamlit app uses today.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import alerts as alerts_module

from .deps import require_api_key
from .utils import normalize_pair, serialize

logger = logging.getLogger(__name__)

router = APIRouter()


class AlertRuleIn(BaseModel):
    pair:      str            = Field(..., description="Trading pair, e.g. BTC/USDT")
    condition: str            = Field(..., description="Rule condition, e.g. 'price_above', 'confidence_above'")
    threshold: float          = Field(..., description="Numeric threshold for the condition")
    channels:  list[str]      = Field(default_factory=lambda: ["email"], description="Notification channels")
    note:      Optional[str]  = Field(default=None, description="Free-text reminder for the rule")


def _load_rules() -> list[dict[str, Any]]:
    """AUDIT-2026-05-04 (B1): canonical key is `watchlist` — matches the
    default config in alerts.py:115 and the consumer in
    alerts.check_watchlist_alerts (alerts.py:476). Earlier router code
    wrote to `watchlist_alerts` which the consumer never read, so every
    rule created via the Next.js Alerts page was silently dead. Migrate
    on read: if a stale `watchlist_alerts` entry exists from a pre-fix
    deploy, merge it into `watchlist` and drop the duplicate key.
    """
    cfg = alerts_module.load_alerts_config()
    rules = cfg.get("watchlist") or []
    if not isinstance(rules, list):
        rules = []
    legacy = cfg.get("watchlist_alerts") or []
    if isinstance(legacy, list) and legacy:
        # One-time merge — defensive against pre-2026-05-04 deploys.
        seen_ids = {r.get("id") for r in rules if isinstance(r, dict)}
        for r in legacy:
            if isinstance(r, dict) and r.get("id") not in seen_ids:
                rules.append(r)
        def _migrate(c: dict[str, Any]) -> dict[str, Any]:
            c["watchlist"] = rules
            c.pop("watchlist_alerts", None)
            return c
        try:
            alerts_module.update_alerts_config(_migrate)
        except Exception as _e:
            logger.warning("[alerts] migration of watchlist_alerts → watchlist failed (non-fatal): %s", _e)
    return rules


def _save_rules(rules: list[dict[str, Any]]):
    """AUDIT-2026-05-03 (P1): use update_alerts_config so the
    load → modify → save sequence runs under the module RLock.
    Concurrent POST/DELETE callers no longer race the rules list.
    AUDIT-2026-05-04 (B1): write to canonical key `watchlist`.
    """
    def _updater(cfg: dict[str, Any]) -> dict[str, Any]:
        cfg["watchlist"] = rules
        return cfg
    alerts_module.update_alerts_config(_updater)


@router.get(
    "/configure",
    summary="List all configured watchlist alert rules",
    dependencies=[Depends(require_api_key)],
)
def list_alert_rules():
    rules = _load_rules()
    return serialize({"count": len(rules), "rules": rules})


@router.post(
    "/configure",
    summary="Create a new watchlist alert rule",
    dependencies=[Depends(require_api_key)],
)
def create_alert_rule(rule: AlertRuleIn):
    """Persist a new alert rule. Server-assigned `id` is returned in
    the response so the frontend can DELETE by id later.

    AUDIT-2026-05-03: pair is normalized to canonical `BASE/QUOTE` form
    before persisting so downstream `check_watchlist_alerts` lookups
    match regardless of how the frontend formatted the input
    (`BTCUSDT`, `BTC-USDT`, `BTC_USDT`, `BTC/USDT-SWAP` all collapse
    to `BTC/USDT`).

    AUDIT-2026-05-03 (P1): the load-append-save sequence runs inside
    `update_alerts_config`'s RLock so two concurrent POSTs no longer
    lose one caller's rule. Each caller's append happens against the
    most-recent persisted state, not a stale baseline.
    """
    try:
        normalized_pair = normalize_pair(rule.pair)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    new_rule = rule.model_dump()
    new_rule["pair"] = normalized_pair
    new_rule["id"] = uuid.uuid4().hex

    def _append_rule(cfg: dict[str, Any]) -> dict[str, Any]:
        # AUDIT-2026-05-04 (B1): canonical key is `watchlist`.
        rules = cfg.get("watchlist") or []
        if not isinstance(rules, list):
            rules = []
        rules.append(new_rule)
        cfg["watchlist"] = rules
        return cfg

    alerts_module.update_alerts_config(_append_rule)
    return serialize({"status": "created", "rule": new_rule})


@router.delete(
    "/configure/{rule_id}",
    summary="Delete a watchlist alert rule by id",
    dependencies=[Depends(require_api_key)],
)
def delete_alert_rule(rule_id: str):
    """AUDIT-2026-05-03 (P1): delete runs inside update_alerts_config
    so a concurrent POST/DELETE doesn't reintroduce or clobber the
    rule. The 404 is raised inside the updater so the lock is held
    only for the read+check, then released without a write.
    """
    deletion_state: dict[str, Any] = {"found": False, "remaining": 0}

    def _delete_rule(cfg: dict[str, Any]) -> dict[str, Any]:
        # AUDIT-2026-05-04 (B1): canonical key is `watchlist`.
        rules = cfg.get("watchlist") or []
        if not isinstance(rules, list):
            rules = []
        new_rules = [r for r in rules if r.get("id") != rule_id]
        if len(new_rules) == len(rules):
            # No-op write — preserves the existing config exactly.
            return cfg
        cfg["watchlist"] = new_rules
        deletion_state["found"] = True
        deletion_state["remaining"] = len(new_rules)
        return cfg

    alerts_module.update_alerts_config(_delete_rule)
    if not deletion_state["found"]:
        raise HTTPException(status_code=404, detail=f"No rule with id {rule_id!r}")
    return {"status": "deleted", "id": rule_id, "remaining": deletion_state["remaining"]}
