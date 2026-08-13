import { describe, expect, it } from "vitest";

import {
  FUT_TICK_MILLI,
  buildFuturesLadder,
  futExchangeContract,
  splitMyLots,
  type FutOrderSource,
} from "@/lib/futures-ladder";

const noDepth = { bids: [], asks: [], myLots: [] };
const wide = { upperMilli: 25_300_000, lowerMilli: 20_700_000 };

describe("buildFuturesLadder 期貨階梯生成", () => {
  it("tick 固定 1 點 = 1000 毫點", () => expect(FUT_TICK_MILLI).toBe(1_000));

  it("以 center 為中心、高價在前,步進固定 1000 毫點", () => {
    const rows = buildFuturesLadder({ centerMilli: 23_000_000, ...wide, ...noDepth, rows: 3 });
    expect(rows.map((r) => r.priceMilli)).toEqual([
      23_003_000, 23_002_000, 23_001_000, 23_000_000, 22_999_000, 22_998_000, 22_997_000,
    ]);
    expect(rows[3]!.isCenter).toBe(true);
    expect(rows.filter((r) => r.isCenter)).toHaveLength(1);
  });

  it("rows 預設 60:上下各 60 檔共 121 列、center 置中", () => {
    const rows = buildFuturesLadder({ centerMilli: 23_000_000, ...wide, ...noDepth });
    expect(rows).toHaveLength(121);
    expect(rows[60]!.priceMilli).toBe(23_000_000);
    expect(rows[60]!.isCenter).toBe(true);
  });

  it("上下界 clamp:不越過 upperMilli / lowerMilli", () => {
    const rows = buildFuturesLadder({
      centerMilli: 23_000_000,
      upperMilli: 23_002_000,
      lowerMilli: 22_999_000,
      ...noDepth,
      rows: 5,
    });
    expect(rows.map((r) => r.priceMilli)).toEqual([
      23_002_000, 23_001_000, 23_000_000, 22_999_000,
    ]);
  });

  it("clickable = 離 center ±5% 內(含邊界)", () => {
    const rows = buildFuturesLadder({
      centerMilli: 100_000,
      upperMilli: 110_000,
      lowerMilli: 90_000,
      ...noDepth,
      rows: 10,
    });
    const at = (p: number) => rows.find((r) => r.priceMilli === p)!;
    expect(at(105_000).clickable).toBe(true); // 恰在 +5% 邊界(含)
    expect(at(106_000).clickable).toBe(false); // 超過
    expect(at(95_000).clickable).toBe(true);
    expect(at(94_000).clickable).toBe(false);
  });

  it("五檔量與我方掛單對到價位列;範圍外為 0 / 空陣列", () => {
    const rows = buildFuturesLadder({
      centerMilli: 23_000_000,
      ...wide,
      bids: [{ priceMilli: 22_999_000, qty: 45 }],
      asks: [{ priceMilli: 23_001_000, qty: 88 }],
      myLots: [{ priceMilli: 22_998_000, qty: 3, filled: 2, seqNos: ["A1", "A2"] }],
      rows: 5,
    });
    const at = (p: number) => rows.find((r) => r.priceMilli === p)!;
    expect(at(22_999_000).bidQty).toBe(45);
    expect(at(23_001_000).askQty).toBe(88);
    expect(at(22_998_000).myQty).toBe(3);
    expect(at(22_998_000).mySeqNos).toEqual(["A1", "A2"]);
    // 已成交量也要烘進 row(SC-4:紅方格文字 `未成交(已成交)` 的來源)
    expect(at(22_998_000).myFilled).toBe(2);
    expect(at(23_000_000).bidQty).toBe(0);
    expect(at(23_000_000).askQty).toBe(0);
    expect(at(23_000_000).myQty).toBe(0);
    expect(at(23_000_000).mySeqNos).toEqual([]);
    expect(at(23_000_000).myFilled).toBe(0);
  });

  it("center 非 tick 對齊 → snap down 到合法檔位再置中", () => {
    const rows = buildFuturesLadder({ centerMilli: 23_000_400, ...wide, ...noDepth, rows: 2 });
    expect(rows.find((r) => r.isCenter)!.priceMilli).toBe(23_000_000);
  });

  it("center > upper → clamp 到 upper:置中列 = upper 且無更高列(review C5)", () => {
    const rows = buildFuturesLadder({ centerMilli: 25_400_000, ...wide, ...noDepth, rows: 3 });
    expect(rows.map((r) => r.priceMilli)).toEqual([
      25_300_000, 25_299_000, 25_298_000, 25_297_000,
    ]);
    expect(rows[0]!.priceMilli).toBe(25_300_000); // = upperMilli
    expect(rows[0]!.isCenter).toBe(true);
    expect(rows.filter((r) => r.isCenter)).toHaveLength(1);
  });

  it("center < lower → clamp 到 lower:置中列 = lower 且無更低列(review C5)", () => {
    const rows = buildFuturesLadder({ centerMilli: 20_600_000, ...wide, ...noDepth, rows: 3 });
    expect(rows.map((r) => r.priceMilli)).toEqual([
      20_703_000, 20_702_000, 20_701_000, 20_700_000,
    ]);
    expect(rows.at(-1)!.priceMilli).toBe(20_700_000); // = lowerMilli
    expect(rows.at(-1)!.isCenter).toBe(true);
    expect(rows.filter((r) => r.isCenter)).toHaveLength(1);
  });

  it("界反轉(upper < lower)→ 空 rows", () => {
    expect(
      buildFuturesLadder({
        centerMilli: 23_000_000,
        upperMilli: 22_000_000,
        lowerMilli: 23_000_000,
        ...noDepth,
      }),
    ).toEqual([]);
  });
});

