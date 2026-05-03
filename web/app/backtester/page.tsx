"use client";

import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { SegmentedControl } from "@/components/segmented-control";
import { ControlButton } from "@/components/control-button";
import { KpiCard } from "@/components/kpi-card";
import { EquityCurve } from "@/components/equity-curve";
import { OptunaTable, type OptunaRun } from "@/components/optuna-table";
import { TradesTable, type Trade } from "@/components/trades-table";
import { Button } from "@/components/ui/button";

// Mock data
const kpis = [
  { label: "Total return", value: "+ 342.8%", subtitle: "vs BTC + 184.1%", valueColor: "success" as const, subtitleDirection: "up" as const },
  { label: "CAGR", value: "+ 72.4%", subtitle: "vs BTC + 46.2%", subtitleDirection: "up" as const },
  { label: "Sharpe", value: "4.12", subtitle: "risk-free 4.5%", valueColor: "accent" as const },
  { label: "Max drawdown", value: "−18.4%", subtitle: "BTC −42.1%", valueColor: "danger" as const, subtitleDirection: "down" as const },
  { label: "Win rate", value: "68%", subtitle: "n = 482 trades" },
];

const optunaRuns: OptunaRun[] = [
  { rank: 1, params: "rsi_period=14, macd=(12,26,9), regime_lb=30", sharpe: "4.12", returnPct: "+342.8%" },
  { rank: 2, params: "rsi_period=10, macd=(8,21,9), regime_lb=30", sharpe: "3.98", returnPct: "+321.4%" },
  { rank: 3, params: "rsi_period=14, macd=(12,26,9), regime_lb=45", sharpe: "3.84", returnPct: "+305.2%" },
  { rank: 4, params: "rsi_period=20, macd=(12,26,9), regime_lb=30", sharpe: "3.72", returnPct: "+289.6%" },
  { rank: 5, params: "rsi_period=14, macd=(10,21,7), regime_lb=20", sharpe: "3.58", returnPct: "+274.1%" },
];

const recentTrades: Trade[] = [
  { date: "Apr 22", side: "buy", reason: "BTC · regime shift bull, composite 78", returnPct: "+4.2%", duration: "open" },
  { date: "Apr 18", side: "sell", reason: "SOL · overbought + funding spike", returnPct: "+18.6%", duration: "8d" },
  { date: "Apr 10", side: "buy", reason: "SOL · composite crossed 70", returnPct: "+18.6%", duration: "8d" },
  { date: "Apr 05", side: "sell", reason: "ETH · regime transition risk-off", returnPct: "−2.1%", duration: "12d" },
  { date: "Mar 24", side: "buy", reason: "ETH · composite crossed 65", returnPct: "−2.1%", duration: "12d" },
  { date: "Mar 18", side: "sell", reason: "BTC · distribution signal", returnPct: "+8.4%", duration: "21d" },
  { date: "Feb 25", side: "buy", reason: "BTC · accumulation phase entry", returnPct: "+8.4%", duration: "21d" },
  { date: "Feb 14", side: "sell", reason: "XRP · momentum fade", returnPct: "+12.2%", duration: "6d" },
];

export default function BacktesterPage() {
  const router = useRouter();

  return (
    <AppShell crumbs="Research" currentPage="Backtester">
      <PageHeader
        title="Backtester"
        subtitle="Composite signal backtested across 2023–2026. Optuna-tuned hyperparams."
      />

      {/* Primary view toggle */}
      <SegmentedControl
        options={[
          { label: "Backtest", value: "backtest" },
          { label: "Arbitrage", value: "arbitrage" },
        ]}
        value="backtest"
        onChange={(v) => {
          if (v === "arbitrage") router.push("/backtester/arbitrage");
        }}
        className="mb-5"
      />

      {/* Controls row */}
      <div className="mb-5 flex flex-wrap items-center gap-2.5">
        <ControlButton label="Universe" value="Top 10 cap" />
        <ControlButton label="Period" value="2023-01-01 → today" />
        <ControlButton label="Initial" value="$100,000" />
        <ControlButton label="Rebalance" value="Weekly" />
        <ControlButton label="Costs" value="12 bps · realistic slippage" />
        <Button className="min-h-[44px]">Re-run backtest →</Button>
      </div>

      {/* KPI strip */}
      <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        {kpis.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      {/* Secondary view toggle */}
      <SegmentedControl
        options={[
          { label: "Summary", value: "summary" },
          { label: "Trade History", value: "trades" },
          { label: "Advanced", value: "advanced" },
        ]}
        value="summary"
        size="sm"
        className="mb-4"
      />

      {/* Equity curve + Optuna */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <EquityCurve dateRange="2023-01 → 2026-04-23" />
        <OptunaTable
          runs={optunaRuns}
          footer="TPE sampler · 2,400 trials · selected by best out-of-sample Sharpe."
        />
      </div>

      {/* Trades table */}
      <TradesTable
        trades={recentTrades}
        title="Recent trades - signal-driven"
        count="last 8 of 482"
      />
    </AppShell>
  );
}
