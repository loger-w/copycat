/** ref 與 state 的**單一出口**(N119)。
 *
 *  常駐 WS hook 的 handler 是 deps `[]` 的閉包,讀不到最新 state → merge 基底改由 ref 取。
 *  正確性條件只有一條:**寫 state 的每一個地方都要當場把同一份值寫進 ref**,否則同一個
 *  macrotask 內的下一則訊息(或 commit 前抵達的增量)會拿到上一次 commit 的舊基底,
 *  把剛併進去的那一格靜默抹掉。
 *
 *  兩行為什麼要包成函式:漏掉其中一行不會有任何訊號(tsc / lint / 畫面都正常,只有
 *  「偶爾少一格」),而分開寫的兩行沒有任何機制強制它們成對出現。包起來之後
 *  「寫 ref」與「setState」不可能只做一半,grep 這個名字也就等於 grep 全部寫入點。
 *
 *  **不接受 updater function**:`SetStateAction<T>` 的 updater 形式算得出新值的時機在
 *  React 內部,helper 拿不到那個值就沒法同步寫 ref —— 型別上收成 `T`,讓「想用 updater」
 *  在編譯期就撞牆,而不是執行期靜默寫進一個 function。 */
import type { Dispatch, RefObject, SetStateAction } from "react";

export function commitRef<T>(
  ref: RefObject<T>,
  setState: Dispatch<SetStateAction<T>>,
  next: T,
): void {
  ref.current = next;
  setState(next);
}
