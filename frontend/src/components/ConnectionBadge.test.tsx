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
});
