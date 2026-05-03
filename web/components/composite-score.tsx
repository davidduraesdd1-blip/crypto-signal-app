import { cn } from "@/lib/utils";

interface Layer {
  name: string;
  score: number;
  variant?: "high" | "mid" | "low";
}

interface CompositeScoreProps {
  score: number;
  layers: Layer[];
  weightsNote: string;
}

export function CompositeScore({ score, layers, weightsNote }: CompositeScoreProps) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-border-default bg-bg-1 p-4">
      <div className="mb-2.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Composite score · 0–100
        </span>
        <span className="font-mono text-base font-semibold text-accent-brand">
          {score.toFixed(1)}
        </span>
      </div>

      <div className="mt-2 flex flex-1 flex-col gap-3.5">
        {layers.map((layer) => {
          const barVariant = layer.score >= 75 ? "high" : layer.score >= 60 ? "mid" : "low";
          
          return (
            <div key={layer.name} className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between">
                <span className="text-[13px] font-medium text-text-primary">{layer.name}</span>
                <span className="font-mono text-base font-semibold">{layer.score}</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-sm bg-bg-2">
                <div
                  className={cn(
                    "h-full rounded-sm transition-all",
                    barVariant === "high" && "bg-accent-brand",
                    barVariant === "mid" && "bg-warning",
                    barVariant === "low" && "bg-danger"
                  )}
                  style={{ width: `${layer.score}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-4 border-t border-border-default pt-3.5 text-xs text-text-muted">
        {weightsNote}
      </div>
    </div>
  );
}
