"use client";

import { memo } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { useExecutionStatus } from "@/hooks/use-execution-status";
import { useRefreshAll } from "@/hooks/use-refresh-all";
import { useUserLevel, type UserLevel } from "@/providers/user-level-provider";
import { useStartAgent, useStopAgent } from "@/hooks/use-agent";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// AUDIT-2026-05-06 (post-launch v6): the level switcher (Beginner/
// Intermediate/Advanced) was visibly flickering every 5 seconds because
// it shared a parent component with the AGENT pill that polls every 5s.
// Extracted as a memoized child that only re-renders when its own state
// (level from useUserLevel context) actually changes.
const LevelSwitcher = memo(function LevelSwitcher() {
  const { level, setLevel } = useUserLevel();
  return (
    <div
      role="radiogroup"
      aria-label="User experience level"
      className="hidden items-center gap-0 rounded-lg border border-border-default bg-bg-1 p-0.5 md:inline-flex"
    >
      {(["Beginner", "Intermediate", "Advanced"] as UserLevel[]).map((l) => (
        <button
          key={l}
          type="button"
          role="radio"
          aria-checked={level === l}
          onClick={() => setLevel(l)}
          className={cn(
            "min-h-[32px] min-w-[44px] rounded-md px-2.5 py-1 text-xs font-medium text-text-muted transition-colors",
            "hover:text-text-primary",
            level === l && "bg-accent-soft text-text-primary",
          )}
        >
          {l}
        </button>
      ))}
    </div>
  );
});

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

  // AUDIT-2026-05-06 (post-launch v4): AGENT pill is now a dropdown menu.
  // Click opens Start / Stop / View activity. Mutations defined here so
  // the topbar can act without navigating to /ai-assistant.
  const router = useRouter();
  const startAgent = useStartAgent();
  const stopAgent = useStopAgent();

  // AUDIT-2026-05-03 (D4b): global "Refresh All Data" button —
  // invalidates every active query + force-refetches the on-page ones
  // per CLAUDE.md §12 master-template requirement.
  // AUDIT-2026-05-06 (v6): now shows progress (n pending / n peak)
  // and a thin progress bar under the button while in flight.
  const { refresh, isFetching, pendingCount, totalCount, progress } = useRefreshAll();

  return (
    <header className="sticky top-0 z-10 flex h-[var(--topbar-h)] items-center gap-4 border-b border-border-default bg-bg-0 px-6 md:gap-4 md:px-6">
      {/* Breadcrumbs */}
      <div className="text-[13px] text-text-muted">
        {crumbs} / <span className="font-medium text-text-primary">{currentPage}</span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Agent status pill - hidden on mobile, now a dropdown menu */}
      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn(
            "hidden items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold uppercase tracking-wide outline-none transition-colors md:inline-flex",
            "hover:opacity-90 focus-visible:ring-2 focus-visible:ring-accent-brand",
            liveAgentRunning
              ? "bg-success/10 text-success hover:bg-success/15"
              : "bg-info/10 text-info hover:bg-info/15",
          )}
          title={execQuery.isError ? "Status unavailable — check /execution/status" : "Click to manage agent"}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              liveAgentRunning ? "animate-pulse bg-success" : "bg-info",
            )}
          />
          <span>
            Agent · {execQuery.isLoading && agentRunning === undefined ? "—" : liveAgentRunning ? "Running" : "Stopped"}
          </span>
          <span className="text-[10px] opacity-70">▾</span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[200px]">
          <DropdownMenuItem
            disabled={liveAgentRunning || startAgent.isPending}
            onSelect={() => startAgent.mutate()}
            className="cursor-pointer"
          >
            <span className="mr-2 text-success">▶</span>
            {startAgent.isPending ? "Starting…" : "Start agent"}
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!liveAgentRunning || stopAgent.isPending}
            onSelect={() => stopAgent.mutate()}
            className="cursor-pointer"
          >
            <span className="mr-2 text-danger">■</span>
            {stopAgent.isPending ? "Stopping…" : "Stop agent"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => router.push("/ai-assistant")}
            className="cursor-pointer"
          >
            <span className="mr-2">📊</span>
            View activity & decisions
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Level group - memoized child, isolated from topbar re-renders.
          AUDIT-2026-05-06 (v6 — fix 5s flicker on level buttons). */}
      <LevelSwitcher />

      {/* Refresh button + live progress indicator + schedule tooltip.
          AUDIT-2026-05-06 (v6): shows "n/N" count while fetching and a
          thin progress bar fills as queries complete. */}
      <div className="relative inline-flex flex-col">
        <button
          onClick={refresh}
          disabled={isFetching}
          className={cn(
            "inline-flex min-h-[36px] min-w-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-1 px-2.5 py-1.5 text-[13px] text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary md:px-2.5",
            isFetching && "cursor-wait",
          )}
          aria-label={isFetching ? `Refreshing: ${pendingCount} of ${totalCount} pending` : "Refresh all data"}
          title={
            isFetching
              ? `Refreshing — ${pendingCount} of ${totalCount} pending`
              : "Refresh all data — see refresh schedule for auto-poll cadence"
          }
        >
          <span className={cn(isFetching && "animate-spin text-accent-brand")}>↻</span>
          <span className="hidden md:inline">
            {isFetching ? `Refresh ${totalCount - pendingCount}/${totalCount}` : "Refresh"}
          </span>
        </button>
        {isFetching && (
          <div
            aria-hidden="true"
            className="absolute -bottom-0.5 left-0 right-0 h-0.5 overflow-hidden rounded-full bg-bg-2"
          >
            <div
              className="h-full bg-accent-brand transition-all duration-300 ease-out"
              style={{ width: `${(progress * 100).toFixed(1)}%` }}
            />
          </div>
        )}
      </div>

      {/* Refresh-schedule tooltip — shows the auto-poll cadence for
          every data type so the user knows how often things refresh.
          AUDIT-2026-05-06 (v6). */}
      <button
        type="button"
        aria-label="Show refresh schedule"
        title={[
          "Auto-refresh schedule (per CLAUDE.md §12):",
          "  Agent status   — every 15s",
          "  AI agent log   — every 10s",
          "  Signals + Home — every 5 min",
          "  Funding rates  — every 10 min",
          "  Regime states  — every 15 min",
          "  Macro / health — every 5 min",
          "  On-chain       — every 1 hour",
          "  Backtest data  — every 1 hour",
          "  Settings       — session-long (until you change them)",
          "",
          "Click 'Refresh' to force-refresh everything now.",
        ].join("\n")}
        className="hidden min-h-[36px] items-center justify-center rounded-lg border border-border-default bg-bg-1 px-2 text-[12px] text-text-muted transition-colors hover:border-border-strong hover:text-text-primary md:inline-flex"
      >
        ⓘ
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
