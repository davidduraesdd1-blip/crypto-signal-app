# D4 Frontend §4 Audit — 2026-05-03

**Trigger:** CLAUDE.md §4 — D4 sprint completed (10 commits 78104cb →
c846387), full audit of the new code surface mandatory.

**Auditor:** focused subagent, ~3.5 min runtime.

**Scope:** `web/lib/*`, `web/hooks/*`, `web/providers/*`,
`web/app/**/page.tsx` (15 routes), `web/components/topbar.tsx`,
`web/tests/api-contract.test.ts`, `web/.env.local.example`.

---

## Executive summary

| Severity | Count | Action |
|---|---|---|
| CRITICAL | 1 | False alarm — endpoint already correct (verified by D4d contract test against live deploy) |
| HIGH     | 6 | All shipped in `5cf6f7f` |
| MEDIUM   | 9 | Shipped in this batch — `<commit>` |
| LOW      | 6 | Mostly shipped in this batch; remainder noted in TODO(D-ext) |

22 findings. Surface area otherwise solid: error envelope clean,
query keys well-factored, contract test caught real drift on first
run.

---

## CRITICAL — false alarm (no action)

**`/execute/status` endpoint mismatch?** The agent flagged this but
the contract test in `c846387` already verified the path works
end-to-end against the live deploy:

```bash
curl -H "X-API-Key: $KEY" https://crypto-signal-app-1fsi.onrender.com/execute/status
# → 200 OK
```

The earlier drift (`/execution/status` in TS vs `/execute/status` in
FastAPI) was caught + fixed in `c846387`. The contract test now
passes. No action needed.

---

## HIGH — shipped in `5cf6f7f`

1. **`useRefreshAll` double-fetch** — dropped redundant
   `refetchQueries({type:"active"})` since `invalidateQueries()`
   already triggers refetch. -50% request volume per Refresh click.

2. **AI Assistant `running` stale-closure** — added
   `useEffect(() => setRunning(apiAgentRunning), [apiAgentRunning])`
   to sync local state to server-side state on every refetch.

3. **Settings forms hydration race** — `useRef("hydrated")` guard in
   3 settings pages so refetch can't clobber user edits.

4. **Settings save copy leak** — replaced "applied to
   alerts_config.json" with backend-agnostic "all values applied".

5. **`formatPct` magnitude heuristic broken** — removed the
   `if abs(v) <= 1.5: v *= 100` heuristic. The API emits already-
   percent values (e.g. 2.14 for 2.14%); the heuristic incorrectly
   inflated flat-day "+0.8%" changes to "+80.0%". New
   `formatPctFromFraction()` for explicit-contract use cases.

6. **`triggerScan` ApiError discriminators** — actionable copy
   ("API key missing", "rate-limited — wait", "blocked from this
   region") instead of raw Python detail strings.

7. **`JSON.stringify(detail)` circular-ref crash** — try/catch
   wrapper. Bonus: array-shaped FastAPI validation-error detail now
   pulls first entry's `.msg` instead of rendering as
   "[object Object],[object Object]".

---

## MEDIUM — shipped in this batch

8. **`useScanStatus` always polls** — function-form
   `refetchInterval: (query) => query.state.data?.running ? 5_000 : false`
   so polling only fires while a scan is actually running.
   -720 requests/hour per page when idle.

9. **`window.location.href` in alerts tabs** — replaced with
   `router.push()` from `next/navigation`. Preserves TanStack Query
   cache + React state across the tab switch.

10. **Topbar theme local-state desync** — switched to
    `useTheme()` from `next-themes`. The prior code hand-managed the
    `.light` class on `<html>` while the ThemeProvider also owned the
    class via `attribute="class"`, causing reload to always revert
    to dark.

11. **Topbar level not persisted** — added localStorage persistence
    via `crypto-signal-app:user-level` key. Per CLAUDE.md §7, user
    level must persist across pages.

12. **`String(detail.detail)` produces `"[object Object]"` on
    arrays** — fixed in HIGH-7 batch (FastAPI validation error
    arrays now render as the first entry's `.msg`).

13. **`formatUsd` 950K-1M rounding** — false alarm on closer
    review; the M branch covers ≥950K correctly. No fix.

14. **Duplicated `regime` / `regime_label` in API types** — server-
    side change; documented for future Pydantic cleanup.

15. **`[extra: string]: unknown` index signatures** — defeats
    type-narrowing on `SignalRow`. Acknowledged trade-off for D4
    flexibility; future tightening when Pydantic models stabilize.

16. **`useExecutionStatus` always polls 5s** — UX trade-off, not
    auto-safe to change. Documented for D6 perf pass.

---

## LOW — shipped in this batch (cleanup)

17. **`getOnchainMetric` raw `metric` URL** — added
    `encodeURIComponent`.

18. **Unused `directionToSignalType` import in
    `app/backtester/page.tsx`** — removed.

19. **`key={idx}` in dev-tools endpoints table** — switched to
    `${ep.method}-${ep.path}` for stable React reconciliation.

20. **Raw ISO `lastCheck` timestamp on Dev Tools** — formatted as
    "14:32:14" via `toLocaleTimeString`.

21. **Raw ISO `r.timestamp` in AI decisions table** — formatted
    same-day as time-only, multi-day as "May 03, 14:32".

22. **`directionToSignalType` silent "hold" fallback** — accepted as
    intentional (every unknown direction safely falls back to hold).
    No warn added per "don't add error handling for scenarios that
    can't happen" rule.

---

## Net result

- CRITICAL: 0 (false alarm reverted on inspection)
- HIGH: 7/7 shipped (`5cf6f7f`)
- MEDIUM: 5/9 shipped, 4 documented as design trade-offs or
  server-side concerns
- LOW: 5/6 shipped, 1 acknowledged as intentional

Build clean every commit. Contract test green against live deploy.

## Restore reference

If any post-audit fix regresses Phase D, restore points:
- `pre-db-rewrite-2026-05-03` (before today's whole D-day)
- `c846387` (D4 closure)
- `5cf6f7f` (post-HIGH-batch checkpoint)
