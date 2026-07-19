/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderConfirm } from "@/components/OrderConfirm";
import type { OrderPreviewResult } from "@/types";

afterEach(cleanup);

const PREVIEW: OrderPreviewResult = {
  preview_id: "pv1",
  request_id: "rq1",
  param: {
    Symbol: "TC.O.TWF.TXO.202607.C.23000",
    BrokerID: "SIM",
    Account: "9999000",
    Side: "1",
    OrderType: "2",
    TimeInForce: "1",
    Price: "15.5",
    OrderQty: "2",
    PositionEffect: "4",
  },
  account_masked: "****9000",
  mode: "sim",
};

describe("OrderConfirm", () => {
  it("顯示 param 摘要與模擬徽章", () => {
    render(
      <OrderConfirm
        preview={PREVIEW}
        submitting={false}
        errorText={null}
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(screen.getByText(/23000/)).toBeTruthy();
    expect(screen.getByText("買")).toBeTruthy();
    expect(screen.getByText("15.5")).toBeTruthy();
    expect(screen.getByText("模擬")).toBeTruthy();
    expect(screen.getByText("****9000")).toBeTruthy();
  });

  it("確認送出觸發 onConfirm,取消觸發 onCancel", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <OrderConfirm
        preview={PREVIEW}
        submitting={false}
        errorText={null}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByText("確認送出"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("取消"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("submitting 時確認鈕 disabled", () => {
    render(
      <OrderConfirm
        preview={PREVIEW}
        submitting={true}
        errorText={null}
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );
    const btn = screen.getByText(/送出中|確認送出/).closest("button");
    expect(btn?.getAttribute("disabled")).not.toBeNull();
  });

  it("errorText 以繁中顯示", () => {
    render(
      <OrderConfirm
        preview={PREVIEW}
        submitting={false}
        errorText="券商拒單(-22)"
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(screen.getByText(/券商拒單/)).toBeTruthy();
  });
});
