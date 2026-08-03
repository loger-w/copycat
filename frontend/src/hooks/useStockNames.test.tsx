/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useStockNames } from "@/hooks/useStockNames";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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

  // 🔴 M9:`null` 是合法 JSON,`.catch(() => ({}))` 攔不到它 —— 存取 `null.detail`
  // 會拋 TypeError 逸出 queryFn,錯誤訊息變成 TypeError 文字而不是錯誤碼
  it("body 為合法 JSON null → 退回 HTTP_<status>,不讓 TypeError 逸出", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("null", { status: 500 })));
    const hook = renderHook(() => useStockNames(), { wrapper: wrap });
    await waitFor(() => expect(hook.result.current.isError).toBe(true), { timeout: 5000 });
    expect((hook.result.current.error as Error).message).toBe("HTTP_500");
  });
});
