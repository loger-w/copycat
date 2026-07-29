import { cn } from "@/lib/utils";

/** 個股五檔 —— 垂直雙欄版式(SC-1,參照 treading-king `QuoteBook.tsx`)。
 *
 * 版式:標題列(委買賣 五檔 / 鎖停 badge / 成交價+漲跌%)→ 總量列(左紅買、右綠賣,
 * 大字 + 「張」)→ 左右兩欄各 5 列,量 bar 是列背景(買側貼右緣往左長、賣側貼左緣往右長)。
 *
 * 與期貨頁的差異是**刻意的**:期貨頁仍用共用的水平 `components/quote/DepthBar.tsx`
 * (change-spec Q1 拍板「只改個股」)。兩者不再共用版式,但共用兩條規則:
 * 檔位不足補「—」不塌陷、**不送單**(design §11:五檔誤觸面大,送單集中在閃電梯上)。
 *
 * 點價只發 `stock-price-click` CustomEvent → PriceLadder 把該價置中。 */

const DEPTH = 5;

interface Props {
  code: string;
  book: { bids: [number, number][]; asks: [number, number][] } | null;
  last: { p: number; t: string; cum_vol: number } | null;
  ref_: number | null; // 參考價(漲跌色基準)
  upper?: number | null; // 漲停價(鎖停 badge 判定;SC-5)
  lower?: number | null;
}

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

/** 千分位固定 en-US:不指定 locale 時分隔符隨執行環境 ICU 預設變動(非 en-US 會拿到
 *  `1.033`),會讓斷言與畫面都變成環境相依(review R16)。 */
function lots(n: number): string {
  return n.toLocaleString("en-US");
}

function emitPriceClick(priceMilli: number, side: "bid" | "ask", code: string): void {
  // PriceLadder 監聽 → 該價置中(不送單;design §11)
  window.dispatchEvent(
    new CustomEvent("stock-price-click", { detail: { priceMilli, side, code } }),
  );
}

interface SideProps {
  levels: [number, number][];
  side: "bid" | "ask";
  maxQty: number;
  onPriceClick: (priceMilli: number, side: "bid" | "ask") => void;
}

/** 買賣兩欄共用一份:缺檔補位、bar 歸一、點價規則只寫一次,兩側不可漂移
 *  (沿用 treading-king BookSide 的收斂理由)。 */
