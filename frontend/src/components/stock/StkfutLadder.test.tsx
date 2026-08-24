/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StkfutLadder } from "@/components/stock/StkfutLadder";
import { setCapitalWsStatus } from "@/hooks/useCapital";
import { ARM_IDLE_MS, LOCK_TITLE } from "@/lib/flash-arm";
import type { StkfutSelection } from "@/lib/stkfut";
import type { CapitalOrder, CapitalPosition } from "@/types";

/** 個股期閃電梯(SC-6 / R2-4):檔位幾何走**現股 tick 表**(期交所實證同級距),
 *  送單走期貨路(tc4_symbol = 月份 leaf,不是 HOT)。 */

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

const CDF_202609: StkfutSelection = { prod: "CDF", ym: "202609", mini: false, unit: 2000 };
/** futExchangeContract("CDF","202609") —— 月碼 I(9 月)+ 年末碼 6 */
const CDFI6 = "CDFI6";

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

/** orders / positions 兩條路由每個 render 都要在(未登記 URL 會讓 mock fetch throw)。 */
function mockCapitalFetch(extra: Record<string, Route> = {}) {
  return mockFetch({
    "/api/capital/orders": () => json({ orders: [] }),
    "/api/capital/positions": () => json({ positions: [] }),
    ...extra,
  });
}

function futOrder(overrides: Partial<CapitalOrder> = {}): CapitalOrder {
  return {
    seq_no: "F01",
    stock_no: CDFI6,
    name: "台積電期貨",
    market: "TF",
    buy_sell: "B",
    flag_label: null,
    book_no: "B1",
    status_raw: "0",
    status_label: "已委託",
    price: 100,
    avg_fill_price: null,
    order_qty: 2,
    filled_qty: 0,
    unit: "口",
    date: "20260806",
    time: "09:01:00",
    pre_order: false,
    error_msg: null,
    actionable: true,
    price_type: null,
    raw: "",
    ...overrides,
  };
}

/** 動態 YYYYMMDD:已成交量的日期界每 render 以 `new Date()` 算(個股期梯 = ±1 日窗,
 *  夜盤跨午夜的 date 語意未實證),fixture 寫死過去日的話徽章案取不到 filled(spec A6)。 */
