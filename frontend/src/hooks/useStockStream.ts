/** 個股 WS 流 + snapshot 對齊(design v4 §4;WS push 不套 TQ,同 useTxoSnapshot 慣例)。

seq gap 復原:跳號判定 `next != last+1`(含回退)→ refetch 全量 snapshot;
refetch 期間交錯的 tick 進 pending buffer,snapshot(seq=S)套用後丟 seq ≤ S、
依序 append seq > S。meta 基底走 snapshot(engine 不發 meta WS 型別,book 每則自足);
**當日高低由 tick 的 `h`/`l` 增量更新** —— 盤中不重抓 snapshot,掛 meta 上會停在舊值。 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { emitSignal, emitWsOpen } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";
import { applyTick, fromSnapshot, type StockAccum, type StockBook, type StockTickMsg } from "@/lib/stock-accum";
import { instrumentKeyOf, type StkfutSelection } from "@/lib/stkfut";

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

/** snapshot refetch 失敗的重試節奏(F-3)。與 WS 重連的 backoff 分開:WS 斷了整頁都停,
 *  refetch 失敗只是**這一個標的**的一次取數失敗,cap 短一點才不會讓自癒等半分鐘。
 *  刻意**不設次數上限** —— TC4 / 後端一時不可用是常態,自癒比放棄有用;避免無限打的
 *  節流靠排程前的三道檢查(標的未變 + WS 仍 open + 元件未 unmount)。 */
const REFETCH_RETRY_START_MS = 1_000;
const REFETCH_RETRY_CAP_MS = 8_000;

/** refetch 交錯期間暫存的簿(F-2);帶 instrumentKey 標記,切檔撞上 in-flight 時丟棄。 */
interface PendingBook {
  key: string;
  book: StockBook;
}

interface WsMsg {
  type: string;
  code?: string;
  [key: string]: unknown;
}

/** 主圖 snapshot 的 REST URL —— **五個 refetch 觸發共用的唯一產生點**(R2-7)。
 *
 *  路徑段恆為股號、合約走 query string:instrument key(`F:CDF:202609`)放進路徑會被
 *  後端 `_valid_code` 400,而且 D7 白名單需要股號才驗得了「這個合約屬於這檔股票」。
 *  任何一條 refetch 路徑漏帶 `?contract=` 都會靜默把畫面拉回現貨資料。 */
function stateUrl(code: string, contract: { prod: string; ym: string } | null): string {
  return contract === null
    ? `/api/stock/state/${code}`
    : `/api/stock/state/${code}?contract=${contract.prod}:${contract.ym}`;
}

