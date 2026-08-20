/** @vitest-environment jsdom */
/** MarketPane 的「容器剩餘高 → 圖 viewBox 高」量測鏈(SC-4)。
 *
 *  **與 MarketPane.test.tsx 拆開**:本檔在其中一個 it 內把全域 `ResizeObserver` 換成
 *  同步回呼的假物件,那是整個檔案唯一需要量測態的地方 —— 混進主檔會讓所有既有測試的
 *  fallback 語意(jsdom 無 ResizeObserver → 分時退回 core 預設 800×260、重疊退回 640×220,
 *  W-10)靜默改變。
 *  對照案(不 stub)就掛在同一個 describe 裡,兩者一起讀才看得出「量得到 / 量不到」
 *  真的分岔。 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketPane, type PaneStores } from "@/components/index/MarketPane";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import {
  INDEX_OVERLAY_STORE,
  MARKET_FUT_STORE,
  MARKET_KEY_STORE,
  MARKET_MODE_STORE,
} from "@/lib/constants";
import {
  CANDLE_CHROME_Y,
  CANDLE_INSET_X,
  PANE_FRAMES,
  paneCandleBox,
  paneIntradayBox,
  paneSvgHeight,
} from "@/lib/pane-frame";

const TWSE: IndexSeries = {
  p: 42_039_920,
  ref: 43_634_190,
  high: 43_221_930,
  low: 41_815_780,
  stale: false,
  minutes: { "0901": 43_000_000, "0930": 42_039_920 },
};

const OTC: IndexSeries = {
  p: 359_800,
  ref: 378_090,
  high: 373_420,
  low: 358_430,
  stale: false,
  minutes: { "1017": 359_800 },
};

/** 日 K 態的合法 payload(`/api/index/bars`;fixture 沿 IndexPage.test.tsx)。 */
const DK_BODY = {
  key: "TWSE",
  tf: "D",
  bars: Array.from({ length: 3 }, (_, i) => ({
    t: `2026-07-2${7 + i}`,
    o: 100,
    h: 110,
    l: 90,
    c: 105,
    v: 10,
  })),
  meta: {
    source: "tc4_dk",
    coverage_from: "2026-07-27",
    coverage_to: "2026-07-29",
    partial_last: false,
    volume: true,
    refusal: null,
    synth_since: null,
  },
};

const LEFT_STORES: PaneStores = {
  key: MARKET_KEY_STORE,
  mode: MARKET_MODE_STORE,
  fut: MARKET_FUT_STORE,
  overlay: INDEX_OVERLAY_STORE,
};

// cdp / ma 全關:分時態不打 `/api/index/overlay`,本檔只關心 viewBox 幾何
const TOGGLES: ChartToggles = { vwap: true, cdp: false, ma: false, bb: true, vp: false, fills: true };

/** ResizeObserver 的最小替身:`observe` 當下就同步餵一筆 contentRect。
 *
 *  **必須同步**:`useContainerSize` 是 callback ref,節點掛上時才 observe;非同步餵
 *  在 RTL 的同步斷言之前不會到達,測試會靜默退回 fallback 值(= 綠得毫無意義)。 */
