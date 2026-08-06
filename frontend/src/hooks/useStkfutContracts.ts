import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { StkfutContracts } from "@/lib/stkfut";

/** 個股期合約清單(stkfut-contracts SC-4)。
 *
 *  **404 不是錯誤**:後端 `NO_STKFUT` 的語意是「這檔股票沒有期貨」,是多數股票的
 *  正常狀態 → 轉成 `null`,呼叫端據此不渲染下拉。反過來 502(TC4 斷線)必須留在
 *  錯誤態:兩者一旦壓成同一個「沒有下拉」,達錢 4 掛掉時畫面看起來會像「這檔本來
 *  就沒期貨」,而那是零訊號的誤導。
 *
 *  合約清單一天只換一次(月份到期才變動),`staleTime` 10 分鐘足夠 —— 後端本身
 *  已有當日 cache,這裡只是省掉切檔來回的重打。 */

const TEN_MIN_MS = 10 * 60 * 1000;

async function fetchContracts(code: string): Promise<StkfutContracts | null> {
  const res = await fetch(`/api/stock/stkfut/contracts/${code}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as StkfutContracts;
}

export function useStkfutContracts(code: string | null) {
  return useQuery({
    queryKey: ["stkfut-contracts", code],
    queryFn: () => fetchContracts(code as string),
    enabled: code !== null,
    staleTime: TEN_MIN_MS,
    retry: 1,
    // 下拉只是 header 上的一顆選單:TC4 斷線時它該消失,不該把整個個股頁
    // 拋進 error boundary(同 useOiLevels 的降級語意)。
    throwOnError: false,
  });
}
