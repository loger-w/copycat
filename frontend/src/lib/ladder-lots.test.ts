import { describe, expect, it } from "vitest";

import { aggregateLots, ymdOf, ymdWindow, type LadderLot } from "@/lib/ladder-lots";
import type { CapitalOrder } from "@/types";

const TODAY = "20260813";
const YESTERDAY = "20260812";
/** 現股梯口徑(嚴格今日);個股期梯是 ±1 日窗 */
const STRICT = new Set([TODAY]);
const WINDOW = new Set([YESTERDAY, TODAY, "20260814"]);

function order(over: Partial<CapitalOrder> = {}): CapitalOrder {
  return {
    seq_no: "S1",
    stock_no: "2330",
    name: "台積電",
    market: "TS",
    buy_sell: "B",
    flag_label: "現股",
    book_no: "A1",
    status_raw: "0",
    status_label: "已委託",
    price: 100,
    avg_fill_price: null,
    order_qty: 2,
    filled_qty: 0,
    unit: "張",
    date: TODAY,
    time: "09:01:00",
    pre_order: false,
    error_msg: null,
    actionable: true,
    price_type: null,
    raw: "",
    ...over,
  };
}

/** 全部成交(rank 3)的終態單:actionable=false、殘量恆 0 */
function filledOrder(over: Partial<CapitalOrder> = {}): CapitalOrder {
  return order({
    actionable: false,
    status_label: "全部成交",
    order_qty: 2,
    filled_qty: 2,
    ...over,
  });
}

const buyAt = (
  r: { buy: Map<number, LadderLot> },
  priceMilli = 100_000,
): LadderLot | undefined => r.buy.get(priceMilli);

describe("aggregateLots 價位聚合(未成交 / 已成交)", () => {
  it("同價活單:殘量相加、seqs 併列、已成交量同時累加", () => {
    const r = aggregateLots(
      [
        order({ seq_no: "A", order_qty: 3, filled_qty: 1 }),
        order({ seq_no: "B", order_qty: 2, filled_qty: 0 }),
      ],
      "2330",
      STRICT,
    );
    expect(buyAt(r)).toEqual({ qty: 4, filled: 1, seqs: ["A", "B"] });
    expect(r.sell.size).toBe(0);
  });

  it("買賣分側:B 進 buy、S 進 sell;buy_sell 非 B/S 整筆跳過", () => {
    const r = aggregateLots(
      [
        order({ seq_no: "A" }),
        order({ seq_no: "B", buy_sell: "S", price: 100.5 }),
        order({ seq_no: "C", buy_sell: null }),
      ],
      "2330",
      STRICT,
    );
    expect(buyAt(r)?.seqs).toEqual(["A"]);
    expect(r.sell.get(100_500)?.seqs).toEqual(["B"]);
    expect(r.buy.size + r.sell.size).toBe(2);
  });

  it("價 float → 毫元 round(100.1 × 1000 的浮點殘差收斂)", () => {
    const r = aggregateLots([order({ price: 100.1 })], "2330", STRICT);
    expect([...r.buy.keys()]).toEqual([100_100]);
  });

  it("他檔 / 市價(price=null)/ key=null 全排除", () => {
    const orders = [
      order({ seq_no: "X", stock_no: "2317" }),
      order({ seq_no: "W", price: null }),
    ];
    const r = aggregateLots(orders, "2330", STRICT);
    expect(r.buy.size).toBe(0);
    const none = aggregateLots([order({ stock_no: null })], null, STRICT);
    expect(none.buy.size).toBe(0);
  });

  it("終態全成交單(date 在日期界內)→ filled 進來、qty 0、seqs 空(無刪單入口)", () => {
    const r = aggregateLots([filledOrder({ seq_no: "F" })], "2330", STRICT);
    expect(buyAt(r)).toEqual({ qty: 0, filled: 2, seqs: [] });
  });

  it("終態單 date 在日期界外 / date=null → 整筆不計(跨日幽靈不長出來)", () => {
    const stale = aggregateLots([filledOrder({ date: YESTERDAY })], "2330", STRICT);
    expect(stale.buy.size).toBe(0);
    const nodate = aggregateLots([filledOrder({ date: null })], "2330", STRICT);
    expect(nodate.buy.size).toBe(0);
    // 同一筆在 ±1 日窗(個股期 / 期貨梯口徑)下就算數
    const win = aggregateLots([filledOrder({ date: YESTERDAY })], "2330", WINDOW);
    expect(buyAt(win)).toEqual({ qty: 0, filled: 2, seqs: [] });
  });

  it("活單的成交恆計,不看日期界(昨日建立、今日成交中的預約單)", () => {
    const r = aggregateLots(
      [order({ seq_no: "P", date: YESTERDAY, order_qty: 3, filled_qty: 1 })],
      "2330",
      STRICT,
    );
    expect(buyAt(r)).toEqual({ qty: 2, filled: 1, seqs: ["P"] });
  });

  it("失敗 / 退單(終態、filled 0)→ 零痕跡", () => {
    const r = aggregateLots(
      [filledOrder({ seq_no: "E", status_label: "失敗", order_qty: 2, filled_qty: 0 })],
      "2330",
      STRICT,
    );
    expect(r.buy.size).toBe(0);
  });

  it("actionable 殘 0(P/U 先到、N 未到)→ 仍上梯且 seqs 有值(刪單入口不消失)", () => {
    const r = aggregateLots(
      [order({ seq_no: "P0", order_qty: 0, filled_qty: 0 })],
      "2330",
      STRICT,
    );
    expect(buyAt(r)).toEqual({ qty: 0, filled: 0, seqs: ["P0"] });
  });

  it("actionable 且已全部成交(N 未到)→ qty 0 但 seqs 保留", () => {
    const r = aggregateLots(
      [order({ seq_no: "A", order_qty: 2, filled_qty: 2 })],
      "2330",
      STRICT,
    );
    expect(buyAt(r)).toEqual({ qty: 0, filled: 2, seqs: ["A"] });
  });

  it("同價混合(活單 ×2 + 全成交 ×1):qty=Σ活單殘、filled=Σ全部、seqs=活單 only", () => {
    const r = aggregateLots(
      [
        order({ seq_no: "A", order_qty: 3, filled_qty: 1 }),
        order({ seq_no: "B", order_qty: 1, filled_qty: 0 }),
        filledOrder({ seq_no: "F", order_qty: 5, filled_qty: 5 }),
      ],
      "2330",
      STRICT,
    );
    expect(buyAt(r)).toEqual({ qty: 3, filled: 6, seqs: ["A", "B"] });
  });

  it("excludeUnit:現股梯傳「股」→ 零股單整筆不上梯(活單與已成交都不計)", () => {
    const orders = [
      order({ seq_no: "L1", unit: "股", order_qty: 1_000, filled_qty: 0 }),
      filledOrder({ seq_no: "L2", unit: "股", order_qty: 500, filled_qty: 500 }),
    ];
    expect(aggregateLots(orders, "2330", STRICT, "股").buy.size).toBe(0);
    // 不傳 excludeUnit(期貨 / 個股期梯)→ 不設單位閘
    expect(aggregateLots(orders, "2330", STRICT).buy.size).toBe(1);
  });
});

