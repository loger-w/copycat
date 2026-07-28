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

/** 群益寫入動作共用確認彈窗(刪改減/平倉/表單送單)。 */
export function CapitalConfirmDialog({
  title,
  rows,
  danger = false,
  onConfirm,
  onCancel,
}: CapitalConfirmDialogProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg/85 p-4"
    >
      <div className="w-full max-w-sm border border-line bg-bg-deep">
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
              type="button"
              onClick={onCancel}
              className="flex-1 border border-line px-3 py-2 text-sm text-ink-muted transition-colors hover:border-ink-dim hover:text-ink"
            >
              取消
            </button>
            <button
              type="button"
              onClick={onConfirm}
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
      </div>
    </div>
  );
}
