/** 分時圖「當日成交點」的純函式層(單檔頁現貨 / 個股期 + 群組圖牆共用;零 React)。
 *
 *  ## 精確版:每筆成交一點(L76,2026-08-31;取代近似版 D7)
 *
 *  資料源是 `CapitalFill`(`GET /api/capital/fills`,後端逐筆 D 事件、只留當日):
 *  每筆帶**自己的**成交價與時刻 —— 近似版(每張委託一點 = 最新事件分鐘 × 均價)的
 *  三種失真(分批壓成一點 / 刪單時刻蓋成交時刻 / 昨日均價畫今日圖)全數消失。
 *  同 (分鐘, 側, 價位) 的多筆**無損合併**(qty 相加;同點多個三角只是重疊雜訊),
 *  不同價位各自一點 —— 「每筆一標記」的語意保住。拿不到 API(舊後端 404)→ 空 =
 *  不畫(D2 拍板:寧空白不失真)。
 *
 *  ## 與 `lib/ladder-lots.ts::aggregateLots` 的分工
 *
 *  梯吃 orders 定**殘量 / 刪單入口**(價格軸,委託價);圖自本輪起吃 fills(時間軸,逐筆成交)。
 *  2026-09-05(mod/ladder-market-fill-marker)起現股梯的**已成交量**也吃 fills:同 seq 的逐筆
 *  成交價落格(限價 / 市價同一把尺,與成本線同尺;fills 解釋不了 `filled_qty` 時退回委託價)——
 *  兩邊對成交畫的是同一筆資料,價格軸與時間軸各自一份投影。excludeUnit="股"(現股排零股)
 *  與 `price > 0` 守門兩邊同口徑(AD-3)。 */
import { alldayIndexOf, anchorDateOf } from "@/lib/allday";
import { futExchangeContract } from "@/lib/futures-ladder";
import { minuteKey } from "@/lib/stock-accum";
import { minuteToX, type XWindow } from "@/lib/stock-intraday-svg";
import type { CapitalFill } from "@/types";

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

/** 過濾通過的單筆(尚未合併);`code` 留著給 `fillsByCode` 分組(= wire `code` 衍生欄,
 *  個股期契約碼已反查成股號;反查不到退回 `stock_no`,那筆只會被合約鍵的圖撿到)。 */
interface RawFill extends FillPoint {
  code: string;
}

/** 與軸無關的欄位守門(量 / 價 / 側 / 單位)。兩種軸(現貨窗 / 近全軸)共用這一份,
 *  各寫一次的話漂掉的樣態是「圖上多一個不該有的三角」而兩邊都不報錯。 */
interface FillBase {
  code: string;
  side: FillSide;
  priceMilli: number;
  qty: number;
  /** YYYYMMDD(成交**到達日**,逐筆自帶)/ HH:MM:SS */
  date: string;
  time: string;
}

function baseFill(f: CapitalFill, excludeUnit?: string): FillBase | null {
  if (f.stock_no === null || f.time === null) return null;
  if (f.qty <= 0 || !(f.price > 0)) return null;
  if (excludeUnit !== undefined && f.unit === excludeUnit) return null;
  // 非 B/S 整筆跳過(無側可歸;同 aggregateLots 的紀律)
  const side: FillSide | null = f.buy_sell === "B" ? "B" : f.buy_sell === "S" ? "S" : null;
  if (side === null) return null;
  return {
    code: f.code ?? f.stock_no,
    side,
    priceMilli: Math.round(f.price * 1000),
    qty: f.qty,
    date: f.date,
    time: f.time,
  };
}

/** 單筆成交 → `RawFill`,不合條件回 null。
 *
 *  `excludeUnit`:現股(單檔頁現貨態 + 群組卡)傳 `"股"` 排零股 —— 與現股梯同口徑(AD-3)。
 *  日期界 = **今日**(逐筆自帶真實到達日;後端本來只回當日,這裡是防禦性再過濾 ——
 *  近似版「昨日活單」那半條連同它的殘餘風險一起退役)。 */
function rawFill(f: CapitalFill, todayYmd: string, excludeUnit?: string): RawFill | null {
  const b = baseFill(f, excludeUnit);
  if (b === null) return null;
  if (b.date !== todayYmd) return null;
  return { code: b.code, minute: minuteKey(b.time), priceMilli: b.priceMilli, side: b.side, qty: b.qty };
}

/** 同 (分鐘, 側, **價位**) 無損合併(qty 相加)→ minute 升冪(同分鐘 B 先 S 後、同側價升冪)。
 *
 *  精確版不做量加權(AD-4 退役):逐筆自帶真實價,不同價各自一點才是「每筆一標記」;
 *  完全同點的多筆合併只是去掉重疊的三角,資訊零損。 */
function aggregate(raws: readonly RawFill[]): readonly FillPoint[] {
  if (raws.length === 0) return EMPTY_FILLS;
  const buckets = new Map<string, FillPoint>();
  for (const r of raws) {
    const k = `${r.minute}|${r.side}|${r.priceMilli}`;
    const cur = buckets.get(k);
    if (cur === undefined) {
      buckets.set(k, { minute: r.minute, side: r.side, priceMilli: r.priceMilli, qty: r.qty });
    } else {
      cur.qty += r.qty;
    }
  }
  return [...buckets.values()].sort(
    (a, b) =>
      a.minute - b.minute ||
      (a.side === b.side ? 0 : a.side === "B" ? -1 : 1) ||
      a.priceMilli - b.priceMilli,
  );
}

