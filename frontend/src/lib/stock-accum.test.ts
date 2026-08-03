import { describe, expect, it } from "vitest";

import { applyTick, fromSnapshot, type StockAccum } from "@/lib/stock-accum";

const SNAP = {
  code: "2330",
  seq: 3,
  last: { p: 2_380_000, t: "09:01:30.000", cum_vol: 10 },
  vwap: 2_380_000,
  minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0 } },
  ticks: [{ t: "09:01:30.000", p: 2_380_000, q: 10, side: "outer" }],
  book: { bids: [[2_375_000, 5]] as [number, number][], asks: [[2_380_000, 7]] as [number, number][] },
  meta: { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 },
  no_data: false,
};

describe("fromSnapshot", () => {
  it("maps snapshot into accum state", () => {
    const acc = fromSnapshot(SNAP);
    expect(acc.seq).toBe(3);
    expect(acc.last?.p).toBe(2_380_000);
    expect(acc.vwap).toBe(2_380_000);
    expect(acc.minutes.get(541)?.v).toBe(10);
    expect(acc.ticks.length).toBe(1);
    expect(acc.meta?.name).toBe("台積電");
  });
});

describe("當日高低與逐筆買賣價(round5 §🔴-11)", () => {
  it("snapshot 的 high / low 讀 top-level(不是 meta)", () => {
    const acc = fromSnapshot({ ...SNAP, high: 2_395_000, low: 2_370_000 });
    expect(acc.high).toBe(2_395_000);
    expect(acc.low).toBe(2_370_000);
  });

  it("snapshot 缺欄位(舊後端)→ null,不崩", () => {
    const acc = fromSnapshot(SNAP);
    expect(acc.high).toBeNull();
    expect(acc.low).toBeNull();
  });

  it("snapshot 的 ticks 帶買賣價", () => {
    const acc = fromSnapshot({
      ...SNAP,
      ticks: [{ t: "09:01:30.000", p: 2_380_000, q: 10, side: "outer", b: 2_379_000, a: 2_380_000 }],
    });
    expect(acc.ticks[0]?.b).toBe(2_379_000);
    expect(acc.ticks[0]?.a).toBe(2_380_000);
  });

  it("tick 的 h / l 增量更新當日高低(WS 不發 meta 型別訊息)", () => {
    let acc = fromSnapshot({ ...SNAP, high: 2_380_000, low: 2_380_000 });
    acc = applyTick(acc, {
      type: "tick", code: "2330", t: "09:02:00.000", p: 2_395_000, q: 1, side: "outer",
      seq: 4, b: 2_394_000, a: 2_395_000, h: 2_395_000, l: 2_380_000,
    });
    expect(acc.high).toBe(2_395_000);
    expect(acc.low).toBe(2_380_000);
    expect(acc.ticks.at(-1)?.b).toBe(2_394_000);
    expect(acc.ticks.at(-1)?.a).toBe(2_395_000);
  });

  it("tick 缺 h / l(舊後端)→ 保留原值,不打成 null", () => {
    let acc = fromSnapshot({ ...SNAP, high: 2_390_000, low: 2_370_000 });
    acc = applyTick(acc, {
      type: "tick", code: "2330", t: "09:02:00.000", p: 2_380_000, q: 1, side: "outer", seq: 4,
    });
    expect(acc.high).toBe(2_390_000);
    expect(acc.low).toBe(2_370_000);
  });
});

