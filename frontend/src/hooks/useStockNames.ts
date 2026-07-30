import { useQuery } from "@tanstack/react-query";

import type { StockName } from "@/lib/stock-search";

/** 全市場代號↔名稱表(搜尋提示列用;round4 項 1)。
 *
 *  表是**版控靜態檔**(`copycat/stock_names.json`,實測 2,401 檔 / 約 58 KB),盤中不會變 →
 *  `staleTime: Infinity` 一次載入就好,不需要 refresh 慣例的 `?refresh=true`。 */
async function fetchStockNames(): Promise<StockName[]> {
  const res = await fetch("/api/stock/names");
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: { error?: string } };
    throw new Error(body.detail?.error ?? `HTTP_${res.status}`);
  }
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
