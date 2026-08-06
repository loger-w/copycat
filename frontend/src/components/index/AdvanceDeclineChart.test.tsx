/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AdvanceDeclineChart } from "@/components/index/AdvanceDeclineChart";
import type { BreadthBuckets, BreadthPoint } from "@/types";

/** 桶序固定 `[limit_up, up, flat, down, limit_down]`(types.ts 契約)。 */
function pt(t: string, twse: BreadthBuckets, tpex: BreadthBuckets): BreadthPoint {
  return { t, twse, tpex };
}

function pointCount(): number {
  const line = screen.getByTestId("adl-line");
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
    const solo = (screen.getByTestId("adl-line").getAttribute("points") ?? "").split(",")[0];
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
    const many = (screen.getByTestId("adl-line").getAttribute("points") ?? "").split(/\s+/)[1];
    expect(many?.split(",")[0]).toBe(solo);
  });

  it("(g) 0 軸恆可見", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-zero")).toBeTruthy();
  });

  it("(h) 空 series → 佔位文字、無折線", () => {
    render(<AdvanceDeclineChart series={[]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
    expect(screen.queryByTestId("adl-line")).toBeNull();
  });

  it("(i) 全部域外 → 同樣走佔位(沒有可畫的點)", () => {
    render(<AdvanceDeclineChart series={[pt("1430", [0, 9, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("盤中累積後顯示");
    expect(screen.queryByTestId("adl-line")).toBeNull();
  });

  it("(j) 單序列不放 legend(標題即名)", () => {
    render(<AdvanceDeclineChart series={[pt("0930", [0, 10, 0, 0, 0], [0, 0, 0, 0, 0])]} />);
    expect(screen.getByTestId("adl-chart").textContent).toContain("騰落線");
    expect(screen.queryByTestId("adl-legend")).toBeNull();
  });
});
