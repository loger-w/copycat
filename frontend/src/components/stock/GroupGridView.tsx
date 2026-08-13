import { memo, useCallback, useEffect, useRef, useState } from "react";

import { MiniIntradayChart } from "@/components/stock/MiniIntradayChart";
import { useGroupSnapshots, type GroupSnapshot } from "@/hooks/useGroupSnapshots";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { STOCK_GROUP_KEY } from "@/lib/constants";
import { fmt, fmtPct } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Group } from "@/lib/watchlist-model";

/** 群組檢視:自選群組成員的 mini 分時圖牆(group-grid SC-3)。
 *
 *  要回答的問題是「同產業今天有沒有一起動」—— 所以卡片只留代碼 / 名稱 / 現價 /
 *  一條分時線,沒有座標軸、沒有五檔、沒有明細。點任一張卡片切回單檔檢視看細節。 */

interface Props {
  groups: Group[];
  /** WS `watchlist_quote`(每秒);現價與漲跌幅來源,同時餵 mini 圖的末點延伸 */
  quotes: Record<string, WatchlistQuote>;
  onPick: (code: string) => void;
  /** 自選 query 首載中(review A4)。`groups` 空陣列有三種意思,分不出來的話「還在載」
   *  與「後端出事」都會被講成「你還沒建群組」—— 而只有真的零群組才該叫人去建。 */
  wlPending?: boolean;
  /** 自選 query 失敗(同上)。**手上還有舊資料時不採用**:群組結構是慢變數,上一份
   *  仍然有用,拿一句錯誤訊息換掉它是拿走使用者唯一看得到的東西。 */
  wlError?: boolean;
}

function loadGroupName(): string | null {
  try {
    return window.localStorage.getItem(STOCK_GROUP_KEY);
  } catch {
    return null;
  }
}

function persistGroupName(name: string): void {
  try {
    window.localStorage.setItem(STOCK_GROUP_KEY, name);
  } catch {
    // 存不進去就算了 —— 下次開回第一個群組,不值得為此讓整頁掛掉
  }
}

/** 卡片右上的價格區(R11)。`p` 與 `ref` 是**互斥**的兩欄:尚無成交時後端只給 `ref`。
 *  參考價不套漲跌色也不印 `0.00%` —— 那會讓昨收看起來像今天的走勢(同側欄既有紀律)。 */
function QuoteCell({ code, q }: { code: string; q: WatchlistQuote | undefined }) {
  const tone =
    q?.p == null
      ? "text-ink-dim"
      : (q.chg_pct ?? 0) > 0
        ? "text-bull"
        : (q.chg_pct ?? 0) < 0
          ? "text-bear"
          : "text-ink";
  return (
    <span
      data-testid={`group-quote-${code}`}
      className={cn("flex shrink-0 items-baseline gap-1 font-mono text-xs", tone)}
    >
      {q?.p != null ? (
        <>
          <span className="text-sm">{fmt(q.p)}</span>
          <span>{q.chg_pct != null ? fmtPct(q.chg_pct) : "-"}</span>
        </>
      ) : q?.ref != null ? (
        <>
          <span className="text-sm">{fmt(q.ref)}</span>
          <span className="text-[0.625rem]">參考</span>
        </>
      ) : (
        <span className="text-sm">-</span>
      )}
    </span>
  );
}

/** 單張卡片(review A6-1)。抽成 `memo` 子元件而不是留在父層的 `card()`:
 *  `quotes` 每秒整份換 identity → 父層每秒 re-render 一次,而每張卡片都要重跑
 *  `buildIntradayGeometry`(當日最多 271 分鐘 × 50 檔)。memo 之後只有 quote 真的
 *  變了的那幾張會重畫。
 *
 *  `onPick` 由父層以穩定參照傳入(StockPage 的 handler 每次 render 都是新的,但那層
 *  的 re-render 頻率是使用者操作級,不是每秒);`snap` 來自 TQ cache,60s 才換一次。 */
