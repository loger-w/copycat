/** @vitest-environment jsdom */
/** N073:`fills` toggle **關態**時 `fillMarks` 必須是模組層常數 `EMPTY_MARKS`。
 *
 *  關著的圖每秒仍隨報價 / 每個 mousemove 重繪本元件;行內 `[]` 每輪新 identity →
 *  打穿 `ChartStatic` 的 `memo`,整層線圖跟著重建。症狀只是掉幀,**沒有任何斷言會紅**。
 *
 *  cr1 B-p2-3 當時 rejected 的理由是「關態沒有可計次函式」—— 那是就 `fill-marks` 這支
 *  lib 而言:關態確實不呼叫 `projectFills` / `fillTrianglePoints`(同檔 SC-9 的計次通道
 *  在關態恆為 0,量不到東西)。可計次的探針在別處:`ChartStatic` 的 **render body**
 *  (不在任何 `useMemo` 裡)無條件呼叫 `stock-intraday-svg::buildVwapLabel`。
 *  探針落在 useMemo 內就會被它擋住 → mutant 全綠(frontend-testing 的 memo 計次教訓)。
 *
 *  `vi.mock` 是檔案級 + hoisted,故獨立成檔;`...actual` 保真(漏掉任何常數會讓座標全 NaN)。
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IntradayChartCore } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { FillPoint } from "@/lib/fill-marks";
import { fromSnapshot } from "@/lib/stock-accum";
import * as svg from "@/lib/stock-intraday-svg";

vi.mock("@/lib/stock-intraday-svg", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/stock-intraday-svg")>();
  return { ...actual, buildVwapLabel: vi.fn(actual.buildVwapLabel) };
});

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
  vwap: 2_380_000,
  minutes: {
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_395_000, l: 2_370_000 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
  },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
});

const TOGGLES: ChartToggles = {
  vwap: true,
  cdp: false,
  ma: false,
  bb: false,
  vp: false,
  fills: false, idxTwse: false, idxOtc: false, idxTxf: false, syncHover: true, // ← 本檔的重點:**關態**
};

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null }))),
  );
  // jsdom getBoundingClientRect 恆 0:hover 座標換算需要真實寬高(frontend-testing 慣例)
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0, top: 0, right: 800, bottom: 260, width: 800, height: 260, x: 0, y: 0,
    toJSON: () => ({}),
  } as DOMRect);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

function fill(over: Partial<FillPoint> = {}): FillPoint {
  return { minute: 541, priceMilli: 2_380_000, side: "B", qty: 1, ...over };
}

describe("StockIntradayChart 成交點 toggle 關態的 memo 邊界(N073)", () => {
  it("關態下 fills 換 identity 不重繪 ChartStatic(回模組層常數,不是行內 [])", () => {
    // `useMemo` 的快取只擋「deps 沒變」的那一半 —— deps 變了(新成交進來、caller 重算
    // fills)時 factory 一定會重跑,回 `[]` 就是新 identity。這條測的正是那一半:
    // toggle 關著時,**任何** fills 變動都不該讓線圖重建。
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (fills: readonly FillPoint[]) => (
      <QueryClientProvider client={qc}>
        <IntradayChartCore accum={ACCUM} toggles={TOGGLES} variant="page" fills={fills} />
      </QueryClientProvider>
    );
    const { rerender } = render(view([fill()]));
    const probe = vi.mocked(svg.buildVwapLabel);

    // 前提自檢:探針真的被呼叫過(mock 沒接上 / ChartStatic 沒 render 時本測試 vacuous)
    expect(probe.mock.calls.length).toBeGreaterThan(0);

    const settled = probe.mock.calls.length;
    rerender(view([fill(), fill({ minute: 542, side: "S" })]));
    rerender(view([fill({ qty: 3 })]));
    rerender(view([]));
    expect(probe.mock.calls.length).toBe(settled);
  });

  it("對照組:toggle 開著時同樣的 fills 變動**會**重繪(上一條不是恆真)", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (fills: readonly FillPoint[]) => (
      <QueryClientProvider client={qc}>
        <IntradayChartCore
          accum={ACCUM}
          toggles={{ ...TOGGLES, fills: true }}
          variant="page"
          fills={fills}
        />
      </QueryClientProvider>
    );
    const { rerender } = render(view([fill()]));
    const probe = vi.mocked(svg.buildVwapLabel);
    const settled = probe.mock.calls.length;
    rerender(view([fill(), fill({ minute: 542, side: "S" })]));
    expect(probe.mock.calls.length).toBeGreaterThan(settled);
  });
});
