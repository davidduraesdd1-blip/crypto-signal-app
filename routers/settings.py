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

from fastapi import APIRouter, Depends, Response

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


# AUDIT-2026-05-03 (MEDIUM bug — config corruption): per-key type +
# range validators for every PUT-able settings field. Prior code accepted
# `dict[str, Any]` and wrote whatever the caller sent into
# alerts_config.json, so a frontend bug or malicious caller could persist
# `min_confidence_threshold: "abc"` and crash the next scan when the
# engine compares a string to a numeric threshold. Validators reject the
# bad value (silent drop + structured `rejected` array in the response)
# while leaving valid keys in the same patch fully applied. Backward
# compatible: the existing `status: "ok"` + `applied: {...}` shape only
# changes (`status: "partial"` + non-empty `rejected: [...]`) when at
# least one value fails type/range — clean PUTs look exactly like before.
#
# Coercion: only the most common harmless cases — bool from "true"/"false"
# strings (frontend form serialization quirk), float ↔ int when
# loss-free. Anything else fails fast.
_VALIDATORS: dict[str, dict[str, Any]] = {
    # ── Signal-risk (percentages 0-100, except dict overrides) ──────────────
    "min_confidence_threshold":    {"type": int,   "ge": 0,    "le": 100},
    "high_conf_threshold":         {"type": int,   "ge": 0,    "le": 100},
    "min_alert_confidence":        {"type": int,   "ge": 0,    "le": 100},
    "regime_high_conf_overrides":  {"type": dict},
    "max_drawdown_pct":            {"type": float, "ge": 0.0,  "le": 100.0},
    "position_size_pct":           {"type": float, "ge": 0.0,  "le": 100.0},
    # ── Dev-tools (bools + free-form dict for feature flags) ────────────────
    "debug_logging":               {"type": bool},
    "verbose_scan_output":         {"type": bool},
    "feature_flags_override":      {"type": dict},
    "dev_mode":                    {"type": bool},
    # ── Execution (mostly bools + numeric caps; enum on order type) ─────────
    "live_trading_enabled":        {"type": bool},
    "auto_execute":                {"type": bool},
    "exchange":                    {"type": str},
    "max_order_size_usd":          {"type": float, "ge": 0.0},
    "default_order_type":          {"type": str,
                                    "choices": ("market", "limit",
                                                "MARKET", "LIMIT")},
    "slippage_tolerance_pct":      {"type": float, "ge": 0.0,  "le": 100.0},
    # ── Trading (lists of strings + bools + free strings) ────────────────────
    "trading_pairs":               {"type": list, "item_type": str},
    "active_timeframes":           {"type": list, "item_type": str},
    "ta_exchange":                 {"type": str},
    "custom_pair":                 {"type": str},
    "regional_color_convention":   {"type": bool},
    "compact_watchlist_mode":      {"type": bool},
}


def _validate_value(key: str, value: Any) -> tuple[bool, Any, str | None]:
    """Validate `value` against the spec for `key`.

    Returns `(ok, coerced_value, error_message)`. When `ok` is False, the
    caller drops the key from the persisted patch and surfaces
    `error_message` in the `rejected` response array.
    """
    spec = _VALIDATORS.get(key)
    if spec is None:
        return True, value, None  # unknown — handled by caller's allowlist
    expected = spec["type"]

    # ── Coerce (only loss-free common cases) ─────────────────────────────────
    if expected is bool and isinstance(value, str):
        v_lower = value.strip().lower()
        if v_lower in ("true", "1", "yes", "on"):
            value = True
        elif v_lower in ("false", "0", "no", "off"):
            value = False
    if expected is int and isinstance(value, float) and not isinstance(value, bool):
        if value.is_integer():
            value = int(value)
    if expected is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)

    # ── Type check (bool is treated separately because it's a subclass of int) ──
    if expected is bool:
        if not isinstance(value, bool):
            return False, value, f"expected bool, got {type(value).__name__}"
    elif expected is int:
        if isinstance(value, bool) or not isinstance(value, int):
            return False, value, f"expected int, got {type(value).__name__}"
    elif expected is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, value, f"expected number, got {type(value).__name__}"
    elif expected is str:
        if not isinstance(value, str):
            return False, value, f"expected str, got {type(value).__name__}"
    elif expected is dict:
        if not isinstance(value, dict):
            return False, value, f"expected dict, got {type(value).__name__}"
    elif expected is list:
        if not isinstance(value, list):
            return False, value, f"expected list, got {type(value).__name__}"

    # ── Range / enum check ───────────────────────────────────────────────────
    if expected in (int, float):
        if "ge" in spec and value < spec["ge"]:
            return False, value, f"value {value} below min {spec['ge']}"
        if "le" in spec and value > spec["le"]:
            return False, value, f"value {value} above max {spec['le']}"
    if expected is str and "choices" in spec:
        if value not in spec["choices"]:
            return False, value, f"value {value!r} not in {list(spec['choices'])}"
    if expected is list and "item_type" in spec:
        item_t = spec["item_type"]
        for i, item in enumerate(value):
            if not isinstance(item, item_t):
                return False, value, (
                    f"item[{i}] expected {item_t.__name__}, "
                    f"got {type(item).__name__}"
                )

    return True, value, None


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


