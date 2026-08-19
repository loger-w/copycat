/** dev-only User Timing guard(2026-08-19 /bug react-dev-measure-leak)。
 *
 *  React 19.2 development build 的 Component Performance Track(`react-dom-client.development.js`
 *  `logComponentRender`)對每個「props identity 變了」的 re-render 打一筆 `performance.measure`
 *  (含 Changed Props diff 的 detail,~1.8 KB);Chrome 的 User Timing buffer **沒有上限、不在 V8
 *  heap、不自動回收**。本 app 每則 WS 訊息都讓整棵樹 re-render → 實測 632 筆/秒 ≈ 1.1 MB/s,
 *  看盤數小時後 renderer 膨脹到 10 GB 級 → Aw Snap(證據:docs/research/2026-08-19-browser-crash-scan.md)。
 *
 *  修法 = 條目數到閾值就清。**用 PerformanceObserver 不用 setInterval**:看盤分頁常在背景,
 *  Chrome 對隱藏分頁的 timer 做 intensive throttling(實測 20 s 只跑 7 次 1 s interval),
 *  observer 回呼不受節流(同 20 s 256 次)。
 *
 *  只在 `import.meta.env.DEV` 安裝(production build 沒有那段 React 程式,也不該替別人的效能
 *  工具清 buffer);app 自身不用 performance.mark/measure,清除不影響邏輯;DevTools Performance
 *  錄製在 measure 發出當下就擷取了,事後清 buffer 不影響錄到的 track。 */

export interface UserTimingGuardOptions {
  /** 條目數上限;達到即清空。5,000 筆 × ~1.8 KB ≈ 9 MB 的暫存上限,對 DevTools 即時觀察夠用也夠小。 */
  maxEntries: number;
}

/** 回傳 dispose;HMR / 測試用。缺 PerformanceObserver / clearMeasures 的環境直接 no-op。 */
export function installUserTimingGuard({ maxEntries }: UserTimingGuardOptions): () => void {
  if (typeof PerformanceObserver !== "function" || typeof performance.clearMeasures !== "function") {
    return () => {};
  }
  const observer = new PerformanceObserver(() => {
    if (performance.getEntriesByType("measure").length >= maxEntries) {
      performance.clearMeasures();
      performance.clearMarks();
    }
  });
  observer.observe({ type: "measure" });
  return () => observer.disconnect();
}
