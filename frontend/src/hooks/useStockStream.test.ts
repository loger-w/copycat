/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStockStream } from "@/hooks/useStockStream";

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }

  emit(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
}

function snap(seq: number, ticks: { t: string; p: number; q: number; side: string }[]) {
  return {
    code: "2330",
    seq,
    last: ticks.length
      ? { p: ticks[ticks.length - 1]!.p, t: ticks[ticks.length - 1]!.t, cum_vol: seq }
      : null,
    vwap: null,
    minutes: {},
    ticks,
    book: null,
    meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: null },
    no_data: false,
  };
}

const T = (seq: number) => ({
  type: "tick", code: "2330", t: "09:10:00.000", p: 2_380_000, q: 1, side: "outer", seq,
});

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  fetchMock = vi.fn(async () => new Response(JSON.stringify(snap(1, [{ t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" }]))));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function setup() {
  const hook = renderHook(() => useStockStream("2330"));
  await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
  const ws = FakeWS.instances[0]!;
  return { hook, ws };
}

describe("useStockStream", () => {
  it("初始 fetch snapshot 建立 accum", async () => {
    const { hook } = await setup();
    expect(fetchMock).toHaveBeenCalledWith("/api/stock/state/2330");
    expect(hook.result.current.accum?.seq).toBe(1);
    expect(hook.result.current.accum?.ticks.length).toBe(1);
  });

  it("連續 seq 的 tick 直接累算", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit(T(2)));
    expect(hook.result.current.accum?.seq).toBe(2);
    expect(hook.result.current.accum?.ticks.length).toBe(2);
  });

  it("seq 跳號觸發 refetch,交錯訊息無重複無漏(對齊規則 seq ≤ S 丟棄)", async () => {
    const { hook, ws } = await setup();
    // refetch 會回 seq=5 的 snapshot(含 4 筆)
    let resolveRefetch: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveRefetch = res; }),
    );
    act(() => ws.emit(T(4))); // 1→4 跳號(漏 2,3)→ refetch
    // refetch 期間交錯:seq 5(> S 不該丟)與 seq 3(≤ S 該丟)
    act(() => ws.emit(T(5)));
    act(() => ws.emit(T(3)));
    act(() => {
      resolveRefetch(new Response(JSON.stringify(snap(4, [
        { t: "09:00:01.000", p: 2_370_000, q: 1, side: "inner" },
        { t: "09:01:00.000", p: 2_375_000, q: 1, side: "outer" },
        { t: "09:02:00.000", p: 2_380_000, q: 1, side: "outer" },
        { t: "09:03:00.000", p: 2_380_000, q: 1, side: "outer" },
      ]))));
    });
    await waitFor(() => expect(hook.result.current.accum?.seq).toBe(5));
    // snapshot 4 筆 + 交錯倖存 1 筆(seq 5);seq 3 被丟
    expect(hook.result.current.accum?.ticks.length).toBe(5);
  });

  it("切檔撞上 in-flight refetch 不被吞(CR1:合併不丟棄)", async () => {
    let resolveFirst: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveFirst = res; }),
    );
    const hook = renderHook(({ c }: { c: string }) => useStockStream(c), {
      initialProps: { c: "2330" },
    });
    // 2330 的 fetch in-flight 中切到 5483
    hook.rerender({ c: "5483" });
    act(() => {
      resolveFirst(new Response(JSON.stringify(snap(1, []))));
    });
    // 舊結果作廢後必須補發新檔 fetch(修前:單飛旗標把 5483 的需求吞掉)
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]) === "/api/stock/state/5483")).toBe(true),
    );
    await waitFor(() => expect(hook.result.current.accum).not.toBeNull());
  });

  it("status 訊息更新 tc4 狀態;backfilling 完成觸發 refetch", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit({ type: "status", tc4: "down", backfilling: null }));
    expect(hook.result.current.status.tc4).toBe("down");
    const calls = fetchMock.mock.calls.length;
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: "2330" }));
    act(() => ws.emit({ type: "status", tc4: "up", backfilling: null }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(calls));
  });

  it("watchlist_quote 更新側欄報價(含 no_data)", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit({ type: "watchlist_quote", code: "5483", p: 216_500, chg_pct: -1.2, vol: 100, no_data: false }));
    act(() => ws.emit({ type: "watchlist_quote", code: "9999", p: null, chg_pct: null, vol: null, no_data: true }));
    expect(hook.result.current.watchlist["5483"]?.p).toBe(216_500);
    expect(hook.result.current.watchlist["9999"]?.no_data).toBe(true);
  });

  // round4 項 4(review F4):`ref` 的解析只有這一層測得到 —— 下游的參考價測試都是把
  // quotes 當 props 直接餵元件,繞過 WS 解析,把這行改壞不會有任何測試紅。
  it("watchlist_quote 的 ref 欄位(尚無成交時的參考價)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({
        type: "watchlist_quote", code: "9998",
        p: null, chg_pct: null, vol: null, ref: 995_000, no_data: false,
      }),
    );
    expect(hook.result.current.watchlist["9998"]?.ref).toBe(995_000);
    expect(hook.result.current.watchlist["9998"]?.p).toBeNull();
  });

  it("舊後端不發 ref → 降級 null(不是 undefined)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit({ type: "watchlist_quote", code: "9997", p: 100_000, chg_pct: 0, vol: 1, no_data: false }),
    );
    expect(hook.result.current.watchlist["9997"]?.ref).toBeNull();
  });

  it("stkfut 訊息更新期現對照", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit({ type: "stkfut", code: "2330", prod: "CDF", p: 2_398_000, basis: 18_000 }));
    expect(hook.result.current.stkfut?.p).toBe(2_398_000);
    expect(hook.result.current.stkfut?.basis).toBe(18_000);
  });
});
