import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import { inTradingHours } from "@/lib/trading-hours";
import type { BreadthRowsState } from "@/types";

/** 漲跌停列表資料流(market-overview R3 SC-1;design §5.2)。
 *
 * **REST on-demand 不進 WS**(brainstorm Q2):payload 是全市場 ~2800 列 × 15 欄,
 * 掛上 `/ws/breadth` 等於所有開站的人都吃這份頻寬,而它只有人在台股綜合頁時才有人看。
 * 消費端(`LimitListSection`)自 2026-08-16 一頁總覽起**恆掛**在右欄(subtab 機制退役,
 * 改版前是「非 active subtab 即 unmount」)—— 省頻寬的責任整條落到下面的 `active` gate,
 * 不再有 unmount 這條退路。
 *
 * `refetchInterval` 用**函式形式**(R10,`useMarketBars` 同慣例):TQ 每次 interval
 * 到期都重新求值,開盤 / 收盤的開關不依賴外部 re-render 才會生效。收盤後回 false
 * = 完全停輪詢(家數引擎自己也只在盤中窗取數,盤後輪詢只是白打)。
 *
 * `retry: 1` 而非預設的 3:這條路的失敗多半是後端引擎不在 / FinMind 掛了,
 * 重試三輪只是把「載入中」拖得更長。
 */

const POLL_MS = 10_000;

async function fetchBreadthRows(): Promise<BreadthRowsState> {
  const res = await fetch("/api/market/breadth/rows");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as BreadthRowsState;
}

/** @param active 使用者是否正看著台股綜合 tab。該 tab 的 DOM 由 App 以 `hidden` 保留
 *  (不 unmount),列表又恆掛在右欄 —— 沒有這道 gate,只要開過站台一次,整個盤中每
 *  10 秒都在抓一份全市場 ~2800 列的 payload(review FE-2)。
 *
 *  **只停 `refetchInterval`,不關 `enabled`**(`useFuturesBars` 同慣例):輪詢是這支
 *  query 唯一的背景請求來源,停掉即達成目的;而 `enabled: false` 會讓切回 tab 時
 *  query 退回 pending 態 → 表格閃一次「載入中…」而不是留著舊表等新料。
 *
 *  預設 `true`:獨立使用與既有呼叫路徑不因這道 gate 靜默停更。 */
export function useBreadthRows(active = true) {
  return useQuery({
    queryKey: ["breadth-rows"],
    queryFn: fetchBreadthRows,
    retry: 1,
    refetchInterval: () => (active && inTradingHours() ? POLL_MS : false),
  });
}
