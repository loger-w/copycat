import { describe, expect, it } from "vitest";

import {
  aggregateBars,
  buildCandleGeometry,
  hlineYOf,
  movingAverage,
  type Bar,
} from "@/lib/candle";
import { snapNearest } from "@/lib/stock-tick";

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

// 🔵 R2a:priceAtY 是 toY 的逆函數,SC-7 的「左緣顯示滑鼠所在價位」全靠它。
// round-trip 是唯一能抓到「公式與 toY 不同步」的測試(中間點永遠正確,只有兩端偏移)。
describe("buildCandleGeometry.priceAtY(R2a)", () => {
  const size = { width: 400, height: 200 };
  const bars = [
    bar("2026-07-27", 100_000, 110_000, 90_000, 105_000, 10),
    bar("2026-07-28", 105_000, 120_000, 100_000, 102_000, 20),
  ];

  it("round-trip:域內價位經 toY 再 priceAtY 回到原值(±1 毫元)", () => {
    const g = buildCandleGeometry(bars, size);
    for (const p of [90_000, 97_500, 105_000, 112_500, 120_000]) {
      expect(Math.abs(g.priceAtY(g.toY(p)) - p)).toBeLessThanOrEqual(1);
    }
  });

  it("底部量區的 y 被夾制在 lo,不產生低於最低價或負數的價位", () => {
    const g = buildCandleGeometry(bars, size);
    // 量區在 priceBottom 之下,一路到 size.height 都不該反演出 < lo
    for (const y of [size.height - 20, size.height, size.height * 2]) {
      expect(g.priceAtY(y)).toBe(90_000);
    }
  });

  it("上緣越界夾制在 hi", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.priceAtY(-50)).toBe(120_000);
  });

  it("全平盤(span=0)回 hi,不產生 NaN/Infinity", () => {
    const g = buildCandleGeometry([bar("d", 100_000, 100_000, 100_000, 100_000)], size);
    expect(g.priceAtY(10)).toBe(100_000);
    expect(Number.isFinite(g.priceAtY(150))).toBe(true);
  });

  it("空幾何有 priceAtY 可呼叫(不是 undefined)", () => {
    const g = buildCandleGeometry([], size);
    expect(typeof g.priceAtY).toBe("function");
    expect(g.priceAtY(50)).toBe(0);
  });
});

describe("buildCandleGeometry.indexOf(右緣邊界)", () => {
  const size = { width: 400, height: 200 };
  const bars = Array.from({ length: 10 }, (_, i) =>
    bar(`2026-07-28 ${String(i)}`, 100_000, 110_000, 90_000, 105_000, 10),
  );

  it("最右像素(x === width)對應最後一根,不是 null", () => {
    // slot = width / bars.length 整除 → floor(width/slot) === bars.length 被濾成 null,
    // 最右一個像素 hover 失去十字線(next-time 2026-07-29)
    const g = buildCandleGeometry(bars, size);
    expect(g.indexOf(size.width)).toBe(bars.length - 1);
  });

  it("超出右緣仍回 null", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.indexOf(size.width + 0.1)).toBe(null);
  });

  it("左緣與右緣內側不受影響", () => {
    const g = buildCandleGeometry(bars, size);
    expect(g.indexOf(0)).toBe(0);
    expect(g.indexOf(size.width - 0.1)).toBe(bars.length - 1);
  });

  it("0 ≤ x < width 的內部映射逐點不變(白名單只放行 x === width)", () => {
    // 右緣修法是「只多放行最右那一個像素」。若哪天改成整體位移(例如 round 取代
    // floor),下面每個槽的頭尾都會挪一格,而既有三條端點測試只釘得住兩端。
    const g = buildCandleGeometry(bars, size);
    const slot = size.width / bars.length;
    for (let i = 0; i < bars.length; i += 1) {
      expect(g.indexOf(i * slot)).toBe(i);
      expect(g.indexOf((i + 1) * slot - 0.01)).toBe(i);
    }
  });

  it("單根時最右像素回 0(bars.length - 1 的退化端點)", () => {
    const g = buildCandleGeometry(bars.slice(0, 1), size);
    expect(g.indexOf(size.width)).toBe(0);
  });

  it("空幾何的 indexOf 恆 null(另一個 closure,不吃上面的修法)", () => {
    const g = buildCandleGeometry([], size);
    expect(g.indexOf(0)).toBe(null);
    expect(g.indexOf(size.width)).toBe(null);
  });
});

