import { describe, expect, it } from "vitest";

import type { VpCell } from "@/lib/stock-accum";
import { PAD_Y, plotWidth, X_LABEL_H } from "@/lib/stock-intraday-svg";
import { tickOf } from "@/lib/stock-tick";
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

  /** 🔴 review A1/A2/B2(design amendment 2026-08-05):價位帶由「向上一個 tick」
   *  `[p, p + tick)` 改為**以成交價置中** `[p − tick/2, p + tick/2]`。
   *
   *  舊語意有兩個症狀:(a) 整組 bar 相對走勢線上偏半檔;(b) 漲停 / 跌停那一檔的帶
   *  整段落在 y 域外 → clamp 後 dist = 0 → `h` 被 clamp 成 **1px 髮絲**,而鎖停日
   *  量最大的正是那一檔(§0a 鎖板品質的核心觀察對象)反而看不見。
   *
   *  本節下面兩條的舊版斷言(「y = toY(p + tick)」與「最上緣 h === 1」)是
   *  **事前標記為該變**的行為合約更新,不是把紅的斷言改綠。 */
  it("bar 帶原始總張;價位帶以成交價置中(y = toY(p + tick/2))", () => {
    const g = geom(2_300_000, 2_400_000);
    const p = 2_350_000;
    const half = tickOf(p) / 2; // 2500 毫元(≥1000 元帶 tick = 5 元)
    const bars = buildVpBars(cells([[p, 42]]), g, WIDTH);
    const top = g.toY(p + half);
    const bottom = g.toY(p - half);
    expect(bars[0]?.total).toBe(42);
    expect(bars[0]?.y).toBeCloseTo(top, 6);
    expect(bars[0]?.h).toBeCloseTo((bottom - top) * 0.85, 6);
    // 成交價的 y 落在 bar 之內 —— 舊語意下 toY(p) 恰好貼在 bar 的下緣**之外**
    expect(g.toY(p)).toBeGreaterThan(bars[0]!.y);
    expect(g.toY(p)).toBeLessThan(bars[0]!.y + bars[0]!.h);
    // R6 的 0.15 縫全由下緣吃掉(`y = top` 是端點 clamp 所必需,見下兩條)→ 中心與
    // 價線只差半條縫(0.075 × dist),對比舊語意差的是整整半個 tick。
    expect(bars[0]!.y + bars[0]!.h / 2 - g.toY(p)).toBeCloseTo((bottom - top) * 0.075, 6);
  });

  it("退化域(toY 常數)→ dist 0,h clamp 到 1", () => {
    const g = geom(2_350_000, 2_350_000);
    const bars = buildVpBars(cells([[2_350_000, 5]]), g, WIDTH);
    expect(bars.length).toBe(1);
    expect(bars[0]?.h).toBe(1);
  });

  it("最上緣(漲停)檔位:帶的上半 clamp 進域,仍得半帶高(不再是 1px 髮絲)", () => {
    const g = geom(2_300_000, 2_350_000);
    const p = 2_350_000; // = yTop
    const halfBand = g.toY(p - tickOf(p) / 2) - g.toY(p);
    const bars = buildVpBars(cells([[p, 5]]), g, WIDTH);
    expect(bars[0]?.y).toBeCloseTo(g.toY(p), 6); // 不外溢畫布
    expect(bars[0]?.h).toBeCloseTo(halfBand * 0.85, 6);
    expect(bars[0]!.h).toBeGreaterThan(1);
  });

  it("最下緣(跌停)檔位:帶的下半 clamp 進域,同樣得半帶高", () => {
    const g = geom(2_300_000, 2_350_000);
    const p = 2_300_000; // = yBottom
    const halfBand = g.toY(p) - g.toY(p + tickOf(p) / 2);
    const bars = buildVpBars(cells([[p, 5]]), g, WIDTH);
    expect(bars[0]?.y).toBeCloseTo(g.toY(p + tickOf(p) / 2), 6);
    expect(bars[0]?.h).toBeCloseTo(halfBand * 0.85, 6);
    expect(bars[0]!.y + bars[0]!.h).toBeLessThanOrEqual(g.toY(p) + 1e-9);
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
