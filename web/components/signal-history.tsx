import { cn } from "@/lib/utils";

export type SignalType = "buy" | "hold" | "sell";

interface HistoryEntry {
  timestamp: string;
  signal: SignalType;
  note: string;
  returnPct: string;
}

interface SignalHistoryProps {
  entries: HistoryEntry[];
}

const signalConfig: Record<SignalType, { icon: string; label: string; className: string }> = {
  buy: { icon: "▲", label: "BUY", className: "text-success" },
  hold: { icon: "■", label: "HOLD", className: "text-warning" },
  sell: { icon: "▼", label: "SELL", className: "text-danger" },
};

export function SignalHistory({ entries }: SignalHistoryProps) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-4">
      <div className="mb-2.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Recent signal history · BTC
        </span>
        <span className="text-xs text-text-muted">
          last {entries.length} state transitions
        </span>
      </div>

      <div className="flex flex-col">
        {entries.map((entry, index) => {
          const config = signalConfig[entry.signal];
          const isPositive = entry.returnPct.startsWith("+");

          return (
            <div
              key={index}
              className={cn(
                "grid grid-cols-[1fr] gap-2 border-b border-border-default py-2.5 text-[12.5px] md:grid-cols-[110px_70px_1fr_90px] md:items-center md:gap-3",
                index === entries.length - 1 && "border-b-0"
              )}
            >
              <span className="font-mono text-text-muted">{entry.timestamp}</span>
              <span className={cn("font-semibold", config.className)}>
                {config.icon} {config.label}
              </span>
              <span className="text-text-secondary">{entry.note}</span>
              <span
                className={cn(
                  "font-mono md:text-right",
                  isPositive ? "text-success" : "text-danger"
                )}
              >
                {entry.returnPct}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
