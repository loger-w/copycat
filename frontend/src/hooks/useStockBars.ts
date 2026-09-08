import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { Bar } from "@/lib/candle";
import { dayBarsRefetchInterval, dayBarsStaleTime } from "@/lib/day-bars-rollover";
import { inTradingHours, msUntilTradingOpen, offHoursInterval } from "@/lib/trading-hours";

/** K 線資料(SC-7)。日 K 與分 K 的新鮮度策略不同:
 *  - `D`:**兩道界之間**不過期(已完成日 bar 不會變);query key **不含 days**(D-15)。
 *    界 = 日曆午夜 + slack 與 14:00 定稿界 + slack,與期指 / 加權日 K 同一把尺 —— 症狀與由來見
 *    `lib/day-bars-rollover.ts::msUntilDayRollover`(bug/daily-bars-siblings-rollover;W2 T2 #206 加定稿界,
 *    今日那根 14:01 換定稿)。個股 overlay(CDP / MA)走後端 `/api/stock/overlay` 的
 *    `date < today` + queryKey 帶日期,不受這條影響。
 *  - `1`:交易時段每 60s 重取(D-9)。成本控制在後端 —— 歷史日走永久 memo,
 *    只有當日段會真的打 TC4(change-spec R2-2/R2-3)。盤外回「距 09:01 的 ms」不回 false
 *    (W2 T3 #208):開盤前開著的個股頁到開點那秒自己打第一發(盤中靠個股 WS 重繪順便醒)。
 *
 *  2–10 分 K **共用同一份 `tf=1` 原料**,由前端 `aggregateBars` 聚合;後端 `tf` 值域
 *  仍只有 `D` / `1`,不需要改(app.py:399 的 BAD_TF 白名單)。 */

/** 分 K 由 1/5 兩檔擴為 1–10 連續(SC-6.1)。union 展開而非 template literal 型別 ——
 *  後者在 noUncheckedIndexedAccess 下的推導比較難駕馭,而這裡只有十個值。 */
export type MinuteMode =
  | "m1" | "m2" | "m3" | "m4" | "m5"
  | "m6" | "m7" | "m8" | "m9" | "m10";
export type ChartMode = "intraday" | "day" | MinuteMode;

/** 分 K 一次載滿的天數。原本是「往前」鈕每次 +5 的上限,現在是固定值 ——
 *  user 要求不必再點往前才能看 30 日,改由圖上縮放/平移取用(SC-6.2)。 */
export const MINUTE_DAYS = 30;
const POLL_MS = 60_000;

/** `m7` → 7;非分 K 模式回 1(不聚合)。 */
export function minutesOf(mode: ChartMode): number {
  if (mode === "intraday" || mode === "day") return 1;
  const n = Number(mode.slice(1));
  return Number.isFinite(n) && n >= 1 ? n : 1;
}

/** 空 bars 的三種來源(後端 /api/stock/bars 的 `status` 欄位):
 *  - `ok`:TC4 有回應但窗內無 bar(= 真無資料的最接近表述)
 *  - `timeout`:等滿 deadline 沒等到首頁備妥(慢**或**查無,TC4 協定不可分)
 *  - `disconnected`:TC4 連線中斷(engine 層 ConnectionError) */
export type BarsStatus = "ok" | "timeout" | "disconnected";
export type BarsPayload = { bars: Bar[]; status: BarsStatus };

const STATUSES: readonly string[] = ["ok", "timeout", "disconnected"];

/** payload 正規化**只在這一處**。
 *  - status:欄位缺(舊後端,§3 backward compat)或值不在白名單一律當 `"ok"` = 現況
 *    行為。未知值若放行,`barsPollInterval` 會因 `!== "ok"` 開始輪詢、StockChart 卻落回
 *    「無 K 線資料」,形成零訊號的矛盾態(review R6)。
 *  - bars:同一個理由(payload drift / 版本落差)也可能整個欄位缺。不兜住的話
 *    `data.bars.length` 會丟 TypeError,而專案沒有 ErrorBoundary → 整頁白畫面,
 *    比舊碼的 TanStack error 態更糟(review F1)。 */