def _apply_partial(
    allowed: set[str], patch: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], dict[str, Any]]:
    """Validate and persist a partial settings patch.

    AUDIT-2026-05-03 (P1): now uses `alerts_module.update_alerts_config`
    so the load → validate → mutate → save sequence runs under the
    module-level RLock. Without the lock, two concurrent PUTs (e.g. the
    Next.js Settings page issuing parallel saves on rapid form edits)
    could each load the same baseline cfg, mutate different keys, and
    both call save — the second save would overwrite the first's
    changes silently.

    Returns `(updated_cfg, rejected, unknown, applied_post_coerce)` where:
      - `rejected` is a list of `{key, reason, value}` dicts for known
        keys that failed type/range validation. The `value` is echoed
        back so the frontend can show "you tried X, why it failed".
      - `unknown` is a list of key names that aren't in `allowed` —
        silently dropped per the existing contract.
      - `applied_post_coerce` is the subset of `patch` that was actually
        persisted, with any harmless coercion applied (e.g. "true" → True,
        65.0 → 65 for an int field).
    """
    rejected: list[dict[str, Any]] = []
    unknown: list[str] = []
    applied: dict[str, Any] = {}

    def _updater(cfg: dict[str, Any]) -> dict[str, Any]:
        for k, v in patch.items():
            if k not in allowed:
                logger.debug("[settings] dropping unknown key %r (not in %s)", k, sorted(allowed))
                unknown.append(k)
                continue
            ok, coerced, err = _validate_value(k, v)
            if not ok:
                logger.warning("[settings] rejected key %r: %s", k, err)
                rejected.append({"key": k, "reason": err, "value": v})
                continue
            cfg[k] = coerced
            applied[k] = coerced
        return cfg

    updated_cfg = alerts_module.update_alerts_config(_updater)
    return updated_cfg, rejected, unknown, applied


@router.get(
    "/",
    summary="Current settings snapshot (sensitive values redacted)",
    dependencies=[Depends(require_api_key)],
)
def get_settings(response: Response):
    # AUDIT-2026-05-03 (Tier 1 MEDIUM overnight): explicit Cache-Control
    # no-store. Settings include redacted secrets (●●●●●●●●) and live
    # config — no intermediate proxy, CDN, or browser back-button cache
    # should retain the response. Defense in depth alongside the redaction.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    cfg = alerts_module.load_alerts_config()
    redacted = _redact(cfg)
    return serialize({
        "trading":     {k: redacted.get(k) for k in _TRADING_KEYS     if k in redacted},
        "signal_risk": {k: redacted.get(k) for k in _SIGNAL_RISK_KEYS if k in redacted},
        "dev_tools":   {k: redacted.get(k) for k in _DEV_TOOLS_KEYS   if k in redacted},
        "execution":   {k: redacted.get(k) for k in _EXECUTION_KEYS   if k in redacted},
        "all":         redacted,
    })


def _put_response(
    allowed: set[str], updated: dict[str, Any], rejected: list[dict[str, Any]],
    applied: dict[str, Any],
) -> dict[str, Any]:
    """Shared response shape for the four PUT endpoints.

    `status` stays `"ok"` when nothing was rejected so existing callers
    don't notice the new validation layer; flips to `"partial"` only when
    at least one known key failed type/range. Unknown keys are silently
    dropped (existing contract) and never affect status.
    """
    return serialize({
        "status":   "partial" if rejected else "ok",
        "applied":  applied,
        "rejected": rejected,
        "current":  {k: updated.get(k) for k in allowed if k in updated},
    })


@router.put(
    "/trading",
    summary="Update Trading settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_trading(patch: dict[str, Any]):
    updated, rejected, _unknown, applied = _apply_partial(_TRADING_KEYS, patch)
    return _put_response(_TRADING_KEYS, updated, rejected, applied)


@router.put(
    "/signal-risk",
    summary="Update Signal-Risk settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_signal_risk(patch: dict[str, Any]):
    updated, rejected, _unknown, applied = _apply_partial(_SIGNAL_RISK_KEYS, patch)
    return _put_response(_SIGNAL_RISK_KEYS, updated, rejected, applied)


@router.put(
    "/dev-tools",
    summary="Update Dev-Tools settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_dev_tools(patch: dict[str, Any]):
    updated, rejected, _unknown, applied = _apply_partial(_DEV_TOOLS_KEYS, patch)
    return _put_response(_DEV_TOOLS_KEYS, updated, rejected, applied)


@router.put(
    "/execution",
    summary="Update Execution settings (partial)",
    dependencies=[Depends(require_api_key)],
)
def put_execution(patch: dict[str, Any]):
    updated, rejected, _unknown, applied = _apply_partial(_EXECUTION_KEYS, patch)
    return _put_response(_EXECUTION_KEYS, updated, rejected, applied)
