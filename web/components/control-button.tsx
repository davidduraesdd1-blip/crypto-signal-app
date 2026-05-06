"use client";

import { cn } from "@/lib/utils";

interface ControlButtonProps {
  label: string;
  value: string;
  onClick?: () => void;
  className?: string;
}

// AUDIT-2026-05-06 (post-launch dropdown fix): chevron + cursor-pointer +
// hover styling now only render when an onClick handler is actually
// provided. Pre-fix every ControlButton (Backtester knobs Universe,
// Period, Initial, Rebalance, Costs etc.) showed a ▾ chevron and a
// hover state that suggested a dropdown menu — clicks did nothing.
// Honest UI: read-only labels look read-only.
export function ControlButton({
  label,
  value,
  onClick,
  className,
}: ControlButtonProps) {
  const interactive = typeof onClick === "function";
  const Tag = interactive ? "button" : "div";
  return (
    <Tag
      onClick={interactive ? onClick : undefined}
      className={cn(
        "inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5 text-[13px]",
        interactive && "group cursor-pointer transition-all hover:border-border-strong hover:bg-bg-2",
        className
      )}
      {...(!interactive && { "aria-readonly": "true" as const })}
    >
      <span className="text-[11px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span className="max-w-[140px] truncate font-mono font-medium">
        {value}
      </span>
      {interactive && (
        <span className="text-[11px] text-text-muted group-hover:text-text-primary">
          ▾
        </span>
      )}
    </Tag>
  );
}
