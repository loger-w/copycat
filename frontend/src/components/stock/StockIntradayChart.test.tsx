/** @vitest-environment jsdom */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { fromSnapshot } from "@/lib/stock-accum";
import { buildIntradayGeometry, lastPoint, R_AXIS_W, Y_AXIS_W } from "@/lib/stock-intraday-svg";

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

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const ACCUM = fromSnapshot({
  code: "2330",
  seq: 2,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 12 },
  vwap: 2_380_000,
  cum_inner: 2,
  cum_outer: 10,
  minutes: {
    // round4 項 1:per-minute h/l 是當日高低標記的定位依據 —— 標記畫在「摸到極值的
    // 那一分鐘」上,而 541 的高(2_395_000)高於任何一分鐘的收盤,正是「摸到就算」的樣態
    "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_395_000, l: 2_370_000 },
    "542": { c: 2_390_000, v: 2, i: 2, o: 0, u: 0, h: 2_390_000, l: 2_385_000 },
  },
  ticks: [],
  book: null,
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_close: 2_320_000, y_vol: 100 },
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
      vwap: 2_380_000, cum_inner: 2, cum_outer: 10,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: null, upper: null, lower: null, y_close: null, y_vol: 100 },
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
      code: "2330", seq: 0, last: null, vwap: null, cum_inner: 0, cum_outer: 0,
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

  // 🟢 round3 SC-8:內外盤能量副圖的量刻度
  it("內外盤副圖左緣有量刻度(頂端 = 單邊最大張數、中線 = 其半)(SC-8)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const sub = [...container.querySelectorAll("svg")].find(
      (s2) => s2.getAttribute("aria-label") === "內外盤能量",
    )!;
    const texts = [...sub.querySelectorAll("text")].map((t) => t.textContent);
    // ACCUM 的最大單邊 = 10(540 分 o:10)
    expect(texts).toContain("10");
    expect(texts).toContain("5");
  });

  // 🔴 SC-5:主圖底部量 bar 移除,只留內外盤能量副圖
  it("主圖不再有量 bar;內外盤能量副圖仍在(SC-5)", () => {
    const { container } = wrap(<StockIntradayChart accum={ACCUM} />);
    const svgs = [...container.querySelectorAll("svg")];
    const main = svgs.find((s) => s.getAttribute("aria-label") === "分時走勢圖")!;
    const sub = svgs.find((s) => s.getAttribute("aria-label") === "內外盤能量")!;
    // defs 內的 rect 是 clipPath 的裁切框、不是畫面元素,要排除。
    // round6 項 5 起主圖多了兩個 rect(左緣漲跌停亮燈),它們不是量 bar ——
    // 本條守的是「量 bar 不在主圖」,所以改成排除已知的非量元素後仍須為 0,
    // 而不是「主圖一個 rect 都不能有」(後者會把任何新的色塊元素都誤判成 regression)。
    const drawnRects = [...main.querySelectorAll("rect")].filter(
      (r) =>
        r.closest("defs") === null &&
        !(r.getAttribute("data-testid") ?? "").startsWith("y-tick-lamp") &&
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
      sub: all.find((s) => s.getAttribute("aria-label") === "內外盤能量")!,
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
      vwap: 2_380_000, cum_inner: 0, cum_outer: 10,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_380_000, l: 2_380_000 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: null, upper: null, lower: null, y_close: null, y_vol: 100 },
    });
    const { container } = wrap(<StockIntradayChart accum={noRef} />);
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

  it("未分類段用斜線 pattern,不是實心 fill-* class(review R11)", () => {
    const { container } = wrap(<StockIntradayChart accum={withUnch} />);
    const seg = container.querySelector('[data-testid="energy-unch"]')!;
    expect(seg.getAttribute("style")).toMatch(/fill:\s*url\(#/);
    // fill class 一旦留著就會蓋掉 pattern(presentation attribute 優先權低於 CSS)
    expect(seg.getAttribute("class") ?? "").not.toContain("fill-");
  });

  it("pattern 用 userSpaceOnUse,且 id 隨 useId 唯一(同頁多張圖不撞)", () => {
    const { container } = wrap(<StockIntradayChart accum={withUnch} />);
    const pat = container.querySelector("pattern")!;
    expect(pat.getAttribute("patternUnits")).toBe("userSpaceOnUse");
    const seg = container.querySelector('[data-testid="energy-unch"]')!;
    expect(seg.getAttribute("style")).toContain(pat.getAttribute("id")!);
    // tile 內有底色 rect,窄柱不會整根落在空白帶上變透明(review R6)
    expect(pat.querySelector("rect")).toBeTruthy();
  });

  it("說明列印出未分類量與判定率", () => {
    wrap(<StockIntradayChart accum={withUnch} />);
    expect(screen.getByTestId("unch-total").textContent).toBe("122");
    expect(screen.getByTestId("outer-pct").textContent).toBe("86.4%"); // 127/147
    expect(screen.getByTestId("decided-pct").textContent).toContain("55%"); // 147/269
  });

  it("判定率低於門檻 → 外盤比降對比(SC-2.4)", () => {
    wrap(<StockIntradayChart accum={withUnch} />);
    expect(screen.getByTestId("outer-pct").className).toContain("text-ink-dim/50");
  });

  it("判定率高 → 外盤比維持原色", () => {
    const clean = {
      ...ACCUM,
      minutes: new Map([[540, { c: 2_380_000, v: 100, o: 60, i: 40, u: 0, h: null, l: null }]]),
    } as unknown as typeof ACCUM;
    wrap(<StockIntradayChart accum={clean} />);
    expect(screen.getByTestId("outer-pct").className).not.toContain("text-ink-dim/50");
    expect(screen.getByTestId("decided-pct").textContent).toContain("100%");
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

  function geometryOf(container: HTMLElement) {
    const [, , w, h] = container
      .querySelector("svg")!
      .getAttribute("viewBox")!
      .split(" ")
      .map(Number);
    return buildIntradayGeometry(
      { minutes: ACCUM.minutes, meta: ACCUM.meta },
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

  it("標記是**空心**環,不是實心點 —— 與實心的現價圈 / hover 錨區分(SC-1.5)", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    const ring = container.querySelector('circle[data-testid="day-high"]')!;
    expect(ring.getAttribute("fill")).toBe("none");
    expect(ring.getAttribute("class")).toContain("stroke-ink-muted");
    // 現價圈是實心且帶漲跌色
    const dot = container.querySelector('[data-testid="last-dot"]')!;
    expect(dot.getAttribute("fill")).toBeNull();
    expect(dot.getAttribute("class")).toMatch(/^fill-/);
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
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    const g = geometryOf(container);
    const high = container.querySelector('circle[data-testid="day-high"]')!;
    expect(Number(high.getAttribute("cy"))).toBeCloseTo(g.toY(2_395_000), 5);
    const low = container.querySelector('circle[data-testid="day-low"]')!;
    expect(Number(low.getAttribute("cy"))).toBeCloseTo(g.toY(2_370_000), 5);
  });

  it("標記落在**摸到極值的那一分鐘**,不是最後一分鐘", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_395_000, 2_370_000)} />);
    const g = geometryOf(container);
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

  // review R12:無漲跌停時 y 域由**分鐘收盤**極值決定,裝不下逐筆極值 → 標記會落到時間軸上
  it("當日高超出 y 域 → 不畫(低點仍畫)", () => {
    const { container } = wrap(<StockIntradayChart accum={withHL(2_600_000, 2_370_000)} />);
    expect(container.querySelector('[data-testid="day-high"]')).toBeNull();
    expect(container.querySelector('[data-testid="day-low"]')).toBeTruthy();
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
      vwap: 2_380_000, cum_inner: 2, cum_outer: 10,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
      ticks: [], book: null,
      meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_close: 2_320_000, y_vol: 100 },
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
    const g = geometryOf(container);
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

  it("尚無成交 → 不渲染圓點且不崩", () => {
    const empty = fromSnapshot({
      code: "2330", seq: 1, last: null, vwap: null, cum_inner: 0, cum_outer: 0,
      minutes: {}, ticks: [], book: null,
      meta: { name: "台積電", ref: 2_320_000, upper: null, lower: null, y_close: null, y_vol: null },
    });
    const { container } = wrap(<StockIntradayChart accum={empty} />);
    expect(container.querySelector('[data-testid="last-dot"]')).toBeNull();
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });
});
