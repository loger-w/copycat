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
 *  observer 回呼不受節流(同 20 s 256 次)。計數用回呼帶進來的增量累加,不每次
 *  `getEntriesByType` 全表掃描(review C-1:那是 O(buffer)/回呼,加在本來就忙的主執行緒上)。
 *
 *  只在 `import.meta.env.DEV` 安裝(production build 沒有那段 React 程式,也不該替別人的效能
 *  工具清 buffer);app 自身不用 performance.mark/measure,清除不影響邏輯;DevTools Performance
 *  錄製在 measure 發出當下就擷取了,事後清 buffer 不影響錄到的 track。 */

export interface UserTimingGuardOptions {
  /** 條目數上限;達到即清空。5,000 筆 × ~1.8 KB ≈ 9 MB 的暫存上限(峰值再加單一 task 的批量),
   *  對 DevTools 即時觀察夠用也夠小。 */
  maxEntries: number;
}

const noop = (): void => {};

/** 模組層單例:重複 install 回同一個 dispose(review C-4;HMR / 多入口不疊 observer)。 */
let active: (() => void) | null = null;

/** 回傳 dispose;HMR / 測試用。缺 PerformanceObserver / clearMeasures / clearMarks,或 observe 不接受
 *  `{type}`(Performance Timeline Level 1 只認 entryTypes,會丟 TypeError)的環境一律 no-op ——
 *  這支在 main.tsx 頂層同步跑,拋錯 = createRoot 永遠不執行 = dev 白畫面(review C-3)。 */
export function installUserTimingGuard({ maxEntries }: UserTimingGuardOptions): () => void {
  if (active !== null) return active;
  if (
    typeof PerformanceObserver !== "function" ||
    typeof performance.clearMeasures !== "function" ||
    typeof performance.clearMarks !== "function"
  ) {
    return noop;
  }
  let seen = 0;
  const observer = new PerformanceObserver((list) => {
    seen += list.getEntries().length;
    if (seen >= maxEntries) {
      performance.clearMeasures();
      performance.clearMarks();
      seen = 0;
    }
  });
  try {
    observer.observe({ type: "measure" });
  } catch {
    return noop;
  }
  active = () => {
    observer.disconnect();
    active = null;
  };
  return active;
}
