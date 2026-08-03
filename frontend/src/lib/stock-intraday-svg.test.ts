import { describe, expect, it } from "vitest";

import type { MinuteAgg } from "@/lib/stock-accum";
import {
  buildEnergyBars,
  buildIntradayGeometry,
  minuteToX,
  overlayLines,
  plotWidth,
  R_AXIS_W,
  sideSummary,
  SUB_TOP_PAD,
  X_END_MIN,
  X_START_MIN,
  Y_AXIS_W,
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
