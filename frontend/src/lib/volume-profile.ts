/** 價位別成交量(volume profile)的幾何純函數;零 React 依賴。
 *
 *  與 CDP overlay 同一「價位 → toY → 畫水平元素」樣板,只是畫的是有寬度的長條。
 *  x 恆為 `Y_AXIS_W`(bar 自繪圖區左緣向右)由元件端負責,這裡只出 y/h/w。 */

import type { VpCell } from "@/lib/stock-accum";
import { plotWidth } from "@/lib/stock-intraday-svg";
import { stepDown, stepUp } from "@/lib/stock-tick";

/** bar 最大寬 = 繪圖區的 22%(長條是背景參考,不該吃掉走勢線的可讀空間)。 */
export const VP_MAX_W_RATIO = 0.22;

/** 渲染透明度。收在 lib 常數而不是元件的 magic number:與 `VP_MAX_W_RATIO` 一樣是
 *  「這組長條在視覺層級上壓在走勢線之下」這一個決策的兩半,分開放會各自漂移。 */
export const VP_FILL_OPACITY = 0.25;

/** POC(域內量最大的那一根)的透明度。與 `VP_FILL_OPACITY` 放在一起是同一個理由 ——
 *  兩個值的關係(POC 必須比其餘 bar 更顯眼)是一個決策的兩半,分開放會各自漂移。 */
export const VP_POC_FILL_OPACITY = 0.45;

export interface VpBar {
  /** 價位帶頂端的 y(svg 座標,愈小愈上);帶以成交價置中並 clamp 進 y 域 */
  y: number;
  h: number;
  w: number;
  priceMilli: number;
  /** 該檔位當日總張(未歸一)。SC-4 起是 POC 判定的依據(見 `poc`);
   *  歸一後的 `w` 只上得了畫面,比大小要用這個原始值。 */
  total: number;
  /** 這一根是不是 POC(域內 `total` 最大的價位)。**非 optional** —— 可選欄位讓
   *  「忘了算」與「不是 POC」在型別上同形,而元件端的 `b.poc ?` 分支照樣不報錯。 */
  poc: boolean;
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

  // POC = 域內 `total` 最大的價位(SC-4)。三件事收在這個迴圈裡:
  // (a) **不能用上面的 `maxTotal` 比對** —— 它被 `Math.max(1, ...)` clamp 過,全 0 的
  //     當下拿它比會讓任何一根都對不上(還好),但若哪天有一檔恰為 1 張就會憑空
  //     多出一個「POC」;判定要跟原始最大值走,而原始最大值為 0 = 無 POC。
  // (b) tie 取**較高**價位:`w` 是歸一後的浮點數,拿它比大小在同量時不決定性,
  //     而 React 的 key 與 class 都吃這個結果 —— 同一份資料兩次 render 挑到不同那根
  //     的症狀是 highlight 在畫面上跳動,沒有任何錯誤訊號。
  // (c) 域限定與歸一分母同規:域外那筆根本沒畫出來,不該奪走這張圖的 POC。
  let pocPrice: number | null = null;
  let pocTotal = 0;
  for (const [priceMilli, cell] of inDomain) {
    if (cell.t > pocTotal || (cell.t === pocTotal && pocPrice !== null && priceMilli > pocPrice)) {
      pocTotal = cell.t;
      pocPrice = priceMilli;
    }
  }

  const bars = inDomain.map(([priceMilli, cell]): VpBar => {
    // 價位帶 = **以成交價置中** `[p − tick/2, p + tick/2]`,兩端各自 clamp 進 y 域
    // (review A1/A2/B2;design v2 amendment 2026-08-05)。
    //
    // 舊版是「向上一個 tick」`[p, p + tick)`,兩個症狀:(a) 整組 bar 相對走勢線上偏
    // 半檔 —— 長條與價線指的是同一個價位,對不上就沒有比對價值;(b) 漲停(或跌停)
    // 那一檔的帶整段落在域外,clamp 後 dist = 0 → h 被壓成 1px 髮絲,而鎖停日量最大
    // 的正是那一檔(§0a 鎖板品質的核心觀察對象)反而看不見。置中之後端點檔位的帶
    // 有一半在域內,拿得到半帶高。
    //
    // `y = top` 而不是把 bar 再置中進帶內:0.15 的縫必須全由下緣吃掉,否則端點檔位
    // 的 bar 會往上溢出畫布(它的 top 已經**就是**域邊界)。代價是中心與價線差
    // 0.075 × dist(半條縫),遠小於舊語意的半個 tick。
    //
    // 兩端取「與相鄰**合法檔位**的中點」而不是 `± tickOf(p)/2`(F-5):tick 級距邊界上
    // 下方鄰檔比自己細(100.00 元的 tick 是 0.5,但下一檔 99.90 的 tick 是 0.1),
    // 同寬的帶會跨進鄰檔的帶 0.2 元 —— fillOpacity 疊加後看起來像那一帶量特別集中。
    // 檔位規則沿 `stock-tick.ts` 的單一定義,不在這裡自寫第二份。
    // 非邊界檔位的結果與 `p ± tick/2` 等價,只有 `TICK_TABLE` 的**五**個交界
    // (10 / 50 / 100 / 500 / 1000 元)收斂。
    const topMilli = (priceMilli + stepUp(priceMilli)) / 2;
    const bottomMilli = (priceMilli + stepDown(priceMilli)) / 2;
    const top = Math.max(g.toY(yTop), g.toY(topMilli));
    const bottom = Math.min(g.toY(yBottom), g.toY(bottomMilli));
    const dist = bottom - top;
    return {
      y: top,
      // 比例縫(0.85):高密度域(dist ≈ 1px)時退化成近連續帶而相鄰不重疊;
      // dist < 1(或退化域 toY 常數 → dist 0)時 clamp 到 1,亞像素重疊是刻意接受的下界
      h: Math.max(1, dist * 0.85),
      w: (cell.t / maxTotal) * maxW,
      priceMilli,
      total: cell.t,
      poc: priceMilli === pocPrice,
    };
  });
  // 降冪 = 由上而下,React key 穩定
  bars.sort((a, b) => b.priceMilli - a.priceMilli);
  return bars;
}
