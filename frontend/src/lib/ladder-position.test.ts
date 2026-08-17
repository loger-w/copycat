import { describe, expect, it } from "vitest";

import {
  avgTickOf,
  clampDiscount,
  FEE_DISCOUNT_DEFAULT,
  feeRate,
  positionEcon,
  secPositionsOf,
  snapBreakEven,
} from "@/lib/ladder-position";
import type { CapitalPosition } from "@/types";

function pos(over: Partial<CapitalPosition> = {}): CapitalPosition {
  return {
    market: "sec",
    stock_no: "2330",
    qty: 2,
    name: "台積電",
    avg_price: 100,
    kind: "cash",
    pnl_base: null,
    pnl_base_price: null,
    pnl_cost: null,
    code: null,
    ...over,
  };
}

describe("feeRate", () => {
  it("1.8 折 = 牌告 ×0.18", () => {
    expect(feeRate(1.8)).toBeCloseTo(0.0002565, 10);
  });

  it("10 折 = 牌告原價", () => {
    expect(feeRate(10)).toBeCloseTo(0.001425, 10);
  });

  it("預設折數是 user 實答的 1.8", () => {
    expect(FEE_DISCOUNT_DEFAULT).toBe(1.8);
  });
});

// design v2「SC-2/SC-3」節手算例(五組),折數 1.8(f = 0.0002565)
describe("positionEcon 手算例(design v2 五組)", () => {
  it("多方 pnl:avg=100 px=102 qty=2 現股 → 4000 − 51.3 − 664.326 = +3284", () => {
    expect(positionEcon(2, 100, 102_000, 1.8, "cash").pnl).toBe(3_284);
  });

  it("多方 BE:avg=100 → 100.352…,snapUp = 100_500", () => {
    const be = positionEcon(2, 100, 102_000, 1.8, "cash").breakEvenMilli;
    expect(be).not.toBeNull();
    expect(be!).toBeCloseTo(100_352.45, 1);
    expect(snapBreakEven(be!, 2)).toBe(100_500);
  });

  it("空方 pnl:avg=100 px=98 qty=−2 融券 → 4000 − 811.3 − 50.274 = +3138", () => {
    expect(positionEcon(-2, 100, 98_000, 1.8, "short").pnl).toBe(3_138);
  });

  it("空方 BE(short 含借券費 b):avg=100 → 99.569…,snapDown = 99_500", () => {
    const be = positionEcon(-2, 100, 98_000, 1.8, "short").breakEvenMilli;
    expect(be).not.toBeNull();
    expect(be!).toBeCloseTo(99_568.81, 1);
    expect(snapBreakEven(be!, -2)).toBe(99_500);
  });

  it("空方虧損例:avg=100 px=103 qty=−2 融券 → −6864(費用不得變號成收益)", () => {
    expect(positionEcon(-2, 100, 103_000, 1.8, "short").pnl).toBe(-6_864);
  });
});

describe("positionEcon 邊界", () => {
  it("非 short 的空方不計借券費(b 只在 kind==='short')", () => {
    // 4000 − 100×2000×0.0032565(=651.3) − 50.274 = 3298.426
    expect(positionEcon(-2, 100, 98_000, 1.8, "daytrade_sell").pnl).toBe(3_298);
  });

  it("多方恆不計借券費 —— kind 誤植 short 也一樣", () => {
    expect(positionEcon(2, 100, 102_000, 1.8, "short").pnl).toBe(
      positionEcon(2, 100, 102_000, 1.8, "cash").pnl,
    );
  });

  it("qty = 0 → 全 null(「0 不是部位」,同 px() 歸一精神;CALC-2)", () => {
    expect(positionEcon(0, 100, 102_000, 1.8, "cash")).toEqual({
      pnl: null,
      breakEvenMilli: null,
    });
  });

  it("avgPrice 為 null → pnl 與 BE 皆 null", () => {
    expect(positionEcon(2, null, 102_000, 1.8, "cash")).toEqual({
      pnl: null,
      breakEvenMilli: null,
    });
  });

  it("avgPrice <= 0 視為缺值(D14:「0 不是價格」)→ 全 null", () => {
    expect(positionEcon(2, 0, 102_000, 1.8, "cash")).toEqual({ pnl: null, breakEvenMilli: null });
    expect(positionEcon(2, -1, 102_000, 1.8, "cash")).toEqual({ pnl: null, breakEvenMilli: null });
  });

  it("lastMilli = 0 → pnl null,BE 照算(D14)", () => {
    const econ = positionEcon(2, 100, 0, 1.8, "cash");
    expect(econ.pnl).toBeNull();
    expect(econ.breakEvenMilli).not.toBeNull();
  });

  it("lastMilli = null → pnl null,BE 照算(D15)", () => {
    const econ = positionEcon(2, 100, null, 1.8, "cash");
    expect(econ.pnl).toBeNull();
    expect(econ.breakEvenMilli).toBeCloseTo(100_352.45, 1);
  });

  it("|qty| 計費:同均價同現價,做多 2 張與做空 2 張的費用基數一致(D3)", () => {
    // 空方(非 short,b=0)相對均價的對稱點,費用結構與多方同基數
    const long = positionEcon(2, 100, 100_000, 1.8, "cash").pnl;
    const short = positionEcon(-2, 100, 100_000, 1.8, "cash").pnl;
    expect(long).toBe(short);
    expect(long).toBe(-703); // 0 − 51.3 − 651.3
  });
});

