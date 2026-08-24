/** 期貨行情流:/ws/futures 推播 + GET /api/futures/state 全量對齊(SC-8)。
 *
 * useStockStream 同款慣例:退避 1s→30s、seq 跳號(含回退)→ REST refetch 全量、
 * onopen 全量 refetch;refetch 期間交錯訊息進 pending buffer,snapshot(seq=S)套用後
 * 丟 seq ≤ S、依序併 seq > S(每則 WS 訊息帶該 product 全量 state,last-write-wins)。
 * 純邏輯抽 applyFuturesMsg / mergePending export 供單元測試。
 */
import { useEffect, useRef, useState } from "react";

import { connectWithRetry } from "@/lib/ws-reconnect";
import type { FuturesProductState, FuturesState, WsStatus } from "@/types";

export interface FuturesWsMsg {
  type: string; // "futures"
  seq: number;
  product: string;
  state: FuturesProductState;
}

export interface FuturesStreamState {
  state: FuturesState | null;
  wsStatus: WsStatus;
}

/** seq 對齊純邏輯:連續 → 併入該 product;跳號/回退/未就緒 → 要求 refetch。 */
export function applyFuturesMsg(
  prev: FuturesState | null,
  msg: FuturesWsMsg,
): { next: FuturesState | null; refetch: boolean } {
  if (prev === null) return { next: null, refetch: true }; // 全量未就緒 → 對齊
  if (msg.seq !== prev.seq + 1) return { next: prev, refetch: true }; // 跳號(含回退)
  return {
    next: { seq: msg.seq, products: { ...prev.products, [msg.product]: msg.state } },
    refetch: false,
  };
}

/** refetch 交錯緩衝合併:丟 seq ≤ snapshot、依序 last-write-wins 併 seq > snapshot。 */
export function mergePending(snap: FuturesState, pending: FuturesWsMsg[]): FuturesState {
  let next = snap;
  for (const msg of pending) {
    if (msg.seq <= next.seq) continue;
    next = { seq: msg.seq, products: { ...next.products, [msg.product]: msg.state } };
  }
  return next;
}

export function useFuturesStream(): FuturesStreamState {
  const [state, setState] = useState<FuturesState | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");

  // refetch 單飛 + 交錯緩衝(ref:WS callback 不隨 render 換)
  const stateRef = useRef<FuturesState | null>(null);
  const refetchingRef = useRef(false);
  const pendingRefetchRef = useRef(false);
  const pendingRef = useRef<FuturesWsMsg[]>([]);

  const refetch = async (): Promise<void> => {
    if (refetchingRef.current) {
      // in-flight 中的需求「合併不丟棄」— finally 補發(useStockStream CR1 同款)
      pendingRefetchRef.current = true;
      return;
    }
    refetchingRef.current = true;
    pendingRef.current = [];
    try {
      const res = await fetch("/api/futures/state");
      if (res.ok) {
        const snap = (await res.json()) as FuturesState;
        const next = mergePending(snap, pendingRef.current);
        stateRef.current = next;
        setState(next);
      }
    } catch (err) {
      console.warn("futures: state 載入失敗", err);
    } finally {
      refetchingRef.current = false;
      pendingRef.current = [];
      if (pendingRefetchRef.current) {
        pendingRefetchRef.current = false;
        void refetch();
      }
    }
  };

  useEffect(() => {
    void refetch();

    const handle = (msg: FuturesWsMsg): void => {
      if (msg.type !== "futures") return;
      if (refetchingRef.current) {
        pendingRef.current.push(msg);
        return;
      }
      const cur = stateRef.current;
      const out = applyFuturesMsg(cur, msg);
      if (out.next !== cur) {
        stateRef.current = out.next;
        setState(out.next);
      }
      if (out.refetch) {
        void refetch(); // 同步段先清 pending,再把本則入緩衝(useStockStream 同序)
        pendingRef.current.push(msg);
      }
    };

    const conn = connectWithRetry(
      () => {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        return `${proto}://${window.location.host}/ws/futures`;
      },
      {
        onConnecting: () => setWsStatus("connecting"),
        onOpen: () => {
          setWsStatus("open");
          void refetch(); // 重連對齊(斷線期間漏訊息)
        },
        onMessage: (msg) => handle(msg as FuturesWsMsg),
        onClose: () => setWsStatus("closed"),
      },
      { label: "futures ws" },
    );

    return () => {
      conn.close();
    };
  }, []);

  return { state, wsStatus };
}
