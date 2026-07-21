import { describe, expect, it } from "vitest";

import { applyTick, fromSnapshot, type StockAccum } from "@/lib/stock-accum";

const SNAP = {
  code: "2330",
  seq: 3,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 10 },
  vwap: 2_380_000,
  cum_inner: 0,
  cum_outer: 10,
  minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
  ticks: [{ t: "09:01:30.000", p: 2_380_000, q: 10, side: "outer" }],
  book: { bids: [[2_375_000, 5]] as [number, number][], asks: [[2_380_000, 7]] as [number, number][] },
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_close: 2_320_000, y_vol: 100 },
  no_data: false,
  tc4: "up",
  backfilling: null,
  stkfut_prod: "CDF",
};

describe("fromSnapshot", () => {
  it("maps snapshot into accum state", () => {
    const acc = fromSnapshot(SNAP);
    expect(acc.seq).toBe(3);
    expect(acc.last?.p).toBe(2_380_000);
    expect(acc.vwap).toBe(2_380_000);
    expect(acc.cumOuter).toBe(10);
    expect(acc.minutes.get(541)?.v).toBe(10);
    expect(acc.ticks.length).toBe(1);
    expect(acc.meta?.name).toBe("台積電");
  });
});

describe("applyTick", () => {
  it("accumulates minutes, vwap and inner/outer(與後端 StockDayState 等值)", () => {
    // 後端 tests/live/test_stock_state.py::TestAggregation 同一組數字
    let acc: StockAccum = fromSnapshot({ ...SNAP, seq: 1, minutes: {}, ticks: [], last: null, vwap: null, cum_outer: 0, cum_inner: 0 });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:30.000", p: 2_380_000, q: 10, side: "outer", seq: 2 });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:59.000", p: 2_390_000, q: 4, side: "inner", seq: 3 });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:02:10.000", p: 2_400_000, q: 6, side: "outer", seq: 4 });
    const m1 = acc.minutes.get(541);
    expect(m1?.c).toBe(2_390_000);
    expect(m1?.v).toBe(14);
    expect(m1?.o).toBe(10);
    expect(m1?.i).toBe(4);
    expect(acc.cumOuter).toBe(16);
    expect(acc.cumInner).toBe(4);
    expect(acc.vwap).toBe(2_388_000);
    expect(acc.seq).toBe(4);
    expect(acc.last?.p).toBe(2_400_000);
  });

  it("continues vwap from snapshot baseline", () => {
    let acc = fromSnapshot(SNAP); // vwap 2380, cum_vol 10
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:03:00.000", p: 2_400_000, q: 10, side: "outer", seq: 4 });
    // (2380*10 + 2400*10) / 20 = 2390.0 元
    expect(acc.vwap).toBe(2_390_000);
  });

  it("keeps tick tape bounded to latest 200 rows", () => {
    let acc = fromSnapshot({ ...SNAP, ticks: [] });
    for (let i = 0; i < 250; i++) {
      acc = applyTick(acc, { type: "tick", code: "2330", t: "09:05:00.000", p: 2_380_000, q: 1, side: "neutral", seq: 10 + i });
    }
    expect(acc.ticks.length).toBe(200);
  });
});
