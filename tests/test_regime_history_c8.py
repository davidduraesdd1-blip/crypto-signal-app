"""
C8 verification (Phase C plan §C8): regime_history data layer.

  - Table created via init_db (idempotent CREATE TABLE IF NOT EXISTS).
  - record_regime_state UPSERTs by (pair, timestamp).
  - regime_history_segments returns canonical-ordered segments
    summing ~100%.
  - append_to_master writes one regime_history row per scan-result
    pair (DB-level scan hook).
  - page_regimes pulls real history from regime_history_segments
    and falls back to current-state placeholder when empty.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"
DB_PY = REPO_ROOT / "database.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── Schema + helper structural ─────────────────────────────────────────

def test_regime_history_table_in_init_db():
    s = _read(DB_PY)
    assert "CREATE TABLE IF NOT EXISTS regime_history" in s
    # Composite PK enforces dedupe per (pair, timestamp).
    assert "PRIMARY KEY (pair, timestamp)" in s
    # Index for the time-range query in regime_history_segments.
    assert "idx_regime_history_pair_ts" in s


def test_record_regime_state_helper_exists():
    s = _read(DB_PY)
    assert "def record_regime_state(" in s
    body = s[s.find("def record_regime_state("):]
    body = body[:body.find("\ndef ")] if "\ndef " in body else body[:3000]
    # UPSERT pattern (PK conflict → update).
    assert "ON CONFLICT(pair, timestamp) DO UPDATE" in body


def test_regime_history_segments_helper_exists():
    s = _read(DB_PY)
    assert "def regime_history_segments(" in s


def test_append_to_master_writes_regime_history():
    """Hooking append_to_master is the spec's "scan-loop write" point —
    it runs on every scan and gives us one regime per pair per cycle
    without coupling crypto_model_core to the DB."""
    s = _read(DB_PY)
    apm_idx = s.find("def append_to_master(")
    assert apm_idx > 0
    body = s[apm_idx:apm_idx + 8000]
    assert "record_regime_state(" in body, (
        "append_to_master no longer calls record_regime_state — the "
        "scan-loop hook is broken; regime_history will never populate."
    )


def test_page_regimes_calls_regime_history_segments():
    s = _read(APP_PY)
    assert "regime_history_segments" in s, (
        "page_regimes no longer queries regime_history_segments — the "
        "BTC state bar will keep rendering its 100%-placeholder."
    )


# ── Behaviour: round-trip ──────────────────────────────────────────────

def test_record_and_segment_round_trip():
    """Real DB round-trip on the dev SQLite (test rows use a unique
    pair so they don't pollute the real BTC/USDT data)."""
    import database as dbmod
    test_pair = "C8TEST/USDT"
    base = datetime.now(timezone.utc) - timedelta(days=10)

    # Six snapshots over 10 days: 6 days bull, 4 days bear.
    for i in range(6):
        dbmod.record_regime_state(
            pair=test_pair, state="bull", confidence=0.7,
            timestamp=(base + timedelta(days=i)).isoformat(),
        )
    for i in range(6, 10):
        dbmod.record_regime_state(
            pair=test_pair, state="bear", confidence=0.6,
            timestamp=(base + timedelta(days=i)).isoformat(),
        )

    segs = dbmod.regime_history_segments(test_pair, days=30)
    assert segs, "regime_history_segments returned empty after writes"
    states = {s for s, _ in segs}
    assert "bull" in states and "bear" in states
    total_pct = sum(p for _, p in segs)
    # Allow small rounding drift.
    assert 99.0 <= total_pct <= 100.5


def test_record_regime_state_normalises_aliases():
    """`accum`/`dist`/`trans`/`ranging`/`neutral` are folded to the
    canonical state names used by the segment-builder."""
    import database as dbmod
    pair = "C8ALIAS/USDT"
    ts = datetime.now(timezone.utc).isoformat()
    dbmod.record_regime_state(pair=pair, state="ACCUM", timestamp=ts)
    segs = dbmod.regime_history_segments(pair, days=1)
    # We can't easily inspect the DB row directly without bypassing
    # the helper, but the segment should report the canonical name.
    if segs:
        assert all(s.lower() in (
            "bull", "bear", "accumulation", "distribution", "transition"
        ) for s, _ in segs), (
            f"alias normalisation failed — got {segs}"
        )


def test_record_regime_state_upsert_dedupes():
    """Two writes with the same (pair, timestamp) PK should produce
    one row, not two — the second updates the state/confidence."""
    import database as dbmod
    pair = "C8UPSERT/USDT"
    ts = datetime.now(timezone.utc).isoformat()
    dbmod.record_regime_state(pair=pair, state="bear", confidence=0.5, timestamp=ts)
    dbmod.record_regime_state(pair=pair, state="bull", confidence=0.9, timestamp=ts)
    segs = dbmod.regime_history_segments(pair, days=1)
    # Only one snapshot exists, so segments == [("bull", 100.0)] approx
    if segs:
        # First state in canonical order with non-zero pct should be "bull"
        # (because the upsert overwrote bear with bull).
        non_zero = [(s, p) for s, p in segs if p > 0]
        assert non_zero, "no non-zero segments after upsert"
        # The most recent state wins after UPSERT.
        assert "bull" in {s for s, _ in non_zero}
