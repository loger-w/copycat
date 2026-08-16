import { useCallback, useRef, useState } from "react";

import type { Size } from "@/lib/chart-frame";

/** 量測容器尺寸(change-spec R-2)。
 *
 * **呼叫端契約(照做才有意義)**:
 * 1. ref 必須掛在**恆存 wrapper** —— loading / error / data 三態都 mount 的那個元素。
 *    只掛 data 分支的話,冷載入時量到 0×0 而 hook 不會重跑,畫面永遠空白。
 * 2. 被量測元素的高度**必須由外層 flex 指派**(`flex-1 min-h-0`),**不得由內容決定**。
 *    由內容決定時量到的是「內容現在多高」而不是「還剩多少空間」,呼叫端據此設定內容
 *    高度就形成回饋迴圈:高度每輪漂移一點,並觸發 ResizeObserver loop 告警。
 *
 * 用 **callback ref** 而非 `useRef`:effect 內讀 `ref.current` 的寫法在 null-ref 時
 * early-return 且不會重跑(專案 conventions 記載的既有陷阱);callback ref 在節點掛上的
 * 當下就拿得到。
 *
 * jsdom 沒有 `ResizeObserver`(是 `undefined`,不是壞掉的實作)→ feature-detect 後
 * 回 `{0,0}`,呼叫端退回固定尺寸常數,既有測試行為不變。 */
export function useContainerSize<T extends HTMLElement>(): [
  (node: T | null) => void,
  Size,
] {
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback((node: T | null) => {
    observerRef.current?.disconnect();
    observerRef.current = null;
    if (node === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect === undefined) return;
      // 0×0 = 「這個節點現在看不見」,不是「沒有空間了」:主 tab 以 `hidden` 保留 DOM
      // (專案慣例),隱藏的那一刻 RO 會回一報 0×0。照收就把上一組有效量測沖掉 ——
      // 切回來的第一幀畫的是呼叫端的 fallback 尺寸,圖跳一下才回到正確比例。
      // 保留舊值:反正節點看不見時畫多大都無所謂,顯示回來若真的變了 RO 會再報一次。
      if (rect.width <= 0 || rect.height <= 0) return;
      const next = { width: rect.width, height: rect.height };
      // 1px 去抖:亞像素抖動不該觸發 re-render,也避免與「呼叫端據此設高度」形成
      // 每輪 ±0.5px 的無盡回饋。
      setSize((prev) =>
        Math.abs(prev.width - next.width) <= 1 && Math.abs(prev.height - next.height) <= 1
          ? prev
          : next,
      );
    });
    observer.observe(node);
    observerRef.current = observer;
  }, []);

  return [ref, size];
}
