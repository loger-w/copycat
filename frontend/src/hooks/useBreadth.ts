/** 全市場家數帶 / 騰落線資料流 hook(market-overview R2 SC-4;App 層常駐)。
 *
 * 手寫 WS + fetch(非 TanStack Query):常駐推播 merge 流與 `useIndexStream` 同型例外
 * (TQ 慣例適用於 request/response)。
 * merge 契約(design §7 R8):scalar(counts/stale/as_of)覆寫;`last_minute` 依 `t`
 * upsert(同 t 覆寫、新 t 升冪插入);`trade_date` 與本地不同 → 清 series + refetch;
 * WS `onopen` → refetch 全量(補回斷線期間漏掉的分鐘格),回應以 union-by-t 併回在途
 * 期間抵達的增量格(見 `mergeSnapshot`)。
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { BreadthPoint, BreadthState } from "@/types";

const ENDPOINT = "/api/market/breadth";
const BACKOFF_START_MS = 1_000;
const BACKOFF_CAP_MS = 30_000;

/** WS 每輪一則;`last_minute` 只在該輪真的 append 了一格時帶值。 */
interface WireMsg {
  type: string;
  trade_date?: string | null;
  as_of?: string | null;
  stale?: boolean;
  counts?: BreadthState["counts"];
  last_minute?: BreadthPoint | null;
}

/** 依 `t` upsert 並維持升冪 —— 後端雖是順序 append,但 reconnect refetch 與增量
 *  可能交錯抵達,順序交給這裡保證,圖層才不必再排一次。 */
function upsert(series: BreadthPoint[], point: BreadthPoint): BreadthPoint[] {
  const idx = series.findIndex((p) => p.t >= point.t);
  if (idx < 0) return [...series, point];
  if (series[idx]!.t === point.t) {
    const next = [...series];
    next[idx] = point;
    return next;
  }
  return [...series.slice(0, idx), point, ...series.slice(idx)];
}

/** 全量回應併回「fetch 在途期間抵達的 WS 增量格」(review P2-3)。
 *
 *  refetch 拍的是發出請求那一刻的快照,回應在飛的期間 WS 可能已經 append 了新的分鐘格;
 *  直接整份取代會把那幾格靜默抹掉(reconnect onopen 必 refetch,所以這條路很常走)。
 *  以回應為基底做 union-by-t:同 t 以回應為準(全量恆為權威),回應缺席而本地有的補回,
 *  順序交給 `upsert` 維持升冪。`trade_date` 不同 = 本地序列屬舊日,不合併。 */
function mergeSnapshot(prev: BreadthState | null, next: BreadthState): BreadthState {
  if (prev === null || prev.trade_date !== next.trade_date) return next;
  const inNext = new Set(next.series.map((p) => p.t));
  const missing = prev.series.filter((p) => !inNext.has(p.t));
  if (missing.length === 0) return next;
  let series = next.series;
  for (const point of missing) series = upsert(series, point);
  return { ...next, series };
}

export function useBreadth(): BreadthState | null {
  const [state, setState] = useState<BreadthState | null>(null);
  const stateRef = useRef<BreadthState | null>(null);

  // WS handler 是 deps `[]` 的閉包,讀不到最新 state → 靠這顆 ref 取當下值。同步寫在
  // layout effect 而非 render 期間:render 必須是純的(StrictMode / 中止的 render 都會
  // 讓 ref 提前髒掉),而 layout effect 在 paint 前同步跑完,WS 訊息一律晚於它抵達。
  useLayoutEffect(() => {
    stateRef.current = state;
  }, [state]);

  const refetch = async (): Promise<void> => {
    try {
      const res = await fetch(ENDPOINT);
      if (!res.ok) return;
      const snapshot = (await res.json()) as BreadthState;
      setState((prev) => mergeSnapshot(prev, snapshot));
    } catch (err) {
      console.warn("breadth: state 載入失敗", err);
    }
  };

  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let backoff = BACKOFF_START_MS;

    void refetch();

    const handle = (msg: WireMsg): void => {
      if (msg.type !== "breadth") return;
      const incomingDate = msg.trade_date ?? null;
      const localDate = stateRef.current?.trade_date ?? null;
      if (incomingDate !== null && localDate !== null && incomingDate !== localDate) {
        // 換日:本地序列屬於舊日,清掉並以全量 refetch 對齊(refetch 不 await 安全 ——
        // 全量快照恆 ≥ 增量,後續 WS 訊息只會 upsert 新日的分鐘鍵)
        setState((prev) =>
          prev === null ? prev : { ...prev, trade_date: incomingDate, series: [] },
        );
        void refetch();
        return;
      }
      setState((prev) => {
        if (prev === null) return prev; // 初載 fetch 尚未回來:全量將覆蓋,不從增量拼半份
        const series = msg.last_minute ? upsert(prev.series, msg.last_minute) : prev.series;
        return {
          ...prev,
          trade_date: incomingDate ?? prev.trade_date,
          as_of: msg.as_of ?? null,
          stale: Boolean(msg.stale),
          counts: msg.counts ?? null,
          series,
        };
      });
    };

    const connect = (): void => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/breadth`);
      ws.onopen = () => {
        backoff = BACKOFF_START_MS;
        void refetch(); // reconnect 對齊:斷線期間的分鐘格只在全量裡
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          handle(JSON.parse(ev.data) as WireMsg);
        } catch (err) {
          console.warn("breadth ws: 無法解析訊息", err);
        }
      };
      ws.onclose = () => {
        if (!alive) return;
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

  return state;
}
