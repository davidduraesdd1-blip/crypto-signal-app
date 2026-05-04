"use client";

import { cn } from "@/lib/utils";

interface SegmentedControlProps {
  options: { label: string; value: string; href?: string }[];
  value: string;
  onChange?: (value: string) => void;
  size?: "default" | "sm";
  className?: string;
  ariaLabel?: string;
}

// AUDIT-2026-05-04 (overnight a11y): wrapping div now exposes role=radiogroup
// with an aria-label, and each button is role=radio + aria-checked. Without
// these, screen readers announce three plain buttons with no grouping
// context. Used on Settings sub-tabs and several pages — high-leverage fix.
export function SegmentedControl({
  options,
  value,
  onChange,
  size = "default",
  className,
  ariaLabel,
}: SegmentedControlProps) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel ?? "Segmented control"}
      className={cn(
        "inline-flex gap-0 rounded-lg border border-border bg-bg-1 p-[3px]",
        size === "sm" && "p-[2px]",
        className
      )}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={value === opt.value}
          onClick={() => onChange?.(opt.value)}
          className={cn(
            "min-h-[44px] cursor-pointer rounded-[5px] px-[18px] py-2 text-[13px] font-medium text-text-muted transition-all",
            size === "sm" && "min-h-[36px] px-[14px] py-1.5 text-[12.5px]",
            "hover:text-text-primary",
            value === opt.value &&
              "bg-accent-brand/10 font-semibold text-text-primary"
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
