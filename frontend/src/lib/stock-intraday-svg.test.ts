import { describe, expect, it } from "vitest";

import type { MinuteAgg } from "@/lib/stock-accum";
import {
  buildEnergyBars,
  buildIntradayGeometry,
  EDGE_LABEL_H,
  edgePriceLabels,
  minuteToX,
  overlayLines,
  PAD_Y,
  plotWidth,
  R_AXIS_W,
  sideSummary,
  SPOT_WINDOW,
  STKFUT_WINDOW,
  SUB_TOP_PAD,
  X_END_MIN,
  X_LABEL_H,
  X_START_MIN,
  Y_AXIS_W,
  type OverlayLevel,
  type OverlayLine,
} from "@/lib/stock-intraday-svg";

function minutes(entries: [number, Partial<MinuteAgg>][]): Map<number, MinuteAgg> {
  return new Map(
    entries.map(([k, m]) => [k, { c: 0, v: 0, i: 0, o: 0, u: 0, ...m }]),
  );
}

const META = {
  name: "台積電",
  ref: 2_320_000,
  upper: 2_550_000,
  lower: 2_090_000,
  y_vol: 100,
};

describe("buildIntradayGeometry", () => {
  it("x domain 固定 09:00–13:30", () => {
    expect(X_START_MIN).toBe(540);
    expect(X_END_MIN).toBe(810);
  });

  it("price line spans minutes;有漲跌停 → 域**恰為**漲跌停(SC-4,該變:原 ×1.02/×0.98 留邊)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }], [541, { c: 2_436_000, v: 2 }]]), meta: META },
      { width: Y_AXIS_W + (810 - 540) + R_AXIS_W, height: 100 },
    );
    expect(g.priceLine.length).toBe(2);
    // 🔴 SC-4:區間就是漲停/跌停,不再多留 2% 邊
    expect(g.yDomain[1]).toBe(2_550_000);
    expect(g.yDomain[0]).toBe(2_090_000);
    // 域收窄到恰為漲跌停後,「走勢線在漲跌停不被裁掉半條 stroke」改由 PAD_Y 幾何留邊承擔
    // (不是價格域放寬)。原本靠已刪的 y 邊界欄位間接守著,現在直接錨 toY 的兩個端點:
    // height=100 → 上緣 = PAD_Y(4)、下緣 = height − X_LABEL_H(14) − PAD_Y(4)。
    // 這兩個字面值即 X_LABEL_H / PAD_Y 的現值,改帶寬時本測試該一起被迫過目。
    expect(g.toY(g.yDomain[1])).toBeCloseTo(4, 6);
    expect(g.toY(g.yDomain[0])).toBeCloseTo(100 - 14 - 4, 6);
    expect(g.priceLine[1]!.y).toBeLessThan(g.priceLine[0]!.y);
    // 🔴 round4 項 3:繪圖區改從左緣價位帶右側起算,x 不再從 0 開始
    // (width = Y_AXIS_W + 分鐘數 → 繪圖區仍是每分鐘 1px)
    expect(g.priceLine[0]!.x).toBeCloseTo(Y_AXIS_W, 5);
    expect(g.priceLine[1]!.x).toBeCloseTo(Y_AXIS_W + 1, 5);
  });

  // 🟢 round4 項 1:當日高低由橫虛線改成「標在摸到的那一分鐘上」的標記。
  // 位置靠 per-minute h/l 與 top-level high 的**等值反查**取得。
  describe("當日高低標記(highMark / lowMark)", () => {
    const W = Y_AXIS_W + 270 + R_AXIS_W;
    const MS = minutes([
      [540, { c: 2_320_000, v: 1, h: 2_330_000, l: 2_310_000 }],
      [545, { c: 2_380_000, v: 1, h: 2_395_000, l: 2_360_000 }],
      [550, { c: 2_350_000, v: 1, h: 2_360_000, l: 2_300_000 }],
    ]);

    it("標記落在摸到極值的那一分鐘(不是收盤最高的分鐘、不是最後一分鐘)", () => {
      const g = buildIntradayGeometry(
        { minutes: MS, meta: META, high: 2_395_000, low: 2_300_000 },
        { width: W, height: 100 },
      );
      expect(g.highMark).not.toBeNull();
      expect(g.highMark!.priceMilli).toBe(2_395_000);
      expect(g.highMark!.x).toBeCloseTo(minuteToX(545, W), 6);
      expect(g.highMark!.y).toBeCloseTo(g.toY(2_395_000), 6);
      // 低點在 550 分,而 550 的收盤(2_350_000)不是全日最低收盤 → 只有 per-minute l 找得到
      expect(g.lowMark!.x).toBeCloseTo(minuteToX(550, W), 6);
      expect(g.lowMark!.priceMilli).toBe(2_300_000);
    });

    it("high === low(漲停鎖死)→ 只給 highMark,lowMark 為 null", () => {
      const flat = minutes([[540, { c: 2_550_000, v: 1, h: 2_550_000, l: 2_550_000 }]]);
      const g = buildIntradayGeometry(
        { minutes: flat, meta: META, high: 2_550_000, low: 2_550_000 },
        { width: W, height: 100 },
      );
      expect(g.highMark).not.toBeNull();
      expect(g.lowMark).toBeNull();
    });

    it("域外的極值不畫(沿用既有規則)", () => {
      const g = buildIntradayGeometry(
        { minutes: MS, meta: META, high: 9_999_000, low: 1_000 },
        { width: W, height: 100 },
      );
      expect(g.highMark).toBeNull();
      expect(g.lowMark).toBeNull();
    });

    it("域內但反查落空(沒有分鐘的 h 等於該值)→ 不畫,不退而求其次", () => {
      const g = buildIntradayGeometry(
        { minutes: MS, meta: META, high: 2_390_000, low: 2_305_000 },
        { width: W, height: 100 },
      );
      expect(g.highMark).toBeNull();
      expect(g.lowMark).toBeNull();
    });

    it("minutes 缺 h / l(舊後端降級)→ 不畫", () => {
      const noHL = minutes([
        [540, { c: 2_320_000, v: 1 }],
        [545, { c: 2_395_000, v: 1 }],
      ]);
      const g = buildIntradayGeometry(
        { minutes: noHL, meta: META, high: 2_395_000, low: 2_320_000 },
        { width: W, height: 100 },
      );
      expect(g.highMark).toBeNull();
      expect(g.lowMark).toBeNull();
    });

    it("high / low 未傳(呼叫端沒給)→ 兩者皆 null", () => {
      const g = buildIntradayGeometry({ minutes: MS, meta: META }, { width: W, height: 100 });
      expect(g.highMark).toBeNull();
      expect(g.lowMark).toBeNull();
    });
  });

  // 🔴 round4 項 3:價位文字原本畫在 x=2 而繪圖區從 x=0 起,文字直接壓在走勢線上。
  // 左緣讓出 Y_AXIS_W 寬的價位帶後,`minuteToX` / `minuteOf` 必須**共用**同一組常數,
  // 否則反演只在兩端偏移(同 toY / priceAtY 共用 PAD_Y 的理由)。
  describe("左緣價位帶(gutter)", () => {
    const W = Y_AXIS_W + 270 + R_AXIS_W;

    // 🔴 round4 項 6:原本硬編 `expect(Y_AXIS_W).toBe(46)`,測的其實是「hover 價位標整格
    // 塞得進價位帶」這個語意 —— 那條不變式屬於元件(PRICE_TAG.w === Y_AXIS_W),
    // 在純函數測試裡只能退化成一個會隨帶寬改動而失效的字面值。改成守語意:
    // 繪圖區左界必須恰是價位帶右緣(帶寬多少由元件與 UI 決定)。
    it("繪圖區左界恰是價位帶右緣(帶寬本身不寫死)", () => {
      expect(minuteToX(X_START_MIN, W)).toBeCloseTo(Y_AXIS_W, 6);
    });

    it("繪圖區起於價位帶右緣、迄於圖右緣", () => {
      expect(minuteToX(X_START_MIN, W)).toBeCloseTo(Y_AXIS_W, 6);
      expect(minuteToX(X_END_MIN, W)).toBeCloseTo(W - R_AXIS_W, 6);
      expect(plotWidth(W)).toBeCloseTo(270, 6);
    });

    it("minuteOf ↔ minuteToX 互逆(每個有成交分鐘往返守恆)", () => {
      const ms = [540, 600, 661, 720, 809];
      const g = buildIntradayGeometry(
        { minutes: minutes(ms.map((m) => [m, { c: 2_320_000, v: 1 }])), meta: META },
        { width: W, height: 100 },
      );
      for (const m of ms) {
        expect(g.minuteOf(minuteToX(m, W))).toBe(m);
      }
    });

    // 🔴 self-review R4-4:width <= Y_AXIS_W 時 plotWidth 被 clamp 成 1,minuteToX 最大回
    // Y_AXIS_W + 1 = 47 > width,而 minuteOf 的上界用 size.width 擋 → 兩者不再互逆。
    // 現行唯一呼叫端寫死 800 不會踩到,但這兩支是 export 的公開純函數,不變量要自洽。
    it("退化寬度(width <= Y_AXIS_W)下仍互逆", () => {
      const g = buildIntradayGeometry(
        { minutes: minutes([[X_END_MIN, { c: 2_320_000, v: 1 }]]), meta: META },
        { width: Y_AXIS_W + R_AXIS_W, height: 100 },
      );
      const x = minuteToX(X_END_MIN, Y_AXIS_W + R_AXIS_W);
      expect(g.minuteOf(x)).toBe(X_END_MIN);
    });

    it("價位帶內的 x 不對應任何分鐘(不會被誤讀成 09:00)", () => {
      const g = buildIntradayGeometry(
        { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
        { width: W, height: 100 },
      );
      expect(g.minuteOf(Y_AXIS_W)).toBe(540);
      expect(g.minuteOf(Y_AXIS_W - 1)).toBeNull();
      expect(g.minuteOf(0)).toBeNull();
    });

    it("副圖 bar 與主圖價點同 x(同 width 下對位守恆;hover 直線貫穿兩圖要對準)", () => {
      const input = {
        minutes: minutes([[540, { c: 2_320_000, v: 1, o: 1, i: 1 }], [600, { c: 2_330_000, v: 1, o: 2, i: 1 }]]),
        meta: META,
      };
      const main = buildIntradayGeometry(input, { width: W, height: 260 });
      // 副圖走**出貨路徑** `buildEnergyBars`(元件實際呼叫的那支);沿用
      // `buildIntradayGeometry` 只驗得到已經沒人走的舊路,對位漂了也不會紅。
      const sub = buildEnergyBars(input.minutes, { width: W, height: 70 });
      expect(sub.bars[0]!.x).toBeCloseTo(Y_AXIS_W, 6);
      expect(sub.bars.map((b) => b.x)).toEqual(main.priceLine.map((p) => p.x));
    });

    // L-1:副圖抽出 `buildEnergyBars` 後,主圖的 `energyBars` 仍存在(hover/量刻度共用)。
    // 兩份 bar 必須是同一份 `energyFrom` 的產物 —— 逐值相等是「沒有各漂各的」的守門,
    // 只比 x 會漏掉高度與歸一分母(那才是副圖真正畫出來的東西)。
    it("buildEnergyBars 與 buildIntradayGeometry.energyBars 輸出逐值相同", () => {
      const input = {
        minutes: minutes([
          [540, { c: 2_320_000, v: 269, o: 127, i: 20, u: 122 }],
          [600, { c: 2_330_000, v: 100, o: 60, i: 40, u: 0 }],
        ]),
        meta: META,
      };
      const size = { width: W, height: 70 };
      const viaGeometry = buildIntradayGeometry(input, size);
      const viaEnergy = buildEnergyBars(input.minutes, size);
      expect(viaEnergy.bars).toEqual(viaGeometry.energyBars);
      expect(viaEnergy.maxTotal).toBe(viaGeometry.maxTotal);
    });
  });

  // 🔴 SC-4 / R1:priceAtY 必須是改動後 toY 的逆函數。中間點在任何公式下都剛好正確,
  // 只有兩端會偏 —— round-trip 是唯一抓得到「公式沒跟著 toY 改」的測試。
  it("priceAtY 是 toY 的逆函數(域內 round-trip ±1 毫元),超界夾制", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );
    for (const p of [2_090_000, 2_205_000, 2_320_000, 2_435_000, 2_550_000]) {
      expect(Math.abs(g.priceAtY(g.toY(p)) - p)).toBeLessThanOrEqual(1);
    }
    expect(g.priceAtY(-99)).toBe(2_550_000);
    expect(g.priceAtY(9999)).toBe(2_090_000);
  });

  // 🔴 SC-2:走勢線與平盤之間的封閉多邊形(起點x,refY → 各點 → 終點x,refY)
  it("areaPolygon 以 refY 封閉且首尾點貼齊平盤", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }], [541, { c: 2_436_000, v: 2 }]]), meta: META },
      { width: Y_AXIS_W + 270 + R_AXIS_W, height: 100 },
    );
    const pts = g.areaPolygon.split(" ");
    expect(pts.length).toBe(4); // 起點 + 2 個資料點 + 終點
    // 🔴 round4 項 3:填色多邊形一併右移到繪圖區內(否則會延伸進左緣價位帶)
    expect(pts[0]).toBe(`${Y_AXIS_W.toFixed(1)},${g.refY.toFixed(1)}`);
    expect(pts[3]).toBe(`${(Y_AXIS_W + 1).toFixed(1)},${g.refY.toFixed(1)}`);
  });

  it("無 ref 時 areaPolygon 為空字串(fallback 走單色線、不填色)", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([[540, { c: 2_320_000, v: 1 }]]),
        meta: { ...META, ref: null, upper: null, lower: null },
      },
      { width: 270, height: 100 },
    );
    expect(g.areaPolygon).toBe("");
  });

  it("upper/lower 缺 → 沿用對稱 autofit 域(edge 1)", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([[540, { c: 2_320_000, v: 1 }], [541, { c: 2_436_000, v: 2 }]]),
        meta: { ...META, upper: null, lower: null },
      },
      { width: 270, height: 100 },
    );
    // 對稱域:以 ref 為中心
    const [lo, hi] = g.yDomain;
    expect((lo + hi) / 2).toBeCloseTo(2_320_000, -2);
  });

  // 🔴 M5:後端 `to_milli_units("0")` 對 ref/upper/lower 回 0 不回 None,而 TC4 真的會送 "0"
  // (三欄多半同時 0)。0 不是價格是「不可得」,幾何入口統一歸一,此後既有分支自然走 autofit。
  it("ref/upper/lower 皆為 0 → 視為不可得,y 域走 autofit 且不含 0", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([[540, { c: 2_320_000, v: 1 }], [541, { c: 2_436_000, v: 2 }]]),
        meta: { ...META, ref: 0, upper: 0, lower: 0 },
      },
      { width: 270, height: 100 },
    );
    const [lo, hi] = g.yDomain;
    // 走 autofit(以首筆成交價為中心)而不是退化的 [0, 0] 常數域
    expect(hi).toBeGreaterThan(lo);
    expect(lo).toBeGreaterThan(0);
    // 域涵蓋實際成交價
    expect(lo).toBeLessThanOrEqual(2_320_000);
    expect(hi).toBeGreaterThanOrEqual(2_436_000);
    // ref=0 不得留在刻度上變成假價位
    expect(g.yTicks.every((t) => t.priceMilli > 0)).toBe(true);
    expect(g.hasRef).toBe(false);
  });

  /** 🔴 autofit 域原本只吃**每分鐘收盤**,裝不下逐筆極值 → 當日高低標記被 markFor 的
   *  域外 guard 靜默攔掉(2330 2026-07-30 盤後:域 [2160.5, 2259.5] 差 0.5 元裝不下
   *  當日最高 2260.0)。域改為併入 `input.high` / `input.low`,0 值仍依歸一慣例視為不可得。 */
  describe("autofit 域含當日高低(無漲跌停)", () => {
    const W = Y_AXIS_W + 270 + R_AXIS_W;
    const H = 100;
    /** 長上影:540 的逐筆高遠離兩分鐘的收盤(2_200_000 / 2_210_000);ref = 首筆收盤 */
    const SPIKE = minutes([
      [540, { c: 2_200_000, v: 1, h: 2_600_000 }],
      [541, { c: 2_210_000, v: 1 }],
    ]);
    const REF = 2_200_000;

    it("長上影極端分鐘 → 域含 high,highMark 可畫(SC-1/SC-3)", () => {
      const g = buildIntradayGeometry(
        { minutes: SPIKE, meta: null, high: 2_600_000 },
        { width: W, height: H },
      );
      expect(g.yDomain[1]).toBeGreaterThanOrEqual(2_600_000);
      expect(g.highMark).not.toBeNull();
      expect(g.highMark!.priceMilli).toBe(2_600_000);
      expect(g.highMark!.x).toBeCloseTo(minuteToX(540, W), 6);
      // sanity(與 markFor 域外 guard 雙保險):guard 在時,「非 null 的標記」必然已在域內,
      // 這兩行恆真 —— 它守的不是「標記壓到時間帶」那種不可達樣態,而是「域 / toY / PAD_Y
      // 三者其中一個被改到不自洽」時能一起紅(例:toY 改了留邊而域沒跟著)。
      expect(g.highMark!.y).toBeGreaterThanOrEqual(PAD_Y);
      expect(g.highMark!.y).toBeLessThanOrEqual(H - X_LABEL_H - PAD_Y);
    });

    it("low 低於收盤群 → 域含 low,lowMark 可畫(SC-2)", () => {
      const dip = minutes([
        [540, { c: 2_200_000, v: 1, l: 1_900_000 }],
        [541, { c: 2_190_000, v: 1 }],
      ]);
      const g = buildIntradayGeometry(
        { minutes: dip, meta: null, low: 1_900_000 },
        { width: W, height: H },
      );
      expect(g.yDomain[0]).toBeLessThanOrEqual(1_900_000);
      expect(g.lowMark).not.toBeNull();
      expect(g.lowMark!.priceMilli).toBe(1_900_000);
      expect(g.lowMark!.x).toBeCloseTo(minuteToX(540, W), 6);
    });

    /** 白名單 7:TC4 送 "0" → 後端 `to_milli_units` 原樣轉 0。危險方向是 **low = 0**
     *  (`Math.min` 會把它吃進域讓下緣變負;high = 0 被 `Math.max` 自然忽略,測不出漏做 norm)。 */
    it("low = 0 → 視為不可得,域同未傳且下緣仍 > 0", () => {
      const base = buildIntradayGeometry({ minutes: SPIKE, meta: null }, { width: W, height: H });
      const g = buildIntradayGeometry(
        { minutes: SPIKE, meta: null, low: 0 },
        { width: W, height: H },
      );
      expect(g.yDomain).toEqual(base.yDomain);
      expect(g.yDomain[0]).toBeGreaterThan(0);
    });

    it("含極值後域仍以 ref 為中心(SC-4:對稱語意不變,只是半幅池擴大)", () => {
      const g = buildIntradayGeometry(
        { minutes: SPIKE, meta: null, high: 2_600_000 },
        { width: W, height: H },
      );
      expect((g.yDomain[0] + g.yDomain[1]) / 2).toBeCloseTo(REF, 6);
    });

    /** SC-5:單點 fixture 撐不住「域必含當日極值」這條不變式 —— 只要 high/low 相對
     *  收盤群的位置換一組就可能落回舊行為而沒有測試會紅。改成 table-driven 掃五種位置。 */
    const INV = minutes([
      [540, { c: 2_200_000, v: 1, h: 2_600_000, l: 1_900_000 }],
      [541, { c: 2_210_000, v: 1, h: 2_215_000, l: 2_205_000 }],
    ]);
    it.each([
      ["(a) high 在收盤群之上且舊域外", 2_600_000, 2_205_000, false],
      ["(b) low 在收盤群之下且舊域外", 2_215_000, 1_900_000, false],
      ["(c) high/low 皆在收盤群內", 2_210_000, 2_200_000, true],
      ["(d) high === ref", REF, REF, true],
      ["(e) low = 0(不可得)", null, 0, true],
    ] as [string, number | null, number | null, boolean][])(
      "不變式:域必含當日極值 — %s",
      (_name, high, low, sameAsBaseline) => {
        const base = buildIntradayGeometry({ minutes: INV, meta: null }, { width: W, height: H });
        const g = buildIntradayGeometry(
          { minutes: INV, meta: null, high, low },
          { width: W, height: H },
        );
        if ((high ?? 0) > 0) expect(high!).toBeLessThanOrEqual(g.yDomain[1]);
        if ((low ?? 0) > 0) expect(g.yDomain[0]).toBeLessThanOrEqual(low!);
        expect(g.yDomain[0]).toBeGreaterThan(0);
        if (sameAsBaseline) expect(g.yDomain).toEqual(base.yDomain);
      },
    );

    /** 刻意接受的連帶變化:域是疊線的裁切門檻,域一寬原本被裁掉的 CDP/MA 就會出現。
     *  與 round4 R6「域收窄時疊線變少」是同一條語意的反向。 */
    it("疊線裁切門檻隨域放寬(舊域外、新域內的 ma5 由不給變成給)", () => {
      const g = buildIntradayGeometry(
        { minutes: SPIKE, meta: null, high: 2_600_000 },
        { width: W, height: H },
      );
      // 2_500_000 > 舊上緣 2_224_200(半幅由 ref×1% 決定),< 新上緣 2_640_000
      const overlay = { cdp: null, ma5: 2_500_000, ma20: null, date: "2026-07-30" };
      expect(overlayLines(overlay, g, { cdp: false, ma: true }).map((l) => l.level)).toEqual([
        "ma5",
      ]);
    });

    /** SC-3 的實例回歸(2330 2026-07-30 盤後)。臨界形狀刻意留在測試裡:域上緣
     *  2_259_500 由**低側**(ref − lo = 45_000)決定,當日高 2_260_000 只差 0.5 元被裁掉 ——
     *  差這麼小的失效沒有任何畫面訊號,只是標記不見。 */
    it("實例回歸:域上緣差 0.5 元裝不下當日高(2330 2026-07-30)", () => {
      const ms = minutes([
        [540, { c: 2_210_000, v: 1 }],
        [541, { c: 2_165_000, v: 1 }],
        [542, { c: 2_255_000, v: 1, h: 2_260_000 }],
      ]);
      const g = buildIntradayGeometry(
        { minutes: ms, meta: null, high: 2_260_000 },
        { width: W, height: H },
      );
      expect(g.yDomain[1]).toBeGreaterThanOrEqual(2_260_000);
      expect(g.highMark).not.toBeNull();
      expect(g.highMark!.priceMilli).toBe(2_260_000);
    });

    /** 🔴 F5:`ref = 0`(meta 無 ref **且**收盤全濾光)時沒有中心錨點可言 —— 對稱域退化成
     *  [−1, 1]。此時把 high/low 併進半幅池只是放大垃圾:域變成 [−1.1×high, 1.1×high],
     *  3 點 fallback 會印出負價位刻度,標記還會畫在錯位的 y 上。ref = 0 一律維持退化域。 */
    const DEGENERATE = minutes([
      [540, { c: 0, v: 0, h: 2_600_000, l: 2_370_000 }],
      [541, { c: 0, v: 0 }],
    ]);

    it("ref = 0(無 meta ref 且收盤全 0)→ 域不受 high/low 影響,標記皆不畫", () => {
      const base = buildIntradayGeometry(
        { minutes: DEGENERATE, meta: null },
        { width: W, height: H },
      );
      const g = buildIntradayGeometry(
        { minutes: DEGENERATE, meta: null, high: 2_600_000, low: 2_370_000 },
        { width: W, height: H },
      );
      expect(g.yDomain).toEqual(base.yDomain);
      expect(g.highMark).toBeNull();
      expect(g.lowMark).toBeNull();
    });

    /** markFor 吃 norm 後的值(不是原始 `input.low`)這件事,只有在**退化域**下才測得出來:
     *  域 [−1, 1] 含 0,raw 版會通過域外 guard、反查命中 `l: 0` 的那一分鐘,畫出一個
     *  價位 0 的假標記。正常域(下緣 > 0)時 0 會被 guard 自然擋掉,兩版無差別。 */
    it("low = 0 且有分鐘的 l 為 0(退化域)→ 仍不畫假標記", () => {
      const zeros = minutes([
        [540, { c: 0, v: 0, l: 0 }],
        [541, { c: 0, v: 0 }],
      ]);
      const g = buildIntradayGeometry(
        { minutes: zeros, meta: null, low: 0 },
        { width: W, height: H },
      );
      expect(g.lowMark).toBeNull();
    });

    /** 白名單 1 的反向釘子:有漲跌停時域**恰為** [lower, upper],high/low 一絲都不得洩入
     *  (本輪只動 autofit 分支)。用遠在域外的極值當探針,洩入的話域會立刻被撐爆。 */
    it("有漲跌停 → 域恰為 [lower, upper],完全不受 high/low 影響", () => {
      const g = buildIntradayGeometry(
        {
          minutes: minutes([[540, { c: 2_320_000, v: 1 }]]),
          meta: META,
          high: 9_999_000,
          low: 1_000,
        },
        { width: W, height: H },
      );
      expect(g.yDomain).toEqual([2_090_000, 2_550_000]);
    });
  });

  // 🔴 SC-4:刻度由「以 5% 為分隔的 5 點」改為 ±2/4/6/8/10% 的 11 點(2330 tick 5 元,不去重)
  it("yTicks:有漲跌停 → 11 點(0/±2/±4/±6/±8/±10%),全為合法 tick 且由上而下遞減", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );
    expect(g.yTicks).toHaveLength(11);
    // 端點用 upper/lower 原值、中央用 ref 原值(不經 snap,避免與域端點差一個 tick)
    expect(g.yTicks[0]!.priceMilli).toBe(2_550_000);
    expect(g.yTicks[5]!.priceMilli).toBe(2_320_000);
    expect(g.yTicks[10]!.priceMilli).toBe(2_090_000);
    // ±2% 的價位 = snapDown(ref×1.02) = snapDown(2366400) = 2365000(5 元 tick)
    expect(g.yTicks[4]!.priceMilli).toBe(2_365_000);
    for (const t of g.yTicks) expect(t.priceMilli % 5_000).toBe(0);
    // 由上而下:價位遞減、y 遞增
    for (let i = 1; i < g.yTicks.length; i += 1) {
      expect(g.yTicks[i]!.priceMilli).toBeLessThan(g.yTicks[i - 1]!.priceMilli);
      expect(g.yTicks[i]!.y).toBeGreaterThan(g.yTicks[i - 1]!.y);
    }
  });

  // 🟢 round6 項 2:說明列要能誠實交代「灰色是多少、外盤比可不可信」
  describe("sideSummary(內外盤口徑)", () => {
    it("四個數字同源,外盤比分母**排除**未分類(既有語意不變)", () => {
      // 2026-07-31 實測 09:00 那一分鐘:量 269 = 外 127 + 內 20 + 未分類 122
      const s = sideSummary(minutes([[540, { c: 100_000, v: 269, o: 127, i: 20, u: 122 }]]));
      expect(s).toMatchObject({ outer: 127, inner: 20, unch: 122 });
      expect(s.outerPct).toBeCloseTo((127 / 147) * 100, 5);
      // 判定率的分母才是總量
      expect(s.decidedPct).toBeCloseTo((147 / 269) * 100, 5);
    });

    it("鎖漲停整天判不出來 → 外盤比 null(不是 0)、判定率 0", () => {
      const s = sideSummary(minutes([[540, { c: 502_000, v: 2131, o: 0, i: 0, u: 2131 }]]));
      expect(s.outerPct).toBeNull();
      expect(s.decidedPct).toBe(0);
    });

    it("無資料 → 兩個比率都是 null(不是 0 —— 0% 會被讀成「全內盤」)", () => {
      const s = sideSummary(new Map());
      expect(s.outerPct).toBeNull();
      expect(s.decidedPct).toBeNull();
    });

    /** 與副圖的灰段總和對得上是這個數字的全部意義,所以窗要一致 ——
     *  `buildIntradayGeometry` 會把分鐘過濾成 [09:00, 13:30],這裡也必須。 */
    it("窗外的分鐘不計入(與副圖畫出來的灰段同窗)", () => {
      const s = sideSummary(
        minutes([
          [539, { c: 100_000, v: 999, o: 999, i: 0, u: 0 }], // 08:59,窗外
          [540, { c: 100_000, v: 10, o: 6, i: 4, u: 0 }],
        ]),
      );
      expect(s.outer).toBe(6);
    });
  });

  // 🔴 round6 項 5:左緣價位軸的漲停 / 跌停兩格要亮燈 → 幾何層標出哪一格是哪個
  describe("yTicks.kind(漲跌停亮燈的判定來源)", () => {
    it("端點兩格標 upper / lower,中間各格不標", () => {
      const g = buildIntradayGeometry(
        { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
        { width: 270, height: 100 },
      );
      expect(g.yTicks[0]!.kind).toBe("upper");
      expect(g.yTicks[10]!.kind).toBe("lower");
      for (const t of g.yTicks.slice(1, 10)) expect(t.kind).toBeUndefined();
    });

    it("缺漲跌停(對稱 autofit)→ 兩格都不標(SC-5.5:沒有漲跌停可言就不亮)", () => {
      const g = buildIntradayGeometry(
        {
          minutes: minutes([[540, { c: 2_320_000, v: 1 }]]),
          meta: { ...META, upper: null, lower: null },
        },
        { width: 270, height: 100 },
      );
      for (const t of g.yTicks) expect(t.kind).toBeUndefined();
    });

    /** review R9:kind 的標記條件不可綁在「11 點分支」上。決定 y 域的條件是
     *  `upper !== null && lower !== null`(**不含** `ref > 0`),而 tick 分支多了 `ref > 0`
     *  —— 有漲跌停但 ref 不可得時會走 3 點 fallback,那條分支的 yTop / yBottom
     *  **仍然就是** upper / lower,兩格畫的確實是漲跌停價卻不會亮,違反 SC-5.4「恆亮」。 */
    it("有漲跌停但 ref 不可得(走 3 點 fallback)→ 端點仍標 kind", () => {
      const g = buildIntradayGeometry(
        {
          minutes: minutes([[540, { c: 2_320_000, v: 1 }]]),
          meta: { ...META, ref: null },
        },
        { width: 270, height: 100 },
      );
      expect(g.yTicks[0]!.priceMilli).toBe(2_550_000);
      expect(g.yTicks[0]!.kind).toBe("upper");
      expect(g.yTicks[g.yTicks.length - 1]!.kind).toBe("lower");
    });
  });

  // 低價股 tick 粗 → 相鄰 pct snap 到同價;去重後少於 11 點屬正常(SC-4.2)
  // 🔴 M2:±10% 用 upper/lower 原值,±2/4/6/8% 卻是拿 ref 獨立算的 —— 兩者沒互相校驗。
  // 漲跌幅不是 ±10% 的商品(槓桿 ETF ±20%、或任何比 ±10% 窄的),公式算出的中間刻度會
  // 落到 [lower, upper] 之外 → toY 變負、刻度視覺次序反轉。
  it("yTicks:漲跌幅非 ±10% 的商品,所有刻度仍落在 [lower, upper] 內且嚴格遞減", () => {
    for (const [lower, upper] of [
      [4_850, 5_150], // ±3%(比 ±10% 窄)
      [4_000, 6_000], // ±20%(槓桿型 ETF)
    ] as [number, number][]) {
      const g = buildIntradayGeometry(
        { minutes: minutes([[540, { c: 5_000, v: 1 }]]), meta: { ...META, ref: 5_000, upper, lower } },
        { width: 270, height: 100 },
      );
      for (const t of g.yTicks) {
        expect(t.priceMilli).toBeGreaterThanOrEqual(lower);
        expect(t.priceMilli).toBeLessThanOrEqual(upper);
      }
      for (let i = 1; i < g.yTicks.length; i += 1) {
        expect(g.yTicks[i]!.priceMilli).toBeLessThan(g.yTicks[i - 1]!.priceMilli);
        expect(g.yTicks[i]!.y).toBeGreaterThan(g.yTicks[i - 1]!.y);
      }
      // 端點恆為漲跌停原值
      expect(g.yTicks[0]!.priceMilli).toBe(upper);
      expect(g.yTicks[g.yTicks.length - 1]!.priceMilli).toBe(lower);
    }
  });

  // 🔴 M1:yTop === yBottom 時 `ySpan || 1` 只擋除以零,toY 仍是無界線性函數 ——
  // 只差 10 毫元就會算出跑出畫布數百 px 的座標,而 priceAtY 靠 clamp 收斂成常數,兩者不再互逆。
  it("退化域(upper === lower)時 toY 為常數且與 priceAtY 互逆,座標不飛出畫布", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 5_000, v: 1 }]]), meta: { ...META, ref: 5_000, upper: 5_000, lower: 5_000 } },
      { width: 270, height: 70 },
    );
    for (const p of [4_990, 5_000, 5_010]) {
      const y = g.toY(p);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(70);
    }
    expect(g.toY(4_990)).toBe(g.toY(5_010)); // 常數函數
    expect(g.priceAtY(g.toY(5_000))).toBe(5_000);
  });

  it("yTicks:低價股相鄰檔位 snap 到同價時去重,不產生重複 priceMilli", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 10_000, v: 1 }]]), meta: { ...META, ref: 10_000, upper: 11_000, lower: 9_000 } },
      { width: 270, height: 100 },
    );
    const prices = g.yTicks.map((t) => t.priceMilli);
    expect(new Set(prices).size).toBe(prices.length);
    expect(prices.length).toBeLessThanOrEqual(11);
  });

  it("yTicks:缺漲跌停 → 沿用 3 點的 fallback(白名單 11,不套 11 點)", () => {
    const g2 = buildIntradayGeometry(
      {
        minutes: minutes([[540, { c: 2_320_000, v: 1 }]]),
        meta: { ...META, upper: null, lower: null },
      },
      { width: 270, height: 100 },
    );
    expect(g2.yTicks).toHaveLength(3);
  });

  it("minuteOf:bucket 有資料回分鐘、無資料回 null(SC-1/R6)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }], [600, { c: 2_330_000, v: 1 }]]), meta: META },
      { width: Y_AXIS_W + 270 + R_AXIS_W, height: 100 },
    );
    expect(g.minuteOf(Y_AXIS_W)).toBe(540); // 繪圖區起點 → 09:00
    expect(g.minuteOf(Y_AXIS_W + 60)).toBe(600); // +60px → 10:00(繪圖區 270 → 1px/分)
    expect(g.minuteOf(Y_AXIS_W + 30)).toBeNull(); // 09:30 無資料
    expect(g.minuteOf(-5)).toBeNull();
    expect(g.minuteOf(999)).toBeNull();
  });

  // 🔴 SC-5:主圖底部量 bar 已移除(user 拍板留內外盤能量副圖),volumeBars 不再存在

  it("overlayLines:域內才給、含 level(SC-2)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );
    const overlay = {
      cdp: { cdp: 2_320_000, ah: 2_400_000, nh: 2_360_000, nl: 2_280_000, al: 2_240_000 },
      ma5: 2_330_000,
      ma20: 9_999_000, // 域外 → 不給
      date: "2026-07-25",
    };
    const lines = overlayLines(overlay, g, { cdp: true, ma: true });
    const levels = lines.map((l) => l.level);
    expect(levels).toContain("cdp");
    expect(levels).toContain("ah");
    expect(levels).toContain("ma5");
    expect(levels).not.toContain("ma20");
    // label 欄位已移除:右緣文字改由元件用 priceMilli 現算(SC-2)
    expect("label" in lines[0]!).toBe(false);
    expect(lines.every((l) => l.y >= 0 && l.y <= 100)).toBe(true);
    // toggle 關 → 不給該類
    expect(overlayLines(overlay, g, { cdp: false, ma: true }).map((l) => l.level)).not.toContain(
      "cdp",
    );
  });

  // 🔴 SC-4 收窄 yDomain 的連帶語意(review R6):落在 upper..upper×1.02 那 2% 夾層的疊線
  // 由「有畫」變成「不畫」。刻意接受 —— 超出漲停的價位當日不可能成交,畫出來是雜訊。
  it("overlayLines:介於 upper 與舊域上緣(upper×1.02)之間的線不再給(域收窄後的新語意)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );
    // 2_570_000 > upper(2_550_000) 但 < 舊上緣 2_601_000
    const overlay = {
      cdp: null,
      ma5: 2_570_000,
      ma20: 2_060_000, // < lower(2_090_000) 但 > 舊下緣 2_048_200
      date: "2026-07-25",
    };
    expect(overlayLines(overlay, g, { cdp: false, ma: true })).toEqual([]);
    // 域內的照給
    expect(
      overlayLines({ ...overlay, ma5: 2_540_000 }, g, { cdp: false, ma: true }).map((l) => l.level),
    ).toEqual(["ma5"]);
  });

  it("energy bars per minute(SC-5:主圖量 bar 已移除,副圖每分鐘一根)", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          [540, { c: 2_320_000, v: 10, o: 7, i: 3 }],
          [545, { c: 2_330_000, v: 5, o: 1, i: 4 }],
        ]),
        meta: META,
      },
      { width: 270, height: 100 },
    );
    expect(g.energyBars.length).toBe(2);
    // 🔴 round6c:三段(outer/inner/unch)合併成單一總量 —— user 拍板「不要分顏色,
    // 單純顯示量」。內外盤統計沒有消失,移到說明列(`sideSummary`)。
    expect(g.energyBars[0]!.h).toBeGreaterThan(g.energyBars[1]!.h);
    expect("volumeBars" in g).toBe(false);
  });

  it("vwap line approximates running average from minutes", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          [540, { c: 2_300_000, v: 10 }],
          [541, { c: 2_400_000, v: 10 }],
        ]),
        meta: META,
      },
      { width: 270, height: 100 },
    );
    expect(g.vwapLine.length).toBe(2);
    // 第二點 running vwap = (2300*10 + 2400*10)/20 = 2350 → 介於兩價之間
    expect(g.vwapLine[1]!.vwap).toBe(2_350_000);
  });

  it("empty minutes yields empty paths without NaN", () => {
    const g = buildIntradayGeometry({ minutes: new Map(), meta: META }, { width: 270, height: 100 });
    expect(g.priceLine).toEqual([]);
    expect(g.vwapLine).toEqual([]);
    expect(Number.isFinite(g.refY)).toBe(true);
  });

  it("meta 缺參考價(null)不產生 NaN", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: { ...META, ref: null, upper: null, lower: null } },
      { width: 270, height: 100 },
    );
    expect(Number.isFinite(g.priceLine[0]!.y)).toBe(true);
  });
});

