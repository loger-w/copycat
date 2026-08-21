/** 前端交易日曆(SC-9 的純函式面)。
 *
 *  模組級集合會跨 it 外溢 → `beforeEach` 一律清空(未載入 = 空集合 = 只擋週末,
 *  也是「日曆沒回來」時該有的行為)。 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  clearHolidays,
  isTradingDay,
  isWeekendIso,
  isoLocalDate,
  setHolidays,
} from "@/lib/trading-calendar";

/** 2026-10-08 四 / 10-09 五(國慶調整假)/ 10-10 六 / 10-11 日。 */
const THU = new Date(2026, 9, 8, 10, 0);
const FRI = new Date(2026, 9, 9, 10, 0);
const SAT = new Date(2026, 9, 10, 10, 0);
const SUN = new Date(2026, 9, 11, 10, 0);

beforeEach(() => {
  clearHolidays();
});

describe("isoLocalDate(本機時區,非 UTC)", () => {
  it("月 / 日補零", () => {
    expect(isoLocalDate(new Date(2026, 0, 1, 23, 30))).toBe("2026-01-01");
    expect(isoLocalDate(new Date(2026, 8, 5, 0, 0))).toBe("2026-09-05");
  });

  // toISOString() 是 UTC:台北 08:00 前會退成前一天,整個早盤的假日判定錯位一天。
  it("台北早上 07:00 仍是當天(toISOString 會退一天)", () => {
    const d = new Date(2026, 9, 9, 7, 0);
    expect(isoLocalDate(d)).toBe("2026-10-09");
  });
});

describe("isTradingDay", () => {
  it("未載入日曆 = 只擋週末(改動前行為逐字相同,W8)", () => {
    expect(isTradingDay(THU)).toBe(true);
    expect(isTradingDay(FRI)).toBe(true);
    expect(isTradingDay(SAT)).toBe(false);
    expect(isTradingDay(SUN)).toBe(false);
  });

  it("setHolidays 後該日轉非交易日,鄰近平日不受影響", () => {
    setHolidays(["2026-10-09"]);
    expect(isTradingDay(FRI)).toBe(false);
    expect(isTradingDay(THU)).toBe(true);
  });

  it("clearHolidays 還原成只擋週末", () => {
    setHolidays(["2026-10-09"]);
    expect(isTradingDay(FRI)).toBe(false);
    clearHolidays();
    expect(isTradingDay(FRI)).toBe(true);
  });

  it("setHolidays 是覆寫不是累加(第二次取數的清單即全部)", () => {
    setHolidays(["2026-10-09"]);
    setHolidays(["2026-10-08"]);
    expect(isTradingDay(FRI)).toBe(true);
    expect(isTradingDay(THU)).toBe(false);
  });

  it("假日集合含週末日期時週末仍為假(不重複判定也不翻轉)", () => {
    setHolidays(["2026-10-10"]);
    expect(isTradingDay(SAT)).toBe(false);
  });
});

// AR8:膠囊的週末守門子。**輸入是後端給的 ISO 字串**(不是 Date)—— 用本機
// `getDay()` 解析會在時區偏移下把週一算成週日,所以固定以 UTC 午夜解讀。
describe("isWeekendIso", () => {
  it("週六 / 週日為 true,週一至週五為 false", () => {
    expect(isWeekendIso("2026-08-15")).toBe(true); // 週六
    expect(isWeekendIso("2026-08-16")).toBe(true); // 週日
    expect(isWeekendIso("2026-08-14")).toBe(false); // 週五
    expect(isWeekendIso("2026-08-17")).toBe(false); // 週一
    expect(isWeekendIso("2026-10-09")).toBe(false); // 週五(國定假日仍非週末)
  });

  it("形狀不合(空字串 / 亂字串)→ false(寧可少擋也不要因 NaN 誤判)", () => {
    expect(isWeekendIso("")).toBe(false);
    expect(isWeekendIso("not-a-date")).toBe(false);
  });
});
