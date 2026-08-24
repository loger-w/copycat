/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTxoSnapshot } from "@/hooks/useTxoSnapshot";
import { WS_BACKOFF_START_MS, WS_WATCHDOG_JITTER_MS } from "@/lib/ws-reconnect";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
    this.onclose?.();
  }
}

describe("useTxoSnapshot", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("收到訊息更新 data 與 wsStatus", () => {
    const { result } = renderHook(() => useTxoSnapshot());
    const ws = FakeWebSocket.instances[0];
    expect(ws).toBeDefined();
    act(() => {
      ws?.onopen?.();
      ws?.onmessage?.({ data: JSON.stringify({ series_id: "TX4.202607", curve: [] }) });
    });
    expect(result.current.wsStatus).toBe("open");
    expect(result.current.data?.series_id).toBe("TX4.202607");
  });

  it("斷線後標記 closed 並排程重連", () => {
    const { result } = renderHook(() => useTxoSnapshot());
    act(() => {
      FakeWebSocket.instances[0]?.onopen?.();
      FakeWebSocket.instances[0]?.onclose?.();
    });
    expect(result.current.wsStatus).toBe("closed");
    act(() => {
      vi.advanceTimersByTime(1_100);
    });
    expect(FakeWebSocket.instances.length).toBe(2);
  });

  it("unmount 關閉 socket", () => {
    const { unmount } = renderHook(() => useTxoSnapshot());
    unmount();
    expect(FakeWebSocket.instances[0]?.closed).toBe(true);
  });

  it("心跳 ping 不覆蓋 snapshot(SC-3)", () => {
    const { result } = renderHook(() => useTxoSnapshot());
    const ws = FakeWebSocket.instances[0];
    expect(ws).toBeDefined();
    act(() => {
      ws?.onopen?.();
      ws?.onmessage?.({ data: JSON.stringify({ series_id: "TX4.202607", curve: [] }) });
    });
    expect(result.current.data?.series_id).toBe("TX4.202607");

    act(() => {
      ws?.onmessage?.({ data: JSON.stringify({ type: "ping" }) });
    });
    expect(result.current.data?.series_id).toBe("TX4.202607"); // 仍是原 snapshot
  });

  it("收過 ping 後 35 s 全靜默 → 卸掉半死 socket 並重連(SC-2)", () => {
    const { result } = renderHook(() => useTxoSnapshot());
    const ws = FakeWebSocket.instances[0];
    expect(ws).toBeDefined();
    act(() => {
      ws?.onopen?.();
      ws?.onmessage?.({ data: JSON.stringify({ type: "ping" }) });
    });
    expect(result.current.wsStatus).toBe("open");

    act(() => {
      vi.advanceTimersByTime(35_000);
    });
    expect(ws?.closed).toBe(true);
    expect(result.current.wsStatus).toBe("closed");

    act(() => {
      // watchdog 放棄路徑 = 1 s backoff + [0, WS_WATCHDOG_JITTER_MS) 抖動(R4 N038)
      vi.advanceTimersByTime(WS_BACKOFF_START_MS + WS_WATCHDOG_JITTER_MS);
    });
    expect(FakeWebSocket.instances.length).toBe(2);
    expect(result.current.wsStatus).toBe("connecting");
  });
});
