import { cn } from "@/lib/utils";

interface Metric {
  label: string;
  value: string;
  subtext: string;
  highlight?: "success" | "danger" | "warning";
}

interface AgentMetricStripProps {
  metrics: Metric[];
}

export function AgentMetricStrip({ metrics }: AgentMetricStripProps) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {metrics.map((m, i) => (
        <div
          key={i}
          className="rounded-xl border border-border-default bg-bg-1 p-4"
        >
          <div className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
            {m.label}
          </div>
          <div
            className={cn(
              "mt-1 font-mono text-lg font-semibold",
              m.highlight === "success" && "text-success",
              m.highlight === "danger" && "text-danger",
              m.highlight === "warning" && "text-warning",
              !m.highlight && "text-text-primary"
            )}
          >
            {m.value}
          </div>
          <div className="mt-0.5 text-[11px] text-text-muted">{m.subtext}</div>
        </div>
      ))}
    </div>
  );
}
