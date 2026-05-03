"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { cn } from "@/lib/utils";

const tabs = [
  { href: "/settings/trading", label: "Trading", icon: "📊" },
  { href: "/settings/signal-risk", label: "Signal & Risk", icon: "⚡" },
  { href: "/settings/dev-tools", label: "Dev Tools", icon: "🛠️" },
  { href: "/settings/execution", label: "Execution", icon: "⚙️" },
];

const subtitles: Record<string, string> = {
  "/settings/trading":
    "Configure pairs, signal thresholds, dev tools, and execution. Title shows 'Config Editor' at Advanced level.",
  "/settings/signal-risk":
    "Signal sizing thresholds and portfolio-level risk caps. These bind the composite signal model and any auto-execution loop.",
  "/settings/dev-tools":
    "Operator-grade developer tools — circuit breakers, database health, REST API server, and the legacy sidebar utilities relocated from the 2026-04 redesign.",
  "/settings/execution":
    "Connect OKX API keys to place real or paper orders directly from the dashboard. Paper mode is the default — real orders only fire when LIVE TRADING MODE is explicitly enabled.",
};

const tabNames: Record<string, string> = {
  "/settings/trading": "Trading",
  "/settings/signal-risk": "Signal & Risk",
  "/settings/dev-tools": "Dev Tools",
  "/settings/execution": "Execution",
};

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const currentTab = tabNames[pathname] || "Trading";

  return (
    <AppShell crumbs={`Account / Settings`} currentPage={currentTab}>
      <PageHeader
        title="Settings"
        subtitle={subtitles[pathname] || subtitles["/settings/trading"]}
      />

      {/* Tab navigation */}
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-border-default">
        {tabs.map((tab) => {
          const isActive = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "flex min-h-[44px] shrink-0 items-center gap-1.5 border-b-2 px-4 py-3 text-sm font-medium transition-colors",
                isActive
                  ? "border-accent-brand bg-accent-soft font-semibold text-text-primary"
                  : "border-transparent text-text-muted hover:text-text-secondary"
              )}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </Link>
          );
        })}
      </nav>

      {children}
    </AppShell>
  );
}
