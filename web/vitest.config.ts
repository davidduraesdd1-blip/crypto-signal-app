/**
 * web/vitest.config.ts
 *
 * Vitest config for the D4d test scaffold. Uses jsdom for hook/component
 * tests; the api-contract.test.ts hits the live deploy and uses node
 * fetch directly (no DOM needed there but jsdom is harmless).
 */
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
    // Drift test against the live API hits the network and may take
    // up to 10s on a cold Render container — give the suite some
    // slack but cap so a hung URL doesn't tie up CI forever.
    testTimeout: 30_000,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
