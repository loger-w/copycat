import { describe, expect, it } from "vitest";

import {
  buildLadder,
  snapDown,
  snapUp,
  stepDown,
  stepUp,
  tickOf,
} from "@/lib/stock-tick";

describe("tickOf(毫元)", () => {
  it("各價格段 tick 對齊後端 market.py 表", () => {
    expect(tickOf(5_000)).toBe(10); // <10 元:0.01
    expect(tickOf(10_000)).toBe(50); // 10-50 元:0.05
    expect(tickOf(49_950)).toBe(50);
    expect(tickOf(50_000)).toBe(100); // 50-100 元:0.1
    expect(tickOf(100_000)).toBe(500); // 100-500 元:0.5
    expect(tickOf(500_000)).toBe(1_000); // 500-1000 元:1
    expect(tickOf(1_000_000)).toBe(5_000); // >=1000 元:5
  });
});

describe("stepUp / stepDown 跨級距", () => {
  it("級距內步進", () => {
    expect(stepUp(100_000)).toBe(100_500);
    expect(stepDown(100_500)).toBe(100_000);
  });
  it("跨級距:100 元往下一檔是 99.9 不是 99.5", () => {
    expect(stepDown(100_000)).toBe(99_900);
    expect(stepUp(99_900)).toBe(100_000);
  });
  it("跨級距:50 元往下是 49.95", () => {
    expect(stepDown(50_000)).toBe(49_950);
  });
});

describe("snapUp / snapDown", () => {
  it("非對齊價 snap 到合法 tick", () => {
    expect(snapDown(101_300)).toBe(101_000);
    expect(snapUp(101_300)).toBe(101_500);
  });
  it("已對齊價不動", () => {
    expect(snapDown(101_500)).toBe(101_500);
    expect(snapUp(101_500)).toBe(101_500);
  });
});

describe("buildLadder(固定界錨定)", () => {
  const book = {
    bids: [
      [100_000, 30],
      [99_900, 20],
    ] as [number, number][],
    asks: [
      [100_500, 10],
      [101_000, 40],
    ] as [number, number][],
  };

  it("rows = 上界到下界全域合法 tick、遞減、端點為界", () => {
    const rows = buildLadder({
      center: 100_000,
      ref: 100_000,
      upper: 110_000,
      lower: 90_000,
      book,
    });
    expect(rows[0]!.priceMilli).toBe(110_000);
    expect(rows[rows.length - 1]!.priceMilli).toBe(90_000);
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i]!.priceMilli).toBeLessThan(rows[i - 1]!.priceMilli);
    }
  });

  it("五檔量 exact match 對映、其餘 0", () => {
    const rows = buildLadder({
      center: 100_000,
      ref: 100_000,
      upper: 110_000,
      lower: 90_000,
      book,
    });
    const at = (p: number) => rows.find((r) => r.priceMilli === p)!;
    expect(at(100_000).bidQty).toBe(30);
    expect(at(99_900).bidQty).toBe(20);
    expect(at(100_500).askQty).toBe(10);
    expect(at(102_000).bidQty).toBe(0);
    expect(at(102_000).askQty).toBe(0);
  });

  it("isCenter 標在最接近 center 的價位、dimmed 在 ±5% 外", () => {
    const rows = buildLadder({
      center: 100_000,
      ref: 100_000,
      upper: 110_000,
      lower: 90_000,
      book,
    });
    expect(rows.filter((r) => r.isCenter)).toHaveLength(1);
    expect(rows.find((r) => r.isCenter)!.priceMilli).toBe(100_000);
    expect(rows.find((r) => r.priceMilli === 104_500)!.dimmed).toBe(false);
    expect(rows.find((r) => r.priceMilli === 105_500)!.dimmed).toBe(true);
    expect(rows.find((r) => r.priceMilli === 94_500)!.dimmed).toBe(true);
  });

  it("upper/lower 缺 → 假想界 round-then-snap(ref×1.1 / ×0.9)", () => {
    const rows = buildLadder({
      center: 33_500,
      ref: 33_500,
      upper: null,
      lower: null,
      book: null,
    });
    // 33.5×1.1 = 36.85(float 殘差 36850.000000000004 → round 後 snapDown)
    expect(rows[0]!.priceMilli).toBe(36_850);
    expect(rows[rows.length - 1]!.priceMilli).toBe(30_150);
  });

  it("ref 與 last 皆缺 → 空 rows;book null → 量全 0", () => {
    expect(buildLadder({ center: null, ref: null, upper: null, lower: null, book: null })).toEqual(
      [],
    );
    const rows = buildLadder({
      center: 100_000,
      ref: 100_000,
      upper: 101_000,
      lower: 99_000,
      book: null,
    });
    expect(rows.every((r) => r.bidQty === 0 && r.askQty === 0)).toBe(true);
  });
});
