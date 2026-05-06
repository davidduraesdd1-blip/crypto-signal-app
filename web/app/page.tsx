"use client";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { DataSourceRow } from "@/components/data-source-badge";
import { SignalCard, type SignalType } from "@/components/signal-card";
import { MacroStrip } from "@/components/macro-strip";
import { Watchlist } from "@/components/watchlist";
import { BacktestCard } from "@/components/backtest-card";
import { BeginnerHint } from "@/components/beginner-hint";
import { useHomeSummary } from "@/hooks/use-home-summary";
import { useBacktestSummary } from "@/hooks/use-backtester";
import { useMacroStrip } from "@/hooks/use-macro";
import { useWatchlist } from "@/hooks/use-watchlist";
import { useHealth } from "@/hooks/use-diagnostics";
import {
  directionToSignalType,
  formatConfidence,
  formatNumber,
  formatPct,
  isMissing,
  regimeToDisplay,
} from "@/lib/format";

// AUDIT-2026-05-06 (Everything-Live): MacroStrip + Watchlist + DataSourceRow
// were hardcoded mock literals pre-fix. Now wired to:
//   - useMacroStrip()   → /macro/strip
//   - useWatchlist()    → /home/watchlist (price + 24h delta + sparkline)
//   - useHealth()       → /health (feed status drives DataSourceRow pills)
// Hero cards + Backtest KPIs were already live (D4b).

// ─── Build sparkline polyline from raw closes ──────────────────────────────

function _closesToPolyline(closes: number[], height = 22, width = 80): string {
  if (!closes || closes.length < 2) return "";
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const stepX = width / (closes.length - 1);
  return closes
    .map((c, i) => {
      const x = (i * stepX).toFixed(0);
      // Invert Y so higher prices render higher on screen
      const y = (height - ((c - min) / range) * height).toFixed(0);
      return `${x},${y}`;
    })
    .join(" ");
}

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
  const macroQuery = useMacroStrip();
  const watchlistQuery = useWatchlist(6, 24);
  const healthQuery = useHealth();

  // ── Live MacroStrip from /macro/strip ────────────────────────────────────
  const macroItems = (() => {
    const m = macroQuery.data;
    if (!m) {
      // Loading / error — render placeholders rather than pretend live.
      return [
        { label: "BTC Dominance", value: "—", sub: "loading" },
        { label: "Fear & Greed",  value: "—", sub: "loading" },
        { label: "DXY",           value: "—", sub: "loading" },
        { label: "Funding (BTC)", value: "—", sub: "loading" },
        { label: "Regime (macro)", value: "—", sub: "loading" },
      ];
    }
    const fg = m.fear_greed?.value;
    const fgLabel = m.fear_greed?.label ?? "—";
    const fgColor = (
      fgLabel?.toLowerCase().includes("greed")
        ? ("warning" as const)
        : fgLabel?.toLowerCase().includes("fear")
          ? ("accent" as const)
          : undefined
    );
    const macroSig = m.macro_signal?.label ?? "—";
    const macroNice = (
      macroSig === "RISK_ON" ? "Risk-on"
      : macroSig === "RISK_OFF" ? "Risk-off"
      : macroSig === "MILD_RISK_ON" ? "Mild risk-on"
      : macroSig === "MILD_RISK_OFF" ? "Mild risk-off"
      : macroSig === "NEUTRAL" ? "Neutral"
      : "—"
    );
    const score = m.macro_signal?.score;
    const fundingPct = m.btc_funding?.value;
    return [
      {
        label: "BTC Dominance",
        value: m.btc_dominance?.value != null ? `${m.btc_dominance.value.toFixed(1)}%` : "—",
        sub: m.btc_dominance?.alt_season_label ?? (m.btc_dominance?.source ?? "—"),
      },
      {
        label: "Fear & Greed",
        value: fg != null ? String(fg) : "—",
        sub: fgLabel ?? "—",
        ...(fgColor ? { subColor: fgColor } : {}),
      },
      {
        label: "DXY",
        value: m.dxy?.value != null ? m.dxy.value.toFixed(2) : "—",
        sub: m.dxy?.trend ? m.dxy.trend.toLowerCase().replace("_", " ") : "—",
      },
      {
        label: "Funding (BTC)",
        value: fundingPct != null ? `${fundingPct >= 0 ? "+" : ""}${fundingPct.toFixed(3)}%` : "—",
        sub: m.btc_funding?.signal?.toLowerCase() ?? "8h avg",
      },
      {
        label: "Regime (macro)",
        value: macroNice,
        sub: score != null ? `score ${score}` : "—",
        subColor: "accent" as const,
      },
    ];
  })();

  // ── Live watchlist from /home/watchlist ──────────────────────────────────
  const watchlistItems = (() => {
    const items = watchlistQuery.data?.items ?? [];
    if (items.length === 0) return [] as Array<{
      ticker: string; price: string; change: string;
      changeDirection: "up" | "down"; sparklinePoints: string;
    }>;
    return items.map((it) => {
      const change = it.change_24h_pct;
      const dir: "up" | "down" = (change ?? 0) >= 0 ? "up" : "down";
      return {
        ticker: it.ticker,
        price: it.price != null
          ? (it.price >= 1000 ? `$${it.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : `$${it.price.toFixed(2)}`)
          : "—",
        change: change != null ? `${Math.abs(change).toFixed(2)}%` : "—",
        changeDirection: dir,
        sparklinePoints: _closesToPolyline(it.sparkline ?? []),
      };
    });
  })();

  // ── DataSourceRow from /health ───────────────────────────────────────────
  const dataSources = (() => {
    const h = healthQuery.data as undefined | {
      status?: string;
      feeds?: { status?: string; pairs_live?: string[]; pairs_stale?: string[] };
      scan?: { running?: boolean; timestamp?: string | null };
    };
    if (!h) {
      return [
        { name: "Render API", status: "cached" as const, statusLabel: "loading" },
        { name: "WS feeds",   status: "cached" as const, statusLabel: "loading" },
        { name: "Scanner",    status: "cached" as const, statusLabel: "loading" },
      ];
    }
    const feedStatus = h.feeds?.status === "DEGRADED" ? "cached" : "live";
    const stale = h.feeds?.pairs_stale?.length ?? 0;
    const live = h.feeds?.pairs_live?.length ?? 0;
    const scanLive = !h.scan?.running;
    return [
      { name: "Render API", status: "live" as const, statusLabel: h.status === "ok" ? "live" : (h.status ?? "live") },
      { name: "WS feeds",   status: feedStatus as "live" | "cached", statusLabel: stale > 0 ? `${live} live · ${stale} stale` : `${live} live` },
      { name: "Scanner",    status: (scanLive ? "live" : "cached") as "live" | "cached", statusLabel: h.scan?.timestamp ? "scan idle" : "no scan yet" },
    ];
  })();

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

      {/* AUDIT-2026-05-06 (W2 Tier 6 F-LEVEL-1): Beginner gloss */}
      <BeginnerHint title="What you're looking at">
        Each card below is one cryptocurrency with a quick verdict
        (Buy / Hold / Sell), how confident the model is, and the
        current market &ldquo;regime&rdquo; (Trending / Ranging /
        Risk-off). The model never guarantees a profit — it surfaces
        the strongest opportunities and risks. Always size positions
        to your own risk tolerance.
      </BeginnerHint>

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
