/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { fromSnapshot } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  lastPoint,
  minuteToX,
  R_AXIS_W,
  SPOT_WINDOW,
  STKFUT_WINDOW,
  Y_AXIS_W,
} from "@/lib/stock-intraday-svg";
import { VP_FILL_OPACITY, VP_POC_FILL_OPACITY } from "@/lib/volume-profile";
import { wrap } from "@/test-utils";

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
