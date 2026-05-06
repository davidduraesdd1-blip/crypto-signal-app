import { cn } from "@/lib/utils";

// AUDIT-2026-05-06 (P1-D): canonical SignalType lives in lib/signal-types.
export type { SignalType } from "@/lib/signal-types";
import type { SignalType } from "@/lib/signal-types";

export interface HistoryEntry {
  timestamp: string;
  signal: SignalType;
  note: string;
  /** Already-formatted signed pct string ("+ 12.6%" / "− 6.2%" / "—") */
  returnPct: string;
}

interface SignalHistoryProps {
  /** Real entries from the daily_signals table (after transition-dedup
   *  in the parent). Empty array → render the honest empty state. */
  entries: HistoryEntry[];
  /** Display ticker (e.g. "BTC", "ETH") for the heading. */
  ticker?: string;
  /** Loading state (waiting for /signals/history to resolve). */
  isLoading?: boolean;
  /** Error state (request failed). */
  error?: { message: string } | null;
}

const signalConfig: Record<SignalType, { icon: string; label: string; className: string }> = {
  buy: { icon: "▲", label: "BUY", className: "text-success" },
  hold: { icon: "■", label: "HOLD", className: "text-warning" },
  sell: { icon: "▼", label: "SELL", className: "text-danger" },
};

export function SignalHistory({ entries, ticker = "—", isLoading, error }: SignalHistoryProps) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-4">
      <div className="mb-2.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Recent signal history · {ticker}
        </span>
        <span className="text-xs text-text-muted">
          {entries.length > 0
            ? `last ${entries.length} state transitions`
            : "transitions only — consecutive same-direction scans collapse"}
        </span>
      </div>

      {/* P0-7 honest empty / loading / error states. v0 mock pre-fix
          showed Apr/Mar/Feb 2026 demo dates regardless of API state. */}
      {isLoading && (
        <div className="py-6 text-center text-[12.5px] text-text-muted">
          Loading…
        </div>
      )}
      {!isLoading && error && (
        <div className="py-6 text-center text-[12.5px] text-text-muted">
          History unavailable — {error.message}
        </div>
      )}
      {!isLoading && !error && entries.length === 0 && (
        <div className="py-6 text-center text-[12.5px] text-text-muted">
          No signal transitions logged yet for {ticker}. The first transition
          appears after the next scheduled scan flips direction.
        </div>
      )}

      <div className="flex flex-col">
        {entries.map((entry, index) => {
          const config = signalConfig[entry.signal];
          const isPositive = entry.returnPct.startsWith("+");
          const isUnknown = entry.returnPct === "—";

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
                  isUnknown
                    ? "text-text-muted"
                    : isPositive
                      ? "text-success"
                      : "text-danger"
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
