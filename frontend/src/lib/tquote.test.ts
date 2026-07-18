import { describe, expect, it } from "vitest";

import {
  atmBoundaryIndex,
  buildTQuoteRows,
  energyWidth,
  maxAbsNetQty,
  outerRatio,
} from "@/lib/tquote";
import type { ContractRow } from "@/types";

function row(over: Partial<ContractRow> & { cp: "C" | "P"; strike: number }): ContractRow {
  return {
    symbol: `TC.O.TWF.TX4.202607.${over.cp}.${over.strike}`,
    net_qty: 0,
    volume: 0,
    outer_qty: 0,
    inner_qty: 0,
    ...over,
  };
}

const C44 = row({ cp: "C", strike: 44000, net_qty: 1, volume: 6, outer_qty: 2, inner_qty: 1 });
const P44 = row({ cp: "P", strike: 44000, net_qty: -4, volume: 4, outer_qty: 0, inner_qty: 4 });
const C45 = row({ cp: "C", strike: 45000, net_qty: -28, volume: 96, outer_qty: 31, inner_qty: 59 });

describe("buildTQuoteRows", () => {
  it("依 strike 配對 C/P、降冪排列(高履約價在上)", () => {
    const rows = buildTQuoteRows([C44, P44, C45]);
    expect(rows.map((r) => r.strike)).toEqual([45000, 44000]);
    expect(rows[0]?.call).toEqual(C45);
    expect(rows[0]?.put).toBeNull();
    expect(rows[1]?.call).toEqual(C44);
    expect(rows[1]?.put).toEqual(P44);
  });

  it("兩側皆零成交的履約價不入列", () => {
    const dead = row({ cp: "C", strike: 43000 });
    const deadPut = row({ cp: "P", strike: 43000 });
    expect(buildTQuoteRows([dead, deadPut, C44])).toHaveLength(1);
  });

  it("空輸入回空陣列", () => {
    expect(buildTQuoteRows([])).toEqual([]);
  });
});

describe("outerRatio", () => {
  it("外盤 /(外盤+內盤)", () => {
    expect(outerRatio(C44)).toBeCloseTo(2 / 3);
    expect(outerRatio(P44)).toBe(0);
  });

  it("分母 0 → null(全未分類)", () => {
    expect(outerRatio(row({ cp: "C", strike: 44000, volume: 5 }))).toBeNull();
  });
});

describe("maxAbsNetQty / energyWidth", () => {
  it("全表兩側 |net_qty| 最大值", () => {
    const rows = buildTQuoteRows([C44, P44, C45]);
    expect(maxAbsNetQty(rows)).toBe(28);
  });

  it("空表 → 0;maxAbs=0 → energyWidth null", () => {
    expect(maxAbsNetQty([])).toBe(0);
    expect(energyWidth(5, 0)).toBeNull();
  });

  it("寬度 = |net|/maxAbs", () => {
    expect(energyWidth(-4, 28)).toBeCloseTo(4 / 28);
    expect(energyWidth(28, 28)).toBe(1);
  });
});

describe("atmBoundaryIndex", () => {
  const rows = buildTQuoteRows([
    C45,
    C44,
    P44,
    row({ cp: "P", strike: 43000, net_qty: 2, volume: 3, outer_qty: 2, inner_qty: 1 }),
  ]); // strikes 降冪 [45000, 44000, 43000]

  it("spot 介於相鄰列之間 → 上方列 index", () => {
    expect(atmBoundaryIndex(rows, 44500)).toBe(0);
    expect(atmBoundaryIndex(rows, 43200)).toBe(1);
  });

  it("等於邊界 strike 取首個符合區間", () => {
    expect(atmBoundaryIndex(rows, 44000)).toBe(0);
  });

  it("spot null / 範圍外 / 列數不足 → null(DR-8)", () => {
    expect(atmBoundaryIndex(rows, null)).toBeNull();
    expect(atmBoundaryIndex(rows, 46000)).toBeNull();
    expect(atmBoundaryIndex(rows, 42000)).toBeNull();
    expect(atmBoundaryIndex(rows.slice(0, 1), 44500)).toBeNull();
  });
});
