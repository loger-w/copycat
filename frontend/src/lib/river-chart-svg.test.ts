import { describe, expect, it } from "vitest";

import {
  buildLegGeometry,
  buildOverlayGeometry,
  offsetAtX,
  spreadLabelYs,
  timeTicks,
} from "@/lib/river-chart-svg";
import type { RiverLeg, RiverWindow } from "@/types";

const DAY: RiverWindow = { start_min: 525, end_min: 825 };
const NIGHT: RiverWindow = { start_min: 900, end_min: 1740 };
const SIZE = { width: 300, height: 100 };

function leg(minutes: Record<string, number>, label = "台指"): RiverLeg {
  const offsets = Object.keys(minutes).map(Number);
  const last = offsets.length ? Math.max(...offsets) : null;
  return {
    label,
    minutes,
    last: last === null ? null : minutes[String(last)]!,
    last_minute: last,
  };
}

describe("buildLegGeometry", () => {
  it("x 依 offset 等分於窗寬,y 落在畫布內", () => {
    const g = buildLegGeometry(leg({ "150": 40_646_000, "300": 40_800_000 }), DAY, SIZE);

    expect(g.line.map((p) => p.offset)).toEqual([150, 300]);
    expect(g.line[0]!.x).toBeCloseTo(150, 6); // offset 150 / span 300 × 300px
    expect(g.line[1]!.x).toBeCloseTo(300, 6);
    for (const p of g.line) {
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(SIZE.height);
    }
  });

  it("字串鍵依數值排序(不是字典序)", () => {
    const g = buildLegGeometry(leg({ "9": 100_000, "10": 200_000, "100": 300_000 }), DAY, SIZE);

    expect(g.line.map((p) => p.offset)).toEqual([9, 10, 100]);
  });

  it("pct = 相對窗內第一個有值分鐘", () => {
    const g = buildLegGeometry(leg({ "150": 40_646_000, "300": 40_800_000 }), DAY, SIZE);

    expect(g.first).toBe(40_646_000);
    expect(g.last).toBe(40_800_000);
    expect(g.pct).toBeCloseTo(0.378881, 5);
  });

  it("平盤基準線畫在第一筆的價位上", () => {
    const g = buildLegGeometry(leg({ "150": 40_000_000, "300": 40_400_000 }), DAY, SIZE);

    expect(g.baseY).toBeCloseTo(g.line[0]!.y, 6);
  });

  it("空腿:無線、pct 為 null、不除零", () => {
    const g = buildLegGeometry(leg({}), DAY, SIZE);

    expect(g.line).toEqual([]);
    expect(g.pct).toBeNull();
    expect(g.first).toBeNull();
    expect(Number.isFinite(g.baseY)).toBe(true);
  });

  it("單點腿:退化域不讓 y 飛出畫布", () => {
    const g = buildLegGeometry(leg({ "150": 40_000_000 }), DAY, SIZE);

    expect(g.line).toHaveLength(1);
    expect(g.line[0]!.y).toBeGreaterThanOrEqual(0);
    expect(g.line[0]!.y).toBeLessThanOrEqual(SIZE.height);
    expect(g.pct).toBe(0);
  });

  it("y 刻度含上界 / 基準 / 下界三檔", () => {
    const g = buildLegGeometry(leg({ "150": 40_000_000, "300": 40_400_000 }), DAY, SIZE);

    expect(g.yTicks).toHaveLength(3);
    expect(g.yTicks[0]!.priceMilli).toBeGreaterThan(g.yTicks[2]!.priceMilli);
  });
});

