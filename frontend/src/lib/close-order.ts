/** 平倉送單 body 的**唯一產生處**(SC-10;design §7)。
 *
 * `CapitalPositionsList`(部位列的平倉鍵)與 `FuturesLadder`(武裝列的一鍵平倉)送的是
 * 同一形狀 —— 同形正是抽這支 helper 的理由。**不開 `qty` 參數**:開了就等於允許兩個
 * 呼叫端送不同口數,而那是送單面最不該有的自由度。
 *
 * `kindOf` 與其值域(`KIND_TEXT` 的鍵集)一併放這裡,讓「哪些 kind 認得」只有一份定義
 * —— UI 標籤(`CapitalPositionsList`)與送單判定若各留一份,漂移的表現會是「畫面標了
 * 融資、送出去沒帶 kind」這種難察覺的不一致。
 */

import type { CapitalCloseBody, CapitalMarket, CapitalPosition, PositionKind } from "@/types";

/** sec 庫存種類標籤(列內小字 / 確認彈窗全稱);fut 不顯示(OI 列無種類維度)。 */
export const KIND_TEXT: Record<PositionKind, { short: string; full: string }> = {
  cash: { short: "現", full: "現股" },
  margin: { short: "資", full: "融資" },
  short: { short: "券", full: "融券" },
};

/** 後端 `Position.kind` 值域(TradeKind)比 `PositionKind` 寬(另有 daytrade_sell)——
 *  認不得就不標也不送 kind(退回「同檔唯一列」語意;真有多列後端會擋,不會猜錯種類)。
 *
 *  用 `Object.hasOwn` 不用 `in`:`in` 會讓 "toString" / "constructor" 這種原型鏈上的
 *  名字被判為合法 kind,而 kind 是後端字串直傳的。 */
export function kindOf(p: CapitalPosition): PositionKind | null {
  return Object.hasOwn(KIND_TEXT, p.kind) ? (p.kind as PositionKind) : null;
}

/** 部位 + 閘用估價 → 平倉 body。
 *
 *  - `key` = `stock_no`(**不是** UI 列選取用的複合鍵 `stock_no:kind`)
 *  - `kind` 只在 `market === "sec"` 且認得種類時附加 —— fut 硬送 "cash" 會讓每筆期貨
 *    平倉的審計多一個看起來像「現股」的誤導欄位(後端也只在 sec 分支讀它)
 *  - `qty` 一律送絕對值(空單的 `qty` 是負數) */
export function closeBodyOf(pos: CapitalPosition, price: number): CapitalCloseBody {
  const market = pos.market as CapitalMarket;
  const kind = market === "sec" ? kindOf(pos) : null;
  return {
    market,
    key: pos.stock_no,
    price,
    qty: Math.abs(pos.qty),
    ...(kind !== null ? { kind } : {}),
  };
}
