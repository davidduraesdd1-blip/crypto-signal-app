import { cn } from "@/lib/utils";

type FlowDirection = "inflow" | "outflow";

interface WhaleEvent {
  time: string;
  coin: string;
  direction: FlowDirection;
  notes: string;
  amountUSD: string;
}

interface WhaleActivityProps {
  events: WhaleEvent[];
}

export function WhaleActivity({ events }: WhaleActivityProps) {
  return (
    <div className="min-w-0 max-w-full overflow-hidden rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Header */}
      <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Whale activity · last 24h
        </div>
        <div className="text-xs text-text-muted">
          ≥ $10M USD equivalent · live stream
        </div>
      </div>

      {/* Table */}
      <div className="min-w-0 overflow-x-auto">
        {/* Header row - hidden on mobile */}
        <div className="hidden border-b border-border-default pb-2 text-[10.5px] font-medium uppercase tracking-wider text-text-muted md:grid md:grid-cols-[90px_60px_110px_minmax(0,1fr)_130px] md:gap-3">
          <span>Time UTC</span>
          <span>Coin</span>
          <span>Direction</span>
          <span>Notes</span>
          <span className="text-right">Amount (USD)</span>
        </div>

        {/* Mobile header */}
        <div className="grid grid-cols-[70px_minmax(0,1fr)_90px] gap-3 border-b border-border-default pb-2 text-[10.5px] font-medium uppercase tracking-wider text-text-muted md:hidden">
          <span>Time</span>
          <span>Notes</span>
          <span className="text-right">Amount</span>
        </div>

        {/* Rows */}
        {events.map((event, idx) => (
          <div
            key={idx}
            className={cn(
              "items-center border-b border-border-default py-2.5 text-[13px]",
              idx === events.length - 1 && "border-b-0",
              // Desktop layout
              "hidden md:grid md:grid-cols-[90px_60px_110px_minmax(0,1fr)_130px] md:gap-3",
            )}
          >
            <span className="font-mono text-xs text-text-muted">{event.time}</span>
            <span className="font-mono font-semibold">{event.coin}</span>
            <span
              className={cn(
                "inline-flex items-center gap-1 text-xs font-medium",
                event.direction === "inflow" ? "text-danger" : "text-success"
              )}
            >
              {event.direction === "inflow" ? "▲" : "▼"}{" "}
              {event.direction === "inflow" ? "inflow" : "outflow"}
            </span>
            <span className="min-w-0 truncate text-text-secondary">{event.notes}</span>
            <span
              className={cn(
                "text-right font-mono font-semibold",
                event.direction === "inflow" ? "text-danger" : "text-success"
              )}
            >
              {event.amountUSD}
            </span>
          </div>
        ))}

        {/* Mobile rows */}
        {events.map((event, idx) => (
          <div
            key={`mobile-${idx}`}
            className={cn(
              "grid grid-cols-[70px_minmax(0,1fr)_90px] items-center gap-3 border-b border-border-default py-2.5 text-[13px] md:hidden",
              idx === events.length - 1 && "border-b-0"
            )}
          >
            <span className="font-mono text-xs text-text-muted">{event.time}</span>
            <span className="min-w-0 truncate text-text-secondary">{event.notes}</span>
            <span
              className={cn(
                "text-right font-mono text-sm font-semibold",
                event.direction === "inflow" ? "text-danger" : "text-success"
              )}
            >
              {event.amountUSD}
            </span>
          </div>
        ))}
      </div>

      {/* Footnote */}
      <div className="mt-3.5 border-t border-border-default pt-3 text-[11.5px] leading-relaxed text-text-muted">
        <span className="font-medium text-danger">▲ inflow to exchange</span> = potential sell pressure.{" "}
        <span className="font-medium text-success">▼ outflow to cold/staking</span> = supply tightening.
        Direction is paired with shape (▲/▼) so the signal is readable for color-blind users.
      </div>
    </div>
  );
}
