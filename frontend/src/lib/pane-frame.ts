/** 台股綜合雙圖 pane 的「量測 → viewBox 尺寸」換算(§4.1 CS-1)。
 *
 *  **兩種語彙,別混**:1:1 的 `paneIntradayBox`(分時,2026-08-17)/ `paneCandleBox`
 *  (K 線,2026-08-21)把量到的 px 直接當 viewBox 尺寸 → 縮放比恆 1,字級與排版常數
 *  就是它們字面的大小;等比縮放的 `paneSvgHeight` + `paneUnitScale` 只剩 `OverlayCard`
 *  (viewBox 寬寫死 640)一個讀者,字級得靠補償乘回去。新的圖一律走 1:1。
 *
 *  **為什麼在 lib 而不是 MarketPane 檔內**:這裡全是純函式與常數,與元件同檔會讓
 *  `react-refresh/only-export-components` 每次都報一條(元件檔混非元件 export 會讓
 *  HMR 整檔重載)。專案慣例是「純渲染 / 純算術抽 lib」——`lib/chart-frame.ts::svgBox`
 *  是同型的鄰居(那支是 StockChart 的契約,**不共用**:兩邊的 chrome 組成不同,
 *  合併會讓其中一邊每次改動都要驗另一邊)。 */

import type { Size } from "@/lib/chart-frame";

/** 一種圖模式的「量測 → viewBox 高」換算參數。
 *
 *  - `chromeY`:svg 以外、但**在被量測 wrapper 之內**的垂直用量(px)。
 *  - `insetX`:同上的水平用量(px);svg 實際可用寬 = 容器寬 − 這個值。
 *  - `vbW`:該模式 svg 的 viewBox 寬 —— px 高要換成 viewBox 單位得乘 `vbW / svgW`。 */
export interface PaneFrame {
  chromeY: number;
  insetX: number;
  vbW: number;
}

/** 仍走**等比縮放**的圖模式的 chrome 用量。**逐條列舉不共用一組數字**:各態的 DOM
 *  巢狀深度不同,用同一組會差數十 px —— 症狀是圖比容器高一點點,於是主 grid 出現一條
 *  誰也解釋不了的捲軸。
 *
 *  **每一項都必須是固定高的元素**:會折行的東西在窄 pane 下折成兩行,chromeY 就少算
 *  一行的高度,svg 溢出 figure。折不折得掉由該元素自己保證,不是靠這裡多留餘裕。
 *
 *  **分時態(2026-08-17)與 K 線態(2026-08-21)都不在這張表裡**:兩者改走 1:1 px box
 *  (`paneIntradayBox` / `paneCandleBox`),沒有 viewBox 反解也沒有縮放比可言。留一筆
 *  用不到的條目在這裡,下一個人會以為兩條路都還在,而錯用的症狀是圖高差一個
 *  `vbW / svgW` 倍率、畫面照畫。
 *
 *  剩下的唯一讀者是 overlay:`OverlayCard` 是巢狀 figure —— border 2 + `p-4` 32 +
 *  標題列 20 + svg `mt-2` 8 = 62;水平 border 2 + p-4 32 = 34;viewBox 寬寫死 640。 */
export const PANE_FRAMES: Record<"overlay", PaneFrame> = {
  overlay: { chromeY: 62, insetX: 34, vbW: 640 },
};

/** 分時態 svg 以外、但在被量測 wrapper 之內的垂直用量(px):`IntradayChartCore` 的
 *  頂列(readout + toggle)`h-[1.375rem]` 22 + `mb-1` 4 = 26。
 *
 *  數值與舊自繪版的 toggle 列相同(兩者都是同一組 tailwind class)—— 所以 `MarketPane`
 *  的 figure `min-h-48` 算式不必跟著改。 */
export const INTRADAY_CHROME_Y = 26;

