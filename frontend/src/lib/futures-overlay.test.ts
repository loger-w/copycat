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

/** 「圖錨在 08-22 這一節」→ 08-21 及更早才是已完成交易日。 */
const ANCHOR_0822 = "2026-08-22";

describe("buildFuturesOverlay — CDP(與 server/overlay.py::compute_cdp 同式)", () => {
  it("末根已完成 bar 的 H/L/C 決定五值,date = 該根日期", () => {
    const ov = buildFuturesOverlay([day("2026-08-20", 1, 1, 1), LAST], ANCHOR_0822);
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
    const ov = buildFuturesOverlay([day("2026-08-21", 1001, 1000, 1000)], ANCHOR_0822);
    expect(ov.cdp!.cdp).toBe(1000);
    expect(Number.isInteger(ov.cdp!.ah)).toBe(true);
  });

  it("錨定日當節的 bar 剔除(盤中未完成 bar 不得入計算),基準退到前一交易日", () => {
    const partial = day("2026-08-22", 99_000_000, 1, 50_000_000);
    const ov = buildFuturesOverlay(
      [day("2026-08-20", 1, 1, 1), LAST, partial],
      ANCHOR_0822,
    );
    expect(ov.date).toBe("2026-08-21");
    expect(ov.cdp!.cdp).toBe(23_000_000);
  });
});

// ---------------------------------------------------------------------------
// 基準日判準 = **圖上錨定日**(review P1)。舊判準 `meta.partial_last` 是**日曆日**
// 口徑(末根日期 == 今天),而近全軸一張圖橫跨兩個日曆日 —— 兩頭都會破窗,且 meta
// 缺欄位時 falsy = 不剔末根,失效落在**不安全側**。
// ---------------------------------------------------------------------------
describe("buildFuturesOverlay — 基準日以圖上錨定日為界(不信 partial_last)", () => {
  /** cdp = (23_100_000 + 22_900_000 + 46_000_000 + 2)//4 = 23_000_000 */
  const D19 = day("2026-08-19", 23_100_000, 22_900_000, 23_000_000);
  /** cdp = (22_100_000 + 21_900_000 + 44_000_000 + 2)//4 = 22_000_000 */
  const D20 = day("2026-08-20", 22_100_000, 21_900_000, 22_000_000);
  /** cdp = (21_100_000 + 20_900_000 + 42_000_000 + 2)//4 = 21_000_000 */
  const D21 = day("2026-08-21", 21_100_000, 20_900_000, 21_000_000);

  it("22:00 視角:TC4 把夜盤成形 bar 標成次一交易日 → 基準不得是那個未來日", () => {
    // 08-21 22:00 的圖(錨定日 08-21)。TC4 的日 K 末根已標成 08-22(夜盤成形),
    // 而後端 `partial_last`(末根日期 == 日曆今日 08-21)= false → 舊判準一根都不剔,
    // 基準會落在**尚未發生的交易日**上,而畫面只是幾條位置不對的線。
    const nightborn = day("2026-08-22", 99_000_000, 1, 50_000_000);
    const ov = buildFuturesOverlay([D19, D20, D21, nightborn], "2026-08-21");
    expect(ov.date).toBe("2026-08-20");
    expect(ov.cdp!.cdp).toBe(22_000_000);
  });

  it("00:00–05:00 視角:日曆日已翻頁但圖仍錨在前一日 → 基準不得是當前這一節", () => {
    // 牆上時鐘 08-22 01:00、圖的錨定日仍是 08-21。後端 `partial_last`(末根 08-21
    // == 日曆今日 08-22?)= false → 舊判準把**當前這一節自己的未完成 bar** 當昨日基準。
    const ov = buildFuturesOverlay([D19, D20, D21], "2026-08-21");
    expect(ov.date).toBe("2026-08-20");
    expect(ov.cdp!.cdp).toBe(22_000_000);
  });

  it("界是**嚴格小於**(對齊後端 build_overlay 的 `date < today`)", () => {
    expect(buildFuturesOverlay([D19, D20], "2026-08-20").date).toBe("2026-08-19");
    expect(buildFuturesOverlay([D19, D20], "2026-08-21").date).toBe("2026-08-20");
  });
});

describe("buildFuturesOverlay — MA(compute_ma:不足根數回 null;floor 平均)", () => {
  const closes = [10, 20, 30, 40, 51];
  const bars = closes.map((c, i) => day(`2026-08-1${i}`, c, c, c));

  it("5 根整 → ma5 = floor(151/5) = 30;不足 20 根 → ma20 null", () => {
    const ov = buildFuturesOverlay(bars, "2026-08-20");
    expect(ov.ma5).toBe(30);
    expect(ov.ma20).toBeNull();
  });

  it("只有 4 根已完成 → ma5 也是 null(錨定日當節那根不算一根)", () => {
    const ov = buildFuturesOverlay(bars, "2026-08-14");
    expect(ov.ma5).toBeNull();
  });

  it("ma5 只吃**最後** 5 根 close(不是全期間平均)", () => {
    const long = [1, 1, 1, 1, 1, 10, 20, 30, 40, 51].map((c, i) =>
      day(`2026-08-${String(i + 10)}`, c, c, c),
    );
    expect(buildFuturesOverlay(long, "2026-08-20").ma5).toBe(30);
  });
});

describe("buildFuturesOverlay — 空 / 壞資料一律回全 null(反灰,不猜)", () => {
  it("零根 → 全 null(date 也是 null)", () => {
    expect(buildFuturesOverlay([], ANCHOR_0822)).toEqual({
      cdp: null,
      ma5: null,
      ma20: null,
      date: null,
    });
  });

  it("只有錨定日當節那一根 → 剔除後空 → 全 null", () => {
    expect(buildFuturesOverlay([LAST], "2026-08-21").cdp).toBeNull();
  });

  it("c/h/l 有 0 的 bar 整根剔除(TC4 送 0 = 不可得,不是價)", () => {
    const zero = day("2026-08-22", 0, 0, 0);
    const ov = buildFuturesOverlay([LAST, zero], "2026-08-23");
    expect(ov.date).toBe("2026-08-21");
    expect(ov.cdp!.cdp).toBe(23_000_000);
  });
});
