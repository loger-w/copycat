/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RightRail, type RailContext } from "@/components/rail/RightRail";
import { setCapitalWsStatus } from "@/hooks/useCapital";
import type { CapitalOrder, CapitalPosition, FuturesProductState } from "@/types";

const META = {
  name: "台積電",
  ref: 100_000,
  upper: 110_000,
  lower: 90_000,
  y_close: 100_000,
  y_vol: 10,
};
const BOOK = {
  bids: [[100_000, 30]] as [number, number][],
  asks: [[100_500, 10]] as [number, number][],
};
const LAST = { p: 100_000, t: "09:10:00.000", cum_vol: 5 };

const FUT_STATE: FuturesProductState = {
  product: "TXF",
  name: "台指期",
  p: 21_042_000,
  q: 1,
  cum_vol: 100,
  t: "10:00:00",
  date: "2026-07-28",
  bids: [[21_041_000, 5]],
  asks: [[21_043_000, 3]],
  ref: 20_940_000,
  upper: 23_034_000,
  lower: 18_846_000,
  resolved_contract: "202608",
};

const STOCK_CTX: RailContext = {
  kind: "stock",
  code: "2330",
  name: "台積電",
  book: BOOK,
  last: LAST,
  meta: META,
};
const FUT_CTX: RailContext = {
  kind: "futures",
  product: "TXF",
  state: FUT_STATE,
  contract: "TXFH6",
};
const NONE_CTX: RailContext = { kind: "none" };

function secOrder(): CapitalOrder {
  return {
    seq_no: "s1", stock_no: "2330", name: "台積電", market: "TS", buy_sell: "B",
    flag_label: "現股", book_no: "A1", status_raw: "0", status_label: "已委託",
    price: 100, avg_fill_price: null, order_qty: 2, filled_qty: 0, unit: "張",
    date: "20260728", time: "09:01:00", pre_order: false, error_msg: null,
    actionable: true, raw: "",
  };
}
function futOrder(): CapitalOrder {
  return { ...secOrder(), seq_no: "f1", stock_no: "TXFH6", name: "台指期", market: "TF", unit: "口" };
}
function position(over: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "sec", stock_no: "2330", qty: 2, name: "台積電", avg_price: 100,
    kind: "cash", pnl_base: 0, pnl_base_price: null, pnl_cost: null, ...over,
  };
}

let qc: QueryClient;
let orders: CapitalOrder[] = [];
let positions: CapitalPosition[] = [];

