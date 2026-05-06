"use client";

import { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { RegimeCard, type RegimeState } from "@/components/regime-card";
import { RegimeTimeline, type TimelineState } from "@/components/regime-timeline";
import { MacroOverlay } from "@/components/macro-overlay";
import { RegimeWeights, type RegimeType } from "@/components/regime-weights";
import { Button } from "@/components/ui/button";
import { BeginnerHint } from "@/components/beginner-hint";
import { useRegimes, useRegimeWeights, useRegimeTimeline } from "@/hooks/use-regimes";
import { useMacroStrip } from "@/hooks/use-macro";
import type { TradingPair } from "@/lib/api-types";

// AUDIT-2026-05-03 (D4b): regime cards wired to GET /regimes/. The
// timeline + MacroOverlay + RegimeWeights stay as v0 mock until the
// downstream endpoints exist (regime_history with date strings,
// consolidated /macro endpoint). Each is decorative + visually
// anchors the page.

/** Map engine regime label → v0's RegimeState union */
function toRegimeState(label: string | null | undefined): RegimeState {
  if (!label) return "bear";
  const l = label.toLowerCase();
  if (l.includes("bull")) return "bull";
  if (l.includes("bear")) return "bear";
  if (l.includes("trans")) return "transition";
  if (l.includes("accum")) return "accumulation";
  if (l.includes("distrib")) return "distribution";
  if (l.includes("rang")) return "bear";  // "ranging" maps to neutral; v0 lacks that, fold into bear
  return "bear";
}

function pairToTicker(pair: string): string {
  return pair.split("/")[0] ?? pair;
}

// AUDIT-2026-05-06 (Everything-Live): timelineSegments + timelineDates +
// macroIndicators + regimeWeightColumns are no longer hardcoded — they
// derive from useRegimeTimeline / useMacroStrip / useRegimeWeights inside
// the component below.

// Map backend HMM regime taxonomy (CRISIS/TRENDING/RANGING/NORMAL) onto
// the existing 4 visual variants of the RegimeWeights component.
function _backendRegimeToVisual(regime: string): RegimeType {
  const r = regime.toUpperCase();
  if (r === "CRISIS") return "bear";       // ▼ defensive
  if (r === "TRENDING") return "bull";     // ▲ uptrend
  if (r === "RANGING") return "accumulation"; // ● sideways
  return "distribution";                    // ○ NORMAL / fallback
}

// Map regime-history state strings → TimelineState union for the bar.
function _toTimelineState(state: string | null | undefined): TimelineState {
  const s = (state ?? "").toLowerCase();
  if (s.includes("bull")) return "bull";
  if (s.includes("bear")) return "bear";
  if (s.includes("trans")) return "transition";
  if (s.includes("accum")) return "accumulation";
  if (s.includes("distrib")) return "distribution";
  return "bear"; // sideways / unknown — visually conservative
}

export default function RegimesPage() {
  const [selectedTicker, setSelectedTicker] = useState("BTC");
  const regimesQuery = useRegimes();
  const macroQuery = useMacroStrip();
  const weightsQuery = useRegimeWeights();
  const timelineQuery = useRegimeTimeline(`${selectedTicker}/USDT` as TradingPair, 90);

  // Map /regimes/ rows → RegimeCard props. `since` and `durationDays`
  // aren't in the API response; show "—" placeholders until
  // /regimes/{pair}/history wiring lands in a follow-up commit.
  const regimeStates = (() => {
    const rows = regimesQuery.data?.results ?? [];
    if (rows.length === 0) return [];
    return rows.slice(0, 8).map((row) => ({
      ticker: pairToTicker(row.pair),
      state: toRegimeState(row.regime),
      confidence: Math.round(row.confidence ?? 0),
      since: "—",
      durationDays: 0,
    }));
  })();

  const totalCount = regimesQuery.data?.count ?? 0;

  // ── Live macro indicators (6 items) ──────────────────────────────────────
  const macroIndicators = (() => {
    const m = macroQuery.data;
    if (!m) {
      return [
        { name: "BTC Dominance", value: "—", change: "loading", changeDirection: "up" as const, sentiment: "neutral" as const, sentimentLabel: "loading" },
        { name: "DXY",           value: "—", change: "loading", changeDirection: "up" as const, sentiment: "neutral" as const, sentimentLabel: "loading" },
        { name: "VIX",           value: "—", change: "loading", changeDirection: "up" as const, sentiment: "neutral" as const, sentimentLabel: "loading" },
        { name: "10Y yield",     value: "—", change: "loading", changeDirection: "up" as const, sentiment: "neutral" as const, sentimentLabel: "loading" },
        { name: "Fear & Greed",  value: "—", change: "loading", changeDirection: "up" as const, sentiment: "neutral" as const, sentimentLabel: "loading" },
        { name: "HY spreads",    value: "—", change: "loading", changeDirection: "up" as const, sentiment: "neutral" as const, sentimentLabel: "loading" },
      ];
    }
    const dxyTrend = m.dxy?.trend ?? "";
    const dxySent = dxyTrend === "WEAK_DOLLAR" ? "bull" : dxyTrend === "STRONG_DOLLAR" ? "bear" : "neutral";
    const vixVal = m.vix?.value ?? null;
    const vixSent = vixVal != null && vixVal < 18 ? "bull" : vixVal != null && vixVal > 25 ? "bear" : "neutral";
    const fgVal = m.fear_greed?.value ?? null;
    const yieldCurve = m.yield_curve ?? "";
    const yldSent = yieldCurve === "INVERTED" ? "bear" : yieldCurve === "NORMAL" ? "bull" : "neutral";
    const hy = m.hy_spreads?.value ?? null;
    const hySent = hy != null && hy < 350 ? "bull" : hy != null && hy > 500 ? "bear" : "neutral";

    return [
      {
        name: "BTC Dominance",
        value: m.btc_dominance?.value != null ? `${m.btc_dominance.value.toFixed(1)}%` : "—",
        change: m.btc_dominance?.alt_season_label ?? "—",
        changeDirection: "up" as const,
        sentiment: "neutral" as const,
        sentimentLabel: m.btc_dominance?.source ?? "—",
      },
      {
        name: "DXY",
        value: m.dxy?.value != null ? m.dxy.value.toFixed(2) : "—",
        change: dxyTrend ? dxyTrend.toLowerCase().replace("_", " ") : "—",
        changeDirection: dxySent === "bull" ? ("down" as const) : ("up" as const),
        sentiment: dxySent as "bull" | "bear" | "neutral",
        sentimentLabel: dxySent === "bull" ? "risk-on" : dxySent === "bear" ? "risk-off" : "neutral",
      },
      {
        name: "VIX",
        value: vixVal != null ? vixVal.toFixed(1) : "—",
        change: m.vix?.structure ? m.vix.structure.toLowerCase() : "—",
        changeDirection: vixSent === "bull" ? ("down" as const) : ("up" as const),
        sentiment: vixSent as "bull" | "bear" | "neutral",
        sentimentLabel: vixSent === "bull" ? "calm" : vixSent === "bear" ? "stressed" : "normal",
      },
      {
        name: "10Y yield",
        value: m.ten_yr_yield?.raw != null ? `${m.ten_yr_yield.raw.toFixed(2)}%` : (m.ten_yr_yield?.raw_10y != null ? `${m.ten_yr_yield.raw_10y.toFixed(2)}%` : "—"),
        change: yieldCurve ? yieldCurve.toLowerCase() : "—",
        changeDirection: "up" as const,
        sentiment: yldSent as "bull" | "bear" | "neutral",
        sentimentLabel: yldSent === "bull" ? "tailwind" : yldSent === "bear" ? "headwind" : "neutral",
      },
      {
        name: "Fear & Greed",
        value: fgVal != null ? String(fgVal) : "—",
        change: m.fear_greed?.label ?? "—",
        changeDirection: "up" as const,
        sentiment: "neutral" as const,
        sentimentLabel: m.fear_greed?.label ? m.fear_greed.label.toLowerCase() : "—",
      },
      {
        name: "HY spreads",
        value: hy != null ? `${hy.toFixed(0)} bps` : "—",
        change: hy != null && hy < 350 ? "tightening" : hy != null && hy > 500 ? "widening" : "—",
        changeDirection: hySent === "bull" ? ("down" as const) : ("up" as const),
        sentiment: hySent as "bull" | "bear" | "neutral",
        sentimentLabel: hySent === "bull" ? "tightening" : hySent === "bear" ? "stress" : "stable",
      },
    ];
  })();

  // ── Live macro signal label for MacroOverlay header ──────────────────────
  const macroSignalNice = (() => {
    const lbl = macroQuery.data?.macro_signal?.label;
    if (lbl === "RISK_ON") return "Risk-on";
    if (lbl === "RISK_OFF") return "Risk-off";
    if (lbl === "MILD_RISK_ON") return "Mild risk-on";
    if (lbl === "MILD_RISK_OFF") return "Mild risk-off";
    if (lbl === "NEUTRAL") return "Neutral";
    return "—";
  })();
  const macroScoreOutOf4 = (() => {
    const s = macroQuery.data?.macro_signal?.score;
    if (s == null) return 0;
    // Map -4..+4 to 0..100 confidence-ish display
    return Math.round(((s + 4) / 8) * 100);
  })();

  // ── Live regime weights (CRISIS / TRENDING / RANGING / NORMAL) ────────────
  const regimeWeightColumns = (() => {
    const cols = weightsQuery.data?.columns ?? [];
    if (cols.length === 0) {
      return [
        { regime: "bull" as RegimeType, label: "Loading…", weights: { tech: 0, macro: 0, sentiment: 0, onChain: 0 } },
      ];
    }
    return cols.map((c) => ({
      regime: _backendRegimeToVisual(c.regime),
      label:  c.regime.charAt(0) + c.regime.slice(1).toLowerCase(),
      weights: {
        tech:      c.weights.technical ?? 0,
        macro:     c.weights.macro ?? 0,
        sentiment: c.weights.sentiment ?? 0,
        onChain:   c.weights.onchain ?? 0,
      },
    }));
  })();

  // ── Live timeline segments + dates ─────────────────────────────────────────
  const tl = timelineQuery.data;
  const timelineSegments = (() => {
    const segs = tl?.segments ?? [];
    if (segs.length === 0) return [];
    const totalDays = segs.reduce((acc, s) => acc + (s.duration_days ?? 0), 0) || 1;
    return segs.map((s) => ({
      state:        _toTimelineState(s.state),
      widthPercent: Math.max(1, Math.round(((s.duration_days ?? 0) / totalDays) * 100)),
      label:        s.state.charAt(0).toUpperCase() + s.state.slice(1, 5),
    }));
  })();
  const timelineDates = (() => {
    const segs = tl?.segments ?? [];
    return segs.map((s) => {
      try {
        const d = new Date(s.start);
        return d.toLocaleString("en-US", { month: "short", day: "2-digit" });
      } catch {
        return "—";
      }
    });
  })();
  const currentRegimeText = (() => {
    if (!tl) return "Loading regime history…";
    if (!tl.current_state) return `No regime history yet for ${selectedTicker}.`;
    let dateStr = "—";
    try {
      dateStr = new Date(tl.since ?? "").toLocaleString("en-US", { month: "short", day: "2-digit" });
    } catch {
      // ignore
    }
    return `HMM 4-state model over composite + on-chain + macro features. State transitions shown on the bar. Current state: ${tl.current_state} since ${dateStr} (${Math.round(tl.duration_days ?? 0)}d).`;
  })();

  return (
    <AppShell crumbs="Markets" currentPage="Regimes">
      <PageHeader
        title="Regimes"
        subtitle="HMM-inferred market regime per asset + macro overlay. Regime-specific signal weights auto-adjust."
      />

      {/* AUDIT-2026-05-06 (W2 Tier 6 F-LEVEL-1): Beginner gloss */}
      <BeginnerHint title="What is a market regime?">
        Markets behave differently in different conditions:
        <strong className="text-text-primary"> trending </strong>
        (sustained direction up or down),
        <strong className="text-text-primary"> ranging </strong>
        (sideways), or
        <strong className="text-text-primary"> risk-off </strong>
        (defensive, cash-heavy). The model figures out which regime
        each coin is in right now, and tunes its signal weights
        accordingly. A &ldquo;Buy&rdquo; in a Trending regime means
        something different than the same Buy in a Ranging regime.
      </BeginnerHint>

      {/* Section header */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          Regime states · showing {regimeStates.length} of {totalCount} pairs · click any to drill in
        </span>
        <Button variant="outline" size="sm" className="h-8 text-xs">
          More <span className="ml-1 opacity-60">+{Math.max(0, totalCount - regimeStates.length)}</span>
        </Button>
      </div>

      {/* Regime cards grid */}
      {regimeStates.length === 0 ? (
        <div className="mb-5 rounded-lg border border-dashed border-border-default p-8 text-center text-sm text-muted-foreground">
          {regimesQuery.isLoading
            ? "Loading regime states…"
            : regimesQuery.isError
              ? "Couldn't load regime states — try refreshing in 30 seconds."
              : "Run a scan to populate regime states (no scan results yet)."}
        </div>
      ) : (
        <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {regimeStates.map((r) => (
            <RegimeCard
              key={r.ticker}
              ticker={r.ticker}
              state={r.state}
              confidence={r.confidence}
              since={r.since}
              durationDays={r.durationDays}
              selected={selectedTicker === r.ticker}
              onClick={() => setSelectedTicker(r.ticker)}
            />
          ))}
        </div>
      )}

      {/* Timeline + Macro overlay - 2 columns */}
      <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RegimeTimeline
          ticker={selectedTicker}
          segments={timelineSegments}
          dates={timelineDates}
          description={currentRegimeText}
        />
        <MacroOverlay regime={macroSignalNice} confidence={macroScoreOutOf4} indicators={macroIndicators} />
      </div>

      {/* Signal weights by regime */}
      <RegimeWeights columns={regimeWeightColumns} />
    </AppShell>
  );
}