describe("ymdWindow 日期界(YYYYMMDD 本機時區)", () => {
  it("offsets [0] → 只有今日", () => {
    expect([...ymdWindow(new Date(2026, 7, 13, 9, 30), [0])]).toEqual(["20260813"]);
  });

  it("offsets [-1,0,1] → 昨 / 今 / 明 三日", () => {
    expect([...ymdWindow(new Date(2026, 7, 13, 23, 59), [-1, 0, 1])]).toEqual([
      "20260812",
      "20260813",
      "20260814",
    ]);
  });

  it("跨月邊界:月初往前退到上個月最後一日", () => {
    expect([...ymdWindow(new Date(2026, 2, 1, 0, 5), [-1, 0, 1])]).toEqual([
      "20260228",
      "20260301",
      "20260302",
    ]);
  });

  it("跨年邊界:1/1 往前退到去年 12/31", () => {
    expect([...ymdWindow(new Date(2026, 0, 1, 0, 5), [-1, 0, 1])]).toEqual([
      "20251231",
      "20260101",
      "20260102",
    ]);
  });
});

// 🔵 `ymdOf` 由 `ymdWindow` 抽出(分時圖成交點的日期界共用同一格式化)。
// 上面的 `ymdWindow` 四案即這次抽出的行為鎖(輸出逐字不變),下面兩案直接鎖 helper 本身。
describe("ymdOf(YYYYMMDD 本機時區)", () => {
  it("月 / 日補零到兩位", () => {
    expect(ymdOf(new Date(2026, 8, 5, 23, 59))).toBe("20260905");
  });

  it("Date 建構子溢出正規化:2/28 + 1 天 → 3/1(非閏年)", () => {
    expect(ymdOf(new Date(2026, 1, 28 + 1))).toBe("20260301");
  });
});
