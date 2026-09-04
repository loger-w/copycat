import { describe, expect, it } from "vitest";

import { aggregateLots, ymdOf, ymdWindow, type LadderLot } from "@/lib/ladder-lots";
import type { CapitalFill, CapitalOrder } from "@/types";

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

/** 一筆成交(fills 表列;`price` 是這一筆的成交價、`qty` 已是顯示單位)。 */
function fill(over: Partial<CapitalFill> = {}): CapitalFill {
  return {
    seq_no: "M1",
    stock_no: "2330",
    buy_sell: "B",
    flag_label: "現股",
    price: 100,
    qty: 1,
    unit: "張",
    date: TODAY,
    time: "09:01:30",
    code: "2330",
    ...over,
  };
}

/** 現股市價單(送群益 bstrPrice="0" → 回報委託價 0;本 app 送出的才有 `price_type`)。 */
function marketOrder(over: Partial<CapitalOrder> = {}): CapitalOrder {
  return filledOrder({ seq_no: "M1", price: 0, price_type: "market", ...over });
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

  it("他檔 / 委託價缺(null、0)且無 fills / key=null 全排除", () => {
    const orders = [
      order({ seq_no: "X", stock_no: "2317" }),
      order({ seq_no: "W", price: null }),
      // 委託價 0 不是價格(市價單回報)—— 過去會長出一格 key=0 的幽靈 entry(對不到任何列)
      order({ seq_no: "Z", price: 0, filled_qty: 1 }),
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

/** 市價單沒有委託價可當梯列鍵 → 已成交量改由 fills 表(逐筆真實成交價)落格;
 *  限價單路徑不看 fills(白名單 W1)。 */
describe("aggregateLots 市價單:成交量以 fills 表逐筆成交價落格", () => {
  it("市價買 2 張成交 100 / 100.5 各 1 → 兩格各 filled 1、qty 0、seqs 空(不取均價)", () => {
    const fills = [
      fill({ price: 100, qty: 1 }),
      fill({ price: 100.5, qty: 1, time: "09:01:31" }),
    ];
    const r = aggregateLots([marketOrder({ order_qty: 2, filled_qty: 2 })], "2330", STRICT, "股", fills);
    expect([...r.buy.keys()].sort((a, b) => a - b)).toEqual([100_000, 100_500]);
    expect(buyAt(r, 100_000)).toEqual({ qty: 0, filled: 1, seqs: [] });
    expect(buyAt(r, 100_500)).toEqual({ qty: 0, filled: 1, seqs: [] });
    expect(r.sell.size).toBe(0);
  });

  it("市價賣 → 側取 fill 的 buy_sell 進 sell;同價兩筆成交累加", () => {
    const fills = [
      fill({ buy_sell: "S", price: 99.5, qty: 1 }),
      fill({ buy_sell: "S", price: 99.5, qty: 2, time: "09:01:31" }),
    ];
    const r = aggregateLots(
      [marketOrder({ buy_sell: "S", order_qty: 3, filled_qty: 3 })],
      "2330",
      STRICT,
      "股",
      fills,
    );
    expect(r.buy.size).toBe(0);
    expect(r.sell.get(99_500)).toEqual({ qty: 0, filled: 3, seqs: [] });
  });

  it("price_type 未知(手機 APP 下的市價單)但委託價 0 → 同樣走 fills", () => {
    const r = aggregateLots(
      [marketOrder({ price_type: null })],
      "2330",
      STRICT,
      "股",
      [fill({ price: 100, qty: 2 })],
    );
    expect(buyAt(r)).toEqual({ qty: 0, filled: 2, seqs: [] });
  });

  it("price_type=market 但回報帶了名目價 → 仍以 fills 落格,不用名目價", () => {
    const r = aggregateLots(
      [marketOrder({ price: 98.4 })],
      "2330",
      STRICT,
      "股",
      [fill({ price: 98.35, qty: 2 })],
    );
    expect([...r.buy.keys()]).toEqual([98_350]);
  });

  it("fills 無同 seq 成交 / 他檔的 fills → 零 entry(未成交殘量沒有價位可掛)", () => {
    const active = marketOrder({ actionable: true, status_label: "已委託", filled_qty: 0 });
    const r = aggregateLots([active], "2330", STRICT, "股", [fill({ seq_no: "OTHER" })]);
    expect(r.buy.size).toBe(0);
  });

  it("日期界與零股閘沿用單的判準:終態 date 昨日 → 零 entry;unit 股 → 零 entry", () => {
    const fills = [fill({ price: 100, qty: 1 })];
    const stale = aggregateLots([marketOrder({ date: YESTERDAY })], "2330", STRICT, "股", fills);
    expect(stale.buy.size).toBe(0);
    const odd = aggregateLots(
      [marketOrder({ unit: "股", order_qty: 500, filled_qty: 500 })],
      "2330",
      STRICT,
      "股",
      [fill({ unit: "股", qty: 500 })],
    );
    expect(odd.buy.size).toBe(0);
  });
});

/** user 實遇:掛 98.5 買、成交 98.3,梯上徽章卡在 98.5 而成本線在 98.3 —— 兩條線說的不是同一件事。
 *  統一口徑:已成交量一律標在成交價;殘量與 seqs(刪單入口)留在委託價。 */
describe("aggregateLots 限價單:已成交量同樣以 fills 成交價落格,殘量留委託價", () => {
  it("限價 98.5 買全成交於 98.3 → 98.3 列 (1)、98.5 列無 entry", () => {
    const limit = filledOrder({ seq_no: "L1", price: 98.5, order_qty: 1, filled_qty: 1 });
    const r = aggregateLots([limit], "2330", STRICT, "股", [fill({ seq_no: "L1", price: 98.3 })]);
    expect([...r.buy.keys()]).toEqual([98_300]);
    expect(buyAt(r, 98_300)).toEqual({ qty: 0, filled: 1, seqs: [] });
  });

  it("活單 98.5 買 2 張、成交 98.3 × 1 → 委託價列 {qty 1, filled 0, seqs [L1]} + 成交價列 {qty 0, filled 1}", () => {
    const active = order({ seq_no: "L1", price: 98.5, order_qty: 2, filled_qty: 1 });
    const r = aggregateLots([active], "2330", STRICT, "股", [fill({ seq_no: "L1", price: 98.3 })]);
    expect(buyAt(r, 98_500)).toEqual({ qty: 1, filled: 0, seqs: ["L1"] });
    expect(buyAt(r, 98_300)).toEqual({ qty: 0, filled: 1, seqs: [] });
  });

  it("成交價 = 委託價(絕大多數限價成交)→ 與不傳 fills 完全同一格(白名單 W1)", () => {
    const active = order({ seq_no: "L1", price: 100, order_qty: 2, filled_qty: 1 });
    const withFills = aggregateLots([active], "2330", STRICT, "股", [fill({ seq_no: "L1", price: 100 })]);
    const without = aggregateLots([active], "2330", STRICT, "股");
    expect(buyAt(withFills)).toEqual({ qty: 1, filled: 1, seqs: ["L1"] });
    expect(buyAt(withFills)).toEqual(buyAt(without));
  });

  it("成交價不明(fills 給了但無同 seq 成交)→ 限價單退回委託價列(舊後端 / 載入中同此)", () => {
    const limit = filledOrder({ seq_no: "L1", price: 100, order_qty: 1, filled_qty: 1 });
    const r = aggregateLots([limit], "2330", STRICT, "股", [fill({ seq_no: "OTHER", price: 99 })]);
    expect([...r.buy.keys()]).toEqual([100_000]);
    expect(buyAt(r)).toEqual({ qty: 0, filled: 1, seqs: [] });
  });

  /** orders / fills 是兩支獨立 query(同一 WS 事件 invalidate、各自解析):fills 先到 2 筆而 orders
   *  仍 filled_qty 1 時,若照 fills 畫會變成 成交價列 2 + 委託價列殘 1 = 3 張(該單只有 2 張)。
   *  規則:fills 總量要**恰等於** `filled_qty` 才拿它定位,否則整張退回委託價(review spec F-02)。 */
  it("fills 總量 ≠ filled_qty(兩支 query 不同步)→ 整張退回委託價,不膨脹", () => {
    const ahead = order({ seq_no: "L1", price: 98.5, order_qty: 2, filled_qty: 1 });
    const twoFills = [fill({ seq_no: "L1", price: 98.3 }), fill({ seq_no: "L1", price: 98.3, time: "09:01:31" })];
    const r = aggregateLots([ahead], "2330", STRICT, "股", twoFills);
    expect([...r.buy.keys()]).toEqual([98_500]);
    expect(buyAt(r, 98_500)).toEqual({ qty: 1, filled: 1, seqs: ["L1"] });
    // 反向:orders 先到(filled_qty 2)、fills 只有 1 筆 → 同樣退回委託價,不短計
    const behind = order({ seq_no: "L1", price: 98.5, order_qty: 2, filled_qty: 2 });
    const r2 = aggregateLots([behind], "2330", STRICT, "股", [fill({ seq_no: "L1", price: 98.3 })]);
    expect(buyAt(r2, 98_500)).toEqual({ qty: 0, filled: 2, seqs: ["L1"] });
    expect(r2.buy.has(98_300)).toBe(false);
  });

  /** 異常 fill 列不得長出幽靈格:unit 股(store 除不盡退回股數)、price 0(不是價格)、側別空字串
   *  (store `a.buy_sell or ""`)—— 濾掉後總量對不上 → 退回委託價(review spec F-01/F-04/F-05)。 */
  it("異常 fill(unit 股 / price 0 / 側別空)不計入 → 總量不等 → 退回委託價", () => {
    const limit = filledOrder({ seq_no: "L1", price: 98.5, order_qty: 1, filled_qty: 1 });
    for (const bad of [
      fill({ seq_no: "L1", price: 98.3, unit: "股", qty: 1000 }),
      fill({ seq_no: "L1", price: 0 }),
      fill({ seq_no: "L1", price: 98.3, buy_sell: "" }),
    ]) {
      const r = aggregateLots([limit], "2330", STRICT, "股", [bad]);
      expect([...r.buy.keys()]).toEqual([98_500]);
      expect(r.buy.size + r.sell.size).toBe(1);
    }
  });

  it("終態限價單 date 昨日 → 即使 fills 有同 seq 成交也零 entry(日期界在單上判)", () => {
    const stale = filledOrder({ seq_no: "L1", price: 98.5, filled_qty: 1, date: YESTERDAY });
    const r = aggregateLots([stale], "2330", STRICT, "股", [fill({ seq_no: "L1", price: 98.3 })]);
    expect(r.buy.size).toBe(0);
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
