import { vi } from "vitest";

import type { RiverState } from "@/types";

/** 江波圖兩支測試檔(`RiverPanel.test.tsx` 行為 / `RiverPanel.memo.test.tsx` 計次)共用的
 *  fixture。**必須共檔**:兩檔的斷言互相引用同一組數字(memo 檔的「台指 —」讀值列自檢
 *  依賴行為檔拍下的 hover 換算,`xAt` 的 960 又綁死 `RiverOverlay.SIZE`),各留一份的話
 *  改動只落在其中一邊時,另一邊會以「看起來很正常」的舊數字繼續綠。
 *
 *  `vi.mock` **不放這裡**:它是檔案級 + hoisted,memo 檔要 mock `@/lib/river-chart-svg`
 *  而行為檔要看真幾何數字,兩者不能共存(見 memo 檔檔頭)。 */

/** 日盤窗(08:45–13:45,分鐘序號)。`xAt` 的換算與重疊圖 x 軸同源。 */
export const DAY = { start_min: 525, end_min: 825 };

/** 三腿:台指(漲)/ 富台(跌)/ 道瓊(全窗無點)。`over` 讓行為檔覆寫 session 等欄位。 */
export function riverState(over: Partial<RiverState> = {}): RiverState {
  return {
    type: "river",
    seq: 3,
    session: "day",
    base: "TXF",
    window: DAY,
    legs: {
      TXF: {
        label: "台指",
        minutes: { "10": 40_000_000, "20": 40_400_000 },
        last: 40_400_000,
        last_minute: 20,
      },
      TWN: {
        label: "富台",
        minutes: { "10": 3_400_000, "20": 3_366_000 },
        last: 3_366_000,
        last_minute: 20,
      },
      YM: { label: "道瓊", minutes: {}, last: null, last_minute: null },
    },
    ...over,
  };
}

/** viewBox 寬 = 960(`RiverOverlay.SIZE`),量測寬取同值 → clientX 即 viewBox x。
 *  jsdom 的 rect 恆 0 會讓 `handleMouseMove` 早退(cursor 永遠 null = 假綠),非 spy 不可。 */
export function mockRect(): void {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0,
    top: 0,
    right: 960,
    bottom: 340,
    width: 960,
    height: 340,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect);
}

/** offset(分鐘)→ clientX。窗長 300 分、圖寬 960 → 每分鐘 3.2px。 */
export function xAt(offset: number): number {
  return (offset / (DAY.end_min - DAY.start_min)) * 960;
}
