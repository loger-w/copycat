/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockChart } from "@/components/stock/StockChart";
import type { StockAccum } from "@/lib/stock-accum";

const ACCUM = {
  code: "2330",
  seq: 1,
  last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
  vwap: 2_380_000,
  cumInner: 0,
  cumOuter: 1,
  minutes: new Map([[540, { c: 2_380_000, v: 1, i: 0, o: 1, u: 0 }]]),
  ticks: [{ t: "09:00:01.000", p: 2_380_000, q: 1, side: "outer" }],
  book: { bids: [], asks: [] },
  meta: {
    name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000,
    y_close: 2_320_000, y_vol: 100,
  },
  noData: false,
  backfilling: null,
} as unknown as StockAccum;

const BARS = [
  { t: "2026-07-27", o: 100_000, h: 110_000, l: 90_000, c: 105_000, v: 10 },
  { t: "2026-07-28", o: 105_000, h: 120_000, l: 100_000, c: 102_000, v: 20 },
];

let barsUrls: string[];

beforeEach(() => {
  window.localStorage.clear();
  barsUrls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/stock/bars")) {
        barsUrls.push(u);
        return new Response(JSON.stringify({ bars: BARS }));
      }
      return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function chart() {
  return wrap(<StockChart accum={ACCUM} code="2330" />);
}

describe("StockChart 模式切換(SC-7)", () => {
  it("四顆鈕文字依序為 江波圖 / 1分K / 5分K / 日K", () => {
    chart();
    const labels = ["江波圖", "1分K", "5分K", "日K"];
    for (const l of labels) expect(screen.getByRole("button", { name: l })).toBeTruthy();
  });

  it("預設江波圖:選中者 aria-pressed=true 且外框 border-accent", () => {
    chart();
    const btn = screen.getByRole("button", { name: "江波圖" });
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(btn.className).toContain("border-accent");
    expect(screen.getByLabelText("分時走勢圖")).toBeTruthy();
    expect(screen.queryByLabelText("K 線圖")).toBeNull();
  });

  it("切日K → 顯示 K 線圖,江波圖卸載", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByLabelText("分時走勢圖")).toBeNull();
  });

  it("切回江波圖 → 回到既有分時走勢圖(含 VWAP 切換與內外盤副圖)", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "江波圖" }));
    expect(screen.getByLabelText("分時走勢圖")).toBeTruthy();
    expect(screen.getByLabelText("內外盤能量")).toBeTruthy();
    expect(screen.getByRole("button", { name: "均價" })).toBeTruthy();
  });

  it("模式寫入 localStorage copycat-chart-mode 並在重載後復原", async () => {
    const { unmount } = chart();
    fireEvent.click(screen.getByRole("button", { name: "5分K" }));
    expect(window.localStorage.getItem("copycat-chart-mode")).toBe("m5");
    unmount();
    cleanup();
    chart();
    expect(screen.getByRole("button", { name: "5分K" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("分K 模式才有「往前」鈕,每次 +5 日並重新取數(D-10)", async () => {
    chart();
    expect(screen.queryByRole("button", { name: "往前" })).toBeNull(); // 江波圖無
    fireEvent.click(screen.getByRole("button", { name: "1分K" }));
    await waitFor(() => expect(barsUrls.some((u) => u.includes("days=5"))).toBe(true));
    expect(screen.getByText("近 5 日")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "往前" }));
    await waitFor(() => expect(barsUrls.some((u) => u.includes("days=10"))).toBe(true));
    expect(screen.getByText("近 10 日")).toBeTruthy();
  });

  it("日K 模式無「往前」鈕", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "往前" })).toBeNull();
  });

  it("往前到上限 30 日後鈕 disabled", async () => {
    chart();
    fireEvent.click(screen.getByRole("button", { name: "1分K" }));
    const back = () => screen.getByRole("button", { name: "往前" });
    for (let i = 0; i < 5; i += 1) fireEvent.click(back());
    await waitFor(() => expect(screen.getByText("近 30 日")).toBeTruthy());
    expect(back().hasAttribute("disabled")).toBe(true);
  });

  // 🔴 SC-3:失敗態與「真的沒資料」原本共用同一句「無 K 線資料」,害 2026-07-29 那次
  // 舊 build 佔 port(endpoint 404)被誤讀成「這檔沒 K 線」。失敗態要看得出是失敗。
  // 錯誤碼取值鏈:body 的 detail.error 優先 → 否則 HTTP_<status>(useStockBars.ts:35-44),
  // 故本 case 的碼是 NOT_READY 而非 HTTP_503。
  it("取數失敗顯示「K 線載入失敗」+ 錯誤碼,不崩", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ detail: { error: "NOT_READY" } }), { status: 503 })
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("K 線載入失敗")).toBeTruthy(), { timeout: 5000 });
    expect(screen.getByText("NOT_READY")).toBeTruthy();
    expect(screen.queryByText("無 K 線資料")).toBeNull();
  });

  // 🟢 SC-3 反向:真的取到空陣列 → 仍是「無 K 線資料」,不可誤報成失敗(W-13)
  it("取到空 bars 仍顯示「無 K 線資料」,不誤報失敗", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        String(url).includes("/api/stock/bars")
          ? new Response(JSON.stringify({ bars: [] }))
          : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
      ),
    );
    chart();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByText("無 K 線資料")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText("K 線載入失敗")).toBeNull();
  });
});
