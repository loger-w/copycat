/** 江波圖腿配色:**依腿序位**指派,不綁 leg key。
 *
 * 腿清單走 `configs/correlation.json`(realtime-correlation SC-8:加第七腿只改設定檔),
 * 所以顏色不能寫成 `{TXF: ..., TWN: ...}` 對照表 —— 那會讓新腿沒有顏色。序位 0 = base 腿
 * (重疊圖畫粗線)。腿數超過調色盤時取模循環。
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
] as const;

export const RIVER_FILLS = [
  "fill-river-1",
  "fill-river-2",
  "fill-river-3",
  "fill-river-4",
  "fill-river-5",
  "fill-river-6",
] as const;

export const RIVER_TEXTS = [
  "text-river-1",
  "text-river-2",
  "text-river-3",
  "text-river-4",
  "text-river-5",
  "text-river-6",
] as const;
