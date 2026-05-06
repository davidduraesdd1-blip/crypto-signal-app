"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { SegmentedControl } from "@/components/segmented-control";
import { AlertLogTable } from "@/components/alert-log-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAlertLog } from "@/hooks/use-alerts";
import type { AlertLogRow } from "@/lib/api-types";

// AUDIT-2026-05-06 (post-launch v4): four real dropdown filters wire
// client-side filtering of the alerts log. Range filter uses the
// timestamp; Type / Status / Channel use the row fields directly.
// Server-side filter params come post-V1 — for now we filter the
// already-fetched 100-row response window.

const RANGE_OPTIONS = ["Last 1h", "Last 24h", "Last 7d", "Last 30d", "All time"] as const;
const TYPE_OPTIONS = ["All", "Buy", "Sell", "Regime", "On-chain", "Funding", "Unlock"] as const;
const STATUS_OPTIONS = ["All", "Sent", "Failed", "Suppressed"] as const;
const CHANNEL_OPTIONS = ["All", "Email", "Slack", "Telegram", "Browser push"] as const;

type RangeValue = (typeof RANGE_OPTIONS)[number];
type TypeValue = (typeof TYPE_OPTIONS)[number];
type StatusValue = (typeof STATUS_OPTIONS)[number];
type ChannelValue = (typeof CHANNEL_OPTIONS)[number];

const RANGE_MS: Record<RangeValue, number | null> = {
  "Last 1h":  60 * 60 * 1000,
  "Last 24h": 24 * 60 * 60 * 1000,
  "Last 7d":  7 * 24 * 60 * 60 * 1000,
  "Last 30d": 30 * 24 * 60 * 60 * 1000,
  "All time": null,
};

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
  const router = useRouter();
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 10;
  const logQuery = useAlertLog(100);  // Server returns up to 100, paginate client-side for now

  // AUDIT-2026-05-06 (post-launch v4): client-side filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [rangeFilter, setRangeFilter] = useState<RangeValue>("Last 7d");
  const [typeFilter, setTypeFilter] = useState<TypeValue>("All");
  const [statusFilter, setStatusFilter] = useState<StatusValue>("All");
  const [channelFilter, setChannelFilter] = useState<ChannelValue>("All");

  const allEntries = (logQuery.data?.alerts ?? []).map(rowToEntry);
  const totalCount = logQuery.data?.count ?? 0;

  // AUDIT-2026-05-06 (post-launch v4): apply filters before paginating
  const filteredEntries = useMemo(() => {
    const cutoff = RANGE_MS[rangeFilter];
    const cutoffMs = cutoff != null ? Date.now() - cutoff : null;
    const term = searchTerm.trim().toLowerCase();

    return allEntries.filter((e) => {
      // Range
      if (cutoffMs != null) {
        const ts = Date.parse(e.timestamp);
        if (!Number.isNaN(ts) && ts < cutoffMs) return false;
      }
      // Type
      if (typeFilter !== "All") {
        const want = typeFilter.toLowerCase().replace("-", "");
        const got = e.type.toLowerCase().replace("-", "");
        if (got !== want && want === "onchain" ? got !== "onchain" : got !== want) return false;
      }
      // Status
      if (statusFilter !== "All") {
        if (e.status.toLowerCase() !== statusFilter.toLowerCase()) return false;
      }
      // Channel
      if (channelFilter !== "All") {
        const want = channelFilter.toLowerCase().split(" ")[0];
        if (!e.channel.toLowerCase().includes(want)) return false;
      }
      // Search term
      if (term && !`${e.message} ${e.asset} ${e.typeLabel}`.toLowerCase().includes(term)) return false;
      return true;
    });
  }, [allEntries, rangeFilter, typeFilter, statusFilter, channelFilter, searchTerm]);

  const startIdx = (currentPage - 1) * PAGE_SIZE;
  const visibleEntries = filteredEntries.slice(startIdx, startIdx + PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(filteredEntries.length / PAGE_SIZE));

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
            // AUDIT-2026-05-03 (D4 audit, MEDIUM): router.push instead
            // of full page reload — preserves TanStack Query cache.
            if (v === "configure") router.push("/alerts");
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

      {/* Filter row — all 4 dropdowns + search now real client-side
          filters. AUDIT-2026-05-06 (post-launch v4). */}
      <div className="mb-5 flex flex-wrap items-center gap-2.5">
        <div className="flex min-w-[200px] max-w-[320px] flex-1 items-center gap-2 rounded-lg border border-border bg-bg-1 px-3 py-1.5">
          <span className="text-text-muted">🔎</span>
          <Input
            type="text"
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
            placeholder="search messages, assets, types..."
            className="h-7 border-0 bg-transparent p-0 text-[13px] focus-visible:ring-0"
          />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-bg-1 px-3 text-[13px] outline-none transition-colors hover:border-border-strong hover:bg-bg-2 focus-visible:ring-2 focus-visible:ring-accent-brand">
            <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Range</span>
            <span className="font-mono font-medium">{rangeFilter}</span>
            <span className="text-[11px] text-text-muted">▾</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-[140px]">
            {RANGE_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt}
                onSelect={() => { setRangeFilter(opt); setCurrentPage(1); }}
                className="cursor-pointer text-[13px]"
              >
                {opt === rangeFilter ? "✓ " : "  "}{opt}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-bg-1 px-3 text-[13px] outline-none transition-colors hover:border-border-strong hover:bg-bg-2 focus-visible:ring-2 focus-visible:ring-accent-brand">
            <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Type</span>
            <span className="font-mono font-medium">{typeFilter}</span>
            <span className="text-[11px] text-text-muted">▾</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-[140px]">
            {TYPE_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt}
                onSelect={() => { setTypeFilter(opt); setCurrentPage(1); }}
                className="cursor-pointer text-[13px]"
              >
                {opt === typeFilter ? "✓ " : "  "}{opt}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-bg-1 px-3 text-[13px] outline-none transition-colors hover:border-border-strong hover:bg-bg-2 focus-visible:ring-2 focus-visible:ring-accent-brand">
            <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Status</span>
            <span className="font-mono font-medium">{statusFilter}</span>
            <span className="text-[11px] text-text-muted">▾</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-[140px]">
            {STATUS_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt}
                onSelect={() => { setStatusFilter(opt); setCurrentPage(1); }}
                className="cursor-pointer text-[13px]"
              >
                {opt === statusFilter ? "✓ " : "  "}{opt}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-bg-1 px-3 text-[13px] outline-none transition-colors hover:border-border-strong hover:bg-bg-2 focus-visible:ring-2 focus-visible:ring-accent-brand">
            <span className="text-[11px] uppercase tracking-[0.06em] text-text-muted">Channel</span>
            <span className="font-mono font-medium">{channelFilter}</span>
            <span className="text-[11px] text-text-muted">▾</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-[160px]">
            {CHANNEL_OPTIONS.map((opt) => (
              <DropdownMenuItem
                key={opt}
                onSelect={() => { setChannelFilter(opt); setCurrentPage(1); }}
                className="cursor-pointer text-[13px]"
              >
                {opt === channelFilter ? "✓ " : "  "}{opt}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
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
