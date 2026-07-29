import { OrderBook } from "@/components/stock/OrderBook";
import { StockChart } from "@/components/stock/StockChart";
import { TickTape } from "@/components/stock/TickTape";
import { WatchlistSidebar } from "@/components/stock/WatchlistSidebar";
import type { StockStreamState } from "@/hooks/useStockStream";
import { cn } from "@/lib/utils";

/** 個股頁中間主區(SC-6):報價 header → 圖表(江波圖 / K 線)→ 下半 五檔 | 明細。
 *  閃電梯 / 委託 / 部位已移到常駐右欄(RightRail);主檔與資料流由 App 持有(D-3)。 */

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

interface Props {
  code: string | null;
  onSelect: (code: string) => void;
  stream: StockStreamState;
}

export function StockPage({ code, onSelect, stream }: Props) {
  const { accum, watchlist, status, stkfut, wsStatus } = stream;

  const meta = accum?.meta ?? null;
  const last = accum?.last ?? null;
  const chg = last && meta?.ref ? ((last.p - meta.ref) / meta.ref) * 100 : null;

  return (
    <div className="flex min-h-0 flex-1 gap-4">
      <WatchlistSidebar active={code} onSelect={onSelect} quotes={watchlist} />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto">
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
                <StockChart accum={accum} code={code} />
                {/* 下半:左五檔、右明細(round3 SC-6)。

                    h-56 shrink-0 = **確定高度**,不吃剩餘空間 —— 剩餘全歸圖表。
                    確定高度是必要的而不只是好看:TickTape 根節點的 `h-full` +
                    `overflow-y-auto` 只有在父層高度確定時才會內捲;父層若退化成
                    「內容自然高」,30 筆明細(每列 h-6)就把這列撐成 ~770px,
                    每點一次「載入更多」再 +720px,圖表被擠光而 <main> 靜默裁切。

                    兩個子 wrapper 都要 min-h-0,內層的 overflow 容器才算得出可捲高度。
                    五檔的 self-start 已移除、OrderBook 卡片加 h-full ——「兩塊底邊
                    齊平貼底」要求卡片撐滿列高,代價是卡片底部約 24px 留白,
                    這是對舊 self-start 取捨的刻意推翻(change-spec Known Risks 3)。 */}
                <div data-testid="stock-lower-row" className="flex h-56 min-w-0 shrink-0 gap-3">
                  <div className="min-h-0 min-w-0 flex-[3]">
                    <OrderBook
                      code={code}
                      book={accum.book}
                      last={last}
                      ref_={meta?.ref ?? null}
                      upper={meta?.upper ?? null}
                      lower={meta?.lower ?? null}
                    />
                  </div>
                  <div className="min-h-0 min-w-0 flex-[2]">
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
