/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FuturesPage, futCloseEstimate } from "@/components/futures/FuturesPage";
import type { CapitalPosition, FuturesProductState } from "@/types";

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
  p: 23_010_000,
};

const TMF_STATE: FuturesProductState = {
  ...TXF_STATE,
  product: "TMF",
  name: "微型臺指",
  resolved_contract: null,
};

const FUT_STATE = {
  seq: 1,
  products: { TXF: TXF_STATE, MXF: MXF_STATE, TMF: TMF_STATE },
};

class FakeWS {
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {}

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

function baseRoutes(overrides: Record<string, Route> = {}): Record<string, Route> {
  return {
    "/api/futures/state": () => json(FUT_STATE),
    "/api/capital/orders": () => json({ orders: [] }),
    "/api/capital/positions": () => json({ positions: [] }),
    "/api/capital/status": () => json({ status: "ok", env: "test", order_enabled: true }),
    ...overrides,
  };
}

function futPosition(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "fut",
    stock_no: "TXFI6",
    qty: 1,
    name: "臺股期貨",
    avg_price: 22_900,
    kind: "cash",
    pnl_base: null,
    pnl_base_price: null,
    pnl_cost: null,
    ...overrides,
  };
}

let qc: QueryClient;

function page() {
  return (
    <QueryClientProvider client={qc}>
      <FuturesPage />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  Element.prototype.scrollIntoView = vi.fn();
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("futCloseEstimate 平倉閘用估價(design amendment:限價貼漲跌停)", () => {
  it("多單平倉(賣)→ 跌停價(元 = Milli/1000)", () => {
    expect(futCloseEstimate(futPosition({ qty: 2 }), "TXFI6", TXF_STATE)).toBe(20_520);
  });

  it("空單平倉(買)→ 漲停價", () => {
    expect(futCloseEstimate(futPosition({ qty: -1 }), "TXFI6", TXF_STATE)).toBe(25_080);
  });

  it("非當前商品契約 → null(無行情不估)", () => {
    expect(futCloseEstimate(futPosition({ stock_no: "MXFI6" }), "TXFI6", TXF_STATE)).toBe(null);
  });

  it("contract null(合約未解析)→ null", () => {
    expect(futCloseEstimate(futPosition(), null, TXF_STATE)).toBe(null);
  });

  it("行情缺漲跌停 → null", () => {
    expect(
      futCloseEstimate(futPosition(), "TXFI6", { ...TXF_STATE, lower: null }),
    ).toBe(null);
  });
});

describe("FuturesPage 商品切換與頂部資訊列(SC-8)", () => {
  it("預設大台:現價/漲跌/漲跌%/合約顯示", async () => {
    mockFetch(baseRoutes());
    render(page());
    await waitFor(() => expect(screen.getByText("23000")).toBeTruthy());
    expect(screen.getByText("+200")).toBeTruthy(); // 漲跌(點)
    expect(screen.getByText("+0.88%")).toBeTruthy();
    expect(screen.getByText("TXF 2026/09")).toBeTruthy();
    expect(screen.getByRole("button", { name: "大台" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("切小台:顯示 MXF 行情與合約;localStorage 記憶商品", async () => {
    mockFetch(baseRoutes());
    render(page());
    fireEvent.click(screen.getByRole("button", { name: "小台" }));
    await waitFor(() => expect(screen.getByText("MXF 2026/09")).toBeTruthy());
    expect(screen.getByText("23010")).toBeTruthy();
    expect(window.localStorage.getItem("copycat-fut-product")).toBe("MXF");
  });

  it("localStorage 既值 TMF → 初始微台;resolved null 顯示「合約解析中」", async () => {
    window.localStorage.setItem("copycat-fut-product", "TMF");
    mockFetch(baseRoutes());
    render(page());
    expect(screen.getByRole("button", { name: "微台" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    await waitFor(() => expect(screen.getByText("合約解析中")).toBeTruthy());
  });

  it("部位平倉:多單估價貼跌停,確認彈窗顯示閘用估價", async () => {
    mockFetch(
      baseRoutes({
        "/api/capital/positions": () => json({ positions: [futPosition({ qty: 2 })] }),
      }),
    );
    render(page());
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    expect(screen.getByText("20520")).toBeTruthy();
  });
});
