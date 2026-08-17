/** 江波圖幾何純函數(零 React 依賴;design v4 §3 + stock-ui-upgrade SC-1..4)。

Y 域(stock-ui-round2 SC-4):有漲跌停 → **域恰為 [lower, upper]**(不再多留 2% 邊);
缺 → 對稱 autofit(以參考價置中,無漲跌幅商品 fallback,白名單 11 不動)。
上下不被裁掉半條 stroke 靠的是 `PAD_Y` 幾何留邊 —— 那是**像素留邊不是價格域放寬**,
所以漲停時走勢線確實貼在最上面那條刻度上。

`toY` 與 `priceAtY` 必須共用同一組 `PAD_Y` / `X_LABEL_H`:兩者各自硬編過一次的話,
反演在域中央仍剛好正確、只在兩端偏移(實測 ±0.3% / ±1.4%),目視幾乎抓不到。

VWAP 線由分鐘序列 running 近似(Σ close×vol / Σ vol),與後端逐筆 VWAP 誤差
在分鐘粒度內可忽略。 */

import type { MinuteAgg, StockMeta } from "@/lib/stock-accum";
import { snapDown } from "@/lib/stock-tick";

export const X_START_MIN = 9 * 60; // 09:00
export const X_END_MIN = 13 * 60 + 30; // 13:30

/** x 軸的分鐘窗(兩端皆含)。
 *
 *  幾何層原本把 `[X_START_MIN, X_END_MIN]` 當成全域事實硬編在五個地方(minuteToX /
 *  minuteOf / windowedEntries / sideSummary / 元件 barW 分母)。同一張圖要換窗時,
 *  漏改任何一處的失效樣態都是「圖畫得出來、只是對不齊」——線與整點刻度差幾 px、
 *  bar 寬與分鐘間距不等、反演回來的分鐘偏移一格,沒有任何 assertion 會紅。
 *  所以窗一律當**參數**沿呼叫鏈傳,不再由各處各自 import 常數。 */
export interface XWindow {
  start: number;
  end: number;
}

/** 現貨日盤窗 09:00–13:30。所有窗參數的預設值 = 既有語意,呼叫端不傳即零行為改變。 */
export const SPOT_WINDOW: XWindow = { start: X_START_MIN, end: X_END_MIN };

/** 個股期日盤窗 08:45–13:45(期交所股票期貨交易時段;比現貨兩端各長一截)。
 *
 *  **模組層常數不是行內字面值**:窗物件會直接進 `memo` 子元件的 props,行內 `{...}`
 *  每次 render 都是新 identity,靜態圖層(ChartStatic / EnergySub)的 memo 會被整層打穿。 */
export const STKFUT_WINDOW: XWindow = { start: 8 * 60 + 45, end: 13 * 60 + 45 };

/** 底部時間標籤帶;繪圖區 = [PAD_Y, height − X_LABEL_H − PAD_Y] */
export const X_LABEL_H = 14;
export const PAD_Y = 4;

/** 內外盤副圖頂端預留(SC-8):量刻度文字畫在這裡。不留的話最大那根 bar 高度恰等於
 *  副圖全高,頂端刻度必被蓋住。 */
export const SUB_TOP_PAD = 10;

/** 左緣刻度的百分比階(SC-4:由上而下)。±10 直接用 upper/lower 原值、0 用 ref 原值。 */
const TICK_PCTS = [10, 8, 6, 4, 2, 0, -2, -4, -6, -8, -10] as const;

/** 左緣價位帶寬度(round4 項 3 讓出、項 6 內縮)。價位文字原本畫在 `x=2` 而繪圖區從
 *  `x=0` 起,文字直接壓在走勢線與紅綠填色上。讓出這條帶後繪圖區改為 `[Y_AXIS_W, width]`。
 *
 *  **36(round4 項 6:原 46)**。「離走勢圖太遠」的根因是**左對齊**不是帶寬 ——
 *  `123.5` 從 x=2 起排,右緣落在 ~27,離繪圖區還有 19px;兩位數更遠,而且數字長度不同
 *  時右緣參差。改成右對齊(`x = Y_AXIS_W − 4`、`textAnchor="end"`)後所有刻度一律距
 *  繪圖區 4px 且對齊成一欄,帶寬才有內縮的餘裕。
 *
 *  仍與元件的 `PRICE_TAG.w` 綁定:hover 價位標(左上角固定在 x=0)要整格塞進帶內。
 *  最寬內容是 `snapDown` 後的合法檔位(≥1000 元級距 5 元 → 4 位整數;最長是
 *  100–500 元帶的 `412.5`)@0.5625rem ≈ 25px,36 寬左右各留 4~5px。 */
export const Y_AXIS_W = 36;

/** 右緣疊線標籤帶寬度(round5 D)。CDP/MA 的價位標原本畫在 `x = width − 32`,而繪圖區
 *  一路到 `width` —— 標籤直接疊在走勢線上,與左緣價位帶當初的症狀是同一個。
 *
 *  取 40:最寬的標籤是四位數價位加 `*`(例 `1005.0*`,~34px),留 6px 呼吸。 */
