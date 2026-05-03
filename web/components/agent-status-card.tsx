"use client";

import { cn } from "@/lib/utils";

interface AgentStatusCardProps {
  running: boolean;
  cycle: number;
  onStart?: () => void;
  onStop?: () => void;
}

export function AgentStatusCard({
  running,
  cycle,
  onStart,
  onStop,
}: AgentStatusCardProps) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left: Status */}
        <div className="flex items-center gap-3">
          <span
            className={cn(
              "inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold uppercase tracking-wide",
              running
                ? "bg-success/10 text-success"
                : "bg-info/10 text-info"
            )}
          >
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                running ? "animate-pulse bg-success" : "bg-info"
              )}
            />
            {running ? "RUNNING" : "STOPPED"}
          </span>
          <span className="text-sm text-text-muted">
            cycle {cycle} of session
          </span>
        </div>

        {/* Right: Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={onStart}
            disabled={running}
            className={cn(
              "inline-flex min-h-[44px] items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
              running
                ? "cursor-not-allowed border-border-default bg-bg-2 text-text-muted"
                : "border-success bg-success/10 text-success hover:bg-success/20"
            )}
          >
            <span>▶</span>
            <span>Start</span>
          </button>
          <button
            onClick={onStop}
            disabled={!running}
            className={cn(
              "inline-flex min-h-[44px] items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
              !running
                ? "cursor-not-allowed border-border-default bg-bg-2 text-text-muted"
                : "border-border-default bg-bg-2 text-text-primary hover:bg-bg-3"
            )}
          >
            <span>■</span>
            <span>Stop</span>
          </button>
        </div>
      </div>
    </div>
  );
}
