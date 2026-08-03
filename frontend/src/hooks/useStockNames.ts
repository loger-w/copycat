import { useQuery } from "@tanstack/react-query";

import { parseError } from "@/lib/api-error";
import type { StockName } from "@/lib/stock-search";

/** 全市場代號↔名稱表(搜尋提示列用;round4 項 1)。
 *
 *  表是**版控靜態檔**(`copycat/stock_names.json`,實測 2,401 檔 / 約 58 KB),盤中不會變 →
 *  `staleTime: Infinity` 一次載入就好,不需要 refresh 慣例的 `?refresh=true`。 */
async function fetchStockNames(): Promise<StockName[]> {
  const res = await fetch("/api/stock/names");
  // 走共用的 parseError(never-raise):行內的 `.json().catch(() => ({}))` 只擋得住
  // 「不是 JSON」,擋不住「是 JSON 的 null」—— 那時存取 detail 會把 TypeError
  // 拋出 queryFn,畫面拿到的是解析失敗的訊息而不是錯誤碼。
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { names?: StockName[] };
  // 後端表不可用時回空陣列(不 500);欄位缺失也一律當空表 —— 提示列不出現,
  // 但「直接打完整股號 Enter 新增」那條路徑照樣可用(白名單 W-4)
  return Array.isArray(body.names) ? body.names : [];
}

export function useStockNames() {
  return useQuery({
    queryKey: ["stock-names"],
    queryFn: fetchStockNames,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  });
}
