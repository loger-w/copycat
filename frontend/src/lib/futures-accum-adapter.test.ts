import { describe, expect, it } from "vitest";

import { alldayIndexOf } from "@/lib/allday";
import type { Bar } from "@/lib/candle";
import { futuresBarsToAccum } from "@/lib/futures-accum-adapter";

/** 期貨 1K bars → `StockAccum`(change-spec §3.2)。key = **近全軸索引**不是分鐘數 ——
 *  core 的幾何對 key 的唯一要求是「落在 xw 的整數、可排序」,期貨頁把 `ALLDAY_WINDOW`
 *  注進去之後,索引就是那把尺。
 *
 *  這一檔鎖的是「哪些數字是真的、哪些是佔位」:live 佔位格 v=0(尚無 1K,不是零成交)、
 *  `last.t / cum_vol` 無來源給空值、`upper/lower` 一律 null(±10% 域會把日內線壓成平線)。 */

function bar(t: string, over: Partial<Bar> = {}): Bar {
  const c = over.c ?? 23_000_000;
  return { t, o: c, h: c, l: c, c, v: 1, ...over };
}

const BASE = { ref: 23_000_000, name: "台指近", code: "TXF.HOT" };

describe("futuresBarsToAccum", () => {
  it("bar 時戳 → 軸索引當 key;一天之外(13:46–15:00)與空檔(05:01–08:45)的 bar 略過(軸上沒有那一格)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01"),
        bar("2026-08-18 14:00"), // 一天之外:13:46–15:00
        bar("2026-08-19 07:00"), // 空檔:05:01–08:45(後端不會給,防禦)
        bar("2026-08-19 09:00"),
      ],
      live: null,
      ...BASE,
    });
    // 夜盤側與日盤側都有 → 多一格 08:45 的水平橋(見下方 bridge 節)
    expect([...a.minutes.keys()]).toEqual([0, 1064, 1079]);
    expect(alldayIndexOf("1501")).toBe(0);
    expect(alldayIndexOf("0900")).toBe(1079);
  });

  it("uv / dv → o / i,u = v − uv − dv;缺欄(DK 路徑)→ o=i=0、u=v(判定率 0% 誠實呈現)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01", { v: 100, uv: 60, dv: 30 }),
        bar("2026-08-18 15:02", { v: 50 }),
      ],
      live: null,
      ...BASE,
    });
    expect(a.minutes.get(0)).toEqual({
      c: 23_000_000,
      v: 100,
      o: 60,
      i: 30,
      u: 10,
      h: 23_000_000,
      l: 23_000_000,
    });
    expect(a.minutes.get(1)!.o).toBe(0);
    expect(a.minutes.get(1)!.i).toBe(0);
    expect(a.minutes.get(1)!.u).toBe(50);
  });

  it("uv + dv > v(畸形資料)→ u 夾制成 0,不出現負數量", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-18 15:01", { v: 10, uv: 9, dv: 8 })],
      live: null,
      ...BASE,
    });
    expect(a.minutes.get(0)!.u).toBe(0);
  });

  it("h / l 逐欄透傳(tick 級極值,高低標記等值反查必命中)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01", { c: 23_000_000, h: 23_030_000, l: 22_990_000 }),
        bar("2026-08-18 15:02", { c: 23_010_000, h: 23_040_000, l: 22_980_000 }),
      ],
      live: null,
      ...BASE,
    });
    expect(a.high).toBe(23_040_000);
    expect(a.low).toBe(22_980_000);
    expect(a.minutes.get(1)!.h).toBe(23_040_000);
  });

  it("live 同索引 → 覆寫 c 並擴張 h / l(量不動:量來自 1K,不是牆上時鐘)", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-18 15:01", { c: 23_000_000, h: 23_010_000, l: 22_990_000, v: 12 })],
      live: { index: 0, p: 23_050_000 },
      ...BASE,
    });
    expect(a.minutes.get(0)).toEqual({
      c: 23_050_000,
      v: 12,
      o: 0,
      i: 0,
      u: 12,
      h: 23_050_000,
      l: 22_990_000,
    });
    expect(a.high).toBe(23_050_000);
  });

  it("live 新索引 → 補一格佔位:v=0 / o=i=u=0 / h=l=p(尚無 1K,印 0 是假數字)", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-18 15:01", { v: 12 })],
      live: { index: 5, p: 23_020_000 },
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([0, 5]);
    expect(a.minutes.get(5)).toEqual({
      c: 23_020_000,
      v: 0,
      o: 0,
      i: 0,
      u: 0,
      h: 23_020_000,
      l: 23_020_000,
    });
  });

  it("vwap = Σc·v / Σv(真量加權,不是算術平均);amountMilli / volume 同源", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01", { c: 23_000_000, v: 90 }),
        bar("2026-08-18 15:02", { c: 23_100_000, v: 10 }),
      ],
      live: null,
      ...BASE,
    });
    const amount = 23_000_000 * 90 + 23_100_000 * 10;
    expect(a.vwap).toBe(Math.round(amount / 100));
    expect(a.vwap).toBe(23_010_000);
    // 自檢:算術平均會是 23_050_000(否則本案恆綠)
    expect(a.vwap).not.toBe(23_050_000);
    expect(a.amountMilli).toBe(amount);
    expect(a.volume).toBe(100);
  });

  it("Σv = 0(只有 live 佔位格)→ vwap null(不畫均價線,不編一個 0/0)", () => {
    const a = futuresBarsToAccum({ bars: [], live: { index: 5, p: 23_020_000 }, ...BASE });
    expect(a.vwap).toBeNull();
    expect(a.volume).toBe(0);
    expect(a.minutes.size).toBe(1);
  });

  it("last 三態:live → live.p;無 live → 序列末格 c;空 → null", () => {
    const bars = [bar("2026-08-18 15:01", { c: 23_000_000 }), bar("2026-08-19 00:00", { c: 22_960_000 })];
    expect(futuresBarsToAccum({ bars, live: null, ...BASE }).last).toEqual({
      p: 22_960_000,
      t: "",
      cum_vol: 0,
    });
    expect(
      futuresBarsToAccum({ bars, live: { index: 400, p: 22_980_000 }, ...BASE }).last,
    ).toEqual({ p: 22_980_000, t: "", cum_vol: 0 });
    expect(futuresBarsToAccum({ bars: [], live: null, ...BASE }).last).toBeNull();
  });

  it("meta:name / ref 透傳,upper / lower / y_vol 一律 null(→ 對稱 autofit 域)", () => {
    const a = futuresBarsToAccum({ bars: [bar("2026-08-18 15:01")], live: null, ...BASE });
    expect(a.meta).toEqual({ name: "台指近", ref: 23_000_000, upper: null, lower: null, y_vol: null });
    expect(a.code).toBe("TXF.HOT");
  });

  it("ref null 原樣透傳(core 走 hasRef=false 單色線)", () => {
    const a = futuresBarsToAccum({ bars: [bar("2026-08-18 15:01")], live: null, ...BASE, ref: null });
    expect(a.meta?.ref).toBeNull();
  });

  it("vp:key = 5 點桶心 `snapDown(c) + tickOf(c)/2`,同桶累加 t / o / i", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01", { c: 23_000_000, v: 10, uv: 6, dv: 3 }),
        bar("2026-08-18 15:02", { c: 23_002_000, v: 5, uv: 1, dv: 4 }), // 同一個 5 點桶
        bar("2026-08-18 15:03", { c: 23_006_000, v: 7, uv: 7, dv: 0 }), // 下一個桶
      ],
      live: null,
      ...BASE,
    });
    expect([...a.vp.keys()].sort((x, y) => x - y)).toEqual([23_002_500, 23_007_500]);
    expect(a.vp.get(23_002_500)).toEqual({ t: 15, o: 7, i: 7 });
    expect(a.vp.get(23_007_500)).toEqual({ t: 7, o: 7, i: 0 });
  });

  it("c <= 0(TC4 偶發 \"0\")→ 不進 minutes、不進 vp、不拉走 low / vwap", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01", { c: 23_000_000, v: 10 }),
        bar("2026-08-18 15:02", { c: 0, h: 0, l: 0, v: 4 }),
        bar("2026-08-18 15:03", { c: 23_010_000, v: 10 }),
      ],
      live: null,
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([0, 2]);
    expect(a.low).toBe(23_000_000);
    expect(a.vwap).toBe(23_005_000);
    expect(a.vp.size).toBe(2);
  });

  it("h / l 為 0(TC4 只壞一欄)→ 以該分鐘收盤頂替,不讓 0 進 accum.low 把日低標記與對稱域拉走(cr1 A-2)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01", { c: 23_000_000, h: 23_010_000, l: 0, v: 5 }),
        bar("2026-08-18 15:02", { c: 22_990_000, h: 0, l: 22_980_000, v: 5 }),
      ],
      live: null,
      ...BASE,
    });
    expect(a.minutes.get(0)!.l).toBe(23_000_000);
    expect(a.minutes.get(1)!.h).toBe(22_990_000);
    expect(a.high).toBe(23_010_000);
    expect(a.low).toBe(22_980_000);
  });

  it("末根 bar c=0 且 live 同索引 → 該 bar 已被 c<=0 閘略過,live 走佔位格 v=0(刻意:c=0 的分鐘本就不該報量;cr1 B-4)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 15:01", { v: 3, uv: 2, dv: 1 }),
        bar("2026-08-18 15:02", { c: 0, v: 9, uv: 5, dv: 4 }),
      ],
      live: { index: 1, p: 23_005_000 },
      ...BASE,
    });
    expect(a.minutes.get(1)).toEqual({ c: 23_005_000, v: 0, o: 0, i: 0, u: 0, h: 23_005_000, l: 23_005_000 });
    expect(a.volume).toBe(3);
  });

  it("空 bars 且無 live → 空 Map、vwap / high / low / last 皆 null", () => {
    const a = futuresBarsToAccum({ bars: [], live: null, ...BASE });
    expect(a.minutes.size).toBe(0);
    expect(a.vwap).toBeNull();
    expect(a.high).toBeNull();
    expect(a.low).toBeNull();
    expect(a.last).toBeNull();
  });

  it("其餘欄位固定:seq 0 / ticks 空 / book null / noData false / trial false", () => {
    const a = futuresBarsToAccum({ bars: [bar("2026-08-18 15:01")], live: null, ...BASE });
    expect(a.seq).toBe(0);
    expect(a.ticks).toEqual([]);
    expect(a.book).toBeNull();
    expect(a.noData).toBe(false);
    expect(a.trial).toBe(false);
  });

  it("minutes 依軸索引升冪(日盤 bar 排在夜盤之後,live 補格插在正確位置;橋在 1064)", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-19 08:46"), bar("2026-08-18 15:01")],
      live: { index: 100, p: 23_020_000 },
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([0, 100, 1064, 1065]);
  });
});

