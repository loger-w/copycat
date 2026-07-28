/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PriceLadder } from "@/components/stock/PriceLadder";
import { ARM_IDLE_MS } from "@/lib/flash-arm";
import type { CapitalOrder } from "@/types";

const META = {
  name: "測試",
  ref: 100_000,
  upper: 110_000,
  lower: 90_000,
  y_close: 100_000,
  y_vol: 10,
};

const BOOK = {
  bids: [[100_000, 30]] as [number, number][],
  asks: [[100_500, 10]] as [number, number][],
};

const LAST = { p: 100_000, t: "09:10:00.000", cum_vol: 5 };

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {}
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Route = (init?: RequestInit) => Response | Promise<Response>;

function mockFetch(routes: Record<string, Route>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    for (const [prefix, make] of Object.entries(routes)) {
      if (url.includes(prefix)) return make(init ?? undefined);
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
}

function capitalOrder(overrides: Partial<CapitalOrder> = {}): CapitalOrder {
  return {
    seq_no: "001",
    stock_no: "2330",
    name: "台積電",
    market: "TS",
    buy_sell: "B",
    flag_label: "現股",
    book_no: "A1",
    status_raw: "0",
    status_label: "已委託",
    price: 100,
    avg_fill_price: null,
    order_qty: 2,
    filled_qty: 0,
    unit: "張",
    date: "20260728",
    time: "09:01:00",
    pre_order: false,
    error_msg: null,
    actionable: true,
    raw: "",
    ...overrides,
  };
}

const OK_RESULT = { ok: true, code: 0, message: "ok", seq_no: "001" };

let qc: QueryClient;

function ladder(code = "2330", last: typeof LAST | null = LAST) {
  return (
    <QueryClientProvider client={qc}>
      <PriceLadder code={code} book={BOOK} last={last} meta={META} />
    </QueryClientProvider>
  );
}

function expand(): void {
  fireEvent.click(screen.getByRole("button", { name: "閃電梯" }));
}

function armUp(): void {
  fireEvent.click(screen.getByRole("button", { name: "武裝" }));
}

beforeEach(() => {
  window.localStorage.clear();
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  // jsdom 無 scrollIntoView(跟隨置中 / 置中事件 spy stub)
  Element.prototype.scrollIntoView = vi.fn();
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("PriceLadder(既有顯示行為)", () => {
  it("預設收合:只有「閃電梯」鈕;點擊展開出現價格列(SC-7)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    expect(screen.queryByText("110")).toBeNull();
    expand();
    expect(screen.getByText("110")).toBeTruthy(); // 漲停端點
    expect(screen.getByText("90")).toBeTruthy(); // 跌停端點
  });

  it("五檔量對映顯示於對應價位列(買賣側各自可點區)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    expand();
    expect(screen.getByLabelText("買 100").textContent).toBe("30");
    expect(screen.getByLabelText("賣 100.5").textContent).toBe("10");
  });

  it("±5% 外價位買賣側皆反灰不可點(SC-7)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    expand();
    expect(screen.getByLabelText("買 110").hasAttribute("disabled")).toBe(true);
    expect(screen.getByLabelText("賣 110").hasAttribute("disabled")).toBe(true);
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(false);
  });

  it("跟隨置中預設開,center 變更觸發 scrollIntoView", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    const { rerender } = render(ladder());
    expand();
    expect(
      screen.getByRole("button", { name: "跟隨置中" }).getAttribute("aria-pressed"),
    ).toBe("true");
    const spy = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    spy.mockClear();
    rerender(ladder("2330", { ...LAST, p: 101_000 }));
    expect(spy).toHaveBeenCalled();
  });

  it("無 ref 與 last → 顯示「無資料」(edge 6)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(
      <QueryClientProvider client={qc}>
        <PriceLadder
          code="2330"
          book={null}
          last={null}
          meta={{ ...META, ref: null, upper: null, lower: null }}
        />
      </QueryClientProvider>,
    );
    expand();
    expect(screen.getByText("無資料")).toBeTruthy();
  });
});

