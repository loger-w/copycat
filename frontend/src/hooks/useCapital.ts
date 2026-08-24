/** 群益 capital hooks:TQ polling + WS 事件觸發 invalidate + 寫入 mutations(design §6)。
 *
 * useCapitalStream 是唯一 WS 連線「與」唯一 invalidate 接線擁有者(App 層掛一次;
 * review B2/B4):WS 事件 fanout 到全域 listener set 之外,自己也訂閱並對
 * capital_order/capital_position 做 200ms trailing debounce invalidate(module-level
 * 單一 timer per queryKey,多元件用 orders/positions hooks 也不重複 invalidate)。
 * orders/positions hooks 只剩 TQ 輪詢 + 被動吃 invalidate;wsStatus 走 module store
 * (useCapitalWsStatus 任何元件可讀)。
 * fetch helper 的 detail 解析共用 lib/api-error,本檔只留 capital 專屬語意
 * (ORDER_BLOCKED 帶 reason 以 ":" 後綴進 Error message,trade-text 解析)。
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

import { parseErrorDetail } from "@/lib/api-error";
import { connectWithRetry } from "@/lib/ws-reconnect";
import type {
  CapitalCancelBody,
  CapitalCloseBody,
  CapitalCorrectPriceBody,
  CapitalDecreaseBody,
  CapitalFutureOrderBody,
  CapitalOrder,
  CapitalPosition,
  CapitalStatus,
  CapitalStockOrderBody,
  OrderResult,
  WsStatus,
} from "@/types";

// ---------------------------------------------------------------------------
// WS 事件 pub/sub(module-level;useCapitalStream 發布、query hooks 訂閱)
// ---------------------------------------------------------------------------

export interface CapitalEvent {
  event: string; // capital_status | capital_order | capital_position
  data: Record<string, unknown>;
}

type CapitalListener = (ev: CapitalEvent) => void;

const listeners = new Set<CapitalListener>();

/** 訂閱 capital WS 事件;回傳退訂函式。 */
export function subscribeCapitalEvents(fn: CapitalListener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** 發布事件到所有 listener(useCapitalStream 內部用;export 供測試)。 */
export function emitCapitalEvent(ev: CapitalEvent): void {
  for (const fn of listeners) fn(ev);
}

// ---------------------------------------------------------------------------
// wsStatus module store(useSyncExternalStore;任何元件經 useCapitalWsStatus 讀)
// ---------------------------------------------------------------------------

let currentWsStatus: WsStatus = "connecting";
const wsStatusListeners = new Set<() => void>();

/** 更新 wsStatus 並通知訂閱者(產品碼只由 useCapitalStream 呼叫;export 供測試注入)。 */
export function setCapitalWsStatus(next: WsStatus): void {
  if (next === currentWsStatus) return;
  currentWsStatus = next;
  for (const fn of wsStatusListeners) fn();
}

function subscribeWsStatus(fn: () => void): () => void {
  wsStatusListeners.add(fn);
  return () => {
    wsStatusListeners.delete(fn);
  };
}

/** capital WS 連線狀態(閃電梯 conn_lost 自動解除等用)。 */
export function useCapitalWsStatus(): WsStatus {
  return useSyncExternalStore(subscribeWsStatus, () => currentWsStatus);
}

// ---------------------------------------------------------------------------
// fetch helper(detail 解析走 lib/api-error;本檔只留 capital 的 ":" 後綴語意)
// ---------------------------------------------------------------------------

/** 非 2xx body → 錯誤碼字串;ORDER_BLOCKED 附 reason、BROKER_REJECTED 附 err_code,
 *  皆走 ":" 後綴(trade-text 契約)。 */
export async function parseCapitalError(res: Response): Promise<string> {
  const detail = await parseErrorDetail(res);
  const code = detail.error ?? `HTTP_${res.status}`;
  if (code === "ORDER_BLOCKED" && detail.reason) {
    return `${code}:${detail.reason}`;
  }
  if (code === "BROKER_REJECTED" && detail.err_code) {
    return `${code}:${detail.err_code}`;
  }
  return code;
}

async function fetchJson<T>(url: string, body?: unknown): Promise<T> {
  const init: RequestInit | undefined =
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        };
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await parseCapitalError(res));
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// queries
// ---------------------------------------------------------------------------

const INVALIDATE_DEBOUNCE_MS = 200;

/** WS event 名 → 對應 queryKey(useCapitalStream 唯一接線;review B2/B4)。 */
const EVENT_QUERY_KEY: Record<string, string> = {
  capital_order: "capital-orders",
  capital_position: "capital-positions",
};

// module-level 單一 timer per queryKey:同 key 連發只在尾端 invalidate 一次,
// 且不因多處掛載而重複(review B4)
const invalidateTimers = new Map<string, number>();

