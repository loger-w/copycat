import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import { fetchWithTimeout } from "@/lib/fetch-timeout";
import type { FutChartMode } from "@/lib/fut-chart-mode";
import type { MarketKey } from "@/lib/timeframe";
import { msUntilNextLocalDate } from "@/lib/trading-calendar";
import { inFuturesAllDayHours } from "@/lib/trading-hours";
import type { MarketBars } from "@/hooks/useMarketBars";

/** 期貨 tab 的 K 線資料源(futures-allday SC-1/2/3;design §4.1)。
 *
 * 與 `useMarketBars` 刻意分成兩支:
 * - 後端 `session=allday`(近全時段分鐘域)只有期指鍵吃得下,大盤 tab 的 `TXF`(day)
 *   與這裡的 `TXF:allday` 是**兩份後端 cache**(D10 記錄的取捨:同 symbol 歷史抓兩遍,
 *   換取大盤頁零改動)。
 * - 輪詢窗是近全時段(`inFuturesAllDayHours`),日盤那把尺會讓夜盤整段不自動更新。
 *
 * **分時與分 K 共用同一份 `tf=1` 原料**(分時圖的幾何在 `lib/allday.ts`,聚合在
 * `lib/candle.ts`)—— 一份原料餵所有分鐘級模式,切模式不重打。
 */

/** 分 K 取數天數。**5 不是 30**:近全時段一天 1140 根,30 日窗會是 34,000 根 ≈ 3 MB
 *  JSON 且冷啟動要 TC4 收割同量級的列(D10 payload 預算)。 */
export const FUTURES_MINUTE_DAYS = 5;

const POLL_MS = 60_000;
const SESSION = "allday";

/** 一趟 bars 請求最多等多久(bug/futures-tab-reactivate-refetch)。
 *
 *  **30 s 不是 10 s**:期指 1K 只有一段 SubHistory(`futures_source.fetch_bars_range`),首頁 deadline
 *  10 s(`BARS_POLL_DEADLINE`)+ 分頁收割 + 與 REALTIME 搶同一把 `api.lock` + 歷史段冷啟動可能多日,
 *  08-28 實測切回 tab 那一趟 14 s 才回 —— 太短會把「慢但會回」誤判成壞;30 s 仍 < 60 s 輪詢,
 *  凍結上界 = timeout + retry 一次 ≈ 61 s。含 body(headers 到了不算回完,見 `fetchWithTimeout`)。
 *  超時的失效樣態(改前)= TQ 把後續 refetch 併進永不回的那一趟,該商品永久凍結、換商品才好。 */
export const BARS_FETCH_TIMEOUT_MS = 30_000;

/** 一趟超過這個時間才回就 `console.warn`:抓 user 真事件用(「那一趟為什麼慢」目前零證據,
 *  uvicorn access log 只記完成的請求且無時間戳)。門檻 = 常態(0–1 s)與 14 s 實測之間留餘裕。
 *  刻意不節流:每一趟慢請求都是一筆證據,60 s 一輪的量級不會洗版。 */
export const BARS_SLOW_WARN_MS = 15_000;

/** 日 K 的有效期 = **同一個本機日曆日**(bug/futures-daily-bars-rollover)。
 *
 *  舊碼 `staleTime: Infinity` + 不輪詢:看盤日常是 preview 整天掛著(CLAUDE.md §1),跨過午夜
 *  那份 cache 永不失效 → 新交易日的 CDP / MA 疊線(`lib/futures-overlay.ts`,基準 = 錨定日前
 *  一交易日)拿的是**昨天早上抓的那份**:昨天的 D bar 停在盤中部分值(或根本還沒有),而
 *  錨定日判準只保證「不畫到未來」,對「停在更早的一天」無感 —— 畫面只是幾條位置不對的線。
 *
 *  **界是日曆午夜,不是 15:00 錨定日翻頁**:後端 `server/bars.py::build_period` 的日 K cache
 *  鍵是 `date.today()`,15:01–24:00 之間再怎麼問都是同一份(那一段留 next-time);午夜一過
 *  後端才有新料。三條路徑同一把尺:
 *  - `refetchInterval`:人一直在 tab 上 → 午夜到了自己打一發(函式形式,每次結果落地後
 *    重算到下一個午夜;不是固定 24 h —— 那會把「掛載時刻」當午夜);
 *  - `staleTime`:切走的 observer 是退訂(沒計時器)、背景分頁 interval 被跳過(TQ 預設
 *    `refetchIntervalInBackground: false`)—— 這兩條都靠「這份是昨天抓的」才能在切回 /
 *    回前景時補上。以 `dataUpdatedAt` 為起點算到它之後的第一個午夜,不是以現在算(否則
 *    每次判定都會把過期點往後推)。
 *  `DAY_ROLLOVER_SLACK_MS`:午夜過後再等一分鐘才問 —— 同一台機器上前後端牆鐘無時差,
 *  這一分鐘擋的是計時器早觸發那類秒級抖動(早一秒問到的還是昨天那份,而下一次是 24 h 後)。 */
export const DAY_ROLLOVER_SLACK_MS = 60_000;

/** `from` 起算,到「下一個日曆日 + slack」的毫秒數。`from` = 0(尚無資料)→ 0:立即過期。 */
export function msUntilDayRollover(from: number): number {
  if (from <= 0) return 0;
  return msUntilNextLocalDate(new Date(from)) + DAY_ROLLOVER_SLACK_MS;
}

