/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapitalOrdersList } from "@/components/capital/CapitalOrdersList";
import type { CapitalOrder } from "@/types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function order(overrides: Partial<CapitalOrder> = {}): CapitalOrder {
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
    price: 1050,
    avg_fill_price: null,
    order_qty: 3,
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

function futOrder(overrides: Partial<CapitalOrder> = {}): CapitalOrder {
  return order({
    seq_no: "002",
    stock_no: "TXFI6",
    name: "台指期",
    market: "TF",
    buy_sell: "S",
    unit: "口",
    order_qty: 2,
    ...overrides,
  });
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

const STATUS = { status: "ok", env: "test", order_enabled: true };

function renderList(market: "sec" | "fut") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CapitalOrdersList market={market} />
    </QueryClientProvider>,
  );
}

describe("CapitalOrdersList", () => {
  it("market=sec 只顯示非期貨家族委託(null market 歸 sec)", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/orders": () =>
        json({
          orders: [
            order(),
            futOrder(),
            order({ seq_no: "003", stock_no: "9999", name: "雜項", market: null }),
          ],
        }),
    });
    renderList("sec");
    expect(await screen.findByText(/2330/)).toBeTruthy();
    expect(screen.getByText(/9999/)).toBeTruthy();
    expect(screen.queryByText(/TXFI6/)).toBeNull();
  });

  it("market=fut 只顯示期貨家族(TF/TO/OF/OO)委託", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/orders": () => json({ orders: [order(), futOrder()] }),
    });
    renderList("fut");
    expect(await screen.findByText(/TXFI6/)).toBeTruthy();
    expect(screen.queryByText(/2330/)).toBeNull();
  });

  it("渲染繁中欄位:買紅賣綠/價格/數量帶單位/狀態 label", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/orders": () =>
        json({ orders: [order(), order({ seq_no: "004", buy_sell: "S", actionable: false })] }),
    });
    renderList("sec");
    await screen.findAllByText(/2330/);
    for (const head of ["代號", "買賣", "價格", "數量", "狀態"]) {
      expect(screen.getByText(head)).toBeTruthy();
    }
    expect(screen.getByText("買").className).toContain("text-bull");
    expect(screen.getByText("賣").className).toContain("text-bear");
    expect(screen.getAllByText("1050").length).toBe(2);
    expect(screen.getAllByText("0/3 張").length).toBe(2);
    expect(screen.getAllByText("已委託").length).toBe(2);
  });

  it("空列表顯示無委託", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderList("sec");
    expect(await screen.findByText("無委託")).toBeTruthy();
  });

  it("非 actionable 列不顯示操作鍵", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/orders": () => json({ orders: [order({ actionable: false })] }),
    });
    renderList("sec");
    await screen.findByText(/2330/);
    expect(screen.queryByText("刪單")).toBeNull();
    expect(screen.queryByText("改")).toBeNull();
  });

  it("刪單 → 彈窗 → 確認 → cancel mutation 帶 seq_no+market;取消不再送", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/order/cancel": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "001" });
      },
      "/api/capital/orders": () => json({ orders: [order()] }),
    });
    renderList("sec");
    await screen.findByText(/2330/);
    fireEvent.click(screen.getByText("刪單"));
    expect(screen.getByText("確認刪單")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ seq_no: "001", market: "sec" });
    await waitFor(() => expect(screen.queryByText("確認刪單")).toBeNull());
    fireEvent.click(screen.getByText("刪單"));
    fireEvent.click(screen.getByText("取消"));
    expect(screen.queryByText("確認刪單")).toBeNull();
    expect(bodies.length).toBe(1);
  });

  it("改價 inline 輸入 → 彈窗 → 確認 → correct-price mutation 帶 price(fut market)", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/order/correct-price": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "002" });
      },
      "/api/capital/orders": () => json({ orders: [futOrder()] }),
    });
    renderList("fut");
    await screen.findByText(/TXFI6/);
    fireEvent.click(screen.getByText("改"));
    const sendBtn = screen.getByLabelText("送出改價");
    expect(sendBtn.getAttribute("disabled")).not.toBeNull(); // 未輸入 → disabled
    fireEvent.change(screen.getByLabelText("改價"), { target: { value: "23100.5" } });
    expect(sendBtn.getAttribute("disabled")).toBeNull();
    fireEvent.click(sendBtn);
    expect(screen.getByText("確認改價")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ seq_no: "002", market: "fut", price: 23100.5 });
  });

  it("減量 inline 輸入 → 彈窗 → 確認 → decrease mutation 帶 qty", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/order/decrease": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "001" });
      },
      "/api/capital/orders": () => json({ orders: [order()] }),
    });
    renderList("sec");
    await screen.findByText(/2330/);
    fireEvent.click(screen.getByText("改"));
    const sendBtn = screen.getByLabelText("送出減量");
    fireEvent.change(screen.getByLabelText("減量"), { target: { value: "1.5" } });
    expect(sendBtn.getAttribute("disabled")).not.toBeNull(); // 非整數 → disabled
    fireEvent.change(screen.getByLabelText("減量"), { target: { value: "2" } });
    fireEvent.click(sendBtn);
    expect(screen.getByText("確認減量")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ seq_no: "001", market: "sec", qty: 2 });
  });

  it("mutation pending 中鎖操作鍵", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/order/cancel": () => new Promise<Response>(() => undefined),
      "/api/capital/orders": () => json({ orders: [order()] }),
    });
    renderList("sec");
    await screen.findByText(/2330/);
    fireEvent.click(screen.getByText("刪單"));
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => {
      expect(screen.getByText("刪單").closest("button")?.getAttribute("disabled")).not.toBeNull();
    });
    expect(screen.getByText("改").closest("button")?.getAttribute("disabled")).not.toBeNull();
  });

  it("正式環境(env=prod)彈窗標題列紅底", async () => {
    mockFetch({
      "/api/capital/status": () => json({ ...STATUS, env: "prod" }),
      "/api/capital/orders": () => json({ orders: [order()] }),
    });
    renderList("sec");
    await screen.findByText(/2330/);
    fireEvent.click(screen.getByText("刪單"));
    await waitFor(() => {
      expect(screen.getByText("確認刪單").closest("div")?.className).toContain("bg-loss");
    });
  });
});
