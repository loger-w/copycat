/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CandleChart } from "@/components/stock/CandleChart";
import type { Bar } from "@/lib/candle";

afterEach(cleanup);

function bar(t: string, o: number, h: number, l: number, c: number, v = 10): Bar {
  return { t, o, h, l, c, v };
}

const BARS: Bar[] = [
  bar("2026-07-24", 100_000, 110_000, 95_000, 108_000),
  bar("2026-07-25", 108_000, 112_000, 104_000, 105_000),
  bar("2026-07-28", 105_000, 118_000, 105_000, 116_000, 30),
];

describe("CandleChart(SC-7)", () => {
  it("無資料顯示「無 K 線資料」", () => {
    render(<CandleChart bars={[]} />);
    expect(screen.getByText("無 K 線資料")).toBeTruthy();
  });

  it("每根 bar 一個蠟燭 body", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(container.querySelectorAll("[data-testid='candle-body']").length).toBe(3);
  });

  it("紅漲綠跌:收 > 開用 bull、收 < 開用 bear(台股慣例)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const bodies = [...container.querySelectorAll("[data-testid='candle-body']")];
    expect(bodies[0]!.getAttribute("class")).toContain("bull"); // 100000 → 108000 漲
    expect(bodies[1]!.getAttribute("class")).toContain("bear"); // 108000 → 105000 跌
  });

  // 🔴 SC-6.3:maxBars prop 移除,可視範圍改由 viewport(initBars + 滾輪縮放)決定
  it("初始只畫最後 initBars 根(viewport 取代 maxBars)", () => {
    const many = Array.from({ length: 200 }, (_, i) =>
      bar(`2026-01-${String((i % 28) + 1).padStart(2, "0")}`, 100, 100, 100, 100),
    );
    const { container } = render(<CandleChart bars={many} initBars={120} />);
    expect(container.querySelectorAll("[data-testid='candle-body']").length).toBe(120);
  });

  // 🔴 SC-6.5:showMa prop 移除,MA 在所有 K 線模式都畫
  it("MA5 / MA20 無條件畫(資料足夠時)", () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      bar(`2026-01-${String(i + 1).padStart(2, "0")}`, 100_000 + i, 100_000 + i, 100_000 + i, 100_000 + i),
    );
    const { container } = render(<CandleChart bars={many} />);
    expect(container.querySelector("[data-testid='ma-5']")).toBeTruthy();
    expect(container.querySelector("[data-testid='ma-20']")).toBeTruthy();
  });

  it("資料不足 5 根 → 連 MA5 都不畫(不是靠 prop 關掉)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(container.querySelector("[data-testid='ma-5']")).toBeNull();
  });

  it("資料不足 20 根時只畫 MA5,不畫 MA20", () => {
    const few = Array.from({ length: 8 }, (_, i) =>
      bar(`2026-01-0${i + 1}`, 100_000, 100_000, 100_000, 100_000),
    );
    const { container } = render(<CandleChart bars={few} />);
    expect(container.querySelector("[data-testid='ma-5']")).toBeTruthy();
    expect(container.querySelector("[data-testid='ma-20']")).toBeNull();
  });

  // 🔴 SC-7.6:圖下方的浮動 tooltip 改成圖上方常駐資訊列 —— 沒 hover 時顯示最後一根,
  // 不是空白。固定停靠、零遮圖、零版面跳動。
  it("資訊列:預設顯示最後一根(即時態),hover 時切換為游標所在根", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const readout = () => screen.getByTestId("chart-readout");
    expect(screen.queryByTestId("candle-tooltip")).toBeNull(); // 舊 tooltip 已移除
    expect(readout().textContent).toContain("2026-07-28"); // 即時態 = 最後一根
    expect(readout().getAttribute("data-hovering")).toBe("false");

    const svg = container.querySelector("svg")!;
    // jsdom 的 getBoundingClientRect 恆 0 寬 → x 直接當 viewBox 座標,x=5 落在第一根
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 100 });
    expect(readout().textContent).toContain("2026-07-24");
    expect(readout().getAttribute("data-hovering")).toBe("true");

    fireEvent.mouseLeave(svg);
    expect(readout().textContent).toContain("2026-07-28");
    expect(readout().getAttribute("data-hovering")).toBe("false");
  });

  // 🔴 SC-7.2:K 線原本只有垂直線,現在兩軸都有,且水平線跟滑鼠 y(當量尺)不是鎖收盤價
  it("十字線:垂直線 snap 蠟燭、水平線跟滑鼠 y", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 120 });
    const h = container.querySelector("[data-testid='crosshair-h']")!;
    expect(h).toBeTruthy();
    expect(Number(h.getAttribute("y1"))).toBe(120);
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 200 });
    expect(Number(container.querySelector("[data-testid='crosshair-h']")!.getAttribute("y1"))).toBe(200);
    expect(container.querySelector("[data-testid='crosshair-v']")).toBeTruthy();
    fireEvent.mouseLeave(svg);
    expect(container.querySelector("[data-testid='crosshair-h']")).toBeNull();
    expect(container.querySelector("[data-testid='crosshair-v']")).toBeNull();
  });

  // 🟢 SC-7.3:左緣顯示滑鼠所在價位(snap 到合法 tick、夾制在資料值域內)
  it("左價標:顯示滑鼠所在價位,量區的 y 夾制在最低價不出負值", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const svg = container.querySelector("svg")!;
    const tagText = () => container.querySelector("[data-testid='price-tag-text']")!.textContent;
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 10 });
    expect(Number(tagText())).toBeLessThanOrEqual(118); // ≤ 全域最高 118
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 999 }); // 遠低於量區
    expect(Number(tagText())).toBe(95); // 夾制在全域最低 95
  });

  // 🟢 SC-7.5:底部時間標籤,且不被 viewBox 上下緣裁切
  it("底部時間標:顯示 hover 根的時間,矩形底邊不超出 viewBox", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 100 });
    const rect = container.querySelector("[data-testid='time-tag']")!;
    const vbH = Number(svg.getAttribute("viewBox")!.split(" ")[3]);
    expect(Number(rect.getAttribute("y")) + Number(rect.getAttribute("height"))).toBeLessThanOrEqual(vbH);
    expect(container.querySelector("[data-testid='time-tag-text']")!.textContent).toBe("07/24");
  });

  it("圖表有可辨識的 aria-label", () => {
    render(<CandleChart bars={BARS} />);
    expect(screen.getByLabelText("K 線圖")).toBeTruthy();
  });

  // 🔴 SC-4:在圖上拖曳是「拉一段來看」的自然手勢,不該把座標軸數字 / 日期標籤反白選起來
  it("圖表容器禁止選字(拖曳不反白;SC-4)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(container.querySelector("figure")?.className).toContain("select-none");
  });
});

