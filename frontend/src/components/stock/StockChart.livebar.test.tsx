/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockChart } from "@/components/stock/StockChart";
import type { Bar } from "@/lib/candle";
import type { MinuteAgg, StockAccum } from "@/lib/stock-accum";
import { isoLocalDate } from "@/lib/trading-calendar";

/** 即時末根接線(spec #214 seam (a);T1 #215 分 K / T2 #216 日 K)。
 *
 *  只假造 `Date`(不假造 timer:RTL `waitFor` 在 vitest 下偵測不到 fake timers,見 frontend-testing skill)。
 *  盤中時刻固定 09:06:30,`today` 由它動態算 —— 寫死日期會在隔天靜默轉紅。 */

const NOW = new Date(2026, 8, 8, 9, 6, 30); // 2026-09-08 09:06:30(週二,交易日)
const TODAY = isoLocalDate(NOW);
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
