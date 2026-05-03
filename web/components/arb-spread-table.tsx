import { cn } from "@/lib/utils";

export type ArbSignal = "opportunity" | "marginal" | "none";

export interface ArbSpread {
  pair: string;
  buyOn: string;
  sellOn: string;
  buyPrice: string;
  sellPrice: string;
  netSpread: string;
  signal: ArbSignal;
}

interface ArbSpreadTableProps {
  spreads: ArbSpread[];
}

const signalConfig: Record<
  ArbSignal,
  { label: string; shape: string; colorClass: string; bgClass: string }
> = {
  opportunity: {
    label: "Opportunity",
    shape: "▲",
    colorClass: "text-success",
    bgClass: "bg-success/15",
  },
  marginal: {
    label: "Marginal",
    shape: "■",
    colorClass: "text-warning",
    bgClass: "bg-warning/15",
  },
  none: {
    label: "No arb",
    shape: "—",
    colorClass: "text-text-muted",
    bgClass: "bg-bg-2",
  },
};

export function ArbSpreadTable({ spreads }: ArbSpreadTableProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-1 p-4">
      <div className="text-[12.5px]">
        {/* Header */}
        <div className="grid grid-cols-[70px_1fr_80px_70px] gap-3 border-b border-border px-1 py-2.5 text-[10.5px] font-medium uppercase tracking-wider text-text-muted md:grid-cols-[100px_100px_100px_170px_110px_1fr]">
          <span>Pair</span>
          <span className="hidden md:block">Buy on</span>
          <span className="hidden md:block">Sell on</span>
          <span className="hidden md:block">Buy / Sell</span>
          <span className="text-right">Net spread</span>
          <span>Signal</span>
        </div>
        {/* Rows */}
        {spreads.map((s, i) => {
          const cfg = signalConfig[s.signal];
          return (
            <div
              key={i}
              className={cn(
                "grid grid-cols-[70px_1fr_80px_70px] items-center gap-3 px-1 py-2.5 md:grid-cols-[100px_100px_100px_170px_110px_1fr]",
                i < spreads.length - 1 && "border-b border-border"
              )}
            >
              <span className="font-mono font-semibold">{s.pair}</span>
              <span className="hidden font-mono text-text-secondary md:block">
                {s.buyOn}
              </span>
              <span className="hidden font-mono text-text-secondary md:block">
                {s.sellOn}
              </span>
              <span className="hidden font-mono md:block">
                {s.buyPrice} / {s.sellPrice}
              </span>
              <span
                className={cn(
                  "text-right font-mono font-semibold",
                  s.signal === "opportunity" && "text-success",
                  s.signal === "marginal" && "text-warning",
                  s.signal === "none" && "text-text-muted"
                )}
              >
                + {s.netSpread}
              </span>
              <span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider",
                    cfg.colorClass,
                    cfg.bgClass
                  )}
                >
                  {cfg.shape} {cfg.label}
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
