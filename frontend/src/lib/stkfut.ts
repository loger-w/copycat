/** 個股期合約的共用型別與純函式(stkfut-contracts SC-4)。
 *
 *  **兩個口徑必須分開**,這是整條前端資料流唯一容易靜默壞掉的地方:
 *  - 股號(`2330`):REST 路徑段、K 線 endpoint、右欄點價 gate、下單面標的顯示;
 *  - instrument key(`F:CDF:202609`):WS 推播的 `code` 欄、engine 的訂閱槽位鍵。
 *  後端 `_valid_code` 對 key 會 400,而 TC4 對不存在的 symbol 一律回 `Success: OK`
 *  —— 兩者互換時都不會有錯誤訊號,只會畫錯商品。
 */

/** 一腿產品(標準或小型)。`contracts` = 可訂閱的月份(YYYYMM)。 */
export interface StkfutLeg {
  prod: string;
  contracts: string[];
}

/** `GET /api/stock/stkfut/contracts/{code}` 的回應;`mini` 可能沒有(不是每檔都有小型)。 */
export interface StkfutContracts {
  code: string;
  name: string;
  std: StkfutLeg;
  mini: StkfutLeg | null;
}

/** 使用者當前選中的合約;`null` = 現貨態(既有行為逐項不變)。
 *  `mini` 留在選擇態裡而不是每次由 prod 反查:下單面的乘數 / 口數標籤要用它,
 *  而那一層拿不到 contracts 清單。 */
export interface StkfutSelection {
  prod: string;
  ym: string;
  mini: boolean;
}

/** 主圖 instrument 鍵 —— **WS 比對與 effect deps 專用**,不可當 REST 路徑段。 */
export function instrumentKeyOf(
  code: string | null,
  contract: { prod: string; ym: string } | null,
): string | null {
  if (code === null) return null;
  return contract === null ? code : `F:${contract.prod}:${contract.ym}`;
}

/** `202609` → `2026/09`(下拉選項文字)。 */
export function ymLabel(ym: string): string {
  return `${ym.slice(0, 4)}/${ym.slice(4)}`;
}

/** `<select>` 的 option value(`CDF:202609`)→ 選擇態。
 *
 *  `""`(現貨)與**任何不在清單內的值**都回 `null` —— 這是前端側的白名單:
 *  後端 D7 也會擋,但這裡先擋掉可以避免拿一個必被 400 的 URL 去洗掉主圖。 */
export function selectionOf(contracts: StkfutContracts, value: string): StkfutSelection | null {
  const [prod, ym] = value.split(":");
  if (prod === undefined || ym === undefined) return null;
  const mini = contracts.mini;
  if (mini !== null && mini.prod === prod && mini.contracts.includes(ym)) {
    return { prod, ym, mini: true };
  }
  if (contracts.std.prod === prod && contracts.std.contracts.includes(ym)) {
    return { prod, ym, mini: false };
  }
  return null;
}
