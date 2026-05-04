"use client";

import { useEffect, useId, useState } from "react";
import { cn } from "@/lib/utils";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { AgentStatusCard } from "@/components/agent-status-card";
import { AgentMetricStrip } from "@/components/agent-metric-strip";
import { DecisionsTable } from "@/components/decisions-table";
import { PipelineDiagram } from "@/components/pipeline-diagram";
import { AgentConfigCard } from "@/components/agent-config-card";
import { EmergencyStopCard } from "@/components/emergency-stop-card";
import { useAiDecisions, useAskAi } from "@/hooks/use-ai";
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

  // AUDIT-2026-05-03 (D4 audit, LOW): format ISO timestamp as
  // "14:32:18" / "May 03, 14:32" instead of the raw
  // "2026-05-03T14:32:18..." that landed in the table.
  const timeStr = (() => {
    if (!r.timestamp) return "—";
    try {
      const d = new Date(r.timestamp);
      const today = new Date();
      const sameDay =
        d.getFullYear() === today.getFullYear() &&
        d.getMonth() === today.getMonth() &&
        d.getDate() === today.getDate();
      return sameDay
        ? d.toLocaleTimeString("en-US", { hour12: false })
        : d.toLocaleString("en-US", {
            month: "short",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          });
    } catch {
      return String(r.timestamp);
    }
  })();

  return {
    time: timeStr,
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

  // AGENT pill state derived from /execute/status. The toggle on the
  // page (Start/Stop) is wired to local state for D4b — D4c hooks it
  // up to a real /agent/start | /agent/stop endpoint when those land.
  //
  // AUDIT-2026-05-03 (D4 audit, HIGH stale-closure fix): `useState`
  // captures `apiAgentRunning` only at first render — when the query
  // resolves later, `running` would stay at the stale `undefined ->
  // false` value. Sync via useEffect so the local toggle reflects the
  // server-side state on every refetch.
  const apiAgentRunning = Boolean(execQuery.data?.agent_running);
  const [running, setRunning] = useState(apiAgentRunning);
  useEffect(() => {
    setRunning(apiAgentRunning);
  }, [apiAgentRunning]);

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

      {/* Ask Claude — D4d wiring of POST /ai/ask */}
      <section className="mb-6">
        <h2 className="mb-1 text-lg font-semibold text-text-primary">Ask Claude</h2>
        <p className="mb-4 text-[12px] text-text-muted">
          plain-English follow-up on a recent signal · responses cached 30 min
          per (pair, signal) bucket
        </p>
        <AskClaudeCard />
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

/** AUDIT-2026-05-03 (D4d): Ask Claude card — small input + result
 * pane wired to POST /ai/ask via useAskAi mutation. The pair/signal/
 * confidence fields are simple text inputs because the engine
 * sanitizes them server-side via the per-field whitelist landed in
 * P6-LLM-1+LLM-2 (commits 40a473e, 1c28a20). Indicators are typed
 * free-form for now; D-extension can wire a ticker-picker dropdown
 * once a /signals enriched endpoint surfaces the most-recent
 * indicator snapshot per pair. */
function AskClaudeCard() {
  const ask = useAskAi();
  const [pair, setPair] = useState("BTC/USDT");
  const [signal, setSignal] = useState("BUY");
  const [confidence, setConfidence] = useState("78");
  const [question, setQuestion] = useState("");
  // AUDIT-2026-05-04 (T4 a11y): label↔control association IDs.
  const pairId = useId();
  const signalId = useId();
  const confId = useId();
  const questionId = useId();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const conf = parseFloat(confidence);
    if (Number.isNaN(conf)) return;
    ask.mutate({
      pair,
      signal,
      confidence: conf,
      indicators: {},
      question: question || null,
    });
  };

  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1.5">
            <label htmlFor={pairId} className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
              Pair
            </label>
            <input
              id={pairId}
              type="text"
              value={pair}
              onChange={(e) => setPair(e.target.value)}
              className="min-h-[36px] w-full rounded-md border border-border-default bg-bg-2 px-3 py-1.5 font-mono text-sm text-text-primary"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor={signalId} className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
              Signal
            </label>
            <select
              id={signalId}
              value={signal}
              onChange={(e) => setSignal(e.target.value)}
              className="min-h-[36px] w-full rounded-md border border-border-default bg-bg-2 px-3 py-1.5 text-sm text-text-primary"
            >
              <option>BUY</option>
              <option>SELL</option>
              <option>STRONG BUY</option>
              <option>STRONG SELL</option>
              <option>NEUTRAL</option>
              <option>HOLD</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor={confId} className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
              Confidence %
            </label>
            <input
              id={confId}
              type="number"
              min="0"
              max="100"
              value={confidence}
              onChange={(e) => setConfidence(e.target.value)}
              className="min-h-[36px] w-full rounded-md border border-border-default bg-bg-2 px-3 py-1.5 font-mono text-sm text-text-primary"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor={questionId} className="text-[11.5px] font-medium uppercase tracking-[0.05em] text-text-muted">
            Question (optional)
          </label>
          <input
            id={questionId}
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. why is confidence dropping vs yesterday?"
            className="min-h-[36px] w-full rounded-md border border-border-default bg-bg-2 px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted"
          />
        </div>
        <button
          type="submit"
          disabled={ask.isPending}
          className="inline-flex min-h-[40px] items-center gap-2 rounded-lg bg-accent-brand px-4 py-2 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90 disabled:opacity-60 disabled:cursor-wait"
        >
          <span className={cn(ask.isPending && "animate-spin")}>✨</span>
          <span>{ask.isPending ? "Asking…" : "Ask Claude"}</span>
        </button>
      </form>

      {ask.isError && (
        <div className="mt-3 rounded-lg border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
          Ask failed — {String(ask.error?.message ?? "unknown error")}
        </div>
      )}
      {ask.data && (
        <div
          className={cn(
            "mt-3 rounded-lg border p-3 text-sm",
            ask.data.source === "unavailable"
              ? "border-warning/30 bg-warning/5 text-warning"
              : "border-info/30 bg-info/5 text-text-primary",
          )}
        >
          {ask.data.source === "unavailable" ? (
            <span>
              AI Assistant unavailable — fallback rule-based explanation only.
            </span>
          ) : (
            <span className="leading-relaxed">{ask.data.text}</span>
          )}
        </div>
      )}
    </div>
  );
}
