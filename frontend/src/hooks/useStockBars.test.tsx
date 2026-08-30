/** @vitest-environment jsdom */
import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MINUTE_DAYS,
  barsPollInterval,
  useStockBars,
  type BarsPayload,
} from "@/hooks/useStockBars";
import { isoLocalDate } from "@/lib/trading-calendar";
import { inTradingHours } from "@/lib/trading-hours";

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ bars: [] })));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  focusManager.setFocused(undefined); // 跨日測試手動切過 focus 的還原,避免外溢到別檔
});

/** 與 `useMarketBars.test.ts` / `useFuturesBars.test.ts` 同簽章:一顆 client 跨 render 穩定
 *  (舊版每 render new 一顆 → rerender 換 client、observer 重建,量不到同一份 cache)。 */
function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
    renderHook(() => useStockBars("2330", "intraday", 5), { wrapper: wrapper(newClient()) });
    expect(urls().filter((u) => u.includes("/api/stock/bars")).length).toBe(0);
  });

  it("code=null 不取數", () => {
    renderHook(() => useStockBars(null, "day", 5), { wrapper: wrapper(newClient()) });
    expect(urls().filter((u) => u.includes("/api/stock/bars")).length).toBe(0);
  });

  it("日K:tf=D 且 query string 不帶 days(D-15)", async () => {
    renderHook(() => useStockBars("2330", "day", 5), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(urls().some((u) => u.includes("/api/stock/bars"))).toBe(true));
    const url = urls().find((u) => u.includes("/api/stock/bars"))!;
    expect(url).toContain("tf=D");
    expect(url).not.toContain("days=");
  });

  it("分K:tf=1 且帶 days", async () => {
    renderHook(() => useStockBars("2330", "m1", 10), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(urls().some((u) => u.includes("/api/stock/bars"))).toBe(true));
    const url = urls().find((u) => u.includes("/api/stock/bars"))!;
    expect(url).toContain("tf=1");
    expect(url).toContain("days=10");
  });

  it("5分K 與 1分K 共用同一份 tf=1 資料(前端聚合,不多打一次)", async () => {
    const { unmount } = renderHook(() => useStockBars("2330", "m1", 5), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(urls().length).toBeGreaterThan(0));
    unmount();
    const before = urls().length;
    renderHook(() => useStockBars("2330", "m5", 5), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(urls().length).toBe(before + 1)); // 新 client → 各自一次
    expect(urls()[before]).toContain("tf=1");
  });

  // days 已固定為 MINUTE_DAYS(往前鈕移除),但 query key 仍含 days —— 這條保住
  // 「days 進 key」的契約,之後若要恢復可變天數不會靜默失效
  it("days 改變會重新取數(query key 含 days)", async () => {
    const { rerender } = renderHook(({ d }: { d: number }) => useStockBars("2330", "m1", d), {
      wrapper: wrapper(newClient()),
      initialProps: { d: 5 },
    });
    await waitFor(() => expect(urls().some((u) => u.includes("days=5"))).toBe(true));
    rerender({ d: 10 });
    await waitFor(() => expect(urls().some((u) => u.includes("days=10"))).toBe(true));
  });

  it("m2…m10 一律走 tf=1(前端聚合,不打新 endpoint)", async () => {
    renderHook(() => useStockBars("2330", "m7", MINUTE_DAYS), { wrapper: wrapper(newClient()) });
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
    const { result } = renderHook(() => useStockBars("2330", "day", 5), { wrapper: wrapper(newClient()) });
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect(result.current.error?.message).toBe("BAD_TF");
  });

  it("MINUTE_DAYS 為 30(與後端 clamp 一致;分K 一次載滿不再分頁)", () => {
    expect(MINUTE_DAYS).toBe(30);
  });
});

