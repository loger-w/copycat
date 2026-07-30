/** 極值標記的幾何(分時圖當日高低 / K 線視窗高低共用;round4 項 1)。
 *
 *  兩張圖各寫一份的話,「三角尖端該貼在價位上」與「文字撞到圖框要翻面」這兩條規則
 *  會各自漂移,而漂移的樣態是「標記被裁掉半截」或「文字壓在量柱上」—— 目視才抓得到,
 *  沒有測試會紅(同 `toY` / `priceAtY` 必須共用 `PAD_Y` 的教訓)。
 *
 *  尺寸不共用:兩張圖的 viewBox 寬差 1.75×(800 vs 1400,同一容器寬),硬套同一組 px
 *  會讓 K 線的標記只有分時圖的 57% 大。共用的是**規則**,各自帶自己的 style。 */

export type ExtremeDir = "up" | "down";

export interface ExtremeMarkStyle {
  /** 三角半寬 */
  half: number;
  /** 三角高(apex → 底邊) */
  height: number;
  /** 高標文字:`out` = 畫在三角外側(apex 上方)的 baseline 距離;`flip` = 撞到圖框時翻到內側 */
  labelUp: { out: number; flip: number };
  /** 低標文字:`out` = 畫在三角外側(apex 下方);`flip` = 撞到圖框時翻到內側 */
  labelDown: { out: number; flip: number };
}

/** 分時圖(viewBox 800 寬、字級 0.5625rem) */
export const INTRADAY_MARK: ExtremeMarkStyle = {
  half: 3.5,
  height: 6,
  labelUp: { out: 5, flip: 15 },
  labelDown: { out: 12, flip: 10 },
};

/** K 線圖(viewBox 1400 寬、字級 0.625rem) */
export const CANDLE_MARK: ExtremeMarkStyle = {
  half: 5,
  height: 8,
  labelUp: { out: 6, flip: 19 },
  labelDown: { out: 16, flip: 12 },
};

/** 三角形點串。**apex 貼在價位上、body 朝圖內延伸** ——
 *  body 朝圖外的話,極值恰在 y 域端點時(K 線視窗高低是常態、分時圖漲跌停時)
 *  三角會被 viewBox 裁掉半截。 */
export function trianglePoints(
  x: number,
  y: number,
  dir: ExtremeDir,
  style: ExtremeMarkStyle,
): string {
  const dy = dir === "up" ? style.height : -style.height;
  return `${x},${y} ${x - style.half},${y + dy} ${x + style.half},${y + dy}`;
}

/** 價位文字的 baseline。預設畫在三角外側,撞到圖框就翻到內側。
 *  `limits.top` / `limits.bottom` 是文字 baseline 的可用範圍(呼叫端已把字高算進去)。 */
export function markLabelY(
  y: number,
  dir: ExtremeDir,
  style: ExtremeMarkStyle,
  limits: { top: number; bottom: number },
): number {
  if (dir === "up") {
    return y - style.labelUp.out < limits.top ? y + style.labelUp.flip : y - style.labelUp.out;
  }
  return y + style.labelDown.out > limits.bottom
    ? y - style.labelDown.flip
    : y + style.labelDown.out;
}

/** 文字的水平夾制:標記本身留在真 x,只夾文字(標記位置承載時間語意,不可位移)。 */
export function clampLabelX(x: number, minX: number, maxX: number): number {
  return Math.min(Math.max(x, minX), maxX);
}