// 🟢 SC-6.3 / 6.4:滾輪縮放 + 拖曳平移(取代「往前」鈕的分頁載入)
describe("CandleChart 縮放與平移(SC-6.3/6.4)", () => {
  const MANY = Array.from({ length: 600 }, (_, i) =>
    bar(`2026-07-28 ${String(9 + Math.floor(i / 60)).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}`,
      100_000 + i, 100_100 + i, 99_900 + i, 100_000 + i),
  );
  const bodies = (c: HTMLElement) => c.querySelectorAll("[data-testid='candle-body']").length;

  it("滾輪往下(deltaY > 0)看更多根、往上看更少根", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={240} />);
    expect(bodies(container)).toBe(240);
    const svg = container.querySelector("svg")!;
    fireEvent.wheel(svg, { deltaY: 100, clientX: 700 });
    expect(bodies(container)).toBeGreaterThan(240);
    fireEvent.wheel(svg, { deltaY: -100, clientX: 700 });
    fireEvent.wheel(svg, { deltaY: -100, clientX: 700 });
    expect(bodies(container)).toBeLessThan(240);
  });

  it("縮放下限 20 根、上限 min(total, 700) 根", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={240} />);
    const svg = container.querySelector("svg")!;
    for (let i = 0; i < 40; i += 1) fireEvent.wheel(svg, { deltaY: -100, clientX: 700 });
    expect(bodies(container)).toBe(20);
    for (let i = 0; i < 60; i += 1) fireEvent.wheel(svg, { deltaY: 100, clientX: 700 });
    expect(bodies(container)).toBe(600); // total < MAX_VISIBLE(700)
  });

  it("拖曳往右平移看更早的資料;拖到左端點即停", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={100} />);
    const svg = container.querySelector("svg")!;
    const firstStamp = () =>
      container.querySelector("[data-testid='candle-figure']")?.getAttribute("data-first");
    const before = firstStamp();
    fireEvent.mouseDown(svg, { clientX: 700, button: 0 });
    fireEvent.mouseMove(window, { clientX: 1100 });
    fireEvent.mouseUp(window, { clientX: 1100 });
    expect(firstStamp()).not.toBe(before);
    // 一路拖到底 → 停在第一根
    for (let i = 0; i < 20; i += 1) {
      fireEvent.mouseDown(svg, { clientX: 100, button: 0 });
      fireEvent.mouseMove(window, { clientX: 1300 });
      fireEvent.mouseUp(window, { clientX: 1300 });
    }
    expect(firstStamp()).toBe(MANY[0]!.t);
  });

  // 🔴 C3:hover 存的是「對可視窗口的索引」,縮放改變 viewport.start 後同一個索引會指到
  // 別根 bar —— 十字線與資訊列一起指錯,而且要等下次滑鼠移動才會修正。
  // 不變式:十字線垂直線必須落在游標附近(±1 個 slot),縮放前後都成立。
  it("原地滾輪縮放後,十字線仍落在游標位置(hover 不因視窗位移而失準)", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={240} />);
    const svg = container.querySelector("svg")!;
    const X = 700;
    const crossX = () => Number(container.querySelector("[data-testid='crosshair-v']")!.getAttribute("x1"));
    const slot = () => 1400 / container.querySelectorAll("[data-testid='candle-body']").length;

    fireEvent.mouseMove(svg, { clientX: X, clientY: 200 });
    expect(Math.abs(crossX() - X)).toBeLessThanOrEqual(slot());

    // 滑鼠不動,只滾輪縮放
    fireEvent.wheel(svg, { deltaY: -100, clientX: X });
    expect(Math.abs(crossX() - X)).toBeLessThanOrEqual(slot());
    fireEvent.wheel(svg, { deltaY: -100, clientX: X });
    fireEvent.wheel(svg, { deltaY: 100, clientX: X });
    expect(Math.abs(crossX() - X)).toBeLessThanOrEqual(slot());
  });

  // 🔴 C4:漲跌% 的前一根若只在可視窗口內找,窗口最左那根永遠拿不到 prev → 恆顯示 "-"。
  // MA/BB 已經是「用完整序列算完再切片」以免斷頭,這裡也該同源。
  it("視窗最左一根的漲跌%取自完整序列的前一根,不因切片而顯示 -", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={100} />);
    const svg = container.querySelector("svg")!;
    // 先往右拖(看更早的資料),確保視窗左緣不是整個序列的第一根
    fireEvent.mouseDown(svg, { clientX: 700, button: 0 });
    fireEvent.mouseMove(window, { clientX: 1100 });
    fireEvent.mouseUp(window, { clientX: 1100 });
    // hover 視窗最左那根
    fireEvent.mouseMove(svg, { clientX: 1, clientY: 200 });
    const text = screen.getByTestId("chart-readout").textContent ?? "";
    expect(text).toContain("漲跌");
    expect(text).not.toContain("漲跌 - "); // 佔位
    expect(/漲跌 [+-]?\d/.test(text)).toBe(true);
  });

  it("資料延伸時:原本貼右緣 → 跟進;已平移 → 不被拉回(R10)", () => {
    const { container, rerender } = render(<CandleChart bars={MANY} initBars={100} />);
    const firstStamp = () =>
      container.querySelector("[data-testid='candle-figure']")!.getAttribute("data-first");
    const extended = [...MANY, bar("2026-07-28 19:00", 200_000, 200_000, 200_000, 200_000)];
    // (a) 貼右緣 → 視窗跟著往右
    const atRightBefore = firstStamp();
    rerender(<CandleChart bars={extended} initBars={100} />);
    expect(firstStamp()).not.toBe(atRightBefore);
    // (b) 平移後再延伸 → start 不動
    const svg = container.querySelector("svg")!;
    fireEvent.mouseDown(svg, { clientX: 700, button: 0 });
    fireEvent.mouseMove(window, { clientX: 1100 });
    fireEvent.mouseUp(window, { clientX: 1100 });
    const pannedTo = firstStamp();
    rerender(<CandleChart bars={[...extended, bar("2026-07-28 19:01", 1, 1, 1, 1)]} initBars={100} />);
    expect(firstStamp()).toBe(pannedTo);
  });
});

