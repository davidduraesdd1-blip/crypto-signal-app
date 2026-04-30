"""
C9 verification (Phase C plan §C9): level-aware variations on
Signals / Regimes / On-chain.

Static checks against app.py — verifies the level branches exist and
each branch produces a recognisably different output. Behaviour is
verified manually on Streamlit Cloud per the per-batch cadence
(toggling Beginner/Intermediate/Advanced should visibly change
content density on all three pages).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"


def _src() -> str:
    return APP_PY.read_text(encoding="utf-8")


# ── Signals page rationale block ───────────────────────────────────────

def test_signals_has_level_aware_rationale_block():
    s = _src()
    sg_idx = s.find("def page_signals():")
    assert sg_idx > 0
    body = s[sg_idx:sg_idx + 30000]

    # All three branches must be present.
    assert 'if _ds_level == "beginner":' in body, (
        "Signals page lost the Beginner branch of the level-aware "
        "rationale block — the beginner sees no plain-English summary."
    )
    assert 'elif _ds_level == "intermediate":' in body, (
        "Signals page lost the Intermediate rationale branch."
    )
    # Advanced is the implicit `else` — check for the diagnostic marker.
    assert "Advanced diagnostics" in body, (
        "Signals page lost the Advanced diagnostics card title."
    )


def test_signals_rationale_branches_render_differently():
    """The three rationale branches must contain DIFFERENT output —
    not just the same string with different formatting."""
    s = _src()
    sg_idx = s.find("def page_signals():")
    body = s[sg_idx:sg_idx + 30000]
    # Beginner-only string (plain-English fallback).
    assert "wait-and-see zone" in body, (
        "Signals beginner rationale missing the plain-English HOLD case."
    )
    # Intermediate-only string.
    assert "layers above neutral" in body, (
        "Signals intermediate rationale missing the layer-alignment line."
    )
    # Advanced-only string.
    assert "RSI(14)" in body, (
        "Signals advanced rationale missing the raw-RSI line."
    )


# ── Regimes state-bar note ─────────────────────────────────────────────

def test_regimes_note_has_three_level_branches():
    s = _src()
    rg_idx = s.find("def page_regimes():")
    assert rg_idx > 0
    body = s[rg_idx:rg_idx + 20000]
    # Three distinct phrasings — one per level.
    assert "looks " in body and "to the model" in body, (
        "Regimes Beginner note lost its plain-English phrasing."
    )
    assert "HMM regime: " in body, (
        "Regimes Intermediate note lost its condensed `HMM regime: X` line."
    )
    assert "HMM 4-state model" in body, (
        "Regimes Advanced note lost its full diagnostic phrasing."
    )


# ── On-chain page subtitle ─────────────────────────────────────────────

def test_onchain_page_has_level_aware_subtitle():
    s = _src()
    oc_idx = s.find("def page_onchain():")
    assert oc_idx > 0
    body = s[oc_idx:oc_idx + 8000]
    # Beginner-only marker.
    assert "long-cycle inflection points" in body, (
        "On-chain Beginner subtitle lost its plain-English description."
    )
    # Intermediate-only marker.
    assert "On-chain valuation + flow metrics" in body, (
        "On-chain Intermediate subtitle lost its condensed line."
    )
    # Advanced-only marker (the legacy default).
    assert "Glassnode + Dune metrics for the major majors" in body, (
        "On-chain Advanced subtitle lost the legacy reference."
    )
