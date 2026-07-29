import { describe, expect, it } from "vitest";

import { aggregateBars, buildCandleGeometry, movingAverage, type Bar } from "@/lib/candle";

function bar(t: string, o: number, h: number, l: number, c: number, v = 1): Bar {
  return { t, o, h, l, c, v };
}

describe("aggregateBars(1分 → n分;終點標記語意)", () => {
  it("09:01–09:05 併為一根,標記 09:05(amendment P2-14)", () => {
    const out = aggregateBars(
      [
        bar("2026-07-28 09:01", 100, 105, 99, 104, 10),
        bar("2026-07-28 09:02", 104, 108, 103, 106, 5),
        bar("2026-07-28 09:03", 106, 107, 101, 102, 7),
        bar("2026-07-28 09:04", 102, 103, 100, 101, 3),
        bar("2026-07-28 09:05", 101, 110, 101, 109, 9),
      ],
      5,
    );
    expect(out).toEqual([
      { t: "2026-07-28 09:05", o: 100, h: 110, l: 99, c: 109, v: 34 },
    ]);
  });

  it("09:06 進下一桶(標記 09:10),桶界不跨界", () => {
    const out = aggregateBars(
      [
        bar("2026-07-28 09:05", 101, 110, 101, 109, 9),
        bar("2026-07-28 09:06", 109, 112, 108, 111, 4),
      ],
      5,
    );
    expect(out.map((b) => b.t)).toEqual(["2026-07-28 09:05", "2026-07-28 09:10"]);
  });

  it("不足一桶的尾巴照樣成一根(標記為該桶終點,非最後一筆時間)", () => {
    const out = aggregateBars([bar("2026-07-28 09:06", 109, 112, 108, 111, 4)], 5);
    expect(out).toEqual([{ t: "2026-07-28 09:10", o: 109, h: 112, l: 108, c: 111, v: 4 }]);
  });

  it("跨日不合併(同桶號但不同日期)", () => {
    const out = aggregateBars(
      [
        bar("2026-07-28 09:01", 100, 100, 100, 100, 1),
        bar("2026-07-29 09:01", 200, 200, 200, 200, 2),
      ],
      5,
    );
    expect(out.length).toBe(2);
    expect(out.map((b) => b.c)).toEqual([100, 200]);
  });

  it("n=1 原樣回傳(標記不變)", () => {
    const input = [bar("2026-07-28 09:03", 106, 107, 101, 102, 7)];
    expect(aggregateBars(input, 1)).toEqual(input);
  });

  it("空輸入回空陣列", () => {
    expect(aggregateBars([], 5)).toEqual([]);
  });

  it("缺分鐘(無成交)不影響桶歸屬 — 09:02 缺,09:04 仍歸 09:05 桶", () => {
    const out = aggregateBars(
      [bar("2026-07-28 09:01", 100, 100, 100, 100, 1), bar("2026-07-28 09:04", 102, 103, 100, 101, 3)],
      5,
    );
    expect(out.length).toBe(1);
    expect(out[0]!.t).toBe("2026-07-28 09:05");
    expect(out[0]!.o).toBe(100);
    expect(out[0]!.c).toBe(101);
  });
});

describe("movingAverage", () => {
  it("前 n-1 根為 null,第 n 根起為整數均價(毫元整數除法)", () => {
    const bars = [10, 20, 30, 40].map((c, i) => bar(`d${i}`, c, c, c, c));
    expect(movingAverage(bars, 3)).toEqual([null, null, 20, 30]);
  });

  it("資料不足 n 根 → 全 null", () => {
    expect(movingAverage([bar("d0", 1, 1, 1, 1)], 5)).toEqual([null]);
  });
});

