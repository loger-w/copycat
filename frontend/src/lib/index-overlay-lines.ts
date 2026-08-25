import type { IndexSeries } from "@/hooks/useIndexStream";
import { minuteOf } from "@/lib/index-accum-adapter";
import { minuteToX, type IntradayGeometry, type XWindow } from "@/lib/stock-intraday-svg";

/** 個股分時圖上疊「加權 / 櫃買」即時走勢(feat/chart-ux-batch-0826 F1)。
 *
 *  疊法 = **相對昨收 %** 映射到個股自己的價格軸:`y = toY(stockRef × p / idxRef)`。
 *  個股的 y 域是 [跌停, 漲停](±10%)時指數日內振幅恆在域內;**沒有漲跌停**(對稱域 fallback,
 *  半幅下限只 ±1.1%)時指數可能跑出域外 —— 域外點**剔除不畫**(PR #111 review F-05),與同圖
 *  `overlayLines` 同一把尺(閉區間、同一組 `g.yDomain`),不 clamp 到邊緣講成「圖緣的價位」。
 *  % 的定義與台股綜合頁 `MarketPane` 的「加權 vs 櫃買(相對昨收 %)」同一條
 *  (`lib/index-chart-svg.ts::buildOverlayGeometry`)。讀法:個股價線在指數線之上 = 今天比大盤強。
 *
 *  純函式、零 React 依賴;caller(`IntradayChartCore`)以 `useMemo` 依 series identity 折。
 *  兩個「沒有基準就不畫」的閘都在這裡:個股沒昨收(`stockRef` null / 0)→ 全部不畫;
 *  某指數沒昨收 → 只那一條不畫。相對 % 沒有基準就是假線。
 *
 *  **排序只做一次**(review F-06):`IndexSeries.minutes` 的 entries + sort 與個股無關,但圖牆上
 *  50 張卡各持一份 useMemo,每則指數推播會各重跑一次 → 以 series identity 為鍵的 WeakMap 快取
 *  已排序列,per-card 只剩窗過濾 + toY。series 是每則 WS 新物件(`toSeries` 展開),快取隨舊物件
 *  被 GC,沒有洩漏。 */

export type IndexOverlayKey = "twse" | "otc";

export interface IndexOverlaySeries {
  twse: IndexSeries | null;
  otc: IndexSeries | null;
}

export interface IndexOverlayLine {
  key: IndexOverlayKey;
  /** 線上的點(已是 SVG 座標,依分鐘升冪;域外點已剔除) */
  pts: { x: number; y: number }[];
  /** 末點(最後一個域內點)的相對昨收 %(右緣標籤用) */
  lastPct: number;
  /** 指數串流已中斷(`IndexSeries.stale`):標籤要加註,數字不能當「現在」讀(review F-09) */
  stale: boolean;
}

export const INDEX_OVERLAY_LABEL: Record<IndexOverlayKey, string> = {
  twse: "加權",
  otc: "櫃買",
};

interface Row {
  minute: number;
  p: number;
}

const SORTED_ROWS = new WeakMap<IndexSeries, readonly Row[]>();

/** `minutes` → 依分鐘升冪的 (minute, p) 列;壞 key / 0 值剔除。同一個 series 物件只算一次。 */
export function sortedIndexRows(s: IndexSeries): readonly Row[] {
  const hit = SORTED_ROWS.get(s);
  if (hit !== undefined) return hit;
  const rows: Row[] = [];
  for (const [k, p] of Object.entries(s.minutes)) {
    const minute = minuteOf(k);
    // `p > 0`:後端 `_millipt("0")` 回 0 不回 None(TC4 偶發送 "0"),毫點恆 > 0 → 0 = 不可得
    if (minute === null || !(p > 0)) continue;
    rows.push({ minute, p });
  }
  rows.sort((a, b) => a.minute - b.minute);
  SORTED_ROWS.set(s, rows);
  return rows;
}

export function buildIndexOverlayLines(
  series: IndexOverlaySeries | null,
  on: { twse: boolean; otc: boolean },
  stockRefMilli: number | null,
  g: Pick<IntradayGeometry, "toY" | "yDomain">,
  width: number,
  xw: XWindow,
): IndexOverlayLine[] {
  // 判定寫成保留條件的否定(NaN 兩個比較都 false 會把壞 ref 留下,同 buildOverlayGeometry)
  if (series === null || !(stockRefMilli !== null && stockRefMilli > 0)) return [];
  const [yBottom, yTop] = g.yDomain;
  const out: IndexOverlayLine[] = [];
  for (const key of ["twse", "otc"] as const) {
    if (!on[key]) continue;
    const s = series[key];
    if (s === null || !(s.ref !== null && s.ref > 0)) continue;
    const ref = s.ref;
    const pts: { x: number; y: number }[] = [];
    let lastP: number | null = null;
    for (const { minute, p } of sortedIndexRows(s)) {
      if (minute < xw.start || minute > xw.end) continue;
      // 映射寫成 `stockRef × p / ref` 而不是 `stockRef × (1 + pct)`:兩者數學上同值,但後者先算
      // 出 0.005 這類不可精確表示的比率再乘回去,整數毫元會漂成 100499.999…(測試釘的是整數)。
      const priceMilli = (stockRefMilli * p) / ref;
      if (priceMilli < yBottom || priceMilli > yTop) continue; // 域外不畫(閉區間,同 overlayLines)
      pts.push({ x: minuteToX(minute, width, xw), y: g.toY(priceMilli) });
      lastP = p;
    }
    if (pts.length === 0 || lastP === null) continue;
    out.push({ key, pts, lastPct: ((lastP - ref) / ref) * 100, stale: s.stale });
  }
  return out;
}
