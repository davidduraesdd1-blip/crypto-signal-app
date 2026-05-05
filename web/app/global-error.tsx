"use client";

import { useEffect } from "react";

/**
 * Root-level React error boundary.
 *
 * AUDIT-2026-05-04 (H1): catches errors that bubble past app/error.tsx
 * (typically render errors thrown inside layout.tsx itself). Next.js
 * requires this file to render its own <html>/<body> because the root
 * layout has crashed. Keep it dependency-free — no shadcn imports, no
 * design tokens — just inline styles so it works even if the global
 * stylesheet failed to load.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (typeof window !== "undefined") {
      // eslint-disable-next-line no-console
      console.error("[GlobalError]", error);
    }
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          padding: 0,
          background: "#0a0a0f",
          color: "#e8e8f0",
          fontFamily:
            "Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            maxWidth: 480,
            padding: 24,
            textAlign: "center",
          }}
        >
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 56,
              height: 56,
              borderRadius: "50%",
              background: "rgba(239, 68, 68, 0.1)",
              color: "#ef4444",
              fontSize: 28,
              marginBottom: 16,
            }}
          >
            ⚠
          </div>
          <h1
            style={{
              fontSize: 22,
              fontWeight: 600,
              marginBottom: 8,
            }}
          >
            The app couldn&rsquo;t load
          </h1>
          <p style={{ fontSize: 14, color: "#8a8a9d", marginBottom: 24 }}>
            A page-level error occurred and the layout failed to render. Try
            reloading. If this keeps happening, the FastAPI backend at Render
            may be redeploying — wait 60 seconds and try again.
          </p>
          {error?.digest && (
            <p
              style={{
                fontFamily:
                  "JetBrains Mono, ui-monospace, monospace",
                fontSize: 11,
                color: "#5d5d6e",
                marginBottom: 16,
              }}
            >
              Reference: {error.digest}
            </p>
          )}
          <button
            type="button"
            onClick={() => reset()}
            style={{
              display: "inline-flex",
              alignItems: "center",
              minHeight: 44,
              padding: "10px 20px",
              borderRadius: 8,
              border: "none",
              background: "#22d36f",
              color: "#0a0a0f",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      </body>
    </html>
  );
}
