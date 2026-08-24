import { useEffect, useState } from "react";

import { connectWithRetry } from "@/lib/ws-reconnect";
import type { Snapshot, WsStatus } from "@/types";

/** WS push 流(不套 TanStack Query:TQ 是 request/response 模型,design §5)。 */
export function useTxoSnapshot(): { data: Snapshot | null; wsStatus: WsStatus } {
  const [data, setData] = useState<Snapshot | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");

  useEffect(() => {
    const handle = connectWithRetry(
      () => {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        return `${proto}://${window.location.host}/ws/txo-pnl`;
      },
      {
        onConnecting: () => setWsStatus("connecting"),
        onOpen: () => setWsStatus("open"),
        onMessage: (msg) => setData(msg as Snapshot),
        onClose: () => setWsStatus("closed"),
      },
      { label: "txo-pnl" },
    );

    return () => {
      handle.close();
    };
  }, []);

  return { data, wsStatus };
}
