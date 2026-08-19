/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  emitCapitalEvent,
  parseCapitalError,
  setCapitalWsStatus,
  subscribeCapitalEvents,
  useCapitalOrders,
  useCapitalPositions,
  useCapitalStream,
  useCapitalWsStatus,
  type CapitalEvent,
} from "@/hooks/useCapital";
import { resetWsPingMemory } from "@/lib/ws-reconnect";

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

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  FakeWS.instances = [];
  setCapitalWsStatus("connecting"); // module store 跨測試重置
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ orders: [], positions: [] })));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function makeWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function newClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("subscribeCapitalEvents(pub/sub)", () => {
  it("多 listener 廣播;退訂後不再收", () => {
    const got1: CapitalEvent[] = [];
    const got2: CapitalEvent[] = [];
    const un1 = subscribeCapitalEvents((ev) => got1.push(ev));
    const un2 = subscribeCapitalEvents((ev) => got2.push(ev));
    emitCapitalEvent({ event: "capital_order", data: { seq_no: "001" } });
    expect(got1.length).toBe(1);
    expect(got2.length).toBe(1);
    un1();
    emitCapitalEvent({ event: "capital_status", data: {} });
    expect(got1.length).toBe(1);
    expect(got2.length).toBe(2);
    un2();
  });

  it("無 listener 時 emit 不炸", () => {
    expect(() => emitCapitalEvent({ event: "capital_position", data: {} })).not.toThrow();
  });
});

describe("parseCapitalError", () => {
  it("detail.error 碼原樣回傳", async () => {
    const res = new Response(JSON.stringify({ detail: { error: "CAPITAL_DOWN" } }), {
      status: 502,
    });
    expect(await parseCapitalError(res)).toBe("CAPITAL_DOWN");
  });

  it("ORDER_BLOCKED 帶 reason 以 : 後綴(trade-text 解析契約)", async () => {
    const res = new Response(
      JSON.stringify({ detail: { error: "ORDER_BLOCKED", reason: "order_disabled" } }),
      { status: 403 },
    );
    expect(await parseCapitalError(res)).toBe("ORDER_BLOCKED:order_disabled");
  });

  it("非 JSON body 回 HTTP_ 狀態碼", async () => {
    const res = new Response("boom", { status: 500 });
    expect(await parseCapitalError(res)).toBe("HTTP_500");
  });

  it("BROKER_REJECTED 帶 err_code 以 : 後綴(群益拒單透傳;review A2)", async () => {
    const res = new Response(
      JSON.stringify({ detail: { error: "BROKER_REJECTED", err_code: "1097", err_msg: "廢單" } }),
      { status: 400 },
    );
    expect(await parseCapitalError(res)).toBe("BROKER_REJECTED:1097");
  });
});

