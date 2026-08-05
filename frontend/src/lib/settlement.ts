/** 台指期月契約結算(第三個週三)與倒數(SC-6;design §6.2)。
 *
 * 純日曆計算,不含國定假日行事曆 —— 遇連假時倒數會偏大(brainstorm known limitation,
 * 與 `trading-hours` / `spot-session` 同一個已知取捨)。
 */

const YM = /^\d{6}$/;
const YMD = /^\d{4}-\d{2}-\d{2}$/;
const WEDNESDAY = 3;

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** YYYYMM → 該月第三個週三的 `YYYY-MM-DD`。壞 YYYYMM 拋錯
 *  (與 `futures-ladder.futExchangeContract` 同慣例;不想被拋的呼叫端走
 *  `settlementCountdown`,那支對壞輸入回 null)。 */
export function thirdWednesday(ym: string): string {
  const year = Number(ym.slice(0, 4));
  const month = Number(ym.slice(4, 6));
  if (!YM.test(ym) || month < 1 || month > 12) {
    throw new Error(`invalid YYYYMM: ${ym}`);
  }
  // UTC 建構:本機時區只影響顯示,而這裡要的是純日曆推算(DST 地區用本機會偏一天)
  const first = new Date(Date.UTC(year, month - 1, 1));
  const offset = (WEDNESDAY - first.getUTCDay() + 7) % 7; // 月初當天就是週三 → 0
  return `${year}-${pad2(month)}-${pad2(1 + offset + 14)}`;
}

/** 今天到結算日之間的**交易日(週一〜五)**天數;結算當日 = 0、已過 = null。
 *
 * 已過回 null 而不是負數:HOT 契約在結算日盤後才換月,那段空窗期用舊 ym 算出來的
 * 「T-(−3)」比不顯示更難懂(design §6.2)。
 *
 * **never-throw**:呼叫點在 render path,壞輸入白屏的代價遠大於少一顆 badge。 */
export function settlementCountdown(ym: string, today: string): number | null {
  if (!YM.test(ym) || !YMD.test(today)) return null;
  let settle: string;
  try {
    settle = thirdWednesday(ym);
  } catch {
    return null;
  }
  if (today > settle) return null;
  if (today === settle) return 0;

  const end = new Date(`${settle}T00:00:00Z`);
  const cur = new Date(`${today}T00:00:00Z`);
  if (Number.isNaN(end.getTime()) || Number.isNaN(cur.getTime())) return null;
  let n = 0;
  // 從「今天的下一天」數到結算日(含)—— 這樣結算當日自然是 0(T-0 = 當天)
  cur.setUTCDate(cur.getUTCDate() + 1);
  while (cur.getTime() <= end.getTime()) {
    const dow = cur.getUTCDay();
    if (dow >= 1 && dow <= 5) n += 1;
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return n;
}
