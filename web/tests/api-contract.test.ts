/**
 * web/tests/api-contract.test.ts
 *
 * D4d drift-guard test. Fetches /openapi.json from the live FastAPI
 * deploy and asserts that every endpoint our typed lib/api.ts client
 * uses still exists with the expected method. If the Python-side
 * routers move or rename a path, this test fails loudly so the TS
 * client gets updated alongside the Python change.
 *
 * Run with:
 *   npm test -- api-contract
 *
 * Reads the live URL from CRYPTO_SIGNAL_API_BASE_FOR_TESTS env var
 * (defaults to NEXT_PUBLIC_API_BASE) so CI can point at staging /
 * production explicitly. Skip when no URL is reachable — drift
 * tests should never block a feature commit just because the live
 * deploy is asleep.
 */
import { describe, expect, it } from "vitest";

interface OpenApiPath {
  [method: string]: unknown;
}

interface OpenApiSpec {
  paths: Record<string, OpenApiPath>;
  components?: {
    schemas?: Record<string, unknown>;
  };
}

const API_BASE =
  process.env.CRYPTO_SIGNAL_API_BASE_FOR_TESTS ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "https://crypto-signal-app-1fsi.onrender.com";

/** Endpoints the D4 wire-up depends on. Pair = [METHOD, PATH] where
 * PATH may include {param} placeholders matching the FastAPI path. */
const REQUIRED_ENDPOINTS: Array<[string, string]> = [
  ["GET", "/health"],
  ["GET", "/scan/status"],
  ["POST", "/scan/trigger"],
  ["GET", "/home/summary"],
  ["GET", "/signals"],
  ["GET", "/signals/{pair}"],
  ["GET", "/regimes/"],
  ["GET", "/regimes/{pair}/history"],
  ["GET", "/regimes/transitions"],
  ["GET", "/onchain/dashboard"],
  ["GET", "/onchain/{metric}"],
  ["GET", "/alerts/configure"],
  ["POST", "/alerts/configure"],
  ["DELETE", "/alerts/configure/{rule_id}"],
  ["GET", "/alerts/log"],
  ["POST", "/ai/ask"],
  ["GET", "/ai/decisions"],
  ["GET", "/settings/"],
  ["PUT", "/settings/trading"],
  ["PUT", "/settings/signal-risk"],
  ["PUT", "/settings/dev-tools"],
  ["PUT", "/settings/execution"],
  ["POST", "/exchange/test-connection"],
  ["GET", "/diagnostics/circuit-breakers"],
  ["GET", "/diagnostics/database"],
  ["GET", "/execute/status"],
  ["POST", "/execute/order"],
];

async function fetchOpenApi(): Promise<OpenApiSpec | null> {
  try {
    const res = await fetch(`${API_BASE}/openapi.json`, {
      // 10s timeout via AbortSignal so a sleeping Render container
      // doesn't hang CI for minutes.
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return null;
    return (await res.json()) as OpenApiSpec;
  } catch {
    return null;
  }
}

describe("FastAPI ↔ TypeScript contract", () => {
  it("every endpoint used by lib/api.ts exists in the live /openapi.json", async () => {
    const spec = await fetchOpenApi();
    if (!spec) {
      // Not a failure — the live deploy may be asleep, or this test
      // ran offline. Surface as a skip so CI logs make the reason
      // visible without failing the build.
      console.warn(
        `[api-contract] /openapi.json unreachable at ${API_BASE} — skipping drift check.`,
      );
      return;
    }

    const missing: string[] = [];
    for (const [method, path] of REQUIRED_ENDPOINTS) {
      const ops = spec.paths[path];
      if (!ops || !(method.toLowerCase() in ops)) {
        missing.push(`${method} ${path}`);
      }
    }

    if (missing.length > 0) {
      throw new Error(
        `FastAPI ↔ TS drift detected — these endpoints are referenced by ` +
          `web/lib/api.ts but do not exist in the live /openapi.json:\n` +
          missing.map((m) => `  • ${m}`).join("\n") +
          `\n\nFix path: either update the FastAPI router (path moved/renamed) or ` +
          `update the TS client + the corresponding hook to match the new path.`,
      );
    }

    expect(missing).toEqual([]);
  });
});
