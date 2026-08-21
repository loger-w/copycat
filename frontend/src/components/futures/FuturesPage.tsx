import { ConnectionBadge } from "@/components/ConnectionBadge";
import { FuturesChart } from "@/components/futures/FuturesChart";
import { DepthBar } from "@/components/quote/DepthBar";
import { RadioPills } from "@/components/ui/RadioPills";
import type { WsStatus } from "@/hooks/useFuturesStream";
import type { IndexSeries } from "@/hooks/useIndexStream";
import type { FuturesBarsKey } from "@/hooks/useFuturesBars";
import { fmt, fmtPct, formatPts } from "@/lib/format";
import { settlementCountdown } from "@/lib/settlement";
import { inTwseSessionNow } from "@/lib/spot-session";
import { cn } from "@/lib/utils";
import type { FuturesProductState } from "@/types";

/** 期貨頁中間主區(SC-1/5/6):商品切換 → 報價列(含期現價差 / 結算倒數)→
 *  水平五檔 → 近全時段主圖。
 *  閃電梯 / 委託 / 部位已移到常駐右欄(RightRail);商品與資料流由 App 持有(D-3)。 */

// 本體已搬到 lib/futures-ladder.ts(右欄需要它,不能經 lazy 頁面 import);
// 既有測試 import 路徑不破 → 保留 re-export。
export { futCloseEstimate } from "@/lib/futures-ladder";

/** 支援近全時段圖的商品鍵;其餘商品(若日後擴充)不掛圖而不是猜一把 key。 */
function barsKeyOf(product: string): FuturesBarsKey | null {
  return product === "TXF" || product === "MXF" || product === "TMF" ? product : null;
}

/** 本機日曆日 `YYYY-MM-DD`(結算倒數的「今天」)。 */
function todayOf(now: Date): string {
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${m}-${d}`;
}

interface Props {
  products: readonly (readonly [string, string])[];
  product: string;
  onProduct: (product: string) => void;
  state: FuturesProductState | null;
  resolvedYm: string | null;
  wsStatus: WsStatus;
  /** 加權指數(App 的 `useIndexStream().twse`)—— 期現價差的現貨腿。 */
  twse: IndexSeries | null;
  /** 使用者是否正看著期貨 tab(App 的 `tab === "futures"`)。本頁的 DOM 由 App 以
   *  `hidden` 保留 → 沒有這道 gate 主圖會在背景整晚輪詢(review LF-2)。
   *  未給時預設 true(既有呼叫路徑不靜默停更)。 */
  active?: boolean;
}

export function FuturesPage({
  products,
  product,
  onProduct,
  state,
  resolvedYm,
  wsStatus,
  twse,
  active = true,
}: Props) {
  const diff = state?.p != null && state.ref != null ? state.p - state.ref : null;
  const chg = diff !== null && state?.ref ? (diff / state.ref) * 100 : null;
  const tone =
    diff === null ? "text-ink" : diff > 0 ? "text-bull" : diff < 0 ? "text-bear" : "text-ink";

  // 期現價差(SC-5)。三條件缺一不可 —— `stale` 只在 09:00–13:25 的 watch 窗內維護,
  // 收盤後 p 保留收盤值且 stale 恆 false,單靠它會整夜顯示一個假價差(design §6.1)。
  const spread =
    state?.p != null && twse?.p != null && !twse.stale && inTwseSessionNow()
      ? (state.p - twse.p) / 1000
      : null;
  const spreadTone =
    spread === null || spread === 0 ? "text-ink-dim" : spread > 0 ? "text-bull" : "text-bear";

  const countdown = resolvedYm === null ? null : settlementCountdown(resolvedYm, todayOf(new Date()));
  const barsKey = barsKeyOf(product);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-line pb-3">
        {/* a11y 批:商品列是單選 —— 原 `role="group"` + 三顆 `aria-pressed` button 讓 AT
            聽成三個互不相干的開關、鍵盤要按三次 Tab 才穿得過。改 RadioPills 後一個 tab
            stop + 方向鍵切換。容器 `overflow-hidden` 會裁掉外擴的 focus ring,`RadioPills`
            內建的 `ring-inset` 正是為此。 */}
        <RadioPills<string>
          ariaLabel="商品切換"
          className="flex overflow-hidden rounded border border-line"
          value={product}
          onChange={onProduct}
          items={products.map(([id, label]) => ({ value: id, label }))}
          pillClass={(_item, checked) =>
            cn(
              "px-3 py-1 text-sm",
              checked ? "bg-surface text-ink" : "text-ink-dim hover:text-ink",
            )
          }
        />
        <h2 className="text-lg font-bold text-ink">
          {state?.name ?? ""} <span className="font-mono text-sm text-ink-muted">{product}</span>
        </h2>
        {state?.p != null ? (
          <span className={cn("flex items-baseline gap-1.5 font-mono text-lg", tone)}>
            <span>{fmt(state.p)}</span>
            {diff !== null ? (
              <span className="text-xs">{`${diff > 0 ? "+" : ""}${fmt(diff)}`}</span>
            ) : null}
            {chg !== null ? (
              <span className="text-xs">{fmtPct(chg)}</span>
            ) : null}
          </span>
        ) : null}
        <span data-testid="fut-spread" className={cn("font-mono text-xs", spreadTone)}>
          {spread === null ? "價差 —" : `價差 ${spread > 0 ? "+" : ""}${formatPts(spread)}`}
        </span>
        <span className="font-mono text-xs text-ink-muted">
          {resolvedYm !== null
            ? `${product} ${resolvedYm.slice(0, 4)}/${resolvedYm.slice(4, 6)}`
            : "合約解析中"}
        </span>
        {countdown === null ? null : (
          <span
            data-testid="fut-settlement"
            className={cn(
              "rounded px-1.5 py-0.5 font-mono text-xs",
              countdown === 0 ? "bg-amber-500/20 text-amber-400" : "text-ink-muted",
            )}
          >
            {countdown === 0 ? "今日結算" : `結算 T-${countdown}`}
          </span>
        )}
        <span className="ml-auto">
          <ConnectionBadge status="live" wsStatus={wsStatus} />
        </span>
      </header>
      {/* 水平五檔(與個股共用 DepthBar;SC-5) */}
      <DepthBar
        bids={state?.bids ?? []}
        asks={state?.asks ?? []}
        last={state?.p ?? null}
        ref_={state?.ref ?? null}
        upper={state?.upper ?? null}
        lower={state?.lower ?? null}
      />
      {/* 近全時段主圖(SC-1/2/4/7/8/11)。掛在 DepthBar 下方 —— 五檔是「現在」、
          圖是「怎麼走到現在」,由上而下的閱讀順序。 */}
      {barsKey === null ? null : (
        <FuturesChart product={barsKey} state={state} resolvedYm={resolvedYm} active={active} />
      )}
    </div>
  );
}

export default FuturesPage;
