/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ConnectionBadge } from "@/components/ConnectionBadge";

afterEach(cleanup);

describe("ConnectionBadge", () => {
  it("live 顯示即時連線中", () => {
    render(<ConnectionBadge status="live" wsStatus="open" />);
    expect(screen.getByText("即時連線中")).toBeTruthy();
  });

  it("回補中狀態", () => {
    render(<ConnectionBadge status="backfilling" wsStatus="open" />);
    expect(screen.getByText("回補中")).toBeTruthy();
  });

  it("WS 斷線優先顯示連線中斷", () => {
    render(<ConnectionBadge status="live" wsStatus="closed" />);
    expect(screen.getByText("連線中斷,重試中")).toBeTruthy();
  });

  it("degraded 用警示 tone", () => {
    render(<ConnectionBadge status="degraded" wsStatus="open" />);
    const el = screen.getByText("資料降級");
    expect(el.className).toContain("text-bull");
    expect(el.className).toContain("border-bull/40");
  });

  it("未知狀態 fallback:label 原樣、預設 tone", () => {
    render(<ConnectionBadge status="mystery" wsStatus="open" />);
    const el = screen.getByText("mystery");
    expect(el.className).toContain("bg-surface");
    expect(el.className).toContain("text-ink-muted");
  });
});
