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

  const mobileNavItems = [
    { name: "Home", href: "/" },
    { name: "Signals", href: "/signals" },
    { name: "Regimes", href: "/regimes" },
    { name: "Alerts", href: "/alerts" },
    { name: "Settings", href: "/settings" },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-20 flex h-14 items-center justify-around border-t border-border-default bg-bg-1 px-1 md:hidden">
      {mobileNavItems.map((item) => {
        const isActive = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex min-h-[44px] min-w-[44px] flex-col items-center justify-center gap-0.5 rounded-lg px-2.5 py-1 text-[10.5px] font-medium text-text-secondary",
              "hover:text-text-primary",
              isActive && "bg-accent-soft text-accent-brand"
            )}
          >
            <span
              className={cn(
                "h-[5px] w-[5px] rounded-full bg-accent-brand",
                !isActive && "opacity-0"
              )}
            />
            <span>{item.name}</span>
          </Link>
        );
      })}
    </nav>
  );
}
