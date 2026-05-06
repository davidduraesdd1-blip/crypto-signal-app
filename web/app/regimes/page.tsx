"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { RegimeCard, type RegimeState } from "@/components/regime-card";
import { RegimeTimeline, type TimelineState } from "@/components/regime-timeline";
import { MacroOverlay } from "@/components/macro-overlay";
import { RegimeWeights } from "@/components/regime-weights";
import { Button } from "@/components/ui/button";
import { BeginnerHint } from "@/components/beginner-hint";
import { useRegimes } from "@/hooks/use-regimes";

// AUDIT-2026-05-03 (D4b): regime cards wired to GET /regimes/. The
// timeline + MacroOverlay + RegimeWeights stay as v0 mock until the
// downstream endpoints exist (regime_history with date strings,
// consolidated /macro endpoint). Each is decorative + visually
// anchors the page.

/** Map engine regime label → v0's RegimeState union */
function toRegimeState(label: string | null | undefined): RegimeState {
  if (!label) return "bear";
  const l = label.toLowerCase();
  if (l.includes("bull")) return "bull";
  if (l.includes("bear")) return "bear";
  if (l.includes("trans")) return "transition";
  if (l.includes("accum")) return "accumulation";
  if (l.includes("distrib")) return "distribution";
  if (l.includes("rang")) return "bear";  // "ranging" maps to neutral; v0 lacks that, fold into bear
  return "bear";
}

function pairToTicker(pair: string): string {
  return pair.split("/")[0] ?? pair;
}

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
  const regimesQuery = useRegimes();

  // Map /regimes/ rows → RegimeCard props. `since` and `durationDays`
  // aren't in the API response; show "—" placeholders until
  // /regimes/{pair}/history wiring lands in a follow-up commit.
  const regimeStates = (() => {
    const rows = regimesQuery.data?.results ?? [];
    if (rows.length === 0) return [];
    return rows.slice(0, 8).map((row) => ({
      ticker: pairToTicker(row.pair),
      state: toRegimeState(row.regime),
      confidence: Math.round(row.confidence ?? 0),
      since: "—",
      durationDays: 0,
    }));
  })();

  const totalCount = regimesQuery.data?.count ?? 0;

  return (
    <AppShell crumbs="Markets" currentPage="Regimes">
      <PageHeader
        title="Regimes"
        subtitle="HMM-inferred market regime per asset + macro overlay. Regime-specific signal weights auto-adjust."
      />

      {/* AUDIT-2026-05-06 (W2 Tier 6 F-LEVEL-1): Beginner gloss */}
      <BeginnerHint title="What is a market regime?">
        Markets behave differently in different conditions:
        <strong className="text-text-primary"> trending </strong>
        (sustained direction up or down),
        <strong className="text-text-primary"> ranging </strong>
        (sideways), or
        <strong className="text-text-primary"> risk-off </strong>
        (defensive, cash-heavy). The model figures out which regime
        each coin is in right now, and tunes its signal weights
        accordingly. A &ldquo;Buy&rdquo; in a Trending regime means
        something different than the same Buy in a Ranging regime.
      </BeginnerHint>

      {/* Section header */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Regime states · showing {regimeStates.length} of {totalCount} pairs · click any to drill in
        </span>
        <Button variant="outline" size="sm" className="h-8 text-xs">
          More <span className="ml-1 opacity-60">+{Math.max(0, totalCount - regimeStates.length)}</span>
        </Button>
      </div>

      {/* Regime cards grid */}
      {regimeStates.length === 0 ? (
        <div className="mb-5 rounded-lg border border-dashed border-border-default p-8 text-center text-sm text-muted-foreground">
          {regimesQuery.isLoading
            ? "Loading regime states…"
            : regimesQuery.isError
              ? "Couldn't load regime states — try refreshing in 30 seconds."
              : "Run a scan to populate regime states (no scan results yet)."}
        </div>
      ) : (
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
      )}

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
