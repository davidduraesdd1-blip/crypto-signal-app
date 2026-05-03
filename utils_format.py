"""
utils/format.py — Unified display formatters for cross-app consistency.

All 3 apps (DeFi, SuperGrok, RWA) ship an identical copy of this module
so numeric displays are rendered the same way everywhere — critical for
the family-office unified narrative (see Phase 3 audit synthesis).

Philosophy:
- Always return a string
- Always em-dash "—" for None/NaN/empty (§ToS-convention)
- Prefer k/M/B abbreviations for large numbers (> $10K)
- Preserve tabular alignment (tabular-nums CSS handled upstream)
"""

from __future__ import annotations

import logging
import math


logger = logging.getLogger(__name__)

_EM_DASH = "—"


def _coerce_numeric_string(s: str) -> str:
    """Strip common decoration from numeric strings before float() parsing.

    AUDIT-2026-05-03 (HIGH bug fix F-1): handles values like `"7,200"` or
    `" 7200 "` that came from a CSV / user paste. Without this, the
    surrounding `_is_missing` swallowed the ValueError and `format_usd`
    silently rendered "—" for valid values, masking the upstream type bug.
    """
    return s.replace(",", "").replace("_", "").replace(" ", "").strip()


def _is_missing(v) -> bool:
    """Return True if v should render as em-dash."""
    if v is None:
        return True
    if isinstance(v, str):
        stripped = v.strip()
        if stripped in ("", "N/A", "None", "nan", "NaN", "—"):
            return True
        # Try the cleaned form so well-formed comma/underscore numerics
        # are NOT classified as missing.
        try:
            f = float(_coerce_numeric_string(stripped))
            if math.isnan(f) or math.isinf(f):
                return True
            return False
        except (TypeError, ValueError):
            # Genuinely non-numeric string ("abc") is treated as missing —
            # safer to render em-dash than to leak the raw string into the
            # UI. This is a behavior change from the prior version which
            # returned False here; the new contract is stricter and
            # surfaces obvious upstream-type-bug cases as em-dash earlier.
            return True
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return True
    except (TypeError, ValueError):
        return False
    return False


def format_usd(value, decimals: int = 2, compact: bool = False) -> str:
    """Format a USD number.
    - None / NaN / empty → em-dash
    - compact=True: abbreviate > $10K as $1.2K / $1.2M / $1.2B
    - compact=False: full comma-separated $1,234,567.89

    Examples:
        format_usd(15_950)         → "$15,950.00"
        format_usd(15_950, 0)      → "$15,950"
        format_usd(15_950, compact=True)  → "$15.95K"
        format_usd(2_126_140)      → "$2,126,140.00"
        format_usd(2_126_140, compact=True) → "$2.13M"
        format_usd("7,200")        → "$7,200.00"   (AUDIT-2026-05-03 F-1)
        format_usd(None)           → "—"
    """
    if _is_missing(value):
        return _EM_DASH
    try:
        # AUDIT-2026-05-03 (HIGH F-1): coerce decoration on numeric strings
        # before float() so `format_usd("7,200")` returns "$7,200.00"
        # instead of silently rendering em-dash.
        if isinstance(value, str):
            v = float(_coerce_numeric_string(value))
        else:
            v = float(value)
    except (TypeError, ValueError):
        return _EM_DASH
    # Audit aba91f63: guard against negative `decimals` which would raise
    # ValueError in the f-string. Clamp to 0..6.
    # AUDIT-2026-05-03 (MEDIUM F-3): log when the clamp actually fires so
    # silent decimals truncation no longer masks bugs where `decimals`
    # came from user input.
    _orig_decimals = decimals
    decimals = max(0, min(6, int(decimals)))
    if decimals != _orig_decimals:
        logger.debug(
            "[format_usd] decimals clamped %r → %d (valid range 0..6)",
            _orig_decimals, decimals,
        )
    sign = "-" if v < 0 else ""
    av = abs(v)
    if compact:
        if av >= 1_000_000_000:
            return f"{sign}${av / 1_000_000_000:.{decimals}f}B"
        # Audit aba91f63: avoid confusing "$1000.00K" output for values in
        # the 950K..1M range — transition to M at 950K for cleaner display.
        if av >= 950_000:
            return f"{sign}${av / 1_000_000:.{decimals}f}M"
        if av >= 10_000:
            return f"{sign}${av / 1_000:.{decimals}f}K"
    return f"{sign}${av:,.{decimals}f}"


