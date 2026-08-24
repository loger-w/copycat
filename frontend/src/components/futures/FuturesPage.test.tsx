/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FuturesPage, futCloseEstimate } from "@/components/futures/FuturesPage";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { wrap } from "@/test-utils";
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
    code: null,
    ...overrides,
  };
}

/** 指數流的 twse 腿(SC-5 期現價差來源)。 */
function series(overrides: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 22_950_000,
    ref: 22_900_000,
    high: null,
    low: null,
    stale: false,
    minutes: {},
    ...overrides,
  };
}

/** product 已上提到 App(D-3)→ 這裡用受控 wrapper 模擬父層持有 state。 */
function Harness({
  initial = "TXF",
  twse = null,
}: {
  initial?: string;
  twse?: IndexSeries | null;
}) {
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
      twse={twse}
    />
  );
}

// test-infra:FuturesPage 自 SC-1 起掛 FuturesChart(TQ hooks)→ render 必須有
// QueryClientProvider 與這四條路由的 fetch mock,否則與本檔斷言無關的 query 會炸開。
let barsUrls: string[] = [];

beforeEach(() => {
  window.localStorage.clear();
  barsUrls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/market/bars")) {
        barsUrls.push(u);
        return new Response(
          JSON.stringify({
            bars: [],
            meta: {
              source: "tc4_1k",
              coverage_from: null,
              coverage_to: null,
              partial_last: false,
              volume: true,
              refusal: null,
              synth_since: null,
            },
          }),
        );
      }
      if (u.includes("/api/futures/oi-levels")) {
        return new Response(JSON.stringify({ date: null, contract: null, strikes: [] }));
      }
      if (u.includes("/api/capital/positions")) {
        return new Response(JSON.stringify({ positions: [] }));
      }
      // R2 起 FuturesChart 掛 useCapitalOrders(近全軸成交點 N043/N070)
      if (u.includes("/api/capital/orders")) {
        return new Response(JSON.stringify({ orders: [] }));
      }
      throw new Error(`unexpected fetch: ${u}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
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
    wrap(<Harness />);
    // 「23000」同時出現在五檔中央 → 收斂 scope 到頂部資訊列(header)
    const header = within(screen.getByRole("banner"));
    expect(header.getByText("23000")).toBeTruthy();
    expect(header.getByText("+200")).toBeTruthy(); // 漲跌(點)
    expect(header.getByText("+0.88%")).toBeTruthy();
    expect(header.getByText("TXF 2026/09")).toBeTruthy();
    expect((screen.getByRole("radio", { name: "大台" }) as HTMLInputElement).checked).toBe(true);
  });

  // a11y 批 SC-1':商品列是單選 —— 原本三顆 `aria-pressed` button 讓 AT 聽成三個互不
  // 相干的開關、鍵盤要按三次 Tab 才穿得過。改 radiogroup 後恰一顆 checked。
  it("商品列是 radiogroup:三顆 radio、恰一顆 checked、同一個 name", () => {
    wrap(<Harness />);
    const group = within(screen.getByRole("radiogroup", { name: "商品切換" }));
    const radios = group.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.parentElement!.textContent)).toEqual(["大台", "小台", "微台"]);
    expect(radios.filter((r) => r.checked).length).toBe(1);
    expect(new Set(radios.map((r) => r.name)).size).toBe(1);
  });

  it("切小台:回呼上拋並顯示 MXF 行情與合約", () => {
    wrap(<Harness />);
    fireEvent.click(screen.getByRole("radio", { name: "小台" }));
    const header = within(screen.getByRole("banner"));
    expect(header.getByText("MXF 2026/09")).toBeTruthy();
    expect(header.getByText("23010")).toBeTruthy();
  });

  it("初始微台;resolved null 顯示「合約解析中」", () => {
    wrap(<Harness initial="TMF" />);
    expect((screen.getByRole("radio", { name: "微台" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("合約解析中")).toBeTruthy();
  });
});

// 🔴-5:閃電梯 / 委託 / 部位已移到常駐右欄。
// 「部位平倉:多單估價貼跌停,確認彈窗顯示閘用估價」已逐條搬入 RightRail.test.tsx。
describe("FuturesPage 中間主區(SC-5)", () => {
  it("渲染水平五檔(DepthBar)", () => {
    wrap(<Harness />);
    // DepthBar 的格子一律是 div(五檔點價置中是個股 OrderBook 專屬)→ 以 aria-label 指認
    expect(screen.getByLabelText("買1 22999")).toBeTruthy();
    expect(screen.getByLabelText("賣1 23001")).toBeTruthy();
    expect(screen.getByText(/委買 45/)).toBeTruthy();
    expect(screen.getByText(/委賣 88/)).toBeTruthy();
  });

  it("不再渲染閃電梯 / 委託 / 部位(已移到右欄)", () => {
    wrap(<Harness />);
    expect(screen.queryByRole("button", { name: "武裝" })).toBeNull();
    expect(screen.queryByText("委託")).toBeNull();
    expect(screen.queryByText("部位")).toBeNull();
  });
});

describe("FuturesPage 期現價差(SC-5)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  function spreadText(): string {
    return within(screen.getByRole("banner")).getByTestId("fut-spread").textContent ?? "";
  }

  it("盤中 + twse 有價且不 stale → 正價差(text-bull)", () => {
    vi.setSystemTime(new Date(2026, 7, 5, 10, 0)); // 週三 10:00
    wrap(<Harness twse={series({ p: 22_950_000 })} />);
    const el = within(screen.getByRole("banner")).getByTestId("fut-spread");
    expect(el.textContent).toBe("價差 +50");
    expect(el.getAttribute("class")).toContain("text-bull");
  });

  it("期指低於現貨 → 負價差(text-bear)", () => {
    vi.setSystemTime(new Date(2026, 7, 5, 10, 0));
    wrap(<Harness twse={series({ p: 23_050_000 })} />);
    const el = within(screen.getByRole("banner")).getByTestId("fut-spread");
    expect(el.textContent).toBe("價差 -50");
    expect(el.getAttribute("class")).toContain("text-bear");
  });

  it("twse.stale → 價差 —", () => {
    vi.setSystemTime(new Date(2026, 7, 5, 10, 0));
    wrap(<Harness twse={series({ stale: true })} />);
    expect(spreadText()).toBe("價差 —");
  });

  it("夜間假價差:{p:23000, stale:false} 但現貨已收盤 → 價差 —", () => {
    // index_engine 的 watchdog 只在 09:00–13:25 維護 stale,收盤後 p 保留收盤值且
    // stale 恆 false —— 單靠 stale 會整夜顯示一個看起來很真的假價差(design §6.1)
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0)); // 週三 22:00 夜盤
    wrap(<Harness twse={series({ p: 23_000_000, stale: false })} />);
    expect(spreadText()).toBe("價差 —");
  });

  it("twse null(指數流未就緒)→ 價差 —", () => {
    vi.setSystemTime(new Date(2026, 7, 5, 10, 0));
    wrap(<Harness twse={null} />);
    expect(spreadText()).toBe("價差 —");
  });
});

describe("FuturesPage 結算倒數 badge(SC-6)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it("2026-08-05 對 202609 契約 → 結算 T-N", () => {
    vi.setSystemTime(new Date(2026, 7, 5, 10, 0));
    // 2026-09 第三週三 = 2026-09-16;交易日(週一〜五)倒數
    wrap(<Harness />);
    const badge = screen.getByTestId("fut-settlement");
    expect(badge.textContent).toBe("結算 T-30");
  });

  it("結算當日 → amber 底「今日結算」", () => {
    vi.setSystemTime(new Date(2026, 8, 16, 10, 0)); // 2026-09-16 = 202609 第三週三
    wrap(<Harness />);
    const badge = screen.getByTestId("fut-settlement");
    expect(badge.textContent).toBe("今日結算");
    expect(badge.getAttribute("class")).toContain("amber");
  });

  it("resolvedYm null → 不顯示 badge", () => {
    vi.setSystemTime(new Date(2026, 7, 5, 10, 0));
    wrap(<Harness initial="TMF" />);
    expect(screen.queryByTestId("fut-settlement")).toBeNull();
  });
});

describe("FuturesPage 掛載 FuturesChart(SC-1/SC-4)", () => {
  it("圖表跟隨商品切換 —— 換小台後改抓 MXF 的 bars", async () => {
    wrap(<Harness />);
    await waitFor(() => expect(barsUrls.some((u) => u.includes("/bars/TXF"))).toBe(true));
    fireEvent.click(screen.getByRole("radio", { name: "小台" }));
    await waitFor(() => expect(barsUrls.some((u) => u.includes("/bars/MXF"))).toBe(true));
  });

  it("模式列與五檔同時在頁上(圖表掛在 DepthBar 下方)", () => {
    wrap(<Harness />);
    expect(screen.getByRole("radio", { name: "分時" })).toBeTruthy();
    expect(screen.getByLabelText("買1 22999")).toBeTruthy();
  });
});
