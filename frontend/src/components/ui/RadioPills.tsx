import { useId, type ReactNode } from "react";

import { cn } from "@/lib/utils";

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
}: Props<V>) {
  /** 同頁多組 pill(OrderPanel 兩組 / 圖牆與週期列)必須各自獨立的 `name`,
   *  否則原生 radio 會把它們當同一組互搶選取。 */
  const uid = useId();
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={className}>
      {leading}
      {items.map((item) => {
        const checked = item.value === value;
        return (
          <label
            key={item.value}
            htmlFor={`${uid}-${item.value}`}
            title={item.title}
            aria-disabled={item.disabled ? "true" : undefined}
            className={cn(
              pillClass(item, checked),
              item.disabled && "cursor-not-allowed",
              "has-focus-visible:ring-1 has-focus-visible:ring-inset has-focus-visible:ring-accent",
            )}
          >
            <input
              type="radio"
              className="sr-only"
              name={uid}
              id={`${uid}-${item.value}`}
              value={item.value}
              checked={checked}
              disabled={item.disabled}
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
