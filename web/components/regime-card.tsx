"use client";

import { cn } from "@/lib/utils";

export type RegimeState = "bull" | "bear" | "transition" | "accumulation" | "distribution";

interface RegimeCardProps {
  ticker: string;
  state: RegimeState;
  confidence: number;
  since: string;
  durationDays: number;
  selected?: boolean;
  onClick?: () => void;
}

const stateConfig: Record<
  RegimeState,
  { label: string; shape: string; textColor: string; bgColor: string; borderColor: string }
> = {
  bull: {
    label: "BULL",
    shape: "▲",
    textColor: "text-success",
    bgColor: "bg-success/10",
    borderColor: "border-l-success",
  },
  bear: {
    label: "BEAR",
    shape: "▼",
    textColor: "text-danger",
    bgColor: "bg-danger/10",
    borderColor: "border-l-danger",
  },
  transition: {
    label: "TRANSITION",
    shape: "◆",
    textColor: "text-warning",
    bgColor: "bg-warning/10",
    borderColor: "border-l-warning",
  },
  accumulation: {
    label: "ACCUMULATION",
    shape: "●",
    textColor: "text-teal",
    bgColor: "bg-teal/10",
    borderColor: "border-l-teal",
  },
  distribution: {
    label: "DISTRIBUTION",
    shape: "○",
    textColor: "text-orange",
    bgColor: "bg-orange/10",
    borderColor: "border-l-orange",
  },
};

export function RegimeCard({
  ticker,
  state,
  confidence,
  since,
  durationDays,
  selected = false,
  onClick,
}: RegimeCardProps) {
  const config = stateConfig[state];

  return (
    <div
      onClick={onClick}
      className={cn(
        "relative flex min-h-[44px] cursor-pointer flex-col gap-1.5 rounded-xl border border-l-[3px] bg-bg-1 p-4 transition-all",
        config.borderColor,
        "hover:bg-bg-2",
        selected && "bg-bg-2 outline outline-1 outline-accent-brand"
      )}
    >
      {selected && (
        <span className="absolute right-3 top-2.5 text-[9.5px] font-semibold uppercase tracking-wider text-accent-brand">
          shown below
        </span>
      )}
      <div className="font-mono text-sm font-semibold">{ticker}</div>
      <div className="mt-1 flex items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold tracking-wider",
            config.textColor,
            config.bgColor
          )}
        >
          <span>{config.shape}</span>
          <span>{config.label}</span>
        </span>
      </div>
      <div className="font-mono text-[11.5px] text-text-muted">confidence {confidence}%</div>
      <div className="mt-1 text-[11px] text-text-muted">
        since {since} · {durationDays}d{durationDays > 7 ? " stable" : ""}
      </div>
    </div>
  );
}
