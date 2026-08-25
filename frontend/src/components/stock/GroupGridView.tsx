import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CardIntradayChart } from "@/components/stock/CardIntradayChart";
import { RadioPills } from "@/components/ui/RadioPills";
import { useCapitalOrders, useCapitalPositions } from "@/hooks/useCapital";
import { useChartToggles, type ChartToggles } from "@/hooks/useChartToggles";
import { useGroupSnapshots, type GroupSnapshot } from "@/hooks/useGroupSnapshots";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { STOCK_GROUP_KEY } from "@/lib/constants";
import { useFeeDiscount } from "@/lib/fee-discount";
import { EMPTY_FILLS, fillDates, fillsByCode, type FillPoint } from "@/lib/fill-marks";
import { fmt, fmtPct } from "@/lib/format";
import { ymdOf } from "@/lib/ladder-lots";
import {
  cardText,
  chipTitle,
  chipTone,
  EMPTY_POSITIONS,
  futSummary,
  positionsByCode,
  secSummary,
} from "@/lib/position-summary";
import { hasWindowedMinutes } from "@/lib/stock-intraday-svg";
import { readLocal, writeLocal } from "@/lib/storage";
import { cn } from "@/lib/utils";
import type { Group } from "@/lib/watchlist-model";
import type { CapitalPosition } from "@/types";

/** 群組檢視:自選群組成員的分時圖牆(group-grid SC-3)。
 *
 *  要回答的問題是「同產業今天有沒有一起動」。卡片上的圖是**單檔頁同一份渲染碼**
 *  (D4):價位刻度 / VWAP / CDP / 量分佈 / 高低標 / hover 十字線全在 —— 圖牆就是
 *  盯盤主畫面,細節在這裡看得完。點卡片只換右欄閃電梯的標的(D3),檢視不跳;
 *  要進單檔頁走檢視 pill。 */

interface Props {
  groups: Group[];
  /** WS `watchlist_quote`(每秒);現價與漲跌幅來源,同時餵卡片圖的末點延伸 */
  quotes: Record<string, WatchlistQuote>;
  onPick: (code: string) => void;
  /** 右欄閃電梯現在瞄的股號 → 該卡畫選中框(AD-6)。不在當前群組 = 全部未選中(edge 6) */
  active: string | null;
  /** 自選 query 首載中(review A4)。`groups` 空陣列有三種意思,分不出來的話「還在載」
   *  與「後端出事」都會被講成「你還沒建群組」—— 而只有真的零群組才該叫人去建。 */
  wlPending?: boolean;
  /** 自選 query 失敗(同上)。**手上還有舊資料時不採用**:群組結構是慢變數,上一份
   *  仍然有用,拿一句錯誤訊息換掉它是拿走使用者唯一看得到的東西。 */
  wlError?: boolean;
}

/** 檔數 → 格線 class(SC-1)。欄數不由容器寬決定而由檔數決定「最小可容納矩陣」:
 *  同一群組每次打開都是同一個版面,眼睛才記得住哪張卡片在哪。
 *
 *  回傳**靜態字面值**是 Tailwind JIT 的前提 —— JIT 掃的是原始碼字面,`grid-cols-${n}`
 *  拼出來的 class 永遠不會被產出(而且是零錯誤訊號:畫面直接退回單欄)。
 *
 *  列軌下限 `minmax(8rem,1fr)` 不可省:Tailwind 的 `grid-rows-N` = `repeat(N,minmax(0,1fr))`,
 *  列軌可被壓到低於內容高,卡片會**溢軌與下一列重疊**而不是乾淨捲動。過矮視窗時
 *  8rem(標題列 + 圖 80px + padding)撐出的內容高 > 容器高,改走外層捲軸降級。
 *  n>16 不給列軌:固定 4 欄、列高 auto —— auto 軌在有確定容器高(flex-1)時會被
 *  align-content 預設 stretch 等量撐高,所以容器 base class 帶 `content-start`
 *  (review A-1),列高才真的回到內容高(圖 80px 基準)、超出才捲。 */
