/** dev-only User Timing guard(2026-08-19 /bug react-dev-measure-leak)。
 *
 *  React 19.2 development build 的 Component Performance Track(`react-dom-client.development.js`
 *  `logComponentRender`)對每個「props identity 變了」的 re-render 打一筆 `performance.measure`
 *  (含 Changed Props diff 的 detail,~1.8 KB);Chrome 的 User Timing buffer **沒有上限、不在 V8
 *  heap、不自動回收**。本 app 每則 WS 訊息都讓整棵樹 re-render → 實測 632 筆/秒 ≈ 1.1 MB/s,
 *  看盤數小時後 renderer 膨脹到 10 GB 級 → Aw Snap(證據:docs/research/2026-08-19-browser-crash-scan.md)。
 *
 *  修法 = 定期清掉。只在 `import.meta.env.DEV` 安裝(production build 沒有那段 React 程式,
 *  也不該替別人的效能工具清 buffer);app 自身不用 performance.mark/measure,清除不影響邏輯;
 *  DevTools Performance 錄製在 measure 發出當下就擷取了,事後清 buffer 不影響錄到的 track。 */

export interface UserTimingGuardOptions {
  /** 清除週期。10 s × 632 筆/秒 ≈ 6,000 筆 ≈ 11 MB 的上限,對 DevTools 即時觀察夠用也夠小。 */
  intervalMs: number;
}

/** 回傳 dispose;HMR / 測試用。`performance.clearMeasures` 不存在的環境直接 no-op。 */
export function installUserTimingGuard({ intervalMs }: UserTimingGuardOptions): () => void {
  if (typeof performance.clearMeasures !== "function") return () => {};
  const timer = setInterval(() => {
    performance.clearMeasures();
    performance.clearMarks();
  }, intervalMs);
  return () => clearInterval(timer);
}
