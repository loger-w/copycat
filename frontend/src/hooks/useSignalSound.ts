/** 提示音開關的共用來源(design §8.3;SC-9/10)。
 *
 *  **為什麼要獨立於 `useSignalAlerts`**:切換鈕在個股頁的 SignalRail(左欄),
 *  真正會發聲的訂閱者卻是掛在 App 常駐的 `useSignalAlerts` —— 兩處各自 `useState`
 *  會漂(關掉後仍持續嗶到重新整理為止),從 App 一路 props 穿到 rail 又要動
 *  `StockPage` 的介面與全部既有測試。
 *
 *  真值就放在 localStorage、**每次直讀**(不快取模組變數):測試 `beforeEach` 清掉
 *  storage 後不會殘留上一個 it 的狀態,也不必為了測試而 reset 模組。訂閱者集合只用來
 *  通知同分頁的其他 hook 重讀。 */

import { useSyncExternalStore } from "react";

import { SOUND_KEY } from "@/lib/constants";
import { readLocal, writeLocal } from "@/lib/storage";

const subscribers = new Set<() => void>();

/** 預設開;storage 被鎖(隱私模式)時偏好設定不落檔,不是關掉音效。 */
export function getSoundOn(): boolean {
  return readLocal(SOUND_KEY) !== "off";
}

export function setSoundOn(next: boolean): void {
  // 寫入結果不看:`getSoundOn` 每次快照都重讀 storage,所以兩種失效態下(配額滿 / 政策鎖)
  // 通知都只會讓訂閱者讀回舊值、開關自己彈回去 —— 留著通知只是省一個分支,
  // 與 `lib/fee-discount.ts::persistDiscount` 早退的差別僅止於此,不是「真相在別的地方」。
  // 要讓開關在寫失敗時照使用者按的走得補 in-memory 覆寫,那是 change-spec §1 決定 6 的非目標。
  writeLocal(SOUND_KEY, next ? "on" : "off");
  for (const notify of [...subscribers]) notify();
}

function subscribe(notify: () => void): () => void {
  subscribers.add(notify);
  return () => {
    subscribers.delete(notify);
  };
}

/** `{ soundOn, setSoundOn }`:同分頁內任一處切換,其他訂閱者立即重讀。 */
export function useSignalSound(): { soundOn: boolean; setSoundOn: (value: boolean) => void } {
  // getSnapshot 回傳 boolean 純值 → 內容相同即引用相同,不會無限重繪
  const soundOn = useSyncExternalStore(subscribe, getSoundOn, getSoundOn);
  return { soundOn, setSoundOn };
}