def format_pct(value, decimals: int = 1, signed: bool = False) -> str:
    """Format a percentage.
    `value` may be a percent (e.g. 12.3 = 12.3%) OR a fraction (0.123 = 12.3%);
    values with abs > 1.5 are treated as already-percent.
    signed=True prepends +/- always (for deltas).

    Examples:
        format_pct(12.3)   → "12.3%"
        format_pct(0.123)  → "12.3%"
        format_pct(-5.2, signed=True) → "-5.2%"
        format_pct(None)   → "—"
    """
    if _is_missing(value):
        return _EM_DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _EM_DASH
    # Heuristic: fractions like 0.12 → percent 12
    if abs(v) <= 1.5:
        v = v * 100.0
    if signed:
        return f"{v:+.{decimals}f}%"
    return f"{v:.{decimals}f}%"


def format_large_number(value, decimals: int = 2) -> str:
    """Format a large integer/float with k/M/B abbreviation.
    Used for TVL, volumes, market caps where no currency symbol needed.

    Examples:
        format_large_number(7_703_261) → "7.70M"
        format_large_number(2_200_000_000) → "2.20B"
        format_large_number(1500)  → "1,500"
        format_large_number(None)  → "—"
    """
    if _is_missing(value):
        return _EM_DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _EM_DASH
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1_000_000_000:
        return f"{sign}{av / 1_000_000_000:.{decimals}f}B"
    if av >= 1_000_000:
        return f"{sign}{av / 1_000_000:.{decimals}f}M"
    if av >= 10_000:
        return f"{sign}{av / 1_000:.{decimals}f}K"
    return f"{sign}{av:,.0f}"


def format_basis_points(value, decimals: int = 0) -> str:
    """Format a basis-points value (1bp = 0.01%).
    Input may be in bps (e.g. 150 = 150bps) OR fraction (0.015 = 150bps).

    Examples:
        format_basis_points(150)     → "150bps"
        format_basis_points(0.015)   → "150bps"
        format_basis_points(1)       → "1bp"  (singular for exactly ±1)
    """
    if _is_missing(value):
        return _EM_DASH
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _EM_DASH
    if abs(v) <= 1.5:
        v = v * 10_000
    # P2 audit fix — was always "bp" regardless of value. Convention is
    # plural "bps" except for exactly ±1.
    suffix = "bp" if abs(round(v, decimals)) == 1 else "bps"
    return f"{v:.{decimals}f}{suffix}"


def format_delta_color(value) -> str:
    """Return canonical semantic color hex for a numeric delta.
    Used by callers that don't have access to the regional color helpers.

    - positive     → #22c55e (green)
    - negative     → #ef4444 (red)
    - zero/missing → #64748b (grey)
    """
    if _is_missing(value):
        return "#64748b"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "#64748b"
    if v > 0:
        return "#22c55e"
    if v < 0:
        return "#ef4444"
    return "#64748b"


# ─────────────────────────────────────────────────────────────────────
# TRUTHFUL EMPTY STATES (Audit 2026-05-02 Phase 4)
# ─────────────────────────────────────────────────────────────────────
# CLAUDE.md §8 mandates plain-English error messages with detail
# scaling per user level. The pre-Phase-4 codebase had 135+ bare "—"
# sites and 19 silent except-pass paths that left users unable to
# tell loading vs geo-blocked vs rate-limited vs no-key vs genuinely
# zero. This helper centralizes those copy strings into 9 reason
# codes × 3 user-level tiers so a one-line call replaces every
# misleading dash.

