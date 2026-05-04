"use client";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { DataSourceRow } from "@/components/data-source-badge";
import { SignalCard, type SignalType } from "@/components/signal-card";
import { MacroStrip } from "@/components/macro-strip";
import { Watchlist } from "@/components/watchlist";
import { BacktestCard } from "@/components/backtest-card";
import { useHomeSummary } from "@/hooks/use-home-summary";
import { useBacktestSummary } from "@/hooks/use-backtester";
import {
  directionToSignalType,
  formatConfidence,
  formatNumber,
  formatPct,
  isMissing,
  regimeToDisplay,
} from "@/lib/format";

// AUDIT-2026-05-03 (D4b): live wiring of Home page hero cards via
// `/home/summary` and BacktestCard KPIs via `/backtest/summary`.
// MacroStrip + Watchlist + DataSourceRow are still stubbed because
// no consolidated /macro or /watchlist-with-sparkline endpoint exists
// yet — those become D-extension follow-ups. The page silently falls
// back to the mock arrays below if the API call returns empty/null,
// so the visual contract holds even when the live deploy is cold.

// ─── Stubbed sections (TODO(D-ext): wire when endpoints exist) ──────────────

const dataSources = [
  // TODO(D-ext): GET /data-sources — for now show the three the home
  // page actually depends on per the v0 mockup contract.
  { name: "OKX", status: "live" as const },
  { name: "Glassnode", status: "live" as const },
  { name: "Google Trends", status: "cached" as const },
];

const macroItems = [
  // TODO(D-ext): consolidated macro endpoint. Today the values come
  // from disparate sources (BTC dominance via /signals, fear/greed
  // via separate scraper, DXY via yfinance). Keep mock until a
  // single endpoint exists.
  { label: "BTC Dominance", value: "58.9%", sub: "+ 0.4 ppts · 7d" },
  { label: "Fear & Greed", value: "72", sub: "Greed", subColor: "warning" as const },
  { label: "DXY", value: "104.21", sub: "− 0.6% · 30d" },
  { label: "Funding (BTC)", value: "+ 0.012%", sub: "8h avg" },
  { label: "Regime (macro)", value: "Risk-on", sub: "confidence 76%", subColor: "accent" as const },
];

const watchlistItems = [
  // TODO(D-ext): /signals enriched with sparkline points. The current
  // /signals response doesn't carry per-pair price history needed for
  // the inline sparklines. Keep mock until /signals/{pair}/sparkline
  // (or similar) exists. Sparkline data is decorative — the rest of
  // the watchlist (price, change) can be derived from /signals.
  {
    ticker: "BTC",
    price: "$104,280",
    change: "2.14%",
    changeDirection: "up" as const,
    sparklinePoints: "0,16 8,15 16,17 24,13 32,14 40,11 48,10 56,7 64,8 72,5 80,3",
  },
  {
    ticker: "ETH",
    price: "$3,844",
    change: "1.08%",
    changeDirection: "up" as const,
    sparklinePoints: "0,14 8,13 16,11 24,12 32,10 40,8 48,9 56,11 64,8 72,7 80,6",
  },
  {
    ticker: "SOL",
    price: "$192.40",
    change: "0.72%",
    changeDirection: "down" as const,
    sparklinePoints: "0,6 8,8 16,9 24,10 32,11 40,13 48,14 56,13 64,15 72,16 80,17",
  },
  {
    ticker: "AVAX",
    price: "$41.80",
    change: "3.20%",
    changeDirection: "up" as const,
    sparklinePoints: "0,18 8,17 16,14 24,15 32,12 40,11 48,8 56,6 64,4 72,3 80,2",
  },
  {
    ticker: "LINK",
    price: "$22.04",
    change: "0.91%",
    changeDirection: "up" as const,
    sparklinePoints: "0,12 8,14 16,11 24,13 32,10 40,11 48,9 56,8 64,9 72,7 80,6",
  },
  {
    ticker: "NEAR",
    price: "$5.82",
    change: "1.44%",
    changeDirection: "down" as const,
    sparklinePoints: "0,8 8,9 16,10 24,9 32,11 40,12 48,13 56,14 64,13 72,15 80,16",
  },
];

// ─── Fallback hero cards (shown only if /home/summary returns empty) ────────

