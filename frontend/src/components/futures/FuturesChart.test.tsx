/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FuturesChart } from "@/components/futures/FuturesChart";
import { ALLDAY_WINDOW, alldayIndexOf } from "@/lib/allday";
import { svgBox } from "@/lib/chart-frame";
import { FUT_CHART_MODE_KEY } from "@/lib/constants";
import { fmtIndexPts } from "@/lib/format";
import { futuresBarsToAccum } from "@/lib/futures-accum-adapter";
import { buildIntradayGeometry, minuteToX } from "@/lib/stock-intraday-svg";
import { wrap } from "@/test-utils";
import type { Bar } from "@/lib/candle";
import type { CapitalPosition, FuturesProductState, OiLevelsResponse } from "@/types";

const META = {
  source: "tc4_1k",
  coverage_from: "2026-08-05",
  coverage_to: "2026-08-05",
  partial_last: true,
  volume: true,
  refusal: null,
  synth_since: null,
};

/** 窄幅 bar(分時折線只讀 `c`;K 線模式的 y 域就是這一帶)。 */
function bar(t: string, c: number): Bar {
  return { t, o: c, h: c + 1_000, l: c - 1_000, c, v: 10, uv: 6, dv: 4 };
}

const STATE: FuturesProductState = {
  product: "TXF",
  name: "臺股期貨",
  p: 23_000_000,
  q: 1,
  cum_vol: 100,
  t: "09:30:00",
  date: "20260805",
  bids: [[22_999_000, 5]],
  asks: [[23_001_000, 5]],
  ref: 22_950_000,
  upper: 25_000_000,
  lower: 20_000_000,
  resolved_contract: "202608",
};

function futPos(overrides: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "fut",
    stock_no: "TXFH6", // futExchangeContract("TXF", "202608")
    qty: 2,
    name: "臺股期貨",
    avg_price: 23_000,
    kind: "cash",
    pnl_base: null,
    pnl_base_price: null,
    pnl_cost: null,
    code: null,
    ...overrides,
  };
}

const EMPTY_OI: OiLevelsResponse = { date: null, contract: null, strikes: [] };

let barsUrls: string[] = [];
let barsBody: unknown;
let oiBody: unknown;
let oiStatus: number;
let positionsBody: unknown;

/** core 的 viewBox(jsdom 無 ResizeObserver → 退回 `IntradayChartCore` 的預設)。 */
const VB_W = 800;
const VB_H = 260;

/** 每個 x 座標在主價線 `points` 字串裡的形(core 的 `pts` 一律 toFixed(1))。 */
function xOf(index: number): string {
  return minuteToX(index, VB_W, ALLDAY_WINDOW).toFixed(1);
}

/** `last-dot` 的 `cx`(直接吃 `lastPt.x`,不經 toFixed)。 */
function cxOf(index: number): string {
  return String(minuteToX(index, VB_W, ALLDAY_WINDOW));
}

/** 分時態的 svg(core 的 `ariaLabel`);K 線態 / 空態下不存在 → 用它指認「走的是分時」。 */
function findIntraday(): Promise<HTMLElement> {
  return screen.findByRole("img", { name: "期貨近全時段分時走勢" });
}

/** 主價線的 x 座標串。
 *
 *  無昨收(`state={null}` → `meta.ref` null)→ 單條 `stroke-accent`;
 *  有昨收 → 紅綠雙段(同一份 points,取上半段那條)。均價線是 `stroke-ink`,不會誤中。 */
function mainLineXs(container: HTMLElement): string[] {
  const line = container.querySelector("polyline.stroke-accent, polyline.stroke-bull");
  return (line?.getAttribute("points") ?? "")
    .trim()
    .split(/\s+/)
    .filter((s) => s !== "")
    .map((p) => p.split(",")[0]!);
}

