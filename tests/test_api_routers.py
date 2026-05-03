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


def test_alerts_create_normalizes_pair(client, stub_alerts_config):
    """AUDIT-2026-05-03: pair input must collapse to canonical BASE/QUOTE
    before persisting so the downstream `check_watchlist_alerts` lookup
    matches regardless of how the frontend formatted the input.
    """
    payload = {
        "pair": "ETHUSDT",  # concatenated form, no separator
        "condition": "price_above",
        "threshold": 3000.0,
        "channels": ["email"],
        "note": "normalize-pair regression test",
    }
    r = client.post("/alerts/configure", json=payload)
    assert r.status_code == 200, r.text
    rule = r.json()["rule"]
    assert rule["pair"] == "ETH/USDT", f"pair not normalized: {rule['pair']!r}"


def test_alerts_create_rejects_unparseable_pair(client, stub_alerts_config):
    """AUDIT-2026-05-03: an unparseable pair raises ValueError in
    normalize_pair which the route surfaces as 422 with the original
    input echoed back, so the frontend can render a useful validation
    error.
    """
    payload = {
        "pair": "!!!",
        "condition": "price_above",
        "threshold": 1.0,
        "channels": ["email"],
    }
    r = client.post("/alerts/configure", json=payload)
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


def test_ai_ask_rejects_out_of_range_confidence(client, stub_llm):
    """AUDIT-2026-05-03: confidence is bounded [0, 100]. An out-of-range
    value fails fast at 422 instead of reaching the LLM call where it
    would be interpolated into the prompt verbatim.
    """
    payload = {
        "pair": "BTC/USDT",
        "signal": "BUY",
        "confidence": 250.0,  # impossible
        "indicators": {},
    }
    r = client.post("/ai/ask", json=payload)
    assert r.status_code == 422


def test_ai_ask_rejects_unknown_signal(client, stub_llm):
    """AUDIT-2026-05-03: signal must be one of the canonical
    BUY/SELL/STRONG BUY/STRONG SELL/NEUTRAL/HOLD vocabulary.
    """
    payload = {
        "pair": "BTC/USDT",
        "signal": "MOON",  # not in allowed set
        "confidence": 70.0,
        "indicators": {},
    }
    r = client.post("/ai/ask", json=payload)
    assert r.status_code == 422
    assert "MOON" in r.json()["detail"] or "Unknown signal" in r.json()["detail"]


# ── Settings ─────────────────────────────────────────────────────────────────

def test_settings_get_redacts_secrets(client, stub_alerts_config):
    # Seed a non-empty api_key into the in-memory config and expect redaction.
    stub_alerts_config["api_key"] = "secret-deadbeef"
    r = client.get("/settings/")
    assert r.status_code == 200
    body = r.json()
    assert body["all"]["api_key"].startswith("•")  # redacted, not the literal secret
    assert "secret-deadbeef" not in r.text


def test_api_key_env_var_takes_precedence_over_config(monkeypatch):
    """AUDIT-2026-05-03 (CRITICAL C-1 fix): CRYPTO_SIGNAL_API_KEY env
    var must be honored as the primary auth source so the production
    Render deploy has a persistent key home (Render's file system is
    ephemeral and resets on every push). Falls back to alerts_config.json
    only when the env var is unset.
    """
    # Clear the 30s caches in both modules so this test sees fresh state
    from routers import deps as deps_module
    import api as api_module

    canary_env_key = "env-key-2026-05-03-overnight-fix"
    canary_cfg_key = "config-key-should-be-ignored"

    monkeypatch.setattr(deps_module, "_api_key_cache",
                        {"key": None, "ts": 0.0})
    monkeypatch.setattr(api_module, "_api_key_cache",
                        {"key": None, "ts": 0.0})
    monkeypatch.setenv("CRYPTO_SIGNAL_API_KEY", canary_env_key)

    import alerts as alerts_module
    monkeypatch.setattr(alerts_module, "load_alerts_config",
                        lambda: {"api_key": canary_cfg_key})

    # Both auth paths must resolve to the env-var value, not the config
    assert deps_module._get_configured_api_key() == canary_env_key
    assert api_module._get_configured_api_key() == canary_env_key


