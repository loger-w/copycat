/** 台股綜合頁的訊號時間軸 subtab panel(market-overview R4 SC-7;design §9.2)。
 *
 *  **非 active subtab = unmount**(`LimitListSection` / `SectorSection` 同款;2026-08-14
 *  subtab 改版前是「收合 = unmount」),但這裡**刻意沒有** `active` prop:資料是
 *  **一次性 query + WS bus 推播**,沒有輪詢可以 gate —— 加一個 gate 進來
 *  只會擋掉 bus 的即時列,而畫面上看起來像「盤中沒有訊號」。
 *
 *  **兩族同軸,但廣度列要自我標示**:`market_*` 來自 FinMind 快照 diff(精度 5-10s),
 *  與自選池的 tick 級訊號放在同一條時間軸上時,外觀相同會讓人拿快照時刻去推敲秒級
 *  因果 —— 每列一顆「廣度」badge 把精度差寫在畫面上。
 *
 *  **分族由 feed 層負責**(`useSignalFeed({ market: "include" })`,design §9.3):漲停潮日
 *  一分鐘湧進上百則 market 事件,cap 若不分族,自選那幾則會在進到這裡之前就被擠掉,
 *  chips 再怎麼切都救不回來。 */
import { useMemo, useState } from "react";

import { useSignalFeed } from "@/hooks/useSignalFeed";
import { isMarketKind, kindLabel, type SignalMsg } from "@/lib/signal-model";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// kind 篩選(chip 群組)
// ---------------------------------------------------------------------------

/** chip 以**群組**定義而不是逐 kind:使用者問的是「爆拉跌」不是「surge 還是 crash」,
 *  而 `limit_lock` / `limit_open` 是同一個現象的兩端,拆成兩顆只會讓人來回點。
 *
 *  `null` = 全部(不過濾)。市場族用 `isMarketKind` 前綴判別而不是列舉:後端補新的
 *  廣度 kind 時,這顆 chip 不必同步改就仍然收得到。 */
type ChipKey = "all" | "own" | "cdp" | "move" | "vol" | "lock" | "market";

interface Chip {
  key: ChipKey;
  label: string;
  match: ((sig: SignalMsg) => boolean) | null;
}

const CHIPS: Chip[] = [
  { key: "all", label: "全部", match: null },
  // **族層 chip,擺在 kind 層之前**(design §9.3 的驗收原文;§9.2 的列表漏列 →
  // review round-2 FE-5):「這則跟我有關嗎」與「這是哪種訊號」是兩個問題,前者
  // 沒有專屬 chip 的話,想只看自選就得逐 kind 點過去 —— 而 kind 是會增加的,
  // 後端補一種就靜默漏一種。同樣用 `isMarketKind` 的補集,不列舉自選 kind。
  { key: "own", label: "自選", match: (s) => !isMarketKind(s.kind) },
  { key: "cdp", label: "CDP", match: (s) => s.kind === "cdp_cross" },
  { key: "move", label: "爆拉跌", match: (s) => s.kind === "surge" || s.kind === "crash" },
  { key: "vol", label: "爆量", match: (s) => s.kind === "vol_burst" },
  {
    key: "lock",
    label: "鎖板(自選)",
    match: (s) => s.kind === "limit_lock" || s.kind === "limit_open",
  },
  { key: "market", label: "全市場鎖板", match: (s) => isMarketKind(s.kind) },
];

// ---------------------------------------------------------------------------
// 呈現
// ---------------------------------------------------------------------------

/** 方向著色(台股慣例:漲紅 = bull / 跌綠 = bear)。`SignalRail.toneOf` 的同款判定,
 *  多了 market 兩案 —— 那兩案在 rail 裡永遠不會出現(rail 走 exclude 模式)。 */
function toneOf(sig: SignalMsg): string {
  const kind: string = sig.kind;
  if (kind === "surge") return "text-bull";
  if (kind === "crash") return "text-bear";
  if (kind === "cdp_cross") return sig.direction === "from_above" ? "text-bear" : "text-bull";
  // `endsWith` 一次收自選與廣度兩族(`limit_lock` / `market_limit_lock`);
  // 兩族的 `direction` 語意相同(up / down),著色規則不必分開寫。
  if (kind.endsWith("limit_lock") || kind.endsWith("limit_open")) {
    return sig.direction === "down" ? "text-bear" : "text-bull";
  }
  return "text-ink-muted";
}

/** 廣度事件的精度註記。**寫在 title 而不只是顏色**:「這一列晚了幾秒」是判讀前提,
 *  不是裝飾 —— 5-10s 的快照時刻拿去對 tick 級的因果就會得到錯的順序。 */
