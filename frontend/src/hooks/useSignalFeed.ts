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
import { isMarketKind, mergeSignals, type SignalMsg } from "@/lib/signal-model";

/** queryKey 的**前綴**。實際的 key 帶模式(`[...TODAY_KEY, mode]`)—— exclude 與
 *  include 兩個掛載點的 baseline 內容本來就不同(後端過濾),共用固定 key 會讓先掛載
 *  的那邊把 cache 灌給另一邊(第二次連 fetch 都不發)。invalidate 用這個前綴,兩族一起自癒。 */
const TODAY_KEY = ["stock-signals-today"];

/** 分族 cap:market 族與自選族各自這個上限(design §9.3)。 */
const FAMILY_CAP = 200;

export type MarketMode = "include" | "exclude";

/** 回傳已反轉為「新在前」的 baseline —— `mergeSignals` 兩份輸入都要求新在前。 */
async function fetchToday(mode: MarketMode): Promise<SignalMsg[]> {
  // exclude 由後端濾(R2-7):jsonl 是全市場 + 自選同檔,前端濾等於把幾百則 market
  // 事件先傳過來再丟掉。
  const url =
    mode === "exclude" ? "/api/stock/signals/today?market=exclude" : "/api/stock/signals/today";
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP_${res.status}`);
  const body = (await res.json()) as { signals?: SignalMsg[] };
  return [...(body.signals ?? [])].reverse();
}

/** include 模式的合併:**兩族各自 cap 再併排**。
 *
 *  漲停潮日一分鐘可湧進上百則 market 事件,單一 cap 200 會讓自選訊號整批被擠出清單
 *  ——(而畫面上看起來就只是「今天訊號很多」)。分族後 chip 切「自選」仍見得到自選那幾則。 */
function mergeByFamily(baseline: SignalMsg[], live: SignalMsg[]): SignalMsg[] {
  const pick = (list: SignalMsg[], market: boolean) =>
    list.filter((s) => isMarketKind(s.kind) === market);
  const marketSide = mergeSignals(pick(baseline, true), pick(live, true), FAMILY_CAP);
  const ownSide = mergeSignals(pick(baseline, false), pick(live, false), FAMILY_CAP);
  // 再過一次 mergeSignals 只為了共用那份 time 降冪排序(兩族已各自去重、各自截斷)
  return mergeSignals([...marketSide, ...ownSide], [], FAMILY_CAP * 2);
}

export function useSignalFeed(opts?: { market?: MarketMode }): { signals: SignalMsg[] } {
  const mode: MarketMode = opts?.market ?? "exclude";
  const queryClient = useQueryClient();
  const today = useQuery({
    queryKey: [...TODAY_KEY, mode],
    queryFn: () => fetchToday(mode),
    retry: 1,
  });
  const [live, setLive] = useState<SignalMsg[]>([]);

  // 外部事件源訂閱(不是從 props/state 推導的值)—— effect 是正解。
  // 新到的那筆當 `live` 參數(第二個)、已累積的當 `baseline`:`mergeSignals` 依 time
  // 降冪重排,參數順序只決定**同秒併列**時誰在上,新到的在上與下方 signals 那次呼叫
  // 「live 贏 baseline」的語意一致。
  //
  // **過濾/分族發生在 cap 之前**(design §9.3):`live` 這顆累積器自己就有 cap,不在
  // 進來的當下分流,自選訊號在 market 事件洪峰時就已經被截掉了,下游再怎麼濾也救不回來。
  useEffect(
    () =>
      onSignal((sig) => {
        if (mode === "exclude" && isMarketKind(sig.kind)) return;
        setLive((prev) =>
          mode === "include" ? mergeByFamily(prev, [sig]) : mergeSignals(prev, [sig]),
        );
      }),
    [mode],
  );
  useEffect(
    () => onWsOpen(() => void queryClient.invalidateQueries({ queryKey: TODAY_KEY })),
    [queryClient],
  );

  // 抓失敗(hub 未就緒 503)= 沒有 baseline,不是壞掉:live 訊號照樣進得來
  const baseline = today.data;
  const signals = useMemo(
    () =>
      mode === "include" ? mergeByFamily(baseline ?? [], live) : mergeSignals(baseline ?? [], live),
    [baseline, live, mode],
  );
  return { signals };
}