// 🔵 R4:extraSeries 讓布林上下軌參與 y 域,否則超出 o/h/l/c 值域的軌線會被畫到圖框外。
describe("buildCandleGeometry.extraSeries(R4)", () => {
  const size = { width: 400, height: 200 };
  const bars = [
    bar("2026-07-27", 100_000, 110_000, 90_000, 105_000, 10),
    bar("2026-07-28", 105_000, 120_000, 100_000, 102_000, 20),
  ];

  it("不傳時 y 域與現況相同(向後相容)", () => {
    const a = buildCandleGeometry(bars, size);
    const b = buildCandleGeometry(bars, size, []);
    expect(b.toY(120_000)).toBeCloseTo(a.toY(120_000), 9);
    expect(b.toY(90_000)).toBeCloseTo(a.toY(90_000), 9);
  });

  it("超出 o/h/l/c 值域的序列被納入 y 域,toY 落在繪圖區內", () => {
    const upper = [140_000, 145_000];
    const lower = [70_000, 72_000];
    const g = buildCandleGeometry(bars, size, [upper, lower]);
    const priceBottom = (size.height - 14) * (1 - 0.22);
    for (const v of [...upper, ...lower]) {
      expect(g.toY(v)).toBeGreaterThanOrEqual(0);
      expect(g.toY(v)).toBeLessThanOrEqual(priceBottom);
    }
    // 未納入時 145000 會被畫到 y < 0
    expect(buildCandleGeometry(bars, size).toY(145_000)).toBeLessThan(0);
  });

  it("null 元素略過,不汙染 y 域", () => {
    const withNulls = [null, null, 145_000];
    const g = buildCandleGeometry(bars, size, [withNulls]);
    expect(g.toY(145_000)).toBeGreaterThanOrEqual(0);
    // yTicks 仍以最終 hi/lo 產生,不出現 null 造成的 NaN
    for (const t of g.yTicks) expect(Number.isFinite(t.priceMilli)).toBe(true);
  });
});

// ---- round3 T-3:y 刻度合法檔位(user 項 10)----

describe("buildCandleGeometry yTicks 合法檔位(round3 SC-10)", () => {
  const size = { width: 1400, height: 320 };

  it("1000 元以上標的:刻度只出現 5 元的倍數,不帶小數(user 原話「不要出現 1003」)", () => {
    // 等分會算出 2547.32 / 2560.74 這種非法價位(next-time 2026-07-29 實際觀察到的症狀)
    const g = buildCandleGeometry(
      [
        bar("d1", 2_550_000, 2_601_000, 2_547_320, 2_580_000),
        bar("d2", 2_580_000, 2_600_000, 2_550_000, 2_595_000),
      ],
      size,
    );
    expect(g.yTicks.length).toBeGreaterThan(0);
    for (const t of g.yTicks) {
      expect(t.priceMilli % 5_000).toBe(0);
      expect(snapNearest(t.priceMilli)).toBe(t.priceMilli);
    }
  });

  it("100-500 元標的:刻度只出現 0.5 元的倍數(不出現 102.4)", () => {
    const g = buildCandleGeometry(
      [bar("d1", 100_400, 104_900, 100_400, 103_000), bar("d2", 103_000, 104_900, 101_100, 102_400)],
      size,
    );
    for (const t of g.yTicks) {
      expect(t.priceMilli % 500).toBe(0);
    }
  });

  it("刻度不重複(tick 粗於等分間距時相鄰刻度會 snap 到同價)", () => {
    // 1000 元帶 tick 5 元,域寬僅 8 元 → 等分間距 2 元 < tick
    const g = buildCandleGeometry([bar("d", 1_000_000, 1_008_000, 1_000_000, 1_006_000)], size);
    const prices = g.yTicks.map((t) => t.priceMilli);
    expect(new Set(prices).size).toBe(prices.length);
  });

  it("極窄域(區間內無任何合法檔位)仍給至少一根刻度,且該刻度也必須合法", () => {
    // 1000 元帶 tick 5 元;域 = [1000.1, 1003.0] 內部沒有 5 的倍數
    // → 5 個等分候選全被域外過濾掉,走保底分支。
    // 保底值若不 snap 會吐出 1001.55(= (lo+hi)/2)這種下不了單的價位(self-review B1)。
    const g = buildCandleGeometry([bar("d", 1_000_100, 1_003_000, 1_000_100, 1_003_000)], size);
    expect(g.yTicks.length).toBeGreaterThanOrEqual(1);
    for (const t of g.yTicks) {
      expect(t.priceMilli % 5_000).toBe(0);
      expect(snapNearest(t.priceMilli)).toBe(t.priceMilli);
    }
    // 唯一的合法檔位落在域外 → y 要夾回繪圖區,否則刻度會畫進下方量區
    for (const t of g.yTicks) {
      expect(t.y).toBeGreaterThanOrEqual(0);
      expect(t.y).toBeLessThanOrEqual(size.height);
    }
  });

  it("extraSeries(布林/MA)撐開的非法端點:刻度仍全合法且不落到域外", () => {
    const g = buildCandleGeometry(
      [bar("d1", 100_000, 110_000, 95_000, 105_000), bar("d2", 105_000, 112_000, 98_000, 108_000)],
      size,
      [[92_137, 113_881]], // movingAverage 的 Math.floor 產物,非合法檔位
    );
    expect(g.yTicks.length).toBeGreaterThan(0);
    for (const t of g.yTicks) {
      expect(snapNearest(t.priceMilli)).toBe(t.priceMilli);
      expect(t.priceMilli).toBeGreaterThanOrEqual(92_137);
      expect(t.priceMilli).toBeLessThanOrEqual(113_881);
    }
  });
});

