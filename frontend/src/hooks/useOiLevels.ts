import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { OiLevelsResponse } from "@/types";

/** TXO 月契約 OI 撐壓(futures-allday SC-11;design §5.2)。
 *
 * 資料是**日級**的(FinMind 前一交易日結算後的 OI),盤中不會變 → `staleTime` 一小時。
 *
 * `throwOnError: false` 是這支的重點,不是裝飾:OI 線只是圖上兩條輔助 overlay,
 * FinMind 掛了 / token 沒設 / 契約還沒解析出來都該是「線消失」,而不是把整個期貨頁
 * 拋進 error boundary。後端那側同樣一律回 200 空 shape(降級語意在兩端一致)。
 *
 * TXF / MXF / TMF 共用同一份(標的都是台指),所以 query key 不帶商品。
 */

const ONE_HOUR_MS = 60 * 60 * 1000;

async function fetchOiLevels(): Promise<OiLevelsResponse> {
  const res = await fetch("/api/futures/oi-levels");
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as OiLevelsResponse;
}

export function useOiLevels() {
  return useQuery({
    queryKey: ["oi-levels"],
    queryFn: fetchOiLevels,
    retry: 1,
    staleTime: ONE_HOUR_MS,
    throwOnError: false,
  });
}
