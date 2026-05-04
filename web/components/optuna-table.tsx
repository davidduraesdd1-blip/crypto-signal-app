import { cn } from "@/lib/utils";

export interface OptunaRun {
  rank: number;
  params: string;
  sharpe: string;
  returnPct: string;
}

interface OptunaTableProps {
  runs: OptunaRun[];
  footer?: string;
}

export function OptunaTable({ runs, footer }: OptunaTableProps) {
  return (
    <div className="rounded-xl border border-border bg-bg-1 p-4">
      <div className="mb-2.5 text-xs font-medium uppercase tracking-wider text-text-muted">
        Optuna studies - top 5 hyperparam sets
      </div>
      <div>
        {runs.map((r, i) => (
          <div
            key={i}
            className={cn(
              "grid grid-cols-[46px_1fr_60px_60px] items-center gap-2 px-1 py-2 text-[12.5px] md:grid-cols-[60px_1fr_90px_70px]",
              i < runs.length - 1 && "border-b border-border"
            )}
          >
            <span className="font-mono text-text-muted">
              #{r.rank}
              {r.rank === 1 && " ★"}
            </span>
            <span className="min-w-0 truncate font-mono text-[11.5px] text-text-secondary md:text-[12px]">
              {r.params}
            </span>
            <span className="text-right font-mono font-semibold text-accent-brand">
              {r.sharpe}
            </span>
            <span className="text-right font-mono text-success">
              {r.returnPct}
            </span>
          </div>
        ))}
      </div>
      {footer && (
        <div className="mt-3.5 border-t border-border pt-3 text-[11.5px] text-text-muted">
          {footer}
        </div>
      )}
    </div>
  );
}
