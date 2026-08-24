import { useId, type ReactNode } from "react";

import { cn, safeIdToken } from "@/lib/utils";

/** 單選 pill 群的共用元件(a11y 批 D1' / D1'')。
 *
 *  改前每處都是 N 顆 `<button aria-pressed>`:AT 聽成 N 個互不相干的開關、鍵盤要按 N 次 Tab
 *  才穿得過一組 pill。改成**原生 radio**(視覺上藏起來的 `<input type="radio" class="sr-only">`
 *  + 帶原 button class 的 `<label>`)後,單選語意 / 方向鍵切換 / roving tabindex 全部由瀏覽器
 *  免費提供 —— 不自寫 key handler(自寫的版本永遠會漏 Home/End 或 RTL 方向)。
 *
 *  **視覺零變是硬約束**:label 的 class 由呼叫端 `pillClass(item, checked)` 逐字回傳原 button
 *  的 class,容器 class 由 `className` 逐字沿用原容器 —— DOM 每項一個 label ↔ 原每項一個 button,
 *  層數不變。唯一新增的外觀是 focus ring:sr-only 的 input 焦點框看不見,不補在 label 側的話
 *  鍵盤使用者完全看不到焦點。`ring-inset` 讓 `overflow-hidden` 容器內的 pill 不被裁掉。
 *
 *  `leading` / `trailing` 是**容器內**的非 radio 插槽(GroupGridView 的「群組」字、MarketPane
 *  週期列的「重疊」toggle):它們原本就在同一個容器裡,包一層 div 會改版面。 */
export interface RadioPillItem<V extends string> {
  value: V;
  label: ReactNode;
  disabled?: boolean;
  title?: string;
}

interface Props<V extends string> {
  ariaLabel: string;
  value: V;
  onChange: (value: V) => void;
  items: readonly RadioPillItem<V>[];
  /** 回傳該項在該狀態下的 class,**逐字沿用原 button**(含 disabled 態) */
  pillClass: (item: RadioPillItem<V>, checked: boolean) => string;
  /** 容器 class,逐字沿用原容器 */
  className?: string;
  leading?: ReactNode;
  trailing?: ReactNode;
  /** 「使用者點了這組 pill」的訊號,**每一次點 label 都發**(含點已選中的那顆)。
   *
   *  `onChange` 不夠用:原生 radio 點已選中項不發 change,而閃電梯用「有沒有在操作」
   *  重置武裝閒置計時(A11Y-6)—— 一直點同一顆的使用者會被判定閒置而解除武裝。
   *  停用項不觸發(原 `<button disabled>` 連 click 都不派)。 */
  onInteract?: () => void;
}

export function RadioPills<V extends string>({
  ariaLabel,
  value,
  onChange,
  items,
  pillClass,
  className,
  leading,
  trailing,
  onInteract,
}: Props<V>) {
  /** 同頁多組 pill(OrderPanel 兩組 / 圖牆與週期列)必須各自獨立的 `name`,
   *  否則原生 radio 會把它們當同一組互搶選取。
   *  `safeIdToken`:React 19 的 useId 是 «r0» 形態,含非識別字元。 */
  const uid = safeIdToken(useId());
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={className}>
      {leading}
      {items.map((item, i) => {
        const checked = item.value === value;
        /** **按 index 編號,不拼 value**:value 是呼叫端資料(合約鍵 / 使用者群組名),
         *  可能帶空白或標點 —— 拼出來的 id 不是合法 token,`querySelector("#…")` 與
         *  CSS 選擇器會直接語法錯誤,而畫面完全正常(靜默)。 */
        const id = `${uid}-${i}`;
        return (
          <label
            key={item.value}
            htmlFor={id}
            title={item.title}
            aria-disabled={item.disabled ? "true" : undefined}
            className={cn(
              pillClass(item, checked),
              // `<label>` 沒有 UA cursor / user-select 樣式:不補的話每顆 pill 都是
              // I-beam 游標、文字可被反白拖選 —— 原 `<button>` 兩者皆無(A11Y-3)。
              item.disabled ? "cursor-not-allowed" : "cursor-default select-none",
              "has-focus-visible:ring-1 has-focus-visible:ring-inset has-focus-visible:ring-accent",
            )}
          >
            <input
              type="radio"
              className="sr-only"
              name={uid}
              id={id}
              value={item.value}
              checked={checked}
              disabled={item.disabled}
              /** 「使用者還在操作」的訊號,**掛 input 不掛 label**(N265)。
               *
               *  掛 label 的話同一次點擊會跑兩趟:label activation 的預設行為是把 click
               *  **轉發**到被標記的控制項(這裡是內層 input),轉發出去的那則再冒泡回
               *  label → handler 第二次。現有讀者(閃電梯重置武裝閒置計時)冪等所以看不出來,
               *  但任何拿它計數 / 節流的呼叫端都會多算一倍。
               *
               *  掛 input 三條路徑各恰一次:點 label(轉發)/ 點到 input 本體 / 鍵盤選取
               *  (原生 radio 的鍵盤啟動同樣派 click 到 input)。`onChange` 不夠用的理由
               *  不變 —— 點已選中項不發 change(A11Y-6)。 */
              onClick={() => {
                if (item.disabled) return;
                onInteract?.();
              }}
              /** `disabled` 之外再擋一層:jsdom 的 `fireEvent.click` 會直接把 click 派到
               *  disabled input 上(真瀏覽器根本不派),React 由 click 推導 change 時不吃
               *  disabled 判別子 → 沒有這道 guard,測試環境與真環境對「停用項被點」的
               *  語意會不一致(原 `<button disabled>` 是不會觸發的)。 */
              onChange={() => {
                if (item.disabled) return;
                onChange(item.value);
              }}
              /** radio 的 Enter 沒有原生動作,但在 `<form>` 內會觸發 implicit submit ——
               *  OrderPanel 的 pill 就在 form 裡,焦點掃到它按 Enter 會直接跳確認窗。 */
              onKeyDown={(e) => {
                if (e.key === "Enter") e.preventDefault();
              }}
            />
            {item.label}
          </label>
        );
      })}
      {trailing}
    </div>
  );
}