beforeEach(() => {
  window.localStorage.clear();
  setCapitalWsStatus("connecting");
  orders = [];
  positions = [];
  qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (url.includes("/api/capital/orders")) return new Response(JSON.stringify({ orders }));
    if (url.includes("/api/capital/positions")) return new Response(JSON.stringify({ positions }));
    if (url.includes("/api/capital/status")) {
      return new Response(JSON.stringify({ status: "ok", env: "test", order_enabled: true }));
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  // jsdom 無 scrollIntoView(spyOn 需方法存在)→ 直接指派 stub,同 PriceLadder.test
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function rail(ctx: RailContext) {
  return (
    <QueryClientProvider client={qc}>
      <RightRail ctx={ctx} />
    </QueryClientProvider>
  );
}

describe("RightRail 三 tab(SC-2 / D1)", () => {
  it("三顆 tab 文字依序為 閃電 / 委託 / 部位", () => {
    render(rail(STOCK_CTX));
    expect(screen.getAllByRole("tab").map((el) => el.textContent)).toEqual([
      "閃電",
      "委託",
      "部位",
    ]);
  });

  it("預設選中閃電;點委託後 aria-selected 轉移且閃電內容卸載", () => {
    render(rail(STOCK_CTX));
    expect(screen.getByRole("tab", { name: "閃電" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    expect(screen.getByRole("tab", { name: "委託" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("button", { name: "武裝" })).toBeNull();
  });

  it("tab 選擇寫入 localStorage copycat-rail-tab 並在重載後復原", () => {
    const { unmount } = render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    expect(window.localStorage.getItem("copycat-rail-tab")).toBe("positions");
    unmount();
    cleanup();
    render(rail(STOCK_CTX));
    expect(screen.getByRole("tab", { name: "部位" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("RightRail 內容跟隨 context(SC-3 / D2)", () => {
  it("個股 context → 個股閃電梯,標題列顯示股號 + 股名(D-12)", () => {
    render(rail(STOCK_CTX));
    expect(screen.getByText("2330")).toBeTruthy();
    expect(screen.getByText("台積電")).toBeTruthy();
    expect(screen.getByLabelText("交易別")).toBeTruthy(); // 個股專屬控制
  });

  it("期貨 context → 期貨閃電梯,標題列顯示商品 + 契約(D-12)", () => {
    render(rail(FUT_CTX));
    expect(screen.getByText("TXF")).toBeTruthy();
    expect(screen.getByText("TXFH6")).toBeTruthy();
    expect(screen.getByLabelText("當沖")).toBeTruthy(); // 期貨專屬控制
    expect(screen.queryByLabelText("交易別")).toBeNull();
  });

  it("TXO / 指數 context → 閃電 tab 顯示「此頁無可下單標的」且無武裝鈕(D6)", () => {
    render(rail(NONE_CTX));
    expect(screen.getByText("此頁無可下單標的")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "武裝" })).toBeNull();
  });

  it("個股未選檔(code=null)→ 同款空狀態,不掛載閃電梯(amendment P2-16)", () => {
    render(rail({ ...STOCK_CTX, code: null }));
    expect(screen.getByText("此頁無可下單標的")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "武裝" })).toBeNull();
  });
});

describe("RightRail 武裝不跨畫面殘留(SC-9 / W-A2 第 6 條 / D-13)", () => {
  it("個股武裝後切到期貨 context 再切回 → 鈕回到「武裝」", async () => {
    const { rerender } = render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("button", { name: "武裝" }));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    rerender(rail(FUT_CTX));
    rerender(rail(STOCK_CTX));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "武裝" }).getAttribute("aria-pressed")).toBe(
        "false",
      ),
    );
  });

  it("武裝後切右欄 tab 再切回閃電 → 鈕回到「武裝」", async () => {
    render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("button", { name: "武裝" }));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    fireEvent.click(screen.getByRole("tab", { name: "閃電" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "武裝" }).getAttribute("aria-pressed")).toBe(
        "false",
      ),
    );
  });
});

describe("RightRail 交易別 / 數量不隨 tab 重置(R2-10)", () => {
  it("選融券後切 tab 再切回,交易別仍是融券(真錢:靜默回現股會出事)", () => {
    render(rail(STOCK_CTX));
    fireEvent.change(screen.getByLabelText("交易別"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    fireEvent.click(screen.getByRole("tab", { name: "閃電" }));
    expect((screen.getByLabelText("交易別") as HTMLSelectElement).value).toBe("short");
  });

  it("張數快捷值切 tab 後保留", () => {
    render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    expect((screen.getByLabelText("張數") as HTMLInputElement).value).toBe("5");
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    fireEvent.click(screen.getByRole("tab", { name: "閃電" }));
    expect((screen.getByLabelText("張數") as HTMLInputElement).value).toBe("5");
  });
});

describe("RightRail 五檔點價接點(W-C1 / R2-5)", () => {
  it("停在委託 tab 時點五檔 → 自動切回閃電 tab 並置中該價", async () => {
    render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    expect(screen.getByRole("tab", { name: "委託" }).getAttribute("aria-selected")).toBe("true");
    act(() => {
      window.dispatchEvent(
        new CustomEvent("stock-price-click", {
          detail: { priceMilli: 100_500, side: "ask", code: "2330" },
        }),
      );
    });
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "閃電" }).getAttribute("aria-selected")).toBe("true"),
    );
    expect(Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).toHaveBeenCalled();
  });

  it("他檔的點價事件忽略(不切 tab)", () => {
    render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    act(() => {
      window.dispatchEvent(
        new CustomEvent("stock-price-click", {
          detail: { priceMilli: 100_500, side: "ask", code: "9999" },
        }),
      );
    });
    expect(screen.getByRole("tab", { name: "委託" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("RightRail 委託 / 部位(P0-2 兩段並排)", () => {
  it("個股 context 的委託只顯示證券單", async () => {
    orders = [secOrder(), futOrder()];
    render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    await waitFor(() => expect(screen.getByText("2330 台積電")).toBeTruthy());
    expect(screen.queryByText("TXFH6 台指期")).toBeNull();
  });

  it("期貨 context 的委託只顯示期貨單", async () => {
    orders = [secOrder(), futOrder()];
    render(rail(FUT_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    await waitFor(() => expect(screen.getByText("TXFH6 台指期")).toBeTruthy());
    expect(screen.queryByText("2330 台積電")).toBeNull();
  });

  it("TXO / 指數 context 的委託 = 證券 + 期貨兩段並排,各自 market 不混", async () => {
    orders = [secOrder(), futOrder()];
    render(rail(NONE_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    // 等在委託資料上,不是靜態小標(小標一 render 就在,waitFor 會提早通過)
    await waitFor(() => expect(screen.getByText("2330 台積電")).toBeTruthy());
    expect(screen.getByText("TXFH6 台指期")).toBeTruthy();
    expect(screen.getByText("證券")).toBeTruthy();
    expect(screen.getByText("期貨")).toBeTruthy();
  });
});

describe("RightRail 平倉閘用估價(W-A8 / W-A10;自 StockPage/FuturesPage 搬入)", () => {
  it("個股部位:估價 = 主檔最新成交價,確認彈窗顯示該值", async () => {
    positions = [position()];
    render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    const close = await screen.findByRole("button", { name: "平倉" });
    expect(close.hasAttribute("disabled")).toBe(false);
    fireEvent.click(close);
    expect(screen.getByText("確認平倉")).toBeTruthy();
    expect(screen.getByText("100")).toBeTruthy(); // 100_000 毫元 / 1000
  });

  it("期貨部位:多單估價貼跌停(futCloseEstimate)", async () => {
    positions = [position({ market: "fut", stock_no: "TXFH6", name: "台指期", qty: 1 })];
    render(rail(FUT_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    fireEvent.click(await screen.findByRole("button", { name: "平倉" }));
    expect(screen.getByText("確認平倉")).toBeTruthy();
    expect(screen.getByText("18846")).toBeTruthy(); // lower 18_846_000 / 1000
  });

  it("TXO / 指數 context:無行情語境 → 平倉鍵 disabled(W-A10)", async () => {
    positions = [position(), position({ market: "fut", stock_no: "TXFH6", name: "台指期" })];
    render(rail(NONE_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    const closes = await screen.findAllByRole("button", { name: "平倉" });
    expect(closes.length).toBe(2);
    for (const b of closes) expect(b.hasAttribute("disabled")).toBe(true);
  });
});
