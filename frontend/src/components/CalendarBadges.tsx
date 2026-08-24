import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { calendarQueryOptions } from "@/hooks/useTradingCalendar";
import { isoLocalDate, isWeekendIso } from "@/lib/trading-calendar";
import type { CalendarState } from "@/types";

/** nav 列的日曆膠囊組(SC-1 / D2' + N016 / N090 / N091)。
 *
 *  三顆都吃**同一份** `/api/calendar` payload,答三個互相獨立的問題:
 *
 *  1. 「今天為什麼畫面不動?」——`calendar_trade_date !== today`
 *  2. 「日曆自己是不是過期了?」——`years_loaded` 不含今年(此後只擋週末)
 *  3. 「是不是有人忘了清 `TXO_BACKFILL_DATE`?」——`backfill_env` 有值
 *
 *  共同判準:**健康態零 DOM**。誤報一次就會被當雜訊無視,之後真的出事也不會有人看
 *  (同 `VersionDriftBadge`)。未載入 / 取數失敗一律不顯示 = 降級成改動前的現況。 */
function Badge({
  testId,
  title,
  children,
}: {
  testId: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <span
      data-testid={testId}
      title={title}
      className="inline-flex items-center gap-1.5 rounded-sm border border-warn/40 bg-warn/15 px-2.5 py-1 font-mono text-xs text-warn"
    >
      {children}
    </span>
  );
}

/** 日曆判今日休市(SC-1 / D2';N090 調整週末守門)。
 *
 *  **要解的是「錯標」的靜默**:`configs/trading_holidays.json` 把一個真交易日標成假日時,
 *  後端 `_resolve_trade_date` 會退到最近交易日、盤中輪詢整天不動,而畫面上完全看不出來
 *  (只有 boot 一行 WARNING)。前端判不出「錯標」—— 它能判的只有「日曆說今天休市」,
 *  所以真假日也一起顯示:那時這顆膠囊回答的是「為什麼今天畫面不動」。
 *
 *  **判準 = `calendar_trade_date !== today`,不自己算假日**(review C-2):後端
 *  `resolve_trade_date` 已經把「今天有沒有開盤」推導完了,而那支涵蓋補班日
 *  (`extra_trading_days`:週末仍開盤)。前端拿 `holidays.includes` 重算是複製一份會漂
 *  的判定 —— 漂掉的樣態正是補班日當天亮著說「今天休市」。
 *
 *  **日期本身全取自後端同一份 payload**(`today` / `calendar_trade_date` / `trade_date`):
 *  看盤機的時區與時鐘和後端日別是兩回事,拿本機今天去比對後端日別會在跨午夜與時區偏移
 *  時各錯一種。
 *
 *  **本機日保險絲**(review C-3):payload 是 `staleTime: Infinity` + 5 分鐘背景輪詢的
 *  快取,長跑分頁跨午夜後 `today` 最多停在昨天 5 分鐘 —— 那份 payload 對「今天」已經無話可說,
 *  `data.today !== isoLocalDate(new Date())` 就不亮。這是唯一用到瀏覽器時鐘的地方,而
 *  它只用來**否決**(時鐘歪掉的失效方向是「該亮時不亮」= 降級成現況)。
 *
 *  **週末守門**(AR8 + N090):週末本來就休市,常駐一顆膠囊兩週後就沒人看得見它了;
 *  真正要被看見的是平日亮起來的那一次。**例外 = 今天列在 `extra_trading_days`**:
 *  那是「這個週六本來就該開盤」,後端卻仍判非交易日 —— 補班日設了沒生效,是真的
 *  不變式違反,必須亮。
 *
 *  **已知擋不到的那半**(N090 留尾):補班日**漏設**時 payload 與普通週末完全同形
 *  (後端判非交易日 + 該日不在 `extra_trading_days`),前端沒有第二個訊號可以分辨,
 *  只能繼續靜音。 */
function shouldShowHoliday(data: CalendarState): boolean {
  if (!data.calendar_loaded) return false;
  if (data.calendar_trade_date === data.today) return false;
  if (data.today !== isoLocalDate(new Date())) return false;
  return !isWeekendIso(data.today) || (data.extra_trading_days ?? []).includes(data.today);
}

export function CalendarBadges() {
  const { data } = useQuery(calendarQueryOptions);
  if (data === undefined) return null;

  const year = Number(data.today.slice(0, 4));
  // 日曆載到了、卻沒有今年的資料 = 此後只擋週末,國定假日會被當交易日(N016)。
  // `calendar_loaded=false` 走的是另一件事(根本沒日曆),那條由既有的休市膠囊守門
  // 表述成「不顯示」—— 兩者混在一起會讓「沒日曆」被講成「日曆過期」。
  const stale = data.calendar_loaded && Number.isFinite(year) && !data.years_loaded.includes(year);

  return (
    <>
      {shouldShowHoliday(data) ? (
        // 資料日寫進 title:「今天沒動」與「畫面停在哪一天」是同一個問題的兩半,
        // 少了後者還是得自己去翻 /api/calendar。
        <Badge
          testId="calendar-holiday-badge"
          title={`日曆判今日休市,後端資料日 = ${data.trade_date};若今天實際有開盤,更新 configs/trading_holidays.json 並重啟`}
        >
          日曆判今日休市
        </Badge>
      ) : null}
      {stale ? (
        <Badge
          testId="calendar-stale-badge"
          title={`交易日曆缺 ${year} 年資料,此後只擋週末(國定假日會被當成交易日);更新 configs/trading_holidays.json 並重啟`}
        >
          交易日曆過期
        </Badge>
      ) : null}
      {data.backfill_env !== null ? (
        // 忘了清這個 env 的樣態 = TXO 面整盤凍在某一天,而畫面上只是「都沒在動」。
        // payload 早就有這一格,只是從來沒有讀者(N091)。
        <Badge
          testId="calendar-backfill-env-badge"
          title={`環境變數 TXO_BACKFILL_DATE=${data.backfill_env} 把 TXO 面鎖在這一天;要看即時行情請清掉它並重啟`}
        >
          TXO 回補日鎖定 {data.backfill_env}
        </Badge>
      ) : null}
    </>
  );
}
