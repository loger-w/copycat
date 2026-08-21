import { useQuery } from "@tanstack/react-query";

import { calendarQueryOptions } from "@/hooks/useTradingCalendar";
import { isoLocalDate, isWeekendIso } from "@/lib/trading-calendar";

/** 日曆判今日休市膠囊(SC-1 / D2')。
 *
 *  **要解的是「錯標」的靜默**:`configs/trading_holidays.json` 把一個真交易日標成假日時,
 *  後端 `_resolve_trade_date` 會退到最近交易日、盤中輪詢整天不動,而畫面上完全看不出來
 *  (只有 boot 一行 WARNING)。前端判不出「錯標」—— 它能判的只有「日曆說今天休市」,
 *  所以真假日也一起顯示:那時這顆膠囊回答的是「為什麼今天畫面不動」。
 *
 *  **判準 = `calendar_trade_date !== today`,不自己算假日**(review C-2):後端
 *  `resolve_trade_date` 已經把「今天有沒有開盤」推導完了,而那支涵蓋補班日
 *  (`extra_trading_days`:日期在 `holidays` 內但仍開盤)。前端拿 `holidays.includes`
 *  重算是複製一份會漂的判定 —— 漂掉的樣態正是補班日當天亮著說「今天休市」。
 *
 *  **日期本身全取自後端同一份 payload**(`today` / `calendar_trade_date` / `trade_date`):
 *  看盤機的時區與時鐘和後端日別是兩回事,拿本機今天去比對後端日別會在跨午夜與時區偏移
 *  時各錯一種。
 *
 *  **本機日保險絲**(review C-3):payload 是 `staleTime: Infinity` + 6 小時 refetch 的
 *  快取,長跑分頁跨午夜後 `today` 會停在昨天 —— 那份 payload 對「今天」已經無話可說,
 *  `data.today !== isoLocalDate(new Date())` 就不亮。這是唯一用到瀏覽器時鐘的地方,而
 *  它只用來**否決**(時鐘歪掉的失效方向是「該亮時不亮」= 降級成現況)。
 *
 *  **週末不亮**(AR8):週末本來就休市,常駐一顆膠囊兩週後就沒人看得見它了;真正要
 *  被看見的是平日亮起來的那一次。週末補班(`extra_trading_days` 設在週六)真開盤這條
 *  由此排除,記 next-time。
 *
 *  未載入 / 取數失敗 → 不顯示:降級成改動前的現況。誤報一次就會被當雜訊無視,之後真的
 *  錯標也不會有人看(同 `VersionDriftBadge` 的「健康態零 DOM」判準)。 */
export function CalendarHolidayBadge() {
  const { data } = useQuery(calendarQueryOptions);
  if (data === undefined || !data.calendar_loaded) return null;
  if (data.calendar_trade_date === data.today) return null;
  if (isWeekendIso(data.today) || data.today !== isoLocalDate(new Date())) return null;
  return (
    <span
      data-testid="calendar-holiday-badge"
      // 資料日寫進 title:「今天沒動」與「畫面停在哪一天」是同一個問題的兩半,
      // 少了後者還是得自己去翻 /api/calendar。
      title={`日曆判今日休市,後端資料日 = ${data.trade_date};若今天實際有開盤,更新 configs/trading_holidays.json 並重啟`}
      className="inline-flex items-center gap-1.5 rounded-sm border border-warn/40 bg-warn/15 px-2.5 py-1 font-mono text-xs text-warn"
    >
      日曆判今日休市
    </span>
  );
}