function BookSide({ levels, side, maxQty, onPriceClick }: SideProps) {
  const isBid = side === "bid";
  return (
    <div>
      {[...Array(DEPTH).keys()].map((i) => {
        const entry = levels[i];
        if (entry === undefined) {
          // W-4:檔位不足不塌陷,維持 5 列
          return (
            <div
              key={i}
              className="grid h-[25px] grid-cols-2 items-center gap-2 border-b border-line px-2 font-mono text-sm text-ink-dim"
            >
              <span className={cn(isBid && "order-2 text-right")}>—</span>
              <span className={cn(isBid && "order-1")} />
            </div>
          );
        }
        const [priceMilli, qty] = entry;
        return (
          <button
            type="button"
            key={i}
            onClick={() => onPriceClick(priceMilli, side)}
            aria-label={`${isBid ? "買" : "賣"}${i + 1} ${fmt(priceMilli)}`}
            className="relative grid h-[25px] w-full grid-cols-2 items-center gap-2 border-b border-line px-2 font-mono text-sm hover:bg-bg-deep/60"
          >
            <span
              data-testid="depth-vol-bar"
              className={cn(
                "pointer-events-none absolute inset-y-0",
                isBid ? "right-0 bg-bull/15" : "left-0 bg-bear/15",
              )}
              style={{ width: `${Math.round((qty / maxQty) * 100)}%` }}
            />
            {isBid ? (
              <>
                <span className="relative z-[1] text-left text-ink-muted">{qty}</span>
                <span className="relative z-[1] text-right text-bull">{fmt(priceMilli)}</span>
              </>
            ) : (
              <>
                <span className="relative z-[1] text-left text-bear">{fmt(priceMilli)}</span>
                <span className="relative z-[1] text-right text-ink-muted">{qty}</span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function OrderBook({ code, book, last, ref_, upper = null, lower = null }: Props) {
  const b = (book?.bids ?? []).slice(0, DEPTH);
  const a = (book?.asks ?? []).slice(0, DEPTH);
  // `1` 不可省:五檔全 0 量(盤前 / 剛重啟未收 snapshot)時除零 → width "NaN%",
  // React 靜默產生無效 style,只有盤中才看得到(review R7;對齊 DepthBar.tsx:78)
  const maxQty = Math.max(1, ...b.map(([, v]) => v), ...a.map(([, v]) => v));
  const bidTotal = b.reduce((s, [, v]) => s + v, 0);
  const askTotal = a.reduce((s, [, v]) => s + v, 0);
  // 本元件的 last 是物件(DepthBar 收的是 number),漏了這層會在 6/8 既有測試炸 TypeError
  const lastMilli = last?.p ?? null;
  const chg = lastMilli !== null && ref_ ? ((lastMilli - ref_) / ref_) * 100 : null;
  const lockedUp = upper !== null && b[0]?.[0] === upper;
  const lockedDown = lower !== null && a[0]?.[0] === lower;

  return (
    // h-full:兩塊卡片底邊要與中間欄底部齊平(round3 SC-6)。內容約 200px、
    // 列高 224px → 卡片底部約 24px 留白,是「貼底」的必要代價。
    <section className="h-full rounded-md border border-line bg-surface p-2.5">
      {/* 標題列:鎖停 badge + 成交價(五檔區自足,不必回頭看頁面最上方的 header) */}
      <div
        data-testid="depth-head"
        className="mb-1.5 flex items-center gap-2 border-b border-line pb-1.5"
      >
        <h3 className="text-sm font-bold text-ink">委買賣 五檔</h3>
        {lockedUp ? (
          <span className="rounded border border-bull/40 px-1.5 text-xs text-bull">鎖漲停</span>
        ) : null}
        {lockedDown ? (
          <span className="rounded border border-bear/40 px-1.5 text-xs text-bear">鎖跌停</span>
        ) : null}
        <span className="ml-auto flex items-baseline gap-1 font-mono">
          <span
            data-testid="depth-last"
            className={cn(
              "text-sm",
              chg === null ? "text-ink" : chg > 0 ? "text-bull" : chg < 0 ? "text-bear" : "text-ink",
            )}
          >
            {lastMilli !== null ? fmt(lastMilli) : "—"}
          </span>
          {chg !== null ? (
            <span className={cn("text-xs", chg > 0 ? "text-bull" : chg < 0 ? "text-bear" : "text-ink-dim")}>
              {`${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}
            </span>
          ) : null}
        </span>
      </div>

      {/* 總量列 */}
      <div className="mb-1.5 flex items-baseline justify-between font-mono">
        <span data-testid="depth-total-bid" className="text-base font-bold text-bull">
          {lots(bidTotal)}
          <span className="ml-1 text-xs font-normal text-bull/70">張</span>
        </span>
        <span data-testid="depth-total-ask" className="text-base font-bold text-bear">
          {lots(askTotal)}
          <span className="ml-1 text-xs font-normal text-bear/70">張</span>
        </span>
      </div>

      {/* 本體:左欄買 1→5、右欄賣 1→5 */}
      <div className="grid grid-cols-2 gap-4">
        <BookSide
          levels={b}
          side="bid"
          maxQty={maxQty}
          onPriceClick={(p, s) => emitPriceClick(p, s, code)}
        />
        <BookSide
          levels={a}
          side="ask"
          maxQty={maxQty}
          onPriceClick={(p, s) => emitPriceClick(p, s, code)}
        />
      </div>
    </section>
  );
}
