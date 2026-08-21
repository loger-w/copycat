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
 *  `null` = 不是本組按鍵,呼叫端不要 `preventDefault`。
 *
 *  參數吃**事件物件**(不只 `key`):修飾鍵組合是瀏覽器 / OS 的快捷鍵,不是 tablist 的
 *  —— Alt+←/→ 是上一頁 / 下一頁、Ctrl+Home/End 是捲到頁首 / 頁尾。只看 `key` 的話這些
 *  全被 tablist 吃掉(呼叫端拿到非 null 就 `preventDefault`),而使用者只會覺得
 *  「這個網站的上一頁壞了」。 */
export function tablistKeyAction(
  e: { key: string; altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean },
  index: number,
  count: number,
): number | "select" | null {
  if (e.altKey === true || e.ctrlKey === true || e.metaKey === true) return null;
  // Shift 不列入:Shift+方向鍵沒有與本組衝突的瀏覽器語意(且 Shift+Tab 走的是 Tab)。
  const key = e.key;
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
