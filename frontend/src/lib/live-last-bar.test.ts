import { describe, expect, it } from "vitest";

import { aggregateBars, type Bar } from "@/lib/candle";
import { mergeLiveDailyBar, mergeLiveMinuteBars } from "@/lib/live-last-bar";
import type { MinuteAgg } from "@/lib/stock-accum";

/** 規則表(spec #214 Testing Decisions;seam (b)):期望值全部手寫字面量,不從實作同源的常數算回來。
 *  價是毫元、量是張;accum 分鐘 key = 起點分(`HH*60+MM`),1K bar `t` = 終點標記。 */

function bar(t: string, o: number, h: number, l: number, c: number, v = 1, extra: Partial<Bar> = {}): Bar {
  return { t, o, h, l, c, v, ...extra };
}

/** accum 分鐘累積(`MinuteAgg`):`o` / `i` / `u` 是外 / 內 / 未分類**量**,不是價。 */
function agg(c: number, v: number, h: number | null, l: number | null, o = 0, i = 0): MinuteAgg {
  return { c, v, i, o, u: v - o - i, h, l };
}

const TODAY = "2026-09-08";
const M = (hh: number, mm: number) => hh * 60 + mm;

describe("mergeLiveMinuteBars(分 K 即時末根)", () => {
  it("案 1:只補正式末根之後的分鐘;起點分 +1 = 終點標記;o = 前一根 c(正式或已補)", () => {
    const official = [
      bar(`${TODAY} 09:04`, 100_000, 101_000, 99_000, 100_500, 8),
      bar(`${TODAY} 09:05`, 100_500, 105_000, 99_000, 104_000, 10, { uv: 6, dv: 4 }),
    ];
    const minutes = new Map<number, MinuteAgg>([
      [M(9, 4), agg(104_000, 10, 105_000, 99_000, 6, 4)], // → 09:05,正式已有,跳過
      [M(9, 5), agg(106_000, 5, 107_000, 103_000, 3, 2)], // → 09:06
      [M(9, 6), agg(103_000, 7, 108_000, 102_000, 4, 3)], // → 09:07(進行中)
    ]);
    const out = mergeLiveMinuteBars(official, minutes, TODAY, M(9, 6));
    expect(out).toEqual([
      official[0],
      official[1],
      { t: `${TODAY} 09:06`, o: 104_000, h: 107_000, l: 103_000, c: 106_000, v: 5, uv: 3, dv: 2 },
      { t: `${TODAY} 09:07`, o: 106_000, h: 108_000, l: 102_000, c: 103_000, v: 7, uv: 4, dv: 3 },
    ]);
  });

  it("案 2:13:29 與 13:30(收盤撮合)併進單一根 13:30,不產生 13:31", () => {
    const official = [bar(`${TODAY} 13:28`, 120_000, 120_500, 119_500, 120_000, 2)];
    const minutes = new Map<number, MinuteAgg>([
      [M(13, 29), agg(120_500, 3, 121_000, 119_000, 2, 1)], // → 13:30
      [M(13, 30), agg(122_000, 50, 122_000, 118_000, 30, 20)], // → 13:31 → 上限 13:30,併根
    ]);
    const out = mergeLiveMinuteBars(official, minutes, TODAY, M(13, 30));
    expect(out).toEqual([
      official[0],
      { t: `${TODAY} 13:30`, o: 120_000, h: 122_000, l: 118_000, c: 122_000, v: 53, uv: 32, dv: 21 },
    ]);
    expect(out.some((b) => b.t.endsWith("13:31"))).toBe(false);
  });

  it("案 3:正式末根不是今天 → 從 accum 最早分鐘補起,o = 昨日末根 c;09:01 以前的分鐘(試撮殘留)丟棄", () => {
    const official = [bar("2026-09-05 13:30", 88_000, 90_000, 87_000, 90_000, 40)];
    const minutes = new Map<number, MinuteAgg>([
      [M(9, 1), agg(92_000, 4, 92_500, 91_000)], // 插入順序刻意亂放:Map 不保證排序
      [M(8, 59), agg(95_000, 9, 95_000, 95_000)], // → 09:00 < 09:01,丟
      [M(9, 0), agg(91_000, 12, 91_500, 90_500, 7, 5)], // → 09:01
    ]);
    const out = mergeLiveMinuteBars(official, minutes, TODAY, M(9, 1));
    expect(out).toEqual([
      official[0],
      { t: `${TODAY} 09:01`, o: 90_000, h: 91_500, l: 90_500, c: 91_000, v: 12, uv: 7, dv: 5 },
      { t: `${TODAY} 09:02`, o: 91_000, h: 92_500, l: 91_000, c: 92_000, v: 4, uv: 0, dv: 0 },
    ]);
  });

  it("案 4:晚於 nowMinute 的分鐘不補(時鐘倒退防禦);nowMinute 那分鐘本身是進行中根", () => {
    const official = [bar(`${TODAY} 09:04`, 100_000, 101_000, 99_000, 100_500, 8)];
    const minutes = new Map<number, MinuteAgg>([
      [M(9, 5), agg(101_000, 1, 101_000, 101_000)],
      [M(9, 6), agg(102_000, 1, 102_000, 102_000)],
    ]);
    const out = mergeLiveMinuteBars(official, minutes, TODAY, M(9, 5));
    expect(out.map((b) => b.t)).toEqual([`${TODAY} 09:04`, `${TODAY} 09:06`]);
  });

  it("案 5:分鐘 h / l 為 null(舊後端快照)→ 用 c 頂替;uv / dv 恆給欄(0 也給)", () => {
    const official = [bar(`${TODAY} 09:04`, 100_000, 101_000, 99_000, 100_500, 8)];
    const minutes = new Map<number, MinuteAgg>([[M(9, 5), agg(101_000, 3, null, null)]]);
    const out = mergeLiveMinuteBars(official, minutes, TODAY, M(9, 5));
    expect(out[1]).toEqual({
      t: `${TODAY} 09:06`, o: 100_500, h: 101_000, l: 101_000, c: 101_000, v: 3, uv: 0, dv: 0,
    });
  });

  it("案 8:正式段元素 identity 保留、傳入 array 不被改動;沒東西可補時仍回新 array", () => {
    const official = [
      bar(`${TODAY} 09:04`, 100_000, 101_000, 99_000, 100_500, 8),
      bar(`${TODAY} 09:05`, 100_500, 105_000, 99_000, 104_000, 10),
    ];
    const snapshot = [...official];
    const minutes = new Map<number, MinuteAgg>([[M(9, 5), agg(106_000, 5, 107_000, 103_000)]]);
    const out = mergeLiveMinuteBars(official, minutes, TODAY, M(9, 5));
    expect(out[0]).toBe(official[0]);
    expect(out[1]).toBe(official[1]);
    expect(official).toEqual(snapshot);
    const none = mergeLiveMinuteBars(official, new Map(), TODAY, M(9, 5));
    expect(none).not.toBe(official);
    expect(none).toEqual(official);
  });

  it("案 9:與 aggregateBars(3) 串接 —— 補的 09:06 落進 09:06 桶、09:07 落進進行中的 09:09 桶", () => {
    const official = [
      bar(`${TODAY} 09:01`, 100_000, 101_000, 99_000, 100_500, 1),
      bar(`${TODAY} 09:02`, 100_500, 101_000, 100_000, 100_800, 1),
      bar(`${TODAY} 09:03`, 100_800, 101_500, 100_500, 101_000, 1),
      bar(`${TODAY} 09:04`, 101_000, 101_200, 100_900, 101_100, 1),
      bar(`${TODAY} 09:05`, 101_100, 105_000, 99_000, 104_000, 10),
    ];
    const minutes = new Map<number, MinuteAgg>([
      [M(9, 5), agg(106_000, 5, 107_000, 103_000)],
      [M(9, 6), agg(103_000, 7, 108_000, 102_000)],
    ]);
    const out = aggregateBars(mergeLiveMinuteBars(official, minutes, TODAY, M(9, 6)), 3);
    expect(out.map((b) => b.t)).toEqual([`${TODAY} 09:03`, `${TODAY} 09:06`, `${TODAY} 09:09`]);
    expect(out[1]).toMatchObject({ o: 101_000, h: 107_000, l: 99_000, c: 106_000, v: 16 });
    expect(out[2]).toMatchObject({ o: 106_000, h: 108_000, l: 102_000, c: 103_000, v: 7 });
  });
});

