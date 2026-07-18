/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PnlChart } from "@/components/PnlChart";
import type { Snapshot } from "@/types";

afterEach(cleanup);

const BASE: Snapshot = {
  series_id: "TX4.202607",
  status: "live",
  curve: [],
};

describe("PnlChart", () => {
  it("空狀態顯示尚無成交累積,不畫假曲線", () => {
    const { container } = render(<PnlChart snapshot={BASE} />);
    expect(screen.getByText("尚無成交累積")).toBeTruthy();
    expect(container.querySelector("svg path")).toBeNull();
  });

  it("有曲線時渲染 path 與 BEP 標記", () => {
    const snap: Snapshot = {
      ...BASE,
      curve: [
        [43_000_000, 100_000],
        [44_000_000, -100_000],
      ],
      beps: [43500],
      spot: { symbol: "TXF", price: 43600 },
    };
    const { container } = render(<PnlChart snapshot={snap} />);
    expect(container.querySelectorAll("svg path").length).toBeGreaterThanOrEqual(3);
    expect(container.querySelectorAll("circle").length).toBe(1); // BEP 標記
  });
});
