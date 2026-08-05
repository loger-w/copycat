/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useOiLevels } from "@/hooks/useOiLevels";

const RESP = {
  date: "2026-08-04",
  contract: "202608",
  strikes: [
    { strike: 23500, call_oi: 5_000, put_oi: 12_000 },
    { strike: 25000, call_oi: 14_000, put_oi: 2_000 },
  ],
};

let urls: string[] = [];

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  urls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url));
      return new Response(JSON.stringify(RESP));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useOiLevels(SC-11)", () => {
  it("抓 /api/futures/oi-levels 並回傳 strikes", async () => {
    const { result } = renderHook(() => useOiLevels(), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(result.current.data).toEqual(RESP));
    expect(urls).toEqual(["/api/futures/oi-levels"]);
  });

  it("多個消費端共用同一把 key(一天只需一份)", async () => {
    const client = newClient();
    const w = wrapper(client);
    renderHook(() => useOiLevels(), { wrapper: w });
    renderHook(() => useOiLevels(), { wrapper: w });
    await waitFor(() => expect(urls.length).toBeGreaterThan(0));
    expect(urls.length).toBe(1);
    expect(
      client
        .getQueryCache()
        .getAll()
        .map((q) => q.queryKey),
    ).toEqual([["oi-levels"]]);
  });

  // R14:降級設定真的關著 —— throwOnError 若為 true,錯誤會在 render 期拋出去
  // 打掉整個期貨頁;OI 線只是輔助 overlay,消失即可。
  it("HTTP 500 → 不 throw、data 維持 undefined(線消失即降級)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 500 })));
    const { result } = renderHook(() => useOiLevels(), { wrapper: wrapper(newClient()) });
    // hook 內 retry:1 → 要等一次重試(exponential backoff 初次 1s)
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect(result.current.data).toBeUndefined();
    expect((result.current.error as Error).message).toBe("HTTP_500");
  });
});
