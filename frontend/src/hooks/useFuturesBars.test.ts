/** @vitest-environment jsdom */
import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FUTURES_MINUTE_DAYS, useFuturesBars } from "@/hooks/useFuturesBars";
import { isoLocalDate } from "@/lib/trading-calendar";

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

/** 日 K 跨日測試共用:D = 2026-08-05(週三)。D 當天的請求回 `dBars`、D+1 起的請求回 `d1Bars`。 */
const D1_ISO = "2026-08-06";
function stubDayFetchByWallClock(dBars: readonly object[], d1Bars: readonly object[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url));
      const bars = isoLocalDate(new Date()) >= D1_ISO ? d1Bars : dBars;
      return new Response(JSON.stringify({ key: "TXF", tf: "D", bars, meta: META }));
    }),
  );
}
const dayFetchCount = () => urls.filter((u) => u.includes("tf=D")).length;

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
  focusManager.setFocused(undefined); // 跨日測試手動切過 focus 的還原,避免外溢到別檔
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

// bug/futures-daily-bars-rollover(next-time 08-24 L408 → 08-28 升 /bug):看盤日常 = preview 整天掛著,
// 跨過午夜後日 K 那份 cache 不會失效(`staleTime: Infinity` + 不輪詢)→ 新交易日的 CDP / MA 疊線
// 拿**前一天那份快照**當基準。為什麼界是日曆午夜:見 `lib/day-bars-rollover.ts::msUntilDayRollover`。
describe("useFuturesBars 日 K 跨日曆日(bug/futures-daily-bars-rollover)", () => {
  /** D 當天的請求回「D 部分 bar」快照;D+1 起的請求回「D 完成 + D+1 部分」
   *  (第四條推到 D+2 只數 URL,快照沒有 D+2 bar 無妨)。 */
  const D_SNAPSHOT = [
    { t: "2026-08-04", o: 1, h: 3, l: 1, c: 2, v: 10 },
    { t: "2026-08-05", o: 2, h: 2, l: 2, c: 2, v: 1 }, // 09:00 時的部分 bar
  ];
  const D1_SNAPSHOT = [
    { t: "2026-08-04", o: 1, h: 3, l: 1, c: 2, v: 10 },
    { t: "2026-08-05", o: 2, h: 9, l: 1, c: 8, v: 99 }, // D 完成
    { t: "2026-08-06", o: 8, h: 8, l: 8, c: 8, v: 1 },
  ];
  // 界 = 日曆午夜 + 60 s slack,不是「掛載後固定 24 h」(那會讓 20:00 開的分頁整個次日都用舊基準;
  // review Spec F-1)—— 所以掛載時刻取 09:00、斷言點取 23:59 / 00:00:30 / 00:01:01 三點,固定 24 h
  // 與 slack = 0 兩種突變體各紅一點。
  it("人一直在期貨 tab 上跨過午夜 → 00:01 重抓一次,cache 不停在昨天的快照", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0)); // D 09:00,preview 開著
    stubDayFetchByWallClock(D_SNAPSHOT, D1_SNAPSHOT);
    const { result } = renderHook(() => useFuturesBars("TXF", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1);
    expect(result.current.data?.bars).toEqual(D_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(14 * 60 * 60_000 + 59 * 60_000); // 23:59
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1);
    await vi.advanceTimersByTimeAsync(90_000); // D+1 00:00:30:午夜過了但還在 slack 內
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1);
    await vi.advanceTimersByTimeAsync(31_000); // 00:01:01
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(2);
    // 使用者的症狀:D+1 早上疊線基準仍是昨天 09:00 那份(D bar 停在部分值)
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(9 * 60 * 60_000); // 09:00:xx:同一日曆日內不再打
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(2);
  });

  // 午夜那一發失敗(TC4 忙 / 後端 503)→ `retry: 1` 用完後 interval 若照樣重算成「下一個午夜」,
  // 整個交易日就停在昨天的基準 —— 與修前同一個症狀(review Spec F-2)。
  it("午夜那一發失敗 → 60 s 後再試,成功即回到「下一個午夜」節奏", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    let failLeft = 2; // 本體 + retry:1 各失敗一次
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(String(url));
        if (isoLocalDate(new Date()) >= D1_ISO && failLeft > 0) {
          failLeft -= 1;
          return new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 });
        }
        const bars = isoLocalDate(new Date()) >= D1_ISO ? D1_SNAPSHOT : D_SNAPSHOT;
        return new Response(JSON.stringify({ key: "TXF", tf: "D", bars, meta: META }));
      }),
    );
    const { result } = renderHook(() => useFuturesBars("TXF", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 + 60_000 + 5_000); // 00:01:05:本體失敗 + 1 s 後 retry 失敗
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(3);
    expect(result.current.isError).toBe(true);
    expect(result.current.data?.bars).toEqual(D_SNAPSHOT); // v5:refetch 失敗保留舊 data
    await vi.advanceTimersByTimeAsync(60_000); // 60 s 重試
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(4);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(10 * 60_000); // 成功後不再每 60 s 打
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(4);
  });

  // pr-159-review F-01 同洞(useFuturesBars 與 useMarketBars 同一條 200 降級路):午夜那發拿到
  // 200 + 空 bars → 空 bars 視同失敗,60 s 重試,不把空快照鎖到隔天。
  it("日 K:午夜那一發拿到 200 + 空 bars(TC4 沒開)→ 60 s 後重試,不把空快照鎖到隔天", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    let emptyLeft = 1; // 200 不觸發 TQ retry,一發就夠
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(String(url));
        const d1 = isoLocalDate(new Date()) >= D1_ISO;
        if (d1 && emptyLeft > 0) {
          emptyLeft -= 1;
          const meta = { ...META, source: "unavailable" };
          return new Response(JSON.stringify({ key: "TXF", tf: "D", bars: [], meta }));
        }
        const bars = d1 ? D1_SNAPSHOT : D_SNAPSHOT;
        return new Response(JSON.stringify({ key: "TXF", tf: "D", bars, meta: META }));
      }),
    );
    const { result } = renderHook(() => useFuturesBars("TXF", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1);
    await vi.advanceTimersByTimeAsync(2 * 60 * 60_000 + 61_000); // D+1 00:01:01:拿到空快照
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(2);
    expect(result.current.data?.bars).toEqual([]);
    await vi.advanceTimersByTimeAsync(60_000); // 60 s 重試 → TC4 回來了
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(3);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
    await vi.advanceTimersByTimeAsync(10 * 60_000); // 資料非空後回到「下一個午夜」節奏
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(3);
  });

  // 切走的 observer 是退訂(subscribed: false):沒有計時器,午夜那一發不會打;切回時靠
  // staleTime 判「這份是昨天的」才重抓 —— 同日曆日內切回仍不重抓(上一個 describe 那條)。
  it("在個股頁跨過午夜再切回期貨 tab → 日 K 重抓(同日曆日切回才是不重抓)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0)); // D 22:00 在期貨 tab
    stubDayFetchByWallClock(D_SNAPSHOT, D1_SNAPSHOT);
    const { result, rerender } = renderHook(({ active }) => useFuturesBars("TXF", "day", active), {
      initialProps: { active: true },
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1);
    rerender({ active: false });
    await vi.advanceTimersByTimeAsync(11 * 60 * 60_000); // 個股頁待到 D+1 09:00
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1); // 退訂期間零請求
    rerender({ active: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(2);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
  });

  // TQ 預設 `refetchIntervalInBackground: false`:分頁在背景時每個 interval tick 都被 focus 閘跳過
  //(本例 period = 22:00 → 00:01 的 2 h 1 min,背景中一路跳過)—— 回前景那一刻要靠「已過期」+
  // refetchOnWindowFocus(`queryCache.onFocus`)補上,不是靠 interval。
  it("分頁在背景跨過午夜 → 回前景那一刻重抓,不等下一個 24 小時", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubDayFetchByWallClock(D_SNAPSHOT, D1_SNAPSHOT);
    const { result } = renderHook(() => useFuturesBars("TXF", "day"), {
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1);
    focusManager.setFocused(false); // 分頁縮到背景
    await vi.advanceTimersByTimeAsync(11 * 60 * 60_000); // D+1 09:00
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1); // 背景不打
    focusManager.setFocused(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(2);
    expect(result.current.data?.bars).toEqual(D1_SNAPSHOT);
  });

  it("同一日曆日內(22:00 → 23:59)不重抓,跨兩個午夜恰重抓兩次(不是每 60 s 一發)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    stubDayFetchByWallClock(D_SNAPSHOT, D1_SNAPSHOT);
    renderHook(() => useFuturesBars("TXF", "day"), { wrapper: wrapper(newClient()) });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(119 * 60_000); // 23:59
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(1);
    await vi.advanceTimersByTimeAsync(48 * 60 * 60_000); // D+2 23:59
    expect(urls.filter((u) => u.includes("tf=D")).length).toBe(3);
  });
});

