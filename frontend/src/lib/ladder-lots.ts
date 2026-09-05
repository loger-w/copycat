/** 閃電梯「我的單」價位聚合(現股 `PriceLadder` / 個股期 `StkfutLadder` 共用)。
 *
 *  兩個 container 原本各留一份逐字相同的 `aggregateLots`(stkfut-contracts R2-4 抽
 *  LadderView 時的遺留),本檔把它合一後擴充「已成交量」。
 *
 *  期貨梯不走這裡(`lib/futures-ladder.ts::splitMyLots`)。兩邊的 **qty / seqs 算式**
 *  必須一致 —— 改一邊就要改另一邊 —— 但有三處刻意的差異:
 *
 *  1. 本函式分買賣側輸出兩張 map;`splitMyLots` 不分側(期貨梯是單一紅方格,
 *     spec auto-default 第 4 條)。
 *  2. 本函式對 `buy_sell` 非 `"B"`/`"S"` 的單**整筆跳過**(連 seq 都不收,因為無側
 *     可歸);`splitMyLots` 根本不看 `buy_sell`。該態僅在「刪單失敗回報先到、原單
 *     欄位尚未補齊」的極罕留 null 情形出現,現股梯少一個刪單入口(委託列表仍在)
 *     優於歸錯側。fills 路徑的側別由 `groupUsableFillsBySeq` 同口徑過濾(側別空的列
 *     不計 → 總量對不上 → 該單退回委託價,見 `aggregateLots` doc)。
 *  3. **filled 的落格**(2026-09-05 起):本函式接 `fills` 時已成交量落**成交價**列
 *     (見 `aggregateLots` doc);`splitMyLots` 仍落委託價(期貨梯本輪不接 fills)。
 *     不傳 fills 時兩邊 filled 算式仍逐字一致。
 */
import type { CapitalFill, CapitalOrder } from "@/types";

/** 同價位聚合。`qty` = 活單殘量、`filled` = 已成交量、`seqs` = **活單** seq。
 *
 *  三者刻意分開:`seqs` 是刪單入口(只有活單刪得掉),`filled` 是既成事實(終態單、
 *  部分成交後刪單都算)。`seqs` 非空一律維持可點紅方格(actionable 殘 0 的單也刪得掉);
 *  `qty === 0 && seqs.length === 0 && filled > 0` 畫面轉不可點徽章 —— 它代表「這一格只有
 *  既成的成交」:終態全成交單,**或**活單 / 市價單在**別的價位**(成交價 ≠ 委託價)成交的
 *  那部分;該活單的刪單入口在它的委託價列。 */
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
 *  `fills`(選傳,現股梯傳):**已成交量以成交價落格**。該單在 fills 表的成交能**完整解釋**
 *  `filled_qty`(可用列的量總和恰等於它)時,每筆成交落在**它自己的成交價**那格
 *  (`filled += fill.qty`,不取均價 —— 均價可能落在不存在的檔位),`filled_qty` 就不再落委託價列;
 *  殘量與 `seqs`(刪單入口)恆留委託價列。動機 = user 實遇「掛 98.5 買、成交 98.3,徽章卡 98.5 而
 *  成本線在 98.3」—— 成本 / 打平線本就吃成交均價,梯上的成交徽章要跟它同一把尺。
 *  **成交價不明時整張退回委託價**(= 過去的算式一字不改):不傳 fills(個股期梯)/ 舊後端 404 → `[]` /
 *  query 載入前的一拍 / fills 表沒有該 seq / **總量對不上**(orders 與 fills 是兩支獨立 query,
 *  同一 WS 事件 invalidate 但各自解析,fills 先到會比 `filled_qty` 多、orders 先到會少 —— 照 fills 畫
 *  會膨脹或短計,退回委託價等下一拍對齊)。可用列 = `qty > 0`、`price > 0`、側別 B/S、且不是
 *  `excludeUnit`(store 除不盡退回 `unit="股"` 的列,張梯不能把股數當張數;同 `fill-marks` AD-3 口徑);
 *  異常列被濾掉後總量對不上,也就自然退回委託價。市價單(`limitPriceOf` 回 null)沒有委託價列:
 *  成交靠這條路上梯,殘量沒有價位可掛、不上梯,成交價不明時零 entry(與過去相同)。
 *  日期界仍在**單**上判(fills 只是量的來源)。已知畫面態:活單全成交但 N 未到(actionable 仍真)且
 *  成交價 ≠ 委託價 → 委託價列紅方格印 `0(0)`(刪單入口保留)+ 成交價列 `(n)`。 */
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
  const sideOf = (bs: string | null): Map<number, LadderLot> | null =>
    bs === "B" ? buy : bs === "S" ? sell : null;
  const addToLot = (
    map: Map<number, LadderLot>,
    priceMilli: number,
    part: { qty: number; filled: number; seq?: string },
  ): void => {
    const cur = map.get(priceMilli) ?? { qty: 0, filled: 0, seqs: [] };
    cur.qty += part.qty;
    cur.filled += part.filled;
    if (part.seq !== undefined) cur.seqs.push(part.seq);
    map.set(priceMilli, cur);
  };
  const fillsBySeq = groupUsableFillsBySeq(fills, excludeUnit);
  for (const o of orders ?? []) {
    if (o.stock_no !== key) continue;
    if (excludeUnit !== undefined && o.unit === excludeUnit) continue;
    // 終態單只認日期界內的(活單恆計);失敗 / 退單 filled_qty 恆 0 → 自然零痕跡
    const countFilled = o.actionable || (o.date !== null && filledDates.has(o.date));
    const seqFills = countFilled ? fillsBySeq.get(o.seq_no) : undefined;
    const fillsExplainAll =
      seqFills !== undefined && seqFills.reduce((s, f) => s + f.qty, 0) === o.filled_qty;
    if (fillsExplainAll) {
      for (const f of seqFills) {
        addToLot(f.side === "B" ? buy : sell, f.priceMilli, { qty: 0, filled: f.qty });
      }
    }
    const limitPrice = limitPriceOf(o);
    if (limitPrice === null) continue; // 市價單:殘量沒有價位可掛
    const map = sideOf(o.buy_sell);
    if (map === null) continue;
    // 活單:殘量 + seq(殘量可能是 0 —— P/U 先到 N 未到,刪單入口仍必須在)
    const addQty = o.actionable ? Math.max(0, o.order_qty - o.filled_qty) : 0;
    // 成交價不明才把 filled_qty 落委託價(fills 能完整解釋的已在上面逐筆落格)
    const addFilled = countFilled && !fillsExplainAll ? o.filled_qty : 0;
    if (!o.actionable && addFilled === 0) continue; // 不產生 entry
    addToLot(map, Math.round(limitPrice * 1000), {
      qty: addQty,
      filled: addFilled,
      seq: o.actionable ? o.seq_no : undefined,
    });
  }
  return { buy, sell };
}

