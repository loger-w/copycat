/** 全市場家數帶(market-overview R2 SC-4):上市 / 上櫃兩列 × 五格。
 *
 *  純展示元件 —— 資料由 App 層 `useBreadth()` 取得後經 IndexPage 下傳(design R8)。
 *  桶序 `漲停 / 上漲 / 平盤 / 下跌 / 跌停` 與後端 `_series_list()` 同一份順序,**不得重排**。
 *
 *  染色只落在**格底**(漲停紅底 / 跌停綠底,台股紅漲綠跌),數字一律 ink token:
 *  數字若跟著染成同色系,紅底上的紅字在暗色盤面幾乎讀不出來(dataviz:文字穿 text
 *  token,顏色由旁邊的色塊承擔識別)。中間三格保持中性 —— 五格全染等於沒有重點。 */
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { BreadthCounts, BreadthState } from "@/types";

type Bucket = keyof BreadthCounts["twse"];

/** `tone` 只給格底與框線;`null` = 中性(沿用面板既有 surface/line)。 */
const BUCKETS: readonly { key: Bucket; label: string; tone: string | null }[] = [
  { key: "limit_up", label: "漲停", tone: "border-bull/40 bg-bull/15" },
  { key: "up", label: "上漲", tone: null },
  { key: "flat", label: "平盤", tone: null },
  { key: "down", label: "下跌", tone: null },
  { key: "limit_down", label: "跌停", tone: "border-bear/40 bg-bear/15" },
];

const MARKETS: readonly { key: keyof BreadthCounts; label: string }[] = [
  { key: "twse", label: "上市" },
  { key: "tpex", label: "上櫃" },
];

function Shell({ children }: { children: ReactNode }) {
  return (
    <div data-testid="breadth-band" className="flex flex-col gap-1.5">
      {children}
    </div>
  );
}

export function BreadthBand({ breadth }: { breadth: BreadthState | null }) {
  // 三態:引擎缺席 / token 未設(enabled=false)與「還沒收到第一輪」是不同的事,
  // 文案分開才看得出「要去設 .env」還是「等一下就好」。
  if (breadth !== null && !breadth.enabled) {
    return (
      <Shell>
        <p className="text-sm text-ink-muted">漲跌家數:FinMind 未設定</p>
      </Shell>
    );
  }
  const counts = breadth?.counts ?? null;
  if (counts === null) {
    return (
      <Shell>
        <p className="text-sm text-ink-muted">漲跌家數:載入中…</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-sm text-ink">漲跌家數</span>
        {breadth?.as_of ? (
          <span className="font-mono text-xs text-ink-dim">至 {breadth.as_of}</span>
        ) : null}
        {breadth?.stale ? (
          <span
            data-testid="breadth-stale"
            className="rounded border border-bull/40 bg-bull/15 px-1.5 text-xs text-bull"
          >
            資料延遲
          </span>
        ) : null}
      </div>
      {MARKETS.map((m) => (
        <div key={m.key} data-testid={`breadth-row-${m.key}`} className="flex items-stretch gap-1">
          <span className="w-8 shrink-0 self-center text-xs text-ink-muted">{m.label}</span>
          {BUCKETS.map((b) => (
            <div
              key={b.key}
              data-testid={`breadth-cell-${m.key}-${b.key}`}
              className={cn(
                "flex min-w-16 flex-1 flex-col items-center rounded border px-2 py-1",
                b.tone ?? "border-line bg-surface",
              )}
            >
              <span className="text-xs text-ink-dim">{b.label}</span>
              <span
                data-testid={`breadth-value-${m.key}-${b.key}`}
                className="font-mono text-sm text-ink"
              >
                {counts[m.key][b.key]}
              </span>
            </div>
          ))}
        </div>
      ))}
    </Shell>
  );
}

export default BreadthBand;
