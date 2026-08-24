/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { CHART_TOGGLES_KEY } from "@/lib/constants";
import {
  clampFillX,
  FILL_MARK,
  fillTrianglePoints,
  type FillPoint,
} from "@/lib/fill-marks";
import { fromSnapshot } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  EDGE_LABEL_H,
  lastPoint,
  minuteToX,
  R_AXIS_W,
  SPOT_WINDOW,
  STKFUT_WINDOW,
  Y_AXIS_W,
} from "@/lib/stock-intraday-svg";
import { VP_FILL_OPACITY, VP_POC_FILL_OPACITY } from "@/lib/volume-profile";
import { wrap } from "@/test-utils";

/** SC-9 的計次通道。**delegate 原實作**(`vi.fn(actual.…)` 只多記一次呼叫)——
 *  換成假回傳值的話同檔 SC-3 的頂點座標斷言全部變成在量假資料,而它們照樣會綠。
 *  `vi.mock` 是檔案級 + hoisted,所以整檔的 `fillTrianglePoints` 都是這個計次版。 */
vi.mock("@/lib/fill-marks", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/fill-marks")>();
  return { ...actual, fillTrianglePoints: vi.fn(actual.fillTrianglePoints) };
});

const OVERLAY = {
  // ah / nh 刻意用**非合法檔位**(後端 CDP 公式不保證對齊 tick,這正是顯示層要
  // fmtTickPrice 的理由)。2_401_237 → snap 到 2_400_000 → 顯示 "2400*";
  // 沒 snap 的話會顯示 "2401.2*" 這種下不了單的價位(self-review B4)。
  cdp: { cdp: 2_320_000, ah: 2_401_237, nh: 2_357_800, nl: 2_280_000, al: 2_240_000 },
  ma5: 2_330_000,
  ma20: 2_310_000,
  date: "2026-07-25",
};

let overlayResponse: object = OVERLAY;

beforeEach(() => {
  window.localStorage.removeItem("copycat-chart-toggles");
  overlayResponse = OVERLAY;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(overlayResponse))),
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
});

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
  vwap: 2_380_000,
  minutes: {
    // round4 項 1:per-minute h/l 是當日高低標記的定位依據 —— 標記畫在「摸到極值的
    // 那一分鐘」上,而 541 的高(2_395_000)高於任何一分鐘的收盤,正是「摸到就算」的樣態
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_395_000, l: 2_370_000 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
  },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
});

describe("StockIntradayChart", () => {
  it("渲染價線/VWAP/內外盤副圖", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const polylines = container.querySelectorAll("polyline");
    expect(polylines.length).toBeGreaterThanOrEqual(2);
    expect(container.querySelectorAll("svg").length).toBeGreaterThanOrEqual(1);
    // round6 項 2:說明列由「累積外盤 / 內盤 / 外盤比」改為「外盤 / 內盤 / 未分類 /
    // 外盤比(判定率)」—— 四個數字改為同源(sideSummary),不再混用後端 running 值
    expect(screen.getByText(/外盤比/)).toBeTruthy();
  });

  // 🔴 SC-2:走勢線平盤上紅、平盤下綠(clipPath 切上下兩段),線與平盤之間填半透明色塊
  it("價線雙色 + 平盤填色:bull/bear 各一條 polyline 與一個 polygon", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelector('polyline[class*="stroke-bull"]')).toBeTruthy();
    expect(container.querySelector('polyline[class*="stroke-bear"]')).toBeTruthy();
    const up = container.querySelector('polygon[class*="fill-bull"]');
    const down = container.querySelector('polygon[class*="fill-bear"]');
    expect(up).toBeTruthy();
    expect(down).toBeTruthy();
    expect(up!.getAttribute("fill-opacity")).toBe("0.15");
    expect(down!.getAttribute("fill-opacity")).toBe("0.15");
  });

  it("clipPath id 互異、只含識別字元,且被對應元素以 url(#…) 引用", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const clips = [...container.querySelectorAll("clipPath")];
    expect(clips.length).toBe(2);
    const ids = clips.map((c) => c.getAttribute("id")!);
    expect(new Set(ids).size).toBe(2);
    // React 19 的 useId 產出 «r0» 形態,含非識別字元;必須過濾後才拼進 url(#…)
    for (const id of ids) expect(id).toMatch(/^[A-Za-z0-9_-]+$/);
    for (const id of ids) {
      expect(container.querySelector(`[clip-path="url(#${id})"]`)).toBeTruthy();
    }
  });

  it("無昨收(meta.ref 缺)→ 單條 accent 價線、無填色無 clipPath,且與白色 VWAP 可區分", () => {
    const noRef = fromSnapshot({
      code: "2330", seq: 1,
      last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
      vwap: 2_380_000,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: null, upper: null, lower: null, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={noRef} />);
    expect(container.querySelectorAll("clipPath").length).toBe(0);
    expect(container.querySelectorAll("polygon").length).toBe(0);
    expect(container.querySelector('polyline[class*="stroke-accent"]')).toBeTruthy();
    expect(container.querySelector('polyline[class*="stroke-ink"]')).toBeTruthy(); // VWAP
  });

  // 🔴 SC-2.3:均價線由琥珀金 profit 改白色 ink
  it("VWAP 線為 stroke-ink,全圖不再出現 stroke-profit", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelector('polyline[class*="stroke-profit"]')).toBeNull();
    expect(container.querySelector('polyline[class*="stroke-ink"]')).toBeTruthy();
  });

  it("無分鐘資料顯示等待提示", () => {
    const empty = fromSnapshot({
      code: "2330", seq: 0, last: null, vwap: null,
      minutes: {}, ticks: [], book: null, meta: null,
    });
    wrap(<StockIntradayChart accum={empty} />);
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });

  // 🔴 SC-3:CDP 改為預設開
  it("toggle 列:均價/CDP/MA 三鈕,均價與 CDP 預設開(SC-3)", () => {
    wrap(<StockIntradayChart accum={ACCUM} />);
    expect(screen.getByRole("button", { name: "均價" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "CDP" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "MA" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("均價 toggle 關 → VWAP 線消失", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const before = container.querySelectorAll("polyline").length;
    fireEvent.click(screen.getByRole("button", { name: "均價" }));
    expect(container.querySelectorAll("polyline").length).toBe(before - 1);
  });

  // 🔴 round3 SC-2:右緣不再印 AH / NH / CDP 等用語,改印該線的合法價位 + `*`
  it("CDP 預設開 → 右緣印價位(帶 *),不出現 AH / NH 等用語(SC-2)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    // ah 2401.237 → 最近合法檔位 2400(5 元 tick,向下 1.237 < 向上 3.763)
    // nh 2357.8   → 2360(向上 2.2 < 向下 2.8)—— snap 是取最近不是一律向下
    await waitFor(() => expect(screen.getByText("2400*", { selector: "text" })).toBeTruthy());
    expect(screen.getByText("2320*", { selector: "text" })).toBeTruthy();
    expect(screen.getByText("2360*", { selector: "text" })).toBeTruthy();
    // 未 snap 的原值不得出現
    expect(screen.queryByText("2401.2*", { selector: "text" })).toBeNull();
    expect(screen.queryByText("2357.8*", { selector: "text" })).toBeNull();
    for (const term of ["AH", "NH", "NL", "AL"]) {
      expect(screen.queryByText(term, { selector: "text" })).toBeNull();
    }
    // 「CDP」只該出現在 toggle 按鈕上,不該出現在 svg text
    expect(screen.queryByText("CDP", { selector: "text" })).toBeNull();
    expect(container.querySelectorAll("line").length).toBeGreaterThan(5);
  });

  it("CDP 五條線顏色互不相同(SC-2:名稱移除後靠顏色區分)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    await waitFor(() => expect(screen.getByText("2400*", { selector: "text" })).toBeTruthy());
    const cdpLines = [...container.querySelectorAll("line")].filter((l) =>
      (l.getAttribute("class") ?? "").includes("stroke-bull") ||
      (l.getAttribute("class") ?? "").includes("stroke-bear") ||
      (l.getAttribute("class") ?? "").includes("stroke-profit"),
    );
    const classes = cdpLines.map((l) => l.getAttribute("class"));
    expect(new Set(classes).size).toBe(5);
  });

  it("CDP toggle 關 → overlay 線與價位標消失(toggle 行為仍在)", async () => {
    wrap(<StockIntradayChart accum={ACCUM} />);
    await waitFor(() => expect(screen.getByText("2400*", { selector: "text" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "CDP" }));
    expect(screen.queryByText("2400*", { selector: "text" })).toBeNull();
    expect(screen.queryByText("2320*", { selector: "text" })).toBeNull();
  });

  it("overlay 全 null → CDP/MA 反灰 disabled + title 無日線資料(SC-4/R8)", async () => {
    overlayResponse = { cdp: null, ma5: null, ma20: null, date: null };
    wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "CDP" }));
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: "CDP" });
      expect(btn.hasAttribute("disabled")).toBe(true);
    });
    const btn = screen.getByRole("button", { name: "CDP" });
    expect(btn.getAttribute("title")).toBe("無日線資料");
    expect(btn.getAttribute("aria-pressed")).toBe("false"); // 自動置 off,不卡開著關不掉
  });

  // SC-11(確認項,round3 不得改動)+ 🔴 SC-1:右緣 % 欄整組移除
  it("Y 軸刻度:左緣仍 11 個價位含 ±2% 階;右緣不再有 % 欄(SC-11 / SC-1)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    // 端點 = 漲跌停原值
    expect(screen.getByText("2090", { selector: "text" })).toBeTruthy();
    expect(screen.getByText("2550", { selector: "text" })).toBeTruthy();
    // ±2% 階:ref 2320 → snapDown(2366.4) = 2365 / snapDown(2273.6) = 2270
    expect(screen.getByText("2365", { selector: "text" })).toBeTruthy();
    expect(screen.getByText("2270", { selector: "text" })).toBeTruthy();
    // 左緣價位刻度共 11 個(不能用 x="2" 選 —— 會撞到 09:00 的時間軸標籤 toX(540)+2)
    expect(container.querySelectorAll('[data-testid="y-tick-price"]').length).toBe(11);
    // 主圖右側 60 個 viewBox 單位內不得有含 % 的 text(SC-1 的量法;
    // 圖下 figcaption 的「外盤比 %」與頂部資訊列的漲跌 % 刻意保留,不在 svg 內)
    const main = [...container.querySelectorAll("svg")].find(
      (s2) => s2.getAttribute("aria-label") === "分時走勢圖",
    )!;
    const rightTexts = [...main.querySelectorAll("text")].filter(
      (t) => Number(t.getAttribute("x") ?? 0) > 800 - 60,
    );
    expect(rightTexts.some((t) => (t.textContent ?? "").includes("%"))).toBe(false);
  });

  // 🔴 round3 SC-4:漲跌停虛線移除(域已恰為 [lower, upper],兩條線本就貼在上下緣)
  it("不再畫漲跌停虛線(SC-4)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const main = [...container.querySelectorAll("svg")].find(
      (s2) => s2.getAttribute("aria-label") === "分時走勢圖",
    )!;
    const dashed43 = [...main.querySelectorAll("line")].filter(
      (l) => l.getAttribute("stroke-dasharray") === "4 3",
    );
    expect(dashed43.length).toBe(0);
  });

  // 🔴 round3 SC-7:時間文字改黃色
  it("X 軸時間文字與 hover 時間標皆為黃色(SC-7)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const nine = screen.getByText("09:00", { selector: "text" });
    expect(nine.getAttribute("class")).toContain("fill-time");
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 39, clientY: 100 });
    expect(
      container.querySelector("[data-testid='time-tag-text']")!.getAttribute("class"),
    ).toContain("fill-time");
  });

  // 🟢 round3 SC-8:成交量副圖的量刻度
  it("內外盤副圖左緣有量刻度(頂端 = 單邊最大張數、中線 = 其半)(SC-8)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const sub = [...container.querySelectorAll("svg")].find(
      (s2) => s2.getAttribute("aria-label") === "成交量",
    )!;
    const texts = [...sub.querySelectorAll("text")].map((t) => t.textContent);
    // ACCUM 的最大單邊 = 10(540 分 o:10)
    expect(texts).toContain("10");
    expect(texts).toContain("5");
  });

  // 🔴 SC-5:主圖底部量 bar 移除,只留成交量副圖
  it("主圖不再有量 bar;成交量副圖仍在(SC-5)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const svgs = [...container.querySelectorAll("svg")];
    const main = svgs.find((s) => s.getAttribute("aria-label") === "分時走勢圖")!;
    const sub = svgs.find((s) => s.getAttribute("aria-label") === "成交量")!;
    // defs 內的 rect 是 clipPath 的裁切框、不是畫面元素,要排除。
    // round6 項 5 起主圖多了兩個 rect(左緣漲跌停亮燈),它們不是量 bar ——
    // 本條守的是「量 bar 不在主圖」,所以改成排除已知的非量元素後仍須為 0,
    // 而不是「主圖一個 rect 都不能有」(後者會把任何新的色塊元素都誤判成 regression)。
    // `vp-bar`(價位別成交量)同理要排除:它是**價位軸**方向的量分佈,不是本條所指的
    // 「底部沿時間軸的量 bar」。此處 ACCUM 的 ticks 為空所以現在一根都沒有,但把它
    // 留給預設值決定,這條就會在「哪天有人給 ACCUM 補 ticks」時無關地紅掉(review B3)。
    const drawnRects = [...main.querySelectorAll("rect")].filter(
      (r) =>
        r.closest("defs") === null &&
        !(r.getAttribute("data-testid") ?? "").startsWith("y-tick-lamp") &&
        r.getAttribute("data-testid") !== "vp-bar" &&
        r.getAttribute("data-testid") !== "price-tag" &&
        r.getAttribute("data-testid") !== "time-tag",
    );
    expect(drawnRects.length).toBe(0);
    expect(sub.querySelectorAll("rect").length).toBeGreaterThan(0);
  });

  // 🔴 SC-7:SVG 內浮動 tooltip 移除,改圖上方常駐資訊列;水平線改跟滑鼠 y 當量尺
  it("資訊列:預設顯示最新分鐘(即時態),hover 時切換為游標所在分鐘", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const readout = () => screen.getByTestId("chart-readout");
    expect(readout().textContent).toContain("09:02"); // 最新分鐘 = 542
    expect(readout().getAttribute("data-hovering")).toBe("false");
    const svg = container.querySelector("svg")!;
    // 🔴 round4 項 3 / 項 6:繪圖區起於左緣價位帶右側(Y_AXIS_W=36),541 分在
    // x = 36 + 1/270*(800-36-40) ≈ 38.7px;x≈3 落在價位帶內 → 不對應任何分鐘
    fireEvent.mouseMove(svg, { clientX: 39, clientY: 100 });
    expect(readout().textContent).toContain("09:01");
    expect(readout().getAttribute("data-hovering")).toBe("true");
    fireEvent.mouseLeave(svg);
    expect(readout().getAttribute("data-hovering")).toBe("false");
    expect(readout().textContent).toContain("09:02");
  });

  it("資訊列含每分鐘內外盤(本專案核心訊號,原 tooltip 沒顯示)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 39, clientY: 100 });
    const text = screen.getByTestId("chart-readout").textContent ?? "";
    expect(text).toContain("外 10");
    expect(text).toContain("內 0");
  });

  it("十字線:垂直線 snap 分鐘、水平線跟滑鼠 y(不再鎖該分鐘收盤價)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 39, clientY: 120 });
    expect(Number(container.querySelector("[data-testid='crosshair-h']")!.getAttribute("y1"))).toBe(120);
    fireEvent.mouseMove(svg, { clientX: 39, clientY: 60 });
    expect(Number(container.querySelector("[data-testid='crosshair-h']")!.getAttribute("y1"))).toBe(60);
    expect(container.querySelector("[data-testid='crosshair-v']")).toBeTruthy();
    fireEvent.mouseLeave(svg);
    expect(container.querySelector("[data-testid='crosshair-h']")).toBeNull();
  });

  // 🟢 SC-7.8:量尺不依賴資料 —— 無成交分鐘仍要能量價位,只是沒有 bar 可指
  it("hover 無資料分鐘:垂直線與 hover 資訊列不出現,水平線與左價標仍在(分解退化)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 400, clientY: 100 }); // ~11:15 無資料
    expect(container.querySelector("[data-testid='crosshair-v']")).toBeNull();
    expect(screen.getByTestId("chart-readout").getAttribute("data-hovering")).toBe("false");
    expect(container.querySelector("[data-testid='crosshair-h']")).toBeTruthy();
    expect(container.querySelector("[data-testid='price-tag-text']")).toBeTruthy();
  });

  // 🔴 round3 SC-1:hover 右緣 % 標整個移除(左緣價位標與底部時間標照舊)
  it("hover 右緣不再浮出 % 標,左價標與時間標仍在(SC-1)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 39, clientY: 100 });
    expect(container.querySelector("[data-testid='pct-tag']")).toBeNull();
    expect(container.querySelector("[data-testid='pct-tag-text']")).toBeNull();
    expect(container.querySelector("[data-testid='price-tag-text']")).toBeTruthy();
    expect(container.querySelector("[data-testid='time-tag-text']")).toBeTruthy();
  });

  // 🔴 SC-4:在圖上拖曳是「拉一段來看」的自然手勢,不該把時間軸 / 價位刻度 / 內外盤文字反白
  it("圖表容器禁止選字(拖曳不反白;SC-4)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelector("figure")?.className).toContain("select-none");
  });
});

