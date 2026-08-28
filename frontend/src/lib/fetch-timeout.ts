/** `fetch` 加一道 timeout(bug/futures-tab-reactivate-refetch)。
 *
 *  TanStack Query 對同一個 query 在飛時,後續所有 refetch 都併進**同一個 promise**
 *  (`query.js` 的 dedup);`fetch` 本身沒有 timeout,一趟永不回應 = 那個 query 永久凍結,
 *  畫面上只是「資料停住」,換商品(新 query)才會好。這裡讓每一趟至多等 `timeoutMs`,
 *  超時以 `TimeoutError` 拒絕 → TQ 走 error / retry / 下一輪輪詢,凍結有上界。
 *
 *  **body 也在 timeout 之內**(review round 1 Spec F-2):`fetch` resolve 只代表 headers 到了,
 *  TCP 半死的典型樣態正是 body 中途停住;所以這裡把 body 整段讀完再回一個**已緩衝**的
 *  `Response`,caller 之後的 `res.json()` / `parseError(res)` 讀的是記憶體,不會再懸。
 *  body 讀取以 `Promise.race` 對 abort —— 不依賴 fetch 實作把 stream 綁到 signal 上(jsdom 不綁)。
 *
 *  **不用 `AbortSignal.any` / `AbortSignal.timeout`**:jsdom 與舊 Chrome 支援不齊,手寫一顆
 *  AbortController 把「外層 signal(TQ 取消)」與「計時器」都接上,成功 / 失敗都清計時器。
 *  TimeoutError 的訊息不帶 URL(它會被 `FuturesChart` 原樣印在畫面上)。
 *
 *  純函式、零 React;caller 自己決定 timeoutMs(bars 那條路是 `useFuturesBars.BARS_FETCH_TIMEOUT_MS`)。 */
export interface FetchWithTimeoutOptions {
  timeoutMs: number;
  /** 外層(TanStack Query queryFn context)的 signal;abort 時原樣轉發 reason。 */
  signal?: AbortSignal;
}

export async function fetchWithTimeout(
  url: string,
  { timeoutMs, signal }: FetchWithTimeoutOptions,
): Promise<Response> {
  const ctrl = new AbortController();
  const onOuterAbort = () => ctrl.abort(signal?.reason);
  if (signal !== undefined) {
    if (signal.aborted) ctrl.abort(signal.reason);
    else signal.addEventListener("abort", onOuterAbort, { once: true });
  }
  const timer = setTimeout(
    () => ctrl.abort(new DOMException(`請求 ${timeoutMs / 1000} 秒未回應,已中止`, "TimeoutError")),
    timeoutMs,
  );
  // body 讀取的 abort 出口:ctrl 一 abort 就拒絕(fetch 實作有沒有把 stream 綁到 signal 都一樣)
  const aborted = new Promise<never>((_resolve, reject) => {
    if (ctrl.signal.aborted) reject(ctrl.signal.reason);
    else ctrl.signal.addEventListener("abort", () => reject(ctrl.signal.reason), { once: true });
  });
  // fetch 自己先拒絕(真 fetch 綁了 signal)時 race 不會消費 aborted,它稍後的拒絕會變 unhandled rejection
  aborted.catch(() => {});
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    const buf = await Promise.race([res.arrayBuffer(), aborted]);
    return new Response(buf, { status: res.status, statusText: res.statusText, headers: res.headers });
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onOuterAbort);
  }
}
