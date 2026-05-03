"use client";

import { useState } from "react";
import { useCircuitBreakers, useDatabaseHealth } from "@/hooks/use-diagnostics";
import { formatNumber } from "@/lib/format";
import type { CircuitBreakerGate } from "@/lib/api-types";

// AUDIT-2026-05-03 (D4b): Settings · Dev Tools page wired:
// - Circuit-breaker 7-gate card → useCircuitBreakers (live)
// - Database 5-col KPI strip → useDatabaseHealth (live)
// Sidebar tools / API config / endpoint reference stay as v0 mock —
// they're operator-action UIs that don't have backing endpoints, or
// the contents are static (build info, secrets copy, start command).

/** Map FastAPI gate status to display string + color class. */
function gateDisplay(gate: CircuitBreakerGate): { name: string; status: string; color: string } {
  const symbol =
    gate.status === "ok"
      ? "✓"
      : gate.status === "warn"
        ? "⚠"
        : gate.status === "breach"
          ? "✗"
          : "○"; // unmeasured
  const color =
    gate.status === "ok"
      ? "text-success"
      : gate.status === "warn"
        ? "text-warning"
        : gate.status === "breach"
          ? "text-danger"
          : "text-text-muted"; // unmeasured = neutral
  return {
    name: `Gate ${gate.id} · ${gate.label}`,
    status: `${symbol} ${gate.detail}`,
    color,
  };
}

const sidebarTools = [
  {
    icon: "🔁",
    name: "Auto-Scan",
    desc: "scheduled top-100 sweep · currently every 30 min",
    action: "Configure",
  },
  {
    icon: "🧪",
    name: "Demo / Sandbox",
    desc: "paper-mode toggle · safe to play with live UI",
    action: "Open",
  },
  {
    icon: "📡",
    name: "API Health",
    desc: "OKX · Glassnode · Dune · CoinGecko status",
    action: "Check",
  },
  {
    icon: "👛",
    name: "Wallet Import",
    desc: "CSV / read-only address tracking",
    action: "Import",
  },
  {
    icon: "🔑",
    name: "API Keys",
    desc: "third-party data providers · separate from execution keys",
    action: "Manage",
  },
  {
    icon: "ℹ️",
    name: "Build Info",
    desc: "v2026.04.29 · commit 335832c · branch redesign/ui-2026-05-full-mockup-match",
    action: "Details",
  },
];

// gates + dbStats are now derived from live hooks inside the page
// component — see useCircuitBreakers() + useDatabaseHealth() below.

const endpoints = [
  { method: "GET", path: "/health", auth: "—" },
  { method: "GET", path: "/signals", auth: "key" },
  { method: "GET", path: "/signals/{pair}", auth: "key" },
  { method: "GET", path: "/signals/history", auth: "key" },
  { method: "GET", path: "/positions", auth: "key" },
  { method: "GET", path: "/paper-trades", auth: "key" },
  { method: "GET", path: "/backtest", auth: "key" },
  { method: "GET", path: "/backtest/trades", auth: "key" },
  { method: "GET", path: "/backtest/runs", auth: "key" },
  { method: "GET", path: "/weights", auth: "key" },
  { method: "GET", path: "/scan/status", auth: "—" },
  { method: "POST", path: "/scan/trigger", auth: "key" },
  { method: "POST", path: "/webhook/tradingview", auth: "key" },
  { method: "GET", path: "/alerts/log", auth: "key" },
];