/** 過閘後的成交列:側別已窄化為 B/S、價格已是毫元 —— 消費端不必再守 null 側。 */
interface UsableFill {
  side: "B" | "S";
  priceMilli: number;
  qty: number;
}

/** seq → 該單**可用**的成交列:`qty > 0`、`price > 0`(0 不是價格,同 `fill-marks` 的 `!(f.price > 0)`
 *  守門與本檔 `limitPriceOf`)、側別 B/S(store 寫 `a.buy_sell or ""`,空字串無側可歸;過濾當下窄化型別,
 *  消費端不需要 fallback 側)、非 `excludeUnit`。**不看 `stock_no`**:群益 seq 是帳戶全域唯一
 *  (store 以 seq_no 為聚合鍵),同 seq 就是同一張單。空 / 未傳 → 空 map(每張單都「成交價不明」)。 */
function groupUsableFillsBySeq(
  fills: readonly CapitalFill[] | undefined,
  excludeUnit: string | undefined,
): Map<string, UsableFill[]> {
  const out = new Map<string, UsableFill[]>();
  for (const f of fills ?? []) {
    if (f.qty <= 0 || !(f.price > 0)) continue;
    if (f.buy_sell !== "B" && f.buy_sell !== "S") continue;
    if (excludeUnit !== undefined && f.unit === excludeUnit) continue;
    const usable: UsableFill = { side: f.buy_sell, priceMilli: Math.round(f.price * 1000), qty: f.qty };
    const cur = out.get(f.seq_no);
    if (cur === undefined) out.set(f.seq_no, [usable]);
    else cur.push(usable);
  }
  return out;
}

/** 可當梯列鍵的委託價;`null` = 沒有(市價單)。本 app 送出的市價單帶 `price_type === "market"`
 *  (回報可能帶名目價,仍不能拿來定位);群益 APP 下的 `price_type` 恆 null,唯一線索是委託價
 *  0(送單 bstrPrice="0" 的回聲)或空(解析失敗)。`price <= 0` 不是價格 —— 同
 *  `stock-tick::isMarketLevel`(`priceMilli <= 0`)與後端 `_best_limit_price` 的口徑。 */
function limitPriceOf(o: CapitalOrder): number | null {
  if (o.price_type === "market" || o.price === null || o.price <= 0) return null;
  return o.price;
}
