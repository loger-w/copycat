/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { groupPollInterval, useGroupSnapshots } from "@/hooks/useGroupSnapshots";

/** 後端 `/api/stock/group-state` 的 payload 形(design v3 SC-4;R15 寫死三鍵 + backfilling) */
const BODY = {
  states: {
    "2330": {
      minutes: { "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0, h: 2_385_000, l: 2_375_000 } },
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
      no_data: false,
      backfilling: false,
    },
    "2317": {
      minutes: {},
      meta: null,
      no_data: true,
      backfilling: true,
    },
  },
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(JSON.stringify(BODY)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useGroupSnapshots", () => {
  it("打單一 batch 端點(逗號分隔 codes),不逐檔請求", async () => {
    const hook = renderHook(() => useGroupSnapshots(["2330", "2317"], true), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/stock/group-state?codes=2330,2317");
  });

  it("minutes 轉成 Map(鍵為數字),meta / noData / backfilling 一併帶出", async () => {
    const hook = renderHook(() => useGroupSnapshots(["2330", "2317"], true), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toBeTruthy());
    const data = hook.result.current.data!;
    const a = data["2330"]!;
    expect(a.minutes instanceof Map).toBe(true);
    expect(a.minutes.get(540)?.c).toBe(2_380_000);
    expect(a.meta?.ref).toBe(2_320_000);
    expect(a.noData).toBe(false);
    expect(a.backfilling).toBe(false);
    const b = data["2317"]!;
    expect(b.minutes.size).toBe(0);
    expect(b.meta).toBeNull();
    expect(b.noData).toBe(true);
    expect(b.backfilling).toBe(true);
  });

  it("空 codes → 零請求(R17:空群組不打端點)", async () => {
    renderHook(() => useGroupSnapshots([], true), { wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("enabled=false → 零請求(切回單檔檢視不再輪詢)", async () => {
    renderHook(() => useGroupSnapshots(["2330"], false), { wrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("非 2xx → error 終態(卡片端據此全部顯示無資料)", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "BAD_CODES" } }), { status: 400 }),
    );
    const hook = renderHook(() => useGroupSnapshots(["2330"], true), { wrapper });
    await waitFor(() => expect(hook.result.current.isError).toBe(true));
    expect(hook.result.current.error?.message).toBe("BAD_CODES");
  });
});

// 輪詢窗抽成純函式才量得到(沿 `barsPollInterval` 慣例):hook 內是函式形
// refetchInterval,值形式只在 render 當下求值 —— 冷門股沒 re-render 就永遠不會開始輪詢。
describe("groupPollInterval", () => {
  it("盤中 60s;盤外不輪詢", () => {
    expect(groupPollInterval(true)).toBe(60_000);
    expect(groupPollInterval(false)).toBe(false);
  });
});
