/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FuturesLadder } from "@/components/futures/FuturesLadder";
import { setCapitalWsStatus } from "@/hooks/useCapital";
import { ARM_IDLE_MS } from "@/lib/flash-arm";
import type { CapitalOrder, FuturesProductState } from "@/types";

const TXF_STATE: FuturesProductState = {
  product: "TXF",
  name: "臺股期貨",
  p: 23_000_000,
  q: 3,
  cum_vol: 12_000,
  t: "09:10:00",
  date: "20260728",
  bids: [[22_999_000, 45]],
  asks: [[23_001_000, 88]],
  ref: 22_800_000,
  upper: 25_080_000,
  lower: 20_520_000,
  resolved_contract: "202609",
};

const MXF_STATE: FuturesProductState = {
  ...TXF_STATE,
  product: "MXF",
  name: "小型臺指",
};

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

function futOrder(overrides: Partial<CapitalOrder> = {}): CapitalOrder {
  return {
    seq_no: "F01",
    stock_no: "TXFI6",
    name: "臺股期貨",
    market: "TF",
    buy_sell: "B",
    flag_label: null,
    book_no: "B1",
    status_raw: "0",
    status_label: "已委託",
    price: 23_000,
    avg_fill_price: null,
    order_qty: 2,
    filled_qty: 0,
    unit: "口",
    date: "20260728",
    time: "09:01:00",
    pre_order: false,
    error_msg: null,
    actionable: true,
    raw: "",
    ...overrides,
  };
}

const OK_RESULT = { ok: true, code: 0, message: "ok", seq_no: "F01" };

let qc: QueryClient;

function ladder(state: FuturesProductState | null = TXF_STATE, product = "TXF") {
  return (
    <QueryClientProvider client={qc}>
      <FuturesLadder product={product} state={state} />
    </QueryClientProvider>
  );
}

function armUp(): void {
  fireEvent.click(screen.getByRole("button", { name: "武裝" }));
}

beforeEach(() => {
  window.localStorage.clear();
  setCapitalWsStatus("connecting"); // wsStatus module store 跨測試重置
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

describe("FuturesLadder 武裝直送(SC-8)", () => {
  it("武裝點價:1 次 API call;payload 帶 HOT symbol + day_trade 預設 false", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      tc4_symbol: "TC.F.TWF.TXF.HOT",
      buy_sell: "buy",
      price: 22_999,
      qty: 1,
      price_type: "limit",
      time_in_force: "ROD",
      day_trade: false,
      source: "flash",
    });
  });

  it("當沖 checkbox 開啟 → payload day_trade: true", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    const dayTrade = screen.getByLabelText("當沖") as HTMLInputElement;
    expect(dayTrade.checked).toBe(false); // 預設關
    fireEvent.click(dayTrade);
    armUp();
    fireEvent.click(screen.getByLabelText("賣 23001"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ buy_sell: "sell", day_trade: true });
  });

  it("未武裝點價:零請求 + hint「未武裝 — 點價不送單」", () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    fireEvent.click(screen.getByLabelText("買 22999"));
    expect(screen.getByText("未武裝 — 點價不送單")).toBeTruthy();
    expect(bodies.length).toBe(0);
  });

  it("resolved_contract null → 武裝鈕 disabled(title 合約未解析)且點價零請求", () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder({ ...TXF_STATE, resolved_contract: null }));
    const armBtn = screen.getByRole("button", { name: "武裝" });
    expect(armBtn.hasAttribute("disabled")).toBe(true);
    expect(armBtn.getAttribute("title")).toBe("合約未解析");
    fireEvent.click(armBtn);
    fireEvent.click(screen.getByLabelText("買 22999"));
    expect(bodies.length).toBe(0);
  });

  it("同格 500ms 防抖:連點同格 1 call;不同格照送", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    fireEvent.click(screen.getByLabelText("買 22999"));
    fireEvent.click(screen.getByLabelText("賣 23001"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies).toMatchObject([{ buy_sell: "buy" }, { buy_sell: "sell" }]);
  });

  it("product 變更自動解除武裝(symbol_changed)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    const { rerender } = render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    rerender(ladder(MXF_STATE, "MXF"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("capital wsStatus 轉 closed 自動解除(conn_lost;wsStatus store 注入)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    armUp();
    act(() => setCapitalWsStatus("open"));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    act(() => setCapitalWsStatus("closed"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });
});

describe("FuturesLadder 武裝防護(review C3/C4)", () => {
  it("idle 5 分鐘自動解除", () => {
    vi.useFakeTimers();
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 1);
    });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("送單 400:hint 顯示 tradeErrorText 文案;連 3 次失敗自動解除", async () => {
    mockFetch({
      "/api/capital/order/future": () =>
        json({ detail: { error: "BROKER_REJECTED", err_code: "1097", err_msg: "廢單" } }, 400),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(screen.getByText("券商拒單(1097)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 1 次失敗仍武裝
    fireEvent.click(screen.getByLabelText("賣 23001"));
    fireEvent.click(screen.getByLabelText("買 23000"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
  });

  it("200 但 ok:false(結果未知 code=-1)→ hint 顯示 message 且 failStreak 累積", async () => {
    mockFetch({
      "/api/capital/order/future": () =>
        json({ ok: false, code: -1, message: "結果未知(逾時)", seq_no: null }),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(screen.getByText("結果未知(逾時)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 1 次失敗仍武裝
    fireEvent.click(screen.getByLabelText("賣 23001"));
    fireEvent.click(screen.getByLabelText("買 23000"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
  });

  it("qty 快捷「3」按兩下累加 → payload qty 6(review C4)", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect((screen.getByLabelText("口數") as HTMLInputElement).value).toBe("6");
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ qty: 6 });
  });
});

describe("FuturesLadder 掛單紅方格(SC-8)", () => {
  it("本契約活單聚合口數;他契約不顯示;點擊逐 seq 直刪(market=fut)", async () => {
    const cancelBodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            futOrder({ seq_no: "F01", price: 23_000, order_qty: 2, filled_qty: 0 }),
            futOrder({ seq_no: "F02", price: 23_000, order_qty: 3, filled_qty: 1 }),
            futOrder({ seq_no: "F03", stock_no: "MXFI6", price: 23_001 }),
          ],
        }),
    });
    render(ladder());
    const lot = await screen.findByLabelText("刪 23000 掛單");
    expect(lot.textContent).toBe("4"); // 2 + (3-1)
    expect(screen.queryByLabelText("刪 23001 掛單")).toBeNull(); // 他契約
    fireEvent.click(lot);
    await waitFor(() => expect(cancelBodies.length).toBe(2));
    expect(cancelBodies).toMatchObject([
      { seq_no: "F01", market: "fut" },
      { seq_no: "F02", market: "fut" },
    ]);
  });
});
