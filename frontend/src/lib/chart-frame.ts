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

/** 群組卡片變體的框外 chrome(px @ root font-size 16)。**與 `CHART_FRAME` 分開** ——
 *  卡片沒有 figure 的 padding / border,也沒有底部說明列,只剩 readout 那一列;
 *  硬套 `CHART_FRAME` 會多扣 84px,在 250px 高的卡片上等於三分之一張圖。 */
export const CARD_CHROME = {
  /** readout 列 h-[1.375rem](22)+ mb-1(4);與 `CHART_FRAME.topRow` 同一份口徑 */
  readoutRow: 26,
} as const;

/** 主圖佔可用高的比例分子 / 分母 = 單檔頁 `MAIN.height` : `MAIN.height + SUB.height`。
 *  比例寫在這裡而不是元件裡:元件端另算一次的話,卡片的主副比會與單檔頁靜默岔開。
 *
 *  **分子 / 分母分開 export**:呼叫端算的是 `Math.round((h * NUM) / DEN)`(先乘後除),
 *  改用比值 `Math.round(h * CARD_MAIN_RATIO)` 會在 `260/330` 這個無限循環小數上差 1px
 *  —— 而 1px 正好是「兩張圖相加溢出格軌」的臨界。要比值的自己 derive。 */
export const MAIN_RATIO_NUM = 260;
export const MAIN_RATIO_DEN = 330;
const CARD_MAIN_RATIO = MAIN_RATIO_NUM / MAIN_RATIO_DEN;

export interface CardSvgBox {
  /** viewBox 寬 = 量到的 px 寬(1:1);**主圖與副圖共用** */
  width: number;
  mainH: number;
  subH: number;
  usable: boolean;
}

/** 卡片圖區 wrapper 的量測尺寸 → 主 / 副圖的 viewBox 尺寸(1:1)。
 *
 *  `−2` 安全邊與 `svgBox` 同理:誤差方向恆為「略短」,多 1px 就會讓卡片內容溢出格軌
 *  (矩陣佈局的列軌壓不住 overflow visible 的 item,會與下一列重疊而不是乾淨捲動)。
 *
 *  兩張圖的高用**減法**拆而不是各自 round:各自 round 時 `mainH + subH` 可能比可用高
 *  多 1px,而那 1px 正好是溢軌的臨界。 */
export function cardSvgBox(size: Size): CardSvgBox {
  const usable = size.height - CARD_CHROME.readoutRow - 2;
  if (size.width <= 0 || usable <= 0) {
    return { width: 0, mainH: 0, subH: 0, usable: false };
  }
  const mainH = Math.round(usable * CARD_MAIN_RATIO);
  return { width: Math.round(size.width), mainH, subH: usable - mainH, usable: true };
}

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
