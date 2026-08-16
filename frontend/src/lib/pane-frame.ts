/** 台股綜合雙圖 pane 的「量測 → viewBox 高」換算(§4.1 CS-1)。
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

/** 三種圖模式各自的 chrome 用量。**逐條列舉不共用一組數字**:三者的 DOM 巢狀深度不同,
 *  用同一組會讓其中兩種各差 30-70px —— 症狀是圖比容器高一點點,於是主 grid 出現一條
 *  誰也解釋不了的捲軸。
 *
 *  **每一項都必須是固定高的元素**:會折行的東西(K 線態那條 meta 列曾是 `text-xs`
 *  無高度限制)在窄 pane 下折成兩行,chromeY 就少算一行的高度,svg 溢出 figure。
 *  折不折得掉由該元素自己保證(meta 列 `h-4` + `truncate`),不是靠這裡多留餘裕。
 *
 *  - intraday:toggle 列 `h-[1.375rem]` 22 + `mb-1` 4 = 26;svg 直接在 wrapper 內,不內縮。
 *  - overlay:`OverlayCard` 是巢狀 figure —— border 2 + `p-4` 32 + 標題列 20 + svg `mt-2` 8
 *    = 62;水平 border 2 + p-4 32 = 34。
 *  - candle:`CandleChart` 自身 figure(border 2 + `p-4` 32 + 頂列 26 + figcaption 20 = 80)
 *    + `MarketChart` 的 meta 列(`h-4` 16 + `mt-1` 4 = 20)= 100;水平同 overlay 34;
 *    **viewBox 寬是 CandleChart 的 `DIMS.width` = 1400**,不是 640。 */
export const PANE_FRAMES: Record<"intraday" | "overlay" | "candle", PaneFrame> = {
  intraday: { chromeY: 26, insetX: 0, vbW: 640 },
  overlay: { chromeY: 62, insetX: 34, vbW: 640 },
  candle: { chromeY: 100, insetX: 34, vbW: 1400 },
};

/** 量到的容器尺寸(px)→ 圖的 viewBox 高(viewBox 單位)。
 *
 *  **反解只此一處**(§4.1 CS-1):`MarketChart` / `OverlayCard` 收到的 `height` 一律是
 *  viewBox 單位,兩邊各自換算會讓「誰扣了 chrome」變成得逐檔確認的事。
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
