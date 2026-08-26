/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type React from "react";
import { GroupGridView } from "@/components/stock/GroupGridView";
import { useStockGroup } from "@/hooks/useStockGroup";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { ymdOf } from "@/lib/ladder-lots";
import type { Group } from "@/lib/watchlist-model";
import type { CapitalOrder, CapitalPosition } from "@/types";

/** review A6-1 的 regression lock:卡片 `memo` 有沒有真的擋下重畫。
 *
 *  這件事**在畫面上完全看不出來** —— memo 失效只是每秒多算 50 次分時幾何(最多
 *  271 格),圖照畫、值照對。失效的典型原因也不在卡片自己身上:父層每秒隨 `quotes`
 *  re-render,傳下去的 `onPick` 若是 inline arrow,`memo` 的比較每一輪都不會過。
 *
 *  量法 = 把卡片內的圖換成計次替身。**獨立檔**:`vi.mock` 是檔案級 + hoisted,
 *  與同目錄那份「要看到真 svg」的測試不能共存(frontend-testing skill 的 lazy 三坑同理)。 */


/** 測試用外殼:圖牆自 F2 起受控(「現在看哪一組」唯一持有者是 StockPage 的 `useStockGroup`),
 *  這裡以同一支 hook 扮演 StockPage,既有「記住的群組」語意(localStorage)一字不改。 */
function Grid(props: Omit<React.ComponentProps<typeof GroupGridView>, "selectedGroup" | "onSelectGroup">) {
  const { picked, select } = useStockGroup();
  return <GroupGridView {...props} selectedGroup={picked} onSelectGroup={select} />;
}
const hoisted = vi.hoisted(() => ({
  renders: [] as (number | null)[],
  /** per-code 的 render 記錄(cr1 B-p2-5 用):`renders` 只留 `liveP`,量不出「哪一張卡
   *  重畫了」也量不出成交點有沒有真的傳到那張卡。 */
  byCode: [] as { code: string; fills: number }[],
}));

vi.mock("@/components/stock/CardIntradayChart", () => ({
  CardIntradayChart: ({
    code,
    liveP,
    fills,
  }: {
    code: string;
    liveP: number | null;
    fills: readonly unknown[];
  }) => {
    hoisted.renders.push(liveP);
    hoisted.byCode.push({ code, fills: fills.length });
    return <span data-testid="mini-stub" />;
  },
}));

const GROUPS: Group[] = [{ name: "半導體", codes: ["2330", "2317"] }];

function quote(over: Partial<WatchlistQuote> = {}): WatchlistQuote {
  return {
    p: null,
    chg_pct: null,
    vol: null,
    ref: null,
    upper: null,
    lower: null,
    no_data: false,
    trial: false,
    ...over,
  };
}

function state() {
  return {
    minutes: { "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 } },
    meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: 1 },
    no_data: false,
    backfilling: false,
  };
}

/** 今日一筆 2330 現股成交(cr1 B-p2-5)。`date` 走 `ymdOf(new Date())` —— 寫死日期的話
 *  這條會在隔天靜默變成「昨日終態單」而被日期界濾掉,測試恆綠。 */
function filledOrder(): CapitalOrder {
  return {
    seq_no: "S1",
    stock_no: "2330",
    name: "台積電",
    market: "TS",
    buy_sell: "B",
    flag_label: "現股",
    book_no: "A1",
    status_raw: "0",
    status_label: "全部成交",
    price: 2380,
    avg_fill_price: 2380,
    order_qty: 1,
    filled_qty: 1,
    unit: "張",
    date: ymdOf(new Date()),
    time: "09:00:30",
    pre_order: false,
    error_msg: null,
    actionable: false,
    price_type: null,
    raw: "",
  };
}

/** 本輪的委託列表(預設空:既有兩案不該因為多了一條路由而改變行為)。 */
let orders: CapitalOrder[] = [];
/** 本輪的部位列(預設空,同上)。 */
let positions: CapitalPosition[] = [];

