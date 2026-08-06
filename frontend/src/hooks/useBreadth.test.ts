/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useBreadth } from "@/hooks/useBreadth";

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

const COUNTS = {
  twse: { limit_up: 3, up: 512, flat: 88, down: 401, limit_down: 1 },
  tpex: { limit_up: 1, up: 300, flat: 40, down: 250, limit_down: 0 },
};

const STATE = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "09:03:11",
  stale: false,
  counts: COUNTS,
  series: [
    { t: "0901", twse: [3, 500, 90, 400, 1], tpex: [1, 290, 45, 245, 0] },
    { t: "0903", twse: [3, 512, 88, 401, 1], tpex: [1, 300, 40, 250, 0] },
  ],
};

function wsMsg(over: Record<string, unknown> = {}) {
  return {
    type: "breadth",
    trade_date: "2026-08-06",
    as_of: "09:04:07",
    stale: false,
    counts: COUNTS,
    last_minute: null,
    ...over,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  fetchMock = vi.fn(async () => new Response(JSON.stringify(STATE)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function setup() {
  const hook = renderHook(() => useBreadth());
  await waitFor(() => expect(hook.result.current).not.toBeNull());
  const ws = FakeWS.instances[0]!;
  act(() => ws.onopen?.());
  return { hook, ws };
}

describe("useBreadth", () => {
  it("初載 /api/market/breadth 全量", async () => {
    const { hook } = await setup();
    const state = hook.result.current!;
    expect(state.enabled).toBe(true);
    expect(state.trade_date).toBe("2026-08-06");
    expect(state.as_of).toBe("09:03:11");
    expect(state.stale).toBe(false);
    expect(state.counts).toEqual(COUNTS);
    expect(state.series.map((p) => p.t)).toEqual(["0901", "0903"]);
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/market/breadth");
  });

  it("WS scalar 覆寫(counts / stale / as_of),series 不動", async () => {
    const { hook, ws } = await setup();
    const nextCounts = {
      twse: { limit_up: 9, up: 1, flat: 2, down: 3, limit_down: 4 },
      tpex: { limit_up: 8, up: 5, flat: 6, down: 7, limit_down: 2 },
    };
    act(() => ws.emit(wsMsg({ counts: nextCounts, stale: true })));
    const state = hook.result.current!;
    expect(state.counts).toEqual(nextCounts);
    expect(state.stale).toBe(true);
    expect(state.as_of).toBe("09:04:07");
    expect(state.series.map((p) => p.t)).toEqual(["0901", "0903"]);
  });

  it("last_minute upsert:同 t 覆寫", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit(
        wsMsg({
          last_minute: { t: "0903", twse: [4, 520, 80, 395, 1], tpex: [2, 305, 35, 245, 0] },
        }),
      ),
    );
    const series = hook.result.current!.series;
    expect(series.map((p) => p.t)).toEqual(["0901", "0903"]);
    expect(series[1]!.twse).toEqual([4, 520, 80, 395, 1]);
  });

  it("last_minute upsert:新 t 按升冪插入 / 追加", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit(
        wsMsg({ last_minute: { t: "0902", twse: [3, 505, 89, 402, 1], tpex: [1, 295, 42, 248, 0] } }),
      ),
    );
    expect(hook.result.current!.series.map((p) => p.t)).toEqual(["0901", "0902", "0903"]);

    act(() =>
      ws.emit(
        wsMsg({ last_minute: { t: "0904", twse: [3, 515, 85, 400, 1], tpex: [1, 302, 38, 249, 0] } }),
      ),
    );
    expect(hook.result.current!.series.map((p) => p.t)).toEqual(["0901", "0902", "0903", "0904"]);
  });

  it("trade_date 變更 → 清 series 並 refetch 全量", async () => {
    const { hook, ws } = await setup();
    const before = fetchMock.mock.calls.length;
    fetchMock.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            ...STATE,
            trade_date: "2026-08-07",
            series: [{ t: "0901", twse: [0, 1, 2, 3, 4], tpex: [0, 1, 2, 3, 4] }],
          }),
        ),
    );
    act(() => ws.emit(wsMsg({ trade_date: "2026-08-07" })));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
    await waitFor(() => expect(hook.result.current!.trade_date).toBe("2026-08-07"));
    // 舊日格子已清:refetch 回來的全量取代,不留 0901/0903 舊值
    expect(hook.result.current!.series).toEqual([
      { t: "0901", twse: [0, 1, 2, 3, 4], tpex: [0, 1, 2, 3, 4] },
    ]);
  });

  it("WS reconnect onopen → refetch 全量(補回斷線期間漏格)", async () => {
    const { ws } = await setup();
    const before = fetchMock.mock.calls.length;
    act(() => ws.onclose?.());
    await waitFor(() => expect(FakeWS.instances.length).toBeGreaterThan(1), { timeout: 3000 });
    const ws2 = FakeWS.instances[FakeWS.instances.length - 1]!;
    act(() => ws2.onopen?.());
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
  });

  it("enabled=false 透傳(FinMind 未設定)", async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            enabled: false,
            trade_date: null,
            as_of: null,
            stale: false,
            counts: null,
            series: [],
          }),
        ),
    );
    const hook = renderHook(() => useBreadth());
    await waitFor(() => expect(hook.result.current).not.toBeNull());
    const state = hook.result.current!;
    expect(state.enabled).toBe(false);
    expect(state.counts).toBeNull();
    expect(state.series).toEqual([]);
  });

  it("unmount → WS 關閉", async () => {
    const { hook, ws } = await setup();
    hook.unmount();
    expect(ws.closed).toBe(true);
  });
});

