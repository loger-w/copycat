import { QueryClient, type DefaultOptions } from "@tanstack/react-query";

/**
 * 全站 QueryClient 的唯一工廠(#237):prod(`main.tsx`)與測試(`test-utils.tsx`)都經這裡建,
 * 「mutation 預設」只有一份。
 *
 * `mutations.networkMode: "always"` 的理由(真錢):TanStack 預設 `"online"` 時,瀏覽器判「沒網路」
 * (`navigator.onLine`)mutation **不送、排隊**,要等**網路恢復且分頁聚焦**兩者都成立(較晚者觸發)才一次
 * 放行 —— 曝險窗沒有時間上界,真錢限價單可能在幾小時後、完全不同的價位送出。而本系統 server 在同機
 * loopback(127.0.0.1),WiFi 斷了這條路還通,那個判斷與真實可達性完全不相干。改 `"always"` = 斷網時
 * 立刻失敗、不排隊;五個 mutation 點(送單 / 平倉 / 改價 / 刪單、自選 PUT、規則 upsert / delete、TXO series)
 * 全部是「立即失敗優於延遲放行」。
 *
 * **絕不能放進 `queries` 層**:TanStack `defaultQueryOptions` 會在 `refetchOnReconnect` 未設時把它算成
 * `networkMode !== "always"` —— 放錯層 = 全站輪詢 hook 重連後不重抓,零錯誤訊號。`query-client.test.tsx`
 * 釘住兩層。
 *
 * 呼叫端傳進來的 `mutations` **蓋不掉** `networkMode`(安全預設最後展開;pr-238 review F-09):
 * 其他 mutation 鍵(retry 等)照常由呼叫端決定。要關掉這道保護只能改這個檔,不能在呼叫端偷偷傳。
 */
const MUTATION_DEFAULTS = { networkMode: "always" } as const satisfies DefaultOptions["mutations"];

export function createQueryClient(defaults: DefaultOptions = {}): QueryClient {
  return new QueryClient({
    defaultOptions: {
      ...defaults,
      mutations: { ...defaults.mutations, ...MUTATION_DEFAULTS },
    },
  });
}
