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
  isStrongSignal,
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

// AUDIT-2026-05-05 (P0-MTF, P0-COMPOSITE): the prior `timeframes` array
// + `compositeFallback` were 100% hardcoded mock data — the timeframe
// strip showed 1m/5m/15m/30m tiles that DON'T EXIST in the engine
// (TIMEFRAMES = ['1h','4h','1d','1w','1M'] per crypto_model_core.py:87)
// and composite layer scores (Tech 82 / Macro 74 / etc.) were demo
// numbers with no backend equivalent. Replaced below with live data.
//
// Per-layer scores (Technical/Macro/Sentiment/On-chain) don't exist as
// distinct backend fields yet — composite_signal.py blends them into
// confidence_avg_pct without exposing intermediate weights. Until the
// backend ships per-layer scoring, the layer breakdown shows the
// composite + an honest "per-layer breakdown not in V1" note.

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

/** Defensive number coercion — daily_signals rows from older engine
 *  versions can have any of these fields as string, null, or undefined.
 *  Only return a number if the value cleanly coerces to a finite one. */
function _toFiniteNumber(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Coerce a value that should be a string but might be null/number/etc. */
function _toCleanString(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  return s.length > 0 && s.toLowerCase() !== "nan" ? s : null;
}

/** Compress consecutive same-direction rows into transition entries.
 *  Each kept row is the FIRST scan that flipped to a new direction.
 *  Return % is computed from price at this transition vs price at the
 *  next transition (i.e. the holding period of the previous direction).
 *
 *  AUDIT-2026-05-05 (HOTFIX): hardened against type drift in
 *  daily_signals rows. Pre-fix, calling .toFixed() on a null/string
 *  mtf_alignment crashed the page (caught by the H1 error boundary).
 *  Now every numeric read is coerced through _toFiniteNumber and every
 *  string read through _toCleanString. */
function _deriveTransitions(rows: SignalHistoryRow[]): HistoryEntry[] {
  if (!Array.isArray(rows) || rows.length === 0) return [];
  try {
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
    return transitions.slice(0, 6).map((t, i) => {
      const next = transitions[i + 1];
      const priceNow = _toFiniteNumber(t.row.price_usd);
      const pricePrev = next ? _toFiniteNumber(next.row.price_usd) : null;
      const ret =
        priceNow !== null && pricePrev !== null && pricePrev > 0
          ? ((priceNow - pricePrev) / pricePrev) * 100
          : null;
      const noteParts: string[] = [];
      const regime = _toCleanString(t.row.regime);
      if (regime) noteParts.push(regime.replace(/^Regime:\s*/i, "").trim());
      const conf = _toFiniteNumber(t.row.confidence_avg_pct);
      if (conf !== null) noteParts.push(`conf ${Math.round(conf)}%`);
      const mtf = _toFiniteNumber(t.row.mtf_alignment);
      if (mtf !== null) noteParts.push(`mtf ${mtf.toFixed(2)}`);
      const ts = _toCleanString(t.row.scan_timestamp) ?? "";
      return {
        timestamp: ts ? _formatTs(ts) : "—",
        signal: t.signal,
        note: noteParts.length ? noteParts.join(" · ") : "—",
        returnPct: _formatReturn(ret),
      };
    });
  } catch (err) {
    // Last-resort guard — empty entries beat a crashed page.
    // eslint-disable-next-line no-console
    console.error("[signals] _deriveTransitions failed", err);
    return [];
  }
}

// Engine TF order (crypto_model_core.py:87) — defines tile sequence.
const _ENGINE_TFS = ["1h", "4h", "1d", "1w", "1M"] as const;

export default function SignalsPage() {
  const [activeCoinIdx, setActiveCoinIdx] = useState(0);
  // Default to 1d (index 2 in the 5-element engine TF list).
  const [activeTimeframe, setActiveTimeframe] = useState(2);
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
      // AUDIT-2026-05-06 (P1-D): directionToSignalType is now canonical
      // 3-tier (lib/signal-types) — collapses STRONG SELL → "sell" etc.
      // internally. The intensity flows through signalStrength below.
      signal: directionToSignalType(detail.direction),
      signalStrength: detail.high_conf || isStrongSignal(detail.direction)
        ? "strong"
        : "moderate",
      timeframe: "1d",
      regime: regimeToDisplay(detail.regime ?? detail.regime_label ?? null),
      confidence: isMissing(detail.confidence_avg_pct)
        ? "—"
        : `${Math.round(detail.confidence_avg_pct as number)}%`,
      regimeAge: "—",  // TODO(D-ext): regime_age_days from regime_history join
    };
  })();

  // AUDIT-2026-05-05 (P0-MTF): timeframes wired to detail.timeframes.
  // Engine returns a dict keyed by '1h'/'4h'/'1d'/'1w'/'1M' — we
  // surface them as 5 tiles in fixed order. Direction → buy/hold/sell;
  // 'NO DATA' / 'LOW VOL' both render as hold.
  // Hardened against type drift via _toCleanString / _toFiniteNumber.
  const timeframes: { label: string; signal: SignalType; score: number }[] = (() => {
    try {
      const tfDict = (detail?.timeframes ?? {}) as Record<
        string,
        { direction?: unknown; confidence?: unknown } | undefined
      >;
      return _ENGINE_TFS.map((tf) => {
        const row = tfDict[tf] ?? {};
        const dir = (_toCleanString(row.direction) ?? "NO DATA").toUpperCase();
        const sig: SignalType = dir.includes("BUY")
          ? "buy"
          : dir.includes("SELL")
            ? "sell"
            : "hold";
        const conf = _toFiniteNumber(row.confidence);
        return { label: tf, signal: sig, score: conf !== null ? Math.round(conf) : 0 };
      });
    } catch {
      return _ENGINE_TFS.map((tf) => ({ label: tf, signal: "hold" as SignalType, score: 0 }));
    }
  })();

  // AUDIT-2026-05-05 (P0-COMPOSITE): composite score is the engine's
  // confidence_avg_pct (0-100). Per-layer scoring not yet in backend.
  const compositeFallback = (() => {
    const composite = _toFiniteNumber(detail?.confidence_avg_pct);
    return {
      score: composite ?? 0,
      layers: [] as { name: string; score: number }[],
      weightsNote: detail
        ? `Composite confidence ${composite !== null ? composite.toFixed(1) + "%" : "—"}. Per-layer breakdown (Technical / Macro / Sentiment / On-chain) not in V1 — backend exposes the blended composite only.`
        : "Run a scan to populate.",
    };
  })();

  // AUDIT-2026-05-06 (P1-B): technical indicators were reading
  // `detail.rsi` / `.macd` / `.adx` at top level, but the engine puts
  // them under `detail.timeframes['<active-tf>'].rsi`. Pre-fix every
  // tile rendered "—" "unavailable". Now reads from the active TF
  // keyed off `activeTimeframe` index so changing the tile updates
  // the indicator panel beneath.
  const technicalIndicators = (() => {
    if (!detail) {
      return [
        { label: "RSI (14)", value: "—", subtext: "loading", variant: "default" as const },
        { label: "MACD hist", value: "—", subtext: "loading", variant: "default" as const },
        { label: "Supertrend", value: "—", subtext: "loading", variant: "default" as const },
        { label: "ADX (14)", value: "—", subtext: "loading", variant: "default" as const },
      ];
    }
    const activeTf = _ENGINE_TFS[activeTimeframe] ?? "1d";
    const tfDict = (detail.timeframes ?? {}) as Record<string, Record<string, unknown> | undefined>;
    const tfRow = tfDict[activeTf] ?? {};
    const rsi = _toFiniteNumber(tfRow.rsi);
    // engine key is `macd_div` (a string like "Bullish (hidden) (Strong)")
    // — there's no scalar MACD-histogram field. Surface the divergence
    // text instead with bull/bear/neutral classification.
    const macdDivRaw = _toCleanString(tfRow.macd_div);
    const macdDiv = macdDivRaw && macdDivRaw !== "None (N/A)" ? macdDivRaw : null;
    const adx = _toFiniteNumber(tfRow.adx);
    const supertrend = _toCleanString(tfRow.supertrend);
    return [
      {
        label: "RSI (14)",
        value: rsi === null ? "—" : formatNumber(rsi, 1),
        subtext: rsi === null
          ? "unavailable"
          : rsi >= 70
            ? "overbought"
            : rsi <= 30
              ? "oversold"
              : "neutral",
        variant: (rsi === null
          ? "default"
          : rsi >= 70 || rsi <= 30
            ? "warning"
            : "default") as "default" | "warning" | "success",
      },
      {
        label: "MACD",
        value: macdDiv ? macdDiv.split(" ")[0] : "—",
        subtext: macdDiv
          ? macdDiv.toLowerCase().includes("bull")
            ? "bullish divergence"
            : macdDiv.toLowerCase().includes("bear")
              ? "bearish divergence"
              : "neutral"
          : "no divergence",
        variant: (macdDiv && macdDiv.toLowerCase().includes("bull")
          ? "success"
          : macdDiv && macdDiv.toLowerCase().includes("bear")
            ? "warning"
            : "default") as "default" | "warning" | "success",
      },
      {
        label: "Supertrend",
        value: supertrend ?? "—",
        subtext: `${activeTf} regime`,
        variant: (supertrend?.toLowerCase().includes("up")
          ? "success"
          : supertrend?.toLowerCase().includes("down")
            ? "warning"
            : "default") as "default" | "warning" | "success",
      },
      {
        label: "ADX (14)",
        value: adx === null ? "—" : formatNumber(adx, 1),
        subtext: adx === null
          ? "unavailable"
          : adx > 25
            ? "strong trend"
            : adx > 15
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
