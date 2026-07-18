/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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

  it("SC-3:滑鼠移動顯示游標試算,移出清除", () => {
    const snap: Snapshot = {
      ...BASE,
      curve: [
        [43_000_000, 100_000],
        [44_000_000, -100_000],
      ],
    };
    render(<PnlChart snapshot={snap} />);
    const svg = screen.getByRole("img");
    // jsdom 無 layout(IR-2)→ mock 渲染盒為 1:1 viewBox
    svg.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 960, height: 420 }) as DOMRect;
    // clientX=480 → pad 內、對應 x=43,500,000(插值 PnL=0)
    fireEvent.mouseMove(svg, { clientX: 480, clientY: 200 });
    const readout = screen.getByText(/▸/);
    expect(readout.textContent).toContain("43,500");
    expect(readout.textContent).toContain("NT$ 0");
    fireEvent.mouseLeave(svg);
    expect(screen.queryByText(/▸/)).toBeNull();
  });

  it("SC-3:游標超出曲線範圍不顯示 readout", () => {
    const snap: Snapshot = {
      ...BASE,
      curve: [
        [43_000_000, 100_000],
        [44_000_000, -100_000],
      ],
    };
    render(<PnlChart snapshot={snap} />);
    const svg = screen.getByRole("img");
    svg.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 960, height: 420 }) as DOMRect;
    fireEvent.mouseMove(svg, { clientX: 5, clientY: 200 }); // pad 外
    expect(screen.queryByText(/▸/)).toBeNull();
  });
});
