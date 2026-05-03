"use client";

import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { SegmentedControl } from "@/components/segmented-control";
import { KpiCard } from "@/components/kpi-card";
import { ArbSpreadTable, type ArbSpread } from "@/components/arb-spread-table";
import { FundingCarryTable, type FundingCarry } from "@/components/funding-carry-table";
import { Button } from "@/components/ui/button";
import { useBacktestArbitrage } from "@/hooks/use-backtester";
import { formatNumber, formatPct, isMissing } from "@/lib/format";
import type { ArbitrageOpportunity } from "@/lib/api-types";

// AUDIT-2026-05-03 (D4b): Backtester · Arbitrage page partially wired:
// - Spot Price Spread table → useBacktestArbitrage (when endpoint
//   exists; gracefully shows empty state on 404)
// - KPI strip (Pairs Scanned / Opportunities / Marginal / No Arb)
//   derived from the same response
// FundingCarryTable stays v0 mock — no /funding-carry endpoint yet
// (would need pairwise funding-rate diffs across exchanges, which
// extends data_feeds.py).

/** Map ArbitrageOpportunity → ArbSpread with signal classification */
function rowToSpread(opp: ArbitrageOpportunity): ArbSpread {
  const netPct = opp.net_spread_pct ?? 0;
  const signal: "opportunity" | "marginal" | "none" =
    netPct >= 0.4 ? "opportunity" : netPct >= 0.1 ? "marginal" : "none";
  return {
    pair: String(opp.pair ?? "—"),
    buyOn: String(opp.buy_exchange ?? "—"),
    sellOn: String(opp.sell_exchange ?? "—"),
    buyPrice: isMissing(opp.buy_price) ? "—" : formatNumber(opp.buy_price as number, 3),
    sellPrice: isMissing(opp.sell_price) ? "—" : formatNumber(opp.sell_price as number, 3),
    netSpread: isMissing(netPct) ? "—" : formatPct(netPct, 2),
    signal,
  };
}

const carries: FundingCarry[] = [
  // TODO(D-ext): GET /funding-carry — needs cross-exchange funding-rate diffs
  { pair: "BTC/USDT", okx8h: "+ 0.018%", bybit8h: "− 0.012%", delta: "+ 0.030%", strategy: "Long Bybit · Short OKX", annualized: "+ 32.9%" },
  { pair: "ETH/USDT", okx8h: "+ 0.024%", bybit8h: "+ 0.008%", delta: "+ 0.016%", strategy: "Long Bybit · Short OKX", annualized: "+ 17.5%" },
  { pair: "SOL/USDT", okx8h: "+ 0.041%", bybit8h: "− 0.018%", delta: "+ 0.059%", strategy: "Long Bybit · Short OKX", annualized: "+ 64.7%" },
  { pair: "XRP/USDT", okx8h: "− 0.006%", bybit8h: "+ 0.022%", delta: "+ 0.028%", strategy: "Long OKX · Short Bybit", annualized: "+ 30.7%" },
  { pair: "AVAX/USDT", okx8h: "+ 0.014%", bybit8h: "+ 0.012%", delta: "+ 0.002%", strategy: "Edge too thin — skip", annualized: "+ 2.2%" },
];

