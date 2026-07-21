import { describe, expect, it } from "vitest";

import type { MinuteAgg } from "@/lib/stock-accum";
import { buildIntradayGeometry, X_END_MIN, X_START_MIN } from "@/lib/stock-intraday-svg";

function minutes(entries: [number, Partial<MinuteAgg>][]): Map<number, MinuteAgg> {
  return new Map(
    entries.map(([k, m]) => [k, { c: 0, v: 0, i: 0, o: 0, u: 0, ...m }]),
  );
}

const META = {
  name: "台積電",
  ref: 2_320_000,
  upper: 2_550_000,
  lower: 2_090_000,
  y_close: 2_320_000,
  y_vol: 100,
};

describe("buildIntradayGeometry", () => {
  it("x domain 固定 09:00–13:30", () => {
    expect(X_START_MIN).toBe(540);
    expect(X_END_MIN).toBe(810);
  });

  it("price line spans minutes and y centers on ref", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }], [541, { c: 2_436_000, v: 2 }]]), meta: META },
      { width: 810 - 540, height: 100 },
    );
    // ref 置中:2320 在 y=50;2436 高於 ref → y < 50
    expect(g.priceLine.length).toBe(2);
    expect(g.priceLine[0]!.y).toBeCloseTo(50, 0);
    expect(g.priceLine[1]!.y).toBeLessThan(50);
    expect(g.refY).toBeCloseTo(50, 0);
    // x:每分鐘 1px(width = 分鐘數)
    expect(g.priceLine[0]!.x).toBeCloseTo(0, 5);
    expect(g.priceLine[1]!.x).toBeCloseTo(1, 5);
  });

  it("volume and energy bars per minute", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          [540, { c: 2_320_000, v: 10, o: 7, i: 3 }],
          [545, { c: 2_330_000, v: 5, o: 1, i: 4 }],
        ]),
        meta: META,
      },
      { width: 270, height: 100 },
    );
    expect(g.volumeBars.length).toBe(2);
    expect(g.volumeBars[0]!.v).toBe(10);
    expect(g.energyBars.length).toBe(2);
    expect(g.energyBars[0]!.outer).toBe(7);
    expect(g.energyBars[0]!.inner).toBe(3);
    // 量 bar 高度正規化:最大分鐘量 = 滿高
    expect(g.volumeBars[0]!.h).toBeGreaterThan(g.volumeBars[1]!.h);
  });

  it("vwap line approximates running average from minutes", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          [540, { c: 2_300_000, v: 10 }],
          [541, { c: 2_400_000, v: 10 }],
        ]),
        meta: META,
      },
      { width: 270, height: 100 },
    );
    expect(g.vwapLine.length).toBe(2);
    // 第二點 running vwap = (2300*10 + 2400*10)/20 = 2350 → 介於兩價之間
    expect(g.vwapLine[1]!.vwap).toBe(2_350_000);
  });

  it("empty minutes yields empty paths without NaN", () => {
    const g = buildIntradayGeometry({ minutes: new Map(), meta: META }, { width: 270, height: 100 });
    expect(g.priceLine).toEqual([]);
    expect(g.vwapLine).toEqual([]);
    expect(Number.isFinite(g.refY)).toBe(true);
  });

  it("meta 缺參考價(null)不產生 NaN", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: { ...META, ref: null, upper: null, lower: null } },
      { width: 270, height: 100 },
    );
    expect(Number.isFinite(g.priceLine[0]!.y)).toBe(true);
  });
});
