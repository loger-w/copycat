/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AdvanceDeclineChart } from "@/components/index/AdvanceDeclineChart";
import type { BreadthBuckets, BreadthPoint } from "@/types";

/** 桶序固定 `[limit_up, up, flat, down, limit_down]`(types.ts 契約)。 */
function pt(t: string, twse: BreadthBuckets, tpex: BreadthBuckets): BreadthPoint {
  return { t, twse, tpex };
}

/** 線拆成 0 軸上下兩段後,**兩段的 points 完全相同**(可見範圍由 clip 決定,不是各畫
 *  一半)—— 幾何類斷言一律錨 `adl-line-up`,兩段都查等於同一件事驗兩次。 */
function pointCount(): number {
  const line = screen.getByTestId("adl-line-up");
  const raw = (line.getAttribute("points") ?? "").trim();
  return raw === "" ? 0 : raw.split(/\s+/).length;
}

afterEach(cleanup);

describe("AdvanceDeclineChart net 計算(SC-4)", () => {
  it("(a) net = (漲停+上漲) − (下跌+跌停),上市 + 上櫃合計", () => {
    // twse: (1+10) − (4+0) = 7;tpex: (0+2) − (1+1) = 0 → 合計 +7
    render(
      <AdvanceDeclineChart series={[pt("0930", [1, 10, 5, 4, 0], [0, 2, 1, 1, 1])]} />,
    );
    expect(screen.getByTestId("adl-last").textContent).toContain("+7");
  });

  // SVG `<text>` 的字色走 `fill-*`(`text-*` 在 SVG 是 no-op;MarketChart 同慣例),
  // 語意仍是 bull/bear 兩顆 token。
  it("(b) net 為負 → 末值染 bear;為正 → bull", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 1, 0, 20, 3], [0, 0, 0, 0, 0])]} />);
    const neg = screen.getByTestId("adl-last");
    expect(neg.textContent).toContain("-22");
    expect(neg.getAttribute("class")).toContain("fill-bear");
    cleanup();
    render(<AdvanceDeclineChart series={[pt("0930", [2, 30, 0, 1, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-last").getAttribute("class")).toContain("fill-bull");
  });

  it("(c) 只標右端末值,不逐點標數字", () => {
    render(
      <AdvanceDeclineChart
        series={[
          pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1000", [0, 20, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1030", [0, 33, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    expect(screen.getAllByTestId("adl-last").length).toBe(1);
    expect(screen.getByTestId("adl-last").textContent).toContain("+33");
    expect(screen.queryByText(/^\+10$/)).toBeNull();
  });
});

describe("AdvanceDeclineChart 域與防禦(SC-4)", () => {
  it("(d) 域外 / 非法分鐘鍵不產生點(1430 盤後、abcd 非數字、0860 非法分)", () => {
    render(
      <AdvanceDeclineChart
        series={[
          pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1430", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("abcd", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("0860", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("0800", [0, 99, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    expect(pointCount()).toBe(1);
    // 末值取的是「有效點」的最後一格,不是陣列末項
    expect(screen.getByTestId("adl-last").textContent).toContain("+10");
  });

  it("(e) 域邊界 0901 與 1330 都算有效點", () => {
    render(
      <AdvanceDeclineChart
        series={[
          pt("0901", [0, 1, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1330", [0, 2, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    expect(pointCount()).toBe(2);
  });

  it("(f) x 是固定域不隨資料伸縮:同一分鐘鍵在不同 series 下 x 相同", () => {
    render(<AdvanceDeclineChart series={[pt("1000", [0, 5, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    const solo = (screen.getByTestId("adl-line-up").getAttribute("points") ?? "").split(",")[0];
    cleanup();
    render(
      <AdvanceDeclineChart
        series={[
          pt("0910", [0, 1, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1000", [0, 5, 0, 0, 0], [0, 0, 0, 0, 0]),
          pt("1300", [0, 9, 0, 0, 0], [0, 0, 0, 0, 0]),
        ]}
      />,
    );
    const many = (screen.getByTestId("adl-line-up").getAttribute("points") ?? "").split(/\s+/)[1];
    expect(many?.split(",")[0]).toBe(solo);
  });

  it("(g) 0 軸恆可見", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-zero")).toBeTruthy();
  });

  // 兩段線都要斷:只查舊的單一 `adl-line` 在改名後恆為 null,測試會靜默轉 vacuous
  // (實作把線畫出來了照樣綠)。
  it("(h) 空 series → 佔位文字、無折線", () => {
    render(<AdvanceDeclineChart series={[]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
    expect(screen.queryByTestId("adl-line-up")).toBeNull();
    expect(screen.queryByTestId("adl-line-down")).toBeNull();
  });

  it("(i) 全部域外 → 同樣走佔位(沒有可畫的點)", () => {
    render(<AdvanceDeclineChart series={[pt("1430", [0, 9, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
    expect(screen.queryByTestId("adl-line-up")).toBeNull();
    expect(screen.queryByTestId("adl-line-down")).toBeNull();
  });

  it("(j) 單序列不放 legend(標題即名)", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("騰落線");
    expect(screen.queryByTestId("adl-legend")).toBeNull();
  });
});

// 分時圖(StockIntradayChart)同款手法:一條完整的線 / 一塊完整的面積各畫兩份,可見
// 範圍交給 0 軸上下兩個 clipPath 決定。**兩份恆 render** —— 依 net 正負條件 render 的話,
// 全紅那天的 `adl-line-down` 會消失,錨點隨資料時有時無。
describe("AdvanceDeclineChart 紅綠雙色(SC-6)", () => {
  const MIXED = [
    pt("0930", [0, 30, 0, 1, 0], [0, 0, 0, 0, 0]), // net +29
    pt("1000", [0, 1, 0, 40, 0], [0, 0, 0, 0, 0]), // net −39
  ];

  it("(k) 線拆兩段:上段 stroke-bull / 下段 stroke-bear,各自 clip 到 defs 內同 id", () => {
    const { container } = render(<AdvanceDeclineChart series={MIXED} />);
    const up = screen.getByTestId("adl-line-up");
    const down = screen.getByTestId("adl-line-down");
    expect(up.getAttribute("class")).toContain("stroke-bull");
    expect(down.getAttribute("class")).toContain("stroke-bear");
    // 單色 accent 線已退役:留著等於改壞雙色時仍有一條線在,零錯誤訊號
    expect(container.querySelector(".stroke-accent")).toBeNull();

    const clips = [...container.querySelectorAll("clipPath")];
    expect(clips.length).toBe(2);
    for (const clip of clips) {
      const id = clip.getAttribute("id")!;
      // url(#…) 解析失敗在 SVG 規範下是「該元素不繪製」,完全靜默 → id 字元集要鎖
      expect(id).toMatch(/^[A-Za-z0-9_-]+$/);
    }
    const [above, below] = clips.map((c) => c.getAttribute("id")!);
    expect(above!.endsWith("-above")).toBe(true);
    expect(below!.endsWith("-below")).toBe(true);
    expect(up.getAttribute("clip-path")).toBe(`url(#${above})`);
    expect(down.getAttribute("clip-path")).toBe(`url(#${below})`);
  });

  it("(l) 面積同樣兩段:fill-bull / fill-bear,半透明 0.15", () => {
    render(<AdvanceDeclineChart series={MIXED} />);
    const upArea = screen.getByTestId("adl-area-up");
    const downArea = screen.getByTestId("adl-area-down");
    expect(upArea.getAttribute("class")).toContain("fill-bull");
    expect(downArea.getAttribute("class")).toContain("fill-bear");
    expect(upArea.getAttribute("fill-opacity")).toBe("0.15");
    expect(downArea.getAttribute("fill-opacity")).toBe("0.15");
  });

  it("(k2) 全正 / 全負也照畫兩段(錨點不隨資料正負消失)", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 30, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-line-up")).toBeTruthy();
    expect(screen.getByTestId("adl-line-down")).toBeTruthy();
    expect(screen.getByTestId("adl-area-up")).toBeTruthy();
    expect(screen.getByTestId("adl-area-down")).toBeTruthy();
  });
});