describe("buildOverlayGeometry", () => {
  const entries = [
    { key: "TXF", label: "台指", colorIndex: 0, leg: leg({ "150": 40_000_000, "300": 40_400_000 }) },
    { key: "TWN", label: "富台", colorIndex: 1, leg: leg({ "150": 3_400_000, "300": 3_366_000 }, "富台") },
  ];

  it("各腿都從 0% 起,量級差 12 倍不影響", () => {
    const g = buildOverlayGeometry(entries, DAY, SIZE);

    expect(g.lines.map((l) => l.key)).toEqual(["TXF", "TWN"]);
    expect(g.lines[0]!.pts[0]!.pct).toBe(0);
    expect(g.lines[1]!.pts[0]!.pct).toBe(0);
    expect(g.lines[0]!.pts[1]!.pct).toBeCloseTo(1, 9); // 40.0k → 40.4k = +1%
    expect(g.lines[1]!.pts[1]!.pct).toBeCloseTo(-1, 9); // 3.400k → 3.366k = -1%
  });

  it("漲的腿 y 比跌的腿小(y 軸向下為負)", () => {
    const g = buildOverlayGeometry(entries, DAY, SIZE);

    expect(g.lines[0]!.pts[1]!.y).toBeLessThan(g.lines[1]!.pts[1]!.y);
  });

  it("零線在域內且 pct 域含 0", () => {
    const g = buildOverlayGeometry(entries, DAY, SIZE);

    expect(g.zeroY).toBeGreaterThan(0);
    expect(g.zeroY).toBeLessThan(SIZE.height);
    expect(g.pctDomain[0]).toBeLessThanOrEqual(0);
    expect(g.pctDomain[1]).toBeGreaterThanOrEqual(0);
  });

  it("全窗無值的腿不出現(不畫成 0% 直線)", () => {
    const g = buildOverlayGeometry([...entries, { key: "SXF", label: "費半", colorIndex: 5, leg: leg({}, "費半") }], DAY, SIZE);

    expect(g.lines.map((l) => l.key)).toEqual(["TXF", "TWN"]);
  });

  it("colorIndex 原樣帶出(配色由腿序位決定,不綁 key)", () => {
    const g = buildOverlayGeometry(entries, DAY, SIZE);

    expect(g.lines.map((l) => l.colorIndex)).toEqual([0, 1]);
  });

  it("空清單:零線仍可畫,不除零", () => {
    const g = buildOverlayGeometry([], DAY, SIZE);

    expect(g.lines).toEqual([]);
    expect(Number.isFinite(g.zeroY)).toBe(true);
  });
});

describe("timeTicks", () => {
  it("日盤每小時一格 09:00–13:00", () => {
    expect(timeTicks(DAY)).toEqual([
      { offset: 15, label: "09:00" },
      { offset: 75, label: "10:00" },
      { offset: 135, label: "11:00" },
      { offset: 195, label: "12:00" },
      { offset: 255, label: "13:00" },
    ]);
  });

  it("夜盤每三小時一格,跨午夜標 00:00", () => {
    expect(timeTicks(NIGHT)).toEqual([
      { offset: 0, label: "15:00" },
      { offset: 180, label: "18:00" },
      { offset: 360, label: "21:00" },
      { offset: 540, label: "00:00" },
      { offset: 720, label: "03:00" },
    ]);
  });
});

describe("spreadLabelYs", () => {
  // real-env 截圖發現:六腿收盤價位接近時,右緣腿名互相疊住讀不到(SC-8 要求「右緣印腿名」)
  it("間距足夠時原位不動", () => {
    expect(spreadLabelYs([10, 40, 80], 11, 300)).toEqual([10, 40, 80]);
  });

  it("擠在一起的標籤往下推開到最小間距", () => {
    expect(spreadLabelYs([100, 103, 106], 11, 300)).toEqual([100, 111, 122]);
  });

  it("回傳順序與輸入順序對應(不是排序後的順序)", () => {
    // 依 y 升冪推開:100(idx1)不動 → 103(idx2)推到 111 → 106(idx0)推到 122
    expect(spreadLabelYs([106, 100, 103], 11, 300)).toEqual([122, 100, 111]);
  });

  it("推到底時往上回折,不超出畫布", () => {
    const out = spreadLabelYs([98, 99, 100], 11, 100);
    expect(Math.max(...out)).toBeLessThanOrEqual(100);
    expect(new Set(out).size).toBe(3);
  });

  it("空輸入回空", () => {
    expect(spreadLabelYs([], 11, 300)).toEqual([]);
  });
});

describe("offsetAtX", () => {
  it("兩端對應窗首與窗尾", () => {
    expect(offsetAtX(0, DAY, SIZE)).toBe(0);
    expect(offsetAtX(SIZE.width, DAY, SIZE)).toBe(300);
  });

  it("域外回 null(不 clamp 成端點)", () => {
    expect(offsetAtX(-1, DAY, SIZE)).toBeNull();
    expect(offsetAtX(SIZE.width + 1, DAY, SIZE)).toBeNull();
  });

  it("中間位置四捨五入到最近分鐘", () => {
    expect(offsetAtX(150.4, DAY, SIZE)).toBe(150);
  });
});
