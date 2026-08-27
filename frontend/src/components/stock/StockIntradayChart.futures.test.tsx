/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import type { ChartHLine } from "@/components/stock/CandleChart";
import { IntradayChartCore, StockIntradayChart } from "@/components/stock/StockIntradayChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { ALLDAY_HOUR_TICKS, ALLDAY_WINDOW, alldayHhmmOf } from "@/lib/allday";
import type { Bar } from "@/lib/candle";
import { fmt, fmtIndexPts } from "@/lib/format";
import { futuresBarsToAccum } from "@/lib/futures-accum-adapter";
import { fromSnapshot } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  minuteToX,
  R_AXIS_W,
  SPOT_WINDOW,
  Y_AXIS_W,
} from "@/lib/stock-intraday-svg";
import { snapDown } from "@/lib/stock-tick";
import { hhmm, hourTicksOf } from "@/lib/time-labels";
import { wrap } from "@/test-utils";

/** `IntradayChartCore` 的 `mode="futures"` 契約(change-spec §3.1)。
 *
 *  這一檔鎖的是 **stock 與 futures 兩態的差集**(軸由 caller 注入、價位口徑走整數點、
 *  不打 `/api/stock/overlay`、hlines 由 caller 傳入),以及「stock 態逐字不變」(W-1)。
 *  差集靜默漂掉的樣態:期貨圖的底部時間標籤印成現貨窗的 09:00–13:00、readout 首欄印
 *  軸索引換算出來的假時刻(index 300 → 「05:00」而不是「15:01」)、或 core 拿
 *  `TXF.HOT` 當股號去打 `/api/stock/overlay/` 吃 400。 */

const VB = { width: 800, height: 260 };

/** 對稱域推導(fixture 可讀性靠這段註解,不靠讀者心算):
 *  ref 23000、分鐘收盤 [23000, 23050, 22960]、tick 極值 h 23060 / l 22940
 *  → 半幅 = max(60, 60, ref×1% = 230) × 1.1 = 253 → y 域 [22747, 23253]。
 *  → hline 23100 在域內(該畫)、23900 在域外(不該畫)。 */
const BARS: readonly Bar[] = [
  { t: "2026-08-17 15:01", o: 23_050_000, h: 23_050_000, l: 22_940_000, c: 22_960_000, v: 60, uv: 10, dv: 45 },
  { t: "2026-08-18 08:46", o: 23_000_000, h: 23_010_000, l: 22_990_000, c: 23_000_000, v: 120, uv: 70, dv: 40 },
  { t: "2026-08-18 09:00", o: 23_000_000, h: 23_060_000, l: 23_000_000, c: 23_050_000, v: 80, uv: 50, dv: 20 },
];

/** 軸索引(15:00 起算):15:01 → 0(軸起點)、08:46 → 1065、09:00 → 1079;
 *  夜盤側 + 日盤側都有 → adapter 在 08:45(1064)補一格水平橋(mod/futures-day-1500)。 */
const IDX_1501 = 0;
const IDX_BRIDGE = 1064;
const IDX_0846 = 1065;
const IDX_0900 = 1079;

const FUT = futuresBarsToAccum({
  bars: BARS,
  live: null,
  ref: 23_000_000,
  name: "台指近",
  code: "TXF.HOT",
});

/** live 落在**新索引**(09:01 的 1K 尚未回)→ 末格是 v=0 的佔位格。
 *  同一份 accum 在 futures 態印「-」、在 stock 態印「0」(反向 lock:閘只在 futures 態開)。 */
const FUT_LIVE = futuresBarsToAccum({
  bars: BARS,
  live: { index: IDX_0900 + 1, p: 22_970_000 },
  ref: 23_000_000,
  name: "台指近",
  code: "TXF.HOT",
});

/** 模組層常數(identity 穩定,不打穿 ChartStatic 的 memo)—— 呼叫端的紀律同 `fills`。 */
const HLINES: readonly ChartHLine[] = [
  { priceMilli: 23_100_000, label: "均 23100 多2口", className: "stroke-bull", title: "持倉均價 23100 · 多 2 口" },
  { priceMilli: 23_900_000, label: "壓 23900", className: "stroke-bear" },
];

const TOGGLES: ChartToggles = { vwap: true, cdp: true, ma: true, bb: true, vp: true, fills: true, idxTwse: false, idxOtc: false, idxTxf: false, syncHover: true };

let fetchMock: Mock;