class FakeResizeObserver {
  private readonly cb: ResizeObserverCallback;

  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }

  observe(node: Element): void {
    this.cb(
      [{ target: node, contentRect: { width: 430, height: 300 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve(): void {}

  disconnect(): void {}
}

/** `otc` 只有重疊態需要(`buildOverlayGeometry` 兩條 series 都得非 null)—— 其餘測試維持
 *  單邊,避免多一份資料改變分時態的幾何。 */
function renderPane(otc: IndexSeries | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarketPane
        paneId="left"
        twse={TWSE}
        otc={otc}
        futures={null}
        stores={LEFT_STORES}
        defaultKey="TWSE"
        toggles={TOGGLES}
        onToggle={() => undefined}
      />
    </QueryClientProvider>,
  );
}

/** 分時圖 svg 的 viewBox 字串。分時態改吃 1:1 px box 後,**寬也是變數**
 *  (不再是恆定的 640),只比高會漏掉「寬沒跟著量測走」這個失效樣態。 */
function intradayViewBox(): string | null {
  return screen.getByRole("img", { name: "加權指數分時走勢" }).getAttribute("viewBox");
}

beforeEach(() => {
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

/** K 線態 2026-08-21 起也退出 `PANE_FRAMES`(改 1:1,見下一個 describe)——
 *  這張表與這支反解只剩 `OverlayCard` 一個讀者。 */
describe("paneSvgHeight(overlay 唯一讀者;§4.1)", () => {
  const size = { width: 430, height: 300 };

  it("overlay:巢狀 figure 再吃 62 高 34 寬", () => {
    // svgW = 430 − 34 = 396;renderPx = max(96, floor(300 − 62) − 2) = 236
    expect(paneSvgHeight(size, PANE_FRAMES.overlay)).toBe(381);
  });

  it("地板 96:容器矮到 chrome 都放不下時不回 0 / 負高", () => {
    // svgW = 396;renderPx 夾到 96 → 96 × 640 / 396
    expect(paneSvgHeight({ width: 430, height: 30 }, PANE_FRAMES.overlay)).toBe(155);
  });

  it("量不到(0 寬 / 0 高)或寬度扣不出 svg 寬 → undefined(呼叫端走各自 fallback)", () => {
    expect(paneSvgHeight({ width: 0, height: 300 }, PANE_FRAMES.overlay)).toBeUndefined();
    expect(paneSvgHeight({ width: 430, height: 0 }, PANE_FRAMES.overlay)).toBeUndefined();
    expect(paneSvgHeight({ width: 30, height: 300 }, PANE_FRAMES.overlay)).toBeUndefined();
  });
});

/** K 線態改 1:1(2026-08-21;同 2026-08-17 分時態的理由):字級補償補得了 7 處
 *  fontSize,補不了 `PRICE_TAG` / `TIME_TAG` / `X_LABEL_H` 這些 viewBox 單位的排版
 *  常數 —— 縮放比 0.2 下 hover 價位框只有 11×3px,字放大後必撞。
 *
 *  **常數一律 import 不硬寫**:`CANDLE_CHROME_Y` 的 80 + 20 拆解是 W-4 契約的出處
 *  (`MarketChart` 的 meta 列 `h-4`),測試裡寫死 100 會讓契約漂掉時這裡照樣綠。 */
describe("paneCandleBox 算式(1:1)", () => {
  it("量得到:寬 = round(量到的寬 − insetX)、高 = max(96, floor(高 − chromeY) − 2)", () => {
    expect(paneCandleBox({ width: 430, height: 300 })).toEqual({
      width: 430 - CANDLE_INSET_X,
      height: Math.max(96, Math.floor(300 - CANDLE_CHROME_Y) - 2),
      usable: true,
    });
  });

  it("地板 96:容器矮到 chrome 都放不下時不回 0 / 負高", () => {
    expect(paneCandleBox({ width: 430, height: 30 }).height).toBe(96);
  });

  it("量不到(0 寬 / 0 高)或寬度扣不出 svg 寬 → usable false(呼叫端傳 undefined)", () => {
    expect(paneCandleBox({ width: 0, height: 300 }).usable).toBe(false);
    expect(paneCandleBox({ width: 430, height: 0 }).usable).toBe(false);
    // 邊界:寬恰等於 insetX → svgW = 0(edge 2);再窄一格同樣不得傳 0 / 負寬
    expect(paneCandleBox({ width: CANDLE_INSET_X, height: 300 }).usable).toBe(false);
    expect(paneCandleBox({ width: CANDLE_INSET_X - 4, height: 300 }).usable).toBe(false);
  });
});

/** 分時態退出 `PANE_FRAMES`(不再有 viewBox 反解):量到多少 px 就畫多少 px,
 *  與群組卡片的 `cardSvgBox` 同法 —— 字級因此與 pane 寬無關,`unitScale` 那條補償
 *  對分時態隨之退場。 */
describe("paneIntradayBox 算式(1:1)", () => {
  it("量得到:寬 = 量到的寬、高 = max(96, floor(高 − 26) − 2)", () => {
    // chrome 26 = core readout 列 h-[1.375rem] 22 + mb-1 4;−2 抗抖
    expect(paneIntradayBox({ width: 430, height: 300 })).toEqual({
      width: 430,
      height: 272,
      usable: true,
    });
  });

  it("地板 96:容器矮到 chrome 都放不下時不回 0 / 負高", () => {
    expect(paneIntradayBox({ width: 430, height: 30 }).height).toBe(96);
  });

  it("量不到(0 寬 / 0 高)→ usable false(呼叫端傳 undefined 讓 core 走預設)", () => {
    expect(paneIntradayBox({ width: 0, height: 300 }).usable).toBe(false);
    expect(paneIntradayBox({ width: 430, height: 0 }).usable).toBe(false);
  });
});

describe("MarketPane 量測 → 圖高(SC-4)", () => {
  it("有 ResizeObserver:分時 svg 走 1:1 box(寬高都跟著量測),不再是固定 640×220", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    renderPane();

    const box = paneIntradayBox({ width: 430, height: 300 });
    expect(box.usable).toBe(true);
    expect(intradayViewBox()).toBe(`0 0 ${box.width} ${box.height}`);
  });

  it("無 ResizeObserver(jsdom 預設 / 舊瀏覽器)→ 退回 core 預設 800×260(W-10)", () => {
    expect(typeof ResizeObserver).toBe("undefined");
    renderPane();
    expect(intradayViewBox()).toBe("0 0 800 260");
  });
});

/** 🔒 lock(review TD-7):**選對換算** 這件事原本零測試 —— 三態的 chrome 差 30-70px,
 *  選錯的症狀是圖比容器高一點點、於是主 grid 長出一條誰也解釋不了的捲軸,而算式本身
 *  (`paneSvgHeight` / `paneCandleBox` / `paneIntradayBox` 各自)照樣全綠。這幾支走整條
 *  真鏈:localStorage 預設 → 模式判別 → 換算 → 下傳 → 各自的 svg viewBox。 */
describe("MarketPane 依模式選換算(TD-7)", () => {
  const SIZE = { width: 430, height: 300 };

  it("重疊態 → 用 overlay frame(巢狀 figure 再吃 62 高 34 寬)", () => {
    window.localStorage.setItem(INDEX_OVERLAY_STORE, "overlay");
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    renderPane(OTC);

    const svg = screen.getByRole("img", { name: "指數重疊走勢" });
    const expected = paneSvgHeight(SIZE, PANE_FRAMES.overlay);
    expect(expected).toBeDefined();
    expect(svg.getAttribute("viewBox")).toBe(`0 0 640 ${expected}`);
  });

  it("K 線態 → 1:1 candleBox(viewBox 寬 = 量到的 svg 寬,不再是 1400)", async () => {
    window.localStorage.setItem(MARKET_KEY_STORE, "TWSE");
    window.localStorage.setItem(MARKET_MODE_STORE, "day");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DK_BODY))),
    );
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    renderPane();

    const figure = await screen.findByTestId("candle-figure");
    const box = paneCandleBox(SIZE);
    expect(box.usable).toBe(true);
    // 寬也是變數(1:1)—— 只比高會漏掉「寬沒跟著量測走」這個失效樣態,而那正是
    // 字級被縮成 3px 的成因(同 intradayViewBox 的理由)
    expect(figure.querySelector("svg")!.getAttribute("viewBox")).toBe(
      `0 0 ${box.width} ${box.height}`,
    );
  });

  // W-3:量不到就**不傳**,讓 CandleChart 走它自己的 1400×578 —— 傳一組 0 的話 svg
  // 不報錯、純粹畫不出來(同分時態退回 core 預設的精神)。
  it("無 ResizeObserver(jsdom 預設)→ K 線退回 CandleChart 自有的 1400×578(W-3)", async () => {
    window.localStorage.setItem(MARKET_KEY_STORE, "TWSE");
    window.localStorage.setItem(MARKET_MODE_STORE, "day");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DK_BODY))),
    );
    expect(typeof ResizeObserver).toBe("undefined");
    renderPane();

    const figure = await screen.findByTestId("candle-figure");
    expect(figure.querySelector("svg")!.getAttribute("viewBox")).toBe("0 0 1400 578");
  });
});

