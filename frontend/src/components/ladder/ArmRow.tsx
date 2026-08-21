/** 閃電梯武裝列(武裝 / 解除 + 鎖定 / 鎖定中 + 商品別控制項)的唯一畫法。
 *
 *  兩座梯(`stock/LadderView` = 現股 / 個股期,`futures/FuturesLadder` = 期貨)原本各寫
 *  一份逐字相同的 JSX。**這一列是誤送風險最高的 UI**:武裝態的配色與鎖定態的字是使用者
 *  判斷「現在點價會不會真的送出去」的唯一訊號,兩份分開演化的失效樣態是「其中一梯的
 *  武裝態顏色沒跟上」—— 沒有任何測試會紅。
 *
 *  **差異一律走 props,不在元件內判梯別**:容器 `className`(gap 兩梯不同)、鎖定鈕
 *  是否存在(`onToggleLock` 未給 = 整顆不渲染)、`lockTitle`(期貨態會換成連線未就緒
 *  的說明)、右側 `children` slot(現股交易別 select / 個股期 + 期貨的當沖 checkbox)。
 *  加「if 期貨」分支就等於把兩份複本搬進同一個檔案,沒解決任何東西。
 *
 *  DOM 逐字受 `ArmRow.characterization.test.tsx` 的 outerHTML 字面量守著。 */
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function ArmRow({
  className,
  armed,
  armDisabled = false,
  armTitle,
  onToggleArm,
  locked = false,
  lockDisabled = false,
  lockTitle,
  onToggleLock,
  children,
}: {
  /** 容器 class(含 gap —— 兩梯不同,見檔頭) */
  className: string;
  armed: boolean;
  /** 進入武裝的阻擋理由(現股 blocked / 期貨合約未解析) */
  armDisabled?: boolean;
  armTitle?: string;
  onToggleArm: () => void;
  locked?: boolean;
  lockDisabled?: boolean;
  /** 鎖定鈕的 title;呼叫端負責選字(期貨態會在連線未就緒時換成另一句) */
  lockTitle?: string;
  /** 未給 = 鎖定鈕整顆不渲染(現股梯的部分呼叫端不帶鎖定) */
  onToggleLock?: () => void;
  /** 武裝鈕右側的商品別控制項(交易別 select / 當沖 checkbox) */
  children?: ReactNode;
}) {
  return (
    <div className={className}>
      <button
        type="button"
        aria-pressed={armed}
        /* disabled 只擋**進入**方向:已武裝時解除鈕恆可按,否則 blocked 契約上
           武裝態就沒有 UI 出口(change-spec review R2)。 */
        disabled={armDisabled && !armed}
        title={armTitle}
        onClick={onToggleArm}
        className={cn(
          // min-w-0:288px 右欄下與鎖定鈕 + 商品別控制項同列,長出去會把列擠換行
          "min-w-0 flex-1 rounded border px-2 py-1 text-xs font-bold",
          armed
            ? "border-loss bg-loss text-bg"
            : "border-line text-ink-dim hover:border-accent hover:text-ink",
          armDisabled && !armed && "opacity-40",
        )}
      >
        {armed ? "解除" : "武裝"}
      </button>
      {onToggleLock !== undefined ? (
        <button
          type="button"
          aria-pressed={locked}
          disabled={lockDisabled}
          title={lockTitle}
          onClick={onToggleLock}
          className={cn(
            // shrink-0:武裝鈕才是可壓縮的那顆 —— 鎖定鈕被壓到看不出字就等於沒有訊號
            "shrink-0 rounded border px-2 py-1 text-xs font-bold",
            locked
              ? "border-accent bg-accent text-bg"
              : "border-line text-ink-dim hover:border-accent hover:text-ink",
            lockDisabled && "opacity-40",
          )}
        >
          {locked ? "鎖定中" : "鎖定"}
        </button>
      ) : null}
      {children}
    </div>
  );
}
