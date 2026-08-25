import { describe, expect, it } from "vitest";

import type { IndexSeries } from "@/hooks/useIndexStream";
import { buildIndexOverlayLines } from "@/lib/index-overlay-lines";
import { minuteToX, SPOT_WINDOW, STKFUT_WINDOW } from "@/lib/stock-intraday-svg";

function series(minutes: Record<string, number>, ref: number | null = 20_000_000): IndexSeries {
  return { p: null, ref, high: null, low: null, stale: false, minutes };
}

/** toY 取恆等(y = 毫元),斷言直接讀「映射到個股軸的價格」;域給得很寬,域外案例另開 */
const g = { toY: (priceMilli: number) => priceMilli, yDomain: [0, 1_000_000_000] as [number, number] };
const W = 640;

describe("buildIndexOverlayLines(指數相對昨收 % → 個股價格軸)", () => {
  it("指數 +1% 映到個股昨收 × 1.01;末點 % 給右緣標籤", () => {
    const lines = buildIndexOverlayLines(
      { twse: series({ "0901": 20_100_000, "0902": 20_200_000 }), otc: null },
      { twse: true, otc: true },
      100_000, // 個股昨收 100 元
      g,
      W,
      SPOT_WINDOW,
    );
    expect(lines).toHaveLength(1);
    const twse = lines[0]!;
    expect(twse.key).toBe("twse");
    expect(twse.pts.map((p) => p.y)).toEqual([100_500, 101_000]);
    expect(twse.pts[0]!.x).toBe(minuteToX(9 * 60 + 1, W, SPOT_WINDOW));
    expect(twse.lastPct).toBeCloseTo(1, 6);
  });

  it("toggle 關的那條不畫;兩條都開時順序恆為 加權、櫃買", () => {
    const both = { twse: series({ "0901": 20_100_000 }), otc: series({ "0901": 250_000 }, 250_000) };
    expect(buildIndexOverlayLines(both, { twse: false, otc: true }, 100_000, g, W, SPOT_WINDOW).map((l) => l.key)).toEqual(["otc"]);
    expect(buildIndexOverlayLines(both, { twse: true, otc: true }, 100_000, g, W, SPOT_WINDOW).map((l) => l.key)).toEqual(["twse", "otc"]);
  });

  it("個股沒昨收(null / 0)→ 全部不畫;指數沒昨收 → 只那一條不畫", () => {
    const both = { twse: series({ "0901": 20_100_000 }, null), otc: series({ "0901": 251_000 }, 250_000) };
    expect(buildIndexOverlayLines(both, { twse: true, otc: true }, null, g, W, SPOT_WINDOW)).toEqual([]);
    expect(buildIndexOverlayLines(both, { twse: true, otc: true }, 0, g, W, SPOT_WINDOW)).toEqual([]);
    expect(buildIndexOverlayLines(both, { twse: true, otc: true }, 100_000, g, W, SPOT_WINDOW).map((l) => l.key)).toEqual(["otc"]);
  });

  it("窗外分鐘、0 值、壞 key 剔除;點依分鐘升冪", () => {
    const lines = buildIndexOverlayLines(
      { twse: series({ "0903": 20_300_000, "0901": 20_100_000, "0830": 20_000_000, "1400": 20_000_000, "0902": 0, xx: 1 }), otc: null },
      { twse: true, otc: false },
      100_000,
      g,
      W,
      SPOT_WINDOW,
    );
    expect(lines[0]!.pts.map((p) => p.y)).toEqual([100_500, 101_500]);
  });

  it("域外點剔除(review F-05):對稱域 ±1.1% 時 +2% 的指數點不畫、末點 % 取最後一個域內點", () => {
    const narrow = { toY: (p: number) => p, yDomain: [98_900, 101_100] as [number, number] };
    const lines = buildIndexOverlayLines(
      { twse: series({ "0901": 20_100_000, "0902": 20_400_000, "0903": 20_200_000 }), otc: null },
      { twse: true, otc: false },
      100_000,
      narrow,
      W,
      SPOT_WINDOW,
    );
    expect(lines[0]!.pts.map((p) => p.y)).toEqual([100_500, 101_000]); // 102_000 域外剔除
    expect(lines[0]!.lastPct).toBeCloseTo(1, 6); // 末點 = 0903 的 +1%,不是被剔掉的 0902
    // 全部域外 → 整條不畫
    expect(
      buildIndexOverlayLines({ twse: series({ "0902": 20_400_000 }), otc: null }, { twse: true, otc: false }, 100_000, narrow, W, SPOT_WINDOW),
    ).toEqual([]);
  });

  it("x 隨 xw 走(review F-16):同一分鐘在 STKFUT_WINDOW 下 x 不同於 SPOT_WINDOW", () => {
    const s = { twse: series({ "0901": 20_100_000 }), otc: null };
    const spot = buildIndexOverlayLines(s, { twse: true, otc: false }, 100_000, g, W, SPOT_WINDOW)[0]!.pts[0]!.x;
    const stkfut = buildIndexOverlayLines(s, { twse: true, otc: false }, 100_000, g, W, STKFUT_WINDOW)[0]!.pts[0]!.x;
    expect(stkfut).toBe(minuteToX(9 * 60 + 1, W, STKFUT_WINDOW));
    expect(stkfut).not.toBe(spot);
  });

  it("NaN 昨收當作沒有基準(review F-16):個股 NaN → 全不畫;指數 NaN → 該線不畫", () => {
    const both = { twse: series({ "0901": 20_100_000 }, Number.NaN), otc: series({ "0901": 251_000 }, 250_000) };
    expect(buildIndexOverlayLines(both, { twse: true, otc: true }, Number.NaN, g, W, SPOT_WINDOW)).toEqual([]);
    expect(buildIndexOverlayLines(both, { twse: true, otc: true }, 100_000, g, W, SPOT_WINDOW).map((l) => l.key)).toEqual(["otc"]);
  });

  it("stale 旗標帶到線上(review F-09)", () => {
    const st: IndexSeries = { ...series({ "0901": 20_100_000 }), stale: true };
    expect(buildIndexOverlayLines({ twse: st, otc: null }, { twse: true, otc: false }, 100_000, g, W, SPOT_WINDOW)[0]!.stale).toBe(true);
  });

  it("series 為 null 或該指數全無分鐘 → 空", () => {
    expect(buildIndexOverlayLines(null, { twse: true, otc: true }, 100_000, g, W, SPOT_WINDOW)).toEqual([]);
    expect(buildIndexOverlayLines({ twse: series({}), otc: null }, { twse: true, otc: true }, 100_000, g, W, SPOT_WINDOW)).toEqual([]);
  });
});
