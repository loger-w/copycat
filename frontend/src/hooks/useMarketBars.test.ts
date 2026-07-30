/** @vitest-environment jsdom */
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useMarketBars } from "@/hooks/useMarketBars";

const META = {
  source: "tc4_dk",
  coverage_from: "2026-07-01",
  coverage_to: "2026-07-30",
  partial_last: false,
  volume: true,
  refusal: null,
  synth_since: null,
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
      return new Response(JSON.stringify({ key: "TWSE", tf: "D", bars: [], meta: META }));
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useMarketBars", () => {
  it("intraday 不打 API(enabled=false)", () => {
    renderHook(() => useMarketBars("TWSE", "intraday"), { wrapper: wrapper(newClient()) });
    expect(urls).toEqual([]);
  });

  it("D / W / M 各自一把 query key,且**不含 days**(忽略的參數進 key 會產生等價 cache)", async () => {
    const client = newClient();
    const w = wrapper(client);
    renderHook(() => useMarketBars("TWSE", "day"), { wrapper: w });
    renderHook(() => useMarketBars("TWSE", "week"), { wrapper: w });
    renderHook(() => useMarketBars("TWSE", "month"), { wrapper: w });
    await waitFor(() => expect(urls.length).toBe(3));
    expect(urls.map((u) => u.split("?")[1])).toEqual(["tf=D", "tf=W", "tf=M"]);
    const keys = client
      .getQueryCache()
      .getAll()
      .map((q) => q.queryKey);
    expect(keys).toEqual([
      ["market-bars", "TWSE", "D"],
      ["market-bars", "TWSE", "W"],
      ["market-bars", "TWSE", "M"],
    ]);
  });

  it("分 K 的 query key 含 days,且 2–90 分共用同一份 tf=1 原料", async () => {
    const client = newClient();
    const w = wrapper(client);
    renderHook(() => useMarketBars("TWSE", "m1"), { wrapper: w });
    renderHook(() => useMarketBars("TWSE", "m90"), { wrapper: w });
    await waitFor(() => expect(urls.length).toBeGreaterThan(0));
    const keys = client
      .getQueryCache()
      .getAll()
      .map((q) => q.queryKey);
    expect(keys).toEqual([["market-bars", "TWSE", "1", 30]]); // 同一把 key = 只打一次
    expect(urls).toEqual(["/api/market/bars/TWSE?tf=1&days=30"]);
  });

  it("標的不同 → key 不同(換標的要換料)", async () => {
    const client = newClient();
    const w = wrapper(client);
    renderHook(() => useMarketBars("TWSE", "day"), { wrapper: w });
    renderHook(() => useMarketBars("MXF", "day"), { wrapper: w });
    await waitFor(() => expect(urls.length).toBe(2));
    expect(urls).toEqual(["/api/market/bars/TWSE?tf=D", "/api/market/bars/MXF?tf=D"]);
  });

  it("非交易時段不輪詢(refetchInterval 為 false)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 6, 30, 20, 0)); // 週四 20:00,日盤已收
    const { result } = renderHook(() => useMarketBars("TWSE", "m1"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(result.current.isFetching || result.current.isSuccess).toBe(true);
    const before = urls.length;
    await vi.advanceTimersByTimeAsync(180_000); // 三個輪詢週期
    expect(urls.length).toBe(before);
  });

  it("HTTP 錯誤 → error 帶 detail.error 錯誤碼", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: { error: "BAD_KEY" } }), { status: 400 }),
      ),
    );
    const { result } = renderHook(() => useMarketBars("TWSE", "day"), {
      wrapper: wrapper(newClient()),
    });
    // hook 內 retry:1 覆寫 defaultOptions → 要等一次重試(與 useStockBars 同慣例)
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect((result.current.error as Error).message).toBe("BAD_KEY");
  });
});
