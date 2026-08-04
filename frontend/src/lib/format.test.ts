import { describe, expect, it } from "vitest";

import { chgPct, fmtPct, formatNtd, formatPts } from "@/lib/format";

describe("formatNtd", () => {
  it("億級縮寫", () => {
    expect(formatNtd(45_050_126)).toBe("NT$ 4,505萬");
    expect(formatNtd(3_054_064_316)).toBe("NT$ 30.54億");
  });
  it("負值帶號", () => {
    expect(formatNtd(-1_852_600)).toBe("-NT$ 185萬");
  });
  it("萬以下千分位", () => {
    expect(formatNtd(9_500)).toBe("NT$ 9,500");
    expect(formatNtd(0)).toBe("NT$ 0");
  });
});

describe("formatPts", () => {
  it("整數點位千分位", () => {
    expect(formatPts(43513)).toBe("43,513");
  });
  it("小數保留一位", () => {
    expect(formatPts(44300.4)).toBe("44,300.4");
  });
});

describe("fmtPct", () => {
  it("正值帶 +,負值帶 -", () => {
    expect(fmtPct(1)).toBe("+1.00%");
    expect(fmtPct(-1)).toBe("-1.00%");
  });
  it("平盤不帶號", () => {
    // `v > 0` 而非 `v >= 0` —— 0 走的是「不帶號」分支,原本全 repo 零正向斷言。
    expect(fmtPct(0)).toBe("0.00%");
  });
});

describe("chgPct", () => {
  it("相對參考價的漲跌百分比", () => {
    expect(chgPct(40_400_000, 40_000_000)).toBeCloseTo(1);
  });
});
