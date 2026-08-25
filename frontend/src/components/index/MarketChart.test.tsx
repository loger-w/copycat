/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketChart } from "@/components/index/MarketChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { fmt } from "@/lib/format";
import { R_AXIS_W, Y_AXIS_W } from "@/lib/stock-intraday-svg";
import { fmtTickPrice } from "@/lib/stock-tick";
import type { MarketKey } from "@/lib/timeframe";

/** 分時圖改吃 `IntradayChartCore`(mode="index")後,**域是對稱 autofit 不是緊貼**:
 *  ref 23000、分鐘收盤 [23000, 23100]、當日高低同池
 *  → 半幅 = max(hi−ref = 100, ref−lo = 0, ref×1% = 230) × 1.1 = 253
 *  → y 域 [22747, 23253]。下面兩份 overlay fixture 的域內 / 域外都以這個域為準。 */
function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 23_100_000,
    ref: 23_000_000,
    high: 23_100_000,
    low: 22_990_000,
    stale: false,
    minutes: { "0901": 23_000_000, "0930": 23_100_000 },
    ...over,
  };
}

/** 五條 CDP + 兩條 MA 全在域內。
 *  `ma5` 刻意取 **23018**(非合法檔位):`fmtTickPrice` 會 snap 成 23020,`fmt` 才印
 *  23018 —— 指數沒有 tick 表,snap 出來的點位是憑空捏造的(SC-2)。 */
const OVERLAY_IN = {
  // cdp 本尊 / ma5 刻意**非 5 點整數倍且帶小數**(review T-1 / C-2):tick 表對 ≥1000 元帶
  // 是 5 元檔,整數倍的 fixture 讓 fmtTickPrice 與整數點口徑同值,priceText 改回 snap 也全綠。
  cdp: { cdp: 23_051_440, ah: 23_150_000, nh: 23_100_000, nl: 22_995_000, al: 22_950_000 },
  ma5: 23_018_440,
  ma20: 22_930_000,
  date: "2026-08-13",
};

/** ah / cdp 在域上方、al / ma20 在域下方;nh / nl / ma5 仍在域內 */
const OVERLAY_OUT = {
  cdp: { cdp: 24_000_000, ah: 24_100_000, nh: 23_100_000, nl: 22_995_000, al: 22_000_000 },
  ma5: 23_020_000,
  ma20: 22_000_000,
  date: "2026-08-13",
};

const TOGGLES: ChartToggles = { vwap: true, cdp: true, ma: false, bb: true, vp: true, fills: true, idxTwse: false, idxOtc: false };

function toggles(over: Partial<ChartToggles> = {}): ChartToggles {
  return { ...TOGGLES, ...over };
}

let urls: string[] = [];

function stub(body: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(String(url));
      return new Response(JSON.stringify(body), { status });
    }),
  );
}

function renderChart(opts: {
  marketKey?: MarketKey;
  name?: string;
  s?: IndexSeries | null;
  t?: ChartToggles;
  intradayBox?: { width: number; height: number };
}) {
  const client = new QueryClient({
    // retryDelay 0:hook 自帶 retry:1,error 終態才不用等 exponential backoff
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MarketChart
        marketKey={opts.marketKey ?? "TWSE"}
        mode="intraday"
        name={opts.name ?? "加權指數"}
        series={opts.s === undefined ? series() : opts.s}
        toggles={opts.t ?? toggles()}
        onToggle={() => undefined}
        intradayBox={opts.intradayBox}
      />
    </QueryClientProvider>,
  );
}

/** 日 K 態的合法 payload(`/api/index/bars`)。intraday 那條路不打這支端點,
 *  所以只有 candle 測試需要換 stub。 */
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

function renderCandle(candleBox: { width: number; height: number } | undefined) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MarketChart
        marketKey="TWSE"
        mode="day"
        name="加權指數"
        series={null}
        toggles={toggles()}
        onToggle={() => undefined}
        candleBox={candleBox}
      />
    </QueryClientProvider>,
  );
}

function dashedOverlayLines(root: HTMLElement): NodeListOf<Element> {
  return root.querySelectorAll('line[stroke-dasharray="3 2"]');
}

/** 昨收線:`2 3` 虛線裡**第一條**(ChartStatic 先畫昨收再畫 y 格線)。 */
function refLine(root: HTMLElement): Element {
  return root.querySelector('line[stroke-dasharray="2 3"]')!;
}

