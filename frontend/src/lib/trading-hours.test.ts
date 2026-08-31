import { beforeEach, describe, expect, it } from "vitest";

import { clearHolidays, setHolidays } from "@/lib/trading-calendar";
import {
  inFuturesAllDayHours,
  inFuturesTradingHours,
  inTradingHours,
  msUntilTradingOpen,
} from "@/lib/trading-hours";

/** 2026-08 月曆:01 六 / 02 日 / 03 一 / 04 二 / 05 三 / 06 四 / 07 五 / 08 六。
 *  月/日直接寫死,測的是「星期維度」而不是某個絕對時刻。 */
function at(day: number, hh: number, mm: number): Date {
  return new Date(2026, 7, day, hh, mm, 0);
}

const WED = 5;
const THU = 6;
const SAT = 8;
const SUN = 9;
const MON = 10;

/** 假日集合是模組級狀態,會跨 it / 跨 describe 外溢 —— 每條測試從空集合開始
 *  (空集合 = 只擋週末 = 改動前行為,上面既有的星期維度測點全部靠這個前提)。 */
beforeEach(() => {
  clearHolidays();
});

describe("inFuturesAllDayHours(SC-12;design §4.2 星期維度)", () => {
  it("brainstorm SC-12 的 11 個(星期,時刻)測點", () => {
    expect(inFuturesAllDayHours(at(WED, 10, 0))).toBe(true);
    expect(inFuturesAllDayHours(at(WED, 13, 47))).toBe(true);
    expect(inFuturesAllDayHours(at(WED, 14, 30))).toBe(false);
    expect(inFuturesAllDayHours(at(WED, 14, 56))).toBe(true);
    expect(inFuturesAllDayHours(at(WED, 16, 0))).toBe(true);
    expect(inFuturesAllDayHours(at(THU, 0, 30))).toBe(true);
    expect(inFuturesAllDayHours(at(SAT, 0, 30))).toBe(true);
    expect(inFuturesAllDayHours(at(SAT, 10, 0))).toBe(false);
    expect(inFuturesAllDayHours(at(SUN, 20, 0))).toBe(false);
    expect(inFuturesAllDayHours(at(MON, 3, 0))).toBe(false);
    expect(inFuturesAllDayHours(at(MON, 8, 50))).toBe(true);
  });

  it("停輪詢窗邊界:13:50 開 / 13:51 關 / 14:54 關 / 14:55 開", () => {
    expect(inFuturesAllDayHours(at(WED, 13, 50))).toBe(true);
    expect(inFuturesAllDayHours(at(WED, 13, 51))).toBe(false);
    expect(inFuturesAllDayHours(at(WED, 14, 54))).toBe(false);
    expect(inFuturesAllDayHours(at(WED, 14, 55))).toBe(true);
  });

  it("清晨邊界:05:05 開 / 05:06 關 / 08:39 關 / 08:40 開", () => {
    expect(inFuturesAllDayHours(at(THU, 5, 5))).toBe(true);
    expect(inFuturesAllDayHours(at(THU, 5, 6))).toBe(false);
    expect(inFuturesAllDayHours(at(THU, 8, 39))).toBe(false);
    expect(inFuturesAllDayHours(at(THU, 8, 40))).toBe(true);
  });

  it("週六 05:05 前算週五夜盤、05:06 後全關", () => {
    expect(inFuturesAllDayHours(at(SAT, 5, 5))).toBe(true);
    expect(inFuturesAllDayHours(at(SAT, 5, 6))).toBe(false);
    expect(inFuturesAllDayHours(at(SAT, 16, 0))).toBe(false);
  });

  it("週日全日關(週一夜盤要到週一 14:55 才開)", () => {
    expect(inFuturesAllDayHours(at(SUN, 0, 30))).toBe(false);
    expect(inFuturesAllDayHours(at(SUN, 10, 0))).toBe(false);
    expect(inFuturesAllDayHours(at(SUN, 23, 30))).toBe(false);
  });

  it("週一凌晨關(週日無夜盤),週一 23:30 開", () => {
    expect(inFuturesAllDayHours(at(MON, 0, 30))).toBe(false);
    expect(inFuturesAllDayHours(at(MON, 5, 5))).toBe(false);
    expect(inFuturesAllDayHours(at(MON, 23, 30))).toBe(true);
  });

  it("不帶參數時吃當下時鐘(不崩、回布林)", () => {
    expect(typeof inFuturesAllDayHours()).toBe("boolean");
  });
});

/** 2026-10-09(五)國慶調整假;10-08 四為交易日、10-10 六、10-12 一。
 *
 *  少了假日這一維,國定假日整天每 60s 空打當日段(當日段恆空 → don't-cache-empty
 *  → 每次都真的走 TC4 SubHistory)—— 與週末那條路同一種浪費,只是原本擋不掉。 */
