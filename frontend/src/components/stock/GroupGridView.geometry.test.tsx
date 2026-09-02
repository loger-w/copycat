/** @vitest-environment jsdom */
/** SC-6(d):hover 不重算幾何。
 *
 *  卡片上的圖與單檔頁是同一份渲染碼,而那份碼的 hover 每個 mousemove 都會 setState ——
 *  少了 `useMemo` 護欄,圖牆上 16 張卡片時滑過任何一張都會重算一次分時幾何(最多 271
 *  格 × 每次 mousemove)。**畫面上完全看不出來**:圖照畫、值照對,只是掉幀。
 *
 *  量法 = 把 `buildIntradayGeometry` 換成計次的同一份實作(`importOriginal` 保留行為)。
 *  `vi.mock` 是檔案級 + hoisted → 獨立檔。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type React from "react";
import { GroupGridView } from "@/components/stock/GroupGridView";
import { useStockGroup } from "@/hooks/useStockGroup";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { buildIntradayGeometry } from "@/lib/stock-intraday-svg";
import { emitTicks } from "@/lib/tick-stream";
import type { Group } from "@/lib/watchlist-model";
import { wrap } from "@/test-utils";


/** 測試用外殼:圖牆自 F2 起受控(「現在看哪一組」唯一持有者是 StockPage 的 `useStockGroup`),
 *  這裡以同一支 hook 扮演 StockPage,既有「記住的群組」語意(localStorage)一字不改。 */
function Grid(props: Omit<React.ComponentProps<typeof GroupGridView>, "selectedGroup" | "onSelectGroup">) {
  const { picked, select } = useStockGroup();
  return <GroupGridView {...props} selectedGroup={picked} onSelectGroup={select} />;
}
vi.mock("@/lib/stock-intraday-svg", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/stock-intraday-svg")>();
  return { ...actual, buildIntradayGeometry: vi.fn(actual.buildIntradayGeometry) };
});

const CODES = ["2330", "2317", "2454", "2308"];
const GROUPS: Group[] = [{ name: "半導體", codes: CODES }];

