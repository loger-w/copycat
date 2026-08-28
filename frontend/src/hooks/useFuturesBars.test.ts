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
  vi.restoreAllMocks(); // console.warn spy 不外溢到同檔後續測試(review round 1 S F-7)
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

  // 期貨 tab 的 DOM 由 App 以 `hidden` 保留(不 unmount)→ 沒有 active gate 的話
  // 這支 hook 會在使用者看著別的 tab 時整晚輪詢(近全時段窗 ≈ 19h/日打 TC4)
  it("active=false(人不在期貨 tab)→ 夜盤時段也不輪詢", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0)); // active=true 時這個時刻會輪詢
    renderHook(() => useFuturesBars("TXF", "m1", false), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    // bug/futures-tab-reactivate-refetch(事前標該變:原斷言「掛載時仍抓一次」= 1):
    // active=false 現在是 TQ 的 `subscribed: false` —— 沒人看的 observer 連掛載那一發都不打。
    // App 的期貨 tab 由 `visited.futures` 閘住,第一次掛載必在 active=true 時,所以真實路徑
    // 上這一發本來就不存在;舊斷言釘的是一個沒有 caller 的情境。
    expect(urls.length).toBe(0);
    await vi.advanceTimersByTimeAsync(180_000);
    expect(urls.length).toBe(0);
  });

  // 08-28 user 配方:個股頁待一陣子 → 切期貨 tab → 該商品分時圖凍住、「落後 N 根」常亮。
  // 舊碼切回時只重設 60 s 計時器,不立即重抓 → 切回當下必亮提示、最多等 60 s。
  it("active false→true(切回期貨 tab)→ 立即重抓,不等下一輪 60 s", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    const { rerender } = renderHook(({ active }) => useFuturesBars("TMF", "intraday", active), {
      initialProps: { active: true },
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.length).toBe(1); // 掛載(人在 tab 上)
    rerender({ active: false });
    await vi.advanceTimersByTimeAsync(300_000); // 個股頁待 5 分鐘:零輪詢
    expect(urls.length).toBe(1);
    rerender({ active: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.length).toBe(2); // 切回當下就抓,不是 60 s 後
    await vi.advanceTimersByTimeAsync(60_000);
    expect(urls.length).toBe(3); // 之後照 60 s 輪詢
  });

  // review round 1 兩軸各一條 P1:退訂後 observer 歸零 → TQ 預設 gcTime 5 分鐘回收 cache →
  // 待超過 5 分鐘切回會 data undefined 閃「載入中」+ 日 K 也重抓,正是 user「個股頁待很久」的配方。
  it("離開超過 5 分鐘(gcTime 預設)再切回 → 舊圖仍在、不進 pending;日 K 不重抓", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    const client = newClient();
    const w = wrapper(client);
    const minute = renderHook(({ active }) => useFuturesBars("TMF", "intraday", active), {
      initialProps: { active: true },
      wrapper: w,
    });
    const day = renderHook(({ active }) => useFuturesBars("TMF", "day", active), {
      initialProps: { active: true },
      wrapper: w,
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.length).toBe(2); // 分 K + 日 K 各一發
    minute.rerender({ active: false });
    day.rerender({ active: false });
    await vi.advanceTimersByTimeAsync(10 * 60_000); // 待 10 分鐘 > 預設 gcTime 5 分鐘
    expect(urls.length).toBe(2);
    minute.rerender({ active: true });
    day.rerender({ active: true });
    // 切回那一個 render:分 K 的 data 還在(不閃載入中),日 K 不重抓
    expect(minute.result.current.data).toBeDefined();
    expect(minute.result.current.isPending).toBe(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.filter((u) => u.includes("tf=1")).length).toBe(2); // 分 K 立即重抓一發
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1); // 日 K 沒重抓
  });

  // 候選根因(未證實但機制成立):TQ 對同 query 在飛時把後續 refetch 併進同一個 promise,
  // `fetch` 沒 timeout 的話一趟永不回就永久凍結(換商品 = 新 query 才好)。
  it("queryFn 把 timeout signal 交給 fetch(永不回的一趟不能把 query 凍住)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    renderHook(() => useFuturesBars("TMF", "intraday"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    const init = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]?.[1] as
      | RequestInit
      | undefined;
    expect(init?.signal).toBeInstanceOf(AbortSignal);
  });

  it("一趟超過 BARS_SLOW_WARN_MS 才回 → console.warn 留下慢請求證據(抓 user 真事件用)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (url: string) =>
          new Promise<Response>((resolve) => {
            urls.push(String(url));
            setTimeout(
              () =>
                resolve(
                  new Response(JSON.stringify({ key: "TMF", tf: "1", bars: [], meta: META })),
                ),
              20_000,
            );
          }),
      ),
    );
    renderHook(() => useFuturesBars("TMF", "intraday"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(20_000);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0]?.[0])).toMatch(/^bars: 慢請求 .*bars\/TMF.*20\.0 s/);
  });

  it("active 未給 → 預設 true(獨立使用與既有呼叫路徑照輪詢)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    renderHook(() => useFuturesBars("TXF", "m1"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    const before = urls.length;
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

  // 🟢 feat/txf-intraday-overlay review round 1 S1/P1:個股頁的台指期觀察者在鈕關著時必須**零請求**
  //(掛載即抓 + refetchOnWindowFocus 都擋住),`active=false` 只停輪詢擋不住這兩條
  it("enabled=false → 掛載不打、回焦不打;轉 true 才打第一發", async () => {
    const client = newClient();
    // active 與 enabled 同值 = App 個股頁疊線的真實呼叫形狀(`txfWanted` 一份值餵兩個參數);
    // active=false 現在是退訂(subscribed: false),單獨看 enabled 的話這條會被它遮住
    const hook = renderHook(({ enabled }) => useFuturesBars("TXF", "intraday", enabled, enabled), {
      wrapper: wrapper(client),
      initialProps: { enabled: false },
    });
    await new Promise((r) => setTimeout(r, 20));
    expect(urls).toEqual([]);
    expect(hook.result.current.fetchStatus).toBe("idle");
    hook.rerender({ enabled: true });
    await waitFor(() => expect(urls.length).toBe(1));
    expect(urls[0]).toContain("/api/market/bars/TXF?tf=1&days=5&session=allday");
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
