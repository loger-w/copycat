/** 台北交易時段判定(本機時區 = 台北,部署綁本機)。
 *
 * 從 `hooks/useStockBars.ts` 搬來(index-board 🔵):大盤頁的 K 線輪詢要用同一條規則,
 * 而 `lib/` 才是純函式的落點 —— 讓新 hook 去 import 一個 hooks 模組只為拿一個 helper
 * 是反向依賴。`useStockBars` 仍 re-export,個股側 import 路徑不變。
 *
 * 非交易日必須擋掉:少了這一維,週末與國定假日整個上午都會每 60s 打一次當日段,
 * 而當日段恆空 → `today_put` don't-cache-empty → 每次都真的走 TC4 SubHistory
 * (首頁 poll deadline ≈ 30s、約 30 個 REQ,搶同一個 source 的 `api.lock`)。
 *
 * 起點取 09:01 而非 08:45:當日第一根 1K 就是 09:01,更早輪詢必定空手而回。
 * (國定假日自 mod/trading-calendar 起由 `isTradingDay` 一併擋掉 —— 假日集合來自
 * `/api/calendar`;未載入時退回只擋週末 = 改動前行為。)
 */
import { isTradingDay } from "@/lib/trading-calendar";

export function inTradingHours(now: Date = new Date()): boolean {
  if (!isTradingDay(now)) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 9 * 60 + 1 && mins <= 13 * 60 + 35;
}

/** 台指期日盤時段(08:45 開盤 → 首根 1K 是 08:46;13:45 收盤 + 一分鐘餘裕)。
 *
 * 個股那把尺(09:01–13:35)套在期指上,開盤前 15 分與 13:36–13:45 的分 K 不會自動
 * 更新,要手動切模式才重取(review P2-5)。夜盤不在本輪 scope(期指 K 線只取日盤窗)。 */
export function inFuturesTradingHours(now: Date = new Date()): boolean {
  if (!isTradingDay(now)) return false;
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= 8 * 60 + 46 && mins <= 13 * 60 + 46;
}

/** 前一日(本機時區)。00:00–05:05 那段夜盤屬前一交易日,判的是它。 */
function prevDay(now: Date): Date {
  const d = new Date(now);
  d.setDate(d.getDate() - 1);
  return d;
}

/** 台指期**近全時段**(日盤 + 夜盤)輪詢窗(SC-12;design §4.2)。
 *
 * **日別是必要的一維,不是加分項**:夜盤後半(00:00–05:00)屬**前一交易日**,所以
 * 「週六凌晨 = 週五夜盤」要開、「週一凌晨 = 週日無夜盤」要關。少了這一維,週末兩天
 * 會整夜每 60s 空打當日段(當日段恆空 → don't-cache-empty → 每次都真的走 TC4)。
 *
 * 該段改判 `isTradingDay(前一日)`(mod/trading-calendar R1):對純週末與原本的
 * `day >= 2 && day <= 6` **完全等價**(週二〜週六的前一日恰是週一〜週五),
 * 只是多疊一層假日否決 —— 假日次日凌晨沒有夜盤可收,而假日**當天**凌晨照收前一
 * 交易日的夜盤。
 *
 * 兩段停輪詢窗:13:51–14:54(日盤收→夜盤開,含收尾餘裕)與 05:06–08:39。 */
export function inFuturesAllDayHours(now: Date = new Date()): boolean {
  const mins = now.getHours() * 60 + now.getMinutes();
  // 00:00–05:05 先判:這段屬前一日的夜盤,所以看的是前一天是不是交易日
  if (mins <= 5 * 60 + 5) return isTradingDay(prevDay(now));
  if (!isTradingDay(now)) return false;
  return (mins >= 8 * 60 + 40 && mins <= 13 * 60 + 50) || mins >= 14 * 60 + 55;
}
