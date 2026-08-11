import { useState } from "react";

import { toSvgPoint } from "@/lib/chart-crosshair";

/** K 線圖 hover 十字線的事件層(自 CandleChart 抽出,行為不變)。
 *
 *  hover 存的是 **viewBox 座標**不是 bar index:index 是對可視窗口 shown 的,
 *  一旦滾輪縮放或資料延伸讓 viewport.start 改變,同一個索引就指到別根 bar —— 十字線與
 *  資訊列會一起指錯,而且要等下次滑鼠移動才修正(實測游標在 x=700、十字線飄到 807)。
 *  存座標則每次 render 都用當下的 g 重新反查,錨點守恆的縮放天然維持「指著同一根」。
 *  y 同時是水平線位置:水平線是「自由量尺」(跟滑鼠),不鎖收盤價 —— 盤中最常做的事是
 *  量距離(現價到某價位差幾%),鎖收盤價的水平線與蠟燭重合、資訊冗餘。 */
export function useCandleHover(
  dimW: number,
  dimH: number,
): {
  hover: { x: number; y: number } | null;
  onMove: (e: React.MouseEvent<SVGSVGElement>) => void;
  /** mouseleave 與拖曳平移中呼叫:拖曳中不更新十字線,避免抖動 */
  clearHover: () => void;
} {
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);

  function onMove(e: React.MouseEvent<SVGSVGElement>): void {
    const rect = e.currentTarget.getBoundingClientRect();
    const { x, y } = toSvgPoint(e, rect, { width: dimW, height: dimH });
    const rx = Math.round(x);
    const ry = Math.round(y);
    // 值相同就回 prev 讓 React bail out:亞像素抖動不該觸發 re-render
    setHover((p) => (p !== null && p.x === rx && p.y === ry ? p : { x: rx, y: ry }));
  }

  return { hover, onMove, clearHover: () => setHover(null) };
}
