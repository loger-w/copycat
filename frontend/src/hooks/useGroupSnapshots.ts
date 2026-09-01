import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import { minutesFromRecord, type MinuteAgg, type StockMeta, type VpCell } from "@/lib/stock-accum";
import { inTradingHours, msUntilTradingOpen } from "@/lib/trading-hours";

/** 群組檢視的成員狀態(group-grid SC-4)。
 *
 *  **單一 batch 端點,不是 per-code query**:`/api/stock/state/{code}` 會 `set_main`,
 *  群組檢視每分鐘對整組(上限 150 檔)各要一次 = 每分鐘把主圖搶走上百次,主圖分時線就此凍結
 *  而畫面上只表現為「圖不動了」,沒有任何錯誤訊號(design R1)。
 *
 *  payload 沒有 `ticks`(數千筆,整組上限檔數一起送等於把 batch 端點變成頻寬炸彈),但帶
 *  它的**聚合**:`vwap` / `high` / `low` / `vp` —— 卡片圖要與單檔頁「完全同款」
 *  (VWAP 白線 / 日高低圈 / VP 條 + POC),而由 minutes 在前端近似會畫出與單檔頁
 *  對不上的圖,兩份數字都看起來對(change-spec AD-1)。
 *
 *  **結構相容 `GroupLikeSnapshot`**(`lib/stock-accum.ts`)—— `accumFromGroupSnapshot`
 *  吃的是那個結構型別,lib 不反向 import 本檔。 */
export interface GroupSnapshot {
  minutes: Map<number, MinuteAgg>;
  meta: StockMeta | null;
  /** 未知 / 未訂閱 / TC4 查無此檔 —— 卡片只要答「這格畫不畫得出東西」,三者同義 */
  noData: boolean;
  /** 今日回補尚未落地:卡片顯示「回補中…」而不是呈現半截圖 */
  backfilling: boolean;
  /** 後端逐 tick 維護的當日 VWAP / 高 / 低(毫元);舊後端缺鍵 → `null` = 不可得 */
  vwap: number | null;
  high: number | null;
  low: number | null;
  /** 價位別成交量(key = 已 snap 的毫元檔位)。**必填**:缺鍵降級成空 Map 而不是
   *  undefined —— 消費端對兩者的分支不同,而漏帶不會有任何錯誤訊號。 */
  vp: Map<number, VpCell>;
}

const POLL_MS = 60_000;

interface RawState {
  minutes?: Record<string, MinuteAgg>;
  meta?: StockMeta | null;
  no_data?: boolean;
  backfilling?: boolean;
  /** 以下四鍵為後端 light_snapshot 的加鍵;**選填** —— 舊後端不送(§3 additive) */
  vwap?: number | null;
  high?: number | null;
  low?: number | null;
  /** 緊湊陣列形 `{ "<毫元檔位>": [總張, 外, 內] }`(JSON 物件鍵只能是字串) */
  vp?: Record<string, [number, number, number]>;
}

/** 後端 vp(字串鍵 + 緊湊陣列)→ 前端 Map。
 *
 *  **key 轉 number 不可省**:幾何層拿毫元價位去 `vp.get(priceMilli)`,字串鍵的 Map
 *  對它永遠 miss —— VP 條整排消失,而沒有任何型別或測試會抗議(`Map.get` 的鍵型別
 *  在 `Map<number, …>` 宣告下由 TS 擋,但這份 Map 是從 JSON 現建的)。
 *
 *  緊湊陣列而不是 `{t,o,i}` 物件是 wire 形的選擇(上限 150 檔 × 數百檔位 × 三個鍵名);
 *  展開成具名欄位就在這裡一次做完,消費端看到的與 `foldVp` 的產物同形。 */
function vpFromRecord(
  rec: Record<string, [number, number, number]> | undefined | null,
): Map<number, VpCell> {
  const vp = new Map<number, VpCell>();
  for (const [price, [t, o, i]] of Object.entries(rec ?? {})) {
    vp.set(Number(price), { t, o, i });
  }
  return vp;
}

