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
  nextTradingDayIso,
  setHolidays,
  shiftIso,
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

  // [lock] review TQ-1:上面那組在 UTC+8(台北,開發機與 CI 的預設)下,`getUTCDay()`
  // 與本機 `getDay()` 同值 —— 把實作改回 `new Date(iso).getDay()` 全綠,而那正是這支
  // 函式存在的理由。負偏移時區才分得出來:`new Date("2026-08-17")` 是 UTC 午夜 =
  // 洛杉磯 08-16 17:00 → 本機 `getDay()` 回 0(週日),週一會被當成週末。
  //
  // Node 16+ 起 `process.env.TZ` 的指派會重設 ICU 時區快取(改完立即生效);
  // 還原放 `finally` —— 漏還原會讓同一個 worker 之後所有含日期的測試在 UTC−7 下跑。
  it("UTC−7 時區下仍以 UTC 午夜解讀(本機 getDay() 會把週一算成週日)", () => {
    const orig = process.env.TZ;
    try {
      process.env.TZ = "America/Los_Angeles";
      expect(isWeekendIso("2026-08-15")).toBe(true); // 週六(本機 getDay() = 5)
      expect(isWeekendIso("2026-08-17")).toBe(false); // 週一(本機 getDay() = 0)
    } finally {
      process.env.TZ = orig;
    }
  });
});

describe("nextTradingDayIso / shiftIso(mod/futures-day-1500:錨定日要跳到「次一交易日」)", () => {
  it("shiftIso:UTC 日曆進位 / 退位,跨月跨年正確;壞字串原樣回傳不炸", () => {
    expect(shiftIso("2026-08-31", 1)).toBe("2026-09-01");
    expect(shiftIso("2026-09-01", -1)).toBe("2026-08-31");
    expect(shiftIso("2027-01-01", -1)).toBe("2026-12-31");
    expect(shiftIso("garbage", 1)).toBe("garbage");
    expect(nextTradingDayIso("garbage")).toBe("garbage");
  });

  it("nextTradingDayIso:顯式集合優先於模組集合(caller 把 query data 當 memo dep 時走這條)", () => {
    setHolidays(["2026-10-09"]);
    expect(nextTradingDayIso("2026-10-08", new Set())).toBe("2026-10-09");
    clearHolidays();
    expect(nextTradingDayIso("2026-10-08", new Set(["2026-10-09"]))).toBe("2026-10-12");
  });

  it("nextTradingDayIso:週一→週二;週五→週一;週六 / 週日→週一(跳週末)", () => {
    // 2026-08-24 一 … 08-28 五 / 08-29 六 / 08-30 日 / 08-31 一
    expect(nextTradingDayIso("2026-08-24")).toBe("2026-08-25");
    expect(nextTradingDayIso("2026-08-28")).toBe("2026-08-31");
    expect(nextTradingDayIso("2026-08-29")).toBe("2026-08-31");
    expect(nextTradingDayIso("2026-08-30")).toBe("2026-08-31");
  });

  it("nextTradingDayIso:假日前一日 → 假日後首個交易日(10-08 四 → 10-09 假 → 10-10/11 週末 → 10-12 一)", () => {
    expect(nextTradingDayIso("2026-10-08")).toBe("2026-10-09"); // 未載日曆:只跳週末
    setHolidays(["2026-10-09"]);
    expect(nextTradingDayIso("2026-10-08")).toBe("2026-10-12");
    clearHolidays();
    expect(nextTradingDayIso("2026-10-08")).toBe("2026-10-09");
  });

  it("nextTradingDayIso:跨月 / 跨年進位以 UTC 日曆算(不受本機時區影響)", () => {
    expect(nextTradingDayIso("2026-08-31")).toBe("2026-09-01"); // 一 → 二
    expect(nextTradingDayIso("2026-12-31")).toBe("2027-01-01"); // 四 → 五(未載日曆)
  });

  it("nextTradingDayIso:連續 30 天皆非交易日 → 仍回第 31 天(有界,不無限迴圈)", () => {
    const days: string[] = [];
    for (let i = 1; i <= 40; i += 1) {
      const d = new Date(Date.UTC(2026, 7, 24 + i));
      days.push(d.toISOString().slice(0, 10));
    }
    setHolidays(days);
    expect(nextTradingDayIso("2026-08-24")).toBe("2026-09-24");
  });
});
