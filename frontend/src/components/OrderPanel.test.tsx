/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderPanel } from "@/components/OrderPanel";
import type { OrdersView, TradeAccount } from "@/types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const SYM = "TC.O.TWF.TXO.202607.C.23000";

function account(overrides: Partial<TradeAccount> = {}): TradeAccount {
  return {
    status: "ready",
    mode: "sim",
    account_masked: "****9000",
    broker_id: "SIM",
    audit_degraded: false,
    orderable_symbols: ["TC.F.TWF.FITX.HOT", SYM],
    ...overrides,
  };
}

const EMPTY_ORDERS: OrdersView = { orders: [], fills: [], degraded: false, audit_degraded: false };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockFetch(routes: Record<string, (init?: RequestInit) => Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url =
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    for (const [prefix, make] of Object.entries(routes)) {
      if (url.includes(prefix)) return make(init ?? undefined);
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
}

function renderPanel() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <OrderPanel />
    </QueryClientProvider>,
  );
}

describe("OrderPanel", () => {
  it("ready 時顯示模擬徽章且送單鈕可按", async () => {
    mockFetch({
      "/api/trade/account": () => json(account()),
      "/api/trade/orders": () => json(EMPTY_ORDERS),
    });
    renderPanel();
    expect(await screen.findByText("模擬")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    const btn = screen.getByText("送單(預覽)").closest("button");
    expect(btn?.getAttribute("disabled")).toBeNull();
  });

  it("touchance_down 時鈕 disabled 且顯示達錢未連線", async () => {
    mockFetch({
      "/api/trade/account": () => json(account({ status: "touchance_down", mode: null })),
      "/api/trade/orders": () => json(EMPTY_ORDERS),
    });
    renderPanel();
    expect(await screen.findByText(/達錢未連線/)).toBeTruthy();
    const btn = screen.getByText("送單(預覽)").closest("button");
    expect(btn?.getAttribute("disabled")).not.toBeNull();
  });

  it("切市價隱藏價格欄", async () => {
    mockFetch({
      "/api/trade/account": () => json(account()),
      "/api/trade/orders": () => json(EMPTY_ORDERS),
    });
    renderPanel();
    await screen.findByText("模擬");
    expect(screen.getByLabelText("價格(點)")).toBeTruthy();
    fireEvent.click(screen.getByText("市價"));
    expect(screen.queryByLabelText("價格(點)")).toBeNull();
  });

  it("送單(預覽)呼叫 preview API 並開啟確認 dialog", async () => {
    const previewBodies: unknown[] = [];
    mockFetch({
      "/api/trade/account": () => json(account()),
      "/api/trade/preview": (init) => {
        previewBodies.push(JSON.parse(String(init?.body)));
        return json({
          preview_id: "pv1",
          request_id: "rq1",
          param: {
            Symbol: SYM,
            BrokerID: "SIM",
            Account: "9999000",
            Side: "1",
            OrderType: "2",
            TimeInForce: "1",
            Price: "15.5",
            OrderQty: "1",
            PositionEffect: "4",
          },
          account_masked: "****9000",
          mode: "sim",
        });
      },
      "/api/trade/orders": () => json(EMPTY_ORDERS),
    });
    renderPanel();
    await screen.findByText("模擬");
    fireEvent.change(screen.getByLabelText("商品"), { target: { value: SYM } });
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    fireEvent.click(screen.getByText("送單(預覽)"));
    await waitFor(() => {
      expect(screen.getByText("確認送出")).toBeTruthy();
    });
    expect(previewBodies[0]).toMatchObject({ symbol: SYM, side: "buy", kind: "limit", qty: 1 });
  });
});
