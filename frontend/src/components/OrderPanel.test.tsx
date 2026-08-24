/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderPanel } from "@/components/OrderPanel";
import type { CapitalStatus, ContractRow } from "@/types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const CALL = "TC.O.TWF.TXO.202607.C.23000";
const PUT = "TC.O.TWF.TXO.202607.P.22000";

function contract(overrides: Partial<ContractRow> = {}): ContractRow {
  return {
    symbol: CALL,
    cp: "C",
    strike: 23000,
    net_qty: 1,
    volume: 10,
    outer_qty: 6,
    inner_qty: 4,
    last_price: 15.5,
    ...overrides,
  };
}

// CALL 有成交估價;PUT 無(市價選項應鎖定)
const CONTRACTS: ContractRow[] = [
  contract(),
  contract({ symbol: PUT, cp: "P", strike: 22000, last_price: null }),
];

function capStatus(overrides: Partial<CapitalStatus> = {}): CapitalStatus {
  return {
    status: "ok",
    env: "test",
    account_masked: "****1234",
    futures_account_masked: "****5678",
    order_enabled: true,
    ...overrides,
  };
}

/** 🔴 a11y 批:委託類型 pill 改 RadioPills(sr-only radio + label)。
 *  舊寫法 `getByText("市價").closest("button")?.getAttribute("disabled")` 在改後會靜默
 *  vacuous —— `closest("button")` 回 null、`?.` 讓 `.not.toBeNull()` 對著 `undefined` 通過。
 *  改鎖 input 的 `disabled` 本身,並連 `title`(W8:文案與觸發條件不變)一起釘。 */
function expectMarketLocked() {
  const market = screen.getByRole("radio", { name: "市價" }) as HTMLInputElement;
  expect(market.disabled).toBe(true);
  expect(market.closest("label")?.getAttribute("title")).toBe("此合約尚無成交估價,市價暫不可送出");
}

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

function renderPanel(contracts: ContractRow[] | undefined = CONTRACTS) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <OrderPanel contracts={contracts} />
    </QueryClientProvider>,
  );
}

