/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

const STATES: Record<string, FuturesProductState> = {
  TXF: TXF_STATE,
  MXF: MXF_STATE,
  TMF: TMF_STATE,
};

const PRODUCTS = [
  ["TXF", "大台"],
  ["MXF", "小台"],
  ["TMF", "微台"],
] as const;

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

/** product 已上提到 App(D-3)→ 這裡用受控 wrapper 模擬父層持有 state。 */
function Harness({ initial = "TXF" }: { initial?: string }) {
  const [product, setProduct] = useState(initial);
  const state = STATES[product] ?? null;
  return (
    <FuturesPage
      products={PRODUCTS}
      product={product}
      onProduct={setProduct}
      state={state}
      resolvedYm={state?.resolved_contract ?? null}
      wsStatus="open"
    />
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
    expect(futCloseEstimate(futPosition(), "TXFI6", { ...TXF_STATE, lower: null })).toBe(null);
  });
});

describe("FuturesPage 商品切換與頂部資訊列(SC-8)", () => {
  it("預設大台:現價/漲跌/漲跌%/合約顯示", () => {
    render(<Harness />);
    // 「23000」同時出現在五檔中央 → 收斂 scope 到頂部資訊列(header)
    const header = within(screen.getByRole("banner"));
    expect(header.getByText("23000")).toBeTruthy();
    expect(header.getByText("+200")).toBeTruthy(); // 漲跌(點)
    expect(header.getByText("+0.88%")).toBeTruthy();
    expect(header.getByText("TXF 2026/09")).toBeTruthy();
    expect(screen.getByRole("button", { name: "大台" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("切小台:回呼上拋並顯示 MXF 行情與合約", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "小台" }));
    const header = within(screen.getByRole("banner"));
    expect(header.getByText("MXF 2026/09")).toBeTruthy();
    expect(header.getByText("23010")).toBeTruthy();
  });

  it("初始微台;resolved null 顯示「合約解析中」", () => {
    render(<Harness initial="TMF" />);
    expect(screen.getByRole("button", { name: "微台" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("合約解析中")).toBeTruthy();
  });
});

// 🔴-5:閃電梯 / 委託 / 部位已移到常駐右欄。
// 「部位平倉:多單估價貼跌停,確認彈窗顯示閘用估價」已逐條搬入 RightRail.test.tsx。
describe("FuturesPage 中間主區(SC-5)", () => {
  it("渲染水平五檔(DepthBar)", () => {
    render(<Harness />);
    // DepthBar 的格子一律是 div(五檔點價置中是個股 OrderBook 專屬)→ 以 aria-label 指認
    expect(screen.getByLabelText("買1 22999")).toBeTruthy();
    expect(screen.getByLabelText("賣1 23001")).toBeTruthy();
    expect(screen.getByText(/委買 45/)).toBeTruthy();
    expect(screen.getByText(/委賣 88/)).toBeTruthy();
  });

  it("不再渲染閃電梯 / 委託 / 部位(已移到右欄)", () => {
    render(<Harness />);
    expect(screen.queryByRole("button", { name: "武裝" })).toBeNull();
    expect(screen.queryByText("委託")).toBeNull();
    expect(screen.queryByText("部位")).toBeNull();
  });
});
