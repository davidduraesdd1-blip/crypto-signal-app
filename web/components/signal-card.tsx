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

  // AUDIT-2026-05-06 (W2-N1): defensive lookup mirrors the SignalHero
  // hotfix from 9d136c2. Pre P1-D, directionToSignalType could return
  // "strong-buy" / "strong-sell" which crashed this lookup; P1-D
  // narrowed it to 3-tier but the defensive guard stays as
  // belt-and-suspenders for any future SignalType drift.
  const config = signalConfig[signal] ?? signalConfig.hold;

  return (
    <div className="flex min-w-0 max-w-full flex-col gap-3 rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Header row: ticker + signal badge */}
      {/* AUDIT-2026-05-06 (post-launch dropdown fix): the ▾ chevron
          implied a click-to-swap dropdown that never existed (button had
          no onClick). The hero card shows whatever pair the parent
          assigns; pair switching belongs on the /signals page picker.
          Render the ticker as a plain label. */}
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 px-1 py-0.5 text-sm font-medium text-text-secondary">
          {ticker}
        </span>
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
