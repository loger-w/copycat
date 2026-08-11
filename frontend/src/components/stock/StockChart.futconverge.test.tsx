/** @vitest-environment jsdom */
/** 🔴 react-doctor P1(StockChart.tsx:74-89):進出個股期合約的模式收斂走 `useEffect`,
 *  也就是「下一個 render 才生效」。回現貨那一瞬間 `isFut` 已是 false 而 `mode` 還停在
 *  收斂後的 intraday → 中間會實際 commit 一次「現貨態的分時圖」(`stkfut=false`),
 *  下一個 render 才換成還原後的 K 線。:100-102 的註解自承這個「閃一格」。
 *
 *  既有的 A6 還原測試只看終態(`waitFor` K 線圖出現),中間那一格 commit 完全不可見 ——
 *  這一檔就是補那個時間軸:把 `StockIntradayChart` 換成會記下每次 `stkfut` 的 stub,
 *  斷言回現貨的過程中**不存在** `stkfut === false` 的紀錄。
 *
 *  斷言不寫成「零 render」:useContainerSize / query settle 都會製造無關的 re-render,
 *  那種斷言會偽紅(spec review P2-4)。`CandleChart` 不 mock —— 終態「K 線圖真的掛上」
 *  要由真身提供,否則本檔可以靠「什麼都不掛」假綠。
 *
 *  mock stub 與真身不能同檔(vi.mock 是檔案級 + hoisted),所以獨立成檔,
 *  期貨態 / 還原的行為契約仍由 `StockChart.test.tsx` 的 D10 / A6 兩節(真身)守住。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockChart } from "@/components/stock/StockChart";
import type { StockAccum } from "@/lib/stock-accum";

/** vi.mock 的 factory 是 hoisted 且在被 mock 模組首次 import 時就執行(早於本檔的
 *  module body)→ 紀錄陣列必須用 vi.hoisted 建,直接引用 top-level const 會踩 TDZ。 */
const { renders } = vi.hoisted(() => ({ renders: [] as (boolean | undefined)[] }));

vi.mock("@/components/stock/StockIntradayChart", () => ({
  StockIntradayChart: (props: { stkfut?: boolean }) => {
    renders.push(props.stkfut);
    return <div data-testid="fake-intraday" data-stkfut={String(props.stkfut)} />;
  },
}));

const ACCUM = {
  code: "2330",
  seq: 1,
  last: { p: 2_380_000, t: "09:00:01.000", cum_vol: 1 },
  vwap: 2_380_000,
  minutes: new Map([[540, { c: 2_380_000, v: 1, i: 0, o: 1, u: 0 }]]),
  ticks: [{ t: "09:00:01.000", p: 2_380_000, q: 1, side: "outer" }],
  vp: new Map(),
  book: { bids: [], asks: [] },
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  noData: false,
} as unknown as StockAccum;

const BARS = [
  { t: "2026-07-27", o: 100_000, h: 110_000, l: 90_000, c: 105_000, v: 10 },
  { t: "2026-07-28", o: 105_000, h: 120_000, l: 100_000, c: 102_000, v: 20 },
];

const CONTRACT = { prod: "CDF", ym: "202609" };

beforeEach(() => {
  window.localStorage.clear();
  renders.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      String(url).includes("/api/stock/bars")
        ? new Response(JSON.stringify({ bars: BARS }))
        : new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** 進出合約要在**同一個元件實例**上驗(重掛載 = 待還原偏好歸零 = 測不到還原);
 *  `wrap` 的 rerender 會把 QueryClientProvider 一起換掉,所以自己持有 client
 *  (逐字同 StockChart.test.tsx「現貨模式還原(A6)」節的 mount)。 */
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (contract: { prod: string; ym: string } | null) => (
    <QueryClientProvider client={client}>
      <StockChart accum={ACCUM} code="2330" contract={contract} />
    </QueryClientProvider>
  );
  const view = render(tree(null));
  return { setContract: (c: typeof CONTRACT | null) => view.rerender(tree(c)) };
}

describe("StockChart 回現貨的收斂時點(react-doctor P1)", () => {
  it("回現貨還原日K:過程中不得掛上 stkfut=false 的分時圖", async () => {
    const { setContract } = mount();
    fireEvent.click(screen.getByRole("button", { name: "日K" }));
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });

    setContract(CONTRACT);
    await waitFor(() => expect(screen.getByTestId("fake-intraday")).toBeTruthy());
    // 進合約的紀錄(stkfut=true)與本條無關,只看「回現貨」這一段
    renders.length = 0;

    setContract(null);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy(), { timeout: 5000 });

    // 中間那一格:isFut 已 false、mode 還沒被 effect 追上 → 現貨態分時圖被 commit 一次
    expect(renders.filter((v) => v === false)).toEqual([]);
    expect(screen.queryByTestId("fake-intraday")).toBeNull();
  });
});
