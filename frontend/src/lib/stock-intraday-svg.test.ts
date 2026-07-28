import { describe, expect, it } from "vitest";

import type { MinuteAgg } from "@/lib/stock-accum";
import { buildIntradayGeometry, overlayLines, X_END_MIN, X_START_MIN } from "@/lib/stock-intraday-svg";

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

  it("price line spans minutes;有漲跌停 → 漲跌停域(SC-2,該變:原 ref 置中斷言)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }], [541, { c: 2_436_000, v: 2 }]]), meta: META },
      { width: 810 - 540, height: 100 },
    );
    expect(g.priceLine.length).toBe(2);
    // 漲跌停域:yTop = upper×1.02、yBottom = lower×0.98(design v2 SC-2)
    expect(g.yDomain[1]).toBeCloseTo(2_550_000 * 1.02, 3);
    expect(g.yDomain[0]).toBeCloseTo(2_090_000 * 0.98, 3);
    expect(g.priceLine[1]!.y).toBeLessThan(g.priceLine[0]!.y);
    // 漲跌停線恆在域內(貼近上下緣)
    expect(g.upperY).not.toBeNull();
    expect(g.lowerY).not.toBeNull();
    expect(g.upperY!).toBeGreaterThan(0);
    expect(g.lowerY!).toBeLessThan(100);
    // x:每分鐘 1px(width = 分鐘數)
    expect(g.priceLine[0]!.x).toBeCloseTo(0, 5);
    expect(g.priceLine[1]!.x).toBeCloseTo(1, 5);
  });

  it("upper/lower 缺 → 沿用對稱 autofit 域(edge 1)", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([[540, { c: 2_320_000, v: 1 }], [541, { c: 2_436_000, v: 2 }]]),
        meta: { ...META, upper: null, lower: null },
      },
      { width: 270, height: 100 },
    );
    // 對稱域:以 ref 為中心
    const [lo, hi] = g.yDomain;
    expect((lo + hi) / 2).toBeCloseTo(2_320_000, -2);
  });

  it("yTicks:有漲跌停 → 5 點(端點+昨收+snap 中點)含 pct;缺 → 3 點 pct null(SC-2)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );
    expect(g.yTicks).toHaveLength(5);
    expect(g.yTicks[0]!.priceMilli).toBe(2_090_000);
    expect(g.yTicks[2]!.priceMilli).toBe(2_320_000);
    expect(g.yTicks[4]!.priceMilli).toBe(2_550_000);
    expect(g.yTicks[0]!.pct).toBeCloseTo(-9.9, 1);
    expect(g.yTicks[2]!.pct).toBe(0);
    // 中點 snap 到合法 tick(2435 已對齊 5 元 tick)
    expect(g.yTicks[3]!.priceMilli % 5_000).toBe(0);

    const g2 = buildIntradayGeometry(
      {
        minutes: minutes([[540, { c: 2_320_000, v: 1 }]]),
        meta: { ...META, upper: null, lower: null },
      },
      { width: 270, height: 100 },
    );
    expect(g2.yTicks).toHaveLength(3);
    expect(g2.yTicks.every((t) => t.pct === null)).toBe(true);
  });

  it("minuteOf:bucket 有資料回分鐘、無資料回 null(SC-1/R6)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }], [600, { c: 2_330_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );
    expect(g.minuteOf(0)).toBe(540); // x=0 → 09:00
    expect(g.minuteOf(60)).toBe(600); // x=60px → 10:00(width=270 → 1px/分)
    expect(g.minuteOf(30)).toBeNull(); // 09:30 無資料
    expect(g.minuteOf(-5)).toBeNull();
    expect(g.minuteOf(999)).toBeNull();
  });

  it("volume bar dir:比前一有效分鐘 c(首分鐘 flat)(SC-3)", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          [540, { c: 2_320_000, v: 1 }],
          [541, { c: 2_330_000, v: 1 }],
          [542, { c: 2_310_000, v: 1 }],
          [543, { c: 2_310_000, v: 1 }],
        ]),
        meta: META,
      },
      { width: 270, height: 100 },
    );
    expect(g.volumeBars.map((b) => b.dir)).toEqual(["flat", "up", "down", "flat"]);
  });

  it("overlayLines:域內才給、含 label 與 kind(SC-4)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );
    const overlay = {
      cdp: { cdp: 2_320_000, ah: 2_400_000, nh: 2_360_000, nl: 2_280_000, al: 2_240_000 },
      ma5: 2_330_000,
      ma20: 9_999_000, // 域外 → 不給
      date: "2026-07-25",
    };
    const lines = overlayLines(overlay, g, { cdp: true, ma: true });
    const labels = lines.map((l) => l.label);
    expect(labels).toContain("CDP");
    expect(labels).toContain("AH");
    expect(labels).toContain("MA5");
    expect(labels).not.toContain("MA20");
    expect(lines.every((l) => l.y >= 0 && l.y <= 100)).toBe(true);
    // toggle 關 → 不給該類
    expect(overlayLines(overlay, g, { cdp: false, ma: true }).map((l) => l.kind)).not.toContain(
      "cdp",
    );
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
