/** @vitest-environment jsdom */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MetricsBar } from "@/components/MetricsBar";
import type { Snapshot } from "@/types";

afterEach(cleanup);

const SNAP: Snapshot = {
  series_id: "TX4.202607",
  series_name: "TX4 202607",
  status: "live",
  accumulated_from: "08:45:00",
  spot: { symbol: "TXF", price: 43735 },
  curve: [[43_000_000, 100]],
  beps: [43513, 44300.4],
  max_profit: { x: 44300, y: 45_050_126 },
  max_loss: { x: 41000, y: -3_054_064_316 },
  spot_pnl: 35_474_590,
  totals: {
    call_net_qty: -21_526,
    put_net_qty: -3_412,
    contracts_active: 118,
    ticks: 12_345,
    unclassified_ticks: 1_234,
    unclassified_qty: 2_000,
    overlap_risk_ticks: 0,
    dropped_foreign_ticks: 0,
    queue_dropped: 0,
  },
};

describe("MetricsBar", () => {
  it("關鍵指標格式化呈現", () => {
    render(<MetricsBar snapshot={SNAP} />);
    expect(screen.getByText("NT$ 4,505萬")).toBeTruthy(); // 最大獲利
    expect(screen.getByText("-NT$ 30.54億")).toBeTruthy(); // 最大虧損
    expect(screen.getByText("43,513 / 44,300.4")).toBeTruthy(); // BEP
    expect(screen.getByText("43,735")).toBeTruthy(); // 現價
    expect(screen.getByText("-21,526")).toBeTruthy(); // Call 淨口數
    expect(screen.getByText("90.0%")).toBeTruthy(); // 分類覆蓋率 (1 - 1234/12345)
  });

  it("無資料欄位顯示破折號", () => {
    render(<MetricsBar snapshot={{ ...SNAP, max_profit: null, beps: [], spot_pnl: null }} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("totals 缺失時口數/合約數/覆蓋率顯示破折號", () => {
    render(<MetricsBar snapshot={{ ...SNAP, totals: undefined }} />);
    for (const label of ["Call 淨口數", "Put 淨口數", "參與合約數", "分類覆蓋率"]) {
      expect(screen.getByText(label).nextElementSibling?.textContent).toBe("—");
    }
  });
});