beforeEach(() => {
  hoisted.renders.length = 0;
  hoisted.byCode.length = 0;
  orders = [];
  positions = [];
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/capital/orders")) {
        return new Response(JSON.stringify({ orders }));
      }
      if (u.includes("/api/capital/positions")) {
        return new Response(JSON.stringify({ positions }));
      }
      const codes = new URL(u, "http://x").searchParams.get("codes") ?? "";
      const picked: Record<string, unknown> = {};
      for (const c of codes.split(",").filter(Boolean)) picked[c] = state();
      return new Response(JSON.stringify({ states: picked }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("GroupGridView 卡片 memo(review A6-1)", () => {
  it("只有一檔報價變 → 只有那張卡片重畫(父層每次都給新的 onPick)", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const q1 = { "2330": quote({ p: 2_380_000 }), "2317": quote({ p: 2_000_000 }) };
    // 每次都現做一個 inline arrow —— 正是 StockPage 的寫法,也是 memo 最容易破功的地方
    const ui = (quotes: Record<string, WatchlistQuote>) => (
      <QueryClientProvider client={client}>
        <Grid groups={GROUPS} quotes={quotes} onPick={() => {}} active={null} />
      </QueryClientProvider>
    );

    const { rerender } = render(ui(q1));
    await waitFor(() => expect(screen.getAllByTestId("mini-stub")).toHaveLength(2));
    const before = hoisted.renders.length;

    // 只換 2317 那一格(`setWatchlist` 是 `{...prev, [code]: q}` → 其餘 entry 保持同參照)
    rerender(ui({ ...q1, "2317": quote({ p: 2_010_000 }) }));

    expect(hoisted.renders.length).toBe(before + 1);
    expect(hoisted.renders[hoisted.renders.length - 1]).toBe(2_010_000);
  });

  it("報價完全沒變(只是父層 re-render)→ 零重畫", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const q1 = { "2330": quote({ p: 2_380_000 }), "2317": quote({ p: 2_000_000 }) };
    const ui = () => (
      <QueryClientProvider client={client}>
        <Grid groups={GROUPS} quotes={q1} onPick={() => {}} active={null} />
      </QueryClientProvider>
    );
    const { rerender } = render(ui());
    await waitFor(() => expect(screen.getAllByTestId("mini-stub")).toHaveLength(2));
    const before = hoisted.renders.length;
    rerender(ui());
    expect(hoisted.renders.length).toBe(before);
  });

  /** cr1 B-p2-5 [lock]:**有成交**的那張卡 memo 還在不在。`fillsByCode` 每 render 現折的話
   *  它回的是新 Map + 新陣列 → 有成交的 code 每輪 `fills` 都是新 identity,那張卡每秒
   *  重畫(無成交的卡拿的是模組常數 `EMPTY_FILLS`,照樣被 memo 擋住)。
   *  失效只有那幾張「我今天有下單」的卡會掉幀 —— 正是盤中最常盯的那幾張,而畫面看不出來。
   *  量法 = 拿「無成交卡」當同輪對照組:兩者增量相同才算 memo 沒被成交點打穿。 */
  it("有成交的卡:quotes 換 identity 兩輪 → 重畫次數與無成交卡相同(fills identity 穩定)", async () => {
    orders = [filledOrder()];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const q1 = { "2330": quote({ p: 2_380_000 }), "2317": quote({ p: 2_000_000 }) };
    const ui = (quotes: Record<string, WatchlistQuote>) => (
      <QueryClientProvider client={client}>
        <Grid groups={GROUPS} quotes={quotes} onPick={() => {}} active={null} />
      </QueryClientProvider>
    );
    const { rerender } = render(ui(q1));
    // 等成交點真的抵達 2330 那張卡(orders query settle 後才有);自檢:沒抵達的話
    // 兩張卡都是 EMPTY_FILLS,下面量的東西與成交點無關而恆綠
    await waitFor(() =>
      expect(hoisted.byCode.some((r) => r.code === "2330" && r.fills === 1)).toBe(true),
    );
    expect(hoisted.byCode.some((r) => r.code === "2317" && r.fills > 0)).toBe(false);
    const count = (code: string) => hoisted.byCode.filter((r) => r.code === code).length;
    const [b2330, b2317] = [count("2330"), count("2317")];
    // `quotes` 換整份 identity、每一格 entry 維持同參照(= `setWatchlist` 每秒的樣態)
    rerender(ui({ ...q1 }));
    rerender(ui({ ...q1 }));
    expect(count("2330") - b2330).toBe(count("2317") - b2317);
  });
  /** batch3 R3 SC-4 [lock]:**有倉**的那張卡 memo 還在不在。`positionsByCode` 每 render
   *  現折的話它回的是新 Map + 新陣列 → 有倉的 code 每輪 `positions` 都是新 identity,
   *  那張卡每秒重畫(無倉的卡拿的是模組常數 `EMPTY_POSITIONS`,照樣被 memo 擋住)。
   *  失效只有「我今天有部位」的那幾張會掉幀 —— 正是盯得最兇的那幾張,而畫面看不出來。
   *  量法同上:拿無倉卡當同輪對照組,兩者增量相同才算 memo 沒被倉位打穿。 */
  it("有倉的卡:quotes 換 identity 兩輪 → 重畫次數與無倉卡相同(positions identity 穩定)", async () => {
    positions = [
      {
        market: "sec",
        stock_no: "2330",
        qty: 3,
        name: "台積電",
        avg_price: 2350,
        kind: "cash",
        pnl_base: null,
        pnl_base_price: null,
        pnl_cost: null,
        avg_source: null,
        today_qty: 0,
        code: "2330",
      },
    ];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const q1 = { "2330": quote({ p: 2_380_000 }), "2317": quote({ p: 2_000_000 }) };
    const ui = (quotes: Record<string, WatchlistQuote>) => (
      <QueryClientProvider client={client}>
        <Grid groups={GROUPS} quotes={quotes} onPick={() => {}} active={null} />
      </QueryClientProvider>
    );
    const { rerender } = render(ui(q1));
    // 自檢:倉位真的抵達 2330 那張卡(positions query settle 後才有)。沒抵達的話
    // 兩張卡都是 EMPTY_POSITIONS,下面量的東西與倉位無關而恆綠
    await screen.findByTestId("group-pos-2330");
    expect(screen.queryByTestId("group-pos-2317")).toBeNull();
    const count = (code: string) => hoisted.byCode.filter((r) => r.code === code).length;
    const [b2330, b2317] = [count("2330"), count("2317")];
    rerender(ui({ ...q1 }));
    rerender(ui({ ...q1 }));
    expect(count("2330") - b2330).toBe(count("2317") - b2317);
  });
});
