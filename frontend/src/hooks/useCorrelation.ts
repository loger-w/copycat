/** 相關係數流:/ws/corr 每秒推全量快照 + GET /api/corr/state 初次載入(SC-6/7)。
 *
 * 與 useFuturesStream 的關鍵差異:corr payload 是**全量快照**(不是 per-product 增量),
 * 最新一則即完整狀態 → 不需要 seq 對齊、跳號 refetch、交錯緩衝那整套機制。
 * 每秒一則推播本身也是天然 heartbeat,client 靜默超過數秒即可判定連線異常。
 */
import { useEffect, useRef, useState } from "react";

import type { CorrState } from "@/types";

export type WsStatus = "connecting" | "open" | "closed";

export interface CorrStreamState {
  state: CorrState | null;
  wsStatus: WsStatus;
}

const BACKOFF_START_MS = 1_000;
const BACKOFF_CAP_MS = 30_000;

export function useCorrelation(): CorrStreamState {
  const [state, setState] = useState<CorrState | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");
  const seqRef = useRef<number>(-1);

  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let backoff = BACKOFF_START_MS;

    const apply = (next: CorrState): void => {
      // 全量快照:只擋住亂序抵達的舊快照,不做跳號 refetch
      if (next.seq < seqRef.current) return;
      seqRef.current = next.seq;
      setState(next);
    };

    const load = async (): Promise<void> => {
      try {
        const res = await fetch("/api/corr/state");
        if (!res.ok) return; // 503 = 引擎未就緒,等推播或下次重連
        const snap = (await res.json()) as CorrState;
        if (alive) apply(snap);
      } catch (err) {
        // 初次載入失敗不是致命的 —— 下一則推播就會補上完整狀態
        console.warn("corr: state 載入失敗", err);
      }
    };

    void load();

    const connect = (): void => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/corr`);
      setWsStatus("connecting");
      ws.onopen = () => {
        backoff = BACKOFF_START_MS;
        setWsStatus("open");
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(ev.data) as CorrState;
          if (msg.type !== "corr") return;
          apply(msg);
        } catch (err) {
          console.warn("corr ws: 無法解析訊息", err);
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

  return { state, wsStatus };
}
