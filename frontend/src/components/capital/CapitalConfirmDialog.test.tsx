/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapitalConfirmDialog } from "@/components/capital/CapitalConfirmDialog";

afterEach(cleanup);

describe("CapitalConfirmDialog", () => {
  it("渲染標題/明細列/確認/取消,點擊觸發 callbacks", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <CapitalConfirmDialog
        title="確認刪單"
        rows={[
          { label: "代號", value: "2330 台積電" },
          { label: "動作", value: "刪單" },
        ]}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText("確認刪單")).toBeTruthy();
    expect(screen.getByText("代號")).toBeTruthy();
    expect(screen.getByText("2330 台積電")).toBeTruthy();
    expect(screen.getByText("動作")).toBeTruthy();
    fireEvent.click(screen.getByText("確認"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("取消"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("danger 時標題列紅底(bg-loss),預設無", () => {
    const noop = (): void => undefined;
    const { rerender } = render(
      <CapitalConfirmDialog title="確認平倉" rows={[]} danger onConfirm={noop} onCancel={noop} />,
    );
    expect(screen.getByText("確認平倉").closest("div")?.className).toContain("bg-loss");
    rerender(
      <CapitalConfirmDialog title="確認平倉" rows={[]} onConfirm={noop} onCancel={noop} />,
    );
    expect(screen.getByText("確認平倉").closest("div")?.className).not.toContain("bg-loss");
  });
});
