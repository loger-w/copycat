import { describe, expect, it } from "vitest";

import { inTwseSessionNow } from "@/lib/spot-session";

/** 2026-08:05 三 / 08 六 / 09 日。 */
function at(day: number, hh: number, mm: number): Date {
  return new Date(2026, 7, day, hh, mm, 0);
}

const WED = 5;
const SAT = 8;
const SUN = 9;

describe("inTwseSessionNow(SC-5 期現價差 gate;週一〜五 09:00–13:33)", () => {
  it("盤中為 true", () => {
    expect(inTwseSessionNow(at(WED, 9, 0))).toBe(true);
    expect(inTwseSessionNow(at(WED, 11, 30))).toBe(true);
    expect(inTwseSessionNow(at(WED, 13, 33))).toBe(true);
  });

  it("開收盤邊界外為 false", () => {
    expect(inTwseSessionNow(at(WED, 8, 59))).toBe(false);
    expect(inTwseSessionNow(at(WED, 13, 34))).toBe(false);
  });

  it("夜間為 false —— index_engine 收盤後 p 保留收盤值且 stale 恆 false,單靠 stale 會整夜顯示假價差", () => {
    expect(inTwseSessionNow(at(WED, 20, 0))).toBe(false);
    expect(inTwseSessionNow(at(WED, 0, 30))).toBe(false);
  });

  it("週末全日 false", () => {
    expect(inTwseSessionNow(at(SAT, 10, 0))).toBe(false);
    expect(inTwseSessionNow(at(SUN, 10, 0))).toBe(false);
  });

  it("不帶參數時吃當下時鐘(不崩、回布林)", () => {
    expect(typeof inTwseSessionNow()).toBe("boolean");
  });
});
