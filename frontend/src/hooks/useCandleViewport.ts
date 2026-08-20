import { useEffect, useState } from "react";

import {
  initialViewport,
  onTotalChange,
  panBy,
  zoomAt,
  type Viewport,
} from "@/lib/candle-viewport";
import { toSvgPoint } from "@/lib/chart-crosshair";

/** 滾輪每一格的縮放倍率 */
const ZOOM_STEP = 1.15;

/** K 線圖可視窗口的狀態與事件層(自 CandleChart 抽出,行為不變):
 *  viewport state + 序列延伸調整 + 滾輪縮放 + 拖曳平移。 */
export function useCandleViewport({
  total,
  initBars,
  svgRef,
  dimW,
  dimH,
  onDragMove,
}: {
  /** 完整序列長度(bars.length) */
  total: number;
  /** 初始可視根數(日 K 120 / 分 K 240) */
  initBars: number;
  /** 圖面 svg;wheel 原生 listener 與拖曳座標換算都掛它 */
  svgRef: React.RefObject<SVGSVGElement | null>;
  dimW: number;
  dimH: number;
  /** 拖曳平移每步回呼(CandleChart 傳 clearHover:拖曳中不更新十字線,避免抖動) */
  onDragMove: () => void;
}): {
  viewport: Viewport;
  onDragStart: (e: React.MouseEvent<SVGSVGElement>) => void;
} {
  const [viewport, setViewport] = useState<Viewport>(() => initialViewport(total, initBars));
  const [prevTotal, setPrevTotal] = useState(total);

  // 序列延伸(分 K 每 60s refetch 追加新 bar)時調整窗口。用 render 期間調整 state 的
  // 官方 pattern,不用 effect —— 專案有 react-you-might-not-need-an-effect lint。
  // ⚠ 只處理「同一 code+mode 的延伸」;換股/換模式由 StockChart 給的 key 強制重掛。
  if (prevTotal !== total) {
    setPrevTotal(total);
    setViewport((v) => onTotalChange(v, prevTotal, total));
  }

  // 滾輪縮放。**必須掛原生 listener 且 passive: false** —— React 的 onWheel 綁在 root
  // 且為 passive,preventDefault() 無效,頁面會跟著一起捲。
  useEffect(() => {
    const el = svgRef.current;
    if (el === null) return;
    const onWheel = (e: WheelEvent): void => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const { x } = toSvgPoint(e, rect, { width: dimW, height: dimH });
      const ratio = dimW > 0 ? x / dimW : 0.5;
      const factor = e.deltaY > 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      setViewport((v) => zoomAt(v, total, factor, ratio));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // dimW **現在是 prop**(`CandleChart.width`;台股綜合 pane 傳量測寬走 1:1),
    // 不再是模組常數 —— 它入 deps 已經不只是形式:pane 縮寬時 dimW 換值,舊 listener
    // 的閉包會用舊寬算 `x / dimW` 這個縮放錨點,症狀是滾輪縮放的中心悄悄偏掉而圖照畫。
    // dimH 仍不參與 x 幾何,列出來是為了「閉包捕捉什麼就寫什麼」,補不補行為相同。
    // svgRef 是 ref(identity 恆定),入 deps 純為 exhaustive-deps 誠實,不會多跑。
  }, [total, dimW, dimH, svgRef]);

  /** 拖曳平移:mousedown 記起點,mousemove/mouseup 掛 window(拖出圖外仍跟手)。
   *  維持 mouse 事件模型 —— 專案慣例是觸控靠 tap 的 synthetic mousemove,改 pointer 會破。 */
  function onDragStart(e: React.MouseEvent<SVGSVGElement>): void {
    if (e.button !== 0) return;
    const el = svgRef.current;
    if (el === null) return;
    const rect = el.getBoundingClientRect();
    const scale = rect.width > 0 ? dimW / rect.width : 1;
    const startX = e.clientX;
    // 起始窗口直接取 closure 的 viewport —— 這個 handler 來自最近一次 render,值即為當下。
    // 不要用 `setViewport(v => { startVp = v; return v; })` 的 side effect 去讀:React 不保證
    // updater 同步執行(只是常常如此),讀到 null 就得 fallback,等於多一條沒必要的路徑。
    const startVp = viewport;
    const slot = dimW / Math.max(1, startVp.count);
    const move = (ev: MouseEvent): void => {
      // 往右拖 = 看更早的資料 → start 往左。以「拖曳起點」為基準算絕對位移,
      // 不是逐次累加 —— 累加會因為 clamp 而在端點附近漂移。
      const deltaBars = -Math.round(((ev.clientX - startX) * scale) / slot);
      setViewport(panBy(startVp, total, deltaBars));
      onDragMove(); // 拖曳中不更新十字線,避免抖動
    };
    const up = (): void => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  return { viewport, onDragStart };
}
