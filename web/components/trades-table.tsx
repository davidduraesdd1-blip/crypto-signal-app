import { cn } from "@/lib/utils";

export type TradeSide = "buy" | "sell";

export interface Trade {
  date: string;
  side: TradeSide;
  reason: string;
  returnPct: string;
  duration: string;
}

interface TradesTableProps {
  trades: Trade[];
  title?: string;
  count?: string;
}

export function TradesTable({
  trades,
  title = "Recent trades - signal-driven",
  count,
}: TradesTableProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-1 p-4">
      <div className="mb-2.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          {title}
        </span>
        {count && <span className="text-xs text-text-muted">{count}</span>}
      </div>
      <div className="text-[12.5px]">
        {/* Header */}
        <div className="grid grid-cols-[70px_50px_1fr_70px] gap-2 border-b border-border px-1 py-2 text-[10.5px] font-medium uppercase tracking-wider text-text-muted md:grid-cols-[100px_60px_1fr_90px_80px]">
          <span>Date</span>
          <span>Side</span>
          <span>Reason</span>
          <span className="text-right">Return</span>
          <span className="hidden text-right md:block">Duration</span>
        </div>
        {/* Rows */}
        {trades.map((t, i) => (
          <div
            key={i}
            className={cn(
              "grid grid-cols-[70px_50px_1fr_70px] gap-2 px-1 py-2 md:grid-cols-[100px_60px_1fr_90px_80px]",
              i < trades.length - 1 && "border-b border-border"
            )}
          >
            <span className="font-mono text-text-muted">{t.date}</span>
            <span
              className={cn(
                "inline-flex items-center gap-1 font-semibold",
                t.side === "buy" ? "text-success" : "text-danger"
              )}
            >
              <span>{t.side === "buy" ? "▲" : "▼"}</span>
              <span>{t.side === "buy" ? "BUY" : "SELL"}</span>
            </span>
            <span className="min-w-0 truncate text-text-secondary">
              {t.reason}
            </span>
            <span
              className={cn(
                "text-right font-mono",
                t.returnPct.startsWith("+") ? "text-success" : "text-danger"
              )}
            >
              {t.returnPct}
            </span>
            <span className="hidden text-right font-mono text-[11.5px] text-text-muted md:block">
              {t.duration === "open" ? (
                <span className="inline-flex items-center gap-1 rounded bg-warning/10 px-1.5 py-0.5 text-warning">
                  <span>◆</span>
                  <span>open</span>
                </span>
              ) : (
                t.duration
              )}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
