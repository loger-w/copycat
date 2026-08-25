/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketPane, type PaneFutState, type PaneStores } from "@/components/index/MarketPane";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import {
  INDEX_OVERLAY_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";

/** S2 memo 邊界的 regression lock:`OverlayCard` 的疊圖幾何有沒有被無關的 rerender 拖著重算。
 *
 *  **畫面上完全看不出來** —— 失效只是多算幾何:重疊開著時,App 層那五條流(期貨
 *  coalesce 0.1s 是最兇的一條)每推一次就重繪整棵樹 → 加權/櫃買一個分鐘點都沒動,
 *  兩條 series 的全窗幾何照樣重算一遍。線照畫、值照對,只有 CPU 知道。
 *
 *  **收益條件性(refactor-plan R10)**:`OverlayCard` 只在「重疊」toggle 開啟時 render
 *  (預設關)。本檔所有案例都**強制開啟** toggle(`fireEvent.click(btn("重疊"))`,沿
 *  MarketPane.test.tsx:379 的既有操作慣例);使用者不開重疊時本步收益 = 0。
 *
 *  量法(refactor-plan R11):`importOriginal` partial mock `@/lib/index-chart-svg`,
 *  **只包住** `buildOverlayGeometry` 計次,其餘 export(`X_START_MIN` / `X_END_MIN` /
 *  `outOfDomainLevels` …)一律保留真身 —— 漏了 `X_START_MIN`
 *  這對常數,MarketPane 自己的 `toX` 立刻變 NaN,測試會以為自己在量 memo,
 *  其實在量壞掉的圖。
 *
 *  探針選在 `buildOverlayGeometry` 而不是「render 次數」:本步要鎖的就是這支呼叫有沒有
 *  被 `useMemo` 擋住,拔掉 useMemo 後計次必然跳(S3 踩過的「探針在 useMemo 內、mutation
 *  量不到」在這裡不成立,因為 useMemo 本身就是待測邊界)。
 *
 *  **獨立檔**:`vi.mock` 是檔案級 + hoisted,與同目錄那兩份要看到真幾何數字的
 *  `MarketPane.test.tsx` / `MarketPane.size.test.tsx` 不能共存。
 *
 *  mutation-verified:(a) 拔掉 `useMemo` → 第一條紅(3 vs 0);(b) deps 改 `[]` →
 *  第二條紅(0 vs 1)。兩個方向各有一條守著,不是單向的空 lock。 */

const hoisted = vi.hoisted(() => ({
  /** buildOverlayGeometry 被呼叫幾次(= 加權 + 櫃買兩條全窗幾何重算次數) */
  overlay: 0,
}));

vi.mock("@/lib/index-chart-svg", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/index-chart-svg")>();
  return {
    ...actual,
    buildOverlayGeometry: (...args: Parameters<typeof actual.buildOverlayGeometry>) => {
      hoisted.overlay += 1;
      return actual.buildOverlayGeometry(...args);
    },
  };
});

function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 42_039_920,
    ref: 43_634_190,
    high: 43_221_930,
    low: 41_815_780,
    stale: false,
    minutes: { "0901": 43_000_000, "0930": 42_039_920 },
    ...over,
  };
}

const OTC = series({
  p: 359_800,
  ref: 378_090,
  high: 373_420,
  low: 358_430,
  minutes: { "1017": 359_800 },
});

const TOGGLES: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true, vp: false, fills: true, idxTwse: false, idxOtc: false, syncHover: true };

const LEFT_STORES: PaneStores = {
  key: MARKET_KEY_STORE,
  mode: MARKET_MODE_STORE,
  fut: MARKET_FUT_STORE,
  overlay: INDEX_OVERLAY_STORE,
};

/** 期貨引擎 coalesce 0.1s 的推播樣態:每則都是新物件,而 `MarketPane` 在加權態
 *  根本不讀它(`futState` 恆 null)—— 純粹是 App 層重繪整棵樹帶下來的串擾。 */
function futures(p: number): Record<string, PaneFutState> {
  return { TXF: { p, ref: 42_000_000 } };
}

function tree(twse: IndexSeries, fut: Record<string, PaneFutState>, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MarketPane
        paneId="left"
        twse={twse}
        otc={OTC}
        futures={fut}
        stores={LEFT_STORES}
        defaultKey="TWSE"
        toggles={TOGGLES}
        onToggle={() => {}}
      />
    </QueryClientProvider>
  );
}

/** 開重疊 + 自檢圖真的畫出來了,回傳 rerender 與「此刻的計次」。 */
function openOverlay() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const twse = series();
  const { rerender } = render(tree(twse, futures(42_142_000), client));
  fireEvent.click(screen.getByRole("button", { name: "重疊" }));
  // 自檢:重疊圖真的 mount 了(沒 mount 的話下面量的 +0 與 memo 無關,是空綠)
  expect(screen.getByLabelText("指數重疊走勢")).toBeTruthy();
  expect(hoisted.overlay).toBeGreaterThan(0);
  return {
    twse,
    before: hoisted.overlay,
    show: (next: IndexSeries, fut: Record<string, PaneFutState>) =>
      rerender(tree(next, fut, client)),
  };
}

beforeEach(() => {
  hoisted.overlay = 0;
  window.localStorage.clear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null }))),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OverlayCard 疊圖幾何 memo 邊界計次(S2;重疊 toggle = 開)", () => {
  it("期貨 tick 連推三則(加權/櫃買一個分鐘點沒動)→ 疊圖幾何零重算", () => {
    const { twse, before, show } = openOverlay();

    // 三則**相異**的期貨現價:同值連發會被 React 的 props 比對省掉一輪,量不到東西。
    // `twse` / `OTC` 兩個 series 全程保持同參照 = 指數流沒有新推播的真實樣態。
    show(twse, futures(42_143_000));
    show(twse, futures(42_144_000));
    show(twse, futures(42_145_000));

    // 自檢:重疊圖還在(切掉的話 +0 一樣是空綠)
    expect(screen.getByLabelText("指數重疊走勢")).toBeTruthy();
    expect(hoisted.overlay - before).toBe(0);
  });

  it("加權真的多出一個分鐘點 → 幾何重算,恰一次(memo 不可鎖死成 deps=[])", () => {
    const { before, show } = openOverlay();

    show(
      series({ minutes: { "0901": 43_000_000, "0930": 42_039_920, "0931": 42_100_000 } }),
      futures(42_142_000),
    );

    expect(hoisted.overlay - before).toBe(1);
  });
});
