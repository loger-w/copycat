import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchWithTimeout } from "@/lib/fetch-timeout";

/** 模擬真 `fetch` 對 abort 的行為:signal 一 abort 就以 reason 拒絕。 */
function hangingFetch(): ReturnType<typeof vi.fn> {
  return vi.fn((_url: string, init?: RequestInit) => {
    return new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(init.signal!.reason));
    });
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("fetchWithTimeout(bug/futures-tab-reactivate-refetch)", () => {
  it("超過 timeoutMs 仍未回 → 以 TimeoutError 拒絕(永不回的一趟不能把 query 凍住)", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingFetch());
    const p = fetchWithTimeout("/api/x", { timeoutMs: 30_000 });
    const settled = p.then(
      () => "resolved",
      (e: unknown) => (e as Error).name,
    );
    await vi.advanceTimersByTimeAsync(29_999);
    // 還沒到:promise 仍懸著(用 race 證明,不用 sleep)
    expect(await Promise.race([settled, Promise.resolve("pending")])).toBe("pending");
    await vi.advanceTimersByTimeAsync(1);
    expect(await settled).toBe("TimeoutError");
  });

  it("外層 signal(TanStack Query 的取消)abort → 以外層 reason 拒絕,不等 timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingFetch());
    const outer = new AbortController();
    const p = fetchWithTimeout("/api/x", { timeoutMs: 30_000, signal: outer.signal });
    const settled = p.then(
      () => "resolved",
      (e: unknown) => (e as Error).name,
    );
    outer.abort(new DOMException("cancelled", "AbortError"));
    await vi.advanceTimersByTimeAsync(0);
    expect(await settled).toBe("AbortError");
    expect(vi.getTimerCount()).toBe(0); // 計時器一併清掉,不留孤兒 timer
  });

  it("正常回應 → 回已緩衝的 Response(status / body 原樣),且不留下 timeout 計時器", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response('{"ok":1}', { status: 201 })),
    );
    const res = await fetchWithTimeout("/api/x", { timeoutMs: 30_000 });
    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ ok: 1 });
    expect(vi.getTimerCount()).toBe(0);
  });

  // review round 1 Spec F-2:headers 到了不代表回完 —— TCP 半死的典型樣態是 body 中途停住。
  // 只包 fetch 的話,caller 的 res.json() 會在 timeout 之外永遠懸著。
  it("headers 到了但 body 永遠不完 → 仍以 TimeoutError 拒絕(body 讀取也在 timeout 之內)", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(new ReadableStream<Uint8Array>({ start() {} }), { status: 200 })),
    );
    const p = fetchWithTimeout("/api/x", { timeoutMs: 30_000 });
    const settled = p.then(
      () => "resolved",
      (e: unknown) => (e as Error).name,
    );
    await vi.advanceTimersByTimeAsync(30_000);
    expect(await settled).toBe("TimeoutError");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("TimeoutError 的訊息不帶 URL(會被畫面原樣印出)", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", hangingFetch());
    const p = fetchWithTimeout("/api/market/bars/TMF?tf=1", { timeoutMs: 30_000 });
    const settled = p.then(
      () => "resolved",
      (e: unknown) => (e as Error).message,
    );
    await vi.advanceTimersByTimeAsync(30_000);
    const msg = await settled;
    expect(msg).toBe("請求 30 秒未回應,已中止");
    expect(msg).not.toContain("/api/");
  });
});
