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

  it("hover 顯示該根 OHLC tooltip;移出清除", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    const svg = container.querySelector("svg")!;
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 5 });
    // jsdom 的 getBoundingClientRect 恆 0 寬 → x=0 落在第一根
    expect(screen.getByTestId("candle-tooltip").textContent).toContain("2026-07-24");
    fireEvent.mouseLeave(svg);
    expect(screen.queryByTestId("candle-tooltip")).toBeNull();
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
