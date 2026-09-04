/** 閃電梯「我的單」價位聚合(現股 `PriceLadder` / 個股期 `StkfutLadder` 共用)。
 *
 *  兩個 container 原本各留一份逐字相同的 `aggregateLots`(stkfut-contracts R2-4 抽
 *  LadderView 時的遺留),本檔把它合一後擴充「已成交量」。
 *
 *  期貨梯不走這裡(`lib/futures-ladder.ts::splitMyLots`)。兩邊的 **qty / filled 算式**
 *  與 **seqs 收集規則**必須一致 —— 改一邊就要改另一邊 —— 但有兩處刻意的差異:
 *
 *  1. 本函式分買賣側輸出兩張 map;`splitMyLots` 不分側(期貨梯是單一紅方格,
 *     spec auto-default 第 4 條)。
 *  2. 本函式對 `buy_sell` 非 `"B"`/`"S"` 的單**整筆跳過**(連 seq 都不收,因為無側
 *     可歸);`splitMyLots` 根本不看 `buy_sell`。該態僅在「刪單失敗回報先到、原單
 *     欄位尚未補齊」的極罕留 null 情形出現,現股梯少一個刪單入口(委託列表仍在)
 *     優於歸錯側。
 */
import type { CapitalFill, CapitalOrder } from "@/types";

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

/** 本機日曆日 → `YYYYMMDD`(與 `OrderRecord.date` 同格式)。
 *
 *  `ymdWindow` 原本把這段格式化內嵌在迴圈裡,而分時圖的成交點也要同一格式的「今日」字串
 *  (`lib/fill-marks.ts` 的日期界)。各抄一份的失效樣態是「其中一處忘了 padStart」——
 *  九月變成 `20269` 而不是 `202609`,兩邊的日期界從此永遠對不上,而畫面只是「沒有我的單」,
 *  零錯誤訊號(同 `aggregateLots` 比對鍵抄錯的教訓)。 */
export function ymdOf(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${d.getFullYear()}${m}${String(d.getDate()).padStart(2, "0")}`;
}

/** `now` 起算 `offsets` 天的本機日曆日集合(YYYYMMDD,與 `OrderRecord.date` 同格式)。
 *
 *  現股梯傳 `[0]`(嚴格今日);期貨 / 個股期梯傳 `[-1, 0, 1]` —— `date` 是**最新事件日**
 *  (`CapitalStore.apply_reply` 每筆回報有值即覆寫,不是委託建立日;cr1 A-3),
 *  夜盤跨午夜時它是交易日還是日曆日尚未實證,±1 日窗在兩種假設下都涵蓋得到。 */
export function ymdWindow(now: Date, offsets: readonly number[]): Set<string> {
  const out = new Set<string>();
  for (const off of offsets) {
    // `Date` 建構子自己會把溢出的日數正規化(月初 −1 天 → 上個月最後一日)
    out.add(ymdOf(new Date(now.getFullYear(), now.getMonth(), now.getDate() + off)));
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
 *  會誤殺 market 缺值 fallback 成 "張" 的期貨單,連刪單入口都砍掉)。
 *  ⚠ `unit === "股"` 實際涵蓋的是**零股 ∪ 未知 market**(store `_to_record` 的 else
 *  是 catch-all),寬於「排除零股」的字面承認面;現股梯靠第一道股號比對鍵二次擋住
 *  未知 market 的契約碼單,所以擴大的那一塊落不到畫面上。
 *
 *  `fills`(選傳,現股梯傳):**沒有委託價可當梯列鍵的單**(`isPriceless`,= 市價單)
 *  改由 fills 表同 seq 的逐筆成交決定已成交量 —— 每筆成交落在**它自己的成交價**那格
 *  (`filled += fill.qty`),不取均價(均價可能落在不存在的檔位);未成交殘量沒有價位可掛,
 *  不上梯(與過去相同)。日期界與 `excludeUnit` 仍在**單**上判(fills 只是量的來源)。
 *  不傳 fills = 這類單一律不上梯(個股期梯:其市價鈕實為限價貼漲跌停 + IOC,委託價有效,
 *  本就不走這條)。限價單路徑**不看 fills**:委託價優於成交價時徽章仍在委託價列。 */
export function aggregateLots(
  orders: CapitalOrder[] | undefined,
  key: string | null,
  filledDates: ReadonlySet<string>,
  excludeUnit?: string,
  fills?: readonly CapitalFill[],
): { buy: Map<number, LadderLot>; sell: Map<number, LadderLot> } {
  const buy = new Map<number, LadderLot>();
  const sell = new Map<number, LadderLot>();
  if (key === null) return { buy, sell };
  /** 走 fills 路徑的 seq(已過股號 / unit / 日期界三道閘) */
  const pricelessSeqs = new Set<string>();
  for (const o of orders ?? []) {
    if (o.stock_no !== key) continue;
    if (excludeUnit !== undefined && o.unit === excludeUnit) continue;
    // 終態單只認日期界內的(活單恆計);失敗 / 退單 filled_qty 恆 0 → 自然零痕跡
    const countFilled = o.actionable || (o.date !== null && filledDates.has(o.date));
    const limitPrice = limitPriceOf(o);
    if (limitPrice === null) {
      if (countFilled) pricelessSeqs.add(o.seq_no);
      continue;
    }
    const map = o.buy_sell === "B" ? buy : o.buy_sell === "S" ? sell : null;
    if (map === null) continue;
    // 活單:殘量 + seq(殘量可能是 0 —— P/U 先到 N 未到,刪單入口仍必須在)
    const addQty = o.actionable ? Math.max(0, o.order_qty - o.filled_qty) : 0;
    const addFilled = countFilled ? o.filled_qty : 0;
    if (!o.actionable && addFilled === 0) continue; // 不產生 entry
    const priceMilli = Math.round(limitPrice * 1000);
    const cur = map.get(priceMilli) ?? { qty: 0, filled: 0, seqs: [] };
    cur.qty += addQty;
    cur.filled += addFilled;
    if (o.actionable) cur.seqs.push(o.seq_no);
    map.set(priceMilli, cur);
  }
  if (pricelessSeqs.size > 0) {
    for (const f of fills ?? []) {
      if (!pricelessSeqs.has(f.seq_no)) continue;
      const map = f.buy_sell === "B" ? buy : f.buy_sell === "S" ? sell : null;
      if (map === null || f.qty <= 0) continue;
      const priceMilli = Math.round(f.price * 1000);
      const cur = map.get(priceMilli) ?? { qty: 0, filled: 0, seqs: [] };
      cur.filled += f.qty;
      map.set(priceMilli, cur);
    }
  }
  return { buy, sell };
}

/** 可當梯列鍵的委託價;`null` = 沒有(市價單)。本 app 送出的市價單帶 `price_type === "market"`
 *  (回報可能帶名目價,仍不能拿來定位);群益 APP 下的 `price_type` 恆 null,唯一線索是委託價
 *  0(送單 bstrPrice="0" 的回聲)或空(解析失敗)。`price: 0` 不是價格 —— 同
 *  `stock-tick::isMarketLevel` 與後端 `_best_limit_price` 的口徑。 */
function limitPriceOf(o: CapitalOrder): number | null {
  if (o.price_type === "market" || o.price === null || o.price === 0) return null;
  return o.price;
}