// 🟢 SC-6.6:布林通道
describe("CandleChart 布林通道(SC-6.6)", () => {
  const MANY = Array.from({ length: 40 }, (_, i) =>
    bar(`2026-01-${String(i + 1).padStart(2, "0")}`, 100_000 + i * 137, 100_000 + i * 137, 100_000 + i * 137, 100_000 + i * 137),
  );

  it("showBb 關(預設)→ 不畫布林", () => {
    const { container } = render(<CandleChart bars={MANY} />);
    expect(container.querySelector("[data-testid='bb-upper']")).toBeNull();
    expect(container.querySelector("[data-testid='bb-lower']")).toBeNull();
  });

  it("showBb 開 → 上下軌各一條 + 通道填色", () => {
    const { container } = render(<CandleChart bars={MANY} showBb />);
    expect(container.querySelector("[data-testid='bb-upper']")).toBeTruthy();
    expect(container.querySelector("[data-testid='bb-lower']")).toBeTruthy();
    expect(container.querySelector("[data-testid='bb-band']")).toBeTruthy();
  });

  // R9:BB 上下軌常超出 o/h/l/c 值域,y 域沒納入就會被畫到圖框外
  it("上軌超出全域最高價時仍落在圖框內(y 域納入 extraSeries)", () => {
    // 需 ≥21 根才有 2 個以上 band 點(polyline 至少兩點才畫);末根急殺撐大 σ
    const spiky = [
      ...Array.from({ length: 24 }, (_, i) => bar(`2026-02-${String(i + 1).padStart(2, "0")}`, 300_000, 300_000, 300_000, 300_000)),
      bar("2026-02-25", 100_000, 100_000, 100_000, 100_000),
    ];
    const { container } = render(<CandleChart bars={spiky} showBb />);
    const vbH = Number(container.querySelector("svg")!.getAttribute("viewBox")!.split(" ")[3]);
    const upper = container.querySelector("[data-testid='bb-upper']")!;
    const ys = upper.getAttribute("points")!.split(" ").map((p) => Number(p.split(",")[1]));
    for (const y of ys) {
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(vbH);
    }
  });

  it("BB 鈕在圖表頂列,點擊回呼 onToggleBb", () => {
    const calls: boolean[] = [];
    render(<CandleChart bars={MANY} showBb={false} onToggleBb={(v) => calls.push(v)} />);
    const btn = screen.getByRole("button", { name: "BB" });
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(btn);
    expect(calls).toEqual([true]);
  });
});

