const nf = new Intl.NumberFormat("en-US");
const nfPts = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** NTD 縮寫:≥1 億 → 兩位小數億;≥1 萬 → 整數萬(千分位);其下千分位。 */
export function formatNtd(value: number): string {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 100_000_000) {
    return `${sign}NT$ ${(abs / 100_000_000).toFixed(2)}億`;
  }
  if (abs >= 10_000) {
    return `${sign}NT$ ${nf.format(Math.round(abs / 10_000))}萬`;
  }
  return `${sign}NT$ ${nf.format(abs)}`;
}

/** 指數點位:千分位,最多一位小數。 */
export function formatPts(value: number): string {
  return nfPts.format(value);
}

/** 漲跌百分比 → 顯示字串:正值帶 `+`,固定兩位小數。
 *  null 的「-」留在呼叫端 —— 各處的空值文案與 tone 判定不同。 */
export function fmtPct(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/** 相對參考價的漲跌百分比。`ref` 的合法性(null / 0)判定留在呼叫端。 */
export function chgPct(v: number, ref: number): number {
  return ((v - ref) / ref) * 100;
}

/** 毫元價格 → 顯示字串:整數不帶小數,否則兩位並去掉尾隨 0。 */
export function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}