// pr-151-review F-01 / F-02 / F-07:TQ 每一次 render 都重算 `refetchInterval` 並在回值變動時重排計時器
//(推導見 `lib/day-bars-rollover.ts::msUntilDayRollover`)。上一個 describe 用 `renderHook` 推進期間不重繪,
// 量不到「人一直在期貨 tab 上」這一維 —— 這裡用 `rerender` 模擬 FuturesChart 吃 WS 的重繪節奏。
describe("useFuturesBars 日 K 跨午夜 × 重繪(pr-151-review F-01 / F-02 / F-07)", () => {
  /** 只數請求,一根 bar 就夠(與上一個 describe 的兩根快照刻意不同名)。 */
  const ONE_BAR_D = [{ t: "2026-08-05", o: 2, h: 2, l: 2, c: 2, v: 1 }];
  const ONE_BAR_D1 = [{ t: "2026-08-05", o: 2, h: 9, l: 1, c: 8, v: 99 }];
  /** 模擬 FuturesChart 吃 WS 的重繪節奏:每 `everyMs` 一次 rerender、持續 `forMs`。 */
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

  it("slack 窗內(00:00:10 → 00:00:50)每 100 ms 重繪一次 → 00:01:01 照樣重抓,不被推到隔天", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubDayFetchByWallClock(ONE_BAR_D, ONE_BAR_D1);
    // callback 不吃 props:`rerender({ tick })` 只為了觸發一次 render(FuturesChart 每則 WS 訊息就是這樣)
    const { result, rerender } = renderHook(() => useFuturesBars("TXF", "day"), {
      initialProps: { tick: -1 },
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(dayFetchCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(15 * 60 * 60_000 + 10_000); // D+1 00:00:10
    await rerenderBurst(rerender, 40_000, 100); // → 00:00:50,400 次重繪
    expect(dayFetchCount()).toBe(1); // 還在 slack 內
    await vi.advanceTimersByTimeAsync(11_000); // 00:01:01
    expect(dayFetchCount()).toBe(2);
    expect(result.current.data?.bars).toEqual(ONE_BAR_D1);
    await vi.advanceTimersByTimeAsync(9 * 60 * 60_000); // 09:00:xx:同日不再打
    expect(dayFetchCount()).toBe(2);
  });

  // 鎖住修法的另一面:以 `dataUpdatedAt` 起算的版本跨 render 穩定,但 setInterval 的週期是從「重新武裝的時刻」
  // 起算 —— 09:00 抓、20:00 切回會武裝 15 h、11:00 才打。界必須以「現在」算到下一個 00:01。
  it("09:00 抓 → 15:00 切走 → 20:00 切回(未過期)→ 仍在 00:01:01 重抓,不是 11:00", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubDayFetchByWallClock(ONE_BAR_D, ONE_BAR_D1);
    const { rerender } = renderHook(({ active }) => useFuturesBars("TXF", "day", active), {
      initialProps: { active: true },
      wrapper: wrapper(newClient()),
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(dayFetchCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(6 * 60 * 60_000); // 15:00
    rerender({ active: false });
    await vi.advanceTimersByTimeAsync(5 * 60 * 60_000); // 20:00
    rerender({ active: true });
    await vi.advanceTimersByTimeAsync(0);
    expect(dayFetchCount()).toBe(1); // 同日曆日切回不重抓
    await vi.advanceTimersByTimeAsync(4 * 60 * 60_000 + 30_000); // 00:00:30
    expect(dayFetchCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(31_000); // 00:01:01
    expect(dayFetchCount()).toBe(2);
  });

  // F-02:連續值 interval 讓每次 render 都 clear + setInterval 一組;秒級量化後同一秒內的重繪不再重排。
  // 期望值是 0 不是「≤ 1」:fixture 對齊 09:00:00.000、首發在 advance(0) 落地,窗內 50 次的回值恆同。
  // 跨過整秒後再重繪一次必須看到 1 —— 生效自檢(spy 真的看得到 TQ 的 setInterval),不然 0 是 vacuous。
  it("同一秒內重繪 50 次 → setInterval 零重排(秒級量化);跨秒重繪一次 → 恰 1 次", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 9, 0));
    stubDayFetchByWallClock(ONE_BAR_D, ONE_BAR_D1);
    const { rerender } = renderHook(() => useFuturesBars("TXF", "day"), {
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
