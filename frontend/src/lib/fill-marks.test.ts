import { describe, expect, it } from "vitest";

import {
  clampFillX,
  EMPTY_FILLS,
  EMPTY_MARKS,
  FILL_MARK,
  fillDates,
  fillLabel,
  fillPoints,
  fillsAtMinute,
  fillsByCode,
  fillTrianglePoints,
  projectFills,
  stkfutFillKey,
  type FillPoint,
} from "@/lib/fill-marks";
import { minuteToX, SPOT_WINDOW } from "@/lib/stock-intraday-svg";
import type { CapitalOrder } from "@/types";

const TODAY = "20260813";
const YESTERDAY = "20260812";
const BEFORE = "20260811";
const DATES = { today: TODAY, yesterday: YESTERDAY };

/** 已成交的活單(部分成交):`avg_fill_price` / `time` 齊、`filled_qty > 0` */
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
    status_label: "部分成交",
    price: 100,
    avg_fill_price: 100,
    order_qty: 3,
    filled_qty: 1,
    unit: "張",
    date: TODAY,
    time: "09:01:30",
    pre_order: false,
    error_msg: null,
    actionable: true,
    price_type: null,
    raw: "",
    ...over,
  };
}

const MIN_901 = 9 * 60 + 1;
const MIN_902 = 9 * 60 + 2;

describe("fillDates(YYYYMMDD 減一日)", () => {
  it("同月內減一日", () => {
    expect(fillDates("20260813")).toEqual({ today: "20260813", yesterday: "20260812" });
  });

  it("跨月:月初退到上個月最後一日(非閏年 3/1 → 2/28)", () => {
    expect(fillDates("20260301")).toEqual({ today: "20260301", yesterday: "20260228" });
  });

  it("跨年:1/1 退到去年 12/31", () => {
    expect(fillDates("20260101")).toEqual({ today: "20260101", yesterday: "20251231" });
  });
});

describe("fillPoints 過濾條件", () => {
  it("key === null → 直接回 EMPTY_FILLS(同一 identity)", () => {
    expect(fillPoints([order()], null, DATES)).toBe(EMPTY_FILLS);
  });

  it("零筆 → 回 EMPTY_FILLS(同一 identity;memo 不被打穿)", () => {
    expect(fillPoints([], "2330", DATES)).toBe(EMPTY_FILLS);
    expect(fillPoints(undefined, "2330", DATES)).toBe(EMPTY_FILLS);
    expect(fillPoints([order({ filled_qty: 0 })], "2330", DATES)).toBe(EMPTY_FILLS);
  });

  it("比對鍵不符 → 排除", () => {
    expect(fillPoints([order({ stock_no: "2317" })], "2330", DATES)).toEqual([]);
  });

  it("filled_qty === 0 → 排除(只掛單未成交)", () => {
    expect(fillPoints([order({ filled_qty: 0, avg_fill_price: null })], "2330", DATES)).toEqual([]);
  });

  it("avg_fill_price === null 但 filled_qty > 0(回報欄位缺)→ 排除", () => {
    expect(fillPoints([order({ avg_fill_price: null })], "2330", DATES)).toEqual([]);
  });

  it("time === null → 排除(無分鐘可落點)", () => {
    expect(fillPoints([order({ time: null })], "2330", DATES)).toEqual([]);
  });

  it("buy_sell 非 B/S → 整筆排除(無側可歸)", () => {
    expect(fillPoints([order({ buy_sell: null })], "2330", DATES)).toEqual([]);
    expect(fillPoints([order({ buy_sell: "X" })], "2330", DATES)).toEqual([]);
  });

  it("excludeUnit 命中 → 整筆排除(現股零股單)", () => {
    const zero = [order({ unit: "股", order_qty: 1000, filled_qty: 1000 })];
    expect(fillPoints(zero, "2330", DATES, "股")).toEqual([]);
    // 不傳 excludeUnit(個股期態)→ 不設單位閘
    expect(fillPoints(zero, "2330", DATES)).toHaveLength(1);
  });

  it("今日 date 的終態單(全部成交)→ 計入", () => {
    const done = order({ actionable: false, status_label: "全部成交", filled_qty: 3 });
    expect(fillPoints([done], "2330", DATES)).toEqual([
      { minute: MIN_901, priceMilli: 100_000, side: "B", qty: 3 },
    ]);
  });

  it("昨日 date + actionable + filled → 計入(盤後預約單今日成交)", () => {
    const pre = order({ date: YESTERDAY, pre_order: true });
    expect(fillPoints([pre], "2330", DATES)).toHaveLength(1);
  });

  it("昨日 date + 非活單 → 排除(昨日的成交不畫上今日圖)", () => {
    expect(fillPoints([order({ date: YESTERDAY, actionable: false })], "2330", DATES)).toEqual([]);
  });

  it("前日 date + actionable → 排除(跨日不清的幽靈活單不無界計入)", () => {
    expect(fillPoints([order({ date: BEFORE })], "2330", DATES)).toEqual([]);
  });

  it("date === null → 排除", () => {
    expect(fillPoints([order({ date: null })], "2330", DATES)).toEqual([]);
  });
});