beforeEach(() => {
  urls = [];
  stub(OVERLAY_IN);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("MarketChart 分時疊線(SC-3)", () => {
  it("加權 + CDP 開 → 域內疊線畫水平虛線,右緣印帶 * 的價位", async () => {
    const { container } = renderChart({ t: toggles({ cdp: true, ma: false }) });
    await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(5));
    expect(urls).toContain("/api/index/overlay");
    const starred = [...container.querySelectorAll("text")]
      .map((t) => t.textContent ?? "")
      .filter((s) => s.endsWith("*"));
    expect(starred.sort()).toEqual(["22950*", "22995*", "23051*", "23100*", "23150*"]);
    // 自檢:cdp 23_051_440 在 tick 口徑會 snap 成 23050,整數點口徑印 23051 —— fixture 區分得出兩者
    expect(fmtTickPrice(23_051_440)).not.toBe("23051");
    // 線體止於繪圖區(core 的左緣價位帶 / 右緣疊線帶都不被覆蓋),不再橫貫全寬
    expect(dashedOverlayLines(container)[0]!.getAttribute("x1")).toBe(String(Y_AXIS_W));
    expect(dashedOverlayLines(container)[0]!.getAttribute("x2")).toBe(String(800 - R_AXIS_W));
  });

  it("域外 → 不畫線體,繪圖區右緣掛牌帶名稱與方向", async () => {
    stub(OVERLAY_OUT);
    const { container } = renderChart({ t: toggles({ cdp: true, ma: true }) });
    // 域內只剩 nh / nl / ma5
    await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(3));
    expect(screen.getByTestId("overlay-peg-ah").textContent).toBe("AH 24100↑");
    expect(screen.getByTestId("overlay-peg-cdp").textContent).toBe("CDP 24000↑");
    expect(screen.getByTestId("overlay-peg-al").textContent).toBe("AL 22000↓");
    expect(screen.getByTestId("overlay-peg-ma20").textContent).toBe("MA20 22000↓");
    // 域內的值不得同時掛牌(掛牌與線體互補)
    expect(container.querySelector('[data-testid="overlay-peg-nh"]')).toBeNull();
    expect(container.querySelector('[data-testid="overlay-peg-ma5"]')).toBeNull();
    // 域外的值不得出現線體價位標(那是「畫了線」的語彙)
    expect(screen.queryByText("24000*")).toBeNull();
  });

  it("MA 開 → 右緣帶名稱 + 繪圖區內側價位標,價位走整數點不 snap tick", async () => {
    const { container } = renderChart({ t: toggles({ cdp: false, ma: true }) });
    await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(2));
    // 右緣帶內是名稱(R_AXIS_W 裝不下名稱 + 四位數價位)
    expect(screen.getByText("MA5")).toBeTruthy();
    expect(screen.getByText("MA20")).toBeTruthy();
    // 價位標:23018.44 → 整數點 23018,不得被 snap 成 23020(指數沒有可下單檔位),
    // 也不印小數(36/40px 的軸帶裝不下 8 字,review C-2)
    expect(container.querySelector('[data-testid="edge-price-ma5"]')!.textContent).toBe("23018");
    expect(container.querySelector('[data-testid="edge-price-ma20"]')!.textContent).toBe("22930");
    // 自檢:fixture 真的區分得出兩種口徑(否則本案恆綠)
    expect(fmtTickPrice(23_018_440)).not.toBe("23018");
  });
});