/** K 線態 svg 以外、但在被量測 wrapper 之內的垂直用量(px)。**這個 100 是 W-4 契約的
 *  出處**,拆解:
 *  - `CandleChart` 自身 figure:border 2 + `p-4` 32 + 頂列 `h-[1.375rem]`+`mb-1` 26
 *    + figcaption `h-4`+`mt-1` 20 = **80**
 *  - `MarketChart` 的 meta 列:`h-4` 16 + `mt-1` 4 = **20**
 *
 *  meta 列的 `h-4 truncate` 因此是契約不是裝飾:它原本無高度限制,窄 pane 下最長的
 *  來源字串會折成兩行 → 這裡少算 16 → svg 溢出 figure。
 *
 *  ⚠ **這兩值假設 root font-size = 16px**(chrome 全是 rem:`p-4` / `h-[1.375rem]` /
 *  `h-4` / `mt-1` / `mb-1`;本專案目前無 root 縮放 media query,所以 px 與 rem 一對一)。
 *  日後若加 root 縮放 media query,本兩顆與 `INTRADAY_CHROME_Y` 必須同步改為 rem 反算,
 *  否則 chromeY 少算 → svg 溢出 figure、1:1 破 1–2%。 */
export const CANDLE_CHROME_Y = 100;

/** K 線態的水平用量(px):`CandleChart` figure 的 border 2 + `p-4` 32。與 overlay 同值
 *  是巧合不是共用 —— 兩者各自數自己的框。
 *
 *  ⚠ 同 `CANDLE_CHROME_Y` 的 root = 16px 假設(見上)。 */
export const CANDLE_INSET_X = 34;

/** 1:1 圖的 viewBox 尺寸(分時 / K 線共用)。
 *
 *  **改名自 `IntradayBox`**(2026-08-21 K 線態也走 1:1):留著分時專屬的名字會讓
 *  `paneCandleBox` 的回傳型別看起來是借用別人的。 */
export interface PaneBox {
  /** viewBox 寬 = 量到的 px 寬(1:1) */
  width: number;
  /** viewBox 高 = 可用 px 高(1:1) */
  height: number;
  /** 量測有效與否;false → 呼叫端傳 undefined,由圖走它自己的預設尺寸 */
  usable: boolean;
}

/** 量到的容器尺寸(px)→ 分時圖的 viewBox 尺寸(**1:1,同 `cardSvgBox` 的精神**)。
 *
 *  1:1 的意義:viewBox 寬 = 渲染寬 → 縮放比恆 1 → viewBox 內的 rem 字級在畫面上就是
 *  它字面的大小,與 pane 寬無關。等比縮放版本要靠 `paneUnitScale` 把字級乘回去(WL-3),
 *  而那條補償只補得了字、補不了 `EDGE_LABEL_H` 這種排版常數 —— 群組卡片早已走 1:1,
 *  分時 pane 跟上之後兩邊的圖是同一份像素語彙。
 *
 *  地板 96 與 −2 抗抖動的理由同 `paneSvgHeight`:容器矮到 chrome 都放不下時回 0 / 負高
 *  會畫出一張沒有高度的圖(svg 不報錯,純粹消失);反解後的高恰等於量到的高時,亞像素
 *  進位會讓內容比容器高半格,觸發 ResizeObserver 的「量測 → 設高 → 再量測」迴圈。 */
export function paneIntradayBox(size: Size): PaneBox {
  if (size.width <= 0 || size.height <= 0) return { width: 0, height: 0, usable: false };
  return {
    width: Math.round(size.width),
    height: Math.max(96, Math.floor(size.height - INTRADAY_CHROME_Y) - 2),
    usable: true,
  };
}

/** 量到的容器尺寸(px)→ K 線圖的 viewBox 尺寸(**1:1**,同 `paneIntradayBox` 的精神)。
 *
 *  **為什麼 K 線態 2026-08-21 也退出等比縮放**:縮放比 = `1400 / svgW`,1536 兩欄態的
 *  pane 只有 282px → 比值 0.2 → 字級 0.625rem 只剩 3.0px。字級補償(`paneUnitScale`)
 *  補得了 7 處 `fontSize`,補不了 `PRICE_TAG {56,16}` / `TIME_TAG {48,14}` /
 *  `lib/candle.ts::X_LABEL_H 14` 這些 viewBox 單位的排版常數 —— 那些框在 0.2 倍下只有
 *  11×3px,字放大回去必定撞在一起。1:1 之後三者都是真 px,與分時態是同一份像素語彙。
 *
 *  **寬要扣 `CANDLE_INSET_X`**(分時態不扣):被量測的 wrapper 在 `CandleChart` 的
 *  figure **之外**,svg 實際渲染寬 = 容器寬 − figure 的 border + padding。少扣的症狀是
 *  viewBox 比渲染寬大 34px → 又變回等比縮放(比值 0.9),只是這次沒人看得出來。
 *
 *  寬取 `Math.round`:1:1 容許 ±0.5px 取整誤差(≈ 0.2% 縮放,三檔真環境實測 viewBox
 *  寬 = clientWidth 逐值相等)。
 *
 *  地板 96 與 −2 抗抖動的理由同 `paneIntradayBox`。任一邊 ≤ 0 或扣完寬 ≤ 0(pane 窄到
 *  只剩框)→ `usable: false`,呼叫端傳 undefined 而不是傳 0(svg 不報錯,純粹消失)。 */
