/**
 * 三支日 K hook(`useFuturesBars` / `useMarketBars` / `useStockBars`)跨日測試共用的鷹架
 * (refactor/w3-b2-test-scaffolds;原三檔逐字三份,08-31 review S-F5)。
 *
 * 時間軸:D = 2026-08-05(週三)。D 當天回「D 部分 bar」快照(`D_SNAPSHOT`);D 14:00 起後端
 * `DAILY_FINAL_TIME` 定稿、今日那根換成完成值(`D_FINAL_SNAPSHOT`);D+1 起回「D 完成 + D+1 部分」
 * (`D1_SNAPSHOT`)。**Response 信封不在這裡**:`{key, tf, bars, meta}` 與 `{bars, status}` 是各 hook
 * 自己的 interface 事實,三檔各留信封 stub,只向這裡要料(含 `meta.partial_last` 的值,見 `partialLastAt`)。
 */
import { vi } from "vitest";

import type { Bar } from "@/lib/candle";
import { isoLocalDate } from "@/lib/trading-calendar";

/** D+1 的日曆日;`pastMidnight` 以 `isoLocalDate(now) >= D1_ISO` 判,與 hook 的日界同一把尺。 */
const D1_ISO = "2026-08-06";

/** D 09:00 時的快照:昨日完成 + 今日部分 bar。 */
export const D_SNAPSHOT: readonly Bar[] = [
  { t: "2026-08-04", o: 1, h: 3, l: 1, c: 2, v: 10 },
  { t: "2026-08-05", o: 2, h: 2, l: 2, c: 2, v: 1 }, // 09:00 時的部分 bar
];

/** D 14:00 定稿後的快照:今日那根換成完成值,尚無 D+1。 */
export const D_FINAL_SNAPSHOT: readonly Bar[] = [
  D_SNAPSHOT[0]!,
  { t: "2026-08-05", o: 2, h: 9, l: 1, c: 8, v: 99 },
];

/** D+1 起的快照:D 完成 + D+1 部分 bar。 */
export const D1_SNAPSHOT: readonly Bar[] = [
  { t: "2026-08-04", o: 1, h: 3, l: 1, c: 2, v: 10 },
  { t: "2026-08-05", o: 2, h: 9, l: 1, c: 8, v: 99 }, // D 完成
  { t: "2026-08-06", o: 8, h: 8, l: 8, c: 8, v: 1 },
];

/** 牆鐘已跨過 D 的午夜(在 D+1 或之後)。 */
export function pastMidnight(now: Date = new Date()): boolean {
  return isoLocalDate(now) >= D1_ISO;
}

/** 牆鐘已過當日 14:00 定稿界。14 是與後端 `DAILY_FINAL_TIME` 同值的**測試側字面值**(只看小時,同三檔原寫法);
 *  不受 CLAUDE.md §4 那條 parity 測試保護 —— 那條釘的是 `lib/day-bars-rollover.ts::DAILY_FINAL_TIME`,不是這裡。 */
function pastDailyFinal(now: Date = new Date()): boolean {
  return now.getHours() >= 14;
}

/** 三段牆鐘下後端 `meta.partial_last` 的值:D 14:00 前 true(今日那根仍在進行)、D 14:00 起 false(定稿)、
 *  D+1 起 true(D+1 那根又在進行)。與 `snapshotAtWithDailyFinal` 同一把尺;二段 stub 用不到(恆 `META` 原值)。 */
export function partialLastAt(now: Date = new Date()): boolean {
  return pastMidnight(now) || !pastDailyFinal(now);
}

/** 二段選料:D 當天恆回 `D_SNAPSHOT`(含 14:00 後),D+1 起回 `D1_SNAPSHOT`。 */
export function snapshotAt(now: Date = new Date()): readonly Bar[] {
  return pastMidnight(now) ? D1_SNAPSHOT : D_SNAPSHOT;
}

/** 三段選料(W2 T2 #206):D 14:00 前 `D_SNAPSHOT`、D 14:00 起 `D_FINAL_SNAPSHOT`、D+1 起 `D1_SNAPSHOT`。 */
export function snapshotAtWithDailyFinal(now: Date = new Date()): readonly Bar[] {
  if (pastMidnight(now)) return D1_SNAPSHOT;
  return pastDailyFinal(now) ? D_FINAL_SNAPSHOT : D_SNAPSHOT;
}

/**
 * 「D+1 起前 n 次請求走另一條路」的計數器:回 `() => boolean`,午夜前恆 false、午夜後前 `n` 次呼叫 true。
 * 「先失敗 n 發(503)」與「午夜那一發 200+空 bars」共用同一顆,差別只在 stub 對 true 回什麼。
 */
export function firstCallsAfterMidnight(n: number): () => boolean {
  let left = n;
  return () => {
    if (!pastMidnight() || left <= 0) return false;
    left -= 1;
    return true;
  };
}

/** 模擬圖表吃 WS 推播的重繪節奏:每 `everyMs` 一次 rerender、持續 `forMs`(fake timers 下推進)。 */
export async function rerenderBurst(
  rerender: (p: { tick: number }) => void,
  forMs: number,
  everyMs: number,
): Promise<void> {
  for (let t = 0; t < forMs; t += everyMs) {
    rerender({ tick: t });
    await vi.advanceTimersByTimeAsync(everyMs);
  }
}
