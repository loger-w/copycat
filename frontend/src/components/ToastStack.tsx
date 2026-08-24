/** 訊號 toast 疊層(design §8.3;SC-10)。
 *
 *  **純展示**:toast 的產生 / TTL / 上限與溢出計數全在 `useSignalAlerts`,這裡只畫。
 *  掛在 App 常駐(與 tab 無關)—— 訊號涵蓋整個自選池,人在看期貨頁時個股鎖漲停
 *  一樣要跳出來。 */

import type { SignalToast } from "@/hooks/useSignalAlerts";

interface Props {
  toasts: SignalToast[];
  /** 超出同時顯示上限的則數(0 = 沒有溢出)。 */
  overflow: number;
  onDismiss: (key: string) => void;
}

export function ToastStack({ toasts, overflow, onDismiss }: Props) {
  // 沒有東西可顯示就整個不掛:fixed 容器留在 DOM 會蓋在右上角的元件上(pointer-events
  // 雖可繞開,但空盒子壓版面的坑本專案踩過 —— 見 CLAUDE.md §8 dialog 條目)
  if (toasts.length === 0 && overflow === 0) return null;
  return (
    <div
      data-testid="toast-stack"
      aria-live="polite"
      className="pointer-events-none fixed right-3 top-3 z-50 flex w-72 flex-col gap-1"
    >
      {toasts.map((t) => (
        <button
          key={t.key}
          type="button"
          // 整則可點即關(design §8.3):5s 自動消失之外的手動出口,不另設 × 小鈕
          onClick={() => onDismiss(t.key)}
          // `line-clamp-2 break-words`(比照 B3 的 SignalRail 合併列):合併 toast 的文案是
          // 「代號 名稱 <kind 段以「・」串接> 價格」,同一 tick 併進三四則時會把這張 w-72 的
          // 卡片撐成一整片,把下面幾張擠出視窗。clamp 是**縱向**的事,寬度不變。
          className="pointer-events-auto line-clamp-2 rounded border border-accent/60 bg-bg-deep px-2 py-1 text-left font-mono text-sm break-words text-ink shadow-lg hover:border-accent"
        >
          {t.text}
        </button>
      ))}
      {overflow > 0 ? (
        <div className="pointer-events-none rounded border border-line bg-bg-deep px-2 py-0.5 text-center font-mono text-xs text-ink-dim">
          +{overflow}
        </div>
      ) : null}
    </div>
  );
}
