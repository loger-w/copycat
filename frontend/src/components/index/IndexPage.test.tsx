/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IndexPage } from "@/components/index/IndexPage";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import type { BreadthState } from "@/types";
import {
  MARKET2_FUT_STORE,
  MARKET2_KEY_STORE,
  MARKET2_MODE_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";

function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 42_039_920,
    ref: 43_634_190,
    high: 43_221_930,
    low: 41_815_780,
    stale: false,
    minutes: { "0901": 43_000_000, "0930": 42_039_920 },
    ...over,
  };
}

const OTC = series({
  p: 359_800,
  ref: 378_090,
  high: 373_420,
  low: 358_430,
  minutes: { "1017": 359_800 },
});
const TXF: TxfQuote = { p: 42_142_000, time: "10:16:10" };
const FUTURES = { TXF: { p: 42_142_000, ref: 42_000_000 } };

function bars(n = 3) {
  return Array.from({ length: n }, (_, i) => ({
    t: `2026-07-2${7 + i}`,
    o: 100,
    h: 110,
    l: 90,
    c: 105,
    v: 10,
  }));
}

let lastUrls: string[] = [];

function stubFetch(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      lastUrls.push(String(url));
      return new Response(JSON.stringify(body));
    }),
  );
}

const DK_BODY = {
  key: "TWSE",
  tf: "D",
  bars: bars(),
  meta: {
    source: "tc4_dk",
    coverage_from: "2026-07-27",
    coverage_to: "2026-07-29",
    partial_last: false,
    volume: true,
    refusal: null,
    synth_since: null,
  },
};

beforeEach(() => {
  window.localStorage.clear();
  lastUrls = [];
  stubFetch(DK_BODY);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const BREADTH: BreadthState = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  counts: {
    twse: { limit_up: 3, up: 512, flat: 88, down: 401, limit_down: 2 },
    tpex: { limit_up: 7, up: 388, flat: 61, down: 290, limit_down: 1 },
  },
  series: [{ t: "0930", twse: [3, 512, 88, 401, 2], tpex: [7, 388, 61, 290, 1] }],
};

function renderPage(txf: TxfQuote | null = TXF, breadth: BreadthState | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IndexPage twse={series()} otc={OTC} txf={txf} futures={FUTURES} breadth={breadth} />
    </QueryClientProvider>,
  );
}

/** 兩個 pane 的按鈕文字**完全相同**(加權 / 櫃買 / 日K …)——本檔一律先收斂到 pane
 *  再查,裸 `screen.getByRole` 必撞 ambiguous。 */
function pane(id: "left" | "right") {
  return within(screen.getByTestId(`market-pane-${id}`));
}

