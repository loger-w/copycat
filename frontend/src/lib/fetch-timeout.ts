/** `fetch` 加一道 timeout(bug/futures-tab-reactivate-refetch)。
 *
 *  TanStack Query 對同一個 query 在飛時,後續所有 refetch 都併進**同一個 promise**
 *  (`query.js` 的 dedup);`fetch` 本身沒有 timeout,一趟永不回應 = 那個 query 永久凍結,
 *  畫面上只是「資料停住」,換商品(新 query)才會好。這裡讓每一趟至多等 `timeoutMs`,
 *  超時以 `TimeoutError` 拒絕 → TQ 走 error / retry / 下一輪輪詢,凍結有上界。
 *
 *  **不用 `AbortSignal.any` / `AbortSignal.timeout`**:jsdom 與舊 Chrome 支援不齊,手寫一顆
 *  AbortController 把「外層 signal(TQ 取消)」與「計時器」都接上,成功 / 失敗都清計時器。
 *
 *  純函式、零 React;caller 自己決定 timeoutMs(bars 那條路是 `useFuturesBars.BARS_FETCH_TIMEOUT_MS`)。 */
export interface FetchWithTimeoutOptions {
  timeoutMs: number;
  /** 外層(TanStack Query queryFn context)的 signal;abort 時原樣轉發 reason。 */
  signal?: AbortSignal;
  init?: RequestInit;
}

export async function fetchWithTimeout(
  url: string,
  { timeoutMs, signal, init }: FetchWithTimeoutOptions,
): Promise<Response> {
  const ctrl = new AbortController();
  const onOuterAbort = () => ctrl.abort(signal?.reason);
  if (signal !== undefined) {
    if (signal.aborted) ctrl.abort(signal.reason);
    else signal.addEventListener("abort", onOuterAbort, { once: true });
  }
  const timer = setTimeout(
    () => ctrl.abort(new DOMException(`fetch ${url} 超過 ${timeoutMs} ms 未回應`, "TimeoutError")),
    timeoutMs,
  );
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onOuterAbort);
  }
}
