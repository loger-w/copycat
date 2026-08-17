/** 分時圖「當日成交點」的純函式層(單檔頁現貨 / 個股期 + 群組圖牆共用;零 React)。
 *
 *  ## 近似版:每張委託一點(D7,user 拍板)
 *
 *  資料源是 `CapitalOrder`(委託列表),它**沒有逐筆成交明細** —— 一張單只留
 *  `avg_fill_price`(均價)與 `time`(**最新事件時間**,不是首筆成交時間)。所以一張委託
 *  折成一個點,座標 = (最新事件分鐘, 均價)。已知的失真:
 *
 *  - 分批成交多筆會被壓成同一點(時間取最後那筆事件)。
 *  - 尾段事件是刪單(部分成交後刪)時,點落在**刪單時刻**而不是成交時刻。
 *  - `date` 同樣是**最新事件日**(`CapitalStore.apply_reply` 每筆回報有值即覆寫)——
 *    昨日部分成交、今日刪單的單,`date` 會變成今日,於是以「今日刪單分鐘 × 昨日均價」
 *    畫上今日圖。日期界怎麼收都躲不掉(它與成交事件本身不同源);唯一乾淨解 = 精確版
 *    逐筆 D 事件(下方 next-time)。
 *
 *  精確版(後端保留逐筆 D 事件 + `GET /api/capital/fills`)記 next-time,不在本輪。
 *
 *  ## 與 `lib/ladder-lots.ts::aggregateLots` 的分工
 *
 *  兩者吃同一份 orders,但**聚合的欄位不同,不可互換**:
 *
 *  | | 位置欄位 | 聚合鍵 | 日期界 |
 *  |---|---|---|---|
 *  | `aggregateLots`(閃電梯) | `price`(**委託價**) | 價位 | 活單恆計、終態單看日期集合 |
 *  | 本檔(分時圖) | `avg_fill_price`(**成交均價**)+ `time` | 分鐘 × 買賣側 | 今日 ∨ 昨日活單 |
 *
 *  梯是價格軸、沒有時間軸,所以「昨日建立的幽靈活單」最多多一格徽章;圖有時間軸,幽靈單
 *  會在**今日的圖上畫出一個假成交**(AD-2)。代價不對稱,日期界因此比梯窄。 */
import { futExchangeContract } from "@/lib/futures-ladder";
import { ymdOf } from "@/lib/ladder-lots";
import { minuteKey } from "@/lib/stock-accum";
import { minuteToX, type XWindow } from "@/lib/stock-intraday-svg";
import type { CapitalOrder } from "@/types";

export type FillSide = "B" | "S";

/** 一個成交點:分鐘序號 × 價格(毫元)× 側 × 成交量(顯示單位,張 / 口)。 */
export interface FillPoint {
  minute: number;
  priceMilli: number;
  side: FillSide;
  qty: number;
}

/** 投影到 SVG 座標後的成交點;`x` / `y` 是**三角尖端**(= 成交價那個點)。 */
export interface FillMark extends FillPoint {
  x: number;
  y: number;
}

export interface FillMarkStyle {
  /** 三角底邊半寬 */
  halfW: number;
  /** 尖端到底邊的高 */
  height: number;
  /** 與底色同色的描邊寬(`paintOrder="stroke"` 墊在填色下),讓三角在走勢線 / 填色上讀得出來 */
  halo: number;
}

/** 由極值標記的 `INTRADAY_MARK.dot`(radius 2.5 / halo 1,視覺外緣半徑 3)推導:
 *  高 = 外緣直徑 6、底邊半寬 3.5 —— 與現價圈 / 極值圓在畫面上量級相同,不搶視覺。
 *  **不共用 `ExtremeMarkStyle`**:那個 style 帶價位文字的翻面距離,三角沒有文字。 */
export const FILL_MARK: FillMarkStyle = { halfW: 3.5, height: 6, halo: 1 };

