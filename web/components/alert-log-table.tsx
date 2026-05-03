"use client";

import { cn } from "@/lib/utils";

type AlertType = "buy" | "sell" | "regime" | "onchain" | "funding" | "unlock";
type AlertStatus = "sent" | "failed" | "suppressed";

interface AlertLogEntry {
  timestamp: string;
  type: AlertType;
  typeLabel: string;
  asset: string;
  message: string;
  status: AlertStatus;
  channel: string;
}

interface AlertLogTableProps {
  entries: AlertLogEntry[];
}

const typeConfig: Record<
  AlertType,
  { shape: string; bgClass: string; textClass: string }
> = {
  buy: { shape: "▲", bgClass: "bg-success/15", textClass: "text-success" },
  sell: { shape: "▼", bgClass: "bg-danger/15", textClass: "text-danger" },
  regime: { shape: "◈", bgClass: "bg-info/15", textClass: "text-info" },
  onchain: { shape: "⬡", bgClass: "bg-warning/15", textClass: "text-warning" },
  funding: { shape: "⚡", bgClass: "bg-warning/15", textClass: "text-warning" },
  unlock: { shape: "🔓", bgClass: "bg-bg-3", textClass: "text-text-secondary" },
};

const statusConfig: Record<AlertStatus, { color: string }> = {
  sent: { color: "text-success" },
  failed: { color: "text-danger" },
  suppressed: { color: "text-text-muted" },
};

export function AlertLogTable({ entries }: AlertLogTableProps) {
  return (
    <div className="text-[12.5px]">
      {/* Header - hidden on mobile */}
      <div className="hidden border-b border-border px-1 py-2.5 text-[10.5px] uppercase tracking-[0.05em] text-text-muted md:grid md:grid-cols-[140px_130px_80px_minmax(0,1fr)_100px_110px] md:gap-3">
        <span>Time UTC</span>
        <span>Type</span>
        <span>Asset</span>
        <span>Message</span>
        <span>Status</span>
        <span>Channel</span>
      </div>

      {entries.map((entry, i) => {
        const type = typeConfig[entry.type];
        const status = statusConfig[entry.status];
        return (
          <div
            key={i}
            className="grid grid-cols-[80px_minmax(0,1fr)_80px] items-center gap-3 border-b border-border px-1 py-3 transition-colors hover:bg-bg-2 md:grid-cols-[140px_130px_80px_minmax(0,1fr)_100px_110px]"
          >
            <span className="whitespace-nowrap font-mono text-[11.5px] text-text-muted">
              {entry.timestamp}
            </span>
            <span className="hidden md:block">
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium tracking-[0.02em]",
                  type.bgClass,
                  type.textClass
                )}
              >
                {type.shape} {entry.typeLabel}
              </span>
            </span>
            <span className="hidden font-mono text-[13px] font-semibold md:block">
              {entry.asset}
            </span>
            <span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-text-secondary">
              {entry.message}
            </span>
            <span
              className={cn(
                "flex items-center gap-1.5 text-[11.5px] font-medium",
                status.color
              )}
            >
              <span
                className={cn("h-1.5 w-1.5 rounded-full", {
                  "bg-success": entry.status === "sent",
                  "bg-danger": entry.status === "failed",
                  "bg-text-muted": entry.status === "suppressed",
                })}
              />
              {entry.status}
            </span>
            <span className="hidden font-mono text-[11.5px] text-text-muted md:block">
              {entry.channel}
            </span>
          </div>
        );
      })}
    </div>
  );
}
