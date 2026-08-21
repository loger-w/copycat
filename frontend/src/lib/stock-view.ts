/** 個股頁中間主區的檢視(group-grid SC-3):單檔看盤 vs 群組 mini 圖牆。
 *
 *  **持有者仍是 StockPage**(localStorage 與切換函式都留在那邊);抽到 lib 只是為了讓
 *  App 能拿到**同一份**初值 —— 兩邊各寫一份「只認得 group」的判讀,漂掉的樣態是重開頁
 *  時 App 以為在單檔、畫面卻停在群組(於是照樣拖回整份 tape),而畫面上零訊號。 */

import { STOCK_VIEW_KEY } from "@/lib/constants";

export type StockView = "single" | "group";

/** 只認得 `"group"`,其餘(未設 / 被人手動改壞 / 舊版遺留值)一律回單檔 ——
 *  預設檢視必須是「有主圖」的那個,壞值把使用者丟進群組檢視會像整頁不見了。 */
export function readStockView(): StockView {
  try {
    return window.localStorage.getItem(STOCK_VIEW_KEY) === "group" ? "group" : "single";
  } catch {
    return "single";
  }
}