describe("fillPoints 聚合與排序", () => {
  it("元 → 毫元(四捨五入)", () => {
    const r = fillPoints([order({ avg_fill_price: 100.335 })], "2330", DATES);
    expect(r[0]!.priceMilli).toBe(100_335);
  });

  it("同分鐘同向合併:qty 加總、price 量加權平均後取整(100000@2 + 101000@1 → 100333)", () => {
    const r = fillPoints(
      [
        order({ seq_no: "A", avg_fill_price: 100, filled_qty: 2 }),
        order({ seq_no: "B", avg_fill_price: 101, filled_qty: 1, time: "09:01:59" }),
      ],
      "2330",
      DATES,
    );
    expect(r).toEqual([{ minute: MIN_901, priceMilli: 100_333, side: "B", qty: 3 }]);
  });

  it("同分鐘買賣各一 → 兩點(不合併),B 先 S 後", () => {
    const r = fillPoints(
      [
        order({ seq_no: "S", buy_sell: "S", avg_fill_price: 101 }),
        order({ seq_no: "B", buy_sell: "B", avg_fill_price: 100 }),
      ],
      "2330",
      DATES,
    );
    expect(r).toEqual([
      { minute: MIN_901, priceMilli: 100_000, side: "B", qty: 1 },
      { minute: MIN_901, priceMilli: 101_000, side: "S", qty: 1 },
    ]);
  });

  it("跨分鐘同向不合併", () => {
    const r = fillPoints(
      [
        order({ seq_no: "A", filled_qty: 1 }),
        order({ seq_no: "B", filled_qty: 2, time: "09:02:00" }),
      ],
      "2330",
      DATES,
    );
    expect(r.map((p) => [p.minute, p.qty])).toEqual([
      [MIN_901, 1],
      [MIN_902, 2],
    ]);
  });

  it("輸出依 minute 升冪(輸入亂序)", () => {
    const r = fillPoints(
      [
        order({ seq_no: "C", time: "13:00:00" }),
        order({ seq_no: "A", time: "09:02:00" }),
        order({ seq_no: "B", time: "09:01:00" }),
      ],
      "2330",
      DATES,
    );
    expect(r.map((p) => p.minute)).toEqual([MIN_901, MIN_902, 13 * 60]);
  });
});

describe("fillsByCode 分組(圖牆)", () => {
  it("按 stock_no 分組;零筆的 code 不入 map", () => {
    const m = fillsByCode(
      [
        order({ seq_no: "A", stock_no: "2330", avg_fill_price: 1000, filled_qty: 2 }),
        order({ seq_no: "B", stock_no: "2317", avg_fill_price: 200, buy_sell: "S" }),
        // 未成交 → 2454 整筆不產生 entry
        order({ seq_no: "C", stock_no: "2454", filled_qty: 0, avg_fill_price: null }),
      ],
      DATES,
    );
    expect([...m.keys()].sort()).toEqual(["2317", "2330"]);
    expect(m.get("2330")).toEqual([{ minute: MIN_901, priceMilli: 1_000_000, side: "B", qty: 2 }]);
    expect(m.get("2317")).toEqual([{ minute: MIN_901, priceMilli: 200_000, side: "S", qty: 1 }]);
    expect(m.get("2454")).toBeUndefined();
  });

  it("同 code 同分鐘同向仍合併;excludeUnit 生效", () => {
    const orders = [
      order({ seq_no: "A", avg_fill_price: 100, filled_qty: 2 }),
      order({ seq_no: "B", avg_fill_price: 101, filled_qty: 1 }),
      order({ seq_no: "Z", stock_no: "2317", unit: "股", filled_qty: 1000 }),
    ];
    const m = fillsByCode(orders, DATES, "股");
    expect(m.get("2330")).toEqual([{ minute: MIN_901, priceMilli: 100_333, side: "B", qty: 3 }]);
    expect(m.has("2317")).toBe(false);
  });

  it("orders undefined → 空 map", () => {
    expect(fillsByCode(undefined, DATES).size).toBe(0);
  });
});

describe("stkfutFillKey", () => {
  it("合法 YYYYMM → 期交所契約碼", () => {
    expect(stkfutFillKey("CDF", "202608")).toBe("CDFH6");
  });

  it("非法 ym(throw)→ null,不炸", () => {
    expect(stkfutFillKey("CDF", "2026")).toBeNull();
    expect(stkfutFillKey("CDF", "202613")).toBeNull();
  });
});

describe("clampFillX", () => {
  const edge = FILL_MARK.halfW + FILL_MARK.halo / 2; // 視覺外緣半寬 = 4

  it("左端出界 → 夾到外緣半寬", () => {
    expect(clampFillX(0, 800)).toBe(edge);
  });

  it("右端出界 → 夾到 w − 外緣半寬", () => {
    expect(clampFillX(800, 800)).toBe(800 - edge);
  });

  it("窗內不動", () => {
    expect(clampFillX(400, 800)).toBe(400);
  });
});

