import { useQuery } from "@tanstack/react-query";

import { calendarQueryOptions } from "@/hooks/useTradingCalendar";
import { isWeekendIso } from "@/lib/trading-calendar";

/** 日曆判今日休市膠囊(SC-1 / D2')。
 *
 *  **要解的是「錯標」的靜默**:`configs/trading_holidays.json` 把一個真交易日標成假日時,
 *  後端 `_resolve_trade_date` 會退到最近交易日、盤中輪詢整天不動,而畫面上完全看不出來
 *  (只有 boot 一行 WARNING)。前端判不出「錯標」—— 它能判的只有「日曆說今天休市」,
 *  所以真假日也一起顯示:那時這顆膠囊回答的是「為什麼今天畫面不動」。
 *
 *  **條件全取自後端同一份 payload**(`today` / `holidays` / `trade_date`),不用瀏覽器
 *  時鐘:看盤機的時區與時鐘和後端日別是兩回事,拿本機今天去比對假日清單會在跨午夜與
 *  時區偏移時各錯一種,而錯的方向是「該亮時不亮」。
 *
 *  **週末不亮**(AR8):週末本來就休市,常駐一顆膠囊兩週後就沒人看得見它了;真正要
 *  被看見的是平日亮起來的那一次。補班日(`extra_trading_days`)漏設而週末真開盤這條
 *  由此排除,記 next-time。
 *
 *  未載入 / 取數失敗 → 不顯示:降級成改動前的現況。誤報一次就會被當雜訊無視,之後真的
 *  錯標也不會有人看(同 `VersionDriftBadge` 的「健康態零 DOM」判準)。 */
export function CalendarHolidayBadge() {
  const { data } = useQuery(calendarQueryOptions);
  if (data === undefined || !data.calendar_loaded) return null;
  if (!data.holidays.includes(data.today) || isWeekendIso(data.today)) return null;
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
