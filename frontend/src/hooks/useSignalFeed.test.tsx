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
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/stock/signals/today");
  });

  it("live 訊號 prepend 在最前,且同 id 不重複入列", async () => {
    const hook = renderHook(() => useSignalFeed(), { wrapper });
    await waitFor(() => expect(hook.result.current.signals.length).toBe(3));

    act(() => emitSignal(sig("live-1")));
    expect(ids(hook.result.current.signals)).toEqual(["live-1", "new", "mid", "old"]);

    // 重啟後同訊號重發(id 決定性鍵)→ 去重,不是變兩列
    act(() => emitSignal(sig("new")));
    expect(ids(hook.result.current.signals)).toEqual(["live-1", "new", "mid", "old"]);
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
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(hook.result.current.signals).toEqual([]);
    act(() => emitSignal(sig("live-1")));
    expect(ids(hook.result.current.signals)).toEqual(["live-1"]);
  });
});
