/** 自選寫入的**跨元件串行佇列**(N117;原本住在 `WatchlistManagerDialog` 內)。
 *
 *  ## 為什麼佇列要在元件之外
 *
 *  自選只有一份、後端 PUT 是**全量取代且無樂觀鎖**(last-write-wins)。寫入者卻有三個:
 *  管理 Dialog、側欄(拖曳 / 移除 / 加入群組)、個股頁的「加入自選」。
 *  各自持一顆 mutation observer 時,兩件事會壞:
 *
 *  1. **per-call callbacks 只對最新一發執行**(TQ v5 契約)—— 連發時第一發的 `onSuccess`
 *     被靜默吞掉(2026-08-11 W-20 復發的根因)。
 *  2. **以 render 閉包算 next = stale 基底** —— 前一發 PUT 在途時,後一發用的還是舊內容,
 *     把前一發的結果原樣還原回去,而畫面上兩步都「成功」了。
 *
 *  Dialog 內部的佇列只解決了「Dialog 自己連發」。跨元件那一半仍在:關窗後佇列殘餘的
 *  sub-second 窗內,側欄拖曳以 render 閉包算 next,兩者可互相覆寫。窗很窄(modal 開著時
 *  側欄不可互動),但代價是**靜默改資料**,而且沒有任何錯誤訊號。
 *
 *  所以佇列上提到 module 層:**同一份資源、同一條 chain、同一個基底**,三個 caller 共用。
 *
 *  ## 動作是 transform,不是值
 *
 *  `commit((base) => next)`:輪到時才以「最新已知內容」(上一發 PUT 的回應)重算。
 *  回 `null` = 這個動作在**套用當下**被拒(撞名 / 保留名),呼叫端顯示 BAD_GROUP ——
 *  N115:撞名判定必須跟基底走,呼叫端 render 閉包上的 eager 檢查只能當即時 UX。
 *  回 `base` 自身(或內容相同的物件)= 無事可做 → 零 PUT 靜默早退,**不是**錯誤。
 *
 *  ## 錯誤文案歸呼叫端
 *
 *  佇列只回報「這一發怎麼了」(`onError(code)` / 成功時 `onError(null)`),文案與擺放位置
 *  由呼叫端自己決定 —— 三個 caller 的錯誤各自長在不同的地方(窗內橫幅 / 側欄一行 /
 *  header 尾),而且呼叫端還有自己的 eager UX 錯誤要跟它共用同一個槽。
 */
import { useCallback, useLayoutEffect, useRef } from "react";

import { useSaveWatchlist, useStockWatchlist } from "@/hooks/useStockWatchlist";
import { isSameWatchlist, type Watchlist } from "@/lib/watchlist-model";

/** 以「最新已知內容」為基底算下一份自選;`null` = 套用當下被拒(撞名 / 保留名)。 */
export type WatchlistTransform = (base: Watchlist) => Watchlist | null;

interface QueueState {
  /** 串行 chain。**尾端恆 fulfilled**(唯一 catch 收斂點)—— 留在 rejected 的話之後所有
   *  `.then` 一律被跳過 = 全站靜默失去自選寫入能力。 */
  chain: Promise<void> | null;
  /** 最新已知的自選內容(上一發 PUT 的回應 / query data)。`null` = 從未載入成功。 */
  base: Watchlist | null;
  /** 在途 + 排隊中的動作數;`0` 才允許用 query data 覆寫基底。 */
  pending: number;
  /** 失敗世代:某發失敗 → +1,其後**已排隊**的動作全部作廢(它們排隊時假設前面會成功,
   *  靜默跳過失敗那步繼續套用會產生使用者未預期的複合狀態)。失敗後的**新**動作是新意圖。 */
  gen: number;
}

function freshQueue(): QueueState {
  return { chain: null, base: null, pending: 0, gen: 0 };
}

let queue = freshQueue();
/** 掛載中的 hook 實例數。0 → 1 時整份重置:沒有任何寫入者在場時,上一輪的殘餘
 *  (半途的 pending / 失敗世代 / 舊基底)沒有繼承的理由,而在測試環境裡繼承它就是
 *  跨檔互污。**重置換的是整個物件**,飛在半空的舊動作繼續改舊物件、互不干擾。 */
let instances = 0;

