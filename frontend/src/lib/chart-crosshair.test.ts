import { describe, expect, it } from "vitest";

import { clampTagX, clampTagY, toSvgPoint } from "@/lib/chart-crosshair";

describe("clampTagY", () => {
  it("中段:標籤垂直置中於 y", () => {
    expect(clampTagY(100, 14, 246)).toBe(93);
  });

  it("貼上緣:不回負值", () => {
    expect(clampTagY(2, 14, 246)).toBe(0);
    expect(clampTagY(-50, 14, 246)).toBe(0);
  });

  it("貼下緣:底邊不超過 plotBottom", () => {
    expect(clampTagY(246, 14, 246)).toBe(232);
    expect(clampTagY(999, 14, 246)).toBe(232);
  });

  it("容器比標籤還小的退化情形回 0,不回負值", () => {
    expect(clampTagY(50, 40, 10)).toBe(0);
  });
});

describe("clampTagX", () => {
  it("中段:標籤水平置中於 x", () => {
    expect(clampTagX(400, 34, 800)).toBe(383);
  });

  it("貼左緣 / 右緣皆夾制", () => {
    expect(clampTagX(2, 34, 800)).toBe(0);
    expect(clampTagX(800, 34, 800)).toBe(766);
  });

  it("width 小於 boxW 的退化情形回 0", () => {
    expect(clampTagX(5, 50, 20)).toBe(0);
  });
});

describe("toSvgPoint", () => {
  it("螢幕座標依 rect/viewBox 比例換算", () => {
    const p = toSvgPoint(
      { clientX: 600, clientY: 130 },
      { left: 0, top: 0, width: 1200, height: 390 },
      { width: 800, height: 260 },
    );
    expect(p.x).toBeCloseTo(400, 6);
    expect(p.y).toBeCloseTo(86.667, 3);
  });

  it("扣掉 rect 位移", () => {
    const p = toSvgPoint(
      { clientX: 100, clientY: 60 },
      { left: 50, top: 10, width: 800, height: 260 },
      { width: 800, height: 260 },
    );
    expect(p.x).toBe(50);
    expect(p.y).toBe(50);
  });

  it("jsdom 恆 0 的 rect → 退回 1:1(測試與真環境同一條路徑)", () => {
    const p = toSvgPoint(
      { clientX: 3, clientY: 100 },
      { left: 0, top: 0, width: 0, height: 0 },
      { width: 800, height: 260 },
    );
    expect(p.x).toBe(3);
    expect(p.y).toBe(100);
  });
});