const GroupCard = memo(function GroupCard({
  code,
  snap,
  quote,
  onPick,
}: {
  code: string;
  snap: GroupSnapshot | undefined;
  quote: WatchlistQuote | undefined;
  onPick: (code: string) => void;
}) {
  const name = snap?.meta?.name ?? "";
  // 三態優先序:回補中 → 無資料 → 常態。`snap === undefined` 收斂進無資料 ——
  // batch 整批失敗時全部卡片一命(edge 6)。
  //
  // 「回補中…」是**佔位**,只在真的沒東西可畫時才蓋圖(review A5):已經有分鐘資料
  // (live tick 進來了、或前一輪回補已落地)還蓋掉,等於每次重回補都讓卡片閃回空白,
  // 而重回補在鎖停日的漲跌停值變化上是常態。
  const backfilling = snap?.backfilling === true && (snap?.minutes.size ?? 0) === 0;
  return (
    <button
      type="button"
      data-testid={`group-card-${code}`}
      aria-label={name === "" ? `查看 ${code}` : `查看 ${code} ${name}`}
      onClick={() => onPick(code)}
      className="flex flex-col gap-1 rounded border border-line p-2 text-left hover:border-accent"
    >
      <span className="flex min-w-0 items-baseline gap-1">
        <span className="font-mono text-sm text-ink">{code}</span>
        <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">{name}</span>
        <QuoteCell code={code} q={quote} />
      </span>
      {backfilling ? (
        <span className="flex h-20 items-center justify-center text-xs text-ink-dim">回補中…</span>
      ) : snap === undefined || snap.noData ? (
        <span className="flex h-20 items-center justify-center text-xs text-ink-dim">無資料</span>
      ) : (
        <MiniIntradayChart minutes={snap.minutes} meta={snap.meta} liveP={quote?.p ?? null} />
      )}
    </button>
  );
});

export function GroupGridView({ groups, quotes, onPick, wlPending, wlError }: Props) {
  const [picked, setPicked] = useState<string | null>(loadGroupName);
  // 群組可能在另一個分頁 / Discord 被刪掉,localStorage 留著舊名(edge 5)——
  // fallback 第一個而不是停在空態,否則畫面會說「這個群組還沒有成員」而使用者
  // 根本沒有那一組。衍生值不入 state:同步 state 與 props 正是 effect anti-pattern。
  const selected = groups.find((g) => g.name === picked) ?? groups[0] ?? null;
  const codes = selected?.codes ?? [];
  const { data, isPending } = useGroupSnapshots(codes, codes.length > 0);
  // 給卡片的**穩定** onPick(review A6-1)。`quotes` 每秒換一次 → 本元件每秒 render,
  // 而父層傳進來的 handler 是 inline arrow(每次都是新參照)—— 直接往下傳的話
  // `memo` 每一輪都比不過,30 張卡片照樣全部重畫,memo 形同虛設。
  // latest-ref 而不是要求父層 useCallback:這是葉節點自己的效能問題,不該讓每個
  // 呼叫端記得配合;ref 在 commit 後才更新,而 click 只會發生在 commit 之後。
  const pickRef = useRef(onPick);
  useEffect(() => {
    pickRef.current = onPick;
  }, [onPick]);
  const pick = useCallback((code: string) => pickRef.current(code), []);

  // 空態三分(review A4)。**只在真的沒有群組可畫時**才走這三條:`groups` 一旦有內容
  // (含 TQ 失敗但仍握著上一份 cache)就照畫,錯誤不遮既有資料。
  if (groups.length === 0) {
    const empty = wlPending ? "載入群組…" : wlError ? "自選載入失敗" : "尚無群組 — 到自選欄建立群組";
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-ink-muted">{empty}</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      {/* 可見文字與 `aria-label` 刻意不用 `<label>` 包起來:兩者同時存在時 aria-label
          會蓋掉 label 文字,可及名稱與畫面文字不一致是最難查的 a11y 漂移 */}
      <div className="flex shrink-0 items-center gap-2 text-xs text-ink-muted">
        <span>群組</span>
        <select
          aria-label="選擇群組"
          value={selected?.name ?? ""}
          onChange={(e) => {
            setPicked(e.target.value);
            persistGroupName(e.target.value);
          }}
          className="rounded border border-line bg-bg px-2 py-1 text-sm text-ink outline-none focus:border-accent"
        >
          {groups.map((g) => (
            <option key={g.name} value={g.name}>
              {g.name}
            </option>
          ))}
        </select>
      </div>
      {codes.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-ink-muted">這個群組還沒有成員</p>
        </div>
      ) : isPending ? (
        // 首載未回前**不畫卡片**:卡片的三態全是**終態宣告**,而「無資料」是其中最強的
        // 一句(「這檔今天沒東西可看」)。載入中就先鋪一整面「無資料」再逐格翻回圖,
        // 既是閃爍也是說謊 —— 50 檔的群組會有整整一輪 batch 的時間停在錯的答案上。
        // 錯誤終態不走這條(`isPending` 只涵蓋首載):整批失敗時卡片照畫、答「無資料」。
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-ink-muted">載入群組…</p>
        </div>
      ) : (
        // min-h-0 不可省:少了它 flex 子項不會縮,`overflow-y-auto` 算不出可捲高度
        <div className="grid min-h-0 grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-2 overflow-y-auto">
          {codes.map((code) => (
            <GroupCard
              key={code}
              code={code}
              snap={data?.[code]}
              quote={quotes[code]}
              onPick={pick}
            />
          ))}
        </div>
      )}
    </div>
  );
}
