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

  // 🔴 SC-2:重試期間後端每 attempt 推一則(handover.attempt),badge 要講到第幾次 ——
  // 沒有這個數字時「還在第一次」與「重試到第三次」在畫面上一模一樣,而後者代表回補
  // 一直失敗、快要降級。
  it("回補中第 2 次:label 帶次數", () => {
    render(
      <ConnectionBadge
        status="backfilling"
        wsStatus="open"
        handover={{ attempt: 2, attempts_max: 3, phase: "backfilling" }}
      />,
    );
    expect(screen.getByText("回補中(第 2 次)")).toBeTruthy();
  });

  it("attempt 1 = 第一次回補 → 逐字「回補中」不變(W2)", () => {
    render(
      <ConnectionBadge
        status="backfilling"
        wsStatus="open"
        handover={{ attempt: 1, attempts_max: 3, phase: "backfilling" }}
      />,
    );
    expect(screen.getByText("回補中")).toBeTruthy();
  });

  it("舊後端不發 handover → 逐字「回補中」", () => {
    render(<ConnectionBadge status="backfilling" wsStatus="open" handover={null} />);
    expect(screen.getByText("回補中")).toBeTruthy();
  });

  it("非 backfilling 不帶次數(attempt 留在上一輪的值也不得外洩到別的狀態)", () => {
    render(
      <ConnectionBadge
        status="live"
        wsStatus="open"
        handover={{ attempt: 3, attempts_max: 3, phase: "live" }}
      />,
    );
    expect(screen.getByText("即時連線中")).toBeTruthy();
  });

  it("WS 斷線優先顯示連線中斷", () => {
    render(<ConnectionBadge status="live" wsStatus="closed" />);
    expect(screen.getByText("連線中斷,重試中")).toBeTruthy();
  });

  it("WS 斷線時 handover 的次數不得蓋掉斷線文案(W2:broken 分支優先)", () => {
    render(
      <ConnectionBadge
        status="backfilling"
        wsStatus="closed"
        handover={{ attempt: 3, attempts_max: 3, phase: "backfilling" }}
      />,
    );
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
