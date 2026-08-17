import { describe, expect, it } from "vitest";

import { RIVER_FILLS, RIVER_STROKES, RIVER_TEXTS } from "./river-colors";

/** 江波圖調色盤:腿數依設定檔(2026-08-17 起七腿含小日經),第 7 腿不得取模撞回 base 近白色。 */
describe("river-colors", () => {
  it("三組調色盤長度一致且至少 7 組(第七腿小日經)", () => {
    expect(RIVER_STROKES.length).toBe(RIVER_FILLS.length);
    expect(RIVER_STROKES.length).toBe(RIVER_TEXTS.length);
    expect(RIVER_STROKES.length).toBeGreaterThanOrEqual(7);
  });

  it("第 7 組是 Tailwind 可靜態掃描的字面值 *-river-7", () => {
    expect(RIVER_STROKES[6]).toBe("stroke-river-7");
    expect(RIVER_FILLS[6]).toBe("fill-river-7");
    expect(RIVER_TEXTS[6]).toBe("text-river-7");
  });

  it("前六組不動(白名單 W3)", () => {
    expect(RIVER_STROKES.slice(0, 6)).toEqual([
      "stroke-river-1",
      "stroke-river-2",
      "stroke-river-3",
      "stroke-river-4",
      "stroke-river-5",
      "stroke-river-6",
    ]);
  });
});