beforeEach(() => {
  window.localStorage.removeItem("copycat-chart-toggles");
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ cdp: null, ma5: null, ma20: null, date: null })));
  vi.stubGlobal("fetch", fetchMock);
  // jsdom getBoundingClientRect 恆 0 → hover 座標換算需要真實寬高(frontend-testing 慣例)
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0, top: 0, right: VB.width, bottom: VB.height,
    width: VB.width, height: VB.height, x: 0, y: 0,
    toJSON: () => ({}),
  } as DOMRect);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

type CoreProps = Parameters<typeof IntradayChartCore>[0];

/** 與 `FuturesChart` 的實際用法同一組 props。
 *  `overlaySupported={false}` = 日 K 回了但無已完成 bar(N042 後 CDP/MA 的反灰路徑)。 */
function renderFut(over: Partial<CoreProps> = {}) {
  return wrap(
    <IntradayChartCore
      accum={FUT}
      toggles={TOGGLES}
      onToggle={() => {}}
      variant="page"
      mode="futures"
      xWindow={ALLDAY_WINDOW}
      hourTicks={ALLDAY_HOUR_TICKS}
      timeText={alldayHhmmOf}
      hlines={HLINES}
      overlaySupported={false}
      ariaLabel="期貨近全時段分時走勢"
      {...over}
    />,
  );
}

/** polyline 的 x 座標串(points = "x,y x,y …",皆 toFixed(1))。 */
function xsOf(el: Element): string[] {
  return (el.getAttribute("points") ?? "")
    .trim()
    .split(/\s+/)
    .map((p) => p.split(",")[0]!);
}

