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
  // 個股期合約選擇(stkfut-contracts SC-4)的獨立欄;現貨態 = null,本檔行為不變
  contract: null,
  name: "台積電",
  book: BOOK,
  last: LAST,
  meta: META,
};
/** 個股期態:`code` 仍是股號(點價 gate 依賴),合約走獨立欄(stkfut-contracts R4) */
const STKFUT_CTX: RailContext = {
  ...STOCK_CTX,
  contract: { prod: "CDF", ym: "202609", mini: false, unit: 2000 },
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
/** 送單路由行為:ok = 立即成功 / fail = 400 券商拒單(err_code 逐發遞增,好逐次等待)/
 *  pending = 永不自行結束,由測試持有 reject 決定何時回應(R3 卸載後才回應的情境)。 */
let orderMode: "ok" | "fail" | "pending" = "ok";
let orderCalls = 0;
let pendingOrders: ((reason: unknown) => void)[] = [];

beforeEach(() => {
  window.localStorage.clear();
  setCapitalWsStatus("connecting");
  orders = [];
  positions = [];
  orderMode = "ok";
  orderCalls = 0;
  pendingOrders = [];
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (url.includes("/api/capital/orders")) return new Response(JSON.stringify({ orders }));
    if (url.includes("/api/capital/positions")) return new Response(JSON.stringify({ positions }));
    if (url.includes("/api/capital/status")) {
      return new Response(JSON.stringify({ status: "ok", env: "test", order_enabled: true }));
    }
    if (url.includes("/api/capital/order/")) {
      orderCalls += 1;
      if (orderMode === "pending") {
        return new Promise<Response>((_resolve, reject) => pendingOrders.push(reject));
      }
      if (orderMode === "fail") {
        return new Response(
          JSON.stringify({ detail: { error: "BROKER_REJECTED", err_code: `109${orderCalls}` } }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ ok: true, code: 0, message: "ok", seq_no: "x" }));
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

// 🔴 round3 SC-5:右欄與中間主區之間要有可見分隔線
describe("RightRail 版面(round3 SC-5)", () => {
  it("aside 左緣有 border 與中間區隔", () => {
    render(rail(STOCK_CTX));
    const aside = screen.getByRole("complementary", { name: "交易面板" });
    expect(aside.className).toContain("border-l");
    expect(aside.className).toContain("border-line");
  });
});

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

  // LP-5:閃電 tab 是唯一渲染 PriceLadder 的地方,而部位條插在卡片最底 —— 這則守的是
  // 「部位資料到達不會擠掉價格列」的整合面(PriceLadder.test.tsx 只驗元件單體)。
  it("閃電 tab + 本檔部位 → 部位條出現且價格列仍在(LP-5)", async () => {
    positions = [position()];
    render(rail(STOCK_CTX));
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(bar.textContent).toContain("現股 2張 @100");
    expect(screen.getByLabelText("買 100")).toBeTruthy();
    expect(screen.getByLabelText("賣 100.5")).toBeTruthy();
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

  it("切離閃電 tab 會清掉置中請求(重掛載不重放過期價位;review P2-2)", async () => {
    render(rail(STOCK_CTX));
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
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    (Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>).mockClear();
    fireEvent.click(screen.getByRole("tab", { name: "閃電" }));
    // 重掛載後跟隨回到開啟(置中於現價),不是捲回剛才點的價位
    expect(
      screen.getByRole("button", { name: "跟隨置中" }).getAttribute("aria-pressed"),
    ).toBe("true");
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

// R4:選中個股期合約後,右欄三個 tab 必須整組換到期貨市場 —— 委託 / 部位若還停在
// `sec`,使用者看到的是現股庫存與現股委託,而閃電梯送出去的是期貨單。
describe("RightRail 個股期態 market 貫穿(stkfut-contracts R4)", () => {
  it("閃電 tab → 個股期閃電梯(口數 + 當沖;無交易別)", () => {
    render(rail(STKFUT_CTX));
    expect(screen.getByLabelText("口數")).toBeTruthy();
    expect(screen.getByLabelText("當沖")).toBeTruthy();
    expect(screen.queryByLabelText("交易別")).toBeNull();
    expect(screen.queryByLabelText("張數")).toBeNull();
    expect(screen.getByText("2330")).toBeTruthy(); // 標的仍以股號指認
    expect(screen.getByText("台積電 CDF 2026/09")).toBeTruthy();
  });

  it("委託 tab → CapitalOrdersList 收到 market=fut(證券單不混入)", async () => {
    orders = [secOrder(), futOrder()];
    render(rail(STKFUT_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    await waitFor(() => expect(screen.getByText("TXFH6 台指期")).toBeTruthy());
    expect(screen.queryByText("2330 台積電")).toBeNull();
  });

  it("部位 tab → market=fut,估價走 futCloseEstimate(合約 + meta 漲跌停)", async () => {
    positions = [position({ market: "fut", stock_no: "CDFI6", name: "台積電期貨", qty: 2 })];
    render(rail(STKFUT_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    const close = await screen.findByRole("button", { name: "平倉" });
    expect(close.hasAttribute("disabled")).toBe(false);
    fireEvent.click(close);
    expect(screen.getByText("確認平倉")).toBeTruthy();
    // 多單平倉貼跌停(meta.lower 90_000 毫元 / 1000);現股態會是最新成交價 100
    expect(screen.getByText("90")).toBeTruthy();
  });

  it("他契約的期貨部位估不出價 → 平倉鍵鎖住(不放行跨商品平倉)", async () => {
    positions = [position({ market: "fut", stock_no: "TXFH6", name: "台指期", qty: 1 })];
    render(rail(STKFUT_CTX));
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    const close = await screen.findByRole("button", { name: "平倉" });
    expect(close.hasAttribute("disabled")).toBe(true);
    expect(close.getAttribute("title")).toBe("無行情估價");
  });

  // ⚠ 這條**不是** R2-5(instrumentKey 解除鍵)的鎖:現貨 → 合約會把 PriceLadder 換成
  // StkfutLadder,元件不同 = 必然重新掛載,武裝鈕本來就回到未武裝 —— 就算解除鍵寫成
  // `code` 它照樣綠(code review B5)。R2-5 的真鎖是 StkfutLadder.test.tsx「武裝解除鍵 =
  // instrumentKey」那兩條(同一個元件實例內換月份 / 換產品腿)。留著它是整合面的煙霧測試。
  it("現貨態切到合約 → 閃電梯換成合約梯且未武裝(整合面煙霧測試,非 R2-5 鎖)", async () => {
    const { rerender } = render(rail(STOCK_CTX));
    fireEvent.click(screen.getByRole("button", { name: "武裝" }));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    rerender(rail(STKFUT_CTX));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "武裝" }).getAttribute("aria-pressed")).toBe(
        "false",
      ),
    );
    expect(screen.getByLabelText("口數")).toBeTruthy(); // 真的換成合約梯了
  });
});

// 🔴 code review A5:個股期口數改 per instrument key。標準檔 2,000 股與小型檔 100 股
// 差 20 倍 —— 共用一格的話「在小型上按 20 口再切回標準」直接送出 20 倍規模的單,而那個
// 數字本來就是使用者自己按的,畫面上沒有任何異狀。
describe("RightRail 個股期口數不跨合約(A5)", () => {
  const MINI_CTX: RailContext = {
    ...STOCK_CTX,
    contract: { prod: "QFF", ym: "202609", mini: true, unit: 100 },
  };
  const NEXT_MONTH_CTX: RailContext = {
    ...STOCK_CTX,
    contract: { prod: "CDF", ym: "202610", mini: false, unit: 2000 },
  };

  function qty(): string {
    return (screen.getByLabelText("口數") as HTMLInputElement).value;
  }

  it("換產品腿(標準 ↔ 小型)口數回初值,切回時各自記得自己那格", () => {
    const { rerender } = render(rail(STKFUT_CTX));
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    expect(qty()).toBe("5");
    rerender(rail(MINI_CTX));
    expect(qty()).toBe("1"); // 小型那格是新的
    fireEvent.click(screen.getByRole("button", { name: "10" }));
    expect(qty()).toBe("10");
    rerender(rail(STKFUT_CTX));
    expect(qty()).toBe("5"); // 標準那格原樣還在
  });

  it("換月份(同產品腿)同樣各自一格", () => {
    const { rerender } = render(rail(STKFUT_CTX));
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    rerender(rail(NEXT_MONTH_CTX));
    expect(qty()).toBe("1");
  });

  it("切 rail tab 仍不重置(R2-10 既有行為不因分槽而破)", () => {
    render(rail(STKFUT_CTX));
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    fireEvent.click(screen.getByRole("tab", { name: "部位" }));
    fireEvent.click(screen.getByRole("tab", { name: "閃電" }));
    expect(qty()).toBe("5");
  });
});

// 🔴 code review A7a:置中請求的清除判準改 instrumentKey,且改在 render 期間清。
// 舊碼判準是 `stockCode` —— 合約 ↔ 現貨之間它完全不變(D5:code 恆是股號)→ cleanup
// 不觸發、舊的置中請求活著;而那一步正好會把 StkfutLadder 換成 PriceLadder(元件不同 =
// 真的重新掛載),新掛載的現股梯立刻吃到一個屬於合約價帶的舊請求 → 開頁就捲到別的價位
// 並關掉跟隨,零錯誤訊號。(只把 instrumentKey 加進 deps 不夠 —— destroy 裡的 setState
// 贏不了同一個 commit 內的子元件掛載,見元件內註解。)
describe("RightRail 置中請求不跨 instrument(A7a)", () => {
  function clickPrice(): void {
    act(() => {
      window.dispatchEvent(
        new CustomEvent("stock-price-click", {
          detail: { priceMilli: 100_500, side: "ask", code: "2330" },
        }),
      );
    });
  }

  const follow = () =>
    screen.getByRole("button", { name: "跟隨置中" }).getAttribute("aria-pressed");

  it("合約態點價置中後切回現貨 → 現股梯掛載時跟隨仍開啟(舊請求已清)", async () => {
    const { rerender } = render(rail(STKFUT_CTX));
    clickPrice();
    await waitFor(() => expect(follow()).toBe("false"));
    rerender(rail(STOCK_CTX)); // 同一個股號、換回現貨 → 舊 deps 認不出這是換標的
    expect(screen.getByLabelText("交易別")).toBeTruthy(); // 前提:真的換成現股梯了
    await waitFor(() => expect(follow()).toBe("true"));
  });

  it("同 instrument re-render 不清(否則每則報價都會把使用者捲回現價)", async () => {
    const { rerender } = render(rail(STKFUT_CTX));
    clickPrice();
    await waitFor(() => expect(follow()).toBe("false"));
    rerender(rail({ ...STKFUT_CTX, last: { p: 100_500, t: "09:11:00.000", cum_vol: 6 } }));
    expect(follow()).toBe("false");
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

// ---------------------------------------------------------------------------
// 鎖定武裝(R5)。上面三則「武裝不跨畫面殘留」是**未鎖定**時的合約,一條都不動;
// 鎖定是新語意:同樣的換梯 / 切 tab 動作改成保留武裝,而斷線 / Esc / 連 3 敗照舊清除。
// state 住在 RightRail(常駐全部 tab)→ 停在無梯頁時 Esc 與斷線一樣收得到。
// ---------------------------------------------------------------------------

/** blocked 個股期契約(ETF 單位 10,000):後端 `_stkfut_gates` 一律拒單 */
const BLOCKED_STKFUT_CTX: RailContext = {
  ...STOCK_CTX,
  code: "0050",
  contract: { prod: "NYF", ym: "202609", mini: false, unit: 10000 },
};

function lockUp(): void {
  fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
}

describe("RightRail 鎖定武裝跨梯保留(SC-3 / SC-4 / SC-10)", () => {
  it("SC-3:鎖定後 現貨 → 個股期 → 期貨 → 現貨,每一座新梯掛載即武裝", () => {
    setCapitalWsStatus("open");
    const { rerender } = render(rail(STOCK_CTX));
    lockUp();
    rerender(rail(STKFUT_CTX));
    expect(screen.getByLabelText("口數")).toBeTruthy(); // 真的換成合約梯
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
    rerender(rail(FUT_CTX));
    expect(screen.getByText("TXFH6")).toBeTruthy(); // 真的換成期貨梯
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
    rerender(rail(STOCK_CTX));
    expect(screen.getByLabelText("交易別")).toBeTruthy(); // 真的換回現股梯
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
  });

  it("SC-4:鎖定後切右欄 tab(閃電 → 委託 → 閃電)→ 仍武裝", () => {
    setCapitalWsStatus("open");
    render(rail(STOCK_CTX));
    lockUp();
    fireEvent.click(screen.getByRole("tab", { name: "委託" }));
    fireEvent.click(screen.getByRole("tab", { name: "閃電" }));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
  });

  it("SC-10:鎖定後整個右欄 unmount 再重新 render → 未武裝未鎖定(純 in-memory)", () => {
    setCapitalWsStatus("open");
    const { unmount } = render(rail(STOCK_CTX));
    lockUp();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
    unmount();
    cleanup();
    render(rail(STOCK_CTX));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });
});

describe("RightRail 鎖定的清除路徑(SC-6 / SC-7 / SC-12b / E-7 / R3)", () => {
  it("SC-6:鎖定中停在無梯頁時 WS 轉 closed → 回個股頁是未武裝未鎖定", () => {
    setCapitalWsStatus("open");
    const { rerender } = render(rail(STOCK_CTX));
    lockUp();
    rerender(rail(NONE_CTX));
    expect(screen.getByText("此頁無可下單標的")).toBeTruthy(); // 前提:真的沒有梯
    act(() => setCapitalWsStatus("closed"));
    rerender(rail(STOCK_CTX));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });

  it("SC-7:鎖定中停在無梯頁按 Esc → 回個股頁是未武裝未鎖定", () => {
    setCapitalWsStatus("open");
    const { rerender } = render(rail(STOCK_CTX));
    lockUp();
    rerender(rail(NONE_CTX));
    expect(screen.getByText("此頁無可下單標的")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    rerender(rail(STOCK_CTX));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });

  /** SC-12(b):disabled 只擋**進入**方向 —— 兩鈕都鎖死的話,鎖定態在 blocked 契約上
   *  沒有任何 UI 出口。點價本身仍由 priceLocked 擋。 */
  it("SC-12(b):鎖定中切到 blocked 個股期契約 → 解除 / 解鎖兩鈕仍可按,點價仍擋", () => {
    setCapitalWsStatus("open");
    const { rerender } = render(rail(STOCK_CTX));
    lockUp();
    rerender(rail(BLOCKED_STKFUT_CTX));
    expect(screen.getByRole("button", { name: "解除" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "鎖定中" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(true);
    expect(orderCalls).toBe(0);
  });

  /** E-7:鎖定態的 failStreak **刻意不隨換梯歸零**(安全方向)—— 換梯歸零的話,
   *  一直換梯就能無限重試,而連 3 敗自動解除正是為了擋住「後端在拒單但使用者在連點」。 */
  it("E-7:鎖定態 failStreak 跨梯累積(梯 A 敗 2 次 + 梯 B 敗 1 次 → 解除且清鎖定)", async () => {
    orderMode = "fail";
    setCapitalWsStatus("open");
    const { rerender } = render(rail(STOCK_CTX));
    lockUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(screen.getByText("券商拒單(1091)")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    await waitFor(() => expect(screen.getByText("券商拒單(1092)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy(); // 2 次仍鎖定
    rerender(rail(FUT_CTX));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 換梯保留武裝
    fireEvent.click(screen.getByLabelText("買 21041"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });

  /** R3:send_fail 的 dispatch 若留在 `aliveRef` 守門內,「送出後切走、回應才到」的失敗
   *  在鎖定態會整批漏計 —— 使用者一路換梯連點,連 3 敗這道閘就永遠不會關上。 */
  it("R3:鎖定中送出後切走、回應才到的三次失敗仍計數 → 解除且清鎖定", async () => {
    orderMode = "pending";
    setCapitalWsStatus("open");
    render(rail(STOCK_CTX));
    lockUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    fireEvent.click(screen.getByLabelText("買 99.9"));
    await waitFor(() => expect(pendingOrders.length).toBe(3));
    fireEvent.click(screen.getByRole("tab", { name: "部位" })); // ladder 卸載,回應還沒到
    for (const reject of pendingOrders) reject(new Error("NETWORK_DOWN"));
    fireEvent.click(screen.getByRole("tab", { name: "閃電" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });
});