// 🔴 N-8 / SC-4:空且非 ok 的結果要能自己走出來。原本 tf=D 空結果 staleTime ∞ 釘死到
// remount = 零流量,TC4 慢一次就永遠停在「無 K 線資料」。20s > 後端 15s 負向快取 TTL,
// 每輪重試都真打 TC4,不會撞負向快取空轉。
describe("barsPollInterval(SC-4 純函式)", () => {
  const empty = (status: BarsPayload["status"]): BarsPayload => ({ bars: [], status });
  const filled: BarsPayload = {
    bars: [{ t: "2026-08-05", o: 1, h: 1, l: 1, c: 1, v: 1 }],
    status: "timeout",
  };

  it("空 + 非 ok → 20_000(日K 與分K、盤中與盤外皆同)", () => {
    expect(barsPollInterval(empty("timeout"), true, false)).toBe(20_000);
    expect(barsPollInterval(empty("disconnected"), true, false)).toBe(20_000);
    expect(barsPollInterval(empty("timeout"), false, true)).toBe(20_000);
  });

  it("空 + ok → 既有邏輯(日K false;分K 依交易時段)", () => {
    expect(barsPollInterval(empty("ok"), true, false)).toBe(false);
    expect(barsPollInterval(empty("ok"), false, true)).toBe(60_000);
    expect(barsPollInterval(empty("ok"), false, false)).toBe(false);
  });

  it("非空 + 非 ok → 既有邏輯,不觸發 20s(Out of scope 3:有資料就照常畫)", () => {
    expect(barsPollInterval(filled, true, false)).toBe(false);
    expect(barsPollInterval(filled, false, true)).toBe(60_000);
    expect(barsPollInterval(filled, false, false)).toBe(false);
  });

  it("data 尚未到位(undefined)→ 既有邏輯", () => {
    expect(barsPollInterval(undefined, true, false)).toBe(false);
    expect(barsPollInterval(undefined, false, true)).toBe(60_000);
  });
});

// 接線測試(R3):純函式綠不足以證明 refetchInterval 真的吃它 —— TanStack v5 函式形
// refetchInterval 若讀閉包裡的 data 會恆為初值(undefined),純函式測全綠但線沒接上。
describe("useStockBars 非 ok 空態自動重試接線(SC-4)", () => {
  function barsCalls(): number {
    return urls().filter((u) => u.includes("/api/stock/bars")).length;
  }

  afterEach(() => {
    vi.useRealTimers();
  });

  it("tf=D 空 + timeout:20s 後真的重打", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ bars: [], status: "timeout" })),
    );
    vi.useFakeTimers();
    renderHook(() => useStockBars("2330", "day", 5), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(50);
    expect(barsCalls()).toBe(1);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(barsCalls()).toBe(2);
  });

  it("tf=D 空 + ok:前進 60s 仍只打一次(同日曆日內不重抓;界見 msUntilDayRollover)", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ bars: [], status: "ok" })),
    );
    vi.useFakeTimers();
    renderHook(() => useStockBars("2330", "day", 5), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(50);
    expect(barsCalls()).toBe(1);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(barsCalls()).toBe(1);
  });

  // R6:未知 status 在 fetchBars 就被正規化成 ok → 不得因 `!== "ok"` 而輪詢
  it("tf=D 空 + 未知 status:正規化成 ok,前進 20s 不重打", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ bars: [], status: "weird" })),
    );
    vi.useFakeTimers();
    renderHook(() => useStockBars("2330", "day", 5), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(50);
    expect(barsCalls()).toBe(1);
    await vi.advanceTimersByTimeAsync(20_000);
    expect(barsCalls()).toBe(1);
  });
});