// 🔴 WL-3:svg 帶 viewBox + `w-full` → 內容整份等比縮放,pane 變窄時 rem 字級跟著縮
// (1536 兩欄態 svgW 312 → 0.625rem 只剩 ~4.9px,不可讀)。補償 = 把 `vbW / svgW` 這個
// 縮放比乘回 viewBox 內的字級,渲染 px 因此與 pane 寬無關。
//
// **分時態已不在本條的射程內**:改吃 1:1 px box 後 viewBox 寬 = 渲染寬,縮放比恆 1,
// 字級與 pane 寬天生無關(取代補償)。仍走等比縮放的只剩 `OverlayCard`(viewBox 寬
// 寫死 640),補償留在那裡。
describe("MarketPane svg 字級補償(WL-3;overlay 態)", () => {
  /** 重疊圖 svg 內第一個 `<text>`(整點刻度標籤)的 font-size。 */
  function firstTextFontSize(): string | null {
    const svg = screen.getByRole("img", { name: "指數重疊走勢" });
    return svg.querySelector("text")!.getAttribute("font-size");
  }

  it("量得到:字級 × (vbW / svgW) —— 430px 寬的 pane 把 0.625rem 放大回可讀", () => {
    window.localStorage.setItem(INDEX_OVERLAY_STORE, "overlay");
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    renderPane(OTC);
    // insetX = 34(巢狀 figure 的 border + p-4)→ svgW = 430 − 34 = 396
    const expected = `${(0.625 * (640 / 396)).toFixed(4)}rem`;
    expect(firstTextFontSize()).toBe(expected);
  });

  it("量不到(jsdom 無 ResizeObserver)→ scale 1,與改版前的字級數值等價", () => {
    window.localStorage.setItem(INDEX_OVERLAY_STORE, "overlay");
    expect(typeof ResizeObserver).toBe("undefined");
    renderPane(OTC);
    expect(Number(firstTextFontSize()!.replace("rem", ""))).toBeCloseTo(0.625, 6);
  });
});

