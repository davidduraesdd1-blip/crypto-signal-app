"use client";

import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface CoinPickerProps {
  coins: string[];
  activeIndex: number;
  extraCount?: number;
  /** Full list of coins beyond the visible top-N. When provided, "More"
   * becomes a real dropdown that lets the user pick any of them.
   * AUDIT-2026-05-06 (post-launch v4): Signals page used to render
   * "More ▾ +N" with no behavior; now it expands to a dropdown of the
   * remaining coins. */
  extraCoins?: string[];
  /** Called with the selected coin name when picked from the More dropdown. */
  onPickExtra?: (coin: string) => void;
  onSelect?: (index: number) => void;
  /** Legacy: simple click handler. Ignored when `extraCoins` is provided. */
  onMore?: () => void;
}

export function CoinPicker({
  coins,
  activeIndex,
  extraCount = 0,
  extraCoins,
  onPickExtra,
  onSelect,
  onMore,
}: CoinPickerProps) {
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
          {/* AUDIT-2026-05-06 (post-launch v4): "More" is now a real
              dropdown when extraCoins[] is provided — clicking shows the
              full universe and selecting one calls onPickExtra. */}
          {Array.isArray(extraCoins) && extraCoins.length > 0 ? (
            <DropdownMenu>
              <DropdownMenuTrigger
                className={cn(
                  "min-h-[44px] rounded-md border border-border-default px-2.5 py-1 text-[12.5px] font-medium text-text-secondary outline-none transition-colors md:min-h-0 md:py-1.5",
                  "hover:border-border-strong hover:bg-bg-2 hover:text-text-primary",
                  "focus-visible:ring-2 focus-visible:ring-accent-brand",
                )}
              >
                More ▾ <span className="ml-0.5 text-[11px] opacity-60">+{extraCount}</span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="max-h-[420px] min-w-[160px] overflow-y-auto">
                {extraCoins.map((c) => (
                  <DropdownMenuItem
                    key={c}
                    onSelect={() => onPickExtra?.(c)}
                    className="cursor-pointer font-mono text-[13px]"
                  >
                    {c}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : typeof onMore === "function" ? (
            <button
              onClick={onMore}
              className={cn(
                "min-h-[44px] rounded-md border border-border-default px-2.5 py-1 text-[12.5px] font-medium text-text-secondary transition-colors md:min-h-0 md:py-1.5",
                "hover:border-border-strong hover:bg-bg-2 hover:text-text-primary"
              )}
            >
              More ▾ <span className="ml-0.5 text-[11px] opacity-60">+{extraCount}</span>
            </button>
          ) : (
            <span className="min-h-[44px] rounded-md border border-border-default px-2.5 py-1 text-[12.5px] font-medium text-text-muted md:min-h-0 md:py-1.5">
              +{extraCount} more
            </span>
          )}
        </>
      )}
    </div>
  );
}