def test_api_key_falls_back_to_config_when_env_unset(monkeypatch):
    """When CRYPTO_SIGNAL_API_KEY is absent or empty, fall back to the
    alerts_config.json path so local dev + Streamlit UI keep working.
    """
    from routers import deps as deps_module
    import api as api_module

    canary_cfg_key = "config-key-from-alerts-json"

    monkeypatch.setattr(deps_module, "_api_key_cache",
                        {"key": None, "ts": 0.0})
    monkeypatch.setattr(api_module, "_api_key_cache",
                        {"key": None, "ts": 0.0})
    monkeypatch.delenv("CRYPTO_SIGNAL_API_KEY", raising=False)

    import alerts as alerts_module
    monkeypatch.setattr(alerts_module, "load_alerts_config",
                        lambda: {"api_key": canary_cfg_key})

    assert deps_module._get_configured_api_key() == canary_cfg_key
    assert api_module._get_configured_api_key() == canary_cfg_key


def test_settings_get_redacts_unlisted_secrets_by_suffix(client, stub_alerts_config):
    """AUDIT-2026-05-02 (CRITICAL C-2): the redaction list previously had
    drift vs the live alerts_config schema. This regression-guards the
    defense-in-depth suffix match — any future config field with a
    sensitive suffix MUST be redacted even if a maintainer forgets to
    add it to `_REDACTED_KEYS`.
    """
    canary_secrets = {
        "okx_secret":              "leak-okx-secret-xyz",
        "email_pass":              "leak-email-pass-xyz",
        "lunarcrush_key":          "leak-lc-xyz",
        "coinglass_key":           "leak-cg-xyz",
        "cryptoquant_key":         "leak-cq-xyz",
        "glassnode_key":           "leak-gn-xyz",
        "supergrok_sentry_dsn":    "https://leak@sentry.io/xyz",
        # New hypothetical field added by a future maintainer:
        "future_provider_secret":  "leak-future-secret-xyz",
        "future_provider_token":   "leak-future-token-xyz",
    }
    for k, v in canary_secrets.items():
        stub_alerts_config[k] = v
    r = client.get("/settings/")
    assert r.status_code == 200
    body_text = r.text
    body = r.json()
    for k, v in canary_secrets.items():
        # No canary secret value should appear in the response anywhere
        assert v not in body_text, (
            f"Secret value for {k!r} leaked plaintext in /settings/ response"
        )
        # The field itself should still be present, just redacted to bullets
        assert body["all"][k].startswith("•"), (
            f"{k!r} not redacted (current value: {body['all'][k]!r})"
        )


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
    assert "has_unmeasured" in body  # AUDIT-2026-05-02: surfaced for honest UI
    assert isinstance(body["gates"], list)
    assert body["gate_count"] == 7
    assert len(body["gates"]) == 7
    # Each gate has the canonical shape the frontend renders
    for g in body["gates"]:
        assert {"id", "label", "status", "detail"} <= set(g.keys())
        # AUDIT-2026-05-02: "unmeasured" status added so gates that
        # cannot be computed don't fail-open as misleading-green.
        assert g["status"] in {"ok", "warn", "breach", "unmeasured"}
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
    # Cooldown is the canonical "unmeasured" gate (live state not tracked
    # in the agent pipeline yet); regression-guard against a future
    # change that silently flips it back to fake-green.
    g4 = body["gates"][3]
    assert g4["label"] == "Cooldown after loss"
    assert g4["status"] == "unmeasured"
    # Operational composite must reflect the unmeasured gate.
    assert body["all_operational"] is False
    assert body["has_unmeasured"] is True


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
