import { afterEach, describe, expect, it, vi } from "vitest";

import {
  accumFromGroupSnapshot,
  applyTick,
  extendMinutes,
  fromSnapshot,
  type MinuteAgg,
  type StockAccum,
  type StockTickMsg,
} from "@/lib/stock-accum";
import { sideSummary } from "@/lib/stock-intraday-svg";

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

// 🟢 緩撮旗標(SC-2 的種子)。snapshot 是主圖 accum 的基底 —— 開頁就在窗內時
// badge 要立刻在,不能等到下一則 watchlist_quote 才亮。
describe("fromSnapshot 的 trial", () => {
  it("snapshot 帶 trial → 原樣帶入", () => {
    expect(fromSnapshot({ ...SNAP, trial: true }).trial).toBe(true);
  });

  it("snapshot 缺 trial(舊後端)→ false,不是 undefined", () => {
    const acc = fromSnapshot(SNAP);
    expect(acc.trial).toBe(false);
  });

  it("applyTick 保留 trial(tick 不帶這個欄位,spread 不可漏)", () => {
    const acc = fromSnapshot({ ...SNAP, trial: true });
    const next = applyTick(acc, {
      type: "tick", code: "2330", t: "09:02:00.000", p: 2_385_000, q: 1, side: "outer", seq: 4,
    });
    expect(next.trial).toBe(true);
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

/** VP(價位別成交量)fold — SC-1。
 *
 *  fold **先於 tape 截斷**:tape 只留最後 200 筆是顯示需求,VP 要的是「全日」。
 *  兩者共用同一批 tick,所以測試同時鎖住「vp 收到 300 筆」與「ticks 仍是 200 筆」。 */
describe("vp(價位別成交量 fold,SC-1)", () => {
  const tick = (over: Partial<StockTickMsg> = {}): StockTickMsg => ({
    type: "tick",
    code: "2330",
    t: "09:01:30.000",
    p: 2_380_000,
    q: 1,
    side: "outer",
    seq: 1,
    ...over,
  });

  it("fromSnapshot 對原始全量 ticks fold(tape 截斷之前)", () => {
    // 300 筆:前 100 筆在 238.0、後 200 筆在 239.0(皆為合法檔位)
    const ticks = Array.from({ length: 300 }, (_, i) => ({
      t: "09:01:30.000",
      p: i < 100 ? 2_380_000 : 2_390_000,
      q: 2,
      side: "outer",
    }));
    const acc = fromSnapshot({ ...SNAP, ticks });
    expect(acc.ticks.length).toBe(200); // tape 行為不變
    const total = [...acc.vp.values()].reduce((s, c) => s + c.t, 0);
    expect(total).toBe(600); // 300 筆 × 2 張,全數入 vp
    expect(acc.vp.get(2_380_000)?.t).toBe(200);
    expect(acc.vp.get(2_390_000)?.t).toBe(400);
  });

  it("applyTick 在同一檔位上增量累加", () => {
    let acc = fromSnapshot({ ...SNAP, ticks: [] });
    expect(acc.vp.size).toBe(0);
    acc = applyTick(acc, tick({ p: 2_380_000, q: 3, seq: 4 }));
    acc = applyTick(acc, tick({ p: 2_380_000, q: 5, seq: 5 }));
    acc = applyTick(acc, tick({ p: 2_390_000, q: 7, seq: 6 }));
    expect(acc.vp.get(2_380_000)?.t).toBe(8);
    expect(acc.vp.get(2_390_000)?.t).toBe(7);
  });

  it("applyTick 不就地改動前一份 vp(memo 比較與時間旅行安全)", () => {
    const base = fromSnapshot({ ...SNAP, ticks: [] });
    const next = applyTick(base, tick({ p: 2_380_000, q: 3, seq: 4 }));
    expect(base.vp.size).toBe(0);
    expect(next.vp.size).toBe(1);
    expect(next.vp).not.toBe(base.vp);
  });

  it("p <= 0(市價偽價位)不入 vp", () => {
    // 鎖漲跌停時 TC4 的市價佇列價格欄是 0;snapDown(0) 會產生一個假檔位
    let acc = fromSnapshot({ ...SNAP, ticks: [{ t: "09:01:30.000", p: 0, q: 9, side: "outer" }] });
    expect(acc.vp.size).toBe(0);
    acc = applyTick(acc, tick({ p: 0, q: 9, seq: 4 }));
    expect(acc.vp.size).toBe(0);
  });

  it("非合法檔位的成交價 snapDown 到檔位", () => {
    // 2383 元 → 2380 元(≥1000 元帶 tick = 5 元,2383 不是合法檔位)
    const acc = fromSnapshot({
      ...SNAP,
      ticks: [{ t: "09:01:30.000", p: 2_383_000, q: 4, side: "outer" }],
    });
    expect(acc.vp.get(2_380_000)?.t).toBe(4);
    expect(acc.vp.get(2_383_000)).toBeUndefined();
  });

  it("窗外([09:00, 13:30] 外)的成交不入 vp", () => {
    const acc = fromSnapshot({
      ...SNAP,
      ticks: [
        { t: "08:59:59.000", p: 2_380_000, q: 11, side: "outer" }, // 盤前試撮
        { t: "13:31:00.000", p: 2_380_000, q: 13, side: "outer" }, // 收盤後
        { t: "09:00:00.000", p: 2_380_000, q: 1, side: "outer" }, // 窗邊界(含)
        { t: "13:30:59.000", p: 2_380_000, q: 1, side: "outer" }, // 窗邊界(含)
      ],
    });
    expect(acc.vp.get(2_380_000)?.t).toBe(2);
  });

  // 🔴 review A3:窗過濾要用**正向條件的否定**(`!(m >= START && m <= END)`),
  // 不是 `m < START || m > END`。後者對 NaN 的兩個比較都是 false → 壞掉的時間戳
  // 整筆漏進 vp,而畫面上只是多一根對不上任何分鐘的長條(說明列三數和與 VP 總張
  // 靜默岔開)。`windowedEntries` / `sideSummary` 用的是 filter 的正向式,天然沒這問題。
  it("分鐘鍵解不出(NaN)的 tick 不入 vp", () => {
    let acc = fromSnapshot({
      ...SNAP,
      ticks: [{ t: "xx:yy:00.000", p: 2_380_000, q: 9, side: "outer" }],
    });
    expect(acc.vp.size).toBe(0);
    acc = applyTick(acc, tick({ t: "xx:yy:00.000", p: 2_380_000, q: 9, seq: 4 }));
    expect(acc.vp.size).toBe(0);
  });

  it("side 拆分:outer/inner 各自進 o/i,其餘只進 t", () => {
    const acc = fromSnapshot({
      ...SNAP,
      ticks: [
        { t: "09:01:30.000", p: 2_380_000, q: 10, side: "outer" },
        { t: "09:01:31.000", p: 2_380_000, q: 4, side: "inner" },
        { t: "09:01:32.000", p: 2_380_000, q: 6, side: "neutral" },
      ],
    });
    expect(acc.vp.get(2_380_000)).toEqual({ t: 20, o: 10, i: 4 });
  });

  it("R3 一致性鎖:Σ vp[*].t === sideSummary(minutes) 的 外+內+未分類", () => {
    // minutes 與 vp 同源(同一批 tick 走 applyTick),兩者套的是同一把窗尺
    // ([09:00, 13:30])→ 總張必然相等。這條同時鎖住:
    //   (a) foldVp 的窗與 windowedEntries / sideSummary 不會各漂各的;
    //   (b) 後端 20k tick deque 截斷時,snapshot 的 minutes 完整而 ticks 缺角 →
    //       兩數岔開,說明列與 VP 對不上就會被這條的同構造版本間接暴露。
    const batch: StockTickMsg[] = [
      { type: "tick", code: "2330", t: "08:59:00.000", p: 2_380_000, q: 50, side: "outer", seq: 1 },
      { type: "tick", code: "2330", t: "09:00:00.000", p: 2_380_000, q: 10, side: "outer", seq: 2 },
      { type: "tick", code: "2330", t: "09:01:30.000", p: 2_385_000, q: 4, side: "inner", seq: 3 },
      { type: "tick", code: "2330", t: "10:00:00.000", p: 2_390_000, q: 6, side: "neutral", seq: 4 },
      { type: "tick", code: "2330", t: "13:30:00.000", p: 2_400_000, q: 3, side: "outer", seq: 5 },
      { type: "tick", code: "2330", t: "13:35:00.000", p: 2_400_000, q: 90, side: "outer", seq: 6 },
    ];
    let acc = fromSnapshot({ ...SNAP, minutes: {}, ticks: [], last: null, vwap: null });
    for (const m of batch) acc = applyTick(acc, m);
    const s = sideSummary(acc.minutes);
    const vpTotal = [...acc.vp.values()].reduce((sum, c) => sum + c.t, 0);
    expect(vpTotal).toBe(s.outer + s.inner + s.unch);
    expect(vpTotal).toBe(23); // 窗內 10 + 4 + 6 + 3;窗外 50 / 90 皆不計
  });

  // 🟢 review B1:上一條的「VP 總張 = 說明列三數和」只在 **applyTick 路徑**(前端自己
  // 從頭累起)恆成立。`fromSnapshot` 路徑不成立 —— 後端 tick deque 上限 20,000
  // (`stock_state.py::_TICKS_MAXLEN`),超界時 snapshot 的 `minutes` 仍是**完整日聚合**
  // 而 `ticks` 只剩尾段,VP 會靜默缺早盤那一角。
  //
  // 這條是 **characterization**:把「兩數會岔開」釘成已知且刻意接受的行為(design
  // Known Risks;零後端改動拍板),而不是宣稱它相等。真要修是後端補一份價位直方圖,
  // 屆時這條會紅 —— 那正是它該提醒的時機。
  it("fromSnapshot 的 20k 截斷簽名:vp 總張 < 說明列三數和(B1 characterization)", () => {
    const acc = fromSnapshot({
      ...SNAP,
      // 完整日聚合(後端 minutes 不受 tick deque 影響)
      minutes: {
        "540": { c: 2_380_000, v: 500, i: 200, o: 300, u: 0 }, // 早盤,對應 tick 已被砍頭
        "541": { c: 2_385_000, v: 30, i: 10, o: 20, u: 0 },
      },
      // deque 砍頭後只剩尾段的兩筆
      ticks: [
        { t: "09:01:10.000", p: 2_385_000, q: 20, side: "outer" },
        { t: "09:01:20.000", p: 2_385_000, q: 10, side: "inner" },
      ],
    });
    const vpTotal = [...acc.vp.values()].reduce((sum, c) => sum + c.t, 0);
    const s = sideSummary(acc.minutes);
    expect(vpTotal).toBe(30); // fromSnapshot 路徑:vp 與**手上這批 ticks** 合計一致
    expect(s.outer + s.inner + s.unch).toBe(530);
    expect(vpTotal).toBeLessThan(s.outer + s.inner + s.unch); // ← 截斷簽名
  });
});

// R10 延伸規則:分鐘鍵 = 本機時鐘分鐘,僅當落在 [09:00, 13:30] 且 liveP > 0 才延伸。
// (自 `components/stock/MiniIntradayChart.test.tsx` 原樣搬家 —— 函式本體已移入本檔
//  所屬模組;元件層「延伸後的點真的畫進走勢線」那條需要 jsdom,留在原檔。)
describe("extendMinutes(R10 現價延伸)", () => {
  const at = (h: number, m: number) => new Date(2026, 7, 6, h, m, 30);

  it("既有 bucket → 只覆寫 c,量與高低原樣", () => {
    const src = new Map<number, MinuteAgg>([
      [600, { c: 2_300_000, v: 12, i: 5, o: 6, u: 1, h: 2_310_000, l: 2_295_000 }],
    ]);
    const out = extendMinutes(src, 2_345_000, at(10, 0));
    expect(out.get(600)).toEqual({
      c: 2_345_000,
      v: 12,
      i: 5,
      o: 6,
      u: 1,
      h: 2_310_000,
      l: 2_295_000,
    });
    // 淺拷不就地改:原 Map 不可被污染
    expect(src.get(600)?.c).toBe(2_300_000);
  });

  it("無 bucket → 新建零量點(h/l 為 null,不冒充)", () => {
    const out = extendMinutes(new Map(), 2_345_000, at(10, 0));
    expect(out.get(600)).toEqual({ c: 2_345_000, v: 0, i: 0, o: 0, u: 0, h: null, l: null });
  });

  it("窗外時刻(13:31 之後 / 09:00 之前)不延伸", () => {
    const src = new Map<number, MinuteAgg>([[600, { c: 2_300_000, v: 1, i: 0, o: 1, u: 0 }]]);
    expect(extendMinutes(src, 2_345_000, at(14, 0))).toBe(src);
    expect(extendMinutes(src, 2_345_000, at(8, 50))).toBe(src);
  });

  it("liveP 為 null / 0 / 負 → 不延伸(0 是 TC4 的「不可得」不是價格)", () => {
    const src = new Map<number, MinuteAgg>([[600, { c: 2_300_000, v: 1, i: 0, o: 1, u: 0 }]]);
    expect(extendMinutes(src, null, at(10, 0))).toBe(src);
    expect(extendMinutes(src, 0, at(10, 0))).toBe(src);
    expect(extendMinutes(src, -5, at(10, 0))).toBe(src);
  });
});

/** 群組卡片的 accum 組裝(change-spec §6 A)。卡片走 `/api/stock/group-state` 的精簡
 *  snapshot(沒有 ticks),而 `IntradayChartCore` 吃的是 `StockAccum` —— 這支把前者
 *  補成後者。缺鍵一律降級成「不可得」而不是猜:舊後端還沒送 vwap/high/low/vp 時,
 *  卡片應該少畫那幾層,而不是拿分鐘資料近似出一份與單檔頁不同的數字。 */
describe("accumFromGroupSnapshot", () => {
  const at = (h: number, m: number, s: number) => new Date(2026, 7, 6, h, m, s);
  const META = { name: "台積電", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 100 };
  const MIN = (): Map<number, MinuteAgg> =>
    new Map<number, MinuteAgg>([
      [540, { c: 2_330_000, v: 10, i: 4, o: 6, u: 0, h: 2_335_000, l: 2_325_000 }],
      [541, { c: 2_340_000, v: 5, i: 1, o: 4, u: 0, h: null, l: null }],
    ]);

  afterEach(() => {
    vi.useRealTimers();
  });

  it("缺鍵(舊後端)→ vwap/high/low 為 null、vp 空 Map,其餘欄位取零值", () => {
    const acc = accumFromGroupSnapshot(
      "2330",
      { minutes: MIN(), meta: META, noData: false },
      null,
    );
    expect(acc.code).toBe("2330");
    expect(acc.vwap).toBeNull();
    expect(acc.high).toBeNull();
    expect(acc.low).toBeNull();
    expect(acc.vp.size).toBe(0);
    expect(acc.ticks).toEqual([]);
    expect(acc.book).toBeNull();
    expect(acc.seq).toBe(0);
    expect(acc.trial).toBe(false);
    expect(acc.amountMilli).toBe(0);
    expect(acc.volume).toBe(0);
    expect(acc.noData).toBe(false);
    expect(acc.meta).toBe(META);
  });

  it("新後端四鍵齊 → 原樣帶入(不重算、不近似)", () => {
    const vp = new Map([[2_330_000, { t: 10, o: 6, i: 4 }]]);
    const acc = accumFromGroupSnapshot(
      "2330",
      {
        minutes: MIN(),
        meta: META,
        noData: false,
        vwap: 2_333_000,
        high: 2_345_000,
        low: 2_320_000,
        vp,
      },
      null,
    );
    expect(acc.vwap).toBe(2_333_000);
    expect(acc.high).toBe(2_345_000);
    expect(acc.low).toBe(2_320_000);
    expect(acc.vp.get(2_330_000)).toEqual({ t: 10, o: 6, i: 4 });
  });

  it("noData 原樣帶入(卡片三態的判準之一)", () => {
    const acc = accumFromGroupSnapshot(
      "9999",
      { minutes: new Map(), meta: null, noData: true },
      null,
    );
    expect(acc.noData).toBe(true);
    expect(acc.meta).toBeNull();
  });

  // last 分支 A:liveP 是每秒都在動的那一份,現價圈與末點要同源(AD-9)
  it("liveP > 0 → last 取 liveP,時間戳是本機時鐘 HH:MM:SS", () => {
    vi.useFakeTimers();
    vi.setSystemTime(at(10, 5, 7));
    const acc = accumFromGroupSnapshot(
      "2330",
      { minutes: MIN(), meta: META, noData: false },
      2_355_000,
    );
    expect(acc.last).toEqual({ p: 2_355_000, t: "10:05:07", cum_vol: 0 });
  });

  // last 分支 B(edge 10):liveP 不可得 → 退回**最後一格**的收盤,不是第一格也不是 null
  it("liveP null / ≤0 → last 退回最大分鐘鍵那格的 close,t 為該分鐘整秒", () => {
    const snap = { minutes: MIN(), meta: META, noData: false };
    expect(accumFromGroupSnapshot("2330", snap, null).last).toEqual({
      p: 2_340_000,
      t: "09:01:00",
      cum_vol: 0,
    });
    // 0 是 TC4 的「不可得」不是價格
    expect(accumFromGroupSnapshot("2330", snap, 0).last?.p).toBe(2_340_000);
  });

  it("liveP 不可得且 minutes 空 → last 為 null(不冒充)", () => {
    const acc = accumFromGroupSnapshot(
      "2330",
      { minutes: new Map(), meta: META, noData: false },
      null,
    );
    expect(acc.last).toBeNull();
  });

  it("minutes 走 extendMinutes:窗內 liveP 多一格,且**不污染**輸入的 Map", () => {
    vi.useFakeTimers();
    vi.setSystemTime(at(10, 0, 30));
    const src = MIN();
    const acc = accumFromGroupSnapshot("2330", { minutes: src, meta: META, noData: false }, 2_355_000);
    expect(acc.minutes.size).toBe(3);
    expect(acc.minutes.get(600)?.c).toBe(2_355_000);
    // 來源是 TQ cache 的物件 —— 被就地改過的話,下一次 render 拿到的「快取」已經髒了
    expect(src.size).toBe(2);
    expect(src.has(600)).toBe(false);
  });

  it("窗外時刻 + liveP > 0 → 分鐘不延伸,但 last 仍是 liveP(現價圈照畫)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(at(14, 30, 0));
    const acc = accumFromGroupSnapshot(
      "2330",
      { minutes: MIN(), meta: META, noData: false },
      2_355_000,
    );
    expect(acc.minutes.size).toBe(2);
    expect(acc.last?.p).toBe(2_355_000);
  });
});

describe("tape_omitted(2026-08-22 review R9 P2)", () => {
  it("fromSnapshot 讀 tape_omitted → tapeOmitted;缺欄(舊後端 / 全量)→ false", () => {
    expect(fromSnapshot({ ...SNAP, ticks: [], tape_omitted: true }).tapeOmitted).toBe(true);
    expect(fromSnapshot(SNAP).tapeOmitted).toBe(false);
  });
});