/** 「沒有成交」的**單一 identity**。零筆時每次回新 `[]` 會讓 `ChartStatic` / `GroupCard`
 *  的 memo 每秒被打穿(quotes 每秒換 identity → 父層每秒 render),而症狀只是「圖有點卡」,
 *  沒有測試會紅。所有回空陣列的路徑一律回這個常數。 */
export const EMPTY_FILLS: readonly FillPoint[] = [];
export const EMPTY_MARKS: readonly FillMark[] = [];

/** 成交點的日期界(YYYYMMDD,與 `CapitalOrder.date` 同格式)。 */
export interface FillDates {
  today: string;
  yesterday: string;
}

/** `YYYYMMDD` → `{today, yesterday}`。輸入取自 `ymdOf(new Date())`(caller 每 render 算,
 *  跨午夜時字串一變 useMemo 自然失效);減一日交給 `Date` 建構子正規化,與 `ymdWindow` 同源。 */
export function fillDates(todayYmd: string): FillDates {
  const y = Number(todayYmd.slice(0, 4));
  const m = Number(todayYmd.slice(4, 6));
  const d = Number(todayYmd.slice(6, 8));
  return { today: todayYmd, yesterday: ymdOf(new Date(y, m - 1, d - 1)) };
}

/** 過濾通過的單筆(尚未按分鐘 × 側合併);`code` 留著給 `fillsByCode` 分組。 */
interface RawFill extends FillPoint {
  code: string;
}

/** 單筆委託 → `RawFill`,不合條件回 null。
 *
 *  `excludeUnit`:現股(單檔頁現貨態 + 群組卡)傳 `"股"` 把零股單整筆排除 —— 與現股梯同
 *  口徑(AD-3),「我的單」在梯與圖上才一致。個股期不傳(契約碼與股號零碰撞,比對鍵已足)。
 *
 *  日期界(AD-2):`今日` ∨(`actionable` ∧ `昨日`)。`date` 是**最新事件日**
 *  (`CapitalStore.apply_reply` 每筆回報有值即覆寫),**不是委託建立日**(cr1 A-3)——
 *  所以「盤後預約單今日成交」那種單在成交回報進來的同時 `date` 就已經是今日,前半條
 *  就收得到。後半條真正收的是「最後一次回報停在昨日、今日仍 actionable」的單,而
 *  `filled_qty > 0` 意味那筆成交發生在昨日 —— 它會以昨日的均價 × 昨日的分鐘畫在今日
 *  圖上,是明示接受的殘餘風險(理論上收盤即終態,活單不該跨日留著)。
 *  不放寬到「活單恆計」是因為 `CapitalStore` 跨日不清 + prod server 長跑,更早的幽靈
 *  活單會在今日圖上畫出假成交。 */
function rawFill(o: CapitalOrder, dates: FillDates, excludeUnit?: string): RawFill | null {
  if (o.stock_no === null || o.time === null || o.avg_fill_price === null) return null;
  if (o.filled_qty <= 0) return null;
  if (excludeUnit !== undefined && o.unit === excludeUnit) return null;
  // 非 B/S 整筆跳過(無側可歸;同 aggregateLots 的紀律)
  const side: FillSide | null = o.buy_sell === "B" ? "B" : o.buy_sell === "S" ? "S" : null;
  if (side === null) return null;
  if (o.date !== dates.today && !(o.actionable && o.date === dates.yesterday)) return null;
  return {
    code: o.stock_no,
    minute: minuteKey(o.time),
    priceMilli: Math.round(o.avg_fill_price * 1000),
    side,
    qty: o.filled_qty,
  };
}

/** 同分鐘同向合併 → 依 minute 升冪(同分鐘 B 先 S 後)。
 *
 *  合併價 = **量加權平均**(AD-4):同分鐘同向 100 元@2 與 101 元@1 標在 100 或 101 都是
 *  假陳述,加權是唯一不偏的那一點。分子累加用毫元整數 × 量(市場價格運算一律整數毫元,
 *  同 `market.py` 紀律),最後才 `Math.round` 落回毫元。 */