// ---- round3 T-10b:尺寸 prop regression(同 StockIntradayChart 的理由)----
describe("CandleChart 高度 prop(SC-6 / T-10b)", () => {
  function probe(height?: number) {
    const { container } = render(<CandleChart bars={BARS} height={height} />);
    const svg = container.querySelector("svg")!;
    return {
      viewBox: svg.getAttribute("viewBox"),
      // 取**最低價**那根刻度:它的 y 依賴可用高度。最高價那根恆在 PAD_Y,
      // 拿它比對會兩次都是 4,測試就抓不到「幾何沒重算」。
      lowTickY: [...svg.querySelectorAll("text")]
        .filter((t) => Number(t.getAttribute("x")) === 2)[0]!
        .getAttribute("y"),
    };
  }

  it("高度改變 → viewBox 與刻度 y 座標都跟著變(幾何必須重算)", () => {
    const a = probe(578);
    cleanup();
    const b = probe(900);
    expect(a.viewBox).not.toBe(b.viewBox);
    expect(b.viewBox).toContain("900");
    expect(a.lowTickY).not.toBe(b.lowTickY);
  });

  it("未傳高度時沿用固定常數(既有行為不變)", () => {
    expect(probe().viewBox).toBe("0 0 1400 578");
  });
});

// 🟢 round5 SC-3:視窗高低標(數字與 figcaption 同源 → 縮放後必然同步)
describe("CandleChart 視窗高低標", () => {
  const capOf = (container: HTMLElement): string =>
    container.querySelector("figcaption")!.textContent ?? "";

  it("兩條線 + 價位標,數字等於 figcaption 的高 / 低", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(container.querySelector("[data-testid='window-high']")).toBeTruthy();
    expect(container.querySelector("[data-testid='window-low']")).toBeTruthy();
    expect(screen.getByTestId("window-high-label").textContent).toBe("118");
    expect(screen.getByTestId("window-low-label").textContent).toBe("95");
    expect(capOf(container)).toContain("高 118");
    expect(capOf(container)).toContain("低 95");
  });

  it("滾輪縮放改變可視範圍後,價位標與 figcaption 仍相等", () => {
    const many = Array.from({ length: 300 }, (_, i) =>
      bar(`2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
        100_000 + i, 100_100 + i, 99_900 + i, 100_000 + i),
    );
    const { container } = render(<CandleChart bars={many} initBars={240} />);
    const svg = container.querySelector("svg")!;
    for (let i = 0; i < 5; i += 1) fireEvent.wheel(svg, { deltaY: -100, clientX: 700 });
    const high = screen.getByTestId("window-high-label").textContent!;
    const low = screen.getByTestId("window-low-label").textContent!;
    expect(capOf(container)).toContain(`高 ${high}`);
    expect(capOf(container)).toContain(`低 ${low}`);
  });

  it("無可視 bar → 不渲染", () => {
    const { container } = render(<CandleChart bars={[]} />);
    expect(container.querySelector("[data-testid='window-high']")).toBeNull();
    expect(container.querySelector("[data-testid='window-low']")).toBeNull();
  });
});

describe("CandleChart 量副圖(index-board W-1 pin)", () => {
  const bars = [
    { t: "2026-07-28", o: 100, h: 110, l: 90, c: 105, v: 12 },
    { t: "2026-07-29", o: 105, h: 115, l: 100, c: 112, v: 34 },
  ];

  it("未傳 showVolume → 量柱存在(個股頁既有行為的唯一保護)", () => {
    const { container } = render(<CandleChart bars={bars} />);
    expect(container.querySelectorAll('rect[class*="fill-bull"], rect[class*="fill-bear"]').length)
      .toBeGreaterThan(0);
    expect(screen.queryByText("無量資料")).toBeNull();
  });

  it("showVolume=false → 不畫量柱,改印「無量資料」,資訊列量欄為「—」", () => {
    render(<CandleChart bars={bars} showVolume={false} />);
    expect(screen.getByText("無量資料")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.queryByText("34")).toBeNull();
  });
});

// 🔴 round4 項 1(B-2):視窗高低由橫貫左右的虛線改成標在該根蠟燭上的三角 + 價位文字。
// 現況零測試覆蓋(grep 全 frontend/src,window-high/low 只出現在元件自身)→ 先寫新版紅測試。
describe("CandleChart 視窗高低標記(round4 項 1)", () => {
  function apex(container: HTMLElement, id: string): [number, number] {
    const pts = container.querySelector(`polygon[data-testid="${id}"]`)!.getAttribute("points")!;
    const [x, y] = pts.split(" ")[0]!.split(",").map(Number);
    return [x!, y!];
  }

  it("高低各一個三角標記 + 價位文字,文字與底列 figcaption 同值", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(container.querySelector('polygon[data-testid="window-high"]')).toBeTruthy();
    expect(container.querySelector('polygon[data-testid="window-low"]')).toBeTruthy();
    // BARS 視窗高 118_000 → "118";低 95_000 → "95"
    expect(screen.getByTestId("window-high-label").textContent).toBe("118");
    expect(screen.getByTestId("window-low-label").textContent).toBe("95");
    expect(screen.getByText("高 118")).toBeTruthy();
    expect(screen.getByText("低 95")).toBeTruthy();
  });

  it("不再有橫貫左右的高低虛線(4 3 / 0.8)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const dashed = [...container.querySelectorAll("line")].filter(
      (l) => l.getAttribute("stroke-dasharray") === "4 3",
    );
    expect(dashed.length).toBe(0);
  });

  it("標記落在造成該高 / 低的那一根蠟燭上(取最早出現的)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const bodies = [...container.querySelectorAll("[data-testid='candle-body']")];
    const cxOf = (i: number) => {
      const el = bodies[i]!;
      return Number(el.getAttribute("x")) + Number(el.getAttribute("width")) / 2;
    };
    expect(apex(container, "window-high")[0]).toBeCloseTo(cxOf(2), 5); // 118_000 在第 3 根
    expect(apex(container, "window-low")[0]).toBeCloseTo(cxOf(0), 5); // 95_000 在第 1 根
  });

  it("三角 apex 貼在影線端點(高 = 該根 wickTop、低 = 該根 wickBottom)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const wicks = [...container.querySelectorAll("svg line")].filter(
      (l) => l.getAttribute("stroke-dasharray") === null && l.getAttribute("stroke-width") === "1",
    );
    const highY = apex(container, "window-high")[1];
    const lowY = apex(container, "window-low")[1];
    // 最高點的 y 是全圖最小 y、最低點是最大(價格區內)
    for (const w of wicks) expect(Number(w.getAttribute("y1"))).toBeGreaterThanOrEqual(highY - 0.01);
    for (const w of wicks) expect(Number(w.getAttribute("y2"))).toBeLessThanOrEqual(lowY + 0.01);
  });

  it("三角三個頂點都落在 viewBox 內(body 朝圖內,不被裁)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    for (const id of ["window-high", "window-low"]) {
      const pts = container.querySelector(`polygon[data-testid="${id}"]`)!.getAttribute("points")!;
      for (const p of pts.split(" ")) {
        const [x, y] = p.split(",").map(Number);
        expect(x!).toBeGreaterThanOrEqual(0);
        expect(y!).toBeGreaterThanOrEqual(0);
        expect(y!).toBeLessThanOrEqual(578);
      }
    }
  });

  it("常態(BB 關閉):高標文字翻到三角下方、低標文字翻到三角上方", () => {
    // toY(windowHigh) === PAD_Y === 6 → 文字畫在上方會被裁;
    // toY(windowLow) 貼價格區底 → 文字畫在下方會落進成交量區
    const { container } = render(<CandleChart bars={BARS} />);
    expect(Number(screen.getByTestId("window-high-label").getAttribute("y"))).toBeGreaterThan(
      apex(container, "window-high")[1],
    );
    expect(Number(screen.getByTestId("window-low-label").getAttribute("y"))).toBeLessThan(
      apex(container, "window-low")[1],
    );
  });

  // review F2:分 K 預設 240 根 → slot ≈ 5.8px、首根 cx ≈ 2.9px,而三角半寬 5。
  // 3 根 bar 的 BARS fixture(slot ≈ 466)完全碰不到這條路徑。
  it("窄 slot + 極值落在首 / 末根 → 三角仍完整落在 viewBox 內", () => {
    const many = Array.from({ length: 240 }, (_, i) =>
      // 第 1 根是全場最高、最後一根是全場最低
      bar(
        `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
        100_000,
        i === 0 ? 200_000 : 100_000,
        i === 239 ? 10_000 : 100_000,
        100_000,
      ),
    );
    const { container } = render(<CandleChart bars={many} initBars={240} />);
    for (const id of ["window-high", "window-low"]) {
      const pts = container.querySelector(`polygon[data-testid="${id}"]`)!.getAttribute("points")!;
      for (const p of pts.split(" ")) {
        const x = Number(p.split(",")[0]);
        expect(x).toBeGreaterThanOrEqual(0);
        expect(x).toBeLessThanOrEqual(1400);
      }
    }
  });

  it("平移視窗後標記跟著換根(視窗高低是「當下視野」不是全序列)", () => {
    const many = Array.from({ length: 40 }, (_, i) =>
      bar(`2026-01-${String((i % 28) + 1).padStart(2, "0")}`, 100_000, 100_000 + i * 100, 100_000 - i * 100, 100_000),
    );
    const { container, rerender } = render(<CandleChart bars={many} initBars={10} />);
    // 初始視窗 = 最後 10 根 → 高 = 第 40 根的 h = 103_900
    expect(screen.getByTestId("window-high-label").textContent).toBe("103.9");
    rerender(<CandleChart key="x" bars={many.slice(0, 10)} initBars={10} />);
    cleanup();
    const r2 = render(<CandleChart bars={many.slice(0, 10)} initBars={10} />);
    // 換成前 10 根 → 高 = 第 10 根的 h = 100_900
    expect(screen.getByTestId("window-high-label").textContent).toBe("100.9");
    expect(r2.container.querySelector('polygon[data-testid="window-high"]')).toBeTruthy();
    expect(container).toBeTruthy();
  });
});
