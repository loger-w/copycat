import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { parseError } from "@/lib/api-error";
import { setHolidays } from "@/lib/trading-calendar";
import type { CalendarState } from "@/types";

/** 交易日曆取數(SC-9):每 5 分鐘問一次 `/api/calendar`,把假日集合灌進 `lib/trading-calendar`。
 *
 *  **掛在 App 層且只掛一支**:消費端(三支交易時段函式)是模組級的,多掛幾份只是多打
 *  幾次同一個端點。
 *
 *  `staleTime: Infinity` + 5 分鐘 `refetchInterval`(**背景分頁照輪詢**):日曆是靜態
 *  config,盤中不會變;重取是給**長跑分頁跨日**用的(看盤日常 = preview 整天掛在背景)。
 *  原本 6 小時:TanStack 預設背景分頁停掉 interval、而 staleTime Infinity 又消解
 *  focus 重取 → 跨午夜後膠囊最壞要等前景 6 小時才亮(2026-08-22 review R6 P2)。
 *  5 分鐘與 useSignalFeed 的 BASELINE_REFETCH_MS 同口徑,/api/calendar 是靜態 JSON,成本可忽略。
 *
 *  `retry: 1`:失敗的樣態是後端不在 —— 重試三輪只是延後降級,而降級本身是安全的
 *  (空集合 = 只擋週末 = 改動前行為)。
 *
 *  寫入放 `useEffect` 而不是 `queryFn` 內:queryFn 也會在 refetch / 背景重取時跑,
 *  但它是「取資料」的位置;副作用綁在 data 上,重取到同一份 reference 時不重複寫。 */

const CALENDAR_REFETCH_MS = 5 * 60_000;

async function fetchCalendar(): Promise<CalendarState> {
  const res = await fetch("/api/calendar");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as CalendarState;
}

/** 共用 query options(D1):第二個讀者(`CalendarBadges`)要的是**同一份 cache**,
 *  不是第二次取數 —— 各自寫一份 options 會在 queryKey 相同但 staleTime 不同時,
 *  讓兩邊互相觸發背景重取。掛載點仍只有 App 那一支寫入模組級假日集合。 */
export const calendarQueryOptions = {
  queryKey: ["calendar"],
  queryFn: fetchCalendar,
  staleTime: Infinity,
  retry: 1,
  refetchInterval: CALENDAR_REFETCH_MS,
  refetchIntervalInBackground: true,
} as const;

export function useTradingCalendar() {
  const query = useQuery(calendarQueryOptions);

  const holidays = query.data?.holidays;
  useEffect(() => {
    if (holidays !== undefined) setHolidays(holidays);
  }, [holidays]);

  return query;
}
