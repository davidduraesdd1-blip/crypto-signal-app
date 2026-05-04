"use client";

import { cn } from "@/lib/utils";

interface CoinPickerProps {
  coins: string[];
  activeIndex: number;
  extraCount?: number;
  onSelect?: (index: number) => void;
  onMore?: () => void;
}

export function CoinPicker({ coins, activeIndex, extraCount = 0, onSelect, onMore }: CoinPickerProps) {
  return (
    <div className="inline-flex flex-wrap items-center gap-1.5 rounded-[10px] border border-border-default bg-bg-1 p-1">
      {coins.map((coin, index) => (
        <button
          key={coin}
          onClick={() => onSelect?.(index)}
          className={cn(
            "min-h-[44px] rounded-md px-3.5 py-1.5 font-mono text-[13px] font-semibold text-text-muted transition-colors md:min-h-0 md:py-1.5",
            "hover:bg-bg-2 hover:text-text-primary",
            activeIndex === index && "bg-accent-soft text-text-primary"
          )}
        >
          {coin}
        </button>
      ))}
      
      {extraCount > 0 && (
        <>
          <span className="mx-1 h-[18px] w-px bg-border-default" />
          <button
            onClick={onMore}
            className={cn(
              "min-h-[44px] rounded-md border border-border-default px-2.5 py-1 text-[12.5px] font-medium text-text-secondary transition-colors md:min-h-0 md:py-1.5",
              "hover:border-border-strong hover:bg-bg-2 hover:text-text-primary"
            )}
          >
            More ▾ <span className="ml-0.5 text-[11px] opacity-60">+{extraCount}</span>
          </button>
        </>
      )}
    </div>
  );
}
