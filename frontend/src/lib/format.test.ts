import { describe, expect, it } from "vitest";

import { formatNtd, formatPts } from "@/lib/format";

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