export default function DevToolsSettingsPage() {
  const [showAllTables, setShowAllTables] = useState(false);
  const cbQuery = useCircuitBreakers();
  const dbQuery = useDatabaseHealth();

  // Derive gate display rows from /diagnostics/circuit-breakers
  const gates = (cbQuery.data?.gates ?? []).map(gateDisplay);
  const allOperational = cbQuery.data?.all_operational ?? false;
  const hasUnmeasured = cbQuery.data?.has_unmeasured ?? false;
  // AUDIT-2026-05-03 (D4 audit, LOW): format the ISO timestamp as a
  // local time-of-day string so the operator sees "14:32:14" instead
  // of the raw "2026-05-03T15:54:35.985949+00:00" output.
  const lastCheck = (() => {
    const iso = cbQuery.data?.last_check;
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleTimeString("en-US", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return iso;
    }
  })();

  // Header pill copy reflects all_operational + has_unmeasured per
  // the P-19 honest-UI contract (gate 4 + gate 5 are _unmeasured by
  // design; the pill should not show solid green when any gate is
  // unmeasured).
  const headerPillText = (() => {
    if (cbQuery.isLoading) return "Loading…";
    if (cbQuery.isError) return "Status unavailable";
    if (allOperational) return `All ${gates.length} gates operational`;
    if (hasUnmeasured) return `${gates.length - gates.filter((g) => g.color === "text-text-muted").length} of ${gates.length} measured`;
    return "Gate breach — investigate";
  })();
  const headerPillClass = (() => {
    if (cbQuery.isError) return "bg-danger/10 text-danger";
    if (allOperational) return "bg-success/10 text-success";
    if (hasUnmeasured) return "bg-warning/10 text-warning";
    return "bg-danger/10 text-danger";
  })();

  // Derive 5-col KPI strip from /diagnostics/database
  const dbStats = (() => {
    const d = dbQuery.data;
    if (!d) {
      return [
        { label: "Feedback log", value: "—", sub: "loading" },
        { label: "Signal history", value: "—", sub: "loading" },
        { label: "Backtest trades", value: "—", sub: "loading" },
        { label: "Paper trades", value: "—", sub: "loading" },
        { label: "DB size", value: "—", sub: "loading" },
      ];
    }
    return [
      { label: "Feedback log", value: formatNumber(d.tables.feedback_log), sub: "rows" },
      { label: "Signal history", value: formatNumber(d.tables.signal_history), sub: "rows" },
      {
        label: "Backtest trades",
        value: formatNumber(d.tables.backtest_trades),
        sub: `rows · ${d.backtest_unique_runs} unique runs`,
      },
      { label: "Paper trades", value: formatNumber(d.tables.paper_trades), sub: "rows" },
      {
        label: "DB size",
        value: formatNumber(d.db_size_kb),
        sub: `KB · ${formatNumber(d.db_size_mb, 1)} MB`,
      },
    ];
  })();

  return (
    <div className="space-y-6">
      {/* Card 1: Sidebar tools */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <div className="mb-1 flex items-center gap-2">
          <span>🧰</span>
          <h3 className="text-sm font-semibold text-text-primary">
            Sidebar tools
          </h3>
        </div>
        <p className="mb-4 text-[11px] text-text-muted">
          relocated from the legacy left rail in the 2026-04 redesign · still
          operator-accessible
        </p>

        <div className="grid gap-3 md:grid-cols-2">
          {sidebarTools.map((tool) => (
            <div
              key={tool.name}
              className="flex items-center justify-between gap-3 rounded-lg border border-border-default bg-bg-2 p-3"
            >
              <div className="flex items-center gap-3">
                <span className="text-xl">{tool.icon}</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-text-primary">
                    {tool.name}
                  </div>
                  <div className="text-[11px] text-text-muted">{tool.desc}</div>
                </div>
              </div>
              <button className="shrink-0 rounded-md border border-border-default bg-bg-1 px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-bg-3">
                {tool.action}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Card 2: Circuit breakers */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span>🛑</span>
              <h3 className="text-sm font-semibold text-text-primary">
                Circuit breakers · Level-C 7-gate safety
              </h3>
            </div>
            <p className="text-[11px] text-text-muted">
              protects the agent from runaway loss · halts fire on any gate
              breach
            </p>
          </div>
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${headerPillClass}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {headerPillText}
          </span>
        </div>

        {gates.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-default p-6 text-center text-sm text-muted-foreground">
            {cbQuery.isLoading
              ? "Loading circuit breakers…"
              : cbQuery.isError
                ? "Couldn't load circuit breakers — try refreshing in 30 seconds."
                : "No gates configured."}
          </div>
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {gates.map((gate) => (
              <div
                key={gate.name}
                className="flex items-center justify-between rounded-lg bg-bg-2 px-3 py-2 font-mono text-xs"
              >
                <span className="text-text-secondary">{gate.name}</span>
                <span className={gate.color}>{gate.status}</span>
              </div>
            ))}
          </div>
        )}

        <p className="mt-4 text-[11px] text-text-muted">
          Last check: {lastCheck}
          {hasUnmeasured && (
            <>
              {" · "}
              <span className="text-warning">
                Some gates are not status-tracked at read-time (enforced at order time)
              </span>
            </>
          )}
        </p>
      </div>

      {/* Card 3: Database health */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <div className="mb-1 flex items-center gap-2">
          <span>🗄️</span>
          <h3 className="text-sm font-semibold text-text-primary">
            Database health
          </h3>
        </div>
        <p className="mb-4 text-[11px] text-text-muted">
          SQLite WAL-mode · row counts and disk usage · auto-vacuum nightly
        </p>

        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
          {dbStats.map((stat) => (
            <div
              key={stat.label}
              className="rounded-lg bg-bg-2 px-3 py-2 text-center"
            >
              <div className="font-mono text-lg font-semibold text-text-primary">
                {stat.value}
              </div>
              <div className="text-[10px] text-text-muted">{stat.label}</div>
              <div className="text-[9px] text-text-muted">{stat.sub}</div>
            </div>
          ))}
        </div>

        <button
          onClick={() => setShowAllTables(!showAllTables)}
          className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary"
        >
          <span>{showAllTables ? "▾" : "▸"}</span>
          <span>Show all 18 table counts</span>
        </button>
      </div>

      {/* Card 4: REST API server */}
      <div className="rounded-xl border border-border-default bg-bg-1 p-4">
        <div className="mb-1 flex items-center gap-2">
          <span>🚀</span>
          <h3 className="text-sm font-semibold text-text-primary">
            REST API server
          </h3>
        </div>
        <p className="mb-4 text-[11px] text-text-muted">
          FastAPI + Uvicorn · 14 endpoints for external integrations and
          TradingView webhooks
        </p>

        <div className="grid gap-4 lg:grid-cols-2">
          {/* Left: Config */}
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-text-primary">
                API Key
              </label>
              <input
                type="password"
                placeholder="●●●● (saved)"
                className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-text-primary">
                  Host
                </label>
                <input
                  type="text"
                  defaultValue="0.0.0.0"
                  className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-text-primary">
                  Port
                </label>
                <input
                  type="text"
                  defaultValue="8000"
                  className="min-h-[44px] w-full rounded-lg border border-border-default bg-bg-2 px-3 py-2 font-mono text-sm text-text-primary"
                />
              </div>
            </div>
            <button className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90">
              <span>💾</span>
              <span>Save API Config</span>
            </button>
          </div>

          {/* Right: Start command + Secrets */}
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-text-primary">
                Start command
              </label>
              <pre className="overflow-x-auto rounded-lg bg-bg-2 p-3 font-mono text-xs text-text-secondary">
                {`cd "/path/to/crypto-signal-app"
python -m uvicorn api:app \\
  --host 0.0.0.0 --port 8000 \\
  --reload`}
              </pre>
              <p className="text-[11px] text-text-muted">
                Swagger UI:{" "}
                <span className="font-mono text-accent-brand">
                  http://localhost:8000/docs
                </span>
              </p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-text-primary">
                Secrets
              </label>
              <p className="text-[11px] text-text-muted">
                Secrets are environment-only. Production secrets live in Render (FastAPI) and Vercel (Next.js) dashboards. Local dev uses <code className="rounded bg-bg-2 px-1 font-mono">.env.local</code> at the Next.js root (gitignored). The legacy <code className="rounded bg-bg-2 px-1 font-mono">.streamlit/secrets.toml</code> path is no longer read.
              </p>
              <pre className="overflow-x-auto rounded-lg bg-bg-2 p-3 font-mono text-xs text-text-secondary">
{`# .env.local (Next.js root — gitignored)
NEXT_PUBLIC_API_BASE=http://localhost:8000
CRYPTO_SIGNAL_API_KEY=<paste-from-render-dashboard>`}
              </pre>
            </div>
          </div>
        </div>

        {/* Endpoint reference */}
        <div className="mt-6">
          <h4 className="mb-3 text-sm font-medium text-text-primary">
            Endpoint reference (14)
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border-default text-text-muted">
                  <th className="pb-2 pr-4 font-medium">Method</th>
                  <th className="pb-2 pr-4 font-medium">Endpoint</th>
                  <th className="pb-2 font-medium">Auth</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {endpoints.map((ep) => (
                  <tr
                    key={`${ep.method}-${ep.path}`}
                    className="border-b border-border-default last:border-0"
                  >
                    <td className="py-2 pr-4">
                      <span
                        className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                          ep.method === "GET"
                            ? "bg-success/10 text-success"
                            : "bg-info/10 text-info"
                        }`}
                      >
                        {ep.method}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-text-secondary">{ep.path}</td>
                    <td className="py-2 text-text-muted">{ep.auth}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