export const R_AXIS_W = 40;

/** 繪圖區寬度(扣掉左右兩條軸帶);至少 1 避免除以零。 */
export function plotWidth(width: number): number {
  return Math.max(1, width - Y_AXIS_W - R_AXIS_W);
}

/** 分鐘 → x 座標。**幾何與元件共用這一份** —— 兩邊各寫一次的話,任何 x 軸幾何改動
 *  都得同時改對兩處,而漂移的症狀是「線與刻度差幾 px」,目視幾乎抓不到
 *  (同 `toY` / `priceAtY` 必須共用 `PAD_Y` 的理由)。 */
export function minuteToX(minute: number, width: number, xw: XWindow = SPOT_WINDOW): number {
  return Y_AXIS_W + ((minute - xw.start) / (xw.end - xw.start)) * plotWidth(width);
}

export interface Pt {
  x: number;
  y: number;
}

/** 成交量副圖的一根 bar(round6c:由「內外盤堆疊」改回**單純的量**)。
 *
 *  堆疊版曾把每分鐘拆成 外盤紅 / 內盤綠 / 未分類灰 三段。灰段是 user 連兩輪反映的痛點:
 *  它在圖表語彙裡看起來像「第三種方向」,而它其實是「判不出方向」。round6 先修了後端
 *  判定的根因、又把灰段改成斜線紋理,user 仍然覺得多餘 —— 拍板「不要分顏色,單純顯示量」。
 *
 *  內外盤的統計沒有消失,只是移出圖形語彙:說明列仍印 外盤 / 內盤 / 未分類 / 外盤比 /
 *  判定率(見 `sideSummary`)。**用文字承載會誤讀的資訊,用圖形承載一眼要懂的資訊。** */
export interface EnergyBar {
  /** 該分鐘的中心 x(= 走勢線頂點與十字線的 x);bar 由元件以此為中心左右各畫半根 */
  x: number;
  /** 依全日最大總量(外 + 內 + 未分類)正規化後的高度 */
  h: number;
}

export interface YTick {
  y: number;
  priceMilli: number;
  /** 這一格恰好是漲停 / 跌停價(round6 項 5:左緣要亮燈)。其餘格為 undefined。
   *
   *  **判定必須與 y 域的分支條件對齊**(`upper !== null && lower !== null`,不含 `ref > 0`)
   *  —— 刻度有兩條分支(11 點 / 3 點 fallback),但兩條的 yTop / yBottom 在有漲跌停時
   *  **都是** upper / lower。把 kind 綁在 11 點那條上的話,「有漲跌停但 ref 不可得」
   *  會畫出漲跌停價卻不亮燈。所以這裡採「與 upper/lower 比值」的統一後處理,不分支。 */
  kind?: "upper" | "lower";
}

/** 當日極值標記(round4 項 1)。位置 = 摸到該價位的那一分鐘,值 = tick 級極值本身。 */
export interface ExtremeMark {
  x: number;
  y: number;
  priceMilli: number;
}

export interface IntradayGeometry {
  priceLine: (Pt & { minute: number })[];
  vwapLine: (Pt & { vwap: number })[];
  refY: number;
  /** meta 真的有昨收(不是拿首筆成交當 fallback)。false → 無「平盤」可言,
   *  走勢線走單色、不填色(SC-2.4) */
  hasRef: boolean;
  /** 走勢線與平盤之間的封閉多邊形點串;`hasRef` 為 false 或無資料時為空字串 */
  areaPolygon: string;
  yDomain: [number, number]; // 毫元
  yTicks: YTick[];
  /** 當日高 / 低的標記(round4 項 1);域外、反查落空、缺 per-minute h/l 一律 null = 不畫 */
  highMark: ExtremeMark | null;
  lowMark: ExtremeMark | null;
  energyBars: EnergyBar[];
  /** 歸一分母 = 全日最大**總量**(外+內+未分類),即副圖頂端刻度值。
   *  round5 E 之前是「單邊最大」,那讓資訊列的「量」在副圖上找不到對應高度。 */
  maxTotal: number;
  /** 價格 → y 座標(overlay 線共用同一縮放) */
  toY: (priceMilli: number) => number;
  /** y 座標 → 價格(`toY` 的逆函數);回傳前夾制進 yDomain */
  priceAtY: (y: number) => number;
  /** X 座標反演到分鐘 bucket;bucket 無資料 → null(SC-1/R6,不 snap 最近) */
  minuteOf: (xPx: number) => number | null;
}

