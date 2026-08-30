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

/** 修前口徑:均價當純成交價、無當沖段(舊測試的期望值全在這個口徑下手算)。 */
const FILL = { avgSource: "fill", todayQty: 0 } as const;
const BROKER = { avgSource: "broker", todayQty: 0 } as const;

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
    avg_source: null,
    today_qty: 0,
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
    expect(positionEcon(2, 100, 102_000, 1.8, "cash", FILL).pnl).toBe(3_284);
  });

  it("多方 BE:avg=100 → 100.352…,snapUp = 100_500", () => {
    const be = positionEcon(2, 100, 102_000, 1.8, "cash", FILL).breakEvenMilli;
    expect(be).not.toBeNull();
    expect(be!).toBeCloseTo(100_352.45, 1);
    expect(snapBreakEven(be!, 2)).toBe(100_500);
  });

  it("空方 pnl:avg=100 px=98 qty=−2 融券 → 4000 − 811.3 − 50.274 = +3138", () => {
    expect(positionEcon(-2, 100, 98_000, 1.8, "short", FILL).pnl).toBe(3_138);
  });

  it("空方 BE(short 含借券費 b):avg=100 → 99.569…,snapDown = 99_500", () => {
    const be = positionEcon(-2, 100, 98_000, 1.8, "short", FILL).breakEvenMilli;
    expect(be).not.toBeNull();
    expect(be!).toBeCloseTo(99_568.81, 1);
    expect(snapBreakEven(be!, -2)).toBe(99_500);
  });

  it("空方虧損例:avg=100 px=103 qty=−2 融券 → −6864(費用不得變號成收益)", () => {
    expect(positionEcon(-2, 100, 103_000, 1.8, "short", FILL).pnl).toBe(-6_864);
  });
});

