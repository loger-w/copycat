/** @vitest-environment jsdom */
import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
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
  focusManager.setFocused(undefined); // 測試內手動切過 focus 的還原,避免外溢到別檔
});

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

// client 建在測試作用域、不進 render path(review A-4;樣板 useBreadthRows.test.ts)—
// wrapper 若被重 render 不會重建 client,跨輪計數斷言才站得住
function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

/** fake-timer 推進包 act:timer 驅動的 TQ 通知(macrotask)與 React state 更新在
 *  推進中一併 flush,`result.current` 斷言才不會讀到舊值 */
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
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
    const hook = renderHook(() => useStockNames(), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(hook.result.current.data).toBeTruthy());
    expect(hook.result.current.data).toEqual([{ code: "2330", name: "台積電" }]);
  });

  it("names 欄位缺失 → 空陣列不炸(提示列不出現,直接打股號仍可用)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ count: 0 }))));
    const hook = renderHook(() => useStockNames(), { wrapper: wrapper(newClient()) });
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
    const hook = renderHook(() => useStockNames(), { wrapper: wrapper(newClient()) });
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
    const hook = renderHook(() => useStockNames(), { wrapper: wrapper(newClient()) });
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
    const hook = renderHook(() => useStockNames(), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(hook.result.current.isError).toBe(true), { timeout: 5000 });
    expect((hook.result.current.error as Error).message).toBe("HTTP_500");
  });

  // 🔴 錯誤終態輪詢收斂(SC-1,拍板:停止不是退避):server 永久不可用(404 / 舊 build)
  // 時舊版每 3s 無限輪詢;連續失敗達上限後應停(visibilitychange 仍是停止後的復原後門)
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
    const hook = renderHook(() => useStockNames(), { wrapper: wrapper(newClient()) });
    await advance(1000);
    // 先確立真的 success(review B-3:「停止」與「卡在 fetching」不可同綠)
    expect(hook.result.current.data).toEqual([{ code: "2330", name: "台積電" }]);
    expect(fetchMock.mock.calls.length).toBe(1);
    await advance(10_000); // 超過 3 個輪詢週期
    expect(fetchMock.mock.calls.length).toBe(1);
  });

  it("永久失敗:達上限即停;visibilitychange 後門再失敗仍停、成功即復原", async () => {
    vi.useFakeTimers();
    let ok = false;
    const fetchMock = vi.fn(async () =>
      ok
        ? new Response(JSON.stringify({ names: [{ code: "2330", name: "台積電" }], count: 1 }))
        : new Response("proxy error", { status: 500 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const hook = renderHook(() => useStockNames(), { wrapper: wrapper(newClient()) });
    // 節奏探針(review B-2,鎖 wiring 面的 3s):首輪兩次嘗試(t=0 + 1s retry)後,
    // 第 3 次最早在 t=3000 —— 對「interval 從 mount 起算」與「每次 state 更新重啟」
    // 兩種排程語意都成立;wiring 節奏被縮短(如 250ms)必紅
    await advance(2500);
    expect(fetchMock.mock.calls.length).toBe(2);
    await advance(3000); // t=5500:恰第二輪結束(兩語意皆 4 次)
    expect(fetchMock.mock.calls.length).toBe(4);
    // 推進到不動點(review B-4:不假設每輪恰 4s,retry 參數變動時以紅燈顯性失敗)
    let prev = -1;
    for (let i = 0; i < 200 && prev !== fetchMock.mock.calls.length; i++) {
      prev = fetchMock.mock.calls.length;
      await advance(4000);
    }
    // 每輪恰兩次嘗試(retry: 1)→ 總次數封頂;精確值同時鎖 retry:1 與 errorUpdateCount 語意
    const settled = fetchMock.mock.calls.length;
    expect(settled).toBe(2 * NAMES_MAX_ERROR_CYCLES);
    await advance(60_000);
    expect(fetchMock.mock.calls.length).toBe(settled);
    // 停止後唯一自動後門 = 分頁 visibilitychange(review A-1/B-1:v5 focusManager 不聽
    // 純 window focus)。後門再失敗 → 燒一輪(2 次嘗試)後仍停(spec Edge case 2 前半)
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    await advance(2000);
    expect(fetchMock.mock.calls.length).toBe(settled + 2);
    await advance(60_000);
    expect(fetchMock.mock.calls.length).toBe(settled + 2);
    // 後門成功 → 復原且即停(Edge case 2 後半 + W-2)
    ok = true;
    focusManager.setFocused(false);
    focusManager.setFocused(true);
    await advance(2000);
    expect(hook.result.current.data).toEqual([{ code: "2330", name: "台積電" }]);
    expect(fetchMock.mock.calls.length).toBe(settled + 3);
    await advance(30_000);
    expect(fetchMock.mock.calls.length).toBe(settled + 3);
  });
});