class FakeResizeObserver {
  private readonly cb: ResizeObserverCallback;

  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }

  observe(node: Element): void {
    this.cb(
      [{ target: node, contentRect: { width: 300, height: 200 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve(): void {}

  disconnect(): void {}
}

function state() {
  return {
    minutes: {
      "540": { c: 2_380_000, v: 10, i: 3, o: 7, u: 0 },
      "541": { c: 2_390_000, v: 6, i: 2, o: 4, u: 0 },
    },
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    no_data: false,
    backfilling: false,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/stock/overlay/")) {
        return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
      }
      const picked: Record<string, unknown> = {};
      for (const c of CODES) picked[c] = state();
      return new Response(JSON.stringify({ states: picked }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers(); // 只假造 Date 的測試也要還原,否則外溢到同檔後續 it
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function quote(p: number): WatchlistQuote {
  return {
    p,
    chg_pct: 2.59,
    vol: 12_000,
    ref: null,
    upper: null,
    lower: null,
    no_data: false,
    trial: false,
    disposition: false,
  };
}

/** 保留**同一個** QueryClient 的 rerender。`wrap` 每次呼叫都建新 client —— 用它 rerender
 *  會連 group-state 的 cache 一起換掉,`snap` 跟著換 identity,量到的就不是「報價換了
 *  一份新物件」這件事,而是「快取被清掉」。 */
function renderGrid(quotes: Record<string, WatchlistQuote>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (q: Record<string, WatchlistQuote>) => (
    <QueryClientProvider client={client}>
      <Grid groups={GROUPS} quotes={q} onPick={vi.fn()} active={null} />
    </QueryClientProvider>
  );
  const { rerender } = render(ui(quotes));
  return { rerender: (q: Record<string, WatchlistQuote>) => rerender(ui(q)) };
}

describe("GroupGridView hover 不重算幾何(SC-6d)", () => {
  it("4 張卡掛好後,對其中一張連發 3 個 mousemove → 幾何重算次數不變", async () => {
    wrap(<Grid groups={GROUPS} quotes={{}} onPick={vi.fn()} active={null} />);
    for (const code of CODES) {
      const card = await screen.findByTestId(`group-card-${code}`);
      // 錨點:卡片上真的是**單檔同款**那張圖(有 role=img 的主圖),不是舊 mini 圖 ——
      // 少了這條,「hover 沒重算」在根本沒有 hover 事件的元件上也會綠
      await waitFor(() => expect(card.querySelector('svg[role="img"]')).toBeTruthy());
    }
    const counted = vi.mocked(buildIntradayGeometry);
    const before = counted.mock.calls.length;
    // 計次自檢:mock 沒接上時「次數沒變」是 0 → 0,恆綠而毫無意義
    expect(before).toBeGreaterThan(0);

    const svg = screen.getByTestId("group-card-2330").querySelector('svg[role="img"]')!;
    for (const clientX of [10, 40, 90]) {
      fireEvent.mouseMove(svg, { clientX, clientY: 20 });
    }

    expect(counted.mock.calls.length).toBe(before);
  });

  it("每秒報價重送(新物件、值相同)→ 幾何重算次數不變(accum useMemo 護欄)", async () => {
    // 每秒 `watchlist_quote` 進來時 `quotes` 是**整份新物件**(WS handler 重建 record),
    // 即使某一檔的價格一格都沒動 —— `quotes[code]` 是新 identity,memo 擋不住,
    // 卡片必然重 render。這時擋在中間的只剩 `CardIntradayChart` 的 accum useMemo:
    // 少了它,accum 每輪新 identity → core 內吃 accum 的幾何 useMemo 全部重算,
    // 16 張卡每秒重算 16 次 271 格。**畫面完全看不出來**,只是掉幀。
    // 時鐘鎖在窗內(只假造 Date、不假造 timer:RTL 的 waitFor 偵測不到 vitest fake
    // timers,連 setInterval 一起假造會讓 findBy* 直接吊死)。窗外時 `extendMinutes`
    // **原樣回傳**傳入的 Map → `accum.minutes` identity 不變,護欄拿掉也不會重算,
    // 這條測試會靜默變成永遠綠的假證據。
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 7, 17, 10, 30, 0));
    const { rerender } = renderGrid({});
    for (const code of CODES) {
      const card = await screen.findByTestId(`group-card-${code}`);
      await waitFor(() => expect(card.querySelector('svg[role="img"]')).toBeTruthy());
    }
    const counted = vi.mocked(buildIntradayGeometry);

    // 自檢:成交**真的**通到幾何(tick → 該檔 accum 換 identity → 重算)。少了這一段,
    // 下面那句「次數不變」在卡片根本沒接上 tick 匯流排時也會綠。
    // T4 #185 起圖的末點由 tick 驅動(fixture 無 seq → 播種 seq 0 → 第一筆 seq 1 連續);
    // 舊版是拿每秒報價 `quotes[code].p` 延伸,那條路已明文退役。
    const beforeLive = counted.mock.calls.length;
    expect(beforeLive).toBeGreaterThan(0);
    act(() => {
      emitTicks([{ code: "2330", t: "10:30:00.000", p: 2_400_000, q: 1, side: "outer", seq: 1 }]);
    });
    expect(counted.mock.calls.length).toBeGreaterThan(beforeLive);

    // 每秒報價重送(新物件;值變不變都一樣):卡片頭重畫,圖的 accum identity 不變 →
    // 幾何零重算。舊版「值變 → 重算」的自檢在此反轉為「值變也不重算」。
    const before = counted.mock.calls.length;
    rerender({ "2330": quote(2_400_000) });
    rerender({ "2330": quote(2_410_000) });

    expect(counted.mock.calls.length).toBe(before);
  });
});
