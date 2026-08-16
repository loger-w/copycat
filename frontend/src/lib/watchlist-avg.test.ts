import { describe, expect, it } from "vitest";

import { groupAvgPct } from "@/lib/watchlist-avg";

const q = (p: number | null, chg_pct: number | null, trial = false) => ({ p, chg_pct, trial });

describe("groupAvgPct(batch2 R6 SC-4:群組等權平均漲幅)", () => {
  it("等權平均;p==null(含只有 ref 的盤前檔)與 chg_pct==null 不入分母;n/total 分開回報", () => {
    // E:p==null 但 chg_pct 有值(review A2:後端若對 ref 算 0.00 的未來形)—— 仍不入分母
    const quotes = {
      A: q(100_000, 2),
      B: q(200_000, -1),
      C: q(null, null),
      D: q(300_000, null),
      E: q(null, 0),
    };
    expect(groupAvgPct(["A", "B", "C", "D", "E"], quotes)).toEqual({
      avg: 0.5,
      n: 2,
      total: 5,
      trial: 0,
    });
  });
  it("缺 quote 的代碼跳過;全組無成交 → null(呼叫端不渲染)", () => {
    expect(groupAvgPct(["X", "C"], { C: q(null, null) })).toBeNull();
    expect(groupAvgPct([], {})).toBeNull();
  });
  it("單檔群組 = 該檔本身;試撮檔計入 trial 數(review C3)", () => {
    expect(groupAvgPct(["A"], { A: q(1, -3.25, true) })).toEqual({
      avg: -3.25,
      n: 1,
      total: 1,
      trial: 1,
    });
  });
});
