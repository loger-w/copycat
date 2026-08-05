import { describe, expect, it } from "vitest";

import type { VpCell } from "@/lib/stock-accum";
import { PAD_Y, plotWidth, X_LABEL_H } from "@/lib/stock-intraday-svg";
import { buildVpBars, VP_MAX_W_RATIO } from "@/lib/volume-profile";

const WIDTH = 800;

/** 與 `buildIntradayGeometry` 同式的線性 toY(不依賴整份幾何,只給 VP 需要的兩個欄位)。 */
function geom(yBottom: number, yTop: number, height = 256) {
  const plotH = Math.max(1, height - X_LABEL_H - PAD_Y * 2);
  const span = yTop - yBottom;
  const flat = span <= 0;
  return {
    plotH,
    toY: (p: number): number => (flat ? PAD_Y + plotH / 2 : PAD_Y + ((yTop - p) / span) * plotH),
    yDomain: [yBottom, yTop] as [number, number],
  };
}

function cells(entries: [number, number][]): Map<number, VpCell> {
  return new Map(entries.map(([p, t]) => [p, { t, o: t, i: 0 }]));
}

describe("buildVpBars", () => {
  it("空 map → []", () => {
    expect(buildVpBars(new Map(), geom(2_090_000, 2_550_000), WIDTH)).toEqual([]);
  });

  it("域外檔位跳過;全部域外 → []", () => {
    const g = geom(2_300_000, 2_400_000);
    const bars = buildVpBars(cells([[2_200_000, 5], [2_350_000, 5], [2_500_000, 5]]), g, WIDTH);
    expect(bars.map((b) => b.priceMilli)).toEqual([2_350_000]);
    expect(buildVpBars(cells([[2_200_000, 5], [2_500_000, 5]]), g, WIDTH)).toEqual([]);
  });

  it("歸一分母取**域內** max(域縮放後最大的域內 bar 仍為滿寬)", () => {
    const g = geom(2_300_000, 2_400_000);
    // 域外那筆的 t 遠大於域內任何一筆:若拿它當分母,域內全部 bar 會縮成細線
    const bars = buildVpBars(
      cells([[2_500_000, 1000], [2_350_000, 40], [2_360_000, 10]]),
      g,
      WIDTH,
    );
    const full = plotWidth(WIDTH) * VP_MAX_W_RATIO;
    expect(bars.find((b) => b.priceMilli === 2_350_000)?.w).toBeCloseTo(full, 6);
    expect(bars.find((b) => b.priceMilli === 2_360_000)?.w).toBeCloseTo(full * 0.25, 6);
  });

  it("w 上限 = plotWidth(width) × VP_MAX_W_RATIO(0.22)", () => {
    const g = geom(2_300_000, 2_400_000);
    const bars = buildVpBars(cells([[2_350_000, 7], [2_360_000, 3]]), g, WIDTH);
    const max = Math.max(...bars.map((b) => b.w));
    expect(max).toBeCloseTo(plotWidth(WIDTH) * 0.22, 6);
    for (const b of bars) expect(b.w).toBeLessThanOrEqual(plotWidth(WIDTH) * 0.22 + 1e-9);
  });

  it("t 全 0 → w 有限且非 NaN(maxTotal clamp 到 1,禁 0/0)", () => {
    const bars = buildVpBars(cells([[2_350_000, 0], [2_360_000, 0]]), geom(2_300_000, 2_400_000), WIDTH);
    expect(bars.length).toBe(2);
    for (const b of bars) {
      expect(Number.isFinite(b.w)).toBe(true);
      expect(b.w).toBe(0);
      expect(Number.isFinite(b.h)).toBe(true);
    }
  });

  it("輸出依 priceMilli 降冪(穩定 React key)", () => {
    const bars = buildVpBars(
      cells([[2_310_000, 1], [2_390_000, 2], [2_350_000, 3]]),
      geom(2_300_000, 2_400_000),
      WIDTH,
    );
    expect(bars.map((b) => b.priceMilli)).toEqual([2_390_000, 2_350_000, 2_310_000]);
  });

  it("bar 帶原始總張與價位帶頂端 y", () => {
    const g = geom(2_300_000, 2_400_000);
    const bars = buildVpBars(cells([[2_350_000, 42]]), g, WIDTH);
    expect(bars[0]?.total).toBe(42);
    // 價位帶 [p, p + tickOf(p)) 的頂端
    expect(bars[0]?.y).toBeCloseTo(g.toY(2_350_000 + 5_000), 6);
  });

  it("退化域(toY 常數)→ dist 0,h clamp 到 1", () => {
    const g = geom(2_350_000, 2_350_000);
    const bars = buildVpBars(cells([[2_350_000, 5]]), g, WIDTH);
    expect(bars.length).toBe(1);
    expect(bars[0]?.h).toBe(1);
  });

  it("最上緣檔位的價位帶上界 clamp 進 yDomain(不外溢)", () => {
    const g = geom(2_300_000, 2_350_000);
    const bars = buildVpBars(cells([[2_350_000, 5]]), g, WIDTH);
    expect(bars[0]?.y).toBeCloseTo(g.toY(2_350_000), 6);
    expect(bars[0]?.h).toBe(1); // dist = 0 → clamp
  });

  describe("高密度域的縫(R6)", () => {
    it("(a) dist ≈ 1.19px(域 200 檔)→ h ≤ dist 且 ≥ dist × 0.8(相鄰不重疊)", () => {
      // 250 元帶 tick = 0.5 元(500 毫元);200 檔 = 100_000 毫元域寬
      const yBottom = 200_000;
      const yTop = 300_000;
      const g = geom(yBottom, yTop, 260); // plotH = 260 − X_LABEL_H 14 − PAD_Y×2 8 = 238
      expect(g.plotH).toBe(238);
      const dist = (500 / (yTop - yBottom)) * g.plotH;
      expect(dist).toBeCloseTo(1.19, 6);
      const bars = buildVpBars(cells([[250_000, 5], [250_500, 3]]), g, WIDTH);
      for (const b of bars) {
        expect(b.h).toBeLessThanOrEqual(dist);
        expect(b.h).toBeGreaterThanOrEqual(dist * 0.8);
      }
    });

    it("(b) dist < 1px → h === 1(clamp 生效;亞像素重疊為刻意接受的下界)", () => {
      const yBottom = 200_000;
      const yTop = 400_000; // 400 檔
      const g = geom(yBottom, yTop, 256);
      const dist = (500 / (yTop - yBottom)) * g.plotH;
      expect(dist).toBeLessThan(1);
      const bars = buildVpBars(cells([[250_000, 5]]), g, WIDTH);
      expect(bars[0]?.h).toBe(1);
    });
  });
});
