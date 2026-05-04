"use client";

import { cn } from "@/lib/utils";

export type TimelineState = "bull" | "bear" | "transition" | "accumulation" | "distribution";

interface TimelineSegment {
  state: TimelineState;
  widthPercent: number;
  label: string;
}

interface RegimeTimelineProps {
  ticker: string;
  segments: TimelineSegment[];
  dates: string[];
  description?: string;
}

const stateConfig: Record<TimelineState, { bgColor: string; textColor: string }> = {
  bull: { bgColor: "bg-success", textColor: "text-success" },
  bear: { bgColor: "bg-danger", textColor: "text-danger" },
  transition: { bgColor: "bg-warning", textColor: "text-warning" },
  accumulation: { bgColor: "bg-teal", textColor: "text-teal" },
  distribution: { bgColor: "bg-orange", textColor: "text-orange" },
};

export function RegimeTimeline({ ticker, segments, dates, description }: RegimeTimelineProps) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-5">
      <div className="mb-4 text-xs font-medium uppercase tracking-wider text-text-muted">
        {ticker} regime state · last 90d
      </div>

      {/* Labels above bar */}
      <div className="mb-1 flex">
        {segments.map((seg, i) => {
          const config = stateConfig[seg.state];
          return (
            <div
              key={i}
              className="flex shrink-0 items-center justify-center overflow-hidden text-center"
              style={{ width: `${seg.widthPercent}%` }}
            >
              <span className={cn("text-[10px] font-semibold uppercase tracking-wide", config.textColor)}>
                {seg.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Colored bar segments */}
      <div className="flex h-8 overflow-hidden rounded-lg">
        {segments.map((seg, i) => {
          const config = stateConfig[seg.state];
          return (
            <div
              key={i}
              className={cn("shrink-0", config.bgColor)}
              style={{ width: `${seg.widthPercent}%` }}
            />
          );
        })}
      </div>

      {/* Date axis */}
      <div className="mt-2 flex justify-between text-[11px] text-text-muted">
        {dates.map((date, i) => (
          <span key={i}>{date}</span>
        ))}
      </div>

      {/* Description */}
      {description && (
        <p className="mt-5 text-xs leading-relaxed text-text-muted">{description}</p>
      )}
    </div>
  );
}
