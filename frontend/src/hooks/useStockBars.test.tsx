/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { inTradingHours, MINUTE_DAYS, useStockBars } from "@/hooks/useStockBars";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ bars: [] })));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function urls(): string[] {
  return fetchMock.mock.calls.map((c) => String(c[0]));
}

describe("inTradingHours(台北本機時區)", () => {
  // 2026-07-29 是週三;2026-08-01/02 是週六/日
  it("平日 09:01–13:35 為真,域外為假", () => {
    const at = (h: number, m: number) => new Date(2026, 6, 29, h, m);
    expect(inTradingHours(at(9, 0))).toBe(false);
    expect(inTradingHours(at(9, 1))).toBe(true);
    expect(inTradingHours(at(11, 0))).toBe(true);
    expect(inTradingHours(at(13, 35))).toBe(true);
    expect(inTradingHours(at(13, 36))).toBe(false);
  });

  it("週末恆假(P1-3:否則整個週末每 60s 空打 TC4 約 30 秒)", () => {
    expect(new Date(2026, 7, 1, 11, 0).getDay()).toBe(6); // 前提自檢
    expect(inTradingHours(new Date(2026, 7, 1, 11, 0))).toBe(false); // 週六
    expect(inTradingHours(new Date(2026, 7, 2, 11, 0))).toBe(false); // 週日
  });
});

describe("useStockBars 取數條件", () => {
  it("intraday 模式不取數(江波圖走既有即時 accum)", () => {
    renderHook(() => useStockBars("2330", "intraday", 5), { wrapper });
    expect(urls().filter((u) => u.includes("/api/stock/bars")).length).toBe(0);
  });

  it("code=null 不取數", () => {
    renderHook(() => useStockBars(null, "day", 5), { wrapper });
    expect(urls().filter((u) => u.includes("/api/stock/bars")).length).toBe(0);
  });

  it("日K:tf=D 且 query string 不帶 days(D-15)", async () => {
    renderHook(() => useStockBars("2330", "day", 5), { wrapper });
    await waitFor(() => expect(urls().some((u) => u.includes("/api/stock/bars"))).toBe(true));
    const url = urls().find((u) => u.includes("/api/stock/bars"))!;
    expect(url).toContain("tf=D");
    expect(url).not.toContain("days=");
  });

  it("分K:tf=1 且帶 days", async () => {
    renderHook(() => useStockBars("2330", "m1", 10), { wrapper });
    await waitFor(() => expect(urls().some((u) => u.includes("/api/stock/bars"))).toBe(true));
    const url = urls().find((u) => u.includes("/api/stock/bars"))!;
    expect(url).toContain("tf=1");
    expect(url).toContain("days=10");
  });

  it("5分K 與 1分K 共用同一份 tf=1 資料(前端聚合,不多打一次)", async () => {
    const { unmount } = renderHook(() => useStockBars("2330", "m1", 5), { wrapper });
    await waitFor(() => expect(urls().length).toBeGreaterThan(0));
    unmount();
    const before = urls().length;
    renderHook(() => useStockBars("2330", "m5", 5), { wrapper });
    await waitFor(() => expect(urls().length).toBe(before + 1)); // 新 client → 各自一次
    expect(urls()[before]).toContain("tf=1");
  });

  // days 已固定為 MINUTE_DAYS(往前鈕移除),但 query key 仍含 days —— 這條保住
  // 「days 進 key」的契約,之後若要恢復可變天數不會靜默失效
  it("days 改變會重新取數(query key 含 days)", async () => {
    const { rerender } = renderHook(({ d }: { d: number }) => useStockBars("2330", "m1", d), {
      wrapper,
      initialProps: { d: 5 },
    });
    await waitFor(() => expect(urls().some((u) => u.includes("days=5"))).toBe(true));
    rerender({ d: 10 });
    await waitFor(() => expect(urls().some((u) => u.includes("days=10"))).toBe(true));
  });

  it("m2…m10 一律走 tf=1(前端聚合,不打新 endpoint)", async () => {
    renderHook(() => useStockBars("2330", "m7", MINUTE_DAYS), { wrapper });
    await waitFor(() => expect(urls().some((u) => u.includes("/api/stock/bars"))).toBe(true));
    const url = urls().find((u) => u.includes("/api/stock/bars"))!;
    expect(url).toContain("tf=1");
    expect(url).toContain(`days=${MINUTE_DAYS}`);
  });

  it("錯誤碼依專案契約自 detail.error 解析", async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { error: "BAD_TF" } }), { status: 400 }),
    );
    const { result } = renderHook(() => useStockBars("2330", "day", 5), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect(result.current.error?.message).toBe("BAD_TF");
  });

  it("MINUTE_DAYS 為 30(與後端 clamp 一致;分K 一次載滿不再分頁)", () => {
    expect(MINUTE_DAYS).toBe(30);
  });
});