// ---- round3 T-10b:尺寸 prop regression ----
//
// 這條鎖的是「幾何 useMemo 的 deps 忘了加高度」—— 那會讓 viewBox 換了新高度、
// 但 toY / 刻度仍用舊高度算,畫面錯位且完全不報錯。repo 的 eslint 沒裝
// react-hooks plugin,exhaustive-deps 抓不到;lib 層的純函數測試也照樣全綠。
// 唯一能抓到的位置就是元件層:同一份資料只改高度 prop,render 兩次比對。
describe("StockIntradayChart 高度 prop(SC-6 / T-10b)", () => {
  function heights(mainHeight: number) {
    const { container } = wrap(
      <StockIntradayChart accum={ACCUM} mainHeight={mainHeight} subHeight={70} />,
    );
    const main = [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )!;
    return {
      viewBox: main.getAttribute("viewBox"),
      firstTickY: main.querySelector('[data-testid="y-tick-price"]')!.getAttribute("y"),
      lastTickY: [...main.querySelectorAll('[data-testid="y-tick-price"]')]
        .at(-1)!
        .getAttribute("y"),
    };
  }

  it("高度改變 → viewBox 與刻度 y 座標都跟著變(幾何必須重算)", () => {
    const a = heights(260);
    cleanup();
    const b = heights(420);
    expect(a.viewBox).not.toBe(b.viewBox);
    expect(b.viewBox).toContain("420");
    // 只有 viewBox 變、y 沒變 = 幾何沒重算(deps 漏了高度),圖會整片錯位
    expect(a.lastTickY).not.toBe(b.lastTickY);
  });

  it("未傳高度時沿用固定常數(量測未就緒 / jsdom → 既有行為不變)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const main = [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )!;
    expect(main.getAttribute("viewBox")).toBe("0 0 800 260");
  });
});

// 🔴 round4 項 3/4/5:左緣價位不再壓線、價位有對應水平線、量刻度改靠右
describe("江波圖左緣價位帶與量刻度(round4 項 3/4/5)", () => {
  function svgs(container: HTMLElement) {
    const all = [...container.querySelectorAll("svg")];
    return {
      main: all.find((s) => s.getAttribute("aria-label") === "分時走勢圖")!,
      sub: all.find((s) => s.getAttribute("aria-label") === "成交量")!,
    };
  }

  it("項 3:繪圖區元素一律從價位帶右緣起,價位文字仍在帶內(不重疊)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const { main } = svgs(container);
    // 走勢線第一點的 x 就是繪圖區左界
    const priceLine = main.querySelector('polyline[class*="stroke-bull"]')!;
    const firstX = Number(priceLine.getAttribute("points")!.split(" ")[0]!.split(",")[0]);
    expect(firstX).toBeGreaterThanOrEqual(Y_AXIS_W);
    // 平盤線 / 水平十字線 / 疊線都不得越界進價位帶
    const refLine = [...main.querySelectorAll("line")].find(
      (l) => (l.getAttribute("stroke-dasharray") ?? "") === "2 3" && l.getAttribute("stroke-width") === "1",
    )!;
    expect(Number(refLine.getAttribute("x1"))).toBe(Y_AXIS_W);
    // 價位文字仍畫在帶內(x < Y_AXIS_W)
    for (const t of main.querySelectorAll('[data-testid="y-tick-price"]')) {
      expect(Number(t.getAttribute("x"))).toBeLessThan(Y_AXIS_W);
    }
  });

  it("項 3:hover 水平線起於價位帶右緣(不穿過價位文字)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 39, clientY: 120 });
    const h = container.querySelector("[data-testid='crosshair-h']")!;
    expect(Number(h.getAttribute("x1"))).toBe(Y_AXIS_W);
  });

  it("項 4:每個左緣價位都有一條對應的水平格線,與整點垂直線同色系", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const { main } = svgs(container);
    const ticks = main.querySelectorAll('[data-testid="y-tick-price"]').length;
    const grids = [...main.querySelectorAll('[data-testid="y-grid"]')];
    expect(ticks).toBeGreaterThan(0);
    expect(grids.length).toBe(ticks);
    for (const g of grids) {
      expect(g.getAttribute("class")).toContain("stroke-line");
      expect(Number(g.getAttribute("x1"))).toBe(Y_AXIS_W);
      // 🔴 round5 D:右緣讓出 R_AXIS_W 給疊線價位標,格線右端跟著內縮
      expect(Number(g.getAttribute("x2"))).toBe(800 - R_AXIS_W);
      // 水平線:y1 === y2
      expect(g.getAttribute("y1")).toBe(g.getAttribute("y2"));
    }
  });

  it("項 5:內外盤量刻度兩個數字靠右緣、左緣不再有數字", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const { sub } = svgs(container);
    const texts = [...sub.querySelectorAll("text")];
    expect(texts.length).toBe(2); // 頂端 = 單邊最大張數、中線 = 其半
    for (const t of texts) {
      expect(t.getAttribute("text-anchor")).toBe("end");
      expect(Number(t.getAttribute("x"))).toBe(800 - 2);
    }
  });

  // review R15a:中線數字沒有 SUB_TOP_PAD 那種空白保護,盤中右緣恆有 bar
  it("項 5:中線量刻度有同底色描邊,不會被右緣 bar 蓋掉", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const mid = container.querySelector('[data-testid="vol-tick-mid"]')!;
    expect(mid.getAttribute("class")).toContain("stroke-surface");
    expect(mid.getAttribute("paint-order")).toBe("stroke");
  });

  // review R15b:兩份 46 靠註解維持相等 → 任一方改動就讓 hover 價位標壓線復發
  it("hover 價位標寬度恰等於價位帶寬度(不得各寫一份字面值)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 39, clientY: 120 });
    const tag = container.querySelector('[data-testid="price-tag"]')!;
    expect(Number(tag.getAttribute("width"))).toBe(Y_AXIS_W);
  });
});

// 🟢 round4 項 3:底部 hover 標籤在時間下方多一行「該分鐘成交價」
describe("StockIntradayChart hover 底部標籤(round4 項 3)", () => {
  function hover(container: HTMLElement, clientX = 39): void {
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX, clientY: 100 });
  }

  it("時間標下方多一行價位,值 = 該分鐘收盤(與資訊列同源同格式)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    hover(container);
    expect(screen.getByTestId("time-tag-text").textContent).toBe("09:01");
    // 541 分收盤 2_380_000 → "2380"(資訊列同值)
    expect(screen.getByTestId("time-tag-price").textContent).toBe("2380");
    expect(screen.getByTestId("chart-readout").textContent).toContain("2380");
  });

  it("兩行都置中對齊、盒子仍貼齊 viewBox 底邊(往上長不往下溢出)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    hover(container);
    const rect = container.querySelector('[data-testid="time-tag"]')!;
    const h = Number(rect.getAttribute("height"));
    expect(h).toBe(24);
    const g = rect.parentElement!;
    // translate(x, mainH − h):底邊恰貼 viewBox 底(mainH 預設 260)
    expect(g.getAttribute("transform")).toContain(`, ${260 - h})`);
    expect(screen.getByTestId("time-tag-text").getAttribute("text-anchor")).toBe("middle");
    expect(screen.getByTestId("time-tag-price").getAttribute("text-anchor")).toBe("middle");
  });

  it("價位行相對昨收上色:高於 → bull、低於 → bear", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />); // 2380 > ref 2320
    hover(container);
    expect(screen.getByTestId("time-tag-price").getAttribute("class")).toContain("fill-bull");
    cleanup();

    const bear = {
      ...ACCUM,
      minutes: new Map([[541, { c: 2_300_000, v: 10, i: 0, o: 10, u: 0, h: 2_300_000, l: 2_300_000 }]]),
    };
    const r2 = wrap(<StockIntradayChart accum={bear} />);
    hover(r2.container);
    expect(screen.getByTestId("time-tag-price").getAttribute("class")).toContain("fill-bear");
  });

  it("無昨收(meta.ref 為 null)→ 中性白,不得因 null 被當 0 而塗紅(W-6)", () => {
    const noRef = fromSnapshot({
      code: "2330", seq: 1,
      last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
      vwap: 2_380_000,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_380_000 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: null, upper: null, lower: null, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={noRef} />);
    hover(container);
    const cls = screen.getByTestId("time-tag-price").getAttribute("class")!;
    expect(cls).toContain("fill-ink");
    expect(cls).not.toContain("fill-bull");
    expect(cls).not.toContain("fill-bear");
  });

  // 🔴 M5:ref = 0(TC4 送 "0",後端不轉 None)與 ref = null 同義 —— 毫元恆 > 0,
  // 不歸一的話 `c > 0` 恆真 → 無參考價的商品被塗成一片紅
  it("ref 為 0(不可得)→ 中性白,與 ref=null 同語意", () => {
    const zeroRef = fromSnapshot({
      code: "2330", seq: 1,
      last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
      vwap: 2_380_000,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_380_000 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: 0, upper: 0, lower: 0, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={zeroRef} />);
    hover(container);
    const cls = screen.getByTestId("time-tag-price").getAttribute("class")!;
    expect(cls).toContain("fill-ink");
    expect(cls).not.toContain("fill-bull");
    expect(cls).not.toContain("fill-bear");
  });

  it("時間行維持 fill-time(黃),與價格語意分色", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    hover(container);
    expect(screen.getByTestId("time-tag-text").getAttribute("class")).toContain("fill-time");
  });

  it("滑到沒有成交的分鐘 → 整個底部標籤不出現(W-1 回歸)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 400, clientY: 100 });
    expect(container.querySelector('[data-testid="time-tag"]')).toBeNull();
    expect(container.querySelector('[data-testid="time-tag-price"]')).toBeNull();
  });
});

// 🔴 round4 項 6:價位帶內縮 + 刻度右對齊 + 垂直置中 + 縮字
describe("StockIntradayChart 左緣價位帶(round4 項 6)", () => {
  it("價位帶內縮(繪圖區左界更靠左)", () => {
    // 46 → 36:右對齊之後帶內只需容納數字本身,不必再為左對齊的參差留空間
    expect(Y_AXIS_W).toBe(36);
  });

  it("刻度數字右對齊成一直欄,右緣距繪圖區左界 4px", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const ticks = [...container.querySelectorAll('[data-testid="y-tick-price"]')];
    expect(ticks.length).toBeGreaterThan(0);
    for (const t of ticks) {
      expect(t.getAttribute("text-anchor")).toBe("end");
      expect(Number(t.getAttribute("x"))).toBe(Y_AXIS_W - 4);
    }
  });

  it("刻度數字垂直中心壓在對應格線上(不再整體浮在線上方、不再夾制)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const grids = [...container.querySelectorAll('[data-testid="y-grid"]')];
    const ticks = [...container.querySelectorAll('[data-testid="y-tick-price"]')];
    expect(ticks.length).toBe(grids.length);
    ticks.forEach((t, i) => {
      // baseline 直接取格線 y,視覺置中靠 dy(em 單位 → root font-size 放大時等比)
      expect(Number(t.getAttribute("y"))).toBeCloseTo(Number(grids[i]!.getAttribute("y1")), 6);
      expect(t.getAttribute("dy")).toBe("0.35em");
    });
  });

  it("刻度字級縮到 0.5625rem(與右緣疊線價位標同級)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    for (const t of container.querySelectorAll('[data-testid="y-tick-price"]')) {
      expect(t.getAttribute("font-size")).toBe("0.5625rem");
    }
  });

  it("hover 價位標的數字與靜態刻度右緣對齊在同一條線上", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 39, clientY: 120 });
    const tagText = container.querySelector('[data-testid="price-tag-text"]')!;
    expect(tagText.getAttribute("text-anchor")).toBe("end");
    expect(Number(tagText.getAttribute("x"))).toBe(Y_AXIS_W - 4);
    expect(tagText.getAttribute("font-size")).toBe("0.5625rem");
  });
});

