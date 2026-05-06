"use client";

import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ControlButtonProps {
  label: string;
  value: string;
  /** Click handler. If omitted AND no `options`, the button renders as
   * a non-interactive read-only label (no chevron, no hover state). */
  onClick?: () => void;
  /** When provided, renders as a real dropdown menu. Selecting an
   * option calls `onValueChange(option)`. Adds the ▾ chevron back. */
  options?: string[];
  onValueChange?: (next: string) => void;
  className?: string;
}

// AUDIT-2026-05-06 (post-launch v3): three rendering modes:
//  - options[] provided      → real DropdownMenu (radix-based) with ▾
//  - onClick provided        → simple button + ▾, callback fires on click
//  - neither                 → read-only div, no chevron, no hover
//
// Used on Backtester for Universe / Period / Initial / Rebalance / Costs
// knobs — these now open real dropdown menus that update local state on
// the page (V1: page-level state only; V2 will persist via /backtest/config).
export function ControlButton({
  label,
  value,
  onClick,
  options,
  onValueChange,
  className,
}: ControlButtonProps) {
  const hasMenu = Array.isArray(options) && options.length > 0;
  const interactive = hasMenu || typeof onClick === "function";

  const innerContent = (
    <>
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
    </>
  );

  const baseClasses = cn(
    "inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5 text-[13px]",
    interactive && "group cursor-pointer transition-all hover:border-border-strong hover:bg-bg-2",
    className,
  );

  if (hasMenu) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger className={baseClasses}>
          {innerContent}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[180px]">
          {options!.map((opt) => (
            <DropdownMenuItem
              key={opt}
              onSelect={() => onValueChange?.(opt)}
              className={cn(
                "cursor-pointer font-mono text-[13px]",
                opt === value && "bg-accent-soft text-text-primary",
              )}
            >
              {opt === value ? "✓ " : "  "}{opt}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  if (typeof onClick === "function") {
    return (
      <button onClick={onClick} className={baseClasses}>
        {innerContent}
      </button>
    );
  }

  return (
    <div className={baseClasses} aria-readonly="true">
      {innerContent}
    </div>
  );
}