describe("IntradayChartCore mode=\"futures\"", () => {
  it("readout 六欄,首欄走注入的 timeText(軸索引 1079 = 09:00,不是 hhmm 的 17:59)", () => {
    renderFut();
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children.length).toBe(6);
    // 無 hover → 序列末格(索引 1079)
    expect(readout.children[0]!.textContent).toBe("09:00");
    // 自檢:預設口徑會印別的字(否則本案恆綠)
    expect(hhmm(IDX_0900)).toBe("17:59");
  });

  it("成交量副圖 + 內外盤說明列都在(期貨 1K 帶 uv/dv,語彙同個股)", () => {
    const { container } = renderFut();
    expect(container.querySelector('svg[aria-label="成交量"]')).toBeTruthy();
    expect(container.querySelector("figcaption")).toBeTruthy();
    // 外 70+50+10 = 130 / 內 40+20+45 = 105 / 未分類 (120−110)+(80−70)+(60−55) = 25
    expect(screen.getByTestId("unch-total").textContent).toBe("25");
    expect(container.querySelectorAll("svg").length).toBe(2);
  });

  it("外框仍是 figure(page 變體;舊自繪版的 rounded-md 包框由 core 承接)", () => {
    const { container } = renderFut();
    expect(container.querySelector("figure")).toBeTruthy();
  });

  it("toggle 五顆:均價 / 量分佈 / **成交點** 可按;無日 K 時只有 CDP / MA 反灰(N043/N070)", () => {
    const { container } = renderFut();
    const btns = [...container.querySelectorAll("button")];
    expect(btns.map((b) => b.textContent)).toEqual(["均價", "CDP", "MA", "量分佈", "成交點"]);
    for (const i of [0, 3, 4]) expect(btns[i]!.hasAttribute("disabled")).toBe(false);
    for (const i of [1, 2]) {
      expect(btns[i]!.hasAttribute("disabled")).toBe(true);
      expect(btns[i]!.getAttribute("title")).toBe("無日線資料");
    }
  });

  it("VP 照畫(價位別量由分鐘收盤 × 量折入,不像 index 態整層停掉)", () => {
    const { container } = renderFut();
    expect(container.querySelectorAll('[data-testid="vp-bar"]').length).toBe(3);
  });

  it("注入的 xWindow:主價線 x = minuteToX(軸索引, 800, ALLDAY_WINDOW)", () => {
    const { container } = renderFut();
    const line = container.querySelector("polyline.stroke-bull")!;
    expect(xsOf(line)).toEqual(
      [IDX_1501, IDX_BRIDGE, IDX_0846, IDX_0900].map((i) => minuteToX(i, VB.width, ALLDAY_WINDOW).toFixed(1)),
    );
    // 自檢:現貨窗會算出完全不同的 x(否則本案恆綠)
    expect(minuteToX(IDX_1501, VB.width, ALLDAY_WINDOW)).not.toBeCloseTo(
      minuteToX(IDX_1501, VB.width, SPOT_WINDOW),
    );
  });

  it("注入的 hourTicks:底部九個近全軸標籤(15:00 起算;05:00 → 08:45 空檔保留在軸上)", () => {
    const { container } = renderFut();
    const labels = [...container.querySelectorAll('svg[aria-label="期貨近全時段分時走勢"] text.fill-time')];
    expect(labels.map((t) => t.textContent)).toEqual([
      "15:00", "18:00", "21:00", "00:00", "03:00", "05:00", "09:00", "11:00", "13:00",
    ]);
    expect(labels.map((t) => t.getAttribute("x"))).toEqual(
      ALLDAY_HOUR_TICKS.map((t) => String(minuteToX(t.minute, VB.width, ALLDAY_WINDOW) + 2)),
    );
  });

  it("hlines:域內那條照畫(testid / title / label / 繪圖區左右界),域外那條不畫", () => {
    const { container } = renderFut();
    const lines = screen.getAllByTestId("chart-hline");
    expect(lines.length).toBe(1);
    expect(lines[0]!.querySelector("title")!.textContent).toBe("持倉均價 23100 · 多 2 口");
    const text = lines[0]!.querySelector("text")!;
    expect(text.textContent).toBe("均 23100 多2口");
    expect(text.getAttribute("x")).toBe(String(VB.width - R_AXIS_W - 2));
    expect(text.getAttribute("text-anchor")).toBe("end");
    const seg = lines[0]!.querySelector("line")!;
    expect(seg.getAttribute("x1")).toBe(String(Y_AXIS_W));
    expect(seg.getAttribute("x2")).toBe(String(VB.width - R_AXIS_W));
    expect(seg.getAttribute("class")).toBe("stroke-bull");
    // 域外的 23900 一條都不留(clamp 到邊緣會把「圖外的價位」講成「圖緣的價位」)
    expect(container.textContent).not.toContain("壓 23900");
  });

  it("hlines 未傳 → 零渲染(stock / index 態的預設)", () => {
    const { container } = renderFut({ hlines: undefined });
    expect(container.querySelectorAll('[data-testid="chart-hline"]').length).toBe(0);
  });

  it("hover:價位標整數點不 snap tick(期指沒有個股 tick 表)+ 底部時間標走 timeText", () => {
    const { container } = renderFut();
    const svg = container.querySelector('svg[aria-label="期貨近全時段分時走勢"]')!;
    fireEvent.mouseMove(svg, {
      clientX: minuteToX(IDX_0900, VB.width, ALLDAY_WINDOW),
      clientY: 100,
    });
    const g = buildIntradayGeometry(
      { minutes: FUT.minutes, meta: FUT.meta, high: FUT.high, low: FUT.low },
      VB,
      ALLDAY_WINDOW,
    );
    const raw = g.priceAtY(100);
    expect(screen.getByTestId("price-tag-text").textContent).toBe(fmtIndexPts(raw));
    // 自檢:這個 y 上 tick-snap 與整數點真的不同(否則本案恆綠)
    expect(fmtIndexPts(raw)).not.toBe(fmt(snapDown(raw)));
    expect(screen.getByTestId("time-tag-text").textContent).toBe("09:00");
    expect(screen.getByTestId("crosshair-v")).toBeTruthy();
  });

  it("live 佔位分鐘(v=0)→ readout 量 / 外 / 內 印「-」(bars 尚無 1K,印 0 是假數字)", () => {
    renderFut({ accum: FUT_LIVE });
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children[0]!.textContent).toBe("09:01");
    expect([3, 4, 5].map((i) => readout.children[i]!.textContent)).toEqual(["量 -", "外 -", "內 -"]);
  });

  it("有量的分鐘照印數字(「-」只針對 v=0 的佔位格)", () => {
    renderFut();
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children[3]!.textContent).toBe("量 80");
  });

  it("空序列 → 「無分時資料」(沿用舊自繪版字面)", () => {
    const empty = futuresBarsToAccum({ bars: [], live: null, ref: 23_000_000, name: "台指近", code: "TXF.HOT" });
    renderFut({ accum: empty });
    expect(screen.getByText("無分時資料")).toBeTruthy();
  });

  it("不打 /api/stock/overlay(TXF.HOT 不是股號;疊線一律由 caller 注入)", async () => {
    renderFut();
    await waitFor(() => expect(screen.getByTestId("chart-readout")).toBeTruthy());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/** W-1 lock:mode 預設(不傳)= stock,個股頁逐字不變。
 *
 *  這一組是 `const futures = mode === "futures"` 與 `ptsPrice = index || futures` 兩道閘的
 *  mutation 閘 —— 任一條的判準寫錯(例如 `pts` 改成 `!index`),下面就有案子紅。 */
describe("W-1:mode 預設 = stock,軸 / 時間文字 / 價位口徑 / hlines 零變化", () => {
  const STOCK = fromSnapshot({
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
    high: 2_395_000,
    low: 2_370_000,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  it("hourTicks 仍是 hourTicksOf(SPOT_WINDOW)(09:00–13:00 五個)", () => {
    const { container } = wrap(<StockIntradayChart accum={STOCK} />);
    const labels = [...container.querySelectorAll('svg[aria-label="分時走勢圖"] text.fill-time')];
    expect(labels.map((t) => t.textContent)).toEqual(
      hourTicksOf(SPOT_WINDOW).map((t) => t.label),
    );
  });

  it("時間文字仍走 hhmm(readout 首欄 + hover 底部標籤)", () => {
    const { container } = wrap(<StockIntradayChart accum={STOCK} />);
    expect(screen.getByTestId("chart-readout").children[0]!.textContent).toBe(hhmm(542));
    fireEvent.mouseMove(container.querySelector("svg")!, {
      clientX: minuteToX(541, VB.width, SPOT_WINDOW),
      clientY: 100,
    });
    expect(screen.getByTestId("time-tag-text").textContent).toBe("09:01");
  });

  it("hover 價位標仍 snap 到合法 tick(可下單價位)", () => {
    const { container } = wrap(<StockIntradayChart accum={STOCK} />);
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 300, clientY: 100 });
    const g = buildIntradayGeometry(
      { minutes: STOCK.minutes, meta: STOCK.meta, high: STOCK.high, low: STOCK.low },
      VB,
      SPOT_WINDOW,
    );
    const raw = g.priceAtY(100);
    expect(screen.getByTestId("price-tag-text").textContent).toBe(fmt(snapDown(raw)));
    expect(fmt(snapDown(raw))).not.toBe(fmtIndexPts(raw));
  });

  it("hlines 零渲染 + 仍打 /api/stock/overlay/<code>", async () => {
    const { container } = wrap(<StockIntradayChart accum={STOCK} />);
    expect(container.querySelectorAll('[data-testid="chart-hline"]').length).toBe(0);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/stock/overlay/2330");
  });

  it("**同一份** live 佔位 accum 在 stock 態仍印「量 0」(「-」的閘只在 futures 態開)", () => {
    // 軸窗照樣注入(`xWindow` 與 mode 是兩件事)—— 只有 `mode` 這一個變因不同,
    // 才證明得出翻面的是 `futures` 判別子而不是別的東西。
    wrap(
      <IntradayChartCore
        accum={FUT_LIVE}
        toggles={{ ...TOGGLES, cdp: false, ma: false }}
        onToggle={() => {}}
        variant="page"
        xWindow={ALLDAY_WINDOW}
        hourTicks={ALLDAY_HOUR_TICKS}
      />,
    );
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children.length).toBe(6);
    expect([3, 4, 5].map((i) => readout.children[i]!.textContent)).toEqual(["量 0", "外 0", "內 0"]);
  });
});

// 🔴 N045 / N044(mod/chart-label-batch):期貨態 VWAP 標籤口徑,與 hlines label 的走廊避讓。
describe("IntradayChartCore mode=\"futures\" 的 VWAP 標籤與 hline label(N045/N044)", () => {
  it("VWAP 文字走整數點口徑(fmtIndexPts),不再是同圖唯一的 fmt 兩位小數", () => {
    const { container } = renderFut();
    // Σc·v / Σv = 23_006_154(毫點)→ `fmt` 印「23006.15」(8 字)、整數點口徑印「23006」
    expect(FUT.vwap).toBe(23_006_154);
    expect(fmt(23_006_154)).toBe("23006.15");
    expect(fmtIndexPts(23_006_154)).toBe("23006");
    expect(container.querySelector('[data-testid="edge-price-vwap"]')!.textContent).toBe("23006");
  });

  /** 近全軸末格(13:45 → 索引 1364)有 bar → VWAP 末點貼繪圖區右界,標籤 x 區間
   *  [720, 760] 與 hline label(anchor=end,右緣 758)完全重疊。
   *  vwap = (23000×120 + 23050×80 + 22960×60 + 23000×60) / 320 = 23_005(毫點 ×1000)。 */
  const FUT_LATE = futuresBarsToAccum({
    bars: [
      ...BARS,
      { t: "2026-08-18 13:45", o: 23_000_000, h: 23_010_000, l: 22_990_000, c: 23_000_000, v: 60, uv: 30, dv: 30 },
    ],
    live: null,
    ref: 23_000_000,
    name: "台指近",
    code: "TXF.HOT",
  });
  /** 域 [22_747_000, 23_253_000] → toY(23_000_000) = 123、label baseline 120 / 中心 117;
   *  VWAP 末點 toY(23_005_000) ≈ 120.63 → 中心距 3.63px(修前),兩層 halo 互蓋。 */
  const HLINE_NEAR: readonly ChartHLine[] = [
    { priceMilli: 23_000_000, label: "均 23000 多2口", className: "stroke-bull" },
  ];

  it("hline label 與 VWAP 末點標籤同走廊且 y 幾乎重合 → label 讓位(中心距 ≥ 10),線體不動", () => {
    const { container } = renderFut({ accum: FUT_LATE, hlines: HLINE_NEAR });
    const g = buildIntradayGeometry(
      { minutes: FUT_LATE.minutes, meta: FUT_LATE.meta, high: FUT_LATE.high, low: FUT_LATE.low },
      VB,
      ALLDAY_WINDOW,
    );
    const vwapY = Number(
      container.querySelector('[data-testid="edge-price-vwap"]')!.getAttribute("y"),
    );
    // 前置(敏感度所繫):末點真的貼右界,且兩者 y 差 < 10px
    expect(g.vwapLine.at(-1)!.x).toBeCloseTo(VB.width - R_AXIS_W, 6);
    expect(Math.abs(g.toY(23_000_000) - 6 - vwapY)).toBeLessThan(10);
    const hl = screen.getAllByTestId("chart-hline")[0]!;
    const text = hl.querySelector("text")!;
    // hline label 無 dy → y 是 baseline,中心 = baseline − 3
    expect(Math.abs(Number(text.getAttribute("y")) - 3 - vwapY)).toBeGreaterThanOrEqual(10);
    // 讓位的只有文字:線體仍畫在真價位上,x 也不動
    expect(Number(hl.querySelector("line")!.getAttribute("y1"))).toBeCloseTo(g.toY(23_000_000), 6);
    expect(text.getAttribute("x")).toBe(String(VB.width - R_AXIS_W - 2));
  });

  /** 🔴 讓位路徑的**界單位**(2026-08-24 two-axis review N044-2)。
   *
   *  `edgeBounds`(`{ MARK_LABEL_TOP, plotBottom − 5 }`)是 **baseline** 語意(它與
   *  `markLabelY` 的 limits 同一組數字),但讓位路徑拿它去夾**中心**值再 +3 還原 ——
   *  於是有效的 baseline 上界變成 12 而不是 9,整整差一個 `BASELINE_TO_CENTER`。
   *
   *  幾何:tick 極值 h 23_240 / l 23_230(全段在 ref 之上)→ 半幅 = max(240, −230, 230)
   *  × 1.1 = 264 → 域 [22_736_000, 23_264_000],toY(p) = 4 + (23_264_000 − p)/528_000 × 238。
   *  vwap = (23_230×10 + 23_240×10) / 20 = 23_235 → 末點 y ≈ 17.07(貼右界);
   *  hline 23_240_000 → 線 y ≈ 14.82、label 中心 8.82 → 中心距 8.25 < 10,往上讓到 7.07。
   *  修前那顆 7.07 被「中心值 vs baseline 界」夾成 9 → **與 VWAP 只剩 8.07px,仍疊印**:
   *  讓了位卻沒讓開,是 clamp 單位混用唯一會顯形的地方。 */
  const FUT_TOP = futuresBarsToAccum({
    bars: [
      { t: "2026-08-18 08:46", o: 23_230_000, h: 23_240_000, l: 23_230_000, c: 23_230_000, v: 10, uv: 5, dv: 5 },
      { t: "2026-08-18 13:45", o: 23_240_000, h: 23_240_000, l: 23_235_000, c: 23_240_000, v: 10, uv: 5, dv: 5 },
    ],
    live: null,
    ref: 23_000_000,
    name: "台指近",
    code: "TXF.HOT",
  });
  const HLINE_TOP: readonly ChartHLine[] = [
    { priceMilli: 23_240_000, label: "均 23240 多1口", className: "stroke-bull" },
  ];

  it("讓位撞到走廊頂界 → 夾制與界同語意(baseline ≥ 9),不因單位混用被推回 VWAP 上", () => {
    const { container } = renderFut({ accum: FUT_TOP, hlines: HLINE_TOP });
    const g = buildIntradayGeometry(
      { minutes: FUT_TOP.minutes, meta: FUT_TOP.meta, high: FUT_TOP.high, low: FUT_TOP.low },
      VB,
      ALLDAY_WINDOW,
    );
    const vwapY = Number(
      container.querySelector('[data-testid="edge-price-vwap"]')!.getAttribute("y"),
    );
    // 前置(敏感度所繫):末點貼右界(x 區間相交)、hline label 在 VWAP 上方且中心距 < 10、
    // 且讓開後的位置落在「9 與 6」兩種界之間 —— 三者缺一本案就量不到單位差。
    expect(g.vwapLine.at(-1)!.x).toBeCloseTo(VB.width - R_AXIS_W, 6);
    const rawCenter = g.toY(23_240_000) - 3 - 3;
    expect(rawCenter).toBeLessThan(vwapY);
    expect(vwapY - rawCenter).toBeLessThan(10);
    expect(vwapY - 10).toBeGreaterThan(6);
    expect(vwapY - 10).toBeLessThan(9);
    const text = screen.getAllByTestId("chart-hline")[0]!.querySelector("text")!;
    // 讓位後真的讓開(修前:被夾成 baseline 12 / 中心 9,與 VWAP 只差 8.07px)
    expect(Math.abs(Number(text.getAttribute("y")) - 3 - vwapY)).toBeGreaterThanOrEqual(10);
    // 界仍然守得住:baseline 不得超出 `MARK_LABEL_TOP`(字上緣頂到 viewBox 外)
    expect(Number(text.getAttribute("y"))).toBeGreaterThanOrEqual(9);
  });

  /** 🔴 N044 補完(2026-08-24 two-axis review):hline label 與 **MA 價位標**同走廊。
   *
   *  兩者都 anchor=end 釘在 `w − R_AXIS_W − 2`,x 區間必然相交;至今誰也不避誰 ——
   *  持倉均價恰好落在 MA5 上(常見:均價就是這幾天的成本區)時兩層 halo 直接疊印。
   *  hline label 的 y 由線位決定(與線體同一條資訊),MA 價位標是「這條線在哪」的冗餘
   *  數值 → 讓位的是 MA。
   *
   *  可達性:`hlines` 與注入式 `overlay` 都是 core 的 prop,index 態(`MarketChart`)與
   *  期貨態(疊線已列 next-time)任一邊補上另一半就會同時出現;契約先鎖住,否則那天
   *  只會靜默疊印。幾何:域 [22_747_000, 23_253_000] → toY(23_100_000) ≈ 75.96,
   *  hline label 中心 69.96、MA5 標籤中心 75.96 → 中心距 6px。 */
  const HLINE_ON_MA: readonly ChartHLine[] = [
    { priceMilli: 23_100_000, label: "均 23100 多2口", className: "stroke-bull" },
  ];
  const OVERLAY_MA = { cdp: null, ma5: 23_100_000, ma20: 22_800_000, date: "2026-08-18" };

  it("持倉均價 hline 貼近 MA5 價位 → MA 價位標讓位,hline label 與線體不動", () => {
    const { container } = renderFut({
      hlines: HLINE_ON_MA,
      overlay: OVERLAY_MA,
      overlaySupported: true,
    });
    const g = buildIntradayGeometry(
      { minutes: FUT.minutes, meta: FUT.meta, high: FUT.high, low: FUT.low },
      VB,
      ALLDAY_WINDOW,
    );
    const lineY = g.toY(23_100_000);
    const hlText = screen.getAllByTestId("chart-hline")[0]!.querySelector("text")!;
    const ma5 = container.querySelector('[data-testid="edge-price-ma5"]')!;
    // 前置(敏感度所繫):MA5 真的畫出來了,且未避讓時兩者中心距 < EDGE_LABEL_H
    expect(Number(hlText.getAttribute("y"))).toBeCloseTo(lineY - 3, 6);
    expect(Math.abs(lineY - (lineY - 3 - 3))).toBeLessThan(10);
    // MA 價位標(dy=0.35em → y 即中心)讓開 hline label 的中心
    expect(
      Math.abs(Number(ma5.getAttribute("y")) - (Number(hlText.getAttribute("y")) - 3)),
    ).toBeGreaterThanOrEqual(10);
    // 線體照畫在真價位上;MA20 遠離,不受牽連
    expect(
      Number(screen.getAllByTestId("chart-hline")[0]!.querySelector("line")!.getAttribute("y1")),
    ).toBeCloseTo(lineY, 6);
    expect(
      Number(container.querySelector('[data-testid="edge-price-ma20"]')!.getAttribute("y")),
    ).toBeCloseTo(g.toY(22_800_000), 6);
  });

  it("對照組:hline 遠離 VWAP 末點 → label y 仍為「線 y − 3」逐值不變", () => {
    const { container } = renderFut();
    const g = buildIntradayGeometry(
      { minutes: FUT.minutes, meta: FUT.meta, high: FUT.high, low: FUT.low },
      VB,
      ALLDAY_WINDOW,
    );
    const text = screen.getAllByTestId("chart-hline")[0]!.querySelector("text")!;
    expect(Number(text.getAttribute("y"))).toBeCloseTo(g.toY(23_100_000) - 3, 6);
    expect(container.querySelector('[data-testid="edge-price-vwap"]')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// R2:期貨態疊線注入(N042)/ 成交點(N043+N070)/ hover 命中(N046)/ VP·POC(N096)
// ---------------------------------------------------------------------------

/** 域 [22747, 23253](見 BARS 上方推導):ah 23300 域外、nh 23100 與 cdp 23000 域內。 */
const OVERLAY = {
  cdp: { cdp: 23_000_000, ah: 23_300_000, nh: 23_100_000, nl: 22_900_000, al: 22_700_000 },
  ma5: 23_050_000,
  ma20: null,
  date: "2026-08-21",
};

/** 模組層常數(identity 穩定,同 hlines) */
const FILLS = [
  { minute: IDX_0900, priceMilli: 23_050_000, side: "B" as const, qty: 2 },
  { minute: IDX_1501, priceMilli: 22_960_000, side: "S" as const, qty: 1 },
];

describe("mode=\"futures\" 的疊線注入(N042)", () => {
  it("overlay 注入 + supported → CDP/MA 可按,域內的線畫得出來(域外的 ah 不畫)", () => {
    const { container } = renderFut({ overlay: OVERLAY, overlaySupported: true });
    const btns = [...container.querySelectorAll("button")];
    expect(btns[1]!.hasAttribute("disabled")).toBe(false); // CDP
    expect(btns[2]!.hasAttribute("disabled")).toBe(false); // MA
    // 五條 CDP 中 nh / cdp / nl 在域內,ah / al 域外;ma5 在域內 → 共 4 條
    const dashed = [...container.querySelectorAll("line[stroke-dasharray='3 2']")];
    expect(dashed.length).toBe(4);
  });

  it("右緣 CDP 價位標走整數點口徑 + `*`,MA 價位標走同一把尺(不是個股 tick snap)", () => {
    renderFut({ overlay: OVERLAY, overlaySupported: true });
    expect(screen.getByTestId("edge-price-ma5").textContent).toBe(fmtIndexPts(23_050_000));
    const band = screen.getAllByText(/\*$/).map((t) => t.textContent);
    expect(band).toContain(`${fmtIndexPts(23_100_000)}*`);
  });

  it("overlay = null(日 K 尚未回)→ 不預先反灰、也不畫線", () => {
    const { container } = renderFut({ overlay: null, overlaySupported: true });
    const btns = [...container.querySelectorAll("button")];
    expect(btns[1]!.hasAttribute("disabled")).toBe(false);
    expect(container.querySelectorAll("line[stroke-dasharray='3 2']").length).toBe(0);
  });

  it("overlayError(日 K 查詢失敗)→ CDP/MA 反灰", () => {
    const { container } = renderFut({ overlay: OVERLAY, overlaySupported: true, overlayError: true });
    const btns = [...container.querySelectorAll("button")];
    expect(btns[1]!.hasAttribute("disabled")).toBe(true);
    expect(btns[2]!.hasAttribute("disabled")).toBe(true);
  });

  it("疊線基準日印在說明列(與個股頁同一句)", () => {
    const { container } = renderFut({ overlay: OVERLAY, overlaySupported: true });
    expect(container.querySelector("figcaption")!.textContent).toContain("疊線基準 2026-08-21");
  });
});

describe("mode=\"futures\" 的成交點(N043/N070)", () => {
  it("fills 注入 → 買 ▲ / 賣 ▼ 落在近全軸索引上", () => {
    const { container } = renderFut({ fills: FILLS });
    expect(container.querySelectorAll('[data-testid^="fill-"]').length).toBe(2);
    const buy = screen.getByTestId(`fill-B-${IDX_0900}`);
    // 三角尖端 x = minuteToX(軸索引)(常態寬度下 clampFillX 是 no-op)
    expect(buy.getAttribute("points")!.split(",")[0]).toBe(
      String(minuteToX(IDX_0900, VB.width, ALLDAY_WINDOW)),
    );
    expect(screen.getByTestId(`fill-S-${IDX_1501}`)).toBeTruthy();
  });

  it("toggle 關 → 整層零標記(層本身仍在)", () => {
    const { container } = renderFut({ fills: FILLS, toggles: { ...TOGGLES, fills: false } });
    expect(container.querySelectorAll('[data-testid^="fill-"]').length).toBe(0);
    expect(screen.getByTestId("fills-layer")).toBeTruthy();
  });

  it("readout 追加「成交」欄(hover 到有成交的那一格)", () => {
    const { container } = renderFut({ fills: FILLS });
    const svg = container.querySelector('svg[aria-label="期貨近全時段分時走勢"]')!;
    fireEvent.mouseMove(svg, { clientX: minuteToX(IDX_0900, VB.width, ALLDAY_WINDOW), clientY: 100 });
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children[6]!.textContent).toContain("買 2@");
  });
});

describe("mode=\"futures\" 的 hover 命中(N046)", () => {
  /** 09:01(索引 15)沒有 bar —— 現貨態的規則是整段退化(十字垂直線不畫)。 */
  const IDX_0901 = IDX_0900 + 1;

  it("落在無 bar 的相鄰索引 → 命中最近有 bar 的那一分鐘(垂直線 x = 該分鐘)", () => {
    const { container } = renderFut();
    const svg = container.querySelector('svg[aria-label="期貨近全時段分時走勢"]')!;
    fireEvent.mouseMove(svg, { clientX: minuteToX(IDX_0901, VB.width, ALLDAY_WINDOW), clientY: 100 });
    expect(screen.getByTestId("crosshair-v").getAttribute("x1")).toBe(
      String(minuteToX(IDX_0900, VB.width, ALLDAY_WINDOW)),
    );
    expect(screen.getByTestId("time-tag-text").textContent).toBe("09:00");
  });

  it("離最近的 bar 超過閾值 → 維持既有退化(水平量尺在、垂直線不畫)", () => {
    const { container } = renderFut();
    const svg = container.querySelector('svg[aria-label="期貨近全時段分時走勢"]')!;
    fireEvent.mouseMove(svg, {
      clientX: minuteToX(IDX_0900 + 20, VB.width, ALLDAY_WINDOW),
      clientY: 100,
    });
    expect(screen.queryByTestId("crosshair-v")).toBeNull();
    expect(screen.getByTestId("crosshair-h")).toBeTruthy();
  });

  it("stock 態不 snap(W-1:同一個相鄰空分鐘仍退化)", () => {
    const acc = fromSnapshot({
      code: "2330",
      seq: 1,
      last: { p: 2_380_000, t: "09:00:30.000", cum_vol: 10 },
      vwap: 2_380_000,
      minutes: { "540": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
      ticks: [],
      book: null,
      meta: { name: "台積電", ref: 2_380_000, upper: 2_550_000, lower: 2_090_000, y_vol: 1 },
    });
    const { container } = wrap(
      <IntradayChartCore accum={acc} toggles={TOGGLES} onToggle={() => {}} variant="page" />,
    );
    const svg = container.querySelector('svg[aria-label="分時走勢圖"]')!;
    fireEvent.mouseMove(svg, { clientX: minuteToX(541, VB.width, SPOT_WINDOW), clientY: 100 });
    expect(screen.queryByTestId("crosshair-v")).toBeNull();
  });
});

describe("mode=\"futures\" 的 VP / POC(N096 characterization)", () => {
  it("POC = 域內量最大的價位帶,highlight + 價位標(語彙同現貨)", () => {
    const { container } = renderFut();
    const bars = [...container.querySelectorAll('[data-testid="vp-bar"]')];
    const poc = bars.filter((b) => b.getAttribute("class") === "fill-accent");
    expect(poc.length).toBe(1);
    // BARS 的量:08:46 120 / 09:00 80 / 15:01 60 → POC = 23000 那一桶。
    // 標籤字面是**桶心**「23002.5」不是檔位價「23000」:期貨 vp 的 key 由
    // `futuresBarsToAccum` 取 `snapDown(c) + tickOf(c)/2`(帶界才與桶區間一致)。
    // 這是既有行為,本輪只釘住不改(要改屬另案:期貨 POC 標籤印檔位價)。
    expect(screen.getByTestId("vp-poc-label").textContent).toBe("23002.5");
  });

  it("量分佈 toggle 關 → 整組長條與 POC 標都消失", () => {
    const { container } = renderFut({ toggles: { ...TOGGLES, vp: false } });
    expect(container.querySelectorAll('[data-testid="vp-bar"]').length).toBe(0);
    expect(screen.queryByTestId("vp-poc-label")).toBeNull();
  });
});

describe("VP 折入來源被截斷的標示(N087)", () => {
  it("accum.vpTruncated → 量分佈鈕 tooltip 講明只含最近 20000 筆", () => {
    const { container } = renderFut({ accum: { ...FUT, vpTruncated: true } });
    const vpBtn = [...container.querySelectorAll("button")][3]!;
    expect(vpBtn.getAttribute("title")).toContain("20000");
  });

  it("未截斷 → 無 tooltip(不對正常日多講一句)", () => {
    const { container } = renderFut();
    expect([...container.querySelectorAll("button")][3]!.getAttribute("title")).toBeNull();
  });
});
