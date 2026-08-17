import { useState } from "react";

import { CapitalConfirmDialog } from "@/components/capital/CapitalConfirmDialog";
import {
  useCancelOrder,
  useCapitalOrders,
  useCapitalStatus,
  useCorrectPrice,
  useDecreaseQty,
} from "@/hooks/useCapital";
import { tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { CapitalMarket, CapitalOrder } from "@/types";

/** 群益市場碼的期貨家族(OrderRecord.market;其餘含 null 歸證券)。 */
const FUT_MARKETS = new Set(["TF", "TO", "OF", "OO"]);

export function isFutMarket(market: string | null): boolean {
  return market !== null && FUT_MARKETS.has(market);
}

type PendingAction =
  | { kind: "cancel" }
  | { kind: "correct_price"; price: number }
  | { kind: "decrease"; qty: number };

const GRID = "grid grid-cols-[1fr_auto_auto_auto_auto] items-baseline gap-x-3";

/** 委託列表(market 過濾)+ 活單 改價/減量/刪單(確認彈窗必經;結果靠回報刷新)。 */
export function CapitalOrdersList({ market }: { market: CapitalMarket }) {
  const { data } = useCapitalOrders();
  const status = useCapitalStatus();
  const cancelOrder = useCancelOrder();
  const correctPrice = useCorrectPrice();
  const decreaseQty = useDecreaseQty();

  const danger = status.data?.env === "prod";
  const busy = cancelOrder.isPending || correctPrice.isPending || decreaseQty.isPending;
  // 操作失敗顯示錯誤列(400 BROKER_REJECTED 等;review A2);下次操作前 reset 清除
  const actionError = cancelOrder.error ?? correctPrice.error ?? decreaseQty.error;
  const orders = (data?.orders ?? []).filter(
    (o) => (market === "fut") === isFutMarket(o.market),
  );

  function runAction(action: () => void): void {
    cancelOrder.reset();
    correctPrice.reset();
    decreaseQty.reset();
    action();
  }

  if (orders.length === 0) {
    return <p className="py-3 text-center text-xs text-ink-dim">無委託</p>;
  }
  return (
    <ul className="min-w-0">
      <li className={cn(GRID, "border-b border-line pb-1 text-xs text-ink-dim")}>
        <span>代號</span>
        <span>買賣</span>
        <span>價格</span>
        <span>數量</span>
        <span className="text-right">狀態</span>
      </li>
      {actionError !== null && (
        <li className="border-b border-line/60 py-1 text-xs text-loss">
          {tradeErrorText(actionError.message)}
        </li>
      )}
      {orders.map((o) => (
        <OrderRow
          key={o.seq_no}
          order={o}
          danger={danger}
          busy={busy}
          onCancel={() => runAction(() => cancelOrder.mutate({ seq_no: o.seq_no, market }))}
          onCorrectPrice={(price) =>
            runAction(() => correctPrice.mutate({ seq_no: o.seq_no, market, price }))
          }
          onDecrease={(qty) => runAction(() => decreaseQty.mutate({ seq_no: o.seq_no, market, qty }))}
        />
      ))}
    </ul>
  );
}

interface OrderRowProps {
  order: CapitalOrder;
  danger: boolean;
  busy: boolean;
  onCancel: () => void;
  onCorrectPrice: (price: number) => void;
  onDecrease: (qty: number) => void;
}

function OrderRow({ order, danger, busy, onCancel, onCorrectPrice, onDecrease }: OrderRowProps) {
  const [editing, setEditing] = useState(false);
  const [price, setPrice] = useState("");
  const [decQty, setDecQty] = useState("");
  const [pending, setPending] = useState<PendingAction | null>(null);

  const isBuy = order.buy_sell === "B";
  const title = `${order.stock_no ?? ""} ${order.name}`.trim();
  const priceText = order.price !== null ? String(order.price) : "—";
  const qtyText = `${order.filled_qty}/${order.order_qty} ${order.unit}`;
  // 價格允許小數(後端 %.2f);減量必須正整數(小數會被 pydantic 422 短路,不留審計)
  const priceOk = /^\d+(\.\d+)?$/.test(price.trim()) && Number(price) > 0;
  const decOk = /^\d+$/.test(decQty.trim()) && Number(decQty) > 0;

  function confirm(): void {
    if (pending === null) return;
    if (pending.kind === "cancel") onCancel();
    else if (pending.kind === "correct_price") onCorrectPrice(pending.price);
    else onDecrease(pending.qty);
    setPending(null);
    setEditing(false);
  }

  const dialogTitle =
    pending?.kind === "cancel" ? "確認刪單" : pending?.kind === "correct_price" ? "確認改價" : "確認減量";
  const actionText =
    pending === null
      ? ""
      : pending.kind === "cancel"
        ? "刪單"
        : pending.kind === "correct_price"
          ? `改價 → ${pending.price}`
          : `減量 ${pending.qty} ${order.unit}`;

  return (
    <li className="border-b border-line/60 py-1.5 font-mono text-xs">
      <div className={GRID}>
        <span className="truncate text-ink">{title}</span>
        <span className={cn(isBuy ? "text-bull" : "text-bear")}>{isBuy ? "買" : "賣"}</span>
        <span className="text-ink">
          {/* 市價單的 price 欄印的是**閘用估價**,與限價單的委託價長得一模一樣 ——
              沒有標籤就無從分辨這張單會掃到什麼價。緊湊前綴不換行(288px 右欄下
              標的名仍要可辨,review R12);非本 app 送出 / 跨日的單恆 null → 不標。 */}
          {order.price_type === "market" && (
            <span
              data-testid="order-market-tag"
              title="市價單"
              className="mr-0.5 text-[10px] leading-none text-ink-muted"
            >
              市價
            </span>
          )}
          {priceText}
        </span>
        <span className="text-ink-muted">{qtyText}</span>
        <span className={cn("text-right", order.error_msg ? "text-loss" : "text-ink-muted")}>
          {order.status_label ?? order.status_raw ?? "—"}
        </span>
      </div>
      {order.error_msg && <p className="mt-0.5 text-xs text-loss">{order.error_msg}</p>}

      {order.actionable && (
        <div className="mt-1.5 flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => setPending({ kind: "cancel" })}
            className="border border-line px-2 py-0.5 text-ink-muted transition-colors hover:border-loss hover:text-loss disabled:opacity-40"
          >
            刪單
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setEditing((v) => !v)}
            className="border border-line px-2 py-0.5 text-ink-muted transition-colors hover:border-ink-dim hover:text-ink disabled:opacity-40"
          >
            改
          </button>
        </div>
      )}

      {editing && order.actionable && (
        <div className="mt-2 space-y-1.5 border border-line p-2">
          <div className="flex items-center gap-2">
            <span className="w-8 shrink-0 text-ink-dim">改價</span>
            <input
              aria-label="改價"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              inputMode="decimal"
              placeholder={priceText}
              className="w-full min-w-0 border border-line bg-bg-deep px-2 py-1 text-ink outline-none focus:border-accent"
            />
            <button
              type="button"
              aria-label="送出改價"
              disabled={!priceOk || busy}
              onClick={() => setPending({ kind: "correct_price", price: Number(price) })}
              className="shrink-0 border border-line px-2 py-1 text-ink-muted disabled:opacity-40"
            >
              送出
            </button>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-8 shrink-0 text-ink-dim">減量</span>
            <input
              aria-label="減量"
              value={decQty}
              onChange={(e) => setDecQty(e.target.value)}
              inputMode="numeric"
              placeholder={order.unit}
              className="w-full min-w-0 border border-line bg-bg-deep px-2 py-1 text-ink outline-none focus:border-accent"
            />
            <button
              type="button"
              aria-label="送出減量"
              disabled={!decOk || busy}
              onClick={() => setPending({ kind: "decrease", qty: Number(decQty) })}
              className="shrink-0 border border-line px-2 py-1 text-ink-muted disabled:opacity-40"
            >
              送出
            </button>
          </div>
        </div>
      )}

      {pending !== null && (
        <CapitalConfirmDialog
          title={dialogTitle}
          rows={[
            { label: "代號", value: title },
            { label: "原委託", value: `${priceText} · ${qtyText}` },
            { label: "動作", value: actionText },
          ]}
          danger={danger}
          onConfirm={confirm}
          onCancel={() => setPending(null)}
        />
      )}
    </li>
  );
}