export function gridShape(n: number): string {
  if (n <= 4) return "grid-cols-2 [grid-template-rows:repeat(2,minmax(8rem,1fr))]";
  if (n <= 6) return "grid-cols-3 [grid-template-rows:repeat(2,minmax(8rem,1fr))]";
  if (n <= 9) return "grid-cols-3 [grid-template-rows:repeat(3,minmax(8rem,1fr))]";
  if (n <= 12) return "grid-cols-4 [grid-template-rows:repeat(3,minmax(8rem,1fr))]";
  if (n <= 16) return "grid-cols-4 [grid-template-rows:repeat(4,minmax(8rem,1fr))]";
  return "grid-cols-4";
}

/** 卡片右上的價格區(R11)。`p` 與 `ref` 是**互斥**的兩欄:尚無成交時後端只給 `ref`。
 *  參考價不套漲跌色也不印 `0.00%` —— 那會讓昨收看起來像今天的走勢(同側欄既有紀律)。 */
function QuoteCell({ code, q }: { code: string; q: WatchlistQuote | undefined }) {
  const tone =
    q?.p == null
      ? // 無成交(參考價 / `-` 兩態)= ink-muted(a11y 批 D4''):卡片格比側欄列更小,
        // ink-dim 對 surface 的 2.92:1 在 mini 卡上實際讀不出來。
        "text-ink-muted"
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
  active,
  toggles,
  fills,
  positions,
  discount,
  sizeClass,
  onPick,
}: {
  code: string;
  snap: GroupSnapshot | undefined;
  quote: WatchlistQuote | undefined;
  active: boolean;
  /** 圖牆頂那一份(**不含 `set`**:toggle 鈕不在卡片內,卡片只讀 —— 沒有理由把寫入口
   *  穿進 memo 邊界。註:`set` 自 2026-08-24 起已包 useCallback 身分穩定,舊理由
   *  「每 render 新 identity 打穿 memo」不再成立,但「卡片只讀」仍然成立) */
  toggles: ChartToggles;
  /** 這一檔今天的成交點(SC-6)。無成交的卡一律拿到同一個 `EMPTY_FILLS` ——
   *  每卡各建一個 `[]` 的話 memo 每輪都比不過,50 張卡照樣每秒全部重畫(W-5)。 */
  fills: readonly FillPoint[];
  /** 這一檔的部位列(SC-4)。無倉的卡一律拿到同一個 `EMPTY_POSITIONS` —— 理由同
   *  `fills`:每卡各建一個 `[]` 的話 memo 每輪都比不過。 */
  positions: readonly CapitalPosition[];
  /** 手續費折數(primitive):與閃電梯同一個 localStorage 真相源。物件傳下來的話
   *  memo 每輪都會比不過,而折數是使用者一年動一次的設定。 */
  discount: number;
  /** ≤16 檔 = `min-h-0`(高度由 1fr 列軌指派);>16 檔 = `h-56` 固定高(AD-7)。
   *  字面值由父層挑好傳進來:Tailwind JIT 掃的是原始碼字面,拼出來的 class 不會被產出。 */
  sizeClass: string;
  onPick: (code: string) => void;
}) {
  const name = snap?.meta?.name ?? "";
  // 三態優先序:回補中 → 無資料 → 常態。`snap === undefined` 收斂進無資料 ——
  // batch 整批失敗時全部卡片一命(edge 6)。
  //
  // 「回補中…」是**佔位**,只在真的沒東西可畫時才蓋圖(review A5):已經有分鐘資料
  // (live tick 進來了、或前一輪回補已落地)還蓋掉,等於每次重回補都讓卡片閃回空白,
  // 而重回補在鎖停日的漲跌停值變化上是常態。
  //
  // 「有沒有東西可畫」只有**一把尺**(review A-1):`minutes.size` 與
  // `hasWindowedMinutes` 兩把並用時,盤前只有 08:59 那格的卡片會落進兩尺之間 ——
  // 回補明明還在跑,卡片卻先宣告終態「尚無成交」。
  const hasBars = snap !== undefined && hasWindowedMinutes(snap.minutes);
  const backfilling = snap?.backfilling === true && !hasBars;
  // 倉位(SC-4)。證券損益吃卡片自己那則 quote 現算(quote 本來就是 memo 的 dep),
  // 個股期走群益 pnl_base。兩者皆無 → 整行不渲染(高度差由圖區的 flex-1 吸收)。
  const sec = secSummary(positions, quote?.p ?? null, discount);
  const fut = futSummary(positions);
  return (
    // `<div role="button">` 而不是 `<button>`(review R11):卡片內容從一條線變成一整張
    // 分時圖(svg + 文字標籤 + hover 十字線),而 `<button>` 的內容模型只吃 phrasing
    // content —— 巢狀非 phrasing 內容在瀏覽器裡是未定義行為。可及性靠 role + tabIndex
    // + aria-label + 鍵盤 handler 自己補回來(原生 button 免費附帶的那三件)。
    <div
      role="button"
      tabIndex={0}
      data-testid={`group-card-${code}`}
      // 「選取」而不是「查看」(review A-p2-7):點卡片**不再進單檔頁**(D3),做的
      // 是把右欄閃電梯的標的換成這一檔。螢幕閱讀器使用者聽到「查看」會以為要換頁,
      // 而實際發生的是下單目標換了 —— 那是真錢那一側,語意錯得起的代價不對稱。
      aria-label={name === "" ? `選取 ${code}` : `選取 ${code} ${name}`}
      aria-pressed={active}
      onClick={() => onPick(code)}
      onKeyDown={(e) => {
        // Space 的 preventDefault 不可省:role=button 的 div 不吃原生鍵盤語意,
        // 空白鍵的預設行為是捲動頁面 —— 圖牆會在選檔的同時往下跳一屏。
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onPick(code);
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col gap-1 rounded border p-2 text-left hover:border-accent",
        // 選中框(AD-6):`ring` 是 box-shadow,**不佔版面** —— 用 border-2 加粗的話
        // 選中的那一格會比別格少 2px 內容寬,矩陣上看得出來一格在跳。
        // hover 只換 border 色,選中另加一圈 ring:兩者疊在同一張卡時仍分得出來。
        active ? "border-accent ring-1 ring-accent" : "border-line",
        sizeClass,
      )}
    >
      <span className="flex min-w-0 items-baseline gap-1">
        <span className="font-mono text-sm text-ink">{code}</span>
        <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">{name}</span>
        <QuoteCell code={code} q={quote} />
      </span>
      {sec !== null || fut !== null ? (
        // 一行不得換行(review C-3):對鎖(`多3/空3張`)+ 雙契約 + 六位數損益的字串
        // 塞得進兩行,而 AD-7 的高度評估是「新行 12px」—— 換行就多吃一行圖高,
        // `flex-1 min-h-0` 會把圖再壓矮一截。截斷後全文靠 title 補(與側欄 chip 同一支)。
        <span
          data-testid={`group-pos-${code}`}
          title={chipTitle(sec, fut)}
          className={cn("truncate font-mono text-[0.625rem] leading-tight", chipTone(sec, fut))}
        >
          {cardText(sec, fut)}
        </span>
      ) : null}
      {backfilling ? (
        <span className="flex h-20 grow items-center justify-center text-xs text-ink-dim">回補中…</span>
      ) : snap === undefined || snap.noData ? (
        <span className="flex h-20 grow items-center justify-center text-xs text-ink-dim">無資料</span>
      ) : !hasBars ? (
        // edge 9:已訂閱、有 meta,但**窗內**一格分鐘都沒有(盤前只有 08:59 的試撮分鐘、
        // 盤後只剩 13:31+)。判準不是 `minutes.size === 0` —— 窗外分鐘照樣讓它非空,
        // 而幾何的 priceLine 仍是空的。卡片自己接住:進 StockIntradayChart 會撞它自己
        // 那個帶 border/bg 的早退框,在卡片裡就是框中框。
        <span className="flex h-20 grow items-center justify-center text-xs text-ink-dim">尚無成交</span>
      ) : (
        <CardIntradayChart
          code={code}
          snap={snap}
          liveP={quote?.p ?? null}
          toggles={toggles}
          fills={fills}
        />
      )}
    </div>
  );
});

