"""tests/test_truthful_empty_state.py

Phase 4 audit (2026-05-02): truthful_empty_state and data_source_health
helpers replace 135+ bare em-dash sites with copy that tells the user
WHY data is missing.

These tests lock in:
- All 9 reason codes resolve to a non-empty string per user level
- Unknown reason falls through to no_data
- Beginner messages avoid jargon
- Advanced detail string is appended only at advanced level
- data_source_health correctly maps key/error/timestamp combinations
  to the page_header pill states (live | cached | down) and a
  human-readable label suffix
"""
from __future__ import annotations

import time

import pytest

from utils_format import truthful_empty_state, data_source_health


# ── Empty-state helper ──────────────────────────────────────────────

VALID_REASONS = (
    "loading", "pending_scan", "geo_blocked", "rate_limited",
    "no_api_key", "not_listed", "not_tracked", "source_offline",
    "no_data", "error",
)
LEVELS = ("beginner", "intermediate", "advanced")


@pytest.mark.parametrize("reason", VALID_REASONS)
@pytest.mark.parametrize("level", LEVELS)
def test_truthful_empty_state_returns_nonempty(reason: str, level: str) -> None:
    """Every (reason × level) combination must return a non-empty string."""
    out = truthful_empty_state(reason, level)
    assert isinstance(out, str)
    assert len(out.strip()) > 0
    # Never accidentally return the bare em-dash that this helper exists to replace.
    assert out.strip() != "—"


def test_truthful_empty_state_unknown_reason_falls_back() -> None:
    """Unknown reason code → no_data copy."""
    fallback = truthful_empty_state("nonexistent_reason", "beginner")
    canonical = truthful_empty_state("no_data", "beginner")
    assert fallback == canonical


def test_truthful_empty_state_unknown_level_defaults_to_beginner() -> None:
    out = truthful_empty_state("loading", "expert")  # not a real level
    expected = truthful_empty_state("loading", "beginner")
    assert out == expected


def test_truthful_empty_state_detail_only_in_advanced() -> None:
    """detail kwarg should append only to advanced messages."""
    detail = "429 from Glassnode"
    adv = truthful_empty_state("rate_limited", "advanced", detail=detail)
    beg = truthful_empty_state("rate_limited", "beginner", detail=detail)
    inter = truthful_empty_state("rate_limited", "intermediate", detail=detail)
    assert detail in adv
    assert detail not in beg
    assert detail not in inter


def test_truthful_empty_state_beginner_avoids_jargon() -> None:
    """Spot-check: beginner copy doesn't say "rate-limited" / "geo-blocked" raw."""
    rl = truthful_empty_state("rate_limited", "beginner").lower()
    gb = truthful_empty_state("geo_blocked", "beginner").lower()
    # These exact technical phrases belong to advanced; beginner should
    # describe the situation in plain English.
    assert "geo-blocked" not in gb
    # rate_limited beginner copy mentions "rate limit" naturally — that's
    # different from raw "rate-limited (429)" jargon.
    assert "429" not in rl


# ── data_source_health ──────────────────────────────────────────────


def test_data_source_health_no_key() -> None:
    status, label = data_source_health(has_key=False)
    assert status == "down"
    assert "no api key" in label.lower()


def test_data_source_health_rate_limited() -> None:
    status, label = data_source_health(has_key=True, last_error_code="429")
    assert status == "cached"
    assert "rate" in label.lower()


def test_data_source_health_geo_blocked() -> None:
    status, label = data_source_health(has_key=True, last_error_code="451")
    assert status == "down"
    assert "geo" in label.lower()


def test_data_source_health_live_when_recent_success() -> None:
    now = time.time()
    status, label = data_source_health(
        has_key=True, last_success_ts=now, cache_ttl_s=3600
    )
    assert status == "live"
    assert label == "live"


def test_data_source_health_cached_when_stale() -> None:
    now = time.time()
    # 2 hours old, ttl 1 hour → "cached <N>m"
    status, label = data_source_health(
        has_key=True, last_success_ts=now - 7200, cache_ttl_s=3600
    )
    assert status == "cached"
    assert "h" in label or "m" in label  # some age suffix


def test_data_source_health_fetching_on_first_call() -> None:
    """Has key but no last_success_ts yet → 'fetching' label."""
    status, label = data_source_health(has_key=True, last_success_ts=None)
    assert status == "cached"
    assert "fetching" in label.lower()
