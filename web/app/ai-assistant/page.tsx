"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { AgentStatusCard } from "@/components/agent-status-card";
import { AgentMetricStrip } from "@/components/agent-metric-strip";
import { DecisionsTable } from "@/components/decisions-table";
import { PipelineDiagram } from "@/components/pipeline-diagram";
import { AgentConfigCard } from "@/components/agent-config-card";
import { EmergencyStopCard } from "@/components/emergency-stop-card";
import { useAiDecisions } from "@/hooks/use-ai";
import { useExecutionStatus } from "@/hooks/use-execution-status";
import type { AiDecision } from "@/lib/api-types";

// AUDIT-2026-05-03 (D4b): AI Assistant page wired:
// - AGENT · RUNNING pill (running flag) via useExecutionStatus polling
// - Recent Decisions table via useAiDecisions(limit=10)
// AgentMetricStrip + AgentConfigCard + EmergencyStopCard + Pipeline
// stay as mocks until the FastAPI side surfaces aggregate counters
// (cycles, last-cycle-age, restart count) — those are derived from
// agent_log + execution_log and need a /agent/summary endpoint.

/** Map FastAPI AiDecision row → DecisionsTable entry shape. */
function rowToDecision(r: AiDecision): {
  time: string;
  pair: string;
  decision: "approve" | "reject" | "skip";
  confidence: number;
  rationale: string;
  status: "executed" | "pending" | "dry-run" | "override";
} {
  const dir = String(r.direction ?? "").toUpperCase();
  const conf = Math.round(r.confidence_avg_pct ?? 0);

  let decision: "approve" | "reject" | "skip" = "skip";
  if (dir.includes("BUY")) decision = "approve";
  else if (dir.includes("SELL")) decision = "reject";

  let rationale = `Direction: ${dir || "—"}, confidence ${conf}%`;
  if (typeof r.rationale === "string") rationale = r.rationale;

  // Heuristic status: if confidence >= 75 we'd expect it to have
  // executed; otherwise it's pending or dry-run. Real executed-status
  // comes from joining agent_log with execution_log — for D4b we use
  // this proxy.
  const status: "executed" | "pending" | "dry-run" | "override" =
    conf >= 75 && (dir.includes("BUY") || dir.includes("SELL"))
      ? "executed"
      : conf >= 60
        ? "pending"
        : "dry-run";

  return {
    time: String(r.timestamp ?? "—"),
    pair: String(r.pair ?? "—"),
    decision,
    confidence: conf,
    rationale,
    status,
  };
}

// Mock metrics + fallback table data — kept until /agent/summary lands
// (returns total_cycles + last_cycle_age + last_pair + last_decision).
const metrics = [
  { label: "Total Cycles", value: "—", subtext: "TODO(D-ext)" },
  { label: "Last Cycle", value: "—", subtext: "TODO(D-ext)" },
  { label: "Last Pair", value: "—", subtext: "TODO(D-ext)" },
  { label: "Last Decision", value: "—", subtext: "TODO(D-ext)" },
];

export default function AIAssistantPage() {
  const decisionsQuery = useAiDecisions(10);
  const execQuery = useExecutionStatus({ polling: true });

  // AGENT pill state derived from /execution/status. The toggle on the
  // page (Start/Stop) is wired to local state for D4b — D4c hooks it
  // up to a real /agent/start | /agent/stop endpoint when those land.
  const apiAgentRunning = Boolean(execQuery.data?.agent_running);
  const [running, setRunning] = useState(apiAgentRunning);

  // Map live decisions to the table shape; fall back to empty when
  // no decisions yet.
  const decisions = (decisionsQuery.data?.decisions ?? []).map(rowToDecision);
  const totalDecisions = decisionsQuery.data?.count ?? decisions.length;

  return (
    <AppShell crumbs="Research" currentPage="AI Assistant" agentRunning={running}>
      <PageHeader
        title="AI Assistant"
        subtitle="LangGraph + Claude Sonnet 4.6 autonomous agent. Hard Python risk gates wrap every Claude decision — Claude may only approve or reject, never place orders directly."
      />

      {/* Live status */}
      <section className="mb-6">
        <AgentStatusCard
          running={running}
          cycle={47}
          onStart={() => setRunning(true)}
          onStop={() => setRunning(false)}
        />
      </section>

      {/* Metrics strip */}
      <section className="mb-6">
        <AgentMetricStrip metrics={metrics} />
      </section>

      {/* Engine + restart row */}
      <section className="mb-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
            Engine
          </div>
          <div className="mt-1 font-mono text-sm font-semibold text-text-primary">
            LangGraph state machine
          </div>
          <div className="mt-1 text-[11px] text-text-muted">
            graph: 7 nodes · 12 edges · sequential fallback ready
          </div>
        </div>
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
            Crash Restarts
          </div>
          <div className="mt-1 font-mono text-sm font-semibold text-success">0</div>
          <div className="mt-1 text-[11px] text-text-muted">
            supervisor active · uptime 17d 6h
          </div>
        </div>
      </section>

      {/* In-progress bar */}
      {running && (
        <section className="mb-6">
          <div className="flex items-center gap-3 rounded-xl border border-info/30 bg-info/5 p-4">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-info border-t-transparent" />
            <span className="text-sm text-info">
              Processing AVAX/USDT — cycle running for 14s · waiting on Layer 4 (on-chain) Glassnode call
            </span>
          </div>
        </section>
      )}

      {/* Agent Configuration */}
      <section className="mb-6">
        <h2 className="mb-1 text-lg font-semibold text-text-primary">Agent Configuration</h2>
        <p className="mb-4 text-[12px] text-text-muted">
          saved to alerts_config.json · takes effect on next cycle
        </p>
        <AgentConfigCard />
      </section>

      {/* Emergency Controls */}
      <section className="mb-6">
        <h2 className="mb-1 text-lg font-semibold text-text-primary">Emergency Controls</h2>
        <p className="mb-4 text-[12px] text-text-muted">
          overrides all other config · instant effect
        </p>
        <EmergencyStopCard />
      </section>

      {/* Recent Decisions */}
      <section className="mb-6">
        <h2 className="mb-1 text-lg font-semibold text-text-primary">Recent Decisions</h2>
        <p className="mb-4 text-[12px] text-text-muted">
          last 10 cycles · click any row for full Claude rationale + signal snapshot
        </p>
        {decisions.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-default p-6 text-center text-sm text-muted-foreground">
            {decisionsQuery.isLoading
              ? "Loading recent decisions…"
              : decisionsQuery.isError
                ? "Couldn't load decisions — try refreshing in 30 seconds."
                : "No agent decisions yet — start the agent to begin recording."}
          </div>
        ) : (
          <DecisionsTable decisions={decisions} total={totalDecisions} />
        )}
      </section>

      {/* Pipeline Architecture */}
      <section className="mb-6">
        <h2 className="mb-1 text-lg font-semibold text-text-primary">Pipeline Architecture</h2>
        <p className="mb-4 text-[12px] text-text-muted">
          hard risk gates prevent Claude from ever executing without validation
        </p>
        <PipelineDiagram />
      </section>
    </AppShell>
  );
}
