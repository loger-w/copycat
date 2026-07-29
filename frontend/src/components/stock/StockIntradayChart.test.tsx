/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { fromSnapshot } from "@/lib/stock-accum";

const OVERLAY = {
  cdp: { cdp: 2_320_000, ah: 2_400_000, nh: 2_360_000, nl: 2_280_000, al: 2_240_000 },
  ma5: 2_330_000,
  ma20: 2_310_000,
  date: "2026-07-25",
};

let overlayResponse: object = OVERLAY;

beforeEach(() => {
  window.localStorage.removeItem("copycat-chart-toggles");
  overlayResponse = OVERLAY;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(overlayResponse))),
  );
  // jsdom getBoundingClientRect 恆 0:hover 座標換算需要真實寬高(frontend-testing 慣例)
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0, top: 0, right: 800, bottom: 260, width: 800, height: 260, x: 0, y: 0,
    toJSON: () => ({}),
  } as DOMRect);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
  vwap: 2_380_000,
  cum_inner: 2,
  cum_outer: 10,
  minutes: {
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0 },
  },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_close: 2_320_000, y_vol: 100 },
});

describe("StockIntradayChart", () => {
  it("渲染價線/VWAP/內外盤副圖", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const polylines = container.querySelectorAll("polyline");
    expect(polylines.length).toBeGreaterThanOrEqual(2); // 價線 + VWAP
    expect(container.querySelectorAll("svg").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/累積外盤/)).toBeTruthy();
  });

  it("無分鐘資料顯示等待提示", () => {
    const empty = fromSnapshot({
      code: "2330", seq: 0, last: null, vwap: null, cum_inner: 0, cum_outer: 0,
      minutes: {}, ticks: [], book: null, meta: null,
    });
    wrap(<StockIntradayChart accum={empty} />);
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });

  it("toggle 列:均價/CDP/MA 三鈕,均價預設開(SC-4)", () => {
    wrap(<StockIntradayChart accum={ACCUM} />);
    const vwap = screen.getByRole("button", { name: "均價" });
    expect(vwap.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "CDP" }).getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByRole("button", { name: "MA" })).toBeTruthy();
  });

  it("均價 toggle 關 → VWAP 線消失", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const before = container.querySelectorAll("polyline").length;
    fireEvent.click(screen.getByRole("button", { name: "均價" }));
    expect(container.querySelectorAll("polyline").length).toBe(before - 1);
  });

  it("CDP toggle 開 → overlay 線與 label 出現(SC-4)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "CDP" }));
    await waitFor(() => expect(screen.getByText("CDP", { selector: "text" })).toBeTruthy());
    expect(screen.getByText("AH", { selector: "text" })).toBeTruthy();
    expect(container.querySelectorAll("line").length).toBeGreaterThan(5);
  });

  it("overlay 全 null → CDP/MA 反灰 disabled + title 無日線資料(SC-4/R8)", async () => {
    overlayResponse = { cdp: null, ma5: null, ma20: null, date: null };
    wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "CDP" }));
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: "CDP" });
      expect(btn.hasAttribute("disabled")).toBe(true);
    });
    const btn = screen.getByRole("button", { name: "CDP" });
    expect(btn.getAttribute("title")).toBe("無日線資料");
    expect(btn.getAttribute("aria-pressed")).toBe("false"); // 自動置 off,不卡開著關不掉
  });

  it("Y 軸刻度:左緣價位、右緣 %(SC-2)", () => {
    wrap(<StockIntradayChart accum={ACCUM} />);
    expect(screen.getByText("2090", { selector: "text" })).toBeTruthy();
    expect(screen.getByText("2550", { selector: "text" })).toBeTruthy();
    expect(screen.getByText("+9.9%", { selector: "text" })).toBeTruthy();
    expect(screen.getByText("0%", { selector: "text" })).toBeTruthy();
  });

  it("量 bar 依分鐘漲跌著色(SC-3)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    // 541 首分鐘 flat、542 收高於 541 → up(fill-bull)
    expect(container.querySelector('rect[class*="fill-bull"]')).toBeTruthy();
    expect(container.querySelector('rect[class*="fill-ink-dim"]')).toBeTruthy();
  });

  it("hover 顯示十字與 tooltip、移出消失(SC-1)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const svg = container.querySelector("svg")!;
    // width 800、x 域 540..810 分鐘 → 541 分在 x = 1/270*800 ≈ 2.96px
    fireEvent.mouseMove(svg, { clientX: 3, clientY: 100 });
    expect(screen.getByText(/09:01/, { selector: "text" })).toBeTruthy();
    expect(screen.getByText(/2380/, { selector: "text" })).toBeTruthy();
    fireEvent.mouseLeave(svg);
    expect(screen.queryByText(/09:01/, { selector: "text" })).toBeNull();
  });

  it("hover 無資料分鐘不顯示 tooltip(edge 7)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 400, clientY: 100 }); // ~11:15 無資料
    expect(screen.queryByText(/11:1/)).toBeNull();
  });

  // 🔴 SC-4:在圖上拖曳是「拉一段來看」的自然手勢,不該把時間軸 / 價位刻度 / 內外盤文字反白
  it("圖表容器禁止選字(拖曳不反白;SC-4)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelector("figure")?.className).toContain("select-none");
  });
});
