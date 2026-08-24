import { useMemo, useState } from "react";

import { fmt } from "@/lib/format";
import type { TickRow } from "@/lib/stock-accum";
import { cn } from "@/lib/utils";

const PAGE = 30;

/** 價格相對參考價的色調(四個呼叫點共用一份)。基準用 `meta.ref` 與 header / 側欄 /
 *  江波圖一致 —— 另立基準會出現「同一個價在兩處顏色不同」。 */
function priceTone(v: number | null | undefined, ref: number | null): string {
  if (v == null || ref == null) return "text-ink-dim";
  if (v > ref) return "text-bull";
  if (v < ref) return "text-bear";
  return "text-ink-dim";
}

function volTone(side: string): string {
  return side === "outer" ? "text-bull" : side === "inner" ? "text-bear" : "text-ink-dim";
}

export function TickTape({
  ticks,
  ref_,
  loading = false,
}: {
  ticks: TickRow[];
  ref_: number | null;
  /** 這份 ticks 是 `tape=0` 省略來的、全量補打中(`accum.tapeOmitted`):空態印「載入明細…」
   *  而非終態「尚無成交」—— 兩者畫面同形,使用者分不出「沒成交」與「還沒載」。 */
  loading?: boolean;
}) {
  const [limit, setLimit] = useState(PAGE);
  // reverse 吃整份 ticks(上限 200 筆),而 hover / 展開等純 UI state 變動也會 re-render
  // —— 複製 + 反轉的成本與 ticks 綁定就好,不必跟著每次 render 重付。
  const newestFirst = useMemo(() => [...ticks].reverse(), [ticks]);
  const rows = newestFirst.slice(0, limit);

  if (rows.length === 0) {
    return (
      // h-full 而非 h-40:空態(盤前 / 剛切股)也要與五檔卡片底邊齊平(round3 SC-6)
      <div className="flex h-full items-center justify-center rounded-md border border-line bg-surface">
        <p className="text-sm text-ink-muted">{loading ? "載入明細…" : "尚無成交"}</p>
      </div>
    );
  }

  return (
    // h-full(非固定 max-h-80):高度由 StockPage 下半列決定 —— 圖表佔自然高度後,
    // 剩下的全給下半列,明細因此撐到視窗底(SC-6)。內層 overflow-y-auto 不變。
    <div
      data-testid="tick-tape"
      className="flex h-full flex-col overflow-y-auto rounded-md border border-line bg-surface p-3"
    >
      <table className="w-full border-collapse font-mono text-xs">
        <thead>
          <tr className="text-ink-dim">
            <th className="pb-1 text-left font-normal">時間</th>
            <th className="pb-1 text-right font-normal">買價</th>
            <th className="pb-1 text-right font-normal">賣價</th>
            <th className="pb-1 text-right font-normal">成交</th>
            <th className="pb-1 text-right font-normal">量</th>
          </tr>
        </thead>
        <tbody>
          {/* key 用**該筆自己的單調序號**(`TickRow.n`,N120):前端索引(含尾端回推)
              在「前插」時不變,但 `ticks` 滿 `TAPE_MAX = 200` 後 stock-accum 是環形丟頭
              —— 陣列整體左移一格,任何以位置推導的 key 都會逐筆位移,整個 tbody
              (30–200 列)卸載重掛。序號由 `fromSnapshot` / `applyTick` 兩處以後端 `seq`
              指派,丟頭與全量 refetch 都不換號。 */}
          {rows.map((t) => (
            <tr key={t.n} className="h-6">
              <td className="text-ink-muted">{t.t.slice(0, 8)}</td>
              <td className={cn("text-right", priceTone(t.b, ref_))}>
                {t.b == null ? "-" : fmt(t.b)}
              </td>
              <td className={cn("text-right", priceTone(t.a, ref_))}>
                {t.a == null ? "-" : fmt(t.a)}
              </td>
              <td className={cn("text-right", priceTone(t.p, ref_))}>{fmt(t.p)}</td>
              <td className={cn("text-right", volTone(t.side))}>{t.q}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ticks.length > limit ? (
        <button
          type="button"
          className="mt-2 text-xs text-ink-dim hover:text-ink"
          onClick={() => setLimit((n) => n + PAGE)}
        >
          載入更多
        </button>
      ) : null}
    </div>
  );
}
