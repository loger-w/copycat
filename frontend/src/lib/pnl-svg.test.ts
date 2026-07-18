import { describe, expect, it } from "vitest";

import {
  areaPaths,
  buildScales,
  curvePath,
  interpCurve,
  invertX,
  splitAtZero,
} from "@/lib/pnl-svg";

// 簡單曲線:x 毫點,y NTD。零交叉在 x=43500(y: +100 → -100 的中點)
const CURVE: [number, number][] = [
  [43_000_000, 100],
  [44_000_000, -100],
  [45_000_000, -300],
];

describe("buildScales", () => {
  it("x 映射到繪圖區,y 對稱含零", () => {
    const s = buildScales(CURVE, { width: 100, height: 100, pad: 0 });
    expect(s.x(43_000_000)).toBe(0);
    expect(s.x(45_000_000)).toBe(100);
    expect(s.y(0)).toBe(50); // 對稱 domain → 零線居中
    expect(s.y(300)).toBe(0);
    expect(s.y(-300)).toBe(100);
  });
});

describe("splitAtZero", () => {
  it("在零交叉插入分割點", () => {
    const segs = splitAtZero(CURVE);
    const flat = segs.flat();
    expect(flat).toContainEqual([43_500_000, 0]);
    expect(segs).toHaveLength(2);
    expect(segs[0]?.every(([, y]) => y >= 0)).toBe(true);
    expect(segs[1]?.every(([, y]) => y <= 0)).toBe(true);
  });
});

describe("curvePath", () => {
  it("組出 M/L path", () => {
    const s = buildScales(CURVE, { width: 100, height: 100, pad: 0 });
    expect(curvePath(CURVE, s)).toBe("M0,33.3 L50,66.7 L100,100");
  });
});

describe("invertX", () => {
  const box = { width: 100, height: 100, pad: 10 };

  it("與 buildScales.x 嚴格互逆(DR-2 同源 domain)", () => {
    const s = buildScales(CURVE, box);
    for (const v of [43_000_000, 43_500_000, 44_250_000, 45_000_000]) {
      expect(invertX(s.x(v), CURVE, box)).toBeCloseTo(v, 6);
    }
  });

  it("pad 外像素 → null", () => {
    expect(invertX(5, CURVE, box)).toBeNull();
    expect(invertX(95, CURVE, box)).toBeNull();
  });
});

describe("interpCurve", () => {
  it("線段內線性插值(與後端 payoff.interp_pnl 同語意手算例)", () => {
    expect(interpCurve(CURVE, 43_500_000)).toBeCloseTo(0);
    expect(interpCurve(CURVE, 43_250_000)).toBeCloseTo(50);
    expect(interpCurve(CURVE, 44_500_000)).toBeCloseTo(-200);
    expect(interpCurve(CURVE, 43_000_000)).toBe(100);
    expect(interpCurve(CURVE, 45_000_000)).toBe(-300);
  });

  it("範圍外 → null", () => {
    expect(interpCurve(CURVE, 42_999_999)).toBeNull();
    expect(interpCurve(CURVE, 45_000_001)).toBeNull();
  });
});

describe("areaPaths", () => {
  it("獲利/虧損各自閉合到零線", () => {
    const s = buildScales(CURVE, { width: 100, height: 100, pad: 0 });
    const { profit, loss } = areaPaths(CURVE, s);
    expect(profit).toContain("Z");
    expect(loss).toContain("Z");
    expect(profit).not.toBe(loss);
  });
});