// 🟢 round5 SC-1 / SC-2:當日高低線 + 現價圈
describe("StockIntradayChart 未分類量的呈現(round6 項 2)", () => {
  /** 2026-07-31 實測 09:00 那一分鐘:量 269 = 外 127 + 內 20 + 未分類 122 */
  const withUnch = {
    ...ACCUM,
    minutes: new Map([[540, { c: 2_380_000, v: 269, o: 127, i: 20, u: 122, h: null, l: null }]]),
  } as unknown as typeof ACCUM;

  /** 🔴 round6c:量柱不再依內外盤分色。灰段是 user 連兩輪反映的痛點 —— 它在圖表語彙裡
   *  看起來像「第三種方向」,而它其實是「判不出方向」。修完後端判定的根因、又改成斜線紋理
   *  之後 user 仍覺得多餘,拍板「不要分顏色,單純顯示量」。 */
  it("量柱單色單根,不再有內外盤分段與斜線 pattern", () => {
    const { container } = wrap(<StockIntradayChart accum={withUnch} />);
    const bars = [...container.querySelectorAll('[data-testid="energy-bar"]')];
    expect(bars).toHaveLength(1); // 一分鐘一根,不是三段
    expect(bars[0]!.getAttribute("class")).toContain("fill-ink-muted");
    expect(container.querySelector('[data-testid="energy-unch"]')).toBeNull();
    expect(container.querySelector("pattern")).toBeNull();
  });

  it("柱高仍以總量正規化(W-1:分母含未分類,不因不分色而改)", () => {
    const twoMin = {
      ...ACCUM,
      minutes: new Map([
        [540, { c: 2_380_000, v: 269, o: 127, i: 20, u: 122, h: null, l: null }],
        [541, { c: 2_380_000, v: 100, o: 60, i: 40, u: 0, h: null, l: null }],
      ]),
    } as unknown as typeof ACCUM;
    const { container } = wrap(<StockIntradayChart accum={twoMin} />);
    const hs = [...container.querySelectorAll('[data-testid="energy-bar"]')].map((r) =>
      Number(r.getAttribute("height")),
    );
    // 269 : 100 —— 若分母退回「單邊最大」這個比例會跑掉
    expect(hs[1]! / hs[0]!).toBeCloseTo(100 / 269, 5);
  });

  it("內外盤統計沒有消失,只是移到說明列", () => {
    wrap(<StockIntradayChart accum={withUnch} />);
    expect(screen.getByTestId("unch-total").textContent).toBe("122");
    expect(screen.getByTestId("outer-pct").textContent).toBe("86.4%");
  });

  it("說明列印出未分類量與判定率", () => {
    wrap(<StockIntradayChart accum={withUnch} />);
    expect(screen.getByTestId("unch-total").textContent).toBe("122");
    expect(screen.getByTestId("outer-pct").textContent).toBe("86.4%"); // 127/147
    expect(screen.getByTestId("decided-pct").textContent).toContain("55%"); // 147/269
  });

  // 警示改掛「判定率」本身而非暗化外盤比(2026-07-31 user 拍板):降對比在 UI 語彙裡
  // 是「不重要 / 停用」,而這個數字是「重要但失真」;且判定率本來就印在旁邊,
  // 暗化沒有增加任何資訊位元,只增加一個門檻懸崖。
  function accumWithDecided(decided: number) {
    const v = 100;
    const o = Math.round(decided * 0.6);
    return {
      ...ACCUM,
      minutes: new Map([
        [540, { c: 2_380_000, v, o, i: decided - o, u: v - decided, h: null, l: null }],
      ]),
    } as unknown as typeof ACCUM;
  }

  it("判定率低於門檻 → **判定率本身**標警示色,外盤比維持可讀(SC-2.4)", () => {
    wrap(<StockIntradayChart accum={withUnch} />); // 55%
    expect(screen.getByTestId("decided-pct").className).toContain("text-warn");
    // 外盤比不再降對比 —— 它是重要但失真,不是不重要
    expect(screen.getByTestId("outer-pct").className).not.toContain("text-ink-dim/50");
  });

  it("判定率高 → 判定率不標警示", () => {
    wrap(<StockIntradayChart accum={accumWithDecided(100)} />);
    expect(screen.getByTestId("decided-pct").className).not.toContain("text-warn");
    expect(screen.getByTestId("decided-pct").textContent).toContain("100%");
  });

  // 門檻 60 → 75 的理由(user 拍板):併上盤中 / 盤後六檔樣本後分佈是雙峰 ——
  // 正常群 83.7–100、劣化群 51–64。60 落在劣化群**內部**,讓 4989(未分類逾三分之一)
  // 被顯示成完全可信。最大間隔切點約 74,取 75 兩側各留餘裕。
  it("判定率 64%(4989 實測值)在新門檻下要標警示 —— 舊門檻 60 抓不到", () => {
    wrap(<StockIntradayChart accum={accumWithDecided(64)} />);
    expect(screen.getByTestId("decided-pct").textContent).toContain("64%");
    expect(screen.getByTestId("decided-pct").className).toContain("text-warn");
  });

  it("判定率 83.7%(2317 實測值)屬正常群,不標警示", () => {
    wrap(<StockIntradayChart accum={accumWithDecided(84)} />);
    expect(screen.getByTestId("decided-pct").className).not.toContain("text-warn");
  });

  it("門檻本身:74 標、75 不標(邊界)", () => {
    const { unmount } = wrap(<StockIntradayChart accum={accumWithDecided(74)} />);
    expect(screen.getByTestId("decided-pct").className).toContain("text-warn");
    unmount();
    wrap(<StockIntradayChart accum={accumWithDecided(75)} />);
    expect(screen.getByTestId("decided-pct").className).not.toContain("text-warn");
  });

  it("鎖漲停整天判不出來 → 外盤比顯示「-」不是 0%(0% 會被讀成全內盤)", () => {
    const locked = {
      ...ACCUM,
      minutes: new Map([[540, { c: 2_380_000, v: 2131, o: 0, i: 0, u: 2131, h: null, l: null }]]),
    } as unknown as typeof ACCUM;
    wrap(<StockIntradayChart accum={locked} />);
    expect(screen.getByTestId("outer-pct").textContent).toBe("-");
    expect(screen.getByTestId("decided-pct").textContent).toContain("0%");
  });
});

describe("StockIntradayChart 左緣漲跌停亮燈(round6 項 5)", () => {
  it("最上格紅底、最下格綠底,兩格皆白字", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const up = container.querySelector('[data-testid="y-tick-lamp-upper"]')!;
    const down = container.querySelector('[data-testid="y-tick-lamp-lower"]')!;
    expect(up.getAttribute("class")).toContain("fill-bull");
    expect(down.getAttribute("class")).toContain("fill-bear");
    const texts = [...container.querySelectorAll('[data-testid="y-tick-price"]')];
    expect(texts[0]!.getAttribute("class")).toContain("fill-white");
    expect(texts[texts.length - 1]!.getAttribute("class")).toContain("fill-white");
  });

  it("中間各格不亮、維持 tickTone 的漲跌色(W-27)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelectorAll('[data-testid^="y-tick-lamp"]')).toHaveLength(2);
    const texts = [...container.querySelectorAll('[data-testid="y-tick-price"]')];
    for (const t of texts.slice(1, -1)) {
      expect(t.getAttribute("class")).not.toContain("fill-white");
    }
  });

  it("色塊不出左緣價位帶、也不被 viewBox 上緣裁掉(SC-5.6)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const [, , w, h] = container.querySelector("svg")!.getAttribute("viewBox")!.split(" ").map(Number);
    for (const r of container.querySelectorAll('[data-testid^="y-tick-lamp"]')) {
      const x = Number(r.getAttribute("x"));
      const y = Number(r.getAttribute("y"));
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x + Number(r.getAttribute("width"))).toBeLessThanOrEqual(Y_AXIS_W);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y + Number(r.getAttribute("height"))).toBeLessThanOrEqual(h!);
      expect(w).toBeGreaterThan(0);
    }
  });

  it("無漲跌停的商品不亮燈(SC-5.5)", () => {
    const noLimit = { ...ACCUM, meta: { ...ACCUM.meta!, upper: null, lower: null } };
    const { container } = wrap(<StockIntradayChart accum={noLimit} />);
    expect(container.querySelectorAll('[data-testid^="y-tick-lamp"]')).toHaveLength(0);
  });
});

describe("StockIntradayChart 當日高低與現價圈", () => {
  const withHL = (high: number | null, low: number | null) => ({ ...ACCUM, high, low });

  /** 參考幾何:必須吃**該測試實際渲染的那份 accum**,不是硬編 ACCUM ——
   *  換 meta / 換 high/low 的測試若拿 ACCUM 算,參考值會來自另一條域分支,
   *  斷言仍會綠(或紅得莫名),而漂掉的是「測試在比什麼」本身。 */
  function geometryOf(container: HTMLElement, accum: typeof ACCUM) {
    const [, , w, h] = container
      .querySelector("svg")!
      .getAttribute("viewBox")!
      .split(" ")
      .map(Number);
    return buildIntradayGeometry(
      { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
      { width: w!, height: h! },
    );
  }

  // 🔴 round4 項 1(B-1):橫虛線 → 就地標記 + 價位文字
  // 🔴 round6 項 1:三角 polygon → 空心圓環 circle
  it("域內的當日高低 → 圓環標記 + 價位文字(數字 = top-level high/low 毫元轉元)", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    expect(container.querySelector('circle[data-testid="day-high"]')).toBeTruthy();
    expect(container.querySelector('circle[data-testid="day-low"]')).toBeTruthy();
    expect(screen.getByTestId("day-high-label").textContent).toBe("2395");
    expect(screen.getByTestId("day-low-label").textContent).toBe("2370");
  });

  /** 🔴 round6b:空心環 → **實心小圓**,且圖案與文字同色、依相對平盤判紅 / 綠 / 灰。
   *  ACCUM 的 ref = 2_320_000,所以 2_395_000 是紅、2_300_000 是綠。 */
  it("標記是實心圓,圖案與文字同色", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    const dot = container.querySelector('circle[data-testid="day-high"]')!;
    expect(dot.getAttribute("fill")).toBeNull(); // 不再是 fill="none"
    expect(dot.getAttribute("class")).toContain("fill-bull");
    expect(screen.getByTestId("day-high-label").getAttribute("class")).toContain("fill-bull");
  });

  /** 高低值必須用 fixture 裡真的存在的 per-minute h/l(2_395_000 / 2_370_000)——
   *  換成別的值會被等值反查擋掉而根本不畫(W-6)。要造出「一紅一綠」只能移動 `ref`。 */
  const withRef = (ref: number) =>
    ({
      ...withHL(2_395_000, 2_370_000),
      meta: { ...ACCUM.meta!, ref },
    }) as typeof ACCUM;

  it("高於平盤紅、低於平盤綠", () => {
    // ref 落在兩個極值中間 → 日高紅、日低綠
    const { container } = wrap(<StockIntradayChart accum={withRef(2_380_000)} />);
    expect(container.querySelector('circle[data-testid="day-high"]')!.getAttribute("class")).toContain(
      "fill-bull",
    );
    expect(container.querySelector('circle[data-testid="day-low"]')!.getAttribute("class")).toContain(
      "fill-bear",
    );
  });

  it("整天下跌的股票,其當日高也判綠(判色基準是平盤不是「高低」)", () => {
    // ref 高於當日高 = 這檔今天從頭到尾都在平盤下
    const { container } = wrap(<StockIntradayChart accum={withRef(2_400_000)} />);
    expect(container.querySelector('circle[data-testid="day-high"]')!.getAttribute("class")).toContain(
      "fill-bear",
    );
  });

  it("圓比舊的環小(user:圖案再小一點)", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    const r = Number(container.querySelector('circle[data-testid="day-high"]')!.getAttribute("r"));
    expect(r).toBeLessThan(3); // 舊環 radius 3
  });

  it("標記畫在主價線**之後**(SC-1.2:被價線蓋住等於沒畫)", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    const nodes = [...container.querySelectorAll("polyline, circle[data-testid='day-high']")];
    const priceLineIdx = nodes.findIndex((n) =>
      (n.getAttribute("class") ?? "").includes("stroke-bull"),
    );
    const markIdx = nodes.findIndex((n) => n.getAttribute("data-testid") === "day-high");
    expect(priceLineIdx).toBeGreaterThanOrEqual(0);
    expect(markIdx).toBeGreaterThan(priceLineIdx);
  });

  it("整張圖不再有橫貫左右的高低虛線(4 3 / 0.8)", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    const dashed = [...container.querySelectorAll("line")].filter(
      (l) => l.getAttribute("stroke-dasharray") === "4 3",
    );
    expect(dashed.length).toBe(0);
  });

  it("圓心壓在極值價位上(round4 的「apex 貼價位」語意原樣保留)", () => {
    const accum = withHL(2_395_000, 2_370_000);
    const { container } = wrap(<StockIntradayChart accum={accum} />);
    const g = geometryOf(container, accum);
    const high = container.querySelector('circle[data-testid="day-high"]')!;
    expect(Number(high.getAttribute("cy"))).toBeCloseTo(g.toY(2_395_000), 5);
    const low = container.querySelector('circle[data-testid="day-low"]')!;
    expect(Number(low.getAttribute("cy"))).toBeCloseTo(g.toY(2_370_000), 5);
  });

  it("標記落在**摸到極值的那一分鐘**,不是最後一分鐘", () => {
    const accum = withHL(2_395_000, 2_370_000);
    const { container } = wrap(<StockIntradayChart accum={accum} />);
    const g = geometryOf(container, accum);
    // 高低都發生在 541 分(ACCUM fixture 的 per-minute h/l);最後一分鐘是 542
    const expectedX = g.priceLine[0]!.x;
    const lastX = g.priceLine[g.priceLine.length - 1]!.x;
    const markX = (id: string) =>
      Number(container.querySelector(`circle[data-testid="${id}"]`)!.getAttribute("cx"));
    expect(markX("day-high")).toBeCloseTo(expectedX, 5);
    expect(markX("day-high")).not.toBeCloseTo(lastX, 1);
    expect(markX("day-low")).toBeCloseTo(expectedX, 5);
  });

  it("當日高 === 當日低(漲停鎖死)→ 只畫高標,不畫低標", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_395_000)} />);
    expect(container.querySelector('circle[data-testid="day-high"]')).toBeTruthy();
    expect(container.querySelector('circle[data-testid="day-low"]')).toBeNull();
  });

  /** 白名單 3:ACCUM 有 upper/lower → 走**漲跌停域**(恰為 [lower, upper]),超出漲停的
   *  逐筆極值不畫。**這條與本輪的 autofit 改動無關** —— autofit 分支自本輪起域必含
   *  high/low,已無此裁切;會裁的只剩漲跌停分支(超過漲停的價位當日不可能成交)。 */
  it("當日高超出 y 域 → 不畫(低點仍畫)", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_600_000, 2_370_000)} />);
    expect(container.querySelector('[data-testid="day-high"]')).toBeNull();
    expect(container.querySelector('[data-testid="day-low"]')).toBeTruthy();
  });

  /** 🔴 無漲跌停(autofit 域)時,域原本只由**分鐘收盤**決定 —— 逐筆高一離開收盤群
   *  整個標記就消失,而畫面上完全沒有訊號。既有元件測試全走漲跌停分支或 high/low = null,
   *  對這條路徑零覆蓋,所以另造一份無漲跌停 snapshot。 */
  it("無漲跌停 + 當日高遠離收盤群 → 域跟著擴,標記仍畫得出來", () => {
    const autofit = fromSnapshot({
      code: "2330", seq: 2,
      last: { p: 2_390_000, t: "09:02:30.000", cum_vol: 12 },
      vwap: 2_380_000,
      minutes: {
        "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_600_000, l: 2_370_000 },
        "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_395_000, l: 2_385_000 },
      },
      ticks: [], book: null,
      // upper/lower 缺 → 走對稱 autofit;舊域 [2_243_000, 2_397_000] 裝不下 2_600_000
      meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: 100 },
      high: 2_600_000, low: 2_370_000,
    });
    const { container } = wrap(<StockIntradayChart accum={autofit} />);
    expect(container.querySelector('circle[data-testid="day-high"]')).toBeTruthy();
    expect(container.querySelector('circle[data-testid="day-low"]')).toBeTruthy();
  });

  it("域內但沒有分鐘的 h 等於該值(反查落空)→ 不畫,不退而求其次挑別的分鐘", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_392_000, 2_371_000)} />);
    expect(container.querySelector('[data-testid="day-high"]')).toBeNull();
    expect(container.querySelector('[data-testid="day-low"]')).toBeNull();
  });

  it("minutes 缺 per-minute h/l(舊後端 snapshot)→ 不畫", () => {
    const legacy = fromSnapshot({
      code: "2330", seq: 2,
      last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
      vwap: 2_380_000,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
      high: 2_380_000, low: 2_380_000,
    });
    const { container } = wrap(<StockIntradayChart accum={legacy} />);
    expect(container.querySelector('[data-testid="day-high"]')).toBeNull();
    expect(container.querySelector('[data-testid="day-low"]')).toBeNull();
  });

  it("高低為 null(舊 snapshot / 尚無成交)→ 不畫", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(null, null)} />);
    expect(container.querySelector('[data-testid="day-high"]')).toBeNull();
    expect(container.querySelector('[data-testid="day-low"]')).toBeNull();
  });

  it("現價圈落在走勢線最右端", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const g = geometryOf(container, ACCUM);
    const lp = lastPoint(g)!;
    const dot = container.querySelector('[data-testid="last-dot"]')!;
    expect(Number(dot.getAttribute("cx"))).toBeCloseTo(lp.x, 5);
    expect(Number(dot.getAttribute("cy"))).toBeCloseTo(lp.y, 5);
  });

  // 🔴 round4 項 2(B-3):即時價位文字移除,只留圓點 —— 文字會與右緣疊線價位標重疊
  it("走勢線末端只有圓點,沒有即時價位文字", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelector('[data-testid="last-dot"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="last-price"]')).toBeNull();
  });

  it("現價圈依現價 vs 參考價三態上色", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />); // 2380 > ref 2320
    expect(container.querySelector('[data-testid="last-dot"]')!.getAttribute("class")).toContain(
      "fill-bull",
    );
    cleanup();

    const bear = { ...ACCUM, last: { p: 2_300_000, t: "09:02:00.000", cum_vol: 12 } };
    const r2 = wrap(<StockIntradayChart accum={bear} />);
    expect(r2.container.querySelector('[data-testid="last-dot"]')!.getAttribute("class")).toContain(
      "fill-bear",
    );
    cleanup();

    const flat = { ...ACCUM, last: { p: 2_320_000, t: "09:02:00.000", cum_vol: 12 } };
    const r3 = wrap(<StockIntradayChart accum={flat} />);
    expect(r3.container.querySelector('[data-testid="last-dot"]')!.getAttribute("class")).toContain(
      "fill-ink-dim",
    );
  });

  // 🔴 M5:同上,現價圈的判色也要把 ref=0 當不可得(否則恆 fill-bull)
  it("ref 為 0(不可得)→ 現價圈中性灰,不判紅綠", () => {
    const zeroRef = { ...ACCUM, meta: { name: "台積電", ref: 0, upper: 0, lower: 0, y_vol: 100 } };
    const { container } = wrap(<StockIntradayChart accum={zeroRef} />);
    const cls = container.querySelector('[data-testid="last-dot"]')!.getAttribute("class")!;
    expect(cls).toContain("fill-ink-dim");
    expect(cls).not.toContain("fill-bull");
  });

  it("尚無成交 → 不渲染圓點且不崩", () => {
    const empty = fromSnapshot({
      code: "2330", seq: 1, last: null, vwap: null,
      minutes: {}, ticks: [], book: null,
      meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_vol: null },
    });
    const { container } = wrap(<StockIntradayChart accum={empty} />);
    expect(container.querySelector('[data-testid="last-dot"]')).toBeNull();
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });
});

