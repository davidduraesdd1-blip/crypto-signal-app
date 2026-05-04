"use client";
/**
 * web/providers/app-providers.tsx
 *
 * Composes every top-level provider so app/layout.tsx stays clean.
 * Order matters:
 *   1. ThemeProvider (next-themes) — outermost so theme class is on <html>
 *   2. QueryProvider — innermost client provider; devtools mounted here
 *
 * Future additions (post-D4a):
 *   - <UserLevelProvider> for Beginner/Intermediate/Advanced state
 *   - <ToastProvider> if we add a global toast surface
 */
import { type ReactNode } from "react";

import { ThemeProvider } from "@/components/theme-provider";

import { QueryProvider } from "./query-provider";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem={false}
      disableTransitionOnChange
    >
      <QueryProvider>{children}</QueryProvider>
    </ThemeProvider>
  );
}
