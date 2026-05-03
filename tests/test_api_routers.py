"""
Smoke tests for the Phase D D1 FastAPI routers.

Spec: docs/redesign/2026-05-02_d1-api-audit.md
Plan: docs/redesign/2026-05-02_phase-d-streamlit-retirement.md

Each new endpoint gets one smoke test asserting:
  - HTTP status code matches the documented contract
  - Response shape contains the keys the Next.js frontend will read

Tests run with CRYPTO_SIGNAL_ALLOW_UNAUTH=true so api.py.require_api_key
and routers.deps.require_api_key both bypass the X-API-Key header check.
This is exactly the local-development override the production deploy
will NOT honor (Render env-var matrix sets CRYPTO_SIGNAL_ALLOW_UNAUTH=
false explicitly per D2 plan).

Network-dependent helpers (fetch_onchain_metrics, generate_signal_story)
are monkeypatched to deterministic fakes so tests stay hermetic and
fast. Disk-mutating helpers (save_alerts_config) are stubbed so the
real alerts_config.json is never modified by the test suite.
"""

from __future__ import annotations

import os

# Must be set BEFORE api is imported — startup checks read this.
os.environ.setdefault("CRYPTO_SIGNAL_ALLOW_UNAUTH", "true")
os.environ.setdefault("ANTHROPIC_ENABLED", "false")
os.environ.setdefault("DEMO_MODE", "true")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Module-scoped TestClient — api.py module init runs once."""
    from api import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def stub_alerts_config(monkeypatch):
    """In-memory alerts_config so POST/PUT/DELETE never touch disk."""
    state: dict = {
        "api_key": "",
        "live_trading_enabled": False,
        "watchlist_alerts": [
            {"id": "preexisting", "pair": "BTC/USDT", "condition": "price_above",
             "threshold": 100000.0, "channels": ["email"], "note": "preexisting"},
        ],
        "min_confidence_threshold": 60,
        "high_conf_threshold": 75,
        "debug_logging": False,
        "max_order_size_usd": 100.0,
    }
    import alerts as alerts_module
    monkeypatch.setattr(alerts_module, "load_alerts_config", lambda: dict(state))
    monkeypatch.setattr(alerts_module, "save_alerts_config", lambda cfg: state.update(cfg))
    return state


# ── Home ─────────────────────────────────────────────────────────────────────

def test_home_summary_smoke(client):
    r = client.get("/home/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "hero_cards" in body
    assert "info_strip" in body
    assert "timestamp" in body
    assert isinstance(body["hero_cards"], list)
    assert "direction_counts" in body["info_strip"]


def test_home_summary_respects_hero_count(client):
    r = client.get("/home/summary?hero_count=3")
    assert r.status_code == 200
    assert len(r.json()["hero_cards"]) <= 3


# ── Regimes ──────────────────────────────────────────────────────────────────

def test_regimes_list_smoke(client):
    r = client.get("/regimes/")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body and "summary" in body and "results" in body
    assert {"Trending", "Ranging", "Neutral", "Unknown"} <= set(body["summary"].keys())


def test_regimes_history_smoke(client):
    r = client.get("/regimes/BTC-USDT/history?days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["pair"] == "BTC/USDT"
    assert body["days"] == 30
    assert isinstance(body["segments"], list)


def test_regimes_history_invalid_pair_returns_422(client):
    r = client.get("/regimes/!!!/history")
    assert r.status_code == 422


def test_regimes_transitions_smoke(client):
    r = client.get("/regimes/transitions?days=30&limit=50")
    assert r.status_code == 200
    body = r.json()
    assert "transitions" in body and isinstance(body["transitions"], list)


# ── On-Chain ─────────────────────────────────────────────────────────────────

@pytest.fixture
def stub_onchain(monkeypatch):
    """Avoid network calls in fetch_onchain_metrics."""
    import crypto_model_core as model
    monkeypatch.setattr(
        model,
        "fetch_onchain_metrics",
        lambda pair="BTC/USDT": {
            "sopr": 1.02, "mvrv_z": 1.5, "net_flow": -200.0,
            "whale_activity": True, "source": "test_stub",
        },
    )


def test_onchain_dashboard_smoke(client, stub_onchain):
    r = client.get("/onchain/dashboard?pair=BTC-USDT")
    assert r.status_code == 200
    body = r.json()
    assert body["pair"] == "BTC/USDT"
    assert body["source"] == "test_stub"
    assert body["sopr"] == 1.02


def test_onchain_metric_smoke(client, stub_onchain):
    r = client.get("/onchain/mvrv_z?pair=ETH/USDT")
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "mvrv_z"
    assert body["value"] == 1.5
    assert body["pair"] == "ETH/USDT"


def test_onchain_metric_unknown_returns_404(client, stub_onchain):
    r = client.get("/onchain/not_a_real_metric")
    assert r.status_code == 404


# ── Alerts CRUD ──────────────────────────────────────────────────────────────

def test_alerts_list_configure_smoke(client, stub_alerts_config):
    r = client.get("/alerts/configure")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(rule.get("id") == "preexisting" for rule in body["rules"])


def test_alerts_create_configure_smoke(client, stub_alerts_config):
    payload = {
        "pair": "ETH/USDT",
        "condition": "confidence_above",
        "threshold": 75.0,
        "channels": ["email"],
        "note": "phase-d-1 smoke test",
    }
    r = client.post("/alerts/configure", json=payload)
    assert r.status_code == 200
    rule = r.json()["rule"]
    assert rule["pair"] == "ETH/USDT"
    assert "id" in rule and isinstance(rule["id"], str)


def test_alerts_delete_unknown_returns_404(client, stub_alerts_config):
    r = client.delete("/alerts/configure/does-not-exist")
    assert r.status_code == 404


def test_alerts_create_invalid_payload_returns_422(client, stub_alerts_config):
    r = client.post("/alerts/configure", json={"pair": "BTC/USDT"})  # missing required fields
    assert r.status_code == 422


# ── AI Assistant ─────────────────────────────────────────────────────────────

@pytest.fixture
def stub_llm(monkeypatch):
    import llm_analysis
    monkeypatch.setattr(
        llm_analysis,
        "generate_signal_story",
        lambda pair, signal, confidence, indicators: f"stubbed story for {pair} {signal}",
    )


def test_ai_ask_smoke(client, stub_llm):
    payload = {
        "pair": "BTC/USDT",
        "signal": "BUY",
        "confidence": 78.0,
        "indicators": {"rsi": 65, "macd": 0.5, "adx": 28},
        "question": None,
    }
    r = client.post("/ai/ask", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["pair"] == "BTC/USDT"
    assert body["signal"] == "BUY"
    assert "stubbed story" in body["text"]
    assert body["source"].startswith("llm_analysis")


def test_ai_decisions_smoke(client):
    r = client.get("/ai/decisions?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert "decisions" in body and isinstance(body["decisions"], list)
    assert body["count"] == len(body["decisions"])


# ── Settings ─────────────────────────────────────────────────────────────────

def test_settings_get_redacts_secrets(client, stub_alerts_config):
    # Seed a non-empty api_key into the in-memory config and expect redaction.
    stub_alerts_config["api_key"] = "secret-deadbeef"
    r = client.get("/settings/")
    assert r.status_code == 200
    body = r.json()
    assert body["all"]["api_key"].startswith("•")  # redacted, not the literal secret
    assert "secret-deadbeef" not in r.text


def test_settings_put_signal_risk_smoke(client, stub_alerts_config):
    r = client.put("/settings/signal-risk", json={
        "min_confidence_threshold": 65,
        "high_conf_threshold": 80,
        "ignored_unknown_key": "should be dropped",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["applied"]["min_confidence_threshold"] == 65
    assert "ignored_unknown_key" not in body["applied"]


def test_settings_put_dev_tools_smoke(client, stub_alerts_config):
    r = client.put("/settings/dev-tools", json={"debug_logging": True})
    assert r.status_code == 200
    assert r.json()["applied"]["debug_logging"] is True


def test_settings_put_execution_smoke(client, stub_alerts_config):
    r = client.put("/settings/execution", json={"max_order_size_usd": 250.0})
    assert r.status_code == 200
    assert r.json()["applied"]["max_order_size_usd"] == 250.0


# ── Settings · Trading (D-ext) ──────────────────────────────────────────────

def test_settings_put_trading_smoke(client, stub_alerts_config):
    r = client.put("/settings/trading", json={
        "trading_pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "active_timeframes": ["5m", "15m", "1h"],
        "ta_exchange": "OKX",
        "regional_color_convention": False,
        "compact_watchlist_mode": True,
        "ignored_unknown_key": "should be dropped",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["applied"]["ta_exchange"] == "OKX"
    assert body["applied"]["compact_watchlist_mode"] is True
    assert "ignored_unknown_key" not in body["applied"]


def test_settings_get_includes_trading_group(client, stub_alerts_config):
    stub_alerts_config["trading_pairs"] = ["BTC/USDT"]
    stub_alerts_config["ta_exchange"] = "OKX"
    r = client.get("/settings/")
    assert r.status_code == 200
    body = r.json()
    assert "trading" in body, "Trading group must appear in GET /settings/"
    assert body["trading"].get("ta_exchange") == "OKX"


# ── Exchange (D-ext) ─────────────────────────────────────────────────────────

def test_exchange_test_connection_no_keys_503(client, monkeypatch):
    """Without configured keys, the endpoint returns 503 with operator guidance."""
    import execution as exec_module
    monkeypatch.setattr(exec_module, "get_status",
                        lambda: {"keys_configured": False, "live_trading": False})
    r = client.post("/exchange/test-connection")
    assert r.status_code == 503
    assert "OKX API keys" in r.json()["detail"]


def test_exchange_test_connection_with_keys_returns_result(client, monkeypatch):
    """With keys configured, returns the test_connection() result body."""
    import execution as exec_module
    monkeypatch.setattr(exec_module, "get_status",
                        lambda: {"keys_configured": True, "live_trading": False})
    monkeypatch.setattr(exec_module, "test_connection",
                        lambda: {"ok": True, "balance_usdt": 123.45, "error": None})
    r = client.post("/exchange/test-connection")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["balance_usdt"] == 123.45


# ── Diagnostics (D-ext) ──────────────────────────────────────────────────────

def test_diagnostics_circuit_breakers_smoke(client):
    r = client.get("/diagnostics/circuit-breakers")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "all_operational" in body
    assert isinstance(body["gates"], list)
    assert body["gate_count"] == 7
    assert len(body["gates"]) == 7
    # Each gate has the canonical shape the frontend renders
    for g in body["gates"]:
        assert {"id", "label", "status", "detail"} <= set(g.keys())
        assert g["status"] in {"ok", "warn", "breach"}
    # Mockup-locked labels in mockup order
    expected_labels = [
        "Daily loss limit",
        "Max drawdown",
        "Concurrent positions",
        "Cooldown after loss",
        "Trade-size cap",
        "Allowlist (TIER1 ∪ TIER2)",
        "Emergency stop flag",
    ]
    assert [g["label"] for g in body["gates"]] == expected_labels


def test_diagnostics_circuit_breakers_emergency_breach(client, monkeypatch):
    import agent as agent_module
    monkeypatch.setattr(agent_module, "is_emergency_stop", lambda: True)
    r = client.get("/diagnostics/circuit-breakers")
    assert r.status_code == 200
    body = r.json()
    g7 = body["gates"][6]
    assert g7["label"] == "Emergency stop flag"
    assert g7["status"] == "breach"
    assert body["all_operational"] is False


def test_diagnostics_database_smoke(client):
    r = client.get("/diagnostics/database")
    assert r.status_code == 200
    body = r.json()
    assert "tables" in body
    assert "db_size_kb" in body
    assert "db_size_mb" in body
    # Mockup KPI strip needs these specific table counts
    assert {"feedback_log", "signal_history", "backtest_trades", "paper_trades"} <= set(body["tables"].keys())
    assert body["wal_mode"] is True