const fallbackHeroSignals: {
  ticker: string;
  price: string;
  change: string;
  changeDirection: "up" | "down";
  signal: SignalType;
  regime: string;
  confidence: string;
}[] = [
  // Truthful empty-state — when the API is up but no scan has run yet
  // we'd see []. Show a single placeholder card instead of a blank grid.
];

// ─── Page component ─────────────────────────────────────────────────────────

export default function HomePage() {
  const homeQuery = useHomeSummary(5);
  const backtestQuery = useBacktestSummary();

  // Map /home/summary hero cards → SignalCard props
  const heroSignals = (() => {
    const cards = homeQuery.data?.hero_cards;
    if (!cards || cards.length === 0) return fallbackHeroSignals;
    return cards.map((card) => ({
      ticker: card.pair.replace("/", " / "),
      price: isMissing(card.price)
        ? "—"
        : (card.price as number) >= 1000
          ? formatNumber(card.price as number, 0)
          : formatNumber(card.price as number, 2),
      change: isMissing(card.change_24h)
        ? "—"
        : formatPct(card.change_24h as number, 2),
      changeDirection: ((card.change_24h ?? 0) >= 0 ? "up" : "down") as "up" | "down",
      signal: directionToSignalType(card.direction ?? "HOLD") as SignalType,
      regime: regimeToDisplay(card.regime),
      confidence: formatConfidence(card.confidence),
    }));
  })();

  // Map /backtest/summary → BacktestCard kpi cells
  const backtestKpis = (() => {
    const summary = backtestQuery.data;
    if (!summary) {
      return [
        { label: "Return (90d)", value: "—", delta: "loading", deltaType: "neutral" as const },
        { label: "Max drawdown", value: "—", delta: "loading", deltaType: "neutral" as const },
        { label: "Sharpe", value: "—", delta: "loading", deltaType: "neutral" as const },
        { label: "Win rate", value: "—", delta: "loading", deltaType: "neutral" as const },
      ];
    }
    return [
      {
        label: "Return (90d)",
        value: isMissing(summary.avg_pnl_pct) ? "—" : formatPct(summary.avg_pnl_pct as number, 1, true),
        delta: "live engine",
        deltaType: ((summary.avg_pnl_pct ?? 0) >= 0 ? "up" : "neutral") as "up" | "neutral",
        valueColor: ((summary.avg_pnl_pct ?? 0) >= 0 ? "success" : undefined) as
          | "success"
          | undefined,
      },
      {
        label: "Max drawdown",
        value: isMissing(summary.max_drawdown_pct) ? "—" : formatPct(summary.max_drawdown_pct as number, 1, true),
        delta: `${summary.total_trades ?? "—"} trades`,
        deltaType: "neutral" as const,
      },
      {
        label: "Sharpe",
        value: isMissing(summary.sharpe_ratio) ? "—" : formatNumber(summary.sharpe_ratio as number, 2),
        delta: "vs BTC baseline",
        deltaType: "neutral" as const,
      },
      {
        label: "Win rate",
        value: isMissing(summary.win_rate_pct) ? "—" : formatPct(summary.win_rate_pct as number, 0),
        delta: `n=${summary.total_trades ?? "—"} trades`,
        deltaType: "neutral" as const,
      },
    ];
  })();

  return (
    <AppShell crumbs="Markets" currentPage="Home">
      {/* Page header */}
      <PageHeader
        title="Market home"
        subtitle="Composite signals + regime state across the top-cap set."
      >
        <DataSourceRow sources={dataSources} />
      </PageHeader>

      {/* Hero signals — empty-state when no scan has run yet */}
      {heroSignals.length === 0 ? (
        <div className="mb-6 rounded-lg border border-dashed border-border-default p-8 text-center text-sm text-muted-foreground">
          {homeQuery.isLoading
            ? "Loading market signals…"
            : homeQuery.isError
              ? "Couldn't load signals — try refreshing in 30 seconds."
              : "Run a scan to populate the watchlist (no scan results yet)."}
        </div>
      ) : (
        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {heroSignals.map((signal) => (
            <SignalCard key={signal.ticker} {...signal} />
          ))}
        </div>
      )}

      {/* Macro strip — TODO(D-ext): consolidated /macro endpoint */}
      <div className="mb-6">
        <MacroStrip items={macroItems} />
      </div>

      {/* Two-column layout: Watchlist + Backtest */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Watchlist items={watchlistItems} />
        <BacktestCard kpis={backtestKpis} />
      </div>
    </AppShell>
  );
}