// ---- round3 新增(T-2)----

describe("round3:overlayLines level 與副圖量刻度出口", () => {
  const G = () =>
    buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: 270, height: 100 },
    );

  it("CDP 五個 level 齊全且由上而下 = ah / nh / cdp / nl / al(SC-2 靠顏色區分,順序即語意)", () => {
    const lines = overlayLines(
      {
        cdp: { cdp: 2_320_000, ah: 2_400_000, nh: 2_360_000, nl: 2_280_000, al: 2_240_000 },
        ma5: null,
        ma20: null,
        date: "2026-07-25",
      },
      G(),
      { cdp: true, ma: false },
    );
    expect(lines.map((l) => l.level)).toEqual(["ah", "nh", "cdp", "nl", "al"]);
    // 由上而下:priceMilli 遞減、y 遞增
    for (let i = 1; i < lines.length; i += 1) {
      expect(lines[i]!.priceMilli).toBeLessThan(lines[i - 1]!.priceMilli);
      expect(lines[i]!.y).toBeGreaterThan(lines[i - 1]!.y);
    }
  });

  // 🔴 round5 E:出口由 maxSide(單邊最大)改為 maxTotal(總量最大)。事前標為該變 ——
  // 單邊分母讓資訊列的「量」在副圖上找不到對應高度(未分類整批不畫)。
  it("maxTotal 出口 = 該日最大總量(量刻度的分母)", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          [540, { c: 2_320_000, v: 10, o: 7, i: 3 }],
          [545, { c: 2_330_000, v: 5, o: 1, i: 4 }],
        ]),
        meta: META,
      },
      { width: 270, height: 100 },
    );
    expect(g.maxTotal).toBe(10);
  });

  it("energyBars 高度分母已扣掉頂端留白,最高的 bar 不會頂滿全高(SC-8 刻度才不被蓋住)", () => {
    const H = 100;
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 10, o: 7, i: 3 }]]), meta: META },
      { width: 270, height: H },
    );
    // 分母扣掉頂端留白後,滿格的那根恰為 `H − SUB_TOP_PAD`(round5 E 的總量語意保留)
    const b = g.energyBars[0]!;
    expect(b.h).toBeLessThan(H);
    expect(b.h).toBeCloseTo(H - SUB_TOP_PAD, 6);
  });
});

