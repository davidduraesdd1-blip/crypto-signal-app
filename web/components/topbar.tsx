"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

type Level = "Beginner" | "Intermediate" | "Advanced";

interface TopbarProps {
  crumbs?: string;
  currentPage?: string;
  agentRunning?: boolean;
}

export function Topbar({ crumbs = "Markets", currentPage = "Home", agentRunning = true }: TopbarProps) {
  const [level, setLevel] = useState<Level>("Intermediate");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  const toggleTheme = () => {
    const newTheme = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    document.documentElement.classList.toggle("light", newTheme === "light");
  };

  const handleRefresh = () => {
    // Mock refresh action
  };

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
          agentRunning
            ? "bg-success/10 text-success"
            : "bg-info/10 text-info"
        )}
      >
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            agentRunning ? "animate-pulse bg-success" : "bg-info"
          )}
        />
        <span>Agent · {agentRunning ? "Running" : "Stopped"}</span>
      </div>

      {/* Level group - hidden on mobile */}
      <div className="hidden items-center gap-0 rounded-lg border border-border-default bg-bg-1 p-0.5 md:inline-flex">
        {(["Beginner", "Intermediate", "Advanced"] as Level[]).map((l) => (
          <button
            key={l}
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

      {/* Refresh button */}
      <button
        onClick={handleRefresh}
        className="inline-flex min-h-[36px] min-w-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-1 px-2.5 py-1.5 text-[13px] text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary md:px-2.5"
      >
        <span>↻</span>
        <span className="hidden md:inline">Refresh</span>
      </button>

      {/* Theme toggle */}
      <button
        onClick={toggleTheme}
        className="inline-flex min-h-[36px] min-w-[44px] items-center gap-2 rounded-lg border border-border-default bg-bg-1 px-2.5 py-1.5 text-[13px] text-text-secondary transition-colors hover:border-border-strong hover:text-text-primary md:px-2.5"
      >
        <span>{theme === "dark" ? "☾" : "☀"}</span>
        <span className="hidden md:inline">Theme</span>
      </button>
    </header>
  );
}