describe("snapBreakEven 方向", () => {
  it("多方 snapUp(第一個獲利 ≥ 0 的 tick)", () => {
    expect(snapBreakEven(100_352.45, 2)).toBe(100_500);
  });

  it("空方 snapDown", () => {
    expect(snapBreakEven(99_568.81, -2)).toBe(99_500);
  });

  it("已在合法檔位上 → 兩方向皆不動", () => {
    expect(snapBreakEven(100_500, 2)).toBe(100_500);
    expect(snapBreakEven(100_500, -2)).toBe(100_500);
  });
});

describe("avgTickOf", () => {
  it("均價本身即合法檔位 → 原值", () => {
    expect(avgTickOf(100)).toBe(100_000);
  });

  it("取最近檔位,跨級距時往上收(99.97 → 100)", () => {
    expect(avgTickOf(99.97)).toBe(100_000);
  });

  it("同級距內取較近的一側", () => {
    expect(avgTickOf(99.92)).toBe(99_900);
  });
});

describe("clampDiscount", () => {
  it("合法值原樣回傳(字串與數字皆收)", () => {
    expect(clampDiscount("1.8")).toBe(1.8);
    expect(clampDiscount(1.8)).toBe(1.8);
    expect(clampDiscount(10)).toBe(10);
    expect(clampDiscount("10")).toBe(10);
  });

  it("空字串 / 非數字 → null", () => {
    expect(clampDiscount("")).toBeNull();
    expect(clampDiscount("abc")).toBeNull();
    expect(clampDiscount(Number.NaN)).toBeNull();
  });

  it("超出 0 < v ≤ 10 → null", () => {
    expect(clampDiscount("0")).toBeNull();
    expect(clampDiscount(0)).toBeNull();
    expect(clampDiscount("-1")).toBeNull();
    expect(clampDiscount("11")).toBeNull();
  });
});

describe("secPositionsOf", () => {
  it("只留本檔 sec 且 qty ≠ 0 的部位", () => {
    const all = [
      pos({ kind: "cash" }),
      pos({ market: "fut", stock_no: "TXFH6", kind: "cash" }),
      pos({ stock_no: "2317", kind: "cash" }),
      pos({ qty: 0, kind: "margin" }),
    ];
    const got = secPositionsOf(all, "2330");
    expect(got.length).toBe(1);
    expect(got[0]!.kind).toBe("cash");
  });

  it("排序 cash → margin → short,未知 kind 殿後(D13)", () => {
    const all = [
      pos({ kind: "wtf" }),
      pos({ kind: "short", qty: -2 }),
      pos({ kind: "cash" }),
      pos({ kind: "margin" }),
    ];
    expect(secPositionsOf(all, "2330").map((p) => p.kind)).toEqual([
      "cash",
      "margin",
      "short",
      "wtf",
    ]);
  });

  it("undefined(尚未載入)→ 空陣列", () => {
    expect(secPositionsOf(undefined, "2330")).toEqual([]);
  });
});
