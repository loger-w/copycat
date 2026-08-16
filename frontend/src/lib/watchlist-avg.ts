/** 自選群組標題列的等權平均漲幅(batch2 R6 SC-4)。
 *
 *  分母只算「今日有成交」的檔(`p != null` 且 `chg_pct != null`):盤前只有參考價的檔、
 *  無資料的檔都不入分母 —— 把它們當 0% 會把整組平均往 0 拉、看起來像「這組今天沒動」。
 *  全組都沒成交 → null,呼叫端不渲染(標題列已有檔數,空值再佔一格是噪音)。 */
export function groupAvgPct(
  codes: readonly string[],
  quotes: Record<string, { p: number | null; chg_pct: number | null } | undefined>,
): number | null {
  let sum = 0;
  let n = 0;
  for (const code of codes) {
    const q = quotes[code];
    if (q === undefined || q.p == null || q.chg_pct == null) continue;
    sum += q.chg_pct;
    n += 1;
  }
  return n === 0 ? null : sum / n;
}
