/**
 * web/tests/signal-types.test.ts
 *
 * Regression suite for the SignalType bug class that escaped Wave 1
 * (Phase 0.9 audit). The original directionToSignalType returned
 * 5 values but every UI component only handled 3 — leading to the
 * SignalHero crash on STRONG SELL (HOTFIX 9d136c2 + P1-D consolidation
 * a5be15b).
 *
 * Locks in:
 *   - directionToSignalType ALWAYS returns 3-tier ("buy" | "sell" | "hold")
 *   - isStrongSignal correctly classifies STRONG variants
 *   - toFiniteNumber / toCleanString defensive coercion helpers handle
 *     every type-drift class observed in daily_signals rows
 */
import { describe, expect, it } from "vitest";

import {
  directionToSignalType,
  isStrongSignal,
  type SignalType,
} from "@/lib/signal-types";
import { toFiniteNumber, toCleanString, isMissing } from "@/lib/format";

describe("directionToSignalType — 3-tier guarantee", () => {
  // The bug that crashed SignalHero on 2026-05-05: STRONG SELL
  // returned "strong-sell" which wasn't in any component's
  // signalConfig dict. Now MUST collapse to "sell".
  it("collapses STRONG SELL → sell", () => {
    expect(directionToSignalType("STRONG SELL")).toBe("sell");
  });
  it("collapses STRONG BUY → buy", () => {
    expect(directionToSignalType("STRONG BUY")).toBe("buy");
  });
  it("plain BUY → buy", () => {
    expect(directionToSignalType("BUY")).toBe("buy");
  });
  it("plain SELL → sell", () => {
    expect(directionToSignalType("SELL")).toBe("sell");
  });
  it("HOLD → hold", () => {
    expect(directionToSignalType("HOLD")).toBe("hold");
  });
  it("NO DATA → hold", () => {
    expect(directionToSignalType("NO DATA")).toBe("hold");
  });
  it("LOW VOL → hold (engine emits this for thin volume bars)", () => {
    expect(directionToSignalType("LOW VOL")).toBe("hold");
  });
  it("NEUTRAL → hold", () => {
    expect(directionToSignalType("NEUTRAL")).toBe("hold");
  });
  it("null → hold", () => {
    expect(directionToSignalType(null)).toBe("hold");
  });
  it("undefined → hold", () => {
    expect(directionToSignalType(undefined)).toBe("hold");
  });
  it("empty string → hold", () => {
    expect(directionToSignalType("")).toBe("hold");
  });
  it("unknown engine label → hold (open enum safety)", () => {
    expect(directionToSignalType("FOOBAR")).toBe("hold");
  });

  // Belt-and-suspenders: the return type is provably 3-tier
  it("return type is 3-tier SignalType (compile-time assert)", () => {
    const r: SignalType = directionToSignalType("STRONG SELL");
    // If r ever held "strong-sell" / "strong-buy", this assignment
    // would fail to typecheck. The runtime expects only buy/sell/hold.
    expect(["buy", "sell", "hold"]).toContain(r);
  });
});

describe("isStrongSignal — intensity classification", () => {
  it("STRONG SELL → true", () => {
    expect(isStrongSignal("STRONG SELL")).toBe(true);
  });
  it("STRONG BUY → true", () => {
    expect(isStrongSignal("STRONG BUY")).toBe(true);
  });
  it("BUY → false (not strong)", () => {
    expect(isStrongSignal("BUY")).toBe(false);
  });
  it("HOLD → false", () => {
    expect(isStrongSignal("HOLD")).toBe(false);
  });
  it("null → false", () => {
    expect(isStrongSignal(null)).toBe(false);
  });
});

describe("toFiniteNumber — defensive coercion", () => {
  // Daily_signals SQLite REAL columns occasionally surface as
  // strings via pandas/SQLite type drift. .toFixed() on a string
  // crashes the page (caught by H1 error boundary on 2026-05-05).
  it("number passthrough", () => {
    expect(toFiniteNumber(42.5)).toBe(42.5);
  });
  it("string number → number", () => {
    expect(toFiniteNumber("31.10")).toBe(31.1);
  });
  it("integer string → integer", () => {
    expect(toFiniteNumber("100")).toBe(100);
  });
  it("null → null", () => {
    expect(toFiniteNumber(null)).toBe(null);
  });
  it("undefined → null", () => {
    expect(toFiniteNumber(undefined)).toBe(null);
  });
  it("empty string → null", () => {
    expect(toFiniteNumber("")).toBe(null);
  });
  it("non-numeric string → null", () => {
    expect(toFiniteNumber("N/A")).toBe(null);
  });
  it("NaN → null", () => {
    expect(toFiniteNumber(NaN)).toBe(null);
  });
  it("Infinity → null", () => {
    expect(toFiniteNumber(Infinity)).toBe(null);
  });
  it("-Infinity → null", () => {
    expect(toFiniteNumber(-Infinity)).toBe(null);
  });
  it("zero is finite", () => {
    expect(toFiniteNumber(0)).toBe(0);
  });
  it("negative number passthrough", () => {
    expect(toFiniteNumber(-3.14)).toBe(-3.14);
  });
  it("boolean false → 0 (Number(false) is finite)", () => {
    // Documenting the contract — Number(false) === 0
    expect(toFiniteNumber(false)).toBe(0);
  });
  it("boolean true → 1", () => {
    expect(toFiniteNumber(true)).toBe(1);
  });
});

describe("toCleanString — defensive string coercion", () => {
  it("plain string passthrough", () => {
    expect(toCleanString("hello")).toBe("hello");
  });
  it("trims whitespace", () => {
    expect(toCleanString("  hello  ")).toBe("hello");
  });
  it("number → string", () => {
    expect(toCleanString(42)).toBe("42");
  });
  it("null → null", () => {
    expect(toCleanString(null)).toBe(null);
  });
  it("undefined → null", () => {
    expect(toCleanString(undefined)).toBe(null);
  });
  it("empty string → null", () => {
    expect(toCleanString("")).toBe(null);
  });
  it("whitespace-only → null", () => {
    expect(toCleanString("   ")).toBe(null);
  });
  it("'NaN' string → null", () => {
    expect(toCleanString("NaN")).toBe(null);
  });
  it("'nan' lowercase → null", () => {
    expect(toCleanString("nan")).toBe(null);
  });
  it("'None' (Python literal that pandas can emit) → null", () => {
    expect(toCleanString("None")).toBe(null);
  });
  it("'N/A' → null", () => {
    expect(toCleanString("N/A")).toBe(null);
  });
  it("preserves engine direction labels", () => {
    expect(toCleanString("STRONG SELL")).toBe("STRONG SELL");
  });
});

describe("isMissing — broader coercion (already existed pre-W2)", () => {
  // Spot-check the existing helper to confirm the new helpers
  // don't drift from its semantics.
  it("agrees with toFiniteNumber on null", () => {
    expect(isMissing(null)).toBe(true);
    expect(toFiniteNumber(null)).toBe(null);
  });
  it("agrees on NaN", () => {
    expect(isMissing(NaN)).toBe(true);
    expect(toFiniteNumber(NaN)).toBe(null);
  });
  it("zero is NOT missing (it's a real value)", () => {
    expect(isMissing(0)).toBe(false);
    expect(toFiniteNumber(0)).toBe(0);
  });
});
