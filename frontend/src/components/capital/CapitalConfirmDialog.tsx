import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

export interface ConfirmRow {
  label: string;
  value: string;
}

interface CapitalConfirmDialogProps {
  title: string;
  rows: ReadonlyArray<ConfirmRow>;
  /** 正式環境警示:標題列紅底(bg-loss)。 */
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 群益寫入動作共用確認彈窗(刪改減/平倉/表單送單)。
 *
 *  原生 `<dialog>` + `showModal()`:focus trap / 背景 inert 由瀏覽器提供。
 *  caller 契約 = 條件掛載(mount = 開窗、unmount = 關窗,無 open prop);
 *  Esc / 原生 close 一律等同按一次「取消」,任何路徑都不可能觸發 onConfirm。
 */
export function CapitalConfirmDialog({
  title,
  rows,
  danger = false,
  onConfirm,
  onCancel,
}: CapitalConfirmDialogProps) {
  const dlgRef = useRef<HTMLDialogElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const openerRef = useRef<Element | null>(null);
  /** settled 旗標:按過任一顆鈕(或 Esc)之後,原生 cancel/close 不再補發 onCancel —
   *  堵「點確認送單後、caller 卸載前按 Esc → UI 誤導成已取消但單已送出」。一次性不重置
   *  (前提:4 個 caller 的 onConfirm/onCancel 路徑皆卸載本元件)。 */
  const closedRef = useRef(false);

  // 開窗只走這一條路徑(掛載 = 開):showModal 不進 render(commit 的 open 屬性會讓
  // showModal 拋 InvalidStateError);`!el.open` 前置不可省 — StrictMode double-invoke
  // 下第二輪對已 open 元素 showModal 依標準必拋(同 WatchlistManagerDialog 教訓)。
  // jsdom 26 的 HTMLDialogElement 無 showModal → fallback 手動設 open attribute。
  useEffect(() => {
    const el = dlgRef.current;
    if (el === null) return;
    // ??= 防 StrictMode 第二輪把已聚焦的取消鈕誤記為 opener。
    openerRef.current ??= document.activeElement;
    if (typeof el.showModal === "function") {
      if (!el.open) el.showModal();
    } else if (!el.open) {
      el.setAttribute("open", "");
    }
    // showModal 的 focusing steps 找不到 autofocus attribute(React 的 autoFocus 不落
    // DOM)會把 focus 移到 dialog 本體 → 必須在 showModal 之後 imperative 指定。
    // 落在「取消」是刻意:真錢窗,Enter 不可直達送單。
    cancelRef.current?.focus();
    // cleanup 只還 focus,不呼叫 close():dialog removing steps 不執行 close 演算法
    // (原生不歸還 focus,得自己做),而 cleanup 內 close() 會在「確認」路徑的卸載時序
    // 噴 close 事件、誤呼 onCancel。preventScroll:FuturesLadder 的平倉鈕在自動跟隨
    // 置中的階梯內,關窗瞬間 scroll-into-view 會拉走使用者盯的價位帶。
    return () => {
      const opener = openerRef.current;
      if (opener instanceof HTMLElement && opener.isConnected && opener !== document.body) {
        opener.focus({ preventScroll: true });
      }
    };
  }, []);

  function requestCancel(): void {
    if (closedRef.current) return;
    closedRef.current = true;
    onCancel();
  }

  return (
    <dialog
      ref={dlgRef}
      aria-label={title}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          // 不外洩到 window 層監聽(FuturesLadder 武裝中的 Escape=disarm):窗開著時
          // Esc 只作用於窗。原生 cancel 預設行為不受 stopPropagation 影響,由下方
          // onCancel preventDefault 另擋。
          e.stopPropagation();
          requestCancel();
        }
      }}
      onCancel={(e) => {
        // 關閉一律由 React unmount 驅動,不讓原生 close 先把元素關掉。
        e.preventDefault();
        requestCancel();
      }}
      // 原生 close 的 backstop:任何漏接的關閉路徑都拉回 caller 卸載(requestCancel
      // 有 closedRef 去重,真瀏覽器 Esc 的 keydown+cancel/close 雙路徑只發一次)。
      onClose={() => {
        requestCancel();
      }}
      // m-auto 抵 Tailwind preflight 的 margin:0(否則貼左上角);text-ink 抵 UA 的
      // color:canvastext;刻意不帶任何 display utility — author 層 display 會蓋掉
      // UA 的 `dialog:not([open]){display:none}`(關閉的空盒佔版面那個 bug)。
      className="m-auto w-full max-w-sm border border-line bg-bg-deep p-0 text-ink backdrop:bg-bg/85"
    >
      <div
        className={cn(
          "flex items-center justify-between border-b border-line px-5 py-3",
          danger && "bg-loss",
        )}
      >
        <h2 className={cn("text-sm font-bold tracking-wide", danger ? "text-bg" : "text-ink")}>
          {title}
        </h2>
        {danger && <span className="text-xs font-bold text-bg">正式</span>}
      </div>
      <div className="p-5">
        <dl className="space-y-2">
          {rows.map((row) => (
            <div key={row.label} className="flex items-baseline justify-between gap-4">
              <dt className="text-xs text-ink-dim">{row.label}</dt>
              <dd className="font-mono text-sm text-ink">{row.value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-5 flex gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={() => {
              // 直呼在前、旗標在後:呼叫次數與順序跟舊版逐 click 直呼完全一致,
              // 旗標只擋「之後」的 Esc/close 補發。
              onCancel();
              closedRef.current = true;
            }}
            className="flex-1 border border-line px-3 py-2 text-sm text-ink-muted transition-colors hover:border-ink-dim hover:text-ink"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => {
              onConfirm();
              closedRef.current = true;
            }}
            className={cn(
              "flex-1 border px-3 py-2 text-sm font-bold transition-colors",
              danger
                ? "border-loss text-loss hover:bg-loss/10"
                : "border-accent text-accent hover:bg-accent/10",
            )}
          >
            確認
          </button>
        </div>
      </div>
    </dialog>
  );
}
