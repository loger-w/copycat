const nf = new Intl.NumberFormat("en-US");

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
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value);
}
