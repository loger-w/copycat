import { describe, expect, it } from "vitest";

import { buildIndexGeometry, buildOverlayGeometry } from "@/lib/index-chart-svg";

const SIZE = { width: 270, height: 100 };

function minutes(entries: [string, number][]): Record<string, number> {
  return Object.fromEntries(entries);
}

describe("buildIndexGeometry", () => {
  it("autofit 域含 high/low/ref 並留 pad", () => {
    const g = buildIndexGeometry(
      {
        minutes: minutes([
          ["0901", 43_000_000],
          ["0930", 42_000_000],
        ]),
        ref: 43_634_190,
        high: 43_221_930,
        low: 41_815_780,
      },
      SIZE,
    );
    expect(g.yDomain[0]).toBeLessThan(41_815_780);
    expect(g.yDomain[1]).toBeGreaterThan(43_634_190);
    expect(g.line).toHaveLength(2);
    // 0901 → x=1px(09:00 起每分 1px @ width 270)
    expect(g.line[0]!.x).toBeCloseTo(1, 5);
    expect(Number.isFinite(g.refY)).toBe(true);
    expect(g.yTicks).toHaveLength(3);
  });

  it("空 minutes 不產生 NaN", () => {
    const g = buildIndexGeometry(
      { minutes: {}, ref: 43_000_000, high: null, low: null },
      SIZE,
    );
    expect(g.line).toEqual([]);
    expect(Number.isFinite(g.refY)).toBe(true);
  });

  it("ref null → 以序列均值為基準不炸", () => {
    const g = buildIndexGeometry(
      { minutes: minutes([["0901", 42_000_000]]), ref: null, high: null, low: null },
      SIZE,
    );
    expect(Number.isFinite(g.line[0]!.y)).toBe(true);
  });
});

describe("buildOverlayGeometry", () => {
  it("各線相對各自 ref 的 % 共域,含 zeroY", () => {
    const g = buildOverlayGeometry(
      [
        { minutes: minutes([["0901", 43_634_190], ["0930", 42_000_000]]), ref: 43_634_190 },
        { minutes: minutes([["0901", 378_090], ["0930", 359_800]]), ref: 378_090 },
      ],
      SIZE,
    );
    expect(g.lines).toHaveLength(2);
    // 第一點皆為 0%
    expect(g.lines[0]!.pts[0]!.pct).toBeCloseTo(0, 5);
    expect(g.lines[1]!.pts[0]!.pct).toBeCloseTo(0, 5);
    // 櫃買跌幅較深 → 末點 pct 較低
    expect(g.lines[1]!.pts[1]!.pct).toBeLessThan(g.lines[0]!.pts[1]!.pct);
    expect(Number.isFinite(g.zeroY)).toBe(true);
    expect(g.pctDomain[0]).toBeLessThan(g.pctDomain[1]);
  });

  it("ref null 的線被略過", () => {
    const g = buildOverlayGeometry(
      [
        { minutes: minutes([["0901", 100]]), ref: null },
        { minutes: minutes([["0901", 378_090]]), ref: 378_090 },
      ],
      SIZE,
    );
    expect(g.lines).toHaveLength(1);
  });
});
