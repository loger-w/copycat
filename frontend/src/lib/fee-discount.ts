/** 手續費折數的存取(自 `components/stock/PriceLadder.tsx` 搬出,**行為零變更**)。
 *
 *  折數原本是閃電梯的元件內私有 loader;自選列 / 單檔 header / 群組卡要算出「與梯上
 *  同一個含費稅損益」就得讀同一個來源 —— localStorage key 仍是唯一真相,只是讀者變多。
 */
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

export function persistDiscount(value: number): void {
  try {
    window.localStorage.setItem(FEE_DISCOUNT_KEY, String(value));
  } catch {
    // 存不進去就算了 —— 折數不落檔遠好於看盤畫面崩掉(同 useChartToggles::persist)
  }
}

/** 只要計算用的折數值(不需要輸入框的原始字串)。 */
export function readFeeDiscount(): number {
  return loadDiscount().value;
}