export interface WatchlistCommitOptions {
  /** 自選尚未載入成功時的基底來源(管理 Dialog 拿得到 prop 上的 `wl`)。 */
  seed?: Watchlist;
  /** 這一發的結果:錯誤碼,或 `null` = 成功(把上一則文案清掉)。 */
  onError?: (code: string | null) => void;
}

export interface WatchlistCommit {
  /** 排入一個動作。`onDone` 在該發 PUT 成功後執行(逐發,不會被後續動作覆蓋)。 */
  commit: (make: WatchlistTransform, onDone?: () => void) => void;
  /** 本實例送出的 PUT 是否在途(建議列 / 按鈕停用用)。 */
  isPending: boolean;
}

export function useWatchlistCommit(opts: WatchlistCommitOptions = {}): WatchlistCommit {
  const save = useSaveWatchlist();
  const { data } = useStockWatchlist();
  const mutateAsync = save.mutateAsync;
  const { seed, onError } = opts;
  /** 回呼走 ref:`commit` 的 identity 不該隨呼叫端每輪換掉的 inline 函式一起換。
   *  在 layout effect 內寫(不是 render 期間)—— render 期間改 ref 是 React 明文的
   *  未定義行為(重播 / 中止的 render 會留下不該有的值)。 */
  const onErrorRef = useRef(onError);
  useLayoutEffect(() => {
    onErrorRef.current = onError;
  });

  // **宣告順序即執行順序**:重置必須排在基底同步之前,否則首次掛載會「先同步基底、
  // 再把整份佇列(含剛設好的基底)重置掉」,而症狀是第一個動作靜默零 PUT。
  useLayoutEffect(() => {
    if (instances === 0) queue = freshQueue();
    instances += 1;
    return () => {
      instances -= 1;
    };
  }, []);

  /** 基底只在「佇列空著」時跟著 query data 走(review C-2 的既有結論):`pending` 歸零
   *  早於 cache 更新引發的 re-render,若在事件路徑同步就會把剛拿到的 PUT 回應倒回舊值。 */
  useLayoutEffect(() => {
    const known = data ?? seed;
    if (known !== undefined && queue.pending === 0) queue.base = known;
  }, [data, seed]);

  const commit = useCallback(
    (make: WatchlistTransform, onDone?: () => void): void => {
      const q = queue; // 重置後飛在半空的動作只改舊物件
      const gen = q.gen;
      q.pending += 1;
      q.chain = (q.chain ?? Promise.resolve())
        .then(async () => {
          if (gen !== q.gen) return; // 排隊期間前面有失敗 → 本動作作廢
          const base = q.base;
          // 自選從未載入成功 → 不以空殼為基底整份 PUT(那會把真實自選靜默清空)
          if (base === null) return;
          const next = make(base);
          if (next === null) {
            // 套用當下才判定的拒絕(撞名 / 保留名,N115):基底不動、零 PUT、文案要出來
            onErrorRef.current?.("BAD_GROUP");
            return;
          }
          // 深度比對不可省(W-9):`assignToGroup` 等恆回新陣列,內容相同也會送出,
          // 而內容相同的 PUT 會讓後端重設整個訂閱池(TC4 全量 UNSUB/SUB),零訊號。
          if (isSameWatchlist(next, base)) return;
          q.base = await mutateAsync(next);
          onErrorRef.current?.(null); // 清除點在成功後,不在送出前 —— 送出前清會洗掉前一發的失敗文案
          onDone?.();
        })
        .catch((e: unknown) => {
          // 唯一收斂點(chain 保證回到 fulfilled)。錯誤碼交給呼叫端落在**自己的** state
          // 而不是讀 `save.error` —— 佇列下一發 mutateAsync 會立刻重設 observer 的 error,
          // 文案一幀未渲染就被洗掉。基底不推進;已排隊的後續動作由世代檢查作廢。
          q.gen += 1;
          onErrorRef.current?.(e instanceof Error ? e.message : "SAVE_FAILED");
        })
        .finally(() => {
          q.pending -= 1;
        });
    },
    [mutateAsync],
  );

  // 刻意**不**擋 unmount 後的回呼:卸載後 setState 是 React no-op,而佇列殘餘的 `onDone`
  // (折疊孤兒清理)在關窗 / 換 tab 後照跑正是 W-20 要的「不漏清」—— 與
  // CapitalConfirmDialog 的「unmount 零 callback」語意刻意不同(真錢下單 vs 冪等清理)。
  // lock 見 `WatchlistSidebar.test.tsx` N116 節。
  return { commit, isPending: save.isPending };
}
