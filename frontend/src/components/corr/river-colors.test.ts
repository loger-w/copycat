import { readFileSync } from "node:fs";

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

  it("前六組不動(白名單 W3;三陣列皆鎖)", () => {
    const six = [1, 2, 3, 4, 5, 6];
    expect(RIVER_STROKES.slice(0, 6)).toEqual(six.map((i) => `stroke-river-${i}`));
    expect(RIVER_FILLS.slice(0, 6)).toEqual(six.map((i) => `fill-river-${i}`));
    expect(RIVER_TEXTS.slice(0, 6)).toEqual(six.map((i) => `text-river-${i}`));
  });

  it("每個序位在 index.css @theme 都有 --color-river-N token(缺 token = utility 不會被產生,線靜默無色)", () => {
    const css = readFileSync(new URL("../../index.css", import.meta.url), "utf8");
    RIVER_STROKES.forEach((_cls, i) => {
      expect(css, `--color-river-${i + 1} 缺席`).toContain(`--color-river-${i + 1}:`);
    });
  });
});
