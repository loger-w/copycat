/** 價位別成交量(volume profile)的幾何純函數;零 React 依賴。
 *
 *  與 CDP overlay 同一「價位 → toY → 畫水平元素」樣板,只是畫的是有寬度的長條。
 *  x 恆為 `Y_AXIS_W`(bar 自繪圖區左緣向右)由元件端負責,這裡只出 y/h/w。 */

import type { VpCell } from "@/lib/stock-accum";
import { plotWidth } from "@/lib/stock-intraday-svg";
import { tickOf } from "@/lib/stock-tick";

/** bar 最大寬 = 繪圖區的 22%(長條是背景參考,不該吃掉走勢線的可讀空間)。 */
export const VP_MAX_W_RATIO = 0.22;

/** 渲染透明度。收在 lib 常數而不是元件的 magic number:與 `VP_MAX_W_RATIO` 一樣是
 *  「這組長條在視覺層級上壓在走勢線之下」這一個決策的兩半,分開放會各自漂移。 */
export const VP_FILL_OPACITY = 0.25;

export interface VpBar {
  /** 價位帶頂端的 y(svg 座標,愈小愈上) */
  y: number;
  h: number;
  w: number;
  priceMilli: number;
  /** 該檔位當日總張(未歸一;hover / debug 用) */
  total: number;
}

interface Geo {
  toY: (priceMilli: number) => number;
  yDomain: [number, number];
}

/** 價位別成交量 → 水平長條。空 map / 全部域外 → `[]`;輸出依 priceMilli 降冪。 */
export function buildVpBars(vp: ReadonlyMap<number, VpCell>, g: Geo, width: number): VpBar[] {
  const [yBottom, yTop] = g.yDomain;
  const inDomain: [number, VpCell][] = [];
  for (const [priceMilli, cell] of vp) {
    // 域過濾與 `overlayLines` 同規(閉區間)
    if (priceMilli < yBottom || priceMilli > yTop) continue;
    inDomain.push([priceMilli, cell]);
  }
  if (inDomain.length === 0) return [];

  // 歸一分母取**域內** max:y 域縮放(漲跌停 vs autofit)時 bar 才會用滿寬度。
  // `Math.max(1, ...)` 是 `plotWidth` / `energyFrom` 同一條紀律 —— 全 0 的當下
  // (盤前、或整批都是市價偽價位被濾掉)分母為 0 會讓每個 w 變 NaN,而 NaN 的
  // `width` 屬性在 SVG 是靜默忽略,畫面上只是「沒有長條」看不出算壞了。
  const maxTotal = Math.max(1, ...inDomain.map(([, c]) => c.t));
  const maxW = plotWidth(width) * VP_MAX_W_RATIO;

  const bars = inDomain.map(([priceMilli, cell]): VpBar => {
    // 價位帶 = [p, p + tickOf(p));頂端夾進 y 域上界,最上緣那一檔不外溢畫布
    const top = g.toY(Math.min(priceMilli + tickOf(priceMilli), yTop));
    const dist = g.toY(priceMilli) - top;
    return {
      y: top,
      // 比例縫(0.85):高密度域(dist ≈ 1px)時退化成近連續帶而相鄰不重疊;
      // dist < 1(或退化域 toY 常數 → dist 0)時 clamp 到 1,亞像素重疊是刻意接受的下界
      h: Math.max(1, dist * 0.85),
      w: (cell.t / maxTotal) * maxW,
      priceMilli,
      total: cell.t,
    };
  });
  // 降冪 = 由上而下,React key 穩定
  bars.sort((a, b) => b.priceMilli - a.priceMilli);
  return bars;
}