function aggregate(raws: readonly RawFill[]): readonly FillPoint[] {
  if (raws.length === 0) return EMPTY_FILLS;
  interface Bucket {
    minute: number;
    side: FillSide;
    qty: number;
    /** 量加權分子:Σ(毫元 × 量) */
    amount: number;
  }
  const buckets = new Map<string, Bucket>();
  for (const r of raws) {
    const k = `${r.minute}|${r.side}`;
    const cur = buckets.get(k) ?? { minute: r.minute, side: r.side, qty: 0, amount: 0 };
    cur.qty += r.qty;
    cur.amount += r.priceMilli * r.qty;
    buckets.set(k, cur);
  }
  return [...buckets.values()]
    .map((b) => ({
      minute: b.minute,
      priceMilli: Math.round(b.amount / b.qty),
      side: b.side,
      qty: b.qty,
    }))
    .sort((a, b) => a.minute - b.minute || (a.side === b.side ? 0 : a.side === "B" ? -1 : 1));
}

/** 單一比對鍵(股號 / 期交所契約碼)的成交點。
 *
 *  `key === null` 直接回 `EMPTY_FILLS`(同 `aggregateLots` 的 guard)—— 個股期合約 ym
 *  解不出來時 caller 拿到的就是 null,拿它去比對會對到 `stock_no` 同樣是 null 的單。 */
export function fillPoints(
  orders: readonly CapitalOrder[] | undefined,
  key: string | null,
  dates: FillDates,
  excludeUnit?: string,
): readonly FillPoint[] {
  if (key === null) return EMPTY_FILLS;
  const raws: RawFill[] = [];
  for (const o of orders ?? []) {
    if (o.stock_no !== key) continue;
    const r = rawFill(o, dates, excludeUnit);
    if (r !== null) raws.push(r);
  }
  return aggregate(raws);
}

/** 群組圖牆用:一次折完所有 code(圖牆層算一份,每卡只取自己那個 key)。
 *
 *  零筆的 code **不入 map**,caller 以 `?? EMPTY_FILLS` 補 —— 無成交的卡拿到的永遠是
 *  同一個 identity,`GroupCard` 的 memo 不被打穿(W-5)。
 *  只認現股(`excludeUnit="股"` 由 caller 傳):契約碼→股號反查留給精確版。 */
export function fillsByCode(
  orders: readonly CapitalOrder[] | undefined,
  dates: FillDates,
  excludeUnit?: string,
): Map<string, readonly FillPoint[]> {
  const buckets = new Map<string, RawFill[]>();
  for (const o of orders ?? []) {
    const r = rawFill(o, dates, excludeUnit);
    if (r === null) continue;
    const arr = buckets.get(r.code);
    if (arr === undefined) buckets.set(r.code, [r]);
    else arr.push(r);
  }
  const out = new Map<string, readonly FillPoint[]>();
  for (const [code, raws] of buckets) out.set(code, aggregate(raws));
  return out;
}

/** 個股期態的比對鍵:群益回報的期貨單 `stock_no` 放的是期交所契約碼(如 `CDFH6`)。
 *
 *  `futExchangeContract` 對非 YYYYMM 會 throw。這裡的 catch **有具體處理**:回 null →
 *  `fillPoints` 走 guard 回 `EMPTY_FILLS` = 零標記。不 catch 的話合約月份解不出來時整張
 *  分時圖白屏(圖比成交點重要)。同 `StkfutLadder.tsx:113-121` 既有做法。 */
export function stkfutFillKey(prod: string, ym: string): string | null {
  try {
    return futExchangeContract(prod, ym);
  } catch {
    return null;
  }
}

