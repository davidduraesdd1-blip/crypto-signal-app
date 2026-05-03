"use client";
/**
 * web/providers/query-provider.tsx
 *
 * Client-only TanStack Query <Provider> + devtools (dev only).
 *
 * The QueryClient lives in a `useState(() => createQueryClient())` so
 * each client mount gets a stable instance. With React 19 + Next.js 16
 * app router this pattern avoids re-creating the client on every
 * render. SSR-side hydration (D4d) will switch to per-request clients
 * — for D4a, client-only fetching keeps the surface small.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, type ReactNode } from "react";

import { createQueryClient } from "@/lib/query-client";

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(() => createQueryClient());
  return (
    <QueryClientProvider client={client}>
      {children}
      {process.env.NODE_ENV !== "production" && (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
      )}
    </QueryClientProvider>
  );
}
