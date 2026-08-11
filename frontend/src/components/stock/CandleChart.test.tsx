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
describe("CandleChart 視窗高低標(數字與 figcaption 同源)", () => {
  const capOf = (container: HTMLElement): string =>
    container.querySelector("figcaption")!.textContent ?? "";

  it("兩條線 + 價位標,數字等於 figcaption 的高 / 低", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    // round6b:圖案已移除,只剩價位文字
    expect(container.querySelector("[data-testid='window-high-label']")).toBeTruthy();
    expect(container.querySelector("[data-testid='window-low-label']")).toBeTruthy();
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
    expect(container.querySelector("[data-testid='window-high-label']")).toBeNull();
    expect(container.querySelector("[data-testid='window-low-label']")).toBeNull();
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
  /** 🔴 round6b:K 線圖**不再畫任何圖案**(三角 → 空心環 → 只留文字)。
   *  蠟燭圖本身已經把「哪一根是最高」講得很清楚,再加一顆點只是在影線端點上多一塊遮蔽物。
   *  位置語意改由文字的 x 承載(BARS fixture 的 slot ≈ 466px,遠大於 `MARK_LABEL_PAD_X`,
   *  `clampLabelX` 不會觸發 → 文字 x === 該根蠟燭 cx)。 */
  function labelX(id: string): number {
    return Number(screen.getByTestId(`${id}-label`).getAttribute("x"));
  }
  function labelY(id: string): number {
    return Number(screen.getByTestId(`${id}-label`).getAttribute("y"));
  }

  it("只有價位文字、沒有任何圖案;文字與底列 figcaption 同值", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(container.querySelector('circle[data-testid="window-high"]')).toBeNull();
    expect(container.querySelector('polygon[data-testid="window-high"]')).toBeNull();
    expect(container.querySelector('circle[data-testid="window-low"]')).toBeNull();
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
    expect(labelX("window-high")).toBeCloseTo(cxOf(2), 5); // 118_000 在第 3 根
    expect(labelX("window-low")).toBeCloseTo(cxOf(0), 5); // 95_000 在第 1 根
  });

  it("最高點紅字、最低點綠字(round6b:顏色是唯一的方向語意)", () => {
    render(<CandleChart bars={BARS} />);
    expect(screen.getByTestId("window-high-label").getAttribute("class")).toContain("fill-bull");
    expect(screen.getByTestId("window-low-label").getAttribute("class")).toContain("fill-bear");
  });

  it("文字完整落在 viewBox 內(不被上下緣裁掉)", () => {
    render(<CandleChart bars={BARS} />);
    for (const id of ["window-high", "window-low"]) {
      // baseline 扣掉字高(0.625rem ≈ 10px)後仍在域內
      expect(labelY(id) - 10).toBeGreaterThanOrEqual(0);
      expect(labelY(id)).toBeLessThanOrEqual(578);
    }
  });

  it("標記畫在蠟燭 / MA 之後(SC-1.2:被上層蓋住等於沒畫)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const svg = container.querySelector("svg")!;
    const all = [...svg.querySelectorAll("*")];
    const lastBody = all.map((n) => n.getAttribute("data-testid")).lastIndexOf("candle-body");
    const mark = all.map((n) => n.getAttribute("data-testid")).indexOf("window-high-label");
    expect(lastBody).toBeGreaterThanOrEqual(0);
    expect(mark).toBeGreaterThan(lastBody);
  });

  it("常態(BB 關閉):高標文字翻到影線端點下方、低標文字翻到上方", () => {
    // toY(windowHigh) === PAD_Y === 6 → 文字畫在上方會被裁;
    // toY(windowLow) 貼價格區底 → 文字畫在下方會落進成交量區。
    // 圖案已移除,改用影線端點(全圖最小 / 最大 wick y)當參照。
    const { container } = render(<CandleChart bars={BARS} />);
    const wicks = [...container.querySelectorAll("svg line")].filter(
      (l) => l.getAttribute("stroke-dasharray") === null && l.getAttribute("stroke-width") === "1",
    );
    const topY = Math.min(...wicks.map((w) => Number(w.getAttribute("y1"))));
    const bottomY = Math.max(...wicks.map((w) => Number(w.getAttribute("y2"))));
    expect(labelY("window-high")).toBeGreaterThan(topY);
    expect(labelY("window-low")).toBeLessThan(bottomY);
  });

  // 分 K 預設 240 根 → slot ≈ 5.8px、首根 cx ≈ 2.9px。圖案已移除,只剩文字要夾。
  // 3 根 bar 的 BARS fixture(slot ≈ 466)完全碰不到這條路徑。
  it("窄 slot + 極值落在首 / 末根 → 文字仍完整落在 viewBox 內", () => {
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
    render(<CandleChart bars={many} initBars={240} />);
    for (const id of ["window-high", "window-low"]) {
      expect(labelX(id)).toBeGreaterThanOrEqual(0);
      expect(labelX(id)).toBeLessThanOrEqual(1400);
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
    expect(r2.container.querySelector('[data-testid="window-high-label"]')).toBeTruthy();
    expect(container).toBeTruthy();
  });
});

