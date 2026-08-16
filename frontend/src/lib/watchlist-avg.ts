/** 自選群組標題列的等權平均漲幅(batch2 R6 SC-4)。
 *
 *  分母只算「今日有成交」的檔(`p != null` 且 `chg_pct != null`):盤前只有參考價的檔、
 *  無資料的檔都不入分母 —— 把它們當 0% 會把整組平均往 0 拉、看起來像「這組今天沒動」。
 *  全組都沒成交 → null,呼叫端不渲染(標題列已有檔數,空值再佔一格是噪音)。
 *  `n` / `total` / `trial` 一併回傳(review C3/C4):分母與標題列檔數是兩個母體,
 *  1/10 檔有成交時的「+6.00%」不該讀成整組;試撮窗的撮合價入了平均也要看得出來 ——
 *  呼叫端用它們組 title / aria-label,不做覆蓋率門檻(等權、不隱藏是刻意的:盤前少數檔
 *  先動本身就是資訊)。 */
export interface GroupAvg {
  avg: number;
  /** 入分母的檔數 */
  n: number;
  /** 群組總檔數 */
  total: number;
  /** 入分母的檔裡有幾檔在試撮 / 緩撮窗(`trial`) */
  trial: number;
}

export function groupAvgPct(
  codes: readonly string[],
  quotes: Record<
    string,
    { p: number | null; chg_pct: number | null; trial?: boolean } | undefined
  >,
): GroupAvg | null {
  let sum = 0;
  let n = 0;
  let trial = 0;
  for (const code of codes) {
    const q = quotes[code];
    if (q === undefined || q.p == null || q.chg_pct == null) continue;
    sum += q.chg_pct;
    n += 1;
    if (q.trial === true) trial += 1;
  }
  return n === 0 ? null : { avg: sum / n, n, total: codes.length, trial };
}