// 🟢 SC-3:分時圖價位別成交量(VP)長條 + 「量分佈」toggle
describe("StockIntradayChart 價位別成交量(SC-3)", () => {
  /** **獨立 fixture,刻意不動共用的 `ACCUM`**:ACCUM 的 `ticks` 是空陣列,VP 因此恆空,
   *  而既有的 SC-5「主圖 drawnRects === 0」正是拿 ACCUM 在量 —— 把 tick 加進共用 fixture
   *  會讓那條測試因為多了 VP 的 rect 而紅,紅的原因卻與它要守的「量 bar 不在主圖」無關。
   *
   *  只換 `ticks`:價格全落在既有 y 域 [2_090_000, 2_550_000] 內、時間全落在
   *  [09:00, 13:30] 窗內,三個價位各自是合法檔位(2380 / 2385 / 2390,5 元 tick)
   *  → snapDown 後互不合併,bar 數可精確斷言。 */
  const WITH_TICKS = fromSnapshot({
    code: "2330",
    seq: 2,
    last: { p: 2_390_000, t: "09:02:10.000", cum_vol: 12 },
    vwap: 2_380_000,
    minutes: {
      "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_395_000, l: 2_370_000 },
      "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
    },
    ticks: [
      { t: "09:01:30.000", p: 2_380_000, q: 7, side: "outer" },
      { t: "09:01:40.000", p: 2_385_000, q: 3, side: "outer" },
      { t: "09:02:10.000", p: 2_390_000, q: 2, side: "inner" },
    ],
    book: null,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  function vpBars(container: HTMLElement): Element[] {
    return [...container.querySelectorAll('[data-testid="vp-bar"]')];
  }

  /** 🔴 SC-4:POC(域內量最大的價位)那一根改 accent 色 + 更高透明度。
   *  本節的樣式斷言是**事前標記該變**的既有合約 —— 其餘 bar 的樣式一字不動。
   *  WITH_TICKS 的量分佈 7 / 3 / 2 張,降冪排序後 POC(2380,7 張)是**最後一根**。 */
  it("預設開:每個成交價位一根長條,自繪圖區左緣向右;POC 以外半透明中性色", () => {
    const { container } = wrap(<StockIntradayChart accum={WITH_TICKS} />);
    const bars = vpBars(container);
    expect(bars.length).toBe(3);
    bars.forEach((b, i) => {
      // x 恆為繪圖區左界:長條是「從價位軸長出來的」,越界進價位帶會壓到刻度數字
      expect(Number(b.getAttribute("x"))).toBe(Y_AXIS_W);
      expect(Number(b.getAttribute("width"))).toBeGreaterThan(0);
      if (i === 2) {
        // POC:accent 桃紅 + 0.45 —— 「最長那根」在灰底上要一眼指認得出來
        expect(b.getAttribute("fill-opacity")).toBe(String(VP_POC_FILL_OPACITY));
        expect(b.getAttribute("class")).toContain("fill-accent");
      } else {
        expect(b.getAttribute("fill-opacity")).toBe(String(VP_FILL_OPACITY));
        expect(b.getAttribute("class")).toContain("fill-ink-muted");
      }
    });
    // testid 不變:POC 不另開一種節點,否則既有「vp-bar 數 / z-order」諸條全部漏算它
    expect(bars.filter((b) => (b.getAttribute("class") ?? "").includes("fill-accent")).length).toBe(1);
  });

  it("長度比例 = 該價位當日成交量(量最大的那根最長)", () => {
    const { container } = wrap(<StockIntradayChart accum={WITH_TICKS} />);
    // 降冪排序 → [2390(2 張), 2385(3 張), 2380(7 張)]
    const ws = vpBars(container).map((b) => Number(b.getAttribute("width")));
    expect(ws[2]! / ws[0]!).toBeCloseTo(7 / 2, 5);
    expect(ws[1]! / ws[0]!).toBeCloseTo(3 / 2, 5);
  });

  it("toggle 列多一顆「量分佈」,預設亮起;關掉後長條整組消失", () => {
    const { container } = wrap(<StockIntradayChart accum={WITH_TICKS} />);
    const btn = screen.getByRole("button", { name: "量分佈" });
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(vpBars(container).length).toBeGreaterThan(0);
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: "量分佈" }).getAttribute("aria-pressed")).toBe("false");
    expect(vpBars(container).length).toBe(0);
  });

  /** z-order 是這組長條能不能用的前提:它是背景參考,壓在紅綠填色與走勢線之上就等於
   *  把主資訊蓋掉。svg 沒有 z-index,唯一決定圖層的就是文件順序,所以只能在這裡量。 */
  it("畫在 y 格線之後、平盤填色與走勢線之前(不遮主資訊)", () => {
    const { container } = wrap(<StockIntradayChart accum={WITH_TICKS} />);
    const main = [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )!;
    const nodes = [
      ...main.querySelectorAll('[data-testid="y-grid"], [data-testid="vp-bar"], polygon, polyline'),
    ];
    const testids = nodes.map((n) => n.getAttribute("data-testid"));
    const lastGrid = testids.lastIndexOf("y-grid");
    const firstBar = testids.indexOf("vp-bar");
    const firstFill = nodes.findIndex((n) => n.tagName.toLowerCase() === "polygon");
    expect(lastGrid).toBeGreaterThanOrEqual(0);
    expect(firstBar).toBeGreaterThan(lastGrid);
    expect(firstFill).toBeGreaterThan(firstBar);
  });

  it("尚無成交(tick 全無)→ 一根長條都沒有,不崩", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(vpBars(container).length).toBe(0);
  });

  /** 🟢 SC-4:POC 長條**尖端右側**的價位數字。就地標示(不硬塞左緣 yTicks)——
   *  尖端的 x 隨量比例走,標籤跟著它才指認得出「這根是哪個價位」。 */
  it("POC 長條尖端右側有 accent 價位數字(fmt 口徑)", () => {
    const { container } = wrap(<StockIntradayChart accum={WITH_TICKS} />);
    const label = container.querySelector('[data-testid="vp-poc-label"]')!;
    expect(label).toBeTruthy();
    expect(label.textContent).toBe("2380"); // 7 張 = 域內最大
    const poc = vpBars(container)[2]!; // 降冪排序 → 2380 是最後一根
    expect(Number(label.getAttribute("x"))).toBeCloseTo(
      Y_AXIS_W + Number(poc.getAttribute("width")) + 3,
      6,
    );
    // y 對準長條中心(dy 置中,不用 dominantBaseline —— 同左緣刻度的既有紀律)
    expect(Number(label.getAttribute("y"))).toBeCloseTo(
      Number(poc.getAttribute("y")) + Number(poc.getAttribute("height")) / 2,
      6,
    );
    expect(label.getAttribute("dy")).toBe("0.35em");
    const cls = label.getAttribute("class")!;
    expect(cls).toContain("fill-accent"); // 與 highlight 的長條同色
    // halo 一律描邊,**不得**用底色 rect(主圖 drawnRects === 0 的既有合約)
    expect(cls).toContain("stroke-surface");
    expect(label.getAttribute("paint-order")).toBe("stroke");
  });

  it("關掉量分佈 → POC 標籤跟著消失(vpBars 空 → 自然不畫)", () => {
    const { container } = wrap(<StockIntradayChart accum={WITH_TICKS} />);
    expect(container.querySelector('[data-testid="vp-poc-label"]')).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "量分佈" }));
    expect(container.querySelector('[data-testid="vp-poc-label"]')).toBeNull();
  });

  it("尚無成交(無 bar)→ 無 POC 標籤,不崩", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelector('[data-testid="vp-poc-label"]')).toBeNull();
  });

  it("POC 標籤畫在主價線之後(D7:被 1.6px 主線壓過等於沒畫)", () => {
    const { container } = wrap(<StockIntradayChart accum={WITH_TICKS} />);
    const main = [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )!;
    const nodes = [...main.querySelectorAll('polyline, [data-testid="vp-poc-label"]')];
    const priceIdx = nodes.findIndex((n) =>
      (n.getAttribute("class") ?? "").includes("stroke-bull"),
    );
    const labelIdx = nodes.findIndex((n) => n.getAttribute("data-testid") === "vp-poc-label");
    expect(priceIdx).toBeGreaterThanOrEqual(0);
    expect(labelIdx).toBeGreaterThan(priceIdx);
  });
});