/** 三角中心 x 的夾制。**整個圖案一起平移**(同 `markCenterX` 的理由),位移最多一個外緣
 *  半寬(`halfW + halo/2` = 4),仍指得到那一分鐘。
 *
 *  ⚠ **常態路徑上是 no-op**(cr1 A-4):正常寬度下 `minuteToX` 的值域是
 *  `[Y_AXIS_W, w − R_AXIS_W]` = `[36, w − 40]`,兩端離 viewBox 邊都已 ≥ 36px ≫ 4 ——
 *  夾制實際只在**退化寬度**(`plotWidth` 被 clamp 成 1,即 `w ≤ 77`)下生效。
 *  留著的理由是它就是 spec AD-6 的字面公式 + 那條退化路徑的守衛,不是常態需求;
 *  讀者不要以為第一 / 最後一分鐘的三角平常會被平移。 */
export function clampFillX(x: number, w: number, style: FillMarkStyle = FILL_MARK): number {
  const edge = style.halfW + style.halo / 2;
  return Math.min(Math.max(x, edge), w - edge);
}

/** SVG `points` 字串。**尖端在成交價**(D8 原文):買 = ▲ 尖端在上體在下、賣 = ▼ 尖端在下
 *  體在上 —— 兩種都讓三角體朝「離開價線」的方向長,不會蓋住走勢線本身。 */
export function fillTrianglePoints(
  cx: number,
  tipY: number,
  side: FillSide,
  style: FillMarkStyle = FILL_MARK,
): string {
  const baseY = side === "B" ? tipY + style.height : tipY - style.height;
  return `${cx},${tipY} ${cx - style.halfW},${baseY} ${cx + style.halfW},${baseY}`;
}

/** 成交點 → SVG 座標。窗外 / 域外一律**不畫**,不夾到邊上:夾了就是把成交時間 / 價格
 *  講錯(同 overlay 線與極值標記的既有規則)。
 *
 *  尖端 y **不夾**:域頂的賣點三角體最多被 viewBox 裁掉約 2px(`PAD_Y` 4 vs 高 6),
 *  夾了反而讓尖端指不到成交價 —— 兩害相權取形狀被裁(AD-6 / R10,明示接受)。 */
export function projectFills(
  fills: readonly FillPoint[],
  geo: { toY: (p: number) => number; yDomain: readonly [number, number] },
  w: number,
  xw: XWindow,
): readonly FillMark[] {
  const [lo, hi] = geo.yDomain;
  const out: FillMark[] = [];
  for (const f of fills) {
    // **正向條件的否定**,不寫 `minute < start || minute > end`(沿 `stock-accum.ts::foldVp`
    // review A3 的同一理由):後者對 `NaN` 的兩個比較都是 false,時間戳解不出分鐘的壞單
    // 會整筆漏進來,長出 `x = NaN` 的 polygon(SVG 靜默不畫,readout 卻照樣追加一欄)。
    if (!(f.minute >= xw.start && f.minute <= xw.end)) continue;
    if (f.priceMilli < lo || f.priceMilli > hi) continue;
    out.push({ ...f, x: clampFillX(minuteToX(f.minute, w, xw), w), y: geo.toY(f.priceMilli) });
  }
  return out.length === 0 ? EMPTY_MARKS : out;
}

/** 該分鐘的成交點(readout 用;輸入已是 minute 升冪 / B 先 S 後,順序原樣保留)。 */
export function fillsAtMinute(fills: readonly FillPoint[], minute: number): readonly FillPoint[] {
  const out = fills.filter((f) => f.minute === minute);
  return out.length === 0 ? EMPTY_FILLS : out;
}

/** readout「成交」欄文案(AD-7):`買 2@2380`、雙側以單一空格連接成 `買 2@2380 賣 1@2385`。
 *  不帶單位 —— readout 既有欄位皆無單位。價格格式化由 caller 給(與該圖其他價格同源)。 */
export function fillLabel(
  points: readonly FillPoint[],
  fmt: (priceMilli: number) => string,
): string {
  return points
    .map((p) => `${p.side === "B" ? "買" : "賣"} ${p.qty}@${fmt(p.priceMilli)}`)
    .join(" ");
}
