/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FuturesLadder } from "@/components/futures/FuturesLadder";
import { setCapitalWsStatus } from "@/hooks/useCapital";
import { ARM_IDLE_MS, LOCK_TITLE } from "@/lib/flash-arm";
import type { CapitalOrder, CapitalPosition, FuturesProductState } from "@/types";

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
};

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

function futOrder(overrides: Partial<CapitalOrder> = {}): CapitalOrder {
  return {
    seq_no: "F01",
    stock_no: "TXFI6",
    name: "臺股期貨",
    market: "TF",
    buy_sell: "B",
    flag_label: null,
    book_no: "B1",
    status_raw: "0",
    status_label: "已委託",
    price: 23_000,
    avg_fill_price: null,
    order_qty: 2,
    filled_qty: 0,
    unit: "口",
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

/** 動態 YYYYMMDD:已成交量的日期界每 render 以 `new Date()` 算(期貨梯 = ±1 日窗),
 *  fixture 寫死過去日的話徽章案取不到 filled(spec A6)。 */
function ymd(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${d.getFullYear()}${m}${String(d.getDate()).padStart(2, "0")}`;
}

function futPos(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "fut",
    stock_no: "TXFI6",
    qty: -2,
    name: "臺股期貨",
    avg_price: 23_200,
    kind: "cash",
    pnl_base: -800,
    pnl_base_price: 23_000,
    pnl_cost: null,
    code: null,
    ...overrides,
  };
}

const OK_RESULT = { ok: true, code: 0, message: "ok", seq_no: "F01" };

let qc: QueryClient;

function ladder(state: FuturesProductState | null = TXF_STATE, product = "TXF") {
  return (
    <QueryClientProvider client={qc}>
      <FuturesLadder product={product} state={state} />
    </QueryClientProvider>
  );
}

function armUp(): void {
  fireEvent.click(screen.getByRole("button", { name: "武裝" }));
}

beforeEach(() => {
  window.localStorage.clear();
  setCapitalWsStatus("connecting"); // wsStatus module store 跨測試重置
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

describe("FuturesLadder 武裝直送(SC-8)", () => {
  it("武裝點價:1 次 API call;payload 帶 HOT symbol + day_trade 預設 false", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      tc4_symbol: "TC.F.TWF.TXF.HOT",
      buy_sell: "buy",
      price: 22_999,
      qty: 1,
      price_type: "limit",
      time_in_force: "ROD",
      day_trade: false,
      source: "flash",
    });
  });

  it("當沖 checkbox 開啟 → payload day_trade: true", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    const dayTrade = screen.getByLabelText("當沖") as HTMLInputElement;
    expect(dayTrade.checked).toBe(false); // 預設關
    fireEvent.click(dayTrade);
    armUp();
    fireEvent.click(screen.getByLabelText("賣 23001"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ buy_sell: "sell", day_trade: true });
  });

  it("未武裝點價:零請求 + hint「未武裝 — 點價不送單」", () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    fireEvent.click(screen.getByLabelText("買 22999"));
    expect(screen.getByText("未武裝 — 點價不送單")).toBeTruthy();
    expect(bodies.length).toBe(0);
  });

  it("resolved_contract null → 武裝鈕 disabled(title 合約未解析)且點價零請求", () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder({ ...TXF_STATE, resolved_contract: null }));
    const armBtn = screen.getByRole("button", { name: "武裝" });
    expect(armBtn.hasAttribute("disabled")).toBe(true);
    expect(armBtn.getAttribute("title")).toBe("合約未解析");
    fireEvent.click(armBtn);
    fireEvent.click(screen.getByLabelText("買 22999"));
    expect(bodies.length).toBe(0);
  });

  it("同格 500ms 防抖:連點同格 1 call;不同格照送", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    fireEvent.click(screen.getByLabelText("買 22999"));
    fireEvent.click(screen.getByLabelText("賣 23001"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies).toMatchObject([{ buy_sell: "buy" }, { buy_sell: "sell" }]);
  });

  it("product 變更自動解除武裝(symbol_changed)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    const { rerender } = render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    rerender(ladder(MXF_STATE, "MXF"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("capital wsStatus 轉 closed 自動解除(conn_lost;wsStatus store 注入)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    armUp();
    act(() => setCapitalWsStatus("open"));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    act(() => setCapitalWsStatus("closed"));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });
});

describe("FuturesLadder 武裝防護(review C3/C4)", () => {
  it("idle 5 分鐘自動解除", () => {
    vi.useFakeTimers();
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    render(ladder());
    armUp();
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(ARM_IDLE_MS + 1);
    });
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
  });

  it("送單 400:hint 顯示 tradeErrorText 文案;連 3 次失敗自動解除", async () => {
    mockFetch({
      "/api/capital/order/future": () =>
        json({ detail: { error: "BROKER_REJECTED", err_code: "1097", err_msg: "廢單" } }, 400),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(screen.getByText("券商拒單(1097)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 1 次失敗仍武裝
    fireEvent.click(screen.getByLabelText("賣 23001"));
    fireEvent.click(screen.getByLabelText("買 23000"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
  });

  it("200 但 ok:false(結果未知 code=-1)→ hint 顯示 message 且 failStreak 累積", async () => {
    mockFetch({
      "/api/capital/order/future": () =>
        json({ ok: false, code: -1, message: "結果未知(逾時)", seq_no: null }),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(screen.getByText("結果未知(逾時)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 1 次失敗仍武裝
    fireEvent.click(screen.getByLabelText("賣 23001"));
    fireEvent.click(screen.getByLabelText("買 23000"));
    await waitFor(() => expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy());
  });

  it("qty 快捷「3」按兩下累加 → payload qty 6(review C4)", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    render(ladder());
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    fireEvent.click(screen.getByRole("button", { name: "3" }));
    expect((screen.getByLabelText("口數") as HTMLInputElement).value).toBe("6");
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ qty: 6 });
  });
});

describe("FuturesLadder 鎖定武裝(SC-1 / SC-12a)", () => {
  it("SC-1:按鎖定 → 武裝 +「鎖定中」(期貨梯與現股梯共用 components/ladder/ArmRow)", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    setCapitalWsStatus("open");
    render(ladder());
    const lock = screen.getByRole("button", { name: "鎖定" });
    expect(lock.parentElement).toBe(screen.getByRole("button", { name: "武裝" }).parentElement);
    expect(lock.getAttribute("title")).toBe(LOCK_TITLE); // 常態 tooltip(兩處渲染點同源)
    fireEvent.click(lock);
    expect(screen.getByRole("button", { name: "解除" }).getAttribute("aria-pressed")).toBe("true");
    const locked = screen.getByRole("button", { name: "鎖定中" });
    expect(locked.getAttribute("aria-pressed")).toBe("true");
    expect(locked.className).toContain("bg-accent");
  });

  it("鎖定後換 product → 仍武裝(未鎖定時的 symbol_changed 解除是對照組)", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    setCapitalWsStatus("open");
    const { rerender } = render(ladder());
    fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
    rerender(ladder(MXF_STATE, "MXF"));
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定中" })).toBeTruthy();
  });

  it("SC-12(a):resolved_contract null(未武裝)→ 武裝鈕與鎖定鈕同 disabled", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    setCapitalWsStatus("open");
    render(ladder({ ...TXF_STATE, resolved_contract: null }));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "鎖定" }).hasAttribute("disabled")).toBe(true);
  });

  /** E-3:安全優先 —— 鎖定中合約失解析仍 disarm 並清鎖定(合約一解析要重新武裝) */
  it("鎖定中 resolved_contract 轉 null → 解除且清鎖定", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    setCapitalWsStatus("open");
    const { rerender } = render(ladder());
    fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
    rerender(ladder({ ...TXF_STATE, resolved_contract: null }));
    expect(screen.getByRole("button", { name: "武裝" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "鎖定" })).toBeTruthy();
  });
});

describe("FuturesLadder 掛單紅方格(SC-8)", () => {
  it("本契約活單聚合口數;他契約不顯示;點擊逐 seq 直刪(market=fut)", async () => {
    const cancelBodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            futOrder({ seq_no: "F01", price: 23_000, order_qty: 2, filled_qty: 0 }),
            futOrder({ seq_no: "F02", price: 23_000, order_qty: 3, filled_qty: 1 }),
            futOrder({ seq_no: "F03", stock_no: "MXFI6", price: 23_001 }),
          ],
        }),
    });
    render(ladder());
    const lot = await screen.findByLabelText("刪 23000 掛單");
    expect(lot.textContent).toBe("4(1)"); // 未成交 2 + (3-1) / 已成交 1
    expect(screen.queryByLabelText("刪 23001 掛單")).toBeNull(); // 他契約
    fireEvent.click(lot);
    await waitFor(() => expect(cancelBodies.length).toBe(2));
    expect(cancelBodies).toMatchObject([
      { seq_no: "F01", market: "fut" },
      { seq_no: "F02", market: "fut" },
    ]);
  });

  /** 全成交後無 seq 可刪:徽章不可點,且**全撤鈕必須維持 disabled**
   *  —— allSeqNos 只含活單 seq(R4)。 */
  it("本契約僅剩全成交 → `(N)` 徽章不可點、全撤鈕 disabled", async () => {
    const cancelBodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            futOrder({
              seq_no: "F09",
              price: 23_000,
              order_qty: 2,
              filled_qty: 2,
              actionable: false,
              status_label: "全部成交",
              date: ymd(),
            }),
          ],
        }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    const badge = await screen.findByTestId("ladder-filled-lot");
    expect(badge.textContent).toBe("(2)");
    expect(badge.tagName).toBe("SPAN");
    // T5:span 不吃點擊靠 className,`fireEvent.click` 在 jsdom 不模擬 pointer-events
    // → 上面的「不送 cancel」斷言對「忘了加 pointer-events-none」是恆綠的
    expect(badge.className).toContain("pointer-events-none");
    expect(screen.queryByLabelText("刪 23000 掛單")).toBeNull();
    fireEvent.click(badge);
    await act(async () => {
      await Promise.resolve();
    });
    expect(cancelBodies.length).toBe(0);
    // R8:徽章佔位讓點價鈕變窄是明文承認的偏差,「同列點價鈕仍可點」才是驗收線
    expect(screen.getByLabelText("買 23000").hasAttribute("disabled")).toBe(false);
    const cancelAll = screen.getByRole("button", { name: "全撤" });
    expect(cancelAll.hasAttribute("disabled")).toBe(true);
    expect(cancelAll.getAttribute("title")).toBe("無本契約活單");
  });

  /** T2:`r.myQty > 0 || r.mySeqNos.length > 0` 的後半條無鎖 —— 拿掉它時
   *  actionable 殘 0 的活單會落進 `r.myFilled > 0` 徽章分支,而 filled 也是 0
   *  → **整格消失**,刪單入口與可見痕跡一起沒了。 */
  it("actionable 殘 0 活單 → 紅方格 `0(0)` 可點、全撤鈕非 disabled", async () => {
    const cancelBodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [futOrder({ seq_no: "F12", price: 23_000, order_qty: 0, filled_qty: 0 })],
        }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    const lot = await screen.findByLabelText("刪 23000 掛單");
    expect(lot.textContent).toBe("0(0)");
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
    fireEvent.click(lot);
    await waitFor(() => expect(cancelBodies.length).toBe(1));
    expect(cancelBodies).toMatchObject([{ seq_no: "F12", market: "fut" }]);
    // allSeqNos 收得到這筆 → 全撤鈕必須是活的(徽章案的 disabled 是對照組)
    expect(screen.getByRole("button", { name: "全撤" }).hasAttribute("disabled")).toBe(false);
  });

  /** T6:期貨梯的日期界是 ±1 日窗(A3;夜盤跨午夜語意未實證,兩種假設皆涵蓋)。
   *  lib 層有 `ymdWindow` 的純函式測,但「container 真的把 ±1 窗接進去」沒有鎖 ——
   *  接成嚴格今日或整個不傳,lib 測照樣全綠。 */
  it("終態單 date=昨日 → 徽章仍在(±1 日窗);date=5 日前 → 無徽章", async () => {
    const orders = (date: string) => [
      futOrder({ seq_no: "F20", price: 22_999, order_qty: 1, filled_qty: 0 }), // 同步錨:活單
      futOrder({
        seq_no: "F21",
        price: 23_000,
        order_qty: 2,
        filled_qty: 2,
        actionable: false,
        status_label: "全部成交",
        date,
      }),
    ];
    mockFetch({
      "/api/capital/orders": () => json({ orders: orders(ymd(-1)) }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    await screen.findByLabelText("刪 22999 掛單");
    expect(screen.getByTestId("ladder-filled-lot").textContent).toBe("(2)");
    cleanup();
    vi.restoreAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    mockFetch({
      "/api/capital/orders": () => json({ orders: orders(ymd(-5)) }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    await screen.findByLabelText("刪 22999 掛單"); // 同步錨:資料確實到了
    expect(screen.queryByTestId("ladder-filled-lot")).toBeNull();
  });
});

describe("FuturesLadder 全撤(SC-10)", () => {
  it("無本契約活單 → 全撤鈕 disabled", async () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [futOrder({ stock_no: "MXFI6" })] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    await screen.findByLabelText("買 22999");
    const btn = screen.getByRole("button", { name: "全撤" });
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("全撤:所有價位的 seq 逐筆送 cancel(market=fut,無彈窗)", async () => {
    const cancelBodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/cancel": (init) => {
        cancelBodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () =>
        json({
          orders: [
            futOrder({ seq_no: "F01", price: 23_000, order_qty: 2, filled_qty: 0 }),
            futOrder({ seq_no: "F02", price: 23_000, order_qty: 3, filled_qty: 1 }),
            futOrder({ seq_no: "F03", price: 22_999, order_qty: 1, filled_qty: 0 }),
            futOrder({ seq_no: "F04", stock_no: "MXFI6", price: 22_998 }), // 他契約不撤
          ],
        }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    const btn = await screen.findByRole("button", { name: "全撤" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    await waitFor(() => expect(cancelBodies.length).toBe(3));
    expect(cancelBodies).toMatchObject([
      { seq_no: "F01", market: "fut" },
      { seq_no: "F02", market: "fut" },
      { seq_no: "F03", market: "fut" },
    ]);
    expect(screen.queryByText("確認平倉")).toBeNull(); // 全撤不走彈窗
  });
});

describe("FuturesLadder 一鍵平倉(SC-10)", () => {
  it("本契約部位 → 彈窗列出方向/口數/估價,確認後送 closeBodyOf 形狀", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/position/close": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "C01" });
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    render(ladder());
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    expect(screen.getByText("確認平倉")).toBeTruthy();
    expect(screen.getByText("TXFI6")).toBeTruthy();
    // 空單平倉貼漲停(25080 = upper/1000);方向/口數/估價同列
    expect(screen.getByText("空 2 口 · 估價 25080")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));
    // fut 不送 kind(closeBodyOf 契約);key = stock_no 非複合鍵
    expect(bodies[0]).toEqual({ market: "fut", key: "TXFI6", price: 25_080, qty: 2 });
    await waitFor(() => expect(screen.queryByText("確認平倉")).toBeNull());
  });

  it("多筆本契約部位 → 確認後逐筆送出", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/position/close": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "C01" });
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () =>
        json({
          positions: [
            futPos({ qty: -2 }),
            futPos({ kind: "margin", qty: 3 }), // 多單平倉貼跌停
          ],
        }),
    });
    render(ladder());
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    expect(screen.getByText("空 2 口 · 估價 25080")).toBeTruthy();
    expect(screen.getByText("多 3 口 · 估價 20520")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies).toEqual([
      { market: "fut", key: "TXFI6", price: 25_080, qty: 2 },
      { market: "fut", key: "TXFI6", price: 20_520, qty: 3 },
    ]);
  });

  /** 🔴 TQ-3(review round-1):上面兩條的 `TXF_STATE` 界都**已對齊** FUT_TICK
   *  (snap 前後同值)—— 元件層把 `edgeOf` 接錯口徑照樣綠。這條的 fixture 刻意未對齊:
   *    raw `20_520_600` 毫點 = 20520.6 點
   *    → 期貨 FUT_TICK(1 點)賣側 ceil = **20521**(本案期望值)
   *    → 個股期的股票 tick 表(2 萬點在 5 元檔)ceil = 20525(接錯口徑的觀測值)
   *  兩者差 4,足以把「FuturesLadder:110 誤傳 `stkfutMarketEdgeMilli`」照出來。 */
  it("跌停未對齊 FUT_TICK → 多單估價 ceil 到 1 點(20521,不是股票檔位的 20525)", async () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos({ qty: 3 })] }),
    });
    render(ladder({ ...TXF_STATE, lower: 20_520_600 }));
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    expect(screen.getByText("多 3 口 · 估價 20521")).toBeTruthy();
  });

  it("他契約 / 他市場部位不入清單 → 平倉鈕 disabled 且點擊不開彈窗", async () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () =>
        json({
          positions: [
            futPos({ stock_no: "MXFI6" }), // 他契約
            futPos({ market: "sec", stock_no: "2330" }), // 他市場
          ],
        }),
    });
    render(ladder());
    await screen.findByLabelText("買 22999");
    const btn = screen.getByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(true));
    fireEvent.click(btn);
    expect(screen.queryByText("確認平倉")).toBeNull();
  });

  // 送出後的回饋:與同檔 clickPrice 同型(mutateAsync + then/catch → hint)。
  // 平倉失敗若靜默,畫面上「部位還在」與「送出去被拒」長得一模一樣。
  it("平倉 200 但 ok:false → hint 顯示後端 message", async () => {
    mockFetch({
      "/api/capital/position/close": () =>
        json({ ok: false, code: -1, message: "結果未知(逾時)", seq_no: null }),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    render(ladder());
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(screen.getByText("結果未知(逾時)")).toBeTruthy());
  });

  it("平倉 400 → hint 顯示 tradeErrorText 產物(不是原始錯誤碼)", async () => {
    mockFetch({
      "/api/capital/position/close": () =>
        json({ detail: { error: "BROKER_REJECTED", err_code: "1097", err_msg: "廢單" } }, 400),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    render(ladder());
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(screen.getByText("券商拒單(1097)")).toBeTruthy());
  });

  it("平倉成功 → hint 顯示已送出(含契約與口數)", async () => {
    mockFetch({
      "/api/capital/position/close": () =>
        json({ ok: true, code: 0, message: "ok", seq_no: "C01" }),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    render(ladder());
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    fireEvent.click(btn);
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(screen.getByText("已送平倉 TXFI6 × 2 口")).toBeTruthy());
  });

  it("平倉失敗不動武裝狀態(平倉不是武裝路徑)", async () => {
    mockFetch({
      "/api/capital/position/close": () =>
        json({ ok: false, code: -1, message: "結果未知(逾時)", seq_no: null }),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    render(ladder());
    const btn = await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => expect(btn.hasAttribute("disabled")).toBe(false));
    armUp();
    fireEvent.click(btn);
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(screen.getByText("結果未知(逾時)")).toBeTruthy());
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy();
  });

  it("有部位但估價 null(漲跌停缺)→ disabled + title「無行情估價」", async () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos({ qty: 2 })] }),
    });
    // 多單平倉貼跌停 → lower 缺 = 估不出價;upper 保留讓階梯照常渲染
    render(ladder({ ...TXF_STATE, lower: null }));
    await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: "平倉" });
      expect(btn.hasAttribute("disabled")).toBe(true);
      expect(btn.getAttribute("title")).toBe("無行情估價");
    });
  });

  /** 🔴 TQ-5(review round-1):`0` 是後端界不可得時的**缺值哨符**,不是價 —— 與上面
   *  那條的 `null` 走不同路徑(型別缺值 vs `edgeMilli` 的 ≤0 守門),元件層只驗過 null。
   *  漏掉的症狀是「用 0 元送真錢單」。同一份界餵給市價鈕(`marketEdge("sell")`),
   *  所以兩顆鈕必須同時鎖 —— 一邊鎖一邊不鎖 = 同一份行情兩個矛盾答案。 */
  it("跌停為 0(缺值哨符)→ 平倉鈕 + 賣側市價鈕同時 disabled", async () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [futPos({ qty: 2 })] }),
    });
    render(ladder({ ...TXF_STATE, lower: 0 }));
    await screen.findByRole("button", { name: "平倉" });
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: "平倉" });
      expect(btn.hasAttribute("disabled")).toBe(true);
      expect(btn.getAttribute("title")).toBe("無行情估價");
    });
    expect(marketBtn("賣").hasAttribute("disabled")).toBe(true);
  });
});

describe("FuturesLadder 結算 T-0 警示(SC-6)", () => {
  it("結算當日 → 武裝列上方出現「⚠ 今日結算」amber 列", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 16)); // 2026-09-16 = 202609 第三個週三
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    const warn = screen.getByText("⚠ 今日結算");
    expect(warn).toBeTruthy();
    expect(warn.className).toContain("amber");
    // 位置:在武裝鈕之前(DOM 順序 = 視覺在武裝列上方)
    const arm = screen.getByRole("button", { name: "武裝" });
    expect(warn.compareDocumentPosition(arm) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("非結算日 → 不顯示警示列", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 15)); // T-1
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    expect(screen.queryByText("⚠ 今日結算")).toBeNull();
  });

  // review TZ-3:第三週三遇假日順延 → 那天之後、HOT 換月之前仍是「最後交易日在即」,
  // 警示消失比殘留危險得多(誤留倉 = 現金結算)
  it("純日曆結算日已過但 HOT 未換月 → 警示仍在", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 17)); // 2026-09-17,202609 的第三週三之後
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    expect(screen.getByText("⚠ 今日結算")).toBeTruthy();
  });

  it("resolved_contract null → 不顯示警示列(合約未解析)", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 16));
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder({ ...TXF_STATE, resolved_contract: null }));
    expect(screen.queryByText("⚠ 今日結算")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 梯頂市價鈕(SC-1 / SC-4 / SC-5 / SC-6 / SC-8)。期貨的「市價」= 限價貼漲跌停 + IOC
// (D3a);邊價 floor/ceil 到 FUT_TICK,與 buildFuturesLadder 同口徑(R8)。
// ---------------------------------------------------------------------------

const EDGE_MARKET_TITLE =
  "市價 = 限價貼漲/跌停 + IOC:掃對手方至成交完(簿薄時可能以漲/跌停價成交),餘量取消";

function marketBtn(side: "買" | "賣"): HTMLElement {
  return within(screen.getByTestId("ladder-market-buttons")).getByRole("button", {
    name: `市價${side}`,
  });
}

describe("FuturesLadder 梯頂市價鈕", () => {
  it("SC-1 / SC-8:兩顆鈕在 scroll 容器之前;可用態 title = 貼漲跌停 + IOC 文案", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    const row = screen.getByTestId("ladder-market-buttons");
    expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "市價買",
      "市價賣",
    ]);
    const scroller = screen.getByLabelText("買 22999").closest(".overflow-y-auto")!;
    expect(scroller.contains(row)).toBe(false);
    expect(row.compareDocumentPosition(scroller) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(4);
    expect(marketBtn("買").getAttribute("title")).toBe(EDGE_MARKET_TITLE);
    expect(marketBtn("賣").getAttribute("title")).toBe(EDGE_MARKET_TITLE);
  });

  it("SC-4:武裝後按市價買 → limit/IOC + price = floor(漲停/FUT_TICK);hint 帶契約碼", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toEqual({
      tc4_symbol: "TC.F.TWF.TXF.HOT",
      buy_sell: "buy",
      price: 25_080, // upper 25_080_000 已對齊 1 點
      qty: 1,
      price_type: "limit",
      time_in_force: "IOC",
      day_trade: false,
      source: "flash",
    });
    await waitFor(() => expect(screen.getByText("已送 TXFI6 市價買 × 1 口")).toBeTruthy());
  });

  it("SC-4:市價賣 → price = ceil(跌停/FUT_TICK),非整點的界往簿內收", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder({ ...TXF_STATE, lower: 20_520_500 }));
    armUp();
    fireEvent.click(marketBtn("賣"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({
      buy_sell: "sell",
      price: 20_521,
      price_type: "limit",
      time_in_force: "IOC",
    });
    await waitFor(() => expect(screen.getByText("已送 TXFI6 市價賣 × 1 口")).toBeTruthy());
  });

  it("SC-5:未武裝 → 零請求 + hint「未武裝 — 市價不送單」", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    fireEvent.click(marketBtn("買"));
    expect(screen.getByText("未武裝 — 市價不送單")).toBeTruthy();
    await act(async () => {}); // 排空 microtask 再斷言零請求(IMPL-8)
    expect(bodies.length).toBe(0);
  });

  it("SC-6:resolved_contract null(合約未解析)→ 兩顆 disabled + 鎖定文案", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder({ ...TXF_STATE, resolved_contract: null }));
    for (const side of ["買", "賣"] as const) {
      const b = marketBtn(side);
      expect(b.hasAttribute("disabled")).toBe(true);
      expect(b.getAttribute("title")).toBe("無成交價,市價鈕鎖定");
    }
  });

  it("SC-6:漲停缺 → 兩顆 disabled(不用假想界貼邊)", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder({ ...TXF_STATE, upper: null }));
    expect(marketBtn("買").hasAttribute("disabled")).toBe(true);
    expect(marketBtn("賣").hasAttribute("disabled")).toBe(true);
  });

  /** IMPL-2:render 可用態 → rerender 成應鎖態(界從有值變缺,合約仍解析 = 武裝不受影響)。
   *  React 的 disabled 攔截看 props 不看 DOM 屬性(見 PriceLadder 同案註)→ 這案鎖的是
   *  「行情轉成缺界後 marketState 立刻跟著鎖」,而不是 handler 內那道打不到的雙保險。 */
  it("IMPL-2:武裝中界轉缺 → 兩顆立刻鎖,拔 DOM disabled 也點不出請求", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    const { rerender } = render(ladder());
    armUp();
    expect(marketBtn("買").hasAttribute("disabled")).toBe(false);
    rerender(ladder({ ...TXF_STATE, upper: null, lower: null }));
    for (const side of ["買", "賣"] as const) {
      const b = marketBtn(side);
      expect(b.hasAttribute("disabled")).toBe(true);
      b.removeAttribute("disabled");
      fireEvent.click(b);
    }
    await act(async () => {});
    expect(bodies.length).toBe(0);
    expect(screen.getByRole("button", { name: "解除" })).toBeTruthy(); // 仍武裝(鎖的是鈕)
  });

  /** F2:防抖在現股梯有測、期貨梯沒有 —— 三梯各寫一份 marketOrder,漏一梯就是
   *  「同一顆連按兩下送出兩口」而沒有任何測試會紅。 */
  it("F2:同一顆 500ms 內連按只送一次;另一顆照送", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
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
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>);
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    render(ladder());
    armUp();
    fireEvent.click(marketBtn("買"));
    fireEvent.click(screen.getByLabelText("買 22999"));
    fireEvent.click(marketBtn("買"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies.filter((b) => b.time_in_force === "IOC").length).toBe(1); // 市價鈕
    expect(bodies.filter((b) => b.time_in_force === "ROD").length).toBe(1); // 點價
  });

  /** F4:中心價的兩個來源(成交價 p / 參考價 ref)都缺 → 沒有可估的價,兩顆全鎖;
   *  state 整包缺(WS 未回)時 rows 為空,鈕列照樣要在(鈕自身由估價鎖)。 */
  it("F4:p 與 ref 全缺 → 兩顆 disabled;state 缺(rows 空)仍渲染鈕列", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    const { rerender } = render(ladder({ ...TXF_STATE, p: null, ref: null }));
    for (const side of ["買", "賣"] as const) {
      expect(marketBtn(side).hasAttribute("disabled")).toBe(true);
    }
    rerender(ladder(null));
    expect(screen.getByText("無資料")).toBeTruthy();
    expect(screen.getByTestId("ladder-market-buttons")).toBeTruthy();
    expect(marketBtn("買").hasAttribute("disabled")).toBe(true);
  });

  /** 🔴 N083:`futExchangeContract` 對非 YYYYMM 會 throw,而它在 render body 上 ——
   *  未捕捉 = 整個期貨頁白屏(App.tsx / FuturesChart / StkfutLadder 三處早已各自 try/catch,
   *  只有這裡漏了)。contract=null 是既有的安全狀態:活單 / 部位比對自然落空、梯照畫。 */
  it("resolved_contract 壞值 → 不拋(梯照渲染,活單 / 平倉對象落空)", () => {
    mockFetch({
      "/api/capital/orders": () => json({ orders: [futOrder()] }),
      "/api/capital/positions": () => json({ positions: [futPos()] }),
    });
    expect(() =>
      render(ladder({ ...TXF_STATE, resolved_contract: "2026" })),
    ).not.toThrow();
    expect(screen.getByLabelText("買 22999")).toBeTruthy();
  });
});

// 🔴 N081 + 🔴 N082(期貨梯)。
describe("FuturesLadder 武裝閘與稽核 source(N081 / N082)", () => {
  it("N081:WS 非 open 時武裝鈕 disabled + 文案(與鎖定鈕同一個答案)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    setCapitalWsStatus("connecting");
    render(ladder());
    const arm = screen.getByRole("button", { name: "武裝" });
    expect(arm.hasAttribute("disabled")).toBe(true);
    expect(arm.getAttribute("title")).toBe("連線未就緒,無法武裝");
    act(() => setCapitalWsStatus("open"));
    expect(screen.getByRole("button", { name: "武裝" }).hasAttribute("disabled")).toBe(false);
  });

  it("N081:已武裝後 WS 轉 connecting → 解除鈕恆可按(disabled 只擋進入方向)", () => {
    mockFetch({ "/api/capital/orders": () => json({ orders: [] }) });
    setCapitalWsStatus("open");
    render(ladder());
    armUp();
    act(() => setCapitalWsStatus("connecting")); // connecting 不清武裝(只有 closed 才 conn_lost)
    const off = screen.getByRole("button", { name: "解除" });
    expect(off.hasAttribute("disabled")).toBe(false);
  });

  it("N082:鎖定態點價 → source=flash-locked;未鎖定 → flash", async () => {
    const bodies: { source?: string }[] = [];
    mockFetch({
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json(OK_RESULT);
      },
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/capital/positions": () => json({ positions: [] }),
    });
    setCapitalWsStatus("open");
    render(ladder());
    armUp();
    fireEvent.click(screen.getByLabelText("買 22999"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]?.source).toBe("flash");

    fireEvent.click(screen.getByRole("button", { name: "鎖定" }));
    fireEvent.click(screen.getByLabelText("賣 23001"));
    await waitFor(() => expect(bodies.length).toBe(2));
    expect(bodies[1]?.source).toBe("flash-locked");
  });
});
