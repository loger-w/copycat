/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockPage } from "@/components/stock/StockPage";
import type { StockStreamState } from "@/hooks/useStockStream";
import type { StockAccum } from "@/lib/stock-accum";

// 🔴-3:code / 資料流已上提到 App(D-3)→ 本元件改吃 props,不再自建 WS、不再讀 localStorage。
// 「TC4 斷線告警列(W-B5)」文案斷言原本掛在此檔的 WS 驅動路徑上,改以 props 直接驅動,
// 文案字串逐字不變;「選檔後渲染委託/部位」已逐條搬到 RightRail.test.tsx。

const ACCUM = {
  code: "2330",
  seq: 1,
  last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
  vwap: 2_380_000,
  cumInner: 0,
  cumOuter: 1,
  minutes: new Map([[540, { c: 2_380_000, v: 1, i: 0, o: 1, u: 0 }]]),
  ticks: [{ t: "09:00:01.000", p: 2_380_000, q: 1, side: "outer" }],
  book: { bids: [[2_375_000, 5]], asks: [[2_380_000, 3]] },
  meta: {
    name: "台積電",
    ref: 2_320_000,
    upper: 2_550_000,
    lower: 2_090_000,
    y_close: 2_320_000,
    y_vol: 100,
  },
  noData: false,
  backfilling: null,
} as unknown as StockAccum;

function stream(over: Partial<StockStreamState> = {}): StockStreamState {
  return {
    accum: ACCUM,
    watchlist: {},
    status: { tc4: "up", backfilling: null },
    stkfut: null,
    wsStatus: "open",
    ...over,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (String(url).includes("/api/stock/watchlist")) {
        return new Response(JSON.stringify({ groups: [{ name: "自選", codes: ["2330"] }] }));
      }
      if (String(url).includes("/api/stock/bars")) {
        return new Response(JSON.stringify({ bars: [] }));
      }
      if (String(url).includes("/api/stock/overlay")) {
        return new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }));
      }
      return new Response(JSON.stringify({}), { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("StockPage", () => {
  it("未選檔時顯示提示;自選側欄仍渲染", async () => {
    wrap(<StockPage code={null} onSelect={vi.fn()} stream={stream({ accum: null })} />);
    await waitFor(() => expect(screen.getByText("2330")).toBeTruthy()); // 側欄
    expect(screen.getByText(/從自選清單選擇/)).toBeTruthy();
  });

  it("TC4 斷線顯示告警列(文案不變)", () => {
    wrap(
      <StockPage
        code="2330"
        onSelect={vi.fn()}
        stream={stream({ status: { tc4: "down", backfilling: null } })}
      />,
    );
    expect(screen.getByText(/達錢 4 連線中斷,恢復後自動回補/)).toBeTruthy();
  });

  it("伺服器斷線顯示重連告警列(文案不變)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream({ wsStatus: "closed" })} />);
    expect(screen.getByText(/伺服器連線中斷,重連中…/)).toBeTruthy();
  });

  it("選檔後中間主區 = 圖表切換 + 五檔 + 明細(SC-6/SC-7)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    expect(screen.getByRole("button", { name: "江波圖" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "1分K" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "5分K" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "日K" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "買1 2375" })).toBeTruthy(); // 五檔(W-16:aria-label 格式是定位鍵)
    expect(screen.getByText("時間")).toBeTruthy(); // 明細表頭
  });

  it("中間不再渲染閃電梯 / 委託 / 部位(已移到右欄)", () => {
    wrap(<StockPage code="2330" onSelect={vi.fn()} stream={stream()} />);
    expect(screen.queryByRole("button", { name: "武裝" })).toBeNull();
    expect(screen.queryByText("委託")).toBeNull();
    expect(screen.queryByText("部位")).toBeNull();
  });
});