describe("fillTrianglePoints", () => {
  it("B = 尖端在成交價、體在下(▲)", () => {
    expect(fillTrianglePoints(100, 50, "B")).toBe("100,50 96.5,56 103.5,56");
  });

  it("S = 尖端在成交價、體在上(▼)", () => {
    expect(fillTrianglePoints(100, 50, "S")).toBe("100,50 96.5,44 103.5,44");
  });

  it("style 可換(尺寸不硬編在字串裡)", () => {
    expect(fillTrianglePoints(10, 20, "B", { halfW: 2, height: 4, halo: 1 })).toBe(
      "10,20 8,24 12,24",
    );
  });
});

describe("projectFills", () => {
  const GEO = { toY: (p: number) => 200 - p / 1000, yDomain: [100_000, 110_000] as const };
  const W = 800;
  const pt = (over: Partial<FillPoint> = {}): FillPoint => ({
    minute: MIN_901,
    priceMilli: 105_000,
    side: "B",
    qty: 1,
    ...over,
  });

  it("窗內 + 域內 → 尖端 (x, y) = (clampFillX(minuteToX), toY(price))", () => {
    const r = projectFills([pt()], GEO, W, SPOT_WINDOW);
    expect(r).toHaveLength(1);
    expect(r[0]!.x).toBeCloseTo(clampFillX(minuteToX(MIN_901, W, SPOT_WINDOW), W), 6);
    expect(r[0]!.y).toBeCloseTo(GEO.toY(105_000), 6);
    // FillPoint 欄位原樣帶著走(readout / testid 用得到)
    expect(r[0]!.side).toBe("B");
    expect(r[0]!.qty).toBe(1);
    expect(r[0]!.minute).toBe(MIN_901);
  });

  it("分鐘落在 x 窗外 → 不畫(盤後零股 14:30 / 開盤前)", () => {
    expect(projectFills([pt({ minute: 14 * 60 + 30 })], GEO, W, SPOT_WINDOW)).toBe(EMPTY_MARKS);
    expect(projectFills([pt({ minute: 8 * 60 + 44 })], GEO, W, SPOT_WINDOW)).toBe(EMPTY_MARKS);
  });

  it("價格落在 yDomain 外 → 不畫(同 overlay / 極值既有規則)", () => {
    expect(projectFills([pt({ priceMilli: 99_999 })], GEO, W, SPOT_WINDOW)).toBe(EMPTY_MARKS);
    expect(projectFills([pt({ priceMilli: 110_001 })], GEO, W, SPOT_WINDOW)).toBe(EMPTY_MARKS);
    // 域界兩端本身在內
    expect(projectFills([pt({ priceMilli: 100_000 })], GEO, W, SPOT_WINDOW)).toHaveLength(1);
    expect(projectFills([pt({ priceMilli: 110_000 })], GEO, W, SPOT_WINDOW)).toHaveLength(1);
  });

  // 夾制拿掉的話 x 會停在未夾制的 37(> w − 外緣半寬),三角右緣被 viewBox 裁成缺角
  it("極窄容器:x 走 clampFillX 夾制", () => {
    const narrow = 40; // plotWidth 被 clamp 成 1
    expect(minuteToX(SPOT_WINDOW.end, narrow, SPOT_WINDOW)).toBe(37);
    const r = projectFills([pt({ minute: SPOT_WINDOW.end })], GEO, narrow, SPOT_WINDOW);
    expect(r[0]!.x).toBe(narrow - (FILL_MARK.halfW + FILL_MARK.halo / 2));
  });

  it("零筆 → EMPTY_MARKS(同一 identity)", () => {
    expect(projectFills(EMPTY_FILLS, GEO, W, SPOT_WINDOW)).toBe(EMPTY_MARKS);
  });
});

describe("fillsAtMinute / fillLabel", () => {
  const B: FillPoint = { minute: MIN_901, priceMilli: 2_380_000, side: "B", qty: 2 };
  const S: FillPoint = { minute: MIN_901, priceMilli: 2_385_000, side: "S", qty: 1 };
  const LATER: FillPoint = { minute: MIN_902, priceMilli: 2_390_000, side: "B", qty: 5 };
  /** readout 既有價格格式化的替身(毫元 → 元) */
  const fmt = (p: number): string => String(p / 1000);

  it("fillsAtMinute 只取該分鐘(順序保持 B 先 S 後)", () => {
    expect(fillsAtMinute([B, S, LATER], MIN_901)).toEqual([B, S]);
    expect(fillsAtMinute([B, S, LATER], MIN_902)).toEqual([LATER]);
  });

  it("fillsAtMinute 無成交分鐘 → EMPTY_FILLS", () => {
    expect(fillsAtMinute([B, S], 13 * 60)).toBe(EMPTY_FILLS);
  });

  it("fillLabel 單側", () => {
    expect(fillLabel([B], fmt)).toBe("買 2@2380");
    expect(fillLabel([S], fmt)).toBe("賣 1@2385");
  });

  it("fillLabel 雙側:單一空格連接、不帶單位", () => {
    expect(fillLabel([B, S], fmt)).toBe("買 2@2380 賣 1@2385");
  });

  it("fillLabel 零筆 → 空字串", () => {
    expect(fillLabel(EMPTY_FILLS, fmt)).toBe("");
  });
});
