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

  it("超過上限只畫最後 N 根(maxBars)", () => {
    const many = Array.from({ length: 200 }, (_, i) =>
      bar(`2026-01-${String((i % 28) + 1).padStart(2, "0")}`, 100, 100, 100, 100),
    );
    const { container } = render(<CandleChart bars={many} maxBars={120} />);
    expect(container.querySelectorAll("[data-testid='candle-body']").length).toBe(120);
  });

  it("疊 MA5 / MA20:資料足夠時各畫一條 polyline", () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      bar(`2026-01-${String(i + 1).padStart(2, "0")}`, 100_000 + i, 100_000 + i, 100_000 + i, 100_000 + i),
    );
    const { container } = render(<CandleChart bars={many} showMa />);
    expect(container.querySelector("[data-testid='ma-5']")).toBeTruthy();
    expect(container.querySelector("[data-testid='ma-20']")).toBeTruthy();
  });

  it("showMa 關閉時不畫 MA", () => {
    const { container } = render(<CandleChart bars={BARS} />);
    expect(container.querySelector("[data-testid='ma-5']")).toBeNull();
  });

  it("資料不足 20 根時只畫 MA5,不畫 MA20", () => {
    const few = Array.from({ length: 8 }, (_, i) =>
      bar(`2026-01-0${i + 1}`, 100_000, 100_000, 100_000, 100_000),
    );
    const { container } = render(<CandleChart bars={few} showMa />);
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
});
