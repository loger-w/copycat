/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, configure, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import type { FuturesProductState } from "@/types";

// App 級整鏈測試(lazy 頁 + TQ + WS fake)在剛 `npm ci` 的 worktree / 兩個 reviewer 並跑時,`waitFor` / `findBy*`
// 預設 1 s 會被負載打穿(08-30 五次全量各紅 1–4 條、每次不同、單檔重跑全綠;next-time 08-28 L68 / 08-30 節)。
// 拉到 3 s 只是把「等」的上限放寬,斷言本身不變 —— 綠的路徑仍在首輪就 settle,不會多等。
configure({ asyncUtilTimeout: 3000 });

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
 *    tick 的 `seq` 必須接續 snapshot 的 seq(跳號會觸發自癒 refetch,多一次 setAccum 汙染計次)。
 *
 *  **fixture 的脆性(改動前先看這裡)**:本檔刻意讓 TXO snapshot 保持 null —— `appFetch`
 *  沒有任何 TXO 端點、`FakeWS` 也不對 `/ws/txo-pnl` 送東西,所以 `TxoPage` 停在
 *  「等待伺服器連線…」、`OrderPanel` 不 render。這件事**是計數器正確性的前提**:
 *  `OrderPanel` 內另有一個 `<CapitalOrdersList market="fut" />`(components/OrderPanel.tsx),
 *  而 TXO tab 是 `hidden` 保留 DOM(不是 unmount)—— 它一旦 render,`hoisted.orders`
 *  就同時混著 TXO 頁與右欄兩個來源,`kind:"none"` 那條「+0」斷言會變成量別人的東西。
 *  日後要補 TXO 端點 fixture(例如為了測別的東西)時,得先把 orders 計數器改成
 *  能區分來源(多帶一個 prop / 換 testid),否則兩條 tab 案會靜默失效。 */

const hoisted = vi.hoisted(() => ({
  /** 個股閃電梯(右欄 subtree 的葉子)每次 render 的 {code,name,book,last,meta} 記錄 */
  ladder: [] as { code: unknown; name: unknown; book: unknown; last: unknown; meta: unknown }[],
  /** 期貨閃電梯(右欄 `kind:"futures"` 分支的葉子)每次 render 的 {state,contract} 記錄 */
  futures: [] as { state: unknown; contract: unknown }[],
  /** `kind:"none"` 分支的葉子(委託 tab 的兩段清單)每次 render 的 market 記錄 */
  orders: [] as string[],
}));

/** 三支葉子一律 **partial mock**(`importOriginal` 攤平後只換元件):這三個模組除了元件
 *  本身還 re-export 別的東西 —— `PriceLadder` 模組帶 `TRADE_KINDS` / `type TradeKind`
 *  (`RightRail` 直接 import 它)、`CapitalOrdersList` 模組帶 `isFutMarket`。全量 mock
 *  會把它們一起吃掉,症狀是同一棵樹上某個看似無關的地方拿到 `undefined`,而錯誤訊息
 *  指向的是那個地方、不是這裡。 */
vi.mock("@/components/stock/PriceLadder", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/components/stock/PriceLadder")>()),
  PriceLadder: ({
    code,
    name,
    book,
    last,
    meta,
  }: {
    code: unknown;
    name: unknown;
    book: unknown;
    last: unknown;
    meta: unknown;
  }) => {
    hoisted.ladder.push({ code, name, book, last, meta });
    return <div data-testid="ladder-stub" />;
  },
}));

vi.mock("@/components/futures/FuturesLadder", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/components/futures/FuturesLadder")>()),
  FuturesLadder: ({ state, contractLabel }: { state: unknown; contractLabel: unknown }) => {
    hoisted.futures.push({ state, contract: contractLabel });
    return <div data-testid="fut-ladder-stub" />;
  },
}));

