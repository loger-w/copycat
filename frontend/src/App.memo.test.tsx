/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import type { StockBook } from "@/lib/stock-accum";
import type { FuturesProductState } from "@/types";

/** 🟢 S1 [lock]:App 層 `railCtx` 的 memo 邊界 —— 跨流串擾擋不擋得下來,以及擋下來之後
 *  右欄拿到的還是不是最新的簿 / 成交。
 *
 *  這件事**在畫面上完全看不出來**:memo 失效只是期貨 10 Hz tick 每一則都把右欄整棵
 *  subtree(閃電梯 = 全站最重的 render)重畫一次;memo 生效但 deps 漏一項,則是右欄
 *  掛著舊五檔 / 舊成交價,而那是真錢面板。兩種失效都零錯誤訊號。
 *
 *  量法(plan R14/R15/R16):
 *  - **mock RightRail 內部的葉子、保留真 RightRail 與真 memo** —— 把 RightRail 本身
 *    換成 stub 等於把要測的 memo 一起換掉(stub 不包 memo 恆紅、包了 memo 守門是空的);
 *  - 前置 `copycat-tab=stock` + 主檔 —— tab 落在別的分支時 railCtx 走 `NONE_CTX` 恆定,
 *    斷言零訊號恆綠;
 *  - 案例依**實際訊息型別**拆:單一則更新不可能同時動 book / last / meta。
 *    tick 的 `seq` 必須接續 snapshot 的 seq(跳號會觸發自癒 refetch,多一次 setAccum 汙染計次)。 */

const hoisted = vi.hoisted(() => ({
  /** 個股閃電梯(右欄 subtree 的葉子)每次 render 的 {book,last,meta} 記錄 */
  ladder: [] as { book: unknown; last: unknown; meta: unknown }[],
  /** `kind:"none"` 分支的葉子(委託 tab 的兩段清單)每次 render 的 market 記錄 */
  orders: [] as string[],
}));

vi.mock("@/components/stock/PriceLadder", () => ({
  PriceLadder: ({ book, last, meta }: { book: unknown; last: unknown; meta: unknown }) => {
    hoisted.ladder.push({ book, last, meta });
    return <div data-testid="ladder-stub" />;
  },
}));

vi.mock("@/components/capital/CapitalOrdersList", () => ({
  CapitalOrdersList: ({ market }: { market: string }) => {
    hoisted.orders.push(market);
    return <div data-testid={`orders-stub-${market}`} />;
  },
}));

class FakeWS {
  static instances: FakeWS[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWS.instances.push(this);
  }

  close(): void {}
}

const INDEX_STATE = {
  trade_date: "2026-07-28",
  twse: {
    p: 42_039_920, ref: 43_634_190, high: 43_221_930, low: 41_815_780,
    stale: false, last_minute: null, minutes: { "0901": 43_000_000 },
  },
  otc: {
    p: 359_800, ref: 378_090, high: 373_420, low: 358_430,
    stale: false, last_minute: null, minutes: { "1017": 359_800 },
  },
  txf: { p: 42_142_000, time: "10:16:10" },
};

const BREADTH_ROWS = {
  enabled: true,
  trade_date: "2026-08-06",
  as_of: "10:31:00",
  stale: false,
  streaks_ready: true,
  rows: [],
};

function futProduct(p: number): FuturesProductState {
  return {
    product: "TXF",
    name: "台指期",
    p,
    q: 1,
    cum_vol: 100,
    t: "10:00:00",
    date: "2026-07-28",
    bids: [[p - 1_000, 5]],
    asks: [[p + 1_000, 3]],
    ref: 20_940_000,
    upper: 23_034_000,
    lower: 18_846_000,
    resolved_contract: "202608",
  };
}