const BREADTH_TITLE = "FinMind 快照精度 5-10s,非 tick 級";

function TimelineBody({ onOpenStock }: { onOpenStock?: (code: string) => void }) {
  const { signals, baselineError } = useSignalFeed({ market: "include" });
  // 篩選態刻意不持久化(design §9.2):它是「現在想看什麼」不是偏好,
  // 隔天開站停在昨天切的那顆 chip 只會讓人以為訊號沒了。
  const [chip, setChip] = useState<ChipKey>("all");

  const match = CHIPS.find((c) => c.key === chip)?.match ?? null;
  // feed 已依 time 降冪(新在前),這裡**只過濾不重排** —— 再排一次就是同一份排序
  // 邏輯的第二份實作,兩份會漂。
  const rows = useMemo(
    () => (match === null ? signals : signals.filter(match)),
    [signals, match],
  );

  // 「今天完全沒有訊號」與「自己把 chip 切窄了」是兩句話:共用一句文案會讓後者
  // 看起來像系統沒在跑。
  //
  // **第三句是「取數失敗」**(review round-2 FE-1 / XR-3):達錢 4 沒開時 baseline 端點
  // 回 503,清單同樣是空的 —— 兩者同形已是 CLAUDE.md 記載的既知陷阱,而「今日尚無
  // 訊號」會讓人以為系統好好的、只是今天很安靜,不會去查服務。
  let message: string | null = null;
  if (signals.length === 0) {
    message = baselineError ? "訊號服務未就緒或取數失敗(即時訊號仍會顯示)" : "今日尚無訊號";
  } else if (rows.length === 0) message = "無符合條件";

  return (
    <div data-testid="signal-timeline-body" className="flex flex-col gap-2 px-4 pb-4">
      <div className="flex flex-wrap items-center gap-1">
        {CHIPS.map((c) => (
          <button
            key={c.key}
            type="button"
            data-testid={`signal-timeline-chip-${c.key}`}
            aria-pressed={chip === c.key}
            onClick={() => setChip(c.key)}
            className={cn(
              "rounded border px-2 py-0.5 text-xs pointer-coarse:min-h-11",
              chip === c.key
                ? "border-accent bg-accent/15 text-ink"
                : "border-line text-ink-dim hover:text-ink",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* 清單有東西時失敗不能只是靜靜地少幾列:live 那條路照樣在推,畫面看起來完全
          正常,但少掉的是「今天稍早發生過什麼」—— 那正是時間軸的用途。 */}
      {baselineError && signals.length > 0 ? (
        <p data-testid="signal-timeline-baseline-error" className="text-xs text-ink-muted">
          歷史訊號載入失敗,僅顯示即時訊號
        </p>
      ) : null}

      {message !== null ? (
        <p data-testid="signal-timeline-msg" className="py-6 text-center text-sm text-ink-muted">
          {message}
        </p>
      ) : (
        <ul data-testid="signal-timeline-list" className="flex flex-col">
          {rows.map((sig) => (
            <li key={sig.id}>
              <button
                type="button"
                data-testid={`signal-timeline-row-${sig.id}`}
                onClick={() => onOpenStock?.(sig.code)}
                className="flex w-full items-baseline gap-2 border-b border-line/50 px-1 py-1 text-left text-sm hover:bg-bg-deep pointer-coarse:min-h-11"
              >
                {/* 秒不可省:廣度事件的精度就是靠「同一分鐘裡誰先誰後」在讀 */}
                <span className="shrink-0 font-mono text-xs text-ink-dim">{sig.time}</span>
                <span className="shrink-0 font-mono text-ink">{sig.code}</span>
                <span className="min-w-0 shrink truncate text-xs text-ink-muted">{sig.name}</span>
                <span className={cn("min-w-0 flex-1 truncate text-xs", toneOf(sig))}>
                  {kindLabel(sig)}
                </span>
                {isMarketKind(sig.kind) ? (
                  <span
                    data-testid={`signal-timeline-badge-${sig.id}`}
                    title={BREADTH_TITLE}
                    className="shrink-0 rounded border border-line px-1 text-[0.625rem] text-ink-dim"
                  >
                    廣度
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// subtab panel 殼
// ---------------------------------------------------------------------------

export function SignalTimelineSection({ onOpenStock }: { onOpenStock?: (code: string) => void }) {
  return (
    <div data-testid="signal-timeline" className="px-4 pb-4">
      <TimelineBody onOpenStock={onOpenStock} />
    </div>
  );
}

export default SignalTimelineSection;
