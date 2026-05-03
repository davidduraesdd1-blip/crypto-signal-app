"use client";

import { cn } from "@/lib/utils";

interface AlertTypeCardProps {
  name: string;
  description: string;
  enabled: boolean;
  onToggle?: () => void;
}

export function AlertTypeCard({
  name,
  description,
  enabled,
  onToggle,
}: AlertTypeCardProps) {
  return (
    <div
      onClick={onToggle}
      className={cn(
        "flex min-h-[44px] cursor-pointer items-start gap-3 rounded-lg border bg-bg-2 p-3.5 transition-all",
        enabled
          ? "border-accent-brand bg-accent-brand/5"
          : "border-border hover:border-border-strong"
      )}
    >
      <div
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
    </div>
  );
}
