/** @vitest-environment jsdom */
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useMarketBars } from "@/hooks/useMarketBars";
import { isoLocalDate } from "@/lib/trading-calendar";

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
  cleanup(); // 沒有 globals → RTL 不自動 cleanup;上一條留下的輪詢 hook 會把請求灌進下一條的 urls
  vi.unstubAllGlobals();
  vi.useRealTimers();
  focusManager.setFocused(undefined); // 跨日測試手動切過 focus 的還原,避免外溢到別檔
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

  // (review round-2 XR-4)分 K 這條路在**當日段每次都真走 TC4 SubHistory**,與
  // REALTIME 搶同一把 `api.lock` —— tab 切走後還每 60 秒打一發,是看不見的成本。
  // 同頁的 R3/R4 區塊與 FuturesPage 都已經吃 `active` gate,只有 R1 這兩張圖沒有。
  it("盤中 + active 未給(預設 true)→ 照 60 秒輪詢", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0)); // 週四 10:00,盤中
    renderHook(() => useMarketBars("TWSE", "m1"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.length).toBe(1);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(urls.length).toBe(2);
  });

  it("active=false → 盤中也不背景輪詢(掛載仍抓一次)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 6, 10, 0));
    renderHook(() => useMarketBars("TWSE", "m1", false), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.length).toBe(1);
    await vi.advanceTimersByTimeAsync(180_000); // 三個輪詢週期
    expect(urls.length).toBe(1);
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

// bug/daily-bars-siblings-rollover(next-time 08-30 節第 3 條;pr-151-review F-03):preview 整天掛著跨過
// 午夜後日 / 週 / 月 K 停在昨天的快照。症狀、界(日曆午夜 + slack)與三條鐵律 (a)(b)(c) 都寫在
// `lib/day-bars-rollover.ts::msUntilDayRollover`;本 describe 沿 `useFuturesBars.test.ts` 最後兩個 describe。
// 鐵律對應的測試:(a) 界嚴格在 from 之後 → 「slack 窗內每 100 ms 重繪」;(b) interval 不吃
// `dataUpdatedAt` → 「同一秒重繪 … 跨秒恰 1 次」後半的生效自檢(`dataUpdatedAt` 版跨秒回同值 → 0 ≠ 1;
// 本 hook 無 `subscribed`,沒有期指那條「20:00 切回武裝 15 h」的直接情境);(c) 秒級量化 → 同一條前半。
describe("useMarketBars 日 / 週 / 月 K 跨日曆日(bug/daily-bars-siblings-rollover)", () => {
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(String(url));
        const d1 = isoLocalDate(new Date()) >= D1_ISO;
        if (d1 && failLeft > 0) {
          failLeft -= 1;
          return new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 });
        }
        const bars = d1 ? D1_SNAPSHOT : D_SNAPSHOT;
        return new Response(JSON.stringify({ key: "TWSE", tf: "D", bars, meta: META }));
      }),
    );
  }
  const count = (tf: string) => urls.filter((u) => u.includes(`tf=${tf}`)).length;
  /** 模擬 MarketPane 吃指數 WS 的重繪節奏:每 `everyMs` 一次 rerender、持續 `forMs`。 */
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

  it("日 K:人一直在 tab 上跨過午夜 → 00:01 重抓一次,cache 不停在昨天的快照", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0)); // D 09:00,preview 開著
    stubFetchByWallClock();
    const { result } = renderHook(() => useMarketBars("TWSE", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(1);
    expect(result.current.data?.bars).toEqual(D_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(14 * 60 * 60_000 + 59 * 60_000); // 23:59
    expect(count("D")).toBe(1);
    await vi.advanceTimersByTimeAsync(90_000); // D+1 00:00:30:午夜過了但還在 slack 內
    expect(count("D")).toBe(1);
    await vi.advanceTimersByTimeAsync(31_000); // 00:01:01
    expect(count("D")).toBe(2);
    // 使用者的症狀:D+1 早上 K 線末根仍是昨天 09:00 那份(D bar 停在部分值、沒有 D+1 那根)
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(9 * 60 * 60_000); // 09:00:xx:同一日曆日內不再打
    expect(count("D")).toBe(2);
  });

  // 週 / 月 K 與日 K 同一把 key 形狀(`["market-bars", key, tf]`)、同一條 staleTime / interval 分支:
  // 當週 / 當月那根 bar 每個交易日都會變,界同樣是日曆午夜。
  it.each([
    ["week", "W"],
    ["month", "M"],
  ] as const)("%s(tf=%s):跨過午夜同樣在 00:01 重抓(D / W / M 同一條分支)", async (mode, tf) => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubFetchByWallClock();
    renderHook(() => useMarketBars("OTC", mode), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    expect(count(tf)).toBe(1);
    await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 + 30_000); // 00:00:30
    expect(count(tf)).toBe(1);
    await vi.advanceTimersByTimeAsync(31_000); // 00:01:01
    expect(count(tf)).toBe(2);
  });

  // 午夜那一發失敗(後端 503)→ `retry: 1` 用完後 interval 若照樣重算成「下一個午夜」,整個交易日就
  // 停在昨天的基準 —— 與修前同一個症狀(pr-151-review F-05 同款)。
  it("日 K:午夜那一發失敗 → 60 s 後再試,成功即回到「下一個午夜」節奏", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubFetchByWallClock(2); // 本體 + retry:1 各失敗一次
    const { result } = renderHook(() => useMarketBars("TWSE", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 + 60_000 + 5_000); // 00:01:05:本體 + 1 s 後 retry 皆失敗
    expect(count("D")).toBe(3);
    expect(result.current.isError).toBe(true);
    expect(result.current.data?.bars).toEqual(D_SNAPSHOT); // v5:refetch 失敗保留舊 data
    await vi.advanceTimersByTimeAsync(60_000); // 60 s 重試
    expect(count("D")).toBe(4);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(10 * 60_000); // 成功後不再每 60 s 打
    expect(count("D")).toBe(4);
  });

  // pr-159-review F-01(user 拍板 1a):後端 D/W/M 路徑未三態化,TC4 不可用時回 200 + 空 bars
  //(不 raise)——午夜那一發若拿到它,TQ 判 success、好資料被空快照蓋掉,而 interval 已排到明天、
  // staleTime 整天不過期、回焦 refetch 也被 isStaleByTime 擋 → 主圖空白一整天。空 bars 視同失敗:
  // 與 error 同一個 60 s 節奏重試(修前失效樣態只是「昨天的 K 線」,這條路修後不能更差)。
  it("日 K:午夜那一發拿到 200 + 空 bars(TC4 沒開)→ 60 s 後重試,不把空快照鎖到隔天", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    let emptyLeft = 1; // 只有午夜那一發降級;200 不觸發 TQ retry,所以一發就夠
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(String(url));
        const d1 = isoLocalDate(new Date()) >= D1_ISO;
        if (d1 && emptyLeft > 0) {
          emptyLeft -= 1;
          const meta = { ...META, source: "unavailable" };
          return new Response(JSON.stringify({ key: "TWSE", tf: "D", bars: [], meta }));
        }
        const bars = d1 ? D1_SNAPSHOT : D_SNAPSHOT;
        return new Response(JSON.stringify({ key: "TWSE", tf: "D", bars, meta: META }));
      }),
    );
    const { result } = renderHook(() => useMarketBars("TWSE", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(1);
    await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 + 61_000); // D+1 00:01:01:拿到空快照
    expect(count("D")).toBe(2);
    expect(result.current.data?.bars).toEqual([]); // 空快照已落地(修的是「之後救得回來」)
    await vi.advanceTimersByTimeAsync(60_000); // 60 s 重試 → TC4 回來了
    expect(count("D")).toBe(3);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(10 * 60_000); // 資料非空後回到「下一個午夜」節奏
    expect(count("D")).toBe(3);
  });

  // 台股綜合 tab 的 DOM 由 App 以 `hidden` 保留(不 unmount),`active` 只擋分 K 的 60 s 輪詢
  //(review round-2 XR-4)。人在個股頁跨過午夜、早上切回台股綜合 tab → K 線必須是今天的:
  // 斷言落在「切回之後」的資料,不釘「哪一刻打的」(午夜打 / 切回才打都算修好)。
  it("日 K:active=false 跨過午夜再切回 → 切回後資料是 D+1 那份;同日曆日內切回不重抓", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubFetchByWallClock();
    const { result, rerender } = renderHook(
      ({ active }) => useMarketBars("TWSE", "day", active),
      { initialProps: { active: true }, wrapper: wrapper(newClient()) },
    );
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(1);
    await vi.advanceTimersByTimeAsync(6 * 60 * 60_000); // 15:00 切去個股頁
    rerender({ active: false });
    await vi.advanceTimersByTimeAsync(5 * 60 * 60_000); // 20:00 切回
    rerender({ active: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(1); // 同日曆日切回不重抓
    rerender({ active: false }); // 20:00 再切去個股頁,待到 D+1 09:00
    await vi.advanceTimersByTimeAsync(13 * 60 * 60_000);
    rerender({ active: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(2);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
  });

  // review round 1 Spec P-F2:午夜那發失敗恰恰最常發生在人不在的時候(後端沒起來);60 s 重試若吃
  // `active`,人在個股頁就整晚凍結、早上切回還要再等 60 s。日 K 這條整段不吃 `active`。
  it("日 K:active=false 時午夜那一發失敗 → 人還沒切回就在 60 s 後重試成功", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubFetchByWallClock(2);
    const { result } = renderHook(() => useMarketBars("TWSE", "day", false), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 + 60_000 + 5_000); // 00:01:05:兩發皆失敗
    expect(count("D")).toBe(3);
    expect(result.current.isError).toBe(true);
    await vi.advanceTimersByTimeAsync(60_000); // 00:02:05:人仍不在 tab 上
    expect(count("D")).toBe(4);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
  });

  // TQ 預設 `refetchIntervalInBackground: false`:分頁在背景時 interval tick 被 focus 閘跳過 ——
  // 回前景那一刻要靠「已過期」+ refetchOnWindowFocus 補上,不是靠 interval。
  it("日 K:分頁在背景跨過午夜 → 回前景那一刻重抓", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubFetchByWallClock();
    const { result } = renderHook(() => useMarketBars("TWSE", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(1);
    focusManager.setFocused(false); // 分頁縮到背景
    await vi.advanceTimersByTimeAsync(11 * 60 * 60_000); // D+1 09:00
    expect(count("D")).toBe(1); // 背景不打
    focusManager.setFocused(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(2);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
  });

  // 鐵律 (a):MarketPane 每個指數 tick 重繪一次,`renderHook` 推進期間不重繪量不到這一維,用 `rerender` 補。
  it("日 K:slack 窗內(00:00:10 → 00:00:50)每 100 ms 重繪 → 00:01:01 照樣重抓,不被推到隔天", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubFetchByWallClock();
    const { result, rerender } = renderHook(() => useMarketBars("TWSE", "day"), {
      initialProps: { tick: -1 },
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(count("D")).toBe(1);
    await vi.advanceTimersByTimeAsync(15 * 60 * 60_000 + 10_000); // D+1 00:00:10
    await rerenderBurst(rerender, 40_000, 100); // → 00:00:50,400 次重繪
    expect(count("D")).toBe(1); // 還在 slack 內
    await vi.advanceTimersByTimeAsync(11_000); // 00:01:01
    expect(count("D")).toBe(2);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(9 * 60 * 60_000); // 09:00:xx:同日不再打
    expect(count("D")).toBe(2);
  });

  // 鐵律 (c) 前半 + (b) 後半:跨秒必須看到 1 是生效自檢(spy 真的看得到 TQ 的 setInterval),
  // 也是 `dataUpdatedAt` 版的死穴(跨 render 恆同值 → 0)。
  it("日 K:同一秒內重繪 50 次 → setInterval 零重排(秒級量化);跨秒重繪一次 → 恰 1 次", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubFetchByWallClock();
    const { rerender } = renderHook(() => useMarketBars("TWSE", "day"), {
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
