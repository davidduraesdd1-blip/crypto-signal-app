"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { RegimeCard, type RegimeState } from "@/components/regime-card";
import { RegimeTimeline, type TimelineState } from "@/components/regime-timeline";
import { MacroOverlay } from "@/components/macro-overlay";
import { RegimeWeights } from "@/components/regime-weights";
import { Button } from "@/components/ui/button";

// Mock data
const regimeStates: {
  ticker: string;
  state: RegimeState;
  confidence: number;
  since: string;
  durationDays: number;
}[] = [
  { ticker: "BTC", state: "bull", confidence: 82, since: "Apr 12", durationDays: 12 },
  { ticker: "ETH", state: "transition", confidence: 61, since: "Apr 20", durationDays: 4 },
  { ticker: "XRP", state: "accumulation", confidence: 68, since: "Apr 08", durationDays: 16 },
  { ticker: "SOL", state: "distribution", confidence: 74, since: "Apr 16", durationDays: 8 },
  { ticker: "AVAX", state: "bull", confidence: 78, since: "Apr 10", durationDays: 14 },
  { ticker: "LINK", state: "accumulation", confidence: 64, since: "Apr 14", durationDays: 10 },
  { ticker: "NEAR", state: "bear", confidence: 72, since: "Apr 06", durationDays: 18 },
  { ticker: "DOT", state: "transition", confidence: 58, since: "Apr 21", durationDays: 3 },
];

const timelineSegments: { state: TimelineState; widthPercent: number; label: string }[] = [
  { state: "bear", widthPercent: 12, label: "Bear" },
  { state: "transition", widthPercent: 8, label: "Trans" },
  { state: "accumulation", widthPercent: 18, label: "Accum" },
  { state: "bull", widthPercent: 44, label: "Bull" },
  { state: "transition", widthPercent: 6, label: "Trans" },
  { state: "bull", widthPercent: 12, label: "Bull" },
];

const timelineDates = ["Jan 24", "Feb 12", "Mar 02", "Mar 20", "Apr 08", "Apr 23"];

const macroIndicators = [
  {
    name: "BTC Dominance",
    value: "58.9%",
    change: "0.4 ppts · 7d",
    changeDirection: "up" as const,
    sentiment: "bull" as const,
    sentimentLabel: "bullish",
  },
  {
    name: "DXY",
    value: "104.21",
    change: "0.6% · 30d",
    changeDirection: "down" as const,
    sentiment: "bull" as const,
    sentimentLabel: "risk-on",
  },
  {
    name: "VIX",
    value: "14.2",
    change: "8% · 30d",
    changeDirection: "down" as const,
    sentiment: "bull" as const,
    sentimentLabel: "risk-on",
  },
  {
    name: "10Y yield",
    value: "4.18%",
    change: "8bps · 7d",
    changeDirection: "down" as const,
    sentiment: "bull" as const,
    sentimentLabel: "tailwind",
  },
  {
    name: "Fear & Greed",
    value: "72",
    change: "6 · 7d",
    changeDirection: "up" as const,
    sentiment: "neutral" as const,
    sentimentLabel: "greed",
  },
  {
    name: "HY spreads",
    value: "312 bps",
    change: "18 bps · 30d",
    changeDirection: "down" as const,
    sentiment: "bull" as const,
    sentimentLabel: "tightening",
  },
];

const regimeWeightColumns = [
  {
    regime: "bull" as const,
    label: "Bull",
    weights: { tech: 0.3, macro: 0.15, sentiment: 0.2, onChain: 0.35 },
  },
  {
    regime: "accumulation" as const,
    label: "Accumulation",
    weights: { tech: 0.2, macro: 0.15, sentiment: 0.15, onChain: 0.5 },
  },
  {
    regime: "distribution" as const,
    label: "Distribution",
    weights: { tech: 0.35, macro: 0.25, sentiment: 0.25, onChain: 0.15 },
  },
  {
    regime: "bear" as const,
    label: "Bear",
    weights: { tech: 0.4, macro: 0.35, sentiment: 0.15, onChain: 0.1 },
  },
];

export default function RegimesPage() {
  const [selectedTicker, setSelectedTicker] = useState("BTC");

  return (
    <AppShell crumbs="Markets" currentPage="Regimes">
      <PageHeader
        title="Regimes"
        subtitle="HMM-inferred market regime per asset + macro overlay. Regime-specific signal weights auto-adjust."
      />

      {/* Section header */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Regime states · showing 8 of 33 pairs · click any to drill in
        </span>
        <Button variant="outline" size="sm" className="h-8 text-xs">
          More <span className="ml-1 opacity-60">+25</span>
        </Button>
      </div>

      {/* Regime cards grid */}
      <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {regimeStates.map((r) => (
          <RegimeCard
            key={r.ticker}
            ticker={r.ticker}
            state={r.state}
            confidence={r.confidence}
            since={r.since}
            durationDays={r.durationDays}
            selected={selectedTicker === r.ticker}
            onClick={() => setSelectedTicker(r.ticker)}
          />
        ))}
      </div>

      {/* Timeline + Macro overlay - 2 columns */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RegimeTimeline
          ticker={selectedTicker}
          segments={timelineSegments}
          dates={timelineDates}
          description="HMM 4-state model over composite score + on-chain + macro features. State transitions shown on the bar. Current state: Bull since Apr 12, confidence 82%."
        />
        <MacroOverlay regime="Risk-on" confidence={76} indicators={macroIndicators} />
      </div>

      {/* Signal weights by regime */}
      <RegimeWeights columns={regimeWeightColumns} />
    </AppShell>
  );
}
