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
import { BeginnerHint } from "@/components/beginner-hint";
import {
  useBacktestSummary,
  useBacktestTrades,
  useOptunaRuns,
  useEquityCurve,
} from "@/hooks/use-backtester";
import {
  formatNumber,
  formatPct,
  isMissing,
} from "@/lib/format";
import type { BacktestTrade } from "@/lib/api-types";

// AUDIT-2026-05-03 (D4b): Backtester page wired:
// - KPI strip → useBacktestSummary
// - Recent trades table → useBacktestTrades(50)
// EquityCurve stays as visual mock (no equity-history endpoint),
// OptunaTable stays as v0 mock (no /backtest/optuna-runs endpoint —
// optuna_studies.sqlite is read by Python but not exposed via API).

// AUDIT-2026-05-06 (Everything-Live, item 4): the prior 5-row hardcoded
// optunaRuns mock is replaced by useOptunaRuns() inside the component
// — it reads optuna_studies.sqlite via /backtest/optuna-runs.

/** Map BacktestTrade row → v0 TradesTable contract */
function rowToTrade(t: BacktestTrade): Trade {
  const side =
    String(t.direction ?? "")
      .toUpperCase()
      .includes("BUY")
      ? "buy"
      : "sell";
  // Compact "Apr 22" timestamp from ISO close_time
  const dateStr = (() => {
    const ts = t.close_time ?? t.open_time;
    if (!ts) return "—";
    try {
      const d = new Date(ts);
      return d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
    } catch {
      return "—";
    }
  })();
  // Duration in days if both timestamps present
  const duration = (() => {
    if (!t.open_time || !t.close_time) return "open";
    try {
      const o = new Date(t.open_time).getTime();
      const c = new Date(t.close_time).getTime();
      const days = Math.round((c - o) / (1000 * 60 * 60 * 24));
      return days <= 0 ? "open" : `${days}d`;
    } catch {
      return "open";
    }
  })();
  const reason = `${t.pair ?? "—"} · ${t.outcome ?? String(t.direction ?? "—")}`;
  const returnPct = isMissing(t.pnl_pct)
    ? "—"
    : formatPct(t.pnl_pct as number, 1, true);
  return { date: dateStr, side, reason, returnPct, duration };
}

