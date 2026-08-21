/** 當日訊號流(design §8.1;SC-9/11)。
 *
 *  兩個來源合成一條清單:
 *  - baseline = `GET /api/stock/signals/today`(hub 的 jsonl,**舊在前**)
 *  - live = WS 推播經訊號 bus 進來的即時訊號(新的在前)
 *
 *  **WS 重連時重抓 baseline**(design Known Risk 2 自癒):斷線期間 WS 丟掉的訊號
 *  沒有任何補發機制,只有 jsonl 留著 —— 不重抓就是那段時間的訊號永久消失,而畫面
 *  上完全看不出來。id 是決定性鍵,補回來的與 live 那份同 id 自動去重。 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { onSignal, onWsOpen } from "@/lib/signal-bus";
import { mergeSignals, type SignalMsg } from "@/lib/signal-model";

/** 全站唯一的 baseline queryKey。**刻意不帶任何維度**:today 端點回的就是當日全部
 *  訊號,所有掛載點看的是同一份 —— 加維度只會讓每個掛載點各抓一份等價資料,
 *  而 ws-open 的 invalidate 也就必須逐一列舉。 */
const TODAY_KEY = ["stock-signals-today"];

/** 跨午夜 / stage2 rollover 後標題要跟上(AR4)。WS 重連的 invalidate 只在斷線時發生,
 *  而長跑分頁可以整晚不斷線 —— 沒有這條週期,標題會停在昨天的日期直到有人重整。 */
const BASELINE_REFETCH_MS = 5 * 60_000;

interface TodayPayload {
  /** 已反轉為「新在前」—— `mergeSignals` 兩份輸入都要求新在前。 */
  signals: SignalMsg[];
  /** 後端 hub 的資料日別 / 牆鐘日;舊後端沒這兩欄 → null(不由前端猜)。 */
  tradeDate: string | null;
  today: string | null;
}

async function fetchToday(): Promise<TodayPayload> {
  const res = await fetch("/api/stock/signals/today");
  if (!res.ok) throw new Error(`HTTP_${res.status}`);
  const body = (await res.json()) as {
    signals?: SignalMsg[];
    trade_date?: string;
    today?: string;
  };
  return {
    signals: [...(body.signals ?? [])].reverse(),
    tradeDate: body.trade_date ?? null,
    today: body.today ?? null,
  };
}

export interface SignalFeed {
  signals: SignalMsg[];
  /** baseline 取數是否已失敗(retry 1 次後才會 true)。
   *
   *  **降級要說得出口**(review round-2 FE-1):達錢 4 沒開時 `/api/stock/signals/today`
   *  回 503 → 這裡沒有 baseline,但 live 訊號照樣進得來。少了這顆旗標,消費端只能把
   *  「服務沒起來」與「今天真的沒訊號」畫成同一句話,而使用者對這兩句的反應完全相反
   *  (去查 vs 繼續等)。 */
  baselineError: boolean;
  /** baseline 是哪一天的訊號(後端 hub 的日別);缺欄 / 未取到 = null。 */
  tradeDate: string | null;
  /** 後端牆鐘日。與 `tradeDate` 成對才有意義 —— 消費端拿兩者比對決定標題文案,
   *  單邊搭配瀏覽器時鐘會在時區偏移 / 跨午夜時給出錯的「今天」。 */
  today: string | null;
}

export function useSignalFeed(): SignalFeed {
  const queryClient = useQueryClient();
  const baselineQuery = useQuery({
    queryKey: TODAY_KEY,
    queryFn: fetchToday,
    retry: 1,
    refetchInterval: BASELINE_REFETCH_MS,
  });
  const [live, setLive] = useState<SignalMsg[]>([]);

  // 外部事件源訂閱(不是從 props/state 推導的值)—— effect 是正解。
  // 新到的那筆當 `live` 參數(第二個)、已累積的當 `baseline`:`mergeSignals` 依 time
  // 降冪重排,參數順序只決定**同秒併列**時誰在上,新到的在上與下方 signals 那次呼叫
  // 「live 贏 baseline」的語意一致。
  useEffect(() => onSignal((sig) => setLive((prev) => mergeSignals(prev, [sig]))), []);
  useEffect(
    () => onWsOpen(() => void queryClient.invalidateQueries({ queryKey: TODAY_KEY })),
    [queryClient],
  );

  // 抓失敗(hub 未就緒 503)= 沒有 baseline,不是壞掉:live 訊號照樣進得來
  const baseline = baselineQuery.data?.signals;
  const signals = useMemo(() => mergeSignals(baseline ?? [], live), [baseline, live]);
  return {
    signals,
    baselineError: baselineQuery.isError,
    tradeDate: baselineQuery.data?.tradeDate ?? null,
    today: baselineQuery.data?.today ?? null,
  };
}
