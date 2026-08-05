/** 左側訊號欄(design §8.2;SC-9 / signal-rules SC-7)。
 *
 *  **純展示元件**:feed / 規則 / 音效狀態全由呼叫端(StockPage)以 props 餵進來 ——
 *  元件內不呼叫 `useSignalFeed` / `useSignalRules`,免得每個測試都要架 TQ provider,
 *  也讓規則切換的送出只有一個註冊點。 */

import type { SignalRule } from "@/hooks/useSignalRules";
import { fmt } from "@/lib/format";
import { kindLabel, type SignalMsg } from "@/lib/signal-model";
import { cn } from "@/lib/utils";

interface Props {
  /** 已是「新在前」(`useSignalFeed` 的合併輸出),本元件不再排序。 */
  signals: SignalMsg[];
  /** 後端規則全集(含停用的)—— 停用的也要列出來,否則使用者找不到地方開回來。 */
  rules: SignalRule[];
  onToggleRule: (rule: SignalRule) => void;
  onOpenManager: () => void;
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
      <span className={cn("min-w-0 truncate", checked ? "text-ink" : "text-ink-dim")}>{label}</span>
      <span className={cn("shrink-0 font-mono", checked ? "text-accent" : "text-ink-dim")}>
        {checked ? "開" : "關"}
      </span>
    </button>
  );
}

export function SignalRail({
  signals,
  rules,
  onToggleRule,
  onOpenManager,
  onSelect,
  notifPermission,
  onRequestNotif,
  soundOn,
  onToggleSound,
}: Props) {
  return (
    // border-r:與中間主區的視覺分隔(同 WatchlistSidebar 慣例)
    <aside
      data-testid="signal-rail"
      aria-label="今日訊號"
      className="flex w-52 shrink-0 flex-col border-r border-line pr-2"
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <h3 className="shrink-0 border-b border-line px-1 py-1 text-xs text-ink-dim">今日訊號</h3>
        {/* **關掉規則不再隱藏它今天已發過的列**(signal-rules R14a,🔴 行為改動):
            那些列帶規則名、來源可辨識,而原本的隱藏語意會讓「剛剛看到的訊號」
            在關掉規則的瞬間整批消失,看起來像資料掉了。 */}
        <ul data-testid="signal-rail-list" className="min-h-0 flex-1 overflow-y-auto">
          {signals.map((sig) => (
            <li key={sig.id}>
              <button
                type="button"
                onClick={() => onSelect(sig.code)}
                className="flex w-full flex-col gap-0.5 border-b border-line px-1 py-1 text-left leading-tight hover:bg-surface"
              >
                {/* 兩行式:200px 欄寬一行塞不下時間 + 代號 + 名稱 + 訊號名 + 價格。
                    第一行是「誰、幾點」,第二行是「哪條規則發的、在什麼價位」。 */}
                <span className="flex w-full items-baseline gap-1">
                  <span className="shrink-0 font-mono text-xs text-ink-dim">{hhmm(sig.time)}</span>
                  <span className="shrink-0 font-mono text-sm text-ink">{sig.code}</span>
                  <span className="min-w-0 truncate text-xs text-ink-muted">{sig.name}</span>
                </span>
                <span className="flex w-full items-baseline justify-between gap-1">
                  {/* 規則名優先(同 kind 多規則靠它辨識來源);缺值 = 升級當日的舊
                      jsonl 行 → 退回 kind 文案,不顯示空白。事件細節(漲跌幅 / 穿越
                      的線)在規則名蓋掉時仍可 hover 看到 —— 窄欄放不下兩者。 */}
                  <span
                    title={kindLabel(sig)}
                    className={cn("min-w-0 truncate text-xs", toneOf(sig))}
                  >
                    {sig.rule_name !== undefined && sig.rule_name !== ""
                      ? sig.rule_name
                      : kindLabel(sig)}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-ink">{fmt(sig.price)}</span>
                </span>
              </button>
            </li>
          ))}
          {signals.length === 0 ? (
            <li className="px-1 py-2 text-xs text-ink-dim">尚無訊號</li>
          ) : null}
        </ul>
      </div>

      <div data-testid="signal-rail-rules" className="shrink-0 border-t border-line pt-1">
        <div className="flex items-center justify-between gap-1 px-1 py-1">
          <h3 className="text-xs text-ink-dim">監聽規則</h3>
          <button
            type="button"
            aria-label="管理訊號規則"
            onClick={onOpenManager}
            className="rounded border border-line px-1 py-0.5 text-xs text-ink-dim hover:border-accent hover:text-ink"
          >
            規則
          </button>
        </div>
        {/* 規則多了會把清單擠光 —— 這一區自己捲,訊號列表的高度不受影響 */}
        <div className="max-h-40 overflow-y-auto">
          {rules.map((rule) => (
            <Toggle
              key={rule.id}
              label={rule.name}
              checked={rule.enabled}
              onChange={() => onToggleRule(rule)}
            />
          ))}
          {rules.length === 0 ? <p className="px-1 py-1 text-xs text-ink-dim">尚無規則</p> : null}
        </div>
      </div>

      {/* 提示音與通知另立一區(review MFS-5):與規則同組時「提示音」會被讀成
          第五條規則,但它管的是抵達方式不是監聽什麼。 */}
      <div data-testid="signal-rail-alerts" className="shrink-0 border-t border-line pt-1">
        <h3 className="px-1 py-1 text-xs text-ink-dim">提示</h3>
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
