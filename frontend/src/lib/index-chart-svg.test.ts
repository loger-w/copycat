import { describe, expect, it } from "vitest";

import {
  buildIndexGeometry,
  buildOverlayGeometry,
  outOfDomainLevels,
  rightEdgeLabels,
} from "@/lib/index-chart-svg";
import { overlayLines, type OverlayLine, type StockOverlay } from "@/lib/stock-intraday-svg";

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

describe("buildIndexGeometry avgLine(SC-1/2)", () => {
  it("第 k 個已有分鐘的值 = 前 k 個已有分鐘收盤的算術平均(缺分鐘不補值)", () => {
    const g = buildIndexGeometry(
      {
        minutes: minutes([
          ["0901", 43_000_000],
          ["0902", 43_000_200],
          // 0903/0904 缺 —— 不補值,均價只走「已有」分鐘
          ["0905", 43_000_400],
          ["0906", 43_000_800],
        ]),
        ref: 43_000_000,
        high: null,
        low: null,
      },
      SIZE,
    );
    expect(g.avgLine.map((p) => p.p)).toEqual([
      43_000_000, 43_000_100, 43_000_200, 43_000_350,
    ]);
    expect(g.avgLine.map((p) => p.minute)).toEqual(["0901", "0902", "0905", "0906"]);
    // x 與走勢線逐點同源(缺分鐘不佔位)
    expect(g.avgLine.map((p) => p.x)).toEqual(g.line.map((p) => p.x));
    expect(g.avgLine[1]!.y).toBeCloseTo(g.toY(43_000_100), 6);
  });

  it("minutes 空 → avgLine 空陣列", () => {
    const g = buildIndexGeometry({ minutes: {}, ref: 43_000_000, high: null, low: null }, SIZE);
    expect(g.avgLine).toEqual([]);
  });

  it("toY 匯出與 yTicks / refY / yDomain 同源", () => {
    const g = buildIndexGeometry(
      {
        minutes: minutes([["0901", 43_000_000]]),
        ref: 43_634_190,
        high: 43_221_930,
        low: 41_815_780,
      },
      SIZE,
    );
    expect(g.toY(g.yDomain[1])).toBeCloseTo(0, 6);
    expect(g.toY(g.yDomain[0])).toBeCloseTo(SIZE.height, 6);
    expect(g.toY(43_634_190)).toBeCloseTo(g.refY, 6);
    for (const t of g.yTicks) expect(g.toY(t.priceMilli)).toBeCloseTo(t.y, 2);
  });
});

const BOUNDS = { top: 8, bottom: 206 };

function line(level: OverlayLine["level"], y: number): OverlayLine {
  return { y, priceMilli: 23_000_000, level };
}

describe("rightEdgeLabels(決策 6:右緣標籤唯一佈局來源)", () => {
  it("3 項同時貼底 → y 兩兩相距 ≥10 且全在界內", () => {
    const out = rightEdgeLabels({
      ref: null,
      oLines: [],
      outOfDomain: [
        { level: "nl", priceMilli: 22_000_000, dir: "down" },
        { level: "al", priceMilli: 21_000_000, dir: "down" },
        { level: "ma20", priceMilli: 20_000_000, dir: "down" },
      ],
      bounds: BOUNDS,
    });
    expect(out).toHaveLength(3);
    const ys = out.map((l) => l.y).sort((a, b) => a - b);
    expect(ys[1]! - ys[0]!).toBeGreaterThanOrEqual(10);
    expect(ys[2]! - ys[1]!).toBeGreaterThanOrEqual(10);
    for (const y of ys) {
      expect(y).toBeGreaterThanOrEqual(BOUNDS.top);
      expect(y).toBeLessThanOrEqual(BOUNDS.bottom);
    }
  });

  it("8 項(昨收 + 七條域內線)全塞得下", () => {
    const out = rightEdgeLabels({
      ref: { y: 100, text: "昨收 23000" },
      oLines: [
        line("ah", 20),
        line("nh", 40),
        line("cdp", 60),
        line("nl", 130),
        line("al", 150),
        line("ma5", 170),
        line("ma20", 190),
      ],
      outOfDomain: [],
      bounds: BOUNDS,
    });
    expect(out).toHaveLength(8);
    // 互不相撞就不推擠:域內線的 y 原封不動
    expect(
      out.filter((l) => l.kind === "line").map((l) => l.y),
    ).toEqual([20, 40, 60, 130, 150, 170, 190]);
  });

  it("cdp 與昨收同 y±3px → 昨收 y 不動、cdp 被推開", () => {
    const out = rightEdgeLabels({
      ref: { y: 100, text: "昨收 23000" },
      oLines: [line("cdp", 102)],
      outOfDomain: [],
      bounds: BOUNDS,
    });
    const refLabel = out.find((l) => l.kind === "ref");
    const cdpLabel = out.find((l) => l.kind === "line");
    expect(refLabel?.y).toBe(100);
    expect(cdpLabel).toBeTruthy();
    expect(Math.abs(cdpLabel!.y - 100)).toBeGreaterThanOrEqual(10);
  });

  it("容量不足 → 依排序末端優先丟棄", () => {
    const out = rightEdgeLabels({
      ref: null,
      oLines: [line("ah", 10), line("nh", 20), line("cdp", 30)],
      outOfDomain: [],
      // 容量 = floor((25−10)/10)+1 = 2
      bounds: { top: 10, bottom: 25 },
    });
    expect(out).toHaveLength(2);
    expect(out.map((l) => (l.kind === "line" ? l.level : null))).toEqual(["ah", "nh"]);
  });
});

describe("outOfDomainLevels(SC-7 域內/域外分類)", () => {
  const g = buildIndexGeometry(
    {
      minutes: minutes([["0901", 23_000_000]]),
      ref: 23_000_000,
      high: 23_100_000,
      low: 22_990_000,
    },
    SIZE,
  );
  const [yBottom, yTop] = g.yDomain;
  const overlay: StockOverlay = {
    cdp: {
      cdp: 23_050_000,
      ah: yTop + 1_000_000,
      nh: 23_100_000,
      nl: 23_000_000,
      al: yBottom - 1_000_000,
    },
    ma5: 23_020_000,
    ma20: yBottom - 500_000,
    date: "2026-08-13",
  };

  it("域外值 → 掛牌項含正確 dir;域內值只進 overlayLines", () => {
    expect(outOfDomainLevels(overlay, g, { cdp: true, ma: true })).toEqual([
      { level: "ah", priceMilli: yTop + 1_000_000, dir: "up" },
      { level: "al", priceMilli: yBottom - 1_000_000, dir: "down" },
      { level: "ma20", priceMilli: yBottom - 500_000, dir: "down" },
    ]);
    expect(overlayLines(overlay, g, { cdp: true, ma: true }).map((l) => l.level)).toEqual([
      "nh",
      "cdp",
      "nl",
      "ma5",
    ]);
  });

  it("toggle 關的類別不掛牌", () => {
    expect(outOfDomainLevels(overlay, g, { cdp: false, ma: true })).toEqual([
      { level: "ma20", priceMilli: yBottom - 500_000, dir: "down" },
    ]);
    expect(outOfDomainLevels(overlay, g, { cdp: false, ma: false })).toEqual([]);
  });
});
