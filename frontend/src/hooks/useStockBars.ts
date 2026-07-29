import { useQuery } from "@tanstack/react-query";

import type { Bar } from "@/lib/candle";

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

/** 台北交易時段(本機時區 = 台北,部署綁本機)。
 *
 * 週末必須擋掉:少了星期判定,週六日整個上午都會每 60s 打一次當日段,而當日段恆空
 * → `today_put` don't-cache-empty → 每次都真的走 TC4 SubHistory(首頁 poll deadline
 * ≈ 30s、約 30 個 REQ,搶同一個 source 的 `api.lock`)。也違反 SC-10 的
 * 「非交易時段不應出現週期性請求」(review P1-3)。
 *
 * 起點取 09:01 而非 08:45:當日第一根 1K 就是 09:01,更早輪詢必定空手而回。
 * (國定假日仍會空跑 —— 需要交易日曆才擋得掉,列入 docs/next-time.md。) */
export function inTradingHours(now: Date = new Date()): boolean {
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 9 * 60 + 1 && mins <= 13 * 60 + 35;
}

async function fetchBars(code: string, tf: string, days: number): Promise<Bar[]> {
  const qs = tf === "D" ? `tf=D` : `tf=1&days=${days}`;
  const res = await fetch(`/api/stock/bars/${code}?${qs}`);
  if (!res.ok) {
    let code_ = `HTTP_${res.status}`;
    try {
      const body = (await res.json()) as { detail?: { error?: string } };
      code_ = body.detail?.error ?? code_;
    } catch {
      /* 非 JSON body:保留 HTTP_ 前綴碼 */
    }
    throw new Error(code_);
  }
  return ((await res.json()) as { bars: Bar[] }).bars;
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
