import { describe, expect, it } from "vitest";

import { pickOiLines } from "@/lib/oi-levels";
import type { OiStrikeRow } from "@/types";

function s(strike: number, call_oi: number, put_oi: number): OiStrikeRow {
  return { strike, call_oi, put_oi };
}

/** 真樣本形狀(FinMind TaiwanOptionDaily TXO 2026-08-04):深度價外 55000 的
 *  call OI 最大,全域取 max 會選到那根 —— 那不是壓力,所以要靠 ±10% 帶內取 max。 */
const STRIKES: OiStrikeRow[] = [
  s(20000, 120, 5_000), // 帶外(< 0.9 × 24000 = 21600)
  s(22000, 3_000, 9_000),
  s(23500, 5_000, 12_000),
  s(24000, 8_000, 7_000),
  s(25000, 14_000, 2_000),
  s(26000, 4_000, 900),
  s(55000, 99_000, 10), // 深度價外垃圾履約價(帶外)
];

const SPOT = 24_000_000; // 24000 點 = 毫點

describe("pickOiLines(SC-11 帶內取 max)", () => {
  it("壓力 = 帶內 call_oi 最大、支撐 = 帶內 put_oi 最大", () => {
    const { call, put } = pickOiLines(STRIKES, SPOT, "2026-08-04");
    expect(call!.priceMilli).toBe(25_000_000);
    expect(put!.priceMilli).toBe(23_500_000);
  });

  it("深度價外的全域 max(55000)被 ±10% 帶排除", () => {
    const { call } = pickOiLines(STRIKES, SPOT, "2026-08-04");
    expect(call!.priceMilli).not.toBe(55_000_000);
  });

  it("帶界含端點:0.9×spot 與 1.1×spot 上的履約價算帶內", () => {
    const edge = [s(21600, 1_000, 1_000), s(26400, 2_000, 3_000)];
    const { call, put } = pickOiLines(edge, SPOT, "2026-08-04");
    expect(call!.priceMilli).toBe(26_400_000);
    expect(put!.priceMilli).toBe(26_400_000);
  });

  it("label 為「壓 {strike}」/「撐 {strike}」", () => {
    const { call, put } = pickOiLines(STRIKES, SPOT, "2026-08-04");
    expect(call!.label).toBe("壓 25000");
    expect(put!.label).toBe("撐 23500");
  });

  it("title 內含口數與日期(SC-11 hover 驗收)", () => {
    const { call, put } = pickOiLines(STRIKES, SPOT, "2026-08-04");
    expect(call!.title).toBe("壓 25000・OI 14000口・2026-08-04");
    expect(put!.title).toBe("撐 23500・OI 12000口・2026-08-04");
  });

  it("多空兩線用不同 className(顏色可分辨)", () => {
    const { call, put } = pickOiLines(STRIKES, SPOT, "2026-08-04");
    expect(call!.className).not.toBe(put!.className);
    expect(call!.className.length).toBeGreaterThan(0);
  });

  it("帶內空 → 兩邊都 null", () => {
    expect(pickOiLines([s(10000, 9_000, 9_000)], SPOT, "2026-08-04")).toEqual({
      call: null,
      put: null,
    });
  });

  it("strikes 空 → 兩邊都 null(降級狀態的資料面)", () => {
    expect(pickOiLines([], SPOT, "2026-08-04")).toEqual({ call: null, put: null });
  });

  it("spot 無值 → 兩邊都 null(不畫比不畫在錯的地方好)", () => {
    expect(pickOiLines(STRIKES, null, "2026-08-04")).toEqual({ call: null, put: null });
  });

  it("帶內該邊 OI 全 0 → 該邊 null(0 口的撐壓不是撐壓)", () => {
    const { call, put } = pickOiLines([s(24000, 0, 500)], SPOT, "2026-08-04");
    expect(call).toBe(null);
    expect(put!.priceMilli).toBe(24_000_000);
  });

  it("date 為 null 時 title 不出現 'null' 字樣", () => {
    const { call } = pickOiLines(STRIKES, SPOT, null);
    expect(call!.title).not.toContain("null");
  });

  it("同 OI 平手取較低履約價(輸入升冪 → 先到者留)", () => {
    const tie = [s(23000, 5_000, 1), s(25000, 5_000, 1)];
    expect(pickOiLines(tie, SPOT, "2026-08-04").call!.priceMilli).toBe(23_000_000);
  });
});
