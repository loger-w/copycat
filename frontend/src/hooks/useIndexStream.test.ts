/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useIndexStream } from "@/hooks/useIndexStream";

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

const STATE = {
  trade_date: "2026-07-28",
  twse: {
    p: 42_039_920, ref: 43_634_190, high: 43_221_930, low: 41_815_780,
    stale: false, last_minute: null, minutes: { "0901": 43_000_000 },
  },
  otc: {
    p: 359_800, ref: 378_090, high: 373_420, low: 358_430,
    stale: false, last_minute: null, minutes: { "1017": 359_800 },
  },
  txf: { p: 42_142_000, time: "10:16:10" },
};

function wsMsg(over: Partial<typeof STATE> = {}) {
  return {
    type: "index",
    trade_date: "2026-07-28",
    twse: { p: 42_000_000, ref: 43_634_190, high: 43_221_930, low: 41_815_780, stale: false, last_minute: ["0932", 42_000_000] },
    otc: { p: 359_000, ref: 378_090, high: 373_420, low: 358_430, stale: false, last_minute: null },
    txf: { p: 42_100_000, time: "10:17:00" },
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
  const hook = renderHook(() => useIndexStream());
  await waitFor(() => expect(hook.result.current.twse).not.toBeNull());
  const ws = FakeWS.instances[0]!;
  act(() => ws.onopen?.());
  return { hook, ws };
}

describe("useIndexStream", () => {
  it("初載 state 全量(含 minutes)", async () => {
    const { hook } = await setup();
    expect(hook.result.current.twse!.p).toBe(42_039_920);
    expect(hook.result.current.twse!.minutes).toEqual({ "0901": 43_000_000 });
    expect(hook.result.current.txf).toEqual({ p: 42_142_000, time: "10:16:10" });
  });

  it("WS merge:scalar 覆蓋 + last_minute upsert(R6)", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit(wsMsg()));
    expect(hook.result.current.twse!.p).toBe(42_000_000);
    expect(hook.result.current.twse!.minutes).toEqual({
      "0901": 43_000_000,
      "0932": 42_000_000,
    });
    expect(hook.result.current.otc!.p).toBe(359_000);
    expect(hook.result.current.otc!.minutes).toEqual({ "1017": 359_800 }); // 無 last_minute 不動
  });

  it("trade_date 變更 → 清 minutes 並 refetch(F3)", async () => {
    const { hook, ws } = await setup();
    const before = fetchMock.mock.calls.length;
    // 換日後 server state 也已是新日(真實時序)
    fetchMock.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({ ...STATE, trade_date: "2026-07-29", twse: { ...STATE.twse, minutes: { "0901": 1 } } }),
        ),
    );
    act(() => ws.emit(wsMsg({ trade_date: "2026-07-29" } as never)));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
    await waitFor(() => expect(hook.result.current.tradeDate).toBe("2026-07-29"));
    expect(hook.result.current.twse!.minutes).toEqual({ "0901": 1 }); // 舊日 minutes 已清
  });

  it("WS reconnect → refetch state 全量(F3)", async () => {
    const { ws } = await setup();
    const before = fetchMock.mock.calls.length;
    act(() => ws.onclose?.());
    await waitFor(() => expect(FakeWS.instances.length).toBeGreaterThan(1), { timeout: 3000 });
    const ws2 = FakeWS.instances[FakeWS.instances.length - 1]!;
    act(() => ws2.onopen?.());
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(before));
  });
});
