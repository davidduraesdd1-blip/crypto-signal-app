/**
 * web/hooks/use-exchange.ts
 * @endpoint POST /exchange/test-connection
 * @endpoint POST /execute/order
 * Drives the Settings · Execution "Test OKX Connection" button + the
 * manual-execute flows.
 */
import { useMutation } from "@tanstack/react-query";

import { placeOrder, testExchangeConnection } from "@/lib/api";
import type { PlaceOrderInput } from "@/lib/api-types";

/** D4c — Test OKX API key connection without placing an order. The
 * 503 (no keys configured) and 200 with `{ok: false, error: ...}`
 * both surface in the same UI. */
export function useTestExchangeConnection() {
  return useMutation({
    mutationFn: () => testExchangeConnection(),
  });
}

/** D4c — Place a paper or live order. Caller-provided
 * `client_order_id` enables idempotent retries (P4-C-4). */
export function usePlaceOrder() {
  return useMutation({
    mutationFn: (input: PlaceOrderInput) => placeOrder(input),
  });
}
