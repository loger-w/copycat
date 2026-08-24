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

  it("WS 訊息帶 minutes → 整份替換(引擎自癒回補的送達契約)", async () => {
    const { hook, ws } = await setup();
    act(() =>
      ws.emit(
        wsMsg({
          twse: {
            p: 42_000_000, ref: 43_634_190, high: 43_221_930, low: 41_815_780,
            stale: false, last_minute: null, minutes: { "0910": 5, "0911": 6 },
          },
        } as never),
      ),
    );
    // 初載的 {"0901": ...} 不得殘留:自癒回補是全量真相源,替換不是 merge
    expect(hook.result.current.twse!.minutes).toEqual({ "0910": 5, "0911": 6 });
  });

  it("換日 refetch 失敗 → 退避重試回填,不永久缺線(fix/index-chart-empty-minutes)", async () => {
    const { hook, ws } = await setup();
    // 換日瞬間 state 端點打嗝一次(網路層失敗),之後恢復且已是新日全量
    fetchMock.mockImplementationOnce(async () => {
      throw new TypeError("network down");
    });
    fetchMock.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            ...STATE,
            trade_date: "2026-07-29",
            twse: { ...STATE.twse, minutes: { "0901": 1 } },
          }),
        ),
    );
    act(() => ws.emit(wsMsg({ trade_date: "2026-07-29" } as never)));
    // 現行 bug:失敗只 console.warn 不重試 → 失敗點之前的分鐘永久缺失(線整條不見)
    await waitFor(() => expect(hook.result.current.twse?.minutes).toEqual({ "0901": 1 }), {
      timeout: 5000,
    });
    expect(hook.result.current.tradeDate).toBe("2026-07-29");
  });

  it("先發後至的舊回應不得覆蓋新回應(review T-6 generation guard)", async () => {
    const { hook, ws } = await setup();
    // 慢途 refetch(舊日資料,手動控制 resolve);其後的呼叫快速回新日全量
    let resolveSlow: ((r: Response) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise<Response>((res) => {
          resolveSlow = res;
        }),
    );
    fetchMock.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            ...STATE,
            trade_date: "2026-07-29",
            twse: { ...STATE.twse, minutes: { "0901": 1 } },
          }),
        ),
    );
    act(() => ws.onopen?.()); // 觸發慢途 refetch(將回舊日)
    await waitFor(() => expect(resolveSlow).toBeDefined());
    act(() => ws.emit(wsMsg({ trade_date: "2026-07-29" } as never))); // 換日 → 新 refetch
    await waitFor(() => expect(hook.result.current.tradeDate).toBe("2026-07-29"));
    await act(async () => {
      resolveSlow!(new Response(JSON.stringify(STATE))); // 舊日回應遲到
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(hook.result.current.tradeDate).toBe("2026-07-29"); // 不得被舊日整份覆蓋
    expect(hook.result.current.twse!.minutes).toEqual({ "0901": 1 });
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

// 🔴 N119:handler 以 ref 讀 merge 基底,而 ref 只在 commit 後由 useLayoutEffect 同步 ——
// 同一個 macrotask 內兩則訊息時,第二則讀到的仍是**上一次 commit** 的 series → 第一則
// 的 last_minute 被靜默抹掉(下一格 upsert / onopen refetch 才自癒)。
describe("useIndexStream 同 tick 兩則訊息(N119)", () => {
  it("兩則 last_minute 都留下(第二則不以舊底覆蓋第一則)", async () => {
    const { hook, ws } = await setup();
    act(() => {
      ws.emit(wsMsg({ twse: { ...wsMsg().twse, last_minute: ["0932", 42_000_000] } as never }));
      ws.emit(wsMsg({ twse: { ...wsMsg().twse, last_minute: ["0933", 41_900_000] } as never }));
    });
    expect(hook.result.current.twse!.minutes).toEqual({
      "0901": 43_000_000,
      "0932": 42_000_000,
      "0933": 41_900_000,
    });
  });

  it("換日後同 tick 的第二則不再被判成換日(不重複清空 + 重抓)", async () => {
    const { hook, ws } = await setup();
    const before = fetchMock.mock.calls.length;
    act(() => {
      ws.emit(wsMsg({ trade_date: "2026-07-29" } as never));
      ws.emit(wsMsg({ trade_date: "2026-07-29" } as never));
    });
    expect(hook.result.current.tradeDate).toBe("2026-07-29");
    // 第一則觸發一次全量對齊;第二則的日期與本地已相同 → 不得再排一次
    expect(fetchMock.mock.calls.length - before).toBe(1);
  });

  // 🔴 N119 收修:`useLayoutEffect` backstop 移除後,**handler / refetch 的配對是 ref 的
  // 唯一寫入點**。這條打的是 refetch 路徑:全量回應在 microtask 裡寫 ref(此時 React 還沒
  // commit —— 排程走的是 macrotask),同一批抵達的增量必須以那份全量為基底。
  // 靠 commit 後的 effect 同步 ref 的話,這裡讀到的是**換日清空後的 null** → 全量的分鐘格
  // 被增量整份覆蓋掉,下一格 upsert 才自癒。
  it("全量在途:回應寫入 ref 後、commit 前抵達的增量以全量為基底", async () => {
    const { hook, ws } = await setup();
    const D2 = {
      ...STATE,
      trade_date: "2026-07-29",
      twse: { ...STATE.twse, minutes: { "0901": 43_000_000 } },
    };
    let release!: () => void;
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((res) => {
          release = () => res(new Response(JSON.stringify(D2)));
        }),
    );
    // 換日 → 清空 + 排一發全量(gate 住)
    act(() => ws.emit(wsMsg({ trade_date: "2026-07-29" } as never)));
    expect(hook.result.current.twse).toBeNull();

    await act(async () => {
      release();
      // 只 drain microtask(不讓出 macrotask)→ refetch 的 .then 跑完寫了 ref,
      // 而 React 的 render 仍排在 macrotask 上還沒 commit
      for (let i = 0; i < 8; i += 1) await Promise.resolve();
      ws.emit(
        wsMsg({
          trade_date: "2026-07-29",
          twse: { ...wsMsg().twse, last_minute: ["0940", 41_000_000] },
        } as never),
      );
    });

    expect(hook.result.current.twse!.minutes).toEqual({
      "0901": 43_000_000,
      "0940": 41_000_000,
    });
  });
});
