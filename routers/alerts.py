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


class AlertConfigPatch(BaseModel):
    """Whitelisted top-level config keys the frontend Alerts page can edit.

    AUDIT-2026-05-06 (Everything-Live, item 6): explicit allow-list — only
    these keys can be PUT from the Alerts page. Any other key in the
    request body is rejected silently. Prevents the page from being a
    write-anything surface to alerts_config.json.
    """
    email_enabled:        Optional[bool]            = Field(default=None)
    email_address:        Optional[str]             = Field(default=None, max_length=320)
    confidence_threshold: Optional[float]           = Field(default=None, ge=0.0, le=100.0)
    slack_webhook_url:    Optional[str]             = Field(default=None, max_length=2048)
    telegram_bot_token:   Optional[str]             = Field(default=None, max_length=256)
    telegram_chat_id:     Optional[str]             = Field(default=None, max_length=64)
    browser_push_enabled: Optional[bool]            = Field(default=None)
    alert_types:          Optional[dict[str, bool]] = Field(default=None, description="alert_type_id → enabled")


_ALERT_TYPE_DEFS = [
    {"id": "buy-sell",  "name": "▲ Buy / ▼ Sell crossings",
     "description": "Composite signal crosses BUY (≥ 70) or SELL (≤ 30) threshold for any tracked pair on the configured timeframes."},
    {"id": "regime",    "name": "◈ Regime transitions",
     "description": "HMM regime state changes (CRISIS / TRENDING / RANGING / NORMAL). Per-pair, with confidence threshold."},
    {"id": "onchain",   "name": "⬡ On-chain divergences",
     "description": "MVRV-Z, SOPR, or exchange reserve flow flips direction relative to spot price for ≥ 2 consecutive days."},
    {"id": "funding",   "name": "⚡ Funding rate spikes",
     "description": "Perpetual funding ≥ +0.05% or ≤ −0.05% for 8h. Often signals over-leveraged positioning before a flush."},
    {"id": "unlock",    "name": "🔓 Token unlock proximity",
     "description": "CryptoRank-tracked unlocks within 7 days for any pair in the watchlist. Flags forward sell-pressure events."},
]


@router.get(
    "/config",
    summary="Read alerts page configuration (channels, types, thresholds)",
    dependencies=[Depends(require_api_key)],
)
def get_alert_config():
    """Return the alerts page configuration shape the Next.js Alerts page renders.

    Reads `alerts_config.json` (now on persistent disk per W2-T8) and shapes it
    into the {alert_types[], channels[], threshold, email_enabled} payload.
    Truthful empty defaults on first run when the file doesn't have these keys yet.
    """
    cfg = alerts_module.load_alerts_config() or {}

    types_state = cfg.get("alert_types") or {}
    alert_types = []
    for spec in _ALERT_TYPE_DEFS:
        alert_types.append({
            **spec,
            "enabled": bool(types_state.get(spec["id"], spec["id"] in {"buy-sell", "regime", "onchain"})),
        })

    channels = [
        {"id": "email", "icon": "📧", "name": "Email",
         "status": (
            f"Connected · {cfg.get('email_address')}"
            if cfg.get("email_enabled") and cfg.get("email_address")
            else "Not connected · add an email address to enable"
         ),
         "connected": bool(cfg.get("email_enabled") and cfg.get("email_address"))},
        {"id": "slack", "icon": "💬", "name": "Slack webhook",
         "status": (
            "Connected · webhook configured"
            if cfg.get("slack_webhook_url") else "Not connected · paste a webhook URL to enable"
         ),
         "connected": bool(cfg.get("slack_webhook_url"))},
        {"id": "telegram", "icon": "📨", "name": "Telegram bot",
         "status": (
            "Connected · bot + chat configured"
            if cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id")
            else "Not connected · @YourBotName + chat ID"
         ),
         "connected": bool(cfg.get("telegram_bot_token") and cfg.get("telegram_chat_id"))},
        {"id": "browser-push", "icon": "🔔", "name": "Browser push",
         "status": (
            "Enabled · works only when app tab is open"
            if cfg.get("browser_push_enabled") else "Not connected · works only when app tab is open"
         ),
         "connected": bool(cfg.get("browser_push_enabled"))},
    ]

    return serialize({
        "alert_types":          alert_types,
        "channels":             channels,
        "confidence_threshold": cfg.get("confidence_threshold", 75),
        "email_enabled":        bool(cfg.get("email_enabled", False)),
        "email_address":        cfg.get("email_address", ""),
    })


@router.put(
    "/config",
    summary="Update alerts page configuration (whitelisted keys only)",
    dependencies=[Depends(require_api_key)],
)
def put_alert_config(patch: AlertConfigPatch):
    """Apply a partial config update. Only whitelisted keys (see
    AlertConfigPatch) are honored; any other field in the request body
    is ignored. Returns the new full config shape (same as GET)."""
    payload = patch.model_dump(exclude_none=True)
    if not payload:
        # No-op: just return current state
        return get_alert_config()

    def _apply(cfg: dict[str, Any]) -> dict[str, Any]:
        for k, v in payload.items():
            if k == "alert_types":
                existing = cfg.get("alert_types") or {}
                if isinstance(existing, dict) and isinstance(v, dict):
                    existing.update({str(kk): bool(vv) for kk, vv in v.items()})
                    cfg["alert_types"] = existing
                else:
                    cfg["alert_types"] = {str(kk): bool(vv) for kk, vv in v.items()} if isinstance(v, dict) else {}
            else:
                cfg[k] = v
        return cfg

    alerts_module.update_alerts_config(_apply)
    return get_alert_config()


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
