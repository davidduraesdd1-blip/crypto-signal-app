/**
 * web/tests/components.test.tsx
 *
 * Regression suite for the 4 frontend HIGH findings closed in commit
 * 47a6f90 (Tier 4 deep-dive audit). Locks in the visual + behavioral
 * fixes so the bugs can't recur on the next refactor.
 *
 * Run with:
 *   npm test -- components
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { MacroOverlay } from "@/components/macro-overlay";
import { EquityCurve } from "@/components/equity-curve";
import { FundingCarryTable } from "@/components/funding-carry-table";

// ─── macro-overlay: bg-success/danger/warning + text-success/danger ──────────
//
// Pre-fix used `bg-semantic-*` and `text-semantic-*` which do not exist in
// the @theme inline block, so sentiment dots and direction text rendered
// transparent / default-text. These tests assert the actually-exposed
// utility classes are emitted.

describe("MacroOverlay (Tier 4 HIGH — bg/text-semantic-* rename)", () => {
  it("emits bg-success / bg-danger / bg-warning sentiment dots", () => {
    const { container } = render(
      <MacroOverlay
        regime="Risk-on"
        confidence={76}
        indicators={[
          { name: "DXY", value: "104.21", change: "0.6%", changeDirection: "down", sentiment: "bull", sentimentLabel: "Risk-on" },
          { name: "CPI", value: "3.1%", change: "0.2%", changeDirection: "up", sentiment: "bear", sentimentLabel: "Hot" },
          { name: "M2", value: "21.4T", change: "0.0%", changeDirection: "up", sentiment: "neutral", sentimentLabel: "Flat" },
        ]}
      />
    );
    expect(container.querySelector(".bg-success")).toBeTruthy();
    expect(container.querySelector(".bg-danger")).toBeTruthy();
    expect(container.querySelector(".bg-warning")).toBeTruthy();
    // The broken classes must not be re-introduced.
    expect(container.innerHTML).not.toContain("bg-semantic-");
  });

  it("uses text-success/text-danger for change direction (not text-semantic-*)", () => {
    const { container } = render(
      <MacroOverlay
        regime="Risk-on"
        confidence={76}
        indicators={[
          { name: "DXY", value: "104.21", change: "0.6%", changeDirection: "up", sentiment: "bull", sentimentLabel: "x" },
          { name: "CPI", value: "3.1%", change: "0.2%", changeDirection: "down", sentiment: "bear", sentimentLabel: "x" },
        ]}
      />
    );
    expect(container.querySelector(".text-success")).toBeTruthy();
    expect(container.querySelector(".text-danger")).toBeTruthy();
    expect(container.innerHTML).not.toContain("text-semantic-");
  });
});

// ─── equity-curve: legend dash uses border-text-secondary ───────────────────
//
// Pre-fix used `border-gray-6` which Tailwind didn't generate (no
// `--color-gray-6` exposed in @theme inline). Assert that the legend
// dash element now has the working border class.

describe("EquityCurve (Tier 4 HIGH — border-gray-6 rename)", () => {
  it("legend dash element has border-text-secondary, not border-gray-6", () => {
    const { container } = render(<EquityCurve dateRange="last 90d" />);
    expect(container.querySelector(".border-text-secondary")).toBeTruthy();
    expect(container.innerHTML).not.toContain("border-gray-6");
  });
});

// ─── funding-carry-table: rateClass operator-precedence fix ─────────────────
//
// Pre-fix `rate.startsWith("+") || rate.startsWith("−") === false` parsed
// as `startsWith("+") || (startsWith("−") === false)`, returning text-success
// for every non-`−` value. Assert that negative values now render text-danger
// and positives render text-success across both U+2212 (proper minus) and
// ASCII hyphen variants.

describe("FundingCarryTable (Tier 4 HIGH — rateClass precedence fix)", () => {
  it("renders text-danger for negative rates (U+2212)", () => {
    const { container } = render(
      <FundingCarryTable
        carries={[
          { pair: "BTC", okx8h: "+0.012%", bybit8h: "−0.008%", delta: "+0.020%", strategy: "long-okx", annualized: "10.95%" },
        ]}
      />
    );
    // The Bybit cell with the negative sign must use text-danger.
    const bybitCell = container.innerHTML.match(/text-danger[^"]*"[^>]*>−0.008%/);
    expect(bybitCell).toBeTruthy();
  });

  it("renders text-danger for ASCII hyphen negatives too", () => {
    const { container } = render(
      <FundingCarryTable
        carries={[
          { pair: "ETH", okx8h: "+0.005%", bybit8h: "-0.003%", delta: "+0.008%", strategy: "x", annualized: "5%" },
        ]}
      />
    );
    expect(container.innerHTML).toMatch(/text-danger[^"]*"[^>]*>-0.003%/);
  });

  it("renders text-success for positive rates", () => {
    const { container } = render(
      <FundingCarryTable
        carries={[
          { pair: "SOL", okx8h: "+0.020%", bybit8h: "+0.018%", delta: "+0.002%", strategy: "x", annualized: "8%" },
        ]}
      />
    );
    // No text-danger should appear on positive rates.
    expect(container.innerHTML).not.toMatch(/text-danger[^"]*"[^>]*>\+0/);
    expect(container.querySelectorAll(".text-success").length).toBeGreaterThan(0);
  });
});
