import { cn } from "@/lib/utils";

type Sentiment = "bull" | "bear" | "neutral";

interface MacroIndicator {
  name: string;
  value: string;
  change: string;
  changeDirection: "up" | "down";
  sentiment: Sentiment;
  sentimentLabel: string;
}

interface MacroOverlayProps {
  regime: string;
  confidence: number;
  indicators: MacroIndicator[];
}

const sentimentDot: Record<Sentiment, string> = {
  bull: "bg-semantic-success",
  bear: "bg-semantic-danger",
  neutral: "bg-semantic-warning",
};

export function MacroOverlay({ regime, confidence, indicators }: MacroOverlayProps) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Header */}
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Macro regime · overlay
        </span>
        <span className="font-semibold text-accent-brand">
          {regime} · {confidence}%
        </span>
      </div>

      {/* Indicator rows */}
      <div className="mt-2">
        {indicators.map((ind, i) => (
          <div
            key={i}
            className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] items-center gap-1.5 border-b border-border-default py-3 text-[13px] last:border-b-0 md:grid-cols-[1.2fr_1fr_1fr_1fr] md:gap-3"
          >
            <span className="truncate font-medium">{ind.name}</span>
            <span className="truncate font-mono">{ind.value}</span>
            <span
              className={cn(
                "truncate font-mono text-xs",
                ind.changeDirection === "up" ? "text-semantic-success" : "text-semantic-danger"
              )}
            >
              {ind.changeDirection === "up" ? "+" : ""}
              {ind.change}
            </span>
            <span className="hidden items-center gap-1.5 text-[11.5px] text-text-muted md:inline-flex">
              <span className={cn("h-1.5 w-1.5 rounded-full", sentimentDot[ind.sentiment])} />
              {ind.sentimentLabel}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
