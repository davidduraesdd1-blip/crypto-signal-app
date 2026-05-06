/**
 * web/hooks/use-agent.ts
 * @endpoints GET /ai/agent/summary, POST /ai/agent/start, POST /ai/agent/stop
 * Drives the AI Assistant page agent controls (Everything-Live).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getAgentSummary, startAgent, stopAgent, type AgentSummary } from "@/lib/api";
import { GC_TIME, queryKeys, STALE_TIME } from "@/lib/query-keys";

export function useAgentSummary({ polling = true }: { polling?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.agentSummary(),
    queryFn: ({ signal }) => getAgentSummary(signal),
    staleTime: STALE_TIME.EXECUTION_STATUS,
    gcTime: GC_TIME.EXECUTION_STATUS,
    refetchInterval: polling ? 10_000 : false,
    refetchOnWindowFocus: true,
  });
}

export function useStartAgent() {
  const qc = useQueryClient();
  return useMutation<AgentSummary, Error, void>({
    mutationFn: () => startAgent(),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.agentSummary(), data);
      qc.invalidateQueries({ queryKey: queryKeys.executionStatus() });
    },
  });
}

export function useStopAgent() {
  const qc = useQueryClient();
  return useMutation<AgentSummary, Error, void>({
    mutationFn: () => stopAgent(),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.agentSummary(), data);
      qc.invalidateQueries({ queryKey: queryKeys.executionStatus() });
    },
  });
}
