/** 閃電梯「我的單」價位聚合(現股 `PriceLadder` / 個股期 `StkfutLadder` 共用)。
 *
 *  兩個 container 原本各留一份逐字相同的 `aggregateLots`(stkfut-contracts R2-4 抽
 *  LadderView 時的遺留),本檔把它合一後擴充「已成交量」。
 *
 *  期貨梯不走這裡(`lib/futures-ladder.ts::splitMyLots`,不分買賣側),但兩邊的
 *  qty / filled / seqs 口徑必須逐條相同 —— 改一邊就要改另一邊。
 */
import type { CapitalOrder } from "@/types";

/** 同價位聚合。`qty` = 活單殘量、`filled` = 已成交量、`seqs` = **活單** seq。
 *
 *  三者刻意分開:`seqs` 是刪單入口(只有活單刪得掉),`filled` 是既成事實(終態單、
 *  部分成交後刪單都算)。`qty === 0 && seqs.length === 0 && filled > 0` = 全成交,
 *  畫面轉不可點徽章;`seqs` 非空一律維持可點紅方格(actionable 殘 0 的單也刪得掉)。 */
export interface LadderLot {
  qty: number;
  filled: number;
  seqs: string[];
}

/** `now` 起算 `offsets` 天的本機日曆日集合(YYYYMMDD,與 `OrderRecord.date` 同格式)。
 *
 *  現股梯傳 `[0]`(嚴格今日);期貨 / 個股期梯傳 `[-1, 0, 1]` —— `date` 是**委託建立日**,
 *  夜盤跨午夜時它是交易日還是日曆日尚未實證,±1 日窗在兩種假設下都涵蓋得到。 */
export function ymdWindow(now: Date, offsets: readonly number[]): Set<string> {
  const out = new Set<string>();
  for (const off of offsets) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + off);
    const m = String(d.getMonth() + 1).padStart(2, "0");
    out.add(`${d.getFullYear()}${m}${String(d.getDate()).padStart(2, "0")}`);
  }
  return out;
}

/** 本檔 / 本合約的單 → 價位(毫元)聚合殘量與已成交量。
 *
 *  比對鍵由呼叫端決定:現股是**股號**、個股期是**期交所契約碼**(CDFI6)—— 群益回報的
 *  期貨單 `stock_no` 放的是契約碼,拿股號比會一筆都對不上(而畫面上只是「沒有掛單」,
 *  零錯誤訊號)。
 *
 *  `filledDates`:終態單的 `date` 要落在此集合才計入已成交量。`CapitalStore` 跨日不清
 *  (`clear()` 全 repo 無 caller)、prod server 長跑 → 無日期界會長出昨日的幽靈徽章。
 *  **活單的成交恆計**,不看日期界(涵蓋昨日建立、今日成交中的預約單)。
 *
 *  `excludeUnit`:現股梯傳 `"股"` 把零股單整筆排除 —— 張梯混進零股單量級差一千倍。
 *  期貨 / 個股期梯不傳(契約碼含英文字母、與股號零碰撞,比對鍵已足;整筆 unit 白名單
 *  會誤殺 market 缺值 fallback 成 "張" 的期貨單,連刪單入口都砍掉)。 */
export function aggregateLots(
  orders: CapitalOrder[] | undefined,
  key: string | null,
  filledDates: ReadonlySet<string>,
  excludeUnit?: string,
): { buy: Map<number, LadderLot>; sell: Map<number, LadderLot> } {
  const buy = new Map<number, LadderLot>();
  const sell = new Map<number, LadderLot>();
  if (key === null) return { buy, sell };
  for (const o of orders ?? []) {
    if (o.stock_no !== key || o.price === null) continue;
    if (excludeUnit !== undefined && o.unit === excludeUnit) continue;
    const map = o.buy_sell === "B" ? buy : o.buy_sell === "S" ? sell : null;
    if (map === null) continue;
    // 活單:殘量 + seq(殘量可能是 0 —— P/U 先到 N 未到,刪單入口仍必須在)
    const addQty = o.actionable ? Math.max(0, o.order_qty - o.filled_qty) : 0;
    // 終態單只認日期界內的(活單恆計);失敗 / 退單 filled_qty 恆 0 → 自然零痕跡
    const countFilled = o.actionable || (o.date !== null && filledDates.has(o.date));
    const addFilled = countFilled ? o.filled_qty : 0;
    if (!o.actionable && addFilled === 0) continue; // 不產生 entry
    const priceMilli = Math.round(o.price * 1000);
    const cur = map.get(priceMilli) ?? { qty: 0, filled: 0, seqs: [] };
    cur.qty += addQty;
    cur.filled += addFilled;
    if (o.actionable) cur.seqs.push(o.seq_no);
    map.set(priceMilli, cur);
  }
  return { buy, sell };
}
