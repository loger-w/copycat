import type { IndexSeries } from "@/hooks/useIndexStream";
import type { MinuteAgg, StockAccum } from "@/lib/stock-accum";
import { SPOT_WINDOW } from "@/lib/stock-intraday-svg";

/** 指數序列 → `StockAccum`,讓台股綜合的加權 / 櫃買分時圖直接吃個股同一份
 *  `IntradayChartCore`(mode="index";R4 D11)。
 *
 *  指數沒有成交量,這裡填的每一個「假值」都是為了讓 core 的既有幾何在 index 態產出
 *  **正確語意**,不是佔位:
 *  - `v = 1`:`buildIntradayGeometry` 的 vwapLine 以 `c × v` 加權,等權後就是**分鐘收盤
 *    算術平均** —— 與舊 `MarketChart` 自繪的均價線同一定義(v = 0 會讓均價線整條消失)。
 *  - `h = l = c`:高低標記走等值反查(`m.h === accum.high`),沒有 per-minute 高低就只能
 *    以收盤代替;`high / low` 同步取**分鐘收盤極值**而不是 `series.high/low`(那是 tick
 *    極值,鮮少恰等於任一分鐘收盤 → 反查落空 = 標記靜默缺席)。figcaption 的 Quote 仍
 *    顯示 tick 高低,兩者差異 ≤ 分鐘內振幅(change-spec §5)。
 *  - `upper / lower = null`:y 域走以昨收置中的對稱 autofit,且不亮漲跌停燈(指數沒有)。
 *  - 只收 `SPOT_WINDOW` 內的分鐘(review R6):`vwap` / `high` / `low` 與幾何的 `windowedEntries`
 *    必須同一把尺 —— 窗外鍵(落檔舊格式 / 未來 14:30 定盤)混進來時,均價末點標籤(唯一文字
 *    來源 = `accum.vwap`)會與 `g.vwapLine` 末點脫節、日高標記找不到等值分鐘而靜默缺席。
 *
 *  純函式、零 IO;caller(`MarketChart`)以 `useMemo` 依 series identity 折,271 格 O(n)。 */
export function indexSeriesToAccum(series: IndexSeries, code: string, name: string): StockAccum {
  const rows: [number, number][] = [];
  for (const [key, value] of Object.entries(series.minutes)) {
    const minute = minuteOf(key);
    if (minute !== null && minute >= SPOT_WINDOW.start && minute <= SPOT_WINDOW.end) {
      rows.push([minute, value]);
    }
  }
  rows.sort((a, b) => a[0] - b[0]);

  const minutes = new Map<number, MinuteAgg>();
  let sum = 0;
  let high: number | null = null;
  let low: number | null = null;
  for (const [minute, c] of rows) {
    minutes.set(minute, { c, v: 1, i: 0, o: 0, u: 0, h: c, l: c });
    sum += c;
    high = high === null || c > high ? c : high;
    low = low === null || c < low ? c : low;
  }

  return {
    code,
    seq: 0,
    last: series.p !== null ? { p: series.p, t: "", cum_vol: 0 } : null,
    vwap: rows.length > 0 ? Math.round(sum / rows.length) : null,
    minutes,
    ticks: [],
    vp: new Map(),
    book: null,
    meta: { name, ref: series.ref, upper: null, lower: null, y_vol: null },
    noData: false,
    trial: false,
    high,
    low,
    amountMilli: 0,
    volume: 0,
  };
}

/** `HHMM` → 分鐘數;非四位數字 / 分鐘 ≥ 60 → null(略過)。時間窗過濾在呼叫端
 *  (`SPOT_WINDOW`,與幾何同源),這裡只擋「解不出來」的鍵。 */
function minuteOf(key: string): number | null {
  if (!/^\d{4}$/.test(key)) return null;
  const hh = Number(key.slice(0, 2));
  const mm = Number(key.slice(2));
  if (mm > 59) return null;
  return hh * 60 + mm;
}
