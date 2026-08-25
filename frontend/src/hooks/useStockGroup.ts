import { useCallback, useState } from "react";

import { STOCK_GROUP_KEY } from "@/lib/constants";
import { readLocal, writeLocal } from "@/lib/storage";

/** 群組圖牆「現在看哪一組」的持有者 + localStorage 記憶(F2,chart-ux-batch-0826)。
 *
 *  原本這份 state 住在 `GroupGridView` 內;F2 要讓側欄(兄弟節點)點列時切群組,共同祖先
 *  `StockPage` 才拿得到 → 上提到這支 hook,`StockPage` 以受控 props 餵 `GroupGridView`。
 *  hook 只管「記住的名字」,**不管 fallback**:記住的群組已被刪(另一分頁 / Discord)→
 *  由讀取端 `GroupGridView` 以 `groups[0]` 承接(edge 5),這裡不看 groups。
 *
 *  寫入失敗不拋(`writeLocal` 承擔):切換本身已生效,代價只是下次開回第一個群組。 */
export function useStockGroup() {
  const [picked, setPicked] = useState<string | null>(() => readLocal(STOCK_GROUP_KEY));
  const select = useCallback((name: string): void => {
    setPicked(name);
    writeLocal(STOCK_GROUP_KEY, name);
  }, []);
  return { picked, select };
}
