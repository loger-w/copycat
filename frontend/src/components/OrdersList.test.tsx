/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OrdersList } from "@/components/OrdersList";
import type { OrdersView } from "@/types";

afterEach(cleanup);

function view(overrides: Partial<OrdersView> = {}): OrdersView {
  return {
    orders: [
      {
        report_id: "E1",
        symbol: "TC.O.TWF.TXO.202607.C.23000",
        side: "1",
        status_raw: "2",
        price: "15.5",
        qty: "1",
        filled_qty: "1",
        err_code: null,
        err_msg: null,
      },
    ],
    fills: [],
    degraded: false,
    audit_degraded: false,
    ...overrides,
  };
}

describe("OrdersList", () => {
  it("委託列顯示繁中狀態與買賣別", () => {
    render(<OrdersList view={view()} />);
    expect(screen.getByText("全部成交")).toBeTruthy();
    expect(screen.getByText("買")).toBeTruthy();
    expect(screen.getByText(/23000/)).toBeTruthy();
  });

  it("err_code 顯示於列", () => {
    const v = view();
    v.orders[0] = { ...v.orders[0]!, status_raw: "8", err_code: "-22", err_msg: "tick" };
    render(<OrdersList view={v} />);
    expect(screen.getByText(/-22/)).toBeTruthy();
  });

  it("degraded 顯示回報中斷警示", () => {
    render(<OrdersList view={view({ degraded: true })} />);
    expect(screen.getByText(/回報連線中斷/)).toBeTruthy();
  });

  it("audit_degraded 顯示審計異常警示", () => {
    render(<OrdersList view={view({ audit_degraded: true })} />);
    expect(screen.getByText(/審計記錄異常/)).toBeTruthy();
  });

  it("無資料顯示空狀態", () => {
    render(<OrdersList view={view({ orders: [], fills: [] })} />);
    expect(screen.getByText(/尚無委託/)).toBeTruthy();
  });
});
