import { useState } from "react";

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

export function GroupGridView({ groups, quotes, onPick }: Props) {
  const [picked, setPicked] = useState<string | null>(loadGroupName);
  // 群組可能在另一個分頁 / Discord 被刪掉,localStorage 留著舊名(edge 5)——
  // fallback 第一個而不是停在空態,否則畫面會說「這個群組還沒有成員」而使用者
  // 根本沒有那一組。衍生值不入 state:同步 state 與 props 正是 effect anti-pattern。
  const selected = groups.find((g) => g.name === picked) ?? groups[0] ?? null;
  const codes = selected?.codes ?? [];
  const { data, isPending } = useGroupSnapshots(codes, codes.length > 0);

  if (groups.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-ink-muted">尚無群組 — 到自選欄建立群組</p>
      </div>
    );
  }

  function card(code: string) {
    const snap: GroupSnapshot | undefined = data?.[code];
    const name = snap?.meta?.name ?? "";
    // 三態優先序:回補中 → 無資料 → 常態。回補完就會有資料,回補中說「無資料」是錯的;
    // `snap === undefined` 收斂進無資料 —— batch 整批失敗時全部卡片一命(edge 6)。
    const backfilling = snap?.backfilling === true;
    return (
      <button
        key={code}
        type="button"
        data-testid={`group-card-${code}`}
        aria-label={name === "" ? `查看 ${code}` : `查看 ${code} ${name}`}
        onClick={() => onPick(code)}
        className="flex flex-col gap-1 rounded border border-line p-2 text-left hover:border-accent"
      >
        <span className="flex min-w-0 items-baseline gap-1">
          <span className="font-mono text-sm text-ink">{code}</span>
          <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">{name}</span>
          <QuoteCell code={code} q={quotes[code]} />
        </span>
        {backfilling ? (
          <span className="flex h-20 items-center justify-center text-xs text-ink-dim">
            回補中…
          </span>
        ) : snap === undefined || snap.noData ? (
          <span className="flex h-20 items-center justify-center text-xs text-ink-dim">
            無資料
          </span>
        ) : (
          <MiniIntradayChart
            minutes={snap.minutes}
            meta={snap.meta}
            liveP={quotes[code]?.p ?? null}
          />
        )}
      </button>
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
        // 既是閃爍也是說謊 —— 30 檔的群組會有整整一輪 batch 的時間停在錯的答案上。
        // 錯誤終態不走這條(`isPending` 只涵蓋首載):整批失敗時卡片照畫、答「無資料」。
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-ink-muted">載入群組…</p>
        </div>
      ) : (
        // min-h-0 不可省:少了它 flex 子項不會縮,`overflow-y-auto` 算不出可捲高度
        <div className="grid min-h-0 grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-2 overflow-y-auto">
          {codes.map((code) => card(code))}
        </div>
      )}
    </div>
  );
}
