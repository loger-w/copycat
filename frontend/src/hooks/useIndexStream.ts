/** 指數流 hook(index-board SC-1/SC-4;App 層常駐)。
 *
 * 手寫 WS + fetch(非 TanStack Query):常駐 WS merge 流與 useStockStream 同型例外
 * (TQ 慣例適用於 request/response,不適用常駐推播)。
 * merge 契約(design R6/F3):scalar 覆蓋 + last_minute upsert;trade_date 變更或
 * reconnect → refetch /api/index/state 全量。
 */

import { useEffect, useRef, useState } from "react";

import { commitRef } from "@/lib/commit-ref";
import { connectWithRetry } from "@/lib/ws-reconnect";
import type { WsStatus } from "@/types";

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

/** refetch 失敗重試的退避(WS 重連退避已移進 `connectWithRetry`)。 */
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

/** WS 一則訊息的線上形狀(原本寫在 `handle` 的參數位置,抽名字給 helper 的 cast 用)。 */
interface WireMsg {
  type: string;
  trade_date?: string;
  twse?: WireSeries;
  otc?: WireSeries;
  txf?: TxfQuote | null;
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

  // refetch 失敗重試(fix/index-chart-empty-minutes):換日清空後 refetch 失敗若只
  // warn 不重試,失敗點之前的分鐘永久缺失(WS merge 只補 last_minute 增量)——
  // 分時圖殼在、線不見的前端路徑。單一 pending timer(不堆疊)+ 指數退避,成功歸零。
  const retryTimerRef = useRef<number | undefined>(undefined);
  const retryAttemptRef = useRef(0);
  const aliveRef = useRef(true);
  // 世代守門(review T-6):refetch 有四個併發呼叫源(mount / onopen / 換日 / 退避
  // timer),先發後至的舊回應不得整份覆蓋新回應(trade_date 會倒退)。
  const fetchSeqRef = useRef(0);

  // WS handler 是 deps `[]` 的閉包,讀不到最新 state → 靠這三顆 ref 取當下值。
  //
  // **imperative 配對**(N119,2026-08-24 升級;同 `useFuturesStream` / `useStockStream`):
  // 每個寫入點都走 `commitRef`(寫 ref → setState,單一出口)。改前 ref 只在 commit 後由
  // 一支 `useLayoutEffect` 同步,同一個 macrotask 內兩則訊息時第二則讀到的是**上一次
  // commit** 的值 —— merge 基底舊 → 第一則的 last_minute 被抹掉;換日比對用舊日 →
  // 同一 tick 的第二則又被判成換日,再清一次序列、再打一次全量。兩者都會自癒
  // (下一格 upsert / onopen refetch),所以症狀只是「偶爾少一格 / 多一發」。
  //
  // 那支 layout effect 曾以「commit 後的 backstop」留著,two-axis review 收修時**移除**:
  // 配對之後 commit 的值恆 ≤ ref,它能寫進去的只有**較舊**的 commit 值,補不上漏掉的
  // 配對(mutation 實證:拿掉 refetch 的三行 ref 寫入、只留 backstop,兩支 hook 的
  // 「全量在途」測試同時轉紅)。要新增 setState 路徑就補 `commitRef`,沒有安全網可靠。

  const refetch = async (): Promise<void> => {
    const seq = ++fetchSeqRef.current;
    try {
      const res = await fetch("/api/index/state");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as {
        trade_date: string;
        twse: WireSeries;
        otc: WireSeries;
        txf: TxfQuote | null;
      };
      if (!aliveRef.current || seq !== fetchSeqRef.current) return; // 舊回應丟棄
      retryAttemptRef.current = 0;
      window.clearTimeout(retryTimerRef.current); // 成功 → 取消已排退避(review C-4)
      retryTimerRef.current = undefined;
      // ref 與 state 同批寫(imperative 配對):全量回來後緊接著抵達的 WS 訊息,
      // 基底必須是這一份而不是上一次 commit 的。
      commitRef(tradeDateRef, setTradeDate, body.trade_date);
      commitRef(twseRef, setTwse, toSeries(body.twse, null));
      commitRef(otcRef, setOtc, toSeries(body.otc, null));
      setTxf(body.txf); // 無 ref(handler 不以它為 merge 基底)
    } catch (err) {
      console.warn("index: state 載入失敗", err);
      // 已有更新一發在跑 → 重試交給它;pending timer 只留一顆不堆疊
      if (!aliveRef.current || seq !== fetchSeqRef.current) return;
      if (retryTimerRef.current !== undefined) return;
      const delay = Math.min(BACKOFF_START_MS * 2 ** retryAttemptRef.current, BACKOFF_CAP_MS);
      retryAttemptRef.current += 1;
      retryTimerRef.current = window.setTimeout(() => {
        retryTimerRef.current = undefined;
        void refetch();
      }, delay);
    }
  };

  useEffect(() => {
    aliveRef.current = true; // StrictMode remount:cleanup 後重進要復活
    void refetch();

    const handle = (msg: WireMsg): void => {
      if (msg.type !== "index") return;
      const incomingDate = msg.trade_date ?? null;
      if (
        incomingDate !== null &&
        tradeDateRef.current !== null &&
        incomingDate !== tradeDateRef.current
      ) {
        // 換日(F3):清本地 minutes,以全量 refetch 對齊。refetch 不 await 是安全的:
        // state 為全量快照恆 ≥ 增量,且後續 WS 訊息只會 upsert 新日分鐘(review A3)
        commitRef(tradeDateRef, setTradeDate, incomingDate);
        commitRef(twseRef, setTwse, null);
        commitRef(otcRef, setOtc, null);
        void refetch();
        return;
      }
      if (incomingDate !== null) commitRef(tradeDateRef, setTradeDate, incomingDate);
      if (msg.twse) commitRef(twseRef, setTwse, toSeries(msg.twse, twseRef.current));
      if (msg.otc) commitRef(otcRef, setOtc, toSeries(msg.otc, otcRef.current));
      if (msg.txf !== undefined) setTxf(msg.txf);
    };

    const conn = connectWithRetry(
      () => {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        return `${proto}://${window.location.host}/ws/index`;
      },
      {
        onConnecting: () => setWsStatus("connecting"),
        onOpen: () => {
          setWsStatus("open");
          void refetch(); // reconnect 對齊(F3:斷線期間漏訊息)
        },
        onMessage: (msg) => handle(msg as WireMsg),
        onClose: () => setWsStatus("closed"),
      },
      { label: "index ws" },
    );

    return () => {
      aliveRef.current = false;
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = undefined;
      conn.close();
    };
  }, []);

  return { twse, otc, txf, tradeDate, wsStatus };
}