export default function BacktesterPage() {
  const router = useRouter();
  const summaryQuery = useBacktestSummary();
  const tradesQuery = useBacktestTrades(50);
  const optunaQuery = useOptunaRuns(5);
  const equityQuery = useEquityCurve();

  // Derive KPI strip from /backtest/summary
  const kpis = (() => {
    const s = summaryQuery.data;
    if (!s) {
      return [
        { label: "Total return", value: "—", subtitle: "loading" },
        { label: "CAGR", value: "—", subtitle: "loading" },
        { label: "Sharpe", value: "—", subtitle: "loading" },
        { label: "Max drawdown", value: "—", subtitle: "loading" },
        { label: "Win rate", value: "—", subtitle: "loading" },
      ];
    }
    const totalReturn = s.avg_pnl_pct;  // closest proxy until full equity curve
    return [
      {
        label: "Avg PnL",
        value: isMissing(totalReturn) ? "—" : formatPct(totalReturn as number, 1, true),
        subtitle: `n = ${s.total_trades ?? "—"} trades`,
        valueColor: ((totalReturn ?? 0) >= 0 ? "success" : "danger") as "success" | "danger",
        subtitleDirection: ((totalReturn ?? 0) >= 0 ? "up" : "down") as "up" | "down",
      },
      {
        label: "Win rate",
        value: isMissing(s.win_rate_pct) ? "—" : formatPct(s.win_rate_pct as number, 0),
        subtitle: `n = ${s.total_trades ?? "—"} trades`,
      },
      {
        label: "Sharpe",
        value: isMissing(s.sharpe_ratio) ? "—" : formatNumber(s.sharpe_ratio as number, 2),
        subtitle: "live engine",
        valueColor: "accent" as const,
      },
      {
        label: "Max drawdown",
        value: isMissing(s.max_drawdown_pct) ? "—" : formatPct(s.max_drawdown_pct as number, 1, true),
        subtitle: "peak-to-trough",
        valueColor: "danger" as const,
        subtitleDirection: "down" as const,
      },
      {
        label: "Trades",
        value: formatNumber(s.total_trades ?? 0),
        subtitle: "in window",
      },
    ];
  })();

  // Map live trades to the table shape; show last 8
  const allTrades = (tradesQuery.data?.trades ?? []).map(rowToTrade);
  const recentTrades = allTrades.slice(0, 8);
  const tradesCount = tradesQuery.data?.count ?? 0;

  // ── Optuna runs from /backtest/optuna-runs ────────────────────────────────
  const optunaRuns: OptunaRun[] = (() => {
    const rows = optunaQuery.data?.runs ?? [];
    if (rows.length === 0) {
      // Truthful empty-state — frontend mock is gone, this surfaces honestly.
      return [];
    }
    return rows.map((r) => ({
      rank:      r.rank,
      params:    r.params || "(no params recorded)",
      sharpe:    r.value != null ? r.value.toFixed(2) : "—",
      returnPct: r.state || "—",
    }));
  })();
  const optunaFooter = (() => {
    const src = optunaQuery.data?.source;
    const err = optunaQuery.data?.error;
    if (err) return `No Optuna runs yet — ${err}`;
    if (src === "optuna_studies.sqlite") {
      return `Live · ${optunaQuery.data?.count ?? 0} completed trials · sorted by objective value desc`;
    }
    return "No tuning runs yet — run a hyperparameter sweep to populate.";
  })();

  // ── Equity curve from /backtest/equity-curve ──────────────────────────────
  const equityPoints = (() => {
    const pts = equityQuery.data?.points ?? [];
    return pts.map((p) => p.equity);
  })();
  const equityDateRange = (() => {
    const s = equityQuery.data?.summary;
    if (!s || !s.start || !s.end) return "no equity data yet";
    try {
      const startStr = new Date(s.start).toLocaleDateString("en-US", { year: "numeric", month: "short" });
      const endStr   = new Date(s.end).toLocaleDateString("en-US", { year: "numeric", month: "short" });
      return `${startStr} → ${endStr}`;
    } catch {
      return `${s.n_trades ?? 0} trades`;
    }
  })();

  return (
    <AppShell crumbs="Research" currentPage="Backtester">
      <PageHeader
        title="Backtester"
        subtitle="Composite signal backtested across 2023–2026. Optuna-tuned hyperparams."
      />

      {/* AUDIT-2026-05-06 (W2 Tier 6 F-LEVEL-1): Beginner gloss */}
      <BeginnerHint title="What is backtesting?">
        Backtesting replays the model&rsquo;s rules across years of
        historical data, asking: &ldquo;If I had used this exact
        strategy in the past, what would I have made or lost?&rdquo;
        It&rsquo;s the single best sanity-check we have. Pay attention
        to <strong className="text-text-primary">max drawdown</strong>
        (worst losing streak) — past performance doesn&rsquo;t
        guarantee future returns, but a strategy with terrible
        backtest drawdowns won&rsquo;t magically become good in
        production.
      </BeginnerHint>

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
        <EquityCurve dateRange={equityDateRange} points={equityPoints} />
        {optunaRuns.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-default bg-bg-1 p-4 text-center text-xs text-text-muted">
            <div className="mb-2 font-medium uppercase tracking-wider">Optuna studies</div>
            {optunaFooter}
          </div>
        ) : (
          <OptunaTable runs={optunaRuns} footer={optunaFooter} />
        )}
      </div>

      {/* Trades table */}
      {recentTrades.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border-default p-6 text-center text-sm text-muted-foreground">
          {tradesQuery.isLoading
            ? "Loading recent trades…"
            : tradesQuery.isError
              ? "Couldn't load trades — try refreshing in 30 seconds."
              : "No trades on this strategy yet — run a backtest to populate."}
        </div>
      ) : (
        <TradesTable
          trades={recentTrades}
          title="Recent trades - signal-driven"
          count={`last ${recentTrades.length} of ${tradesCount}`}
        />
      )}
    </AppShell>
  );
}
