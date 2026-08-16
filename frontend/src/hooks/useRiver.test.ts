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

  // 🔒 lock(review F-1):`onDelta` 順序契約第 1 段 —— **seq 守衛在換場判定之前**。
  // 舊 seq 的跨場 delta 是重播 / 亂序抵達的舊訊息,不是「換場」這個事實;先讓它跑換場判定
  // 的話,每次亂序就多打一份全量(滿窗夜盤 60–80 KB)並把 sessionRef 撥到舊場,而畫面
  // 完全看不出來。上面「舊 seq 的 delta 丟棄」只驗同場的資料面,沒有守副作用面。
  it("舊 seq 的跨場 delta 整則丟棄:不觸發回補、盤別不變", async () => {
    const { hook, ws } = await setup();
    const before = fetchMock.mock.calls.length;

    act(() => ws.emit(delta(0, 30, 40_500_000, "night"))); // seq 0 < 已見的 1

    // `load()` 內的 fetch 是**同步**發出的(async 函式跑到第一個 await 才讓出),
    // 「有沒有多打」在 emit 回來的當下就是定論,不必等任何 tick
    expect(fetchMock.mock.calls.length).toBe(before);
    expect(hook.result.current.state?.session).toBe("day");
    expect(hook.result.current.state?.window).toEqual(DAY);
    expect(txfMinutes(hook.result.current.state)["30"]).toBeUndefined();
  });

  // 🔒 lock(review F-1):`onDelta` 順序契約第 2 段 —— `sessionRef.current !== null` 守衛。
  // REST 503(引擎未就緒)時還沒有任何 snapshot,ref 仍是 null;拿 null 去比 `msg.session`
  // 恆為「不同」= 每一則 delta 都被當成換場,等於每秒打一份 /api/river/state ——
  // 而畫面照樣空白(delta 無 snapshot 可併),症狀只在 network 面板看得到。
  it("無 snapshot(REST 503)時的換場 delta 不觸發回補", async () => {
    fetchMock.mockImplementation(
      async () =>
        new Response(JSON.stringify({ detail: { error: "RIVER_NOT_READY" } }), { status: 503 }),
    );
    const hook = renderHook(() => useRiver());
    await waitFor(() => expect(FakeWS.instances[0]).toBeTruthy());
    const ws = FakeWS.instances[0]!;
    const before = fetchMock.mock.calls.length; // 初載那一發已同步發出

    act(() => ws.emit(delta(2, 30, 40_500_000, "night")));

    expect(fetchMock.mock.calls.length).toBe(before);
    expect(hook.result.current.state).toBeNull();
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

    // 先等「換場回補的 night snapshot 真的併進 state」—— 它同時是兩件事的證據:
    // (1) 那一發回補確實跑完了(上界斷言因此不必靠固定 sleep 賭「已經有機會多打」),
    // (2) 「少打一發」不能靠把整條路徑拆掉來假綠。
    await waitFor(() => expect(txfMinutes(hook.result.current.state)["31"]).toBe(40_600_000));
    expect(fetchMock.mock.calls.length).toBe(before + 1);
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

  // 🔒 lock(review TD-4):同 `useCorrelation.test.ts` —— 「unmount → 連線關閉」原本只由
  // 已刪除的 `CorrSection.lazy.test.tsx` 間接守著。江波圖這條更貴:留著的連線會持續收
  // delta(滿窗夜盤的全量回補 60–80 KB 也可能被觸發)。斷 `closed` 而非「元件消失」;
  // `instances.length` 不變 = cleanup 的 close 沒有反過來排一次重連。
  it("unmount → WS 關閉且不重連(instances 數不增)", async () => {
    const { hook, ws } = await setup();
    expect(ws.closed).toBe(false);
    const before = FakeWS.instances.length;

    hook.unmount();

    expect(ws.closed).toBe(true);
    expect(FakeWS.instances.length).toBe(before);
  });

  it("onopen → open;onclose → closed", async () => {
    const { hook, ws } = await setup();

    act(() => ws.onopen?.());
    expect(hook.result.current.wsStatus).toBe("open");

    act(() => ws.onclose?.());
    expect(hook.result.current.wsStatus).toBe("closed");
  });
});
