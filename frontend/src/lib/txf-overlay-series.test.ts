import { describe, expect, it } from "vitest";

import type { Bar } from "@/lib/candle";
import { txfBarsToSeries } from "@/lib/txf-overlay-series";

/** feat/txf-intraday-overlay S1:期貨 allday 1K bars + 期貨 WS 現價 → 與加權 / 櫃買同形的
 *  `IndexSeries`(分鐘鍵 = 起點 HHMM),餵既有 `buildIndexOverlayLines` 畫「台指期」疊線。 */

function bar(t: string, c: number): Bar {
  return { t, o: c, h: c + 1000, l: c - 1000, c, v: 1 };
}

const REF = 23_000_000;

describe("txfBarsToSeries(期貨 1K → IndexSeries)", () => {
  it("日盤段 bar 的終點標記 −1 分 = 分鐘鍵(08:46 那根是 08:45 那一分鐘的價;13:45 → 1344)", () => {
    const s = txfBarsToSeries(
      [bar("2026-08-27 08:46", 23_100_000), bar("2026-08-27 08:47", 23_200_000), bar("2026-08-27 13:45", 23_050_000)],
      null,
      REF,
      false,
    );
    expect(s).not.toBeNull();
    expect(s!.minutes).toEqual({ "0845": 23_100_000, "0846": 23_200_000, "1344": 23_050_000 });
    expect(s!.ref).toBe(REF);
    expect(s!.p).toBe(23_050_000); // 最後一點
    expect(s!.high).toBe(23_200_000);
    expect(s!.low).toBe(23_050_000);
    expect(s!.stale).toBe(false);
  });

  it("只取錨定日的日盤段:前一日日盤、夜盤前半(15:01–23:59)、夜盤後半(00:00–05:00)全剔除", () => {
    const s = txfBarsToSeries(
      [
        bar("2026-08-26 08:46", 1_000_000), // 前一日日盤
        bar("2026-08-26 15:01", 2_000_000), // 前一日夜盤前半
        bar("2026-08-27 00:30", 3_000_000), // 夜盤後半(錨定 08-26)
        bar("2026-08-27 08:46", 23_100_000),
        bar("2026-08-27 09:00", 23_200_000),
        bar("2026-08-27 15:01", 4_000_000), // 當日夜盤(現貨無盤,不疊)
      ],
      null,
      REF,
      false,
    );
    expect(s!.minutes).toEqual({ "0845": 23_100_000, "0859": 23_200_000 });
  });

  it("最後一根落在凌晨(≤05:00)→ 錨定日是前一日,疊的是前一日的日盤段(同 lib/allday.ts::anchorDateOf)", () => {
    const s = txfBarsToSeries(
      [bar("2026-08-26 08:46", 23_100_000), bar("2026-08-26 15:01", 2_000_000), bar("2026-08-27 00:30", 3_000_000)],
      null,
      REF,
      false,
    );
    expect(s!.minutes).toEqual({ "0845": 23_100_000 });
  });

  it("0 價 bar 整根剔除(TC4 偶發送 0,後端原樣轉 0;同 futures-overlay usable)", () => {
    const s = txfBarsToSeries(
      [bar("2026-08-27 08:46", 23_100_000), bar("2026-08-27 08:47", 0), bar("2026-08-27 08:48", 23_300_000)],
      null,
      REF,
      false,
    );
    expect(s!.minutes).toEqual({ "0845": 23_100_000, "0847": 23_300_000 });
    expect(s!.low).toBe(23_100_000); // 0 不進極值
  });

  it("結算價不可得(null / 0 / NaN)→ null(鈕反灰「無台指期資料」;相對 % 沒基準就是假線)", () => {
    const bars = [bar("2026-08-27 08:46", 23_100_000)];
    expect(txfBarsToSeries(bars, null, null, false)).toBeNull();
    expect(txfBarsToSeries(bars, null, 0, false)).toBeNull();
    expect(txfBarsToSeries(bars, null, Number.NaN, false)).toBeNull();
  });

  it("bars 空 → 有 ref 就回空 minutes 的 series(線不畫、鈕不反灰:資料是可回復的,輪詢會補)", () => {
    const s = txfBarsToSeries([], null, REF, false);
    expect(s).toEqual({ p: null, ref: REF, high: null, low: null, stale: false, minutes: {} });
  });

  describe("WS 現價補尾(bars 每 60 s 才更新)", () => {
    const bars = [bar("2026-08-27 08:46", 23_100_000), bar("2026-08-27 09:00", 23_200_000)]; // 最後一根 = 0859

    it("同錨定日、分鐘在最後一根之後、落在日盤段 → 追加該分鐘", () => {
      const s = txfBarsToSeries(bars, { p: 23_250_000, t: "09:02:15.000", date: "2026-08-27" }, REF, false);
      expect(s!.minutes).toEqual({ "0845": 23_100_000, "0859": 23_200_000, "0902": 23_250_000 });
      expect(s!.p).toBe(23_250_000);
      expect(s!.high).toBe(23_250_000);
    });

    it("分鐘 ≤ 最後一根 → 不追加也不覆寫(bar 是收盤價、WS 是瞬時價,兩把尺不混)", () => {
      const same = txfBarsToSeries(bars, { p: 99_000_000, t: "08:59:59.000", date: "2026-08-27" }, REF, false);
      expect(same!.minutes).toEqual({ "0845": 23_100_000, "0859": 23_200_000 });
      const earlier = txfBarsToSeries(bars, { p: 99_000_000, t: "08:50:00.000", date: "2026-08-27" }, REF, false);
      expect(earlier!.minutes).toEqual({ "0845": 23_100_000, "0859": 23_200_000 });
    });

    it("日期不同 / 落在盤外(13:46 後、夜盤)/ p 0 / t 缺 / bars 空(沒有錨定日)→ 不追加", () => {
      const base = { "0845": 23_100_000, "0859": 23_200_000 };
      expect(txfBarsToSeries(bars, { p: 23_250_000, t: "09:02:00.000", date: "2026-08-28" }, REF, false)!.minutes).toEqual(base);
      expect(txfBarsToSeries(bars, { p: 23_250_000, t: "13:46:00.000", date: "2026-08-27" }, REF, false)!.minutes).toEqual(base);
      expect(txfBarsToSeries(bars, { p: 23_250_000, t: "15:00:30.000", date: "2026-08-27" }, REF, false)!.minutes).toEqual(base);
      expect(txfBarsToSeries(bars, { p: 0, t: "09:02:00.000", date: "2026-08-27" }, REF, false)!.minutes).toEqual(base);
      expect(txfBarsToSeries(bars, { p: 23_250_000, t: null, date: "2026-08-27" }, REF, false)!.minutes).toEqual(base);
      expect(txfBarsToSeries([], { p: 23_250_000, t: "09:02:00.000", date: "2026-08-27" }, REF, false)!.minutes).toEqual({});
    });

    it("13:45 收盤撮合那一分鐘(t = 13:45:xx)仍算日盤段(個股期窗到 13:45)", () => {
      const s = txfBarsToSeries(bars, { p: 23_250_000, t: "13:45:00.000", date: "2026-08-27" }, REF, false);
      expect(s!.minutes["1345"]).toBe(23_250_000);
    });
  });

  it("stale 原樣透傳(期貨 WS 非 open → 標籤加註「(中斷)」;歷史分鐘仍為真)", () => {
    expect(txfBarsToSeries([bar("2026-08-27 08:46", 23_100_000)], null, REF, true)!.stale).toBe(true);
  });
});