async function fetchGroupState(csv: string): Promise<Record<string, GroupSnapshot>> {
  const res = await fetch(`/api/stock/group-state?codes=${csv}`);
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { states?: Record<string, RawState> };
  const out: Record<string, GroupSnapshot> = {};
  for (const [code, raw] of Object.entries(body.states ?? {})) {
    out[code] = {
      // 與主圖 snapshot 共用 `minutesFromRecord`:各寫一份的漂移樣態是其中一邊的
      // h/l 留在 undefined,而幾何的極值等值反查對它是 false → 標記靜默消失
      minutes: minutesFromRecord(raw.minutes),
      meta: raw.meta ?? null,
      noData: raw.no_data ?? false,
      backfilling: raw.backfilling ?? false,
      // 缺鍵(舊後端)一律降級成「不可得」而不是近似:拿分鐘資料折一份前端版 VWAP /
      // VP 出來,畫面會與單檔頁的同一檔對不上,而兩個數字都看起來對(§3)
      vwap: raw.vwap ?? null,
      high: raw.high ?? null,
      low: raw.low ?? null,
      vp: vpFromRecord(raw.vp),
    };
  }
  return out;
}

/** 輪詢窗(design R7)。抽成純函式才量得到(沿 `barsPollInterval` 慣例)。
 *  盤外不輪詢,但**不回 `false`**(next-time L71):TQ 對 false 不排 timer、之後再也
 *  不會重新求值 —— 08:59 就開著的群組檢視要等別的事件碰這條 query 才開始輪詢。
 *  改回「距下個交易窗開點的 ms」:窗開瞬間醒來打第一發,之後每次落地重新求值回 60s。
 *  整組 batch(上限 150 檔)不是免費的這一點不變 —— 盤外整段仍零請求(timer 只在開點醒一次)。 */
export function groupPollInterval(now: Date = new Date()): number {
  if (inTradingHours(now)) return POLL_MS;
  // 秒級量化(day-bars-rollover 鐵律 (c),全 repo 函式形 refetchInterval 同款):毫秒精度
  // 會讓每次 render 求出不同值 → TQ 白做一組 clearInterval/setInterval(盤外仍有 orders
  // 10s 輪詢驅動 render)。1_000 下限 = 開點前最後一秒的重排護欄(09:00:59.x 求出 <1s
  // 的值,不設下限會排出 0ms 級 timer 連環重排)。
  return Math.max(Math.ceil(msUntilTradingOpen(now) / 1000) * 1000, 1_000);
}

/** 群組成員狀態 batch。`enabled` 是檢視開關,`codes` 空(空群組 / 零群組)一律不請求
 *  —— 打了只會拿回 `{"states":{}}`,沒有任何卡片可畫卻每 60s 燒一次來回(R17)。 */
export function useGroupSnapshots(codes: string[], enabled: boolean) {
  // query key 用逗號串而不是陣列:陣列每次 render 都是新 identity,TQ 的結構化比對
  // 雖然吃得下,但 URL 本來就是這個字串,兩處各拼一次反而多一個會漂的地方
  const csv = codes.join(",");
  return useQuery({
    queryKey: ["stock-group-state", csv],
    queryFn: () => fetchGroupState(csv),
    enabled: enabled && codes.length > 0,
    // 不重試:60s 的下一輪就是重試(同 `useServerBuild` 慣例)。retry 在這裡是純損失 ——
    // 退避期間卡片停在載入態,而 batch 是整批一命,一檔的暫時性失敗與整組失敗同表現;
    // 使用者看到的是「圖遲遲不出來」而不是「無資料」,後者至少是誠實的終態。
    retry: false,
    staleTime: 55_000,
    // 函式形式:TQ 每次 interval 到期都會重新求值 → 開盤 / 收盤的開關不依賴外部
    // re-render。這個性質**只在回數字時成立**,所以盤外回距開點 ms 而不是 false
    //(見 `groupPollInterval` docstring;next-time L71)。
    refetchInterval: () => groupPollInterval(),
  });
}