vi.mock("@/components/capital/CapitalOrdersList", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/components/capital/CapitalOrdersList")>()),
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

/** 自選清單(換股案要點得到第二檔)。`9101` / `9102` 兩檔的 snapshot 恆 404 —— 用途見
 *  「snapshot 未到就換股」那條案例。 */
const WATCH_CODES = ["2330", "2454", "9101", "9102"];
/** snapshot 恆 404 的兩檔:`accum` 全程停在 null(FakeWS 不發 onopen → `scheduleRetry`
 *  的 `wsOpen` 那道直接早退,不會有重試 timer 在背景亂打)。 */
const NO_SNAPSHOT = ["9101", "9102"];
/** 股名**跟著 code 走**:換股案要斷言的是「新 code + 新 meta.name 一起到」,
 *  兩檔同名的話漏傳 meta 也照樣綠。 */
const STOCK_NAMES: Record<string, string> = { "2330": "台積電", "2454": "聯發科" };

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
    meta: {
      name: STOCK_NAMES[code] ?? code,
      ref: 2_320_000,
      upper: 2_550_000,
      lower: 2_090_000,
      y_vol: 100,
    },
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
      return new Response(JSON.stringify({ groups: [{ name: "自選", codes: WATCH_CODES }] }));
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
      if (NO_SNAPSHOT.includes(code)) {
        return new Response(JSON.stringify({ detail: { error: "NO_DATA" } }), { status: 404 });
      }
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
  hoisted.futures.length = 0;
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

/** 期貨葉子 / 個股葉子最後一次 render 拿到的 props。**刻意不包 `waitFor`**:waitFor 會
 *  重試到通過為止,「中間有一幀掛著舊值」這種 stale 症狀正好被它整個蓋掉 —— 而那就是
 *  deps 漏一項的實際樣態。 */
function lastFut(): { state: FuturesProductState | null; contract: unknown } | undefined {
  const rec = hoisted.futures.at(-1);
  return rec === undefined
    ? undefined
    : { state: rec.state as FuturesProductState | null, contract: rec.contract };
}

function lastLadder() {
  return hoisted.ladder.at(-1);
}

/** 期貨腿推兩則**連號**訊息(seq 1 / 2,接續 snapshot 的 seq 0)。
 *
 *  呼叫端的 `futStateCalls() === 1` 自檢證明的是「這兩則都**沒有**觸發全量對齊」
 *  = 它們確實被當成連號吃下,計次因此沒有被 refetch 汙染;它**不能**證明訊息真的
 *  送進了 hook —— url 打錯 / onmessage 沒掛上 / type 名改掉的世界裡,計次一樣是 1。
 *  那件事由 `expectFuturesDelivered()` 的跳號訊息負責。 */
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

/** **delivery 自檢**:推一則故意跳號的期貨訊息(seq 99)→ `applyFuturesMsg` 必定判跳號
 *  → 同步再打一次 `/api/futures/state`。計次由 `before` 變成 `before + 1` 才代表整條
 *  路徑(FakeWS url → onmessage → hook handler)是活的。
 *
 *  非有它不可:上面那些「計次沒變 + 葉子沒重畫」的斷言,在「訊息根本沒進到 hook」的
 *  世界裡是一模一樣的綠 —— 而那個世界只要 ws 路徑字串、`type` 名或 handler 掛載
 *  任一處改掉就會發生,memo 邊界的守門會就此靜默失效。 */
function expectFuturesDelivered(before: number): void {
  act(() => {
    send("/ws/futures", { type: "futures", seq: 99, product: "TXF", state: futProduct(21_070_000) });
  });
  expect(futStateCalls()).toBe(before + 1);
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
    // 自檢:期貨訊息真的送得進 hook(見 expectFuturesDelivered 說明)
    expectFuturesDelivered(1);
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
    const book = lastLadder()?.book as StockBook;
    expect(book.bids[0]?.[0]).toBe(2_376_000);
    expect(book.asks[0]?.[0]).toBe(2_381_000);
    // 同一筆 ctx 內的 `meta` 也要一起到:`meta` 餵的是漲跌停 / 昨收(閃電梯的價格帶與
    // 貼停價都吃它),而 book 對了 meta 掉了在畫面上只是梯子的價帶不對 —— 沒有訊號。
    expect((lastLadder()?.meta as StockMeta).name).toBe("台積電");
    expect(lastLadder()?.name).toBe("台積電");
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
    expectFuturesDelivered(1);
  });

  it("停在期貨 tab 時,期貨推播讓右欄期貨葉子拿到新現價 + 新五檔(futuresCtx deps 完整)", async () => {
    window.localStorage.setItem("copycat-tab", "futures");
    renderApp();
    await screen.findByTestId("fut-ladder-stub");
    await waitFor(() => expect(futStateCalls()).toBe(1));
    await settle();
    await settle();

    // 自檢:全量對齊已落地(葉子拿到的是 snapshot 的值,不是 null)—— 少了這道,
    // 下面的「值換了」在「null → 有值」的世界裡也是綠的,而那與 memo deps 無關。
    expect(lastFut()?.state?.p).toBe(21_042_000);
    expect(lastFut()?.contract).toBe("TXFH6");
    const before = hoisted.futures.length;

    pushFuturesTicks();

    // 自檢:兩則都被當連號吃下(跳號會走全量對齊那條路,重繪與 memo 無關)
    expect(futStateCalls()).toBe(1);
    expect(hoisted.futures.length).toBeGreaterThan(before);
    // `futuresCtx` 的 deps 掉了 `futProd` 的樣態:右欄期貨梯掛著開盤那一刻的現價與五檔,
    // 而中間主區的期貨頁照樣跳動 —— 兩邊對不起來,但沒有任何錯誤訊號,送出去的是真錢單。
    const st = lastFut()?.state;
    expect(st?.p).toBe(21_060_000);
    expect(st?.bids[0]?.[0]).toBe(21_059_000);
  });

  it("停在期貨 tab 時,個股流的自選報價不重畫期貨葉子(反向串擾)", async () => {
    window.localStorage.setItem("copycat-tab", "futures");
    renderApp();
    await screen.findByTestId("fut-ladder-stub");
    await waitFor(() => expect(futStateCalls()).toBe(1));
    await settle();
    await settle();

    const before = hoisted.futures.length;
    expect(before).toBeGreaterThan(0);

    // 用 `watchlist_quote` 而不是 `tick`:期貨 tab 下主檔是 null(App 的 D-16 閘門),
    // `tick` 在 hook 內就被 instrumentKey 比對丟掉 —— 連 App 都不會重繪,「+0」變成
    // 「什麼都沒發生」的空綠。`watchlist_quote` 則無條件 `setWatchlist`(側欄報價每秒
    // 一批),setState 落在 App 層 = 整棵樹確實重繪一輪,才是要擋的那件事。
    for (const p of [2_390_000, 2_391_000]) {
      act(() => {
        send("/ws/stock", {
          type: "watchlist_quote",
          code: "2330",
          p,
          chg_pct: 1.2,
          vol: 10,
          ref: 2_320_000,
          upper: 2_550_000,
          lower: 2_090_000,
          no_data: false,
          trial: false,
        });
      });
    }

    expect(hoisted.futures.length).toBe(before);
  });

  it("換主檔 → 右欄葉子拿到新 code 與新股名(stockCtx 跟得上換股)", async () => {
    window.localStorage.setItem("copycat-tab", "stock");
    window.localStorage.setItem("copycat-stock-main-code", "2330");
    renderApp();
    await screen.findByTestId("ladder-stub");
    await settle();
    expect(lastLadder()?.code).toBe("2330");

    fireEvent.click(await screen.findByTestId("wl-select-2454")); // a11y 批:選取改內層 button
    await waitFor(() =>
      expect(fetchUrls().some((u) => u.includes("/api/stock/state/2454"))).toBe(true),
    );
    await settle();
    await settle();

    // **讀 stub 記錄的最後一筆,不包 waitFor**:waitFor 會重試到通過為止,
    // 「換股後還有一幀掛著舊股的簿 / 舊股名」正好被它蓋掉。
    const last = lastLadder();
    expect(last?.code).toBe("2454");
    expect(last?.name).toBe("聯發科");
    expect((last?.meta as StockMeta).name).toBe("聯發科");
  });

  it("snapshot 未到就換主檔 → 右欄葉子仍立刻指認新 code(stockCtx deps 含 stockCode)", async () => {
    // 兩檔的 snapshot 都是 404 → `accum` 全程停在 null、identity 不換。
    // 這正是 `stockCtx` 的 deps 只剩 `[stkfutContract, accum]` 時**唯一**會露餡的場景:
    // 有 snapshot 的換股路徑上 `setAccum(null)` 自己就把 memo 撞開了,漏掉 `stockCode`
    // 也照樣收斂到新值(只有中間一幀是舊的);而這裡沒有那個副作用,右欄會**永久**
    // 掛著上一檔的股號 —— 閃電梯標題寫著 9101、送出去的卻是 9102。
    window.localStorage.setItem("copycat-tab", "stock");
    window.localStorage.setItem("copycat-stock-main-code", "9101");
    renderApp();
    await screen.findByTestId("ladder-stub");
    await settle();
    await settle();
    // 自檢:snapshot 真的沒到(有到的話下面測的是別的東西)
    expect(lastLadder()?.meta).toBeNull();
    expect(lastLadder()?.code).toBe("9101");

    fireEvent.click(await screen.findByTestId("wl-select-9102")); // a11y 批:選取改內層 button
    await settle();
    await settle();

    expect(lastLadder()?.code).toBe("9102");
    expect(lastLadder()?.meta).toBeNull();
  });
});
