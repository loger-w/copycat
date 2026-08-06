import type { XWindow } from "@/lib/stock-intraday-svg";

/** 台北分鐘數(自 00:00 起算)→ `HH:MM`。 */
export function hhmm(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

export interface HourTick {
  minute: number;
  label: string;
}

/** 日盤 X 軸整點刻度(09:00-13:00),個股分時與大盤分時共用同一組。
 *  = `hourTicksOf(SPOT_WINDOW)`(由 time-labels.test.ts 逐值鎖住),大盤分時仍直接吃它。 */
export const HOUR_TICKS: readonly HourTick[] = [540, 600, 660, 720, 780].map((m) => ({
  minute: m,
  label: hhmm(m),
}));

/** 窗內的整點刻度(D9)。個股期窗是 08:45–13:45,兩端都不是整點 —— 刻度只取窗內的
 *  整點(首個 ≥ start 的整點起、到 ≤ end 為止),不為了「有頭有尾」硬塞非整點標籤。
 *
 *  型別參數走 `XWindow` 而不是自己再寫一次 `{start, end}`:兩份結構型別各自漂移時,
 *  失效樣態是刻度算的窗與幾何算的窗不同一個 —— 線與刻度差幾 px,目視抓不到。 */
export function hourTicksOf(xw: XWindow): readonly HourTick[] {
  const ticks: HourTick[] = [];
  for (let m = Math.ceil(xw.start / 60) * 60; m <= xw.end; m += 60) {
    ticks.push({ minute: m, label: hhmm(m) });
  }
  return ticks;
}
