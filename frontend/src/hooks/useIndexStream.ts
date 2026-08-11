/** 指數流 hook(index-board SC-1/SC-4;App 層常駐)。
 *
 * 手寫 WS + fetch(非 TanStack Query):常駐 WS merge 流與 useStockStream 同型例外
 * (TQ 慣例適用於 request/response,不適用常駐推播)。
 * merge 契約(design R6/F3):scalar 覆蓋 + last_minute upsert;trade_date 變更或
 * reconnect → refetch /api/index/state 全量。
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";

export type WsStatus = "connecting" | "open" | "closed";

export interface IndexSeries {
  p: number | null;
  ref: number | null;
  high: number | null;
  low: number | null;
  stale: boolean;
  minutes: Record<string, number>;
}

export interface TxfQuote {
  p: number;
  time: string | null;
}

export interface IndexStreamState {
  twse: IndexSeries | null;
  otc: IndexSeries | null;
  txf: TxfQuote | null;
  tradeDate: string | null;
  wsStatus: WsStatus;
}

const BACKOFF_START_MS = 1_000;
const BACKOFF_CAP_MS = 30_000;

interface WireSeries {
  p: number | null;
  ref: number | null;
  high: number | null;
  low: number | null;
  stale?: boolean;
  last_minute?: [string, number] | null;
  minutes?: Record<string, number>;
}

function toSeries(w: WireSeries, prev: IndexSeries | null): IndexSeries {
  const minutes = { ...(w.minutes ?? prev?.minutes ?? {}) };
  if (w.last_minute) minutes[w.last_minute[0]] = w.last_minute[1];
  return {
    p: w.p,
    ref: w.ref,
    high: w.high,
    low: w.low,
    stale: Boolean(w.stale),
    minutes,
  };
}

export function useIndexStream(): IndexStreamState {
  const [twse, setTwse] = useState<IndexSeries | null>(null);
  const [otc, setOtc] = useState<IndexSeries | null>(null);
  const [txf, setTxf] = useState<TxfQuote | null>(null);
  const [tradeDate, setTradeDate] = useState<string | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");

  const twseRef = useRef<IndexSeries | null>(null);
  const otcRef = useRef<IndexSeries | null>(null);
  const tradeDateRef = useRef<string | null>(null);

  // WS handler 是 deps `[]` 的閉包,讀不到最新 state → 靠這三顆 ref 取當下值。同步寫在
  // layout effect 而非 render 期間:render 必須是純的(StrictMode / 中止的 render 都會
  // 讓 ref 提前髒掉),而 layout effect 在 paint 前同步跑完,WS 訊息一律晚於它抵達。
  //
  // 兩條維護前提(review F-6 / TC-1):
  // 1. **凡被 WS handler 以 ref 讀取的 state,一律進本 effect 的 deps**。少列一個的症狀是
  //    handler 永遠讀到第一輪的值(merge 基底 / 換日比對用舊值),沒有任何錯誤訊號。
  // 2. 本 ref **只在 commit 之後同步,handler 內不做同 tick 回寫** —— 與
  //    `useFuturesStream` / `useStockStream` 那種 imperative 配對(寫入點當場同步 ref)
  //    **不同級**:那種配對連「同一個 tick 內兩則訊息 read-modify-write」都守得住,這裡
  //    守不住(第二則讀到的仍是上一次 commit 的值)。本 hook 的 handler 目前沒有同 tick
  //    連鎖需求,故可接受;日後若有,要升級成 imperative 配對,不是再加 deps。
  useLayoutEffect(() => {
    twseRef.current = twse;
    otcRef.current = otc;
    tradeDateRef.current = tradeDate;
  }, [twse, otc, tradeDate]);

  const refetch = async (): Promise<void> => {
    try {
      const res = await fetch("/api/index/state");
      if (!res.ok) return;
      const body = (await res.json()) as {
        trade_date: string;
        twse: WireSeries;
        otc: WireSeries;
        txf: TxfQuote | null;
      };
      setTradeDate(body.trade_date);
      setTwse(toSeries(body.twse, null));
      setOtc(toSeries(body.otc, null));
      setTxf(body.txf);
    } catch (err) {
      console.warn("index: state 載入失敗", err);
    }
  };

  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let backoff = BACKOFF_START_MS;

    void refetch();

    const handle = (msg: {
      type: string;
      trade_date?: string;
      twse?: WireSeries;
      otc?: WireSeries;
      txf?: TxfQuote | null;
    }): void => {
      if (msg.type !== "index") return;
      const incomingDate = msg.trade_date ?? null;
      if (
        incomingDate !== null &&
        tradeDateRef.current !== null &&
        incomingDate !== tradeDateRef.current
      ) {
        // 換日(F3):清本地 minutes,以全量 refetch 對齊。refetch 不 await 是安全的:
        // state 為全量快照恆 ≥ 增量,且後續 WS 訊息只會 upsert 新日分鐘(review A3)
        setTradeDate(incomingDate);
        setTwse(null);
        setOtc(null);
        void refetch();
        return;
      }
      if (incomingDate !== null) setTradeDate(incomingDate);
      if (msg.twse) setTwse(toSeries(msg.twse, twseRef.current));
      if (msg.otc) setOtc(toSeries(msg.otc, otcRef.current));
      if (msg.txf !== undefined) setTxf(msg.txf);
    };

    const connect = (): void => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/index`);
      setWsStatus("connecting");
      ws.onopen = () => {
        backoff = BACKOFF_START_MS;
        setWsStatus("open");
        void refetch(); // reconnect 對齊(F3:斷線期間漏訊息)
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          handle(JSON.parse(ev.data));
        } catch (err) {
          console.warn("index ws: 無法解析訊息", err);
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

  return { twse, otc, txf, tradeDate, wsStatus };
}
