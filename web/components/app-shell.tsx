"use client";

import { Sidebar, MobileNav } from "./sidebar";
import { Topbar } from "./topbar";

interface AppShellProps {
  children: React.ReactNode;
  crumbs?: string;
  currentPage?: string;
  agentRunning?: boolean;
}

// AUDIT-2026-05-03 (Tier 4 HIGH): drop the `agentRunning = true` default
// — when omitted, Topbar's live `useExecutionStatus()` polling consults
// the API. The `true` literal was silently masking the live state on
// every page that didn't pass an explicit prop.
export function AppShell({ children, crumbs, currentPage, agentRunning }: AppShellProps) {
  return (
    <div className="app grid min-h-screen max-w-[100vw] grid-cols-1 grid-rows-[var(--topbar-h)_1fr_56px] overflow-x-hidden md:grid-cols-[var(--rail-w)_minmax(0,1fr)] md:grid-rows-[var(--topbar-h)_1fr]">
      {/* Desktop sidebar */}
      <div className="hidden md:block md:row-span-2">
        <Sidebar />
      </div>

      {/* Topbar */}
      <Topbar crumbs={crumbs} currentPage={currentPage} agentRunning={agentRunning} />

      {/* Main content */}
      <main className="min-w-0 max-w-full overflow-x-hidden overflow-y-auto p-4 pb-20 md:p-6 md:pb-6">
        {children}
      </main>

      {/* Mobile bottom nav */}
      <MobileNav />
    </div>
  );
}
