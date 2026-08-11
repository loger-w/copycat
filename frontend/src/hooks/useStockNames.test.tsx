/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  NAMES_MAX_ERROR_CYCLES,
  namesRefetchInterval,
  useStockNames,
} from "@/hooks/useStockNames";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function wrap({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useStockNames", () => {
  it("回傳 names 陣列", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ names: [{ code: "2330", name: "台積電" }], count: 1 }),
          ),
      ),
    );
    const hook = renderHook(() => useStockNames(), { wrapper: wrap });
    await waitFor(() => expect(hook.result.current.data).toBeTruthy());
    expect(hook.result.current.data).toEqual([{ code: "2330", name: "台積電" }]);
  });

  it("names 欄位缺失 → 空陣列不炸(提示列不出現,直接打股號仍可用)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ count: 0 }))));
    const hook = renderHook(() => useStockNames(), { wrapper: wrap });
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
    expect(hook.result.current.data).toEqual([]);
  });

  it("404 → error 態帶錯誤碼", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 404 }),
      ),
    );
    const hook = renderHook(() => useStockNames(), { wrapper: wrap });
    await waitFor(() => expect(hook.result.current.isError).toBe(true), { timeout: 5000 });
    expect((hook.result.current.error as Error).message).toBe("NOT_READY");
  });

  // 🔴 server 啟動期 lifespan 阻塞(TXO 全鏈回補,數十秒~分鐘級)時 uvicorn 尚未 bind
  // socket → 首載連線被拒(vite proxy 回 500)。`retry: 1` 兩次嘗試在 1-2 秒內用完 →
  // query 落入 error 終態,提示列與側欄股名要等到 window refocus 才出現。
  it("啟動窗內連續失敗後應自動復原(不需 focus / remount)", async () => {
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        if (calls <= 2) return new Response("proxy error", { status: 500 });
        return new Response(
          JSON.stringify({ names: [{ code: "2330", name: "台積電" }], count: 1 }),
        );
      }),
    );
    const hook = renderHook(() => useStockNames(), { wrapper: wrap });
    await waitFor(() => expect(hook.result.current.isError).toBe(true), { timeout: 5000 });
    await waitFor(
      () => expect(hook.result.current.data).toEqual([{ code: "2330", name: "台積電" }]),
      { timeout: 10000 },
    );
  }, 20000);

  // 🔴 M9:`null` 是合法 JSON,`.catch(() => ({}))` 攔不到它 —— 存取 `null.detail`
  // 會拋 TypeError 逸出 queryFn,錯誤訊息變成 TypeError 文字而不是錯誤碼
  it("body 為合法 JSON null → 退回 HTTP_<status>,不讓 TypeError 逸出", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("null", { status: 500 })));
    const hook = renderHook(() => useStockNames(), { wrapper: wrap });
    await waitFor(() => expect(hook.result.current.isError).toBe(true), { timeout: 5000 });
    expect((hook.result.current.error as Error).message).toBe("HTTP_500");
  });

  // 🔴 錯誤終態輪詢收斂(SC-1,拍板:停止不是退避):server 永久不可用(404 / 舊 build)
  // 時舊版每 3s 無限輪詢;連續失敗達上限後應停(refocus 仍是停止後的復原後門)
  it("連續失敗達上限 → refetchInterval 求值為 false(停止)", () => {
    expect(
      namesRefetchInterval({ state: { data: undefined, errorUpdateCount: NAMES_MAX_ERROR_CYCLES } }),
    ).toBe(false);
    expect(
      namesRefetchInterval({
        state: { data: undefined, errorUpdateCount: NAMES_MAX_ERROR_CYCLES + 5 },
      }),
    ).toBe(false);
  });

  // 鎖輪詢節奏(SC-2):literal 3000 不引用常數 —— interval 被改(如 1ms)必須紅
  it("未拿到資料且未達上限 → 每 3000ms 輪詢(literal 鎖節奏)", () => {
    expect(namesRefetchInterval({ state: { data: undefined, errorUpdateCount: 0 } })).toBe(3000);
    expect(
      namesRefetchInterval({
        state: { data: undefined, errorUpdateCount: NAMES_MAX_ERROR_CYCLES - 1 },
      }),
    ).toBe(3000);
  });

  // 鎖停止條件(SC-2,白名單 W-2):拿到資料(含空表)即停,穩態零輪詢
  it("拿到資料(含空表)→ refetchInterval 求值為 false", () => {
    expect(namesRefetchInterval({ state: { data: [], errorUpdateCount: 0 } })).toBe(false);
    expect(
      namesRefetchInterval({
        state: {
          data: [{ code: "2330", name: "台積電" }],
          errorUpdateCount: NAMES_MAX_ERROR_CYCLES,
        },
      }),
    ).toBe(false);
  });

  // next-time 2026-08-10 原案「成功案 sleep 3.5s 斷言 fetch 次數不增」的 fake-timer 等價版
  // (決定性、免 wall-clock;樣板 useBreadthRows.test.ts)
  it("成功後長時間推進,fetch 次數不增(停止真的生效)", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ names: [{ code: "2330", name: "台積電" }], count: 1 })),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useStockNames(), { wrapper: wrap });
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchMock.mock.calls.length).toBe(1);
    await vi.advanceTimersByTimeAsync(10_000); // 超過 3 個輪詢週期
    expect(fetchMock.mock.calls.length).toBe(1);
  });

  it("永久失敗:達上限後 fetch 次數收斂,不再無限輪詢", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(async () => new Response("proxy error", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    renderHook(() => useStockNames(), { wrapper: wrap });
    // 每輪 ≤ 4s(3s interval + retry:1 的 1s backoff),推進到上限輪數用盡為止
    for (let i = 0; i < NAMES_MAX_ERROR_CYCLES + 5; i++) {
      await vi.advanceTimersByTimeAsync(4000);
    }
    // 每輪恰兩次嘗試(retry: 1)→ 上限後總次數封頂
    const settled = fetchMock.mock.calls.length;
    expect(settled).toBe(2 * NAMES_MAX_ERROR_CYCLES);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchMock.mock.calls.length).toBe(settled);
  });
});
