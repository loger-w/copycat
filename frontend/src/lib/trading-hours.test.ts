import { describe, expect, it } from "vitest";

import { inFuturesAllDayHours } from "@/lib/trading-hours";

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