_EMPTY_STATE_COPY = {
    "loading": {
        "beginner":     "Loading…",
        "intermediate": "Loading…",
        "advanced":     "Fetching…",
    },
    "pending_scan": {
        "beginner":     "No data yet — run a scan to see results",
        "intermediate": "No scan data yet — run a scan",
        "advanced":     "No scan data — run scan to populate",
    },
    "geo_blocked": {
        "beginner":     "Not available from this server location",
        "intermediate": "Geo-blocked — datacenter IP rejected",
        "advanced":     "Geo-blocked",
    },
    "rate_limited": {
        "beginner":     "Hit a rate limit — try again in a few minutes",
        "intermediate": "Rate-limited — back off + retry",
        "advanced":     "Rate-limited (429)",
    },
    "no_api_key": {
        "beginner":     "Not configured — add an API key to enable",
        "intermediate": "API key required",
        "advanced":     "No API key",
    },
    "not_listed": {
        "beginner":     "Not available for this coin",
        "intermediate": "Not listed on this exchange",
        "advanced":     "Not listed",
    },
    "not_tracked": {
        "beginner":     "Not tracked yet — coming soon",
        "intermediate": "Not tracked for this asset",
        "advanced":     "Not tracked",
    },
    "source_offline": {
        "beginner":     "Data source is offline — try again later",
        "intermediate": "Source offline — temporary outage",
        "advanced":     "Source offline",
    },
    "no_data": {
        "beginner":     "No data available right now",
        "intermediate": "No data",
        "advanced":     "No data",
    },
    "error": {
        "beginner":     "Couldn't load this — try refreshing",
        "intermediate": "Load failed — refresh to retry",
        "advanced":     "Error",
    },
}

_VALID_REASONS = set(_EMPTY_STATE_COPY.keys())


def truthful_empty_state(
    reason: str,
    level: str = "beginner",
    detail: str | None = None,
) -> str:
    """
    Return a truthful empty-state message for a given reason code and
    user level. Replaces bare em-dash / "None" / "N/A" with a label
    that tells the user WHY data is missing and what to do about it.

    reason : one of `loading`, `pending_scan`, `geo_blocked`,
             `rate_limited`, `no_api_key`, `not_listed`, `not_tracked`,
             `source_offline`, `no_data`, `error`
    level  : `beginner` | `intermediate` | `advanced`
    detail : optional advanced-mode detail (e.g. "429 from Glassnode")
             — only appended for advanced level.

    Unknown reason → falls through to "no_data".
    """
    if reason not in _VALID_REASONS:
        reason = "no_data"
    lv = (level or "beginner").lower()
    if lv not in ("beginner", "intermediate", "advanced"):
        lv = "beginner"
    base = _EMPTY_STATE_COPY[reason][lv]
    if detail and lv == "advanced":
        return f"{base} — {detail}"
    return base


def data_source_health(
    *,
    has_key: bool = True,
    last_success_ts: float | None = None,
    last_error_code: str | None = None,
    cache_ttl_s: int = 3600,
) -> tuple[str, str]:
    """
    Compute the page_header pill state from data-source observable
    health. Returns (status, label_suffix) where status is one of the
    page_header-recognized strings ("live" | "cached" | "down") and
    label_suffix is a human-readable detail to append to the source
    name in the pill (e.g. "live", "cached 12m", "rate-limited").

    Rules:
      - has_key=False                    → ("down", "no api key")
      - last_error_code in (429, "rate") → ("cached", "rate-limited")
      - last_error_code in (451, 403)    → ("down", "geo-blocked")
      - last_success_ts within ttl       → ("live", "live")
      - last_success_ts older than ttl   → ("cached", f"cached {N}m")
      - last_success_ts is None          → ("cached", "fetching")
      - any other error_code present     → ("down", "error")
    """
    import time as _time

    if not has_key:
        return ("down", "no api key")

    err = (last_error_code or "").lower() if last_error_code else ""
    if err in ("429", "rate", "rate_limited", "rate-limited"):
        return ("cached", "rate-limited")
    if err in ("451", "403", "geo", "geo_blocked", "geo-blocked"):
        return ("down", "geo-blocked")
    if err and err not in ("0", "ok", "none"):
        return ("down", "error")

    if last_success_ts is None:
        return ("cached", "fetching")
    age = max(0.0, _time.time() - last_success_ts)
    if age <= cache_ttl_s:
        return ("live", "live")
    if age <= cache_ttl_s * 24:
        mins = int(age // 60)
        if mins >= 60:
            hrs = mins // 60
            return ("cached", f"cached {hrs}h")
        return ("cached", f"cached {mins}m")
    return ("down", "stale")


__all__ = [
    "format_usd",
    "format_pct",
    "format_large_number",
    "format_basis_points",
    "format_delta_color",
    "truthful_empty_state",
    "data_source_health",
]