// round5 第二輪(user 看畫面後提出;截圖 docs/specs/stock-ui-round5/screenshots/)
describe("round5:右緣帶 + 總量堆疊", () => {
  const META = {
    name: "台積電",
    ref: 2_320_000,
    upper: 2_550_000,
    lower: 2_090_000,
    y_vol: 1,
  };
  const W = Y_AXIS_W + 270 + R_AXIS_W;

  it("R_AXIS_W:繪圖區右界退到右緣帶左緣(疊線標籤才不壓走勢圖)", () => {
    expect(R_AXIS_W).toBeGreaterThan(0);
    expect(plotWidth(W)).toBeCloseTo(270, 6);
    expect(minuteToX(X_START_MIN, W)).toBeCloseTo(Y_AXIS_W, 6);
    expect(minuteToX(X_END_MIN, W)).toBeCloseTo(W - R_AXIS_W, 6);
  });

  it("右緣帶內不對應任何分鐘(與左緣價位帶同款)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 1 }]]), meta: META },
      { width: W, height: 100 },
    );
    expect(g.minuteOf(W - R_AXIS_W + 1)).toBeNull();
    expect(g.minuteOf(W)).toBeNull();
  });

  it("minuteOf ↔ minuteToX 在雙側帶下仍互逆(共用 plotWidth 的建構保證)", () => {
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 1 }], [600, { c: 1 }], [810, { c: 1 }]]), meta: META },
      { width: W, height: 100 },
    );
    for (const m of [540, 600, 810]) {
      expect(g.minuteOf(minuteToX(m, W))).toBe(m);
    }
  });

  it("energyBars 高度依「全日最大總量」正規化(W-1:分母不是單邊最大)", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          // 總量 269 = 外 127 + 內 20 + 未分類 122(截圖 09:00 的真實組成)
          [540, { c: 2_320_000, v: 269, o: 127, i: 20, u: 122 }],
          [541, { c: 2_330_000, v: 100, o: 60, i: 40, u: 0 }],
        ]),
        meta: META,
      },
      { width: W, height: 100 },
    );
    const b0 = g.energyBars[0]!;
    expect(g.maxTotal).toBe(269);
    const energyH = 100 - SUB_TOP_PAD;
    // 全日最大那根恰好滿格;分子含未分類(舊分母用單邊最大時,資訊列的「量」在副圖上
    // 找不到對應高度 —— 122 張 neutral 根本沒畫而刻度是單邊最大 164)
    expect(b0.h).toBeCloseTo(energyH, 5);
    // 第二根總量 100 → 高度為第一根的 100/269
    const b1 = g.energyBars[1]!;
    expect(b1.h).toBeCloseTo((100 / 269) * energyH, 5);
  });

  it("maxTotal 取全日最大總量,不是單邊最大", () => {
    const g = buildIntradayGeometry(
      {
        minutes: minutes([
          [540, { c: 1, v: 269, o: 127, i: 20, u: 122 }],
          [541, { c: 1, v: 200, o: 164, i: 36, u: 0 }], // 單邊最大在這裡(164)
        ]),
        meta: META,
      },
      { width: W, height: 100 },
    );
    expect(g.maxTotal).toBe(269); // 不是 164
  });
});

