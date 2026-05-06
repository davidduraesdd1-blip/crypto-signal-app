"use client";

import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { useExecutionStatus } from "@/hooks/use-execution-status";
import { useRefreshAll } from "@/hooks/use-refresh-all";
import { useUserLevel, type UserLevel } from "@/providers/user-level-provider";

// AUDIT-2026-05-05 (P0-5): level state lifted from local Topbar useState
// into <UserLevelProvider> so any page can scale content to the user's
// tier per CLAUDE.md §7. The provider owns localStorage persistence;
// Topbar is now just a consumer.

type Level = UserLevel;

interface TopbarProps {
  crumbs?: string;
  currentPage?: string;
  /** Optional override — if not provided, the AGENT pill polls
   * /execution/status every 5s for live state (D4b wiring). */
  agentRunning?: boolean;
}

export function Topbar({ crumbs = "Markets", currentPage = "Home", agentRunning }: TopbarProps) {
  const { level, setLevel } = useUserLevel();

  // AUDIT-2026-05-03 (D4 audit, MEDIUM): use next-themes useTheme()
  // instead of hand-managing the .light class on <html>. The
  // ThemeProvider in app-providers.tsx owns the class via
  // attribute="class"; the prior local state would desync on every
  // reload (always reverted to dark) and bypass next-themes'
  // localStorage persistence.
  const { theme, setTheme } = useTheme();
  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");

  // AUDIT-2026-05-03 (D4b): live AGENT pill state from /execute/status.
  // Falls back to the prop when caller passed an explicit override.
  const execQuery = useExecutionStatus({ polling: true });
  const liveAgentRunning =
    agentRunning ?? Boolean(execQuery.data?.agent_running ?? execQuery.data?.live_trading);

  // AUDIT-2026-05-03 (D4b): global "Refresh All Data" button —
  // invalidates every active query + force-refetches the on-page ones
  // per CLAUDE.md §12 master-template requirement.
  const { refresh, isFetching } = useRefreshAll();

  return (
    <header className="sticky top-0 z-10 flex h-[var(--topbar-h)] items-center gap-4 border-b border-border-default bg-bg-0 px-6 md:gap-4 md:px-6">
      {/* Breadcrumbs */}
      <div className="text-[13px] text-text-muted">
        {crumbs} / <span className="font-medium text-text-primary">{currentPage}</span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Agent status pill - hidden on mobile */}
      <div
        className={cn(
          "hidden items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-wide md:inline-flex",
          liveAgentRunning
            ? "bg-success/10 text-success"
            : "bg-info/10 text-info"
        )}
        title={execQuery.isError ? "Status unavailable — check /execution/status" : undefined}
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            liveAgentRunning ? "animate-pulse bg-success" : "bg-info"
          )}
        />
        <span>
          Agent · {execQuery.isLoading && agentRunning === undefined ? "—" : liveAgentRunning ? "Running" : "Stopped"}
        </span>
      </div>

      {/* Level group - hidden on mobile */}
      {/* AUDIT-2026-05-04 (overnight a11y): radiogroup semantics so the
          three-level toggle (CLAUDE.md §7 core UX) reads as a grouped
          choice instead of three plain buttons. */}
      <div
        role="radiogroup"
        aria-label="User experience level"
        className="hidden items-center gap-0 rounded-lg border border-border-default bg-bg-1 p-0.5 md:inline-flex"
      >
        {(["Beginner", "Intermediate", "Advanced"] as Level[]).map((l) => (
          <button
            key={l}
            type="button"
            role="radio"
            aria-checked={level === l}
            onClick={() => setLevel(l)}
            className={cn(
              "min-h-[32px] min-w-[44px] rounded-md px-2.5 py-1 text-xs font-medium text-text-muted transition-colors",
              "hover:text-text-primary",
              level === l && "bg-accent-soft text-text-primary"
            )}
          >
            {l}
          </button>
        ))}
      </div>

      {/* Refresh button — wired to invalidate-all-queries + refetch-active */}
      <button
        onClick={refresh}
        disabled={isFetching}
        className={cn(
          "inline-flex min-h-[36px] min-w-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-1 px-2.5 py-1.5 text-[13px] text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary md:px-2.5",
          isFetching && "opacity-60 cursor-wait",
        )}
        aria-label="Refresh all data"
        title="Stale-mark every query and re-fetch the on-page ones"
      >
        <span className={cn(isFetching && "animate-spin")}>↻</span>
        <span className="hidden md:inline">{isFetching ? "Refreshing…" : "Refresh"}</span>
      </button>

      {/* Theme toggle */}
      {/* AUDIT-2026-05-04 (overnight a11y): on mobile the visible label is
          hidden, leaving only the ☀/☾ glyph — without aria-label the
          button has no accessible name. aria-pressed signals current
          theme state. */}
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
        aria-pressed={theme === "dark"}
        className="inline-flex min-h-[36px] min-w-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-1 px-2.5 py-1.5 text-[13px] text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary md:px-2.5"
      >
        <span aria-hidden="true">{theme === "light" ? "☀" : "☾"}</span>
        <span className="hidden md:inline">Theme</span>
      </button>
    </header>
  );
}