/** fetch 回應懸置在手上,測「refetch 在途」這段窗。 */
function deferredResponse() {
  let release!: (body: unknown) => void;
  const promise = new Promise<Response>((resolve) => {
    release = (body: unknown) => resolve(new Response(JSON.stringify(body)));
  });
  return { promise, release };
}

/** refetch 未回期間抵達的 WS 增量格,不可被隨後的全量回應整份覆蓋掉(review P2-3)。 */
describe("useBreadth refetch 競態(review P2-3)", () => {
  async function inflightRefetch() {
    const hook = renderHook(() => useBreadth());
    await waitFor(() => expect(hook.result.current).not.toBeNull());
    const ws = FakeWS.instances[0]!;
    const pending = deferredResponse();
    fetchMock.mockImplementation(async () => pending.promise);
    act(() => ws.onopen?.()); // reconnect → refetch,回應懸置
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(2));
    return { hook, ws, pending };
  }

  it("fetch 在途 → WS 新格先到 → 全量回應缺該格,該格仍在 series", async () => {
    const { hook, ws, pending } = await inflightRefetch();
    act(() =>
      ws.emit(
        wsMsg({ last_minute: { t: "0904", twse: [3, 515, 85, 400, 1], tpex: [1, 302, 38, 249, 0] } }),
      ),
    );
    expect(hook.result.current!.series.map((p) => p.t)).toEqual(["0901", "0903", "0904"]);

    // 全量只到 0903(該格是 fetch 快照拍完之後才產生的)
    await act(async () => {
      pending.release(STATE);
      await pending.promise;
    });
    await waitFor(() =>
      expect(hook.result.current!.series.map((p) => p.t)).toEqual(["0901", "0903", "0904"]),
    );
    // 同 t 以全量為準
    expect(hook.result.current!.series[1]!.twse).toEqual([3, 512, 88, 401, 1]);
  });

  it("換日 refetch(trade_date 不同)不合併,一律以全量回應為準", async () => {
    const { hook, ws, pending } = await inflightRefetch();
    act(() =>
      ws.emit(
        wsMsg({ last_minute: { t: "0904", twse: [3, 515, 85, 400, 1], tpex: [1, 302, 38, 249, 0] } }),
      ),
    );
    await act(async () => {
      pending.release({
        ...STATE,
        trade_date: "2026-08-07",
        series: [{ t: "0901", twse: [0, 1, 2, 3, 4], tpex: [0, 1, 2, 3, 4] }],
      });
      await pending.promise;
    });
    await waitFor(() => expect(hook.result.current!.trade_date).toBe("2026-08-07"));
    expect(hook.result.current!.series).toEqual([
      { t: "0901", twse: [0, 1, 2, 3, 4], tpex: [0, 1, 2, 3, 4] },
    ]);
  });
});
