/** OI 撐壓線的取線邏輯(SC-11;design §5.2)。純函式 —— 後端只回 per-strike 全表,
 *  「哪一根是壓力 / 支撐」在這裡決定。
 *
 * **為什麼要帶內取 max 而不是全域 max**:2026-08-04 真樣本裡 call OI 的全域最大值落在
 * 履約價 55000(現價 24000 附近),那是深度價外的垃圾部位不是壓力。以現價 ±10% 為帶,
 * 帶內 call_oi 最大者 = 壓力、put_oi 最大者 = 支撐。
 */

import type { OiStrikeRow } from "@/types";

/** 水平 overlay 線的資料形(與 CandleChart `hlines` prop 同形)。 */
export interface OiLine {
  priceMilli: number;
  label: string;
  className: string;
  /** hover 提示:承載口數與資料日 —— 線本身只寫得下履約價,而「這條線憑什麼是壓力」
   *  的證據是那個口數(SC-11 驗收項)。 */
  title: string;
}

const BAND = 0.1; // 現價 ±10%

/** 壓力 = 帶內 call_oi 最大;支撐 = 帶內 put_oi 最大。
 *  帶內空 / spot 無值 / 該邊 OI 全 0 → 該邊 null(不畫,勝過畫在錯的價位)。
 *
 *  `strikes` 假定為 strike 升冪(後端保證);OI 平手時取先到者 = 較低履約價。 */
export function pickOiLines(
  strikes: readonly OiStrikeRow[],
  spotMilli: number | null,
  date: string | null,
): { call: OiLine | null; put: OiLine | null } {
  if (spotMilli === null || !Number.isFinite(spotMilli) || spotMilli <= 0) {
    return { call: null, put: null };
  }
  // 取整:履約價一律是整點(× 1000 後為整數毫點),而 `spot × 1.1` 的浮點餘數
  // (24000000 × 1.1 = 26400000.000000004)會讓「端點算不算帶內」變成浮點運氣 ——
  // 實測上界端點在 `>=` 突變下仍通過,正是靠這一點鬆度。取整後端點判定是確定的。
  const loMilli = Math.round(spotMilli * (1 - BAND));
  const hiMilli = Math.round(spotMilli * (1 + BAND));

  let call: OiStrikeRow | null = null;
  let put: OiStrikeRow | null = null;
  for (const row of strikes) {
    const priceMilli = row.strike * 1000;
    if (priceMilli < loMilli || priceMilli > hiMilli) continue;
    if (row.call_oi > 0 && (call === null || row.call_oi > call.call_oi)) call = row;
    if (row.put_oi > 0 && (put === null || row.put_oi > put.put_oi)) put = row;
  }

  const day = date ?? "—";
  return {
    call:
      call === null
        ? null
        : {
            priceMilli: call.strike * 1000,
            label: `壓 ${call.strike}`,
            className: "stroke-bear",
            title: `壓 ${call.strike}・OI ${call.call_oi}口・${day}`,
          },
    put:
      put === null
        ? null
        : {
            priceMilli: put.strike * 1000,
            label: `撐 ${put.strike}`,
            className: "stroke-bull",
            title: `撐 ${put.strike}・OI ${put.put_oi}口・${day}`,
          },
  };
}