function ymd(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${d.getFullYear()}${m}${String(d.getDate()).padStart(2, "0")}`;
}

function futPos(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "fut",
    stock_no: CDFI6,
    qty: 2,
    name: "台積電期貨",
    avg_price: 100,
    kind: "cash",
    pnl_base: 800,
    pnl_base_price: null,
    pnl_cost: null,
    code: null,
    ...overrides,
  };
}

const OK_RESULT = { ok: true, code: 0, message: "ok", seq_no: "F01" };

let qc: QueryClient;

function ladder(contract: StkfutSelection = CDF_202609, code = "2330") {
  return (
    <QueryClientProvider client={qc}>
      <StkfutLadder
        code={code}
        name="台積電"
        contract={contract}
        book={BOOK}
        last={LAST}
        meta={META}
      />
    </QueryClientProvider>
  );
}

function armUp(): void {
  fireEvent.click(screen.getByRole("button", { name: "武裝" }));
}

beforeEach(() => {
  window.localStorage.clear();
  // N081 起武裝鈕也吃 wsStatus(非 open 不得**進入**武裝)→ 預設改 "open",
  // 否則整批「武裝後…」的既有案會被閘擋在門外。要驗連線閘的案自己設 "connecting"。
  setCapitalWsStatus("open"); // wsStatus module store 跨測試重置
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

describe("StkfutLadder 檔位幾何與版面(R2-4)", () => {
  it("檔位走現股 tick 表:100 上一檔是 100.5(不是期貨的 1 點)", () => {
    mockCapitalFetch();
    render(ladder());
    expect(screen.getByLabelText("買 100").textContent).toBe("30");
    expect(screen.getByLabelText("賣 100.5").textContent).toBe("10");
    expect(screen.getByText("110")).toBeTruthy(); // 漲停端點仍在梯上
  });

  it("標題列可指認股號 + 股名 + 合約(誤送防線)", () => {
    mockCapitalFetch();
    render(ladder());
    expect(screen.getByText("2330")).toBeTruthy();
    expect(screen.getByText("台積電 CDF 2026/09")).toBeTruthy();
  });

  it("交易別列隱藏、數量標籤是「口數」(現股語彙不得出現在期貨面)", () => {
    mockCapitalFetch();
    render(ladder());
    expect(screen.queryByLabelText("交易別")).toBeNull();
    expect(screen.queryByLabelText("張數")).toBeNull();
    expect(screen.getByLabelText("口數")).toBeTruthy();
    expect(screen.getByLabelText("當沖")).toBeTruthy();
  });
});

describe("StkfutLadder 武裝直送(R2-4)", () => {
  it("payload 帶月份 leaf symbol + day_trade 預設 false + 口數", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(bodies.length).toBe(1));
    // HOT 會被 TC4 解析成熱門月 —— 使用者選的是哪個月就必須送哪個月
    expect(bodies[0]).toEqual({
      tc4_symbol: "TC.F.TWF.CDF.202609",
      buy_sell: "buy",
      price: 100,
      qty: 1,
      price_type: "limit",
      time_in_force: "ROD",
      day_trade: false,
      source: "flash",
    });
  });

  it("當沖 checkbox 開啟 → payload day_trade: true", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    const dayTrade = screen.getByLabelText("當沖") as HTMLInputElement;
    expect(dayTrade.checked).toBe(false);
    fireEvent.click(dayTrade);
    armUp();
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ buy_sell: "sell", day_trade: true });
  });

  it("未武裝點價:零請求 + hint「未武裝 — 點價不送單」", () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    fireEvent.click(screen.getByLabelText("買 100"));
    expect(screen.getByText("未武裝 — 點價不送單")).toBeTruthy();
    expect(bodies.length).toBe(0);
  });

  it("送單 400 BAD_TICK → hint 顯示繁中文案(不是原始錯誤碼)", async () => {
    mockCapitalFetch({
      "/api/capital/order/future": () => json({ detail: { error: "BAD_TICK" } }, 400),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(screen.getByText("價格非合法檔位")).toBeTruthy());
  });

  it("capital wsStatus 轉 closed 自動解除武裝(conn_lost)", () => {
    mockCapitalFetch();
    render(ladder());
    armUp();
    act(() => setCapitalWsStatus("open"));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    act(() => setCapitalWsStatus("closed"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });
});

// R2-5:現貨↔合約、合約↔合約切換時**同一個元件實例不 unmount**,`code` 又恆是股號
// → 武裝解除若掛 code 就永遠不觸發,武裝會跨標的殘留 = 繞過確認直送真單。
describe("StkfutLadder 武裝解除鍵 = instrumentKey(R2-5)", () => {
  it("換合約月份(股號不變)→ 武裝自動解除", () => {
    mockCapitalFetch();
    const { rerender } = render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" }).getAttribute("aria-pressed")).toBe("true");
    rerender(ladder({ prod: "CDF", ym: "202610", mini: false, unit: 2000 }));
    expect(screen.getByRole("button", { name: "武裝" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("換產品腿(標準 → 小型,股號不變)→ 武裝自動解除", () => {
    mockCapitalFetch();
    const { rerender } = render(ladder());
    armUp();
    rerender(ladder({ prod: "QFF", ym: "202609", mini: true, unit: 100 }));
    expect(screen.getByRole("button", { name: "武裝" }).getAttribute("aria-pressed")).toBe("false");
  });
});

describe("StkfutLadder 掛單紅方格(R2-4)", () => {
  it("本合約活單聚合口數;他契約不顯示;點擊逐 seq 直刪(market=fut)", async () => {
    const cancelBodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            futOrder({ seq_no: "F01", price: 100, order_qty: 2, filled_qty: 0 }),
            futOrder({ seq_no: "F02", price: 100, order_qty: 3, filled_qty: 1 }),
            futOrder({ seq_no: "F03", buy_sell: "S", price: 100.5, order_qty: 1 }),
            futOrder({ seq_no: "F04", stock_no: "CDFJ6", price: 100 }), // 他月份
            futOrder({ seq_no: "F05", stock_no: "2330", price: 100 }), // 現股單
          ],
        }),
    });
    render(ladder());
    const buyLot = await screen.findByLabelText("刪 100 買單");
    expect(buyLot.textContent).toBe("4(1)"); // 未成交 2 + (3-1) / 已成交 1;他契約與現股單不計入
    expect(screen.getByLabelText("刪 100.5 賣單").textContent).toBe("1(0)");
    fireEvent.click(buyLot);
    await waitFor(() => expect(cancelBodies.length).toBe(2));
    expect(cancelBodies).toMatchObject([
      { seq_no: "F01", market: "fut" },
      { seq_no: "F02", market: "fut" },
    ]);
  });
});

describe("StkfutLadder 已成交徽章(SC-3)", () => {
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
            futOrder({
              seq_no: "F10",
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
    expect(screen.queryByLabelText("刪 100 買單")).toBeNull();
    fireEvent.click(badge);
    await act(async () => {
      await Promise.resolve();
    });
    expect(cancelBodies.length).toBe(0);
  });

  /** 個股期梯是 ±1 日窗(現股梯嚴格今日):夜盤的 date 語意未實證,兩種假設都要涵蓋 */
  function renderFilledOn(date: string) {
    mockCapitalFetch({
      "/api/capital/orders": () =>
        json({
          orders: [
            // 同步錨:orders query 未回時整梯也空 —— 沒有這筆對照單,「查無徽章」恆綠
            futOrder({ seq_no: "F99", buy_sell: "S", price: 100.5, order_qty: 1 }),
            futOrder({
              seq_no: "F11",
              price: 100,
              order_qty: 2,
              filled_qty: 2,
              actionable: false,
              status_label: "全部成交",
              date,
            }),
          ],
        }),
    });
    return render(ladder());
  }

  it("日期界 ±1 日窗:昨日的終態單仍計入(夜盤跨午夜)", async () => {
    renderFilledOn(ymd(-1));
    expect((await screen.findByTestId("ladder-filled-lot")).textContent).toBe("(2)");
  });

  it("日期界外(前 5 日)的終態單 → 無徽章", async () => {
    renderFilledOn(ymd(-5));
    await screen.findByLabelText("刪 100.5 賣單");
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
  });
});

describe("StkfutLadder 部位條(R2-4)", () => {
  it("只收本合約的期貨部位;口數單位;損益走群益名目值(不套現股稅費)", async () => {
    mockCapitalFetch({
      "/api/capital/positions": () =>
        json({
          positions: [
            futPos(),
            futPos({ stock_no: "CDFJ6", qty: -1 }), // 他月份
            futPos({ market: "sec", stock_no: "2330" }), // 現股
          ],
        }),
    });
    render(ladder());
    const bar = await screen.findByTestId("stkfut-position-bar");
    const rows = within(bar).getAllByTestId("stkfut-position-row");
    expect(rows.length).toBe(1);
    // 🔴 N064:均價字面與 header / 自選 chip 同走 `fmt`(整數不帶小數)—— 舊值 `100.00`
    // 是 `toFixed(2)` 的第二套口徑,同一個數字在同一畫面上長兩個樣子。
    // 逐字比對第一顆 span(`toContain` 對 `@100.00` 也成立 —— 鑑別力為零)
    expect(rows[0]!.firstElementChild!.textContent).toBe("多 2 口 @100");
    expect(rows[0]!.textContent).toContain("+800");
    // 現股口徑的「打平(含稅費)」不適用期貨 —— 出現就是抄錯口徑
    expect(bar.textContent).not.toContain("打平");
  });

  /** 🔴 N064:非整數均價仍印兩位以內、去尾隨 0(`fmt` 口徑)。整數案單獨不夠 ——
   *  `toFixed(2)` 對 100.5 給 `100.50`,兩者只在整數案才有差、只鎖整數會漏掉半邊。 */
  it("非整數均價走 fmt 口徑(100.5 → 100.5,不是 100.50)", async () => {
    mockCapitalFetch({
      "/api/capital/positions": () => json({ positions: [futPos({ avg_price: 100.5 })] }),
    });
    render(ladder());
    const bar = await screen.findByTestId("stkfut-position-bar");
    expect(bar.textContent).toContain("@100.5");
    expect(bar.textContent).not.toContain("@100.50");
  });

  it("無本合約部位 → 部位條整段不渲染", async () => {
    mockCapitalFetch({
      "/api/capital/positions": () => json({ positions: [futPos({ stock_no: "CDFJ6" })] }),
    });
    render(ladder());
    await screen.findByLabelText("買 100");
    expect(screen.queryByTestId("stkfut-position-bar")).toBeNull();
  });
});

// 非標準契約單位(ETF 10,000 受益權單位 / 除權息調整契約 2,157)後端 `_stkfut_gates`
// 一律回 PRODUCT_NOT_ALLOWED。前端先擋是為了不讓使用者在真錢面板上按下一個必被拒的鍵。
// 🔴 code review B3:判準由「股號 0 開頭」改吃契約單位 —— 與後端同一個判準。
describe("StkfutLadder 非標準契約單位不開放下單(SC-6)", () => {
  function blockedBodies() {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    return bodies;
  }

  it("ETF 契約(unit 10000)→ 武裝鈕 disabled + 文案;點價零請求", () => {
    const bodies = blockedBodies();
    render(ladder({ prod: "NYF", ym: "202609", mini: false, unit: 10000 }, "0050"));
    const armBtn = screen.getByRole("button", { name: "武裝" });
    expect(armBtn.hasAttribute("disabled")).toBe(true);
    expect(armBtn.getAttribute("title")).toBe("此契約規格暫未開放下單");
    fireEvent.click(armBtn);
    fireEvent.click(screen.getByLabelText("買 100"));
    expect(bodies.length).toBe(0);
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(true);
  });

  // 舊的股號判準對這一檔是「放行」—— 使用者按下去只會收到一句莫名的「委託失敗」
  it("除權息調整契約(股號非 0 開頭、unit 2157)→ 一樣擋", () => {
    const bodies = blockedBodies();
    render(ladder({ prod: "EEF", ym: "202609", mini: false, unit: 2157 }, "1312"));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByLabelText("買 100"));
    expect(bodies.length).toBe(0);
  });

  it("單位不可得(後端查無對映)→ 落回股號 fallback", () => {
    mockCapitalFetch();
    const { unmount } = render(ladder({ prod: "NYF", ym: "202609", mini: false, unit: null }, "0050"));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(true);
    unmount();
    cleanup();
    mockCapitalFetch();
    render(ladder({ prod: "CDF", ym: "202609", mini: false, unit: null }));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(false);
  });

  it("標準 / 小型契約單位 → 武裝鈕可用(閘不誤傷)", () => {
    mockCapitalFetch();
    const { unmount } = render(ladder());
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByLabelText("買 100").hasAttribute("disabled")).toBe(false);
    unmount();
    cleanup();
    mockCapitalFetch();
    render(ladder({ prod: "QFF", ym: "202609", mini: true, unit: 100 }));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(false);
  });
});

// 個股期梯的武裝防護原本只鎖了 conn_lost 與換合約兩條 —— Esc / idle / 連 3 敗三條在
// 現股梯與期貨梯都有測、這裡沒有(current-state §1)。鎖定會讓武裝活得更久,先把
// 這三條在本梯補齊,再加鎖定本身的案例。
describe("StkfutLadder 武裝防護補齊(Esc / idle / 連 3 敗)", () => {
  it("Esc 鍵解除武裝", () => {
    mockCapitalFetch();
    render(ladder());
    armUp();
    fireEvent.keyDown(window, { key: "Escape" });
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

  it("連 3 次送單失敗自動解除", async () => {
    mockCapitalFetch({
      "/api/capital/order/future": () => json({ detail: { error: "BAD_TICK" } }, 400),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(screen.getByText("價格非合法檔位")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 1 次失敗仍武裝
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    fireEvent.click(screen.getByLabelText("買 99.9"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
  });
});

describe("StkfutLadder 鎖定武裝(SC-1 / SC-12a)", () => {
  it("SC-1:按鎖定 → 武裝 +「鎖定中」", () => {
    mockCapitalFetch();
    setCapitalWsStatus("open");
    render(ladder());
    const lock = screen.getByRole("button", { name: "鎖定" });
    expect(lock.getAttribute("title")).toBe(LOCK_TITLE); // 常態 tooltip(兩處渲染點同源)
    fireEvent.click(lock);
    expect(screen.getByRole("button", { name: "解除" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "鎖定中" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("鎖定後換合約月份 → 仍武裝(未鎖定時的自動解除是對照組)", () => {
    mockCapitalFetch();
    setCapitalWsStatus("open");
    const { rerender } = render(ladder());
    fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
    rerender(ladder({ prod: "CDF", ym: "202610", mini: false, unit: 2000 }));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
  });

  it("SC-12(a):未武裝 + blocked 契約 → 武裝鈕與鎖定鈕同 disabled", () => {
    mockCapitalFetch();
    setCapitalWsStatus("open");
    render(ladder({ prod: "NYF", ym: "202609", mini: false, unit: 10000 }, "0050"));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "鎖定" }).hasAttribute("disabled")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 梯頂市價鈕(SC-1 / SC-3 / SC-5 / SC-6 / SC-7 / SC-8)。個股期的「市價」= 限價貼漲跌停
// + IOC(D3a):後端 fut market 映射是 "M" literal(OrderPanel 在用),不能借道。
// ---------------------------------------------------------------------------

const EDGE_MARKET_TITLE =
  "市價 = 限價貼漲/跌停 + IOC:掃對手方至成交完(簿薄時可能以漲/跌停價成交),餘量取消";

function marketBtn(side: "買" | "賣"): HTMLElement {
  return within(screen.getByTestId("ladder-market-buttons")).getByRole("button", {
    name: `市價${side}`,
  });
}

describe("StkfutLadder 梯頂市價鈕", () => {
  it("SC-1 / SC-8:兩顆鈕在 scroll 容器之前;可用態 title = 貼漲跌停 + IOC 文案", () => {
    mockCapitalFetch();
    render(ladder());
    const row = screen.getByTestId("ladder-market-buttons");
    expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "市價買",
      "市價賣",
    ]);
    const scroller = screen.getByLabelText("買 100").closest(".overflow-y-auto")!;
    expect(scroller.contains(row)).toBe(false);
    expect(row.compareDocumentPosition(scroller) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(4);
    expect(marketBtn("買").getAttribute("title")).toBe(EDGE_MARKET_TITLE);
    expect(marketBtn("賣").getAttribute("title")).toBe(EDGE_MARKET_TITLE);
  });

  it("SC-3:武裝後按市價賣 → limit/IOC + price = snapUp(跌停);hint 帶契約碼", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    render(ladder());
    fireEvent.click(screen.getByLabelText("當沖"));
    armUp();
    fireEvent.click(marketBtn("賣"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      tc4_symbol: "TC.F.TWF.CDF.202609",
      buy_sell: "sell",
      price: 90, // snapUp(90_000) / 1000 —— 跌停已在合法檔位
      qty: 1,
      price_type: "limit",
      time_in_force: "IOC",
      day_trade: true,
      source: "flash",
    });
    await waitFor(() => expect(screen.getByText("已送 CDFI6 市價賣 × 1 口")).toBeTruthy());
  });

  it("SC-3:市價買 → price = snapDown(漲停)", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({
      buy_sell: "buy",
      price: 110,
      price_type: "limit",
      time_in_force: "IOC",
    });
    await waitFor(() => expect(screen.getByText("已送 CDFI6 市價買 × 1 口")).toBeTruthy());
  });

  it("SC-5:未武裝 → 零請求 + hint「未武裝 — 市價不送單」", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder());
    fireEvent.click(marketBtn("賣"));
    expect(screen.getByText("未武裝 — 市價不送單")).toBeTruthy();
    await act(async () => {}); // 排空 microtask 再斷言零請求(IMPL-8)
    expect(bodies.length).toBe(0);
  });

  it("SC-6:漲停缺(meta.upper null)→ 兩顆 disabled + 鎖定文案(不用假想界)", () => {
    mockCapitalFetch();
    render(
      <QueryClientProvider client={qc}>
        <StkfutLadder
          code="2330"
          name="台積電"
          contract={CDF_202609}
          book={BOOK}
          last={LAST}
          meta={{ ...META, upper: null }}
        />
      </QueryClientProvider>,
    );
    for (const side of ["買", "賣"] as const) {
      const b = marketBtn(side);
      expect(b.hasAttribute("disabled")).toBe(true);
      expect(b.getAttribute("title")).toBe("無成交價,市價鈕鎖定");
    }
  });

  it("SC-7:blocked 契約 → 兩顆 disabled + title 同前置閘文案;點擊零請求", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    render(ladder({ prod: "NYF", ym: "202609", mini: false, unit: 10000 }, "0050"));
    for (const side of ["買", "賣"] as const) {
      const b = marketBtn(side);
      expect(b.hasAttribute("disabled")).toBe(true);
      expect(b.getAttribute("title")).toBe("此契約規格暫未開放下單");
      // IMPL-2 實測:React 依 **props** 擋 disabled 元素的 onClick,拔掉 DOM 屬性也
      // 打不到 handler → 這一按鎖的是「blocked 契約確實被 marketState 鎖住」
      // (接線斷掉 → 鈕可按 → 這裡會冒出請求而紅),不是 handler 內的雙保險。
      b.removeAttribute("disabled");
      fireEvent.click(b);
    }
    await act(async () => {}); // 排空 microtask 再斷言零請求(IMPL-8)
    expect(bodies.length).toBe(0);
  });

  /** IMPL-2:render 可用態 → rerender 成應鎖態(漲停從有值變缺,武裝不受影響)。
   *  React 的 disabled 攔截看 props 不看 DOM 屬性(見 PriceLadder 同案註),所以這案
   *  鎖的是「行情轉成缺界後 marketState 必須立刻跟著鎖」—— 沒跟上就會拿假想界送真單。 */
  it("IMPL-2:武裝中漲停轉缺 → 兩顆立刻鎖,拔 DOM disabled 也點不出請求", async () => {
    const bodies: unknown[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    const view = (upper: number | null) => (
      <QueryClientProvider client={qc}>
        <StkfutLadder
          code="2330"
          name="台積電"
          contract={CDF_202609}
          book={BOOK}
          last={LAST}
          meta={{ ...META, upper }}
        />
      </QueryClientProvider>
    );
    const { rerender } = render(view(110_000));
    armUp();
    expect(marketBtn("買").hasAttribute("disabled")).toBe(false);
    rerender(view(null));
    for (const side of ["買", "賣"] as const) {
      const b = marketBtn(side);
      expect(b.hasAttribute("disabled")).toBe(true);
      b.removeAttribute("disabled");
      fireEvent.click(b);
    }
    await act(async () => {});
    expect(bodies.length).toBe(0);
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 仍武裝(鎖的是鈕不是武裝)
  });

  /** F2:防抖在現股梯有測、個股期沒有 —— 三梯各寫一份 marketOrder,漏一梯就是
   *  「同一顆連按兩下送出兩口」而沒有任何測試會紅。 */
  it("F2:同一顆 500ms 內連按只送一次;另一顆照送", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
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

  it("F2:交錯「市價買 → 點價格格 → 市價買」500ms 內,市價只送一次", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
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
    expect(bodies.filter((b) => b.time_in_force === "IOC").length).toBe(1); // 市價鈕
    expect(bodies.filter((b) => b.time_in_force === "ROD").length).toBe(1); // 點價
  });

  /** F4:估價缺的兩條分支各有各的鎖法 —— `last` 缺(無成交價)與界缺(SC-6)不同源。 */
  it("F4:last 缺 → 兩顆 disabled;rows 為空(界與成交價全缺)仍渲染鈕列", () => {
    mockCapitalFetch();
    const { rerender } = render(
      <QueryClientProvider client={qc}>
        <StkfutLadder
          code="2330"
          name="台積電"
          contract={CDF_202609}
          book={BOOK}
          last={null}
          meta={META}
        />
      </QueryClientProvider>,
    );
    for (const side of ["買", "賣"] as const) {
      expect(marketBtn(side).hasAttribute("disabled")).toBe(true);
    }
    // 「無資料」態:鈕列照樣在(鈕自身由估價鎖,無資料不是「不該有鈕」)
    rerender(
      <QueryClientProvider client={qc}>
        <StkfutLadder
          code="2330"
          name="台積電"
          contract={CDF_202609}
          book={null}
          last={null}
          meta={null}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText("無資料")).toBeTruthy();
    expect(screen.getByTestId("ladder-market-buttons")).toBeTruthy();
    expect(marketBtn("買").hasAttribute("disabled")).toBe(true);
  });
});

// 🔴 N081 + 🔴 N082(個股期梯)。
describe("StkfutLadder 武裝閘與稽核 source(N081 / N082)", () => {
  it("N081:WS 非 open 時武裝鈕 disabled + 文案", () => {
    mockCapitalFetch();
    setCapitalWsStatus("connecting");
    render(ladder());
    const arm = screen.getByRole("button", { name: "武裝" });
    expect(arm.hasAttribute("disabled")).toBe(true);
    expect(arm.getAttribute("title")).toBe("連線未就緒,無法武裝");
    act(() => setCapitalWsStatus("open"));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(false);
  });

  it("N081:blocked 契約的文案優先於連線文案(前置閘先講不能下單這件事)", () => {
    mockCapitalFetch();
    setCapitalWsStatus("connecting");
    render(ladder({ prod: "NYF", ym: "202609", mini: false, unit: 10_000 }, "0050"));
    expect(screen.getByRole("button", { name: "武裝" }).getAttribute("title")).toBe(
      "此契約規格暫未開放下單",
    );
  });

  it("N082:鎖定態點價 → source=flash-locked;未鎖定 → flash", async () => {
    const bodies: { source?: string }[] = [];
    mockCapitalFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
    });
    setCapitalWsStatus("open");
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 100"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]?.source).toBe("flash");

    fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
    fireEvent.click(screen.getByLabelText("賣 100.5"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies[1]?.source).toBe("flash-locked");
  });
});