describe("positionEcon 邊界", () => {
  it("非 short 的空方不計借券費(b 只在 kind==='short')", () => {
    // 4000 − 100×2000×0.0032565(=651.3) − 50.274 = 3298.426
    expect(positionEcon(-2, 100, 98_000, 1.8, "daytrade_sell", FILL).pnl).toBe(3_298);
  });

  it("多方恆不計借券費 —— kind 誤植 short 也一樣", () => {
    expect(positionEcon(2, 100, 102_000, 1.8, "short", FILL).pnl).toBe(
      positionEcon(2, 100, 102_000, 1.8, "cash", FILL).pnl,
    );
  });

  it("qty = 0 → 全 null(「0 不是部位」,同 px() 歸一精神;CALC-2)", () => {
    expect(positionEcon(0, 100, 102_000, 1.8, "cash", FILL)).toEqual({
      pnl: null,
      breakEvenMilli: null,
    });
  });

  it("avgPrice 為 null → pnl 與 BE 皆 null", () => {
    expect(positionEcon(2, null, 102_000, 1.8, "cash", FILL)).toEqual({
      pnl: null,
      breakEvenMilli: null,
    });
  });

  it("avgPrice <= 0 視為缺值(D14:「0 不是價格」)→ 全 null", () => {
    expect(positionEcon(2, 0, 102_000, 1.8, "cash", FILL)).toEqual({ pnl: null, breakEvenMilli: null });
    expect(positionEcon(2, -1, 102_000, 1.8, "cash", FILL)).toEqual({ pnl: null, breakEvenMilli: null });
  });

  it("lastMilli = 0 → pnl null,BE 照算(D14)", () => {
    const econ = positionEcon(2, 100, 0, 1.8, "cash", FILL);
    expect(econ.pnl).toBeNull();
    expect(econ.breakEvenMilli).not.toBeNull();
  });

  it("lastMilli = null → pnl null,BE 照算(D15)", () => {
    const econ = positionEcon(2, 100, null, 1.8, "cash", FILL);
    expect(econ.pnl).toBeNull();
    expect(econ.breakEvenMilli).toBeCloseTo(100_352.45, 1);
  });

  it("|qty| 計費:同均價同現價,做多 2 張與做空 2 張的費用基數一致(D3)", () => {
    // 空方(非 short,b=0)相對均價的對稱點,費用結構與多方同基數
    const long = positionEcon(2, 100, 100_000, 1.8, "cash", FILL).pnl;
    const short = positionEcon(-2, 100, 100_000, 1.8, "cash", FILL).pnl;
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

// ---- fix/breakeven-avg-source-daytrade-tax(2026-08-26)----
// 真資料:prod /api/capital/positions 4991 現股 1 張,券商均價 469.62、成交價金 469,500(純成交價 469.50);
// 差 0.1204 = 469.5 × 0.1425% × 1.8 折 —— 群益「均價」= 成交價 + 買進手續費。群益 APP 損益 18,285 @489.5。
// 期望值一律字面量手算(f = 0.0002565),不從 feeRate 反算(frontend-testing:同源同常數 = 同義反覆)。
describe("positionEcon avg_source / today_qty(打平線跳格 + 損益與群益 APP 不一致)", () => {
  it("券商均價(broker)已含買進手續費 → 不再加一次;損益對齊群益損益試算 18,285 @489.5", () => {
    // (489.5 − 469.62)·1000 − 489.5·1000·(0.0002565 + 0.003) = 19880 − 1593.86 = 18286.1
    // (群益 18,285 是用未四捨五入的 469.6204 算的,差 1 元)
    expect(positionEcon(1, 469.62, 489_500, 1.8, "cash", BROKER).pnl).toBe(18_286);
  });

  it("樂觀成交價(fill,純價)與券商均價(broker,含買費)算出同一條打平線 → 落地後不跳", () => {
    // fill:469.5 × 1.0002565 / 0.9967435 = 471.15474;broker:469.62 / 0.9967435 = 471.15431(差 0.4 毫元)
    expect(positionEcon(1, 469.5, null, 1.8, "cash", FILL).breakEvenMilli).toBeCloseTo(471_154.74, 1);
    expect(positionEcon(1, 469.62, null, 1.8, "cash", BROKER).breakEvenMilli).toBeCloseTo(471_154.31, 1);
    // 修前(兩者都當純價):broker 那條會是 471,275 → 落地跳 120 毫元,snapUp 後差一檔
  });

  it("今天成交進來的張數賣出稅用現股當沖 0.15%:1 張全今天 → 稅減半", () => {
    const econ = positionEcon(1, 469.62, 489_500, 1.8, "cash", { avgSource: "broker", todayQty: 1 });
    // 19880 − 489.5·1000·(0.0002565 + 0.0015) = 19880 − 859.83 = 19020
    expect(econ.pnl).toBe(19_020);
    // 469.62 / (1 − 0.0002565 − 0.0015) = 470.44634
    expect(econ.breakEvenMilli).toBeCloseTo(470_446.34, 1);
  });

  it("混合部位按張數分段:3 張中 1 張今天 → 有效稅率 (0.0015 + 2×0.003)/3 = 0.0025", () => {
    const econ = positionEcon(3, 100, 110_000, 1.8, "cash", { avgSource: "broker", todayQty: 1 });
    // (110 − 100)·3000 − 110·3000·(0.0002565 + 0.0025) = 30000 − 909.65 = 29090
    expect(econ.pnl).toBe(29_090);
    // 100 / (1 − 0.0002565 − 0.0025) = 100.27641
    expect(econ.breakEvenMilli).toBeCloseTo(100_276.41, 1);
  });

  it("當沖減半只限現股:融資今天買的張數仍 0.3%", () => {
    const withToday = positionEcon(1, 100, 110_000, 1.8, "margin", { avgSource: "broker", todayQty: 1 });
    // (110 − 100)·1000 − 110·1000·(0.0002565 + 0.003) = 10000 − 358.2 = 9642
    expect(withToday.pnl).toBe(9_642);
    expect(withToday.breakEvenMilli).toBeCloseTo(100_326.71, 1); // 100 / 0.9967435
  });

  it("today_qty 超過持有張數不會把稅率壓到負:clamp 到 |qty|(後端也 clamp,這裡是防禦重算)", () => {
    const over = positionEcon(1, 100, 110_000, 1.8, "cash", { avgSource: "broker", todayQty: 5 });
    expect(over.pnl).toBe(9_807); // 10000 − 110·1000·(0.0002565 + 0.0015) = 10000 − 193.2
  });

  it("avg_source 為 null 但均價已知(產生點沒標 / 舊後端)→ 明確走修前口徑:當純價加買費", () => {
    const unknown = positionEcon(2, 100, 102_000, 1.8, "cash", { avgSource: null, todayQty: 0 });
    // 與舊口徑手算例同值:+3284 / BE 100,352.45
    expect(unknown.pnl).toBe(3_284);
    expect(unknown.breakEvenMilli).toBeCloseTo(100_352.45, 1);
    expect(unknown).toEqual(positionEcon(2, 100, 102_000, 1.8, "cash", FILL));
  });
});

describe("positionEcon today_qty 邊界(review round 1)", () => {
  it("payload 兩欄同缺(avg_source 也 undefined,舊後端)→ 與 null 同口徑,不印 NaN", () => {
    const input = { avgSource: undefined, todayQty: undefined } as unknown as {
      avgSource: null;
      todayQty: number;
    };
    const econ = positionEcon(2, 100, 102_000, 1.8, "cash", input);
    expect(Number.isFinite(econ.pnl)).toBe(true);
    expect(econ).toEqual(positionEcon(2, 100, 102_000, 1.8, "cash", { avgSource: null, todayQty: 0 }));
  });

  it("avg_source 值域外字串(後端先加值、前端 dist 未重 build 的窗口)→ 白名單歸一成 null,不印 NaN", () => {
    // `?? null` 只擋 nullish;wire 送 "oi" 之類三個 case 全不中、無 default → cost 未賦值 → NaN(pr-119 F-02)
    const input = { avgSource: "oi", todayQty: 0 } as unknown as Parameters<typeof positionEcon>[5];
    const econ = positionEcon(2, 100, 102_000, 1.8, "cash", input);
    expect(Number.isFinite(econ.pnl)).toBe(true);
    expect(econ).toEqual(positionEcon(2, 100, 102_000, 1.8, "cash", { avgSource: null, todayQty: 0 }));
  });

  it("payload 缺 today_qty(後端未重啟窗口)→ 退成 0,不印 NaN", () => {
    const input = { avgSource: "broker", todayQty: undefined } as unknown as {
      avgSource: "broker";
      todayQty: number;
    };
    const econ = positionEcon(1, 469.62, 489_500, 1.8, "cash", input);
    expect(econ.pnl).toBe(18_286);
    expect(econ.breakEvenMilli).toBeCloseTo(471_154.31, 1);
  });

  it("現股空方(無券當沖先賣)今日淨賣出那段同樣減半 0.15%", () => {
    const short = positionEcon(-2, 100, 98_000, 1.8, "cash", { avgSource: null, todayQty: 2 });
    // (100 − 98)·2000 − 100·2000·(0.0002565 + 0.0015) − 98·2000·0.0002565 = 4000 − 351.3 − 50.27 = 3598
    expect(short.pnl).toBe(3_598);
    // 100 × (1 − 0.0002565 − 0.0015) / 1.0002565 = 99.79875
    expect(short.breakEvenMilli).toBeCloseTo(99_798.75, 1);
  });
});

// ---- fix/borrowless-short-calibration(2026-08-30;08-28 prod 8358 無券當沖實錄)----
describe("positionEcon 無券空單(kind === 'daytrade_sell')", () => {
  it("today_qty 那段同現股當沖減半 0.15% —— 後端負現股列歸 daytrade_sell 後與 cash 空方同一把尺", () => {
    const asDaytrade = positionEcon(-1, 512, 523_000, 1.8, "daytrade_sell", { avgSource: null, todayQty: 1 });
    const asCash = positionEcon(-1, 512, 523_000, 1.8, "cash", { avgSource: null, todayQty: 1 });
    expect(asDaytrade).toEqual(asCash);
    // 0.3% → 0.15% 差 512 × 0.15% ≈ 0.77 元 ≈ 1 檔(08-28 user 看到的打平線偏差)
    const fullTax = positionEcon(-1, 512, 523_000, 1.8, "daytrade_sell", { avgSource: null, todayQty: 0 });
    expect(asDaytrade.breakEvenMilli! - fullTax.breakEvenMilli!).toBeCloseTo(512 * 0.0015 / 1.0002565 * 1000, 0);
  });
});
