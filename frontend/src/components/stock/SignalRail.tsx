/** 左側訊號欄(design §8.2;SC-9)。
 *
 *  **純展示元件**:feed / 開關 / 音效狀態全由呼叫端(StockPage)以 props 餵進來 ——
 *  元件內不呼叫 `useSignalFeed` / `useSignalsConfig`,免得每個測試都要架 TQ provider,
 *  也讓 toggle 的樂觀更新只有一個註冊點。 */

import { fmt } from "@/lib/format";
import {
  filterKinds,
  kindLabel,
  type SignalEnabled,
  type SignalMsg,
  type SignalSwitchKey,
} from "@/lib/signal-model";
import { cn } from "@/lib/utils";

/** 四鍵開關的顯示名(與 `signal-model.KIND_SWITCH` 同一組鍵)。 */
const TOGGLES: readonly (readonly [SignalSwitchKey, string])[] = [
  ["cdp_cross", "CDP 穿越"],
  ["surge_crash", "爆拉爆跌"],
  ["vol_burst", "爆量"],
  ["limit_lock", "鎖漲跌停"],
];

interface Props {
  /** 已是「新在前」(`useSignalFeed` 的合併輸出),本元件不再排序。 */
  signals: SignalMsg[];
  enabled: SignalEnabled;
  onToggle: (key: SignalSwitchKey, value: boolean) => void;
  onSelect: (code: string) => void;
  notifPermission: NotificationPermission;
  onRequestNotif: () => void;
  soundOn: boolean;
  onToggleSound: (value: boolean) => void;
}

/** `HH:MM:SS` → `HH:MM`。窄欄放不下秒,而秒對「幾點發生」的判讀沒有價值。 */
function hhmm(time: string): string {
  return time.slice(0, 5);
}

/** 方向著色(台股慣例:漲紅 = bull / 跌綠 = bear)。盤中靠餘光掃這一欄,
 *  全灰的清單得逐列讀文字才知道是拉是殺。 */
function toneOf(sig: SignalMsg): string {
  if (sig.kind === "surge") return "text-bull";
  if (sig.kind === "crash") return "text-bear";
  if (sig.kind === "limit_lock" || sig.kind === "limit_open") {
    return sig.direction === "down" ? "text-bear" : "text-bull";
  }
  if (sig.kind === "cdp_cross") {
    return sig.direction === "from_above" ? "text-bear" : "text-bull";
  }
  return "text-ink-muted";
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  // role="switch" + aria-checked:原生 checkbox 要另外配 label 才有可及名稱,
  // 而整列可點(不只 3px 的方塊)才符合盤中操作
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-1 px-1 py-1 text-left text-xs hover:bg-surface"
    >
      <span className={checked ? "text-ink" : "text-ink-dim"}>{label}</span>
      <span className={cn("shrink-0 font-mono", checked ? "text-accent" : "text-ink-dim")}>
        {checked ? "開" : "關"}
      </span>
    </button>
  );
}

export function SignalRail({
  signals,
  enabled,
  onToggle,
  onSelect,
  notifPermission,
  onRequestNotif,
  soundOn,
  onToggleSound,
}: Props) {
  // 顯示端也過濾一次(SC-9):後端關掉開關後不再產生新事件,但 baseline jsonl 與
  // live 清單裡仍留著關掉前發過的那些 —— 不過濾的話「關掉類型」在畫面上像沒生效。
  const visible = filterKinds(signals, enabled);

  return (
    // border-r:與中間主區的視覺分隔(同 WatchlistSidebar 慣例)
    <aside
      data-testid="signal-rail"
      aria-label="今日訊號"
      className="flex w-52 shrink-0 flex-col border-r border-line pr-2"
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <h3 className="shrink-0 border-b border-line px-1 py-1 text-xs text-ink-dim">今日訊號</h3>
        <ul data-testid="signal-rail-list" className="min-h-0 flex-1 overflow-y-auto">
          {visible.map((sig) => (
            <li key={sig.id}>
              <button
                type="button"
                onClick={() => onSelect(sig.code)}
                className="flex w-full flex-col gap-0.5 border-b border-line px-1 py-1 text-left leading-tight hover:bg-surface"
              >
                {/* 兩行式:200px 欄寬一行塞不下時間 + 代號 + 名稱 + 訊號名 + 價格。
                    第一行是「誰、幾點」,第二行是「發生什麼、在什麼價位」。 */}
                <span className="flex w-full items-baseline gap-1">
                  <span className="shrink-0 font-mono text-xs text-ink-dim">{hhmm(sig.time)}</span>
                  <span className="shrink-0 font-mono text-sm text-ink">{sig.code}</span>
                  <span className="min-w-0 truncate text-xs text-ink-muted">{sig.name}</span>
                </span>
                <span className="flex w-full items-baseline justify-between gap-1">
                  <span className={cn("min-w-0 truncate text-xs", toneOf(sig))}>
                    {kindLabel(sig)}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-ink">{fmt(sig.price)}</span>
                </span>
              </button>
            </li>
          ))}
          {visible.length === 0 ? (
            <li className="px-1 py-2 text-xs text-ink-dim">尚無訊號</li>
          ) : null}
        </ul>
      </div>

      <div className="shrink-0 border-t border-line pt-1">
        <h3 className="px-1 py-1 text-xs text-ink-dim">監聽訊號</h3>
        {TOGGLES.map(([key, label]) => (
          <Toggle
            key={key}
            label={label}
            checked={enabled[key]}
            onChange={(value) => onToggle(key, value)}
          />
        ))}
        <Toggle label="提示音" checked={soundOn} onChange={onToggleSound} />
        {/* 權限只有 default 能問:granted 不必問,denied 再呼叫也只會被瀏覽器靜默拒絕
            (要使用者自己去網站設定改),留一顆點了沒反應的鈕更糟 */}
        {notifPermission === "default" ? (
          <button
            type="button"
            onClick={onRequestNotif}
            className="m-1 rounded border border-line px-1 py-0.5 text-xs text-ink-dim hover:border-accent hover:text-ink"
          >
            允許通知
          </button>
        ) : null}
      </div>
    </aside>
  );
}
