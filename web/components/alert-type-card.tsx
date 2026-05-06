"use client";

import { cn } from "@/lib/utils";

interface AlertTypeCardProps {
  name: string;
  description: string;
  enabled: boolean;
  onToggle?: () => void;
}

// AUDIT-2026-05-06 (W2 Tier 1 + Tier 6 P0): converted from
// `<div onClick={...}>` to a real `<button>` with role/keyboard
// support. Pre-fix this card was the same a11y regression flagged
// in regime-card.tsx during the 2026-05-04 wave — clickable but
// not keyboard-accessible, no ARIA pressed state, no focus ring.
export function AlertTypeCard({
  name,
  description,
  enabled,
  onToggle,
}: AlertTypeCardProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={`${enabled ? "Disable" : "Enable"} ${name} alert`}
      onClick={onToggle}
      className={cn(
        "flex min-h-[44px] w-full cursor-pointer items-start gap-3 rounded-lg border bg-bg-2 p-3.5 text-left transition-all",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg-1",
        enabled
          ? "border-accent-brand bg-accent-brand/5"
          : "border-border hover:border-border-strong"
      )}
    >
      <div
        aria-hidden="true"
        className={cn(
          "mt-0.5 grid h-[18px] w-[18px] flex-shrink-0 place-items-center rounded-[5px] border-[1.5px] text-[12px] font-bold",
          enabled
            ? "border-accent-brand bg-accent-brand text-accent-ink"
            : "border-border-strong bg-bg-1"
        )}
      >
        {enabled && "✓"}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium">{name}</div>
        <div className="mt-1 text-[11.5px] leading-[1.45] text-text-muted">
          {description}
        </div>
      </div>
    </button>
  );
}