// bug/daily-bars-siblings-rollover(next-time 08-30 節第 3 條;pr-151-review F-03):preview 整天掛著跨過
// 午夜後個股頁日 K 停在昨天的快照(個股 overlay 走後端 `date < today` + 日期鍵,不受影響)。症狀、界與
// 三條鐵律 (a)(b)(c) 都寫在 `useFuturesBars.ts::msUntilDayRollover`;本 describe 沿 `useFuturesBars.test.ts`
// 最後兩個 describe,鐵律 ↔ 測試的對應同 `useMarketBars.test.ts` 同名 describe 前言。
describe("useStockBars 日 K 跨日曆日(bug/daily-bars-siblings-rollover)", () => {
  /** D = 2026-08-05(週三)。D 當天的請求回「D 部分 bar」快照;D+1 起回「D 完成 + D+1 部分」。 */
  const D1_ISO = "2026-08-06";
  const D_SNAPSHOT = [
    { t: "2026-08-04", o: 1, h: 3, l: 1, c: 2, v: 10 },
    { t: "2026-08-05", o: 2, h: 2, l: 2, c: 2, v: 1 }, // 09:00 時的部分 bar
  ];
  const D1_SNAPSHOT = [
    { t: "2026-08-04", o: 1, h: 3, l: 1, c: 2, v: 10 },
    { t: "2026-08-05", o: 2, h: 9, l: 1, c: 8, v: 99 }, // D 完成
    { t: "2026-08-06", o: 8, h: 8, l: 8, c: 8, v: 1 },
  ];
  /** D+1 起先失敗 `failTimes` 發(503),之後照牆鐘回快照。 */
  function stubFetchByWallClock(failTimes = 0) {
    let failLeft = failTimes;
    fetchMock.mockImplementation(async () => {
      const d1 = isoLocalDate(new Date()) >= D1_ISO;
      if (d1 && failLeft > 0) {
        failLeft -= 1;
        return new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 });
      }
      const bars = d1 ? D1_SNAPSHOT : D_SNAPSHOT;
      return new Response(JSON.stringify({ bars, status: "ok" }));
    });
  }
  const dayCalls = () => urls().filter((u) => u.includes("tf=D")).length;
  /** 模擬 StockChart 吃個股 WS 的重繪節奏:每 `everyMs` 一次 rerender、持續 `forMs`。 */
  async function rerenderBurst(
    rerender: (p: { tick: number }) => void,
    forMs: number,
    everyMs: number,
  ) {
    for (let t = 0; t < forMs; t += everyMs) {
      rerender({ tick: t });
      await vi.advanceTimersByTimeAsync(everyMs);
    }
  }

  it("人一直在個股頁跨過午夜 → 00:01 重抓一次,cache 不停在昨天的快照", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0)); // D 09:00,preview 開著
    stubFetchByWallClock();
    const { result } = renderHook(() => useStockBars("2330", "day", MINUTE_DAYS), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(dayCalls()).toBe(1);
    expect(result.current.data?.bars).toEqual(D_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(14 * 60 * 60_000 + 59 * 60_000); // 23:59
    expect(dayCalls()).toBe(1);
    await vi.advanceTimersByTimeAsync(90_000); // D+1 00:00:30:午夜過了但還在 slack 內
    expect(dayCalls()).toBe(1);
    await vi.advanceTimersByTimeAsync(31_000); // 00:01:01
    expect(dayCalls()).toBe(2);
    // 使用者的症狀:D+1 早上 K 線末根仍是昨天 09:00 那份(D bar 停在部分值、沒有 D+1 那根)
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(9 * 60 * 60_000); // 09:00:xx:同一日曆日內不再打
    expect(dayCalls()).toBe(2);
  });

  // 午夜那一發失敗(後端 503)→ `retry: 1` 用完後 interval 若照樣重算成「下一個午夜」,整個交易日就
  // 停在昨天的快照 —— 與修前同一個症狀(pr-151-review F-05 同款)。
  it("午夜那一發失敗 → 60 s 後再試,成功即回到「下一個午夜」節奏", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubFetchByWallClock(2); // 本體 + retry:1 各失敗一次
    const { result } = renderHook(() => useStockBars("2330", "day", MINUTE_DAYS), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 + 60_000 + 5_000); // 00:01:05:本體 + 1 s 後 retry 皆失敗
    expect(dayCalls()).toBe(3);
    expect(result.current.isError).toBe(true);
    expect(result.current.data?.bars).toEqual(D_SNAPSHOT); // v5:refetch 失敗保留舊 data
    await vi.advanceTimersByTimeAsync(60_000); // 60 s 重試
    expect(dayCalls()).toBe(4);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(10 * 60_000); // 成功後不再每 60 s 打
    expect(dayCalls()).toBe(4);
  });

  // SC-4 的 20 s 空態重試優先於日界:空 + 非 ok 在 23:59:50 掛上,20 s 後(00:00:10,slack 內)照樣重打。
  it("空 + timeout 跨午夜 → 20 s 空態重試不被日界蓋掉(barsPollInterval 既有行為)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 23, 59, 50));
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ bars: [], status: "timeout" })),
    );
    renderHook(() => useStockBars("2330", "day", MINUTE_DAYS), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(50);
    expect(dayCalls()).toBe(1);
    await vi.advanceTimersByTimeAsync(20_000); // 00:00:10
    expect(dayCalls()).toBe(2);
  });

  // TQ 預設 `refetchIntervalInBackground: false`:分頁在背景時 interval tick 被 focus 閘跳過 ——
  // 回前景那一刻要靠「已過期」+ refetchOnWindowFocus 補上,不是靠 interval。
  it("分頁在背景跨過午夜 → 回前景那一刻重抓", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubFetchByWallClock();
    const { result } = renderHook(() => useStockBars("2330", "day", MINUTE_DAYS), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(dayCalls()).toBe(1);
    focusManager.setFocused(false); // 分頁縮到背景
    await vi.advanceTimersByTimeAsync(11 * 60 * 60_000); // D+1 09:00
    expect(dayCalls()).toBe(1); // 背景不打
    focusManager.setFocused(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(dayCalls()).toBe(2);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
  });

  // 鐵律 (a):StockChart 每則個股 WS 訊息重繪一次,`renderHook` 推進期間不重繪量不到這一維,用 `rerender` 補。
  it("slack 窗內(00:00:10 → 00:00:50)每 100 ms 重繪 → 00:01:01 照樣重抓,不被推到隔天", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubFetchByWallClock();
    const { result, rerender } = renderHook(() => useStockBars("2330", "day", MINUTE_DAYS), {
      initialProps: { tick: -1 },
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(dayCalls()).toBe(1);
    await vi.advanceTimersByTimeAsync(15 * 60 * 60_000 + 10_000); // D+1 00:00:10
    await rerenderBurst(rerender, 40_000, 100); // → 00:00:50,400 次重繪
    expect(dayCalls()).toBe(1); // 還在 slack 內
    await vi.advanceTimersByTimeAsync(11_000); // 00:01:01
    expect(dayCalls()).toBe(2);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(9 * 60 * 60_000); // 09:00:xx:同日不再打
    expect(dayCalls()).toBe(2);
  });

  // 鐵律 (c) 前半 + (b) 後半:跨秒必須看到 1 是生效自檢,也是 `dataUpdatedAt` 版的死穴(跨 render 恆同值 → 0)。
  it("同一秒內重繪 50 次 → setInterval 零重排(秒級量化);跨秒重繪一次 → 恰 1 次", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubFetchByWallClock();
    const { rerender } = renderHook(() => useStockBars("2330", "day", MINUTE_DAYS), {
      initialProps: { tick: -1 },
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0); // 首發落地 → interval 武裝
    const spy = vi.spyOn(globalThis, "setInterval");
    await rerenderBurst(rerender, 500, 10); // 09:00:00.000 → 09:00:00.500,50 次重繪
    expect(spy).toHaveBeenCalledTimes(0);
    await vi.advanceTimersByTimeAsync(500); // 09:00:01.000:回值少 1 s → TQ 重排一次
    rerender({ tick: 999 });
    await vi.advanceTimersByTimeAsync(0);
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
