import { describe, expect, it } from "vitest";

import {
  CANDLE_MARK,
  clampLabelX,
  INTRADAY_MARK,
  markCenterX,
  markLabelY,
  markOuterRadius,
} from "@/lib/chart-extreme";

describe("圓環尺寸(round6 項 1:三角 → 空心環)", () => {
  it("K 線的環比分時圖大(viewBox 寬差 1.75×)", () => {
    expect(CANDLE_MARK.radius).toBeGreaterThan(INTRADAY_MARK.radius);
    expect(markOuterRadius(CANDLE_MARK)).toBeGreaterThan(markOuterRadius(INTRADAY_MARK));
  });

  it("墨色外緣 = radius + 面環一半線寬(不含底環 —— 底環是背景色墊片,溢出無視覺後果)", () => {
    expect(markOuterRadius(INTRADAY_MARK)).toBe(3 + 1.5 / 2);
    expect(markOuterRadius(CANDLE_MARK)).toBe(4.5 + 1.75 / 2);
  });

  /** 兩張圖的極值標記都會落在 y 域端點上,而且**是常態不是邊角**:
   *  分時圖漲停時 day-high 恰在 `PAD_Y`;K 線圖的視窗高**恆在** `PAD_Y`。
   *  墨色環超過 PAD_Y 就會被 viewBox 裁掉一圈(舊的三角是靠「body 朝圖內」迴避這件事,
   *  圓環沒有方向可以躲,只能靠尺寸)。 */
  it("墨色環在 y 域端點不被 viewBox 裁(分時 PAD_Y=4 / K 線 PAD_Y=6)", () => {
    expect(markOuterRadius(INTRADAY_MARK)).toBeLessThanOrEqual(4);
    expect(markOuterRadius(CANDLE_MARK)).toBeLessThanOrEqual(6);
  });

  it("底環比面環粗 —— 面環才有得墊", () => {
    expect(INTRADAY_MARK.halo).toBeGreaterThan(INTRADAY_MARK.ring);
    expect(CANDLE_MARK.halo).toBeGreaterThan(CANDLE_MARK.ring);
  });

  it("文字外側距離必須清掉整個環 + 字高,否則字會壓在環上", () => {
    // 分時圖字級 0.5625rem ≈ 9px
    expect(INTRADAY_MARK.labelDown.out).toBeGreaterThanOrEqual(markOuterRadius(INTRADAY_MARK) + 9);
    // K 線字級 0.625rem ≈ 10px
    expect(CANDLE_MARK.labelDown.out).toBeGreaterThanOrEqual(markOuterRadius(CANDLE_MARK) + 10);
    // 上方只需清掉環(baseline 在字底),但仍要離環有呼吸
    expect(INTRADAY_MARK.labelUp.out).toBeGreaterThan(markOuterRadius(INTRADAY_MARK));
    expect(CANDLE_MARK.labelUp.out).toBeGreaterThan(markOuterRadius(CANDLE_MARK));
  });
});

describe("markCenterX 邊界夾制", () => {
  it("未傳 bounds → 不夾制(既有行為)", () => {
    expect(markCenterX(2.92, CANDLE_MARK)).toBe(2.92);
  });

  it("靠左出界 → 圓心推到剛好讓底環外緣貼齊左界", () => {
    const r = markOuterRadius(CANDLE_MARK); // 6.5
    expect(markCenterX(2.92, CANDLE_MARK, { min: 0, max: 1400 })).toBe(r);
  });

  it("靠右出界 → 貼齊右界", () => {
    const r = markOuterRadius(CANDLE_MARK);
    expect(markCenterX(1399, CANDLE_MARK, { min: 0, max: 1400 })).toBe(1400 - r);
  });

  it("域內的 x 原樣保留(不因為傳了 bounds 就位移)", () => {
    expect(markCenterX(700, CANDLE_MARK, { min: 0, max: 1400 })).toBe(700);
  });
});

describe("markLabelY 翻面", () => {
  const limits = { top: 9, bottom: 244 };

  it("空間夠 → 高標文字在環上方、低標在下方", () => {
    expect(markLabelY(120, "up", INTRADAY_MARK, limits)).toBe(110);
    expect(markLabelY(120, "down", INTRADAY_MARK, limits)).toBe(135);
  });

  it("高標頂到圖框 → 文字翻到環下方", () => {
    // y=4(漲停貼頂):4−10 = −6 < top 9 → 翻面
    expect(markLabelY(4, "up", INTRADAY_MARK, limits)).toBe(20);
  });

  it("低標頂到圖底 → 文字翻到環上方", () => {
    // y=242(跌停貼底):242+15 = 257 > bottom 244 → 翻面
    expect(markLabelY(242, "down", INTRADAY_MARK, limits)).toBe(232);
  });

  it("K 線常態(BB 關閉):高在 y 域頂、低在價格區底 → 兩個都翻面", () => {
    // buildCandleGeometry:toY(windowHigh) === PAD_Y === 6;toY(windowLow) === priceBottom − PAD_Y
    const k = { top: 11, bottom: 438 };
    expect(markLabelY(6, "up", CANDLE_MARK, k)).toBe(25); // 6+19,不是 6−12=−6(會被裁)
    expect(markLabelY(434, "down", CANDLE_MARK, k)).toBe(422); // 434−12,不是 452(落進量區)
  });
});

describe("clampLabelX", () => {
  it("夾進可用範圍", () => {
    expect(clampLabelX(10, 46, 760)).toBe(46);
    expect(clampLabelX(900, 46, 760)).toBe(760);
    expect(clampLabelX(400, 46, 760)).toBe(400);
  });
});
