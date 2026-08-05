import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { Bar } from "@/lib/candle";
import { inTradingHours } from "@/lib/trading-hours";

/** K 線資料(SC-7)。日 K 與分 K 的新鮮度策略不同:
 *  - `D`:當日內不過期(已完成日 bar 不會變);query key **不含 days**(D-15)。
 *  - `1`:交易時段每 60s 重取(D-9)。成本控制在後端 —— 歷史日走永久 memo,
 *    只有當日段會真的打 TC4(change-spec R2-2/R2-3)。
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

/** status 正規化**只在這一處**:欄位缺(舊後端,§3 backward compat)或值不在白名單
 *  一律當 `"ok"` = 現況行為。未知值若放行,`barsPollInterval` 會因 `!== "ok"` 開始
 *  輪詢、StockChart 卻落回「無 K 線資料」,形成零訊號的矛盾態(review R6)。 */
async function fetchBars(code: string, tf: string, days: number): Promise<BarsPayload> {
  const qs = tf === "D" ? `tf=D` : `tf=1&days=${days}`;
  const res = await fetch(`/api/stock/bars/${code}?${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { bars: Bar[]; status?: string };
  const status = body.status;
  return {
    bars: body.bars,
    status: status !== undefined && STATUSES.includes(status) ? (status as BarsStatus) : "ok",
  };
}

export function useStockBars(code: string | null, mode: ChartMode, days: number) {
  const isDaily = mode === "day";
  const enabled = code !== null && mode !== "intraday";
  const tf = isDaily ? "D" : "1";
  return useQuery({
    // tf=D 不含 days:忽略該參數卻進 key 會產生多份等價 cache(D-15)
    queryKey: isDaily ? ["stock-bars", code, "D"] : ["stock-bars", code, "1", days],
    queryFn: () => fetchBars(code as string, tf, days),
    enabled,
    retry: 1,
    staleTime: isDaily ? Infinity : 0,
    // 函式形式:TQ 每次 interval 到期都會重新求值 → 開盤/收盤的開關不依賴外部 re-render
    // (值形式只在 render 當下求值,冷門股沒推播就不會自動開始輪詢 — review P2-4)
    refetchInterval: () => (!isDaily && inTradingHours() ? POLL_MS : false),
  });
}
