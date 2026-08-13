/** 閃電梯「我的單」價位聚合(現股 `PriceLadder` / 個股期 `StkfutLadder` 共用)。
 *
 *  兩個 container 原本各留一份逐字相同的 `aggregateLots`(stkfut-contracts R2-4 抽
 *  LadderView 時的遺留)。本檔把它合一 —— 行為零變更,只有 null 早退合併:現股的
 *  `code` 恆非 null,個股期的 `contract` 解析失敗時為 null(比對自然落空)。
 *
 *  期貨梯不走這裡(`lib/futures-ladder.ts::splitMyLots`,不分買賣側)。
 */
import type { CapitalOrder } from "@/types";

/** 同價位活單聚合(點紅方格逐 seq 直刪用)。 */
export interface LadderLot {
  qty: number; // 殘量(order_qty - filled_qty 聚合)
  seqs: string[];
}

/** 本檔 / 本合約 actionable 活單 → 價位(毫元)聚合殘量。
 *
 *  比對鍵由呼叫端決定:現股是**股號**、個股期是**期交所契約碼**(CDFI6)—— 群益回報的
 *  期貨單 `stock_no` 放的是契約碼,拿股號比會一筆都對不上(而畫面上只是「沒有掛單」,
 *  零錯誤訊號)。 */
export function aggregateLots(
  orders: CapitalOrder[] | undefined,
  key: string | null,
): { buy: Map<number, LadderLot>; sell: Map<number, LadderLot> } {
  const buy = new Map<number, LadderLot>();
  const sell = new Map<number, LadderLot>();
  if (key === null) return { buy, sell };
  for (const o of orders ?? []) {
    if (!o.actionable || o.stock_no !== key || o.price === null) continue;
    const map = o.buy_sell === "B" ? buy : o.buy_sell === "S" ? sell : null;
    if (map === null) continue;
    const priceMilli = Math.round(o.price * 1000);
    const cur = map.get(priceMilli) ?? { qty: 0, seqs: [] };
    cur.qty += Math.max(0, o.order_qty - o.filled_qty);
    cur.seqs.push(o.seq_no);
    map.set(priceMilli, cur);
  }
  return { buy, sell };
}