describe("PriceLadder 武裝直送(SC-7)", () => {
  it("武裝點價:1 次 API call + payload 斷言;鈕轉「解除」紅底", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    expand();
    armUp();
    const disarmBtn = screen.getByRole("button", { name: "解除" });
    expect(disarmBtn.getAttribute("aria-pressed")).toBe("true");
    expect(disarmBtn.className).toContain("bg-loss");
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      stock_no: "2330",
      buy_sell: "buy",
      price: 100,
      qty: 1,
      price_type: "limit",
      time_in_force: "ROD",
      trade_kind: "cash",
      source: "flash",
    });
  });

  it("未武裝點價:零請求 + hint「未武裝 — 點價不送單」3s 自動消失", () => {
    vi.useFakeTimers();
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    expand();
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    expect(screen.getByText("未武裝 — 點價不送單")).toBeTruthy();
    expect(bodies.length).toBe(0);
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(screen.queryByText("未武裝 — 點價不送單")).toBeNull();
  });

  it("同格 500ms 防抖:連點同格 1 call;不同格照送", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    expand();
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies).toMatchObject([{ buy_sell: "buy" }, { buy_sell: "sell" }]);
  });

  it("code 變更自動解除武裝(symbol_changed)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    const { rerender } = render(ladder());
    expand();
    armUp();
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    rerender(ladder("2317"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("Esc 鍵解除武裝", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    expand();
    armUp();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("capital WS 轉 closed 自動解除(conn_lost)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    expand();
    armUp();
    const ws = FakeWS.instances.find((w) => w.url.endsWith("/ws/capital"))!;
    act(() => {
      ws.onopen?.();
      ws.onclose?.();
    });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("idle 5 分鐘自動解除", () => {
    vi.useFakeTimers();
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    expand();
    armUp();
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 1);
    });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("無券(daytrade_sell)鎖買側;賣側照送且 payload 帶 trade_kind", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    expand();
    armUp();
    fireEvent.change(screen.getByLabelText("交易別"), { target: { value: "daytrade_sell" } });
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(true);
    expect(screen.getByLabelText("賣 100.5").hasAttribute("disabled")).toBe(false);
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ buy_sell: "sell", trade_kind: "daytrade_sell" });
  });

  it("qty 快捷同鍵累加 + 手動輸入重置;payload 帶累加後張數", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    expand();
    const qtyInput = screen.getByLabelText("張數") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect(qtyInput.value).toBe("6");
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    expect(qtyInput.value).toBe("5");
    fireEvent.change(qtyInput, { target: { value: "7" } });
    expect(qtyInput.value).toBe("7");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect(qtyInput.value).toBe("3");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect(qtyInput.value).toBe("6");
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ qty: 6 });
  });

  it("送單失敗:hint 顯示 tradeErrorText 文案;連 3 次失敗自動解除", async () => {
    mockFetch({
      "/api/capital/order/stock": () =>
        json({ detail: { error: "ORDER_BLOCKED", reason: "order_disabled" } }, 403),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    expand();
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(screen.getByText("安全閘拒絕(order_disabled)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 1 次失敗仍武裝
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    fireEvent.click(screen.getByLabelText("買 99.9"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
  });
});

describe("PriceLadder 掛單紅方格(SC-7)", () => {
  it("本檔活單價位聚合殘量;他檔/非活單不顯示;點擊逐 seq 直刪", async () => {
    const cancelBodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            capitalOrder({ seq_no: "001", price: 100, order_qty: 2, filled_qty: 0 }),
            capitalOrder({ seq_no: "002", price: 100, order_qty: 3, filled_qty: 1 }),
            capitalOrder({ seq_no: "003", buy_sell: "S", price: 100.5, order_qty: 1 }),
            capitalOrder({ seq_no: "004", price: 100, actionable: false }),
            capitalOrder({ seq_no: "005", stock_no: "2317", price: 100 }),
          ],
        }),
    });
    render(ladder());
    expand();
    const buyLot = await screen.findByLabelText("刪 100 買單");
    expect(buyLot.textContent).toBe("4"); // 2 + (3-1)
    expect(screen.getByLabelText("刪 100.5 賣單").textContent).toBe("1");
    expect(screen.queryByLabelText("刪 99.9 買單")).toBeNull();
    fireEvent.click(buyLot);
    await waitFor(() => expect(cancelBodies.length).toBe(2));
    expect(cancelBodies).toMatchObject([
      { seq_no: "001", market: "sec" },
      { seq_no: "002", market: "sec" },
    ]);
  });
});

describe("PriceLadder 置中事件(OrderBook 接點)", () => {
  it("stock-price-click(本檔)→ 該價置中且不送單;他檔忽略", () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    expand();
    const spy = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    spy.mockClear();
    act(() => {
      window.dispatchEvent(
        new CustomEvent("stock-price-click", {
          detail: { priceMilli: 100_500, side: "ask", code: "2330" },
        }),
      );
    });
    expect(spy).toHaveBeenCalled();
    expect(bodies.length).toBe(0);
    expect(
      screen.getByRole("button", { name: "跟隨置中" }).getAttribute("aria-pressed"),
    ).toBe("false");
    spy.mockClear();
    act(() => {
      window.dispatchEvent(
        new CustomEvent("stock-price-click", {
          detail: { priceMilli: 100_500, side: "ask", code: "9999" },
        }),
      );
    });
    expect(spy).not.toHaveBeenCalled();
  });
});
