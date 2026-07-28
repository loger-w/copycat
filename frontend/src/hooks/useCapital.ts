/** 群益 capital hooks:TQ polling + WS 事件觸發 invalidate + 寫入 mutations(design §6)。
 *
 * WS 事件走 module-level pub/sub:useCapitalStream 是唯一 WS 連線(App 層掛一次),
 * 事件 fanout 到全域 listener set;orders/positions hooks 訂閱後 invalidate 對應
 * queryKey(200ms trailing debounce,回報連發只重抓尾端一次)。
 * fetch helper 複製 useTrade.ts 最小版(不動其本體;ORDER_BLOCKED 帶 reason 以 ":"
 * 後綴進 Error message,trade-text 解析)。
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

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
} from "@/types";

export type WsStatus = "connecting" | "open" | "closed";

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
// fetch helper(useTrade.ts 最小複製;error contract {detail:{error, reason?}})
// ---------------------------------------------------------------------------

/** 非 2xx body → 錯誤碼字串;ORDER_BLOCKED 附 reason 走 ":" 後綴(trade-text 契約)。 */
export async function parseCapitalError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as {
      detail?: { error?: string; reason?: string };
    };
    const code = body.detail?.error ?? `HTTP_${res.status}`;
    if (code === "ORDER_BLOCKED" && body.detail?.reason) {
      return `${code}:${body.detail.reason}`;
    }
    return code;
  } catch {
    return `HTTP_${res.status}`;
  }
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

/** WS 事件 → invalidate queryKey(trailing debounce:連發只在尾端重抓一次)。 */
function useEventInvalidate(eventName: string, queryKey: string): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    let timer: number | undefined;
    const unsub = subscribeCapitalEvents((ev) => {
      if (ev.event !== eventName) return;
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: [queryKey] });
      }, INVALIDATE_DEBOUNCE_MS);
    });
    return () => {
      window.clearTimeout(timer);
      unsub();
    };
  }, [queryClient, eventName, queryKey]);
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
  useEventInvalidate("capital_order", "capital-orders");
  return useQuery({
    queryKey: ["capital-orders"],
    queryFn: () => fetchJson<{ orders: CapitalOrder[] }>("/api/capital/orders"),
    refetchInterval: 30_000,
    retry: 1,
  });
}

export function useCapitalPositions() {
  useEventInvalidate("capital_position", "capital-positions");
  return useQuery({
    queryKey: ["capital-positions"],
    queryFn: () => fetchJson<{ positions: CapitalPosition[] }>("/api/capital/positions"),
    refetchInterval: 15_000,
    retry: 1,
  });
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
// WS 連線(App 層掛一次;wsStatus 供閃電梯武裝 conn_lost 自動解除)
// ---------------------------------------------------------------------------

const BACKOFF_START_MS = 1_000;
const BACKOFF_CAP_MS = 30_000;

export function useCapitalStream(): { wsStatus: WsStatus } {
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");

  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let backoff = BACKOFF_START_MS;

    const connect = (): void => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/capital`);
      setWsStatus("connecting");
      ws.onopen = () => {
        backoff = BACKOFF_START_MS;
        setWsStatus("open");
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(ev.data) as CapitalEvent;
          if (typeof msg.event === "string") emitCapitalEvent(msg);
        } catch (err) {
          console.warn("capital ws: 無法解析訊息", err);
        }
      };
      ws.onclose = () => {
        if (!alive) return;
        setWsStatus("closed");
        timer = window.setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, BACKOFF_CAP_MS);
      };
      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();
    return () => {
      alive = false;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return { wsStatus };
}