describe("aggregateBars 大盤週期(index-board T-6)", () => {
  function m(hhmm: string, c: number) {
    return { t: `2026-07-30 ${hhmm}`, o: c, h: c + 1, l: c - 1, c, v: 1 };
  }

  it("n=30/60/90 桶界以 09:00 為原點、終點標記", () => {
    const bars = [m("09:01", 1), m("09:30", 2), m("09:31", 3), m("10:30", 4)];
    expect(aggregateBars(bars, 30).map((b) => b.t)).toEqual([
      "2026-07-30 09:30",
      "2026-07-30 10:00",
      "2026-07-30 10:30",
    ]);
    // 10:30 落在 09:00+60×2 = 11:00 那一桶(終點標記,非「該筆時刻」)
    expect(aggregateBars(bars, 60).map((b) => b.t)).toEqual([
      "2026-07-30 10:00",
      "2026-07-30 11:00",
    ]);
    expect(aggregateBars(bars, 90).map((b) => b.t)).toEqual(["2026-07-30 10:30"]);
  });

  it("早於 09:00 的分鐘(期指 08:45 開盤)獨立成標記 09:00 的短桶,不遺失資料", () => {
    // review P2-3:不是「第一根較寬」—— n=30 時該桶只含 ≤15 分鐘,首根寬度不等,刻意接受
    const bars = [m("08:46", 1), m("08:59", 2), m("09:01", 3)];
    const out = aggregateBars(bars, 30);
    expect(out.map((b) => b.t)).toEqual(["2026-07-30 09:00", "2026-07-30 09:30"]);
    expect(out[0]!.o).toBe(1);
    expect(out[0]!.c).toBe(2);
    expect(out[0]!.v).toBe(2);
  });

  it("跨日不合併", () => {
    const out = aggregateBars(
      [m("13:00", 1), { ...m("09:01", 2), t: "2026-07-31 09:01" }],
      90,
    );
    expect(out).toHaveLength(2);
  });
});

// ---- futures-allday SC-2/SC-8:夜盤跨午夜聚合 + 內外盤欄位貫通 ----