// 🟢 SC-5 / D9:x 窗參數化。個股期日盤是 08:45–13:45(300 分鐘),比現貨的
// 09:00–13:30(270 分鐘)兩端各長一截 —— 窗一旦有第二種值,「幾何各處共用同一把尺」
// 就從註解升級成必須被鎖住的契約:漏傳窗的失效樣態全是「圖照畫、只是對不齊」。
describe("x 窗參數化(D9)", () => {
  /** 繪圖區恰 300px → 期貨窗下每分鐘 1px,座標可直接對讀 */
  const W = Y_AXIS_W + 300 + R_AXIS_W;
  const META2 = { name: "台積電期", ref: 2_320_000, upper: 2_550_000, lower: 2_090_000, y_vol: 1 };

  it("SPOT_WINDOW = 09:00–13:30、STKFUT_WINDOW = 08:45–13:45", () => {
    expect(SPOT_WINDOW).toEqual({ start: 540, end: 810 });
    expect(STKFUT_WINDOW).toEqual({ start: 525, end: 825 });
    // 現貨窗必須逐值等於既有兩個常數 —— 兩份數字漂開時,預設參數就不再等於舊語意,
    // 而所有「不傳窗」的既有呼叫端會一起靜默改變
    expect(SPOT_WINDOW.start).toBe(X_START_MIN);
    expect(SPOT_WINDOW.end).toBe(X_END_MIN);
  });

  it("期貨窗:minuteToX 兩端恰落在繪圖區左右界", () => {
    expect(minuteToX(525, W, STKFUT_WINDOW)).toBeCloseTo(Y_AXIS_W, 6);
    expect(minuteToX(825, W, STKFUT_WINDOW)).toBeCloseTo(W - R_AXIS_W, 6);
    // 分母 = 300 分鐘(不是現貨的 270):09:00 落在左界右方恰 15px
    expect(minuteToX(540, W, STKFUT_WINDOW)).toBeCloseTo(Y_AXIS_W + 15, 6);
  });

  it("不傳窗 = 現貨窗(既有呼叫端零改)", () => {
    expect(minuteToX(X_START_MIN, W)).toBeCloseTo(minuteToX(X_START_MIN, W, SPOT_WINDOW), 10);
    expect(minuteToX(X_END_MIN, W)).toBeCloseTo(W - R_AXIS_W, 6);
    // 現貨窗下 09:00 仍在左界(不因期貨窗的存在而位移)
    expect(minuteToX(X_START_MIN, W)).toBeCloseTo(Y_AXIS_W, 6);
  });

  it("期貨窗:minuteOf ↔ minuteToX 互逆(含 08:45 / 13:45 兩端)", () => {
    const ms = [525, 540, 600, 810, 825];
    const g = buildIntradayGeometry(
      { minutes: minutes(ms.map((m) => [m, { c: 2_320_000, v: 1 }])), meta: META2 },
      { width: W, height: 100 },
      STKFUT_WINDOW,
    );
    for (const m of ms) expect(g.minuteOf(minuteToX(m, W, STKFUT_WINDOW))).toBe(m);
  });

  it("期貨窗:窗外(08:44 / 13:46)仍被濾掉,窗內兩端的分鐘進得了價線", () => {
    const ms = minutes([
      [524, { c: 2_300_000, v: 1 }],
      [525, { c: 2_320_000, v: 1 }],
      [600, { c: 2_330_000, v: 1 }],
      [825, { c: 2_340_000, v: 1 }],
      [826, { c: 2_350_000, v: 1 }],
    ]);
    const fut = buildIntradayGeometry(
      { minutes: ms, meta: META2 },
      { width: W, height: 100 },
      STKFUT_WINDOW,
    );
    expect(fut.priceLine.map((p) => p.minute)).toEqual([525, 600, 825]);
    // 同一份資料走預設(現貨)窗只留 09:00–13:30 那一格 —— 證明窗真的是參數而不是常數
    const spot = buildIntradayGeometry({ minutes: ms, meta: META2 }, { width: W, height: 100 });
    expect(spot.priceLine.map((p) => p.minute)).toEqual([600]);
  });

  it("期貨窗:sideSummary 與副圖 bar 與價線吃同一把尺", () => {
    const ms = minutes([
      [525, { c: 2_320_000, v: 5, o: 5 }],
      [600, { c: 2_330_000, v: 3, o: 3 }],
    ]);
    expect(sideSummary(ms, STKFUT_WINDOW).outer).toBe(8);
    expect(sideSummary(ms).outer).toBe(3); // 預設現貨窗:08:45 那分鐘不算
    const sub = buildEnergyBars(ms, { width: W, height: 70 }, STKFUT_WINDOW);
    expect(sub.bars.length).toBe(2);
    expect(sub.bars[0]!.x).toBeCloseTo(minuteToX(525, W, STKFUT_WINDOW), 6);
    // 主圖 energyBars 與副圖逐值相同(既有紀律在新窗下仍成立)
    const g = buildIntradayGeometry(
      { minutes: ms, meta: META2 },
      { width: W, height: 70 },
      STKFUT_WINDOW,
    );
    expect(g.energyBars).toEqual(sub.bars);
  });
});

