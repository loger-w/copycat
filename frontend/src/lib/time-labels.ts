/** 台北分鐘數(自 00:00 起算)→ `HH:MM`。 */
export function hhmm(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

/** 日盤 X 軸整點刻度(09:00-13:00),個股分時與大盤分時共用同一組。 */
export const HOUR_TICKS: readonly { minute: number; label: string }[] = [
  540, 600, 660, 720, 780,
].map((m) => ({ minute: m, label: hhmm(m) }));
