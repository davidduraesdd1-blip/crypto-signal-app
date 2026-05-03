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

// Mock data
const metrics = [
  { label: "Total Cycles", value: "8,924", subtext: "since 2026-04-12" },
  { label: "Last Cycle", value: "42s ago", subtext: "interval 60s" },
  { label: "Last Pair", value: "SOL/USDT", subtext: "timeframe 1h" },
  {
    label: "Last Decision",
    value: "🟢 Approve",
    subtext: "size 2.4% · conf 81%",
    highlight: "success" as const,
  },
];

const decisions = [
  {
    time: "2026-05-02 14:32:18",
    pair: "BTC/USDT",
    decision: "approve" as const,
    confidence: 84,
    rationale: "Composite 84% > threshold 75% · bull regime · funding favorable",
    status: "executed" as const,
  },
  {
    time: "2026-05-02 14:31:14",
    pair: "ETH/USDT",
    decision: "skip" as const,
    confidence: 52,
    rationale: "Pre-gate: composite 52% < min_confidence 75%",
    status: "dry-run" as const,
  },
  {
    time: "2026-05-02 14:30:11",
    pair: "SOL/USDT",
    decision: "reject" as const,
    confidence: 81,
    rationale: "Post-gate: proposed size 11.2% > max_trade_size 10% cap",
    status: "pending" as const,
  },
  {
    time: "2026-05-02 14:29:08",
    pair: "XRP/USDT",
    decision: "skip" as const,
    confidence: 78,
    rationale: "Pre-gate: cooldown active (14:18 −1.4% loss · 1,800s pause)",
    status: "pending" as const,
  },
  {
    time: "2026-05-02 14:28:05",
    pair: "AVAX/USDT",
    decision: "reject" as const,
    confidence: 76,
    rationale: "Pre-gate: drawdown 8.2% approaching 15% cap · manual review queued",
    status: "override" as const,
  },
  {
    time: "2026-05-02 14:27:02",
    pair: "BTC/USDT",
    decision: "approve" as const,
    confidence: 89,
    rationale: "Composite 89% · all 4 layers bullish · position opened at 2.1% size",
    status: "executed" as const,
  },
  {
    time: "2026-05-02 14:26:00",
    pair: "ETH/USDT",
    decision: "skip" as const,
    confidence: 71,
    rationale: "Pre-gate: concurrent positions 6/6 · entry blocked until slot opens",
    status: "pending" as const,
  },
  {
    time: "2026-05-02 14:24:57",
    pair: "SOL/USDT",
    decision: "reject" as const,
    confidence: 82,
    rationale: "Claude: high conviction but funding −0.08% · waiting for funding reset",
    status: "dry-run" as const,
  },
  {
    time: "2026-05-02 14:23:54",
    pair: "BNB/USDT",
    decision: "skip" as const,
    confidence: 55,
    rationale: "Pre-gate: composite 55% < min_confidence 75%",
    status: "dry-run" as const,
  },
  {
    time: "2026-05-02 14:22:51",
    pair: "DOGE/USDT",
    decision: "skip" as const,
    confidence: 63,
    rationale: "Pre-gate: daily P&L −4.8% approaching −5% limit · halting new entries",
    status: "pending" as const,
  },
];

export default function AIAssistantPage() {
  const [running, setRunning] = useState(true);

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
        <DecisionsTable decisions={decisions} total={8924} />
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
