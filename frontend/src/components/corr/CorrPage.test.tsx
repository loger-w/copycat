/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CorrPage from "@/components/corr/CorrPage";
import * as hook from "@/hooks/useCorrelation";
import type { CorrState } from "@/types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const STATE: CorrState = {
  type: "corr",
  seq: 3,
  session: "night",
  base: "TXF",
  windows: [60],
  legs: {
    TXF: { label: "台指", mid: 40_400_000, stale: false },
    SXF: { label: "費半", mid: 10_760_000, stale: false },
  },
  pairs: { SXF: { w60: 0.66, n60: 59 } },
};

describe("CorrPage", () => {
  it("把 hook 的 state 傳進面板", () => {
    vi.spyOn(hook, "useCorrelation").mockReturnValue({ state: STATE, wsStatus: "open" });

    render(<CorrPage />);

    expect(screen.getByText("費半")).toBeTruthy();
    expect(screen.getByText("0.66")).toBeTruthy();
  });

  it("hook 尚未取得資料時顯示載入中", () => {
    vi.spyOn(hook, "useCorrelation").mockReturnValue({ state: null, wsStatus: "connecting" });

    render(<CorrPage />);

    expect(screen.getByText(/載入中/)).toBeTruthy();
  });
});
