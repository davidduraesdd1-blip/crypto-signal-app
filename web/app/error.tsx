"use client";

import { useEffect } from "react";

/**
 * Route-level React error boundary.
 *
 * AUDIT-2026-05-04 (H1 — post-cutover): per CLAUDE.md §8 "Never show a
 * Python exception or stack trace to a user", the React equivalent is
 * also required. Without this, an uncaught render error in any route
 * bubbles to a blank page or Next.js' default dev/prod error UI. The
 * fallback below matches the master template's plain-English error
 * tone — same vocabulary as the FastAPI 502 graceful copy.
 *
 * Reset triggers Next.js to re-render the segment without a full page
 * reload (cheaper than location.reload() on a heavy chart/table page).
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the error to whatever logging the deploy is wired to
    // (Render stdout/Sentry once SUPERGROK_SENTRY_DSN is set).
    if (typeof window !== "undefined") {
      // eslint-disable-next-line no-console
      console.error("[RouteError]", error);
    }
  }, [error]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center p-6">
      <div className="max-w-md text-center">
        <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-danger/10 text-danger text-2xl">
          ⚠
        </div>
        <h1 className="mb-2 text-xl font-semibold text-text-primary">
          Something went wrong on this page
        </h1>
        <p className="mb-6 text-sm text-text-secondary">
          The page hit an unexpected error. This is usually temporary — try again
          in a few seconds, and if the issue keeps happening, check the
          Diagnostics page for service health.
        </p>
        {error?.digest && (
          <p className="mb-4 font-mono text-[11px] text-text-muted">
            Reference: {error.digest}
          </p>
        )}
        <div className="flex justify-center gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-accent-brand px-5 py-2.5 text-sm font-semibold text-bg-0 transition-colors hover:bg-accent-brand/90"
          >
            Try again
          </button>
          <a
            href="/settings/dev-tools"
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-1 px-5 py-2.5 text-sm font-medium text-text-primary transition-colors hover:bg-bg-2"
          >
            Diagnostics
          </a>
        </div>
      </div>
    </div>
  );
}
