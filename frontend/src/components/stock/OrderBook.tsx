import { isMarketLevel, limitState } from "@/lib/stock-tick";
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
        // 市價單佇列(價格欄 0):鎖漲跌停時 TC4 推的第一檔。印「市價」不印 0,
        // 且**不可點** —— 它沒有價格,置中請求送出去只會讓 PriceLadder 查無列而靜默無反應。
        // 用 <div> 不用 disabled button:不需要 focus 進去,也不該出現在 tab 序。
        const market = isMarketLevel(priceMilli);
        const priceText = market ? "市價" : fmt(priceMilli);
        if (market) {
          return (
            <div
              key={i}
              // `role="group"` 不可省(Phase 5 review P2):ARIA 規範禁止 generic role 從
              // author 取 accessible name,裸 `<div aria-label>` 主流 AT 不會朗讀
              // —— 改成 div 之前它是 button(role=button,label 有效),不補 role
              // 就是本輪造成的可及性回歸。RTL 的 getByLabelText 只讀屬性不查 role,測不出來。
              role="group"
              aria-label={`${isBid ? "買" : "賣"}${i + 1} 市價`}
              className="relative grid h-[25px] w-full grid-cols-2 items-center gap-2 border-b border-line px-2 font-mono text-sm"
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
                  <span className="relative z-[1] text-right text-bull">{priceText}</span>
                </>
              ) : (
                <>
                  <span className="relative z-[1] text-left text-bear">{priceText}</span>
                  <span className="relative z-[1] text-right text-ink-muted">{qty}</span>
                </>
              )}
            </div>
          );
        }
        return (
          <button
            type="button"
            key={i}
            onClick={() => onPriceClick(priceMilli, side)}
            aria-label={`${isBid ? "買" : "賣"}${i + 1} ${priceText}`}
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
  const marketBid = b.reduce((s, [p, v]) => (isMarketLevel(p) ? s + v : s), 0);
  const marketAsk = a.reduce((s, [p, v]) => (isMarketLevel(p) ? s + v : s), 0);
  // 本元件的 last 是物件(DepthBar 收的是 number),漏了這層會在 6/8 既有測試炸 TypeError
  const lastMilli = last?.p ?? null;
  const chg = lastMilli !== null && ref_ ? ((lastMilli - ref_) / ref_) * 100 : null;
  // **不可用 `b[0]?.[0] === upper`**:鎖停時 `bids[0]` 是市價單佇列(價格 0),
  // 漲停價被擠到 `bids[1]` → 判定恆假、badge 靜默消失(實測 2327 就是如此)。
  // 改看「委買側有沒有掛在漲停價的檔位」,市價偽檔位再也打不穿它。
  const lockedUp = upper !== null && b.some(([p]) => p === upper);
  const lockedDown = lower !== null && a.some(([p]) => p === lower);
  // 漲跌停亮燈(項 3):現價踩到漲跌停 → 成交價 + 漲跌% 整塊反白底色,
  // 不只是換文字色 —— 這是盤中要用餘光捕捉的狀態。
  const limit = limitState(lastMilli, upper, lower);

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
        {/* 亮燈時**整塊**吃底色,所以 testid 掛在外層容器上;文字色由 limit 覆蓋
            (亮燈時一律白字,不再走漲跌色 —— 紅底紅字看不見)。 */}
        <span
          data-testid="depth-quote"
          className={cn(
            "ml-auto flex items-baseline gap-1 font-mono",
            limit === "upper" && "rounded bg-bull px-1.5 text-white",
            limit === "lower" && "rounded bg-bear px-1.5 text-white",
          )}
        >
          <span
            data-testid="depth-last"
            className={cn(
              "text-sm",
              limit !== null
                ? undefined
                : chg === null
                  ? "text-ink"
                  : chg > 0
                    ? "text-bull"
                    : chg < 0
                      ? "text-bear"
                      : "text-ink",
            )}
          >
            {lastMilli !== null ? fmt(lastMilli) : "—"}
          </span>
          {chg !== null ? (
            <span
              className={cn(
                "text-xs",
                limit !== null
                  ? undefined
                  : chg > 0
                    ? "text-bull"
                    : chg < 0
                      ? "text-bear"
                      : "text-ink-dim",
              )}
            >
              {`${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`}
            </span>
          ) : null}
        </span>
      </div>

      {/* 總量列。**市價量照算進來**(round6 刻意維持既有計算)——但那讓同一個欄位在
          鎖停日與平常日的定義不同:鎖停日是「市價量 + 4 檔限價量」(市價偽檔位吃掉
          DEPTH=5 的一格),平常日是「5 檔限價量」,跨日 / 跨股比較會失真。
          畫面零提示不行,所以有市價量時掛 title 說明(Phase 5 review P2)。 */}
      <div className="mb-1.5 flex items-baseline justify-between font-mono">
        <span
          data-testid="depth-total-bid"
          className="text-base font-bold text-bull"
          title={marketBid > 0 ? `含市價委託 ${lots(marketBid)} 張` : undefined}
        >
          {lots(bidTotal)}
          <span className="ml-1 text-xs font-normal text-bull/70">張</span>
        </span>
        <span
          data-testid="depth-total-ask"
          className="text-base font-bold text-bear"
          title={marketAsk > 0 ? `含市價委託 ${lots(marketAsk)} 張` : undefined}
        >
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
