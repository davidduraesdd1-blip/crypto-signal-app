import { cn } from "@/lib/utils";

interface KpiItem {
  label: string;
  value: string;
  delta?: string;
  deltaType?: "up" | "down" | "neutral";
  valueColor?: "success" | "danger" | "default";
}

interface BacktestCardProps {
  title?: string;
  subtitle?: string;
  kpis: KpiItem[];
}

// AUDIT-2026-05-06 (post-launch): subtitle no longer falls back to a
// hardcoded "BTC basket · 5.2 Sharpe" — the parent page passes a live
// summary string derived from /backtest/summary, or empty when the
// backtest_trades table is empty (engine hasn't run a backtest yet).
export function BacktestCard({
  title = "Composite backtest · last 90d",
  subtitle = "",
  kpis,
}: BacktestCardProps) {
  return (
    <div className="min-w-0 max-w-full rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Header */}
      <div className="mb-2.5 flex items-baseline justify-between">
        <div className="text-xs font-medium uppercase tracking-wider text-text-muted">
          {title}
        </div>
        <div className="text-[11.5px] text-text-muted">{subtitle}</div>
      </div>

      {/* KPIs grid */}
      <div className="mt-2 grid grid-cols-2 gap-3">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="flex flex-col gap-1">
            <div className="text-[11px] uppercase tracking-wide text-text-muted">
              {kpi.label}
            </div>
            <div
              className={cn(
                "font-mono text-[22px] font-semibold leading-tight",
                kpi.valueColor === "success" && "text-success",
                kpi.valueColor === "danger" && "text-danger"
              )}
            >
              {kpi.value}
            </div>
            {kpi.delta && (
              <div
                className={cn(
                  "font-mono text-xs",
                  kpi.deltaType === "up" && "text-success",
                  kpi.deltaType === "down" && "text-danger",
                  kpi.deltaType === "neutral" && "text-text-muted"
                )}
              >
                {kpi.delta}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
