import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { RIVER_FILLS, RIVER_STROKES, RIVER_TEXTS } from "./river-colors";

/** 江波圖調色盤:腿數依設定檔(2026-08-26 F4 起十一腿),末幾腿不得取模撞回前面的腿色。 */
describe("river-colors", () => {
  it("三組調色盤長度一致且至少 11 組(F4 加 VIX / 原油 / 黃金 / 台積電)", () => {
    expect(RIVER_STROKES.length).toBe(RIVER_FILLS.length);
    expect(RIVER_STROKES.length).toBe(RIVER_TEXTS.length);
    expect(RIVER_STROKES.length).toBeGreaterThanOrEqual(11);
  });

  it("每一組都是 Tailwind 可靜態掃描的字面值 *-river-N,序號自 1 連續", () => {
    // 動態拼接 `stroke-river-${i}` 會讓 Tailwind v4 掃不到 → utility 不產生、線靜默無色。
    // 這裡的 expected 字串是**測試側**現算的,不是元件側拼出來的,故不牴觸上面那條。
    RIVER_STROKES.forEach((cls, i) => expect(cls).toBe(`stroke-river-${i + 1}`));
    RIVER_FILLS.forEach((cls, i) => expect(cls).toBe(`fill-river-${i + 1}`));
    RIVER_TEXTS.forEach((cls, i) => expect(cls).toBe(`text-river-${i + 1}`));
  });

  it("三組內各自不重複(重複 = 兩條腿同 class,畫面上分不出是哪一條)", () => {
    [RIVER_STROKES, RIVER_FILLS, RIVER_TEXTS].forEach((arr) => {
      expect(new Set(arr).size).toBe(arr.length);
    });
  });

  it("每個序位在 index.css @theme 都有 --color-river-N token(缺 token = utility 不會被產生,線靜默無色)", () => {
    const css = readFileSync(new URL("../../index.css", import.meta.url), "utf8");
    RIVER_STROKES.forEach((_cls, i) => {
      expect(css, `--color-river-${i + 1} 缺席`).toContain(`--color-river-${i + 1}:`);
    });
  });

  it("腿色兩兩不同值(token 撞值 = class 不同但畫出來同一色)", () => {
    const css = readFileSync(new URL("../../index.css", import.meta.url), "utf8");
    const values = RIVER_STROKES.map((_cls, i) => {
      const matched = new RegExp(`--color-river-${i + 1}:\\s*(#[0-9a-fA-F]{3,8})`).exec(css);
      expect(matched, `--color-river-${i + 1} 取不到色值`).not.toBeNull();
      return matched![1]!.toLowerCase();
    });
    expect(new Set(values).size).toBe(values.length);
  });
});