/** ResizeObserver 的最小替身(樣板同 `MarketPane.size.test`):`observe` 當下同步餵一筆。 */
class FakeResizeObserver {
  private readonly cb: ResizeObserverCallback;

  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }

  observe(node: Element): void {
    this.cb(
      [{ target: node, contentRect: { width: 1000, height: 500 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }

  unobserve(): void {}

  disconnect(): void {}
}

beforeEach(() => {
  window.localStorage.clear();
  barsUrls = [];
  barsBody = { bars: [], meta: META };
  oiBody = EMPTY_OI;
  oiStatus = 200;
  positionsBody = { positions: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      if (u.includes("/api/market/bars")) {
        barsUrls.push(u);
        return new Response(JSON.stringify(barsBody));
      }
      if (u.includes("/api/futures/oi-levels")) {
        return new Response(JSON.stringify(oiBody), { status: oiStatus });
      }
      if (u.includes("/api/capital/positions")) {
        return new Response(JSON.stringify(positionsBody));
      }
      throw new Error(`unexpected fetch: ${u}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("FuturesChart 模式列(SC-2)", () => {
  it("預設分時;切「5分」寫 localStorage 且 aria-pressed 跟隨", async () => {
    barsBody = { bars: [bar("2026-08-05 09:30", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    expect(screen.getByRole("button", { name: "分時" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "5分" }));
    expect(window.localStorage.getItem(FUT_CHART_MODE_KEY)).toBe("m5");
    expect(screen.getByRole("button", { name: "5分" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "分時" }).getAttribute("aria-pressed")).toBe("false");
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
  });

  it("localStorage 有合法值 → 還原該模式(日K 走 tf=D)", async () => {
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "day");
    barsBody = { bars: [bar("2026-08-04", 22_900_000), bar("2026-08-05", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    expect(screen.getByRole("button", { name: "日K" }).getAttribute("aria-pressed")).toBe("true");
    await waitFor(() => expect(barsUrls).toEqual(["/api/market/bars/TXF?tf=D"]));
  });
});

describe("FuturesChart 分時圖(SC-1)", () => {
  it("13:45 與 15:01 在近全軸上相鄰 —— 死區(13:46–15:00)不佔 x", async () => {
    barsBody = {
      bars: [bar("2026-08-05 13:45", 23_000_000), bar("2026-08-05 15:01", 23_020_000)],
      meta: META,
    };
    const { container } = wrap(<FuturesChart product="TXF" state={null} resolvedYm={null} />);
    await findIntraday();
    expect(mainLineXs(container)).toEqual([xOf(alldayIndexOf("1345")!), xOf(alldayIndexOf("1501")!)]);
    // 「相鄰」的定義寫死在斷言裡:兩個索引差 1 = 折線上只隔一個 slot
    expect(alldayIndexOf("1501")! - alldayIndexOf("1345")!).toBe(1);
  });

  it("前一交易日的 bars 被 slice 掉(錨定日以最後一根反推)", async () => {
    barsBody = {
      bars: [
        bar("2026-08-04 09:00", 22_800_000), // 前一交易日日盤 → 不該入圖
        bar("2026-08-05 09:00", 22_960_000),
        bar("2026-08-05 09:30", 23_000_000),
      ],
      meta: META,
    };
    const { container } = wrap(<FuturesChart product="TXF" state={null} resolvedYm={null} />);
    await findIntraday();
    expect(mainLineXs(container).length).toBe(2);
  });

  it("meta.source=unavailable → 進行式空態文案(不下「沒有資料」的結論)", async () => {
    barsBody = { bars: [], meta: { ...META, source: "unavailable" } };
    const { container } = wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("暫無資料(TC4 未回應)")).toBeTruthy());
    expect(container.querySelector('svg[aria-label="期貨近全時段分時走勢"]')).toBeNull();
  });
});

/** 換 `IntradayChartCore`(mode="futures")後的語彙(change-spec SC-1/2/3/4/7)。
 *
 *  這一組鎖的是**接線**:軸 / 時間文字 / 價位口徑 / hlines 有沒有真的注進 core。
 *  core 自身的契約在 `StockIntradayChart.futures.test.tsx`,不在這裡重測。 */
describe("FuturesChart 分時圖 core 語彙", () => {
  /** 三段都有 bar(日盤兩根 + 夜盤一根),h/l 由 `bar()` 給成 c±1 元 → 高低標記畫得出來。 */
  const CORE_BARS = [
    bar("2026-08-05 09:00", 22_960_000),
    bar("2026-08-05 09:30", 23_000_000),
    bar("2026-08-05 15:01", 22_980_000),
  ];

  beforeEach(() => {
    barsBody = { bars: CORE_BARS, meta: META };
    // jsdom 的 getBoundingClientRect 恆 0 → hover 座標換算需要真實寬高(frontend-testing 慣例)
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, right: VB_W, bottom: VB_H,
      width: VB_W, height: VB_H, x: 0, y: 0,
      toJSON: () => ({}),
    } as DOMRect);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderCore() {
    return wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
  }

  it("SC-2 底部時間標籤 = 注入的近全軸九個(不是現貨窗的 09:00–13:00)", async () => {
    const { container } = renderCore();
    await findIntraday();
    const labels = [
      ...container.querySelectorAll('svg[aria-label="期貨近全時段分時走勢"] text.fill-time'),
    ];
    expect(labels.map((t) => t.textContent)).toEqual([
      "09:00", "11:00", "13:00", "15:00", "18:00", "21:00", "00:00", "03:00", "05:00",
    ]);
  });

  it("SC-3 均價線末點標籤 / 當日高低環 / 現價圈 / 左緣三格刻度都在", async () => {
    renderCore();
    await findIntraday();
    expect(screen.getByTestId("edge-price-vwap")).toBeTruthy();
    expect(screen.getByTestId("day-high")).toBeTruthy();
    expect(screen.getByTestId("day-low")).toBeTruthy();
    expect(screen.getByTestId("last-dot")).toBeTruthy();
    // upper/lower 傳 null → 對稱 autofit 的三格(上 / 昨收 / 下)
    expect(screen.getAllByTestId("y-tick-price").length).toBe(3);
  });

  it("SC-4 成交量副圖 + 說明列 + toggle 五顆(CDP / MA / 成交點 反灰)+ VP", async () => {
    const { container } = renderCore();
    await findIntraday();
    expect(container.querySelector('svg[aria-label="成交量"]')).toBeTruthy();
    expect(container.querySelector("figcaption")).toBeTruthy();
    const defs: readonly (readonly [string, boolean])[] = [
      ["均價", false],
      ["CDP", true],
      ["MA", true],
      ["量分佈", false],
      ["成交點", true],
    ];
    for (const [name, off] of defs) {
      const btn = screen.getByRole("button", { name });
      expect(btn.hasAttribute("disabled")).toBe(off);
      if (off) {
        expect(btn.getAttribute("title")).toBe("期貨分時本輪不提供 CDP/MA/成交點");
      }
    }
    expect(container.querySelectorAll('[data-testid="vp-bar"]').length).toBeGreaterThanOrEqual(1);
  });

  it("SC-1 hover:十字 + 價位標整數點(不 snap 個股 tick)+ 時間標走近全軸 + readout 六欄", async () => {
    renderCore();
    const svg = await findIntraday();
    const idx = alldayIndexOf("0930")!;
    fireEvent.mouseMove(svg, { clientX: minuteToX(idx, VB_W, ALLDAY_WINDOW), clientY: 100 });

    expect(screen.getByTestId("crosshair-v")).toBeTruthy();
    expect(screen.getByTestId("crosshair-h")).toBeTruthy();
    expect(screen.getByTestId("time-tag-text").textContent).toBe("09:30");
    expect(screen.getByTestId("chart-readout").children.length).toBe(6);

    // 價標口徑:同一份 accum 走 core 幾何反演 → 整數點,不經 `snapDown`
    const accum = futuresBarsToAccum({
      bars: CORE_BARS,
      live: null,
      ref: STATE.ref,
      name: STATE.name,
      code: "TXF",
    });
    const g = buildIntradayGeometry(
      { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
      { width: VB_W, height: VB_H },
      ALLDAY_WINDOW,
    );
    expect(screen.getByTestId("price-tag-text").textContent).toBe(fmtIndexPts(g.priceAtY(100)));
  });

  it("SC-7 有 ResizeObserver → 主 / 副圖 viewBox 高按量測後的 260:70 拆分", async () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    const { container } = renderCore();
    const svg = await findIntraday();
    const box = svgBox({ width: 1000, height: 500 }, VB_W);
    const mainH = Math.round((box.viewBoxHeight * 260) / 330);
    expect(box.usable).toBe(true);
    expect(svg.getAttribute("viewBox")).toBe(`0 0 ${VB_W} ${mainH}`);
    expect(container.querySelector('svg[aria-label="成交量"]')!.getAttribute("viewBox")).toBe(
      `0 0 ${VB_W} ${box.viewBoxHeight - mainH}`,
    );
  });

  it("SC-7 無 ResizeObserver(jsdom 預設)→ 退回 core 預設 800×260", async () => {
    expect(typeof ResizeObserver).toBe("undefined");
    renderCore();
    const svg = await findIntraday();
    expect(svg.getAttribute("viewBox")).toBe(`0 0 ${VB_W} ${VB_H}`);
  });
});

describe("FuturesChart 背景輪詢 gate(LF-2)", () => {
  it("active=false → 不輪詢(期貨 tab hidden 時不打 TC4)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0)); // 夜盤:active=true 時會輪詢
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m1");
    barsBody = { bars: [bar("2026-08-05 22:00", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" active={false} />);
    await vi.advanceTimersByTimeAsync(0);
    const before = barsUrls.length;
    expect(before).toBe(1);
    await vi.advanceTimersByTimeAsync(180_000);
    expect(barsUrls.length).toBe(before);
  });

  it("active=true → 照輪詢(prop 真的接到 hook 上,不是擺著好看)", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 7, 5, 22, 0));
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m1");
    barsBody = { bars: [bar("2026-08-05 22:00", 23_000_000)], meta: META };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" active />);
    await vi.advanceTimersByTimeAsync(0);
    const before = barsUrls.length;
    await vi.advanceTimersByTimeAsync(65_000);
    expect(barsUrls.length).toBeGreaterThan(before);
  });
});

describe("FuturesChart live 現價點(§3.2 錨定日 gate)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it("時鐘落後資料:末根 bar = D 05:00(軸尾)、時鐘 D 08:45:30 → 不畫 live 點", async () => {
    barsBody = {
      bars: [bar("2026-08-05 04:59", 22_900_000), bar("2026-08-05 05:00", 22_910_000)],
      meta: META,
    };
    // 05:00 那根屬**前一交易日**(2026-08-04)的夜盤後半;08:46 的 live 點屬 08-05。
    // 此案 tail.index(1139)> live.index(0),兩道 gate 同時成立 → 只證「有擋」。
    vi.setSystemTime(new Date(2026, 7, 5, 8, 45, 30));
    const { container } = wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday();
    // gate 擋下 = 序列不追加 live 分鐘、現價圈落在末根 bar 的 x(不是「圈不見了」)
    expect(mainLineXs(container).length).toBe(2);
    expect(screen.getByTestId("last-dot").getAttribute("cx")).toBe(cxOf(alldayIndexOf("0500")!));
  });

  it("錨定日 gate 獨立於時鐘落後守衛:末根 = 前一交易日 08:46、時鐘 = 次日 08:47 → 不畫", async () => {
    // 唯一一根 bar 是**前一交易日**的首根(軸索引 0);live 落 08:48(軸索引 2)。
    // tail.index(0) > live.index(2) 不成立 → 時鐘落後守衛整條不參與,
    // 擋下 live 點的只剩錨定日不同這一條(短路它 → 假 live 點被畫在今日圖上)。
    barsBody = { bars: [bar("2026-08-04 08:46", 22_900_000)], meta: META };
    vi.setSystemTime(new Date(2026, 7, 5, 8, 47, 0));
    const { container } = wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday();
    // 前置條件寫死在斷言裡:兩個索引的大小關係就是「守衛沒被觸發」的證據
    expect(alldayIndexOf("0846")).toBe(0);
    expect(alldayIndexOf("0848")).toBe(2);
    expect(mainLineXs(container).length).toBe(1);
    expect(screen.getByTestId("last-dot").getAttribute("cx")).toBe(cxOf(0));
  });

  it("gate 4 單獨成立:末根 bar 索引 > live 索引(bars 至 D 10:00、時鐘 D 09:30)→ 不追加", async () => {
    // 錨定日相同、live 分鐘不在死區 → 前三道 gate 全不成立,擋下的只剩「時鐘落後資料」。
    barsBody = {
      bars: [bar("2026-08-05 09:00", 22_960_000), bar("2026-08-05 10:00", 23_000_000)],
      meta: META,
    };
    vi.setSystemTime(new Date(2026, 7, 5, 9, 30, 0));
    const { container } = wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday();
    // 前置條件寫死在斷言裡:live 落 09:31,末根 bar 的索引在它之後
    expect(alldayIndexOf("1000")!).toBeGreaterThan(alldayIndexOf("0931")!);
    expect(mainLineXs(container).length).toBe(2);
    expect(screen.getByTestId("last-dot").getAttribute("cx")).toBe(cxOf(alldayIndexOf("1000")!));
  });

  it("同一錨定日:live 點以「當前分 + 1」為終點標記落在序列尾", async () => {
    barsBody = {
      bars: [bar("2026-08-05 09:00", 22_960_000), bar("2026-08-05 09:30", 23_000_000)],
      meta: META,
    };
    vi.setSystemTime(new Date(2026, 7, 5, 9, 35, 30));
    const { container } = wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday();
    // live 分鐘是**新索引** → 序列多一格,現價圈落在它上面
    expect(mainLineXs(container).length).toBe(3);
    expect(screen.getByTestId("last-dot").getAttribute("cx")).toBe(cxOf(alldayIndexOf("0936")!));
  });

  it("live 分鐘落死區(14:30)→ 不畫 live 點", async () => {
    barsBody = {
      bars: [bar("2026-08-05 13:44", 22_960_000), bar("2026-08-05 13:45", 23_000_000)],
      meta: META,
    };
    vi.setSystemTime(new Date(2026, 7, 5, 14, 30, 0));
    const { container } = wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday();
    expect(mainLineXs(container).length).toBe(2);
    expect(screen.getByTestId("last-dot").getAttribute("cx")).toBe(cxOf(alldayIndexOf("1345")!));
  });
});

describe("FuturesChart overlays(SC-7 均價線 / SC-11 OI 線)", () => {
  /** OI / 均價線都要落在 y 視窗內才畫得出來 → 給一根夠寬的 bar。 */
  const WIDE = [
    { t: "2026-08-05 09:30", o: 23_000_000, h: 23_600_000, l: 22_400_000, c: 23_000_000, v: 10 },
    { t: "2026-08-05 09:31", o: 23_000_000, h: 23_600_000, l: 22_400_000, c: 23_010_000, v: 10 },
  ];

  beforeEach(() => {
    window.localStorage.setItem(FUT_CHART_MODE_KEY, "m1");
    barsBody = { bars: WIDE, meta: META };
  });

  it("本契約部位 → 均價線 label 帶方向與口數", async () => {
    positionsBody = { positions: [futPos({ qty: 2, avg_price: 23_000 })] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("均 23000 多2口")).toBeTruthy());
  });

  it("空單 → label 用「空」", async () => {
    positionsBody = { positions: [futPos({ qty: -3, avg_price: 22_800 })] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("均 22800 空3口")).toBeTruthy());
  });

  it("非本契約 / 非期貨 / avg_price null → 不畫均價線", async () => {
    positionsBody = {
      positions: [
        futPos({ stock_no: "MXFH6" }), // 別的商品
        futPos({ stock_no: "TXFI6" }), // 別的月份(完整字串相等,不做前綴猜測)
        futPos({ market: "sec", stock_no: "TXFH6" }),
        futPos({ avg_price: null }),
      ],
    };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByText(/^均 /)).toBeNull();
  });

  it("resolvedYm null(合約未解析)→ 不畫均價線", async () => {
    positionsBody = { positions: [futPos()] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm={null} />);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByText(/^均 /)).toBeNull();
  });

  it("OI 撐壓:現價帶內取 max(深度價外的垃圾履約價不入選)", async () => {
    oiBody = {
      date: "2026-08-04",
      contract: "202608",
      strikes: [
        { strike: 22_500, call_oi: 100, put_oi: 8_000 },
        { strike: 23_500, call_oi: 9_000, put_oi: 100 },
        { strike: 55_000, call_oi: 99_999, put_oi: 0 },
      ],
    } satisfies OiLevelsResponse;
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByText("壓 23500")).toBeTruthy());
    expect(screen.getByText("撐 22500")).toBeTruthy();
    expect(screen.queryByText("壓 55000")).toBeNull();
  });

  it("oi-levels 500 → 線消失、圖照常(降級不拋 error boundary)", async () => {
    oiStatus = 500;
    oiBody = { detail: { error: "BOOM" } };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await waitFor(() => expect(screen.getByLabelText("K 線圖")).toBeTruthy());
    expect(screen.queryByText(/^壓 /)).toBeNull();
    expect(screen.queryByText(/^撐 /)).toBeNull();
  });
});

describe("FuturesChart 分時模式的 overlays(SC-7 / SC-11;與 K 線同一套語意)", () => {
  /** 分時的 y 域只由 close 與 ref 決定(高低價不參與)→ 用一低一高兩根撐開視窗,
   *  讓 22400–23600 這帶的 overlay 落得進來。localStorage 未設 = 預設分時模式。 */
  const SPAN = [bar("2026-08-05 09:30", 22_400_000), bar("2026-08-05 09:31", 23_600_000)];

  const OI_BODY: OiLevelsResponse = {
    date: "2026-08-04",
    contract: "202608",
    strikes: [
      { strike: 22_500, call_oi: 100, put_oi: 8_000 },
      { strike: 23_500, call_oi: 9_000, put_oi: 100 },
      { strike: 55_000, call_oi: 99_999, put_oi: 0 }, // 帶外垃圾履約價
    ],
  };

  beforeEach(() => {
    barsBody = { bars: SPAN, meta: META };
  });

  it("本契約部位 → 分時圖畫出均價 hline(label + 線元素)", async () => {
    positionsBody = { positions: [futPos({ qty: 2, avg_price: 23_000 })] };
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday(); // 確定走的是分時而非 CandleChart
    await waitFor(() => expect(screen.getByText("均 23000 多2口")).toBeTruthy());
    expect(screen.getAllByTestId("chart-hline").length).toBe(1);
  });

  it("OI 有值 → 分時圖畫出壓/撐 hline(帶外 55000 仍不入選)", async () => {
    oiBody = OI_BODY;
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday();
    await waitFor(() => expect(screen.getByText("壓 23500")).toBeTruthy());
    expect(screen.getByText("撐 22500")).toBeTruthy();
    expect(screen.queryByText("壓 55000")).toBeNull();
    expect(screen.getAllByTestId("chart-hline").length).toBe(2);
  });

  it("priceMilli 遠超 y 域 → 只不畫那一條(clamp 到邊緣 = 把圖外價位講成圖緣價位)", async () => {
    // 同一次 render 內一條在窗內、兩條在窗外 → 「只畫窗內那條」才是斷言,
    // 全部不畫或全部照畫都會紅(y 域上緣 = 23600 × 1.003、下緣 = 22400 × 0.997)
    positionsBody = {
      positions: [futPos({ qty: 2, avg_price: 23_000 }), futPos({ qty: 1, avg_price: 30_000 })],
    };
    oiBody = {
      date: "2026-08-04",
      contract: "202608",
      // 帶內(±10% of 23000)但落在 y 域下緣之外
      strikes: [{ strike: 21_000, call_oi: 5_000, put_oi: 5_000 }],
    } satisfies OiLevelsResponse;
    wrap(<FuturesChart product="TXF" state={STATE} resolvedYm="202608" />);
    await findIntraday();
    await waitFor(() => expect(screen.getByText("均 23000 多2口")).toBeTruthy());
    expect(screen.queryByText("均 30000 多1口")).toBeNull();
    expect(screen.queryByText("壓 21000")).toBeNull();
    expect(screen.queryByText("撐 21000")).toBeNull();
    expect(screen.getAllByTestId("chart-hline").length).toBe(1);
  });
});