describe("OrderPanel(群益)", () => {
  it("ok 時顯示模擬徽章(accent 框)+ 期貨帳號遮罩,送出鈕可按", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    const badge = await screen.findByText("模擬");
    expect(badge.className).toContain("border-accent");
    expect(screen.getByText("****5678")).toBeTruthy(); // futures_account_masked 優先
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    const btn = screen.getByText("送出").closest("button");
    expect(btn?.getAttribute("disabled")).toBeNull();
  });

  it("status=disabled 顯示群益未啟用且送出鈕鎖定", async () => {
    mockFetch({
      "/api/capital/status": () => json({ status: "disabled" }),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    expect(await screen.findByText("群益未啟用")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    const btn = screen.getByText("送出").closest("button");
    expect(btn?.getAttribute("disabled")).not.toBeNull();
  });

  it("status=starting 顯示群益連線未就緒且鎖定;degraded 顯示註記但不鎖", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus({ status: "starting" })),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    const first = renderPanel();
    expect(await screen.findByText("群益連線未就緒")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    expect(screen.getByText("送出").closest("button")?.getAttribute("disabled")).not.toBeNull();
    first.unmount();

    mockFetch({
      "/api/capital/status": () => json(capStatus({ status: "degraded" })),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    expect(await screen.findByText(/群益回報連線降級/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    expect(screen.getByText("送出").closest("button")?.getAttribute("disabled")).toBeNull();
  });

  it("彈窗流:送出 → rows 含預估權利金 → 確認 → POST /api/capital/order/future payload", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "0001" });
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    await screen.findByText("模擬");
    fireEvent.change(screen.getByLabelText("商品"), { target: { value: CALL } });
    fireEvent.change(screen.getByLabelText("口數"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    fireEvent.click(screen.getByText("送出"));
    expect(await screen.findByText("確認送單")).toBeTruthy();
    expect(screen.getByText("預估權利金")).toBeTruthy();
    expect(screen.getByText("1,550 元")).toBeTruthy(); // 15.5 × 2 口 × 50 元/點
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({
      tc4_symbol: CALL,
      buy_sell: "buy",
      price: 15.5,
      qty: 2,
      price_type: "limit",
      time_in_force: "ROD",
      day_trade: false,
      source: "panel",
    });
    await waitFor(() => expect(screen.queryByText("確認送單")).toBeNull());
    expect(await screen.findByText("已送出(單號 0001),回報見下方列表")).toBeTruthy();
  });

  it("送單 503 CAPITAL_DISABLED → 顯示群益未啟用", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/order/future": () => json({ detail: { error: "CAPITAL_DISABLED" } }, 503),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    await screen.findByText("模擬");
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    fireEvent.click(screen.getByText("送出"));
    await screen.findByText("確認送單");
    fireEvent.click(screen.getByText("確認"));
    expect(await screen.findByText("群益未啟用")).toBeTruthy();
  });

  it("prod 徽章紅底 + 彈窗 danger 標題列紅底", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus({ env: "prod" })),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    const badge = await screen.findByText("正式");
    expect(badge.className).toContain("bg-loss");
    fireEvent.change(screen.getByLabelText("價格(點)"), { target: { value: "15.5" } });
    fireEvent.click(screen.getByText("送出"));
    await waitFor(() => {
      expect(screen.getByText("確認送單").closest("div")?.className).toContain("bg-loss");
    });
  });

  it("市價估價:snapshot 估價入 payload;無估價合約鎖市價選項", async () => {
    const bodies: unknown[] = [];
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/order/future": (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return json({ ok: true, code: 0, message: "ok", seq_no: "0002" });
      },
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    await screen.findByText("模擬");
    fireEvent.click(screen.getByRole("radio", { name: "市價" }));
    expect(screen.queryByLabelText("價格(點)")).toBeNull();
    fireEvent.click(screen.getByText("送出"));
    expect(await screen.findByText("確認送單")).toBeTruthy();
    expect(screen.getByText("市價(估 15.5 點)")).toBeTruthy();
    expect(screen.getByText("775 元")).toBeTruthy(); // 15.5 × 1 口 × 50 元/點
    fireEvent.click(screen.getByText("確認"));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ tc4_symbol: CALL, price: 15.5, price_type: "market" });

    // 無估價合約(PUT last_price=null)→ 選擇不被改寫,改由送出鈕 + 理由擋(N011)
    fireEvent.change(screen.getByLabelText("商品"), { target: { value: PUT } });
    expect((screen.getByRole("radio", { name: "市價" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("此合約尚無成交估價,市價暫不可送出")).toBeTruthy();
    expect(screen.getByText("送出").closest("button")?.getAttribute("disabled")).not.toBeNull();
  });

  // TC-2:買賣別 radiogroup 在 a11y 批之前**零測試** —— 它決定的是買還是賣(真錢方向),
  // 而 pill 群改成 sr-only radio 之後,「選中態的紅綠框」與「兩組互不搶選」都只剩 DOM
  // 屬性看得出來。text-center 是 grid-cols-2 下 `<label>` 沒有 UA 置中的補救(W-視覺零變)。
  it("TC-2:買賣別 radiogroup —— 預設買進、選賣出換色、與委託類型 name 互異", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    await screen.findByText("模擬");
    const side = screen.getByRole("radiogroup", { name: "買賣別" });
    const radios = within(side).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.length).toBe(2);
    const buy = within(side).getByRole("radio", { name: "買進" }) as HTMLInputElement;
    const sell = within(side).getByRole("radio", { name: "賣出" }) as HTMLInputElement;
    expect(buy.checked).toBe(true);
    expect(sell.checked).toBe(false);
    expect(buy.closest("label")!.className).toContain("border-bull");

    fireEvent.click(sell);
    expect(sell.checked).toBe(true);
    expect(buy.checked).toBe(false);
    const sellCls = sell.closest("label")!.className;
    expect(sellCls).toContain("border-bear");
    expect(sellCls).not.toContain("border-bull");
    // 未選中的那顆回到中性框(留著 border-bull 就等於兩顆同時看起來像選中)
    expect(buy.closest("label")!.className).toContain("border-line");

    // 同頁兩組 radiogroup 必須各自 `name`,否則原生 radio 會互相搶選(選了賣出就把
    // 限價/市價的選取清掉)
    const kind = screen.getByRole("radiogroup", { name: "委託類型" });
    const kindRadios = within(kind).getAllByRole("radio") as HTMLInputElement[];
    expect(new Set(radios.map((r) => r.name)).size).toBe(1);
    expect(new Set(kindRadios.map((r) => r.name)).size).toBe(1);
    expect(radios[0]!.name).not.toBe(kindRadios[0]!.name);

    // grid-cols-2 的格子比文字寬:`<label>` 沒有 UA 置中,漏了就是可見的版面偏移
    for (const r of [...radios, ...kindRadios]) {
      expect(r.closest("label")!.className).toContain("text-center");
    }
  });

  // 🔴 N011(推翻舊 A11Y-2 的單向收斂):選了市價之後換到**無估價**的合約,舊版在
  // render 期間把 `kind` 翻回 limit 且**不還原** —— 估價回來後畫面停在限價,使用者
  // 以為自己還在市價。改成「disabled 只擋**進入**方向」(同 ArmRow 慣例):checked 的
  // 那顆不 disabled(radiogroup 仍有可聚焦項)、送出鈕照樣鎖住並印出可見理由,
  // 估價回來即自動可送 = 還原。
  it("N011:市價態換到無估價合約 → 維持市價 + 送出鈕鎖定 + 可見理由,不靜默翻回限價", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    await screen.findByText("模擬");
    fireEvent.click(screen.getByRole("radio", { name: "市價" }));
    expect((screen.getByRole("radio", { name: "市價" }) as HTMLInputElement).checked).toBe(true);

    fireEvent.change(screen.getByLabelText("商品"), { target: { value: PUT } });
    const market = screen.getByRole("radio", { name: "市價" }) as HTMLInputElement;
    expect(market.checked).toBe(true); // 使用者的選擇不被靜默改寫
    expect(market.disabled).toBe(false); // disabled 只擋進入方向 → checked 的那顆恆可聚焦
    expect(screen.getByText("此合約尚無成交估價,市價暫不可送出")).toBeTruthy();
    expect(screen.getByText("送出").closest("button")?.getAttribute("disabled")).not.toBeNull();
    const group = screen.getByRole("radiogroup", { name: "委託類型" });
    const radios = within(group).getAllByRole("radio") as HTMLInputElement[];
    expect(radios.filter((r) => r.checked && !r.disabled).length).toBe(1);

    // 估價回來(換回有成交的合約)→ 仍是市價、鈕解鎖:「還原」不需要使用者再點一次
    fireEvent.change(screen.getByLabelText("商品"), { target: { value: CALL } });
    expect((screen.getByRole("radio", { name: "市價" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("送出").closest("button")?.getAttribute("disabled")).toBeNull();
  });

  it("N011:未選市價時,無估價合約的市價 pill 仍 disabled(進入方向照擋)", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    await screen.findByText("模擬");
    fireEvent.change(screen.getByLabelText("商品"), { target: { value: PUT } });
    expectMarketLocked();
    expect((screen.getByRole("radio", { name: "限價" }) as HTMLInputElement).checked).toBe(true);
  });

  it("選單以 /api/txo/contracts 全鏈為主:props 子集仍列全鏈;鏈上無估價合約鎖市價", async () => {
    const EXTRA = "TC.O.TWF.TXO.202607.C.24000";
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/txo/contracts": () => json({ contracts: [CALL, PUT, EXTRA] }),
    });
    renderPanel([contract()]); // props 僅 CALL(當日成交子集)
    await screen.findByText("模擬");
    expect(await screen.findByRole("option", { name: "TXO.202607.C.24000" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "TXO.202607.P.22000" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "TXO.202607.C.23000" })).toBeTruthy();
    // EXTRA 不在 props → 無 last_price → 市價鎖定(估價查找仍走 props)
    fireEvent.change(screen.getByLabelText("商品"), { target: { value: EXTRA } });
    expectMarketLocked();
  });

  it("props 為空時選單仍列全鏈", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/txo/contracts": () => json({ contracts: [CALL, PUT] }),
    });
    renderPanel([]);
    await screen.findByText("模擬");
    expect(await screen.findByRole("option", { name: "TXO.202607.C.23000" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "TXO.202607.P.22000" })).toBeTruthy();
  });

  it("/api/txo/contracts 空列表或失敗 → fallback props contracts", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/txo/contracts": () => json({ contracts: [] }),
    });
    const first = renderPanel();
    await screen.findByText("模擬");
    expect(await screen.findByRole("option", { name: "TXO.202607.C.23000" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "TXO.202607.P.22000" })).toBeTruthy();
    first.unmount();

    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
      "/api/txo/contracts": () => json({ detail: { error: "NOT_READY" } }, 503),
    });
    renderPanel();
    await screen.findByText("模擬");
    expect(await screen.findByRole("option", { name: "TXO.202607.C.23000" })).toBeTruthy();
  });

  it("切市價隱藏價格欄、切回限價恢復", async () => {
    mockFetch({
      "/api/capital/status": () => json(capStatus()),
      "/api/capital/orders": () => json({ orders: [] }),
    });
    renderPanel();
    await screen.findByText("模擬");
    expect(screen.getByLabelText("價格(點)")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "市價" }));
    expect(screen.queryByLabelText("價格(點)")).toBeNull();
    fireEvent.click(screen.getByRole("radio", { name: "限價" }));
    expect(screen.getByLabelText("價格(點)")).toBeTruthy();
  });
});
