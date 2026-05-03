/**
 * web/hooks/use-ai.ts
 * @endpoint GET /ai/decisions
 * @endpoint POST /ai/ask
 * Drives the AI Assistant page Recent Decisions table + Ask box.
 */
import { useMutation, useQuery } from "@tanstack/react-query";

import { askAi, getAiDecisions } from "@/lib/api";
import type { AskAiInput, TradingPair } from "@/lib/api-types";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useAiDecisions(limit = 20, pair?: TradingPair) {
  return useQuery({
    queryKey: queryKeys.aiDecisions(limit, pair),
    queryFn: ({ signal }) => getAiDecisions(limit, pair, signal),
    staleTime: STALE_TIME.AI_DECISIONS,
    gcTime: GC_TIME.AI_DECISIONS,
  });
}

/** D4c — POST /ai/ask. No cache invalidation; the response is
 * caller-rendered (Ask box only). */
export function useAskAi() {
  return useMutation({
    mutationFn: (input: AskAiInput) => askAi(input),
  });
}
