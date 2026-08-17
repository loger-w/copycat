import { describe, expect, it } from "vitest";

import type { IndexSeries } from "@/hooks/useIndexStream";
import { indexSeriesToAccum } from "@/lib/index-accum-adapter";

/** 指數序列 → `StockAccum`(change-spec §3.2)。指數沒有量,adapter 的每一個「假值」都
 *  是為了讓 `IntradayChartCore` 的既有幾何在 index 態產出**正確語意**:
 *  v=1 讓 vwapLine 退化成分鐘收盤算術平均(= 舊 MarketChart 的均價線),
 *  h/l = c 讓高低等值反查一定命中,upper/lower null 讓 y 域走對稱 autofit。 */

function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 23_100_000,
    ref: 23_000_000,
    high: 23_120_000,
    low: 22_980_000,
    stale: false,
    minutes: { "0930": 23_100_000, "0901": 23_000_000, "0915": 23_050_000 },
    ...over,
  };
}

describe("indexSeriesToAccum", () => {
  it("HHMM 鍵 → 分鐘數,依分鐘升冪;每格 c=值、v=1、i/o/u=0、h=l=c", () => {
    const a = indexSeriesToAccum(series(), "IX:TWSE", "加權指數");
    expect([...a.minutes.keys()]).toEqual([541, 555, 570]);
    expect(a.minutes.get(555)).toEqual({ c: 23_050_000, v: 1, i: 0, o: 0, u: 0, h: 23_050_000, l: 23_050_000 });
  });

  it("vwap = 分鐘收盤算術平均(四捨五入毫點);high / low = 分鐘收盤極值(不是 series.high/low)", () => {
    const a = indexSeriesToAccum(series(), "IX:TWSE", "加權指數");
    expect(a.vwap).toBe(Math.round((23_000_000 + 23_050_000 + 23_100_000) / 3));
    // series.high 23_120_000 / low 22_980_000 是 tick 極值,分鐘收盤沒有任何一格等於它 →
    // 拿它當 accum.high 會讓 `buildIntradayGeometry` 的等值反查永遠落空(標記靜默缺席)
    expect(a.high).toBe(23_100_000);
    expect(a.low).toBe(23_000_000);
  });

  it("meta:name / ref 透傳,upper / lower / y_vol 為 null(→ 對稱 autofit 域、不亮漲跌停燈)", () => {
    const a = indexSeriesToAccum(series(), "IX:TWSE", "加權指數");
    expect(a.meta).toEqual({ name: "加權指數", ref: 23_000_000, upper: null, lower: null, y_vol: null });
    expect(a.code).toBe("IX:TWSE");
  });

  it("last = {p: series.p};p null → last null(現價圈不畫)", () => {
    expect(indexSeriesToAccum(series(), "IX:TWSE", "加權指數").last).toEqual({
      p: 23_100_000,
      t: "",
      cum_vol: 0,
    });
    expect(indexSeriesToAccum(series({ p: null }), "IX:TWSE", "加權指數").last).toBeNull();
  });

  it("ref null 原樣透傳(core 走 hasRef=false 單色線)", () => {
    expect(indexSeriesToAccum(series({ ref: null }), "IX:OTC", "櫃買指數").meta?.ref).toBeNull();
  });

  it("非法鍵(非四位數字 / 分鐘 ≥ 60)一律略過,不炸也不畫", () => {
    const a = indexSeriesToAccum(
      series({ minutes: { "0901": 1_000_000, abcd: 2_000_000, "0960": 3_000_000, "930": 4_000_000 } }),
      "IX:TWSE",
      "加權指數",
    );
    expect([...a.minutes.keys()]).toEqual([541]);
    expect(a.high).toBe(1_000_000);
  });

  it("窗外鍵(1430 定盤 / 0859)不進 minutes,也不影響 vwap / high / low(與幾何 windowedEntries 同一把尺)", () => {
    const a = indexSeriesToAccum(
      series({ minutes: { "0901": 1_000_000, "1330": 1_100_000, "1430": 9_000_000, "0859": 100 } }),
      "IX:TWSE",
      "加權指數",
    );
    expect([...a.minutes.keys()]).toEqual([541, 810]);
    expect(a.high).toBe(1_100_000);
    expect(a.low).toBe(1_000_000);
    expect(a.vwap).toBe(1_050_000);
  });

  it("值為 0 的分鐘 / p=0 視為不可得(後端 _millipt(\"0\") 回 0 不回 None):不進 minutes、last null", () => {
    const a = indexSeriesToAccum(
      series({ p: 0, minutes: { "0901": 1_000_000, "0902": 0, "0903": 1_200_000 } }),
      "IX:TWSE",
      "加權指數",
    );
    expect([...a.minutes.keys()]).toEqual([541, 543]);
    expect(a.low).toBe(1_000_000);
    expect(a.vwap).toBe(1_100_000);
    expect(a.last).toBeNull();
  });

  it("空 minutes → 空 Map、vwap / high / low 皆 null", () => {
    const a = indexSeriesToAccum(series({ minutes: {} }), "IX:TWSE", "加權指數");
    expect(a.minutes.size).toBe(0);
    expect(a.vwap).toBeNull();
    expect(a.high).toBeNull();
    expect(a.low).toBeNull();
  });

  it("其餘欄位固定:ticks 空、vp 空 Map、book null、noData false、trial false、volume 0", () => {
    const a = indexSeriesToAccum(series(), "IX:TWSE", "加權指數");
    expect(a.ticks).toEqual([]);
    expect(a.vp.size).toBe(0);
    expect(a.book).toBeNull();
    expect(a.noData).toBe(false);
    expect(a.trial).toBe(false);
    expect(a.volume).toBe(0);
    expect(a.amountMilli).toBe(0);
    expect(a.seq).toBe(0);
  });
});
