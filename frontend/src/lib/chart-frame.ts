/** 圖表 figure 的框外 chrome 常數與 viewBox 換算(change-spec R-2b)。
 *
 * **為什麼收在同一個檔**:江波圖與 K 線「切換模式時區塊高度不跳」(白名單 W-12)原本
 * 只靠「兩個元件各自記得扣一樣的項」,漏一項就漂移 —— 實際上 spec review 就抓到頂列的
 * `mb-1`(4px)兩邊都漏扣。改成共用常數後,W-12 由建構保證而不是靠紀律。
 *
 * 換算模型:svg 帶 `viewBox="0 0 W H"` + `className="w-full"` → 渲染寬 = 容器寬,
 * 渲染高 = 容器寬 × H/W。要讓渲染高等於 `renderPx`,就得反解 `H = renderPx ÷ s`,
 * 其中 `s` = 實際縮放比 = **svg 的渲染寬** ÷ viewBox 寬。
 * svg 的渲染寬不是量到的 wrapper 寬 —— 中間隔著 figure 的 `p-4` 與 border。
 */

export interface Size {
  width: number;
  height: number;
}

/** figure 框外 chrome(px @ root font-size 16)。 */
export const CHART_FRAME = {
  /** p-4 左右 */
  padX: 32,
  /** p-4 上下 */
  padY: 32,
  /** border 上下(左右同值) */
  border: 2,
  /** 頂列 h-[1.375rem](22)+ mb-1(4) */
  topRow: 26,
  /** 底列 figcaption h-4(16)+ mt-1(4) */
  bottomRow: 20,
} as const;

export interface SvgBox {
  /** svg 該渲染多高(px) */
  renderPx: number;
  /** 反解出的 viewBox 高度 */
  viewBoxHeight: number;
  /** 量測有效與否;false → 呼叫端退回固定尺寸常數(既有行為) */
  usable: boolean;
}

/** wrapper 量測尺寸 → svg 的渲染高與 viewBox 高。
 *
 * `minPx` 是極矮視窗的地板:不夾制的話 viewBox 高度會趨零甚至為負。
 * 夾到地板後總高可能超出可用空間 —— 那是**刻意**的退化,由 `<main>` 的捲軸接住
 * (W-11 的逃生口,所以 `<main>` 不可改成 `overflow-hidden`)。 */
export function svgBox(wrapper: Size, viewBoxWidth: number, minPx = 180): SvgBox {
  const svgWidth = wrapper.width - CHART_FRAME.padX - CHART_FRAME.border;
  if (wrapper.width <= 0 || wrapper.height <= 0 || svgWidth <= 0 || viewBoxWidth <= 0) {
    return { renderPx: 0, viewBoxHeight: 0, usable: false };
  }
  const chrome =
    CHART_FRAME.padY + CHART_FRAME.border + CHART_FRAME.topRow + CHART_FRAME.bottomRow;
  // −2 安全邊:讓誤差方向恆為「略短」。多出 1px 就會讓 <main> 長出捲軸(SC-6 FAIL),
  // 少 1px 只是圖表底部與下半列之間多一條髮絲空隙,看不出來。
  const renderPx = Math.max(minPx, Math.floor(wrapper.height - chrome) - 2);
  const s = svgWidth / viewBoxWidth;
  return { renderPx, viewBoxHeight: Math.round(renderPx / s), usable: true };
}
