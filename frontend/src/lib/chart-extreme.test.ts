import { describe, expect, it } from "vitest";

import {
  CANDLE_MARK,
  clampLabelX,
  INTRADAY_MARK,
  markCenterX,
  markLabelY,
  markOuterRadius,
  markTone,
} from "@/lib/chart-extreme";

describe("標記形狀(round6b:分時圖實心小圓 / K 線圖只留文字)", () => {
  it("分時圖畫實心圓,K 線圖不畫圖案", () => {
    expect(INTRADAY_MARK.dot).not.toBeNull();
    expect(CANDLE_MARK.dot).toBeNull();
  });

  /** 分時圖漲停時 day-high 恰在 `PAD_Y = 4`,而且**是常態不是邊角**。
   *  舊的三角靠「body 朝圖內」迴避裁切,圓沒有方向可躲,只能靠尺寸。 */
  it("圓的視覺外緣 ≤ PAD_Y(4),y 域端點不被 viewBox 裁", () => {
    expect(markOuterRadius(INTRADAY_MARK)).toBe(2.5 + 1 / 2);
    expect(markOuterRadius(INTRADAY_MARK)).toBeLessThanOrEqual(4);
  });

  it("不畫圖案的 style 外緣為 0,且 markCenterX 不夾制(沒有形狀可裁)", () => {
    expect(markOuterRadius(CANDLE_MARK)).toBe(0);
    expect(markCenterX(2.92, CANDLE_MARK, { min: 0, max: 1400 })).toBe(2.92);
    expect(markCenterX(1399, CANDLE_MARK, { min: 0, max: 1400 })).toBe(1399);
  });

  it("文字外側距離必須清掉圖案 + 字高,否則字會壓在圓上", () => {
    // 分時圖字級 0.5625rem ≈ 9px
    expect(INTRADAY_MARK.labelDown.out).toBeGreaterThanOrEqual(markOuterRadius(INTRADAY_MARK) + 9);
    expect(INTRADAY_MARK.labelUp.out).toBeGreaterThan(markOuterRadius(INTRADAY_MARK));
  });
});

describe("markTone(round6b:相對平盤判色)", () => {
  it("高於平盤紅、低於平盤綠、等於平盤灰", () => {
    expect(markTone(2_395_000, 2_320_000)).toBe("fill-bull");
    expect(markTone(2_300_000, 2_320_000)).toBe("fill-bear");
    expect(markTone(2_320_000, 2_320_000)).toBe("fill-ink-dim");
  });

  /** 「整天下跌的股票其日高塗紅等於假陳述」這條舊顧慮在相對平盤的規則下不成立:
   *  那種股票的日高本來就低於平盤 → 判綠。 */
  it("整天下跌的股票,其當日高仍判綠(不是紅)", () => {
    expect(markTone(2_310_000, 2_320_000)).toBe("fill-bear");
  });

  it("參考價不可得 → 灰(不憑首筆成交價編一個基準出來)", () => {
    expect(markTone(2_395_000, null)).toBe("fill-ink-dim");
    expect(markTone(2_395_000, 0)).toBe("fill-ink-dim");
  });
});

describe("markCenterX 邊界夾制(有圖案時)", () => {
  it("未傳 bounds → 不夾制(既有行為)", () => {
    expect(markCenterX(1, INTRADAY_MARK)).toBe(1);
  });

  it("靠左出界 → 圓心推到剛好讓外緣貼齊左界", () => {
    const r = markOuterRadius(INTRADAY_MARK); // 3
    expect(markCenterX(0.5, INTRADAY_MARK, { min: 0, max: 800 })).toBe(r);
  });

  it("靠右出界 → 貼齊右界", () => {
    const r = markOuterRadius(INTRADAY_MARK);
    expect(markCenterX(799.5, INTRADAY_MARK, { min: 0, max: 800 })).toBe(800 - r);
  });

  it("域內的 x 原樣保留(不因為傳了 bounds 就位移)", () => {
    expect(markCenterX(400, INTRADAY_MARK, { min: 0, max: 800 })).toBe(400);
  });
});

describe("markLabelY 翻面", () => {
  const limits = { top: 9, bottom: 244 };

  it("空間夠 → 高標文字在標記上方、低標在下方", () => {
    expect(markLabelY(120, "up", INTRADAY_MARK, limits)).toBe(113);
    expect(markLabelY(120, "down", INTRADAY_MARK, limits)).toBe(132);
  });

  it("高標頂到圖框 → 文字翻到標記下方", () => {
    // y=4(漲停貼頂):4−7 = −3 < top 9 → 翻面
    expect(markLabelY(4, "up", INTRADAY_MARK, limits)).toBe(18);
  });

  it("低標頂到圖底 → 文字翻到標記上方", () => {
    // y=242(跌停貼底):242+12 = 254 > bottom 244 → 翻面
    expect(markLabelY(242, "down", INTRADAY_MARK, limits)).toBe(234);
  });

  it("K 線常態(BB 關閉):高在 y 域頂、低在價格區底 → 兩個都翻面", () => {
    // buildCandleGeometry:toY(windowHigh) === PAD_Y === 6;toY(windowLow) === priceBottom − PAD_Y
    const k = { top: 11, bottom: 438 };
    expect(markLabelY(6, "up", CANDLE_MARK, k)).toBe(22); // 6+16,不是 6−5=1(會被裁)
    expect(markLabelY(434, "down", CANDLE_MARK, k)).toBe(425); // 434−9,不是 448(落進量區)
  });
});

describe("clampLabelX", () => {
  it("夾進可用範圍", () => {
    expect(clampLabelX(10, 46, 760)).toBe(46);
    expect(clampLabelX(900, 46, 760)).toBe(760);
    expect(clampLabelX(400, 46, 760)).toBe(400);
  });
});
