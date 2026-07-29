/** K 線可視窗口(縮放 / 平移)純函式;無 React 依賴,元件只持有 state。
 *
 * 窗口以 bar index 表示:`[start, start + count)`。
 *
 * `MAX_VISIBLE` 承接舊 `MINUTE_MAX_BARS.m1 = 700` 的保護 —— viewBox 寬 1400 ÷ 700 = 2px/根,
 * 再多就只剩色塊且拖慢 hover(舊常數註解已載明)。刪掉舊上限改走縮放後,保護必須換這裡續存。 */

export interface Viewport {
  start: number;
  count: number;
}

export const MIN_BARS = 20;
export const MAX_VISIBLE = 700;

/** 夾制次序寫死:先 min(不超過資料量與上限)後條件式 max(資料本來就不足 20 根 → 不強拉)。
 *  次序寫反會得到 count > total 與負的 start,而 2–8 根正是既有元件測試的常態。 */
export function clampCount(count: number, total: number): number {
  let c = Math.max(1, Math.min(count, total, MAX_VISIBLE));
  if (total >= MIN_BARS) c = Math.max(c, MIN_BARS);
  return c;
}

export function clampViewport(vp: Viewport, total: number): Viewport {
  if (total <= 0) return { start: 0, count: 0 };
  const count = clampCount(vp.count, total);
  const start = Math.max(0, Math.min(Math.round(vp.start), total - count));
  return { start, count };
}

/** 初始窗口:貼右緣顯示最後 initBars 根。 */
export function initialViewport(total: number, initBars: number): Viewport {
  return clampViewport({ start: Math.max(0, total - initBars), count: initBars }, total);
}

/** 以游標為錨縮放。`anchorRatio` = 游標在窗口內的比例(0=左緣, 1=右緣)。
 *  `factor > 1` = 看更多根(縮小);`factor < 1` = 放大。
 *  錨點守恆:游標所指的那根 bar 在縮放前後仍落在同一個 anchorRatio 位置(未被邊界夾制時)。 */
export function zoomAt(
  vp: Viewport,
  total: number,
  factor: number,
  anchorRatio: number,
): Viewport {
  if (total <= 0) return { start: 0, count: 0 };
  const r = Math.min(Math.max(anchorRatio, 0), 1);
  const anchorIndex = vp.start + r * vp.count;
  // ⚠ count 必須**先**夾制再拿去算 start:用未夾制的 count 推 start,縮放撞到 MAX_VISIBLE
  // 或 MIN_BARS 時錨點會漂(實測 factor=2 撞 700 上限時漂 25 根)。
  const count = clampCount(Math.round(vp.count * factor), total);
  return clampViewport({ start: anchorIndex - r * count, count }, total);
}

/** 平移 deltaBars 根(正 = 往右/往新);夾在資料端點,不空捲。 */
export function panBy(vp: Viewport, total: number, deltaBars: number): Viewport {
  return clampViewport({ start: vp.start + deltaBars, count: vp.count }, total);
}

/** 資料序列**延伸**時的窗口處置(同一 code + mode 的 60s refetch 追加新 bar)。
 *
 * 只有「改動前已貼右緣」才跟進新資料;否則保持 start 不動。無條件貼右緣會讓使用者在盤中
 * 平移到早盤研究時,最多 60 秒就被 refetchInterval 拉回最右(useStockBars.ts refetchInterval)。
 *
 * ⚠ 換股與換模式**不走這條路徑** —— 那兩者由元件 key 強制重掛回 initialViewport。
 * 換模式時 total 會由 ~5,900 變 ~590,沿用舊 index 沒有意義。 */
export function onTotalChange(vp: Viewport, prevTotal: number, nextTotal: number): Viewport {
  const wasAtRight = vp.start + vp.count >= prevTotal;
  const start = wasAtRight ? nextTotal - vp.count : vp.start;
  return clampViewport({ start, count: vp.count }, nextTotal);
}
