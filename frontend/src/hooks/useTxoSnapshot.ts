import { useEffect, useState } from "react";

import type { Snapshot } from "@/types";

export type WsStatus = "connecting" | "open" | "closed";

const BACKOFF_START_MS = 1_000;
const BACKOFF_CAP_MS = 30_000;

/** WS push 流(不套 TanStack Query:TQ 是 request/response 模型,design §5)。 */
export function useTxoSnapshot(): { data: Snapshot | null; wsStatus: WsStatus } {
  const [data, setData] = useState<Snapshot | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");

  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let backoff = BACKOFF_START_MS;

    const connect = (): void => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/txo-pnl`);
      setWsStatus("connecting");
      ws.onopen = () => {
        backoff = BACKOFF_START_MS;
        setWsStatus("open");
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          setData(JSON.parse(ev.data) as Snapshot);
        } catch (err) {
          console.warn("txo-pnl: 無法解析 snapshot", err);
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

  return { data, wsStatus };
}