describe("MarketChart toggle 列(SC-4 / 決策 2)", () => {
  it("櫃買 → CDP / MA 反灰帶 title,均價可按", () => {
    renderChart({
      marketKey: "OTC",
      name: "櫃買指數",
      s: series({ minutes: { "1017": 359_800 }, ref: 378_090, high: 373_420, low: 358_430 }),
      t: toggles({ cdp: true, ma: true }),
    });
    for (const label of ["CDP", "MA"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.hasAttribute("disabled")).toBe(true);
      expect(btn.getAttribute("title")).toBe("櫃買無日 K 資料源");
      // 決策 2:aria-pressed 與 available 連動,不並存 aria-disabled 字串
      expect(btn.getAttribute("aria-pressed")).toBe("false");
      expect(btn.getAttribute("aria-disabled")).toBeNull();
    }
    const vwap = screen.getByRole("button", { name: "均價" });
    expect(vwap.hasAttribute("disabled")).toBe(false);
    expect(vwap.getAttribute("title")).toBe("分鐘收盤均價(指數無成交量)");
    // 櫃買不打 overlay 端點
    expect(urls.some((u) => u.includes("/api/index/overlay"))).toBe(false);
    // 指數態只三顆(量分佈 / 成交點需要逐筆量與委託,指數兩者皆無)
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "均價",
      "CDP",
      "MA",
    ]);
  });

  it("加權但端點 503 → CDP / MA 反灰帶「無日線資料」", async () => {
    stub({ detail: { error: "NOT_READY" } }, 503);
    renderChart({ t: toggles({ cdp: true, ma: true }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    for (const label of ["CDP", "MA"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.getAttribute("title")).toBe("無日線資料");
    }
  });

  it("200 但三欄全 null(TC4 沒開)→ CDP / MA 反灰帶「無日線資料」", async () => {
    stub({ cdp: null, ma5: null, ma20: null, date: null });
    renderChart({ t: toggles({ cdp: true, ma: true }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    for (const label of ["CDP", "MA"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.hasAttribute("disabled")).toBe(true);
      expect(btn.getAttribute("title")).toBe("無日線資料");
    }
  });

  it("cdp null 但 ma5 有值 → CDP 反灰、MA 仍可按(edge case 3 同個股語意)", async () => {
    stub({ cdp: null, ma5: 23_020_000, ma20: null, date: "2026-08-13" });
    renderChart({ t: toggles({ cdp: true, ma: true }) });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    expect(screen.getByRole("button", { name: "CDP" }).getAttribute("title")).toBe("無日線資料");
    const ma = screen.getByRole("button", { name: "MA" });
    expect(ma.hasAttribute("disabled")).toBe(false);
    expect(ma.getAttribute("title")).toBeNull();
  });
});

describe("MarketChart error 態不鎖死 toggle 閘(review G-2)", () => {
  /** 同一個 QueryClient 下換 toggles 重繪 —— `renderChart` 每次新建 client,
   *  「error 殘留 + 閘關掉」這條路只有沿用同一份 query state 才走得到 */
  function rerenderable(t: ChartToggles) {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, retryDelay: 0 } },
    });
    const el = (cur: ChartToggles) => (
      <QueryClientProvider client={client}>
        <MarketChart
          marketKey="TWSE"
          mode="intraday"
          name="加權指數"
          series={series()}
          toggles={cur}
          onToggle={onToggle}
        />
      </QueryClientProvider>
    );
    const onToggle = vi.fn();
    const view = render(el(t));
    return { onToggle, rerender: (next: ChartToggles) => view.rerender(el(next)) };
  }

  it("503 後把 toggle 全關 → CDP / MA 鈕恢復可按,點得回請求路徑", async () => {
    stub({ detail: { error: "NOT_READY" } }, 503);
    const { onToggle, rerender } = rerenderable(toggles({ cdp: true, ma: true }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "CDP" }).hasAttribute("disabled")).toBe(true),
    );
    const overlayCalls = () => urls.filter((u) => u === "/api/index/overlay").length;
    const before = overlayCalls();

    // toggle 全關 → query enabled=false。TanStack 不會因此清掉 error status,
    // refetchInterval 也停 → 沒有閘的話這兩顆鈕從此永久 disabled(重整才解)
    rerender(toggles({ cdp: false, ma: false }));
    for (const label of ["CDP", "MA"]) {
      expect(screen.getByRole("button", { name: label }).hasAttribute("disabled")).toBe(false);
    }

    // 點得下去 = 使用者自己就能把疊線開回來
    fireEvent.click(screen.getByRole("button", { name: "CDP" }));
    expect(onToggle).toHaveBeenCalledWith("cdp", true);

    // 開回來 → 閘重開,請求路徑真的再走一次(不是只有鈕看起來能按)
    rerender(toggles({ cdp: true, ma: false }));
    await waitFor(() => expect(overlayCalls()).toBeGreaterThan(before));
  });
});

