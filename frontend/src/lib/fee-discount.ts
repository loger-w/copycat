/** 手續費折數的存取(自 `components/stock/PriceLadder.tsx` 搬出,**行為零變更**)。
 *
 *  折數原本是閃電梯的元件內私有 loader;自選列 / 單檔 header / 群組卡要算出「與梯上
 *  同一個含費稅損益」就得讀同一個來源 —— localStorage key 仍是唯一真相,只是讀者變多。
 */
import { useRef, useState, useSyncExternalStore } from "react";

import { FEE_DISCOUNT_KEY } from "@/lib/constants";
import { clampDiscount, FEE_DISCOUNT_DEFAULT } from "@/lib/ladder-position";

export interface DiscountState {
  /** 受控輸入的原始值,可暫時為空 / 非法 —— 不吃掉使用者打到一半的按鍵。 */
  raw: string;
  /** 最後一次通過 clampDiscount 的值;計算恆用它。 */
  value: number;
}

/** 讀存檔折數。**整段包 try/catch**:localStorage 在私密視窗 / storage 被政策鎖時
 *  光是存取就會拋,而這是 useState initializer —— 拋出去就是閃電梯首次 render 掛掉
 *  (同 `hooks/useChartToggles.ts::load`)。 */
export function loadDiscount(): DiscountState {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(FEE_DISCOUNT_KEY);
  } catch {
    raw = null; // 讀不到 → 走預設,記憶體內照常運作
  }
  const value = clampDiscount(raw ?? "") ?? FEE_DISCOUNT_DEFAULT;
  return { raw: String(value), value };
}

/** 同分頁的訂閱者。**localStorage 本身不會對寫入它的那個分頁發 `storage` 事件** ——
 *  閃電梯改完折數後,同一頁的自選列 / 群組卡 / header 收不到任何通知,畫面上會有
 *  兩個口徑的損益並存(而且看不出哪個是舊的)。 */
const listeners = new Set<() => void>();

export function persistDiscount(value: number): void {
  try {
    window.localStorage.setItem(FEE_DISCOUNT_KEY, String(value));
  } catch {
    // 存不進去就算了 —— 折數不落檔遠好於看盤畫面崩掉(同 useChartToggles::persist)。
    // 寫失敗就沒有新值可通知:通知了只會讓訂閱者再讀一次舊值,白跑一輪。
    return;
  }
  // 快照複本:訂閱者在通知中退訂(元件卸載)會邊迭代邊改集合
  for (const notify of [...listeners]) notify();
}

/** 只要計算用的折數值(不需要輸入框的原始字串)。 */
export function readFeeDiscount(): number {
  return loadDiscount().value;
}

/** `useSyncExternalStore` 的 subscribe 必須是穩定參照(每 render 換一個會讓 React
 *  每輪重訂閱)→ 放模組層。`storage` 事件負責別的分頁改折數的情形。 */
function subscribe(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

/**
 * 計算用折數,外部變更會觸發重畫。
 *
 * **為什麼是 `useSyncExternalStore` 而不是元件各自 `useState(readFeeDiscount)`**:
 * localStorage 是元件樹之外的可變狀態,複製進 state 就得自己維護同步(而漏同步的
 * 症狀是「梯上 3 折、側欄還是 1.8 折」這種靜默錯值)。getSnapshot 回的是 primitive
 * number,React 以 Object.is 比對 —— 每次 render 讀一次 localStorage 不會造成迴圈。
 *
 * SSR 快照回預設值:本專案沒有 SSR,但 `useSyncExternalStore` 的型別要求給一個,
 * 而「伺服器上沒有 localStorage」的正確答案就是預設折數。
 */
export function useFeeDiscount(): number {
  return useSyncExternalStore(subscribe, readFeeDiscount, () => FEE_DISCOUNT_DEFAULT);
}

/**
 * 折數輸入框(受控)+ 計算值,兩者的同步規則收在這裡(N067)。
 *
 * **計算值走 store**:輸入框原本是元件內 `useState(loadDiscount)`,只在掛載時讀一次 ——
 * 另一分頁改折數時,同頁的自選列 / header / 群組卡(都吃 `useFeeDiscount`)會跟著換,
 * 唯獨閃電梯的框與計算停在舊值,同一畫面上兩個折數並存而看不出哪個才對。
 *
 * **`raw` 仍是本地 state**:store 只存得下合法的 number,把 raw 也交出去會吃掉使用者
 * 打到一半的按鍵(打「2.50」→ clamp 成 2.5 → 框在游標底下被改成 `2.5`)。
 * 兩者的同步**只走一個方向**:外部值變了(≠ 自己剛寫進去的那個)才覆寫 raw。
 * `lastWrite` 就是「這一輪是不是自己寫的」的判別子。
 */
export function useFeeDiscountField(): {
  /** 受控輸入的原始字串(可暫時非法) */
  raw: string;
  /** 計算用折數(恆合法) */
  value: number;
  /** 輸入框 onChange:更新 raw,合法即 persist(並通知其他讀者) */
  onRawChange: (raw: string) => void;
} {
  const value = useSyncExternalStore(subscribe, readFeeDiscount, () => FEE_DISCOUNT_DEFAULT);
  const [raw, setRaw] = useState<string>(() => String(value));
  const lastWrite = useRef<number>(value);
  const [prev, setPrev] = useState<number>(value);
  if (prev !== value) {
    // render 期間調整 state 的官方 pattern(專案有 react-you-might-not-need-an-effect lint)
    setPrev(value);
    if (value !== lastWrite.current) setRaw(String(value));
  }
  return {
    raw,
    value,
    onRawChange: (next: string) => {
      setRaw(next);
      const v = clampDiscount(next);
      if (v === null) return; // 非法值只更新 raw(不吃掉按鍵),計算沿用 store 內上一個合法值
      // 先記再寫:persistDiscount 會同步通知本元件,旗標晚一步的話這一輪會被當成
      // 「外部改動」把 raw 覆寫掉
      lastWrite.current = v;
      persistDiscount(v);
    },
  };
}
