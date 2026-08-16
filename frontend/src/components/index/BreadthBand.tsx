/** 全市場家數帶(market-overview R2 SC-4):上市 / 上櫃兩列 × 五格。
 *
 *  純展示元件 —— 資料由 App 層 `useBreadth()` 取得後經 IndexPage 下傳(design R8)。
 *  桶序 `漲停 / 上漲 / 平盤 / 下跌 / 跌停` 與後端 `_series_list()` 同一份順序,**不得重排**。
 *
 *  **識別手段一格只用一種**(2026-08-14 拍板 + 2026-08-16 D8 加深停板桶):
 *  - 停板兩格是**實心格底**(漲停 `bg-bull` 紅底 / 跌停 `bg-bear` 綠底,台股紅漲綠跌),
 *    標籤與數字一律 `text-white` —— 滿版紅綠上 ink token 對比不足,而字若跟著染成同
 *    色系更是完全讀不出來(dataviz:顏色由色塊承擔,文字只要在色塊上讀得到)。同款
 *    實心燈的既有樣板是個股期漲跌停標(`WatchlistSidebar.tsx:405-406`)。
 *  - 上漲 / 下跌兩格**沒有底色**,所以識別改由**數字**承擔(上漲 `text-bull` /
 *    下跌 `text-bear`)—— 這不是推翻上一條,是同一條規則的另一半:有色塊的格由色塊
 *    說話、字退成白,沒色塊的格才由字說話。
 *  - 平盤維持中性 ink:五格全染等於沒有重點,而「沒漲沒跌」本來就不需要顏色。 */
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import type { BreadthCounts, BreadthState } from "@/types";

type Bucket = keyof BreadthCounts["twse"];

/** `tone` 給格底與框線(`null` = 中性,沿用面板既有 surface/line);`labelTone` 給標籤
 *  (`null` = `text-ink-dim`)、`valueTone` 給數字(`null` = `text-ink`)。實心底的格
 *  兩支 tone 一起給白,無底色的格只給 `valueTone`:見檔頭的「一格只用一種手段」。 */
const BUCKETS: readonly {
  key: Bucket;
  label: string;
  tone: string | null;
  labelTone?: string;
  valueTone: string | null;
}[] = [
  {
    key: "limit_up",
    label: "漲停",
    tone: "border-bull bg-bull",
    labelTone: "text-white",
    valueTone: "text-white",
  },
  { key: "up", label: "上漲", tone: null, valueTone: "text-bull" },
  { key: "flat", label: "平盤", tone: null, valueTone: null },
  { key: "down", label: "下跌", tone: null, valueTone: "text-bear" },
  {
    key: "limit_down",
    label: "跌停",
    tone: "border-bear bg-bear",
    labelTone: "text-white",
    valueTone: "text-white",
  },
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

  // 只印時分秒時,開盤前掛著的前一交易日曲線與今日盤中長得一模一樣 —— 日期要一起印,
  // 舊資料才辨識得出來(review P2-5)。任一端缺值就不留分隔符。
  const stamp = [breadth?.trade_date, breadth?.as_of].filter(Boolean).join(" · ");

  return (
    <Shell>
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-sm text-ink">漲跌家數</span>
        {stamp ? (
          <span data-testid="breadth-stamp" className="font-mono text-xs text-ink-dim">
            {stamp}
          </span>
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
              <span className={cn("text-xs", b.labelTone ?? "text-ink-dim")}>{b.label}</span>
              <span
                data-testid={`breadth-value-${m.key}-${b.key}`}
                className={cn("font-mono text-sm", b.valueTone ?? "text-ink")}
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
