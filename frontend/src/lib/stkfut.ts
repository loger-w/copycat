/** 個股期合約的共用型別與純函式(stkfut-contracts SC-4)。
 *
 *  **兩個口徑必須分開**,這是整條前端資料流唯一容易靜默壞掉的地方:
 *  - 股號(`2330`):REST 路徑段、K 線 endpoint、右欄點價 gate、下單面標的顯示;
 *  - instrument key(`F:CDF:202609`):WS 推播的 `code` 欄、engine 的訂閱槽位鍵。
 *  後端 `_valid_code` 對 key 會 400,而 TC4 對不存在的 symbol 一律回 `Success: OK`
 *  —— 兩者互換時都不會有錯誤訊號,只會畫錯商品。
 */

/** 一腿產品(標準或小型)。`contracts` = 可訂閱的月份(YYYYMM)。
 *
 *  `unit` = 契約單位股數(標準 2,000 / 小型 100 / ETF 10,000);後端對映表查無 → `null`。
 *  **不可用 0 表示未知**:0 會被下單前置閘讀成「非股票單位」→ 誤擋一檔本來可以下單的
 *  標的,而後端那道權威閘根本沒被觸發過(code review B2/B3)。 */
export interface StkfutLeg {
  prod: string;
  contracts: string[];
  unit: number | null;
}

/** `GET /api/stock/stkfut/contracts/{code}` 的回應;`mini` 可能沒有(不是每檔都有小型)。 */
export interface StkfutContracts {
  code: string;
  name: string;
  std: StkfutLeg;
  mini: StkfutLeg | null;
}

/** 使用者當前選中的合約;`null` = 現貨態(既有行為逐項不變)。
 *  `mini` / `unit` 留在選擇態裡而不是每次由 prod 反查:下單面的乘數、口數標籤與
 *  下單前置閘要用它們,而那一層拿不到 contracts 清單。 */
export interface StkfutSelection {
  prod: string;
  ym: string;
  mini: boolean;
  /** 契約單位股數;後端查無對映 → `null`(下單前置閘據此落回股號 fallback) */
  unit: number | null;
}

/** instrument key 的前綴 —— 產生端與辨識端共用同一個定義,不各寫各的字串。 */
const KEY_PREFIX = "F:";

/** 主圖 instrument 鍵 —— **WS 比對與 effect deps 專用**,不可當 REST 路徑段。 */
export function instrumentKeyOf(
  code: string | null,
  contract: { prod: string; ym: string } | null,
): string | null {
  if (code === null) return null;
  return contract === null ? code : `${KEY_PREFIX}${contract.prod}:${contract.ym}`;
}

/** 這個字串是 instrument key(而非股號)?
 *
 *  用途只有一個:**把 key 送進吃股號的 REST 路徑段之前擋下來**。後端 `_valid_code`
 *  對 key 一律 400,而發生的時機是**切換合約的那一個過渡 render** —— 選擇態(`stkfut`
 *  之類的顯式 prop)與 WS 推來的 `accum` 不同步,prop 先翻、snapshot 晚一拍,那一拍
 *  的組合是「現貨態 + 合約 code」,兩邊各自看都合法(Phase 6 real-env finding)。
 *
 *  **不可拿它當渲染分支的判準**(R6):要不要用期貨窗畫、要不要停 VP,一律吃顯式 prop。
 *  這裡判的是「這個 code 能不能當股號用」,是資料形狀問題不是模式問題。 */
export function isInstrumentKey(code: string): boolean {
  return code.startsWith(KEY_PREFIX);
}

/** 送單用的 TC4 月份 leaf symbol。
 *
 *  **不可用 `.HOT`**:HOT 由 TC4 解析成熱門月,使用者在下拉選的若是次月,送出去的
 *  會是近月 —— 真錢面板上「畫面顯示的合約」與「送出去的合約」必須是同一個。 */
export function stkfutTc4Symbol(contract: { prod: string; ym: string }): string {
  return `TC.F.TWF.${contract.prod}.${contract.ym}`;
}

/** 後端 `capital_api._STOCK_FUTURE_UNITS` 的鏡像:本輪唯一開放下單的兩種契約單位。 */
const STOCK_FUTURE_UNITS: readonly number[] = [2000, 100];

/** 股號 fallback 判準(單位不可得時才用)。
 *
 *  台股上市櫃普通股代號一律 1000–9999,開頭為 `0` 的是 ETF / ETN / 受益證券。
 *  這條與契約單位「今天」完全等價(版控對映檔 270 檔雙向驗過,見後端
 *  `TestPackagedMapInvariants`)—— 但那是資料的性質不是契約規格,所以它只是 fallback。 */
export function isEtfUnderlying(code: string): boolean {
  return code.startsWith("0");
}

/** 本輪不開放下單的標的?(下單面前置閘)
 *
 *  ETF 期貨的契約單位是 10,000 受益權單位、除權息調整契約是 2,157 之類的非標準值,
 *  後端 `_stkfut_gates` 對兩者一律回 `PRODUCT_NOT_ALLOWED`(design SC-6)。
 *  **權威判定仍在後端**,這裡只是前置閘,避免使用者在真錢面板上按下一個必被拒的鍵。
 *
 *  判準吃 **`unit`**(contracts route 自對映表併進來的契約單位)—— 與後端同一個判準,
 *  除權息調整契約這種「股號不是 0 開頭卻不可下單」的標的因此也擋得到。
 *  單位不可得(對映檔過期 / 新上市)才落回股號 fallback:方向保守,誤判只會多擋一檔,
 *  不會放行一張必被拒的單。 */
export function isOrderBlocked(code: string, unit: number | null): boolean {
  if (unit === null) return isEtfUnderlying(code);
  return !STOCK_FUTURE_UNITS.includes(unit);
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
    return { prod, ym, mini: true, unit: mini.unit ?? null };
  }
  if (contracts.std.prod === prod && contracts.std.contracts.includes(ym)) {
    return { prod, ym, mini: false, unit: contracts.std.unit ?? null };
  }
  return null;
}