describe("splitMyLots 該契約活單按價位聚合", () => {
  const TODAY = "20260813";
  const YESTERDAY = "20260812";
  /** 期貨梯口徑 = ±1 日窗(夜盤跨午夜語意未實證,兩種假設皆涵蓋) */
  const WINDOW = new Set([YESTERDAY, TODAY, "20260814"]);

  const o = (over: Partial<FutOrderSource>): FutOrderSource => ({
    seq_no: "S1",
    stock_no: "TXFI6",
    buy_sell: "B",
    price: 23_000,
    order_qty: 2,
    filled_qty: 0,
    actionable: true,
    date: TODAY,
    ...over,
  });

  it("同價聚合:殘量相加、seqNos 併列;不同價分列且高價在前", () => {
    const lots = splitMyLots(
      [
        o({ seq_no: "A", price: 23_000, order_qty: 3, filled_qty: 1 }), // 殘 2
        o({ seq_no: "B", price: 23_000, order_qty: 1 }),
        o({ seq_no: "C", price: 22_990, order_qty: 5 }),
      ],
      "TXFI6",
      WINDOW,
    );
    expect(lots).toEqual([
      { priceMilli: 23_000_000, qty: 3, filled: 1, seqNos: ["A", "B"] },
      { priceMilli: 22_990_000, qty: 5, filled: 0, seqNos: ["C"] },
    ]);
  });

  it("過濾:他契約 / 市價(price=null)/ 終態且日期界外 全排除;actionable 殘 0 仍出 entry", () => {
    const lots = splitMyLots(
      [
        o({ seq_no: "X", stock_no: "MXFI6" }),
        o({ seq_no: "Y", actionable: false, date: "20260701" }),
        // actionable 且殘 0(N 未到):qty 不計但 seq 要收 —— 刪單入口不得消失
        o({ seq_no: "Z", order_qty: 2, filled_qty: 2 }),
        o({ seq_no: "W", price: null }),
      ],
      "TXFI6",
      WINDOW,
    );
    expect(lots).toEqual([{ priceMilli: 23_000_000, qty: 0, filled: 2, seqNos: ["Z"] }]);
  });

  it("終態全成交單:日期界內 → filled entry 且 seqNos 空;界外 / date=null → 零痕跡", () => {
    const inWindow = splitMyLots(
      [o({ seq_no: "F", actionable: false, order_qty: 2, filled_qty: 2, date: YESTERDAY })],
      "TXFI6",
      WINDOW,
    );
    expect(inWindow).toEqual([{ priceMilli: 23_000_000, qty: 0, filled: 2, seqNos: [] }]);
    const stale = splitMyLots(
      [o({ seq_no: "F", actionable: false, order_qty: 2, filled_qty: 2, date: "20260701" })],
      "TXFI6",
      WINDOW,
    );
    expect(stale).toEqual([]);
    const nodate = splitMyLots(
      [o({ seq_no: "F", actionable: false, order_qty: 2, filled_qty: 2, date: null })],
      "TXFI6",
      WINDOW,
    );
    expect(nodate).toEqual([]);
  });

  it("失敗 / 退單(終態、filled 0)→ 零痕跡", () => {
    const lots = splitMyLots(
      [o({ seq_no: "E", actionable: false, order_qty: 2, filled_qty: 0 })],
      "TXFI6",
      WINDOW,
    );
    expect(lots).toEqual([]);
  });

  it("價 float → 毫點 round(100.1 × 1000 的浮點殘差收斂)", () => {
    const lots = splitMyLots([o({ price: 100.1 })], "TXFI6", WINDOW);
    expect(lots).toEqual([{ priceMilli: 100_100, qty: 2, filled: 0, seqNos: ["S1"] }]);
  });
});

describe("futExchangeContract 商品 + YYYYMM → 期交所契約碼", () => {
  it("202609 → 月碼 I + 年末 6", () => {
    expect(futExchangeContract("TXF", "202609")).toBe("TXFI6");
  });

  it("202701 → 月碼 A + 年末 7;產品碼原樣前綴", () => {
    expect(futExchangeContract("TMF", "202701")).toBe("TMFA7");
    expect(futExchangeContract("MXF", "202612")).toBe("MXFL6");
  });

  it("非法月份 throw", () => {
    expect(() => futExchangeContract("TXF", "202613")).toThrow();
    expect(() => futExchangeContract("TXF", "bad")).toThrow();
  });
});
