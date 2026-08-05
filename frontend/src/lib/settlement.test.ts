import { describe, expect, it } from "vitest";

import { settlementCountdown, thirdWednesday } from "@/lib/settlement";

describe("thirdWednesday(YYYYMM → YYYY-MM-DD)", () => {
  it("2026-08 的第三週三 = 2026-08-19(月初為週六)", () => {
    expect(thirdWednesday("202608")).toBe("2026-08-19");
  });

  it("2026-09 的第三週三 = 2026-09-16(月初為週二)", () => {
    expect(thirdWednesday("202609")).toBe("2026-09-16");
  });

  it("月初剛好是週三 → 第三週三是 15 日(2026-07)", () => {
    expect(thirdWednesday("202607")).toBe("2026-07-15");
  });

  it("跨年月份照算(2027-01)", () => {
    // 2027-01-01 為週五 → 首個週三是 01-06 → 第三個是 01-20
    expect(thirdWednesday("202701")).toBe("2027-01-20");
  });

  it("壞 YYYYMM 拋錯(與 futExchangeContract 同慣例)", () => {
    expect(() => thirdWednesday("2026")).toThrow();
    expect(() => thirdWednesday("202613")).toThrow();
    expect(() => thirdWednesday("202600")).toThrow();
  });
});

describe("settlementCountdown(週一〜五計數;T-0 = 當天;已過仍 0)", () => {
  it("結算當日 = 0", () => {
    expect(settlementCountdown("202608", "2026-08-19")).toBe(0);
  });

  it("前一交易日 = 1", () => {
    expect(settlementCountdown("202608", "2026-08-18")).toBe(1);
  });

  it("月初(8/3 週一)到 8/19 = 12 個交易日", () => {
    // 8/4-8/7(4)+ 8/10-8/14(5)+ 8/17-8/19(3)
    expect(settlementCountdown("202608", "2026-08-03")).toBe(12);
  });

  it("週末不計:8/15(週六)到 8/19 = 3", () => {
    expect(settlementCountdown("202608", "2026-08-15")).toBe(3);
  });

  it("跨月:8/28(週五)到 9/16 = 13", () => {
    expect(settlementCountdown("202609", "2026-08-28")).toBe(13);
  });

  // review TZ-3 拍板:純日曆的第三週三遇假日順延時,真結算日會落在「算出來的日子之後」,
  // 回 null 等於警示在最該亮的那天整個消失。回 0(維持 T-0 警示)直到 HOT 換月自然收斂。
  it("已過 → 0(結算日順延 / HOT 未換月的空窗期,警示不可消失)", () => {
    expect(settlementCountdown("202608", "2026-08-20")).toBe(0);
    expect(settlementCountdown("202608", "2026-09-01")).toBe(0);
  });

  it("已過仍不回負數(不顯示 T-(−3) 這種讀不懂的倒數)", () => {
    expect(settlementCountdown("202608", "2026-12-31")).toBe(0);
  });

  it("壞輸入回 null 而不拋(render path 不可白屏)", () => {
    expect(settlementCountdown("2026", "2026-08-03")).toBe(null);
    expect(settlementCountdown("202613", "2026-08-03")).toBe(null);
    expect(settlementCountdown("202608", "")).toBe(null);
    expect(settlementCountdown("202608", "2026-8-3")).toBe(null);
  });
});