/** 圖牆頂 toggle 列的五鈕(SC-2;成交點於 R2 SC-6 加入)。label 與單檔頁逐字相同 —— 同一個圖層在兩個畫面上
 *  叫不同名字,使用者得自己對照。**恆可按**(AD-5):可用性是 per-code 的(某一檔沒
 *  日線 ≠ 整列該反灰),個別卡片取不到 overlay 時該卡不畫,整列不動。 */
const GRID_TOGGLES: { key: "vwap" | "cdp" | "ma" | "vp" | "fills"; label: string }[] = [
  { key: "vwap", label: "均價" },
  { key: "cdp", label: "CDP" },
  { key: "ma", label: "MA" },
  { key: "vp", label: "量分佈" },
  { key: "fills", label: "成交點" },
];

export function GroupGridView({ groups, quotes, onPick, active, wlPending, wlError }: Props) {
  const [picked, setPicked] = useState<string | null>(() => readLocal(STOCK_GROUP_KEY));
  // **一份**在圖牆層(W-7 的 localStorage key 不變):卡片各持一份的話,同一面牆上
  // 最多 50 張卡會各自讀寫同一個 key,而且按哪一張的鈕都只有那一張會變。
  const { toggles, set } = useChartToggles();
  // 群組可能在另一個分頁 / Discord 被刪掉,localStorage 留著舊名(edge 5)——
  // fallback 第一個而不是停在空態,否則畫面會說「這個群組還沒有成員」而使用者
  // 根本沒有那一組。衍生值不入 state:同步 state 與 props 正是 effect anti-pattern。
  const selected = groups.find((g) => g.name === picked) ?? groups[0] ?? null;
  const codes = selected?.codes ?? [];
  const { data, isPending } = useGroupSnapshots(codes, codes.length > 0);
  // 給卡片的**穩定** onPick(review A6-1)。`quotes` 每秒換一次 → 本元件每秒 render,
  // 而父層傳進來的 handler 是 inline arrow(每次都是新參照)—— 直接往下傳的話
  // `memo` 每一輪都比不過,50 張卡片照樣全部重畫,memo 形同虛設。
  // latest-ref 而不是要求父層 useCallback:這是葉節點自己的效能問題,不該讓每個
  // 呼叫端記得配合;ref 在 commit 後才更新,而 click 只會發生在 commit 之後。
  const pickRef = useRef(onPick);
  useEffect(() => {
    pickRef.current = onPick;
  }, [onPick]);
  const pick = useCallback((code: string) => pickRef.current(code), []);

  // 當日成交點(SC-6)。委託列表在**圖牆層取一份**、一次折完所有 code,每卡只取自己
  // 那個 key —— 卡片各掛一份 hook 的話 50 張卡會各折一次同一份 orders。
  //
  // `today` 每 render 現算(AD-9):跨午夜開著頁面時字串一變,下面的 useMemo 自然失效
  // 重算,昨天的成交點跟著消失(deps 放 `new Date()` 物件就永遠失效、放空陣列就永不失效)。
  // 現股口徑 `excludeUnit="股"` 與現股梯一致(AD-3);群組卡只認現股(契約碼→股號
  // 反查留給精確版),所以不必分態。
  //
  // 位置必須在 `groups.length === 0` 早退**之前**:hook 不可條件化(本 repo 沒裝
  // react-hooks lint,漏了不會被擋)。
  const orders = useCapitalOrders().data?.orders;
  const today = ymdOf(new Date());
  const fillsMap = useMemo(() => fillsByCode(orders, fillDates(today), "股"), [orders, today]);

  // 倉位(SC-4)同款:圖牆層取一份、一次折完所有 code,每卡只取自己那個 key。
  // 折數在這一層讀一次(primitive)往下傳 —— 每張卡各掛一份 hook 的話,50 張卡會
  // 各訂閱一次同一個 store。位置同樣必須在 `groups.length === 0` 早退**之前**。
  const positions = useCapitalPositions().data?.positions;
  const posMap = useMemo(() => positionsByCode(positions), [positions]);
  const discount = useFeeDiscount();

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
      {/* `aria-label` 掛在 `RadioPills` 的 radiogroup 容器而不是任何一顆 pill(a11y 批:
          原本是 `role="group"` + `aria-pressed` button 群):容器不是表單控制項,
          不觸 label-in-name(pill 自己的可及名稱就是印在上面的群組名,兩者不打架)。
          這個名稱是**契約**:StockPage.test.tsx 671/713(`queryByLabelText` 鎖「單檔檢視
          不渲染群組檢視」)與 746/750(鎖「重掛後還原群組檢視」)四處都靠它接住 ——
          拿掉的失效樣態是那四條斷言靜默 vacuous(查不到元素與「沒渲染」在 queryBy 下
          長得一模一樣),不是紅燈。 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2">
      <RadioPills<string>
        ariaLabel="選擇群組"
        className="flex flex-wrap items-center gap-2 text-xs text-ink-muted"
        leading={<span>群組</span>}
        value={selected?.name ?? ""}
        onChange={(name) => {
          setPicked(name);
          // 存不進去就算了 —— 下次開回第一個群組,不值得為此讓整頁掛掉(`writeLocal` 不拋)
          writeLocal(STOCK_GROUP_KEY, name);
        }}
        items={groups.map((g) => ({ value: g.name, label: g.name }))}
        pillClass={(_item, checked) =>
          cn(
            "rounded border px-2 py-0.5 text-xs",
            checked ? "border-accent text-accent" : "border-line text-ink-dim hover:text-ink",
          )
        }
      />
        {/* toggle 列與群組 pill 同一行(SC-2):圖牆頂只有一列 chrome,兩列會吃掉
            卡片的高。**不放進 radiogroup 容器內**(連 `trailing` 都不走)—— 那個容器的
            可及名稱是「選擇群組」,而這三顆是**開關**不是單選項,混進去會讓 AT 把
            「vp / 成交點 / 布林」讀成群組選項。 */}
        <div className="ml-auto flex shrink-0 gap-1">
          {GRID_TOGGLES.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              data-testid={`grid-toggle-${key}`}
              aria-pressed={toggles[key]}
              onClick={() => set(key, !toggles[key])}
              className={cn(
                "rounded border px-2 py-0.5 text-xs",
                toggles[key] ? "border-accent text-accent" : "border-line text-ink-dim",
              )}
            >
              {label}
            </button>
          ))}
        </div>
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
        // min-h-0 不可省:少了它 flex 子項不會縮,`overflow-y-auto` 算不出可捲高度。
        // flex-1 = 佔滿 main 的剩餘高 —— 矩陣的列軌是 1fr,沒有確定的容器高就無從均分。
        // content-start 是 >16 分支的成立前提(review A-1):auto 列軌 + 確定容器高時
        // align-content 預設 stretch 會把列等量撐高(17~24 檔不出捲軸、圖高漂離 80px);
        // 對 1fr 矩陣分支則是 no-op(free space 已被軌道吃光)。
        // ≤16 檔:列高均分吃滿中區、不捲動;>16 檔:4 欄、列高回到基準(圖 80px)往下捲。
        <div
          data-testid="group-grid"
          className={cn(
            "grid min-h-0 flex-1 content-start gap-2 overflow-y-auto",
            gridShape(codes.length),
          )}
        >
          {codes.map((code) => (
            <GroupCard
              key={code}
              code={code}
              snap={data?.[code]}
              quote={quotes[code]}
              active={code === active}
              toggles={toggles}
              // 零筆的 code 不入 map → 一律回同一個 `EMPTY_FILLS`(identity 穩定)
              fills={fillsMap.get(code) ?? EMPTY_FILLS}
              // 無倉的 code 不入 map → 一律回同一個 `EMPTY_POSITIONS`(identity 穩定)
              positions={posMap.get(code) ?? EMPTY_POSITIONS}
              discount={discount}
              // >16 檔走捲動軌:列高是 auto,卡片得自己有確定高度,否則
              // `useContainerSize` 量到的高由內容決定 → 「量多高就設多高」的回饋迴圈
              // (RO loop 告警)。≤16 檔由 1fr 列軌指派高,卡片只要能縮(min-h-0)。
              sizeClass={codes.length > 16 ? "h-56" : "min-h-0"}
              onPick={pick}
            />
          ))}
        </div>
      )}
    </div>
  );
}
