/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TickTape } from "@/components/stock/TickTape";

afterEach(cleanup);

describe("TickTape", () => {
  it("最新在上,外盤紅內盤綠", () => {
    render(
      <TickTape
        ticks={[
          { t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner" },
          { t: "09:00:02.000", p: 2_375_000, q: 3, side: "outer" },
        ]}
      />,
    );
    const rows = screen.getAllByRole("row").slice(1); // 去表頭
    expect(rows[0]!.textContent).toContain("09:00:02");
    const outerCell = screen.getByText("2375");
    expect(outerCell.className).toContain("text-bull");
    const innerCell = screen.getByText("2370");
    expect(innerCell.className).toContain("text-bear");
  });

  it("空明細顯示提示", () => {
    render(<TickTape ticks={[]} />);
    expect(screen.getByText("尚無成交")).toBeTruthy();
  });

  // 🔴 SC-6:明細改由下半列決定高度(h-full),不再是固定 320px 上限。這是「最外圍不出現
  // 捲軸」機制的一半 —— 圖表維持自然高度,剩餘空間全給下半列,明細在其中自行內捲。
  // 沒有這條護欄,日後誰把 h-full 換回 max-h-* 不會有任何測試變紅。
  it("root 由下半列撐高(h-full),非固定 max-h-80(SC-6)", () => {
    render(<TickTape ticks={[{ t: "09:00:01.000", p: 2_370_000, q: 5, side: "inner" }]} />);
    const root = screen.getByTestId("tick-tape");
    expect(root.className).toContain("h-full");
    expect(root.className).not.toContain("max-h-80");
    expect(root.className).toContain("overflow-y-auto"); // 內捲不可拿掉(W-8 載入更多要可達)
  });
});