describe("三支時段函式吃交易日曆(SC-9)", () => {
  const HOL = (hh: number, mm: number) => new Date(2026, 9, 9, hh, mm);
  const SAT_AFTER_HOL = (hh: number, mm: number) => new Date(2026, 9, 10, hh, mm);
  const MON_AFTER = (hh: number, mm: number) => new Date(2026, 9, 12, hh, mm);

  it("前提自檢:未載日曆時 10-09(五)照現行判定為交易日", () => {
    expect(HOL(10, 0).getDay()).toBe(5);
    expect(inTradingHours(HOL(10, 0))).toBe(true);
    expect(inFuturesTradingHours(HOL(10, 0))).toBe(true);
    expect(inFuturesAllDayHours(HOL(10, 0))).toBe(true);
  });

  it("假日當天日盤窗全關(個股 / 期指日盤 / 近全時段)", () => {
    setHolidays(["2026-10-09"]);
    expect(inTradingHours(HOL(10, 0))).toBe(false);
    expect(inFuturesTradingHours(HOL(10, 0))).toBe(false);
    expect(inFuturesAllDayHours(HOL(10, 0))).toBe(false);
    expect(inFuturesAllDayHours(HOL(16, 0))).toBe(false); // 假日當晚無夜盤
  });

  it("00:00–05:05 屬前一日夜盤 → 判的是前一天(R1)", () => {
    setHolidays(["2026-10-09"]);
    // 假日凌晨:前一日(10-08 四)是交易日 → 那是週四的夜盤,照開
    expect(inFuturesAllDayHours(HOL(1, 0))).toBe(true);
    expect(inFuturesAllDayHours(HOL(5, 5))).toBe(true);
    // 假日次日凌晨:前一日是假日 → 沒有夜盤可收
    expect(inFuturesAllDayHours(SAT_AFTER_HOL(1, 0))).toBe(false);
  });

  it("週末語意不變:未設假日時週六 01:00 開、週一 01:00 關", () => {
    expect(inFuturesAllDayHours(SAT_AFTER_HOL(1, 0))).toBe(true);
    expect(inFuturesAllDayHours(MON_AFTER(1, 0))).toBe(false);
  });

  it("假日集合不含的平日逐字不變(只疊加否決,不改既有維度)", () => {
    setHolidays(["2026-10-09"]);
    expect(inTradingHours(new Date(2026, 9, 8, 10, 0))).toBe(true);
    expect(inFuturesTradingHours(new Date(2026, 9, 8, 10, 0))).toBe(true);
    expect(inFuturesAllDayHours(new Date(2026, 9, 8, 16, 0))).toBe(true);
    // 週末仍恆假(假日集合空與否都一樣)
    expect(inTradingHours(SAT_AFTER_HOL(11, 0))).toBe(false);
    expect(inFuturesTradingHours(SAT_AFTER_HOL(11, 0))).toBe(false);
  });
});

describe("msUntilTradingOpen(pr-164 F-06:防護分支 + 基本幾何)", () => {
  it("窗前:同日開點差(週三 08:00 → 09:01 = 61 分)", () => {
    expect(msUntilTradingOpen(at(WED, 8, 0))).toBe(61 * 60_000);
  });

  it("收盤後:次一交易日開點(週三 14:00 → 週四 09:01 = 19h01m)", () => {
    expect(msUntilTradingOpen(at(WED, 14, 0))).toBe(19 * 3_600_000 + 60_000);
  });

  it("週五收盤後 → 週一開點(跳過週末 = 67h01m)", () => {
    expect(msUntilTradingOpen(at(7, 14, 0))).toBe(67 * 3_600_000 + 60_000);
  });

  it("次日是假日 → 再次日開點(43h01m)", () => {
    setHolidays(["2026-08-06"]);
    expect(msUntilTradingOpen(at(WED, 14, 0))).toBe(43 * 3_600_000 + 60_000);
  });

  it("14 天窮盡 → 24h fallback(「日曆異常不空轉」的唯一保證)", () => {
    // 今天(週三 08-05)開點已過 + 未來 14 個日曆日的平日全設假 → 迴圈窮盡
    setHolidays([
      "2026-08-06", "2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12",
      "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19",
    ]);
    expect(msUntilTradingOpen(at(WED, 10, 0))).toBe(24 * 3_600_000);
  });

  it("開點前最後一秒回原始毫秒差(1s 下限與秒級量化在 groupPollInterval 那層)", () => {
    expect(msUntilTradingOpen(new Date(2026, 7, 5, 9, 0, 59, 500))).toBe(500);
  });
});
