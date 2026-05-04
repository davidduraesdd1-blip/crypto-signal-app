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
import { useSignals, useSignalDetail } from "@/hooks/use-signals";
import { useTriggerScan } from "@/hooks/use-scan";
import { ApiError } from "@/lib/api";
import {
  directionToSignalType,
  formatNumber,
  formatPct,
  isMissing,
  regimeToDisplay,
} from "@/lib/format";

// AUDIT-2026-05-03 (D4b): Signals page wired:
// - Coins list (CoinPicker) derived from useSignals() top-N rows
// - Hero card (SignalHero) wired to useSignalDetail(activePair)
// - Technical-indicator tile values wired from snap_* fields when
//   present in /signals/{pair} response
// Multi-timeframe strip + composite-score + on-chain/sentiment tiles
// + signal history stay as v0 mock with TODO(D-ext) — they need
// endpoints that don't exist yet (/signals/{pair}/timeframes,
// /signals/{pair}/composite-layers, /signals/history). Each is a
// future D-extension.

// ─── Stubs (TODO(D-ext): wire when endpoints exist) ────────────────────────

const timeframes: { label: string; signal: SignalType; score: number }[] = [
  // TODO(D-ext): GET /signals/{pair}/timeframes
  { label: "1m", signal: "hold", score: 52 },
  { label: "5m", signal: "buy", score: 64 },
  { label: "15m", signal: "buy", score: 70 },
  { label: "30m", signal: "buy", score: 73 },
  { label: "1h", signal: "buy", score: 76 },
  { label: "4h", signal: "buy", score: 80 },
  { label: "1d", signal: "buy", score: 78 },
  { label: "1w", signal: "buy", score: 84 },
];

