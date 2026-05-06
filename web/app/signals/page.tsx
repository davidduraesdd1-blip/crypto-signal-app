"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { CoinPicker } from "@/components/coin-picker";
import { TimeframeStrip, type SignalType } from "@/components/timeframe-strip";
import { SignalHero } from "@/components/signal-hero";
import { PriceChart } from "@/components/price-chart";
import { CompositeScore } from "@/components/composite-score";
import { IndicatorTile, IndicatorGrid } from "@/components/indicator-tile";
import { SignalHistory } from "@/components/signal-history";
import { useSignals, useSignalDetail, useSignalHistory } from "@/hooks/use-signals";
import { useTriggerScan } from "@/hooks/use-scan";
import { ApiError } from "@/lib/api";
import { useUserLevel } from "@/providers/user-level-provider";
import {
  directionToSignalType,
  formatNumber,
  formatPct,
  isMissing,
  regimeToDisplay,
} from "@/lib/format";

// AUDIT-2026-05-03 (D4b): Signals page wired:
// - Coins list (CoinPicker) derived from useSignals() top-N rows
// - Hero card (SignalHero) wired to useSignalDetail(activePair)
// - Technical-indicator tile values wired from snap_* fields when
//   present in /signals/{pair} response
// Multi-timeframe strip + composite-score + on-chain/sentiment tiles
// + signal history stay as v0 mock with TODO(D-ext) — they need
// endpoints that don't exist yet (/signals/{pair}/timeframes,
// /signals/{pair}/composite-layers, /signals/history). Each is a
// future D-extension.

// ─── Stubs (TODO(D-ext): wire when endpoints exist) ────────────────────────

const timeframes: { label: string; signal: SignalType; score: number }[] = [
  // TODO(D-ext): GET /signals/{pair}/timeframes
  { label: "1m", signal: "hold", score: 52 },
  { label: "5m", signal: "buy", score: 64 },
  { label: "15m", signal: "buy", score: 70 },
  { label: "30m", signal: "buy", score: 73 },
  { label: "1h", signal: "buy", score: 76 },
  { label: "4h", signal: "buy", score: 80 },
  { label: "1d", signal: "buy", score: 78 },
  { label: "1w", signal: "buy", score: 84 },
];

const compositeFallback = {
  // TODO(D-ext): GET /signals/{pair}/composite-layers
  score: 78.4,
  layers: [
    { name: "Layer 1 · Technical", score: 82 },
    { name: "Layer 2 · Macro", score: 74 },
    { name: "Layer 3 · Sentiment", score: 71 },
    { name: "Layer 4 · On-chain", score: 86 },
  ],
  weightsNote:
    "Composite = weighted avg per regime-adjusted weights. Current regime weights: tech 0.30, macro 0.15, sentiment 0.20, on-chain 0.35.",
};

const onChainIndicators = [
  // TODO(D-ext): pull from /onchain/dashboard for the selected pair
  { label: "MVRV-Z", value: "—", subtext: "live in /on-chain", variant: "default" as const },
  { label: "SOPR", value: "—", subtext: "live in /on-chain", variant: "default" as const },
  { label: "Net flow", value: "—", subtext: "live in /on-chain", variant: "default" as const },
  { label: "Whale", value: "—", subtext: "live in /on-chain", variant: "default" as const },
];

// AUDIT-2026-05-05 (P0-8): user-visible "TODO(D-ext)" subtext strings
// were leaking dev jargon to end-users. Replaced with honest "not in V1"
// / "backfill pending" copy. The internal dev-side TODOs that flag the
// actual missing endpoints stay above each block as comments.

// TODO(internal, post-V1): wire /sentiment endpoint — F&G live in /home,
// funding rates derivable from existing data_feeds.py funding fetcher,
// Google Trends from pytrends with rate-limit fallback, news sentiment
// is the gap that needs a new feed source.
const sentimentIndicators = [
  { label: "Fear&Greed", value: "—", subtext: "see Home", variant: "default" as const },
  { label: "Funding", value: "—", subtext: "backfill pending", variant: "default" as const },
  { label: "Google trends", value: "—", subtext: "not in V1", variant: "default" as const },
  { label: "News sent.", value: "—", subtext: "not in V1", variant: "default" as const },
];

