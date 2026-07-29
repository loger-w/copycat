/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CorrPanel, windowLabel } from "@/components/corr/CorrPanel";
import type { CorrState } from "@/types";

afterEach(cleanup);

function state(over: Partial<CorrState> = {}): CorrState {
  return {
    type: "corr",
    seq: 12,
    session: "night",
    base: "TXF",
    windows: [60, 300, 1800],
    legs: {
      TXF: { label: "台指", mid: 40_400_000, stale: false },
      TWN: { label: "富台", mid: 3_417_750, stale: false },
      SXF: { label: "費半", mid: 10_760_000, stale: false },
    },
    pairs: {
      TWN: { w60: 0.8234, n60: 59, w300: -0.7512, n300: 299, w1800: null, n1800: 120 },
      SXF: { w60: 0.4, n60: 45, w300: null, n300: 60, w1800: null, n1800: 60 },
    },
    ...over,
  };
}

describe("windowLabel(窗長 → 表頭)", () => {
  it("秒換算分鐘", () => {
    expect(windowLabel(60)).toBe("1分");
    expect(windowLabel(300)).toBe("5分");
    expect(windowLabel(1800)).toBe("30分");
  });

  it("不足一分鐘用秒", () => {
    expect(windowLabel(30)).toBe("30秒");
  });
});

describe("CorrPanel(SC-7)", () => {
  it("首欄為標的繁中名稱,base 腿不列為配對", () => {
    const { container } = render(<CorrPanel state={state()} wsStatus="open" />);

    const rows = container.querySelectorAll("tbody tr");
    const firstCells = Array.from(rows).map((r) => r.querySelector("td")?.textContent);
    // 台指是基準腿,不與自己配對 → 表格列只有其餘兩腿
    expect(firstCells).toEqual(["富台", "費半"]);
  });

  it("表頭為 1分 / 5分 / 30分", () => {
    render(<CorrPanel state={state()} wsStatus="open" />);

    expect(screen.getByText("1分")).toBeTruthy();
    expect(screen.getByText("5分")).toBeTruthy();
    expect(screen.getByText("30分")).toBeTruthy();
  });

  it("數值兩位小數,負值保留負號", () => {
    render(<CorrPanel state={state()} wsStatus="open" />);

    expect(screen.getByText("0.82")).toBeTruthy();
    expect(screen.getByText("-0.75")).toBeTruthy();
  });

  it("樣本不足的窗顯示破折號而非 0", () => {
    render(<CorrPanel state={state()} wsStatus="open" />);

    // TWN 的 w1800 與 SXF 的 w300/w1800 皆為 null → 三個破折號
    expect(screen.getAllByText("—").length).toBe(3);
  });

  it("stale 的腿標記出來", () => {
    const s = state();
    s.legs["SXF"] = { label: "費半", mid: null, stale: true };
    const { container } = render(<CorrPanel state={s} wsStatus="open" />);

    const row = screen.getByText("費半").closest("tr");
    expect(row).toBeTruthy();
    expect(row!.getAttribute("data-stale")).toBe("true");
    expect(container.textContent).toContain("費半");
  });

  it("state 為 null 時顯示載入中,不崩潰", () => {
    render(<CorrPanel state={null} wsStatus="connecting" />);
    expect(screen.getByText(/載入中/).textContent).toBeTruthy();
  });

  it("斷線時顯示連線狀態", () => {
    render(<CorrPanel state={state()} wsStatus="closed" />);
    expect(screen.getByText(/斷線|重連/)).toBeTruthy();
  });

  it("基準腿名稱顯示在標題(說明是對誰的相關)", () => {
    render(<CorrPanel state={state()} wsStatus="open" />);
    expect(screen.getByText(/台指/)).toBeTruthy();
  });
});