function scheduleInvalidate(queryClient: QueryClient, queryKey: string): void {
  const prev = invalidateTimers.get(queryKey);
  if (prev !== undefined) window.clearTimeout(prev);
  invalidateTimers.set(
    queryKey,
    window.setTimeout(() => {
      invalidateTimers.delete(queryKey);
      void queryClient.invalidateQueries({ queryKey: [queryKey] });
    }, INVALIDATE_DEBOUNCE_MS),
  );
}

function clearInvalidateTimers(): void {
  for (const timer of invalidateTimers.values()) window.clearTimeout(timer);
  invalidateTimers.clear();
}

export function useCapitalStatus() {
  return useQuery({
    queryKey: ["capital-status"],
    queryFn: () => fetchJson<CapitalStatus>("/api/capital/status"),
    refetchInterval: 10_000,
    retry: 1,
  });
}

export function useCapitalOrders() {
  return useQuery({
    queryKey: ["capital-orders"],
    queryFn: () => fetchJson<{ orders: CapitalOrder[] }>("/api/capital/orders"),
    refetchInterval: 30_000,
    retry: 1,
  });
}

const POSITIONS_POLL_MS = 15_000;

function positionsQueryOptions(refetchInterval: number | false) {
  return {
    queryKey: ["capital-positions"],
    queryFn: () => fetchJson<{ positions: CapitalPosition[] }>("/api/capital/positions"),
    refetchInterval,
    retry: 1,
  } as const;
}

/** 部位讀取端(側欄 / header / 圖牆 / 三座梯,現有 ≥ 4 處)。
 *
 *  **不帶 `refetchInterval`**(N068):每個 observer 各帶一份輪詢節奏時,相位由「掛載時點」
 *  決定 —— 同 tick 掛載的那幾個看起來像 15 s 一發,而 lazy 頁面 / 條件渲染的梯在別的時點
 *  掛上來就自帶一組相位,同一支 API 在 15 s 窗內被打好幾次,畫面上零訊號。
 *  節奏收斂到單一 provider(`useCapitalStream`,App 層掛一次)。
 *  代價(明示):**provider 不在場時本 hook 不輪詢**,只有掛載那一發 + WS 事件 invalidate。 */
export function useCapitalPositions() {
  return useQuery(positionsQueryOptions(false));
}

// ---------------------------------------------------------------------------
// mutations(成功一律 invalidate orders + positions)
// ---------------------------------------------------------------------------

function useCapitalMutation<TBody>(url: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) => fetchJson<OrderResult>(url, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["capital-orders"] });
      void queryClient.invalidateQueries({ queryKey: ["capital-positions"] });
    },
  });
}

export function useSubmitStock() {
  return useCapitalMutation<CapitalStockOrderBody>("/api/capital/order/stock");
}

export function useSubmitFuture() {
  return useCapitalMutation<CapitalFutureOrderBody>("/api/capital/order/future");
}

export function useCancelOrder() {
  return useCapitalMutation<CapitalCancelBody>("/api/capital/order/cancel");
}

export function useCorrectPrice() {
  return useCapitalMutation<CapitalCorrectPriceBody>("/api/capital/order/correct-price");
}

export function useDecreaseQty() {
  return useCapitalMutation<CapitalDecreaseBody>("/api/capital/order/decrease");
}

export function useClosePosition() {
  return useCapitalMutation<CapitalCloseBody>("/api/capital/position/close");
}

// ---------------------------------------------------------------------------
// WS 連線(App 層掛一次 = 唯一連線 + 唯一 invalidate 接線;review B2/B4)
// ---------------------------------------------------------------------------

export function useCapitalStream(): void {
  const queryClient = useQueryClient();

  // 部位輪詢的**唯一擁有者**(N068):本 hook 已是「App 層掛一次」的既有約定,節奏掛在
  // 這裡就與掛載時點無關。讀取端(useCapitalPositions)一律 refetchInterval: false。
  useQuery(positionsQueryOptions(POSITIONS_POLL_MS));

  useEffect(() => {
    // 唯一擁有者:WS 事件 → debounce invalidate(orders/positions hooks 不自行接線)
    const unsub = subscribeCapitalEvents((ev) => {
      const queryKey = EVENT_QUERY_KEY[ev.event];
      if (queryKey !== undefined) scheduleInvalidate(queryClient, queryKey);
    });

    const conn = connectWithRetry(
      () => {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        return `${proto}://${window.location.host}/ws/capital`;
      },
      {
        onConnecting: () => setCapitalWsStatus("connecting"),
        onOpen: () => setCapitalWsStatus("open"),
        onMessage: (raw) => {
          const msg = raw as CapitalEvent;
          if (typeof msg.event === "string") emitCapitalEvent(msg);
        },
        onClose: () => setCapitalWsStatus("closed"),
      },
      { label: "capital ws" },
    );

    return () => {
      unsub();
      clearInvalidateTimers();
      conn.close();
    };
  }, [queryClient]);
}
