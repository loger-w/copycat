import { chgPct, fmt, fmtPct } from "@/lib/format";
import { bestLimit, isMarketLevel } from "@/lib/stock-tick";
import { cn } from "@/lib/utils";

/** 水平五檔(SC-4/D-5)—— **期貨頁專用**(個股已改用 `stock/OrderBook.tsx` 的垂直雙欄版式,
 * mod/stock-ui-fixes Q1 拍板「只改個股」;本檔刻意維持原樣)。
 *
 * 版式:買側由中央往左 買1→買5、賣側由中央往右 賣1→賣5,中央夾成交價 + 漲跌%。
 * 每格內價量疊放(量在上、價在中、比例 bar 在下),欄位固定 10 格,檔位不足補「—」不塌陷。
 * 純展示;**不送單、不點價**(design §11:五檔誤觸面大,送單集中在閃電梯上)。格子一律
 * 渲染成 div —— button 可聚焦卻點了沒反應是假 affordance(review P2-9)。 */

const DEPTH = 5;

export interface Props {
  /** 最佳在前([價毫元, 量]) */
  bids: [number, number][];
  asks: [number, number][];
  /** 最新成交價(毫元) */
  last: number | null;
  /** 參考價(漲跌色與 % 基準) */
  ref_: number | null;
  /** 漲停 / 跌停價(鎖停 badge 判定) */
  upper?: number | null;
  lower?: number | null;
}

interface CellProps {
  entry: [number, number] | undefined;
  label: string;
  side: "bid" | "ask";
  maxVol: number;
}

function Cell({ entry, label, side, maxVol }: CellProps) {
  if (entry === undefined) {
    return (
      <div className="flex min-w-0 flex-col items-center justify-end gap-0.5 px-0.5 py-1">
        <span className="font-mono text-xs text-ink-dim">—</span>
      </div>
    );
  }
  const [priceMilli, qty] = entry;
  // 市價單佇列(價格欄 0):鎖漲跌停時 TC4 推的第一檔。它沒有價格,印「市價」不印 0
  // (照 OrderBook 既有慣例)—— 印 0 看起來像有人掛 0 元。
  const priceText = isMarketLevel(priceMilli) ? "市價" : fmt(priceMilli);
  return (
    <div
      aria-label={`${label} ${priceText}`}
      className={cn(
        "flex min-w-0 flex-col items-center gap-0.5 px-0.5 py-1 font-mono",
        side === "bid" ? "text-bull" : "text-bear",
      )}
    >
      <span className="text-xs text-ink">{qty}</span>
      <span className="text-sm">{priceText}</span>
      <span className="flex h-5 w-full items-end">
        <span
          data-testid="depth-vol-bar"
          className={cn("w-full rounded-sm", side === "bid" ? "bg-bull/30" : "bg-bear/30")}
          // 夾制不可省:`maxVol` 只看限價檔,而市價列的量可以遠超它(比照 OrderBook)
          style={{ height: `${Math.min(100, Math.round((qty / maxVol) * 100))}%` }}
        />
      </span>
    </div>
  );
}

export function DepthBar({ bids, asks, last, ref_, upper = null, lower = null }: Props) {
  const b = bids.slice(0, DEPTH);
  const a = asks.slice(0, DEPTH);
  // 總量與量 bar 歸一**一律只算限價量**(對齊 OrderBook,2026-07-31 user 拍板)。
  // 市價偽檔位混進來的話,同一個欄位在鎖停日是「市價 + 4 檔限價」、平常日是「5 檔限價」
  // —— 定義隨日子變,跨日 / 跨股比較靜默失真;量 bar 更慘,市價佇列可以是限價量的
  // 數倍,五根限價 bar 會一起被壓成看不見的短樁。
  const limitOnly = (levels: [number, number][]) => levels.filter(([p]) => !isMarketLevel(p));
  const limitB = limitOnly(b);
  const limitA = limitOnly(a);
  const maxVol = Math.max(1, ...limitB.map(([, v]) => v), ...limitA.map(([, v]) => v));
  const bidTotal = limitB.reduce((s, [, v]) => s + v, 0);
  const askTotal = limitA.reduce((s, [, v]) => s + v, 0);
  const chg = last !== null && ref_ ? chgPct(last, ref_) : null;
  // **不可用 `b[0]?.[0] === upper`**:鎖停時 `bids[0]` 是市價單佇列(價 0),漲停價被擠到
  // `bids[1]` → 判定恆假、badge 靜默消失(2327 實測)。改看**最佳限價檔**是不是掛在
  // 漲跌停價上 —— 市價偽檔位打不穿它,而語意仍是「排隊排到漲停價上」;用 `some`
  // (簿裡任何一檔碰到漲停價)則會在畸形 / 過期的簿上過度觸發,且 upper 為 0
  // (meta 缺值)時與市價檔的 0 對上,在沒鎖停的股票亮起 badge。
  const lockedUp = upper !== null && bestLimit(b) === upper;
  const lockedDown = lower !== null && bestLimit(a) === lower;

  // 買側 DOM 由左至右 = 買5..買1(最佳貼中央);賣側 = 賣1..賣5
  const bidSlots = [...Array(DEPTH).keys()].reverse();
  const askSlots = [...Array(DEPTH).keys()];

  return (
    <div className="rounded-md border border-line bg-surface p-3">
      <div className="mb-1 flex justify-between border-b border-line pb-1 font-mono text-xs">
        <span className="text-bull">委買 {bidTotal}</span>
        <span className="text-bear">委賣 {askTotal}</span>
      </div>
      <div className="flex items-stretch">
        {/* 左緣列標(對齊每格的 量 / 價 兩行) */}
        <div className="flex shrink-0 flex-col items-end gap-0.5 pr-1 py-1 text-ink-dim">
          <span className="text-xs">量</span>
          <span className="text-sm">價</span>
        </div>
        {bidSlots.map((i) => (
          <div key={`bid-${i}`} className="flex min-w-0 flex-1">
            <Cell entry={b[i]} label={`買${i + 1}`} side="bid" maxVol={maxVol} />
          </div>
        ))}
        {/* 中央成交價 */}
        <div
          aria-label="成交價"
          className="flex shrink-0 flex-col items-center justify-center border-x border-line px-2 font-mono"
        >
          <span
            className={cn(
              "text-base",
              chg === null ? "text-ink" : chg > 0 ? "text-bull" : chg < 0 ? "text-bear" : "text-ink",
            )}
          >
            {last !== null ? fmt(last) : "—"}
          </span>
          {chg !== null ? (
            <span
              className={cn(
                "text-xs",
                chg > 0 ? "text-bull" : chg < 0 ? "text-bear" : "text-ink-dim",
              )}
            >
              {fmtPct(chg)}
            </span>
          ) : null}
          {lockedUp ? (
            <span className="mt-0.5 rounded bg-bull/15 px-1 text-xs text-bull">鎖漲停</span>
          ) : null}
          {lockedDown ? (
            <span className="mt-0.5 rounded bg-bear/15 px-1 text-xs text-bear">鎖跌停</span>
          ) : null}
        </div>
        {askSlots.map((i) => (
          <div key={`ask-${i}`} className="flex min-w-0 flex-1">
            <Cell entry={a[i]} label={`賣${i + 1}`} side="ask" maxVol={maxVol} />
          </div>
        ))}
        <div className="flex shrink-0 flex-col items-start gap-0.5 pl-1 py-1 text-ink-dim">
          <span className="text-xs">量</span>
          <span className="text-sm">價</span>
        </div>
      </div>
    </div>
  );
}
