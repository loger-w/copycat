import { ConnectionBadge } from "@/components/ConnectionBadge";
import { DepthBar } from "@/components/quote/DepthBar";
import type { WsStatus } from "@/hooks/useFuturesStream";
import { fmt } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FuturesProductState } from "@/types";

/** 期貨頁中間主區(SC-5):商品切換 → 報價列 → 與個股同款的水平五檔。
 *  閃電梯 / 委託 / 部位已移到常駐右欄(RightRail);商品與資料流由 App 持有(D-3)。
 *  江波圖 / 明細不做 —— 後端 futures engine 無分鐘聚合、也不保留 tick(D5 拍板)。 */

// 本體已搬到 lib/futures-ladder.ts(右欄需要它,不能經 lazy 頁面 import);
// 既有測試 import 路徑不破 → 保留 re-export。
export { futCloseEstimate } from "@/lib/futures-ladder";

interface Props {
  products: readonly (readonly [string, string])[];
  product: string;
  onProduct: (product: string) => void;
  state: FuturesProductState | null;
  resolvedYm: string | null;
  wsStatus: WsStatus;
}

export function FuturesPage({ products, product, onProduct, state, resolvedYm, wsStatus }: Props) {
  const diff = state?.p != null && state.ref != null ? state.p - state.ref : null;
  const chg = diff !== null && state?.ref ? (diff / state.ref) * 100 : null;
  const tone =
    diff === null ? "text-ink" : diff > 0 ? "text-bull" : diff < 0 ? "text-bear" : "text-ink";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-line pb-3">
        <div className="flex overflow-hidden rounded border border-line" role="group" aria-label="商品切換">
          {products.map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-pressed={product === id}
              onClick={() => onProduct(id)}
              className={cn(
                "px-3 py-1 text-sm",
                product === id ? "bg-surface text-ink" : "text-ink-dim hover:text-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <h2 className="text-lg font-bold text-ink">
          {state?.name ?? ""} <span className="font-mono text-sm text-ink-muted">{product}</span>
        </h2>
        {state?.p != null ? (
          <span className={cn("flex items-baseline gap-1.5 font-mono text-lg", tone)}>
            <span>{fmt(state.p)}</span>
            {diff !== null ? (
              <span className="text-xs">{`${diff > 0 ? "+" : ""}${fmt(diff)}`}</span>
            ) : null}
            {chg !== null ? (
              <span className="text-xs">{`${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}</span>
            ) : null}
          </span>
        ) : null}
        <span className="font-mono text-xs text-ink-muted">
          {resolvedYm !== null
            ? `${product} ${resolvedYm.slice(0, 4)}/${resolvedYm.slice(4, 6)}`
            : "合約解析中"}
        </span>
        <span className="ml-auto">
          <ConnectionBadge status="live" wsStatus={wsStatus} />
        </span>
      </header>
      {/* 水平五檔(與個股共用 DepthBar;SC-5) */}
      <DepthBar
        bids={state?.bids ?? []}
        asks={state?.asks ?? []}
        last={state?.p ?? null}
        ref_={state?.ref ?? null}
        upper={state?.upper ?? null}
        lower={state?.lower ?? null}
      />
    </div>
  );
}

export default FuturesPage;
