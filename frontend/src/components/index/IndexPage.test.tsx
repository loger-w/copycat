/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { IndexPage } from "@/components/index/IndexPage";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";

function series(over: Partial<IndexSeries> = {}): IndexSeries {
  return {
    p: 42_039_920,
    ref: 43_634_190,
    high: 43_221_930,
    low: 41_815_780,
    stale: false,
    minutes: { "0901": 43_000_000, "0930": 42_039_920 },
    ...over,
  };
}

const OTC = series({ p: 359_800, ref: 378_090, high: 373_420, low: 358_430, minutes: { "1017": 359_800 } });
const TXF: TxfQuote = { p: 42_142_000, time: "10:16:10" };

beforeEach(() => {
  window.localStorage.removeItem("copycat-index-mode");
});

afterEach(cleanup);

function renderPage(txf: TxfQuote | null = TXF) {
  return render(<IndexPage twse={series()} otc={OTC} txf={txf} />);
}

describe("IndexPage(SC-2/3)", () => {
  it("並排:兩張卡(加權指數/櫃買指數)含大字現值、漲跌、高低昨收行", () => {
    renderPage();
    expect(screen.getByText("加權指數")).toBeTruthy();
    expect(screen.getByText("櫃買指數")).toBeTruthy();
    expect(screen.getByText("42039.92")).toBeTruthy();
    expect(screen.getByText("359.8")).toBeTruthy();
    expect(screen.getByText(/-1594\.27/)).toBeTruthy(); // 加權跌點
    expect(screen.getByText(/高 43221\.93/)).toBeTruthy();
    expect(screen.getByText(/昨收 43634\.19/)).toBeTruthy();
  });

  it("台指期列:價 + 價差 + 更新時間(HH:MM)", () => {
    renderPage();
    const row = screen.getByText(/台指期/);
    expect(row.textContent).toContain("42142");
    expect(row.textContent).toContain("+102.08");
    expect(row.textContent).toContain("10:16");
  });

  it("重疊模式 toggle:切換後單卡雙線 + 持久化", () => {
    const { container } = renderPage();
    expect(container.querySelectorAll("svg").length).toBe(2); // 並排兩張
    fireEvent.click(screen.getByRole("button", { name: "重疊" }));
    expect(container.querySelectorAll("svg").length).toBe(1);
    expect(container.querySelectorAll("polyline").length).toBe(2); // 雙線
    expect(window.localStorage.getItem("copycat-index-mode")).toBe("overlay");
    fireEvent.click(screen.getByRole("button", { name: "並排" }));
    expect(container.querySelectorAll("svg").length).toBe(2);
  });

  it("txf null → 台指期列顯示「-」", () => {
    renderPage(null);
    expect(screen.getByText(/台指期/).textContent).toContain("-");
  });
});
