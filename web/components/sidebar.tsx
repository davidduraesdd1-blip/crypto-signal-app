"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { name: "Home", href: "/" },
  { name: "Signals", href: "/signals" },
  { name: "Regimes", href: "/regimes" },
  { name: "Backtester", href: "/backtester" },
  { name: "On-Chain", href: "/on-chain" },
  { name: "Alerts", href: "/alerts" },
  { name: "AI Assistant", href: "/ai-assistant" },
  { name: "Settings", href: "/settings" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 z-20 flex h-screen w-[var(--rail-w)] flex-col border-r border-border-default bg-bg-1 px-3 py-4 md:sticky">
      {/* Brand */}
      <div className="flex items-center gap-2 px-2.5 pb-6 pt-1">
        <div className="grid h-[22px] w-[22px] place-items-center rounded-md bg-accent-brand text-xs font-bold text-[var(--accent-ink)]">
          C
        </div>
        <div className="text-[14px] font-semibold tracking-tight text-text-primary">
          Crypto Signal App
        </div>
      </div>

      {/* Navigation - flat list */}
      <nav className="flex flex-col gap-0.5">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex min-h-[44px] items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] font-medium text-text-secondary transition-colors",
                "hover:bg-bg-2 hover:text-text-primary",
                isActive && "bg-accent-soft text-accent-brand"
              )}
            >
              <span
                className={cn(
                  "h-[5px] w-[5px] rounded-full bg-accent-brand opacity-0",
                  isActive && "opacity-100"
                )}
              />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname();

  // AUDIT-2026-05-06 (W2 Tier 1 F-MOBILE-1): pre-fix the bottom nav
  // exposed only 5 routes; On-Chain / Backtester / AI Assistant were
  // unreachable on mobile (CLAUDE.md §8 mobile-parity violation, the
  // sidebar is `hidden md:block`). Now mirrors the full sidebar in a
  // horizontally-scrollable bar — every route is one tap away. Short
  // labels keep tap-targets above the 44px floor.
  const mobileNavItems = [
    { name: "Home", short: "Home", href: "/" },
    { name: "Signals", short: "Signals", href: "/signals" },
    { name: "Regimes", short: "Regimes", href: "/regimes" },
    { name: "Backtester", short: "Backtest", href: "/backtester" },
    { name: "On-Chain", short: "On-chain", href: "/on-chain" },
    { name: "Alerts", short: "Alerts", href: "/alerts" },
    { name: "AI Assistant", short: "AI", href: "/ai-assistant" },
    { name: "Settings", short: "Settings", href: "/settings" },
  ];

  return (
    <nav
      aria-label="Primary"
      className="fixed bottom-0 left-0 right-0 z-20 flex h-14 items-center gap-1 overflow-x-auto border-t border-border-default bg-bg-1 px-2 md:hidden [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
      style={{ paddingBottom: "max(env(safe-area-inset-bottom, 0), 0px)" }}
    >
      {mobileNavItems.map((item) => {
        const isActive = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "flex min-h-[44px] min-w-[60px] flex-shrink-0 flex-col items-center justify-center gap-0.5 rounded-lg px-2 py-1 text-[10.5px] font-medium text-text-secondary",
              "hover:text-text-primary",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand",
              isActive && "bg-accent-soft text-accent-brand"
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "h-[5px] w-[5px] rounded-full bg-accent-brand",
                !isActive && "opacity-0"
              )}
            />
            <span>{item.short}</span>
          </Link>
        );
      })}
    </nav>
  );
}
