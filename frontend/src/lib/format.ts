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

/** `YYYY-MM-DD` → `MM-DD`(SC-10)。年份在盤面上是雜訊,而月日是「這是哪一天的收盤」
 *  唯一需要的資訊;形狀不合就原樣印出來(寧可醜也不要靜默切錯字串)。 */
export function monthDay(iso: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.slice(5) : iso;
}

/** 指數軸帶用的價位文字(index 態的 y 刻度 / CDP `價位*` / MA 價位標 / 掛牌 / hover 價標)。
 *
 *  `fmt` 口徑但**超過 6 字就收整數點**:左緣價位帶 `Y_AXIS_W` 36px / 右緣 40px 是為個股
 *  「1005.0」(6 字)設計的,加權「24283.54」8 字 @0.5625rem ≈ 40px 會把開頭裁出畫布
 *  (code review C-2 / R4 real-env 截圖);櫃買「238.97」6 字裝得下、且 1 點 = 0.4% 收整數
 *  會失真,所以不是一律整數。閾值 6 = 個股既有最寬內容,與 `EDGE_LABEL_W` 的推導同源。 */
export function fmtIndexPts(milli: number): string {
  const full = fmt(milli);
  return full.length > 6 ? String(Math.round(milli / 1000)) : full;
}