describe("aggregateBars 24:00 正規化(futures-allday §4.3 D5)", () => {
  function n(t: string, c: number, v = 1): Bar {
    return { t, o: c, h: c + 1, l: c - 1, c, v };
  }

  it("23:56–00:03 @ n=5:桶時戳是次日 00:00,永不產出 '24:00'", () => {
    const out = aggregateBars(
      [
        n("2026-08-05 23:56", 1),
        n("2026-08-05 23:57", 2),
        n("2026-08-05 23:58", 3),
        n("2026-08-05 23:59", 4),
        n("2026-08-06 00:00", 5),
        n("2026-08-06 00:01", 6),
        n("2026-08-06 00:02", 7),
        n("2026-08-06 00:03", 8),
      ],
      5,
    );
    expect(out.map((b) => b.t)).toEqual(["2026-08-06 00:00", "2026-08-06 00:05"]);
    for (const b of out) expect(b.t).not.toContain("24:00");
    // 23:56–23:59 與次日 00:00 落同一桶 → 自然合併(open 取最早、close 取最後)
    expect(out[0]!.o).toBe(1);
    expect(out[0]!.c).toBe(5);
    expect(out[0]!.v).toBe(5);
    expect(out[1]!.o).toBe(6);
    expect(out[1]!.c).toBe(8);
  });

  it("跨月:2026-08-31 23:56 → 桶時戳 2026-09-01 00:00", () => {
    const out = aggregateBars([n("2026-08-31 23:56", 1), n("2026-08-31 23:58", 2)], 5);
    expect(out.map((b) => b.t)).toEqual(["2026-09-01 00:00"]);
  });

  it("跨年:2026-12-31 23:58 → 桶時戳 2027-01-01 00:00", () => {
    const out = aggregateBars([n("2026-12-31 23:58", 1)], 5);
    expect(out.map((b) => b.t)).toEqual(["2027-01-01 00:00"]);
  });

  it("n=60 的 23:xx 同樣正規化(不是只有小 n 才會溢位)", () => {
    const out = aggregateBars([n("2026-08-05 23:10", 1)], 60);
    expect(out.map((b) => b.t)).toEqual(["2026-08-06 00:00"]);
  });

  it("日盤-only 資料永不觸發正規化(個股/大盤行為零變化)", () => {
    const out = aggregateBars([n("2026-08-05 13:30", 1), n("2026-08-05 13:45", 2)], 30);
    expect(out.map((b) => b.t)).toEqual(["2026-08-05 13:30", "2026-08-05 14:00"]);
  });
});

describe("aggregateBars uv/dv 貫通(futures-allday §4.3 D6)", () => {
  function d(t: string, c: number, uv?: number, dv?: number): Bar {
    const b: Bar = { t, o: c, h: c, l: c, c, v: 1 };
    if (uv !== undefined) b.uv = uv;
    if (dv !== undefined) b.dv = dv;
    return b;
  }

  it("同桶累加,總和不變", () => {
    const out = aggregateBars(
      [
        d("2026-08-05 09:01", 1, 10, 4),
        d("2026-08-05 09:02", 2, 5, 6),
        d("2026-08-05 09:03", 3, 1, 2),
      ],
      5,
    );
    expect(out).toHaveLength(1);
    expect(out[0]!.uv).toBe(16);
    expect(out[0]!.dv).toBe(10);
  });

  it("來源全無 uv/dv → 桶也不設欄(維持 NotRequired 語意,日盤資料 bit-for-bit 不變)", () => {
    const out = aggregateBars([d("2026-08-05 09:01", 1), d("2026-08-05 09:02", 2)], 5);
    expect(out).toEqual([{ t: "2026-08-05 09:05", o: 1, h: 2, l: 1, c: 2, v: 2 }]);
    expect("uv" in out[0]!).toBe(false);
    expect("dv" in out[0]!).toBe(false);
  });

  it("桶內部分 bar 缺欄 → 缺值視 0,只要任一根有欄就設欄", () => {
    const out = aggregateBars(
      [d("2026-08-05 09:01", 1), d("2026-08-05 09:02", 2, 7, 3), d("2026-08-05 09:03", 3)],
      5,
    );
    expect(out[0]!.uv).toBe(7);
    expect(out[0]!.dv).toBe(3);
  });

  it("首根就帶欄、後續缺 → 首根值保留(不被覆寫成 undefined)", () => {
    const out = aggregateBars([d("2026-08-05 09:01", 1, 9), d("2026-08-05 09:02", 2)], 5);
    expect(out[0]!.uv).toBe(9);
    expect(out[0]!.dv).toBe(0);
  });

  it("n=1 原樣回傳時 uv/dv 不遺失", () => {
    const input = [d("2026-08-05 09:01", 1, 3, 4)];
    expect(aggregateBars(input, 1)).toEqual(input);
  });
});

