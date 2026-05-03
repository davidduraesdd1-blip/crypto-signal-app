"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { CoinPicker } from "@/components/coin-picker";
import { TimeframeStrip, type SignalType } from "@/components/timeframe-strip";
import { SignalHero } from "@/components/signal-hero";
import { PriceChart } from "@/components/price-chart";
import { CompositeScore } from "@/components/composite-score";
import { IndicatorTile, IndicatorGrid } from "@/components/indicator-tile";
import { SignalHistory } from "@/components/signal-history";

// Mock data
const coins = ["BTC", "ETH", "XRP", "SOL", "AVAX"];
const extraCoinsCount = 28;

const timeframes: { label: string; signal: SignalType; score: number }[] = [
  { label: "1m", signal: "hold", score: 52 },
  { label: "5m", signal: "buy", score: 64 },
  { label: "15m", signal: "buy", score: 70 },
  { label: "30m", signal: "buy", score: 73 },
  { label: "1h", signal: "buy", score: 76 },
  { label: "4h", signal: "buy", score: 80 },
  { label: "1d", signal: "buy", score: 78 },
  { label: "1w", signal: "buy", score: 84 },
];

const heroData = {
  ticker: "BTC / USD",
  name: "Bitcoin",
  price: "104,280",
  change24h: "+ 2.14%",
  change30d: "+ 18.4%",
  change1y: "+ 134.8%",
  signal: "buy" as SignalType,
  signalStrength: "strong",
  timeframe: "1d",
  regime: "bull",
  confidence: "82%",
  regimeAge: "14d",
};

const compositeData = {
  score: 78.4,
  layers: [
    { name: "Layer 1 · Technical", score: 82 },
    { name: "Layer 2 · Macro", score: 74 },
    { name: "Layer 3 · Sentiment", score: 71 },
    { name: "Layer 4 · On-chain", score: 86 },
  ],
  weightsNote:
    "Composite = weighted avg per regime-adjusted weights. Current regime weights: tech 0.30, macro 0.15, sentiment 0.20, on-chain 0.35.",
};

const technicalIndicators = [
  { label: "RSI (14)", value: "73.2", subtext: "overbought", variant: "warning" as const },
  { label: "MACD hist", value: "+412", subtext: "bullish cross", variant: "success" as const },
  { label: "Supertrend", value: "Buy", subtext: "since Apr 12", variant: "success" as const },
  { label: "ADX (14)", value: "32.4", subtext: "strong trend", variant: "default" as const },
];

const onChainIndicators = [
  { label: "MVRV-Z", value: "2.84", subtext: "mid-cycle", variant: "default" as const },
  { label: "SOPR", value: "1.024", subtext: "profit taking", variant: "default" as const },
  { label: "Exch. reserve", value: "−12k", subtext: "outflow 7d", variant: "success" as const },
  { label: "Active addr.", value: "1.14M", subtext: "+8% vs 30d", variant: "default" as const },
];

const sentimentIndicators = [
  { label: "Fear&Greed", value: "72", subtext: "greed", variant: "warning" as const },
  { label: "Funding", value: "+0.012%", subtext: "neutral-bull", variant: "default" as const },
  { label: "Google trends", value: "58", subtext: "rising · 30d", variant: "default" as const },
  { label: "News sent.", value: "+0.42", subtext: "positive", variant: "success" as const },
];

const priceIndicators = [
  { label: "Vol (24h)", value: "$48.2B", subtext: "+18% vs 30d avg", variant: "default" as const },
  { label: "ATR (14d)", value: "$2,840", subtext: "2.7% of price", variant: "default" as const },
  { label: "Beta vs S&P", value: "1.72", subtext: "90d rolling", variant: "default" as const },
  { label: "Funding (8h)", value: "+0.012%", subtext: "neutral-bull", variant: "default" as const },
  { label: "Token unlocks", value: "none ≤ 30d", subtext: "PoW · no schedule", variant: "success" as const },
];

const signalHistory = [
  { timestamp: "Apr 12 08:20", signal: "buy" as SignalType, note: "Composite crossed above 70; regime shifted bull → accumulation", returnPct: "+ 18.4%" },
  { timestamp: "Mar 28 14:10", signal: "hold" as SignalType, note: "Consolidation; ADX < 20", returnPct: "+ 2.1%" },
  { timestamp: "Mar 14 09:00", signal: "buy" as SignalType, note: "On-chain score 86, MVRV-Z rising", returnPct: "+ 12.6%" },
  { timestamp: "Feb 28 19:45", signal: "sell" as SignalType, note: "Overbought + funding spike; regime risk-off", returnPct: "− 6.2%" },
  { timestamp: "Feb 14 11:30", signal: "buy" as SignalType, note: "Multi-timeframe alignment confirmed", returnPct: "+ 9.8%" },
  { timestamp: "Jan 28 03:20", signal: "hold" as SignalType, note: "Transition regime, awaiting confirmation", returnPct: "+ 1.2%" },
];

export default function SignalsPage() {
  const [activeCoin, setActiveCoin] = useState(0);
  const [activeTimeframe, setActiveTimeframe] = useState(6); // 1d default

  return (
    <AppShell crumbs="Markets" currentPage="Signals">
      <PageHeader
        title="Signal detail"
        subtitle="Layer-by-layer composite signal breakdown for a single coin."
      >
        <CoinPicker
          coins={coins}
          activeIndex={activeCoin}
          extraCount={extraCoinsCount}
          onSelect={setActiveCoin}
        />
      </PageHeader>

      {/* Hero signal card */}
      <div className="mb-5">
        <SignalHero {...heroData} />
      </div>

      {/* Multi-timeframe strip */}
      <div className="mb-5 rounded-xl border border-border-default bg-bg-1 p-4">
        <div className="mb-2.5 flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Multi-timeframe signals · BTC
          </span>
          <span className="text-xs text-text-muted">
            click a timeframe to drill in · selection drives every data section below
          </span>
        </div>
        <TimeframeStrip
          timeframes={timeframes}
          activeIndex={activeTimeframe}
          onSelect={setActiveTimeframe}
        />
      </div>

      {/* Price chart + Composite score */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="flex flex-col gap-4">
          <PriceChart />
          <IndicatorGrid columns={5}>
            {priceIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>
        <CompositeScore {...compositeData} />
      </div>

      {/* Technical / On-chain / Sentiment indicators */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Technical */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
            Technical indicators
          </div>
          <IndicatorGrid columns={2}>
            {technicalIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>

        {/* On-chain */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
            On-chain
          </div>
          <IndicatorGrid columns={2}>
            {onChainIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>

        {/* Sentiment */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
            Sentiment
          </div>
          <IndicatorGrid columns={2}>
            {sentimentIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>
      </div>

      {/* Signal history */}
      <SignalHistory entries={signalHistory} />
    </AppShell>
  );
}
