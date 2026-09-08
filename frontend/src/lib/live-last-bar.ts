import type { Bar } from "@/lib/candle";
import type { MinuteAgg } from "@/lib/stock-accum";

/** 即時末根(CONTEXT.md;spec #214):拿 `StockAccum` 折出的逐筆資料,蓋在**正式 K 棒**之後補到現在。
 *
 *  純函式、零 React、不讀時鐘 / 日曆 —— `today` / `nowMinute` 由呼叫端給(`StockChart`);
 *  期貨 / 加權下一批接線時原料不同(期貨無當日高低、加權無量),但「補在正式末根之後、正式到了讓位」
 *  的形狀相同,規則表在 `live-last-bar.test.ts`。
 *
 *  **兩把時間尺**(CLAUDE.md §4「台指期疊線分鐘鍵 = 1K 終點標記 −1 分」的反向):accum 的分鐘 key 是
 *  **起點分**(tick 時刻的 `HH*60+MM`,`stock-accum.ts::minuteKey`),TC4 1K 的 `t` 是**終點標記**
 *  (09:00:xx 的成交屬 09:01 那根;`candle.ts` 檔頭)。這裡 `+1` 對齊;方向相反、且只有這邊有 13:30 上限,
 *  所以刻意不與疊線那支共用 helper。 */

/** 1K 終點標記的分鐘域(台北):首根 09:01、末根 13:30(`stock_source.py` 分鐘域 0901–1330 inclusive)。
 *  收盤撮合 13:30:00 那筆在 accum 落在起點分 13:30(→ 終點 13:31,不存在),併進 13:30 那根。 */
const FIRST_BAR_MIN = 9 * 60 + 1;
const LAST_BAR_MIN = 13 * 60 + 30;

function stampOf(date: string, minute: number): string {
  const h = Math.floor(minute / 60);
  const m = minute % 60;
  return `${date} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** `YYYY-MM-DD HH:MM` → (date, 終點分);日 K 時戳(無空白)→ minute null。 */
function splitStamp(t: string): { date: string; minute: number | null } {
  const sp = t.indexOf(" ");
  if (sp < 0) return { date: t, minute: null };
  const hh = Number(t.slice(sp + 1, sp + 3));
  const mm = Number(t.slice(sp + 4, sp + 6));
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return { date: t.slice(0, sp), minute: null };
  return { date: t.slice(0, sp), minute: hh * 60 + mm };
}

/** accum 起點分 → 1K 終點標記分;域外回 null(09:01 以前 = 試撮殘留,後端本就丟、這裡防禦)。 */
function barMinuteOf(accumMinute: number): number | null {
  const end = Math.min(accumMinute + 1, LAST_BAR_MIN);
  return end < FIRST_BAR_MIN ? null : end;
}

/** 分 K:正式 1 分 K `official` 之後、到 `nowMinute`(起點分,含)為止的分鐘,由 `minutes` 補成 1 分 bar。
 *
 *  - 只補 `t` 嚴格晚於正式末根(且末根日期 = `today`)的分鐘;正式末根不是今天 → 從最早的分鐘補起。
 *  - 補的 bar:`o` = 前一根(正式或已補)的 `c`(前端沒記每分鐘首筆;最多 90 s 後被正式版換掉);
 *    `h` / `l` null → `c`;`uv` / `dv` = 分鐘外 / 內盤量(恆給欄:與既有 1K 同形,聚合桶才不會在
 *    「全缺」與「部分缺」之間漂)。
 *  - 起點分 > `nowMinute` 的分鐘忽略(時鐘倒退防禦)。
 *  - 正式段元素 identity 保留、傳入 array 不改;恆回新 array。 */
export function mergeLiveMinuteBars(
  official: readonly Bar[],
  minutes: ReadonlyMap<number, MinuteAgg>,
  today: string,
  nowMinute: number,
): Bar[] {
  const out: Bar[] = [...official];
  const last = official[official.length - 1];
  let afterMinute = -1;
  if (last !== undefined) {
    const { date, minute } = splitStamp(last.t);
    if (date === today && minute !== null) afterMinute = minute;
  }
  let prevClose = last?.c ?? null;
  const keys = [...minutes.keys()].filter((m) => m <= nowMinute).sort((a, b) => a - b);
  // `null as Bar | null`:字面 `= null` 會被 TS 窄成 `null`,迴圈內的 spread 就成了 never(TS2698)
  let cur = null as Bar | null;
  for (const m of keys) {
    const endMin = barMinuteOf(m);
    if (endMin === null || endMin <= afterMinute) continue;
    const a = minutes.get(m)!;
    const h = a.h ?? a.c;
    const l = a.l ?? a.c;
    if (cur !== null && cur.t === stampOf(today, endMin)) {
      // 13:29 / 13:30 併根:h / l / 量合併、c 取後者
      cur = {
        ...cur,
        h: Math.max(cur.h, h),
        l: Math.min(cur.l, l),
        c: a.c,
        v: cur.v + a.v,
        uv: (cur.uv ?? 0) + a.o,
        dv: (cur.dv ?? 0) + a.i,
      };
      out[out.length - 1] = cur;
      prevClose = a.c;
      continue;
    }
    cur = { t: stampOf(today, endMin), o: prevClose ?? a.c, h, l, c: a.c, v: a.v, uv: a.o, dv: a.i };
    out.push(cur);
    prevClose = a.c;
  }
  return out;
}