// 🔴 amendment r3:可縮鏈的地板改由**顯式 min-height** 提供(雙圖 grid `min-h-80`、
// figure `min-h-48`),不是靠某一段不可縮。
//
// **pane root 的 `min-h-0` 必須無條件**:條件化成 `@[1050px]:min-h-0` 時,那個門檻量到的
// 是**左欄**(左欄自己是 `@container`,是最近的 container 祖先;兩欄態左欄僅 630–930px)
// → 永不成立 → pane 退回 grid item 的 `min-height: auto` → 軌高被撐到 ≥ pane 內容高
// (figure 內的 svg 是「當前高」不是地板,不會自己縮),雙圖 grid 到 min-h-80 地板後軌道
// 照樣撐開 → 溢出蓋家數帶,與修前同症狀。無條件 min-h-0 下:兩欄態 pane 縮到軌高、
// figure / wrapper 跟著縮 → svg 跟著矮;單欄態 pane 內容驅動高,沿 wrapper−2 收斂到
// figure 的 `min-h-48` 地板,不形成迴圈。
describe("MarketPane 可縮鏈(amendment r3)", () => {
  it("root 無條件 min-h-0(門檻不可條件化);figure 掛地板 min-h-48 而非 min-h-0", () => {
    renderPane();
    const root = screen.getByTestId("market-pane-left");
    expect(root.className).toContain("min-h-0");
    // 條件化的版本量錯 container(見上)→ 兩欄態縮矮時圖卡溢出
    expect(root.className).not.toContain("@[1050px]:min-h-0");

    const figure = root.querySelector("figure")!;
    expect(figure.className).toContain("min-h-48");
    expect(figure.className).toContain("flex-1");
    // 同時掛 min-h-0 會把地板消掉(twMerge 不會擋 —— 兩者是不同 utility),退回「圖可以被壓成 0 高」
    expect(figure.className).not.toContain("min-h-0");
  });
});
