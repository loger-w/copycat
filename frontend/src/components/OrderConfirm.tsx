/** @deprecated 2026-07-28 capital-order:TC4 TradeRuntime 停用,改群益 /api/capital;下輪清 */
import { orderSideText, shortSymbol } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { OrderPreviewResult } from "@/types";

interface OrderConfirmProps {
  preview: OrderPreviewResult;
  submitting: boolean;
  errorText: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

const ROW = "flex items-baseline justify-between gap-4";
const K = "text-xs text-ink-dim";
const V = "font-mono text-sm text-ink";

export function OrderConfirm({
  preview,
  submitting,
  errorText,
  onConfirm,
  onCancel,
}: OrderConfirmProps) {
  const { param } = preview;
  const isBuy = param.Side === "1";
  const isSim = preview.mode === "sim";
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="確認送單"
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg/85 p-4"
    >
      <div className="w-full max-w-sm border border-line bg-bg-deep p-5">
        <div className="mb-4 flex items-center justify-between border-b border-line pb-3">
          <h2 className="text-sm font-bold tracking-wide text-ink">確認送單</h2>
          <span
            className={cn(
              "px-2 py-0.5 text-xs",
              isSim ? "border border-accent text-accent" : "bg-loss font-bold text-bg",
            )}
          >
            {isSim ? "模擬" : "正式"}
          </span>
        </div>
        <dl className="space-y-2">
          <div className={ROW}>
            <dt className={K}>商品</dt>
            <dd className={V}>{shortSymbol(param.Symbol ?? "")}</dd>
          </div>
          <div className={ROW}>
            <dt className={K}>買賣</dt>
            <dd className={cn(V, isBuy ? "text-bull" : "text-bear")}>
              {orderSideText(param.Side ?? "")}
            </dd>
          </div>
          <div className={ROW}>
            <dt className={K}>類型</dt>
            <dd className={V}>{param.OrderType === "1" ? "市價" : "限價"}</dd>
          </div>
          {param.Price !== undefined && (
            <div className={ROW}>
              <dt className={K}>價格</dt>
              <dd className={V}>{param.Price}</dd>
            </div>
          )}
          <div className={ROW}>
            <dt className={K}>口數</dt>
            <dd className={V}>{param.OrderQty}</dd>
          </div>
          <div className={ROW}>
            <dt className={K}>帳戶</dt>
            <dd className={V}>{preview.account_masked}</dd>
          </div>
        </dl>
        {!isSim && (
          <p className="mt-3 border border-loss/40 bg-loss/10 px-2 py-1 text-xs text-loss">
            正式戶實單,送出即進市場
          </p>
        )}
        {errorText && <p className="mt-3 text-xs text-loss">{errorText}</p>}
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
            disabled={submitting}
            className={cn(
              "flex-1 border px-3 py-2 text-sm font-bold transition-colors",
              isBuy
                ? "border-bull text-bull hover:bg-bull/10"
                : "border-bear text-bear hover:bg-bear/10",
              submitting && "opacity-50",
            )}
          >
            {submitting ? "送出中…" : "確認送出"}
          </button>
        </div>
      </div>
    </div>
  );
}
