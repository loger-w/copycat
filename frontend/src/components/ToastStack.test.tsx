/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastStack } from "@/components/ToastStack";
import type { SignalToast } from "@/hooks/useSignalAlerts";
import type { SignalMsg } from "@/lib/signal-model";

afterEach(cleanup);

function sig(id: string): SignalMsg {
  return {
    type: "signal",
    id,
    kind: "limit_lock",
    code: "2330",
    name: "台積電",
    price: 1_050_000,
    time: "09:31:22",
    levels: [],
    direction: "up",
    pct: null,
    touch_count: 1,
  };
}

function toast(i: number): SignalToast {
  const s = sig(`id${i}`);
  // items 是合併後的欄位(ToastStack 純展示 text,不讀它)
  return { key: `k${i}`, sig: s, items: [s], text: `訊號 ${i}` };
}

describe("ToastStack", () => {
  it("渲染 4 則 + 溢出計數 +3", () => {
    render(
      <ToastStack toasts={[toast(1), toast(2), toast(3), toast(4)]} overflow={3} onDismiss={vi.fn()} />,
    );
    for (const i of [1, 2, 3, 4]) expect(screen.getByText(`訊號 ${i}`)).toBeTruthy();
    expect(screen.getByText("+3")).toBeTruthy();
  });

  it("溢出 0 時不出現計數列", () => {
    render(<ToastStack toasts={[toast(1)]} overflow={0} onDismiss={vi.fn()} />);
    expect(screen.queryByText("+0")).toBeNull();
  });

  it("點擊該則 → onDismiss 帶該則的 key", () => {
    const onDismiss = vi.fn();
    render(<ToastStack toasts={[toast(1), toast(2)]} overflow={0} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByText("訊號 2"));
    expect(onDismiss.mock.calls).toEqual([["k2"]]);
  });

  it("無 toast 且無溢出 → 不佔 DOM", () => {
    const { container } = render(<ToastStack toasts={[]} overflow={0} onDismiss={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });
});

// 🔴 N013:合併 toast 的文案是「代號 名稱 <kind 段以「・」串接> 價格」,同一 tick 併進
// 三四則時會長到把 w-72 的卡片撐成一整片。比照 B3(SignalRail 合併列)clamp 2 行 +
// 斷詞;**只加 class,文案與 TTL / 合併行為一字不動**(user 拍板不改合併)。
describe("ToastStack 長文案 clamp(N013)", () => {
  it("toast 文字 clamp 2 行且可斷詞", () => {
    render(<ToastStack toasts={[toast(1)]} overflow={0} onDismiss={vi.fn()} />);
    const btn = screen.getByText("訊號 1");
    expect(btn.className).toContain("line-clamp-2");
    expect(btn.className).toContain("break-words");
  });

  it("容器寬度不變(w-72;clamp 是縱向的事)", () => {
    render(<ToastStack toasts={[toast(1)]} overflow={0} onDismiss={vi.fn()} />);
    expect(screen.getByTestId("toast-stack").className).toContain("w-72");
  });
});
