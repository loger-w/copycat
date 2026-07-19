import { useState } from "react";

import { OrderConfirm } from "@/components/OrderConfirm";
import { OrdersList } from "@/components/OrdersList";
import { useConfirmOrder, useOrders, usePreviewOrder, useTradeAccount } from "@/hooks/useTrade";
import { tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { OrderPreviewResult } from "@/types";

const FIELD =
  "w-full rounded-sm border border-line bg-bg-deep px-2.5 py-1.5 font-mono text-sm text-ink focus:border-accent focus:outline-none";

// status → 送單鈕 disabled 原因(edge case 1/2/閘一,繁中可區分)
const BLOCKED_REASON: Record<string, string> = {
  touchance_down: "達錢未連線",
  no_account: "請在達錢 4 登入交易帳號",
  live_blocked: "正式戶未啟用(DQ4_LIVE)",
};

function shortSymbol(symbol: string): string {
  return symbol.replace(/^TC\.[FO]\.TWF\./, "");
}

export function OrderPanel() {
  const account = useTradeAccount();
  const orders = useOrders();
  const preview = usePreviewOrder();
  const confirm = useConfirmOrder();

  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [kind, setKind] = useState<"limit" | "market">("limit");
  const [qty, setQty] = useState("1");
  const [price, setPrice] = useState("");
  const [pending, setPending] = useState<OrderPreviewResult | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const info = account.data;
  const symbols = info?.orderable_symbols ?? [];
  const selected = symbol || symbols[0] || "";
  const status = info?.status ?? "loading";
  const blockedReason =
    account.error != null
      ? tradeErrorText(account.error.message)
      : BLOCKED_REASON[status] ?? (info == null ? "交易狀態載入中…" : null);
  const qtyNum = Number.parseInt(qty, 10);
  const formInvalid =
    selected === "" ||
    !Number.isFinite(qtyNum) ||
    qtyNum < 1 ||
    (kind === "limit" && price.trim() === "");
  const disabled = blockedReason != null || formInvalid || preview.isPending;

  const handlePreview = () => {
    setNotice(null);
    setSubmitError(null);
    preview.mutate(
      {
        symbol: selected,
        side,
        kind,
        qty: qtyNum,
        price: kind === "limit" ? price.trim() : null,
      },
      { onSuccess: (result) => setPending(result) },
    );
  };

  const handleConfirm = () => {
    if (pending == null) return;
    confirm.mutate(pending.preview_id, {
      onSuccess: (result) => {
        setPending(null);
        confirm.reset();
        setNotice(`已送出(單號 ${result.request_id.slice(0, 8)}),回報見下方列表`);
      },
      onError: (err) => {
        // preview_id 已被 server 消耗(一次性),留在 dialog 重試注定失敗(review A1)
        setPending(null);
        confirm.reset();
        setSubmitError(`${tradeErrorText(err.message)},請重新送單`);
      },
    });
  };

  const handleCancel = () => {
    setPending(null);
    confirm.reset();
  };

  const isSim = info?.mode !== "live";

  return (
    <section className="@container border-t border-line pt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <h2 className="text-sm font-bold tracking-wide text-ink">手動下單</h2>
          {info?.mode != null && (
            <span
              className={cn(
                "px-2 py-0.5 text-xs",
                isSim ? "border border-accent text-accent" : "bg-loss font-bold text-bg",
              )}
            >
              {isSim ? "模擬" : "正式"}
            </span>
          )}
          {info?.account_masked != null && (
            <span className="font-mono text-xs text-ink-dim">{info.account_masked}</span>
          )}
        </div>
        {info?.audit_degraded && <span className="text-xs text-loss">審計記錄異常</span>}
      </div>

      <div className="grid gap-5 @[720px]:grid-cols-[minmax(250px,300px)_1fr]">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            handlePreview();
          }}
        >
          <label className="block text-xs text-ink-muted">
            商品
            <select
              aria-label="商品"
              value={selected}
              onChange={(e) => setSymbol(e.target.value)}
              className={cn(FIELD, "mt-1")}
            >
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {shortSymbol(s)}
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-2" role="group" aria-label="買賣別">
            <button
              type="button"
              aria-pressed={side === "buy"}
              onClick={() => setSide("buy")}
              className={cn(
                "border px-3 py-1.5 text-sm transition-colors",
                side === "buy"
                  ? "border-bull bg-bull/15 font-bold text-bull"
                  : "border-line text-ink-dim hover:text-bull",
              )}
            >
              買進
            </button>
            <button
              type="button"
              aria-pressed={side === "sell"}
              onClick={() => setSide("sell")}
              className={cn(
                "border px-3 py-1.5 text-sm transition-colors",
                side === "sell"
                  ? "border-bear bg-bear/15 font-bold text-bear"
                  : "border-line text-ink-dim hover:text-bear",
              )}
            >
              賣出
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2" role="group" aria-label="委託類型">
            <button
              type="button"
              aria-pressed={kind === "limit"}
              onClick={() => setKind("limit")}
              className={cn(
                "border px-3 py-1.5 text-sm transition-colors",
                kind === "limit"
                  ? "border-accent text-accent"
                  : "border-line text-ink-dim hover:text-ink",
              )}
            >
              限價
            </button>
            <button
              type="button"
              aria-pressed={kind === "market"}
              onClick={() => setKind("market")}
              className={cn(
                "border px-3 py-1.5 text-sm transition-colors",
                kind === "market"
                  ? "border-accent text-accent"
                  : "border-line text-ink-dim hover:text-ink",
              )}
            >
              市價
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="block text-xs text-ink-muted">
              口數
              <input
                aria-label="口數"
                type="number"
                min={1}
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                className={cn(FIELD, "mt-1")}
              />
            </label>
            {kind === "limit" && (
              <label className="block text-xs text-ink-muted">
                價格(點)
                <input
                  aria-label="價格(點)"
                  inputMode="decimal"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  placeholder="15.5"
                  className={cn(FIELD, "mt-1")}
                />
              </label>
            )}
          </div>

          <button
            type="submit"
            disabled={disabled}
            className={cn(
              "w-full border px-3 py-2 text-sm font-bold transition-colors",
              side === "buy"
                ? "border-bull text-bull hover:bg-bull/10"
                : "border-bear text-bear hover:bg-bear/10",
              disabled && "cursor-not-allowed opacity-40",
            )}
          >
            {preview.isPending ? "預覽中…" : "送單(預覽)"}
          </button>

          {blockedReason != null && <p className="text-xs text-loss">{blockedReason}</p>}
          {preview.error != null && (
            <p className="text-xs text-loss">{tradeErrorText(preview.error.message)}</p>
          )}
          {submitError != null && <p className="text-xs text-loss">{submitError}</p>}
          {notice != null && <p className="text-xs text-accent">{notice}</p>}
        </form>

        <OrdersList view={orders.data} />
      </div>

      {pending != null && (
        <OrderConfirm
          preview={pending}
          submitting={confirm.isPending}
          errorText={confirm.error != null ? tradeErrorText(confirm.error.message) : null}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </section>
  );
}
