/** 極值標記的幾何(分時圖當日高低 / K 線視窗高低共用;round4 項 1、round6 項 1、round6b)。
 *
 *  兩張圖各寫一份的話,「標記該貼在價位上」與「文字撞到圖框要翻面」這兩條規則
 *  會各自漂移,而漂移的樣態是「標記被裁掉半截」或「文字壓在量柱上」—— 目視才抓得到,
 *  沒有測試會紅(同 `toY` / `priceAtY` 必須共用 `PAD_Y` 的教訓)。
 *
 *  尺寸不共用:兩張圖的 viewBox 寬差 1.75×(800 vs 1400,同一容器寬),硬套同一組 px
 *  會讓 K 線的標記只有分時圖的 57% 大。共用的是**規則**,各自帶自己的 style。
 *
 *  ## 形狀的三次演變(每一次都是 user 推翻上一次)
 *
 *  1. round4:橫貫左右的虛線 → 三角 + 就地價位文字。
 *  2. round6:三角 → 空心圓環。理由是「空心才不與實心現價圈混淆」。
 *  3. **round6b(本次)**:分時圖改**實心小圓**、K 線圖**不畫圖案只留文字**。
 *
 *  第 3 次同時推翻了「用中性灰不用紅綠」那條 —— 當初的理由是「整天下跌的股票其日高仍低於
 *  昨收,塗紅等於假陳述」,但 user 指定的判色基準是**相對平盤**(高於平盤紅、低於平盤綠、
 *  平盤灰),那種股票的日高本來就會判成綠,原本的顧慮不成立。判色見 `markTone`。
 *
 *  分時圖的實心圓與現價圈(r=3 實心、同樣帶漲跌色)確實變得相似,靠**位置**區分:
 *  現價圈永遠在走勢線末端,極值標記在當日高 / 低那一分鐘。 */

export type ExtremeDir = "up" | "down";

export interface ExtremeMarkStyle {
  /** 圖案幾何;**`null` = 這張圖不畫圖案,只留價位文字**(K 線圖 round6b)。 */
  dot: {
    /** 實心圓半徑 */
    radius: number;
    /** 與底色同色的描邊寬(`paintOrder="stroke"` 墊在填色下),讓圓在走勢線 / 填色上都讀得出來。
     *  同時決定視覺外緣 = `radius + halo / 2`。 */
    halo: number;
  } | null;
  /** 高標文字:`out` = 畫在標記外側(上方)的 baseline 距離;`flip` = 撞到圖框時翻到內側 */
  labelUp: { out: number; flip: number };
  /** 低標文字:`out` = 畫在標記外側(下方);`flip` = 撞到圖框時翻到內側 */
  labelDown: { out: number; flip: number };
}

/** 分時圖(viewBox 800 寬、字級 0.5625rem ≈ 9px)。
 *
 *  `radius + halo/2 = 3 ≤ PAD_Y(4)` —— 漲停時標記恰在 y 域頂端(常態不是邊角),
 *  外緣超過 PAD_Y 就會被 viewBox 裁掉一圈。舊的三角靠「body 朝圖內」迴避這件事,
 *  圓沒有方向可躲,只能靠尺寸。 */
export const INTRADAY_MARK: ExtremeMarkStyle = {
  dot: { radius: 2.5, halo: 1 },
  labelUp: { out: 7, flip: 14 },
  labelDown: { out: 12, flip: 8 },
};

/** K 線圖(viewBox 1400 寬、字級 0.625rem ≈ 10px)。
 *
 *  **不畫圖案**(round6b):蠟燭圖本身已經把「哪一根是最高」講得很清楚,再加一顆點只是
 *  在影線端點上多一塊遮蔽物。位置語意改由價位文字本身承載。
 *  文字距離因此可以比有圖案時近(不必再閃過一顆圓)。 */
export const CANDLE_MARK: ExtremeMarkStyle = {
  dot: null,
  labelUp: { out: 5, flip: 16 },
  labelDown: { out: 14, flip: 9 },
};

/** 標記的視覺外緣半徑;不畫圖案的 style 回 0(文字自己有 `clampLabelX`)。 */
export function markOuterRadius(style: ExtremeMarkStyle): number {
  return style.dot === null ? 0 : style.dot.radius + style.dot.halo / 2;
}

/** 極值標記的判色(round6b,user 指定):**相對平盤**高於紅、低於綠、等於灰。
 *
 *  與左緣刻度的 `tickTone` 差一處:`tickTone` 的平盤是白(`fill-ink`),因為那是一條
 *  刻度基準線要看得清楚;標記的平盤是灰(`fill-ink-dim`)—— user 指定「平盤就灰色即可」,
 *  語意是「這個極值沒有方向可言」而不是「這是基準」。
 *
 *  參考價不可得時同樣回灰:那時沒有「平盤」可言,硬分紅綠等於憑首筆成交價編一個基準出來
 *  (同 `hasRef` 的既有紀律)。 */
export function markTone(priceMilli: number, refMilli: number | null): string {
  if (refMilli === null || refMilli <= 0) return "fill-ink-dim";
  if (priceMilli > refMilli) return "fill-bull";
  if (priceMilli < refMilli) return "fill-bear";
  return "fill-ink-dim";
}

/** 圓心 x。**整個圖案一起平移**(不是把它壓扁),形狀才不會變形;位移最多一個外緣半徑,
 *  仍指得到那根蠟燭 / 那一分鐘。
 *
 *  `bounds`(選填)= 可畫範圍左右界。極值落在第一根 / 最後一根、而每根的 slot 又比圖案
 *  還窄時,沒有夾制的話圖案左緣會出界被裁成缺角。不畫圖案的 style 無事可夾,原樣回傳。 */
export function markCenterX(
  x: number,
  style: ExtremeMarkStyle,
  bounds?: { min: number; max: number },
): number {
  if (bounds === undefined || style.dot === null) return x;
  const r = markOuterRadius(style);
  return Math.min(Math.max(x, bounds.min + r), bounds.max - r);
}

/** 價位文字的 baseline。預設畫在標記外側,撞到圖框就翻到內側。
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

/** 文字的水平夾制:標記本身留在真 x(承載時間語意),只夾文字。 */
export function clampLabelX(x: number, minX: number, maxX: number): number {
  return Math.min(Math.max(x, minX), maxX);
}
