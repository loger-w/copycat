import { ConnectionBadge } from "@/components/ConnectionBadge";
import { cn } from "@/lib/utils";
import type { CorrState, WsStatus } from "@/types";

/** 窗長(秒)→ 表頭文字。 */
export function windowLabel(secs: number): string {
  return secs % 60 === 0 ? `${secs / 60}分` : `${secs}秒`;
}

/** 相關係數色階:中性對比,不用紅綠 —— 那是漲跌語意,套在相關係數上會誤讀方向。
 *
 * 絕對值越高對比越強(強連動一眼可見),接近 0 的弱相關淡出。正負由數字本身的負號表達。
 */
function toneOf(r: number | null): string {
  if (r === null) return "text-ink-dim";
  const abs = Math.abs(r);
  if (abs >= 0.7) return "text-ink";
  if (abs >= 0.4) return "text-ink-muted";
  return "text-ink-dim";
}

function Cell({ r }: { r: number | null }) {
  return (
    <td className={cn("px-3 py-1.5 text-right font-mono tabular-nums", toneOf(r))}>
      {r === null ? "—" : r.toFixed(2)}
    </td>
  );
}

interface Props {
  state: CorrState | null;
  wsStatus: WsStatus;
}

/** 各腿對台指的即時滾動相關係數(SC-7);每秒更新,樣本不足的窗顯示破折號。 */
export function CorrPanel({ state, wsStatus }: Props) {
  if (state === null) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-ink-dim">
        載入中…
      </div>
    );
  }
  const baseLabel = state.legs[state.base]?.label ?? state.base;
  const rows = Object.keys(state.pairs);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-baseline gap-3">
        <h2 className="text-sm text-ink">相關係數(對 {baseLabel})</h2>
        <span className="font-mono text-xs text-ink-dim">
          {state.session === "day" ? "日盤" : "夜盤"}
        </span>
        <span className="ml-auto">
          <ConnectionBadge status="live" wsStatus={wsStatus} />
        </span>
      </div>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-ink-dim">
            <th className="px-3 py-1.5 text-left font-normal">標的</th>
            {state.windows.map((w) => (
              <th key={w} className="px-3 py-1.5 text-right font-normal">
                {windowLabel(w)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((key) => {
            const leg = state.legs[key];
            const pair = state.pairs[key] ?? {};
            const stale = leg?.stale ?? true;
            return (
              <tr
                key={key}
                data-stale={String(stale)}
                className={cn("border-b border-line/50", stale && "opacity-50")}
              >
                <td className="px-3 py-1.5 text-ink">{leg?.label ?? key}</td>
                {state.windows.map((w) => (
                  <Cell key={w} r={pair[`w${w}`] ?? null} />
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs text-ink-dim">
        每秒更新;取樣用最佳買賣中價,樣本不足的窗顯示「—」。
      </p>
    </div>
  );
}

export default CorrPanel;
