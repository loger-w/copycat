import { describe, expect, it } from "vitest";

import type { MinuteAgg } from "@/lib/stock-accum";
import {
  buildIntradayGeometry,
  minuteToX,
  overlayLines,
  plotWidth,
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
  y_close: 2_320_000,
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
      { width: Y_AXIS_W + 810 - 540, height: 100 },
    );
    expect(g.priceLine.length).toBe(2);
    // 🔴 SC-4:區間就是漲停/跌停,不再多留 2% 邊
    expect(g.yDomain[1]).toBe(2_550_000);
    expect(g.yDomain[0]).toBe(2_090_000);
    expect(g.priceLine[1]!.y).toBeLessThan(g.priceLine[0]!.y);
    // 域端點落在幾何留邊上(PAD_Y=4、X_LABEL_H=14):走勢線在漲跌停時不被圖框裁掉半條 stroke
    expect(g.upperY).not.toBeNull();
    expect(g.lowerY).not.toBeNull();
    expect(g.upperY!).toBeCloseTo(4, 6);
    expect(g.lowerY!).toBeCloseTo(100 - 14 - 4, 6);
    // 🔴 round4 項 3:繪圖區改從左緣價位帶右側起算,x 不再從 0 開始
    // (width = Y_AXIS_W + 分鐘數 → 繪圖區仍是每分鐘 1px)
    expect(g.priceLine[0]!.x).toBeCloseTo(Y_AXIS_W, 5);
    expect(g.priceLine[1]!.x).toBeCloseTo(Y_AXIS_W + 1, 5);
  });

  // 🔴 round4 項 3:價位文字原本畫在 x=2 而繪圖區從 x=0 起,文字直接壓在走勢線上。
  // 左緣讓出 Y_AXIS_W 寬的價位帶後,`minuteToX` / `minuteOf` 必須**共用**同一組常數,
  // 否則反演只在兩端偏移(同 toY / priceAtY 共用 PAD_Y 的理由)。
  describe("左緣價位帶(gutter)", () => {
    const W = Y_AXIS_W + 270;

    it("Y_AXIS_W 等於 hover 價位標寬度(標籤恰好整格塞進價位帶,不再壓線)", () => {
      expect(Y_AXIS_W).toBe(46);
    });

    it("繪圖區起於價位帶右緣、迄於圖右緣", () => {
      expect(minuteToX(X_START_MIN, W)).toBeCloseTo(Y_AXIS_W, 6);
      expect(minuteToX(X_END_MIN, W)).toBeCloseTo(W, 6);
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
        { width: Y_AXIS_W, height: 100 },
      );
      const x = minuteToX(X_END_MIN, Y_AXIS_W);
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
      const sub = buildIntradayGeometry(input, { width: W, height: 70 });
      expect(sub.energyBars[0]!.x).toBeCloseTo(Y_AXIS_W, 6);
      expect(sub.energyBars.map((b) => b.x)).toEqual(main.priceLine.map((p) => p.x));
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
      { width: Y_AXIS_W + 270, height: 100 },
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
      { width: Y_AXIS_W + 270, height: 100 },
    );
    expect(g.minuteOf(Y_AXIS_W)).toBe(540); // 繪圖區起點 → 09:00
    expect(g.minuteOf(Y_AXIS_W + 60)).toBe(600); // +60px → 10:00(繪圖區 270 → 1px/分)
    expect(g.minuteOf(Y_AXIS_W + 30)).toBeNull(); // 09:30 無資料
    expect(g.minuteOf(-5)).toBeNull();
    expect(g.minuteOf(999)).toBeNull();
  });

  // 🔴 SC-5:主圖底部量 bar 已移除(user 拍板留內外盤能量副圖),volumeBars 不再存在

  it("overlayLines:域內才給、含 level 與 kind(SC-2)", () => {
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
    expect(overlayLines(overlay, g, { cdp: false, ma: true }).map((l) => l.kind)).not.toContain(
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

  it("energy bars per minute(SC-5:只剩內外盤能量,主圖量 bar 已移除)", () => {
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
    expect(g.energyBars[0]!.outer).toBe(7);
    expect(g.energyBars[0]!.inner).toBe(3);
    // 高度依「該分鐘內外盤較大側」正規化
    expect(g.energyBars[0]!.outerH).toBeGreaterThan(g.energyBars[1]!.outerH);
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

  it("maxSide 出口 = 該日內外盤最大單邊(SC-8 量刻度的分母)", () => {
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
    expect(g.maxSide).toBe(7);
  });

  it("energyBars 高度分母已扣掉頂端留白,最高的 bar 不會頂滿全高(SC-8 刻度才不被蓋住)", () => {
    const H = 100;
    const g = buildIntradayGeometry(
      { minutes: minutes([[540, { c: 2_320_000, v: 10, o: 7, i: 3 }]]), meta: META },
      { width: 270, height: H },
    );
    expect(g.energyBars[0]!.outerH).toBeLessThan(H);
    expect(g.energyBars[0]!.outerH).toBe(H - SUB_TOP_PAD);
  });
});