/** 判定率低於這個門檻時,**判定率本身**在畫面上標警示色(不是暗化外盤比,見下)。
 *  外盤比的分母排除了未分類量,判定率一低就等於「這個百分比是用不到一半的資料算出來的」。
 *
 *  **75 的由來(2026-07-31 user 拍板,原值 60)**:併上當日兩批樣本後分佈是**雙峰** ——
 *  正常群 83.7 / 98 / 100 / 100,劣化群 51 / 64。60 落在**劣化群內部**,結果 4989
 *  (未分類 1500 / 總量 4132,逾三分之一被排除在分母外)被顯示成完全可信。
 *  最大間隔在 64 與 83.7 之間(切點約 74),取 75 讓兩側各留約 11 點餘裕。
 *
 *  樣本 —— **盤中**(鎖停修法前):2330 100% / 2317 鴻海 83.7% / 6207 雷科 52% /
 *  4989 榮科 50.8% / 2327 國巨(鎖漲停)**0%**;**盤後**重量:2327 **100%** / 2330 98% /
 *  4989 **64%** / 6207 51%。
 *
 *  ⚠ 那個 **2327 = 0% 已被 round6 的修法作廢**,不可再拿來推導門檻 ——
 *  `relabel_locked_side` + `_best_limit_price` 正是為了消滅它。
 *  ⚠ 4989 盤中 50.8% → 盤後 64%:判定率會隨盤中累積而漂,跨過門檻會讓標示翻面。
 *  ⚠ 樣本僅 6 檔、單一交易日、集中在近漲停股 —— 那個「間隔」可能是抽樣假象。
 *  若平常日出現大量判定率 70% 左右的普通股被標成可疑,回頭重估這個值。 */
export const LOW_DECIDED_PCT = 75;

export interface SideSummary {
  outer: number;
  inner: number;
  unch: number;
  /** 外盤比 = 外 /(外 + 內)。**分母刻意排除未分類**(既有語意,不在本輪改);
   *  分母為 0 → `null` 而不是 0 —— `0%` 會被讀成「全部內盤」。 */
  outerPct: number | null;
  /** 判定率 = (外 + 內)/ 總量。回答「上面那個外盤比是用多少比例的資料算的」。 */
  decidedPct: number | null;
}

/** 說明列四個數字的**唯一**來源(round6 項 2)。
 *
 *  舊版說明列的「累積外盤 / 內盤」取自後端 running 值 `cumOuter` / `cumInner`,而未分類量
 *  根本沒印。要補「未分類 N」就必須從分鐘聚合算,那時若外 / 內仍走後端值,就會出現
 *  兩個來源混用 —— 而混用的失效樣態是純數字不一致,沒有任何測試會紅。
 *
 *  **窗與副圖一致**(現貨 [09:00, 13:30]):這個數字的全部意義就是與畫面上的灰段總和
 *  對得上,所以窗必須與 `windowedEntries` 吃同一個 `xw`,不可各自 import 常數。 */
export function sideSummary(
  minutes: Map<number, MinuteAgg>,
  xw: XWindow = SPOT_WINDOW,
): SideSummary {
  let outer = 0;
  let inner = 0;
  let unch = 0;
  for (const [k, m] of minutes) {
    if (k < xw.start || k > xw.end) continue;
    outer += m.o;
    inner += m.i;
    unch += m.u;
  }
  const decided = outer + inner;
  const total = decided + unch;
  return {
    outer,
    inner,
    unch,
    outerPct: decided > 0 ? (outer / decided) * 100 : null,
    decidedPct: total > 0 ? (decided / total) * 100 : null,
  };
}

export interface StockOverlay {
  cdp: { cdp: number; ah: number; nh: number; nl: number; al: number } | null;
  ma5: number | null;
  ma20: number | null;
  date: string | null;
}

/** 疊線種類。`label` 字串已移除(round3 SC-2:右緣改印價位)—— 名稱語意留在 `level`,
 *  顯示文字由元件用 `priceMilli` 現算,判色 / React key 也一律走 `level` 不走文字。 */
export type OverlayLevel = "ah" | "nh" | "cdp" | "nl" | "al" | "ma5" | "ma20";

export interface OverlayLine {
  y: number;
  priceMilli: number;
  level: OverlayLevel;
}

/** 疊線配色(SC-2)。名稱從右緣移除後,五條 CDP 只剩顏色可分辨 ——
 *  上方壓力位紅、下方支撐位綠(台股紅漲綠跌),中軸取琥珀金不與紅綠系混淆。
 *
 *  **住在 lib 而非某張圖的元件檔**:個股分時圖與指數分時圖畫的是同一組 CDP/MA 語意,
 *  兩邊各留一份的失效樣態是「改了個股的紅、指數還是舊紅」——沒有 assertion 會紅。 */
export const LEVEL_STROKE: Record<OverlayLevel, string> = {
  ah: "stroke-bull",
  nh: "stroke-bull/55",
  cdp: "stroke-profit",
  nl: "stroke-bear/55",
  al: "stroke-bear",
  ma5: "stroke-ma5",
  ma20: "stroke-ma20",
};

export const LEVEL_FILL: Record<OverlayLevel, string> = {
  ah: "fill-bull",
  nh: "fill-bull/70",
  cdp: "fill-profit",
  nl: "fill-bear/70",
  al: "fill-bear",
  ma5: "fill-ma5",
  ma20: "fill-ma20",
};

