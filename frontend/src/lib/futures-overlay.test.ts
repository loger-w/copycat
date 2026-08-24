import { describe, expect, it } from "vitest";

import type { Bar } from "@/lib/candle";
import { buildFuturesOverlay } from "@/lib/futures-overlay";

/** 日 K bar(毫元)。分時的 uv/dv 在日 K 路徑不帶欄,這裡也不給。 */
function day(t: string, h: number, l: number, c: number): Bar {
  return { t, o: c, h, l, c, v: 100 };
}

/** 期望值一律**寫死字面量**,不由 import 的公式算回來(frontend-testing:同源同義反覆)。
 *  H=23_100_000 / L=22_900_000 / C=23_000_000 →
 *  cdp = (23_100_000 + 22_900_000 + 2×23_000_000 + 2) // 4 = 92_000_002 // 4 = 23_000_000
 *  spread = 200_000 → ah 23_200_000 / nh 2×23_000_000 − 22_900_000 = 23_100_000
 *  nl 2×23_000_000 − 23_100_000 = 22_900_000 / al 22_800_000 */
const LAST = day("2026-08-21", 23_100_000, 22_900_000, 23_000_000);

describe("buildFuturesOverlay — CDP(與 server/overlay.py::compute_cdp 逐式相同)", () => {
  it("末根已完成 bar 的 H/L/C 決定五值,date = 該根日期", () => {
    const ov = buildFuturesOverlay([day("2026-08-20", 1, 1, 1), LAST], false);
    expect(ov.cdp).toEqual({
      cdp: 23_000_000,
      ah: 23_200_000,
      nh: 23_100_000,
      nl: 22_900_000,
      al: 22_800_000,
    });
    expect(ov.date).toBe("2026-08-21");
  });

  it("cdp 是 round-half-up 的整數除((h+l+2c+2)//4),不留小數", () => {
    // H=1001 / L=1000 / C=1000 → (1001+1000+2000+2)//4 = 4003//4 = 1000
    const ov = buildFuturesOverlay([day("2026-08-21", 1001, 1000, 1000)], false);
    expect(ov.cdp!.cdp).toBe(1000);
    expect(Number.isInteger(ov.cdp!.ah)).toBe(true);
  });

  it("partial_last=true → 剔除末根(當日盤中 bar 不得入計算),基準退到前一交易日", () => {
    const partial = day("2026-08-22", 99_000_000, 1, 50_000_000);
    const ov = buildFuturesOverlay([day("2026-08-20", 1, 1, 1), LAST, partial], true);
    expect(ov.date).toBe("2026-08-21");
    expect(ov.cdp!.cdp).toBe(23_000_000);
  });
});

describe("buildFuturesOverlay — MA(compute_ma:不足根數回 null;floor 平均)", () => {
  const closes = [10, 20, 30, 40, 51];
  const bars = closes.map((c, i) => day(`2026-08-1${i}`, c, c, c));

  it("5 根整 → ma5 = floor(151/5) = 30;不足 20 根 → ma20 null", () => {
    const ov = buildFuturesOverlay(bars, false);
    expect(ov.ma5).toBe(30);
    expect(ov.ma20).toBeNull();
  });

  it("只有 4 根已完成 → ma5 也是 null(partial 末根不算一根)", () => {
    const ov = buildFuturesOverlay(bars, true);
    expect(ov.ma5).toBeNull();
  });

  it("ma5 只吃**最後** 5 根 close(不是全期間平均)", () => {
    const long = [1, 1, 1, 1, 1, 10, 20, 30, 40, 51].map((c, i) =>
      day(`2026-08-${String(i + 10)}`, c, c, c),
    );
    expect(buildFuturesOverlay(long, false).ma5).toBe(30);
  });
});

describe("buildFuturesOverlay — 空 / 壞資料一律回全 null(反灰,不猜)", () => {
  it("零根 → 全 null(date 也是 null)", () => {
    expect(buildFuturesOverlay([], false)).toEqual({
      cdp: null,
      ma5: null,
      ma20: null,
      date: null,
    });
  });

  it("只有一根 partial → 剔除後空 → 全 null", () => {
    expect(buildFuturesOverlay([LAST], true).cdp).toBeNull();
  });

  it("c/h/l 有 0 的 bar 整根剔除(TC4 送 0 = 不可得,不是價)", () => {
    const zero = day("2026-08-22", 0, 0, 0);
    const ov = buildFuturesOverlay([LAST, zero], false);
    expect(ov.date).toBe("2026-08-21");
    expect(ov.cdp!.cdp).toBe(23_000_000);
  });
});
