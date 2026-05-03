"""
routers/settings.py — Settings page endpoints.

Persists three Settings sub-pages (Signal-Risk, Dev-Tools, Execution)
through the existing `alerts.load_alerts_config` /
`alerts.save_alerts_config` round-trip — same source of truth as the
Streamlit Settings page, so changes here propagate to both UIs.

Sensitive credentials (`api_key`, OKX exchange keys, email app
password) are redacted from GET responses. PUTs accept partial dicts
and merge into the persisted config; unknown keys are dropped to keep
the surface tight.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

import alerts as alerts_module

from .deps import require_api_key
from .utils import serialize

logger = logging.getLogger(__name__)

router = APIRouter()


# AUDIT-2026-05-02 (CRITICAL security fix C-2): the prior list drifted vs the
# actual alerts_config schema — the live config dump from
# /settings/ shows `okx_secret` (not `okx_api_secret`),
# `email_pass` (not `smtp_password`), and several unlisted third-party keys
# (lunarcrush_key, coinglass_key, cryptoquant_key, glassnode_key,
# bscscan_key, etherscan_key, cryptorank_key, helius_key). With the
# CRYPTO_SIGNAL_ALLOW_UNAUTH=true bypass on the live deploy, any of these
# would leak via GET /settings/ the moment David fills them in. We now
# redact (a) every name in the explicit allowlist below AND (b) every key
# whose name ends in a sensitive suffix — defense-in-depth so a future
# config field doesn't silently expose its value because someone forgot
# to update this list.
_REDACTED_KEYS = {
    # Internal API key + the original list
    "api_key",
    "okx_api_key", "okx_api_secret", "okx_passphrase",
    "smtp_password", "email_app_password",
    "anthropic_api_key", "cryptopanic_api_key",
    # Live config schema names (drift fix)
    "okx_secret",
    "email_pass",
    # Third-party data providers
    "lunarcrush_key", "coinglass_key", "cryptoquant_key", "glassnode_key",
    "bscscan_key", "etherscan_key", "cryptorank_key", "helius_key",
    "supergrok_coingecko_api_key", "coinmarketcap_api_key",
    "zerion_api_key",
    # Telemetry / errors
    "supergrok_sentry_dsn", "sentry_dsn",
}

# Suffixes that always indicate a sensitive value. Defense-in-depth:
# even if a future config key isn't named in `_REDACTED_KEYS`, it'll
# still be redacted if its name matches one of these.
_REDACTED_SUFFIXES = (
    "_key", "_secret", "_passphrase", "_pass", "_password",
    "_token", "_dsn",
)

_SIGNAL_RISK_KEYS = {
    "min_confidence_threshold",
    "high_conf_threshold",
    "min_alert_confidence",
    "regime_high_conf_overrides",
    "max_drawdown_pct",
    "position_size_pct",
}

_DEV_TOOLS_KEYS = {
    "debug_logging",
    "verbose_scan_output",
    "feature_flags_override",
    "dev_mode",
}

_EXECUTION_KEYS = {
    "live_trading_enabled",
    "auto_execute",
    "exchange",
    "max_order_size_usd",
    "default_order_type",
    "slippage_tolerance_pct",
}

_TRADING_KEYS = {
    "trading_pairs",
    "active_timeframes",
    "ta_exchange",
    "custom_pair",
    "regional_color_convention",
    "compact_watchlist_mode",
}


def _is_sensitive_key(name: str) -> bool:
    """Match against the explicit allowlist OR the sensitive-suffix set."""
    if name in _REDACTED_KEYS:
        return True
    name_lower = name.lower()
    return any(name_lower.endswith(suffix) for suffix in _REDACTED_SUFFIXES)


def _redact(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg)
    for k in list(out.keys()):
        if _is_sensitive_key(k):
            v = out[k]
            out[k] = "•" * 8 if v else ""
    return out


def _apply_partial(allowed: set[str], patch: dict[str, Any]) -> dict[str, Any]:
    cfg = alerts_module.load_alerts_config()
    for k, v in patch.items():
        if k in allowed:
            cfg[k] = v
        else:
            logger.debug("[settings] dropping unknown key %r (not in %s)", k, sorted(allowed))
    alerts_module.save_alerts_config(cfg)
    return cfg


@router.get(
    "/",
    summary="Current settings snapshot (sensitive values redacted)",
    dependencies=[Depends(require_api_key)],
)
def get_settings():
    cfg = alerts_module.load_alerts_config()
    redacted = _redact(cfg)
    return serialize({
        "trading":     {k: redacted.get(k) for k in _TRADING_KEYS     if k in redacted},
        "signal_risk": {k: redacted.get(k) for k in _SIGNAL_RISK_KEYS if k in redacted},
        "dev_tools":   {k: redacted.get(k) for k in _DEV_TOOLS_KEYS   if k in redacted},
        "execution":   {k: redacted.get(k) for k in _EXECUTION_KEYS   if k in redacted},
        "all":         redacted,
    })


@router.put(
    "/trading",
    summary="Update Trading settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_trading(patch: dict[str, Any]):
    updated = _apply_partial(_TRADING_KEYS, patch)
    return serialize({
        "status":  "ok",
        "applied": {k: v for k, v in patch.items() if k in _TRADING_KEYS},
        "current": {k: updated.get(k) for k in _TRADING_KEYS if k in updated},
    })


@router.put(
    "/signal-risk",
    summary="Update Signal-Risk settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_signal_risk(patch: dict[str, Any]):
    updated = _apply_partial(_SIGNAL_RISK_KEYS, patch)
    return serialize({
        "status":  "ok",
        "applied": {k: v for k, v in patch.items() if k in _SIGNAL_RISK_KEYS},
        "current": {k: updated.get(k) for k in _SIGNAL_RISK_KEYS if k in updated},
    })


@router.put(
    "/dev-tools",
    summary="Update Dev-Tools settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_dev_tools(patch: dict[str, Any]):
    updated = _apply_partial(_DEV_TOOLS_KEYS, patch)
    return serialize({
        "status":  "ok",
        "applied": {k: v for k, v in patch.items() if k in _DEV_TOOLS_KEYS},
        "current": {k: updated.get(k) for k in _DEV_TOOLS_KEYS if k in updated},
    })


@router.put(
    "/execution",
    summary="Update Execution settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_execution(patch: dict[str, Any]):
    updated = _apply_partial(_EXECUTION_KEYS, patch)
    return serialize({
        "status":  "ok",
        "applied": {k: v for k, v in patch.items() if k in _EXECUTION_KEYS},
        "current": {k: updated.get(k) for k in _EXECUTION_KEYS if k in updated},
    })
