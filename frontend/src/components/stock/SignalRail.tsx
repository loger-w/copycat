/** 左側訊號欄(design §8.2;SC-9 / signal-rules SC-7)。
 *
 *  **純展示元件**:feed / 規則 / 音效狀態全由呼叫端(StockPage)以 props 餵進來 ——
 *  元件內不呼叫 `useSignalFeed` / `useSignalRules`,免得每個測試都要架 TQ provider,
 *  也讓規則切換的送出只有一個註冊點。 */

import { Fragment } from "react";

import { errText, type SignalRule } from "@/hooks/useSignalRules";
import { fmt, monthDay } from "@/lib/format";
import {
  groupKindLabels,
  groupRuleNames,
  groupSignals,
  kindLabel,
  type KindSegment,
  type SignalGroup,
  type SignalMsg,
} from "@/lib/signal-model";
import { cn } from "@/lib/utils";

interface Props {
  /** 已是「新在前」(`useSignalFeed` 的合併輸出),本元件不再排序。 */
  signals: SignalMsg[];
  /** 後端規則全集(含停用的)—— 停用的也要列出來,否則使用者找不到地方開回來。 */
  rules: SignalRule[];
  /** rules GET 失敗:空陣列在這裡有兩種意思,不分開的話「載入失敗」長得像「零規則」。 */
  rulesError: boolean;
  /** 開關 PUT 的錯誤碼(`errText` 的輸入);null = 沒有錯誤。 */
  toggleError: string | null;
  onToggleRule: (rule: SignalRule) => void;
  onOpenManager: () => void;
  onSelect: (code: string) => void;
  notifPermission: NotificationPermission;
  onRequestNotif: () => void;
  soundOn: boolean;
  onToggleSound: (value: boolean) => void;
  /** baseline 的資料日(後端 hub 的 engine 日別);payload 缺欄 / 未接線 = null。 */
  tradeDate?: string | null;
  /** 後端牆鐘日(同一支 payload 自帶)—— **不用瀏覽器時鐘**:看盤機的時區 / 時鐘
   *  與後端日別是兩回事,拿本機今天去比會在跨日與時區偏移時各錯一種。 */
  today?: string | null;
}

/** 標題文案:資料日 ≠ 後端今日(假日 / 盤前開站)時把日期寫進標題 ——
 *  「今日訊號」四個字會讓人把上一交易日的鎖漲停當成剛剛發生的。
 *
 *  兩欄任一缺(舊後端 / 未接線)一律退「今日訊號」:單邊日期推不出「是不是今天」,
 *  拿本機時鐘補那一半只會在時區 / 跨午夜時給出比沉默更糟的答案。
 *
 *  **缺值的形有兩種**(review C-6):`null`(缺欄)與 `""`(欄在但空)—— 後者用
 *  `!= null` 擋不住,會走到 `monthDay("")` = `""`,標題印成「 訊號」:讀不懂,而且與
 *  「今日訊號」在畫面上只差一個空格。`Boolean()` 把兩種形收成同一條退路。
 *
 *  已知落差(D3'):hub `today_signals()` 是 {engine 日, 牆鐘日} 聯集,rollover
 *  stage2 前標題 = engine 日(與列的內容一致),接受。 */
function railTitle(tradeDate: string | null | undefined, today: string | null | undefined): string {
  // `!!x` 而非 `Boolean(x)`:兩者語意相同,但只有前者是 TS 認得的 aliased condition
  // —— `Boolean()` 呼叫不縮型,下一行的 `monthDay(tradeDate)` 就會收到 `| undefined`。
  const stale = !!tradeDate && !!today && tradeDate !== today;
  return stale ? `${monthDay(tradeDate)} 訊號` : "今日訊號";
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
  if (sig.kind === "surge_pullback") return "text-bear"; // 自峰值回落,方向向下
  if (sig.kind === "limit_lock" || sig.kind === "limit_open") {
    return sig.direction === "down" ? "text-bear" : "text-bull";
  }
  if (sig.kind === "cdp_cross") {
    return sig.direction === "from_above" ? "text-bear" : "text-bull";
  }
  return "text-ink-muted";
}

/** kind 段的 hover 提示:「label(rule)」;rule_name 缺值(舊 jsonl)只留 label。 */
function segmentTitle(seg: KindSegment): string {
  const rule = seg.sig.rule_name;
  return rule === undefined || rule === "" ? seg.label : `${seg.label}(${rule})`;
}

