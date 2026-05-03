"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { SegmentedControl } from "@/components/segmented-control";
import { AlertLogTable } from "@/components/alert-log-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { useAlertLog } from "@/hooks/use-alerts";
import type { AlertLogRow } from "@/lib/api-types";

// AUDIT-2026-05-03 (D4b): Alerts → History page wired to GET /alerts/log.
// Stats cards stay as visual mock until /alerts/log enriches with the
// 24h/7d rollup numbers + send-rate stats — that's a small D-extension.
// Filters (Range / Type / Status / Channel) stay non-functional in
// D4b; D4c wires them via URL search params + repeat-query patterns.

const stats = [
  // TODO(D-ext): aggregate counts from /alerts/log enriched response
  { label: "Last 24h", value: "—", sub: "—" },
  { label: "Last 7d", value: "—", sub: "—" },
  { label: "Sent rate", value: "—", sub: "—", valueColor: "text-success" },
  { label: "Avg latency", value: "—", sub: "—" },
];

type AlertEntryType = "buy" | "sell" | "regime" | "onchain" | "funding" | "unlock";

/** Map FastAPI alert-log row to the AlertLogTable entry shape. The
 * FastAPI `type` field carries names like "email_signal", "watchlist",
 * "agent_decision". The v0 table expects "buy" / "sell" / "regime" /
 * "onchain" / "funding" / "unlock" for the colored badge. We fall back
 * to "regime" (neutral teal) when unmappable. */
function rowToEntry(row: AlertLogRow): {
  timestamp: string;
  type: AlertEntryType;
  typeLabel: string;
  asset: string;
  message: string;
  status: "sent" | "failed" | "suppressed";
  channel: string;
} {
  const t = String(row.type ?? "").toLowerCase();
  let entryType: AlertEntryType = "regime";
  let typeLabel = "Alert";
  if (t.includes("buy")) {
    entryType = "buy";
    typeLabel = "Buy crossing";
  } else if (t.includes("sell")) {
    entryType = "sell";
    typeLabel = "Sell crossing";
  } else if (t.includes("regime")) {
    entryType = "regime";
    typeLabel = "Regime";
  } else if (t.includes("onchain") || t.includes("on-chain")) {
    entryType = "onchain";
    typeLabel = "On-chain";
  } else if (t.includes("funding")) {
    entryType = "funding";
    typeLabel = "Funding";
  } else if (t.includes("unlock")) {
    entryType = "unlock";
    typeLabel = "Unlock";
  } else if (t.includes("email") || t.includes("signal")) {
    // Default category: bucket as "buy" if direction looked like buy,
    // otherwise regime (neutral)
    entryType = "regime";
    typeLabel = String(row.type ?? "Alert");
  }

  const status: "sent" | "failed" | "suppressed" =
    String(row.status ?? "sent").toLowerCase() === "failed"
      ? "failed"
      : String(row.status ?? "").toLowerCase() === "suppressed"
        ? "suppressed"
        : "sent";

  return {
    timestamp: String(row.timestamp ?? "—"),
    type: entryType,
    typeLabel,
    asset: row.pair ? row.pair.split("/")[0] : "—",
    message: String(row.message ?? ""),
    status,
    channel: String(row.channel ?? "email"),
  };
}

export default function AlertsHistoryPage() {
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 10;
  const logQuery = useAlertLog(100);  // Server returns up to 100, paginate client-side for now

  const allEntries = (logQuery.data?.alerts ?? []).map(rowToEntry);
  const totalCount = logQuery.data?.count ?? 0;
  const startIdx = (currentPage - 1) * PAGE_SIZE;
  const visibleEntries = allEntries.slice(startIdx, startIdx + PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(allEntries.length / PAGE_SIZE));

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

      {/* Filter row — TODO(D-ext): wire via URL search params */}
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
          {visibleEntries.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              {logQuery.isLoading
                ? "Loading alerts log…"
                : logQuery.isError
                  ? "Couldn't load alerts — try refreshing in 30 seconds."
                  : "No alerts in the last 7d."}
            </div>
          ) : (
            <AlertLogTable entries={visibleEntries} />
          )}

          {/* Pagination */}
          {visibleEntries.length > 0 && (
            <div className="mt-3.5 flex items-center justify-between border-t border-border pt-3.5 text-[12px] text-text-muted">
              <span>
                Showing {visibleEntries.length} of {totalCount}
              </span>
              <div className="flex gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 px-2.5 text-[12px]"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                >
                  ‹ Prev
                </Button>
                {Array.from({ length: Math.min(3, totalPages) }, (_, i) => i + 1).map((p) => (
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
                  className="h-7 px-2.5 text-[12px]"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                >
                  Next ›
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}
