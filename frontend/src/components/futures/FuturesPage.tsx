import { useEffect, useState } from "react";

import { ConnectionBadge } from "@/components/ConnectionBadge";
import { CapitalOrdersList } from "@/components/capital/CapitalOrdersList";
import { CapitalPositionsList } from "@/components/capital/CapitalPositionsList";
import { FuturesLadder } from "@/components/futures/FuturesLadder";
import { useFuturesStream } from "@/hooks/useFuturesStream";
import { futCloseEstimate, futExchangeContract } from "@/lib/futures-ladder";
import { cn } from "@/lib/utils";

// 本體已搬到 lib/futures-ladder.ts(右欄需要它,不能經 lazy 頁面 import);
// 既有測試 import 路徑不破 → 保留 re-export。
export { futCloseEstimate };

const PRODUCTS = [
  ["TXF", "大台"],
  ["MXF", "小台"],
  ["TMF", "微台"],
] as const;
type Product = (typeof PRODUCTS)[number][0];
const PRODUCT_KEY = "copycat-fut-product";

function initialProduct(): Product {
  const saved = window.localStorage.getItem(PRODUCT_KEY);
  return saved === "MXF" || saved === "TMF" ? saved : "TXF";
}

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

export function FuturesPage() {
  const [product, setProduct] = useState<Product>(initialProduct);
  const { state, wsStatus } = useFuturesStream();

  useEffect(() => {
    window.localStorage.setItem(PRODUCT_KEY, product);
  }, [product]);

  const prod = state?.products[product] ?? null;
  const resolvedYm = prod?.resolved_contract ?? null;
  const contract = resolvedYm !== null ? futExchangeContract(product, resolvedYm) : null;
  const diff = prod?.p != null && prod.ref != null ? prod.p - prod.ref : null;
  const chg = diff !== null && prod?.ref ? (diff / prod.ref) * 100 : null;
  const tone =
    diff === null ? "text-ink" : diff > 0 ? "text-bull" : diff < 0 ? "text-bear" : "text-ink";

  return (
    <div className="flex flex-1 flex-col gap-3">
      <header className="flex flex-wrap items-center gap-3 border-b border-line pb-3">
        <div className="flex overflow-hidden rounded border border-line" role="group" aria-label="商品切換">
          {PRODUCTS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-pressed={product === id}
              onClick={() => setProduct(id)}
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
          {prod?.name ?? ""} <span className="font-mono text-sm text-ink-muted">{product}</span>
        </h2>
        {prod?.p != null ? (
          <span className={cn("flex items-baseline gap-1.5 font-mono text-lg", tone)}>
            <span>{fmt(prod.p)}</span>
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
      <div className="flex flex-wrap items-start gap-4">
        <FuturesLadder product={product} state={prod} />
        {/* 群益委託/部位(market=fut;平倉估價 = 漲跌停貼價,futCloseEstimate) */}
        <div className="flex min-w-64 flex-1 flex-col gap-4">
          <section>
            <h3 className="mb-1 text-sm text-ink-muted">委託</h3>
            <CapitalOrdersList market="fut" />
          </section>
          <section>
            <h3 className="mb-1 text-sm text-ink-muted">部位</h3>
            <CapitalPositionsList
              market="fut"
              closePriceOf={(pos) => futCloseEstimate(pos, contract, prod)}
            />
          </section>
        </div>
      </div>
    </div>
  );
}

export default FuturesPage;
