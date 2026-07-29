/** 十字線軸標籤的夾制純函式(兩張圖共用;無 React 依賴)。
 *
 * 回傳的是標籤矩形的左上角座標,不是中心 —— 呼叫端直接餵給 `<rect x/y>`。
 * 兩個函式都對「容器比標籤還小」的退化情形回 0(不回負值把標籤推出畫布)。 */

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(Math.max(v, lo), hi);
}

/** 垂直置中於 `ySvg`,夾在 [0, plotBottom − boxH]。 */
export function clampTagY(ySvg: number, boxH: number, plotBottom: number): number {
  return clamp(ySvg - boxH / 2, 0, Math.max(0, plotBottom - boxH));
}

/** 水平置中於 `xSvg`,夾在 [0, width − boxW]。 */
export function clampTagX(xSvg: number, boxW: number, width: number): number {
  return clamp(xSvg - boxW / 2, 0, Math.max(0, width - boxW));
}

/** 螢幕座標 → SVG viewBox 座標。
 *
 * 這條線性映射成立的前提是 svg 的實際高寬比由 viewBox 決定(現況兩張圖都是
 * `className="w-full"` 且無高度 class)。若日後有人加固定高度 class,y 就會失真。
 * jsdom 下 rect 恆 0 → 退回 1:1(測試與真環境同一條路徑,不 early-return)。 */
export function toSvgPoint(
  e: { clientX: number; clientY: number },
  rect: { left: number; top: number; width: number; height: number },
  vb: { width: number; height: number },
): { x: number; y: number } {
  const sx = rect.width > 0 ? vb.width / rect.width : 1;
  const sy = rect.height > 0 ? vb.height / rect.height : 1;
  return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sy };
}
