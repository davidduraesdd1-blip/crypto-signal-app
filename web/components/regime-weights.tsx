"use client";

import { cn } from "@/lib/utils";

interface WeightSet {
  tech: number;
  macro: number;
  sentiment: number;
  onChain: number;
}

export type RegimeType = "bull" | "accumulation" | "distribution" | "bear";

interface RegimeWeightColumn {
  regime: RegimeType;
  label: string;
  weights: WeightSet;
}

interface RegimeWeightsProps {
  columns: RegimeWeightColumn[];
}

const regimeConfig: Record<RegimeType, { shape: string; textColor: string; bgColor: string }> = {
  bull: { shape: "▲", textColor: "text-success", bgColor: "bg-success/10" },
  accumulation: { shape: "●", textColor: "text-teal", bgColor: "bg-teal/10" },
  distribution: { shape: "○", textColor: "text-orange", bgColor: "bg-orange/10" },
  bear: { shape: "▼", textColor: "text-danger", bgColor: "bg-danger/10" },
};

export function RegimeWeights({ columns }: RegimeWeightsProps) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-1 p-4">
      {/* Header */}
      <div className="mb-4 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Signal weights by regime
        </span>
        <span className="text-xs text-text-muted">auto-adjusted by HMM state</span>
      </div>

      {/* Weight columns */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {columns.map((col, i) => {
          const config = regimeConfig[col.regime];
          return (
            <div key={i} className="rounded-lg border border-border-default bg-bg-2 p-3">
              <div
                className={cn(
                  "mb-3 inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wider",
                  config.textColor,
                  config.bgColor
                )}
              >
                <span>{config.shape}</span>
                <span>{col.label}</span>
              </div>
              <div className="space-y-1.5 font-mono text-xs leading-relaxed text-text-secondary">
                <div className="flex justify-between">
                  <span>Tech</span>
                  <span>{(col.weights.tech * 100).toFixed(0)}%</span>
                </div>
                <div className="flex justify-between">
                  <span>Macro</span>
                  <span>{(col.weights.macro * 100).toFixed(0)}%</span>
                </div>
                <div className="flex justify-between">
                  <span>Sentiment</span>
                  <span>{(col.weights.sentiment * 100).toFixed(0)}%</span>
                </div>
                <div className="flex justify-between">
                  <span>On-chain</span>
                  <span>{(col.weights.onChain * 100).toFixed(0)}%</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