/** 群益回報的 `date`(`YYYYMMDD`)+ `time`(`HH:MM:SS`)→ 近全軸兩支 helper 各自要的輸入形:
 *  `stamp` = `YYYY-MM-DD HH:MM`(`anchorDateOf` 吃的)、`hhmm` = `HHMM`(`alldayIndexOf` 吃的)。
 *
 *  兩個字串**同源一次切完**:分開在呼叫端各切各的話,漂掉的樣態是「日期界用了 A 的分鐘、
 *  軸索引用了 B 的分鐘」—— 成交點畫在別的分鐘上,而兩邊的切法都自己看起來對。 */
function splitCapitalStamp(date: string, time: string): { stamp: string; hhmm: string } {
  const hm = time.slice(0, 5); // HH:MM
  return {
    stamp: `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)} ${hm}`,
    hhmm: `${hm.slice(0, 2)}${hm.slice(3, 5)}`,
  };
}

/** 單一比對鍵(股號 / 期交所契約碼)的成交點。
 *
 *  `key === null` 直接回 `EMPTY_FILLS`(同 `aggregateLots` 的 guard)—— 個股期合約 ym
 *  解不出來時 caller 拿到的就是 null,拿它去比對會對到 `stock_no` 同樣是 null 的單。 */
export function fillPoints(
  fills: readonly CapitalFill[] | undefined,
  key: string | null,
  todayYmd: string,
  excludeUnit?: string,
): readonly FillPoint[] {
  if (key === null) return EMPTY_FILLS;
  const raws: RawFill[] = [];
  for (const f of fills ?? []) {
    if (f.stock_no !== key) continue;
    const r = rawFill(f, todayYmd, excludeUnit);
    if (r !== null) raws.push(r);
  }
  return aggregate(raws);
}

/** 近全軸(期貨分時)的成交點(N043/N070)。回傳的 `minute` 是**近全軸索引**不是分鐘數
 *  —— 與 `futuresBarsToAccum` 的 key 同一套(core 的幾何對 key 只要求「窗內整數、可排序」)。
 *
 *  **日期界換成「錨定日相等」**,不沿用 `fillPoints` 的「今日 ∨ 昨日活單」:近全軸一格圖
 *  橫跨兩個日曆日(D−1 15:01 → D 13:45;15:00 起算,mod/futures-day-1500),日曆日界在這裡
 *  兩頭都錯 —— 昨夜 22:00 的成交(日曆日 = D−1)本來就屬於 D 這張圖,而 D 15:01 起的成交屬
 *  次一交易日、不該畫在 D 上。錨定日的推導走與 slice / live gate 同一支 `anchorDateOf`
 *  (三處各算一份必漂移)。
 *
 *  空檔(05:01–08:45)/ 一天之外(13:46–15:00)的成交 → `alldayIndexOf` 回 null → **不畫**,
 *  不夾到最近的段界:夾了就是把成交時間講錯(同 `projectFills` 窗外不畫的既有規則)。
 *
 *  `anchorDate` = `YYYY-MM-DD`,由 caller 以圖上最後一根 bar 反推(`anchorDateOf(last.t)`);
 *  `holidays` = caller 算 `anchorDate` 用的**同一份**假日集合(選配;缺 = 模組集合)—— 兩邊不同源時
 *  假日前夜盤的成交會被判成別天而整場不畫。 */
export function alldayFillPoints(
  fills: readonly CapitalFill[] | undefined,
  key: string | null,
  anchorDate: string,
  holidays?: ReadonlySet<string>,
): readonly FillPoint[] {
  if (key === null) return EMPTY_FILLS;
  const raws: RawFill[] = [];
  for (const f of fills ?? []) {
    if (f.stock_no !== key) continue;
    const b = baseFill(f);
    if (b === null) continue;
    const { stamp, hhmm } = splitCapitalStamp(b.date, b.time);
    if (anchorDateOf(stamp, holidays) !== anchorDate) continue;
    const index = alldayIndexOf(hhmm);
    if (index === null) continue;
    raws.push({ code: b.code, minute: index, priceMilli: b.priceMilli, side: b.side, qty: b.qty });
  }
  return aggregate(raws);
}

/** 群組圖牆用:一次折完所有 code(圖牆層算一份,每卡只取自己那個 key)。
 *
 *  零筆的 code **不入 map**,caller 以 `?? EMPTY_FILLS` 補 —— 無成交的卡拿到的永遠是
 *  同一個 identity,`GroupCard` 的 memo 不被打穿(W-5)。
 *  分組鍵 = wire `code`(個股期契約碼已反查成股號,L444:個股期成交落到該股的卡);
 *  `excludeUnit="股"` 由 caller 傳 = 排零股(現股口徑)。
 *  已接受的設計代價(pr-167 #21):單檔頁現貨態刻意**不撿**同一筆個股期成交(那邊的
 *  比對鍵是 `stock_no`)—— 圖牆看得到、點進去看不到;卡上期貨價與現貨價的三角同形
 *  無區辨。 */
export function fillsByCode(
  fills: readonly CapitalFill[] | undefined,
  todayYmd: string,
  excludeUnit?: string,
): Map<string, readonly FillPoint[]> {
  const buckets = new Map<string, RawFill[]>();
  for (const f of fills ?? []) {
    const r = rawFill(f, todayYmd, excludeUnit);
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
