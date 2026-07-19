// trade hooks 集中一檔共用 parseError / fetch helper(PLAN 原列三檔,[phase-3 補註]:
// 三檔各抄一份 parseError 違反 DRY,收斂為單檔多 export,對外 API 不變)。
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  OrderPreviewBody,
  OrderPreviewResult,
  OrdersView,
  SubmitResult,
  TradeAccount,
} from "@/types";

async function parseError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as {
      detail?: { error?: string; err_code?: string };
    };
    const code = body.detail?.error ?? `HTTP_${res.status}`;
    // BROKER_REJECTED 附帶 err_code 供 UI 顯示(trade-text 解 ":" 後綴)
    if (code === "BROKER_REJECTED" && body.detail?.err_code) {
      return `${code}:${body.detail.err_code}`;
    }
    return code;
  } catch {
    return `HTTP_${res.status}`;
  }
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as T;
}

export function useTradeAccount() {
  return useQuery({
    queryKey: ["trade-account"],
    queryFn: () => getJson<TradeAccount>("/api/trade/account"),
    refetchInterval: 10_000,
    retry: 1,
  });
}

export function useOrders() {
  return useQuery({
    queryKey: ["trade-orders"],
    queryFn: () => getJson<OrdersView>("/api/trade/orders"),
    refetchInterval: 2_000,
    retry: 1,
  });
}

export function usePreviewOrder() {
  return useMutation({
    mutationFn: (body: OrderPreviewBody) =>
      postJson<OrderPreviewResult>("/api/trade/preview", body),
  });
}

export function useConfirmOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (previewId: string) =>
      postJson<SubmitResult>("/api/trade/orders", { preview_id: previewId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["trade-orders"] });
    },
  });
}
