import { cn } from "@/lib/utils";

export interface FundingCarry {
  pair: string;
  okx8h: string;
  bybit8h: string;
  delta: string;
  strategy: string;
  annualized: string;
}

interface FundingCarryTableProps {
  carries: FundingCarry[];
  footer?: string;
}

function rateClass(rate: string): string {
  if (rate.startsWith("+") || rate.startsWith("−") === false) {
    return rate.includes("−") ? "text-danger" : "text-success";
  }
  return rate.startsWith("−") ? "text-danger" : "text-success";
}

export function FundingCarryTable({ carries, footer }: FundingCarryTableProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-1 p-4">
      <div className="text-[12.5px]">
        {/* Header */}
        <div className="grid grid-cols-[70px_80px_1fr_80px] gap-2.5 border-b border-border px-1 py-2.5 text-[10.5px] font-medium uppercase tracking-wider text-text-muted md:grid-cols-[90px_100px_100px_90px_1fr_110px]">
          <span>Pair</span>
          <span className="hidden text-right md:block">OKX 8h</span>
          <span className="text-right">Bybit 8h</span>
          <span className="hidden text-right md:block">Delta</span>
          <span className="hidden md:block">Strategy</span>
          <span className="text-right">Annualized</span>
        </div>
        {/* Rows */}
        {carries.map((c, i) => {
          const isSkip = c.strategy.toLowerCase().includes("skip");
          return (
            <div
              key={i}
              className={cn(
                "grid grid-cols-[70px_80px_1fr_80px] items-center gap-2.5 px-1 py-2.5 md:grid-cols-[90px_100px_100px_90px_1fr_110px]",
                i < carries.length - 1 && "border-b border-border"
              )}
            >
              <span className="font-mono font-semibold">{c.pair}</span>
              <span
                className={cn(
                  "hidden text-right font-mono md:block",
                  rateClass(c.okx8h)
                )}
              >
                {c.okx8h}
              </span>
              <span className={cn("text-right font-mono", rateClass(c.bybit8h))}>
                {c.bybit8h}
              </span>
              <span
                className={cn(
                  "hidden text-right font-mono md:block",
                  rateClass(c.delta)
                )}
              >
                {c.delta}
              </span>
              <span className="hidden text-[12px] text-text-secondary md:block">
                {c.strategy}
              </span>
              <span
                className={cn(
                  "text-right font-mono font-semibold",
                  isSkip ? "text-text-muted" : "text-accent-brand"
                )}
              >
                {c.annualized}
              </span>
            </div>
          );
        })}
      </div>
      {footer && (
        <div className="mt-3 border-t border-border pt-2.5 text-[11.5px] leading-relaxed text-text-muted">
          {footer}
        </div>
      )}
    </div>
  );
}
