/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PriceLadder } from "@/components/stock/PriceLadder";
import { setCapitalWsStatus } from "@/hooks/useCapital";
import { ARM_IDLE_MS } from "@/lib/flash-arm";
import type { CapitalOrder, CapitalPosition } from "@/types";

const META = {
  name: "測試",
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

/** capital 路由 mock 的預設底：orders / positions 皆空,`extra` 疊加或覆寫。
 *
 *  兩條路由**每個 render 都要在**:PriceLadder 同時訂閱 useCapitalOrders 與
 *  useCapitalPositions,未登記的 URL 會讓 mock fetch 直接 throw —— 失效樣態是某個
 *  與本測試無關的 query 炸開,而不是斷言紅。 */
function mockCapitalFetch(extra: Record<string, Route> = {}) {
  return mockFetch({
    "/api/capital/orders": () => json({ orders: [] }),
    "/api/capital/positions": () => json({ positions: [] }),
    ...extra,
  });
}

function capitalOrder(overrides: Partial<CapitalOrder> = {}): CapitalOrder {
  return {
    seq_no: "001",
    stock_no: "2330",
    name: "台積電",
    market: "TS",
    buy_sell: "B",
    flag_label: "現股",
    book_no: "A1",
    status_raw: "0",
    status_label: "已委託",
    price: 100,
    avg_fill_price: null,
    order_qty: 2,
    filled_qty: 0,
    unit: "張",
    date: "20260728",
    time: "09:01:00",
    pre_order: false,
    error_msg: null,
    actionable: true,
    raw: "",
    ...overrides,
  };
}

function capitalPosition(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "sec",
    stock_no: "2330",
    qty: 2,
    name: "台積電",
    avg_price: 100,
    kind: "cash",
    pnl_base: null,
    pnl_base_price: null,
    pnl_cost: null,
    ...overrides,
  };
}

const OK_RESULT = { ok: true, code: 0, message: "ok", seq_no: "001" };

let qc: QueryClient;

function ladder(code = "2330", last: typeof LAST | null = LAST) {
  return (
    <QueryClientProvider client={qc}>
      <PriceLadder code={code} book={BOOK} last={last} meta={META} />
    </QueryClientProvider>
  );
}

function armUp(): void {
  fireEvent.click(screen.getByRole("button", { name: "武裝" }));
}

