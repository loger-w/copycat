import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { parseError } from "@/lib/api-error";
import { setHolidays } from "@/lib/trading-calendar";
import type { CalendarState } from "@/types";

/** 交易日曆取數(SC-9):開站問一次 `/api/calendar`,把假日集合灌進 `lib/trading-calendar`。
 *
 *  **掛在 App 層且只掛一支**:消費端(三支交易時段函式)是模組級的,多掛幾份只是多打
 *  幾次同一個端點。
 *
 *  `staleTime: Infinity` + 6 小時 `refetchInterval`:日曆是靜態 config,盤中不會變;
 *  留一個長週期重取是給**長跑分頁跨日**用的(開著不關的看盤機,隔天要吃到同一份即可,
 *  但也要能在後端更新 config 重啟後跟上)。
 *
 *  `retry: 1`:失敗的樣態是後端不在 —— 重試三輪只是延後降級,而降級本身是安全的
 *  (空集合 = 只擋週末 = 改動前行為)。
 *
 *  寫入放 `useEffect` 而不是 `queryFn` 內:queryFn 也會在 refetch / 背景重取時跑,
 *  但它是「取資料」的位置;副作用綁在 data 上,重取到同一份 reference 時不重複寫。 */

const SIX_HOURS_MS = 6 * 60 * 60 * 1000;

async function fetchCalendar(): Promise<CalendarState> {
  const res = await fetch("/api/calendar");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as CalendarState;
}

/** 共用 query options(D1):第二個讀者(`CalendarHolidayBadge`)要的是**同一份 cache**,
 *  不是第二次取數 —— 各自寫一份 options 會在 queryKey 相同但 staleTime 不同時,
 *  讓兩邊互相觸發背景重取。掛載點仍只有 App 那一支寫入模組級假日集合。 */
export const calendarQueryOptions = {
  queryKey: ["calendar"],
  queryFn: fetchCalendar,
  staleTime: Infinity,
  retry: 1,
  refetchInterval: SIX_HOURS_MS,
} as const;

export function useTradingCalendar() {
  const query = useQuery(calendarQueryOptions);

  const holidays = query.data?.holidays;
  useEffect(() => {
    if (holidays !== undefined) setHolidays(holidays);
  }, [holidays]);

  return query;
}
