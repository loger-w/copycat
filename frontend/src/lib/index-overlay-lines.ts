import type { IndexSeries } from "@/hooks/useIndexStream";
import { minuteToX, type IntradayGeometry, type XWindow } from "@/lib/stock-intraday-svg";

/** 個股分時圖上疊「加權 / 櫃買」即時走勢(feat/chart-ux-batch-0826 F1)。
 *
 *  疊法 = **相對昨收 %** 映射到個股自己的價格軸:`y = toY(stockRef × (1 + idxPct))`。
 *  個股的 y 域是 [跌停, 漲停](±10%),指數日內振幅 ±2% 恆在域內,不需要第二條 y 軸;
 *  % 的定義與台股綜合頁 `MarketPane` 的「加權 vs 櫃買(相對昨收 %)」同一條
 *  (`lib/index-chart-svg.ts::buildOverlayGeometry`)。讀法:個股價線在指數線之上 = 今天比大盤強。
 *
 *  純函式、零 React 依賴;caller(`IntradayChartCore`)以 `useMemo` 依 series identity 折。
 *  兩個「沒有基準就不畫」的閘都在這裡:個股沒昨收(`stockRef` null / 0)→ 全部不畫;
 *  某指數沒昨收 → 只那一條不畫。相對 % 沒有基準就是假線。 */

export type IndexOverlayKey = "twse" | "otc";

export interface IndexOverlaySeries {
  twse: IndexSeries | null;
  otc: IndexSeries | null;
}

export interface IndexOverlayLine {
  key: IndexOverlayKey;
  /** 線上的點(已是 SVG 座標,依分鐘升冪) */
  pts: { x: number; y: number }[];
  /** 末點的相對昨收 %(右緣標籤用);至少一點才有值 */
  lastPct: number;
}

export const INDEX_OVERLAY_LABEL: Record<IndexOverlayKey, string> = {
  twse: "加權",
  otc: "櫃買",
};

/** `IndexSeries.minutes` 的 key 是 "HHMM";形狀不對 → null(與 `index-accum-adapter` 同判) */
function minuteOfKey(key: string): number | null {
  if (key.length !== 4) return null;
  const h = Number(key.slice(0, 2));
  const m = Number(key.slice(2, 4));
  if (!Number.isInteger(h) || !Number.isInteger(m) || h < 0 || h > 23 || m < 0 || m > 59) return null;
  return h * 60 + m;
}

export function buildIndexOverlayLines(
  series: IndexOverlaySeries | null,
  on: { twse: boolean; otc: boolean },
  stockRefMilli: number | null,
  g: Pick<IntradayGeometry, "toY">,
  width: number,
  xw: XWindow,
): IndexOverlayLine[] {
  if (series === null || !(stockRefMilli !== null && stockRefMilli > 0)) return [];
  const out: IndexOverlayLine[] = [];
  for (const key of ["twse", "otc"] as const) {
    if (!on[key]) continue;
    const s = series[key];
    // 判定寫成保留條件的否定(NaN 兩個比較都 false 會把壞 ref 留下,同 buildOverlayGeometry)
    if (s === null || !(s.ref !== null && s.ref > 0)) continue;
    const ref = s.ref;
    const rows: { minute: number; p: number }[] = [];
    for (const [k, p] of Object.entries(s.minutes)) {
      const minute = minuteOfKey(k);
      // `p > 0`:後端 `_millipt("0")` 回 0 不回 None(TC4 偶發送 "0"),毫點恆 > 0 → 0 = 不可得
      if (minute === null || minute < xw.start || minute > xw.end || !(p > 0)) continue;
      rows.push({ minute, p });
    }
    if (rows.length === 0) continue;
    rows.sort((a, b) => a.minute - b.minute);
    // 映射寫成 `stockRef × p / ref` 而不是 `stockRef × (1 + pct)`:兩者數學上同值,但後者先算
    // 出 0.005 這類不可精確表示的比率再乘回去,整數毫元會漂成 100499.999…(測試釘的是整數)。
    const pts = rows.map(({ minute, p }) => ({
      x: minuteToX(minute, width, xw),
      y: g.toY((stockRefMilli * p) / ref),
    }));
    const last = rows[rows.length - 1]!.p;
    out.push({ key, pts, lastPct: ((last - ref) / ref) * 100 });
  }
  return out;
}