describe("buildCandleGeometry.deltaVol(SC-8 內外盤副圖幾何)", () => {
  const size = { width: 400, height: 200 };
  const volH = (size.height - 14) * 0.22;

  function d(t: string, c: number, uv?: number, dv?: number): Bar {
    const b: Bar = { t, o: c, h: c + 1, l: c - 1, c, v: 10 };
    if (uv !== undefined) b.uv = uv;
    if (dv !== undefined) b.dv = dv;
    return b;
  }

  it("與 candles 同索引對位(長度相同)", () => {
    const g = buildCandleGeometry([d("a", 100, 3, 1), d("b", 101, 2, 6)], size);
    expect(g.deltaVol).not.toBeNull();
    expect(g.deltaVol!.length).toBe(g.candles.length);
  });

  it("分母 = 視窗內 max(uv+dv):最大那根的 uvH+dvH 填滿量區高度", () => {
    const g = buildCandleGeometry([d("a", 100, 3, 1), d("b", 101, 2, 6)], size);
    const [first, second] = g.deltaVol!;
    expect(second!.uvH + second!.dvH).toBeCloseTo(volH, 6); // 2+6 = 8 = max
    expect(first!.uvH + first!.dvH).toBeCloseTo(volH * 0.5, 6); // 3+1 = 4
    expect(first!.uvH).toBeCloseTo((volH * 3) / 8, 6);
    expect(first!.dvH).toBeCloseTo((volH * 1) / 8, 6);
  });

  it("視窗內全無 uv/dv → null(SC-8 隱藏判定的資料面)", () => {
    expect(buildCandleGeometry([d("a", 100), d("b", 101)], size).deltaVol).toBeNull();
  });

  it("uv/dv 都在但全為 0 → null(不除以零、也不畫一排零高柱)", () => {
    expect(buildCandleGeometry([d("a", 100, 0, 0)], size).deltaVol).toBeNull();
  });

  it("部分 bar 缺欄 → 該根視 0,不影響其他根", () => {
    const g = buildCandleGeometry([d("a", 100), d("b", 101, 4, 4)], size);
    expect(g.deltaVol![0]).toEqual({ uvH: 0, dvH: 0 });
    expect(g.deltaVol![1]!.uvH + g.deltaVol![1]!.dvH).toBeCloseTo(volH, 6);
  });

  it("空幾何的 deltaVol 是 null(不是 undefined)", () => {
    expect(buildCandleGeometry([], size).deltaVol).toBeNull();
  });
});

describe("hlineYOf(SC-7/SC-11 水平 overlay 線;超窗不畫)", () => {
  const size = { width: 400, height: 200 };
  const bars = [
    { t: "2026-07-27", o: 100_000, h: 110_000, l: 90_000, c: 105_000, v: 10 },
    { t: "2026-07-28", o: 105_000, h: 120_000, l: 100_000, c: 102_000, v: 20 },
  ];

  it("域內價位回 toY 的同一個 y", () => {
    const g = buildCandleGeometry(bars, size);
    expect(hlineYOf(105_000, g)).toBeCloseTo(g.toY(105_000), 9);
    expect(hlineYOf(90_000, g)).toBeCloseTo(g.toY(90_000), 9);
    expect(hlineYOf(120_000, g)).toBeCloseTo(g.toY(120_000), 9);
  });

  it("超出 y 視窗(高於最高 / 低於最低)回 null,不 clamp 到邊緣誤導價位", () => {
    const g = buildCandleGeometry(bars, size);
    expect(hlineYOf(130_000, g)).toBeNull();
    expect(hlineYOf(80_000, g)).toBeNull();
  });

  it("空幾何一律 null(否則會在空圖底部畫一條假線)", () => {
    const g = buildCandleGeometry([], size);
    expect(hlineYOf(100_000, g)).toBeNull();
  });

  it("全平盤(span=0):同價可畫、他價不畫", () => {
    const g = buildCandleGeometry(
      [{ t: "d", o: 100_000, h: 100_000, l: 100_000, c: 100_000, v: 1 }],
      size,
    );
    expect(hlineYOf(100_000, g)).not.toBeNull();
    expect(hlineYOf(100_500, g)).toBeNull();
  });

  it("extraSeries 撐開的 y 域也算數(布林軌撐開後線就畫得出來)", () => {
    const narrow = buildCandleGeometry(bars, size);
    expect(hlineYOf(140_000, narrow)).toBeNull();
    const wide = buildCandleGeometry(bars, size, [[140_000, 70_000]]);
    expect(hlineYOf(140_000, wide)).not.toBeNull();
  });
});
