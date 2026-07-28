import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { CapitalConfirmDialog } from "@/components/capital/CapitalConfirmDialog";
import { CapitalOrdersList } from "@/components/capital/CapitalOrdersList";
import { useCapitalStatus, useSubmitFuture } from "@/hooks/useCapital";
import { shortSymbol, tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { ContractRow } from "@/types";

const FIELD =
  "w-full rounded-sm border border-line bg-bg-deep px-2.5 py-1.5 font-mono text-sm text-ink focus:border-accent focus:outline-none";

/** TXO 契約乘數(元/點;review R9)— 預估權利金 = 價 × 口 × 50。 */
const TXO_MULTIPLIER = 50;

// status → 送單鈕 disabled 原因(文案由錯誤碼對照導出,單一來源;degraded 不在此 = 不鎖)
const STATUS_BLOCKED: Record<string, string> = {
  disabled: tradeErrorText("CAPITAL_DISABLED"),
  error: tradeErrorText("CAPITAL_DOWN"),
  starting: tradeErrorText("CAPITAL_NOT_READY"),
};

/** Active 序列全鏈合約(Task 16b;snapshot.contracts 僅當日成交子集,選單要全鏈)。 */
function useTxoContracts() {
  return useQuery({
    queryKey: ["txo-contracts"],
    queryFn: async () => {
      const res = await fetch("/api/txo/contracts");
      if (!res.ok) throw new Error(`HTTP_${res.status}`);
      return (await res.json()) as { contracts: string[] };
    },
    refetchInterval: 30_000,
    retry: 1,
  });
}

export function OrderPanel({ contracts }: { contracts?: ContractRow[] }) {
  const status = useCapitalStatus();
  const submit = useSubmitFuture();
  const chain = useTxoContracts();

  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [kind, setKind] = useState<"limit" | "market">("limit");
  const [qty, setQty] = useState("1");
  const [price, setPrice] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const info = status.data;
  // 商品清單主來源 = /api/txo/contracts 全鏈;失敗或空列表 fallback snapshot contracts(子集)
  const chainSymbols = chain.data?.contracts ?? [];
  const symbols = chainSymbols.length > 0 ? chainSymbols : (contracts ?? []).map((c) => c.symbol);
  const selected = symbol || symbols[0] || "";
  // 市價閘用估價 = 該合約最近成交價(snapshot last_price);缺值 → 鎖市價選項
  const marketEstimate = (contracts ?? []).find((c) => c.symbol === selected)?.last_price ?? null;

  const capStatus = info?.status;
  const blockedReason =
    status.error != null
      ? tradeErrorText(status.error.message)
      : info == null
        ? "交易狀態載入中…"
        : (capStatus != null ? STATUS_BLOCKED[capStatus] : undefined) ?? null;
  const degradedNote =
    capStatus === "degraded" ? "群益回報連線降級(可送單,回報可能延遲)" : null;

  const qtyNum = Number.parseInt(qty, 10);
  const priceNum = Number(price.trim());
  const effectivePrice = kind === "limit" ? priceNum : marketEstimate;
  const formInvalid =
    selected === "" ||
    !Number.isFinite(qtyNum) ||
    qtyNum < 1 ||
    (kind === "limit" && (price.trim() === "" || !Number.isFinite(priceNum) || priceNum <= 0)) ||
    (kind === "market" && marketEstimate == null);
  const disabled = blockedReason != null || formInvalid || submit.isPending;

  const handleOpen = () => {
    setNotice(null);
    setSubmitError(null);
    submit.reset();
    setConfirming(true);
  };

  const handleConfirm = () => {
    setConfirming(false);
    if (effectivePrice == null) return;
    submit.mutate(
      {
        tc4_symbol: selected,
        buy_sell: side,
        price: effectivePrice,
        qty: qtyNum,
        price_type: kind,
        time_in_force: "ROD",
        day_trade: false,
        source: "panel",
      },
      {
        onSuccess: (result) => {
          if (result.ok) {
            setNotice(`已送出(單號 ${result.seq_no ?? "—"}),回報見下方列表`);
          } else {
            // 「結果未知,勿重送」等 ok=false 走 200(design §6):顯示 message 不誘發重送
            setSubmitError(result.message);
          }
        },
        onError: (err) => {
          setSubmitError(tradeErrorText(err.message));
        },
      },
    );
  };

  const env = info?.env;
  const isProd = env === "prod";
  const masked = info?.futures_account_masked ?? info?.account_masked;
  const premium =
    effectivePrice != null && Number.isFinite(qtyNum)
      ? Math.round(effectivePrice * qtyNum * TXO_MULTIPLIER * 100) / 100
      : null;

  return (
    <section className="@container border-t border-line pt-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <h2 className="text-sm font-bold tracking-wide text-ink">手動下單</h2>
          {env != null && (
            <span
              className={cn(
                "px-2 py-0.5 text-xs",
                isProd ? "bg-loss font-bold text-bg" : "border border-accent text-accent",
              )}
            >
              {isProd ? "正式" : "模擬"}
            </span>
          )}
          {masked != null && <span className="font-mono text-xs text-ink-dim">{masked}</span>}
        </div>
      </div>

      <div className="grid gap-5 @[720px]:grid-cols-[minmax(250px,300px)_1fr]">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            handleOpen();
          }}
        >
          <label className="block text-xs text-ink-muted">
            商品
            <select
              aria-label="商品"
              name="symbol"
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
              disabled={marketEstimate == null}
              title={marketEstimate == null ? "此合約尚無成交估價,市價不可用" : undefined}
              onClick={() => setKind("market")}
              className={cn(
                "border px-3 py-1.5 text-sm transition-colors",
                kind === "market"
                  ? "border-accent text-accent"
                  : "border-line text-ink-dim hover:text-ink",
                marketEstimate == null && "cursor-not-allowed opacity-40",
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
                name="qty"
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
                  name="price"
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
            {submit.isPending ? "送出中…" : "送出"}
          </button>

          {blockedReason != null && <p className="text-xs text-loss">{blockedReason}</p>}
          {degradedNote != null && <p className="text-xs text-loss">{degradedNote}</p>}
          {submitError != null && <p className="text-xs text-loss">{submitError}</p>}
          {notice != null && <p className="text-xs text-accent">{notice}</p>}
        </form>

        <CapitalOrdersList market="fut" />
      </div>

      {confirming && premium != null && (
        <CapitalConfirmDialog
          title="確認送單"
          rows={[
            { label: "商品", value: shortSymbol(selected) },
            { label: "買賣", value: side === "buy" ? "買進" : "賣出" },
            {
              label: "價格",
              value: kind === "limit" ? `${priceNum} 點` : `市價(估 ${marketEstimate} 點)`,
            },
            { label: "數量", value: `${qtyNum} 口` },
            { label: "預估權利金", value: `${premium.toLocaleString("zh-TW")} 元` },
          ]}
          danger={isProd}
          onConfirm={handleConfirm}
          onCancel={() => setConfirming(false)}
        />
      )}
    </section>
  );
}