// 🟢 SC-1 / SC-2 / SC-3(mod/intraday-ma-poc-labels):VWAP 與 MA 的**即時價位數值**。
//
// 既有畫面上這兩條線都讀不出數字:VWAP 完全沒有標籤,MA 的右緣帶只印名稱。
// 三組標籤全部由既有 props(g / oLines / showVwap / vpBars)內算,ChartStatic 不新增
// prop —— 新增純量以外的 prop 會打穿 memo,而 hover 每個 mousemove 都 re-render 父層。
describe("StockIntradayChart 即時價位標籤(SC-1/2/3)", () => {
  function mainSvg(container: HTMLElement): SVGSVGElement {
    return [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )! as SVGSVGElement;
  }

  function geomOf(accum: typeof ACCUM) {
    return buildIntradayGeometry(
      { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
      { width: 800, height: 260 },
    );
  }

  // ---- SC-2:VWAP 就地標籤 ----

  /** 就地標示不釘右緣(review F1):VWAP 不是橫貫全寬的水平線,盤中末點在畫面中段,
   *  右緣釘標籤會與線脫節整整 640px。 */
  /** 🔴 code review A-1:標籤文字的**來源**由「vwapLine 末點(前端分鐘近似)」改為
   *  `accum.vwap`(後端逐筆,說明列吃的同一份)。事前標記該變 —— 兩個來源在同一張圖上
   *  印出兩個矛盾的 VWAP 數字(本 fixture 實證 2381.67 vs 2380),而 D2 要的是同源同值。
   *  位置仍取 vwapLine 末點(分鐘粒度的位移在畫面上讀不出來,數字對不上讀得出來)。 */
  it("均價開 → vwapLine 末點右側有白色 VWAP 數值(值 = accum.vwap,與說明列同源)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const label = container.querySelector('[data-testid="edge-price-vwap"]')!;
    expect(label).toBeTruthy();
    // ACCUM 的 accum.vwap = 2_380_000 → "2380"(fmt 不 snap tick:VWAP 是統計量
    // 不是可掛單價,review F3)。前端分鐘近似值是 2381.67,兩者刻意不同以驗來源。
    expect(label.textContent).toBe("2380");
    // 同源同值:說明列印的是同一個數字(兩處各取各的來源時,失效樣態是純數字不一致)
    expect(container.querySelector("figcaption")!.textContent).toContain("VWAP 2380");
    const end = geomOf(ACCUM).vwapLine.at(-1)!;
    expect(Number(label.getAttribute("x"))).toBeCloseTo(end.x + 4, 6);
    expect(Number(label.getAttribute("y"))).toBeCloseTo(end.y, 6);
    expect(label.getAttribute("dy")).toBe("0.35em");
    expect(label.getAttribute("text-anchor")).toBe("start");
    const cls = label.getAttribute("class")!;
    expect(cls).toContain("fill-ink"); // 跟線色(白)
    expect(cls).toContain("stroke-surface");
    expect(label.getAttribute("paint-order")).toBe("stroke");
  });

  it("accum.vwap 不可得(null)→ 不畫標籤(與說明列的「-」一致,不退回前端近似值)", () => {
    const noVwap = fromSnapshot({
      code: "2330", seq: 2,
      last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
      vwap: null,
      minutes: {
        "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_380_000 },
      },
      ticks: [], book: null,
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={noVwap} />);
    // 線照畫(它是分鐘序列的幾何,與後端 VWAP 可得性無關),只是沒有數字可標
    expect(container.querySelector('polyline[class*="stroke-ink"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="edge-price-vwap"]')).toBeNull();
    expect(container.querySelector("figcaption")!.textContent).toContain("VWAP -");
  });

  it("關均價 toggle → VWAP 標籤跟著線一起消失", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(container.querySelector('[data-testid="edge-price-vwap"]')).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "均價" }));
    expect(container.querySelector('[data-testid="edge-price-vwap"]')).toBeNull();
  });

  /** 盤末(13:30)時末點就在繪圖區右界上,`x + 4` 會把標籤整塊推進右緣疊線標籤帶
   *  甚至出畫布 —— 那是「畫了但看不到」的靜默失敗。 */
  it("末點貼右界 → 標籤 x 內縮,整塊不出繪圖區右界", () => {
    const late = fromSnapshot({
      code: "2330", seq: 2,
      last: { p: 2_390_000, t: "13:30:10.000", cum_vol: 12 },
      vwap: 2_390_000,
      minutes: {
        "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_380_000 },
        "810": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_390_000 },
      },
      ticks: [], book: null,
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={late} />);
    const label = container.querySelector('[data-testid="edge-price-vwap"]')!;
    const end = geomOf(late).vwapLine.at(-1)!;
    const x = Number(label.getAttribute("x"));
    expect(end.x).toBeCloseTo(800 - R_AXIS_W, 6); // 前提:末點真的貼在右界
    expect(x).toBeLessThan(end.x + 4);
    // 標籤寬用 **fmt 口徑**的 40(review B-4):VWAP 是統計量幾乎必帶兩位小數,
    // 千元帶最長 7 字(「1405.67」);拿 fmtTickPrice 口徑的 34 當寬,字尾會溢進右緣帶
    expect(x + 40).toBeLessThanOrEqual(800 - R_AXIS_W);
  });

  // ---- SC-1:MA 即時價位標籤 ----

  it("MA 開 → 右緣內側出現 MA5 / MA20 價位數值(跟線色、halo、無 * 後綴)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const ma5 = container.querySelector('[data-testid="edge-price-ma5"]')!;
    const ma20 = container.querySelector('[data-testid="edge-price-ma20"]')!;
    expect(ma5.textContent).toBe("2330");
    expect(ma20.textContent).toBe("2310");
    // `*` 是 CDP 的專屬記號(review F3):MA 靠 ma5/ma20 的黃 / 紫與 CDP 區分
    expect(ma5.textContent).not.toContain("*");
    expect(ma20.textContent).not.toContain("*");
    expect(ma5.getAttribute("class")).toContain("fill-ma5");
    expect(ma20.getAttribute("class")).toContain("fill-ma20");
    for (const t of [ma5, ma20]) {
      expect(t.getAttribute("class")).toContain("stroke-surface");
      expect(t.getAttribute("paint-order")).toBe("stroke");
      expect(t.getAttribute("text-anchor")).toBe("end");
      expect(t.getAttribute("dy")).toBe("0.35em");
      expect(t.getAttribute("font-size")).toBe("0.5625rem");
      // 繪圖區**內側**右緣:R_AXIS_W=40 的帶裝不下「2330」與名稱兩份內容
      expect(Number(t.getAttribute("x"))).toBe(800 - R_AXIS_W - 2);
    }
  });

  it("MA 標籤是 fmtTickPrice 口徑(日線衍生值 snap 到可下單檔位;round3 B4 不推翻)", async () => {
    // 2_331_237 → 最近合法檔位 2_330_000(5 元 tick);未 snap 會印出 2331.2 這種下不了單的價位
    overlayResponse = { ...OVERLAY, ma5: 2_331_237, ma20: 2_310_000 };
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    expect(container.querySelector('[data-testid="edge-price-ma5"]')!.textContent).toBe("2330");
  });

  it("標籤 y 貼著對應的 MA 線(兩線相距夠遠 → 不位移)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const g = geomOf(ACCUM);
    expect(
      Number(container.querySelector('[data-testid="edge-price-ma5"]')!.getAttribute("y")),
    ).toBeCloseTo(g.toY(2_330_000), 6);
    expect(
      Number(container.querySelector('[data-testid="edge-price-ma20"]')!.getAttribute("y")),
    ).toBeCloseTo(g.toY(2_310_000), 6);
  });

  it("右緣帶內的 MA5 / MA20 **名稱**標籤照舊(白名單 2:不推翻 round3 拍板)", async () => {
    wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() => expect(screen.getByText("MA5", { selector: "text" })).toBeTruthy());
    expect(screen.getByText("MA20", { selector: "text" })).toBeTruthy();
  });

  it("MA toggle 關(預設)→ 無 MA 價位標籤(CDP 的 `價位*` 不受影響)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    await waitFor(() => expect(screen.getByText("2400*", { selector: "text" })).toBeTruthy());
    expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeNull();
    expect(container.querySelector('[data-testid="edge-price-ma20"]')).toBeNull();
  });

  // ---- SC-3 / D7:圖層與既有合約 ----

  it("MA / VWAP 標籤畫在主價線之後(D7)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const nodes = [...mainSvg(container).querySelectorAll('polyline, [data-testid^="edge-price-"]')];
    const priceIdx = nodes.findIndex((n) =>
      (n.getAttribute("class") ?? "").includes("stroke-bull"),
    );
    expect(priceIdx).toBeGreaterThanOrEqual(0);
    for (const id of ["edge-price-vwap", "edge-price-ma5", "edge-price-ma20"]) {
      expect(nodes.findIndex((n) => n.getAttribute("data-testid") === id)).toBeGreaterThan(
        priceIdx,
      );
    }
  });

  /** 白名單 9/10:新標籤的文字只含價位(x > 740 不得有 %),halo 一律描邊不加底色 rect。
   *  兩條既有合約(round3 SC-1 的 % 量法、SC-5 的 drawnRects === 0)就是靠這兩點成立。 */
  it("新標籤不含 % 且不引入任何底色 rect(白名單 9/10)", async () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const labels = [...mainSvg(container).querySelectorAll('[data-testid^="edge-price-"]')];
    expect(labels.length).toBe(3);
    for (const t of labels) expect(t.textContent).not.toContain("%");
    const drawnRects = [...mainSvg(container).querySelectorAll("rect")].filter(
      (r) =>
        r.closest("defs") === null &&
        !(r.getAttribute("data-testid") ?? "").startsWith("y-tick-lamp"),
    );
    expect(drawnRects.length).toBe(0);
  });

  // ---- review B-6:obstacle 路徑(極值文字/圓落在右緣區 → MA 標籤讓位)----

  /** 極值摸點在 13:25(x ≈ 747,落右緣區)且日高 2331 貼著 MA5 2330(相差 ~0.5px)。
   *  未修前的兩個症狀這條都抓得到:(a) 判準漏窄帶 → obstacle 集空 → 標籤壓在極值
   *  文字上;(b) 只避文字不避圓 → 「讓開文字」恰好把標籤推到圓上(review A-2/B-1/B-3)。 */
  const LATE_HIGH = fromSnapshot({
    code: "2330", seq: 2,
    last: { p: 2_330_000, t: "13:25:10.000", cum_vol: 15 },
    vwap: 2_330_000,
    minutes: {
      "541": { c: 2_320_000, v: 10, i: 0, o: 10, u: 0, h: 2_325_000, l: 2_315_000 },
      "805": { c: 2_330_000, v: 5, i: 0, o: 5, u: 0, h: 2_331_000, l: 2_320_000 },
    },
    ticks: [], book: null,
    high: 2_331_000, low: null,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  it("日高在右緣區且貼近 MA 線 → MA 標籤讓位(與極值文字/圓中心距都 ≥ EDGE_LABEL_H)", async () => {
    const { container } = wrap(<StockIntradayChart accum={LATE_HIGH} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const g = geomOf(LATE_HIGH);
    // 極值文字的**中心** = baseline − 0.35em(≈3px;極值 text 無 dy);圓心 = mark.y
    const highLabel = container.querySelector('[data-testid="day-high-label"]')!;
    const textCenter = Number(highLabel.getAttribute("y")) - 3;
    const circleCenter = g.toY(2_331_000);
    for (const id of ["edge-price-ma5", "edge-price-ma20"]) {
      const y = Number(container.querySelector(`[data-testid="${id}"]`)!.getAttribute("y"));
      expect(Math.abs(y - textCenter)).toBeGreaterThanOrEqual(EDGE_LABEL_H);
      expect(Math.abs(y - circleCenter)).toBeGreaterThanOrEqual(EDGE_LABEL_H);
    }
  });

  it("對照組:日高在左半場 → MA 標籤原位不動(不無故位移)", async () => {
    // 同一組價位,只把摸點移回 09:01(x ≈ 39,遠離右緣)
    const earlyHigh = fromSnapshot({
      code: "2330", seq: 2,
      last: { p: 2_330_000, t: "09:02:10.000", cum_vol: 15 },
      vwap: 2_330_000,
      minutes: {
        "541": { c: 2_320_000, v: 10, i: 0, o: 10, u: 0, h: 2_331_000, l: 2_315_000 },
        "542": { c: 2_330_000, v: 5, i: 0, o: 5, u: 0, h: 2_330_000, l: 2_320_000 },
      },
      ticks: [], book: null,
      high: 2_331_000, low: null,
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={earlyHigh} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const g = geomOf(earlyHigh);
    expect(
      Number(container.querySelector('[data-testid="edge-price-ma5"]')!.getAttribute("y")),
    ).toBeCloseTo(g.toY(2_330_000), 6);
  });

  // ---- review B-7:spec edge case 2 / 6 的補鎖 ----

  it("分鐘 c>0 v=0(試撮窗樣態)→ 主圖照畫、vwapLine 空 → 無 VWAP 標籤(不崩)", () => {
    // priceLine 不看量、vwapLine 只在累計量 > 0 才 push —— 「vwapLine 空」不等於
    // 「尚無成交」分支,`?? null` 的守門就是為這條路徑存在
    const noVol = fromSnapshot({
      code: "2330", seq: 1,
      last: null,
      vwap: 2_380_000, // 後端 VWAP 可得,標籤缺席的原因純粹是 vwapLine 空
      minutes: { "541": { c: 2_380_000, v: 0, i: 0, o: 0, u: 0 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={noVol} />);
    expect(screen.queryByText("尚無成交")).toBeNull();
    expect(container.querySelector("polyline")).toBeTruthy();
    expect(container.querySelector('[data-testid="edge-price-vwap"]')).toBeNull();
  });

  it("退化域(upper === lower → toY 常數)→ 兩顆 MA 標籤同 y 起步,避讓後不疊、不崩", async () => {
    overlayResponse = { cdp: null, ma5: 2_330_000, ma20: 2_330_000, date: "2026-07-25" };
    const flat = fromSnapshot({
      code: "2330", seq: 1,
      last: { p: 2_330_000, t: "09:01:30.000", cum_vol: 5 },
      vwap: 2_330_000,
      minutes: { "541": { c: 2_330_000, v: 5, i: 0, o: 5, u: 0 } },
      ticks: [], book: null,
      // 域恰為 [lower, upper] = [X, X]:MA 要「域內」就必須恰等於 X
      meta: { name: "一字盤", ref: 2_330_000, upper: 2_330_000, lower: 2_330_000, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={flat} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const y5 = Number(container.querySelector('[data-testid="edge-price-ma5"]')!.getAttribute("y"));
    const y20 = Number(
      container.querySelector('[data-testid="edge-price-ma20"]')!.getAttribute("y"),
    );
    expect(y20 - y5).toBeGreaterThanOrEqual(EDGE_LABEL_H);
  });
});

// 🟢 SC-5 / D10:期貨態(個股期合約主圖)。三件事同時成立才算對 ——
// (1) x 窗換成 08:45–13:45(含量柱寬的分母);(2) overlay / VP 這兩個日線與現股口徑的
// 疊加物不畫;(3) **不可打請求**(打了就是白花 TC4/FinMind 的錢還汙染 query cache)。
//
// 期貨態一律由**顯式 prop** 傳入,不從 `accum.code` 猜(R6):code 的形狀是資料層契約,
// 拿它當渲染分支的判準等於讓兩層耦合,而後端哪天改 key 形狀時前端會靜默退回現貨窗。
describe("StockIntradayChart 期貨態(SC-5/D10)", () => {
  const FUT = fromSnapshot({
    code: "F:CDF:202609",
    seq: 3,
    last: { p: 2_390_000, t: "13:40:10.000", cum_vol: 16 },
    vwap: 2_380_000,
    minutes: {
      // 08:45 與 13:40 是個股期獨有的兩段(現貨窗會整段濾掉)
      "525": { c: 2_330_000, v: 4, i: 0, o: 4, u: 0, h: 2_330_000, l: 2_330_000 },
      "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_395_000, l: 2_370_000 },
      "820": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
    },
    ticks: [
      { t: "08:46:10.000", p: 2_330_000, q: 4, side: "outer" },
      { t: "09:01:30.000", p: 2_380_000, q: 10, side: "outer" },
    ],
    book: null,
    meta: { name: "台積電期", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  /** 兩張 svg 的 viewBox 寬固定 800(高度才是隨可用空間變的那一維) */
  const MAIN_VB_W = 800;
  /** 量副圖繪圖區 800 − Y_AXIS_W − R_AXIS_W = 724 */
  const SUB_PLOT_W = MAIN_VB_W - Y_AXIS_W - R_AXIS_W;

  function urls(): string[] {
    return (globalThis.fetch as unknown as Mock).mock.calls.map((c) => String(c[0]));
  }
  function overlayCalls(): number {
    return urls().filter((u) => u.includes("/api/stock/overlay")).length;
  }
  function energyBars(container: HTMLElement): Element[] {
    return [...container.querySelectorAll('[data-testid="energy-bar"]')];
  }

  it("窗 = 08:45–13:45:窗外三段以外的分鐘全入圖(現貨態同資料只留一根)", () => {
    const fut = wrap(<StockIntradayChart accum={FUT} stkfut />);
    expect(energyBars(fut.container).length).toBe(3);
    fut.unmount();
    cleanup();
    // 對照組:同一份 accum 不給 stkfut → 08:45 與 13:40 被現貨窗濾掉
    const spot = wrap(<StockIntradayChart accum={FUT} />);
    expect(energyBars(spot.container).length).toBe(1);
  });

  // 🔴 code review B1(P1):量柱數與寬只驗到「窗有換」的兩個副作用 —— 而 x 軸本身
  // (時間標與整點格線的座標)沒有任何斷言。`minuteToX` 若漏傳 `xw` 就會退回現貨窗:
  // 量柱照樣三根、寬照樣 300 分母(那兩處各自傳對了),但線與刻度整體左右錯位 ——
  // 09:00 的標籤會落在 08:45 的位置,而畫面「看起來完全正常」。
  it("x 軸:09:00 時間標的座標吃期貨窗(現貨窗對照組不同值)", () => {
    const labelX = () => Number(screen.getByText("09:00", { selector: "text" }).getAttribute("x"));
    const fut = wrap(<StockIntradayChart accum={FUT} stkfut />);
    const futX = labelX();
    // +2 = 標籤相對格線的左偏移(元件內同一處計算)
    expect(futX).toBeCloseTo(minuteToX(540, MAIN_VB_W, STKFUT_WINDOW) + 2, 6);
    fut.unmount();
    cleanup();
    wrap(<StockIntradayChart accum={FUT} />);
    const spotX = labelX();
    expect(spotX).toBeCloseTo(minuteToX(540, MAIN_VB_W, SPOT_WINDOW) + 2, 6);
    // 兩窗的 09:00 不在同一個位置 —— 相等就代表 xw 根本沒傳進去
    expect(futX).not.toBeCloseTo(spotX, 1);
  });

  it("x 軸:整點格線與其時間標同源(逐個整點比對,期貨窗 09:00–13:00)", () => {
    const { container } = wrap(<StockIntradayChart accum={FUT} stkfut />);
    const main = [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )!;
    const labels = [...main.querySelectorAll("text")].filter((t) =>
      /^\d{2}:00$/.test(t.textContent ?? ""),
    );
    expect(labels.map((t) => t.textContent)).toEqual([
      "09:00",
      "10:00",
      "11:00",
      "12:00",
      "13:00",
    ]);
    for (const t of labels) {
      const minute = Number(t.textContent!.slice(0, 2)) * 60;
      const gx = minuteToX(minute, MAIN_VB_W, STKFUT_WINDOW);
      expect(Number(t.getAttribute("x"))).toBeCloseTo(gx + 2, 6);
      // 同一個 x 上要有一條垂直格線(標籤與線分開算的話會靜默錯開)
      const line = [...main.querySelectorAll("line")].find(
        (l) => Math.abs(Number(l.getAttribute("x1")) - gx) < 1e-6 &&
          l.getAttribute("x1") === l.getAttribute("x2"),
      );
      expect(line).toBeTruthy();
    }
  });

  it("量柱寬分母 = 300 分鐘(現貨為 270)", () => {
    const fut = wrap(<StockIntradayChart accum={FUT} stkfut />);
    const w = Number(energyBars(fut.container)[0]!.getAttribute("width"));
    expect(w).toBeCloseTo(SUB_PLOT_W / 300 - 0.4, 6);
    fut.unmount();
    cleanup();
    const spot = wrap(<StockIntradayChart accum={FUT} />);
    const w2 = Number(energyBars(spot.container)[0]!.getAttribute("width"));
    expect(w2).toBeCloseTo(SUB_PLOT_W / 270 - 0.4, 6);
  });

  it("期貨態不打 overlay 請求(對照:現貨態在同一組預設下會打)", async () => {
    const spot = wrap(<StockIntradayChart accum={ACCUM} />);
    await waitFor(() => expect(overlayCalls()).toBe(1));
    spot.unmount();
    cleanup();
    (globalThis.fetch as unknown as Mock).mockClear();
    wrap(<StockIntradayChart accum={FUT} stkfut />);
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    expect(overlayCalls()).toBe(0);
  });

  // 🔴 Phase 6 real-env finding:合約→現貨切換的**那一個 render**,`stkfut` prop 已翻
  // false 但 `accum` 還是上一拍的合約 snapshot(code = instrument key)→ overlay 拿
  // `F:CDF:202608` 當股號打 `/api/stock/overlay/`,後端 `_valid_code` 必 400(實測 2/2 必現)。
  //
  // 這道閘吃 `accum.code` 的**形狀**,與 R6「渲染分支不從 code 猜期貨態」不衝突 ——
  // 判的不是「要不要用期貨窗畫」,是「這個 code 能不能當股號送進 REST 路徑段」。
  it("過渡 render(stkfut 已 false 但 accum 仍是合約)不打 overlay", async () => {
    wrap(<StockIntradayChart accum={FUT} />);
    await waitFor(() => expect(screen.getByLabelText("分時走勢圖")).toBeTruthy());
    await new Promise((r) => setTimeout(r, 50));
    expect(overlayCalls()).toBe(0);
  });

  it("期貨態 VP 長條整組不畫(量分佈預設開也一樣;對照組畫得出來)", () => {
    const fut = wrap(<StockIntradayChart accum={FUT} stkfut />);
    expect(fut.container.querySelectorAll('[data-testid="vp-bar"]').length).toBe(0);
    fut.unmount();
    cleanup();
    const spot = wrap(<StockIntradayChart accum={FUT} />);
    expect(spot.container.querySelectorAll('[data-testid="vp-bar"]').length).toBeGreaterThan(0);
  });

  // 🟢 D6:VWAP 標籤**兩態都出**(vwap toggle 期貨態恆可用);MA 與 POC 標籤隨既有
  // 可用性 = 僅現貨態 —— overlay 不打請求就沒有 MA 線可標,VP 整組不畫就沒有 POC。
  it("期貨態:VWAP 標籤仍出,MA 與 POC 標籤不出(D6;對照組現貨態 POC 標籤畫得出來)", () => {
    const fut = wrap(<StockIntradayChart accum={FUT} stkfut />);
    expect(fut.container.querySelector('[data-testid="edge-price-vwap"]')).toBeTruthy();
    expect(fut.container.querySelector('[data-testid="edge-price-ma5"]')).toBeNull();
    expect(fut.container.querySelector('[data-testid="edge-price-ma20"]')).toBeNull();
    expect(fut.container.querySelector('[data-testid="vp-poc-label"]')).toBeNull();
    fut.unmount();
    cleanup();
    const spot = wrap(<StockIntradayChart accum={FUT} />);
    expect(spot.container.querySelector('[data-testid="vp-poc-label"]')).toBeTruthy();
  });

  it("期貨態:CDP / MA / 量分佈 三顆 toggle 反灰,均價仍可用", () => {
    wrap(<StockIntradayChart accum={FUT} stkfut />);
    for (const label of ["CDP", "MA", "量分佈"]) {
      const btn = screen.getByRole("button", { name: label });
      expect(btn.hasAttribute("disabled")).toBe(true);
      expect(btn.getAttribute("aria-pressed")).toBe("false");
      expect(btn.getAttribute("title")).toBe("期貨合約本輪不提供");
    }
    const vwap = screen.getByRole("button", { name: "均價" });
    expect(vwap.hasAttribute("disabled")).toBe(false);
    expect(vwap.getAttribute("aria-pressed")).toBe("true");
  });
});

// 🟢 R2 SC-3 / SC-4 / SC-5 / SC-9:當日成交點(▲ 買 / ▼ 賣)疊在分時主圖上。
//
// 資料由 caller 折好以 `fills` prop 傳入(core 不沾 capital / TQ,白名單 W-7)——
// 所以本節一律直接注入 prop,既有那份「不分 URL 回 overlay」的 fetch stub 免改。
describe("StockIntradayChart 當日成交點(SC-3/4/5/9)", () => {
  /** B@541 2380 元、S@542 2385 元;兩者都在 ACCUM 的 y 域 [2090000, 2550000] 與現貨窗內 */
  const FILLS: readonly FillPoint[] = [
    { minute: 541, priceMilli: 2_380_000, side: "B", qty: 2 },
    { minute: 542, priceMilli: 2_385_000, side: "S", qty: 1 },
  ];

  /** 量法一律 `polygon[data-testid^="fill-"]`(不含恆存的 `fills-layer` 群組本身),
   *  與圖牆的 per-card 計數同一把尺。 */
  function fillPolys(container: HTMLElement): Element[] {
    return [...container.querySelectorAll('polygon[data-testid^="fill-"]')];
  }

  /** 參考幾何吃**該測試實際渲染的那份 accum**(同「當日高低」節的理由)。 */
  function geoOf(container: HTMLElement, accum: typeof ACCUM) {
    const [, , w, h] = container
      .querySelector("svg")!
      .getAttribute("viewBox")!
      .split(" ")
      .map(Number);
    return {
      w: w!,
      g: buildIntradayGeometry(
        { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
        { width: w!, height: h! },
      ),
    };
  }

  function tipOf(poly: Element): [number, number] {
    const [x, y] = poly.getAttribute("points")!.split(" ")[0]!.split(",").map(Number);
    return [x!, y!];
  }

  function baseY(poly: Element): number {
    return Number(poly.getAttribute("points")!.split(" ")[1]!.split(",")[1]);
  }

  it("SC-3:買畫 fill-bull ▲、賣畫 fill-bear ▼,各帶同底色 halo", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} />);
    const buy = container.querySelector('polygon[data-testid="fill-B-541"]');
    const sell = container.querySelector('polygon[data-testid="fill-S-542"]');
    expect(buy).toBeTruthy();
    expect(sell).toBeTruthy();
    expect(buy!.getAttribute("class")).toContain("fill-bull");
    expect(sell!.getAttribute("class")).toContain("fill-bear");
    // halo:描邊先畫、填色蓋上(同極值圓的 paintOrder 紀律),三角在走勢線 / 填色上才讀得出來
    expect(buy!.getAttribute("class")).toContain("stroke-surface");
    expect(buy!.getAttribute("paint-order")).toBe("stroke");
    expect(Number(buy!.getAttribute("stroke-width"))).toBe(FILL_MARK.halo);
  });

  it("SC-3:三角尖端 = (成交分鐘 x, 成交價 y);買體朝下、賣體朝上", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} />);
    const { w, g } = geoOf(container, ACCUM);
    const buy = container.querySelector('polygon[data-testid="fill-B-541"]')!;
    const [bx, by] = tipOf(buy);
    expect(bx).toBeCloseTo(clampFillX(minuteToX(541, w, SPOT_WINDOW), w), 5);
    expect(by).toBeCloseTo(g.toY(2_380_000), 5);
    // 底邊 y:買在尖端**下方**(體背離價線),賣在上方
    expect(baseY(buy)).toBeGreaterThan(by);
    const sell = container.querySelector('polygon[data-testid="fill-S-542"]')!;
    const [, sy] = tipOf(sell);
    expect(sy).toBeCloseTo(g.toY(2_385_000), 5);
    expect(baseY(sell)).toBeLessThan(sy);
  });

  it("SC-3:分鐘落在 x 窗外(14:30 盤後零股)→ 不畫,層本身仍在", () => {
    const { container } = wrap(
      <StockIntradayChart
        accum={ACCUM}
        fills={[{ minute: 870, priceMilli: 2_380_000, side: "B", qty: 1 }]}
      />,
    );
    expect(fillPolys(container).length).toBe(0);
    expect(container.querySelector('[data-testid="fills-layer"]')).toBeTruthy();
  });

  it("SC-3:成交價落在 y 域外 → 不畫(同 overlay / 極值既有規則,不夾到邊上)", () => {
    const { container } = wrap(
      <StockIntradayChart
        accum={ACCUM}
        fills={[{ minute: 541, priceMilli: 3_000_000, side: "S", qty: 1 }]}
      />,
    );
    expect(fillPolys(container).length).toBe(0);
  });

  /** cr1 B-p2-4 [lock]:三角不吃指標事件。整張主圖的 hover 十字線 / readout 都靠 svg 的
   *  `onMouseMove`,而 polygon 蓋在價線上 —— 少了 `pointerEvents="none"`,滑過成交點的
   *  那一瞬 readout 會停格(事件被三角吃掉),而畫面「有圖有值」零錯誤訊號。
   *  沿 `PriceLadder.test.tsx` 的 `pointer-events-none` 屬性鎖先例。 */
  it("SC-3:fills-layer 不吃指標事件(pointerEvents=none)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} />);
    const layer = container.querySelector('[data-testid="fills-layer"]')!;
    expect(layer.getAttribute("pointer-events")).toBe("none");
  });

  it("SC-3:未傳 fills → 零三角(層恆 render,空集合時內容為空)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    expect(fillPolys(container).length).toBe(0);
    expect(container.querySelector('[data-testid="fills-layer"]')).toBeTruthy();
  });

  /** z-order:svg 沒有 z-index,圖層完全由文件順序決定。成交點是「我的單在哪成交」——
   *  被極值標記或 MA 價位標壓過就等於沒畫,而畫面上照樣「有東西」,零錯誤訊號。 */
  it("SC-3:成交點層在 day-high 與 MA 價位標之後(ChartStatic 內最上層)", async () => {
    const withHL = { ...ACCUM, high: 2_395_000, low: 2_370_000 };
    const { container } = wrap(<StockIntradayChart accum={withHL} fills={FILLS} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const main = [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )!;
    const nodes = [...main.querySelectorAll("*")];
    const idx = (sel: string) => nodes.indexOf(main.querySelector(sel)!);
    expect(idx('[data-testid="fills-layer"]')).toBeGreaterThan(idx('[data-testid="day-high"]'));
    expect(idx('[data-testid="fills-layer"]')).toBeGreaterThan(
      idx('[data-testid="edge-price-ma5"]'),
    );
  });

  it("SC-4:hover 到有成交的分鐘 → readout 尾端追加「成交 買 2@2380」(bull)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} />);
    fireEvent.mouseMove(container.querySelector("svg")!, {
      clientX: minuteToX(541, 800, SPOT_WINDOW),
      clientY: 100,
    });
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children.length).toBe(7);
    expect(readout.textContent).toContain("成交");
    expect(readout.textContent).toContain("買 2@2380");
    const last = readout.children[readout.children.length - 1]!;
    expect(last.getAttribute("class")).toContain("text-bull");
  });

  /** cr1 B-p2-2 [lock]:賣單單側的 tone。買側(bull)與雙側(無 tone)本節已鎖,
   *  中間那條 `every(S) → bear` 分支沒有斷言 —— 掉成 undefined 或跟著買側塗紅都不會紅。 */
  it("SC-4:hover 到只有賣的分鐘 → 成交欄 tone bear", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} />);
    fireEvent.mouseMove(container.querySelector("svg")!, {
      clientX: minuteToX(542, 800, SPOT_WINDOW),
      clientY: 100,
    });
    const readout = screen.getByTestId("chart-readout");
    expect(readout.textContent).toContain("賣 1@2385");
    const last = readout.children[readout.children.length - 1]!;
    expect(last.getAttribute("class")).toContain("text-bear");
  });

  it("SC-4:同分鐘買賣各一 → 「買 2@2380 賣 1@2385」且不判色(雙側無單一 tone)", () => {
    const both: readonly FillPoint[] = [
      { minute: 541, priceMilli: 2_380_000, side: "B", qty: 2 },
      { minute: 541, priceMilli: 2_385_000, side: "S", qty: 1 },
    ];
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={both} />);
    fireEvent.mouseMove(container.querySelector("svg")!, {
      clientX: minuteToX(541, 800, SPOT_WINDOW),
      clientY: 100,
    });
    const readout = screen.getByTestId("chart-readout");
    expect(readout.textContent).toContain("買 2@2380 賣 1@2385");
    const last = readout.children[readout.children.length - 1]!;
    expect(last.getAttribute("class")).not.toContain("text-bull");
    expect(last.getAttribute("class")).not.toContain("text-bear");
  });

  /** 🔴 cr1 A-2:readout 與三角**同一把尺**。readout 若吃未過濾的 `fills`,價格落在
   *  `g.yDomain` 外時圖上一個三角都沒有、readout 卻報「成交 賣 1@9999」——
   *  使用者在圖上找不到那一筆,而兩邊都不會有測試紅。 */
  it("SC-4:成交價落在 y 域外 → 圖無三角且 readout 不追加(與三角同一把尺)", () => {
    const { container } = wrap(
      <StockIntradayChart
        accum={ACCUM}
        fills={[{ minute: 541, priceMilli: 9_999_000, side: "S", qty: 1 }]}
      />,
    );
    expect(fillPolys(container).length).toBe(0);
    fireEvent.mouseMove(container.querySelector("svg")!, {
      clientX: minuteToX(541, 800, SPOT_WINDOW),
      clientY: 100,
    });
    const readout = screen.getByTestId("chart-readout");
    expect(readout.children.length).toBe(6);
    expect(readout.textContent).not.toContain("成交");
  });

  it("SC-4:hover 到無成交的分鐘 → 不追加(六欄不變)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={[FILLS[0]!]} />);
    fireEvent.mouseMove(container.querySelector("svg")!, {
      clientX: minuteToX(542, 800, SPOT_WINDOW),
      clientY: 100,
    });
    const readout = screen.getByTestId("chart-readout");
    expect(readout.textContent).toContain("09:02");
    expect(readout.children.length).toBe(6);
    expect(readout.textContent).not.toContain("成交");
  });

  it("SC-5:toggle 列多一顆「成交點」預設亮;關掉 → 三角全消失 + readout 不追加", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} />);
    const btn = screen.getByRole("button", { name: "成交點" });
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(fillPolys(container).length).toBe(2);
    // 即時態(未 hover)顯示最新分鐘 542,其上有賣單 → 關之前 readout 本來就有「成交」欄
    expect(screen.getByTestId("chart-readout").textContent).toContain("賣 1@2385");
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: "成交點" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
    expect(fillPolys(container).length).toBe(0);
    expect(screen.getByTestId("chart-readout").textContent).not.toContain("成交");
  });

  /** cr1 B-1 [lock]:期貨態的 `xw`。`projectFills` 的窗參數寫死 `SPOT_WINDOW` 時本節其餘
   *  案子全綠(它們的分鐘 541 / 542 兩窗皆內),而畫面上 08:45–08:59 的成交整段消失、
   *  留下來的那些 x 還全部偏掉 —— 期貨窗比現貨窗長 30 分鐘,同一分鐘的 x 不同。
   *  兩個斷言各鎖一半:530 鎖「窗界」、541 鎖「x 換算的分母」。 */
  it("SC-5:期貨態成交點走 STKFUT_WINDOW(08:50 畫得出來、x 以期貨窗反算)", () => {
    const stkfutFills: readonly FillPoint[] = [
      { minute: 8 * 60 + 50, priceMilli: 2_380_000, side: "B", qty: 1 },
      { minute: 541, priceMilli: 2_380_000, side: "B", qty: 1 },
    ];
    const { container } = wrap(
      <StockIntradayChart accum={ACCUM} stkfut fills={stkfutFills} />,
    );
    // 08:50 在期貨窗內、現貨窗外:寫死現貨窗的話這顆會被丟掉
    expect(container.querySelector('polygon[data-testid="fill-B-530"]')).toBeTruthy();
    const { w } = geoOf(container, ACCUM);
    const [x] = tipOf(container.querySelector('polygon[data-testid="fill-B-541"]')!);
    expect(x).toBeCloseTo(clampFillX(minuteToX(541, w, STKFUT_WINDOW), w), 5);
    // 自檢:兩窗對 541 算出的 x 確實不同(相同的話上一行恆綠而毫無意義)
    expect(x).not.toBeCloseTo(clampFillX(minuteToX(541, w, SPOT_WINDOW), w), 5);
  });

  it("SC-5:期貨態「成交點」不反灰(成交資料不依賴日線 overlay)", () => {
    wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} stkfut />);
    const btn = screen.getByRole("button", { name: "成交點" });
    expect(btn.hasAttribute("disabled")).toBe(false);
    expect(btn.getAttribute("aria-pressed")).toBe("true");
  });

  /** SC-9:`ChartStatic` 多一個 prop 之後 memo 還在不在。**畫面上完全看不出來** ——
   *  失效只是每個 mousemove 重建整層線圖(最多 271 格 × 每次移動),圖照畫、值照對。
   *  行內字面值 / 每 render 新陣列都會讓這條紅。 */
  it("SC-9:hover 連發不重建靜態層(fillTrianglePoints 計次不變)", () => {
    // cdp / ma 預種關:overlay query 一 settle 就換 oLines identity,ChartStatic 會**合法**
    // 重建一次,那與本條要量的東西無關,留著會讓計數不可預期。
    window.localStorage.setItem(
      CHART_TOGGLES_KEY,
      JSON.stringify({ vwap: true, cdp: false, ma: false, bb: true, vp: true, fills: true, v: 2 }),
    );
    const counted = vi.mocked(fillTrianglePoints);
    counted.mockClear();
    const { container } = wrap(<StockIntradayChart accum={ACCUM} fills={FILLS} />);
    // 計次自檢:mock 沒接上時「次數沒變」是 0 → 0,恆綠而毫無意義
    expect(counted.mock.calls.length).toBe(FILLS.length);
    const svg = container.querySelector("svg")!;
    for (const clientX of [39, 60, 120]) {
      fireEvent.mouseMove(svg, { clientX, clientY: 40 });
    }
    expect(counted.mock.calls.length).toBe(FILLS.length);
  });
});

