/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FUTURES_MINUTE_DAYS, useFuturesBars } from "@/hooks/useFuturesBars";

const META = {
  source: "tc4_1k",
  coverage_from: "2026-08-03",
  coverage_to: "2026-08-05",
  partial_last: true,
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
      return new Response(JSON.stringify({ key: "TXF", tf: "1", bars: [], meta: META }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useFuturesBars(SC-1/2/3)", () => {
  it("分時與分 K 共用同一份 tf=1 原料,URL 帶 days=5 與 session=allday", async () => {
    const client = newClient();
    const w = wrapper(client);
    renderHook(() => useFuturesBars("TXF", "intraday"), { wrapper: w });
    renderHook(() => useFuturesBars("TXF", "m5"), { wrapper: w });
    renderHook(() => useFuturesBars("TXF", "m60"), { wrapper: w });
    await waitFor(() => expect(urls.length).toBeGreaterThan(0));
    // 同一把 key → 三個 hook 只打一次
    expect(urls).toEqual([`/api/market/bars/TXF?tf=1&days=${FUTURES_MINUTE_DAYS}&session=allday`]);
    expect(FUTURES_MINUTE_DAYS).toBe(5);
    expect(
      client
        .getQueryCache()
        .getAll()
        .map((q) => q.queryKey),
    ).toEqual([["futures-bars", "TXF", "1", 5, "allday"]]);
  });

  it("日 K 走 tf=D,且 key 不含 days / session(忽略的參數進 key 會產生等價 cache)", async () => {
    const client = newClient();
    renderHook(() => useFuturesBars("MXF", "day"), { wrapper: wrapper(client) });
    await waitFor(() => expect(urls.length).toBe(1));
    expect(urls).toEqual(["/api/market/bars/MXF?tf=D"]);
    expect(
      client
        .getQueryCache()
        .getAll()
        .map((q) => q.queryKey),
    ).toEqual([["futures-bars", "MXF", "D"]]);
  });

  it("換商品 → 換料(各自一把 key)", async () => {
    const w = wrapper(newClient());
    renderHook(() => useFuturesBars("TXF", "m1"), { wrapper: w });
    renderHook(() => useFuturesBars("TMF", "m1"), { wrapper: w });
    await waitFor(() => expect(urls.length).toBe(2));
    expect(urls).toEqual([
      "/api/market/bars/TXF?tf=1&days=5&session=allday",
      "/api/market/bars/TMF?tf=1&days=5&session=allday",
    ]);
  });

  it("停輪詢窗(週三 14:00,日盤收→夜盤開)不輪詢", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 14, 0)); // 2026-08-05 週三 14:00
    renderHook(() => useFuturesBars("TXF", "m1"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    const before = urls.length;
    expect(before).toBe(1);
    await vi.advanceTimersByTimeAsync(180_000); // 三個輪詢週期
    expect(urls.length).toBe(before);
  });

  it("夜盤時段(週三 22:00)照 60s 輪詢 —— 日盤那把尺會讓夜盤整段不更新", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0)); // 2026-08-05 週三 22:00
    renderHook(() => useFuturesBars("TXF", "m1"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    const before = urls.length;
    expect(before).toBe(1);
    await vi.advanceTimersByTimeAsync(65_000);
    expect(urls.length).toBeGreaterThan(before);
  });

  it("日 K 不輪詢(已完成日 bar 不會變)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    renderHook(() => useFuturesBars("TXF", "day"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    const before = urls.length;
    await vi.advanceTimersByTimeAsync(180_000);
    expect(urls.length).toBe(before);
  });

  it("HTTP 錯誤 → error 帶 detail.error 錯誤碼", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: { error: "INVALID_SESSION" } }), { status: 400 }),
      ),
    );
    const { result } = renderHook(() => useFuturesBars("TXF", "m1"), {
      wrapper: wrapper(newClient()),
    });
    // hook 內 retry:1 覆寫 defaultOptions → 要等一次重試(與 useMarketBars 同慣例)
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect((result.current.error as Error).message).toBe("INVALID_SESSION");
  });
});
