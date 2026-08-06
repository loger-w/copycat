import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import { minutesFromRecord, type MinuteAgg, type StockMeta } from "@/lib/stock-accum";
import { inTradingHours } from "@/lib/trading-hours";

/** 群組檢視的成員狀態(group-grid SC-4)。
 *
 *  **單一 batch 端點,不是 per-code query**:`/api/stock/state/{code}` 會 `set_main`,
 *  群組檢視每分鐘對最多 30 檔各要一次 = 每分鐘把主圖搶走 30 次,主圖分時線就此凍結
 *  而畫面上只表現為「圖不動了」,沒有任何錯誤訊號(design R1)。
 *
 *  payload 只有 minutes / meta 兩份資料(`ticks` 是數千筆,30 檔一起送等於把 batch
 *  端點變成頻寬炸彈)+ 兩個旗標。 */
export interface GroupSnapshot {
  minutes: Map<number, MinuteAgg>;
  meta: StockMeta | null;
  /** 未知 / 未訂閱 / TC4 查無此檔 —— 卡片只要答「這格畫不畫得出東西」,三者同義 */
  noData: boolean;
  /** 今日回補尚未落地:卡片顯示「回補中…」而不是呈現半截圖 */
  backfilling: boolean;
}

const POLL_MS = 60_000;

interface RawState {
  minutes?: Record<string, MinuteAgg>;
  meta?: StockMeta | null;
  no_data?: boolean;
  backfilling?: boolean;
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
    };
  }
  return out;
}

/** 輪詢窗(design R7)。抽成純函式才量得到(沿 `barsPollInterval` 慣例)。
 *  盤外不輪詢:群組成員的分鐘序列收盤後就不會再變,而 30 檔的 batch 不是免費的。 */
export function groupPollInterval(trading: boolean): number | false {
  return trading ? POLL_MS : false;
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
    // re-render(值形式只在 render 當下求值,群組檢視開著不動就永遠不會開始輪詢)
    refetchInterval: () => groupPollInterval(inTradingHours()),
  });
}
