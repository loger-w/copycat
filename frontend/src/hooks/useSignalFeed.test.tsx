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
    // 裸 URL:後端不再有可分族的事件源,today 端點回的就是當日全部訊號。
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/stock/signals/today");
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
      expect(client.getQueryState(["stock-signals-today"])?.status).toBe("error"),
    );
    expect(hook.result.current.signals).toEqual([]);
    act(() => emitSignal(sig("live-1")));
    expect(ids(hook.result.current.signals)).toEqual(["live-1"]);
  });

  // (review round-2 FE-1 / XR-3)降級**必須可見**:達錢 4 沒開時這支端點回 503,
  // 而「baseline 抓不到」與「今天真的沒訊號」在下游畫面上完全同形 —— 消費端沒有
  // 這顆旗標就只能把兩者說成同一句話,使用者看到「今日尚無訊號」不會去查服務。
  it("today 抓失敗 → baselineError 為 true(降級要可見,不只是靜靜地空著)", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 }),
    );
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    // retry: 1 → 第二次 fetch 發出後才是 error 終態(retryDelay 預設 1s)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2), { timeout: 5_000 });
    await waitFor(() => expect(hook.result.current.baselineError).toBe(true));
  });

  it("today 抓成功 → baselineError 為 false(不誤報)", async () => {
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    await waitFor(() => expect(hook.result.current.signals.length).toBe(3));
    expect(hook.result.current.baselineError).toBe(false);
  });
});

// 2026-08-16:分族(全市場廣度事件 vs 自選訊號)整套刪除後,feed 只剩單一 baseline
// 來源 —— 沒有模式參數、沒有查參、queryKey 固定一支。這支釘的是「不再有第二族」:
// 若哪天又有人給 queryKey 加維度,兩個掛載點就會各抓一份、各拿到不同內容。
describe("useSignalFeed — 單一 baseline 來源", () => {
  it("裸 URL 無查參、queryKey 固定一支:兩個掛載點共用同一份 baseline", async () => {
    today = [sig("old"), sig("new")];
    const hook = renderHook(() => ({ a: useSignalFeed(), b: useSignalFeed() }), { wrapper });

    await waitFor(() => expect(hook.result.current.a.signals.length).toBe(2));
    // 兩個掛載點同 key → 只發一次 fetch,且 URL 上沒有任何查參
    expect(fetchMock.mock.calls.map((c) => String(c[0]))).toEqual(["/api/stock/signals/today"]);
    expect(client.getQueryCache().getAll().map((q) => q.queryKey)).toEqual([
      ["stock-signals-today"],
    ]);

    // live 訊號兩邊都收得到(沒有任何 kind 會在 feed 層被早退掉)
    act(() => emitSignal(sig("live-1", "09:20:01")));
    expect(ids(hook.result.current.a.signals)).toEqual(["live-1", "new", "old"]);
    expect(ids(hook.result.current.b.signals)).toEqual(["live-1", "new", "old"]);
  });
});
