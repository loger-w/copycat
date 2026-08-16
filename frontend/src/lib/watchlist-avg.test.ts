import { describe, expect, it } from "vitest";

import { groupAvgPct } from "@/lib/watchlist-avg";

const q = (p: number | null, chg_pct: number | null) => ({ p, chg_pct });

describe("groupAvgPct(batch2 R6 SC-4:群組等權平均漲幅)", () => {
  it("等權平均;p==null(含只有 ref 的盤前檔)與 chg_pct==null 不入分母", () => {
    const quotes = { A: q(100_000, 2), B: q(200_000, -1), C: q(null, null), D: q(300_000, null) };
    expect(groupAvgPct(["A", "B", "C", "D"], quotes)).toBe(0.5);
  });
  it("缺 quote 的代碼跳過;全組無成交 → null(呼叫端不渲染)", () => {
    expect(groupAvgPct(["X", "C"], { C: q(null, null) })).toBeNull();
    expect(groupAvgPct([], {})).toBeNull();
  });
  it("單檔群組 = 該檔本身", () => {
    expect(groupAvgPct(["A"], { A: q(1, -3.25) })).toBe(-3.25);
  });
});