export default function ArbitragePage() {
  const router = useRouter();
  const arbQuery = useBacktestArbitrage();
  const opportunities = arbQuery.data?.opportunities ?? [];
  const spreads: ArbSpread[] = opportunities.map(rowToSpread);

  // Derive KPI counts from the live spread classifications
  const arbKpis = (() => {
    const pairs = spreads.length;
    const ops = spreads.filter((s) => s.signal === "opportunity").length;
    const marginal = spreads.filter((s) => s.signal === "marginal").length;
    const none = spreads.filter((s) => s.signal === "none").length;
    return [
      { label: "Pairs Scanned", value: formatNumber(pairs), subtitle: "live engine" },
      {
        label: "Opportunities",
        value: formatNumber(ops),
        subtitle: "net spread ≥ 0.40%",
        valueColor: "success" as const,
      },
      {
        label: "Marginal",
        value: formatNumber(marginal),
        subtitle: "net spread 0.10–0.40%",
        valueColor: "default" as const,
      },
      { label: "No Arb", value: formatNumber(none), subtitle: "net spread < 0.10%" },
    ];
  })();

  return (
    <AppShell crumbs="Research / Backtester" currentPage="Arbitrage">
      <PageHeader
        title="Backtester"
        subtitle="Live cross-exchange spread scanner. Net spread = gross spread − round-trip taker fees. Funding-rate carry trades from per-pair perp funding deltas."
      />

      {/* Primary view toggle */}
      <SegmentedControl
        options={[
          { label: "Backtest", value: "backtest" },
          { label: "Arbitrage", value: "arbitrage" },
        ]}
        value="arbitrage"
        onChange={(v) => {
          if (v === "backtest") router.push("/backtester");
        }}
        className="mb-5"
      />

      {/* Arbitrage controls */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5 text-[13px]">
          <span className="text-[11px] uppercase tracking-wider text-text-muted">Min Net Spread</span>
          <span className="font-mono font-medium">0.40%</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5 text-[13px]">
          <span className="text-[11px] uppercase tracking-wider text-text-muted">Universe</span>
          <span className="font-mono font-medium">Top 25 cap</span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5 text-[13px]">
          <span className="text-[11px] uppercase tracking-wider text-text-muted">Exchanges</span>
          <span className="font-mono font-medium">OKX · Kraken · Bybit · Coinbase</span>
        </div>
        <Button className="min-h-[44px]">Scan Now →</Button>
        <span className="flex items-center gap-1.5 rounded-full border border-border bg-bg-2 px-2.5 py-1 text-[11.5px] text-text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          last scan 47s ago · live
        </span>
      </div>

      {/* KPI strip */}
      <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {arbKpis.map((kpi) => (
          <KpiCard key={kpi.label} {...kpi} />
        ))}
      </div>

      {/* Spot Price Spread */}
      <div className="mb-3.5 flex items-baseline justify-between">
        <h2 className="text-[15px] font-semibold tracking-tight">Spot Price Spread</h2>
        <span className="text-xs text-text-muted">cross-exchange · ranked by net spread · click any row for routing detail</span>
      </div>
      <div className="mb-5">
        {spreads.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-default p-6 text-center text-sm text-muted-foreground">
            {arbQuery.isLoading
              ? "Scanning cross-exchange spreads…"
              : arbQuery.isError
                ? "Couldn't load arbitrage opportunities — endpoint may not be implemented yet."
                : "No spreads above the 0.10% threshold right now — try widening the universe."}
          </div>
        ) : (
          <ArbSpreadTable spreads={spreads} />
        )}
      </div>

      {/* Beginner-level story card preview */}
      <div className="mb-5 rounded-xl border border-dashed border-border bg-bg-2 p-4">
        <div className="mb-2.5 flex items-baseline justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Beginner view · same data, plain English
          </span>
          <span className="text-[11px] text-text-muted">shown when level = Beginner</span>
        </div>
        <div className="mb-2.5 rounded-lg border-l-[3px] border-accent-brand bg-bg-2 p-3.5">
          <div className="font-mono text-sm font-semibold">XRP/USDT · Net spread + 0.56%</div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-text-secondary">
            XRP is currently <strong className="text-text-primary">$2.836 on Bybit</strong> and{" "}
            <strong className="text-text-primary">$2.852 on Coinbase</strong>. After round-trip taker fees
            (~0.20%), buying on Bybit and selling on Coinbase nets a{" "}
            <strong className="text-text-primary">0.56% return</strong> per round trip.{" "}
            <strong className="text-text-primary">Move fast</strong> — these spreads usually close in 30–90
            seconds.
          </p>
        </div>
        <div className="rounded-lg border-l-[3px] border-accent-brand bg-bg-2 p-3.5">
          <div className="font-mono text-sm font-semibold">SOL/USDT · Net spread + 0.51%</div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-text-secondary">
            SOL is <strong className="text-text-primary">$192.10 on Kraken</strong> versus{" "}
            <strong className="text-text-primary">$193.18 on OKX</strong>. Net of fees:{" "}
            <strong className="text-text-primary">0.51% return</strong>. Best executed when both exchanges have
            liquidity at the quoted price (check order books before pulling the trigger).
          </p>
        </div>
      </div>

      {/* Funding-Rate Carry Trades */}
      <div className="mb-3.5 flex items-baseline justify-between">
        <h2 className="text-[15px] font-semibold tracking-tight">Funding-Rate Carry Trades</h2>
        <span className="text-xs text-text-muted">perpetual funding deltas · 8h funding cycle · annualized yield</span>
      </div>
      <div className="mb-5">
        <FundingCarryTable
          carries={carries}
          footer="Strategy: long the perp on the exchange with negative/lower funding, short the perp on the exchange with positive/higher funding. Profit accrues each 8h funding payment. Annualized = (delta × 3 cycles/day × 365). Carry holds while spread persists — typically 1–4 days."
        />
      </div>

      {/* Historical log expander */}
      <button className="flex w-full cursor-pointer items-center justify-between rounded-lg border border-border bg-bg-1 px-4 py-3 text-[13px] text-text-secondary transition-all hover:bg-bg-2 hover:text-text-primary">
        <span>
          <strong className="text-text-primary">Historical Arbitrage Log</strong> — last 48 opportunities ·
          DB-backed · click to expand
        </span>
        <span className="text-[11px] text-text-muted">▾</span>
      </button>
    </AppShell>
  );
}
