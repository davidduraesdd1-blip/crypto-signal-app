"use client";

import { cn } from "@/lib/utils";

// AUDIT-2026-05-06 (P1-D): canonical SignalType lives in lib/signal-types.
// Re-export for back-compat with existing `import { SignalType } from
// "@/components/signal-card"` patterns.
export type { SignalType } from "@/lib/signal-types";
import type { SignalType } from "@/lib/signal-types";

interface SignalCardProps {
  ticker: string;
  price: string;
  change: string;
  changeDirection: "up" | "down";
  signal: SignalType;
  regime: string;
  confidence: string;
}

export function SignalCard({
  ticker,
  price,
  change,
  changeDirection,
  signal,
  regime,
  confidence,
}: SignalCardProps) {
  const signalConfig = {
    buy: {
      icon: "▲",
      label: "Buy",
      className: "bg-success/15 text-success",
    },
    hold: {
      icon: "■",
      label: "Hold",
      className: "bg-warning/15 text-warning",
    },
    sell: {
      icon: "▼",
      label: "Sell",
      className: "bg-danger/15 text-danger",
    },
  };

  const config = signalConfig[signal];

  return (
    <div className="flex min-w-0 max-w-full flex-col gap-3 rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Header row: ticker + signal badge */}
      <div className="flex items-center justify-between gap-2">
        <button
          className="inline-flex min-h-[44px] items-center gap-1 rounded-md border border-transparent px-1 py-0.5 text-sm font-medium text-text-secondary transition-all hover:border-border-default hover:bg-bg-2 hover:text-text-primary"
          title="Click to swap pair"
        >
          {ticker} <span className="text-[10px] text-text-muted">▾</span>
        </button>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-semibold tracking-wide",
            config.className
          )}
        >
          {config.icon} {config.label}
        </span>
      </div>

      {/* Price */}
      <div className="font-mono text-[28px] font-semibold leading-none tracking-tight">
        {price}
      </div>

      {/* Change + Regime */}
      <div className="flex flex-col gap-1">
        <div
          className={cn(
            "font-mono text-[13px]",
            changeDirection === "up" ? "text-success" : "text-danger"
          )}
        >
          {changeDirection === "up" ? "+" : "-"}{change} · 24h
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-brand" />
          {regime} · {confidence}
        </div>
      </div>
    </div>
  );
}
