"use client";
/**
 * web/providers/app-providers.tsx
 *
 * Composes every top-level provider so app/layout.tsx stays clean.
 * Order matters:
 *   1. ThemeProvider (next-themes) — outermost so theme class is on <html>
 *   2. UserLevelProvider — context for Beginner/Intermediate/Advanced
 *      tier state per CLAUDE.md §7. Wired 2026-05-05 (P0-5).
 *   3. QueryProvider — innermost client provider; devtools mounted here
 */
import { type ReactNode } from "react";

import { ThemeProvider } from "@/components/theme-provider";

import { QueryProvider } from "./query-provider";
import { UserLevelProvider } from "./user-level-provider";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem={false}
      disableTransitionOnChange
    >
      <UserLevelProvider>
        <QueryProvider>{children}</QueryProvider>
      </UserLevelProvider>
    </ThemeProvider>
  );
}