describe("useCapitalStream(WS 連線 + wsStatus store)", () => {
  it("連 /ws/capital;訊息轉發到全域 listener;wsStatus store 轉態", () => {
    const got: CapitalEvent[] = [];
    const unsub = subscribeCapitalEvents((ev) => got.push(ev));
    const hook = renderHook(
      () => {
        useCapitalStream();
        return useCapitalWsStatus();
      },
      { wrapper: makeWrapper(newClient()) },
    );
    const ws = FakeWS.instances[0]!;
    expect(ws.url.endsWith("/ws/capital")).toBe(true);
    expect(hook.result.current).toBe("connecting");
    act(() => ws.onopen?.());
    expect(hook.result.current).toBe("open");
    act(() => ws.emit({ event: "capital_order", data: { seq_no: "001" } }));
    expect(got.some((ev) => ev.event === "capital_order")).toBe(true);
    unsub();
  });

  it("斷線標 closed 並退避重連;unmount 關 socket", () => {
    vi.useFakeTimers();
    const hook = renderHook(
      () => {
        useCapitalStream();
        return useCapitalWsStatus();
      },
      { wrapper: makeWrapper(newClient()) },
    );
    act(() => {
      FakeWS.instances[0]!.onopen?.();
      FakeWS.instances[0]!.onclose?.();
    });
    expect(hook.result.current).toBe("closed");
    act(() => {
      vi.advanceTimersByTime(1_100);
    });
    expect(FakeWS.instances.length).toBe(2);
    hook.unmount();
    expect(FakeWS.instances[1]!.closed).toBe(true);
  });

  it("收過 ping 後 35 s 全靜默 → wsStatus 轉 closed(W11:閃電武裝往安全方向解除)", () => {
    resetWsPingMemory();
    vi.useFakeTimers();
    const hook = renderHook(
      () => {
        useCapitalStream();
        return useCapitalWsStatus();
      },
      { wrapper: makeWrapper(newClient()) },
    );
    const ws = FakeWS.instances[0]!;
    act(() => {
      ws.onopen?.();
      ws.emit({ type: "ping" });
    });
    expect(hook.result.current).toBe("open");

    act(() => {
      vi.advanceTimersByTime(35_000);
    });
    expect(ws.closed).toBe(true);
    expect(hook.result.current).toBe("closed");
    hook.unmount();
  });

  it("從未收 ping:60 s 全靜默仍是 open(舊後端不多出 closed 邊沿;W11)", () => {
    resetWsPingMemory();
    vi.useFakeTimers();
    const hook = renderHook(
      () => {
        useCapitalStream();
        return useCapitalWsStatus();
      },
      { wrapper: makeWrapper(newClient()) },
    );
    const ws = FakeWS.instances[0]!;
    act(() => ws.onopen?.());
    expect(hook.result.current).toBe("open");

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(ws.closed).toBe(false);
    expect(hook.result.current).toBe("open");
    expect(FakeWS.instances.length).toBe(1);
    hook.unmount();
  });

  it("useCapitalWsStatus 可在 stream 外元件讀(module store + 測試 setter)", () => {
    const hook = renderHook(() => useCapitalWsStatus());
    expect(hook.result.current).toBe("connecting");
    act(() => setCapitalWsStatus("closed"));
    expect(hook.result.current).toBe("closed");
  });
});

describe("useCapitalStream = 唯一 invalidate 擁有者(review B2/B4)", () => {
  it("capital_order 事件 200ms trailing debounce 後 invalidate 一次", () => {
    vi.useFakeTimers();
    const client = newClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    renderHook(() => useCapitalStream(), { wrapper: makeWrapper(client) });
    act(() => {
      emitCapitalEvent({ event: "capital_order", data: { seq_no: "001" } });
      emitCapitalEvent({ event: "capital_order", data: { seq_no: "002" } });
    });
    act(() => {
      vi.advanceTimersByTime(199);
    });
    expect(spy).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["capital-orders"] });
  });

  it("capital_position → invalidate positions;capital_status 不觸發任何 invalidate", () => {
    vi.useFakeTimers();
    const client = newClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    renderHook(() => useCapitalStream(), { wrapper: makeWrapper(client) });
    act(() => {
      emitCapitalEvent({ event: "capital_position", data: { count: 2 } });
      emitCapitalEvent({ event: "capital_status", data: {} });
      vi.advanceTimersByTime(200);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["capital-positions"] });
  });

  it("orders/positions hooks 多處掛載:單事件仍單 invalidate(review B4)", () => {
    vi.useFakeTimers();
    const client = newClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    renderHook(
      () => {
        useCapitalStream();
        useCapitalOrders();
        useCapitalOrders();
        useCapitalPositions();
      },
      { wrapper: makeWrapper(client) },
    );
    act(() => {
      emitCapitalEvent({ event: "capital_order", data: { seq_no: "001" } });
      vi.advanceTimersByTime(200);
    });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["capital-orders"] });
  });

  it("stream 未掛載:orders/positions hooks 不自行接 WS 事件(review B2)", () => {
    vi.useFakeTimers();
    const client = newClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    renderHook(
      () => {
        useCapitalOrders();
        useCapitalPositions();
      },
      { wrapper: makeWrapper(client) },
    );
    act(() => {
      emitCapitalEvent({ event: "capital_order", data: {} });
      emitCapitalEvent({ event: "capital_position", data: {} });
      vi.advanceTimersByTime(300);
    });
    expect(spy).not.toHaveBeenCalled();
  });

  it("stream unmount 後事件不再 invalidate(退訂 + 清 timer)", () => {
    vi.useFakeTimers();
    const client = newClient();
    const spy = vi.spyOn(client, "invalidateQueries");
    const hook = renderHook(() => useCapitalStream(), { wrapper: makeWrapper(client) });
    act(() => {
      emitCapitalEvent({ event: "capital_order", data: {} });
    });
    hook.unmount();
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(spy).not.toHaveBeenCalled();
  });
});
