"use client";

import { cn } from "@/lib/utils";

// AUDIT-2026-05-06 (P1-D): canonical SignalType lives in lib/signal-types.
export type { SignalType } from "@/lib/signal-types";
import type { SignalType } from "@/lib/signal-types";

interface TimeframeCell {
  label: string;
  signal: SignalType;
  score: number;
}

interface TimeframeStripProps {
  timeframes: TimeframeCell[];
  activeIndex: number;
  onSelect?: (index: number) => void;
}

const signalConfig: Record<SignalType, { icon: string; label: string; className: string }> = {
  buy: { icon: "▲", label: "BUY", className: "text-success" },
  hold: { icon: "■", label: "HOLD", className: "text-warning" },
  sell: { icon: "▼", label: "SELL", className: "text-danger" },
};

export function TimeframeStrip({ timeframes, activeIndex, onSelect }: TimeframeStripProps) {
  return (
    <div className="grid grid-cols-4 gap-1.5 md:gap-2 lg:grid-cols-8">
      {timeframes.map((tf, index) => {
        const isActive = index === activeIndex;
        const config = signalConfig[tf.signal];
        
        return (
          <button
            key={tf.label}
            onClick={() => onSelect?.(index)}
            className={cn(
              "flex min-h-[44px] flex-col items-center gap-1 rounded-lg border border-border-default bg-bg-2 p-2 transition-all md:p-3",
              "hover:border-border-strong hover:bg-bg-3",
              isActive && "border-accent-brand bg-accent-soft"
            )}
          >
            <span className="font-mono text-xs font-semibold text-text-secondary md:text-[13px]">
              {tf.label}
            </span>
            <span className={cn("flex items-center gap-1 text-[10px] font-semibold tracking-wide md:text-[10.5px]", config.className)}>
              {config.icon} {config.label}
            </span>
            <span className="font-mono text-xs font-semibold text-text-primary md:text-[13.5px]">
              {tf.score}
            </span>
          </button>
        );
      })}
    </div>
  );
}