async function fetchBars(code: string, tf: string, days: number): Promise<BarsPayload> {
  const qs = tf === "D" ? `tf=D` : `tf=1&days=${days}`;
  const res = await fetch(`/api/stock/bars/${code}?${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { bars?: Bar[]; status?: string };
  const status = body.status;
  return {
    bars: Array.isArray(body.bars) ? body.bars : [],
    status: status !== undefined && STATUSES.includes(status) ? (status as BarsStatus) : "ok",
  };
}

/** 輪詢間隔(SC-4)。空且非 ok = 「還在等 / 斷線」,必須自己走得出來:20s > 後端
 *  15s 負向快取 TTL,所以每輪都真打 TC4 而不是撞快取空轉。其餘情形:分K 交易時段 60s、
 *  分K 盤外回「距 09:01 的 ms」(W2 T3 #208;`offHoursInterval` 秒級量化 + 1 s 下限,不回 false —— TQ 對
 *  false 不排 timer、開盤前開著的頁到 09:01 不自醒)、日K 回 false(由 `lib/day-bars-rollover` 的界政策接手)。
 *  抽成純函式才量得到(SC-4 量法);`now` 讓盤外距離可量,呼叫端與 `trading` 用同一個時刻。
 *  **前置:`trading` 必須 = `inTradingHours(now)`**(唯一 prod caller 同源推導,矛盾態到不了 prod);
 *  測試刻意餵 `trading=true` + 盤外 `now` 只為隔離分支。不在函式內自算 `inTradingHours(now)`:那會讓
 *  純函式吃到日曆快取、測試得再 stub 日曆,違背抽成純函式的初衷(pr-211 F-14)。 */
export function barsPollInterval(
  data: BarsPayload | undefined,
  isDaily: boolean,
  trading: boolean,
  now: Date = new Date(),
): number | false {
  if (data !== undefined && data.bars.length === 0 && data.status !== "ok") return 20_000;
  if (isDaily) return false;
  return trading ? POLL_MS : offHoursInterval(msUntilTradingOpen(now));
}

/** `enabled` 是**外部否決**(D10/R5),不是「再判一次 code/mode」:個股期合約態下
 *  這支 endpoint 查的是**現貨**股號,拿回來的 K 線與畫面上的合約無關 —— 畫得出來、
 *  沒有錯誤,是零訊號的假資料。而模式收斂雖然在同一個 render pass 內完成
 *  (StockChart 的 render 期間調整分支),本 hook 是在那個分支**之前**被呼叫的
 *  (hook 呼叫順序不可調)——「殘留日 K + 切進合約」的第一次求值仍是 day,
 *  外部否決(`enabled` 參數)因此仍是唯一保證,不在這裡擋就已經打出去了。 */
export function useStockBars(
  code: string | null,
  mode: ChartMode,
  days: number,
  externallyEnabled = true,
) {
  const isDaily = mode === "day";
  const enabled = externallyEnabled && code !== null && mode !== "intraday";
  const tf = isDaily ? "D" : "1";
  return useQuery({
    // tf=D 不含 days:忽略該參數卻進 key 會產生多份等價 cache(D-15)
    queryKey: isDaily ? ["stock-bars", code, "D"] : ["stock-bars", code, "1", days],
    queryFn: () => fetchBars(code as string, tf, days),
    enabled,
    retry: 1,
    // 日 K 的新鮮度政策整組在 `lib/day-bars-rollover.ts`(三支日 K hook 同動,改政策只改那裡)
    staleTime: isDaily ? dayBarsStaleTime : 0,
    // 函式形式:TQ 每次 interval 到期**與每次 render** 都會重新求值 → 開盤/收盤的開關、日 K 的
    // 下一道界(午夜 / 14:00)都不依賴外部 re-render(值形式只在 render 當下求值,冷門股沒推播就不會自動開始
    // 輪詢 — review P2-4);回值一變 TQ 就重排計時器,所以日 K 那條回整秒值。
    // data 必須讀 `query.state.data`:閉包裡的 data 恆為訂閱當下的初值(undefined),
    // 空態轉 timeout 後永遠不會開始 20s 重試(review R3)。
    // `barsPollInterval` 先判(SC-4 的 20 s 空態重試優先於日界);日 K 它回 false 才輪到
    // lib 的「失敗 60 s 重試 / 下一道界」政策(個股頁本來就沒有 `active` 閘)。
    // retryEmpty: false —— 本 hook 的空態語意由 status 三態接手:空 + 非 ok 上面 20 s 已判,
    // 空 + ok = 「真無資料」刻意不輪詢(SC-4;與 market / futures 的未三態化空回應不是同一種空)。
    refetchInterval: (query) => {
      const now = new Date();
      const poll = barsPollInterval(query.state.data, isDaily, inTradingHours(now), now);
      if (!isDaily || poll !== false) return poll;
      return dayBarsRefetchInterval(query, { retryEmpty: false });
    },
  });
}
