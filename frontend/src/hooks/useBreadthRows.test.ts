/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useBreadthRows } from "@/hooks/useBreadthRows";

const STATE = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  streaks_ready: true,
  rows: [
    {
      stock_id: "1101",
      name: "台泥",
      market: "twse",
      close: 55.5,
      change_rate: 9.98,
      volume_ratio: 3.2,
      total_amount: 900_000_000,
      limit_up: true,
      limit_down: false,
      touched_limit_up: false,
      touched_limit_down: false,
      streak: 2,
      streak_capped: false,
    },
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
      return new Response(JSON.stringify(STATE));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useBreadthRows(SC-1)", () => {
  it("抓 /api/market/breadth/rows 並回傳全量 state", async () => {
    const client = newClient();
    const { result } = renderHook(() => useBreadthRows(), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.data).toEqual(STATE));
    expect(urls).toEqual(["/api/market/breadth/rows"]);
    expect(
      client
        .getQueryCache()
        .getAll()
        .map((q) => q.queryKey),
    ).toEqual([["breadth-rows"]]);
  });

  it("多個消費端共用同一把 key(列表只需一份 payload)", async () => {
    const client = newClient();
    const w = wrapper(client);
    renderHook(() => useBreadthRows(), { wrapper: w });
    renderHook(() => useBreadthRows(), { wrapper: w });
    await waitFor(() => expect(urls.length).toBeGreaterThan(0));
    expect(urls.length).toBe(1);
  });

  // R10:refetchInterval 是函式形式,交易時段 gate 每次到期重新求值。
  it("交易時段內每 10 秒輪詢一次", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0)); // 週四 10:00,盤中
    renderHook(() => useBreadthRows(), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.length).toBe(1);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(urls.length).toBe(2);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(urls.length).toBe(3);
  });

  it("非交易時段不輪詢(refetchInterval 為 false)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 6, 20, 0)); // 週四 20:00,日盤已收
    renderHook(() => useBreadthRows(), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    const before = urls.length;
    expect(before).toBe(1);
    await vi.advanceTimersByTimeAsync(60_000); // 六個輪詢週期
    expect(urls.length).toBe(before);
  });

  it("HTTP 錯誤 → error 終態帶 detail.error 錯誤碼", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () => new Response(JSON.stringify({ detail: { error: "BOOM" } }), { status: 500 }),
      ),
    );
    const { result } = renderHook(() => useBreadthRows(), { wrapper: wrapper(newClient()) });
    // hook 內 retry:1 覆寫 defaultOptions → 要等一次重試(exponential backoff 初次 1s)
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect(result.current.data).toBeUndefined();
    expect((result.current.error as Error).message).toBe("BOOM");
  });
});