// 🔴 R1 SC-1 / SC-2 / SC-3(mod/cdp-edge-label-avoid):右緣**帶內**標籤(走廊 A)避讓。
//
// 帶內每條疊線一顆文字(CDP 印 `價位*`、MA 印名稱),y 至今直接 = 線 y。2330 平靜日
// CDP 五值 + MA5/MA20 七顆常態擠在 36px 內,整組疊字糊成一團(2026-08-20 實證截圖)。
// 這裡鎖的是「標籤離線、線不離」:文字兩兩 ≥ EDGE_LABEL_H,而 <line y1> 逐條仍等於
// 幾何算出的線 y（相鄰只差 6px)。
describe("StockIntradayChart 右緣帶內標籤避讓(R1 SC-1/SC-2/SC-3)", () => {
  /** 七條全落在 y 域內、相鄰 y 差 ≈6px(< 10px 必疊);snap 後五個價位文字互異 */
  const CROWDED = {
    cdp: { ah: 2_364_000, nh: 2_352_400, cdp: 2_340_800, nl: 2_329_200, al: 2_317_600 },
    ma5: 2_306_000,
    ma20: 2_294_400,
    date: "2026-07-25",
  };
  /** 帶內文字的 x(`w − R_AXIS_W + 2`,anchor=start);全檔僅此一處用這個 x */
  const BAND_X = "762";

  function mainSvg(container: HTMLElement): SVGSVGElement {
    return [...container.querySelectorAll("svg")].find(
      (s) => s.getAttribute("aria-label") === "分時走勢圖",
    )! as SVGSVGElement;
  }

  /** 帶內標籤 = x 落在右緣帶、anchor=start 的那組 <text> */
  function bandTexts(container: HTMLElement): SVGTextElement[] {
    return [...mainSvg(container).querySelectorAll("text")].filter(
      (t) => t.getAttribute("x") === BAND_X,
    );
  }

  /** 疊線線體 = 虛線樣式 "3 2" 且自左軸起畫的那組 <line>(平盤線是 "2 3")。
   *  `"36"` = `Y_AXIS_W`(左價軸寬,`stock-intraday-svg.ts`)—— 疊線是唯一自左軸緣起畫的
   *  水平虛線。動了 `Y_AXIS_W` 要一起改這個字面量(改漏的症狀是 selector 收到空陣列)。 */
  function overlayLineEls(container: HTMLElement): SVGLineElement[] {
    return [...mainSvg(container).querySelectorAll("line")].filter(
      (l) => l.getAttribute("stroke-dasharray") === "3 2" && l.getAttribute("x1") === "36",
    );
  }

  async function renderCrowded(): Promise<HTMLElement> {
    overlayResponse = CROWDED;
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() => expect(bandTexts(container).length).toBe(7));
    return container;
  }

  it("SC-2:帶內 7 顆全印,文字集合不變(CDP 五顆帶 `*` + MA5 / MA20 名稱)", async () => {
    const container = await renderCrowded();
    const texts = bandTexts(container).map((t) => t.textContent);
    // fmtTickPrice 口徑(5 元 tick,snapNearest):2_364_000 → 2365、2_317_600 → 2320
    expect(texts).toEqual(["2365*", "2350*", "2340*", "2330*", "2320*", "MA5", "MA20"]);
    expect(texts.filter((t) => t!.endsWith("*")).length).toBe(5);
  });

  it("SC-1:帶內文字相鄰中心距 ≥ 10px(七顆不再疊字)", async () => {
    const container = await renderCrowded();
    // 文字 baseline = 中心 + 3(D5:既有近似,本輪不改渲染方式)
    const ys = bandTexts(container)
      .map((t) => Number(t.getAttribute("y")))
      .sort((a, b) => a - b);
    expect(ys.length).toBe(7);
    for (let i = 1; i < ys.length; i += 1) {
      // 10 = EDGE_LABEL_H;未避讓時這裡是 ≈6.0(fixture 的線距)
      expect(ys[i]! - ys[i - 1]!).toBeGreaterThanOrEqual(10);
    }
  });

  it("SC-3:線體不動 —— <line y1> 逐條仍等於幾何線 y,相鄰只差約 6px", async () => {
    const container = await renderCrowded();
    const g = buildIntradayGeometry(
      { minutes: ACCUM.minutes, meta: ACCUM.meta, high: ACCUM.high, low: ACCUM.low },
      { width: 800, height: 260 },
    );
    const lines = overlayLineEls(container);
    expect(lines.length).toBe(7);
    const prices = [2_364_000, 2_352_400, 2_340_800, 2_329_200, 2_317_600, 2_306_000, 2_294_400];
    for (const [i, l] of lines.entries()) {
      expect(Number(l.getAttribute("y1"))).toBeCloseTo(g.toY(prices[i]!), 6);
      expect(l.getAttribute("y2")).toBe(l.getAttribute("y1"));
    }
    // 線仍擠在一起(標籤被推開的同時線沒跟著走):相鄰 ≈6px < EDGE_LABEL_H。
    // `6.0` 由**檔案級 ACCUM 的 y 域**推得,不是憑感覺挑的:域 = meta 的漲跌停
    // [2_090_000, 2_550_000](跨度 460_000),plotH = 260 − X_LABEL_H(14) − 2×PAD_Y(8) = 238,
    // fixture 相鄰價差 11_600 毫元 → 11_600 / 460_000 × 238 = 6.0017px。
    // 動 ACCUM 的 meta / 本檔 CROWDED 的價位 / 圖高 → 這個字面量要一起重算。
    const ys = lines.map((l) => Number(l.getAttribute("y1"))).sort((a, b) => a - b);
    for (let i = 1; i < ys.length; i += 1) {
      expect(ys[i]! - ys[i - 1]!).toBeCloseTo(6.0, 1);
    }
  });

  it("SC-1:最下面那顆標籤真的離開了自己的線(避讓有作用,不是 vacuous)", async () => {
    const container = await renderCrowded();
    const lastText = bandTexts(container).at(-1)!; // MA20,輸出順序 = 輸入順序
    const lastLine = overlayLineEls(container).at(-1)!;
    const textY = Number(lastText.getAttribute("y"));
    const lineY = Number(lastLine.getAttribute("y1"));
    // 未避讓時 textY === lineY + 3;七顆全擠時 MA20 被推開 24px。
    // `24` 與上一條的 `6.0` **同源**(檔案級 ACCUM 的 y 域):七顆自第一顆起每顆 +10 →
    // 末顆離第一顆 60px,而線只離 6 × 6.0017 = 36.01px,差 23.99 ≈ 24。
    // 動 ACCUM 的 meta / CROWDED 價位 / 圖高 → 6.0 與 24 兩個字面量要一起重算。
    expect(textY - (lineY + 3)).toBeCloseTo(24.0, 1);
  });

  /** 🟢 code review TC-4:D7 —— 走廊 A 用**自己的界** `bandBounds = { PAD_Y, plotBottom − PAD_Y }`
   *  (= 線 y 的值域),不是走廊 B 的 `edgeBounds = { MARK_LABEL_TOP, plotBottom − 5 }`。
   *  兩者上界差 5px(4 vs 9),而 `edgeBounds` 的上界是為了「極值文字不要頂到 viewBox 外」
   *  留的 —— 帶內沒有極值文字,套上去只會把**貼近日高的那條線**的標籤無故往下推 5px,
   *  線卻留在原地(標籤與線脫節)。這一條就是在量那 5px:任一顆線 y 落在 [PAD_Y, MARK_LABEL_TOP)
   *  且不與別人相疊時,標籤必須**完全不動**。
   *
   *  AH 貼近域頂(2_548_000,域 = 漲跌停 [2_090_000, 2_550_000]),其餘四條相距 ≥ 25px。 */
  it("D7:貼近繪圖區頂緣(y < MARK_LABEL_TOP)且不相疊的線 → 標籤不位移(界是 bandBounds 不是 edgeBounds)", async () => {
    overlayResponse = {
      cdp: { ah: 2_548_000, nh: 2_400_000, cdp: 2_350_000, nl: 2_300_000, al: 2_250_000 },
      ma5: null,
      ma20: null,
      date: "2026-07-25",
    };
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    await waitFor(() => expect(bandTexts(container).length).toBe(5));
    const topText = bandTexts(container)[0]!; // AH,輸出順序 = 輸入順序
    const topLine = overlayLineEls(container)[0]!;
    const lineY = Number(topLine.getAttribute("y1"));
    // 推導:plotH = 260 − X_LABEL_H(14) − 2×PAD_Y(8) = 238;
    // y = PAD_Y + (2_550_000 − 2_548_000) / 460_000 × 238 = 4 + 1.0348 = 5.0348 ∈ [4, 9)
    expect(lineY).toBeCloseTo(5.035, 3);
    // 不位移 → 文字 baseline = 線 y + 3(D5)。換成 edgeBounds(top = 9)會 clamp 成 9 → 12
    expect(Number(topText.getAttribute("y"))).toBeCloseTo(lineY + 3, 6);
    expect(Number(topText.getAttribute("y"))).toBeCloseTo(8.035, 3);
  });

  it("W3:文字的 x / 顏色 / 字級不變(只動 y)", async () => {
    const container = await renderCrowded();
    const texts = bandTexts(container);
    for (const t of texts) {
      expect(t.getAttribute("x")).toBe(BAND_X);
      expect(t.getAttribute("font-size")).toBe("0.5625rem");
    }
    expect(texts[0]!.getAttribute("class")).toContain("fill-bull");
    expect(texts[5]!.getAttribute("class")).toContain("fill-ma5");
    expect(texts[6]!.getAttribute("class")).toContain("fill-ma20");
  });
});

