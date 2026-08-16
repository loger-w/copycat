/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { groupPollInterval, useGroupSnapshots } from "@/hooks/useGroupSnapshots";

/** 後端 `/api/stock/group-state` 的 payload 形(design v3 SC-4;R15 寫死三鍵 + backfilling)。
 *
 *  `2330` 帶 light_snapshot 的四個加鍵(vwap/high/low/vp);`2317` **刻意不帶** ——
 *  那一格同時是「舊後端」的降級路徑(change-spec §3),缺鍵必須降成 null / 空 Map
 *  而不是 undefined:卡片對 undefined 與 null 的分支不同,而漏帶不會有任何錯誤。 */
const BODY = {
  states: {
    "2330": {
      minutes: { "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0, h: 2_385_000, l: 2_375_000 } },
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
      vwap: 2_379_000,
      high: 2_385_000,
      low: 2_375_000,
      vp: { "2380000": [10, 7, 3], "2375000": [4, 1, 3] },
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

  it("vwap / high / low 帶出;vp 轉成 number key 的 Map(卡片圖與單檔頁同款所需)", async () => {
    const hook = renderHook(() => useGroupSnapshots(["2330", "2317"], true), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toBeTruthy());
    const a = hook.result.current.data!["2330"]!;
    expect(a.vwap).toBe(2_379_000);
    expect(a.high).toBe(2_385_000);
    expect(a.low).toBe(2_375_000);
    expect(a.vp instanceof Map).toBe(true);
    // key 是 number 不是字串:幾何層拿它與毫元價位比對,字串鍵的 Map 永遠 miss
    expect(a.vp.get(2_380_000)).toEqual({ t: 10, o: 7, i: 3 });
    expect(a.vp.get(2_375_000)).toEqual({ t: 4, o: 1, i: 3 });
    expect(a.vp.size).toBe(2);
  });

  it("舊後端缺四鍵 → null / 空 Map 降級(不是 undefined)", async () => {
    const hook = renderHook(() => useGroupSnapshots(["2330", "2317"], true), { wrapper });
    await waitFor(() => expect(hook.result.current.data).toBeTruthy());
    const b = hook.result.current.data!["2317"]!;
    expect(b.vwap).toBeNull();
    expect(b.high).toBeNull();
    expect(b.low).toBeNull();
    expect(b.vp instanceof Map).toBe(true);
    expect(b.vp.size).toBe(0);
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
