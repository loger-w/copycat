import { describe, expect, it } from "vitest";

import { chgPct, fmtIndexPts, fmtPct, formatNtd, formatPts, monthDay } from "@/lib/format";

describe("formatNtd", () => {
  it("億級縮寫", () => {
    expect(formatNtd(45_050_126)).toBe("NT$ 4,505萬");
    expect(formatNtd(3_054_064_316)).toBe("NT$ 30.54億");
  });
  it("負值帶號", () => {
    expect(formatNtd(-1_852_600)).toBe("-NT$ 185萬");
  });
  it("萬以下千分位", () => {
    expect(formatNtd(9_500)).toBe("NT$ 9,500");
    expect(formatNtd(0)).toBe("NT$ 0");
  });
});

describe("formatPts", () => {
  it("整數點位千分位", () => {
    expect(formatPts(43513)).toBe("43,513");
  });
  it("小數保留一位", () => {
    expect(formatPts(44300.4)).toBe("44,300.4");
  });
});

describe("fmtPct", () => {
  it("正值帶 +,負值帶 -", () => {
    expect(fmtPct(1)).toBe("+1.00%");
    expect(fmtPct(-1)).toBe("-1.00%");
  });
  it("平盤不帶號", () => {
    // `v > 0` 而非 `v >= 0` —— 0 走的是「不帶號」分支,原本全 repo 零正向斷言。
    expect(fmtPct(0)).toBe("0.00%");
  });
});

describe("chgPct", () => {
  it("相對參考價的漲跌百分比", () => {
    expect(chgPct(40_400_000, 40_000_000)).toBeCloseTo(1);
  });
});

describe("fmtIndexPts(指數軸帶價位口徑)", () => {
  it("超過 6 字(加權五位數帶小數)收整數點;6 字以內(櫃買 / 個股量級)保留 fmt 小數", () => {
    expect(fmtIndexPts(24_283_540)).toBe("24284");
    expect(fmtIndexPts(24_300_000)).toBe("24300");
    expect(fmtIndexPts(238_970)).toBe("238.97");
    expect(fmtIndexPts(1_005_000)).toBe("1005");
    expect(fmtIndexPts(1_234_560)).toBe("1235");
  });
});

// [lock] review TQ-7:`monthDay` 從 LimitList 抽到 lib(SC-10)後成為兩個消費端
// (漲跌停列表 + SignalRail 標題)的共用點,而它的**形狀守門**原本零測試 ——
// 把 regex 拿掉、或把 `slice(5)` 改成 `slice(4)` / `substring(5, 10)` 全綠。
// 守門的理由:形狀不合就原樣印出來(寧可醜也不要靜默切錯字串),而「切錯」在畫面上
// 長得像一個正常的日期。
describe("monthDay", () => {
  it("`YYYY-MM-DD` → `MM-DD`", () => {
    expect(monthDay("2026-08-20")).toBe("08-20");
  });
  it("空字串原樣回(缺值的形之一,呼叫端據此退回「今日訊號」)", () => {
    expect(monthDay("")).toBe("");
  });
  it("斜線分隔(形狀不合)原樣回,不切", () => {
    expect(monthDay("2026/08/20")).toBe("2026/08/20");
  });
});
