"use client";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { DataSourceRow } from "@/components/data-source-badge";
import { OnChainCard } from "@/components/onchain-card";
import { WhaleActivity } from "@/components/whale-activity";
import { useOnchainDashboard } from "@/hooks/use-onchain-dashboard";
import { formatNumber, isMissing } from "@/lib/format";
import type { OnchainDashboard } from "@/lib/api-types";

// AUDIT-2026-05-03 (D4b): On-Chain page wired to GET /onchain/dashboard
// for BTC + ETH + XRP via three parallel hook instances. The four
// metrics in each card are: SOPR, MVRV-Z, net flow, whale activity
// flag (per the FastAPI router contract). The "active addresses"
// metric in the v0 mock isn't in the current /onchain endpoint —
// shown as "—" placeholder until the FastAPI side adds it.
//
// WhaleActivity table stays as v0 mock with TODO(D-ext): the FastAPI
// side has whale_activity flag (boolean) per pair but no event-stream
// endpoint yet. Future endpoint: GET /onchain/whale-events?since=&limit=.

const dataSources = [
  { name: "Glassnode", status: "live" as const },
  { name: "Dune", status: "live" as const },
  { name: "On-chain", status: "cached" as const, statusLabel: "cached · 1h" },
];

const whaleEvents = [
  // TODO(D-ext): GET /onchain/whale-events
  { time: "14:32", coin: "BTC", direction: "outflow" as const, notes: "Coinbase Pro → cold storage · single TX", amountUSD: "$184.2M" },
  { time: "12:18", coin: "BTC", direction: "inflow" as const, notes: "Unknown wallet → Binance · ladder of 3 transfers", amountUSD: "$94.6M" },
  { time: "10:04", coin: "ETH", direction: "outflow" as const, notes: "OKX → Lido staking pool", amountUSD: "$72.8M" },
  { time: "08:56", coin: "BTC", direction: "outflow" as const, notes: "Kraken → cold storage", amountUSD: "$48.1M" },
  { time: "06:22", coin: "ETH", direction: "inflow" as const, notes: "DAO treasury → Coinbase Prime", amountUSD: "$36.4M" },
  { time: "03:48", coin: "BTC", direction: "outflow" as const, notes: "Binance → unknown wallet · large transfer", amountUSD: "$28.9M" },
  { time: "01:14", coin: "XRP", direction: "inflow" as const, notes: "Unknown wallet → Bitstamp · pre-listing flow", amountUSD: "$12.6M" },
  { time: "22:36", coin: "BTC", direction: "inflow" as const, notes: "Cold storage → Coinbase Prime · institutional", amountUSD: "$10.8M" },
];

/** Build the 4-indicator strip for one pair from the API dashboard payload. */
function indicatorsFromDashboard(d: OnchainDashboard | undefined) {
  if (!d) {
    return [
      { label: "MVRV-Z", value: "—", subtext: "loading" },
      { label: "SOPR", value: "—", subtext: "loading" },
      { label: "Net flow · 7d", value: "—", subtext: "loading" },
      { label: "Whale activity", value: "—", subtext: "loading" },
    ];
  }

  // SOPR: > 1 = profit-taking, < 1 = capitulation, ~1 = neutral
  const soprSubtext = isMissing(d.sopr)
    ? "unavailable"
    : (d.sopr as number) > 1.02
      ? "profit taking"
      : (d.sopr as number) < 0.98
        ? "capitulation"
        : "neutral";

  // MVRV-Z: > 7 top zone, > 2 mid-cycle, < 0 undervalued
  const mvrvSubtext = isMissing(d.mvrv_z)
    ? "unavailable"
    : (d.mvrv_z as number) > 7
      ? "top zone"
      : (d.mvrv_z as number) > 2
        ? "mid-cycle"
        : (d.mvrv_z as number) > 0
          ? "accumulation"
          : "undervalued";

  // Net flow: positive = inflow (bearish), negative = outflow (bullish)
  const netFlow = d.net_flow;
  const netFlowVariant = isMissing(netFlow)
    ? undefined
    : (netFlow as number) < 0
      ? ("success" as const)
      : ("danger" as const);
  const netFlowSubtext = isMissing(netFlow)
    ? "unavailable"
    : (netFlow as number) < 0
      ? "▼ outflow"
      : "▲ inflow";

  return [
    {
      label: "MVRV-Z",
      value: isMissing(d.mvrv_z) ? "—" : formatNumber(d.mvrv_z as number, 2),
      subtext: mvrvSubtext,
    },
    {
      label: "SOPR",
      value: isMissing(d.sopr) ? "—" : formatNumber(d.sopr as number, 3),
      subtext: soprSubtext,
    },
    {
      label: "Net flow · 7d",
      value: isMissing(netFlow) ? "—" : formatNumber(netFlow as number, 0),
      subtext: netFlowSubtext,
      variant: netFlowVariant,
    },
    {
      label: "Whale activity",
      value: d.whale_activity === null || d.whale_activity === undefined
        ? "—"
        : d.whale_activity
          ? "Active"
          : "Quiet",
      subtext: d.source ?? "unavailable",
    },
  ];
}

export default function OnChainPage() {
  const btc = useOnchainDashboard("BTC/USDT");
  const eth = useOnchainDashboard("ETH/USDT");
  const xrp = useOnchainDashboard("XRP/USDT");

  const btcIndicators = indicatorsFromDashboard(btc.data);
  const ethIndicators = indicatorsFromDashboard(eth.data);
  const xrpIndicators = indicatorsFromDashboard(xrp.data);

  // Status pills reflect the actual `source` field from each fetch.
  const labelFor = (q: typeof btc) =>
    q.isLoading
      ? ("cached" as const)
      : q.data?.source === "unavailable"
        ? ("cached" as const)
        : ("live" as const);
  const labelTextFor = (q: typeof btc, fallback: string) =>
    q.data?.source ?? fallback;

  return (
    <AppShell crumbs="Research" currentPage="On-chain">
      <PageHeader
        title="On-chain"
        subtitle="Glassnode + Dune metrics for the major majors. MVRV-Z, SOPR, exchange flows, whale activity."
      >
        <DataSourceRow sources={dataSources} />
      </PageHeader>

      {/* Section header */}
      <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
        On-chain metrics · 3 simultaneous · click any ticker to swap pair · all pairs available
      </div>

      {/* 3-column indicator grid: BTC / ETH / XRP */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <OnChainCard
          ticker="BTC"
          status={labelFor(btc)}
          statusLabel={labelTextFor(btc, "live · 24h")}
          indicators={btcIndicators}
        />
        <OnChainCard
          ticker="ETH"
          status={labelFor(eth)}
          statusLabel={labelTextFor(eth, "live · 24h")}
          indicators={ethIndicators}
        />
        <OnChainCard
          ticker="XRP"
          status={labelFor(xrp)}
          statusLabel={labelTextFor(xrp, "cached · 1h")}
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
        <span className="font-medium text-text-secondary">net flow</span> recomputes from the 7-day delta on the same cadence;{" "}
        <span className="font-medium text-text-secondary">whale activity</span> is a derived flag from exchange in/out volumes.
        Active-address counts and the streaming whale-events table are scheduled for a future D-extension batch.
      </div>
    </AppShell>
  );
}
