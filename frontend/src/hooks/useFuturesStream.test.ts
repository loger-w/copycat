/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  applyFuturesMsg,
  mergePending,
  useFuturesStream,
  type FuturesWsMsg,
} from "@/hooks/useFuturesStream";
import type { FuturesProductState, FuturesState } from "@/types";

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

function ps(product: string, p: number): FuturesProductState {
  return {
    product,
    name: "臺股期貨",
    p,
    q: 1,
    cum_vol: 100,
    t: "09:00:00",
    date: "20260728",
    bids: [[p - 1000, 5]],
    asks: [[p + 1000, 3]],
    ref: 22_900_000,
    upper: 25_190_000,
    lower: 20_610_000,
    resolved_contract: "202608",
  };
}

function msg(seq: number, product = "TXF", p = 23_000_000): FuturesWsMsg {
  return { type: "futures", seq, product, state: ps(product, p) };
}

function snap(seq: number): FuturesState {
  return { seq, products: { TXF: ps("TXF", 22_990_000) } };
}

describe("applyFuturesMsg(seq 對齊純邏輯)", () => {
  it("連續 seq → 併入該 product、不需 refetch", () => {
    const prev = snap(4);
    const out = applyFuturesMsg(prev, msg(5, "MXF", 23_010_000));
    expect(out.refetch).toBe(false);
    expect(out.next?.seq).toBe(5);
    expect(out.next?.products["MXF"]?.p).toBe(23_010_000);
    expect(out.next?.products["TXF"]?.p).toBe(22_990_000); // 其他 product 保留
  });

  it("跳號 → 不套用、需 refetch", () => {
    const prev = snap(4);
    const out = applyFuturesMsg(prev, msg(6));
    expect(out.refetch).toBe(true);
    expect(out.next).toBe(prev);
  });

  it("回退(seq ≤ 現值)→ 需 refetch", () => {
    const prev = snap(4);
    expect(applyFuturesMsg(prev, msg(4)).refetch).toBe(true);
    expect(applyFuturesMsg(prev, msg(2)).refetch).toBe(true);
  });

  it("state 未就緒(null)→ 需 refetch 對齊", () => {
    const out = applyFuturesMsg(null, msg(3));
    expect(out.refetch).toBe(true);
    expect(out.next).toBeNull();
  });
});

describe("mergePending(refetch 交錯緩衝)", () => {
  it("seq ≤ snapshot 丟棄;> 依序 last-write-wins", () => {
    const merged = mergePending(snap(4), [
      msg(3, "TXF", 1_000_000), // ≤ 4 → 丟
      msg(5, "TXF", 23_005_000),
      msg(6, "MXF", 23_010_000),
    ]);
    expect(merged.seq).toBe(6);
    expect(merged.products["TXF"]?.p).toBe(23_005_000);
    expect(merged.products["MXF"]?.p).toBe(23_010_000);
  });

  it("pending 空 → snapshot 原樣", () => {
    const s = snap(9);
    expect(mergePending(s, [])).toBe(s);
  });
});

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  fetchMock = vi.fn(async () => new Response(JSON.stringify(snap(1))));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function setup() {
  const hook = renderHook(() => useFuturesStream());
  await waitFor(() => expect(hook.result.current.state).not.toBeNull());
  const ws = FakeWS.instances[0]!;
  return { hook, ws };
}

describe("useFuturesStream", () => {
  it("初始 fetch /api/futures/state 建立全量", async () => {
    const { hook, ws } = await setup();
    expect(fetchMock).toHaveBeenCalledWith("/api/futures/state");
    expect(ws.url.endsWith("/ws/futures")).toBe(true);
    expect(hook.result.current.state?.seq).toBe(1);
    expect(hook.result.current.state?.products["TXF"]?.p).toBe(22_990_000);
  });

  it("連續 seq 的推播直接併入", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit(msg(2, "TXF", 23_002_000)));
    expect(hook.result.current.state?.seq).toBe(2);
    expect(hook.result.current.state?.products["TXF"]?.p).toBe(23_002_000);
  });

  it("seq 跳號觸發 refetch 全量對齊;交錯訊息 ≤ S 丟棄、> S 套用", async () => {
    const { hook, ws } = await setup();
    let resolveRefetch: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((res) => { resolveRefetch = res; }),
    );
    act(() => ws.emit(msg(4))); // 1→4 跳號 → refetch
    act(() => ws.emit(msg(5, "MXF", 23_020_000))); // 交錯:> S 該留
    act(() => ws.emit(msg(3, "TXF", 1_000_000))); // 交錯:≤ S 該丟
    act(() => {
      resolveRefetch(new Response(JSON.stringify(snap(4))));
    });
    await waitFor(() => expect(hook.result.current.state?.seq).toBe(5));
    expect(hook.result.current.state?.products["MXF"]?.p).toBe(23_020_000);
    expect(hook.result.current.state?.products["TXF"]?.p).toBe(22_990_000); // 沒被 seq3 汙染
  });

  it("重連 onopen 後 refetch 對齊", async () => {
    const { ws } = await setup();
    const calls = fetchMock.mock.calls.length;
    act(() => ws.onopen?.());
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(calls));
  });

  it("斷線 wsStatus=closed;unmount 關 socket", async () => {
    const { hook, ws } = await setup();
    act(() => ws.onclose?.());
    expect(hook.result.current.wsStatus).toBe("closed");
    hook.unmount();
    expect(ws.closed).toBe(true);
  });
});