// 🟢 SC-1 / SC-3:MA 即時價位標籤的右緣佈局(mod/intraday-ma-poc-labels)。
//
// 佈局規則是純 1D 幾何,收在 lib 才測得到「兩顆標籤疊在一起」與「被極值文字壓住」——
// 那兩個症狀在元件層只看得出「有 text 節點」,座標對不對完全沒有訊號。
describe("edgePriceLabels(SC-1/SC-3)", () => {
  /** 呼叫端(元件)實際傳的那組界:上 = 極值文字的 baseline 上界、下 = 繪圖區底再留 5px */
  const BOUNDS = { top: 9, bottom: 246 };

  function line(level: OverlayLevel, y: number, priceMilli = 2_330_000): OverlayLine {
    return { level, y, priceMilli };
  }

  it("只收 ma5 / ma20;CDP 五線不入(它們在右緣帶內已有 `價位*`)", () => {
    const labels = edgePriceLabels(
      [
        line("ah", 20),
        line("nh", 40),
        line("cdp", 60),
        line("nl", 80),
        line("al", 100),
        line("ma5", 120, 2_330_000),
        line("ma20", 160, 2_310_000),
      ],
      [],
      BOUNDS,
    );
    expect(labels.map((l) => l.level)).toEqual(["ma5", "ma20"]);
  });

  it("空輸入 / 只有 CDP → []", () => {
    expect(edgePriceLabels([], [], BOUNDS)).toEqual([]);
    expect(edgePriceLabels([line("cdp", 60)], [], BOUNDS)).toEqual([]);
  });

  it("priceMilli 與 level 原樣帶出(顯示文字的口徑留在呼叫端)", () => {
    const labels = edgePriceLabels([line("ma5", 120, 2_331_237)], [], BOUNDS);
    expect(labels[0]!.priceMilli).toBe(2_331_237);
    expect(labels[0]!.level).toBe("ma5");
  });

  it("相距夠遠 → y 原樣不動(不無故位移)", () => {
    const labels = edgePriceLabels([line("ma5", 50), line("ma20", 120)], [], BOUNDS);
    expect(labels.map((l) => l.y)).toEqual([50, 120]);
  });

  it("同 y(MA5 === MA20 同價)→ 中心距恰 EDGE_LABEL_H,兩顆各自可讀", () => {
    const labels = edgePriceLabels(
      [line("ma5", 100, 2_330_000), line("ma20", 100, 2_330_000)],
      [],
      BOUNDS,
    );
    // 上下順序取輸入順序(overlayLines 的 ma5 → ma20),不因浮點比較而不決定性
    expect(labels.map((l) => l.level)).toEqual(["ma5", "ma20"]);
    expect(labels[1]!.y - labels[0]!.y).toBeCloseTo(EDGE_LABEL_H, 6);
  });

  it("僅差 3px → 撐開到 EDGE_LABEL_H(上面那顆留原位)", () => {
    const labels = edgePriceLabels([line("ma5", 100), line("ma20", 103)], [], BOUNDS);
    expect(labels[0]!.y).toBe(100);
    expect(labels[1]!.y).toBe(110);
  });

  it("obstacle(右緣區極值文字)不可動 → MA 讓位,中心距 ≥ EDGE_LABEL_H", () => {
    const labels = edgePriceLabels([line("ma5", 105)], [100], BOUNDS);
    expect(labels[0]!.y).not.toBe(105);
    expect(Math.abs(labels[0]!.y - 100)).toBeGreaterThanOrEqual(EDGE_LABEL_H);
    // 讓位方向:先往下(top-down sweep),回推只在底部溢出時發生
    expect(labels[0]!.y).toBe(110);
  });

  it("obstacle 夾在兩條 MA 之間 → 兩顆各自讓開,彼此也不疊", () => {
    const labels = edgePriceLabels([line("ma5", 100), line("ma20", 118)], [115], BOUNDS);
    for (const l of labels) expect(Math.abs(l.y - 115)).toBeGreaterThanOrEqual(EDGE_LABEL_H);
    expect(labels[1]!.y - labels[0]!.y).toBeGreaterThanOrEqual(EDGE_LABEL_H);
  });

  it("兩個 obstacle 連續擠壓 → 仍逐一讓開(不只避讓第一個)", () => {
    const labels = edgePriceLabels([line("ma5", 102)], [100, 112], BOUNDS);
    for (const o of [100, 112]) {
      expect(Math.abs(labels[0]!.y - o)).toBeGreaterThanOrEqual(EDGE_LABEL_H);
    }
  });

  it("近頂(MA 貼漲停)→ clamp 到 bounds.top", () => {
    const labels = edgePriceLabels([line("ma5", 2)], [], BOUNDS);
    expect(labels[0]!.y).toBe(BOUNDS.top);
  });

  it("近底(MA 貼跌停)→ clamp 到 bounds.bottom", () => {
    const labels = edgePriceLabels([line("ma5", 400)], [], BOUNDS);
    expect(labels[0]!.y).toBe(BOUNDS.bottom);
  });

  it("底部溢出 → 整組回推,兩顆都留在界內且仍不疊", () => {
    const labels = edgePriceLabels([line("ma5", 240), line("ma20", 244)], [], BOUNDS);
    for (const l of labels) {
      expect(l.y).toBeGreaterThanOrEqual(BOUNDS.top);
      expect(l.y).toBeLessThanOrEqual(BOUNDS.bottom);
    }
    expect(labels[1]!.y - labels[0]!.y).toBeGreaterThanOrEqual(EDGE_LABEL_H);
    expect(labels[1]!.y).toBe(BOUNDS.bottom);
  });

  it("EDGE_LABEL_H 是**中心距**(字高 ≈9px + 1 呼吸),不是字高本身", () => {
    expect(EDGE_LABEL_H).toBe(10);
  });

  /** review B-5:退化 bounds。可達性不是純理論 —— svgBox 的 minPx 地板 + 超寬容器
   *  會把 mainH 壓到 30px 以下,bounds 區間縮到個位數甚至反轉。 */
  describe("退化 bounds(review B-5)", () => {
    it("top > bottom(超壓縮畫布)→ 一律 [](clamp 語意會讓 bottom 勝出、輸出落界外)", () => {
      expect(
        edgePriceLabels([line("ma5", 12), line("ma20", 14)], [], { top: 9, bottom: 6 }),
      ).toEqual([]);
    });

    it("空間裝不下兩顆(區間 < EDGE_LABEL_H)→ 只留排序在前那顆,不疊印", () => {
      const labels = edgePriceLabels([line("ma5", 12), line("ma20", 14)], [], {
        top: 9,
        bottom: 15,
      });
      expect(labels.map((l) => l.level)).toEqual(["ma5"]);
      expect(labels[0]!.y).toBeGreaterThanOrEqual(9);
      expect(labels[0]!.y).toBeLessThanOrEqual(15);
    });

    it("裝得下但被 obstacle 擠到同一 y → 丟後者不疊印(疊印比少一顆更不可讀)", () => {
      // probe 自 review B-5 evidence:未修前兩顆都被 clamp 成 y=9(完全疊印)
      const labels = edgePriceLabels([line("ma5", 12), line("ma20", 14)], [15], {
        top: 9,
        bottom: 20,
      });
      expect(labels.length).toBe(1);
      expect(labels[0]!.level).toBe("ma5");
      expect(labels[0]!.y).toBeGreaterThanOrEqual(9);
      expect(labels[0]!.y).toBeLessThanOrEqual(20);
    });
  });
});
