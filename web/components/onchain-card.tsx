"use client";

import { cn } from "@/lib/utils";
import { IndicatorTile } from "./indicator-tile";

type CoinStatus = "live" | "cached";

interface OnChainIndicator {
  label: string;
  value: string;
  subtext: string;
  variant?: "default" | "success" | "danger";
}

interface OnChainCardProps {
  ticker: string;
  status: CoinStatus;
  statusLabel: string;
  indicators: OnChainIndicator[];
  onTickerClick?: () => void;
}

export function OnChainCard({
  ticker,
  status,
  statusLabel,
  indicators,
  onTickerClick,
}: OnChainCardProps) {
  return (
    <div className="min-w-0 max-w-full overflow-hidden rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Card header */}
      {/* AUDIT-2026-05-06 (post-launch dropdown fix): drop the ▾ + button
          wrapper when no onTickerClick handler is wired. The page passes
          BTC/ETH/XRP as fixed tickers — there's no swap UI yet. */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-1.5 border-b border-border-default pb-3">
        {typeof onTickerClick === "function" ? (
          <button
            onClick={onTickerClick}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-md border border-transparent px-2 py-1 font-mono text-lg font-semibold transition-all hover:border-border-default hover:bg-bg-2"
          >
            {ticker}
            <span className="text-[11px] font-medium text-text-muted">▾</span>
          </button>
        ) : (
          <span className="inline-flex min-h-[44px] items-center gap-1.5 px-2 py-1 font-mono text-lg font-semibold">
            {ticker}
          </span>
        )}
        <div className="inline-flex items-center gap-1.5 text-[11px] text-text-muted">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              status === "live" ? "bg-success" : "bg-warning"
            )}
          />
          {statusLabel}
        </div>
      </div>

      {/* Indicator grid - 2 columns */}
      <div className="grid grid-cols-2 gap-3">
        {indicators.map((ind) => (
          <IndicatorTile
            key={ind.label}
            label={ind.label}
            value={ind.value}
            subtext={ind.subtext}
            variant={ind.variant}
          />
        ))}
      </div>
    </div>
  );
}
