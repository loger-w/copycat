import { useState } from "react";

import { CapitalConfirmDialog } from "@/components/capital/CapitalConfirmDialog";
import { useCapitalPositions, useCapitalStatus, useClosePosition } from "@/hooks/useCapital";
import { closeBodyOf, kindOf, KIND_TEXT } from "@/lib/close-order";
import { tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { CapitalMarket, CapitalPosition } from "@/types";

interface CapitalPositionsListProps {
  market: CapitalMarket;
  /** 閘用估價(由頁面層帶現價/漲跌停);null = 無行情 → 平倉鍵鎖住。 */
  closePriceOf?: (pos: CapitalPosition) => number | null;
}

const GRID = "grid grid-cols-[1fr_auto_auto_auto_auto_auto] items-baseline gap-x-3";

/** 部位列鍵 = 後端 store 的複合鍵:同檔資+集保並存時兩列才分得開。 */
function rowKeyOf(p: CapitalPosition): string {
  return `${p.stock_no}:${p.kind}`;
}

/** 部位列表(market 過濾)+ 平倉(確認彈窗顯示閘用估價;後端另有 10s 防重送)。 */
export function CapitalPositionsList({ market, closePriceOf }: CapitalPositionsListProps) {
  const { data } = useCapitalPositions();
  const status = useCapitalStatus();
  const closePosition = useClosePosition();
  const [closingKey, setClosingKey] = useState<string | null>(null);

  const danger = status.data?.env === "prod";
  const unit = market === "fut" ? "口" : "張";
  const codeLabel = market === "fut" ? "契約" : "代號";
  const positions = (data?.positions ?? []).filter((p) => p.market === market);
  // closing 走 key 而非快照:dialog 開著時回報更新部位,顯示跟最新資料走;部位消失自動關窗
  const closing =
    closingKey !== null ? positions.find((p) => rowKeyOf(p) === closingKey) : undefined;
  const estimate = closing !== undefined ? (closePriceOf?.(closing) ?? null) : null;
  const closingKind = closing !== undefined && market === "sec" ? kindOf(closing) : null;
  const closingKindText = closingKind !== null ? KIND_TEXT[closingKind] : undefined;

  if (positions.length === 0) {
    return <p className="py-3 text-center text-xs text-ink-dim">無部位</p>;
  }

  function confirm(): void {
    if (closing === undefined || estimate === null) return;
    // body 由共用 helper 產(閃電梯一鍵平倉同一支):kind 只在證券送、key 用 stock_no
    // 而非 UI 的複合鍵 rowKeyOf,兩處若各留一份組裝法會靜默漂移
    closePosition.mutate(closeBodyOf(closing, estimate));
    setClosingKey(null);
  }

  return (
    <ul className="min-w-0">
      <li className={cn(GRID, "border-b border-line pb-1 text-xs text-ink-dim")}>
        <span>{codeLabel}</span>
        <span>方向</span>
        <span>數量</span>
        <span>均價</span>
        <span className="text-right">損益</span>
        <span />
      </li>
      {closePosition.error !== null && (
        // 平倉失敗錯誤列(400 BROKER_REJECTED 等;review A2);下次 mutate 自動清除
        <li className="border-b border-line/60 py-1 text-xs text-loss">
          {tradeErrorText(closePosition.error.message)}
        </li>
      )}
      {positions.map((p) => {
        const isLong = p.qty > 0;
        const est = closePriceOf?.(p) ?? null;
        const pnl = p.pnl_base;
        const rowKind = market === "sec" ? kindOf(p) : null;
        const kindText = rowKind !== null ? KIND_TEXT[rowKind] : undefined;
        return (
          <li
            key={rowKeyOf(p)}
            className={cn(GRID, "border-b border-line/60 py-1.5 font-mono text-xs")}
          >
            {/* 種類是獨立子元素而非併進代號文字:代號的精確字串斷言(RightRail)才不會被打斷 */}
            <span className="truncate text-ink">
              {`${p.stock_no} ${p.name}`.trim()}
              {kindText !== undefined && (
                <span className="ml-1 text-ink-dim">{kindText.short}</span>
              )}
            </span>
            <span className={cn(isLong ? "text-bull" : "text-bear")}>{isLong ? "多" : "空"}</span>
            <span className="text-ink-muted">{`${Math.abs(p.qty)} ${unit}`}</span>
            <span className="text-ink">{p.avg_price !== null ? p.avg_price.toFixed(2) : "—"}</span>
            <span
              className={cn(
                "text-right",
                pnl === null ? "text-ink-dim" : pnl >= 0 ? "text-bull" : "text-bear",
              )}
            >
              {pnl === null ? "—" : `${pnl >= 0 ? "+" : ""}${pnl}`}
            </span>
            <button
              type="button"
              disabled={closePosition.isPending || est === null}
              title={est === null ? "無行情估價" : undefined}
              onClick={() => setClosingKey(rowKeyOf(p))}
              className="border border-line px-2 py-0.5 text-ink-muted transition-colors hover:border-loss hover:text-loss disabled:opacity-40"
            >
              平倉
            </button>
          </li>
        );
      })}
      {closing !== undefined && estimate !== null && (
        <CapitalConfirmDialog
          title="確認平倉"
          rows={[
            { label: codeLabel, value: `${closing.stock_no} ${closing.name}`.trim() },
            // 種類只在證券成立(fut 的 OI 列無種類);同檔兩列時這是唯一的分辨依據
            ...(closingKindText !== undefined
              ? [{ label: "種類", value: closingKindText.full }]
              : []),
            {
              label: "部位",
              value: `${closing.qty > 0 ? "多" : "空"} ${Math.abs(closing.qty)} ${unit} · 均 ${
                closing.avg_price !== null ? closing.avg_price.toFixed(2) : "—"
              }`,
            },
            {
              label: "反向單",
              value: `${closing.qty > 0 ? "賣出" : "買回"} ${Math.abs(closing.qty)} ${unit}`,
            },
            { label: "閘用估價", value: String(estimate) },
          ]}
          danger={danger}
          onConfirm={confirm}
          onCancel={() => setClosingKey(null)}
        />
      )}
    </ul>
  );
}