interface Input {
  minutes: Map<number, MinuteAgg>;
  meta: StockMeta | null;
  /** 當日 tick 級高 / 低(後端 running max/min)。未傳 → 不畫標記。 */
  high?: number | null;
  low?: number | null;
}

interface Size {
  width: number;
  height: number;
}

function windowedEntries(minutes: Map<number, MinuteAgg>, xw: XWindow): [number, MinuteAgg][] {
  return [...minutes.entries()]
    .filter(([k]) => k >= xw.start && k <= xw.end)
    .sort(([a], [b]) => a - b);
}

/** 窗內是否有可畫的分鐘(change-spec edge 9)。
 *
 *  **窗的定義與 `windowedEntries` 同一組 `xw`**,不讓呼叫端自己比 `minutes.size`:
 *  各寫一次的失效樣態是「盤前只有 08:59 的檔在卡片上掛一張空圖」——
 *  `size > 0` 為真而 `priceLine` 為空,畫面上是一張有軸沒線的圖,沒有錯誤訊號。
 *
 *  只問「有沒有」就別建整份陣列(review B3):圖牆最多 50 張卡、每秒隨報價
 *  re-render 各問一次,而 `windowedEntries` 會拷貝 + 排序當日最多 271 格。
 *  第一格命中就退出 —— 盤中常態是第一個 key 就在窗內。 */
export function hasWindowedMinutes(
  minutes: Map<number, MinuteAgg>,
  xw: XWindow = SPOT_WINDOW,
): boolean {
  for (const k of minutes.keys()) {
    if (k >= xw.start && k <= xw.end) return true;
  }
  return false;
}

function energyFrom(
  entries: readonly [number, MinuteAgg][],
  size: Size,
  xw: XWindow,
): { bars: EnergyBar[]; maxTotal: number } {
  // round5 E:分母是**全日最大總量**(外+內+未分類)而不是舊的「單邊最大」。
  // 舊分母讓資訊列的「量」在副圖上找不到對應高度 —— 未分類(開盤集合競價沒有 Bid/Ask
  // 可比,derive_side 判 neutral)整批不畫,而刻度又是單邊值。實測截圖 09:00:
  // 量 269 = 外 127 + 內 20 + 未分類 122,舊刻度顯示 164。
  const maxTotal = Math.max(1, ...entries.map(([, m]) => m.o + m.i + m.u));
  // 分母扣掉 SUB_TOP_PAD:滿格那根不再頂到副圖上緣,頂端量刻度文字才有地方站(SC-8)
  const energyH = Math.max(1, size.height - SUB_TOP_PAD);
  const bars = entries.map(([minute, m]) => {
    const total = m.o + m.i + m.u;
    return { x: minuteToX(minute, size.width, xw), h: (total / maxTotal) * energyH };
  });
  return { bars, maxTotal };
}

/** 副圖(成交量)專用幾何。**副圖只吃 bar 與歸一分母**,原本卻整份跑一次
 *  `buildIntradayGeometry` —— 價線 / VWAP / 刻度 / 極值反查全算一遍再丟掉。
 *  與主圖共用 `energyFrom`,兩邊的 bar 定義不可能各漂各的。 */
export function buildEnergyBars(
  minutes: Map<number, MinuteAgg>,
  size: { width: number; height: number },
  xw: XWindow = SPOT_WINDOW,
): { bars: EnergyBar[]; maxTotal: number } {
  return energyFrom(windowedEntries(minutes, xw), size, xw);
}

