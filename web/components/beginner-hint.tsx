"use client";
/**
 * web/components/beginner-hint.tsx
 *
 * AUDIT-2026-05-06 (W2 Tier 6 F-LEVEL-1): reusable Beginner-tier gloss
 * card. Renders only when useUserLevel().level === "Beginner". Each
 * unwired page (Home, Regimes, On-Chain, Backtester, AI Assistant,
 * Alerts) drops this in at the top with a 1-2 sentence plain-English
 * explanation of what the page does.
 *
 * Per CLAUDE.md §7: "Beginner — Plain English everywhere — zero
 * jargon. 'What does this mean for me?' summary after every signal/
 * score." This component is the cheapest way to honor that mandate
 * across pages without rewriting their layouts.
 *
 * Intermediate / Advanced see nothing — the content collapses to
 * null so they can't see this beginner content cluttering their UI.
 */
import type { ReactNode } from "react";
import { useUserLevel } from "@/providers/user-level-provider";

interface BeginnerHintProps {
  title: string;
  children: ReactNode;
}

export function BeginnerHint({ title, children }: BeginnerHintProps) {
  const { level } = useUserLevel();
  if (level !== "Beginner") return null;
  return (
    <div className="mb-5 rounded-xl border-l-[3px] border-accent-brand bg-bg-1 p-4">
      <div className="text-xs font-medium uppercase tracking-wider text-text-muted">
        {title}
      </div>
      <div className="mt-1.5 text-[13px] leading-relaxed text-text-secondary">
        {children}
      </div>
    </div>
  );
}
