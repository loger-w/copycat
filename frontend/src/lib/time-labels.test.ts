import { describe, expect, it } from "vitest";

import { SPOT_WINDOW, STKFUT_WINDOW } from "@/lib/stock-intraday-svg";
import { hhmm, HOUR_TICKS, hourTicksOf } from "@/lib/time-labels";

describe("hhmm", () => {
  it("台北分鐘數 → HH:MM(補零)", () => {
    expect(hhmm(525)).toBe("08:45");
    expect(hhmm(540)).toBe("09:00");
    expect(hhmm(825)).toBe("13:45");
  });
});

// 🟢 SC-5 / D9:整點刻度改由窗算,不再是全域常數陣列。
describe("hourTicksOf(D9)", () => {
  it("現貨窗逐值等於既有 HOUR_TICKS(index 頁與個股頁呼叫端零改)", () => {
    expect(hourTicksOf(SPOT_WINDOW)).toEqual([...HOUR_TICKS]);
    // 既有常數本身不得被順手改動 —— 大盤分時圖仍直接吃它
    expect(HOUR_TICKS.map((t) => t.minute)).toEqual([540, 600, 660, 720, 780]);
  });

  it("期貨窗 08:45–13:45:整點刻度 09:00–13:00,非整點的兩端不出現", () => {
    expect(hourTicksOf(STKFUT_WINDOW).map((t) => t.minute)).toEqual([540, 600, 660, 720, 780]);
    const labels = hourTicksOf(STKFUT_WINDOW).map((t) => t.label);
    expect(labels).not.toContain("08:45");
    expect(labels).not.toContain("13:45");
    // 08:45 起算的那 15 分鐘沒有整點可標,但 13:00 這格必須在(窗變長不該掉刻度)
    expect(labels).toContain("13:00");
  });

  it("窗端點恰為整點 → 兩端皆含(邊界用 ≤ 不是 <)", () => {
    expect(hourTicksOf({ start: 540, end: 840 }).map((t) => t.minute)).toEqual([
      540, 600, 660, 720, 780, 840,
    ]);
  });

  it("label 恆為 hhmm(minute)(顯示與定位同源)", () => {
    for (const t of hourTicksOf(STKFUT_WINDOW)) expect(t.label).toBe(hhmm(t.minute));
  });

  it("窗內無整點 → 空陣列(不硬塞刻度)", () => {
    expect(hourTicksOf({ start: 541, end: 559 })).toEqual([]);
  });
});
