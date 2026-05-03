/**
 * web/tests/setup.ts
 *
 * Per-test setup. Loaded by vitest.config.ts before each test file.
 * Adds jest-dom matchers (toBeInTheDocument, toHaveTextContent, etc.)
 * for hook/component tests.
 */
import "@testing-library/jest-dom/vitest";