/** 支援 `session=allday` 的標的 = 期指三兄弟。取自 `MarketKey` 而不是另寫一份 union:
 *  後端 `MARKET_KEYS` 是同一份值域,兩處各留一份必漂移。 */
export type FuturesBarsKey = Extract<MarketKey, "TXF" | "MXF" | "TMF">;

async function fetchFuturesBars(
  key: FuturesBarsKey,
  tf: "1" | "D",
  signal: AbortSignal | undefined,
): Promise<MarketBars> {
  const qs =
    tf === "1" ? `tf=1&days=${FUTURES_MINUTE_DAYS}&session=${SESSION}` : `tf=${tf}`;
  const url = `/api/market/bars/${key}?${qs}`;
  const started = Date.now();
  const res = await fetchWithTimeout(url, { timeoutMs: BARS_FETCH_TIMEOUT_MS, signal });
  const elapsed = Date.now() - started;
  if (elapsed > BARS_SLOW_WARN_MS) {
    console.warn(`bars: 慢請求 ${url} ${(elapsed / 1000).toFixed(1)} s 才回(status ${res.status})`);
  }
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as MarketBars;
}

/** 空態 / 壞態由**消費端**判(`data.meta.source === "unavailable"` → 圖表區印進行式
 *  文案)—— hook 只負責把後端講的話原樣帶回來,不在這裡把降級翻譯成 error。 */
/** @param active 使用者是否正看著期貨 tab。期貨 tab 的 DOM 由 App 以 `hidden` 保留
 *  (不 unmount),沒有這道 gate 的話輪詢會在背景整晚跑(review LF-2)。
 *
 *  **走 TQ 的 `subscribed`,不關 `enabled`**(bug/futures-tab-reactivate-refetch):
 *  `subscribed: false` = 這個 observer 退訂 —— 不輪詢、不吃 cache 更新(hidden 的圖本來就沒人看);
 *  翻回 `true` 時 TQ 重新 subscribe,`staleTime: 0` 的分 K 走 `shouldFetchOnMount` **立即重抓**,
 *  切回 tab 當下就有新料。舊碼只停 `refetchInterval`:切回時只重設 60 s 計時器、不重抓,
 *  切回當下必亮「落後 N 根」、最多等 60 s(08-28 user 配方:個股頁待久切回微台)。
 *  `enabled: false` 仍不用:它會讓 query 退回 pending 態,圖表閃一次「載入中」;退訂
 *  不會 —— cache 裡的舊圖留著等新料。**前提是 cache 還在**:退訂後 observer 歸零,TQ 預設
 *  `gcTime` 5 分鐘就回收,而 user 配方正是「個股頁待很久」→ 這幾把 query 給 `gcTime: Infinity`
 *  (鍵集合有界:3 商品 × 2 tf;review round 1 兩軸各一條 P1)。分 K 與日 K 同一道 gate
 *  (日 K 同一日曆日內重新 subscribe 不重抓;跨了午夜才重抓,見 `msUntilDayRollover`)。**不用 `useEffect`**(frontend-conventions:
 *  server state 一律 TQ)。副作用(刻意):queryFn 吃了 TQ 的 signal 後,切走 tab 時在飛的那趟
 *  會被 TQ 主動中止(`cancel({revert:true})`),不再讓它跑完落 cache —— 切回時反正立即重抓。
 *
 *  預設 `true`:獨立使用與既有呼叫路徑不因這道 gate 靜默停更(同 FuturesLadder 的
 *  `qtyState` 慣例)。 */
/** @param enabled **是否要這份資料**(與 `active` 不同尺:`active` 只管輪詢節奏)。預設 true。
 *  個股頁的台指期疊線(feat/txf-intraday-overlay)在鈕關著時傳 false —— 那是「沒人要看」,
 *  不是「先抓著等人看」:`enabled: false` 才擋得住掛載即抓與 `refetchOnWindowFocus`,只停
 *  `refetchInterval` 擋不住。期貨 tab 自己不傳(理由見上:切回不閃 pending)。 */
export function useFuturesBars(
  key: FuturesBarsKey,
  mode: FutChartMode,
  active = true,
  enabled = true,
) {
  const isMinute = mode !== "day";
  const tf: "1" | "D" = isMinute ? "1" : "D";
  return useQuery({
    // 日 K 不含 days / session:忽略的參數進 key 會產生多份等價 cache(D-15)
    queryKey: isMinute
      ? ["futures-bars", key, "1", FUTURES_MINUTE_DAYS, SESSION]
      : ["futures-bars", key, "D"],
    // TQ 的 signal 只在 observer 全部退訂 / cancel 時 abort;timeout 在 fetchFuturesBars 內另接
    queryFn: ({ signal }) => fetchFuturesBars(key, tf, signal),
    enabled,
    subscribed: active,
    // 退訂期間 cache 不能被 gc(理由見 `active` doc);鍵集合有界,Infinity 不會長
    gcTime: Infinity,
    retry: 1,
    // 日 K:以「上次落地時刻」算到它之後的第一個午夜(理由見 `msUntilDayRollover`)
    staleTime: isMinute ? 0 : (q) => msUntilDayRollover(q.state.dataUpdatedAt),
    // 函式形式:TQ 每次結果落地都重新求值 → 日盤收 / 夜盤開的開關、日 K 的下一個午夜
    // 都不依賴外部 re-render。`active` 這一維不在這裡:退訂的 observer 根本沒有計時器
    //(`subscribed` 是唯一的閘)。
    refetchInterval: () =>
      isMinute
        ? inFuturesAllDayHours()
          ? POLL_MS
          : false
        : msUntilDayRollover(Date.now()),
  });
}