export function buildIntradayGeometry(
  input: Input,
  size: Size,
  xw: XWindow = SPOT_WINDOW,
): IntradayGeometry {
  const entries = windowedEntries(input.minutes, xw);
  const prices = entries.map(([, m]) => m.c).filter((p) => p > 0);
  // **幾何入口統一歸一**:TC4 會送 "0",後端 `to_milli_units` 原樣轉成 0 而不是 None,
  // 三欄多半同時為 0。毫元價格恆 > 0,所以 0 只可能是「不可得」——
  // 不在這裡收乾淨的話它會同時打穿三處而且全部靜默:y 域走
  // `upper !== null && lower !== null` 分支得到退化的 [0,0](flat 常數 toY)、
  // yTicks 的 `ref > 0` 退化成 3 格 fallback 且印出假價位 0、判色一律恆 bull。
  // 歸一成 null 之後,既有的「缺漲跌停 → autofit」「無 ref → 不填色」分支自然接手。
  const norm = (v: number | null | undefined): number | null => ((v ?? 0) > 0 ? v! : null);
  const metaRef = norm(input.meta?.ref);
  const ref = metaRef ?? (prices.length ? prices[0]! : 0);
  const upper = norm(input.meta?.upper);
  const lower = norm(input.meta?.lower);
  // 當日極值同走 norm:0 = 不可得。**危險方向是 low**(`Math.min` 會把 0 吃進域讓
  // 下緣變負、整圖壓扁;high = 0 被 `Math.max` 自然忽略)。原本 0 是靠「yBottom > 0」
  // 間接擋下的,而本輪動的正是決定 yBottom 的那條路,不能再依賴它。
  const dayHigh = norm(input.high);
  const dayLow = norm(input.low);

  let yTop: number;
  let yBottom: number;
  if (upper !== null && lower !== null) {
    // 漲跌停域(SC-4):域**恰為**漲跌停,不留 2% 邊。上下緣的呼吸空間改由 PAD_Y 出。
    yTop = upper;
    yBottom = lower;
  } else {
    // 對稱域 fallback:以 ref 為中心,半幅 = max 偏離 × 1.1(最少 1% 防平線貼邊)。
    // 半幅池含當日高低:只看每分鐘**收盤**的話,長上下影就會被域裁掉,而症狀是
    // 高低標記靜默消失(2330 2026-07-30 盤後域 [2160.5, 2259.5],當日高 2260.0 差 0.5 元)。
    // 但 `ref > 0` 是前提:ref = 0 表示 meta 沒 ref **且**收盤全被濾光,對稱域沒有中心
    // 可言(退化成 [−1, 1])—— 這時把極值併進來只是放大垃圾,域變 [−1.1×high, 1.1×high],
    // 3 點 fallback 印出負價位刻度、標記還畫在錯位的 y 上。ref = 0 一律維持退化域。
    const foldExtremes = ref > 0;
    const hi = Math.max(ref, ...prices, ...(foldExtremes && dayHigh !== null ? [dayHigh] : []));
    const lo = Math.min(ref, ...prices, ...(foldExtremes && dayLow !== null ? [dayLow] : []));
    const half = Math.max(hi - ref, ref - lo, ref * 0.01) * 1.1 || 1;
    yTop = ref + half;
    yBottom = ref - half;
  }
  // 繪圖區高度(扣掉底部時間帶與上下留邊);至少 1 避免除以零
  const plotH = Math.max(1, size.height - X_LABEL_H - PAD_Y * 2);
  // 退化域(upper === lower)必須把 toY 也特判成常數,不能只靠 `|| 1` 擋除以零 ——
  // 那只讓分母合法,toY 仍是無界線性函數:域寬 1 毫元時差 10 毫元就算出 10×plotH 的座標,
  // 直接飛出畫布數百 px;而 priceAtY 有 clamp 會收斂成常數,兩者就不再互逆。
  const ySpan = yTop - yBottom;
  const flat = ySpan <= 0;
  const toY = (p: number): number =>
    flat ? PAD_Y + plotH / 2 : PAD_Y + ((yTop - p) / ySpan) * plotH;
  const priceAtY = (y: number): number => {
    if (flat) return yTop;
    const raw = yTop - ((y - PAD_Y) / plotH) * ySpan;
    return Math.min(yTop, Math.max(yBottom, Math.round(raw)));
  };
  const toX = (minute: number): number => minuteToX(minute, size.width, xw);

  const priceLine = entries.map(([minute, m]) => ({ minute, x: toX(minute), y: toY(m.c) }));

  const vwapLine: (Pt & { vwap: number })[] = [];
  let amount = 0;
  let volume = 0;
  for (const [minute, m] of entries) {
    amount += m.c * m.v;
    volume += m.v;
    if (volume > 0) {
      const vwap = Math.round(amount / volume);
      vwapLine.push({ x: toX(minute), y: toY(vwap), vwap });
    }
  }

  const { bars: energyBars, maxTotal } = energyFrom(entries, size, xw);

  const yTicks: YTick[] = [];
  if (upper !== null && lower !== null && ref > 0) {
    // SC-4:由上而下 +10/+8/…/0/…/−8/−10%。端點與中央用原值,其餘 snap 到合法 tick。
    // 去重:低價股 tick 粗時相鄰檔位會 snap 到同價,重複的 priceMilli 會撞 React key。
    const seen = new Set<number>();
    for (const pct of TICK_PCTS) {
      const p =
        pct === 10 ? upper : pct === -10 ? lower : pct === 0 ? ref : snapDown(Math.round(ref * (1 + pct / 100)));
      // 域外的中間刻度直接跳過:±10% 取的是 upper/lower 原值,±2/4/6/8% 卻是拿 ref 獨立
      // 算的,兩者沒互相校驗。漲跌幅不是 ±10% 的商品(槓桿型 ETF ±20%,或任何比 ±10% 窄的)
      // 會讓公式算出的刻度落在 [lower, upper] 之外 → toY 變負、刻度視覺次序反轉。
      if (p < yBottom || p > yTop) continue;
      if (seen.has(p)) continue;
      seen.add(p);
      yTicks.push({ y: toY(p), priceMilli: p });
    }
  } else {
    for (const p of [yTop, ref, yBottom]) {
      yTicks.push({ y: toY(p), priceMilli: Math.round(p) });
    }
  }
  // 漲跌停亮燈的判定(round6 項 5):統一後處理,不綁在上面任何一條分支上(見 YTick.kind)。
  // upper / lower 不可得 → 一格都不標 = 不亮(SC-5.5:沒有漲跌停可言就不猜)。
  if (upper !== null && lower !== null) {
    for (const t of yTicks) {
      // upper 先判:退化商品(upper === lower)時只認一邊,不讓同一格同時是漲停又是跌停
      if (t.priceMilli === upper) t.kind = "upper";
      else if (t.priceMilli === lower) t.kind = "lower";
    }
  }

  const haveMinutes = new Set(entries.map(([k]) => k));
  const minuteOf = (xPx: number): number | null => {
    // 價位帶內(x < Y_AXIS_W)不對應任何分鐘 —— 不夾制成 09:00,否則滑過左緣價位文字時
    // 十字線會憑空指到開盤那一分鐘。必須與 `minuteToX` 共用 Y_AXIS_W / plotWidth,
    // 各自硬編會讓反演只在兩端偏移(同 toY / priceAtY 的教訓)。
    // 上界用 `Y_AXIS_W + plotWidth(width)` 不是 `width`:正常寬度下兩者相等,但退化寬度
    // (width ≤ Y_AXIS_W,plotWidth 被 clamp 成 1)時 minuteToX 最大會回 Y_AXIS_W + 1
    // 而超過 width,用 width 當上界就會把自己算出來的座標判成域外 → 兩者不再互逆。
    if (xPx < Y_AXIS_W || xPx > Y_AXIS_W + plotWidth(size.width)) return null;
    const m =
      Math.round(((xPx - Y_AXIS_W) / plotWidth(size.width)) * (xw.end - xw.start)) + xw.start;
    return haveMinutes.has(m) ? m : null;
  };

  // 「真的有昨收」才有平盤可言 —— ref 的 fallback 是首筆成交價,拿它當平盤畫紅綠填色
  // 會把「開盤後漲跌」誤指為「相對昨收漲跌」(SC-2.4)。
  const hasRef = metaRef !== null;
  const refY = toY(ref);
  // 這裡的點串是行內展開版(頭尾各補一個 refY 錨點,不是純 line.map),
  // 精度必須與 lib/svg-points.ts 的 pts() 一致(皆 toFixed(1))。
  const areaPolygon =
    hasRef && priceLine.length > 0
      ? [
          `${priceLine[0]!.x.toFixed(1)},${refY.toFixed(1)}`,
          ...priceLine.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`),
          `${priceLine[priceLine.length - 1]!.x.toFixed(1)},${refY.toFixed(1)}`,
        ].join(" ")
      : "";

  // 當日高低標記(round4 項 1)。**等值反查**:找出 per-minute h(或 l)恰等於當日極值的
  // 那一分鐘,取它的 x。反查落空一律回 null(不畫)而不是退而求其次挑「收盤最接近的分鐘」——
  // 位置錯就是資料錯,而且完全靜默。落空的三種成因(域外 / 無等值分鐘 / 舊後端缺 h,l)
  // 都收斂到同一個安全結果。
  const markFor = (target: number | null | undefined, pick: "h" | "l"): ExtremeMark | null => {
    if (target == null) return null;
    if (target < yBottom || target > yTop) return null; // 域外不畫(既有規則)
    const hit = entries.find(([, m]) => (pick === "h" ? m.h : m.l) === target);
    return hit === undefined ? null : { x: toX(hit[0]), y: toY(target), priceMilli: target };
  };
  // 吃 norm 後的值:域計算與標記對 high/low 的解讀必須是同一套「0 = 不可得」,
  // 兩邊各判各的話,0 會進得了域卻進不了標記(或反過來)而完全靜默。
  const highMark = markFor(dayHigh, "h");
  // 高 === 低(漲停鎖死 / 一字盤)時兩個標記會疊在同一點變成看不懂的黑塊 → 只留高標
  const lowMark = dayLow !== null && dayLow === dayHigh ? null : markFor(dayLow, "l");

  return {
    priceLine,
    vwapLine,
    refY,
    hasRef,
    areaPolygon,
    highMark,
    lowMark,
    yDomain: [yBottom, yTop],
    yTicks,
    energyBars,
    maxTotal,
    toY,
    priceAtY,
    minuteOf,
  };
}

/** 走勢線末點 = 現價圈的落點(也是資訊列「最新分鐘」的來源);空線 → null(SC-2)。 */
export function lastPoint(g: IntradayGeometry): (Pt & { minute: number }) | null {
  return g.priceLine[g.priceLine.length - 1] ?? null;
}

/** overlay(CDP/MA)→ 域內水平線;toggle 關的類別不給(SC-4)。
 *
 *  第二參數刻意收窄成 `Pick<IntradayGeometry, "yDomain" | "toY">`(函式體只用這兩欄):
 *  指數分時圖的 `IndexGeometry` 帶同名同義的兩欄,結構相容就能共用同一份域內判定,
 *  不必為了型別把整包個股 geometry(vwap / energyBars / 五檔…)硬湊出來。 */
export function overlayLines(
  overlay: StockOverlay,
  g: Pick<IntradayGeometry, "yDomain" | "toY">,
  toggles: { cdp: boolean; ma: boolean },
): OverlayLine[] {
  const [yBottom, yTop] = g.yDomain;
  const lines: OverlayLine[] = [];
  const push = (p: number | null | undefined, level: OverlayLevel): void => {
    if (p == null || p < yBottom || p > yTop) return;
    lines.push({ y: g.toY(p), priceMilli: p, level });
  };
  if (toggles.cdp && overlay.cdp) {
    // 順序 = 由上而下,元件的配色表依賴這個語意(SC-2:名稱移除後靠顏色區分)
    push(overlay.cdp.ah, "ah");
    push(overlay.cdp.nh, "nh");
    push(overlay.cdp.cdp, "cdp");
    push(overlay.cdp.nl, "nl");
    push(overlay.cdp.al, "al");
  }
  if (toggles.ma) {
    push(overlay.ma5, "ma5");
    push(overlay.ma20, "ma20");
  }
  return lines;
}

/** MA 價位標籤的最小**中心距**(不是字高)。字高 @0.5625rem ≈ 9px,再留 1px 呼吸。
 *
 *  文字以 `dy="0.35em"` 置中於 `y`,所以佈局層一律以「中心」為單位算距離 ——
 *  baseline 與中心混用的失效樣態是兩顆標籤看起來仍黏在一起,而數字上「距離夠」。 */
export const EDGE_LABEL_H = 10;

export interface EdgePriceLabel {
  y: number;
  priceMilli: number;
  level: "ma5" | "ma20";
}

/** 域外疊線掛牌的輸入(結構與 `lib/index-chart-svg.ts::OutOfDomainLevel` 逐欄相同)。
 *
 *  **刻意寫成本檔自己的結構型別、不 import 那支**:index-chart-svg 已經 import 本檔的
 *  `EDGE_LABEL_H` / `OverlayLevel`,反向 import 會成環。結構相容 → `outOfDomainLevels()`
 *  的結果可以直接餵進來,不需要任何轉接。 */
export interface PegInput {
  level: OverlayLevel;
  priceMilli: number;
  dir: "up" | "down";
}

export interface PegLabel extends PegInput {
  y: number;
}

/** 域外疊線掛牌的定位(指數分時圖 mode="index")。
 *
 *  y 域是以昨收置中的對稱域,平靜日的 CDP 常態整組落在域外 —— 線體畫不出來,**掛牌
 *  就是唯一的訊號**。所以定位規則簡單且不可被推:向上域外的由 `top` 往下疊、向下域外
 *  的由 `bottom` 往上疊,各自獨立計數(兩個方向共用一個計數器的話,一邊多一顆會把
 *  另一邊整組往中間擠,而擠出來的位置與「在域上/下」的語意無關)。
 *
 *  `edgePriceLabels` 的 MA 標籤反過來要**避開**這裡算出的 y(呼叫端把本函式的結果併進
 *  它的 obstacles):MA 的線本身照畫,標籤只是「這條線在哪」,讓位的成本遠低於掛牌。
 *
 *  矮圖時堆疊會超出界 → 一律 clamp 進界內(疊印可讀性差,但飛出 viewBox 是完全靜默的
 *  不見)。界退化(top > bottom)→ 一顆都不畫,同 `edgePriceLabels` 的紀律。 */
export function pegLabels(
  pegs: readonly PegInput[],
  bounds: { top: number; bottom: number },
): PegLabel[] {
  if (bounds.top > bounds.bottom) return [];
  const clamp = (y: number): number => Math.min(Math.max(y, bounds.top), bounds.bottom);
  // 兩側各自堆疊,**槽位次序都與價位一致**:up 側輸入序已是價位由高到低(`outOfDomainLevels`
  // 的 push 次序 ah→nh→cdp→nl→al→ma5→ma20),第一顆貼上緣、其後往下;down 側同一輸入序
  // 是「較高的先來」,若也照輸入序由下緣往上疊,較高的 NL 會壓在最下、較低的 AL 反而在上
  // (code review C-1)—— 所以 down 側由**該側最後一顆**貼下緣起算,前面的往上排。
  // 只用 push 次序不另做價位排序:兩側都靠 `outOfDomainLevels` 的固定次序,再排一次是第二把尺。
  const downTotal = pegs.filter((p) => p.dir === "down").length;
  let ups = 0;
  let downs = 0;
  const out: PegLabel[] = [];
  for (const p of pegs) {
    const raw =
      p.dir === "up"
        ? bounds.top + ups++ * EDGE_LABEL_H
        : bounds.bottom - (downTotal - 1 - downs++) * EDGE_LABEL_H;
    out.push({ level: p.level, priceMilli: p.priceMilli, dir: p.dir, y: clamp(raw) });
  }
  return out;
}

/** MA5 / MA20 的右緣價位標籤佈局(SC-1/SC-3)。
 *
 *  只管 MA:CDP 五線在右緣帶內已有 `價位*`,VWAP 走**就地標示**(末點右側)不經此函式。
 *
 *  `obstacles` = 已經佔住那條 y 的固定圖元,**單位一律是視覺中心**(review B-1):
 *  呼叫端傳右緣區極值的文字(baseline 先扣 0.35em 正規化)與標記圓(圓心即中心)。
 *  它們**不可動** —— 極值標記承載的是「最高/最低發生在哪一分鐘」,推開它就是改資訊;
 *  能讓位的只有 MA 標籤(它的 y 只是「這條線在哪」,而線本身照畫)。
 *
 *  佈局 = 由上而下掃一遍推開重疊(對 obstacle 一律往下讓,方向固定才決定性),
 *  再由下而上回推處理底部溢出,最後 clamp 進 `bounds`。標籤數 ≤ 2,不需要更聰明的解法。 */
export function edgePriceLabels(
  oLines: readonly OverlayLine[],
  obstacles: readonly number[],
  bounds: { top: number; bottom: number },
): EdgePriceLabel[] {
  const labels: EdgePriceLabel[] = [];
  for (const l of oLines) {
    // level 逐個列舉而不是 `!== cdp 系`:未來多一種 overlay 時,新 level 會**預設不進**
    // 這組標籤(要進就得顯式加),而不是靜默多出一顆沒人設計過位置的文字。
    if (l.level === "ma5" || l.level === "ma20") {
      labels.push({ y: l.y, priceMilli: l.priceMilli, level: l.level });
    }
  }
  if (labels.length === 0) return [];
  // bounds 退化(review B-5):top > bottom 時任何 y 都在界外,clamp 的語意會讓 bottom
  // 勝出、把標籤壓到界外 —— 一律不畫。可達性:svgBox 的 minPx 地板 + 超寬容器會把
  // mainH 壓到 30px 以下。
  if (bounds.top > bounds.bottom) return [];
  // 排序穩定(Array#sort 規範保證):同 y 時維持 oLines 的 ma5 → ma20 順序,
  // 不因浮點比較而讓兩顆標籤在兩次 render 之間互換上下。
  labels.sort((a, b) => a.y - b.y);
  // 空間裝不下全部(review B-5):疊印(兩段數字印在同一 y)比少畫一顆更不可讀。
  // 依 y 排序保留裝得下的前幾顆 —— 決定性,且與最後一道 clamp 的「寧可貼近不裁掉」
  // 分工:那條管的是「裝得下但被 obstacle 擠到界邊」,這條管的是「根本裝不下」。
  const capacity = Math.floor((bounds.bottom - bounds.top) / EDGE_LABEL_H) + 1;
  if (labels.length > capacity) labels.length = capacity;
  const fixed = [...obstacles].sort((a, b) => a - b);

  let floor = bounds.top;
  for (const l of labels) {
    let y = Math.max(l.y, floor);
    // obstacles 由上而下逐一檢查:讓開第一個之後可能撞上第二個,所以不能只查最近的那個
    for (const o of fixed) if (Math.abs(y - o) < EDGE_LABEL_H) y = o + EDGE_LABEL_H;
    l.y = y;
    floor = y + EDGE_LABEL_H;
  }

  // 回推:上面那一輪只會把標籤往下推,推到繪圖區外就等於沒畫。由下而上再走一遍,
  // 讓最下面那顆先回到界內,上面的跟著讓位(對 obstacle 這時改往上讓)。
  let ceil = bounds.bottom;
  for (let i = labels.length - 1; i >= 0; i -= 1) {
    const l = labels[i]!;
    let y = Math.min(l.y, ceil);
    for (let k = fixed.length - 1; k >= 0; k -= 1) {
      const o = fixed[k]!;
      if (Math.abs(y - o) < EDGE_LABEL_H) y = o - EDGE_LABEL_H;
    }
    l.y = y;
    ceil = y - EDGE_LABEL_H;
  }

  // 最後一道:clamp 進界內(裁掉是完全靜默的),再把 clamp 後仍互疊的丟掉、保留排序
  // 在前者(review B-5)—— capacity 截斷管「根本裝不下」,這裡管「裝得下但被 obstacle
  // 擠到界邊」的殘餘重疊;疊印(兩段數字印在同一 y)比少畫一顆更不可讀。
  // 兩輪 sweep 各自維持遞增序、clamp 單調 → 這裡順序仍是由上而下,單趟即可。
  const placed: EdgePriceLabel[] = [];
  for (const l of labels) {
    l.y = Math.min(Math.max(l.y, bounds.top), bounds.bottom);
    const prev = placed[placed.length - 1];
    if (prev === undefined || l.y - prev.y >= EDGE_LABEL_H) placed.push(l);
  }
  return placed;
}
