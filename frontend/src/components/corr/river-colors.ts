/** 江波圖腿配色:**依腿序位**指派,不綁 leg key。
 *
 * 腿清單走 `configs/correlation.json`(realtime-correlation SC-8:加腿只改設定檔),
 * 所以顏色不能寫成 `{TXF: ..., TWN: ...}` 對照表 —— 那會讓新腿沒有顏色。序位 0 = base 腿
 * (重疊圖畫粗線)。腿數超過調色盤時取模循環(2026-08-26 F4 起十一腿:原七腿 + VIX /
 * 原油 / 黃金 / 台積電,調色盤同步補到 11 組,末四腿不再取模撞回 base 近白色與前三腿)。
 *
 * class 名必須是**原始碼裡的字面值**(Tailwind v4 掃描原始碼),故寫成常數陣列而非動態拼接。
 */

export const RIVER_STROKES = [
  "stroke-river-1",
  "stroke-river-2",
  "stroke-river-3",
  "stroke-river-4",
  "stroke-river-5",
  "stroke-river-6",
  "stroke-river-7",
  "stroke-river-8",
  "stroke-river-9",
  "stroke-river-10",
  "stroke-river-11",
] as const;

export const RIVER_FILLS = [
  "fill-river-1",
  "fill-river-2",
  "fill-river-3",
  "fill-river-4",
  "fill-river-5",
  "fill-river-6",
  "fill-river-7",
  "fill-river-8",
  "fill-river-9",
  "fill-river-10",
  "fill-river-11",
] as const;

export const RIVER_TEXTS = [
  "text-river-1",
  "text-river-2",
  "text-river-3",
  "text-river-4",
  "text-river-5",
  "text-river-6",
  "text-river-7",
  "text-river-8",
  "text-river-9",
  "text-river-10",
  "text-river-11",
] as const;
