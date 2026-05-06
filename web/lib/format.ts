/**
 * web/lib/format.ts
 *
 * Display formatters that map raw API numbers to v0's expected string
 * shapes (e.g. "104,280" / "+ 2.14%" / "$1.2M") so pages don't have
 * to re-implement formatting each time.
 *
 * Mirrors the contract of utils_format.py (the Python-side family-
 * office unified formatters) — same em-dash for missing, same
 * compact thresholds.
 */

const EM_DASH = "—";

export function isMissing(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "number" && (Number.isNaN(v) || !Number.isFinite(v))) return true;
  if (typeof v === "string") {
    const s = v.trim();
    return s === "" || s === "N/A" || s === "None" || s === "nan" || s === "NaN" || s === EM_DASH;
  }
  return false;
}

// AUDIT-2026-05-06 (P1-D + W2-N2): defensive coercion helpers. The
// daily_signals SQLite table has REAL columns that can occasionally
// surface as strings via pandas/SQLite type drift across schema
// migrations. Calling .toFixed() / .toLocaleString() / arithmetic on
// these without coercing crashes the page (caught by H1 error
// boundary on 2026-05-05). Promoted from signals/page.tsx so every
// page that reads engine output can use them.

/** Coerce a value that should be a finite number; null otherwise. */
export function toFiniteNumber(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Coerce a value that should be a non-empty string; null otherwise.
 *  Treats "NaN" / "None" / whitespace as missing. */
export function toCleanString(v: unknown): string | null {
  if (v == null) return null;
  const s = String(v).trim();
  if (s.length === 0) return null;
  const lower = s.toLowerCase();
  if (lower === "nan" || lower === "none" || lower === "n/a") return null;
  return s;
}

/** Format a USD value: $104,280 / $1.2K / $2.13M / $5.40B / em-dash */
export function formatUsd(value: number | null | undefined, decimals = 2, compact = false): string {
  if (isMissing(value)) return EM_DASH;
  const v = Number(value);
  const sign = v < 0 ? "-" : "";
  const av = Math.abs(v);
  const d = Math.max(0, Math.min(6, decimals));
  if (compact) {
    if (av >= 1_000_000_000) return `${sign}$${(av / 1_000_000_000).toFixed(d)}B`;
    if (av >= 950_000) return `${sign}$${(av / 1_000_000).toFixed(d)}M`;
    if (av >= 10_000) return `${sign}$${(av / 1_000).toFixed(d)}K`;
  }
  return `${sign}$${av.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

/** Format a number as comma-separated string. 104280 → "104,280" */
export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (isMissing(value)) return EM_DASH;
  const d = Math.max(0, Math.min(6, decimals));
  return Number(value).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

/** Format a percentage value. The FastAPI side emits change_24h_pct
 * etc. as already-percent values (e.g. 2.14 for 2.14%, NOT 0.0214).
 *
 * AUDIT-2026-05-03 (D4 audit, HIGH formatPct fix): the prior magnitude
 * heuristic (`if abs(v) ≤ 1.5: multiply by 100`) silently rendered a
 * real flat-day "+0.8%" change as "+80.0%". The Python utils_format.py
 * contract uses the same heuristic, but the API actually emits percent
 * values for every endpoint we read — so the heuristic was unsafe.
 *
 * Now: always treats `value` as already-percent. Callers with fraction
 * data must multiply by 100 themselves OR use `formatPctFromFraction`.
 */
export function formatPct(value: number | null | undefined, decimals = 1, signed = false): string {
  if (isMissing(value)) return EM_DASH;
  const v = Number(value);
  const d = Math.max(0, Math.min(4, decimals));
  const formatted = v.toFixed(d);
  if (signed && v >= 0 && !formatted.startsWith("-")) {
    return `+${formatted}%`;
  }
  return `${formatted}%`;
}

/** Format a fraction as percent — multiplies by 100 first.
 * Use when the API endpoint returns a fraction (e.g. 0.0214 for 2.14%).
 * Today no D4 endpoint requires this, but it's here so the explicit-
 * contract path exists if a future endpoint emits fractions. */
export function formatPctFromFraction(value: number | null | undefined, decimals = 1, signed = false): string {
  if (isMissing(value)) return EM_DASH;
  return formatPct(Number(value) * 100, decimals, signed);
}

/** Format a confidence score as "82% conf" / "61%" — drives hero card pills */
export function formatConfidence(value: number | null | undefined, withSuffix = false): string {
  if (isMissing(value)) return EM_DASH;
  const v = Math.round(Number(value));
  return withSuffix ? `${v}% conf` : `${v}%`;
}

// AUDIT-2026-05-06 (P1-D): the original directionToSignalType returned
// 5 values (buy/sell/hold/strong-buy/strong-sell), but every UI
// component (SignalHero, SignalHistory, TimeframeStrip, SignalCard)
// only handles 3. The mismatch crashed SignalHero on STRONG SELL
// (HOTFIX commit 9d136c2). Single source of truth now lives in
// lib/signal-types — re-export for back-compat with existing imports.
export { directionToSignalType, isStrongSignal } from "@/lib/signal-types";
export type { SignalType, EngineDirection } from "@/lib/signal-types";

/** Lowercase regime label v0 components expect. */
export function regimeToDisplay(regime: string | null | undefined): string {
  if (!regime) return "unknown";
  return regime.toLowerCase();
}
