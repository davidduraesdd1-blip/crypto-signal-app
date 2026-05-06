import { cn } from "@/lib/utils";

interface WatchlistItem {
  ticker: string;
  price: string;
  change: string;
  changeDirection: "up" | "down";
  sparklinePoints: string;
}

interface WatchlistProps {
  items: WatchlistItem[];
  refreshedAgo?: string;
}

export function Watchlist({ items, refreshedAgo = "2m ago" }: WatchlistProps) {
  return (
    <div className="min-w-0 max-w-full rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Header */}
      {/* AUDIT-2026-05-06 (post-launch dropdown fix): "Customize ▾" was a
          decorative button with no handler — there's no watchlist-edit UI
          yet. Drop it; bring it back when the customize panel ships. */}
      <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Watchlist · top-cap
        </div>
        <span className="text-[11.5px] text-text-muted">
          scan refreshed {refreshedAgo}
        </span>
      </div>

      {/* Rows */}
      <div className="flex flex-col">
        {items.map((item, index) => (
          <div
            key={item.ticker}
            className={cn(
              "grid min-w-0 grid-cols-[1.2fr_1fr_1fr_90px] items-center gap-3 py-2.5 px-1 text-[13px]",
              index < items.length - 1 && "border-b border-border-default"
            )}
          >
            <div className="min-w-0 truncate font-semibold">{item.ticker}</div>
            <div className="min-w-0 truncate font-mono text-text-secondary">
              {item.price}
            </div>
            <div
              className={cn(
                "min-w-0 truncate font-mono",
                item.changeDirection === "up" ? "text-success" : "text-danger"
              )}
            >
              {item.changeDirection === "up" ? "+" : ""}{item.change}
            </div>
            <svg
              className="h-[22px] w-full"
              viewBox="0 0 80 22"
              preserveAspectRatio="none"
            >
              <polyline
                fill="none"
                stroke={item.changeDirection === "up" ? "#22c55e" : "#ef4444"}
                strokeWidth="1.5"
                points={item.sparklinePoints}
              />
            </svg>
          </div>
        ))}
      </div>
    </div>
  );
}