describe("MarketChart 昨收(SC-2)", () => {
  it("有 ref → 左緣中格刻度 = 昨收,昨收虛線畫在同一條 y 上", async () => {
    const { container } = renderChart({ t: toggles({ cdp: false, ma: false }) });
    await waitFor(() => expect(container.querySelector("svg")).toBeTruthy());
    const ticks = [...container.querySelectorAll('[data-testid="y-tick-price"]')];
    expect(ticks).toHaveLength(3);
    // 3 格 fallback = [yTop, ref, yBottom] → 中格恆是昨收
    expect(ticks[1]!.textContent).toBe(fmt(23_000_000));
    expect(ticks[1]!.getAttribute("y")).toBe(refLine(container).getAttribute("y1"));
  });

  it("ref null → hasRef false:不填色、走勢線退回單條 accent", async () => {
    const { container } = renderChart({
      s: series({ ref: null }),
      t: toggles({ cdp: false, ma: false }),
    });
    await waitFor(() => expect(container.querySelector("svg")).toBeTruthy());
    // 平盤上下的紅綠填色需要 `<defs>` 內的兩個 clipPath;沒有昨收就沒有「平盤」可言
    expect(container.querySelector("defs")).toBeNull();
    expect(container.querySelectorAll("polygon")).toHaveLength(0);
    expect(container.querySelectorAll("polyline.stroke-accent")).toHaveLength(1);
    expect(container.querySelectorAll("polyline.stroke-bull")).toHaveLength(0);
  });
});

describe("MarketChart y 域不受疊線影響(SC-7)", () => {
  async function snapshot(t: ChartToggles, expectLines: number) {
    const { container, unmount } = renderChart({ t });
    if (expectLines > 0) {
      await waitFor(() => expect(dashedOverlayLines(container)).toHaveLength(expectLines));
    } else {
      await waitFor(() => expect(container.querySelector("svg")).toBeTruthy());
    }
    const ticks = [...container.querySelectorAll('[data-testid="y-tick-price"]')].map(
      (e) => `${e.getAttribute("y")}|${e.textContent}`,
    );
    const refY = refLine(container).getAttribute("y1");
    unmount();
    return { ticks, refY };
  }

  it("同一 series 下 CDP/MA 開 vs 關,yTicks 與昨收線位置逐字相同", async () => {
    const off = await snapshot(toggles({ cdp: false, ma: false }), 0);
    const on = await snapshot(toggles({ cdp: true, ma: true }), 7);
    expect(off.ticks).toHaveLength(3);
    expect(on.ticks).toEqual(off.ticks);
    expect(on.refY).toBe(off.refY);
  });
});

describe("MarketChart a11y 錨點(W-12)", () => {
  it("role=img + aria-label 掛在 svg 節點,toggle 鈕不在其內", () => {
    renderChart({ t: toggles({ cdp: false, ma: false }) });
    const node = screen.getByRole("img", { name: "加權指數分時走勢" });
    expect(node.tagName).toBe("svg");
    expect(node.querySelectorAll("button")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "均價" })).toBeTruthy();
  });
});

describe("MarketChart 均價線(SC-1)", () => {
  it("均價 toggle 開 → 畫 stroke-ink 1.2 寬的均價線;關 → 不畫", () => {
    const { container, unmount } = renderChart({
      t: toggles({ vwap: true, cdp: false, ma: false }),
    });
    expect(container.querySelectorAll("polyline.stroke-ink")).toHaveLength(1);
    expect(container.querySelector("polyline.stroke-ink")!.getAttribute("stroke-width")).toBe(
      "1.2",
    );
    // 末點價位標 = 分鐘收盤算術平均((23000 + 23100) / 2)
    expect(container.querySelector('[data-testid="edge-price-vwap"]')!.textContent).toBe("23050");
    unmount();
    const off = renderChart({ t: toggles({ vwap: false, cdp: false, ma: false }) });
    expect(off.container.querySelectorAll("polyline.stroke-ink")).toHaveLength(0);
  });
});

describe("MarketChart 高低點與現價圈(SC-3)", () => {
  it("當日高 / 低空心環 + 現價圈都在(高低取分鐘收盤極值,等值反查必命中)", () => {
    const { container } = renderChart({ t: toggles({ cdp: false, ma: false }) });
    expect(container.querySelector('[data-testid="day-high"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="day-low"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="last-dot"]')).toBeTruthy();
  });

  it("series.p 為 null → 不畫現價圈(沒有現價可指)", () => {
    const { container } = renderChart({
      s: series({ p: null }),
      t: toggles({ cdp: false, ma: false }),
    });
    expect(container.querySelector('[data-testid="last-dot"]')).toBeNull();
  });
});

