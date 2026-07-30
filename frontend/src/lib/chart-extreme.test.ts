import { describe, expect, it } from "vitest";

import {
  CANDLE_MARK,
  clampLabelX,
  INTRADAY_MARK,
  markLabelY,
  trianglePoints,
} from "@/lib/chart-extreme";

describe("trianglePoints", () => {
  it("apex 是第一個點且恰在價位上", () => {
    const pts = trianglePoints(100, 50, "up", INTRADAY_MARK).split(" ").map((p) => p.split(",").map(Number));
    expect(pts[0]).toEqual([100, 50]);
  });

  it("高標 body 朝下(圖內)、低標 body 朝上(圖內)—— 不會被 viewBox 裁掉", () => {
    const up = trianglePoints(100, 50, "up", INTRADAY_MARK).split(" ").map((p) => p.split(",").map(Number));
    for (const p of up.slice(1)) expect(p[1]!).toBeGreaterThan(50);
    const down = trianglePoints(100, 50, "down", INTRADAY_MARK).split(" ").map((p) => p.split(",").map(Number));
    for (const p of down.slice(1)) expect(p[1]!).toBeLessThan(50);
  });

  it("K 線的三角比分時圖大(viewBox 寬差 1.75×)", () => {
    expect(CANDLE_MARK.half).toBeGreaterThan(INTRADAY_MARK.half);
    expect(CANDLE_MARK.height).toBeGreaterThan(INTRADAY_MARK.height);
  });

  // review F10:只驗方向與 apex 的話,half / height 被改壞(三角變歪斜或過高)測試仍全綠
  it("底邊兩點的精確幾何(±half / height)被鎖住", () => {
    expect(trianglePoints(100, 50, "up", INTRADAY_MARK)).toBe("100,50 96.5,56 103.5,56");
    expect(trianglePoints(100, 50, "down", INTRADAY_MARK)).toBe("100,50 96.5,44 103.5,44");
    expect(trianglePoints(200, 30, "up", CANDLE_MARK)).toBe("200,30 195,38 205,38");
  });

  // review F2:分 K 240 根時 slot ≈ 5.8px、首根 cx ≈ 2.9px,而 CANDLE_MARK.half = 5
  describe("邊界夾制(bounds)", () => {
    it("未傳 bounds → 不夾制(既有行為)", () => {
      expect(trianglePoints(2.92, 100, "up", CANDLE_MARK)).toBe("2.92,100 -2.08,108 7.92,108");
    });

    it("靠左出界 → 整個三角平移到剛好貼齊左界(形狀不變形)", () => {
      const pts = trianglePoints(2.92, 100, "up", CANDLE_MARK, { min: 0, max: 1400 })
        .split(" ")
        .map((p) => p.split(",").map(Number));
      expect(pts[0]![0]).toBe(5); // apex 被推到 half
      expect(pts[1]![0]).toBe(0); // 左翼恰貼左界,不再是負數
      expect(pts[2]![0]).toBe(10);
      // 三角仍是等腰(左右翼與 apex 等距)= 只平移沒變形
      expect(pts[0]![0]! - pts[1]![0]!).toBe(pts[2]![0]! - pts[0]![0]!);
    });

    it("靠右出界 → 平移到貼齊右界", () => {
      const pts = trianglePoints(1399, 100, "down", CANDLE_MARK, { min: 0, max: 1400 })
        .split(" ")
        .map((p) => p.split(",").map(Number));
      expect(pts[0]![0]).toBe(1395);
      expect(pts[2]![0]).toBe(1400);
    });

    it("域內的 x 原樣保留(不因為傳了 bounds 就位移)", () => {
      expect(trianglePoints(700, 100, "up", CANDLE_MARK, { min: 0, max: 1400 })).toBe(
        "700,100 695,108 705,108",
      );
    });
  });
});

describe("markLabelY 翻面", () => {
  const limits = { top: 9, bottom: 244 };

  it("空間夠 → 高標文字在 apex 上方、低標在下方", () => {
    expect(markLabelY(120, "up", INTRADAY_MARK, limits)).toBe(115);
    expect(markLabelY(120, "down", INTRADAY_MARK, limits)).toBe(132);
  });

  it("高標頂到圖框 → 文字翻到三角下方", () => {
    // y=4(漲停貼頂):4-5 = -1 < top 9 → 翻面
    expect(markLabelY(4, "up", INTRADAY_MARK, limits)).toBe(19);
  });

  it("低標頂到圖底 → 文字翻到三角上方", () => {
    // y=242(跌停貼底):242+12 = 254 > bottom 244 → 翻面
    expect(markLabelY(242, "down", INTRADAY_MARK, limits)).toBe(232);
  });

  it("K 線常態(BB 關閉):高在 y 域頂、低在價格區底 → 兩個都翻面", () => {
    // buildCandleGeometry:toY(windowHigh) === PAD_Y === 6;toY(windowLow) === priceBottom − PAD_Y
    const k = { top: 11, bottom: 438 };
    expect(markLabelY(6, "up", CANDLE_MARK, k)).toBe(25); // 6+19,不是 6−6=0(會被裁)
    expect(markLabelY(434, "down", CANDLE_MARK, k)).toBe(422); // 434−12,不是 450(落進量區)
  });
});

describe("clampLabelX", () => {
  it("夾進可用範圍", () => {
    expect(clampLabelX(10, 46, 760)).toBe(46);
    expect(clampLabelX(900, 46, 760)).toBe(760);
    expect(clampLabelX(400, 46, 760)).toBe(400);
  });
});
