/** 極值標記的幾何(分時圖當日高低 / K 線視窗高低共用;round4 項 1,round6 項 1 改圓環)。
 *
 *  兩張圖各寫一份的話,「標記該貼在價位上」與「文字撞到圖框要翻面」這兩條規則
 *  會各自漂移,而漂移的樣態是「標記被裁掉半截」或「文字壓在量柱上」—— 目視才抓得到,
 *  沒有測試會紅(同 `toY` / `priceAtY` 必須共用 `PAD_Y` 的教訓)。
 *
 *  尺寸不共用:兩張圖的 viewBox 寬差 1.75×(800 vs 1400,同一容器寬),硬套同一組 px
 *  會讓 K 線的標記只有分時圖的 57% 大。共用的是**規則**,各自帶自己的 style。
 *
 *  ## round6 項 1:三角 → 空心圓環
 *
 *  舊註解寫「用三角不用圓點:圓點會與現價圈(r=3)、hover 收盤錨(r=2.5)混淆,
 *  而 ▲/▼ 的方向本身就帶高 / 低語意」。**user 顯式推翻了這條取捨** —— 三角在
 *  800px viewBox 縮到容器寬後辨識度不如圓,且方向語意其實由「標記在圖的上緣還是下緣」
 *  就講完了,不需要形狀再講一次。
 *
 *  防混淆改由**填滿與否**承擔,不是形狀:現價圈與 hover 錨都是**實心**且帶漲跌色,
 *  極值標記是**空心環**且恆為中性灰。空心還有一個好處 —— 標記本輪要移到走勢線之上,
 *  實心會把線在極值那一點截斷,空心則是套在線上。
 *
 *  環畫兩層:底環(與底色同色、較粗)墊在面環下,讓標記在走勢線、紅綠填色、格線上
 *  都讀得出來。**邊界夾制只算墨色外緣**(`radius + ring/2`,見 `markOuterRadius`)——
 *  底環是背景色墊片,溢出 viewBox 沒有視覺後果,把它算進夾制反而會逼出過小的環。 */

export type ExtremeDir = "up" | "down";

export interface ExtremeMarkStyle {
  /** 環的半徑(圓心恰在價位上) */
  radius: number;
  /** 面環線寬(中性灰那一圈) */
  ring: number;
  /** 底環線寬(與底色同色,墊在面環下);同時決定視覺外緣 */
  halo: number;
  /** 高標文字:`out` = 畫在環外側(上方)的 baseline 距離;`flip` = 撞到圖框時翻到內側 */
  labelUp: { out: number; flip: number };
  /** 低標文字:`out` = 畫在環外側(下方);`flip` = 撞到圖框時翻到內側 */
  labelDown: { out: number; flip: number };
}

/** 分時圖(viewBox 800 寬、字級 0.5625rem ≈ 9px)。
 *  `radius + ring/2 = 3.75 ≤ PAD_Y(4)` —— 漲停時標記恰在 y 域頂端,墨色環不被裁。 */
export const INTRADAY_MARK: ExtremeMarkStyle = {
  radius: 3,
  ring: 1.5,
  halo: 3,
  labelUp: { out: 10, flip: 16 },
  labelDown: { out: 15, flip: 10 },
};

/** K 線圖(viewBox 1400 寬、字級 0.625rem ≈ 10px)。
 *  `radius + ring/2 = 5.375 ≤ PAD_Y(6)` —— 視窗高**恆在** y 域頂端(常態不是邊角)。 */
export const CANDLE_MARK: ExtremeMarkStyle = {
  radius: 4.5,
  ring: 1.75,
  halo: 4,
  labelUp: { out: 12, flip: 19 },
  labelDown: { out: 18, flip: 12 },
};

/** 墨色可見外緣 = 半徑 + 面環的一半線寬。
 *
 *  **刻意不含 halo**:底環是與底色同色的墊片,溢出 viewBox 或壓到邊界都沒有視覺後果
 *  (它蓋掉的就是背景本身)。若把 halo 算進夾制,分時圖要求外緣 ≤ PAD_Y(4)會把環壓到
 *  radius 2.5 —— 與 hover 收盤錨同尺寸,反而製造出本輪要避免的混淆。
 *
 *  夾制與「文字要閃多遠」都以它為準,幾何與元件才不會各寫一份 strokeWidth。 */
export function markOuterRadius(style: ExtremeMarkStyle): number {
  return style.radius + style.ring / 2;
}

/** 圓心 x。**整個環一起平移**(不是把它壓扁),形狀才不會變形;位移最多一個外緣半徑,
 *  仍指得到那根蠟燭 / 那一分鐘。
 *
 *  `bounds`(選填)= 可畫範圍左右界。極值落在第一根 / 最後一根、而每根的 slot 又比環
 *  還窄時(K 線分 K 預設 240 根 → slot ≈ 5.8px、首根 cx ≈ 2.9px),沒有夾制的話
 *  環的左緣會出界被裁成缺角。 */
export function markCenterX(
  x: number,
  style: ExtremeMarkStyle,
  bounds?: { min: number; max: number },
): number {
  if (bounds === undefined) return x;
  const r = markOuterRadius(style);
  return Math.min(Math.max(x, bounds.min + r), bounds.max - r);
}

/** 價位文字的 baseline。預設畫在環外側,撞到圖框就翻到內側。
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