beforeEach(() => {
  window.localStorage.clear();
  setCapitalWsStatus("connecting"); // wsStatus module store 跨測試重置
  // jsdom 無 scrollIntoView(跟隨置中 / 置中事件 spy stub)
  Element.prototype.scrollIntoView = vi.fn();
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("PriceLadder 市價單列(round6 項 4)", () => {
  /** 2026-07-31 盤中實測 2327 國巨鎖漲停:bids[0] 是 15966 張市價買單、價格欄 0 */
  const LOCK_UP_BOOK = {
    bids: [[0, 15_966], [110_000, 9_385]] as [number, number][],
    asks: [] as [number, number][],
  };
  const LOCK_DOWN_BOOK = {
    bids: [] as [number, number][],
    asks: [[0, 20_000], [90_000, 5_000]] as [number, number][],
  };

  function render_(book: typeof BOOK) {
    mockCapitalFetch();
    return render(
      <QueryClientProvider client={qc}>
        <PriceLadder code="2327" book={book} last={LAST} meta={META} />
      </QueryClientProvider>,
    );
  }

  it("有市價買單 → 階梯最上方多一列「市價」顯示量(SC-4.3)", () => {
    const { container } = render_(LOCK_UP_BOOK);
    const row = screen.getByTestId("ladder-market-bid");
    expect(row.textContent).toContain("市價");
    expect(row.textContent).toContain("15966");
    // 位置語意:市價買單優先於任何限價買單 → 在漲停價那列**之前**
    const all = [...container.querySelectorAll("[data-testid], .grid")];
    expect(all.indexOf(row)).toBeLessThan(
      all.findIndex((n) => n.textContent?.trim().startsWith("9385")),
    );
  });

  it("有市價賣單 → 階梯最下方多一列(SC-4.3 對稱)", () => {
    render_(LOCK_DOWN_BOOK);
    const row = screen.getByTestId("ladder-market-ask");
    expect(row.textContent).toContain("市價");
    expect(row.textContent).toContain("20000");
    expect(screen.queryByTestId("ladder-market-bid")).toBeNull();
  });

  it("無市價單 → 兩列都不出現", () => {
    render_(BOOK);
    expect(screen.queryByTestId("ladder-market-bid")).toBeNull();
    expect(screen.queryByTestId("ladder-market-ask")).toBeNull();
  });

  it("市價列不可送單 —— 即使已武裝也沒有可點的送單鈕(SC-4.4)", () => {
    render_(LOCK_UP_BOOK);
    armUp();
    const row = screen.getByTestId("ladder-market-bid");
    expect(row.querySelectorAll("button")).toHaveLength(0);
  });
});

describe("PriceLadder(既有顯示行為)", () => {
  // 🔴-6:摺疊機制移除(右欄 tab 本身即顯隱,stock-ladder-open 停用)
  it("直接展開:價格列即時可見,標題列顯示標的(D-12)", () => {
    mockCapitalFetch();
    render(ladder());
    expect(screen.getByText("110")).toBeTruthy(); // 漲停端點
    expect(screen.getByText("90")).toBeTruthy(); // 跌停端點
    expect(screen.queryByRole("button", { name: "閃電梯" })).toBeNull(); // 無摺疊鈕
    expect(screen.getByText("2330")).toBeTruthy(); // 標的股號
  });

  it("標題列帶股名時一併顯示(右欄跨 tab 切換的誤送防線)", () => {
    mockCapitalFetch();
    render(
      <QueryClientProvider client={qc}>
        <PriceLadder code="2330" name="台積電" book={BOOK} last={LAST} meta={META} />
      </QueryClientProvider>,
    );
    expect(screen.getByText("台積電")).toBeTruthy();
  });

  it("五檔量對映顯示於對應價位列(買賣側各自可點區)", () => {
    mockCapitalFetch();
    render(ladder());
    expect(screen.getByLabelText("買 100").textContent).toBe("30");
    expect(screen.getByLabelText("賣 100.5").textContent).toBe("10");
  });

  it("±5% 外價位買賣側皆反灰不可點(SC-7)", () => {
    mockCapitalFetch();
    render(ladder());
    expect(screen.getByLabelText("買 110").hasAttribute("disabled")).toBe(true);
    expect(screen.getByLabelText("賣 110").hasAttribute("disabled")).toBe(true);
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(false);
  });

  it("跟隨置中預設開,center 變更觸發 scrollIntoView", () => {
    mockCapitalFetch();
    const { rerender } = render(ladder());
    expect(
      screen.getByRole("button", { name: "跟隨置中" }).getAttribute("aria-pressed"),
    ).toBe("true");
    const spy = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    spy.mockClear();
    rerender(ladder("2330", { ...LAST, p: 101_000 }));
    expect(spy).toHaveBeenCalled();
  });

  it("無 ref 與 last → 顯示「無資料」(edge 6)", () => {
    mockCapitalFetch();
    render(
      <QueryClientProvider client={qc}>
        <PriceLadder
          code="2330"
          book={null}
          last={null}
          meta={{ ...META, ref: null, upper: null, lower: null }}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("無資料")).toBeTruthy();
  });
});

// 反灰(±5% 外)的淡化落在哪一層。SC-4 的梯內標記必須**不受**淡化影響(遠離現價的
// 打平標記正是最需要看見的),而 opacity 套在 row 容器上時子元素無法「反淡」
// → 淡化改套三個 grid 欄。這是本輪唯一「該變」的既有斷言(PLAN §3 明列)。
describe("PriceLadder 反灰列的淡化落點", () => {
  it("±5% 外的列:三個 grid 欄各自淡化,row 容器不淡化", () => {
    mockCapitalFetch();
    render(ladder());
    const buy = screen.getByLabelText("買 110");
    const sell = screen.getByLabelText("賣 110");
    const row = buy.closest("div.grid") as HTMLElement;
    expect(row).toBeTruthy();
    expect(row.className).not.toContain("opacity-35");
    expect(buy.parentElement!.className).toContain("opacity-35");
    expect(sell.parentElement!.className).toContain("opacity-35");
    expect(within(row).getByText("110").className).toContain("opacity-35");
  });
});

describe("PriceLadder 武裝直送(SC-7)", () => {
  it("武裝點價:1 次 API call + payload 斷言;鈕轉「解除」紅底", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    const disarmBtn = screen.getByRole("button", { name: "解除" });
    expect(disarmBtn.getAttribute("aria-pressed")).toBe("true");
    expect(disarmBtn.className).toContain("bg-loss");
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      stock_no: "2330",
      buy_sell: "buy",
      price: 100,
      qty: 1,
      price_type: "limit",
      time_in_force: "ROD",
      trade_kind: "cash",
      source: "flash",
    });
  });

  it("未武裝點價:零請求 + hint「未武裝 — 點價不送單」3s 自動消失", () => {
    vi.useFakeTimers();
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    expect(screen.getByText("未武裝 — 點價不送單")).toBeTruthy();
    expect(bodies.length).toBe(0);
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(screen.queryByText("未武裝 — 點價不送單")).toBeNull();
  });

  it("同格 500ms 防抖:連點同格 1 call;不同格照送", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies).toMatchObject([{ buy_sell: "buy" }, { buy_sell: "sell" }]);
  });

  it("code 變更自動解除武裝(symbol_changed)", () => {
    mockCapitalFetch();
    const { rerender } = render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    rerender(ladder("2317"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("Esc 鍵解除武裝", () => {
    mockCapitalFetch();
    render(ladder());
    armUp();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("capital wsStatus 轉 closed 自動解除(conn_lost;wsStatus store 注入)", () => {
    mockCapitalFetch();
    render(ladder());
    armUp();
    act(() => setCapitalWsStatus("open"));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    act(() => setCapitalWsStatus("closed"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("idle 5 分鐘自動解除", () => {
    vi.useFakeTimers();
    mockCapitalFetch();
    render(ladder());
    armUp();
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 1);
    });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("無券(daytrade_sell)鎖買側;賣側照送且 payload 帶 trade_kind", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.change(screen.getByLabelText("交易別"), { target: { value: "daytrade_sell" } });
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(true);
    expect(screen.getByLabelText("賣 100.5").hasAttribute("disabled")).toBe(false);
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ buy_sell: "sell", trade_kind: "daytrade_sell" });
  });

  it("qty 快捷同鍵累加 + 手動輸入重置;payload 帶累加後張數", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    const qtyInput = screen.getByLabelText("張數") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect(qtyInput.value).toBe("6");
    fireEvent.click(screen.getByRole("button", { name: "5" }));
    expect(qtyInput.value).toBe("5");
    fireEvent.change(qtyInput, { target: { value: "7" } });
    expect(qtyInput.value).toBe("7");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect(qtyInput.value).toBe("3");
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect(qtyInput.value).toBe("6");
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ qty: 6 });
  });

  it("送單失敗:hint 顯示 tradeErrorText 文案;連 3 次失敗自動解除", async () => {
    mockCapitalFetch({
      "/api/capital/order/stock": () =>
        json({ detail: { error: "ORDER_BLOCKED", reason: "order_disabled" } }, 403),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(screen.getByText("安全閘拒絕(order_disabled)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 1 次失敗仍武裝
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    fireEvent.click(screen.getByLabelText("買 99.9"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
  });
});

describe("PriceLadder 掛單紅方格(SC-7)", () => {
  it("本檔活單價位聚合殘量;他檔/非活單不顯示;點擊逐 seq 直刪", async () => {
    const cancelBodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            capitalOrder({ seq_no: "001", price: 100, order_qty: 2, filled_qty: 0 }),
            capitalOrder({ seq_no: "002", price: 100, order_qty: 3, filled_qty: 1 }),
            capitalOrder({ seq_no: "003", buy_sell: "S", price: 100.5, order_qty: 1 }),
            capitalOrder({ seq_no: "004", price: 100, actionable: false }),
            capitalOrder({ seq_no: "005", stock_no: "2317", price: 100 }),
          ],
        }),
    });
    render(ladder());
    const buyLot = await screen.findByLabelText("刪 100 買單");
    expect(buyLot.textContent).toBe("4"); // 2 + (3-1)
    expect(screen.getByLabelText("刪 100.5 賣單").textContent).toBe("1");
    expect(screen.queryByLabelText("刪 99.9 買單")).toBeNull();
    fireEvent.click(buyLot);
    await waitFor(() => expect(cancelBodies.length).toBe(2));
    expect(cancelBodies).toMatchObject([
      { seq_no: "001", market: "sec" },
      { seq_no: "002", market: "sec" },
    ]);
  });
});

// ---------------------------------------------------------------------------
// 部位列 + 未實現損益 + 含成本打平價(SC-1 / SC-4 / SC-5 / SC-6 / SC-7)
// ---------------------------------------------------------------------------

function renderWith(
  positions: CapitalPosition[],
  last: typeof LAST | null = LAST,
  code = "2330",
) {
  mockCapitalFetch({ "/api/capital/positions": () => json({ positions }) });
  return render(
    <QueryClientProvider client={qc}>
      <PriceLadder code={code} book={BOOK} last={last} meta={META} />
    </QueryClientProvider>,
  );
}

describe("PriceLadder 部位條(SC-1 / SC-6 / SC-7)", () => {
  it("多方現股:第一行 kind + 量 + 均價、右緣未實現損益,第二行打平價", async () => {
    renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(within(bar).getByText("現股 2張 @100")).toBeTruthy();
    const pnl = within(bar).getByText("+3,284");
    expect(pnl.className).toContain("text-bull");
    expect(within(bar).getByText("打平 100.5")).toBeTruthy();
  });

  it("空手 → 部位條整段不渲染(非本檔 / 非 sec / qty 0 皆濾掉)", async () => {
    mockCapitalFetch({
      "/api/capital/positions": () =>
        json({
          positions: [
            capitalPosition({ stock_no: "2317", name: "鴻海" }),
            capitalPosition({ market: "fut", stock_no: "TXFH6", name: "台指期" }),
            capitalPosition({ qty: 0, kind: "margin" }),
          ],
        }),
    });
    const { rerender } = render(ladder("2330"));
    // 「資料已到」的證據:同一份 positions 換到 2317 就看得見部位條
    rerender(ladder("2317"));
    expect(await screen.findByTestId("ladder-position-bar")).toBeTruthy();
    rerender(ladder("2330"));
    expect(screen.queryByTestId("ladder-position-bar")).toBeNull();
  });

  it("多 kind → 逐 kind 一列,cash 在 short 之前(SC-6)", async () => {
    renderWith(
      [capitalPosition({ kind: "short", qty: -2 }), capitalPosition()],
      { ...LAST, p: 102_000 },
    );
    const bar = await screen.findByTestId("ladder-position-bar");
    const rows = within(bar).getAllByTestId("ladder-position-row");
    expect(rows.length).toBe(2);
    expect(rows[0]!.textContent).toContain("現股 2張 @100");
    expect(rows[1]!.textContent).toContain("融券 空2張 @100");
  });

  it("空方列:量帶「空」、負 pnl 用 text-bear、打平往下 snap", async () => {
    renderWith([capitalPosition({ kind: "short", qty: -2 })], { ...LAST, p: 103_000 });
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(within(bar).getByText("融券 空2張 @100")).toBeTruthy();
    expect(within(bar).getByText("-6,864").className).toContain("text-bear");
    expect(within(bar).getByText("打平 99.5")).toBeTruthy();
  });

  it("均價缺值 → 量照顯示、均價與打平皆「—」、不畫任何標記(SC-7)", async () => {
    renderWith([capitalPosition({ avg_price: null })]);
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(within(bar).getByText("現股 2張 @—")).toBeTruthy();
    expect(within(bar).getByText("打平 —")).toBeTruthy();
    expect(within(bar).getByText("—")).toBeTruthy(); // pnl 亦缺
    expect(screen.queryAllByTestId("ladder-be-mark").length).toBe(0);
    expect(screen.queryAllByTestId("ladder-avg-mark").length).toBe(0);
  });

  it("現價缺值 → pnl「—」,打平照算照畫(D15)", async () => {
    renderWith([capitalPosition()], null);
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(within(bar).getByText("打平 100.5")).toBeTruthy();
    expect(within(bar).getByText("—")).toBeTruthy();
    expect(screen.getByTestId("ladder-be-mark")).toBeTruthy();
  });
});

describe("PriceLadder 梯內標記(SC-4)", () => {
  it("打平 / 均價標記落在正確價位列,title 帶 kind", async () => {
    renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    const be = await screen.findByTestId("ladder-be-mark");
    expect(be.closest("[data-price]")!.getAttribute("data-price")).toBe("100500");
    expect(be.getAttribute("title")).toBe("打平(現股)");
    const avg = screen.getByTestId("ladder-avg-mark");
    expect(avg.closest("[data-price]")!.getAttribute("data-price")).toBe("100000");
    expect(avg.getAttribute("title")).toBe("均價(現股)");
  });

  it("反灰列上的標記不跟著淡化(自帶 opacity-100)", async () => {
    renderWith([capitalPosition({ avg_price: 106 })]);
    const avg = await screen.findByTestId("ladder-avg-mark");
    expect(avg.className).toContain("opacity-100");
    expect(avg.className).not.toContain("opacity-35");
    const row = avg.closest("[data-price]") as HTMLElement;
    expect(row.getAttribute("data-price")).toBe("106000");
    expect(row.className).not.toContain("opacity-35");
    // 同列的內容欄確實反灰 —— 標記不淡化才有意義
    expect(screen.getByLabelText("買 106").parentElement!.className).toContain("opacity-35");
  });

  it("打平價超出梯域(均價貼漲停)→ 不畫標記,部位條數字照顯示(IS-3)", async () => {
    renderWith([capitalPosition({ avg_price: 110 })]);
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(within(bar).getByText("打平 110.5")).toBeTruthy();
    expect(screen.queryAllByTestId("ladder-be-mark").length).toBe(0);
    expect(screen.getByTestId("ladder-avg-mark")).toBeTruthy(); // 均價本身仍在梯上
  });
});

describe("PriceLadder 手續費折數(SC-5 / D1)", () => {
  it("初值取 localStorage,缺值退回預設 1.8", () => {
    mockCapitalFetch();
    render(ladder());
    expect((screen.getByLabelText("手續費折數") as HTMLInputElement).value).toBe("1.8");
    cleanup();
    window.localStorage.setItem("copycat-fee-discount", "2.5");
    mockCapitalFetch();
    render(ladder());
    expect((screen.getByLabelText("手續費折數") as HTMLInputElement).value).toBe("2.5");
  });

  it("改折數 → 重算 pnl 並以字面 key 寫入 localStorage(IS-10)", async () => {
    renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(within(bar).getByText("+3,284")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("手續費折數"), { target: { value: "0.5" } });
    expect(window.localStorage.getItem("copycat-fee-discount")).toBe("0.5");
    expect(
      within(screen.getByTestId("ladder-position-bar")).getByText("+3,359"),
    ).toBeTruthy();
  });

  it("非法折數(0 / -1 / 11)不寫入且計算沿用最後一次合法值(IS-6)", async () => {
    renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    await screen.findByTestId("ladder-position-bar");
    const input = screen.getByLabelText("手續費折數") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "0.5" } });
    for (const bad of ["0", "-1", "11"]) {
      fireEvent.change(input, { target: { value: bad } });
      expect(input.value).toBe(bad); // 受控輸入照顯示原始值,不吃掉使用者的按鍵
      expect(window.localStorage.getItem("copycat-fee-discount")).toBe("0.5");
      expect(
        within(screen.getByTestId("ladder-position-bar")).getByText("+3,359"),
      ).toBeTruthy();
    }
  });

  it("空手也能設定折數 —— 輸入框恆常渲染(D1)", () => {
    mockCapitalFetch();
    render(ladder());
    fireEvent.change(screen.getByLabelText("手續費折數"), { target: { value: "3" } });
    expect(window.localStorage.getItem("copycat-fee-discount")).toBe("3");
    expect(screen.queryByTestId("ladder-position-bar")).toBeNull();
  });

  it("改折數不影響張數輸入,且折數框帶可見「折」後綴(IS-8)", () => {
    mockCapitalFetch();
    render(ladder());
    const qty = screen.getByLabelText("張數") as HTMLInputElement;
    fireEvent.change(qty, { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("手續費折數"), { target: { value: "3" } });
    expect(qty.value).toBe("7");
    expect((screen.getByLabelText("手續費折數") as HTMLInputElement).value).toBe("3");
    expect(screen.getByText("折")).toBeTruthy();
  });
});

