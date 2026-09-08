/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockChart } from "@/components/stock/StockChart";
import type { Bar } from "@/lib/candle";
import type { MinuteAgg, StockAccum } from "@/lib/stock-accum";

/** 即時末根接線(spec #214 seam (a);T1 #215 分 K / T2 #216 日 K)。
 *
 *  只假造 `Date`(不假造 timer:RTL `waitFor` 在 vitest 下偵測不到 fake timers,見 frontend-testing skill)。
 *  盤中時刻固定 09:06:30;`TODAY` 是**字面量**不是 `isoLocalDate(NOW)` —— 與實作同源的話 codec 的 mutant
 *  兩邊同步漂、測試恆綠(frontend-testing「期望值寫字面量」;two-axis S-04)。Date 已凍住,不會隔天轉紅。 */

const NOW = new Date(2026, 8, 8, 9, 6, 30); // 2026-09-08 09:06:30(週二,交易日)
const TODAY = "2026-09-08";
const M = (hh: number, mm: number) => hh * 60 + mm;

function bar(t: string, o: number, h: number, l: number, c: number, v = 1): Bar {
  return { t, o, h, l, c, v };
}

const MINUTE_BARS: Bar[] = [
  bar(`${TODAY} 09:01`, 100_000, 101_000, 99_000, 100_500, 1),
  bar(`${TODAY} 09:02`, 100_500, 101_000, 100_000, 100_800, 1),
  bar(`${TODAY} 09:03`, 100_800, 101_500, 100_500, 101_000, 1),
  bar(`${TODAY} 09:04`, 101_000, 101_200, 100_900, 101_100, 1),
  bar(`${TODAY} 09:05`, 101_100, 105_000, 99_000, 104_000, 10),
];

function agg(c: number, v: number, h: number, l: number): MinuteAgg {
  return { c, v, i: 0, o: 0, u: v, h, l };
}

function accumOf(over: Partial<StockAccum> & { minutes: Map<number, MinuteAgg> }): StockAccum {
  return {
    code: "2330",
    seq: 1,
    last: { p: 103_000, t: "09:06:20.000", cum_vol: 21 },
    vwap: 102_000,
    ticks: [],
    vp: new Map(),
    book: { bids: [], asks: [] },
    meta: { name: "台積電", ref: 100_000, upper: 110_000, lower: 90_000, y_vol: 100 },
    noData: false,
    trial: false,
    disposition: false,
    tapeOmitted: false,
    high: 108_000,
    low: 99_000,
    amountMilli: 0,
    volume: 21,
    ...over,
  };
}

/** 09:05(→ 正式已有 09:05 那根的分鐘,跳過)/ 09:05 起點分(→ 09:06)/ 09:06 起點分(→ 09:07 進行中) */
const LIVE_MINUTES = new Map<number, MinuteAgg>([
  [M(9, 4), agg(104_000, 10, 105_000, 99_000)],
  [M(9, 5), agg(106_000, 5, 107_000, 103_000)],
  [M(9, 6), agg(103_000, 7, 108_000, 102_000)],
]);

let client: QueryClient;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  window.localStorage.clear();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/stock/bars")) {
        return new Response(JSON.stringify({ bars: MINUTE_BARS, status: "ok" }));
      }
      if (u.includes("/api/capital/fills")) return new Response(JSON.stringify({ fills: [] }));
      return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function mount(accum: StockAccum, code = "2330") {
  const ui = (a: StockAccum) => (
    <QueryClientProvider client={client}>
      <StockChart accum={a} code={code} />
    </QueryClientProvider>
  );
  const r = render(ui(accum));
  return { ...r, rerenderWith: (a: StockAccum) => r.rerender(ui(a)) };
}

const readout = () => screen.getByTestId("chart-readout").textContent ?? "";

