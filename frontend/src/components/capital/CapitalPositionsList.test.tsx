/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapitalPositionsList } from "@/components/capital/CapitalPositionsList";
import type { CapitalPosition } from "@/types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function pos(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "sec",
    stock_no: "2330",
    qty: 2,
    name: "台積電",
    avg_price: 1000,
    kind: "cash",
    pnl_base: 1500,
    pnl_base_price: 1050,
    pnl_cost: 2000000,
    ...overrides,
  };
}

function futPos(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return pos({
    market: "fut",
    stock_no: "TXFI6",
    name: "台指期",
    qty: -2,
    avg_price: 23200,
    pnl_base: -800,
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

function renderList(
  market: "sec" | "fut",
  closePriceOf?: (p: CapitalPosition) => number | null,
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <CapitalPositionsList market={market} closePriceOf={closePriceOf} />
    </QueryClientProvider>,
  );
}

describe("CapitalPositionsList", () => {
  it("渲染繁中欄位:多紅空綠/數量單位張/均價/損益正紅負綠/null 損益顯示 —", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/positions": () =>
        json({
          positions: [
            pos(),
            pos({ stock_no: "2317", name: "鴻海", qty: -3, pnl_base: -800 }),
            pos({ stock_no: "1101", name: "台泥", qty: 1, pnl_base: null }),
          ],
        }),
    });
    renderList("sec");
    await screen.findByText(/2330/);
    for (const head of ["代號", "方向", "數量", "均價", "損益"]) {
      expect(screen.getByText(head)).toBeTruthy();
    }
    expect(screen.getAllByText("多")[0]!.className).toContain("text-bull");
    expect(screen.getByText("空").className).toContain("text-bear");
    expect(screen.getAllByText("2 張").length).toBe(1);
    expect(screen.getByText("3 張")).toBeTruthy(); // 空方顯示絕對值
    expect(screen.getAllByText("1000.00").length).toBe(3);
    expect(screen.getAllByText("+1500")[0]!.className).toContain("text-bull");
    expect(screen.getByText("-800").className).toContain("text-bear");
    expect(screen.getByText("—")).toBeTruthy(); // pnl_base null
  });

  it("market 過濾:fut 只顯示期貨部位,欄名為契約,單位口", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/positions": () => json({ positions: [pos(), futPos()] }),
    });
    renderList("fut");
    expect(await screen.findByText(/TXFI6/)).toBeTruthy();
    expect(screen.queryByText(/2330/)).toBeNull();
    expect(screen.getByText("契約")).toBeTruthy();
    expect(screen.getByText("2 口")).toBeTruthy();
  });

  it("空列表顯示無部位", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    renderList("sec");
    expect(await screen.findByText("無部位")).toBeTruthy();
  });

  it("估價 null 時平倉鍵 disabled + title 提示無行情估價", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/positions": () => json({ positions: [pos()] }),
    });
    renderList("sec", () => null);
    await screen.findByText(/2330/);
    const btn = screen.getByText("平倉").closest("button");
    expect(btn?.getAttribute("disabled")).not.toBeNull();
    expect(btn?.getAttribute("title")).toBe("無行情估價");
  });

  it("平倉 → 彈窗顯示閘用估價 → 確認 → close mutation 帶 market/key/price/qty", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/position/close": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "005" });
      },
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    renderList("fut", () => 23000);
    await screen.findByText(/TXFI6/);
    fireEvent.click(screen.getByText("平倉"));
    expect(screen.getByText("確認平倉")).toBeTruthy();
    expect(screen.getByText("閘用估價")).toBeTruthy();
    expect(screen.getByText("23000")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      market: "fut",
      key: "TXFI6",
      price: 23000,
      qty: 2,
      kind: "cash",
    });
    await waitFor(() => expect(screen.queryByText("確認平倉")).toBeNull());
  });

  it("同檔資+集保並存 → 兩列各帶種類標籤,平倉各自送出自己的 kind", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/position/close": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "006" });
      },
      "/api/capital/positions": () =>
        json({
          positions: [
            pos({ kind: "cash", qty: 1 }),
            pos({ kind: "margin", qty: 3, avg_price: 980 }),
          ],
        }),
    });
    renderList("sec", () => 985);
    await screen.findAllByText(/2330/);
    // 代號文字節點不變(RTL getNodeText 只取直接文字子節點),種類是獨立子元素
    expect(screen.getAllByText("2330 台積電").length).toBe(2);
    expect(screen.getByText("現")).toBeTruthy();
    expect(screen.getByText("資")).toBeTruthy();

    fireEvent.click(screen.getAllByText("平倉")[0]!);
    expect(screen.getByText("現股")).toBeTruthy(); // 確認彈窗種類列
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));

    fireEvent.click(screen.getAllByText("平倉")[1]!);
    expect(screen.getByText("融資")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies[0]).toEqual({ market: "sec", key: "2330", price: 985, qty: 1, kind: "cash" });
    expect(bodies[1]).toEqual({ market: "sec", key: "2330", price: 985, qty: 3, kind: "margin" });
  });

  it("同檔兩列的 React key 唯一(複合鍵),無 duplicate key warning", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/positions": () =>
        json({ positions: [pos({ kind: "cash" }), pos({ kind: "margin" })] }),
    });
    renderList("sec", () => 985);
    await screen.findAllByText(/2330/);
    const msgs = spy.mock.calls.map((c) => String(c[0]));
    expect(msgs.filter((m) => m.includes("same key"))).toEqual([]);
  });

  it("平倉 400 BROKER_REJECTED → 錯誤列繁中顯示(review A2)", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/position/close": () =>
        json({ detail: { error: "BROKER_REJECTED", err_code: "1097", err_msg: "廢單" } }, 400),
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    renderList("fut", () => 23000);
    await screen.findByText(/TXFI6/);
    fireEvent.click(screen.getByText("平倉"));
    fireEvent.click(screen.getByText("確認"));
    expect(await screen.findByText("券商拒單(1097)")).toBeTruthy();
    expect(screen.getByText("券商拒單(1097)").className).toContain("text-loss");
  });

  it("mutation pending 中鎖平倉鍵", async () => {
    mockFetch({
      "/api/capital/status": () => json(STATUS),
      "/api/capital/position/close": () => new Promise<Response>(() => undefined),
      "/api/capital/positions": () => json({ positions: [pos()] }),
    });
    renderList("sec", () => 985);
    await screen.findByText(/2330/);
    fireEvent.click(screen.getByText("平倉"));
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => {
      expect(screen.getByText("平倉").closest("button")?.getAttribute("disabled")).not.toBeNull();
    });
  });
});
