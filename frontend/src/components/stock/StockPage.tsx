import { useEffect, useState } from "react";

import { OrderBook } from "@/components/stock/OrderBook";
import { StockIntradayChart } from "@/components/stock/StockIntradayChart";
import { TickTape } from "@/components/stock/TickTape";
import { WatchlistSidebar } from "@/components/stock/WatchlistSidebar";
import { useStockStream } from "@/hooks/useStockStream";
import { cn } from "@/lib/utils";

const MAIN_CODE_KEY = "stock-main-code";

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

export function StockPage() {
  const [code, setCode] = useState<string | null>(
    () => window.localStorage.getItem(MAIN_CODE_KEY) || null,
  );
  const { accum, watchlist, status, stkfut, wsStatus } = useStockStream(code);

  useEffect(() => {
    if (code) window.localStorage.setItem(MAIN_CODE_KEY, code);
  }, [code]);

  const meta = accum?.meta ?? null;
  const last = accum?.last ?? null;
  const chg = last && meta?.ref ? ((last.p - meta.ref) / meta.ref) * 100 : null;

  return (
    <div className="flex flex-1 gap-4">
      <WatchlistSidebar active={code} onSelect={setCode} quotes={watchlist} />
      <main className="flex min-w-0 flex-1 flex-col gap-3">
        {status.tc4 === "down" || wsStatus === "closed" ? (
          <p className="rounded border border-bear bg-bear/10 px-3 py-1 text-sm text-bear">
            {status.tc4 === "down" ? "達錢 4 連線中斷,恢復後自動回補" : "伺服器連線中斷,重連中…"}
          </p>
        ) : null}
        {code === null ? (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-sm text-ink-muted">從自選清單選擇一檔開始看盤</p>
          </div>
        ) : (
          <>
            <header className="flex flex-wrap items-baseline gap-3">
              <h2 className="text-lg font-bold text-ink">
                {meta?.name ?? ""} <span className="font-mono text-ink-muted">{code}</span>
              </h2>
              {last ? (
                <span
                  className={cn(
                    "font-mono text-lg",
                    (chg ?? 0) > 0 ? "text-bull" : (chg ?? 0) < 0 ? "text-bear" : "text-ink",
                  )}
                >
                  {fmt(last.p)}
                  {chg != null ? (
                    <span className="ml-1 text-xs">{`${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}</span>
                  ) : null}
                </span>
              ) : null}
              {accum?.noData ? <span className="text-xs text-ink-dim">無資料</span> : null}
              {status.backfilling === code ? (
                <span className="text-xs text-ink-dim">回補中…</span>
              ) : null}
              {stkfut ? (
                <span className="font-mono text-xs text-ink-muted">
                  {stkfut.prod} {fmt(stkfut.p)}
                  {stkfut.basis != null ? (
                    <span className={cn("ml-1", stkfut.basis > 0 ? "text-bull" : stkfut.basis < 0 ? "text-bear" : "")}>
                      {`價差 ${stkfut.basis > 0 ? "+" : ""}${fmt(stkfut.basis)}`}
                    </span>
                  ) : null}
                </span>
              ) : null}
              <span className="ml-auto font-mono text-xs text-ink-dim">
                總量 {last?.cum_vol ?? "-"} · 昨量 {meta?.y_vol ?? "-"}
              </span>
            </header>
            {accum ? (
              <>
                <StockIntradayChart accum={accum} />
                <div className="flex flex-wrap gap-3">
                  <div className="min-w-56">
                    <OrderBook book={accum.book} last={last} ref_={meta?.ref ?? null} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <TickTape ticks={accum.ticks} />
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center">
                <p className="text-sm text-ink-muted">載入中…</p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default StockPage;
