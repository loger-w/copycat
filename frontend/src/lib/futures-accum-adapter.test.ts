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
  it("bar 時戳 → 軸索引當 key;死區 bar 略過(軸上沒有那一分鐘)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 08:46"),
        bar("2026-08-18 14:00"), // 死區:13:46–15:00
        bar("2026-08-18 15:01"),
      ],
      live: null,
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([0, 300]);
    expect(alldayIndexOf("1501")).toBe(300);
  });

  it("uv / dv → o / i,u = v − uv − dv;缺欄(DK 路徑)→ o=i=0、u=v(判定率 0% 誠實呈現)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 08:46", { v: 100, uv: 60, dv: 30 }),
        bar("2026-08-18 08:47", { v: 50 }),
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
      bars: [bar("2026-08-18 08:46", { v: 10, uv: 9, dv: 8 })],
      live: null,
      ...BASE,
    });
    expect(a.minutes.get(0)!.u).toBe(0);
  });

  it("h / l 逐欄透傳(tick 級極值,高低標記等值反查必命中)", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 08:46", { c: 23_000_000, h: 23_030_000, l: 22_990_000 }),
        bar("2026-08-18 08:47", { c: 23_010_000, h: 23_040_000, l: 22_980_000 }),
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
      bars: [bar("2026-08-18 08:46", { c: 23_000_000, h: 23_010_000, l: 22_990_000, v: 12 })],
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
      bars: [bar("2026-08-18 08:46", { v: 12 })],
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
        bar("2026-08-18 08:46", { c: 23_000_000, v: 90 }),
        bar("2026-08-18 08:47", { c: 23_100_000, v: 10 }),
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
    const bars = [bar("2026-08-18 08:46", { c: 23_000_000 }), bar("2026-08-18 15:01", { c: 22_960_000 })];
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
    const a = futuresBarsToAccum({ bars: [bar("2026-08-18 08:46")], live: null, ...BASE });
    expect(a.meta).toEqual({ name: "台指近", ref: 23_000_000, upper: null, lower: null, y_vol: null });
    expect(a.code).toBe("TXF.HOT");
  });

  it("ref null 原樣透傳(core 走 hasRef=false 單色線)", () => {
    const a = futuresBarsToAccum({ bars: [bar("2026-08-18 08:46")], live: null, ...BASE, ref: null });
    expect(a.meta?.ref).toBeNull();
  });

  it("vp:key = 5 點桶心 `snapDown(c) + tickOf(c)/2`,同桶累加 t / o / i", () => {
    const a = futuresBarsToAccum({
      bars: [
        bar("2026-08-18 08:46", { c: 23_000_000, v: 10, uv: 6, dv: 3 }),
        bar("2026-08-18 08:47", { c: 23_002_000, v: 5, uv: 1, dv: 4 }), // 同一個 5 點桶
        bar("2026-08-18 08:48", { c: 23_006_000, v: 7, uv: 7, dv: 0 }), // 下一個桶
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
        bar("2026-08-18 08:46", { c: 23_000_000, v: 10 }),
        bar("2026-08-18 08:47", { c: 0, h: 0, l: 0, v: 4 }),
        bar("2026-08-18 08:48", { c: 23_010_000, v: 10 }),
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
        bar("2026-08-18 08:46", { c: 23_000_000, h: 23_010_000, l: 0, v: 5 }),
        bar("2026-08-18 08:47", { c: 22_990_000, h: 0, l: 22_980_000, v: 5 }),
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
        bar("2026-08-18 08:46", { v: 3, uv: 2, dv: 1 }),
        bar("2026-08-18 08:47", { c: 0, v: 9, uv: 5, dv: 4 }),
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
    const a = futuresBarsToAccum({ bars: [bar("2026-08-18 08:46")], live: null, ...BASE });
    expect(a.seq).toBe(0);
    expect(a.ticks).toEqual([]);
    expect(a.book).toBeNull();
    expect(a.noData).toBe(false);
    expect(a.trial).toBe(false);
  });

  it("minutes 依軸索引升冪(夜盤 bar 排在日盤之後,live 補格插在正確位置)", () => {
    const a = futuresBarsToAccum({
      bars: [bar("2026-08-18 15:01"), bar("2026-08-18 08:46")],
      live: { index: 100, p: 23_020_000 },
      ...BASE,
    });
    expect([...a.minutes.keys()]).toEqual([0, 100, 300]);
  });
});