export function useStockStream(
  code: string | null,
  contract: StkfutSelection | null = null,
): StockStreamState {
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
  // refetch 進行中收到的**最新一份**簿(F-2),套完 snapshot 之後蓋回去。
  //
  // 「推播比 snapshot 新」是**近似恆定不是恆定**(review A-3):snapshot 凍結在後端
  // 處理該 request 的當下,不是前端送出的當下 —— 誤差 = request 的單程延遲,在那個
  // 窗內產生的推播理論上可能比 snapshot 舊。本機 localhost 下這個窗是次毫秒級,而
  // 回捲窗(鎖板 / 盤後推播稀疏時)可達數十秒,兩害相權取這一邊。真正的定序要靠
  // book 自己的 seq(後端目前不發,不在本輪 scope)。
  //
  // 帶 instrumentKey 標記:切檔撞上 in-flight 時 key 不符即丟,不把 A 的簿蓋到 B 上。
  const pendingBookRef = useRef<PendingBook | null>(null);

  /** 取出並清掉暫存的簿。**要經過一層函式**:`refetch` 一開頭就寫 `= null`,而 TS 的
   *  屬性窄化不會被 await / 函式呼叫重置(寫進值的那條路在 WS callback 裡,TS 看不到)
   *  → 直接讀會被判成 `never`,`.key` 編不過。順手清掉也讓「只用一次」變成結構保證。 */
  const takePendingBook = (): PendingBook | null => {
    const pending = pendingBookRef.current;
    pendingBookRef.current = null;
    return pending;
  };
  // 上一則 status 的**真值**(F-1)。WS handler 是 deps `[]` 的閉包讀不到最新 state,
  // 而把比較塞進 `setStatus` 的 updater 會讓副作用跟著 StrictMode 的 double-invoke 重跑。
  const statusRef = useRef<{ tc4: string; backfilling: string | null }>({
    tc4: "up",
    backfilling: null,
  });
  const codeRef = useRef(code);
  codeRef.current = code;
  const contractRef = useRef(contract);
  contractRef.current = contract;
  // 主圖標的的**識別**是 instrument key,不是股號:同一檔股票的現貨與各月合約是
  // 不同標的,而 WS 推播的 `code` 欄、engine 的訂閱槽位鍵用的都是它(R9)。
  // ref 化的理由同 codeRef —— WS callback 只建立一次(effect deps `[]`),閉包裡讀
  // 的必須是「當下」的值而不是掛載當時那個。
  const instrumentKey = instrumentKeyOf(code, contract);
  const instrumentKeyRef = useRef(instrumentKey);
  instrumentKeyRef.current = instrumentKey;

  // 重試排程的三道前置(F-3)。ref 而非 state:排程與取消都發生在 WS callback / async
  // finally 裡,那些地方讀不到 render 當下的 state。
  const mountedRef = useRef(true);
  const wsOpenRef = useRef(false);
  const retryTimerRef = useRef<number | undefined>(undefined);
  const retryDelayRef = useRef(REFETCH_RETRY_START_MS);

  /** 取消還沒打出去的重試並把 backoff 歸零(切標的 / 成功 / unmount)。
   *
   *  兩半都要:
   *  - 取消 timer:舊 timer 到期時 `refetch()` 讀的是**當下**的 ref → 對新標的多打
   *    一份全量 snapshot。(只在新標的自己的 fetch 還 in-flight 時才走得到 ——
   *    否則 `scheduleRetry` 自己開頭的 `clearTimeout` 就先清掉了。)
   *  - 歸零 backoff:漏掉這半的失效樣態是**少一發不是多一發**(review B-8,實測
   *    mutant 是 4 vs 5)—— 新標的的第一段重試沿用上一檔退避後的間隔(2s / 4s / …),
   *    畫面上是「換一檔之後要多等好幾秒才自癒」,而且愈換愈久。 */
  const cancelRetry = (): void => {
    window.clearTimeout(retryTimerRef.current);
    retryTimerRef.current = undefined;
    retryDelayRef.current = REFETCH_RETRY_START_MS;
  };

  const scheduleRetry = (key: string): void => {
    // 三道檢查都是「重試已經沒有意義」:元件沒了 / 標的換了(新標的自己會抓)/
    // WS 斷了(重連的 onopen 本來就會發一次全量對齊,這裡再排只是重複)。
    //
    // 覆蓋度誠實記帳(review B-1):只有 `wsOpen` 那道**單獨拿掉會紅**。另兩道在現行
    // 呼叫點下是防禦、不是可獨立覆蓋的邏輯:
    //  - `mounted`:unmount 的 cleanup(:381)同時清了 `wsOpenRef`,所以單獨拿掉它
    //    測試照樣綠(實測 31/31 passed);兩道一起拿掉才紅。cleanup 的清旗標順序哪天
    //    變了,這道就是唯一剩下的防線,故保留。
    //  - `key`:唯一呼叫點是 `refetch` 的 finally,而那條路已經以
    //    `instrumentKeyRef.current !== current` 分岔去補發,走到這裡時兩者恆相等 ——
    //    可證的死碼,無法覆蓋。留著是為了「之後多一個呼叫點」時不必重新想這件事。
    if (!mountedRef.current) return;
    if (instrumentKeyRef.current !== key) return;
    if (!wsOpenRef.current) return;
    const delay = retryDelayRef.current;
    retryDelayRef.current = Math.min(delay * 2, REFETCH_RETRY_CAP_MS);
    window.clearTimeout(retryTimerRef.current);
    retryTimerRef.current = window.setTimeout(() => {
      retryTimerRef.current = undefined;
      void refetch();
    }, delay);
  };

  const refetch = async (): Promise<void> => {
    const current = instrumentKeyRef.current;
    const currentCode = codeRef.current;
    if (current === null || currentCode === null) return;
    if (refetchingRef.current) {
      // CR1:in-flight 中的需求「合併不丟棄」— finally 補發,切檔/回補完成不被吞
      pendingRefetchRef.current = true;
      return;
    }
    refetchingRef.current = true;
    pendingRef.current = [];
    pendingBookRef.current = null;
    // 非 2xx 與 throw 走同一條復原路徑(F-3);`finally` 讀得到才能與「切檔補發」分岔
    let failed = false;
    try {
      const res = await fetch(stateUrl(currentCode, contractRef.current));
      if (res.ok) {
        cancelRetry(); // 成功即歸零 backoff,並丟掉還沒打出去的重試
        const snap = fromSnapshot(await res.json());
        if (instrumentKeyRef.current === current) {
          let next = snap;
          for (const msg of pendingRef.current) {
            if (msg.seq > snap.seq) next = applyTick(next, msg);
          }
          // 交錯的簿蓋回 snapshot 的凍結簿(F-2);key 不符 = 已切檔 → 丟棄。
          //
          // key 比對看似多餘(切檔已在 :223 清過 pending),但守的正是「那行哪天被拿掉 /
          // 新增一條沒清 pending 的切檔路徑」的情況 —— 窄,但後果是把 A 的五檔畫到 B
          // 的圖上,而且零錯誤訊號。留著(review B-4)。
          const pendingBook = takePendingBook();
          if (pendingBook !== null && pendingBook.key === current) {
            next = { ...next, book: pendingBook.book };
          }
          accumRef.current = next;
          setAccum(next);
        }
      } else {
        // 502/503(TC4 斷線 / 後端還沒起)從正常操作可達 —— 不排重試的話 accum 留 null,
        // 而 accum===null 時 tick 早退 → seq-gap 自癒也是死路,畫面釘在「載入中…」。
        console.warn("stock: snapshot refetch 非 2xx", res.status);
        failed = true;
      }
    } catch (err) {
      console.warn("stock: snapshot refetch 失敗", err);
      failed = true;
    } finally {
      refetchingRef.current = false;
      pendingRef.current = [];
      pendingBookRef.current = null;
      if (pendingRefetchRef.current || instrumentKeyRef.current !== current) {
        pendingRefetchRef.current = false;
        void refetch();
      } else if (failed) {
        scheduleRetry(current);
      }
    }
  };

  // 主圖切標的(換股**或**換合約):載 snapshot。deps 是 instrumentKey 而非 code ——
  // 同股換月時 code 不變,用 code 當 deps 會讓畫面停在舊合約的資料上。
  useEffect(() => {
    setAccum(null);
    setStkfut(null);
    accumRef.current = null;
    pendingBookRef.current = null; // 舊標的的簿不可跨檔存活(F-2)
    cancelRetry(); // 舊標的的重試不可跨檔存活(F-3)
    if (instrumentKey === null) return;
    void refetch();
  }, [instrumentKey]);

  // WS 連線(單條,頁面生命週期)
  useEffect(() => {
    let alive = true;
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let backoff = BACKOFF_START_MS;
    mountedRef.current = true; // StrictMode 的 mount→cleanup→mount 會把它翻回來

    const handle = (msg: WsMsg): void => {
      // 主圖相關訊息(tick / book / stkfut / backfilling)的比對鍵一律是 instrument key:
      // 期貨態下 `2330` 的推播仍在跑(自選池),用股號比對會把現貨 tick 混進合約圖。
      const current = instrumentKeyRef.current;
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
          const book: StockBook = {
            bids: msg.bids as [number, number][],
            asks: msg.asks as [number, number][],
          };
          // refetch 進行中:snapshot 是**較舊**的凍結簿,回來時會整份覆蓋 accum ——
          // 這裡先留一份最新的,套完 snapshot 之後蓋回去(F-2)。
          if (refetchingRef.current && current !== null) {
            pendingBookRef.current = { key: current, book };
          }
          const acc = accumRef.current;
          if (acc === null) return;
          const next = { ...acc, book };
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
          // 主圖也要收這一則(code review A2)。engine 的 `_handle_no_data` 對**任何**
          // code 都發 `watchlist_quote`(包含合約鍵),而側欄只認自選碼 —— 沒有這段的話
          // 「合約訂上了但 TC4 零推播」在畫面上就是一張永遠空著的圖:snapshot 是在
          // set_main 當下取的(那時 TC4 還沒回答),之後再也沒有東西會把 noData 帶進來。
          if (msg.code === current && q.no_data) {
            const acc = accumRef.current;
            if (acc !== null && !acc.noData) {
              const next = { ...acc, noData: true };
              accumRef.current = next;
              setAccum(next);
            }
          }
          return;
        }
        case "status": {
          const next = {
            tc4: String(msg.tc4 ?? "up"),
            backfilling: (msg.backfilling as string | null) ?? null,
          };
          // 比較與 refetch 都在 handler 本體做,**不可搬回 `setStatus` 的 updater 內**
          // (F-1):updater 的契約是純函式,而全站包在 StrictMode 下 dev 會 double-invoke
          // → 第一次進單飛、第二次撞 in-flight 設 pendingRefetchRef,finally 的「合併不
          // 丟棄」再補發一次真 fetch,每次回補完成都串行多打一份 MB 級 snapshot。
          // 前值改由 ref 持有(handler 是 effect deps `[]` 的閉包,讀不到最新的 state)。
          const prev = statusRef.current;
          statusRef.current = next;
          // 主圖回補完成(backfilling 從本檔 → null)→ 全量 refetch(靜市無 tick 也更新)
          if (prev.backfilling !== null && next.backfilling === null && prev.backfilling === current) {
            void refetch();
          }
          setStatus(next);
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
        wsOpenRef.current = true;
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
        // `alive` 早退**必須在寫旗標之前**:`wsOpenRef` 是跨 socket 世代共用的單一
        // 旗標,而 StrictMode(dev)的 mount→cleanup→mount 會讓舊 socket 的 close
        // 晚於新 socket 的 `onopen` 到達 —— 寫在前面的話旗標被清成 false 且**再也
        // 回不去**(新 socket 的 onopen 已經發生過了),scheduleRetry 的第三道檢查
        // 永遠早退 = F-3 自癒整條失效。unmount 語意不受影響:cleanup 自己會清旗標。
        if (!alive) return;
        wsOpenRef.current = false;
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
      mountedRef.current = false;
      wsOpenRef.current = false;
      cancelRetry(); // in-flight 的 refetch 事後失敗時才不會排到已卸載的元件上
      window.clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return { accum, watchlist, status, stkfut, wsStatus };
}
