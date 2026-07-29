/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ChartReadout, type ReadoutField } from "@/components/chart/ChartReadout";

afterEach(cleanup);

const FIELDS: ReadoutField[] = [
  { label: "", value: "09:31" },
  { label: "", value: "232.5", tone: "bull" },
  { label: "", value: "+1.20%", tone: "bull" },
  { label: "量", value: "1234" },
  { label: "外", value: "800", tone: "bull" },
  { label: "內", value: "434", tone: "bear" },
];

describe("ChartReadout", () => {
  it("依序渲染所有欄位,順序與數量不變", () => {
    const { container } = render(<ChartReadout fields={FIELDS} hovering={false} />);
    const spans = [...container.querySelectorAll("[data-testid='chart-readout'] > span")];
    expect(spans.length).toBe(6);
    expect(spans[0]!.textContent).toBe("09:31");
    expect(spans[3]!.textContent).toBe("量 1234");
  });

  it("tone 對應 class:bull 紅 / bear 綠 / muted 灰 / 未給則 ink", () => {
    const { container } = render(
      <ChartReadout
        fields={[
          { label: "", value: "t" },
          { label: "", value: "a", tone: "bull" },
          { label: "", value: "b", tone: "bear" },
          { label: "", value: "c", tone: "muted" },
          { label: "", value: "d" },
        ]}
        hovering={false}
      />,
    );
    const spans = [...container.querySelectorAll("[data-testid='chart-readout'] > span")];
    expect(spans[1]!.className).toContain("text-bull");
    expect(spans[2]!.className).toContain("text-bear");
    expect(spans[3]!.className).toContain("text-ink-dim");
    expect(spans[4]!.className).toContain("text-ink");
  });

  it("hovering 時第一欄轉 accent、否則 ink-muted(零位移的態提示)", () => {
    const { container, rerender } = render(<ChartReadout fields={FIELDS} hovering={false} />);
    const first = () => container.querySelector("[data-testid='chart-readout'] > span")!;
    expect(first().className).toContain("text-ink-muted");
    expect(first().className).not.toContain("text-accent");
    rerender(<ChartReadout fields={FIELDS} hovering />);
    expect(first().className).toContain("text-accent");
  });

  it("缺值以 '-' 佔位,欄位不消失(防寬度跳動)", () => {
    render(
      <ChartReadout
        fields={[
          { label: "", value: "-" },
          { label: "量", value: "-" },
        ]}
        hovering={false}
      />,
    );
    const row = screen.getByTestId("chart-readout");
    expect(row.children.length).toBe(2);
    expect(row.textContent).toContain("量 -");
  });

  it("hovering 狀態暴露在 data 屬性上(供元件測試斷言)", () => {
    const { rerender } = render(<ChartReadout fields={FIELDS} hovering={false} />);
    expect(screen.getByTestId("chart-readout").getAttribute("data-hovering")).toBe("false");
    rerender(<ChartReadout fields={FIELDS} hovering />);
    expect(screen.getByTestId("chart-readout").getAttribute("data-hovering")).toBe("true");
  });
});
