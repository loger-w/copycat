/** @vitest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCorrelation } from "@/hooks/useCorrelation";
import type { CorrState } from "@/types";

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

function snap(seq: number, w60: number | null = 0.5): CorrState {
  return {
    type: "corr",
    seq,
    session: "night",
    base: "TXF",
    windows: [60, 300, 1800],
    legs: {
      TXF: { label: "台指", mid: 40_400_000, stale: false },
      NQ: { label: "納指", mid: 27_001_000, stale: false },
    },
    pairs: { NQ: { w60, n60: 59, w300: null, n300: 59, w1800: null, n1800: 59 } },
  };
}

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
  const hook = renderHook(() => useCorrelation());
  await waitFor(() => expect(hook.result.current.state).not.toBeNull());
  const ws = FakeWS.instances[0]!;
  return { hook, ws };
}

describe("useCorrelation", () => {
  it("初次載入打 REST,不必等第一則推播", async () => {
    const { hook, ws } = await setup();

    expect(fetchMock).toHaveBeenCalledWith("/api/corr/state");
    expect(ws.url.endsWith("/ws/corr")).toBe(true);
    expect(hook.result.current.state?.seq).toBe(1);
  });

  it("推播為全量快照,直接取代(不做 seq 對齊)", async () => {
    const { hook, ws } = await setup();

    act(() => ws.emit(snap(2, 0.9)));

    expect(hook.result.current.state?.seq).toBe(2);
    expect(hook.result.current.state?.pairs["NQ"]?.["w60"]).toBe(0.9);
  });

  it("seq 跳號不觸發 refetch —— 全量快照最新即正確", async () => {
    const { hook, ws } = await setup();
    fetchMock.mockClear();

    act(() => ws.emit(snap(99, 0.1)));

    expect(hook.result.current.state?.seq).toBe(99);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("非 corr 型別的訊息忽略", async () => {
    const { hook, ws } = await setup();

    act(() => ws.emit({ type: "futures", seq: 5 }));

    expect(hook.result.current.state?.seq).toBe(1);
  });

  it("壞 JSON 不讓 hook 崩潰", async () => {
    const { hook, ws } = await setup();

    act(() => ws.onmessage?.({ data: "{not json" }));

    expect(hook.result.current.state?.seq).toBe(1);
  });

  it("onopen → wsStatus open;onclose → closed", async () => {
    const { hook, ws } = await setup();

    act(() => ws.onopen?.());
    expect(hook.result.current.wsStatus).toBe("open");

    act(() => ws.onclose?.());
    expect(hook.result.current.wsStatus).toBe("closed");
  });

  it("REST 失敗不拋,等推播補上", async () => {
    fetchMock.mockImplementationOnce(async () => {
      throw new Error("boom");
    });
    const hook = renderHook(() => useCorrelation());
    const ws = await waitFor(() => {
      const w = FakeWS.instances[0];
      expect(w).toBeTruthy();
      return w!;
    });

    act(() => ws.emit(snap(7)));

    expect(hook.result.current.state?.seq).toBe(7);
  });
});