describe("per-minute 高低(round4 項 1)", () => {
  it("snapshot 帶 h / l → 原樣進 minutes", () => {
    const acc = fromSnapshot({
      ...SNAP,
      minutes: { "541": { c: 2_380_000, v: 10, i: 0, o: 10, u: 0, h: 2_395_000, l: 2_370_000 } },
    });
    expect(acc.minutes.get(541)?.h).toBe(2_395_000);
    expect(acc.minutes.get(541)?.l).toBe(2_370_000);
  });

  it("snapshot 缺 h / l(舊後端)→ null,**不拿 c 頂替**", () => {
    // 頂替會讓「minute.h === accum.high」的等值反查命中錯的分鐘 = 靜默標錯位置;
    // null 則讓反查落空 → 標記不畫(誠實降級)
    const acc = fromSnapshot(SNAP);
    expect(acc.minutes.get(541)?.h).toBeNull();
    expect(acc.minutes.get(541)?.l).toBeNull();
  });

  it("applyTick 在同一分鐘內滾動 h / l", () => {
    let acc = fromSnapshot({ ...SNAP, minutes: {}, ticks: [], last: null, vwap: null });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:10.000", p: 2_380_000, q: 1, side: "outer", seq: 4 });
    expect(acc.minutes.get(541)?.h).toBe(2_380_000);
    expect(acc.minutes.get(541)?.l).toBe(2_380_000); // 單筆分鐘:高 = 低 = 該筆
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:30.000", p: 2_395_000, q: 1, side: "outer", seq: 5 });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:50.000", p: 2_370_000, q: 1, side: "inner", seq: 6 });
    expect(acc.minutes.get(541)?.h).toBe(2_395_000);
    expect(acc.minutes.get(541)?.l).toBe(2_370_000);
    expect(acc.minutes.get(541)?.c).toBe(2_370_000); // 收盤與高低分離
  });

  it("舊 snapshot 來的分鐘(h=null 且 v>0)再吃 tick → h 仍為 null", () => {
    // 只用「本次載入後看到的 tick」算出來的高低不是整分鐘的高低,不可冒充
    let acc = fromSnapshot(SNAP); // 541 有量、無 h/l
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:55.000", p: 2_390_000, q: 1, side: "outer", seq: 4 });
    expect(acc.minutes.get(541)?.h).toBeNull();
    expect(acc.minutes.get(541)?.l).toBeNull();
  });
});

describe("applyTick", () => {
  it("accumulates minutes, vwap and inner/outer(與後端 StockDayState 等值)", () => {
    // 後端 tests/live/test_stock_state.py::TestAggregation 同一組數字
    let acc: StockAccum = fromSnapshot({ ...SNAP, seq: 1, minutes: {}, ticks: [], last: null, vwap: null });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:30.000", p: 2_380_000, q: 10, side: "outer", seq: 2 });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:01:59.000", p: 2_390_000, q: 4, side: "inner", seq: 3 });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:02:10.000", p: 2_400_000, q: 6, side: "outer", seq: 4 });
    const m1 = acc.minutes.get(541);
    expect(m1?.c).toBe(2_390_000);
    expect(m1?.v).toBe(14);
    expect(m1?.o).toBe(10);
    expect(m1?.i).toBe(4);
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

  it("vwap 分母種子取 snapshot 的 vwap_vol(不是 last.cum_vol)", () => {
    // 後端 vwap 分母 = `_volume`(去重剔試撮後的 Σqty),與 `last.cum_vol`
    // (TC4 累積量)是兩個口徑;拿錯的當分母不會報錯,只會靜默偏移。
    // 欄名 `vwap_vol` 不可退回 `vol`(FC-2):WS `watchlist_quote` 的 `vol` 正是
    // 累積量,同名反義的兩個欄位同時在前端手上就是誤用的溫床。
    let acc = fromSnapshot({ ...SNAP, vwap: 100_000, last: { p: 100_000, t: "09:01:30.000", cum_vol: 80 }, vwap_vol: 50 });
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:03:00.000", p: 200_000, q: 10, side: "outer", seq: 4 });
    // 正確:(100_000×50 + 200_000×10) / (50+10) = 116_667
    // 讀 cum_vol 的錯誤實作:(100_000×80 + 200_000×10) / 90 = 111_111
    expect(acc.vwap).toBe(Math.round((100_000 * 50 + 200_000 * 10) / 60));
  });

  it("snapshot 無 vwap_vol(舊後端)→ fallback last.cum_vol", () => {
    let acc = fromSnapshot(SNAP); // vwap 2380, cum_vol 10, 無 vwap_vol
    acc = applyTick(acc, { type: "tick", code: "2330", t: "09:03:00.000", p: 2_400_000, q: 10, side: "outer", seq: 4 });
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
