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
from .utils import serialize

logger = logging.getLogger(__name__)

router = APIRouter()


class AlertRuleIn(BaseModel):
    pair:      str            = Field(..., description="Trading pair, e.g. BTC/USDT")
    condition: str            = Field(..., description="Rule condition, e.g. 'price_above', 'confidence_above'")
    threshold: float          = Field(..., description="Numeric threshold for the condition")
    channels:  list[str]      = Field(default_factory=lambda: ["email"], description="Notification channels")
    note:      Optional[str]  = Field(default=None, description="Free-text reminder for the rule")


def _load_rules() -> list[dict[str, Any]]:
    cfg = alerts_module.load_alerts_config()
    rules = cfg.get("watchlist_alerts") or []
    if not isinstance(rules, list):
        return []
    return rules


def _save_rules(rules: list[dict[str, Any]]):
    cfg = alerts_module.load_alerts_config()
    cfg["watchlist_alerts"] = rules
    alerts_module.save_alerts_config(cfg)


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
    the response so the frontend can DELETE by id later."""
    rules = _load_rules()
    new_rule = rule.model_dump()
    new_rule["id"] = uuid.uuid4().hex
    rules.append(new_rule)
    _save_rules(rules)
    return serialize({"status": "created", "rule": new_rule})


@router.delete(
    "/configure/{rule_id}",
    summary="Delete a watchlist alert rule by id",
    dependencies=[Depends(require_api_key)],
)
def delete_alert_rule(rule_id: str):
    rules = _load_rules()
    new_rules = [r for r in rules if r.get("id") != rule_id]
    if len(new_rules) == len(rules):
        raise HTTPException(status_code=404, detail=f"No rule with id {rule_id!r}")
    _save_rules(new_rules)
    return {"status": "deleted", "id": rule_id, "remaining": len(new_rules)}
