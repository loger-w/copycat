/** 個股 WS 流 + snapshot 對齊(design v4 §4;WS push 不套 TQ,同 useTxoSnapshot 慣例)。

seq gap 復原:跳號判定 `next != last+1`(含回退)→ refetch 全量 snapshot;
refetch 期間交錯的 tick 進 pending buffer,snapshot(seq=S)套用後丟 seq ≤ S、
依序 append seq > S。meta 基底走 snapshot(engine 不發 meta WS 型別,book 每則自足);
**當日高低由 tick 的 `h`/`l` 增量更新** —— 盤中不重抓 snapshot,掛 meta 上會停在舊值。 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { emitSignal, emitWsOpen } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";
import { applyTick, fromSnapshot, type StockAccum, type StockTickMsg } from "@/lib/stock-accum";

export type WsStatus = "connecting" | "open" | "closed";

export interface WatchlistQuote {
  p: number | null;
  chg_pct: number | null;
  vol: number | null;
  /** 今日參考價(round4 項 4)。**只在尚無成交時才有值**,與 `p` 互斥 ——
   *  參考價塞進 `p` 會讓畫面把昨收讀成今價。舊後端不發此欄 → null → 側欄維持 `-`。 */
  ref: number | null;
  /** 漲 / 跌停價(側欄亮燈用)。舊後端不發 → null → `limitState` 回 null = 不亮。
   *  **不可改用 `chg_pct ≈ ±10%` 推**:ETF ±20%、無漲跌幅商品都會誤判。 */
  upper: number | null;
  lower: number | null;
  no_data: boolean;
}

export interface StkfutQuote {
  prod: string;
  p: number;
  basis: number | null;
}

export interface StockStreamState {
  accum: StockAccum | null;
  watchlist: Record<string, WatchlistQuote>;
  status: { tc4: string; backfilling: string | null };
  stkfut: StkfutQuote | null;
  wsStatus: WsStatus;
}

const BACKOFF_START_MS = 1_000;
const BACKOFF_CAP_MS = 30_000;

interface WsMsg {
  type: string;
  code?: string;
  [key: string]: unknown;
}