/** 個股主圖 snapshot。`seq: 1` → 接續的 tick 用 `seq: 2`(跳號會多打一次全量對齊)。 */
function stockSnapshot(code: string) {
  return {
    code,
    seq: 1,
    last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
    vwap: 2_380_000,
    minutes: {},
    ticks: [],
    book: { bids: [[2_375_000, 5]], asks: [[2_380_000, 3]] },
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    no_data: false,
  };
}

function appFetch() {
  return vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/api/index/state")) return new Response(JSON.stringify(INDEX_STATE));
    if (u.includes("/api/futures/state")) {
      return new Response(JSON.stringify({ seq: 0, products: { TXF: futProduct(21_042_000) } }));
    }
    if (u.includes("/api/market/breadth/rows")) return new Response(JSON.stringify(BREADTH_ROWS));
    if (u.includes("/api/stock/signals/today")) return new Response(JSON.stringify({ signals: [] }));
    if (u.includes("/api/stock/signals/rules")) return new Response(JSON.stringify({ rules: [] }));
    if (u.includes("/api/stock/watchlist")) {
      return new Response(JSON.stringify({ groups: [{ name: "自選", codes: ["2330"] }] }));
    }
    if (u.includes("/api/stock/names")) return new Response(JSON.stringify({ names: [], count: 0 }));
    if (u.includes("/api/stock/stkfut/contracts/")) {
      return new Response(JSON.stringify({ detail: { error: "NO_STKFUT" } }), { status: 404 });
    }
    if (u.includes("/api/stock/overlay/")) {
      return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
    }
    if (u.includes("/api/stock/bars")) return new Response(JSON.stringify({ bars: [], status: "ok" }));
    if (u.includes("/api/stock/state/")) {
      const code = u.slice("/api/stock/state/".length).split("?")[0] ?? "2330";
      return new Response(JSON.stringify(stockSnapshot(code)));
    }
    if (u.includes("/api/capital/orders")) return new Response(JSON.stringify({ orders: [] }));
    if (u.includes("/api/capital/positions")) return new Response(JSON.stringify({ positions: [] }));
    if (u.includes("/api/health")) {
      return new Response(JSON.stringify({ git_sha: null, git_dirty: false }));
    }
    if (u.includes("/__build/sha")) {
      return new Response(JSON.stringify({ git_sha: null, behind: null }));
    }
    if (u.includes("/api/calendar")) {
      return new Response(
        JSON.stringify({
          today: "2026-08-16", trade_date: "2026-08-14", calendar_trade_date: "2026-08-14",
          backfill_env: null, holidays: [], years_loaded: [2026], calendar_loaded: true,
        }),
      );
    }
    return new Response(JSON.stringify({}), { status: 404 });
  });
}

beforeEach(() => {
  window.localStorage.clear();
  hoisted.ladder.length = 0;
  hoisted.orders.length = 0;
  FakeWS.instances = [];
  // 右欄閃電梯掛載即置中;jsdom 無 scrollIntoView(同 App.test / PriceLadder.test)
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
  vi.stubGlobal("fetch", appFetch());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

function fetchUrls(): string[] {
  return (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]));
}

function futStateCalls(): number {
  return fetchUrls().filter((u) => u.includes("/api/futures/state")).length;
}

function wsOf(path: string): FakeWS {
  const found = FakeWS.instances.filter((w) => w.url.endsWith(path)).at(-1);
  if (found === undefined) throw new Error(`no ws for ${path}`);
  return found;
}

function send(path: string, msg: unknown): void {
  wsOf(path).onmessage?.({ data: JSON.stringify(msg) });
}

/** 把 in-flight 的 fetch / TQ 通知排乾(TQ 走 notifyManager 的 macrotask 排程)。 */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

/** 期貨腿推兩則**連號**訊息。回傳前的自檢在呼叫端:兩則都被吃下 = 不會多打一次
 *  `/api/futures/state`(seq 對不上就會全量對齊)—— 少了這道,「計次沒變」在
 *  「訊息根本沒進到 hook」的世界裡也是綠的。 */
