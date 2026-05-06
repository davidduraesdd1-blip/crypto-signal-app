/**
 * web/lib/signal-types.ts
 *
 * Canonical signal-type definitions. Single source of truth.
 *
 * AUDIT-2026-05-06 (P1-D): pre-fix there were TWO SignalType
 * definitions:
 *   - 3-tier "buy" | "hold" | "sell" replicated across 4 components
 *     (signal-card, signal-hero, signal-history, timeframe-strip)
 *   - 5-tier "buy" | "sell" | "hold" | "strong-buy" | "strong-sell"
 *     in lib/format.ts:directionToSignalType
 *
 * The 5-tier function returned values like "strong-sell" that the
 * 3-tier components couldn't render — which crashed SignalHero on
 * 2026-05-05 when BTC rotated to STRONG SELL post-merge. The HOTFIX
 * patched the symptom (defensive lookup + page-level collapse to
 * 3-tier) but the architectural smell remained.
 *
 * This module collapses to one canonical 3-tier `SignalType` for UI
 * consumers + introduces `EngineDirection` for raw engine values.
 * Components should always import `SignalType` from here. Per-component
 * re-exports are kept for back-compat but type-aliased to this file's
 * definition.
 */

/** UI-level signal type. 3-tier — every renderer (badges, dots, icons,
 *  colors) keys on this set. Strong-* signals collapse to base. */
export type SignalType = "buy" | "hold" | "sell";

/** Raw engine direction labels. The Python engine emits these strings
 *  in `daily_signals.direction` and `result['direction']`. Frontend
 *  must coerce to `SignalType` before passing to UI components. */
export type EngineDirection =
  | "BUY"
  | "STRONG BUY"
  | "SELL"
  | "STRONG SELL"
  | "HOLD"
  | "NEUTRAL"
  | "NO DATA"
  | "LOW VOL"
  | string; // open enum — engine may add new labels

/** Map engine direction → 3-tier signal type. Always returns a
 *  renderable value; never undefined. STRONG BUY → buy, STRONG SELL
 *  → sell, anything else → hold (safe default). */
export function directionToSignalType(direction: string | null | undefined): SignalType {
  if (!direction) return "hold";
  const d = String(direction).toUpperCase().trim();
  if (d.includes("BUY")) return "buy";
  if (d.includes("SELL")) return "sell";
  return "hold";
}

/** Indicator-tile variant. Used to color-code metric cards. */
export type IndicatorVariant = "default" | "warning" | "success" | "danger";

/** Inverse of directionToSignalType — for tooltip/title text where
 *  the user wants the raw engine label preserved (e.g. show "STRONG
 *  SELL" in a tooltip but render the badge as a plain SELL). */
export function isStrongSignal(direction: string | null | undefined): boolean {
  if (!direction) return false;
  return String(direction).toUpperCase().trim().startsWith("STRONG");
}
