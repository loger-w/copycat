/** 個股搜尋提示列的過濾純函數(round4 項 1)。
 *
 *  名稱表整包由 `GET /api/stock/names` 一次載入(實測 2,401 檔 / 約 58 KB),過濾在前端做:
 *  提示列零延遲,且這條邏輯可單測 —— 換成 server-side `?q=` 就變成每按一鍵打一次 API。
 */

export interface StockName {
  code: string;
  name: string;
}

/** 代碼前綴命中優先於名稱片段命中,各段內按代碼升序;合併去重後取前 `limit` 筆。
 *
 *  代碼比對轉大寫(字母尾碼 ETF 如 `00679B`,使用者不會特意按 shift);
 *  名稱比對**不轉大小寫** —— 中文沒有 case,轉了只是白花 CPU。 */
export function searchStocks(
  query: string,
  table: readonly StockName[],
  limit = 20,
): StockName[] {
  const trimmed = query.trim();
  if (trimmed === "") return [];
  const upper = trimmed.toUpperCase();
  const byCode: StockName[] = [];
  const byName: StockName[] = [];
  for (const row of table) {
    if (row.code.toUpperCase().startsWith(upper)) byCode.push(row);
    else if (row.name.includes(trimmed)) byName.push(row);
  }
  const asc = (a: StockName, b: StockName): number => (a.code < b.code ? -1 : a.code > b.code ? 1 : 0);
  return [...byCode.sort(asc), ...byName.sort(asc)].slice(0, limit);
}