describe("MarketChart hover(SC-1)", () => {
  /** jsdom 的 `getBoundingClientRect` 恆 0 → hover 座標換算需要真實寬高
   *  (frontend-testing 慣例;只在本 describe 內裝,避免影響 candle 態的事件測試)。 */
  function mockRect(): void {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, right: 800, bottom: 260,
      width: 800, height: 260, x: 0, y: 0,
      toJSON: () => ({}),
    } as DOMRect);
  }

  it("游標移入 → 十字線 + 左緣價位標 + readout 切到該分鐘", () => {
    mockRect();
    const { container } = renderChart({ t: toggles({ cdp: false, ma: false }) });
    const readout = () => screen.getByTestId("chart-readout");
    expect(readout().children.length).toBe(3);
    expect(readout().getAttribute("data-hovering")).toBe("false");

    const svg = container.querySelector("svg")!;
    // 09:01 的 x = Y_AXIS_W + 1/270 × (800 − 36 − 40) ≈ 38.7
    fireEvent.mouseMove(svg, { clientX: 39, clientY: 100 });
    expect(container.querySelector('[data-testid="crosshair-v"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="crosshair-h"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="price-tag-text"]')).toBeTruthy();
    expect(readout().getAttribute("data-hovering")).toBe("true");
    expect(readout().children[0]!.textContent).toBe("09:01");

    fireEvent.mouseLeave(svg);
    expect(container.querySelector('[data-testid="crosshair-h"]')).toBeNull();
    expect(readout().getAttribute("data-hovering")).toBe("false");
  });
});

describe("MarketChart 空態", () => {
  it("series null → 「等待指數資料…」", () => {
    renderChart({ s: null, t: toggles({ cdp: false, ma: false }) });
    expect(screen.getByText("等待指數資料…")).toBeTruthy();
  });

  it("series 非 null 但 minutes 空 → core 空態同一句文案(不畫空軸)", () => {
    const { container } = renderChart({
      s: series({ minutes: {} }),
      t: toggles({ cdp: false, ma: false }),
    });
    expect(screen.getByText("等待指數資料…")).toBeTruthy();
    expect(container.querySelector("svg")).toBeNull();
  });
});

// `intradayBox` 的單位是 **px(1:1)**,不是 viewBox 單位 —— caller(MarketPane)已經扣掉
// figure / readout 列的 chrome。本檔只驗「拿到什麼就照畫」,px 那段的算術由
// MarketPane.size.test.tsx 鎖。`candleBox` 同型同單位,是 K 線態專用(intraday 不讀)。
describe("MarketChart intradayBox prop(SC-7)", () => {
  function intradaySvg(container: HTMLElement): Element {
    return container.querySelector('svg[role="img"]')!;
  }

  it("intraday:傳 intradayBox → svg viewBox 1:1;未傳 → core 預設 800×260", () => {
    const withBox = renderChart({
      t: toggles({ cdp: false, ma: false }),
      intradayBox: { width: 430, height: 272 },
    });
    expect(intradaySvg(withBox.container).getAttribute("viewBox")).toBe("0 0 430 272");
    cleanup();
    const noBox = renderChart({ t: toggles({ cdp: false, ma: false }) });
    expect(intradaySvg(noBox.container).getAttribute("viewBox")).toBe("0 0 800 260");
  });

  // WL-2:`pane-frame.ts::CANDLE_CHROME_Y` 把 meta 列算成 20px(text-xs 16 + mt-1 4),
  // 而它原本沒有高度限制 —— 窄 pane(1536 兩欄態 312px)下最長的來源字串超過 400px 會
  // 折成兩行,chromeY 少算 16 → svg 溢出 figure。折不折得掉由這一列自己保證。
  it("candle:meta 列固定一行(h-4 + truncate),chromeY 才算得準", async () => {
    stub(DK_BODY);
    renderCandle(undefined);
    const meta = await screen.findByTestId("market-meta");
    expect(meta.className).toContain("h-4");
    expect(meta.className).toContain("truncate");
  });

  it("candle:candleBox 透傳 CandleChart 走 1:1(未傳 → CandleChart 自有 1400×578)", async () => {
    stub(DK_BODY);
    const withH = renderCandle({ width: 430, height: 300 });
    const figure = await screen.findByTestId("candle-figure");
    expect(figure.querySelector("svg")!.getAttribute("viewBox")).toBe("0 0 430 300");
    withH.unmount();
    cleanup();
    renderCandle(undefined);
    const plain = await screen.findByTestId("candle-figure");
    expect(plain.querySelector("svg")!.getAttribute("viewBox")).toBe("0 0 1400 578");
  });
});
