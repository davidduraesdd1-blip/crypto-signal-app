"use client";

import { cn } from "@/lib/utils";

interface ToggleSwitchProps {
  enabled: boolean;
  onToggle?: () => void;
  label: string;
  sublabel?: string;
}

export function ToggleSwitch({
  enabled,
  onToggle,
  label,
  sublabel,
}: ToggleSwitchProps) {
  return (
    <div className="flex items-center gap-3 border-b border-border py-3">
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-medium">{label}</div>
        {sublabel && (
          <div className="mt-0.5 text-[11.5px] text-text-muted">{sublabel}</div>
        )}
      </div>
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          "relative inline-flex h-6 w-[42px] cursor-pointer items-center rounded-full transition-colors",
          enabled ? "bg-accent-brand" : "bg-bg-3"
        )}
      >
        <span
          className={cn(
            "absolute h-[18px] w-[18px] rounded-full bg-white transition-all",
            enabled ? "left-[21px]" : "left-[3px]"
          )}
        />
      </button>
    </div>
  );
}
