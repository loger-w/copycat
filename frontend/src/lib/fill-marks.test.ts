import { describe, expect, it } from "vitest";

import {
  alldayFillPoints,
  clampFillX,
  EMPTY_FILLS,
  EMPTY_MARKS,
  FILL_MARK,
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
import type { CapitalFill } from "@/types";

const TODAY = "20260813";
const YESTERDAY = "20260812";

/** 當日一筆成交(精確版 L76:`price` 是這一筆的成交價、`date` 是到達日)。 */
function fill(over: Partial<CapitalFill> = {}): CapitalFill {
  return {
    seq_no: "S1",
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

const MIN_901 = 9 * 60 + 1;
const MIN_902 = 9 * 60 + 2;

describe("fillPoints 過濾條件(精確版)", () => {
  it("key === null → 直接回 EMPTY_FILLS(同一 identity)", () => {
    expect(fillPoints([fill()], null, TODAY)).toBe(EMPTY_FILLS);
  });

  it("零筆 → 回 EMPTY_FILLS(同一 identity;memo 不被打穿)", () => {
    expect(fillPoints([], "2330", TODAY)).toBe(EMPTY_FILLS);
    expect(fillPoints(undefined, "2330", TODAY)).toBe(EMPTY_FILLS);
    expect(fillPoints([fill({ qty: 0 })], "2330", TODAY)).toBe(EMPTY_FILLS);
  });

  it("比對鍵不符 → 排除(比對走 stock_no:個股期圖用契約碼撿自己的單)", () => {
    expect(fillPoints([fill({ stock_no: "2317", code: "2317" })], "2330", TODAY)).toEqual([]);
  });

  it("price <= 0 / time null / 非 B|S → 整筆排除", () => {
    expect(fillPoints([fill({ price: 0 })], "2330", TODAY)).toEqual([]);
    expect(fillPoints([fill({ time: null })], "2330", TODAY)).toEqual([]);
    expect(fillPoints([fill({ buy_sell: "X" })], "2330", TODAY)).toEqual([]);
  });

  it("excludeUnit 命中 → 整筆排除(現股零股單);不傳(個股期態)不設單位閘", () => {
    const zero = [fill({ unit: "股", qty: 1000 })];
    expect(fillPoints(zero, "2330", TODAY, "股")).toEqual([]);
    expect(fillPoints(zero, "2330", TODAY)).toHaveLength(1);
  });

  it("date 非今日 → 排除(逐筆自帶真實到達日;近似版「昨日活單」半條退役)", () => {
    expect(fillPoints([fill({ date: YESTERDAY })], "2330", TODAY)).toEqual([]);
  });
});

describe("fillPoints 合併與排序(精確版:同點無損合併,不做量加權)", () => {
  it("元 → 毫元(四捨五入)", () => {
    const r = fillPoints([fill({ price: 100.335 })], "2330", TODAY);
    expect(r[0]!.priceMilli).toBe(100_335);
  });

  it("同分鐘同向**不同價** → 各自一點(近似版會加權壓成一點;每筆一標記的語意)", () => {
    const r = fillPoints(
      [
        fill({ seq_no: "A", price: 100, qty: 2 }),
        fill({ seq_no: "A", price: 101, qty: 1, time: "09:01:59" }),
      ],
      "2330",
      TODAY,
    );
    expect(r).toEqual([
      { minute: MIN_901, priceMilli: 100_000, side: "B", qty: 2 },
      { minute: MIN_901, priceMilli: 101_000, side: "B", qty: 1 },
    ]);
  });

  it("同 (分鐘, 側, 價位) 無損合併:qty 相加(重疊三角只是雜訊)", () => {
    const r = fillPoints([fill({ qty: 2 }), fill({ qty: 1, time: "09:01:59" })], "2330", TODAY);
    expect(r).toEqual([{ minute: MIN_901, priceMilli: 100_000, side: "B", qty: 3 }]);
  });

  it("同分鐘買賣各一 → 兩點,B 先 S 後", () => {
    const r = fillPoints(
      [fill({ buy_sell: "S", price: 101 }), fill({ buy_sell: "B", price: 100 })],
      "2330",
      TODAY,
    );
    expect(r).toEqual([
      { minute: MIN_901, priceMilli: 100_000, side: "B", qty: 1 },
      { minute: MIN_901, priceMilli: 101_000, side: "S", qty: 1 },
    ]);
  });

  it("輸出依 minute 升冪(輸入亂序)", () => {
    const r = fillPoints(
      [fill({ time: "13:00:00" }), fill({ time: "09:02:00" }), fill({ time: "09:01:00" })],
      "2330",
      TODAY,
    );
    expect(r.map((p) => p.minute)).toEqual([MIN_901, MIN_902, 13 * 60]);
  });
});

describe("fillsByCode 分組(圖牆)", () => {
  it("按 wire code 分組;零筆的 code 不入 map", () => {
    const m = fillsByCode(
      [
        fill({ seq_no: "A", stock_no: "2330", code: "2330", price: 1000, qty: 2 }),
        fill({ seq_no: "B", stock_no: "2317", code: "2317", price: 200, buy_sell: "S" }),
      ],
      TODAY,
    );
    expect([...m.keys()].sort()).toEqual(["2317", "2330"]);
    expect(m.get("2330")).toEqual([{ minute: MIN_901, priceMilli: 1_000_000, side: "B", qty: 2 }]);
    expect(m.get("2317")).toEqual([{ minute: MIN_901, priceMilli: 200_000, side: "S", qty: 1 }]);
    expect(m.get("2454")).toBeUndefined();
  });

  it("個股期成交(契約碼 + code 反查股號)落到該股的卡(L444);反查不到退回 stock_no", () => {
    const m = fillsByCode(
      [
        fill({ seq_no: "F", stock_no: "CDFH6", code: "2330", unit: "口", price: 590 }),
        fill({ seq_no: "G", stock_no: "XXFH6", code: null, unit: "口", price: 10 }),
      ],
      TODAY,
    );
    expect(m.get("2330")).toEqual([{ minute: MIN_901, priceMilli: 590_000, side: "B", qty: 1 }]);
    expect(m.has("XXFH6")).toBe(true); // 反查不到:只會被合約鍵的圖撿到,不進任何股號卡
  });

  it("excludeUnit 生效(排零股)", () => {
    const m = fillsByCode(
      [fill(), fill({ seq_no: "Z", stock_no: "2317", code: "2317", unit: "股", qty: 1000 })],
      TODAY,
      "股",
    );
    expect(m.has("2330")).toBe(true);
    expect(m.has("2317")).toBe(false);
  });

  it("fills undefined → 空 map", () => {
    expect(fillsByCode(undefined, TODAY).size).toBe(0);
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

  /** 🔴 cr1 A-1:窗過濾必須寫成**正向條件的否定**(同 `stock-accum.ts::foldVp` review A3)。
   *  `minute < start || minute > end` 對 `NaN` 的兩個比較都是 false —— 時間戳解不出分鐘的
   *  壞單會整筆漏進渲染,長出一個 `x = NaN` 的 polygon(SVG 對 NaN points 靜默不畫,
   *  但 readout 的「成交」欄照樣追加,而畫面上沒有三角可對照)。 */
  it("minute 為 NaN(時間戳解不出分鐘)→ 不畫", () => {
    expect(projectFills([pt({ minute: NaN })], GEO, W, SPOT_WINDOW)).toBe(EMPTY_MARKS);
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

// ---------------------------------------------------------------------------
// N043 / N070:近全軸(期貨分時)的成交點
// ---------------------------------------------------------------------------

/** 期貨成交:`stock_no` 放期交所契約碼,單位「口」。 */
function futFill(over: Partial<CapitalFill> = {}): CapitalFill {
  return fill({
    stock_no: "TXFH6",
    code: null,
    unit: "口",
    date: "20260821",
    time: "09:30:00",
    price: 23_000,
    qty: 2,
    ...over,
  });
}

/** 錨定日 2026-08-21(週五)的近全軸索引(期望值不由 alldayIndexOf 算回來:段長寫死推導;
 *  mod/futures-day-1500 起 15:00 夜盤起算)。
 *  夜盤前半 1501 起 offset 0 → 08-20 22:00 = 419;夜盤後半 0000 起 offset 539 → 08-21 01:00 = 599;
 *  空檔 225 格後日盤段 0846 起 offset 1065 → 0930 = 1065 + 44 = 1109。 */
const IDX_0930 = 1109;
const IDX_2200 = 419;
const IDX_0100 = 599;
const ANCHOR = "2026-08-21";

describe("alldayFillPoints — 近全軸日期界(前一日曆日夜盤的成交屬本錨定日)", () => {
  it("日盤成交 → 軸索引 = 段內偏移(09:30 → 1109)", () => {
    const r = alldayFillPoints([futFill()], "TXFH6", ANCHOR);
    expect(r).toEqual([{ minute: IDX_0930, priceMilli: 23_000_000, side: "B", qty: 2 }]);
  });

  it("**前一日曆日夜盤 22:00 的成交屬本錨定日** → 索引 419(夜盤前半段)", () => {
    const r = alldayFillPoints([futFill({ date: "20260820", time: "22:00:00" })], "TXFH6", ANCHOR);
    expect(r[0]!.minute).toBe(IDX_2200);
  });

  it("同日曆日凌晨 01:00 的成交(前一日夜盤後半)→ 索引 599,不被日期界丟掉", () => {
    const r = alldayFillPoints([futFill({ time: "01:00:00" })], "TXFH6", ANCHOR);
    expect(r[0]!.minute).toBe(IDX_0100);
  });

  it("次一日曆日的**日盤**成交(錨定日 = 08-22)→ 不畫在 08-21 的圖上", () => {
    const r = alldayFillPoints(
      [futFill({ date: "20260822", time: "09:30:00" })],
      "TXFH6",
      ANCHOR,
    );
    expect(r).toBe(EMPTY_FILLS);
  });

  it("同日曆日夜盤(08-21 22:00,週五夜 → 錨定週一 08-24)→ 不畫在 08-21 的圖上", () => {
    const r = alldayFillPoints([futFill({ time: "22:00:00" })], "TXFH6", ANCHOR);
    expect(r).toBe(EMPTY_FILLS);
  });

  it("一天之外的成交(14:30,13:46–15:00 不在近全軸上)→ 不畫(不夾到最近的段界)", () => {
    const r = alldayFillPoints([futFill({ time: "14:30:00" })], "TXFH6", ANCHOR);
    expect(r).toBe(EMPTY_FILLS);
  });

  it("契約碼不符 / key null → 零筆(同 fillPoints 的 guard)", () => {
    expect(alldayFillPoints([futFill()], "MXFH6", ANCHOR)).toBe(EMPTY_FILLS);
    expect(alldayFillPoints([futFill()], null, ANCHOR)).toBe(EMPTY_FILLS);
  });

  it("同索引同向不同價 → 各自一點(精確版;與 fillPoints 同一支聚合)", () => {
    const r = alldayFillPoints(
      [
        futFill({ seq_no: "A", price: 23_000, qty: 2 }),
        futFill({ seq_no: "B", price: 23_006, qty: 1 }),
      ],
      "TXFH6",
      ANCHOR,
    );
    expect(r).toEqual([
      { minute: IDX_0930, priceMilli: 23_000_000, side: "B", qty: 2 },
      { minute: IDX_0930, priceMilli: 23_006_000, side: "B", qty: 1 },
    ]);
  });

  it("量 0 / 價 0 / 無時間 / 非 B|S 一律不畫(共用 fillPoints 的欄位守門)", () => {
    const bad = [
      futFill({ qty: 0 }),
      futFill({ price: 0 }),
      futFill({ time: null }),
      futFill({ buy_sell: "X" }),
    ];
    expect(alldayFillPoints(bad, "TXFH6", ANCHOR)).toBe(EMPTY_FILLS);
  });

  it("fills undefined → EMPTY_FILLS", () => {
    expect(alldayFillPoints(undefined, "TXFH6", ANCHOR)).toBe(EMPTY_FILLS);
  });
});