// 🟢 futures-allday SC-7/SC-11:水平 overlay 線(持倉均價 / OI 撐壓)
describe("CandleChart 水平線 overlay(futures-allday SC-7/SC-11)", () => {
  const hlines = (c: HTMLElement) => [...c.querySelectorAll("[data-testid='chart-hline']")];

  it("未傳 hlines → 一條都不畫(個股 / 大盤頁零行為變化)", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(hlines(container).length).toBe(0);
  });

  it("視窗值域內的線畫出來:線 + 標籤 + hover title", () => {
    const { container } = render(
      <CandleChart
        bars={BARS}
        hlines={[
          { priceMilli: 100_000, label: "均 100 多1口", className: "stroke-accent" },
          { priceMilli: 110_000, label: "壓 110", className: "stroke-bear", title: "壓 110・OI 14000口・2026-08-04" },
        ]}
      />,
    );
    const gs = hlines(container);
    expect(gs.length).toBe(2);
    // 線橫貫整個 viewBox 寬,y 落在價格區內
    const line = gs[0]!.querySelector("line")!;
    expect(Number(line.getAttribute("x1"))).toBe(0);
    expect(Number(line.getAttribute("x2"))).toBe(1400);
    expect(Number(line.getAttribute("y1"))).toBeGreaterThan(0);
    expect(line.getAttribute("class")).toContain("stroke-accent");
    // 標籤文字
    expect(screen.getByText("均 100 多1口")).toBeTruthy();
    expect(screen.getByText("壓 110")).toBeTruthy();
    // title 只掛在有帶的那條(SVG hover 提示 = <title> 子節點)
    expect(gs[0]!.querySelector("title")).toBeNull();
    expect(gs[1]!.querySelector("title")!.textContent).toBe("壓 110・OI 14000口・2026-08-04");
  });

  it("超出當前 y 視窗的線不畫(clamp 到邊緣會把圖外價位講成圖緣價位)", () => {
    const { container } = render(
      <CandleChart
        bars={BARS}
        hlines={[
          { priceMilli: 500_000, label: "壓 500", className: "stroke-bear" }, // 遠高於視窗高 118
          { priceMilli: 1_000, label: "撐 1", className: "stroke-bull" }, // 遠低於視窗低 95
          { priceMilli: 105_000, label: "均 105", className: "stroke-accent" },
        ]}
      />,
    );
    expect(hlines(container).length).toBe(1);
    expect(screen.getByText("均 105")).toBeTruthy();
    expect(screen.queryByText("壓 500")).toBeNull();
    expect(screen.queryByText("撐 1")).toBeNull();
  });

  it("無可視 bar → 不畫線(空幾何無值域可言)", () => {
    const { container } = render(
      <CandleChart bars={[]} hlines={[{ priceMilli: 100_000, label: "均 100", className: "stroke-accent" }]} />,
    );
    expect(hlines(container).length).toBe(0);
  });
});