describe("StockChart 即時末根 —— 分 K(T1 #215)", () => {
  it("3 分 K:最後一根 = 進行中的 09:09 桶(accum 折出),不是正式末根 09:05 所在的 09:06 桶", async () => {
    mount(accumOf({ minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "3分K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    await waitFor(() => expect(readout()).toContain(`${TODAY} 09:09`));
    // 09:09 桶只含補的 09:07 那根:o = 補的 09:06 的 c(106)、h 108、l 102、c 103、量 7
    expect(readout()).toContain("開 106");
    expect(readout()).toContain("高 108");
    expect(readout()).toContain("低 102");
    expect(readout()).toContain("收 103");
    expect(readout()).toContain("量 7");
  });

  it("再一筆成交(accum 換 identity)→ 末根的收 / 高 / 量跟著變,正式段不動", async () => {
    const { rerenderWith } = mount(accumOf({ minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "3分K" }));
    await waitFor(() => expect(readout()).toContain("收 103"));
    const next = new Map(LIVE_MINUTES);
    next.set(M(9, 6), agg(109_000, 9, 109_500, 102_000));
    rerenderWith(accumOf({ minutes: next, last: { p: 109_000, t: "09:06:40.000", cum_vol: 23 } }));
    await waitFor(() => expect(readout()).toContain("收 109"));
    expect(readout()).toContain("高 109.5");
    expect(readout()).toContain("量 9");
    expect(readout()).toContain(`${TODAY} 09:09`);
  });

  it("accum 是別檔的(換股 race)→ 不補,末根 = 正式 09:05 所在的 09:06 桶", async () => {
    mount(accumOf({ code: "2317", minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "3分K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    await waitFor(() => expect(readout()).toContain(`${TODAY} 09:06`));
    expect(readout()).not.toContain("09:09");
    expect(readout()).toContain("收 104");
  });

  it("09:00 前(牆鐘 08:59)不補:凌晨 accum 仍是昨天的,不得貼成今天", async () => {
    vi.setSystemTime(new Date(2026, 8, 8, 8, 59, 0));
    mount(accumOf({ minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "1分K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    await waitFor(() => expect(readout()).toContain(`${TODAY} 09:05`));
    expect(readout()).not.toContain("09:07");
  });
});

/** 日 K fixture:`tf=D` 回昨天 + 今天半成品(開圖在 09:00 後,DK 有今日列);`tf=1` 回 MINUTE_BARS
 *  (今天首根 09:01 的 o = 100 → `dayOpen`,只在 append 路徑用到)。 */
const DAILY_BARS: Bar[] = [
  bar("2026-09-05", 90_000, 92_000, 89_000, 91_000, 300),
  bar(TODAY, 100_000, 101_000, 99_000, 100_500, 5),
];

function stubBars(daily: Bar[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/stock/bars")) {
        return new Response(JSON.stringify({ bars: u.includes("tf=D") ? daily : MINUTE_BARS, status: "ok" }));
      }
      if (u.includes("/api/capital/fills")) return new Response(JSON.stringify({ fills: [] }));
      return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
    }),
  );
}

describe("StockChart 即時末根 —— 日 K(T2 #216)", () => {
  it("今天那根:開 = 正式(100)、高 / 低 / 收 = accum(108 / 99 / 103)、量 = 當日累積量(21)", async () => {
    stubBars(DAILY_BARS);
    mount(accumOf({ minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(readout()).toContain("收 103"));
    expect(readout()).toContain(TODAY);
    expect(readout()).toContain("開 100");
    expect(readout()).toContain("高 108");
    expect(readout()).toContain("低 99");
    expect(readout()).toContain("量 21");
  });

  it("DK 還沒有今日列(09:00 前開圖)→ 補一根今天,開 = 今日首根 1 分 K 的 o(100.5 那根之前的 100)", async () => {
    stubBars(DAILY_BARS.slice(0, 1));
    const { rerenderWith } = mount(accumOf({ minutes: LIVE_MINUTES }));
    // 先進 1 分 K 讓今日 1 分 K 進 cache(dayOpen 的來源),再切日 K
    fireEvent.click(screen.getByRole("radio", { name: "1分K" }));
    await waitFor(() => expect(readout()).toContain("09:07"));
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(readout()).toContain(`${TODAY}開 100`));
    expect(readout()).toContain("收 103");
    rerenderWith(accumOf({ minutes: LIVE_MINUTES, last: { p: 105_000, t: "09:06:50.000", cum_vol: 30 } }));
    await waitFor(() => expect(readout()).toContain("收 105"));
    expect(readout()).toContain("量 30");
  });

  it("08:59 不補:末根仍是昨天(2026-09-05)", async () => {
    vi.setSystemTime(new Date(2026, 8, 8, 8, 59, 0));
    stubBars(DAILY_BARS.slice(0, 1));
    mount(accumOf({ minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(readout()).toContain("2026-09-05"));
    expect(readout()).toContain("收 91");
  });

  it("定稿閘:日 K 是 14:00 界後抓回來的 → 不蓋,今天那根 = 正式定稿值(收 100.5)", async () => {
    vi.setSystemTime(new Date(2026, 8, 8, 14, 5, 0));
    stubBars(DAILY_BARS);
    mount(accumOf({ minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(readout()).toContain(TODAY));
    expect(readout()).toContain("收 100.5");
    expect(readout()).not.toContain("收 103");
  });

  it("13:50 抓的半成品,牆鐘過 14:00 後(14:01 重抓還沒成功)仍以 accum 蓋 —— 失敗不退回舊值", async () => {
    vi.setSystemTime(new Date(2026, 8, 8, 13, 50, 0));
    stubBars(DAILY_BARS);
    const { rerenderWith } = mount(accumOf({ minutes: LIVE_MINUTES }));
    fireEvent.click(screen.getByRole("radio", { name: "日K" }));
    await waitFor(() => expect(readout()).toContain("收 103"));
    vi.setSystemTime(new Date(2026, 8, 8, 14, 5, 0));
    rerenderWith(accumOf({ minutes: LIVE_MINUTES, last: { p: 103_500, t: "13:30:00.000", cum_vol: 40 } }));
    await waitFor(() => expect(readout()).toContain("收 103.5"));
    expect(readout()).toContain("量 40");
  });
});
