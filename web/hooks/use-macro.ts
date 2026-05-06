/**
 * web/hooks/use-macro.ts
 * @endpoint GET /macro/strip
 * Drives the Home MacroStrip + Regimes MacroOverlay (Everything-Live).
 */
import { useQuery } from "@tanstack/react-query";

import { getMacroStrip } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useMacroStrip() {
  return useQuery({
    queryKey: queryKeys.macroStrip(),
    queryFn: ({ signal }) => getMacroStrip(signal),
    staleTime: STALE_TIME.SIGNALS,
    gcTime: GC_TIME.SIGNALS,
  });
}
