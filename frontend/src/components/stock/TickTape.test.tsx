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
});