/** 規則名段的 hover 提示:「rule:該規則在這一 tick 發出的 kind 文案」(到達序、去重)。 */
function ruleTitle(group: SignalGroup, name: string): string {
  const labels = new Set<string>();
  for (const item of [...group.items].reverse()) {
    if (item.rule_name === name) labels.add(kindLabel(item));
  }
  return `${name}:${[...labels].join("・")}`;
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
  rulesError,
  toggleError,
  onToggleRule,
  onOpenManager,
  onSelect,
  notifPermission,
  onRequestNotif,
  soundOn,
  onToggleSound,
  tradeDate,
  today,
}: Props) {
  // 標題與 aria-label 同一句(兩處各寫一份就會漂;讀螢幕器唸到的也該是資料日)
  const title = railTitle(tradeDate, today);
  return (
    // border-r:與中間主區的視覺分隔(同 WatchlistSidebar 慣例)
    <aside
      data-testid="signal-rail"
      aria-label={title}
      className="flex w-52 shrink-0 flex-col border-r border-line pr-2"
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <h3 className="shrink-0 border-b border-line px-1 py-1 text-xs text-ink-dim">{title}</h3>
        {/* **關掉規則不再隱藏它今天已發過的列**(signal-rules R14a,🔴 行為改動):
            那些列帶規則名、來源可辨識,而原本的隱藏語意會讓「剛剛看到的訊號」
            在關掉規則的瞬間整批消失,看起來像資料掉了。 */}
        <ul data-testid="signal-rail-list" className="min-h-0 flex-1 overflow-y-auto">
          {/* **同一 tick 合併成一列**(SC-5):CDP 穿越與爆拉/爆跌常常由同一筆成交
              同時觸發,逐則一列時同一秒同一檔就吃掉三四列,而 200px 欄寬本來就只
              放得下十來列。合併只發生在顯示層 —— WS payload / jsonl / toast 仍逐則。 */}
          {groupSignals(signals).map((group) => {
            const segments = groupKindLabels(group);
            const ruleNames = groupRuleNames(group);
            // **合併列才換版**(B3):單則列一行放得下,照舊 truncate;合併列的 kind 段
            // 實測 154px 只分到 95px(38% 被切),改 clamp 2 行 + 規則名另起一行。
            // 「合併」看兩邊:同 kind 兩條規則時 kind 段去重只剩一段,但規則名有兩段,
            // 與 kind 並排照樣搶同一行寬(review round-1)。
            const merged = segments.length > 1 || ruleNames.length > 1;
            return (
              <li key={group.key}>
                <button
                  type="button"
                  onClick={() => onSelect(group.code)}
                  className="flex w-full flex-col gap-0.5 border-b border-line px-1 py-1 text-left leading-tight hover:bg-surface"
                >
                  {/* 兩行式:200px 欄寬一行塞不下時間 + 代號 + 名稱 + 訊號名 + 價格。
                      第一行是「誰、幾點」,第二行是「哪條規則發的、在什麼價位」。 */}
                  <span className="flex w-full items-baseline gap-1">
                    <span className="shrink-0 font-mono text-xs text-ink-dim">
                      {hhmm(group.time)}
                    </span>
                    <span className="shrink-0 font-mono text-sm text-ink">{group.code}</span>
                    <span className="min-w-0 truncate text-xs text-ink-muted">{group.name}</span>
                  </span>
                  <span className="flex w-full items-baseline justify-between gap-1">
                    {/* **並列**不是二選一(review B1):kind 文案是「發生什麼事」(含
                        漲跌幅 / 穿越的線),規則名只是「誰發的」且可取任意字串 ——
                        規則名蓋掉主文時,列表可能整片是「我的規則1」。規則名缺值 =
                        升級當日的舊 jsonl 行,整段不渲染(不留下單獨的分隔符)。
                        合併列改堆疊(kind 上 / 規則名下):並排時兩段搶同一行寬,
                        kind 154 + 規則名 92 > 可用 150,任一段都還是被切。 */}
                    <span
                      className={cn(
                        "min-w-0 gap-1",
                        // column 方向 items-baseline 無意義(退 flex-start),兩分支各自顯式
                        merged ? "flex flex-col items-start" : "flex items-baseline",
                      )}
                    >
                      {/* **逐段各自著色**:一列裡可能同時有突破(紅)與爆跌(綠),
                          整段套第一則的 tone 會把其中一半畫成相反的方向。
                          **逐段 title**(T-12):整列單一 title 看不出 kind 段與規則名段
                          的一對一對應,改成各段自帶「label(rule)」。 */}
                      <span
                        className={cn(
                          "min-w-0 text-xs",
                          merged ? "line-clamp-2 break-words whitespace-normal" : "truncate",
                        )}
                      >
                        {segments.map((seg, i) => (
                          <Fragment key={seg.label}>
                            {/* 分隔符是視覺用的:讀螢幕器唸出來只會把兩段文案黏成一句 */}
                            {i === 0 ? null : (
                              <span aria-hidden="true" className="text-ink-muted">
                                ・
                              </span>
                            )}
                            <span className={toneOf(seg.sig)} title={segmentTitle(seg)}>
                              {seg.label}
                            </span>
                          </Fragment>
                        ))}
                      </span>
                      {/* 規則名段固定單行 truncate:堆疊後已有整行寬(實測 92px < 150),
                          且它只是「誰發的」,截掉時 hover title 有全文;列高上限因此
                          封在 1 + 2 + 1 行,不是 1 + 2 + 2。 */}
                      {ruleNames.length === 0 ? null : (
                        <span className="min-w-0 truncate text-[0.625rem] text-ink-dim">
                          {ruleNames.map((name, i) => (
                            <Fragment key={name}>
                              {i === 0 ? null : <span aria-hidden="true">・</span>}
                              <span title={ruleTitle(group, name)}>{name}</span>
                            </Fragment>
                          ))}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 font-mono text-xs text-ink">{fmt(group.price)}</span>
                  </span>
                </button>
              </li>
            );
          })}
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
        {/* 開關 PUT 失敗只會讓開關彈回原位 —— 沒有這一行就像「點了沒反應」 */}
        {toggleError !== null ? (
          <p className="px-1 py-0.5 text-xs text-bear">{errText(toggleError)}</p>
        ) : null}
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
          {/* 載入失敗 ≠ 零規則(review A5):後者會讓使用者照著空態去新增,
              而真值可能是規則都好好跑著,新增只會撞名失敗 */}
          {rules.length === 0 ? (
            <p className={cn("px-1 py-1 text-xs", rulesError ? "text-bear" : "text-ink-dim")}>
              {rulesError ? "規則載入失敗" : "尚無規則"}
            </p>
          ) : null}
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
