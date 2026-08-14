/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { extendMinutes, MiniIntradayChart, MINI_H, MINI_W } from "@/components/stock/MiniIntradayChart";
import type { MinuteAgg, StockMeta } from "@/lib/stock-accum";
import { PAD_Y, X_END_MIN, X_START_MIN, Y_AXIS_W } from "@/lib/stock-intraday-svg";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const META: StockMeta = {
  name: "台積電",
  ref: 2_320_000,
  upper: 2_550_000,
  lower: 2_090_000,
  y_vol: 100,
};

function agg(over: Partial<MinuteAgg> = {}): MinuteAgg {
  return { c: 2_320_000, v: 1, i: 0, o: 1, u: 0, h: null, l: null, ...over };
}

function xs(points: string): number[] {
  return points.split(" ").map((p) => Number(p.split(",")[0]));
}

function ys(points: string): number[] {
  return points.split(" ").map((p) => Number(p.split(",")[1]));
}

function priceLinePoints(container: HTMLElement): string {
  const el = container.querySelector('[data-testid="mini-price"]');
  return el?.getAttribute("points") ?? "";
}

describe("MiniIntradayChart 幾何補償(design v3 R5/R13)", () => {
  it("viewBox 平移裁掉左右軸帶 —— 只留繪圖區", () => {
    const { container } = render(
      <MiniIntradayChart minutes={new Map([[X_START_MIN, agg()]])} meta={META} liveP={null} />,
    );
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("viewBox")).toBe(`${Y_AXIS_W} 0 ${MINI_W} ${MINI_H}`);
  });

  it("走勢線 x 滿版:09:00 貼左緣、13:30 貼右緣", () => {
    const minutes = new Map<number, MinuteAgg>([
      [X_START_MIN, agg()],
      [X_END_MIN, agg()],
    ]);
    const { container } = render(<MiniIntradayChart minutes={minutes} meta={META} liveP={null} />);
    const x = xs(priceLinePoints(container));
    expect(x[0]).toBeCloseTo(Y_AXIS_W, 1);
    expect(x[x.length - 1]!).toBeCloseTo(Y_AXIS_W + MINI_W, 1);
  });

  // R13:height 帶 X_LABEL_H 補償 → 內容落在 [PAD_Y, MINI_H − PAD_Y],上下對稱各留一份。
  // v2 的「上緣 0、下緣 4px」不對稱會讓漲停那根貼頂的 stroke 被裁掉半條。
  it("漲停 / 跌停都不被裁:所有 y ∈ [PAD_Y, MINI_H − PAD_Y] 且兩端恰貼邊", () => {
    const minutes = new Map<number, MinuteAgg>([
      [X_START_MIN, agg({ c: META.upper! })],
      [X_START_MIN + 1, agg({ c: META.ref! })],
      [X_END_MIN, agg({ c: META.lower! })],
    ]);
    const { container } = render(<MiniIntradayChart minutes={minutes} meta={META} liveP={null} />);
    const y = ys(priceLinePoints(container));
    for (const v of y) {
      expect(v).toBeGreaterThanOrEqual(PAD_Y);
      expect(v).toBeLessThanOrEqual(MINI_H - PAD_Y);
    }
    expect(y[0]).toBeCloseTo(PAD_Y, 1);
    expect(y[y.length - 1]!).toBeCloseTo(MINI_H - PAD_Y, 1);
  });

  it("meta.ref 有值 → 畫平盤虛線 + 紅綠面積", () => {
    const { container } = render(
      <MiniIntradayChart minutes={new Map([[X_START_MIN, agg()]])} meta={META} liveP={null} />,
    );
    expect(container.querySelector('[data-testid="mini-ref"]')).toBeTruthy();
    expect(container.querySelectorAll('[data-testid="mini-area"]').length).toBeGreaterThan(0);
    // 平盤虛線的線寬/疏密釘螢幕像素(review A-4):矩陣卡片變高後掉了它是純視覺回歸
    expect(
      container.querySelector('[data-testid="mini-ref"]')?.getAttribute("vector-effect"),
    ).toBe("non-scaling-stroke");
  });

  it("meta.ref 缺 → 無平盤可言:不畫虛線也不填色", () => {
    const noRef: StockMeta = { ...META, ref: null };
    const { container } = render(
      <MiniIntradayChart minutes={new Map([[X_START_MIN, agg()]])} meta={noRef} liveP={null} />,
    );
    expect(container.querySelector('[data-testid="mini-ref"]')).toBeNull();
    expect(container.querySelectorAll('[data-testid="mini-area"]').length).toBe(0);
    // 走勢線本身仍要畫得出來
    expect(priceLinePoints(container)).not.toBe("");
    // 無 ref 分支是**第三條** polyline(stroke-accent),GroupGridView 的元件測試
    // 只蓋得到有 ref 的兩條 —— 這裡不鎖,冷門股(無昨收)的線寬回歸零訊號(review A-4)
    expect(
      container.querySelector('[data-testid="mini-price"]')?.getAttribute("vector-effect"),
    ).toBe("non-scaling-stroke");
  });

  // 卡片只有 15rem 寬,任何刻度文字都塞不下也讀不到 —— 「無座標軸」是 SC-3 的明文要求。
  // (clipPath 內的 <rect> 是紅綠切半的機制,不是版面元素,所以只鎖文字。)
  it("mini 圖不掛座標軸文字(SC-3:無座標軸)", () => {
    const { container } = render(
      <MiniIntradayChart minutes={new Map([[X_START_MIN, agg()]])} meta={META} liveP={null} />,
    );
    expect(container.querySelectorAll("text").length).toBe(0);
  });
});