describe("IndexPage 雙 pane 容器(SC-2)", () => {
  it("(a) 兩個 pane 同屏:左加權、右櫃買", () => {
    renderPage();
    expect(pane("left").getByText("加權指數")).toBeTruthy();
    expect(pane("right").getByText("櫃買指數")).toBeTruthy();
    expect(pane("left").queryByText("櫃買指數")).toBeNull();
    expect(pane("right").queryByText("加權指數")).toBeNull();
  });

  it("(b) 兩 pane 週期彼此獨立:左切日K,右仍停在分時", () => {
    renderPage();
    fireEvent.click(pane("left").getByRole("button", { name: "日K" }));
    expect(pane("left").getByRole("button", { name: "日K" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(pane("right").getByRole("button", { name: "分時" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(pane("right").getByRole("button", { name: "日K" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
  });

  it("(b2) 兩 pane 標的彼此獨立:右切加權,左仍是加權且右不影響左標題", () => {
    renderPage();
    fireEvent.click(pane("right").getByRole("button", { name: "加權" }));
    expect(pane("right").getByText("加權指數")).toBeTruthy();
    expect(pane("left").getByText("加權指數")).toBeTruthy();
    expect(pane("left").getByRole("button", { name: "加權" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("(d) 右 pane 寫 market2 三支 key,左 pane 的舊 key 不動", async () => {
    renderPage();
    fireEvent.click(pane("right").getByRole("button", { name: "加權" }));
    fireEvent.click(pane("right").getByRole("button", { name: "日K" }));
    await waitFor(() => expect(window.localStorage.getItem(MARKET2_MODE_STORE)).toBe("day"));
    expect(window.localStorage.getItem(MARKET2_KEY_STORE)).toBe("TWSE");
    expect(window.localStorage.getItem(MARKET_KEY_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBeNull();
  });

  it("(d2) 左 pane 寫舊 key,market2 三支不動", async () => {
    renderPage();
    fireEvent.click(pane("left").getByRole("button", { name: "台指期" }));
    fireEvent.click(pane("left").getByRole("button", { name: "小台" }));
    await waitFor(() => expect(window.localStorage.getItem(MARKET_FUT_STORE)).toBe("MXF"));
    expect(window.localStorage.getItem(MARKET_KEY_STORE)).toBe("MXF");
    expect(window.localStorage.getItem(MARKET_MODE_STORE)).toBe("m1");
    expect(window.localStorage.getItem(MARKET2_KEY_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET2_MODE_STORE)).toBeNull();
    expect(window.localStorage.getItem(MARKET2_FUT_STORE)).toBeNull();
  });

  it("(d3) 重疊鈕只在左 pane(右 pane 開了會畫出第二張同樣的加權 vs 櫃買)", () => {
    renderPage();
    expect(pane("left").getByRole("button", { name: "重疊" })).toBeTruthy();
    expect(pane("right").queryByRole("button", { name: "重疊" })).toBeNull();
  });
});

describe("IndexPage 基差列(SC-3)", () => {
  it("(c) 基差列在雙 pane 之外只有一份,含台指期價 / 價差 / 更新時刻", () => {
    renderPage();
    const rows = screen.getAllByTestId("basis-row");
    expect(rows.length).toBe(1);
    const row = rows[0]!;
    expect(row.textContent).toContain("42142");
    expect(row.textContent).toContain("+102.08");
    expect(row.textContent).toContain("10:16");
    // 不屬於任一 pane
    expect(pane("left").queryByTestId("basis-row")).toBeNull();
    expect(pane("right").queryByTestId("basis-row")).toBeNull();
  });

  it("(c2) 基差列位於雙 pane 之上", () => {
    renderPage();
    const row = screen.getByTestId("basis-row");
    const left = screen.getByTestId("market-pane-left");
    expect(row.compareDocumentPosition(left) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("(c3) 正價差用 text-bull,負價差用 text-bear", () => {
    renderPage();
    const up = screen.getByText(/價差 \+102\.08/);
    expect(up.className).toContain("text-bull");
    cleanup();
    renderPage({ p: 41_000_000, time: "10:16:10" });
    const down = screen.getByText(/價差 -1039\.92/);
    expect(down.className).toContain("text-bear");
  });

  it("(c4) txf null → 價差顯示「-」", () => {
    renderPage(null);
    expect(screen.getByText(/價差 -/)).toBeTruthy();
  });
});

describe("IndexPage 相關係數區塊(SC-4)", () => {
  it("(e) 尾端有相關係數收合鈕,預設收合", () => {
    renderPage();
    const toggle = screen.getByRole("button", { name: /相關係數/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
  });

  it("(e2) 相關係數區塊位於基差列之後", () => {
    renderPage();
    const row = screen.getByTestId("basis-row");
    const toggle = screen.getByRole("button", { name: /相關係數/ });
    expect(row.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("IndexPage 家數帶 + 騰落線(R2 SC-4)", () => {
  it("(f) 中段出現家數帶與騰落線,數字取自 breadth props", () => {
    renderPage(TXF, BREADTH);
    expect(screen.getByTestId("breadth-band")).toBeTruthy();
    expect(screen.getByTestId("adl-chart")).toBeTruthy();
    expect(screen.getByTestId("breadth-cell-twse-limit_up").textContent).toContain("3");
    // net = (3+512+7+388) − (401+2+290+1) = 910 − 694 = +216
    expect(screen.getByTestId("adl-last").textContent).toContain("+216");
  });

  it("(f2) 家數帶位於雙 pane 之後、相關係數區塊之前", () => {
    renderPage(TXF, BREADTH);
    const left = screen.getByTestId("market-pane-left");
    const band = screen.getByTestId("breadth-band");
    const toggle = screen.getByRole("button", { name: /相關係數/ });
    expect(left.compareDocumentPosition(band) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(band.compareDocumentPosition(toggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("(f3) breadth 為 null 時家數帶照樣在位(載入中),不炸圖", () => {
    renderPage(TXF, null);
    expect(screen.getByTestId("breadth-band").textContent).toContain("載入中");
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
  });
});

// 🟢 台股綜合 R3(SC-3 / SC-5):漲跌停列表落在家數 section 與相關係數之間。
// 本檔只驗**落點**(元件自身行為在 LimitListSection.test.tsx,跳轉全鏈在 App.test.tsx)——
// 列表預設收合 = body 不 mount、零 fetch,所以這裡不需要 breadth rows 的 stub。
describe("IndexPage 漲跌停列表落點(R3 SC-3)", () => {
  it("(g) 列表區塊在頁面內,預設收合", () => {
    renderPage(TXF, BREADTH);
    expect(screen.getByTestId("limit-list")).toBeTruthy();
    expect(screen.getByRole("button", { name: /漲跌停/ }).getAttribute("aria-expanded")).toBe(
      "false",
    );
  });

  it("(g2) 列表位於騰落線之後、相關係數區塊之前", () => {
    renderPage(TXF, BREADTH);
    const adl = screen.getByTestId("adl-chart");
    const list = screen.getByTestId("limit-list");
    const corr = screen.getByRole("button", { name: /相關係數/ });
    expect(adl.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(list.compareDocumentPosition(corr) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
