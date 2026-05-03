import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { DataSourceRow } from "@/components/data-source-badge";
import { OnChainCard } from "@/components/onchain-card";
import { WhaleActivity } from "@/components/whale-activity";

// ─────────────────────────────────────────────────────────────
// MOCK DATA
// ─────────────────────────────────────────────────────────────

const dataSources = [
  { name: "Glassnode", status: "live" as const },
  { name: "Dune", status: "live" as const },
  { name: "XRP active addr", status: "cached" as const, statusLabel: "cached 1h" },
];

const btcIndicators = [
  { label: "MVRV-Z", value: "2.84", subtext: "mid-cycle" },
  { label: "SOPR", value: "1.024", subtext: "profit taking" },
  { label: "Exch. reserve · 7d", value: "−12.4k", subtext: "▼ outflow", variant: "success" as const },
  { label: "Active addr · 24h", value: "1.14M", subtext: "+8% vs 30d" },
];

const ethIndicators = [
  { label: "MVRV-Z", value: "1.92", subtext: "accumulation" },
  { label: "SOPR", value: "1.012", subtext: "slight profit" },
  { label: "Exch. reserve · 7d", value: "−84.2k", subtext: "▼ outflow", variant: "success" as const },
  { label: "Active addr · 24h", value: "528k", subtext: "+3% vs 30d" },
];

const xrpIndicators = [
  { label: "MVRV-Z", value: "0.84", subtext: "undervalued" },
  { label: "SOPR", value: "0.998", subtext: "capitulation" },
  { label: "Exch. reserve · 7d", value: "+18.4k", subtext: "▲ inflow", variant: "danger" as const },
  { label: "Active addr · 24h", value: "142k", subtext: "−2% vs 30d" },
];

const whaleEvents = [
  { time: "14:32", coin: "BTC", direction: "outflow" as const, notes: "Coinbase Pro → cold storage · single TX", amountUSD: "$184.2M" },
  { time: "12:18", coin: "BTC", direction: "inflow" as const, notes: "Unknown wallet → Binance · ladder of 3 transfers", amountUSD: "$94.6M" },
  { time: "10:04", coin: "ETH", direction: "outflow" as const, notes: "OKX → Lido staking pool", amountUSD: "$72.8M" },
  { time: "08:56", coin: "BTC", direction: "outflow" as const, notes: "Kraken → cold storage", amountUSD: "$48.1M" },
  { time: "06:22", coin: "ETH", direction: "inflow" as const, notes: "DAO treasury → Coinbase Prime", amountUSD: "$36.4M" },
  { time: "03:48", coin: "BTC", direction: "outflow" as const, notes: "Binance → unknown wallet · large transfer", amountUSD: "$28.9M" },
  { time: "01:14", coin: "XRP", direction: "inflow" as const, notes: "Unknown wallet → Bitstamp · pre-listing flow", amountUSD: "$12.6M" },
  { time: "22:36", coin: "BTC", direction: "inflow" as const, notes: "Cold storage → Coinbase Prime · institutional", amountUSD: "$10.8M" },
];

// ─────────────────────────────────────────────────────────────
// PAGE
// ─────────────────────────────────────────────────────────────

export default function OnChainPage() {
  return (
    <AppShell crumbs="Research" currentPage="On-chain">
      <PageHeader
        title="On-chain"
        subtitle="Glassnode + Dune metrics for the major majors. MVRV-Z, SOPR, exchange flows, active addresses."
      >
        <DataSourceRow sources={dataSources} />
      </PageHeader>

      {/* Section header */}
      <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
        On-chain metrics · 3 simultaneous · click any ticker to swap pair · all 33 pairs available
      </div>

      {/* 3-column indicator grid: BTC / ETH / XRP */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <OnChainCard
          ticker="BTC"
          status="live"
          statusLabel="live · 24h"
          indicators={btcIndicators}
        />
        <OnChainCard
          ticker="ETH"
          status="live"
          statusLabel="live · 24h"
          indicators={ethIndicators}
        />
        <OnChainCard
          ticker="XRP"
          status="cached"
          statusLabel="cached · 1h"
          indicators={xrpIndicators}
        />
      </div>

      {/* Whale activity table */}
      <div className="mb-5">
        <WhaleActivity events={whaleEvents} />
      </div>

      {/* Footnote / data-source caption */}
      <div className="rounded-lg border border-dashed border-border-strong bg-bg-2 p-3.5 text-xs leading-relaxed text-text-muted">
        On-chain data is rate-limited on the Glassnode free tier.{" "}
        <span className="font-medium text-text-secondary">MVRV-Z and SOPR</span> refresh every{" "}
        <span className="font-medium text-text-secondary">1 hour</span>;{" "}
        <span className="font-medium text-text-secondary">exchange reserve</span> recomputes from the 7-day delta on the same cadence;{" "}
        <span className="font-medium text-text-secondary">whale events</span> stream live via Glassnode webhook with a 30s buffer.
        Active-address counts for XRP fall back to a 1-hour cached value when the free Binance ticker doesn&apos;t expose them — the warning pill at top right makes that visible.
      </div>
    </AppShell>
  );
}
