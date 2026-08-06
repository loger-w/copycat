/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSignalFeed } from "@/hooks/useSignalFeed";
import { emitSignal, emitWsOpen } from "@/lib/signal-bus";
import type { SignalMsg } from "@/lib/signal-model";

function sig(id: string, time = "09:15:03"): SignalMsg {
  return {
    type: "signal",
    id,
    kind: "surge",
    code: "2330",
    name: "台積電",
    price: 1_234_500,
    time,
    levels: [],
    direction: null,
    pct: 1.5,
    touch_count: 1,
  };
}

/** 後端 `GET /api/stock/signals/today` 回的是 jsonl 順序 = **舊在前**。 */
let today: SignalMsg[];
let fetchMock: ReturnType<typeof vi.fn>;
let client: QueryClient;

beforeEach(() => {
  today = [sig("old"), sig("mid"), sig("new")];
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ signals: today })));
  vi.stubGlobal("fetch", fetchMock);
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function ids(list: SignalMsg[]): string[] {
  return list.map((s) => s.id);
}

describe("useSignalFeed", () => {
  it("baseline 反轉為新在前(後端 jsonl 是舊在前)", async () => {
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    await waitFor(() => expect(hook.result.current.signals.length).toBe(3));
    expect(ids(hook.result.current.signals)).toEqual(["new", "mid", "old"]);
    // 預設模式 = exclude(design §9.3):baseline 由**後端**濾掉 market 族,
    // 前端只再擋 live 那條。URL 與 queryKey 的變更是事前拍板該變的(SC-8)。
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/stock/signals/today?market=exclude");
  });

  it("live 訊號 prepend 在最前,且同 id 不重複入列", async () => {
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    await waitFor(() => expect(hook.result.current.signals.length).toBe(3));

    act(() => emitSignal(sig("live-1")));
    expect(ids(hook.result.current.signals)).toEqual(["live-1", "new", "mid", "old"]);

    // 重啟後同訊號重發(id 決定性鍵)→ 去重,不是變兩列。
    // 重發者上浮到最前是刻意的:清單序 = 「最近收到」,live 那份贏 baseline 的位置。
    act(() => emitSignal(sig("new")));
    expect(ids(hook.result.current.signals)).toEqual(["new", "live-1", "mid", "old"]);
    expect(ids(hook.result.current.signals).filter((id) => id === "new").length).toBe(1);
  });

  it("ws-open → 重抓當日 baseline(斷線期間漏的訊號自癒補回)", async () => {
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    await waitFor(() => expect(hook.result.current.signals.length).toBe(3));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    today = [sig("old"), sig("mid"), sig("new"), sig("missed")];
    act(() => emitWsOpen());

    await waitFor(() => expect(ids(hook.result.current.signals)).toEqual(["missed", "new", "mid", "old"]));
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("today 抓失敗 → signals 空陣列(不 throw,live 訊號照樣進得來)", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 }),
    );
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    // hook 自帶 retry: 1(壓過 client 的 retry: false)→ 等第二次 fetch 發出才是 error
    // 終態;只等「呼叫過」會落在 retry pending 窗,那時的空清單來自「還沒 settle」而不是
    // 失敗降級(review TQ-5)。retryDelay 預設 1s,waitFor 預設 timeout 1s 抓不到 → 給 5s。
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2), { timeout: 5_000 });
    await waitFor(() =>
      expect(client.getQueryState(["stock-signals-today", "exclude"])?.status).toBe("error"),
    );
    expect(hook.result.current.signals).toEqual([]);
    act(() => emitSignal(sig("live-1")));
    expect(ids(hook.result.current.signals)).toEqual(["live-1"]);
  });
});

// 🟢 market-overview R4(SC-8):全市場廣度事件與自選訊號同一條匯流排,
// 由 feed 層依模式分流 —— 過濾/分族都發生在 `mergeSignals` 的 cap 之前。
function mkt(id: string, time = "09:30:00"): SignalMsg {
  return {
    ...sig(id, time),
    kind: "market_limit_lock",
    code: "1101",
    name: "台泥",
    direction: "up",
    pct: null,
  };
}

