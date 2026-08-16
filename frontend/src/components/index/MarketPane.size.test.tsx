/** @vitest-environment jsdom */
/** MarketPane 的「容器剩餘高 → 圖 viewBox 高」量測鏈(SC-4)。
 *
 *  **與 MarketPane.test.tsx 拆開**:本檔在其中一個 it 內把全域 `ResizeObserver` 換成
 *  同步回呼的假物件,那是整個檔案唯一需要量測態的地方 —— 混進主檔會讓所有既有測試的
 *  fallback 語意(jsdom 無 ResizeObserver → 退回固定 640×220,W-10)靜默改變。
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
import { PANE_FRAMES, paneSvgHeight } from "@/lib/pane-frame";

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
const TOGGLES: ChartToggles = { vwap: true, cdp: false, ma: false, bb: true, vp: false };

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

/** 分時圖 svg 的 viewBox 高(第 4 欄)。 */
function svgViewBoxHeight(): number {
  const svg = screen.getByRole("img", { name: "加權指數分時走勢" });
  return Number((svg.getAttribute("viewBox") ?? "").split(" ")[3]);
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

describe("paneSvgHeight 三態算式(§4.1)", () => {
  const size = { width: 430, height: 300 };

  it("intraday:chrome 26 / 不內縮 / vbW 640", () => {
    // renderPx = max(96, floor(300 − 26) − 2) = 272;vbH = round(272 × 640 / 430)
    expect(paneSvgHeight(size, PANE_FRAMES.intraday)).toBe(405);
  });

  it("overlay:巢狀 figure 再吃 62 高 34 寬", () => {
    // svgW = 430 − 34 = 396;renderPx = max(96, floor(300 − 62) − 2) = 236
    expect(paneSvgHeight(size, PANE_FRAMES.overlay)).toBe(381);
  });

  it("candle:vbW 是 CandleChart 的 1400,不是 640", () => {
    // svgW = 396;renderPx = max(96, floor(300 − 100) − 2) = 198;198 × 1400 / 396
    expect(paneSvgHeight(size, PANE_FRAMES.candle)).toBe(700);
  });

  it("地板 96:容器矮到 chrome 都放不下時不回 0 / 負高", () => {
    expect(paneSvgHeight({ width: 430, height: 30 }, PANE_FRAMES.intraday)).toBe(143);
    expect(paneSvgHeight({ width: 430, height: 10 }, PANE_FRAMES.candle)).toBe(339);
  });

  it("量不到(0 寬 / 0 高)或寬度扣不出 svg 寬 → undefined(呼叫端走各自 fallback)", () => {
    expect(paneSvgHeight({ width: 0, height: 300 }, PANE_FRAMES.intraday)).toBeUndefined();
    expect(paneSvgHeight({ width: 430, height: 0 }, PANE_FRAMES.intraday)).toBeUndefined();
    expect(paneSvgHeight({ width: 30, height: 300 }, PANE_FRAMES.overlay)).toBeUndefined();
    expect(paneSvgHeight({ width: 34, height: 300 }, PANE_FRAMES.candle)).toBeUndefined();
  });
});

describe("MarketPane 量測 → 圖高(SC-4)", () => {
  it("有 ResizeObserver:分時 svg 高 = paneSvgHeight(量到的容器尺寸),不再是固定 220", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    renderPane();

    const expected = paneSvgHeight({ width: 430, height: 300 }, PANE_FRAMES.intraday);
    expect(expected).toBeDefined();
    expect(expected).not.toBe(220);
    expect(svgViewBoxHeight()).toBe(expected);
  });

  it("無 ResizeObserver(jsdom 預設 / 舊瀏覽器)→ 退回固定 220(W-10)", () => {
    expect(typeof ResizeObserver).toBe("undefined");
    renderPane();
    expect(svgViewBoxHeight()).toBe(220);
  });
});

/** 🔒 lock(review TD-7):**選對 frame** 這件事原本零測試 —— 三態的 chrome 差 30-70px,
 *  選錯的症狀是圖比容器高一點點、於是主 grid 長出一條誰也解釋不了的捲軸,而算式本身
 *  (`paneSvgHeight` 三態)照樣全綠。這兩支走整條真鏈:localStorage 預設 → 模式判別 →
 *  frame → 下傳 → 各自的 svg viewBox。 */
describe("MarketPane 依模式選 frame(TD-7)", () => {
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

  it("K 線態 → 用 candle frame,且 viewBox 寬是 CandleChart 的 1400", async () => {
    window.localStorage.setItem(MARKET_KEY_STORE, "TWSE");
    window.localStorage.setItem(MARKET_MODE_STORE, "day");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DK_BODY))),
    );
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    renderPane();

    const figure = await screen.findByTestId("candle-figure");
    const expected = paneSvgHeight(SIZE, PANE_FRAMES.candle);
    expect(expected).toBeDefined();
    expect(figure.querySelector("svg")!.getAttribute("viewBox")).toBe(`0 0 1400 ${expected}`);
  });
});

// 🔴 WL-3:svg 帶 viewBox + `w-full` → 內容整份等比縮放,pane 變窄時 rem 字級跟著縮
// (1536 兩欄態 svgW 312 → 0.625rem 只剩 ~4.9px,不可讀)。補償 = 把 `vbW / svgW` 這個
// 縮放比乘回 viewBox 內的字級,渲染 px 因此與 pane 寬無關。
describe("MarketPane svg 字級補償(WL-3)", () => {
  /** 左 pane 分時 svg 內第一個 `<text>`(整點刻度標籤)的 font-size。 */
  function firstTextFontSize(): string | null {
    const svg = screen.getByRole("img", { name: "加權指數分時走勢" });
    return svg.querySelector("text")!.getAttribute("font-size");
  }

  it("量得到:字級 × (vbW / svgW) —— 430px 寬的 pane 把 0.625rem 放大回可讀", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    renderPane();
    // insetX = 0(分時 svg 直接在 wrapper 內)→ svgW = 430
    const expected = `${(0.625 * (640 / 430)).toFixed(4)}rem`;
    expect(firstTextFontSize()).toBe(expected);
  });

  it("量不到(jsdom 無 ResizeObserver)→ scale 1,與改版前的字級數值等價", () => {
    expect(typeof ResizeObserver).toBe("undefined");
    renderPane();
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
