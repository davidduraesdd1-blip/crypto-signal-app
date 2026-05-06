"use client";

import { Sidebar, MobileNav } from "./sidebar";
import { Topbar } from "./topbar";
import { useAndroidBackButton } from "@/hooks/use-android-back-button";

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
//
// AUDIT-2026-05-06 (W2 Tier 6 P0): added skip-to-content link + main
// landmark id. WCAG 2.4.1 (Bypass Blocks) — keyboard users should be
// able to skip the topbar / sidebar nav and jump straight to content.
// The link is visually hidden until focused via Tab.
export function AppShell({ children, crumbs, currentPage, agentRunning }: AppShellProps) {
  // AUDIT-2026-05-06 (W2 Tier 7 P0): Android hardware back button wired
  // to router.back() inside Capacitor's WebView. No-op on web/iOS.
  useAndroidBackButton();

  return (
    <div className="app grid min-h-screen max-w-[100vw] grid-cols-1 grid-rows-[var(--topbar-h)_1fr_56px] overflow-x-hidden md:grid-cols-[var(--rail-w)_minmax(0,1fr)] md:grid-rows-[var(--topbar-h)_1fr]">
      {/* Skip-to-content — first focusable on every page */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:border focus:border-accent-brand focus:bg-bg-1 focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-text-primary focus:shadow-lg"
      >
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <div className="hidden md:block md:row-span-2">
        <Sidebar />
      </div>

      {/* Topbar */}
      <Topbar crumbs={crumbs} currentPage={currentPage} agentRunning={agentRunning} />

      {/* Main content */}
      <main
        id="main-content"
        tabIndex={-1}
        className="min-w-0 max-w-full overflow-x-hidden overflow-y-auto p-4 pb-20 md:p-6 md:pb-6"
      >
        {children}
      </main>

      {/* Mobile bottom nav */}
      <MobileNav />
    </div>
  );
}
