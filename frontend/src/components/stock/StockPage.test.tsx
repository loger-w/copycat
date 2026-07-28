/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockPage } from "@/components/stock/StockPage";

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

  emit(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
}

beforeEach(() => {
  FakeWS.instances = [];
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/stock/watchlist")) {
        return new Response(JSON.stringify({ groups: [{ name: "自選", codes: ["2330"] }] }));
      }
      if (String(url).includes("/api/capital/status")) {
        return new Response(JSON.stringify({ status: "ok", env: "test", order_enabled: true }));
      }
      if (String(url).includes("/api/capital/orders")) {
        return new Response(JSON.stringify({ orders: [] }));
      }
      if (String(url).includes("/api/capital/positions")) {
        return new Response(JSON.stringify({ positions: [] }));
      }
      return new Response(
        JSON.stringify({
          code: "2330", seq: 1,
          last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
          vwap: 2_380_000, cum_inner: 0, cum_outer: 1,
          minutes: { "540": { c: 2_380_000, v: 1, i: 0, o: 1, u: 0 } },
          ticks: [{ t: "09:00:01.000", p: 2_380_000, q: 1, side: "outer" }],
          book: { bids: [[2_375_000, 5]], asks: [[2_380_000, 3]] },
          meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_close: 2_320_000, y_vol: 100 },
          no_data: false, tc4: "up", backfilling: null, stkfut_prod: "CDF",
        }),
      );
    }),
  );
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("StockPage", () => {
  it("未選檔時顯示提示;選檔後渲染主視圖 header", async () => {
    wrap(<StockPage />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy());
    expect(screen.getByText(/從自選清單選擇/)).toBeTruthy();
  });

  it("TC4 斷線顯示告警列", async () => {
    wrap(<StockPage />);
    await waitFor(() => expect(FakeWS.instances.length).toBe(1));
    const ws = FakeWS.instances[0]!;
    ws.emit({ type: "status", tc4: "down", backfilling: null });
    await waitFor(() => expect(screen.getByText(/達錢 4 連線中斷/)).toBeTruthy());
  });

  it("選檔後下方渲染群益委託/部位列表(market=sec;SC-5/6)", async () => {
    window.localStorage.setItem("stock-main-code", "2330");
    wrap(<StockPage />);
    expect(await screen.findByText("委託")).toBeTruthy();
    expect(screen.getByText("部位")).toBeTruthy();
    expect(await screen.findByText("無委託")).toBeTruthy();
    expect(await screen.findByText("無部位")).toBeTruthy();
  });
});
