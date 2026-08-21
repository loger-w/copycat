import { describe, expect, it } from "vitest";

import {
  FUT_TICK_MILLI,
  buildFuturesLadder,
  edgeMilli,
  futCloseEstimate,
  futExchangeContract,
  futMarketEdgeMilli,
  splitMyLots,
  type FutOrderSource,
} from "@/lib/futures-ladder";
import { stkfutMarketEdgeMilli } from "@/lib/stkfut";

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

  /** T3(review round-1):`addQty` 的 actionable 閘無測 —— 既有終態案都是
   *  `order_qty === filled_qty`,`Math.max(0, 5-5)` 與閘的結果同為 0,把三元改成
   *  無條件 `Math.max(...)` 照樣全綠。部分成交後刪單(殘量 > 0 的終態單)才分得開:
   *  沒有閘的話期貨梯會畫出 3 口不存在的「未成交」量,而且 seqNos 空到無從刪起。 */
  it("部分成交後刪單(終態、殘量 > 0)→ qty 0、filled 留、seqNos 空", () => {
    const lots = splitMyLots(
      [o({ seq_no: "K", actionable: false, order_qty: 5, filled_qty: 2, date: TODAY })],
      "TXFI6",
      WINDOW,
    );
    expect(lots).toEqual([{ priceMilli: 23_000_000, qty: 0, filled: 2, seqNos: [] }]);
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

describe("edgeMilli 貼漲跌停選邊(raw 不 snap;≤0 = 缺值哨符)", () => {
  it("buy → 漲停、sell → 跌停", () => {
    expect(edgeMilli("buy", 25_300_000, 20_700_000)).toBe(25_300_000);
    expect(edgeMilli("sell", 25_300_000, 20_700_000)).toBe(20_700_000);
  });

  it("該側界缺 → null(另一側有值不代打)", () => {
    expect(edgeMilli("buy", null, 20_700_000)).toBeNull();
    expect(edgeMilli("sell", 25_300_000, null)).toBeNull();
  });

  it("不 snap 到合法檔位:非整 tick 的界原樣回傳", () => {
    expect(edgeMilli("buy", 25_300_500, 20_699_500)).toBe(25_300_500);
    expect(edgeMilli("sell", 25_300_500, 20_699_500)).toBe(20_699_500);
  });

  // 🔴 B11(SC-2):後端缺值以 0 給,0 不是「免費」的價 —— 放行的話市價鈕與平倉鍵
  // 都會拿一個假想界去送真錢單(stkfut 版早就擋,兩版口徑必須一致)。
  it("界為 0 或負(資料壞 / 後端缺值哨符)→ null", () => {
    expect(edgeMilli("buy", 0, 20_700_000)).toBeNull();
    expect(edgeMilli("sell", 25_300_000, 0)).toBeNull();
    expect(edgeMilli("buy", -1, 20_700_000)).toBeNull();
    expect(edgeMilli("sell", 25_300_000, -1)).toBeNull();
  });
});

describe("futMarketEdgeMilli 期貨市價邊價(FUT_TICK 對齊)", () => {
  it("buy → 漲停 floor 到 1 點、sell → 跌停 ceil 到 1 點(與 buildFuturesLadder 同口徑)", () => {
    expect(futMarketEdgeMilli("buy", 25_300_500, 20_699_500)).toBe(25_300_000);
    expect(futMarketEdgeMilli("sell", 25_300_500, 20_699_500)).toBe(20_700_000);
  });

  it("界已在合法檔位 → 原值不動", () => {
    expect(futMarketEdgeMilli("buy", 25_080_000, 20_520_000)).toBe(25_080_000);
    expect(futMarketEdgeMilli("sell", 25_080_000, 20_520_000)).toBe(20_520_000);
  });

  it("該側界缺 → null(另一側有值不代打)", () => {
    expect(futMarketEdgeMilli("buy", null, 20_520_000)).toBeNull();
    expect(futMarketEdgeMilli("sell", 25_080_000, null)).toBeNull();
  });

  // 🔴 B11(SC-2):守門在 edgeMilli,市價鈕連帶受益 —— 沒有的話 0 會 floor 成 0 送出去
  it("界為 0 / 負 → null(鎖鈕,不用假想界送真錢單)", () => {
    expect(futMarketEdgeMilli("buy", 0, 20_520_000)).toBeNull();
    expect(futMarketEdgeMilli("sell", 25_080_000, 0)).toBeNull();
    expect(futMarketEdgeMilli("buy", -1_000, 20_520_000)).toBeNull();
  });

  // 🔴 F1(review round-1):`edgeMilli` 的守門在 **snap 之前**,買側 floor 會把
  // `0 < upper < FUT_TICK` 的界壓成 0 —— 而 0 一路送出去就是「用 0 元送真錢單」。
  // 同一份行情下 `futCloseEstimate` 回傳前自己守 ≤0(回 null,平倉鍵鎖住),
  // 市價鈕卻拿到 0 而照樣可按 = 兩處對同一份行情給出不同答案。
  it("界正但 snap 後歸零 → null(不是 0;與平倉估價同號)", () => {
    expect(futMarketEdgeMilli("buy", 500, 20_000_000)).toBeNull();
  });
});

// 🔴 B11(SC-3):平倉估價原本吃 **raw** 界,與市價鈕的 snap 後邊價不同值 ——
// 同一個標的兩處顯示不同價,且未對齊的檔位券商直接退單。
describe("futCloseEstimate 平倉估價吃 snap 後邊價(edgeOf 注入)", () => {
  const pos = (qty: number) => ({ stock_no: "TXFI6", qty });
  /** 未對齊 FUT_TICK 的界(既有 fixture 都對齊了,對齊的值 snap 前後同值 = 測不出來) */
  const OFF = { upper: 25_080_400, lower: 20_520_600 };

  it("空單平倉(買)→ 漲停 floor 到 1 點(25_080_400 → 25_080 元)", () => {
    expect(futCloseEstimate(pos(-1), "TXFI6", OFF)).toBe(25_080);
  });

  it("多單平倉(賣)→ 跌停 ceil 到 1 點(20_520_600 → 20_521 元)", () => {
    expect(futCloseEstimate(pos(2), "TXFI6", OFF)).toBe(20_521);
  });

  it("界為 0 → null(守門在 edgeMilli,平倉鍵鎖住)", () => {
    expect(futCloseEstimate(pos(-1), "TXFI6", { upper: 0, lower: 20_520_000 })).toBeNull();
  });

  // review R5:回傳前自己再守一次 —— 注入者是呼叫端寫的,不能假設它守門
  it("注入的 edgeOf 不守門而回 0 → 仍 null(不依賴注入者)", () => {
    expect(futCloseEstimate(pos(-1), "TXFI6", OFF, () => 0)).toBeNull();
  });

  it("注入的 edgeOf 決定檔位口徑(個股期走股票 tick 表)", () => {
    // 買側往下收到 100 毫元檔:90_030 → 90_000 → 90 元
    expect(
      futCloseEstimate(pos(-1), "TXFI6", { upper: 90_030, lower: null }, (side, u, l) =>
        stkfutMarketEdgeMilli(side, { upper: u, lower: l }),
      ),
    ).toBe(90);
  });
});
