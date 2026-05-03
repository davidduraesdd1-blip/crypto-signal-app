"use client";

import { cn } from "@/lib/utils";

interface ControlButtonProps {
  label: string;
  value: string;
  onClick?: () => void;
  className?: string;
}

export function ControlButton({
  label,
  value,
  onClick,
  className,
}: ControlButtonProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5 text-[13px] transition-all",
        "hover:border-border-strong hover:bg-bg-2",
        className
      )}
    >
      <span className="text-[11px] uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span className="max-w-[140px] truncate font-mono font-medium">
        {value}
      </span>
      <span className="text-[11px] text-text-muted group-hover:text-text-primary">
        ▾
      </span>
    </button>
  );
}
