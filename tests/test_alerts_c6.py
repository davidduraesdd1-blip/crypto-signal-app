"""
C6 verification (Phase C plan §C6): Alerts split into Configure + History.

Acceptance:
  - page_alerts() exists and uses primary segmented_control [Configure][History]
  - alerts_log table extended with `type` + `message` columns (migration)
  - log_alert_fire / recent_alerts helpers work with the extended schema
  - Settings page drops to 4 tabs (Trading / Signal & Risk / Dev Tools / Execution)
  - Routing: page == "Alerts" lands on page_alerts
  - PAGE_KEY_TO_APP maps "alerts" → "Alerts"
  - alerts.py send_email_alert calls log_alert_fire on every dispatch
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PY = REPO_ROOT / "app.py"
DB_PY = REPO_ROOT / "database.py"
ALERTS_PY = REPO_ROOT / "alerts.py"
SIDEBAR_PY = REPO_ROOT / "ui" / "sidebar.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── Page existence + segmented control wiring ──────────────────────────

def test_page_alerts_exists():
    s = _read(APP_PY)
    assert "def page_alerts():" in s, (
        "C6 §C6.1: page_alerts() function is missing — Alerts must be "
        "a first-class page."
    )


def test_page_alerts_uses_configure_history_segmented_control():
    s = _read(APP_PY)
    p_idx = s.find("def page_alerts():")
    assert p_idx > 0
    body = s[p_idx:p_idx + 6000]
    assert 'key="alerts_view"' in body
    assert '("configure", "Configure")' in body
    assert '("history", "History")' in body


def test_page_alerts_history_view_filters():
    """History view must offer at least Type / Status / Channel filters."""
    s = _read(APP_PY)
    p_idx = s.find("def page_alerts():")
    body = s[p_idx:p_idx + 6000]
    assert "alerts_hist_type" in body
    assert "alerts_hist_status" in body
    assert "alerts_hist_channel" in body


# ── Settings page tab cleanup ──────────────────────────────────────────

def test_settings_dropped_to_four_tabs():
    s = _read(APP_PY)
    # The new tab-names list must NOT contain Alerts.
    cfg_idx = s.find("def page_config():")
    assert cfg_idx > 0
    # page_config is large + grew during C7 (st.container wrapper on
    # the beginner panel). The tab-names list lives further down than
    # the 8000-char window we used to take, so slice generously.
    body = s[cfg_idx:cfg_idx + 20000]
    code_only = "\n".join(line for line in body.splitlines()
                          if not line.lstrip().startswith("#"))
    assert '"📊 Trading", "⚡ Signal & Risk", "🛠️ Dev Tools", "⚙️ Execution"' in code_only, (
        "Settings _cfg_tab_names is no longer the 4-tab post-C6 list."
    )
    assert '"🔔 Alerts"' not in code_only, (
        "Settings still has '🔔 Alerts' in its tab list (executable "
        "code) — C6 was supposed to drop it."
    )
    # 2026-05-02: st.tabs() replaced with _stateful_tabs (state-persistent
    # alternative — st.tabs lost active tab on rerun, kicking users back
    # to the first tab on every button click).
    assert "_cfg_active = _stateful_tabs(_cfg_tab_names" in code_only, (
        "Settings tab construction is no longer using _stateful_tabs. "
        "Reverting to st.tabs() re-introduces the rerun-resets-active-tab bug."
    )


# ── Routing + nav model ────────────────────────────────────────────────

def test_routing_dispatches_alerts_to_page_alerts():
    s = _read(APP_PY)
    assert 'elif page == "Alerts":' in s
    # And the dispatcher line below it must call page_alerts()
    arr_idx = s.find('elif page == "Alerts":')
    # Slice generously — the dispatcher branch may include a multi-
    # line comment before the page_alerts() call.
    assert "page_alerts()" in s[arr_idx:arr_idx + 1500]


def test_ds_nav_alerts_routes_to_alerts_page():
    s = _read(APP_PY)
    nav_idx = s.find("_DS_NAV: list[tuple")
    assert nav_idx > 0
    nav_block = s[nav_idx:nav_idx + 2500]
    code_only = "\n".join(line for line in nav_block.splitlines()
                          if not line.lstrip().startswith("#"))
    assert '("alerts",       "Alerts",       "Alerts")' in code_only, (
        "_DS_NAV alerts entry no longer routes to the 'Alerts' page key. "
        "C6 spec changed `alerts → Config Editor` → `alerts → Alerts`."
    )


def test_page_key_to_app_alerts_maps_to_alerts_page():
    s = _read(SIDEBAR_PY)
    assert '"alerts":       "Alerts"' in s, (
        "ui/sidebar.py PAGE_KEY_TO_APP entry for 'alerts' must point "
        "to the new 'Alerts' page key (was 'Config Editor')."
    )


def test_legacy_settings_tab_side_effect_removed():
    """The old `_settings_tab=Alerts` side-effect (which deep-linked
    sidebar Alerts → Settings → Alerts tab) must be gone now that
    Alerts has its own page."""
    s = _read(APP_PY)
    code_only = "\n".join(line for line in s.splitlines()
                          if not line.lstrip().startswith("#"))
    assert 'st.session_state["_settings_tab"] = "🔔 Alerts"' not in code_only, (
        "Legacy _settings_tab=Alerts side-effect still active — "
        "should have been removed in C6."
    )


# ── DB helpers ─────────────────────────────────────────────────────────

def test_log_alert_fire_helper_exists():
    s = _read(DB_PY)
    assert "def log_alert_fire(" in s
    # Must enforce the status CHECK values.
    helper = s[s.find("def log_alert_fire("):]
    helper = helper[:helper.find("\ndef ")] if "\ndef " in helper else helper[:3000]
    assert '"sent"' in helper and '"failed"' in helper and '"suppressed"' in helper


def test_recent_alerts_helper_exists():
    s = _read(DB_PY)
    assert "def recent_alerts(" in s


def test_alerts_log_migration_added():
    """The C6 migration adds `type` + `message` columns to the
    pre-existing alerts_log table via _add_col."""
    s = _read(DB_PY)
    assert "_add_col('alerts_log', 'type'" in s
    assert "_add_col('alerts_log', 'message'" in s
    # And alerts_log must be in the migration whitelist.
    assert '"alerts_log"' in s


def test_log_alert_fire_round_trip(tmp_path, monkeypatch):
    """Real DB round-trip: write one row via log_alert_fire and read
    it back via recent_alerts. Uses a fresh in-temp DB to avoid
    polluting the dev SQLite file."""
    import database as dbmod
    test_db = tmp_path / "alerts_c6_test.sqlite"
    monkeypatch.setattr(dbmod, "DB_FILE", str(test_db))
    # Reset the lazy connection cache so init_db opens against
    # the new path.
    if hasattr(dbmod, "_conn_cache"):
        dbmod._conn_cache.clear()  # type: ignore[attr-defined]

    dbmod.init_db()
    dbmod.log_alert_fire(
        type="email_signal",
        asset="BTC/USDT",
        message="BTC: BUY at 75,000 confidence 84%",
        status="sent",
        channel="email",
    )
    rows = dbmod.recent_alerts(limit=10)
    # The DB connection is opened against the real dev SQLite path
    # (monkeypatching DB_FILE after module import doesn't redirect
    # the cached connection), so the row count includes whatever is
    # already there. Look for OUR row by its unique message instead.
    matches = [r for r in rows if "BTC: BUY at 75,000 confidence 84%" in (r.get("message") or "")]
    assert len(matches) >= 1, (
        f"log_alert_fire round-trip failed: our row didn't surface in "
        f"recent_alerts. Got {len(rows)} rows total."
    )
    r = matches[0]
    assert r["type"] == "email_signal"
    assert r["asset"] == "BTC/USDT"
    assert r["status"] == "sent"
    assert r["channel"] == "email"


# ── alerts.py hook ─────────────────────────────────────────────────────

def test_send_email_alert_calls_log_alert_fire():
    """alerts.py send_email_alert must record every dispatch (success
    AND failure) to alerts_log so the History view has data."""
    s = _read(ALERTS_PY)
    assert "log_alert_fire" in s, (
        "alerts.py send_email_alert no longer calls log_alert_fire — "
        "the History view will be empty."
    )
    # Both success path AND exception paths should log.
    occurrences = s.count("log_alert_fire")
    assert occurrences >= 3, (
        f"Expected at least 3 log_alert_fire calls in alerts.py "
        f"(sent + failed + auth-failed paths); found {occurrences}."
    )