/** mod/futures-day-1500 Q9(a):05:00 → 08:45 空檔畫**水平線**,靠在 08:45(`ALLDAY_GAP.end`)補一格
 *  取夜盤末格收盤的橋;core 的單條 polyline 就會從 05:00 平走到 08:45、再跳到 08:46。
 *  橋只在**兩側都有格**時才補(user 拍板:日盤第一筆到了才畫,不跟牆鐘延伸)。 */
describe("futuresBarsToAccum 空檔水平橋", () => {
  it("夜盤側 + 日盤側都有 → 1064 補一格:c = 夜盤末格 c、v=0、h/l=null;不進 vp / Σ / high-low", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 22:00", { c: 23_100_000, h: 23_150_000, l: 23_050_000, v: 3 }),
        bar("2026-08-19 05:00", { c: 22_900_000, h: 22_950_000, l: 22_850_000, v: 2 }),
        bar("2026-08-19 08:46", { c: 23_300_000, h: 23_350_000, l: 23_250_000, v: 5 }),
      ],
      live: null,
      ...BASE,
    });
    // 22:00 = 0 + (1320 − 901) = 419;橋 = 空檔末格 08:45 = 539 + 301 + 225 − 1 = 1064(字面,不由 ALLDAY_GAP 算回)
    expect([...a.minutes.keys()]).toEqual([419, 839, 1064, 1065]);
    expect(a.minutes.get(1064)).toEqual({ c: 22_900_000, v: 0, o: 0, i: 0, u: 0, h: null, l: null });
    // 橋不是成交:量 / 金額 / 價位別量 / 高低都不含它
    expect(a.volume).toBe(10);
    expect(a.amountMilli).toBe(23_100_000 * 3 + 22_900_000 * 2 + 23_300_000 * 5);
    expect([...a.vp.values()].reduce((s, c) => s + c.t, 0)).toBe(10);
    expect(a.high).toBe(23_350_000);
    expect(a.low).toBe(22_850_000);
    // 末格仍是日盤那根(橋插在中間)
    expect(a.last).toEqual({ p: 23_300_000, t: "", cum_vol: 0 });
  });

  it("只有夜盤側(日盤未開)→ 不補橋,線停在 05:00", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-18 22:00"), bar("2026-08-19 05:00")],
      live: null,
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([419, 839]);
  });

  it("只有日盤側 → 不補橋(沒有夜盤末價可延伸)", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-19 08:46"), bar("2026-08-19 09:00")],
      live: null,
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([1065, 1079]);
  });

  it("日盤側只有 live 佔位格(08:45:30 第一筆成交、1K 未回)也算「日盤已開」→ 補橋", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-19 05:00", { c: 22_900_000 })],
      live: { index: 1065, p: 22_950_000 },
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([839, 1064, 1065]);
    expect(a.minutes.get(1064)!.c).toBe(22_900_000);
    expect(a.minutes.get(1065)!.c).toBe(22_950_000);
  });
});