/** 日 K 的 accum 面(`StockAccum` 的四個欄):`last.cum_vol` = TC4 當日累積量(與 DK 的 `v` 同源)。 */
function live(over: {
  last?: { p: number; t: string; cum_vol: number } | null;
  high?: number | null;
  low?: number | null;
  minutes?: Map<number, MinuteAgg>;
}) {
  return {
    last: over.last === undefined ? { p: 103_000, t: "09:06:20.000", cum_vol: 21 } : over.last,
    high: over.high === undefined ? 108_000 : over.high,
    low: over.low === undefined ? 98_000 : over.low,
    minutes:
      over.minutes ??
      new Map<number, MinuteAgg>([
        [M(9, 1), agg(102_000, 4, 102_500, 101_000)],
        [M(9, 0), agg(101_000, 12, 101_500, 100_500)], // 最早分鐘;插入順序刻意亂放
      ]),
  };
}

describe("mergeLiveDailyBar(日 K 即時末根)", () => {
  it("案 6a:末根 = today → o 保留正式的,c / v 換 accum(last.p / last.cum_vol),h / l 取聯集(此例 accum 較寬)", () => {
    const official = [
      bar("2026-09-05", 90_000, 92_000, 89_000, 91_000, 300),
      bar(TODAY, 100_000, 101_000, 99_000, 100_500, 5),
    ];
    const out = mergeLiveDailyBar(official, live({}), TODAY, 102_000);
    expect(out).toEqual([
      official[0],
      { t: TODAY, o: 100_000, h: 108_000, l: 98_000, c: 103_000, v: 21 },
    ]);
  });

  it("案 6c:正式半成品的 h / l 比 accum 寬(回補未到 / 放棄,accum 只含之後的成交)→ 取聯集,不被 accum 窄化(pr-218 F-02)", () => {
    const official = [
      bar("2026-09-05", 90_000, 92_000, 89_000, 91_000, 300),
      bar(TODAY, 100_000, 110_000, 97_000, 100_500, 5),
    ];
    const out = mergeLiveDailyBar(official, live({}), TODAY, null);
    expect(out[1]).toEqual({ t: TODAY, o: 100_000, h: 110_000, l: 97_000, c: 103_000, v: 21 });
    // accum 較寬的那一側照樣贏(6a 的既有語意不變)
    const wider = mergeLiveDailyBar(official, live({ high: 111_000, low: 96_000 }), TODAY, null);
    expect(wider[1]).toMatchObject({ h: 111_000, l: 96_000 });
  });

  it("案 6b:末根是昨天 → append 今天一根,o = dayOpen;dayOpen null → accum 最早分鐘的 c", () => {
    const official = [bar("2026-09-05", 90_000, 92_000, 89_000, 91_000, 300)];
    expect(mergeLiveDailyBar(official, live({}), TODAY, 102_000)).toEqual([
      official[0],
      { t: TODAY, o: 102_000, h: 108_000, l: 98_000, c: 103_000, v: 21 },
    ]);
    expect(mergeLiveDailyBar(official, live({}), TODAY, null)[1]).toEqual({
      t: TODAY, o: 101_000, h: 108_000, l: 98_000, c: 103_000, v: 21,
    });
  });

  it("案 7:accum 無成交(last null / high null)→ 原樣;末根日期 > today(不該發生)→ 原樣", () => {
    const official = [bar("2026-09-05", 90_000, 92_000, 89_000, 91_000, 300)];
    expect(mergeLiveDailyBar(official, live({ last: null }), TODAY, null)).toEqual(official);
    expect(mergeLiveDailyBar(official, live({ high: null, low: null }), TODAY, null)).toEqual(official);
    const future = [bar("2026-09-09", 90_000, 92_000, 89_000, 91_000, 300)];
    expect(mergeLiveDailyBar(future, live({}), TODAY, null)).toEqual(future);
    expect(mergeLiveDailyBar([], live({}), TODAY, 102_000)).toEqual([
      { t: TODAY, o: 102_000, h: 108_000, l: 98_000, c: 103_000, v: 21 },
    ]);
  });

  it("案 8(日 K):正式段元素 identity 保留、傳入 array 不改;原樣路徑也回新 array", () => {
    const official = [
      bar("2026-09-05", 90_000, 92_000, 89_000, 91_000, 300),
      bar(TODAY, 100_000, 101_000, 99_000, 100_500, 5),
    ];
    const snapshot = official.map((b) => ({ ...b }));
    const out = mergeLiveDailyBar(official, live({}), TODAY, null);
    expect(out[0]).toBe(official[0]);
    expect(out[1]).not.toBe(official[1]);
    expect(official).toEqual(snapshot);
    const none = mergeLiveDailyBar(official, live({ last: null }), TODAY, null);
    expect(none).not.toBe(official);
  });
});
