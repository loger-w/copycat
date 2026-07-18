import { describe, expect, it } from "vitest";

import { areaPaths, buildScales, curvePath, splitAtZero } from "@/lib/pnl-svg";

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

describe("areaPaths", () => {
  it("獲利/虧損各自閉合到零線", () => {
    const s = buildScales(CURVE, { width: 100, height: 100, pad: 0 });
    const { profit, loss } = areaPaths(CURVE, s);
    expect(profit).toContain("Z");
    expect(loss).toContain("Z");
    expect(profit).not.toBe(loss);
  });
});