export function paneCandleBox(size: Size): PaneBox {
  if (size.width <= 0 || size.height <= 0) return { width: 0, height: 0, usable: false };
  const svgW = Math.round(size.width - CANDLE_INSET_X);
  if (svgW <= 0) return { width: 0, height: 0, usable: false };
  return {
    width: svgW,
    height: Math.max(96, Math.floor(size.height - CANDLE_CHROME_Y) - 2),
    usable: true,
  };
}

/** 量到的容器尺寸(px)→ 圖的 viewBox 高(viewBox 單位)。
 *
 *  **反解只此一處**(§4.1 CS-1):`OverlayCard` 收到的 `height` 是 viewBox 單位,
 *  兩邊各自換算會讓「誰扣了 chrome」變成得逐檔確認的事。
 *  分時態(`paneIntradayBox`)與 K 線態(`paneCandleBox`)都不走這支,它們是 1:1。
 *
 *  地板 96:容器矮到連 chrome 都放不下時,回 0 / 負高會畫出一張沒有高度的圖(svg 不報錯,
 *  純粹消失)。−2 是抗抖動餘裕 —— 反解後的 px 高恰等於量到的高時,亞像素進位會讓內容比
 *  容器高半格,觸發 ResizeObserver 的「量測 → 設高 → 再量測」迴圈。
 *
 *  量不到(任一邊 ≤ 0,jsdom / ResizeObserver 缺席 / 首幀)或寬度扣不出 svg 寬 → `undefined`,
 *  呼叫端走各自的固定 fallback(W-10)。 */
export function paneSvgHeight(size: Size, frame: PaneFrame): number | undefined {
  if (size.width <= 0 || size.height <= 0) return undefined;
  const svgW = size.width - frame.insetX;
  if (svgW <= 0) return undefined;
  const renderPx = Math.max(96, Math.floor(size.height - frame.chromeY) - 2);
  return Math.round((renderPx * frame.vbW) / svgW);
}

/** 一個 viewBox 單位在畫面上是幾 px 的**倒數** —— 也就是「要抵銷 svg 的等比縮放,
 *  viewBox 內的尺寸該乘多少」。
 *
 *  svg 帶 `viewBox="0 0 vbW H"` + `className="w-full"` 時整份內容等比縮放到容器寬,
 *  字級也跟著縮:pane 窄到 312px(1536 兩欄態)時 `0.625rem` 只剩約 4.9px,誰也讀不出
 *  刻度寫什麼。把這個比例乘回字級,渲染 px 就與 pane 寬無關(WL-3)。
 *
 *  量不到 → `undefined`,呼叫端當 1(= 改版前的行為,字級數值逐字不變)。 */
export function paneUnitScale(size: Size, frame: PaneFrame): number | undefined {
  if (size.width <= 0 || size.height <= 0) return undefined;
  const svgW = size.width - frame.insetX;
  if (svgW <= 0) return undefined;
  return frame.vbW / svgW;
}

/** viewBox 內的字級字串。**一律走這支不要手寫 rem 字面值**:補償漏一處的症狀是同一張
 *  圖裡有兩種大小的字,而不是報錯。`scale` 預設 1 → 輸出與改版前的字面值數值等價
 *  (`0.625` → `"0.6250rem"`,SVG 解析同值)。 */
export function svgFontRem(base: number, scale = 1): string {
  return `${(base * scale).toFixed(4)}rem`;
}
