import { describe, expect, it } from "vitest";

import { buildOverlayGeometry, outOfDomainLevels } from "@/lib/index-chart-svg";
import { overlayLines, type StockOverlay } from "@/lib/stock-intraday-svg";

const SIZE = { width: 270, height: 100 };

function minutes(entries: [string, number][]): Record<string, number> {
  return Object.fromEntries(entries);
}

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

describe("outOfDomainLevels(SC-7 域內/域外分類)", () => {
  // 幾何寫字面量,不由已刪的 `buildIndexGeometry` 產:本 describe 要測的是
  // `outOfDomainLevels` 對「域」的分類,域怎麼算出來的與它無關(同源算回來也測不到東西)。
  //
  // 值 = 原 fixture(minutes {"0901": 23_000_000} / ref 23_000_000 / high 23_100_000 /
  // low 22_990_000,SIZE 270×100)經 buildIndexGeometry 的域公式所得:
  //   yTop    = high * 1.003 = 23_100_000 * 1.003 = 23_169_299.999_999_996(浮點,非整數)
  //   yBottom = low  * 0.997 = 22_990_000 * 0.997 = 22_921_030
  //   toY(p)  = (yTop − p) / (yTop − yBottom) * height
  // `toY` 是 `overlayLines`(下面對照組)要的第二欄,一併給。
  const yTop = 23_169_299.999_999_996;
  const yBottom = 22_921_030;
  const g: { yDomain: [number, number]; toY: (p: number) => number } = {
    yDomain: [yBottom, yTop],
    toY: (p) => ((yTop - p) / (yTop - yBottom)) * SIZE.height,
  };
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
