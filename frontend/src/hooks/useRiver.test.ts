/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRiver } from "@/hooks/useRiver";
import type { RiverDelta, RiverState } from "@/types";

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
    this.onclose?.();
  }

  emit(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
}

const DAY = { start_min: 525, end_min: 825 };
const NIGHT = { start_min: 900, end_min: 1740 };

function snap(seq: number, minutes: Record<string, number>, session = "day"): RiverState {
  return {
    type: "river",
    seq,
    session,
    base: "TXF",
    window: session === "day" ? DAY : NIGHT,
    legs: {
      TXF: { label: "台指", minutes, last: null, last_minute: null },
      NQ: { label: "納指", minutes: {}, last: null, last_minute: null },
    },
  };
}

function delta(seq: number, m: number, p: number, session = "day"): RiverDelta {
  return {
    type: "river_delta",
    seq,
    session,
    window: session === "day" ? DAY : NIGHT,
    legs: { TXF: { m, p }, NQ: null },
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  fetchMock = vi.fn(async () => new Response(JSON.stringify(snap(1, { "10": 40_000_000 }))));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function setup() {
  const hook = renderHook(() => useRiver());
  await waitFor(() => expect(hook.result.current.state).not.toBeNull());
  const ws = FakeWS.instances[0]!;
  return { hook, ws };
}

function txfMinutes(state: RiverState | null): Record<string, number> {
  return state?.legs["TXF"]?.minutes ?? {};
}

describe("useRiver", () => {
  it("初次載入打 REST 全量,WS 連 /ws/river", async () => {
    const { hook, ws } = await setup();

    expect(fetchMock).toHaveBeenCalledWith("/api/river/state");
    expect(ws.url.endsWith("/ws/river")).toBe(true);
    expect(txfMinutes(hook.result.current.state)).toEqual({ "10": 40_000_000 });
  });

  it("delta 併進既有分鐘序列(不是取代)", async () => {
    const { hook, ws } = await setup();

    act(() => ws.emit(delta(2, 11, 40_100_000)));

    expect(txfMinutes(hook.result.current.state)).toEqual({
      "10": 40_000_000,
      "11": 40_100_000,
    });
    expect(hook.result.current.state?.legs["TXF"]?.last).toBe(40_100_000);
  });

  it("舊 seq 的 delta 丟棄", async () => {
    const { hook, ws } = await setup();

    act(() => ws.emit(delta(5, 11, 40_100_000)));
    act(() => ws.emit(delta(3, 12, 40_200_000)));

    expect(txfMinutes(hook.result.current.state)["12"]).toBeUndefined();
  });

  it("比 delta 舊的 snapshot 仍補進缺的分鐘(review P1-1 迴歸)", async () => {
    const { hook, ws } = await setup();
    act(() => ws.emit(delta(9, 20, 40_900_000)));

    // WS 首則 snapshot(或重連後補抓)seq 比 delta 舊 —— 不可整份丟掉,
    // 否則回補資料永遠進不了畫面
    act(() => ws.emit(snap(2, { "5": 39_900_000, "20": 1 })));

    const minutes = txfMinutes(hook.result.current.state);
    expect(minutes["5"]).toBe(39_900_000); // 補進缺的
    expect(minutes["20"]).toBe(40_900_000); // 既有(較新的 delta)不被覆蓋
  });

  it("server 重啟(snapshot seq 歸零)後,小 seq 的 delta 仍要生效", async () => {
    // Phase 4 自評 finding:seq 若取 max,server 重啟(river_seq 從 0 起算)後
    // 所有 delta 都會被當成「舊訊息」丟掉,畫面凍在 snapshot 那一刻直到 seq 追上舊值。
    const { hook, ws } = await setup();
    act(() => ws.emit(delta(500, 20, 40_900_000)));

    act(() => ws.emit(snap(0, { "5": 39_900_000 }))); // 重連後的首則 snapshot
    act(() => ws.emit(delta(1, 6, 39_950_000)));

    expect(txfMinutes(hook.result.current.state)["6"]).toBe(39_950_000);
  });

  it("盤別變更 → 清空 + 換窗 + 重抓全量", async () => {
    const { hook, ws } = await setup();
    fetchMock.mockClear();
    fetchMock.mockImplementation(async () => new Response(JSON.stringify(snap(1, {}, "night"))));

    act(() => ws.emit(delta(2, 30, 40_500_000, "night")));

    expect(hook.result.current.state?.session).toBe("night");
    expect(hook.result.current.state?.window).toEqual(NIGHT);
    expect(txfMinutes(hook.result.current.state)).toEqual({ "30": 40_500_000 });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/river/state"));
  });

  // 🔴 react-doctor P1(useRiver.ts:115-122):換場的 `void load()` 寫在 `setState` 的
  // updater 內 —— React 的 updater 契約是純函式,而全站包在 StrictMode(main.tsx)下 dev
  // 會 double-invoke,一次換場就打兩份 `/api/river/state` 全量快照(滿窗夜盤 60–80 KB)。
  // 上一條「盤別變更 → 清空 + 換窗 + 重抓全量」只鎖了「有打」的下界,打幾次不管。
  it("StrictMode 下換場的 /api/river/state 恰一發(updater 必須是純函式)", async () => {
    const hook = renderHook(() => useRiver(), { reactStrictMode: true });
    await waitFor(() => expect(hook.result.current.state).not.toBeNull());
    // StrictMode 的 effect double-invoke 會建兩條 FakeWS(第一條已在 cleanup 關掉)。
    // 對 instances[0] 發訊息會假綠:那條的 `alive` 已是 false,回補的 snapshot 會被丟掉。
    expect(FakeWS.instances.length).toBe(2);
    const ws = FakeWS.instances.at(-1)!;
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify(snap(3, { "31": 40_600_000 }, "night"))),
    );
    const before = fetchMock.mock.calls.length;

    act(() => ws.emit(delta(2, 30, 40_500_000, "night")));

    // 換場回補是非同步的,要等它有機會發生才算數(否則斷言的是「還沒打」)
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(fetchMock.mock.calls.length).toBe(before + 1);
    // 上界不是唯一要件:換場回補的 night snapshot 必須真的併進 state,
    // 否則「少打一發」可以靠把整條路徑拆掉來假綠。
    await waitFor(() => expect(txfMinutes(hook.result.current.state)["31"]).toBe(40_600_000));
    expect(hook.result.current.state?.session).toBe("night");
    expect(hook.result.current.state?.window).toEqual(NIGHT);
    expect(txfMinutes(hook.result.current.state)["30"]).toBe(40_500_000);
  });

  it("REST 503 → state 維持 null 且不拋", async () => {
    fetchMock.mockImplementation(
      async () => new Response(JSON.stringify({ detail: { error: "RIVER_NOT_READY" } }), { status: 503 }),
    );
    const hook = renderHook(() => useRiver());
    await waitFor(() => expect(FakeWS.instances[0]).toBeTruthy());

    expect(hook.result.current.state).toBeNull();
  });

  it("非 river 型別的訊息忽略,壞 JSON 不崩", async () => {
    const { hook, ws } = await setup();

    act(() => ws.emit({ type: "corr", seq: 99 }));
    act(() => ws.onmessage?.({ data: "{not json" }));

    expect(txfMinutes(hook.result.current.state)).toEqual({ "10": 40_000_000 });
  });

  it("onopen → open;onclose → closed", async () => {
    const { hook, ws } = await setup();

    act(() => ws.onopen?.());
    expect(hook.result.current.wsStatus).toBe("open");

    act(() => ws.onclose?.());
    expect(hook.result.current.wsStatus).toBe("closed");
  });
});
