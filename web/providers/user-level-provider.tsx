"use client";
/**
 * web/providers/user-level-provider.tsx
 *
 * AUDIT-2026-05-05 (P0-5, Phase 0.9 Tier 6 finding): the Beginner /
 * Intermediate / Advanced user-tier system was decorative pre-fix —
 * `level` lived in local state inside Topbar and was never consumed by
 * any of the 15 user-facing pages. Per CLAUDE.md §7 the system is
 * mandatory across all 3 family-office apps.
 *
 * This provider lifts the localStorage logic out of Topbar so any
 * component can read or scale to the level via `useUserLevel()`.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type UserLevel = "Beginner" | "Intermediate" | "Advanced";

const STORAGE_KEY = "crypto-signal-app:user-level";

// CLAUDE.md §7 (master): "Default on first run = Beginner". The earlier
// Topbar default was Intermediate — fixed here at the provider level so
// every consumer sees the same default. Existing users keep whatever's
// in localStorage.
const DEFAULT_LEVEL: UserLevel = "Beginner";

function readPersisted(): UserLevel {
  if (typeof window === "undefined") return DEFAULT_LEVEL;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "Beginner" || v === "Intermediate" || v === "Advanced") return v;
  } catch {
    /* localStorage may be unavailable — Capacitor private mode, etc. */
  }
  return DEFAULT_LEVEL;
}

interface UserLevelContextValue {
  level: UserLevel;
  setLevel: (next: UserLevel) => void;
  /** True if level is at least the given tier. Beginner < Intermediate < Advanced. */
  atLeast: (tier: UserLevel) => boolean;
  /** Pick a value based on the current level. */
  pick: <T>(opts: { beginner?: T; intermediate?: T; advanced?: T; fallback: T }) => T;
}

const UserLevelContext = createContext<UserLevelContextValue | null>(null);

export function UserLevelProvider({ children }: { children: ReactNode }) {
  const [level, setLevelState] = useState<UserLevel>(() => readPersisted());

  // SSR returns DEFAULT_LEVEL; sync to localStorage value after hydration.
  useEffect(() => {
    const persisted = readPersisted();
    if (persisted !== level) setLevelState(persisted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setLevel = useCallback((next: UserLevel) => {
    setLevelState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<UserLevelContextValue>(() => {
    const rank: Record<UserLevel, number> = { Beginner: 0, Intermediate: 1, Advanced: 2 };
    return {
      level,
      setLevel,
      atLeast: (tier) => rank[level] >= rank[tier],
      pick: ({ beginner, intermediate, advanced, fallback }) => {
        if (level === "Beginner" && beginner !== undefined) return beginner;
        if (level === "Intermediate" && intermediate !== undefined) return intermediate;
        if (level === "Advanced" && advanced !== undefined) return advanced;
        return fallback;
      },
    };
  }, [level, setLevel]);

  return <UserLevelContext.Provider value={value}>{children}</UserLevelContext.Provider>;
}

export function useUserLevel(): UserLevelContextValue {
  const ctx = useContext(UserLevelContext);
  if (!ctx) {
    // Defensive fallback — if a component renders outside the provider
    // (e.g. in a Storybook story, or during a test), surface a sane
    // default instead of crashing the page. This also keeps Tier 6
    // QA scenarios stable while we incrementally wire pages.
    return {
      level: DEFAULT_LEVEL,
      setLevel: () => {
        // eslint-disable-next-line no-console
        console.warn("[useUserLevel] called outside <UserLevelProvider> — setLevel is a no-op");
      },
      atLeast: (tier) => tier === "Beginner",
      pick: ({ beginner, fallback }) => beginner ?? fallback,
    };
  }
  return ctx;
}