// 🔴-10:window listener 上移到 RightRail(右欄非閃電 tab 時本元件已 unmount,
// 自有 listener 收不到 — change-spec R2-5)。本元件改吃 centerRequest prop。
// 「事件 → 切回閃電 tab → 置中」的完整鏈由 RightRail.test.tsx 覆蓋。
describe("PriceLadder 置中請求(centerRequest prop)", () => {
  function withCenter(centerRequest: { priceMilli: number; nonce: number } | null) {
    return (
      <QueryClientProvider client={qc}>
        <PriceLadder
          code="2330"
          book={BOOK}
          last={LAST}
          meta={META}
          centerRequest={centerRequest}
        />
      </QueryClientProvider>
    );
  }

  it("centerRequest → 該價置中、暫停跟隨,且不送單", () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    const { rerender } = render(withCenter(null));
    const spy = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    spy.mockClear();
    rerender(withCenter({ priceMilli: 100_500, nonce: 1 }));
    expect(spy).toHaveBeenCalled();
    expect(bodies.length).toBe(0);
    expect(
      screen.getByRole("button", { name: "跟隨置中" }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("同價連點靠 nonce 變化重捲(值相同不會被 effect deps 吞掉)", () => {
    mockCapitalFetch();
    const { rerender } = render(withCenter({ priceMilli: 100_500, nonce: 1 }));
    const spy = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    spy.mockClear();
    rerender(withCenter({ priceMilli: 100_500, nonce: 2 }));
    expect(spy).toHaveBeenCalled();
  });

  it("不在階梯上的價位 → 不捲動也不崩", () => {
    mockCapitalFetch();
    const { rerender } = render(withCenter(null));
    const spy = Element.prototype.scrollIntoView as ReturnType<typeof vi.fn>;
    spy.mockClear();
    rerender(withCenter({ priceMilli: 999_999, nonce: 1 }));
    expect(spy).not.toHaveBeenCalled();
  });
});