// TODO(internal, post-V1): some are derivable from /signals enriched,
// others (token unlocks) need a new /token-unlocks endpoint backed by
// cryptorank.io.
const priceIndicators = [
  { label: "Vol (24h)", value: "—", subtext: "backfill pending", variant: "default" as const },
  { label: "ATR (14d)", value: "—", subtext: "backfill pending", variant: "default" as const },
  { label: "Beta vs S&P", value: "—", subtext: "not in V1", variant: "default" as const },
  { label: "Funding (8h)", value: "—", subtext: "backfill pending", variant: "default" as const },
  { label: "Token unlocks", value: "—", subtext: "not in V1", variant: "default" as const },
];

// AUDIT-2026-05-05 (P0-7): the v0 mock signal-history block (Apr 12,
// Mar 28, etc.) was here. Replaced with live data via useSignalHistory
// — see deriveSignalHistory() inside SignalsPage.
import type { SignalHistoryRow } from "@/lib/api";
import type { HistoryEntry } from "@/components/signal-history";

/** Map a raw daily_signals row's direction column to the component's
 *  three-tier signal type. Engine emits 'BUY', 'STRONG BUY', 'SELL',
 *  'STRONG SELL', 'HOLD', 'NEUTRAL' etc. */
function _mapDirectionToSignal(dir: string | null | undefined): SignalType {
  const d = (dir ?? "").toUpperCase();
  if (d.includes("BUY")) return "buy";
  if (d.includes("SELL")) return "sell";
  return "hold";
}

/** Format a signed % return string ("+ 12.6%" / "− 6.2%"). */
function _formatReturn(pct: number | null): string {
  if (pct === null || !Number.isFinite(pct)) return "—";
  const sign = pct >= 0 ? "+ " : "− ";
  return `${sign}${Math.abs(pct).toFixed(1)}%`;
}