function pushFuturesTicks(): void {
  // 兩則各自一個 act:同一批送出會被 React 合併成一次 re-render,量到的串擾會被低估
  // (真實 10 Hz 是各自獨立的一則)
  act(() => {
    send("/ws/futures", { type: "futures", seq: 1, product: "TXF", state: futProduct(21_050_000) });
  });
  act(() => {
    send("/ws/futures", { type: "futures", seq: 2, product: "TXF", state: futProduct(21_060_000) });
  });
}

describe("App railCtx memo 邊界(S1)", () => {
  it("停在個股 tab 時,期貨推播不重畫右欄葉子(跨流串擾)", async () => {
    window.localStorage.setItem("copycat-tab", "stock");
    window.localStorage.setItem("copycat-stock-main-code", "2330");
    renderApp();
    await screen.findByTestId("ladder-stub");
    await waitFor(() => expect(futStateCalls()).toBe(1));
    await settle();
    await settle();

    const before = hoisted.ladder.length;
    expect(before).toBeGreaterThan(0);
    pushFuturesTicks();

    // 自檢:兩則都被期貨流吃下(連號 → 不需要全量對齊)
    expect(futStateCalls()).toBe(1);
    expect(hoisted.ladder.length).toBe(before);
  });

  it("book 訊息 → 右欄葉子拿到新的五檔(stockCtx deps 完整)", async () => {
    window.localStorage.setItem("copycat-tab", "stock");
    window.localStorage.setItem("copycat-stock-main-code", "2330");
    renderApp();
    await screen.findByTestId("ladder-stub");
    await settle();
    const before = hoisted.ladder.length;

    act(() => {
      send("/ws/stock", {
        type: "book",
        code: "2330",
        bids: [[2_376_000, 9]],
        asks: [[2_381_000, 4]],
      });
    });

    expect(hoisted.ladder.length).toBeGreaterThan(before);
    const book = hoisted.ladder.at(-1)?.book as StockBook;
    expect(book.bids[0]?.[0]).toBe(2_376_000);
    expect(book.asks[0]?.[0]).toBe(2_381_000);
  });

  it("tick 訊息(seq 接續)→ 右欄葉子拿到新的成交(stockCtx deps 完整)", async () => {
    window.localStorage.setItem("copycat-tab", "stock");
    window.localStorage.setItem("copycat-stock-main-code", "2330");
    renderApp();
    await screen.findByTestId("ladder-stub");
    await settle();
    const before = hoisted.ladder.length;
    const stateCalls = fetchUrls().filter((u) => u.includes("/api/stock/state/")).length;

    act(() => {
      send("/ws/stock", {
        type: "tick",
        code: "2330",
        t: "09:10:00.000",
        p: 2_390_000,
        q: 3,
        side: "outer",
        seq: 2,
      });
    });

    // 自檢:seq 接得上(跳號會多打一次全量 snapshot,那條路的重繪與 memo 無關)
    expect(fetchUrls().filter((u) => u.includes("/api/stock/state/")).length).toBe(stateCalls);
    expect(hoisted.ladder.length).toBeGreaterThan(before);
    const last = hoisted.ladder.at(-1)?.last as { p: number };
    expect(last.p).toBe(2_390_000);
  });

  it("停在台股綜合 tab 時,期貨推播不重畫右欄葉子(NONE_CTX 恆定)", async () => {
    window.localStorage.setItem("copycat-tab", "index");
    window.localStorage.setItem("copycat-rail-tab", "orders");
    renderApp();
    await screen.findByTestId("orders-stub-sec");
    await waitFor(() => expect(futStateCalls()).toBe(1));
    await settle();
    await settle();

    const before = hoisted.orders.length;
    expect(before).toBeGreaterThan(0);
    pushFuturesTicks();

    expect(futStateCalls()).toBe(1);
    expect(hoisted.orders.length).toBe(before);
  });
});
