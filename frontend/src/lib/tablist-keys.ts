/** WAI-ARIA APG `tabs` 的鍵盤語意,**manual activation**:←/→/Home/End 只移焦點
 *  (roving tabindex),Enter / Space 才切換分頁。
 *
 *  為什麼不是 automatic activation(focus 即 select):RightRail 切 tab 會 unmount
 *  閃電梯 = 解除武裝(D-13),方向鍵掃過去就把使用者的武裝狀態洗掉,而畫面上只是
 *  「梯子閃了一下」—— 零錯誤訊號的真錢風險。App 主分頁同款處理,兩處語意一致。
 *
 *  抽成單一來源是因為兩處都要這段判斷,而「其中一處漏了 Home/End」這種漂移不會有
 *  任何畫面訊號,也不會有測試紅(各自的測試各自綠)。
 *
 *  回傳:`"select"` = 呼叫端該切換到當前這顆;數字 = 該把焦點移到第幾顆;
 *  `null` = 不是本組按鍵,呼叫端不要 `preventDefault`。 */
export function tablistKeyAction(
  key: string,
  index: number,
  count: number,
): number | "select" | null {
  // Enter / Space 在 `<button>` 上本來就會觸發原生 click;呼叫端一律 `preventDefault`
  // 後自己呼叫 select,兩條路徑合一(不 preventDefault 的話 Space 會既捲動又觸發)。
  if (key === "Enter" || key === " ") return "select";
  if (count <= 0) return null;
  if (key === "ArrowRight") return (index + 1) % count;
  if (key === "ArrowLeft") return (index - 1 + count) % count;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}