/** Format a daily_signals.scan_timestamp ISO string into "Apr 12 08:20". */
function _formatTs(iso: string): string {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const month = d.toLocaleString("en-US", { month: "short" });
    const day = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${month} ${day} ${hh}:${mm}`;
  } catch {
    return iso;
  }
}

/** Compress consecutive same-direction rows into transition entries.
 *  Each kept row is the FIRST scan that flipped to a new direction.
 *  Return % is computed from price at this transition vs price at the
 *  next transition (i.e. the holding period of the previous direction). */
function _deriveTransitions(rows: SignalHistoryRow[]): HistoryEntry[] {
  // Backend returns oldest-first via .tail() — flip to newest-first.
  const desc = [...rows].reverse();
  const transitions: { row: SignalHistoryRow; signal: SignalType }[] = [];
  let prevSignal: SignalType | null = null;
  for (const row of desc) {
    const sig = _mapDirectionToSignal(row.direction);
    if (sig !== prevSignal) {
      transitions.push({ row, signal: sig });
      prevSignal = sig;
    }
  }
  // Compute return between this transition and the previous one (older).
  return transitions.slice(0, 6).map((t, i) => {
    const next = transitions[i + 1];
    const priceNow = t.row.price_usd;
    const pricePrev = next?.row.price_usd ?? null;
    const ret =
      priceNow != null && pricePrev != null && pricePrev > 0
        ? ((priceNow - pricePrev) / pricePrev) * 100
        : null;
    const noteParts: string[] = [];
    if (t.row.regime) noteParts.push(t.row.regime.replace(/^Regime:\s*/i, "").trim());
    if (t.row.confidence_avg_pct != null) noteParts.push(`conf ${Math.round(t.row.confidence_avg_pct)}%`);
    if (t.row.mtf_alignment != null) noteParts.push(`mtf ${t.row.mtf_alignment.toFixed(2)}`);
    return {
      timestamp: _formatTs(t.row.scan_timestamp),
      signal: t.signal,
      note: noteParts.length ? noteParts.join(" · ") : "—",
      returnPct: _formatReturn(ret),
    };
  });
}

export default function SignalsPage() {
  const [activeCoinIdx, setActiveCoinIdx] = useState(0);
  const [activeTimeframe, setActiveTimeframe] = useState(6); // 1d default
  const { level } = useUserLevel();

  // Derive the coin list from /signals top-N rows
  const signalsQuery = useSignals();
  // D4d: scan trigger button — invalidates signals + home + scan-status
  // queries on success so the page re-fetches the freshly-scanned data.
  const triggerScan = useTriggerScan();
  const allRows = signalsQuery.data?.results ?? [];
  const coins = allRows.slice(0, 5).map((r) => r.pair.split("/")[0]);
  const extraCoinsCount = Math.max(0, allRows.length - 5);
  const activePair = allRows[activeCoinIdx]?.pair ?? null;

  // Per-pair detail for the hero card + technical tiles
  const detailQuery = useSignalDetail(activePair);
  const detail = detailQuery.data;

  // P0-7: live signal-history transitions for this pair
  const historyQuery = useSignalHistory(activePair, 50);
  const signalHistoryEntries = _deriveTransitions(historyQuery.data?.results ?? []);

  // Build the SignalHero props from the detail row
  const heroData = (() => {
    if (!detail) {
      return {
        ticker: activePair ? activePair.replace("/", " / ") : "— / —",
        name: activePair ? activePair.split("/")[0] : "—",
        price: "—",
        change24h: "—",
        change30d: "—",
        change1y: "—",
        signal: "hold" as SignalType,
        signalStrength: "—",
        timeframe: "1d",
        regime: "—",
        confidence: "—",
        regimeAge: "—",
      };
    }
    // AUDIT-2026-05-05 (P0-3): change_30d_pct + change_1y_pct now wired
    // in the engine scan-result dict (crypto_model_core.py:4794). Old
    // TODO(D-ext) comments retired.
    const change24 = detail.change_24h_pct;
    const change30 = (detail as { change_30d_pct?: number | null }).change_30d_pct;
    const change1y = (detail as { change_1y_pct?: number | null }).change_1y_pct;
    return {
      ticker: detail.pair.replace("/", " / "),
      name: detail.pair.split("/")[0],
      price: isMissing(detail.price ?? detail.price_usd)
        ? "—"
        : formatNumber((detail.price ?? detail.price_usd) as number, 2),
      change24h: isMissing(change24) ? "—" : formatPct(change24 as number, 2, true),
      change30d: isMissing(change30) ? "—" : formatPct(change30 as number, 2, true),
      change1y: isMissing(change1y) ? "—" : formatPct(change1y as number, 2, true),
      signal: directionToSignalType(detail.direction) as SignalType,
      signalStrength: detail.high_conf ? "strong" : "moderate",
      timeframe: "1d",
      regime: regimeToDisplay(detail.regime ?? detail.regime_label ?? null),
      confidence: isMissing(detail.confidence_avg_pct)
        ? "—"
        : `${Math.round(detail.confidence_avg_pct as number)}%`,
      regimeAge: "—",  // TODO(D-ext): regime_age_days from regime_history join
    };
  })();

  // Technical indicators from snap_* fields when present
  const technicalIndicators = (() => {
    if (!detail) {
      return [
        { label: "RSI (14)", value: "—", subtext: "loading", variant: "default" as const },
        { label: "MACD hist", value: "—", subtext: "loading", variant: "default" as const },
        { label: "Supertrend", value: "—", subtext: "loading", variant: "default" as const },
        { label: "ADX (14)", value: "—", subtext: "loading", variant: "default" as const },
      ];
    }
    const rsi = detail.rsi as number | undefined;
    const macd = detail.macd as number | undefined;
    const adx = detail.adx as number | undefined;
    return [
      {
        label: "RSI (14)",
        value: isMissing(rsi) ? "—" : formatNumber(rsi as number, 1),
        subtext: isMissing(rsi)
          ? "unavailable"
          : (rsi as number) >= 70
            ? "overbought"
            : (rsi as number) <= 30
              ? "oversold"
              : "neutral",
        variant: (isMissing(rsi)
          ? "default"
          : (rsi as number) >= 70
            ? "warning"
            : "default") as "default" | "warning" | "success",
      },
      {
        label: "MACD",
        value: isMissing(macd) ? "—" : formatNumber(macd as number, 2),
        subtext: isMissing(macd)
          ? "unavailable"
          : (macd as number) >= 0
            ? "bullish"
            : "bearish",
        variant: (isMissing(macd)
          ? "default"
          : (macd as number) >= 0
            ? "success"
            : "warning") as "default" | "warning" | "success",
      },
      {
        label: "Supertrend",
        value: directionToSignalType(detail.direction).toUpperCase(),
        subtext: regimeToDisplay(detail.regime ?? null),
        variant: "success" as const,
      },
      {
        label: "ADX (14)",
        value: isMissing(adx) ? "—" : formatNumber(adx as number, 1),
        subtext: isMissing(adx)
          ? "unavailable"
          : (adx as number) > 25
            ? "strong trend"
            : (adx as number) > 15
              ? "weak trend"
              : "no trend",
        variant: "default" as const,
      },
    ];
  })();

  return (
    <AppShell crumbs="Markets" currentPage="Signals">
      <PageHeader
        title="Signal detail"
        subtitle="Layer-by-layer composite signal breakdown for a single coin."
      >
        <div className="flex flex-wrap items-center gap-2">
          {coins.length > 0 ? (
            <CoinPicker
              coins={coins}
              activeIndex={activeCoinIdx}
              extraCount={extraCoinsCount}
              onSelect={setActiveCoinIdx}
            />
          ) : (
            <div className="text-xs text-text-muted">
              {signalsQuery.isLoading
                ? "Loading coins…"
                : signalsQuery.isError
                  ? "Couldn't load coins"
                  : "Run a scan to populate"}
            </div>
          )}
          <button
            type="button"
            onClick={() => triggerScan.mutate()}
            disabled={triggerScan.isPending}
            className="inline-flex min-h-[36px] items-center gap-1.5 rounded-md border border-accent-brand bg-accent-soft px-3 py-1.5 text-xs font-medium text-accent-brand transition-colors hover:bg-accent-brand/10 disabled:opacity-60 disabled:cursor-wait"
            title="Trigger a fresh scan; results invalidate the signals + home caches"
          >
            <span>{triggerScan.isPending ? "⟳" : "▶"}</span>
            <span>{triggerScan.isPending ? "Scanning…" : "Scan now"}</span>
          </button>
        </div>
      </PageHeader>

      {/* Scan trigger feedback */}
      {triggerScan.isError && (
        <div className="mb-3 rounded-lg border border-danger/30 bg-danger/5 p-2 text-xs text-danger">
          {(() => {
            // AUDIT-2026-05-03 (D4 audit, HIGH): use ApiError
            // discriminators for actionable error copy instead of
            // raw Python detail strings.
            const err = triggerScan.error;
            if (err instanceof ApiError) {
              if (err.isAuthError) return "Scan trigger failed — API key missing or invalid. Set NEXT_PUBLIC_API_KEY in Vercel/local .env.local.";
              if (err.isRateLimited) return "Scan trigger rate-limited — wait a minute before retrying.";
              if (err.isGeoBlocked) return "Scan trigger blocked from this region — provider geo-block.";
            }
            return `Scan trigger failed — ${String(err?.message ?? "unknown error")}`;
          })()}
        </div>
      )}
      {triggerScan.isSuccess && triggerScan.data?.status === "started" && (
        <div className="mb-3 rounded-lg border border-success/30 bg-success/5 p-2 text-xs text-success">
          Scan started — results refresh automatically when complete (~30-60s)
        </div>
      )}
      {triggerScan.isSuccess && triggerScan.data?.status === "already_running" && (
        <div className="mb-3 rounded-lg border border-warning/30 bg-warning/5 p-2 text-xs text-warning">
          A scan is already running — wait for it to finish before triggering another
        </div>
      )}

      {/* Hero signal card */}
      <div className="mb-5">
        <SignalHero {...heroData} />
      </div>

      {/* AUDIT-2026-05-05 (P0-5): Beginner gets a "what does this mean
          for me?" hint per CLAUDE.md §7. Intermediate / Advanced see the
          numbers in the hero + composite cards and don't need the gloss. */}
      {level === "Beginner" && detail && (
        <div className="mb-5 rounded-xl border-l-[3px] border-accent-brand bg-bg-1 p-4">
          <div className="text-xs font-medium uppercase tracking-wider text-text-muted">
            What does this mean for me?
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">
            {(() => {
              const dir = (detail.direction ?? "").toUpperCase();
              const conf = detail.confidence_avg_pct;
              const tickName = detail.pair.split("/")[0];
              const confLabel =
                conf == null ? "moderate confidence" :
                conf >= 75 ? "high confidence" :
                conf >= 55 ? "moderate confidence" :
                "low confidence";
              if (dir.includes("BUY")) {
                return `${tickName} is showing upward momentum across multiple timeframes (${confLabel}). The model favors a long bias here. Always size to your risk tolerance — no signal is a guarantee.`;
              }
              if (dir.includes("SELL")) {
                return `${tickName} is showing downward pressure across multiple timeframes (${confLabel}). The model favors a short / cash bias here. Don't average down on losing positions.`;
              }
              return `${tickName} is in a sideways or transitional state — no clear edge right now (${confLabel}). The model recommends holding existing positions and waiting for a cleaner setup.`;
            })()}
          </p>
        </div>
      )}

      {/* Multi-timeframe strip */}
      <div className="mb-5 rounded-xl border border-border-default bg-bg-1 p-4">
        <div className="mb-2.5 flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
            Multi-timeframe signals · {coins[activeCoinIdx] ?? "—"}
          </span>
          <span className="text-xs text-text-muted">
            click a timeframe to drill in · selection drives every data section below
          </span>
        </div>
        <TimeframeStrip
          timeframes={timeframes}
          activeIndex={activeTimeframe}
          onSelect={setActiveTimeframe}
        />
      </div>

      {/* Price chart + Composite score */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="flex flex-col gap-4">
          <PriceChart />
          <IndicatorGrid columns={5}>
            {priceIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>
        <CompositeScore {...compositeFallback} />
      </div>

      {/* Technical / On-chain / Sentiment indicators */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Technical */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
            Technical indicators
          </div>
          <IndicatorGrid columns={2}>
            {technicalIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>

        {/* On-chain */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
            On-chain
          </div>
          <IndicatorGrid columns={2}>
            {onChainIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>

        {/* Sentiment */}
        <div className="rounded-xl border border-border-default bg-bg-1 p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wider text-text-muted">
            Sentiment
          </div>
          <IndicatorGrid columns={2}>
            {sentimentIndicators.map((ind) => (
              <IndicatorTile key={ind.label} {...ind} />
            ))}
          </IndicatorGrid>
        </div>
      </div>

      {/* Signal history — wired to /signals/history (P0-7) */}
      <SignalHistory
        entries={signalHistoryEntries}
        ticker={activePair ? activePair.split("/")[0] : "—"}
        isLoading={historyQuery.isLoading}
        error={historyQuery.error ? { message: (historyQuery.error as Error).message } : null}
      />
    </AppShell>
  );
}
