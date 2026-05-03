"use client";

import { cn } from "@/lib/utils";

type Decision = "approve" | "reject" | "skip";
type Status = "executed" | "dry-run" | "pending" | "override";

interface DecisionRow {
  time: string;
  pair: string;
  decision: Decision;
  confidence: number;
  rationale: string;
  status: Status;
}

interface DecisionsTableProps {
  decisions: DecisionRow[];
  total: number;
}

const decisionConfig: Record<Decision, { emoji: string; label: string; colorClass: string }> = {
  approve: { emoji: "🟢", label: "Approve", colorClass: "text-success" },
  reject: { emoji: "🔴", label: "Reject", colorClass: "text-danger" },
  skip: { emoji: "⚪", label: "Skip", colorClass: "text-text-muted" },
};

const statusConfig: Record<Status, { label: string; bgClass: string; textClass: string }> = {
  executed: { label: "Executed", bgClass: "bg-success/10", textClass: "text-success" },
  "dry-run": { label: "Dry-run", bgClass: "bg-info/10", textClass: "text-info" },
  pending: { label: "Pending", bgClass: "bg-warning/10", textClass: "text-warning" },
  override: { label: "Override", bgClass: "border border-border-default bg-transparent", textClass: "text-text-muted" },
};

export function DecisionsTable({ decisions, total }: DecisionsTableProps) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1">
      {/* Filter row */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-default p-4">
        <div className="flex flex-wrap items-center gap-2">
          <select className="min-h-[36px] rounded-lg border border-border-default bg-bg-2 px-3 py-1.5 text-sm text-text-primary">
            <option>All Decisions</option>
            <option>Approve</option>
            <option>Reject</option>
            <option>Skip</option>
          </select>
          <select className="min-h-[36px] rounded-lg border border-border-default bg-bg-2 px-3 py-1.5 text-sm text-text-primary">
            <option>All Pairs</option>
            <option>BTC/USDT</option>
            <option>ETH/USDT</option>
            <option>SOL/USDT</option>
          </select>
          <select className="min-h-[36px] rounded-lg border border-border-default bg-bg-2 px-3 py-1.5 text-sm text-text-primary">
            <option>All Statuses</option>
            <option>Executed</option>
            <option>Dry-run</option>
            <option>Pending</option>
            <option>Override</option>
          </select>
        </div>
        <span className="text-xs text-text-muted">
          showing {decisions.length} of {total.toLocaleString()} · scroll for older
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-default text-[11px] uppercase tracking-wider text-text-muted">
              <th className="px-4 py-3 font-medium">Time UTC</th>
              <th className="hidden px-4 py-3 font-medium md:table-cell">Pair</th>
              <th className="px-4 py-3 font-medium">Decision</th>
              <th className="hidden px-4 py-3 font-medium lg:table-cell">Confidence</th>
              <th className="px-4 py-3 font-medium">Rationale</th>
              <th className="hidden px-4 py-3 text-right font-medium lg:table-cell">Status</th>
            </tr>
          </thead>
          <tbody>
            {decisions.map((d, i) => {
              const dc = decisionConfig[d.decision];
              const sc = statusConfig[d.status];
              return (
                <tr
                  key={i}
                  className="cursor-pointer border-b border-border-default transition-colors last:border-b-0 hover:bg-bg-2"
                >
                  <td className="px-4 py-3 font-mono text-[12px] text-text-muted">{d.time}</td>
                  <td className="hidden px-4 py-3 font-mono text-[12px] md:table-cell">{d.pair}</td>
                  <td className="px-4 py-3">
                    <span className={cn("inline-flex items-center gap-1.5 font-medium", dc.colorClass)}>
                      <span>{dc.emoji}</span>
                      <span>{dc.label}</span>
                    </span>
                  </td>
                  <td className="hidden px-4 py-3 font-mono text-[12px] lg:table-cell">{d.confidence}%</td>
                  <td className="max-w-[200px] truncate px-4 py-3 text-[12px] text-text-secondary lg:max-w-[300px]">
                    {d.rationale}
                  </td>
                  <td className="hidden px-4 py-3 text-right lg:table-cell">
                    <span
                      className={cn(
                        "inline-block rounded px-2 py-0.5 text-[11px] font-medium",
                        sc.bgClass,
                        sc.textClass
                      )}
                    >
                      {sc.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="border-t border-border-default p-4 text-[11px] text-text-muted">
        <span className="font-medium">Status legend:</span>{" "}
        <span className="text-success">Executed</span> = order placed ·{" "}
        <span className="text-info">Dry-run</span> = logged only ·{" "}
        <span className="text-warning">Pending</span> = awaiting confirmation ·{" "}
        <span>Override</span> = manually cancelled
      </div>
    </div>
  );
}