// 🟢 futures-allday SC-8:量區改畫內外盤雙柱
describe("CandleChart 內外盤量副圖(futures-allday SC-8)", () => {
  const DELTA_BARS: Bar[] = [
    { t: "2026-08-05 09:01", o: 100_000, h: 101_000, l: 99_000, c: 100_500, v: 30, uv: 20, dv: 10 },
    { t: "2026-08-05 09:02", o: 100_500, h: 102_000, l: 100_000, c: 101_000, v: 20, uv: 5, dv: 15 },
  ];
  const count = (c: HTMLElement, id: string) => c.querySelectorAll(`[data-testid='${id}']`).length;

  it("未傳 volumeDelta → 既有量柱(個股 / 大盤頁零行為變化)", () => {
    const { container } = render(<CandleChart bars={DELTA_BARS} />);
    expect(count(container, "vol-bar")).toBe(2);
    expect(count(container, "vol-delta-outer")).toBe(0);
    expect(count(container, "vol-delta-inner")).toBe(0);
  });

  it("volumeDelta 但視窗內無 uv/dv(日 K 路徑)→ 回退既有量柱", () => {
    const { container } = render(<CandleChart bars={BARS} volumeDelta />);
    expect(count(container, "vol-bar")).toBe(3);
    expect(count(container, "vol-delta-outer")).toBe(0);
  });

  it("volumeDelta 且有 uv/dv → 每根一組外盤 / 內盤半寬柱,主量柱不並存", () => {
    const { container } = render(<CandleChart bars={DELTA_BARS} volumeDelta />);
    expect(count(container, "vol-bar")).toBe(0);
    expect(count(container, "vol-delta-outer")).toBe(2);
    expect(count(container, "vol-delta-inner")).toBe(2);

    const outer = [...container.querySelectorAll("[data-testid='vol-delta-outer']")];
    const inner = [...container.querySelectorAll("[data-testid='vol-delta-inner']")];
    const h = (el: Element) => Number(el.getAttribute("height"));
    // 第 1 根外盤 20 > 內盤 10;第 2 根內盤 15 > 外盤 5(色與量對得上,不是畫反)
    expect(h(outer[0]!)).toBeGreaterThan(h(inner[0]!));
    expect(h(inner[1]!)).toBeGreaterThan(h(outer[1]!));
    // 歸一分母 = 視窗內 max(uv+dv) = 30 → 第 1 根兩柱高度和 = 量區滿格
    expect(h(outer[0]!) + h(inner[0]!)).toBeGreaterThan(h(outer[1]!) + h(inner[1]!));
    // 外盤紅(bull)、內盤綠(bear)
    expect(outer[0]!.getAttribute("class")).toContain("bull");
    expect(inner[0]!.getAttribute("class")).toContain("bear");
    // 兩根並列在同一根 bar 的半寬上,底邊齊平
    const bottom = (el: Element) => Number(el.getAttribute("y")) + h(el);
    expect(bottom(outer[0]!)).toBeCloseTo(bottom(inner[0]!), 5);
    expect(Number(inner[0]!.getAttribute("x"))).toBeGreaterThan(Number(outer[0]!.getAttribute("x")));
    expect(Number(outer[0]!.getAttribute("width"))).toBeCloseTo(
      Number(inner[0]!.getAttribute("width")),
      5,
    );
  });

  it("showVolume=false 勝過 volumeDelta(無量資料就是無量資料)", () => {
    const { container } = render(<CandleChart bars={DELTA_BARS} volumeDelta showVolume={false} />);
    expect(screen.getByText("無量資料")).toBeTruthy();
    expect(count(container, "vol-delta-outer")).toBe(0);
    expect(count(container, "vol-bar")).toBe(0);
  });
});

