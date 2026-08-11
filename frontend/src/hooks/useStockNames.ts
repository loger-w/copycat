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

/** 尚未拿到名稱表時的自動重抓間隔。
 *
 *  server 未起(先開前端後起 server)或啟動窗內,首載連線被拒 → `retry: 1` 兩次嘗試
 *  1-2 秒內用完就落入 error 終態,提示列與側欄股名要等 window refocus 才復原 —
 *  所以 error 終態下仍每 3 秒重抓。拿到資料(哪怕空表)即停,穩態零成本。 */
export const NAMES_RETRY_INTERVAL_MS = 3000;

/** 連續失敗輪數上限(每輪 = 一次 fetch cycle 含 retry:1 共兩次嘗試)。 */
export const NAMES_MAX_ERROR_CYCLES = 20;

/** refetchInterval 求值。具名 export 供白盒測試鎖輪詢節奏與停止條件
 *  (skill `frontend-testing`:輪詢行為斷言 refetchInterval 求值結果)。 */
export function namesRefetchInterval(query: {
  state: { data: StockName[] | undefined; errorUpdateCount: number };
}): number | false {
  return query.state.data === undefined ? NAMES_RETRY_INTERVAL_MS : false;
}

export function useStockNames() {
  return useQuery({
    queryKey: ["stock-names"],
    queryFn: fetchStockNames,
    staleTime: Infinity,
    gcTime: Infinity,
    // `retry: 1` 只是把單輪 fetch cycle 壓在兩次嘗試;error 態目前沒有任何 consumer
    // 在讀(兩個 caller 都只讀 data),錯誤碼僅供 devtools / query cache 查案
    retry: 1,
    refetchInterval: namesRefetchInterval,
  });
}