describe("buildCandleGeometry", () => {
  const bars = [
    bar("2026-07-27", 100_000, 110_000, 90_000, 105_000, 10),
    bar("2026-07-28", 105_000, 120_000, 100_000, 102_000, 20),
  ];
  const size = { width: 400, height: 200 };

  it("空輸入 → candles 空,不崩", () => {
    const g = buildCandleGeometry([], size);
    expect(g.candles).toEqual([]);
    expect(g.yTicks).toEqual([]);
  });

  it("每根一個 candle,x 由左至右遞增且都落在畫布內", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.candles.length).toBe(2);
    expect(g.candles[0]!.x).toBeLessThan(g.candles[1]!.x);
    for (const c of g.candles) {
      expect(c.x).toBeGreaterThanOrEqual(0);
      expect(c.x + c.w).toBeLessThanOrEqual(size.width);
    }
  });

  it("漲 → dir up(收 > 開)、跌 → dir down", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.candles[0]!.dir).toBe("up"); // 100000 → 105000
    expect(g.candles[1]!.dir).toBe("down"); // 105000 → 102000
  });

  it("開收同價 → dir flat 且 body 仍有最小可見高度", () => {
    const g = buildCandleGeometry([bar("d", 100_000, 110_000, 90_000, 100_000)], size);
    expect(g.candles[0]!.dir).toBe("flat");
    expect(g.candles[0]!.bodyH).toBeGreaterThan(0);
  });

  it("y 軸反向:最高價 y 小於最低價 y", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.toY(120_000)).toBeLessThan(g.toY(90_000));
  });

  it("影線涵蓋 body(wickTop ≤ bodyTop,wickBottom ≥ bodyTop+bodyH)", () => {
    const g = buildCandleGeometry(bars, size);
    for (const c of g.candles) {
      expect(c.wickTop).toBeLessThanOrEqual(c.bodyTop + 0.001);
      expect(c.wickBottom).toBeGreaterThanOrEqual(c.bodyTop + c.bodyH - 0.001);
    }
  });

  it("量 bar 依最大量歸一,x 與蠟燭對齊", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.volBars.length).toBe(2);
    expect(g.volBars[1]!.h).toBeGreaterThan(g.volBars[0]!.h); // 20 > 10
    expect(g.volBars[0]!.x).toBe(g.candles[0]!.x);
  });

  it("全平盤(高=低)不產生除以零", () => {
    const g = buildCandleGeometry([bar("d", 100_000, 100_000, 100_000, 100_000)], size);
    expect(Number.isFinite(g.candles[0]!.bodyTop)).toBe(true);
    expect(Number.isFinite(g.toY(100_000))).toBe(true);
  });

  it("yTicks 價位落在 [low, high] 區間內", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.yTicks.length).toBeGreaterThan(0);
    for (const t of g.yTicks) {
      expect(t.priceMilli).toBeGreaterThanOrEqual(90_000);
      expect(t.priceMilli).toBeLessThanOrEqual(120_000);
    }
  });
});

describe("buildCandleGeometry 密集/異常值韌性(phase5 review)", () => {
  const size = { width: 1400, height: 320 };

  it("bars 極密時蠟燭寬度不超過欄位間距(P1-1:否則橫向重疊)", () => {
    const many = Array.from({ length: 5670 }, (_, i) =>
      bar(`2026-07-28 ${String(i)}`, 100, 101, 99, 100),
    );
    const g = buildCandleGeometry(many, size);
    const slot = size.width / many.length;
    for (const c of g.candles) expect(c.w).toBeLessThanOrEqual(slot + 1e-9);
    // 相鄰蠟燭不重疊
    for (let i = 1; i < 50; i += 1) {
      expect(g.candles[i]!.x).toBeGreaterThanOrEqual(g.candles[i - 1]!.x + g.candles[i - 1]!.w - 1e-9);
    }
  });

  it("open 越界(DK 回 0)時實體仍落在畫布內(P2-8)", () => {
    const g = buildCandleGeometry([bar("d", 0, 110_000, 90_000, 105_000)], size);
    const c = g.candles[0]!;
    expect(c.bodyTop).toBeGreaterThanOrEqual(0);
    expect(c.bodyTop + c.bodyH).toBeLessThanOrEqual(size.height);
  });
});
