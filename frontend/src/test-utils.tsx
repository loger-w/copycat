import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";

import { ymdOf } from "@/lib/ladder-lots";
import type { CapitalFill } from "@/types";

/**
 * QueryClientProvider 包裝過的 render:每次呼叫給一個全新、關掉 retry 的 client。
 *
 * 全新是重點 —— 共用 client 會讓上一個 it 的 query cache 洩到下一個;retry 關掉則是
 * 錯誤路徑測試不必等重試退避。個股頁五個元件測試各抄一份逐字相同的定義,任何一處
 * 想調 defaultOptions 都會變成「這檔的 wrap 跟別檔不一樣」。
 */
export function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

/** 成交記錄 fixture(SC-6,`CapitalFill`)。`date` **必須動態算** —— 寫死日期的測試
 *  會在隔天靜默轉綠 / 轉紅(日期界是 `fillPoints` 的過濾條件之一)。
 *  `price` 是**元**(2380 → 毫元 2_380_000);`qty` 現股是張。
 *  GroupGridView.test 與 StockChart.test 原各抄一份逐位相同(pr-167 #23)——
 *  `CapitalFill` 加欄時只改這裡;帶額外參數的變體(toggle / memo 檔)留各自。 */
export function fillOf(over: Partial<CapitalFill> = {}): CapitalFill {
  return {
    seq_no: "s1",
    stock_no: "2330",
    buy_sell: "B",
    flag_label: null,
    price: 2380,
    qty: 2,
    unit: "張",
    date: ymdOf(new Date()),
    time: "09:00:30",
    code: "2330",
    ...over,
  };
}
