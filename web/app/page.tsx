import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { DataSourceRow } from "@/components/data-source-badge";
import { SignalCard, type SignalType } from "@/components/signal-card";
import { MacroStrip } from "@/components/macro-strip";
import { Watchlist } from "@/components/watchlist";
import { BacktestCard } from "@/components/backtest-card";

// ─────────────────────────────────────────────────────────────────────
// MOCK DATA — will be replaced with real API later
// ─────────────────────────────────────────────────────────────────────

const dataSources = [
  { name: "OKX", status: "live" as const },
  { name: "Glassnode", status: "live" as const },
  { name: "Google Trends", status: "cached" as const },
];

const heroSignals: {
  ticker: string;
  price: string;
  change: string;
  changeDirection: "up" | "down";
  signal: SignalType;
  regime: string;
  confidence: string;
}[] = [
  {
    ticker: "BTC / USDT",
    price: "104,280",
    change: "2.14%",
    changeDirection: "up",
    signal: "buy",
    regime: "bull",
    confidence: "82% conf",
  },
  {
    ticker: "ETH / USDT",
    price: "3,844",
    change: "1.08%",
    changeDirection: "up",
    signal: "hold",
    regime: "transition",
    confidence: "61%",
  },
  {
    ticker: "SOL / USDT",
    price: "192.40",
    change: "3.72%",
    changeDirection: "up",
    signal: "buy",
    regime: "bull",
    confidence: "77%",
  },
  {
    ticker: "XRP / USDT",
    price: "2.84",
    change: "0.96%",
    changeDirection: "up",
    signal: "buy",
    regime: "accumulation",
    confidence: "68%",
  },
  {
    ticker: "BNB / USDT",
    price: "612.50",
    change: "1.42%",
    changeDirection: "down",
    signal: "hold",
    regime: "ranging",
    confidence: "54%",
  },
];

const macroItems = [
  { label: "BTC Dominance", value: "58.9%", sub: "+ 0.4 ppts · 7d" },
  { label: "Fear & Greed", value: "72", sub: "Greed", subColor: "warning" as const },
  { label: "DXY", value: "104.21", sub: "− 0.6% · 30d" },
  { label: "Funding (BTC)", value: "+ 0.012%", sub: "8h avg" },
  { label: "Regime (macro)", value: "Risk-on", sub: "confidence 76%", subColor: "accent" as const },
];

const watchlistItems = [
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

const backtestKpis = [
  { label: "Return (90d)", value: "+ 28.4%", delta: "vs BTC +14.1%", deltaType: "up" as const, valueColor: "success" as const },
  { label: "Max drawdown", value: "−8.2%", delta: "vs BTC −16.7%", deltaType: "neutral" as const },
  { label: "Sharpe", value: "5.2", delta: "exc 3.1 (BTC)", deltaType: "up" as const },
  { label: "Win rate", value: "63%", delta: "n=148 trades", deltaType: "neutral" as const },
];

// ─────────────────────────────────────────────────────────────────────
// PAGE COMPONENT
// ─────────────────────────────────────────────────────────────────────

export default function HomePage() {
  return (
    <AppShell crumbs="Markets" currentPage="Home">
      {/* Page header */}
      <PageHeader
        title="Market home"
        subtitle="Composite signals + regime state across the top-cap set."
      >
        <DataSourceRow sources={dataSources} />
      </PageHeader>

      {/* Hero signals - 5 columns on xl, 3 on lg, 2 on md, 1 on mobile */}
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {heroSignals.map((signal) => (
          <SignalCard key={signal.ticker} {...signal} />
        ))}
      </div>

      {/* Macro strip */}
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
