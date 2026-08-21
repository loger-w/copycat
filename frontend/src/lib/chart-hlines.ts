/** 圖表水平 overlay 線的型別與空集合常數(K 線 / 分時共用)。
 *
 *  **為什麼獨立成 lib 檔而不是留在 `CandleChart.tsx`**:`EMPTY_HLINES` 是非元件 export,
 *  放在元件檔會被 react-doctor `only-export-components` 擋下(fast-refresh 邊界)。型別
 *  跟著常數走 —— 兩者分家的話,`ChartHLine` 改欄位時空集合的型別註記會靜默過期。
 *  `CandleChart.tsx` 對 `ChartHLine` 有 `export type` re-export,既有 import 路徑不變。 */

/** 水平 overlay 線(持倉均價 / OI 撐壓;futures-allday SC-7/SC-11)。
 *
 *  `className` 是 **stroke-\* 家族**(線的顏色語意),不套到標籤文字上 —— 套上去
 *  文字會被描邊而不是填色。標籤一律中性 ink + 底色描邊,方向語意由線本身承載。 */
export interface ChartHLine {
  priceMilli: number;
  label: string;
  className: string;
  /** hover 提示(SVG `<title>` 子節點)。線上只寫得下價位,證據(OI 口數 / 資料日 /
   *  部位口數)掛這裡。 */
  title?: string;
}

/** 同 `EMPTY_LINE` 的理由:預設值寫 `hlines = []` 會讓每次 render 產生新 array,
 *  打穿 ChartStatic 的 memo —— 而且是**所有既有頁面**(個股 / 大盤)都被打穿。 */
export const EMPTY_HLINES: readonly ChartHLine[] = [];
