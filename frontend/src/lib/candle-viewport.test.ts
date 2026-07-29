import { describe, expect, it } from "vitest";

import {
  clampViewport,
  initialViewport,
  MAX_VISIBLE,
  MIN_BARS,
  onTotalChange,
  panBy,
  zoomAt,
} from "@/lib/candle-viewport";

describe("clampViewport", () => {
  it("count 上限 = min(total, MAX_VISIBLE)", () => {
    expect(clampViewport({ start: 0, count: 9999 }, 5000).count).toBe(MAX_VISIBLE);
    expect(clampViewport({ start: 0, count: 9999 }, 300).count).toBe(300);
  });

  it("count 下限 = MIN_BARS(資料足夠時)", () => {
    expect(clampViewport({ start: 0, count: 3 }, 500).count).toBe(MIN_BARS);
  });

  // R31:2–8 根正是既有元件測試的常態,夾制次序寫反會得到 count > total 與負的 start
  it("total < MIN_BARS 時不強拉:count = total、start = 0", () => {
    for (const total of [1, 2, 3, 8, 19]) {
      const vp = clampViewport({ start: 0, count: 240 }, total);
      expect(vp.count).toBe(total);
      expect(vp.start).toBe(0);
    }
  });

  it("total = 0 → 空窗口,不回負值", () => {
    expect(clampViewport({ start: 5, count: 240 }, 0)).toEqual({ start: 0, count: 0 });
  });

  it("start 夾在 [0, total − count]", () => {
    expect(clampViewport({ start: -10, count: 50 }, 500).start).toBe(0);
    expect(clampViewport({ start: 9999, count: 50 }, 500).start).toBe(450);
  });
});

describe("initialViewport", () => {
  it("貼右緣顯示最後 initBars 根", () => {
    expect(initialViewport(5900, 240)).toEqual({ start: 5660, count: 240 });
  });

  it("資料少於 initBars → 全顯示", () => {
    expect(initialViewport(80, 240)).toEqual({ start: 0, count: 80 });
  });

  it("資料少於 MIN_BARS 也不崩", () => {
    expect(initialViewport(3, 120)).toEqual({ start: 0, count: 3 });
  });
});

describe("zoomAt", () => {
  const total = 2000;

  it("錨點守恆:游標所指的 bar 在縮放前後落在同一比例位置", () => {
    const vp = { start: 800, count: 400 };
    const r = 0.25; // 游標指向 index 800 + 100 = 900
    const anchorBefore = vp.start + r * vp.count;
    for (const factor of [0.5, 0.8, 1.25, 2]) {
      const next = zoomAt(vp, total, factor, r);
      const anchorAfter = next.start + r * next.count;
      expect(Math.abs(anchorAfter - anchorBefore)).toBeLessThanOrEqual(1);
    }
  });

  it("factor > 1 看更多根、factor < 1 看更少根(未撞上下限時)", () => {
    const vp = { start: 800, count: 200 };
    expect(zoomAt(vp, total, 2, 0.5).count).toBe(400);
    expect(zoomAt(vp, total, 0.5, 0.5).count).toBe(100);
  });

  // 這條是 zoomAt 曾經真的錯過的地方:用未夾制的 count 去推 start,撞上限時錨點漂 25 根
  it("錨點守恆在撞 MAX_VISIBLE 上限時仍成立", () => {
    const vp = { start: 800, count: 400 };
    const r = 0.25;
    const next = zoomAt(vp, total, 2, r); // 400×2 = 800 → 夾到 700
    expect(next.count).toBe(MAX_VISIBLE);
    expect(Math.abs(next.start + r * next.count - (vp.start + r * vp.count))).toBeLessThanOrEqual(1);
  });

  it("縮小到底夾在 min(total, MAX_VISIBLE)", () => {
    expect(zoomAt({ start: 0, count: 600 }, 5000, 10, 0.5).count).toBe(MAX_VISIBLE);
  });

  it("放大到底夾在 MIN_BARS", () => {
    expect(zoomAt({ start: 800, count: 400 }, total, 0.01, 0.5).count).toBe(MIN_BARS);
  });

  it("anchorRatio 超界自動夾到 [0,1]", () => {
    expect(zoomAt({ start: 800, count: 400 }, total, 0.5, 5).start).toBe(
      zoomAt({ start: 800, count: 400 }, total, 0.5, 1).start,
    );
  });

  it("total = 0 不崩", () => {
    expect(zoomAt({ start: 0, count: 0 }, 0, 2, 0.5)).toEqual({ start: 0, count: 0 });
  });
});

describe("panBy", () => {
  it("往左往右都移動 count 不變", () => {
    expect(panBy({ start: 500, count: 200 }, 2000, -100)).toEqual({ start: 400, count: 200 });
    expect(panBy({ start: 500, count: 200 }, 2000, 100)).toEqual({ start: 600, count: 200 });
  });

  it("拖到左端點即停,不空捲", () => {
    expect(panBy({ start: 50, count: 200 }, 2000, -999).start).toBe(0);
  });

  it("拖到右端點即停,不空捲", () => {
    expect(panBy({ start: 1000, count: 200 }, 2000, 9999).start).toBe(1800);
  });
});

describe("onTotalChange", () => {
  // R10:無條件貼右緣會讓盤中平移最多 60 秒就被 refetchInterval 拉回
  it("原本貼右緣 → 跟進新資料(仍貼右緣)", () => {
    const vp = { start: 1800, count: 200 }; // 1800+200 = 2000 = prevTotal
    expect(onTotalChange(vp, 2000, 2050)).toEqual({ start: 1850, count: 200 });
  });

  it("原本已平移到左邊 → start 不動,不被拉回右緣", () => {
    const vp = { start: 300, count: 200 };
    expect(onTotalChange(vp, 2000, 2050)).toEqual({ start: 300, count: 200 });
  });

  it("資料變少(異常回傳)仍夾制在合法範圍", () => {
    const vp = { start: 1800, count: 200 };
    const next = onTotalChange(vp, 2000, 100);
    expect(next.start).toBe(0);
    expect(next.count).toBe(100);
  });
});
