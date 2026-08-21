/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PriceLadder, type TradeKind } from "@/components/stock/PriceLadder";
import { setCapitalWsStatus } from "@/hooks/useCapital";
import { ARM_IDLE_MS, LOCK_TITLE } from "@/lib/flash-arm";
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
    price_type: null,
    raw: "",
    ...overrides,
  };
}

/** 動態 YYYYMMDD:已成交量的日期界以 `new Date()` 每 render 算(現股梯 = 嚴格今日),
 *  fixture 寫死過去日的話終態徽章案永遠取不到 filled(spec A6)。 */
function ymd(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${d.getFullYear()}${m}${String(d.getDate()).padStart(2, "0")}`;
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
    code: null,
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

  it("反灰列的分隔線降階到 border-line/20,一般列維持 /50(LP-4)", () => {
    mockCapitalFetch();
    render(ladder());
    const dimmed = screen.getByLabelText("買 110").closest("div.grid") as HTMLElement;
    const normal = screen.getByLabelText("買 100").closest("div.grid") as HTMLElement;
    // border 掛在 row 容器上,移欄後不再吃 row 的 opacity → 不降階會比改動前亮
    expect(dimmed.className).toContain("border-line/20");
    expect(dimmed.className).not.toContain("border-line/50");
    expect(normal.className).toContain("border-line/50");
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
    // 🔴 R6 該變:交易別 select → 四顆 pill,選取 = 點「無券」(a11y 批:pill 改 radio)
    fireEvent.click(screen.getByRole("radio", { name: "無券" }));
    expect((screen.getByRole("radio", { name: "無券" }) as HTMLInputElement).checked).toBe(true);
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
    expect(buyLot.textContent).toBe("4(1)"); // 未成交 2 + (3-1) / 已成交 1
    expect(screen.getByLabelText("刪 100.5 賣單").textContent).toBe("1(0)");
    expect(screen.queryByLabelText("刪 99.9 買單")).toBeNull();
    fireEvent.click(buyLot);
    await waitFor(() => expect(cancelBodies.length).toBe(2));
    expect(cancelBodies).toMatchObject([
      { seq_no: "001", market: "sec" },
      { seq_no: "002", market: "sec" },
    ]);
  });

  /** T1(review round-1):`isCancelable` 的 `|| seqs.length > 0` 半條在元件層無鎖 ——
   *  拿掉它時 aggregateLots 的測試全綠,但畫面上這種單會從可點紅方格掉成不可點徽章
   *  (甚至整格消失),使用者失去刪單入口。「殘量 0 的活單」不是理論態:P/U 先到、
   *  N 未到,以及改量亂序期都會出現(store.py:86 註)。 */
  it("actionable 殘 0 活單 → 仍是可點紅方格 `0(0)`,點擊照送 cancel", async () => {
    const cancelBodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({ orders: [capitalOrder({ seq_no: "016", order_qty: 0, filled_qty: 0 })] }),
    });
    render(ladder());
    const lot = await screen.findByLabelText("刪 100 買單");
    expect(lot.textContent).toBe("0(0)");
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull(); // 不得降級成徽章
    fireEvent.click(lot);
    await waitFor(() => expect(cancelBodies.length).toBe(1));
    expect(cancelBodies).toMatchObject([{ seq_no: "016", market: "sec" }]);
  });

  it("actionable 且已全數成交(N 未到)→ `0(2)` 仍可點", async () => {
    mockCapitalFetch({
      "/api/capital/orders": () =>
        json({
          orders: [
            capitalOrder({ seq_no: "017", order_qty: 2, filled_qty: 2, date: ymd() }),
          ],
        }),
    });
    render(ladder());
    expect((await screen.findByLabelText("刪 100 買單")).textContent).toBe("0(2)");
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
  });
});

describe("PriceLadder 已成交徽章(SC-2)", () => {
  /** 同價全部成交(終態單)→ 無 seq 可刪 → 不可點徽章;紅方格(button)必須消失 */
  it("全成交 → `(N)` 徽章、非 button、點擊不送 cancel", async () => {
    const cancelBodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            capitalOrder({
              seq_no: "010",
              price: 100,
              order_qty: 2,
              filled_qty: 2,
              actionable: false,
              status_label: "全部成交",
              date: ymd(),
            }),
          ],
        }),
    });
    render(ladder());
    const badge = await screen.findByTestId("ladder-filled-lot");
    expect(badge.textContent).toBe("(2)");
    expect(badge.tagName).toBe("SPAN");
    expect(badge.className).toContain("pointer-events-none");
    expect(screen.queryByLabelText("刪 100 買單")).toBeNull();
    fireEvent.click(badge);
    await act(async () => {
      await Promise.resolve();
    });
    expect(cancelBodies.length).toBe(0);
    // 徽章佔位不吃掉同列點價鈕(R8:鈕變窄是承認的偏差,不可點才是 bug)
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(false);
  });

  /** T4:徽章分支買賣側各一份(LadderView 的兩塊三元),只測買側時賣側那塊
   *  改壞了照樣全綠 —— 賣側紅方格 / 徽章在右緣,渲染路徑獨立。 */
  it("賣側全成交 → 右緣 `(N)` 徽章、賣側紅方格消失(對稱)", async () => {
    mockCapitalFetch({
      "/api/capital/orders": () =>
        json({
          orders: [
            capitalOrder({
              seq_no: "018",
              buy_sell: "S",
              price: 100.5,
              order_qty: 2,
              filled_qty: 2,
              actionable: false,
              status_label: "全部成交",
              date: ymd(),
            }),
          ],
        }),
    });
    render(ladder());
    const badge = await screen.findByTestId("ladder-filled-lot");
    expect(badge.textContent).toBe("(2)");
    expect(screen.queryByLabelText("刪 100.5 賣單")).toBeNull();
  });

  it("部分成交後刪單 → 徽章留下已成交量(成交是事實)", async () => {
    mockCapitalFetch({
      "/api/capital/orders": () =>
        json({
          orders: [
            capitalOrder({
              seq_no: "011",
              price: 100,
              order_qty: 5,
              filled_qty: 2,
              actionable: false,
              status_label: "已刪單",
              date: ymd(),
            }),
          ],
        }),
    });
    render(ladder());
    expect((await screen.findByTestId("ladder-filled-lot")).textContent).toBe("(2)");
  });

  /** 「查無」斷言的同步錨:orders query 未回時整梯也是空的 —— 沒有這筆對照單,
   *  三個 absence 案在「資料還沒到」的瞬間就恆綠(vacuous)。 */
  const ANCHOR = capitalOrder({ seq_no: "099", buy_sell: "S", price: 100.5, order_qty: 1 });

  it("失敗 / 退單(filled 0)→ 零痕跡(無徽章也無紅方格)", async () => {
    mockCapitalFetch({
      "/api/capital/orders": () =>
        json({
          orders: [
            ANCHOR,
            capitalOrder({
              seq_no: "012",
              price: 100,
              order_qty: 2,
              filled_qty: 0,
              actionable: false,
              status_label: "失敗",
              date: ymd(),
            }),
          ],
        }),
    });
    render(ladder());
    await screen.findByLabelText("刪 100.5 賣單");
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
    expect(screen.queryByLabelText("刪 100 買單")).toBeNull();
  });

  it("終態單 date=昨日 → 無徽章(現股梯嚴格今日,跨日幽靈不長出來)", async () => {
    mockCapitalFetch({
      "/api/capital/orders": () =>
        json({
          orders: [
            ANCHOR,
            capitalOrder({
              seq_no: "013",
              price: 100,
              order_qty: 2,
              filled_qty: 2,
              actionable: false,
              status_label: "全部成交",
              date: ymd(-1),
            }),
          ],
        }),
    });
    render(ladder());
    await screen.findByLabelText("刪 100.5 賣單");
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
  });

  it("零股單(unit=股)整筆不上梯 —— 張梯不混單位(R6)", async () => {
    mockCapitalFetch({
      "/api/capital/orders": () =>
        json({
          orders: [
            ANCHOR,
            capitalOrder({ seq_no: "014", price: 100, order_qty: 1_000, unit: "股" }),
            capitalOrder({
              seq_no: "015",
              price: 100,
              order_qty: 500,
              filled_qty: 500,
              unit: "股",
              actionable: false,
              status_label: "全部成交",
              date: ymd(),
            }),
          ],
        }),
    });
    render(ladder());
    await screen.findByLabelText("刪 100.5 賣單");
    expect(screen.queryByLabelText("刪 100 買單")).toBeNull();
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
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

  // LP-3:位置本身是安全需求(D5)—— 部位條插在梯**上方**會讓整梯下移,武裝中的
  // 點擊目標就在部位資料到達的那一刻位移。斷言它是卡片 root 的最後一個子元素。
  it("部位條在卡片最底 —— 價格梯 scroll 區之後(LP-3 / D5)", async () => {
    const { container } = renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    const bar = await screen.findByTestId("ladder-position-bar");
    const card = container.firstElementChild!;
    expect(card.lastElementChild).toBe(bar);
    const scroller = screen.getByLabelText("買 100").closest(".overflow-y-auto")!;
    // DOCUMENT_POSITION_FOLLOWING = 4:bar 在 scroll 容器之後
    expect(scroller.compareDocumentPosition(bar) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(4);
  });

  it("現價前進 → pnl 隨之重算(LP-6)", async () => {
    mockCapitalFetch({
      "/api/capital/positions": () => json({ positions: [capitalPosition()] }),
    });
    const { rerender } = render(ladder("2330", { ...LAST, p: 102_000 }));
    expect(within(await screen.findByTestId("ladder-position-bar")).getByText("+3,284")).toBeTruthy();
    rerender(ladder("2330", { ...LAST, p: 103_000 }));
    // 6000 − 51.3 − 670.839 = 5277.861
    expect(
      within(screen.getByTestId("ladder-position-bar")).getByText("+5,278"),
    ).toBeTruthy();
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

  it("第二行兩顆色點:bg-warn 對「打平 <值>」、bg-ma20 對「均價」標籤(LP-1 / CALC-3)", async () => {
    renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    const bar = await screen.findByTestId("ladder-position-bar");
    expect(within(bar).getByText("打平 100.5")).toBeTruthy();
    expect(within(bar).getByText("均價")).toBeTruthy();
    const dots = [...bar.querySelectorAll("[aria-hidden='true']")];
    expect(dots.some((d) => d.className.includes("bg-warn"))).toBe(true);
    expect(dots.some((d) => d.className.includes("bg-ma20"))).toBe(true);
    // 均價色點**不並列數字**:第一行 @100 是真均價,標線位置是 snapNearest 近似,
    // 兩個口徑的數字並列會讓人以為均價變了(CALC-3)
    expect(bar.textContent).not.toContain("均價 1");
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
  it("打平 / 均價標記落在正確價位列;title 掛 row 容器、標記本身不帶(LP-1)", async () => {
    renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    const be = await screen.findByTestId("ladder-be-mark");
    const beRow = be.closest("[data-price]")!;
    expect(beRow.getAttribute("data-price")).toBe("100500");
    // 標記是 pointer-events-none → 永遠不會觸發自己的 tooltip,title 必須掛 row
    expect(be.getAttribute("title")).toBeNull();
    expect(beRow.getAttribute("title")).toBe("打平(現股)");
    const avg = screen.getByTestId("ladder-avg-mark");
    const avgRow = avg.closest("[data-price]")!;
    expect(avgRow.getAttribute("data-price")).toBe("100000");
    expect(avg.getAttribute("title")).toBeNull();
    expect(avgRow.getAttribute("title")).toBe("均價(現股)");
    // 無標記的列不掛 title(免整梯都是空 tooltip)
    expect(
      screen.getByLabelText("買 99.9").closest("[data-price]")!.getAttribute("title"),
    ).toBeNull();
  });

  it("同一列同時有打平與均價 → row title 併成一句(LP-1)", async () => {
    // 現股 avg=100 的打平落 100.5;融資 avg=100.5 的均價標記同樣落 100.5
    renderWith([capitalPosition(), capitalPosition({ kind: "margin", avg_price: 100.5 })]);
    await screen.findByTestId("ladder-position-bar");
    const row = screen.getByLabelText("買 100.5").closest("[data-price]")!;
    expect(row.getAttribute("title")).toBe("打平(現股)、均價(融資)");
  });

  it("標記不吃點擊(LP-2)—— 左緣正是刪單紅方格與買鈕的點擊區", async () => {
    renderWith([capitalPosition()], { ...LAST, p: 102_000 });
    const be = await screen.findByTestId("ladder-be-mark");
    expect(be.className).toContain("pointer-events-none");
    expect(screen.getByTestId("ladder-avg-mark").className).toContain("pointer-events-none");
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

  it("折數框在標題列(跟隨置中鈕左側),武裝列零折數框(ORD-1 / LP-7)", () => {
    mockCapitalFetch();
    render(ladder());
    const input = screen.getByLabelText("手續費折數");
    const titleRow = screen.getByRole("button", { name: "跟隨置中" }).closest("div.border-b")!;
    const armRow = screen.getByLabelText("張數").closest("div.border-b")!;
    expect(titleRow).not.toBe(armRow);
    expect(titleRow.contains(input)).toBe(true);
    // 折數與張數同型相鄰是誤打風險(誤打折數 → 張數靜默留舊值 → 舊張數送真單)
    expect(armRow.contains(input)).toBe(false);
  });

  it("非法折數 → aria-invalid + 紅框;改回合法即消失(CALC-1)", () => {
    mockCapitalFetch();
    render(ladder());
    const input = screen.getByLabelText("手續費折數");
    expect(input.getAttribute("aria-invalid")).toBeNull();
    expect(input.className).not.toContain("border-loss");
    fireEvent.change(input, { target: { value: "0" } });
    // 「輸入框顯示 raw、計算用舊 value 且零訊號」是靜默態,必須有可視訊號
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.className).toContain("border-loss");
    fireEvent.change(input, { target: { value: "1.8" } });
    expect(input.getAttribute("aria-invalid")).toBeNull();
    expect(input.className).not.toContain("border-loss");
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

// ---------------------------------------------------------------------------
// 鎖定武裝(R5)。鎖定 = 換標的 / 換梯 / 閒置都不解除 —— 誤觸半徑放到最大,所以
// 「鎖定態畫面可指認」與「清除路徑照舊」兩件事都要在元件層釘住。
// ---------------------------------------------------------------------------

function lockUp(): void {
  fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
}

describe("PriceLadder 鎖定武裝(SC-1 / SC-2 / SC-8 / SC-9 / SC-13)", () => {
  it("SC-1:按鎖定 → 梯立即武裝且鎖定鈕轉「鎖定中」桃紅底 aria-pressed=true", () => {
    mockCapitalFetch();
    setCapitalWsStatus("open");
    render(ladder());
    const lock = screen.getByRole("button", { name: "鎖定" });
    expect(lock.getAttribute("aria-pressed")).toBe("false");
    expect(lock.hasAttribute("disabled")).toBe(false);
    expect(lock.getAttribute("title")).toBe(LOCK_TITLE); // 常態 tooltip(兩處渲染點同源)
    expect(lock.className).toContain("border-line"); // 未鎖定 = 灰框灰字,與武裝態可辨
    // 武裝鈕與鎖定鈕同列(288px 右欄下三控制項不換行的前提;寬度本身走截圖層)
    const armBtn = screen.getByRole("button", { name: "武裝" });
    expect(lock.parentElement).toBe(armBtn.parentElement);
    expect(lock.className).toContain("shrink-0");
    // SC-1 的次序:武裝鈕 → 鎖定鈕 → 商品別控制項(交易別 pill 群,R6 起;容器 aria-label 同名)
    expect(armBtn.compareDocumentPosition(lock) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      lock.compareDocumentPosition(screen.getByLabelText("交易別")) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    lockUp();
    expect(screen.getByRole("button", { name: "解除" }).getAttribute("aria-pressed")).toBe("true");
    const locked = screen.getByRole("button", { name: "鎖定中" });
    expect(locked.getAttribute("aria-pressed")).toBe("true");
    expect(locked.className).toContain("bg-accent");
  });

  it("SC-2:鎖定後換自選股(code 變)→ 仍武裝,點價照送 1 call", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    setCapitalWsStatus("open");
    const { rerender } = render(ladder());
    lockUp();
    rerender(ladder("2317"));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ stock_no: "2317", buy_sell: "buy" });
  });

  it("SC-9:按「鎖定中」→ 解鎖但保持武裝;再按「解除」→ 兩旗全清", () => {
    mockCapitalFetch();
    setCapitalWsStatus("open");
    render(ladder());
    lockUp();
    fireEvent.click(screen.getByRole("button", { name: "鎖定中" }));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 仍武裝
    expect(screen.getByRole("button", { name: "鎖定" }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "解除" }));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });

  /** SC-9 後半 / E-5:解鎖 = 回到一般武裝語意,**閒置計時要重新起算**。鎖定期間的
   *  idle_timeout 是 no-op 且不再排下一輪,所以解鎖那一下若沒 `touchIdle()`,就再也
   *  沒有計時器 —— 一路武裝到天亮,而畫面上與「剛剛才武裝」完全一樣。 */
  it("E-5:鎖定閒置 6 分仍武裝 → 按「鎖定中」解鎖 → 再閒置 5 分才解除", () => {
    vi.useFakeTimers();
    mockCapitalFetch();
    setCapitalWsStatus("open");
    render(ladder());
    lockUp();
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 60_000);
    });
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy(); // 6 分仍鎖定
    fireEvent.click(screen.getByRole("button", { name: "鎖定中" })); // 解鎖,保持武裝
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 1);
    });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("SC-8:鎖定中連 3 次送單失敗 → 解除且清鎖定", async () => {
    mockCapitalFetch({
      "/api/capital/order/stock": () =>
        json({ detail: { error: "ORDER_BLOCKED", reason: "order_disabled" } }, 403),
    });
    setCapitalWsStatus("open");
    render(ladder());
    lockUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(screen.getByText("安全閘拒絕(order_disabled)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy(); // 1 次失敗仍鎖定
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    fireEvent.click(screen.getByLabelText("買 99.9"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });

  it("SC-13:capital WS 非 open 時鎖定鈕 disabled + 文案;轉 open 才可按", () => {
    mockCapitalFetch();
    render(ladder()); // beforeEach = connecting
    const lock = screen.getByRole("button", { name: "鎖定" });
    expect(lock.hasAttribute("disabled")).toBe(true);
    expect(lock.getAttribute("title")).toBe("連線未就緒,無法鎖定");
    act(() => setCapitalWsStatus("open"));
    expect(screen.getByRole("button", { name: "鎖定" }).hasAttribute("disabled")).toBe(false);
  });

  /** S3(review r1):`disabled` 只擋**進入**方向。WS 掉到 connecting 不清鎖定(既有語意,
   *  只有 closed 才 conn_lost)—— 若這時把「鎖定中」一併鎖死,使用者就處在「還在鎖定態、
   *  卻按不掉」的位置,而解鎖鈕正是縮小誤觸半徑的那個出口。 */
  it("S3:鎖定中 WS 轉 connecting → 「鎖定中」鈕不 disabled 且仍鎖定", () => {
    mockCapitalFetch();
    setCapitalWsStatus("open");
    render(ladder());
    lockUp();
    act(() => setCapitalWsStatus("connecting"));
    const locked = screen.getByRole("button", { name: "鎖定中" });
    expect(locked.hasAttribute("disabled")).toBe(false);
    expect(locked.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // connecting 不解除
  });

  /** R4:上提後 `dispatch` 的 identity 若隨 render 漂移,卸載 effect 的 cleanup 會在
   *  每次 re-render 跑一遍 —— 每收一則報價就解除一次武裝,而報價每秒都在來。
   *  ⚠ **這則不是 R4 的真鎖**(code review r1 T7):裸 render 的 PriceLadder 走本地備援
   *  `useFlashArm(true)`,identity 本來就恆定,把 `armCtl` 包一層也不會經過這裡。真鎖是
   *  `useFlashArm.test.tsx`「dispatch / touch 的 identity 跨 rerender 恆定」與「identity
   *  不因 active 改變」兩案。留著它是元件整合面的煙霧測試。 */
  it("R4:武裝後連續換報價 rerender 兩次,仍維持「解除」態", () => {
    mockCapitalFetch();
    const { rerender } = render(ladder());
    armUp();
    rerender(ladder("2330", { ...LAST, p: 100_500 }));
    rerender(ladder("2330", { ...LAST, p: 101_000 }));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
  });
});

describe("PriceLadder 交易別四顆 pill(batch2 R6 SC-1)", () => {
  it("四顆並列 pill 現股/融資/融券/無券,單選 checked 轉移;容器 role=radiogroup aria-label=交易別", () => {
    mockCapitalFetch();
    render(ladder());
    // a11y 批:role=group + aria-pressed button → radiogroup + sr-only radio(單選語意)
    const group = screen.getByRole("radiogroup", { name: "交易別" });
    const labels = ["現股", "融資", "融券", "無券"];
    const pills = labels.map(
      (l) => within(group).getByRole("radio", { name: l }) as HTMLInputElement,
    );
    const pillLabel = (r: HTMLInputElement) => r.closest("label")!;
    // DOM 次序 = TRADE_KINDS 次序(review A7:無券在最右,不與最常用的現股對調)
    expect(
      (within(group).getAllByRole("radio") as HTMLInputElement[]).map(
        (r) => pillLabel(r).textContent,
      ),
    ).toEqual(labels);
    expect(pills.map((r) => r.checked)).toEqual([true, false, false, false]);
    expect(pillLabel(pills[0]!).className).toContain("border-accent"); // 現股選中 = accent
    expect(pillLabel(pills[1]!).className).toContain("border-line");
    fireEvent.click(pills[2]!);
    expect(pills.map((r) => r.checked)).toEqual([false, false, true, false]);
    // 非現股選中 = warn 琥珀(review C1:改送單語意的單擊必須在梯面外就刺眼)
    expect(pillLabel(pills[2]!).className).toContain("border-warn");
    expect(pillLabel(pills[2]!).className).not.toContain("border-accent");
    expect(pillLabel(pills[0]!).className).toContain("border-line");
    // 舊 select 已退場
    expect(group.querySelector("select")).toBeNull();
    // 與鎖定鈕同列,pill 群 shrink-0(288px 右欄由武裝鈕吸收壓縮)
    const lock = screen.getByRole("button", { name: "鎖定" });
    expect(group.parentElement).toBe(lock.parentElement);
    expect(group.className).toContain("shrink-0");
  });

  it("點 pill 觸碰閒置計時(SC-2 後半;review A1/C7):武裝後 4 分挑交易別,再 4 分仍武裝", () => {
    mockCapitalFetch();
    vi.useFakeTimers();
    try {
      render(ladder());
      armUp();
      act(() => vi.advanceTimersByTime(ARM_IDLE_MS - 60_000));
      fireEvent.click(screen.getByRole("radio", { name: "融資" }));
      act(() => vi.advanceTimersByTime(ARM_IDLE_MS - 60_000));
      expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
      act(() => vi.advanceTimersByTime(60_001));
      expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});

// ---------------------------------------------------------------------------
// 梯頂市價鈕(SC-1 / SC-2 / SC-5 / SC-6 / SC-7 / SC-9)。恆常可見 + 位置固定 = 誤觸
// 半徑最大的一顆鈕(R-A);唯一的閘是武裝態,所以每一條守門在元件層都要有鎖。
// ---------------------------------------------------------------------------

const STOCK_MARKET_TITLE = "以市價送出:掃對手方(簿薄時可能以漲/跌停價成交);估價 = 最近成交價";

function marketBtn(side: "買" | "賣"): HTMLElement {
  return within(screen.getByTestId("ladder-market-buttons")).getByRole("button", {
    name: `市價${side}`,
  });
}

describe("PriceLadder 梯頂市價鈕", () => {
  it("SC-1:武裝列之後、scroll 容器之前恆常一列;左買右賣、外框不填色", () => {
    mockCapitalFetch();
    render(ladder());
    const row = screen.getByTestId("ladder-market-buttons");
    expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "市價買",
      "市價賣",
    ]);
    // 捲動價格梯時該列不動 → 必須在 scroll 容器**之外**且在它之前
    const scroller = screen.getByLabelText("買 100").closest(".overflow-y-auto")!;
    expect(scroller.contains(row)).toBe(false);
    expect(row.compareDocumentPosition(scroller) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(4);
    const armBtn = screen.getByRole("button", { name: "武裝" });
    expect(armBtn.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // R-A:外框樣式與武裝鈕的填色(bg-loss)區隔 —— 填了色就與「已武裝」同型
    const buy = marketBtn("買");
    const sell = marketBtn("賣");
    expect(buy.className).toContain("border-bull");
    expect(buy.className.split(" ")).not.toContain("bg-bull");
    expect(sell.className).toContain("border-bear");
    expect(sell.className.split(" ")).not.toContain("bg-bear");
    // 可用態 title(SC-8 現股版)
    expect(buy.getAttribute("title")).toBe(STOCK_MARKET_TITLE);
    expect(sell.getAttribute("title")).toBe(STOCK_MARKET_TITLE);
  });

  it("SC-2:武裝後按市價買 → market/ROD payload(price = last.p)+ hint 帶股號", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      stock_no: "2330",
      buy_sell: "buy",
      price: 100,
      qty: 1,
      price_type: "market",
      time_in_force: "ROD",
      trade_kind: "cash",
      source: "flash",
    });
    // hint 帶標的(R-H:鎖定態換標的後仍可送 → 誤送到哪一檔必須當下可見)
    await waitFor(() => expect(screen.getByText("已送 2330 市價買 × 1")).toBeTruthy());
  });

  it("SC-2 對稱:市價賣同 payload 形狀,hint 文案改「市價賣」", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("賣"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({
      buy_sell: "sell",
      price: 100,
      price_type: "market",
      time_in_force: "ROD",
    });
    await waitFor(() => expect(screen.getByText("已送 2330 市價賣 × 1")).toBeTruthy());
  });

  it("SC-5:未武裝按市價鈕 → 零請求 + hint「未武裝 — 市價不送單」3s 自清", async () => {
    vi.useFakeTimers();
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    // 未武裝時兩顆**可按**(與價格格一致,AD-8)—— disabled 的話按了沒有任何回饋
    expect(marketBtn("買").hasAttribute("disabled")).toBe(false);
    fireEvent.click(marketBtn("買"));
    expect(screen.getByText("未武裝 — 市價不送單")).toBeTruthy();
    // 排空 microtask 再斷言零請求(IMPL-8):同步幀檢查對「送出去了但還沒 resolve」
    // 與「根本沒送」是同一個答案 —— fetch mock 的呼叫本身雖同步,但守門若改成 async
    // 早退就會靜默失去鑑別力
    await act(async () => {});
    expect(bodies.length).toBe(0);
    act(() => {
      vi.advanceTimersByTime(3_000);
    });
    expect(screen.queryByText("未武裝 — 市價不送單")).toBeNull();
  });

  it("SC-6:last 缺 → 兩顆 disabled + title「無成交價,市價鈕鎖定」", () => {
    mockCapitalFetch();
    render(ladder("2330", null));
    for (const side of ["買", "賣"] as const) {
      const b = marketBtn(side);
      expect(b.hasAttribute("disabled")).toBe(true);
      expect(b.getAttribute("title")).toBe("無成交價,市價鈕鎖定");
    }
  });

  it("SC-7:無券 → 市價買 disabled(賣可用);賣側照送 market payload", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByRole("button", { name: "無券" }));
    const buy = marketBtn("買");
    expect(buy.hasAttribute("disabled")).toBe(true);
    expect(buy.getAttribute("title")).toBe("無券當沖不可買進");
    expect(marketBtn("賣").hasAttribute("disabled")).toBe(false);
    // IMPL-2 實測:React 的 onClick 依**props**(不是 DOM 屬性)擋 disabled 互動元素 ——
    // 拔掉 DOM 上的 disabled 也打不到 handler。所以這一按鎖住的是「無券時買側確實被
    // marketState 鎖住」(marketState 接線斷掉 → 鈕變可按 → 這裡會多一筆請求而紅),
    // 不是 handler 內的雙保險(那條 DOM 路徑打不到,見同檔 IMPL-2 案的註)。
    buy.removeAttribute("disabled");
    fireEvent.click(buy);
    fireEvent.click(marketBtn("賣"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({
      buy_sell: "sell",
      price_type: "market",
      trade_kind: "daytrade_sell",
    });
  });

  it("SC-9:同一顆 500ms 內連按只送一次;另一顆照送", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("買"));
    fireEvent.click(marketBtn("買"));
    fireEvent.click(marketBtn("賣"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies).toMatchObject([{ buy_sell: "buy" }, { buy_sell: "sell" }]);
  });

  /** R9:市價鈕若與點價共用單槽 `lastClick`,中間插一次點價就會把市價的槽位洗掉 ——
   *  「市價買 → 點價 → 市價買」在 500ms 內會送出**兩張市價單**,而防抖測試(連按)全綠。 */
  it("SC-9:交錯「市價買 → 點價格格 → 市價買」500ms 內,市價只送一次", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("買"));
    fireEvent.click(screen.getByLabelText("買 100"));
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies.filter((b) => b.price_type === "market").length).toBe(1);
    expect(bodies.filter((b) => b.price_type === "limit").length).toBe(1);
  });

  /** IMPL-1:換股時本元件不重掛(`code` 是 prop),防抖 ref 跟著留下 —— key 只認 side
   *  的話「A 檔按市價買 → 切到 B 檔立刻按同一顆」會被**靜默**吞掉,而畫面上還掛著 A 檔
   *  的成功 hint = 使用者以為 B 檔那張送出去了。 */
  it("IMPL-1:換股後 500ms 內按同一顆市價鈕 → 仍送出(防抖 key 併入股號)", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    const { rerender } = render(ladder("2330"));
    armUp();
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(bodies.length).toBe(1));
    rerender(ladder("2454"));
    armUp(); // 換股自動解除武裝(W2)→ 重新武裝後仍在同一個 500ms 窗內
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies[1]).toMatchObject({ stock_no: "2454", price_type: "market" });
  });

  /** IMPL-2:對 `disabled` 鈕 fireEvent.click,React 根本不派發。**實測(本輪 probe)**:
   *  連 `removeAttribute("disabled")` 都繞不過去 —— React 的 `shouldPreventMouseEvent`
   *  看的是元件 **props**,不是 DOM 屬性(拔掉屬性後 `el.disabled === false`,click 照樣
   *  不進 onClick;拔掉 handler 內守門的 mutant 仍全綠)。
   *  → handler 裡的 `if (…) return` 是給**程式面**誤接(caller 傳出與守門不一致的
   *    `MarketBtnState`)用的雙保險,DOM 路徑打不到,無法從 RTL 驗。
   *  這案改鎖真正會壞的那一環:props 轉成應鎖態後 `marketState` 必須跟著鎖 ——
   *  接線斷掉時鈕變可按,click 會真的送出一張市價單 → 紅。 */
  it("IMPL-2:武裝中 props 轉無券 → 買側鎖住,拔 DOM disabled 也點不出請求", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    // 交易別走 prop(RightRail 持有態)→ 才能用 rerender 換成應鎖態
    const view = (kind: TradeKind) => (
      <QueryClientProvider client={qc}>
        <PriceLadder
          code="2330"
          book={BOOK}
          last={LAST}
          meta={META}
          tradeKind={kind}
          onTradeKind={() => {}}
        />
      </QueryClientProvider>
    );
    const { rerender } = render(view("cash"));
    armUp();
    rerender(view("daytrade_sell"));
    const buy = marketBtn("買");
    expect(buy.hasAttribute("disabled")).toBe(true);
    buy.removeAttribute("disabled");
    fireEvent.click(buy);
    await act(async () => {});
    expect(bodies.length).toBe(0);
  });

  /** F3:市價鈕與點價共用同一套武裝守門(W2),但接線是各自寫的 —— 連敗計數沒接上時
   *  「連按 3 次全被拒卻還維持武裝」在畫面上與正常態長得一模一樣。
   *  Date.now 走可控值:同一顆的 500ms 防抖窗要跨過才送得出第 3 發。 */
  it("F3:市價鈕連 3 次被拒(403)→ 自動解除武裝", async () => {
    let now = 1_700_000_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/stock": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ detail: { error: "ORDER_BLOCKED", reason: "order_disabled" } }, 403);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("買"));
    fireEvent.click(marketBtn("賣"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 2 敗仍武裝
    now += 600; // 過同顆防抖窗
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
    expect(bodies.length).toBe(3);
  });
});
