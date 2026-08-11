/** @vitest-environment jsdom */
import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapitalConfirmDialog } from "@/components/capital/CapitalConfirmDialog";

afterEach(cleanup);

const noopCb = (): void => undefined;

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

  // ---- 原生 <dialog> 行為(SC-1..SC-4、SC-8;jsdom 走 fallback 分支:無 showModal)----

  it("以原生 <dialog> 開啟(tagName DIALOG + open attribute)", () => {
    render(
      <CapitalConfirmDialog title="確認刪單" rows={[]} onConfirm={noopCb} onCancel={noopCb} />,
    );
    const dlg = screen.getByRole("dialog");
    expect(dlg.tagName).toBe("DIALOG");
    expect(dlg.hasAttribute("open")).toBe(true);
  });

  it("Esc → onCancel 恰一次,onConfirm 零次", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <CapitalConfirmDialog title="確認刪單" rows={[]} onConfirm={onConfirm} onCancel={onCancel} />,
    );
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("初始 focus 落在取消鈕", () => {
    render(
      <CapitalConfirmDialog title="確認刪單" rows={[]} onConfirm={noopCb} onCancel={noopCb} />,
    );
    expect(document.activeElement).toBe(screen.getByText("取消"));
  });

  it("原生 close 事件(backstop)→ onCancel 恰一次", () => {
    const onCancel = vi.fn();
    render(
      <CapitalConfirmDialog title="確認刪單" rows={[]} onConfirm={noopCb} onCancel={onCancel} />,
    );
    fireEvent(screen.getByRole("dialog"), new Event("close"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("Esc 後補發原生 close(真瀏覽器雙路徑)去重,onCancel 仍恰一次", () => {
    const onCancel = vi.fn();
    render(
      <CapitalConfirmDialog title="確認刪單" rows={[]} onConfirm={noopCb} onCancel={onCancel} />,
    );
    const dlg = screen.getByRole("dialog");
    fireEvent.keyDown(dlg, { key: "Escape" });
    fireEvent(dlg, new Event("close"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("class 契約:m-auto / backdrop:bg-bg/85 / max-w-sm(display 不得被 author 層蓋寫)", () => {
    render(
      <CapitalConfirmDialog title="確認刪單" rows={[]} onConfirm={noopCb} onCancel={noopCb} />,
    );
    const dlg = screen.getByRole("dialog");
    expect(dlg.classList.contains("m-auto")).toBe(true);
    expect(dlg.classList.contains("backdrop:bg-bg/85")).toBe(true);
    expect(dlg.classList.contains("max-w-sm")).toBe(true);
  });

  it("focus 歸還:卸載後 activeElement 回到開窗前的觸發鈕", () => {
    function Harness({ open }: { open: boolean }) {
      return (
        <>
          <button type="button">觸發</button>
          {open && (
            <CapitalConfirmDialog
              title="確認刪單"
              rows={[]}
              onConfirm={noopCb}
              onCancel={noopCb}
            />
          )}
        </>
      );
    }
    const { rerender } = render(<Harness open={false} />);
    const trigger = screen.getByText("觸發");
    trigger.focus();
    rerender(<Harness open />);
    expect(document.activeElement).toBe(screen.getByText("取消"));
    rerender(<Harness open={false} />);
    expect(document.activeElement).toBe(trigger);
  });
});

// jsdom 26 的 HTMLDialogElement 只有 `open` 反射,無 showModal/close → 不能 vi.spyOn
// 不存在的方法,一律手動裝 prototype、afterEach 手動 delete 拆(不拆會讓上面 describe
// 的 fallback 分支語意漂移)。
describe("CapitalConfirmDialog(showModal 分支,手動裝 prototype stub)", () => {
  afterEach(() => {
    delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal;
    vi.restoreAllMocks();
  });

  it("StrictMode 雙輪不炸:showModal 恰一次(!open guard 的真正鎖),focus 兩次(生效自檢)", () => {
    // 模擬真瀏覽器語意:對已 open 元素重複 showModal 依標準拋 InvalidStateError。
    const showModal = vi.fn(function (this: HTMLDialogElement) {
      if (this.open) throw new DOMException("already open", "InvalidStateError");
      this.setAttribute("open", "");
    });
    HTMLDialogElement.prototype.showModal = showModal;
    // spy 釘在 HTMLButtonElement:cleanup 對非按鈕元素(body/opener)的還 focus 不計入,
    // 期望值 = StrictMode effect 兩輪各 focus 取消鈕一次 = 恰 2(兩個數字皆不可放寬)。
    const focusSpy = vi.spyOn(HTMLButtonElement.prototype, "focus");
    render(
      <StrictMode>
        <CapitalConfirmDialog title="確認刪單" rows={[]} onConfirm={noopCb} onCancel={noopCb} />
      </StrictMode>,
    );
    expect(showModal).toHaveBeenCalledTimes(1);
    expect(focusSpy).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("dialog").hasAttribute("open")).toBe(true);
  });
});
