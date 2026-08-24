import { describe, expect, it } from "vitest";

import { otcSourceDead, type SourceLiveness } from "@/lib/index-source-health";

function series(over: Partial<SourceLiveness> = {}): SourceLiveness {
  return { p: null, minutes: {}, ...over };
}

function mins(n: number): Record<string, number> {
  return Object.fromEntries(
    Array.from({ length: n }, (_, i) => [String(901 + i).padStart(4, "0"), 43_000_000]),
  );
}

describe("otcSourceDead(N108)", () => {
  it("盤前兩者皆空 → false(不誤報)", () => {
    expect(otcSourceDead(series(), series())).toBe(false);
  });

  it("任一邊尚未有 series(null)→ false", () => {
    expect(otcSourceDead(null, series())).toBe(false);
    expect(otcSourceDead(series({ minutes: mins(5) }), null)).toBe(false);
  });

  // 寬限邊界:1 格 = 還在等 MIS 的 5s poll,2 格 = 開始判死。門檻寫**字面量**
  // (不由 import 的 `OTC_DEAD_MIN_TWSE_MINUTES` 算回來)—— 同源算回來是同義反覆,
  // 門檻 2→3 的 mutant 照樣全綠。
  it("加權 1 格(寬限內)→ false;2 格(門檻)→ true", () => {
    expect(otcSourceDead(series({ minutes: mins(1) }), series())).toBe(false);
    expect(otcSourceDead(series({ minutes: mins(2) }), series())).toBe(true);
    expect(otcSourceDead(series({ minutes: mins(3) }), series())).toBe(true);
  });

  it("櫃買有現價 → false(即使一格都還沒折出來)", () => {
    expect(otcSourceDead(series({ minutes: mins(9) }), series({ p: 359_800 }))).toBe(false);
  });

  it("櫃買有分鐘格 → false(即使現價暫缺)", () => {
    expect(otcSourceDead(series({ minutes: mins(9) }), series({ minutes: mins(1) }))).toBe(false);
  });
});