// ---- 2026-08-22 review R1 P1:VWAP 就地標籤 × MA 價位標 ----
describe("VWAP 就地標籤進 MA 價位標的 obstacles(mod/vwap-label-avoid)", () => {
  function geomOf(accum: typeof ACCUM) {
    return buildIntradayGeometry(
      { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
      { width: 800, height: 260 },
    );
  }
  const lateSnap = {
    code: "2330", seq: 2,
    last: { p: 2_390_000, t: "13:30:10.000", cum_vol: 12 },
    vwap: 2_390_000,
    minutes: {
      "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_380_000 },
      "810": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_390_000 },
    },
    ticks: [], book: null,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  };

  /** PR #78 SC-4 近拍實證:末點貼右界時 VWAP 標籤右緣 = w−R_AXIS_W,與 MA 價位標
   *  (anchor=end 在 w−R_AXIS_W−2、向左佔 EDGE_LABEL_W)x 區間完全重疊;y 相近即疊印。
   *  VWAP 是就地標籤(位置 = 線末點在哪,是資訊)不動,MA 價位標是冗餘數值 → 讓位。
   *  註:fixture 的 `vwap: 2_390_000` 只決定標籤文字;標籤 y 取前端累計線末點(≈2_381_667),
   *  碰撞依據是 y,所以修前中心距 4.31px(< 10)即重現症狀。 */
  it("末點貼右界且 MA5 價位≈VWAP → MA5 標籤讓位(中心距 ≥ EDGE_LABEL_H),VWAP 標籤不動", async () => {
    overlayResponse = { ...OVERLAY, ma5: 2_390_000, ma20: 2_310_000 };
    const late = fromSnapshot(lateSnap);
    const { container } = wrap(<StockIntradayChart accum={late} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const vwap = container.querySelector('[data-testid="edge-price-vwap"]')!;
    const ma5 = container.querySelector('[data-testid="edge-price-ma5"]')!;
    const end = geomOf(late).vwapLine.at(-1)!;
    expect(Number(vwap.getAttribute("y"))).toBeCloseTo(end.y, 6); // VWAP 就地不動
    expect(
      Math.abs(Number(ma5.getAttribute("y")) - Number(vwap.getAttribute("y"))),
    ).toBeGreaterThanOrEqual(EDGE_LABEL_H);
  });

  it("末點在畫面中段(x 區間不碰 MA 走廊)且 MA5 價位≈VWAP → MA5 標籤不位移", async () => {
    // ACCUM 只有 09:01–09:02 兩分鐘,vwapLine 末點在繪圖區左側(x 不碰 maLabelLeft)。
    // 前置(敏感度所繫):累計 VWAP 末點 ≈2_381_667 與 ma5 2_380_000 的 y 差 ≈0.86px
    // (< EDGE_LABEL_H),所以「無條件把 VWAP 當 obstacle」的回歸才會讓本案紅;
    // 改 ACCUM 的 minutes 前先確認這個差距仍 < 10px,否則本案靜默失去鑑別力。
    overlayResponse = { ...OVERLAY, ma5: 2_380_000, ma20: 2_310_000 };
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    fireEvent.click(screen.getByRole("button", { name: "MA" }));
    await waitFor(() =>
      expect(container.querySelector('[data-testid="edge-price-ma5"]')).toBeTruthy(),
    );
    const g = geomOf(ACCUM);
    expect(
      Number(container.querySelector('[data-testid="edge-price-ma5"]')!.getAttribute("y")),
    ).toBeCloseTo(g.toY(2_380_000), 6);
  });
});

// 🔴 N007(mod/chart-label-batch):VWAP 就地標籤 × 當日極值文字互相避讓。
//
// 兩者至今誰也不避誰。預設側(日高的文字在標記上方 7px)與 VWAP 末點的中心距恰好
// = EDGE_LABEL_H,所以平時看不出問題;**翻面態**(極值貼圖框上緣 → markLabelY 把文字
// 翻到標記下方 14px)會把文字翻到 VWAP 那一側,盤末摸到接近漲停的日高 + VWAP 略低於它
// 就是兩層 halo 疊印。VWAP 標籤不可動(y = 線末點在哪 = 資訊),讓位的是極值**文字**
// —— 標記圓照樣釘在那一分鐘 / 那個價位上。
describe("StockIntradayChart 極值文字 × VWAP 標籤避讓(N007)", () => {
  /** 域 [2_090_000, 2_550_000](upper/lower 給定)、plotH 238 → toY(p) = 4 + (2550−p)/460 × 238。
   *
   *  日高 2_540_000 → 標記 y ≈ 9.17:`y − 7 = 2.17 < MARK_LABEL_TOP(9)` → 文字翻到下方
   *  (baseline 23.17 / 中心 20.17)。累計 VWAP 末點 = (2_500_000×10 + 2_538_000×10) / 20
   *  = 2_519_000 → y ≈ 20.04。兩者中心距 **0.13px**(修前)。
   *  極值在 13:25(x ≈ 746.6)、VWAP 末點同分鐘 → x 區間相交,避讓才該啟動。 */
  const LATE_TOP_HIGH = fromSnapshot({
    code: "2330", seq: 2,
    last: { p: 2_538_000, t: "13:25:10.000", cum_vol: 20 },
    vwap: 2_519_000,
    minutes: {
      "541": { c: 2_500_000, v: 10, i: 0, o: 10, u: 0, h: 2_500_000, l: 2_500_000 },
      "805": { c: 2_538_000, v: 10, i: 0, o: 10, u: 0, h: 2_540_000, l: 2_530_000 },
    },
    ticks: [], book: null,
    high: 2_540_000, low: null,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  /** 對照組:同一組價位,只把「摸到日高的那一分鐘」搬回 09:01(x ≈ 38.7,左半場)
   *  → x 區間不相交,文字不得無故位移。 */
  const EARLY_TOP_HIGH = fromSnapshot({
    code: "2330", seq: 2,
    last: { p: 2_538_000, t: "13:25:10.000", cum_vol: 20 },
    vwap: 2_519_000,
    minutes: {
      "541": { c: 2_500_000, v: 10, i: 0, o: 10, u: 0, h: 2_540_000, l: 2_500_000 },
      "805": { c: 2_538_000, v: 10, i: 0, o: 10, u: 0, h: 2_538_000, l: 2_530_000 },
    },
    ticks: [], book: null,
    high: 2_540_000, low: null,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  function geom(accum: typeof ACCUM) {
    return buildIntradayGeometry(
      { minutes: accum.minutes, meta: accum.meta, high: accum.high, low: accum.low },
      { width: 800, height: 260 },
    );
  }

  it("日高文字翻面後落在 VWAP 標籤上 → 文字讓位(中心距 ≥ EDGE_LABEL_H),圓不動", () => {
    const { container } = wrap(<StockIntradayChart accum={LATE_TOP_HIGH} />);
    const g = geom(LATE_TOP_HIGH);
    const vwapY = Number(
      container.querySelector('[data-testid="edge-price-vwap"]')!.getAttribute("y"),
    );
    // 前置(敏感度所繫):兩者本來就在同一條走廊上、y 幾乎重合
    expect(vwapY).toBeCloseTo(g.vwapLine.at(-1)!.y, 6);
    const label = container.querySelector('[data-testid="day-high-label"]')!;
    // 極值文字無 dy → y 是 baseline,中心 = baseline − 0.35em(≈3px)
    const center = Number(label.getAttribute("y")) - 3;
    // 推到**剛好**一個 EDGE_LABEL_H = 字面 10(不多推:讓位是為了不疊,不是為了離得遠)。
    // 用 closeTo 不用 ≥:浮點下 toY 算出來的差是 9.999999999999996。
    // 字面值不回算常數:回算的話 EDGE_LABEL_H 改了、實際間距跟著改,本案照樣綠
    // —— 那正是「同義反覆」量不到的那一格。
    expect(center - vwapY).toBeCloseTo(10, 6);
    // 標記圓承載「哪一分鐘 / 什麼價位」→ 一律不動
    const circle = container.querySelector('[data-testid="day-high"]')!;
    expect(Number(circle.getAttribute("cy"))).toBeCloseTo(g.toY(2_540_000), 6);
    // 水平位置不變(讓位只動 y)
    expect(Number(label.getAttribute("x"))).toBe(800 - R_AXIS_W - 16);
  });

  it("對照組:日高在左半場(x 區間不相交)→ 文字 y 逐值不變(不無故位移)", () => {
    const { container } = wrap(<StockIntradayChart accum={EARLY_TOP_HIGH} />);
    const g = geom(EARLY_TOP_HIGH);
    const label = container.querySelector('[data-testid="day-high-label"]')!;
    // 翻面後的 baseline = 標記 y + labelUp.flip(14)
    expect(Number(label.getAttribute("y"))).toBeCloseTo(g.toY(2_540_000) + 14, 6);
  });

  /** 🔴 讓位**方向**(2026-08-24 two-axis review N007-1)。
   *
   *  同樣是翻面態日高,只把 VWAP 末點換到文字的**外側**(下方)。
   *  域 [2_090_000, 2_550_000]、plotH 238 → toY(p) = 4 + (2_550_000 − p)/460_000 × 238。
   *  日高 2_540_000 → 標記 y ≈ 9.17;`9.17 − 7 < MARK_LABEL_TOP(9)` → 文字翻到標記下方
   *  (baseline 23.17 / 中心 20.17)。累計 VWAP = (2_500_000×10 + 2_530_000×5) / 15
   *  = 2_510_000 → y ≈ 24.70,中心距 4.52px(< EDGE_LABEL_H)→ 避讓啟動。
   *
   *  「遠離該鄰居」的推法在這一側**正好把文字推向標記圓**:24.70 − 10 = 14.70,距圓心
   *  9.17 只剩 5.52px —— 讓開一層 halo 換來壓在圓上,而圓正是那顆不可動的資訊。
   *  正解是**沿文字原本相對標記的那一側**推開(這裡是往下)。 */
  const LATE_TOP_HIGH_VWAP_OUTSIDE = fromSnapshot({
    code: "2330", seq: 2,
    last: { p: 2_530_000, t: "13:25:10.000", cum_vol: 15 },
    vwap: 2_510_000,
    minutes: {
      "541": { c: 2_500_000, v: 10, i: 0, o: 10, u: 0, h: 2_500_000, l: 2_500_000 },
      "805": { c: 2_530_000, v: 5, i: 0, o: 5, u: 0, h: 2_540_000, l: 2_530_000 },
    },
    ticks: [], book: null,
    high: 2_540_000, low: null,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  it("VWAP 在翻面文字的外側 → 文字沿原方向讓開(不被推回標記圓上)", () => {
    const { container } = wrap(<StockIntradayChart accum={LATE_TOP_HIGH_VWAP_OUTSIDE} />);
    const g = geom(LATE_TOP_HIGH_VWAP_OUTSIDE);
    const markY = g.toY(2_540_000);
    const vwapY = Number(
      container.querySelector('[data-testid="edge-price-vwap"]')!.getAttribute("y"),
    );
    // 前置(敏感度所繫):VWAP 就地標籤真的在文字外側,且中心距 < EDGE_LABEL_H
    expect(vwapY).toBeCloseTo(g.vwapLine.at(-1)!.y, 6);
    const flippedCenter = markY + 14 - 3;
    expect(vwapY).toBeGreaterThan(flippedCenter);
    expect(vwapY - flippedCenter).toBeLessThan(10);
    const label = container.querySelector('[data-testid="day-high-label"]')!;
    const center = Number(label.getAttribute("y")) - 3;
    // 主張一:標記圓不可壓(修前 5.52px = 文字直接落在圓上)。字面 10 = EDGE_LABEL_H
    // 當下的值,不回算常數(理由同上一案)。
    expect(Math.abs(center - markY)).toBeGreaterThanOrEqual(10);
    // 主張二:VWAP 仍讓開剛好一個 10,且是**往原方向**(文字本來就在圓下方)
    expect(center - vwapY).toBeCloseTo(10, 6);
    // 標記圓照樣釘在那一分鐘 / 那個價位上
    const circle = container.querySelector('[data-testid="day-high"]')!;
    expect(Number(circle.getAttribute("cy"))).toBeCloseTo(markY, 6);
  });
});

// 🔴 N008:群組檢視走 `?tape=0`(明細與 VP 全空),切回單檔的**首 paint** 手上還是那份
// accum —— VP 圖層一片空,與「今天真的沒成交」同形。`accum.tapeOmitted` 為真時 toggle
// 區改印「載入中」。**排版必須固定**(user 附註):同一顆 button、class 逐字不變、
// 兩個 label 同為 3 個全形字 → box 尺寸不變。
describe("StockIntradayChart VP 載入佔位(N008)", () => {
  function accumWith(over: Record<string, unknown>) {
    return { ...WITH_TICKS_FOR_PLACEHOLDER, ...over };
  }

  const WITH_TICKS_FOR_PLACEHOLDER = fromSnapshot({
    code: "2330",
    seq: 2,
    last: { p: 2_390_000, t: "09:02:10.000", cum_vol: 12 },
    vwap: 2_380_000,
    minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
    ticks: [{ t: "09:01:30.000", p: 2_380_000, q: 7, side: "outer" }],
    book: null,
    meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  });

  it("tapeOmitted → VP toggle 印「載入中」;正常態印「量分佈」", () => {
    const { unmount } = wrap(<StockIntradayChart accum={accumWith({ tapeOmitted: true })} />);
    expect(screen.getByRole("button", { name: "載入中" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "量分佈" })).toBeNull();
    unmount();
    wrap(<StockIntradayChart accum={WITH_TICKS_FOR_PLACEHOLDER} />);
    expect(screen.getByRole("button", { name: "量分佈" })).toBeTruthy();
  });

  // 不跑版的機械證據:同一顆鈕、class 與 disabled / aria-pressed 逐值相同,
  // label 字數相同 → 佔位與正常態的 box 尺寸不變。
  it("佔位與正常態的 class / 狀態 / 字數完全相同(不跑版)", () => {
    const { unmount } = wrap(<StockIntradayChart accum={WITH_TICKS_FOR_PLACEHOLDER} />);
    const normal = screen.getByRole("button", { name: "量分佈" });
    const normalClass = normal.className;
    const normalPressed = normal.getAttribute("aria-pressed");
    const normalDisabled = (normal as HTMLButtonElement).disabled;
    const toggleCount = screen.getAllByRole("button").length;
    unmount();

    wrap(<StockIntradayChart accum={accumWith({ tapeOmitted: true })} />);
    const loading = screen.getByRole("button", { name: "載入中" });
    expect(loading.className).toBe(normalClass);
    expect(loading.getAttribute("aria-pressed")).toBe(normalPressed);
    expect((loading as HTMLButtonElement).disabled).toBe(normalDisabled);
    expect(screen.getAllByRole("button").length).toBe(toggleCount); // 顆數不變
    expect((loading.textContent ?? "").length).toBe(3); // 與「量分佈」同字數
  });

  it("按下去仍是同一顆 VP toggle(佔位不吃掉互動)", () => {
    wrap(<StockIntradayChart accum={accumWith({ tapeOmitted: true })} />);
    const btn = screen.getByRole("button", { name: "載入中" });
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: "載入中" }).getAttribute("aria-pressed")).toBe("false");
  });
});
