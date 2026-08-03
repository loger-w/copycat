import { chgPct, fmt, fmtPct } from "@/lib/format";
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
  return (
    <div
      aria-label={`${label} ${fmt(priceMilli)}`}
      className={cn(
        "flex min-w-0 flex-col items-center gap-0.5 px-0.5 py-1 font-mono",
        side === "bid" ? "text-bull" : "text-bear",
      )}
    >
      <span className="text-xs text-ink">{qty}</span>
      <span className="text-sm">{fmt(priceMilli)}</span>
      <span className="flex h-5 w-full items-end">
        <span
          data-testid="depth-vol-bar"
          className={cn("w-full rounded-sm", side === "bid" ? "bg-bull/30" : "bg-bear/30")}
          style={{ height: `${Math.round((qty / maxVol) * 100)}%` }}
        />
      </span>
    </div>
  );
}

export function DepthBar({ bids, asks, last, ref_, upper = null, lower = null }: Props) {
  const b = bids.slice(0, DEPTH);
  const a = asks.slice(0, DEPTH);
  const maxVol = Math.max(1, ...b.map(([, v]) => v), ...a.map(([, v]) => v));
  const bidTotal = b.reduce((s, [, v]) => s + v, 0);
  const askTotal = a.reduce((s, [, v]) => s + v, 0);
  const chg = last !== null && ref_ ? chgPct(last, ref_) : null;
  const lockedUp = upper !== null && b[0]?.[0] === upper;
  const lockedDown = lower !== null && a[0]?.[0] === lower;

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