/** 測試側自帶判別子:紅階段 `isMarketKind` 尚不存在,不從 model 匯入(具名 import
 *  一個不存在的 export 在 Vite SSR transform 下是載入期例外 = 整檔 error)。 */
function isMarket(s: SignalMsg): boolean {
  return (s.kind as string).startsWith("market_");
}

describe("useSignalFeed — market 分流(SC-8)", () => {
  it("exclude(預設):live 的 market 事件在合併前就被擋掉,不吃自選的 cap", async () => {
    today = [];
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    act(() => {
      // 漲停潮日:250 則全市場事件擠進來。沒有 feed 層過濾時,cap 200 會把
      // 自選那 3 則整批擠出畫面(而畫面上完全看不出「被擠掉」)。
      for (let i = 0; i < 250; i += 1) emitSignal(mkt(`m${i}`));
      emitSignal(sig("own-1", "09:20:01"));
      emitSignal(sig("own-2", "09:20:02"));
      emitSignal(sig("own-3", "09:20:03"));
    });

    await waitFor(() => expect(hook.result.current.signals.length).toBe(3));
    expect(ids(hook.result.current.signals).sort()).toEqual(["own-1", "own-2", "own-3"]);
    expect(hook.result.current.signals.some(isMarket)).toBe(false);
  });

  it("include:分族各自 cap 200 —— market 族擠不掉自選族", async () => {
    today = [];
    const hook = renderHook(() => useSignalFeed({ market: "include" }), { wrapper });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    act(() => {
      for (let i = 0; i < 250; i += 1) emitSignal(mkt(`m${i}`));
      emitSignal(sig("own-1", "09:20:01"));
      emitSignal(sig("own-2", "09:20:02"));
      emitSignal(sig("own-3", "09:20:03"));
    });

    await waitFor(() =>
      expect(hook.result.current.signals.filter((s) => !isMarket(s)).length).toBe(3),
    );
    // market 族自己吃滿 200 的 cap,但不越界吃到另一族
    expect(hook.result.current.signals.filter(isMarket).length).toBe(200);
  });

  it("同一 QueryClient 兩消費端:各自 fetch、URL 不同、內容不同(queryKey 帶模式)", async () => {
    const own = sig("own-1", "09:20:01");
    const market = mkt("m-1", "09:21:00");
    // 這支要看 URL 才知道回什麼 → 另立一個帶參數的 mock(beforeEach 那支不吃參數)
    const urlFetch = vi.fn(
      async (url: string) =>
        new Response(
          JSON.stringify({
            signals: url.includes("market=exclude") ? [own] : [own, market],
          }),
        ),
    );
    vi.stubGlobal("fetch", urlFetch);

    const hook = renderHook(
      () => ({
        excluded: useSignalFeed(),
        included: useSignalFeed({ market: "include" }),
      }),
      { wrapper },
    );

    await waitFor(() => expect(hook.result.current.included.signals.length).toBe(2));
    // 共用固定 key 時第二個掛載點會直接吃到第一個的 cache → 只會有一次 fetch
    const urls = urlFetch.mock.calls.map((c) => c[0]);
    expect(urls.length).toBe(2);
    expect([...urls].sort()).toEqual([
      "/api/stock/signals/today",
      "/api/stock/signals/today?market=exclude",
    ]);
    expect(ids(hook.result.current.excluded.signals)).toEqual(["own-1"]);
    expect(ids(hook.result.current.included.signals)).toEqual(["m-1", "own-1"]);

    // ws-open 的 invalidate 用 prefix key:兩族一起自癒,不是只救其中一掛載點
    act(() => emitWsOpen());
    await waitFor(() => expect(urlFetch.mock.calls.length).toBe(4));
    const after = urlFetch.mock.calls.map((c) => c[0]);
    expect(after.filter((u) => u.includes("market=exclude")).length).toBe(2);
    expect(after.filter((u) => !u.includes("market=exclude")).length).toBe(2);
  });
});