export function useStockStream(code: string | null): StockStreamState {
  // WS 是全站唯一一條 → 自選失效的註冊點也只在這裡一處(design §8.1 / impl-review R10)。
  // 多處註冊(App + feed hook)會對同一則 watchlist_changed 重複 refetch。
  const queryClient = useQueryClient();
  const [accum, setAccum] = useState<StockAccum | null>(null);
  const [watchlist, setWatchlist] = useState<Record<string, WatchlistQuote>>({});
  const [status, setStatus] = useState<{ tc4: string; backfilling: string | null }>({
    tc4: "up",
    backfilling: null,
  });
  const [stkfut, setStkfut] = useState<StkfutQuote | null>(null);
  const [wsStatus, setWsStatus] = useState<WsStatus>("connecting");

  // refetch 單飛 + 交錯緩衝(ref:WS callback 不隨 render 換)
  const accumRef = useRef<StockAccum | null>(null);
  const refetchingRef = useRef(false);
  const pendingRefetchRef = useRef(false);
  const pendingRef = useRef<StockTickMsg[]>([]);
  const codeRef = useRef(code);
  codeRef.current = code;
  accumRef.current = accum;

  const refetch = async (): Promise<void> => {
    const current = codeRef.current;
    if (current === null) return;
    if (refetchingRef.current) {
      // CR1:in-flight 中的需求「合併不丟棄」— finally 補發,切檔/回補完成不被吞
      pendingRefetchRef.current = true;
      return;
    }
    refetchingRef.current = true;
    pendingRef.current = [];
    try {
      const res = await fetch(`/api/stock/state/${current}`);
      if (res.ok) {
        const snap = fromSnapshot(await res.json());
        if (codeRef.current === current) {
          let next = snap;
          for (const msg of pendingRef.current) {
            if (msg.seq > snap.seq) next = applyTick(next, msg);
          }
          accumRef.current = next;
          setAccum(next);
        }
      }
    } catch (err) {
      console.warn("stock: snapshot refetch 失敗", err);
    } finally {
      refetchingRef.current = false;
      pendingRef.current = [];
      if (pendingRefetchRef.current || codeRef.current !== current) {
        pendingRefetchRef.current = false;
        void refetch();
      }
    }
  };

  // 主圖切檔:載 snapshot
  useEffect(() => {
    setAccum(null);
    setStkfut(null);
    accumRef.current = null;
    if (code === null) return;
    void refetch();
  }, [code]);

  // WS 連線(單條,頁面生命週期)
  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let backoff = BACKOFF_START_MS;

    const handle = (msg: WsMsg): void => {
      const current = codeRef.current;
      switch (msg.type) {
        case "tick": {
          if (msg.code !== current) return;
          const tick = msg as unknown as StockTickMsg;
          if (refetchingRef.current) {
            pendingRef.current.push(tick);
            return;
          }
          const acc = accumRef.current;
          if (acc === null) return; // snapshot 未就緒
          if (tick.seq !== acc.seq + 1) {
            void refetch(); // 跳號(含回退)→ 全量對齊
            pendingRef.current.push(tick);
            return;
          }
          const next = applyTick(acc, tick);
          accumRef.current = next;
          setAccum(next);
          return;
        }
        case "book": {
          if (msg.code !== current) return;
          const acc = accumRef.current;
          if (acc === null) return;
          const next = {
            ...acc,
            book: { bids: msg.bids as [number, number][], asks: msg.asks as [number, number][] },
          };
          accumRef.current = next;
          setAccum(next);
          return;
        }
        case "watchlist_quote": {
          const q: WatchlistQuote = {
            p: (msg.p as number | null) ?? null,
            chg_pct: (msg.chg_pct as number | null) ?? null,
            vol: (msg.vol as number | null) ?? null,
            ref: (msg.ref as number | null) ?? null,
            upper: (msg.upper as number | null) ?? null,
            lower: (msg.lower as number | null) ?? null,
            no_data: Boolean(msg.no_data),
          };
          setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));
          return;
        }
        case "status": {
          const next = {
            tc4: String(msg.tc4 ?? "up"),
            backfilling: (msg.backfilling as string | null) ?? null,
          };
          setStatus((prev) => {
            // 主圖回補完成(backfilling 從本檔 → null)→ 全量 refetch(靜市無 tick 也更新)
            if (prev.backfilling !== null && next.backfilling === null && prev.backfilling === codeRef.current) {
              void refetch();
            }
            return next;
          });
          return;
        }
        case "stkfut": {
          if (msg.code !== current) return;
          setStkfut({
            prod: String(msg.prod ?? ""),
            p: msg.p as number,
            basis: (msg.basis as number | null) ?? null,
          });
          return;
        }
        case "signal": {
          // 不過濾 code:訊號涵蓋整個自選池,主圖看的是哪一檔與要不要提示無關
          emitSignal(msg as unknown as SignalMsg);
          return;
        }
        case "watchlist_changed": {
          // Discord /watch 改了自選 → 重抓(內容不隨訊息帶,避免兩份來源不一致)
          void queryClient.invalidateQueries({ queryKey: ["stock-watchlist"] });
          return;
        }
        default:
          return;
      }
    };

    const connect = (): void => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${window.location.host}/ws/stock`);
      setWsStatus("connecting");
      ws.onopen = () => {
        backoff = BACKOFF_START_MS;
        setWsStatus("open");
        void refetch(); // 重連後對齊(WS 斷線期間漏訊息)
        emitWsOpen(); // 訊號 feed 的自癒鉤:斷線期間丟的訊號由當日 jsonl 補回
      };
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          handle(JSON.parse(ev.data) as WsMsg);
        } catch (err) {
          console.warn("stock ws: 無法解析訊息", err);
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

  return { accum, watchlist, status, stkfut, wsStatus };
}