const compositeFallback = {
  // TODO(D-ext): GET /signals/{pair}/composite-layers
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

const onChainIndicators = [
  // TODO(D-ext): pull from /onchain/dashboard for the selected pair
  { label: "MVRV-Z", value: "—", subtext: "live in /on-chain", variant: "default" as const },
  { label: "SOPR", value: "—", subtext: "live in /on-chain", variant: "default" as const },
  { label: "Net flow", value: "—", subtext: "live in /on-chain", variant: "default" as const },
  { label: "Whale", value: "—", subtext: "live in /on-chain", variant: "default" as const },
];

const sentimentIndicators = [
  // TODO(D-ext): /sentiment endpoint
  { label: "Fear&Greed", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
  { label: "Funding", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
  { label: "Google trends", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
  { label: "News sent.", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
];

const priceIndicators = [
  // TODO(D-ext): some are derivable from /signals enriched, others
  // need /token-unlocks endpoint for the unlock schedule
  { label: "Vol (24h)", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
  { label: "ATR (14d)", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
  { label: "Beta vs S&P", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
  { label: "Funding (8h)", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
  { label: "Token unlocks", value: "—", subtext: "TODO(D-ext)", variant: "default" as const },
];

const signalHistory = [
  // TODO(D-ext): GET /signals/{pair}/history
  { timestamp: "Apr 12 08:20", signal: "buy" as SignalType, note: "Composite crossed above 70; regime shifted bull → accumulation", returnPct: "+ 18.4%" },
  { timestamp: "Mar 28 14:10", signal: "hold" as SignalType, note: "Consolidation; ADX < 20", returnPct: "+ 2.1%" },
  { timestamp: "Mar 14 09:00", signal: "buy" as SignalType, note: "On-chain score 86, MVRV-Z rising", returnPct: "+ 12.6%" },
  { timestamp: "Feb 28 19:45", signal: "sell" as SignalType, note: "Overbought + funding spike; regime risk-off", returnPct: "− 6.2%" },
  { timestamp: "Feb 14 11:30", signal: "buy" as SignalType, note: "Multi-timeframe alignment confirmed", returnPct: "+ 9.8%" },
  { timestamp: "Jan 28 03:20", signal: "hold" as SignalType, note: "Transition regime, awaiting confirmation", returnPct: "+ 1.2%" },
];

export default function SignalsPage() {
  const [activeCoinIdx, setActiveCoinIdx] = useState(0);
  const [activeTimeframe, setActiveTimeframe] = useState(6); // 1d default

  // Derive the coin list from /signals top-N rows
  const signalsQuery = useSignals();
  // D4d: scan trigger button — invalidates signals + home + scan-status
  // queries on success so the page re-fetches the freshly-scanned data.
  const triggerScan = useTriggerScan();
  const allRows = signalsQuery.data?.results ?? [];
  const coins = allRows.slice(0, 5).map((r) => r.pair.split("/")[0]);
  const extraCoinsCount = Math.max(0, allRows.length - 5);
  const activePair = allRows[activeCoinIdx]?.pair ?? null;

  // Per-pair detail for the hero card + technical tiles
  const detailQuery = useSignalDetail(activePair);
  const detail = detailQuery.data;

  // Build the SignalHero props from the detail row
  const heroData = (() => {
    if (!detail) {
      return {
        ticker: activePair ? activePair.replace("/", " / ") : "— / —",
        name: activePair ? activePair.split("/")[0] : "—",
        price: "—",
        change24h: "—",
        change30d: "—",
        change1y: "—",
        signal: "hold" as SignalType,
        signalStrength: "—",
        timeframe: "1d",
        regime: "—",
        confidence: "—",
        regimeAge: "—",
      };
    }
    const change24 = detail.change_24h_pct;
    return {
      ticker: detail.pair.replace("/", " / "),
      name: detail.pair.split("/")[0],
      price: isMissing(detail.price ?? detail.price_usd)
        ? "—"
        : formatNumber((detail.price ?? detail.price_usd) as number, 2),
      change24h: isMissing(change24) ? "—" : formatPct(change24 as number, 2, true),
      change30d: "—",  // TODO(D-ext): change_30d_pct in /signals enriched
      change1y: "—",   // TODO(D-ext): change_1y_pct
      signal: directionToSignalType(detail.direction) as SignalType,
      signalStrength: detail.high_conf ? "strong" : "moderate",
      timeframe: "1d",
      regime: regimeToDisplay(detail.regime ?? detail.regime_label ?? null),
      confidence: isMissing(detail.confidence_avg_pct)
        ? "—"
        : `${Math.round(detail.confidence_avg_pct as number)}%`,
      regimeAge: "—",  // TODO(D-ext): regime_age_days from regime_history join
    };
  })();

  // Technical indicators from snap_* fields when present
  const technicalIndicators = (() => {
    if (!detail) {
      return [
        { label: "RSI (14)", value: "—", subtext: "loading", variant: "default" as const },
        { label: "MACD hist", value: "—", subtext: "loading", variant: "default" as const },
        { label: "Supertrend", value: "—", subtext: "loading", variant: "default" as const },
        { label: "ADX (14)", value: "—", subtext: "loading", variant: "default" as const },
      ];
    }
    const rsi = detail.rsi as number | undefined;
    const macd = detail.macd as number | undefined;
    const adx = detail.adx as number | undefined;
    return [
      {
        label: "RSI (14)",
        value: isMissing(rsi) ? "—" : formatNumber(rsi as number, 1),
        subtext: isMissing(rsi)
          ? "unavailable"
          : (rsi as number) >= 70
            ? "overbought"
            : (rsi as number) <= 30
              ? "oversold"
              : "neutral",
        variant: (isMissing(rsi)
          ? "default"
          : (rsi as number) >= 70
            ? "warning"
            : "default") as "default" | "warning" | "success",
      },
      {
        label: "MACD",
        value: isMissing(macd) ? "—" : formatNumber(macd as number, 2),
        subtext: isMissing(macd)
          ? "unavailable"
          : (macd as number) >= 0
            ? "bullish"
            : "bearish",
        variant: (isMissing(macd)
          ? "default"
          : (macd as number) >= 0
            ? "success"
            : "warning") as "default" | "warning" | "success",
      },
      {
        label: "Supertrend",
        value: directionToSignalType(detail.direction).toUpperCase(),
        subtext: regimeToDisplay(detail.regime ?? null),
        variant: "success" as const,
      },
      {
        label: "ADX (14)",
        value: isMissing(adx) ? "—" : formatNumber(adx as number, 1),
        subtext: isMissing(adx)
          ? "unavailable"
          : (adx as number) > 25
            ? "strong trend"
            : (adx as number) > 15
              ? "weak trend"
              : "no trend",
        variant: "default" as const,
      },
    ];
  })();

  return (
    <AppShell crumbs="Markets" currentPage="Signals">
      <PageHeader
        title="Signal detail"
        subtitle="Layer-by-layer composite signal breakdown for a single coin."
      >
        <div className="flex flex-wrap items-center gap-2">
          {coins.length > 0 ? (
            <CoinPicker
              coins={coins}
              activeIndex={activeCoinIdx}
              extraCount={extraCoinsCount}
              onSelect={setActiveCoinIdx}
            />
          ) : (
            <div className="text-xs text-text-muted">
              {signalsQuery.isLoading
                ? "Loading coins…"
                : signalsQuery.isError
                  ? "Couldn't load coins"
                  : "Run a scan to populate"}
            </div>
          )}
          <button
            type="button"
            onClick={() => triggerScan.mutate()}
            disabled={triggerScan.isPending}
            className="inline-flex min-h-[36px] items-center gap-1.5 rounded-md border border-accent-brand bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent-brand transition-colors hover:bg-accent-brand/10 disabled:opacity-60 disabled:cursor-wait"
            title="Trigger a fresh scan; results invalidate the signals + home caches"
          >
            <span>{triggerScan.isPending ? "⟳" : "▶"}</span>
            <span>{triggerScan.isPending ? "Scanning…" : "Scan now"}</span>
          </button>
        </div>
      </PageHeader>

      {/* Scan trigger feedback */}
      {triggerScan.isError && (
        <div className="mb-3 rounded-lg border border-danger/30 bg-danger/5 p-2 text-xs text-danger">
          {(() => {
            // AUDIT-2026-05-03 (D4 audit, HIGH): use ApiError
            // discriminators for actionable error copy instead of
            // raw Python detail strings.
            const err = triggerScan.error;
            if (err instanceof ApiError) {
              if (err.isAuthError) return "Scan trigger failed — API key missing or invalid. Set NEXT_PUBLIC_API_KEY in Vercel/local .env.local.";
              if (err.isRateLimited) return "Scan trigger rate-limited — wait a minute before retrying.";
              if (err.isGeoBlocked) return "Scan trigger blocked from this region — provider geo-block.";
            }
            return `Scan trigger failed — ${String(err?.message ?? "unknown error")}`;
          })()}
        </div>
      )}
      {triggerScan.isSuccess && triggerScan.data?.status === "started" && (
        <div className="mb-3 rounded-lg border border-success/30 bg-success/5 p-2 text-xs text-success">
          Scan started — results refresh automatically when complete (~30-60s)
        </div>
      )}
      {triggerScan.isSuccess && triggerScan.data?.status === "already_running" && (
        <div className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-2 text-xs text-warning">
          A scan is already running — wait for it to finish before triggering another
        </div>
      )}

      {/* Hero signal card */}
      <div className="mb-5">
        <SignalHero {...heroData} />
      </div>

      {/* Multi-timeframe strip */}
      <div className="mb-5 rounded-xl border border-border-default bg-bg-1 p-4">
        <div className="mb-2.5 flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Multi-timeframe signals · {coins[activeCoinIdx] ?? "—"}
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
        <CompositeScore {...compositeFallback} />
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
