"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { SegmentedControl } from "@/components/segmented-control";
import { AlertLogTable } from "@/components/alert-log-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

// Mock data
const stats = [
  { label: "Last 24h", value: "14", sub: "+ 2 vs prior 24h" },
  { label: "Last 7d", value: "86", sub: "81 sent · 3 failed · 2 suppressed" },
  { label: "Sent rate", value: "94.2%", sub: "7d rolling · email channel", valueColor: "text-success" },
  { label: "Avg latency", value: "3.4s", sub: "event fired → email delivered" },
];

const alertLog = [
  {
    timestamp: "Apr 29 · 14:32",
    type: "buy" as const,
    typeLabel: "Buy crossing",
    asset: "BTC",
    message: "Composite signal crossed 75 (78.4 conf, regime bull stable 14d). Recommended action: enter long.",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 29 · 12:18",
    type: "onchain" as const,
    typeLabel: "On-chain",
    asset: "XRP",
    message: "MVRV-Z flipped to 0.84 (undervalued); SOPR at 0.998 (capitulation). Divergence vs spot up 0.96%.",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 29 · 10:04",
    type: "regime" as const,
    typeLabel: "Regime",
    asset: "SOL",
    message: "SOL regime transitioned: Distribution → Bear (confidence 74%, since Apr 16). Composite weight rebalanced.",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 29 · 08:56",
    type: "buy" as const,
    typeLabel: "Buy crossing",
    asset: "AVAX",
    message: "Composite signal crossed 70 on 4h timeframe (regime bull, on-chain accumulation tier).",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 29 · 06:22",
    type: "sell" as const,
    typeLabel: "Sell crossing",
    asset: "NEAR",
    message: "Composite signal dropped to 28 (regime bear, since Apr 06 · 18d stable). Exit suggested.",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 28 · 22:14",
    type: "funding" as const,
    typeLabel: "Funding",
    asset: "SOL",
    message: "Bybit perpetual funding spiked to −0.018% (long-side over-leveraged). Possible flush within 8h.",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 28 · 18:42",
    type: "unlock" as const,
    typeLabel: "Unlock",
    asset: "DOT",
    message: "Polkadot unlock event in 5 days: 3.2M tokens (~$22.8M at current price). Forward sell-pressure flag.",
    status: "failed" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 28 · 15:08",
    type: "regime" as const,
    typeLabel: "Regime",
    asset: "ETH",
    message: "ETH regime: Bull → Transition (confidence 61%, since Apr 20 · 4d). Weights shifted to defensive.",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 28 · 11:34",
    type: "onchain" as const,
    typeLabel: "On-chain",
    asset: "BTC",
    message: "BTC exchange reserve −12.4k over 7d (significant outflow, supply tightening). Bullish on-chain.",
    status: "sent" as const,
    channel: "email",
  },
  {
    timestamp: "Apr 28 · 09:12",
    type: "buy" as const,
    typeLabel: "Buy crossing",
    asset: "LINK",
    message: "Composite crossed 70 (regime accumulation, since Apr 14 · 10d). On-chain layer score 72.",
    status: "suppressed" as const,
    channel: "email",
  },
];

export default function AlertsHistoryPage() {
  const [currentPage, setCurrentPage] = useState(1);

  return (
    <AppShell crumbs="Account / Alerts" currentPage="History">
      <PageHeader
        title="Alerts"
        subtitle="Every alert that fired across all configured types and channels. Searchable, filterable, exportable."
      />

      {/* Tab navigation */}
      <div className="mb-5">
        <SegmentedControl
          options={[
            { label: "Configure", value: "configure" },
            { label: "History", value: "history" },
          ]}
          value="history"
          onChange={(v) => {
            if (v === "configure") {
              window.location.href = "/alerts";
            }
          }}
        />
      </div>

      {/* 4-stat summary */}
      <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="p-4">
              <div className="text-[11px] uppercase tracking-[0.06em] text-text-muted">
                {stat.label}
              </div>
              <div
                className={`mt-1 font-mono text-xl font-semibold leading-tight ${
                  stat.valueColor || ""
                }`}
              >
                {stat.value}
              </div>
              <div className="mt-0.5 font-mono text-[11.5px] text-text-muted">
                {stat.sub}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filter row */}
      <div className="mb-5 flex flex-wrap items-center gap-2.5">
        <div className="flex min-w-[200px] max-w-[320px] flex-1 items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5">
          <span className="text-text-muted">🔎</span>
          <Input
            type="text"
            placeholder="search messages, assets, types..."
            className="h-7 border-0 bg-transparent p-0 text-[13px] focus-visible:ring-0"
          />
        </div>
        <Button variant="outline" size="sm" className="h-9 gap-1.5 px-3 text-[13px]">
          <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Range</span>
          <span className="font-mono font-medium">Last 7d</span>
          <span className="text-[11px] text-text-muted">▾</span>
        </Button>
        <Button variant="outline" size="sm" className="h-9 gap-1.5 px-3 text-[13px]">
          <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Type</span>
          <span className="font-mono font-medium">All</span>
          <span className="text-[11px] text-text-muted">▾</span>
        </Button>
        <Button variant="outline" size="sm" className="h-9 gap-1.5 px-3 text-[13px]">
          <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Status</span>
          <span className="font-mono font-medium">All</span>
          <span className="text-[11px] text-text-muted">▾</span>
        </Button>
        <Button variant="outline" size="sm" className="h-9 gap-1.5 px-3 text-[13px]">
          <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Channel</span>
          <span className="font-mono font-medium">All</span>
          <span className="text-[11px] text-text-muted">▾</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto h-9 px-3 text-[13px] text-accent-brand"
        >
          ↓ Export CSV
        </Button>
      </div>

      {/* Alert log */}
      <Card>
        <CardContent className="p-4">
          <AlertLogTable entries={alertLog} />

          {/* Pagination */}
          <div className="mt-3.5 flex items-center justify-between border-t border-border pt-3.5 text-[12px] text-text-muted">
            <span>Showing 10 of 86 · last 7d</span>
            <div className="flex gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2.5 text-[12px]"
              >
                ‹ Prev
              </Button>
              {[1, 2, 3].map((p) => (
                <Button
                  key={p}
                  variant="outline"
                  size="sm"
                  className={`h-7 w-7 px-0 text-[12px] ${
                    currentPage === p ? "bg-accent-soft border-accent-brand text-text-primary" : ""
                  }`}
                  onClick={() => setCurrentPage(p)}
                >
                  {p}
                </Button>
              ))}
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2 text-[12px]"
              >
                ...
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 px-0 text-[12px]"
              >
                9
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-2.5 text-[12px]"
              >
                Next ›
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