// R10 延伸規則:分鐘鍵 = 本機時鐘分鐘,僅當落在 [09:00, 13:30] 且 liveP > 0 才延伸。
describe("extendMinutes(R10 現價延伸)", () => {
  const at = (h: number, m: number) => new Date(2026, 7, 6, h, m, 30);

  it("既有 bucket → 只覆寫 c,量與高低原樣", () => {
    const src = new Map<number, MinuteAgg>([
      [600, { c: 2_300_000, v: 12, i: 5, o: 6, u: 1, h: 2_310_000, l: 2_295_000 }],
    ]);
    const out = extendMinutes(src, 2_345_000, at(10, 0));
    expect(out.get(600)).toEqual({
      c: 2_345_000,
      v: 12,
      i: 5,
      o: 6,
      u: 1,
      h: 2_310_000,
      l: 2_295_000,
    });
    // 淺拷不就地改:原 Map 不可被污染
    expect(src.get(600)?.c).toBe(2_300_000);
  });

  it("無 bucket → 新建零量點(h/l 為 null,不冒充)", () => {
    const out = extendMinutes(new Map(), 2_345_000, at(10, 0));
    expect(out.get(600)).toEqual({ c: 2_345_000, v: 0, i: 0, o: 0, u: 0, h: null, l: null });
  });

  it("窗外時刻(13:31 之後 / 09:00 之前)不延伸", () => {
    const src = new Map<number, MinuteAgg>([[600, { c: 2_300_000, v: 1, i: 0, o: 1, u: 0 }]]);
    expect(extendMinutes(src, 2_345_000, at(14, 0))).toBe(src);
    expect(extendMinutes(src, 2_345_000, at(8, 50))).toBe(src);
  });

  it("liveP 為 null / 0 / 負 → 不延伸(0 是 TC4 的「不可得」不是價格)", () => {
    const src = new Map<number, MinuteAgg>([[600, { c: 2_300_000, v: 1, i: 0, o: 1, u: 0 }]]);
    expect(extendMinutes(src, null, at(10, 0))).toBe(src);
    expect(extendMinutes(src, 0, at(10, 0))).toBe(src);
    expect(extendMinutes(src, -5, at(10, 0))).toBe(src);
  });

  // 元件不開「注入 now」的測試專用 prop —— 那條路只有測試會走,鎖不到真實時鐘那一支。
  // 改動系統時鐘,測到的是元件內真的呼叫了 `new Date()`。
  it("延伸後的點真的畫進走勢線(不是只算不畫)", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(at(10, 0));
    const minutes = new Map<number, MinuteAgg>([[X_START_MIN, agg()]]);
    const { container } = render(
      <MiniIntradayChart minutes={minutes} meta={META} liveP={2_500_000} />,
    );
    expect(xs(priceLinePoints(container)).length).toBe(2);
  });
});