// 🟢 characterization(refactor/candlechart-split-hooks 前置):拖曳事件層的既有行為上鎖。
// 這些路徑即將抽進 useCandleViewport / useCandleHover,先拍下當前行為 —— 皆為綠上車,
// 已各以 mutation(改壞 → 紅 → 還原)抽驗非 vacuous。
describe("CandleChart 拖曳既有行為(characterization)", () => {
  const MANY = Array.from({ length: 300 }, (_, i) =>
    bar(
      `2026-07-28 ${String(9 + Math.floor(i / 60)).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}`,
      100_000 + i, 100_100 + i, 99_900 + i, 100_000 + i,
    ),
  );
  const firstStamp = (c: HTMLElement) =>
    c.querySelector("[data-testid='candle-figure']")!.getAttribute("data-first");

  it("拖曳中清除 hover 十字線(拖曳不更新十字線,避免抖動)", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={100} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 700, clientY: 200 });
    expect(container.querySelector("[data-testid='crosshair-h']")).toBeTruthy();
    fireEvent.mouseDown(svg, { clientX: 700, button: 0 });
    fireEvent.mouseMove(window, { clientX: 720 });
    expect(container.querySelector("[data-testid='crosshair-h']")).toBeNull();
    fireEvent.mouseUp(window, { clientX: 720 });
  });

  it("非左鍵 mousedown 不啟動平移", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={100} />);
    const svg = container.querySelector("svg")!;
    const before = firstStamp(container);
    fireEvent.mouseDown(svg, { clientX: 700, button: 2 });
    fireEvent.mouseMove(window, { clientX: 1300 });
    fireEvent.mouseUp(window, { clientX: 1300 });
    expect(firstStamp(container)).toBe(before);
  });

  it("mouseup 後窗口不再跟隨 mousemove(window listener 已卸)", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={100} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseDown(svg, { clientX: 700, button: 0 });
    fireEvent.mouseMove(window, { clientX: 1100 });
    fireEvent.mouseUp(window, { clientX: 1100 });
    const after = firstStamp(container);
    fireEvent.mouseMove(window, { clientX: 100 });
    expect(firstStamp(container)).toBe(after);
  });

  // review TC-1:既有拖曳測試每次拖曳只發一個 mousemove,「絕對位移(以起拖窗口為基準)」
  // 與「逐次累加」在單 move 下不可區分 —— 累加式 mutant 會全綠。連發兩個 move 才釘得住:
  // 拖過左端點(clamp)再拖回,絕對位移不漂移;累加式會停在 clamp 後的位置。
  it("拖曳為絕對位移:同一次拖曳連發 move,拖過左端點再拖回不漂移", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={100} />);
    const svg = container.querySelector("svg")!;
    // 初始 start=200(300 根取末 100);slot = 1400/100 = 14、jsdom rect 寬 0 → scale=1
    fireEvent.mouseDown(svg, { clientX: 100, button: 0 });
    fireEvent.mouseMove(window, { clientX: 4000 }); // Δ=-279 → clamp 到 start=0
    expect(firstStamp(container)).toBe(MANY[0]!.t);
    fireEvent.mouseMove(window, { clientX: 1500 }); // 絕對 Δ=-100 → start=100(累加式停在 0 附近)
    fireEvent.mouseUp(window, { clientX: 1500 });
    expect(firstStamp(container)).toBe(MANY[100]!.t);
    // 第二次拖曳:移出再移回起點 → 完全復位(累加式會殘留第一個 move 的位移)
    fireEvent.mouseDown(svg, { clientX: 700, button: 0 });
    fireEvent.mouseMove(window, { clientX: 1400 });
    fireEvent.mouseMove(window, { clientX: 700 });
    fireEvent.mouseUp(window, { clientX: 700 });
    expect(firstStamp(container)).toBe(MANY[100]!.t);
  });

  // review TC-2:wheel 必須走原生 passive:false listener 且 preventDefault(否則頁面跟著捲)。
  // fireEvent 回傳 dispatchEvent 結果:preventDefault 有被呼叫 → false。
  it("滾輪縮放 preventDefault(原生 passive:false listener,頁面不跟著捲)", () => {
    const { container } = render(<CandleChart bars={MANY} initBars={100} />);
    const svg = container.querySelector("svg")!;
    expect(fireEvent.wheel(svg, { deltaY: 100, clientX: 700, cancelable: true })).toBe(false);
  });
});
