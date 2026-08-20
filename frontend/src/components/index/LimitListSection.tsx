/** 台股綜合頁右欄的漲跌停列表(market-overview R3;design §5.2)。
 *
 *  **恆掛在台股綜合右欄**(2026-08-16 subtab 機制退役,一頁總覽):不再有「切走即
 *  unmount」那道閘,payload 是全市場約 2800 列 × 15 欄、盤中每 10 秒一份,省頻寬
 *  全靠 `active` —— App 以 `hidden` 保留本頁 DOM,切到別的主 tab 時 `active` 轉
 *  false,`useBreadthRows` 的輪詢跟著停(頁內其餘背景輪詢同一道 gate)。
 *  **這裡不需要 `React.lazy`**:本元件無 WS、無圖表、無重依賴,lazy 只會多一個
 *  Suspense 空窗與一條測不到的非同步路徑。
 *
 *  **前端零日期推理**(design R1):`streak` / `streak_capped` 都由後端算完,這裡只負責
 *  把 null / capped 翻成文案。任何「今天是不是還要 +1」的算術一旦在前端重做一份,
 *  盤前、假日、rows 為上一交易日快照這三條路就會各錯一種。 */
import { useMemo, useState } from "react";

import { useBreadthRows } from "@/hooks/useBreadthRows";
import { LIMIT_LIST_FILTER_KEY } from "@/lib/constants";
import { isoLocalDate } from "@/lib/trading-calendar";
import { cn } from "@/lib/utils";
import type { BreadthRow } from "@/types";

// ---------------------------------------------------------------------------
// 狀態歸屬(design R8:優先序 limit_up > limit_down > touched,badge 唯一)
// ---------------------------------------------------------------------------

type RowStatus = "limit_up" | "limit_down" | "touched";

const STATUS_LABEL: Record<RowStatus, string> = {
  limit_up: "漲停",
  limit_down: "跌停",
  touched: "觸及未鎖",
};

/** 分組排序用的名次;同時是「多狀態列歸哪一類」的優先序。 */
const STATUS_ORDER: Record<RowStatus, number> = { limit_up: 0, limit_down: 1, touched: 2 };

const STATUS_TONE: Record<RowStatus, string> = {
  limit_up: "border border-bull/40 bg-bull/15 text-bull",
  limit_down: "border border-bear/40 bg-bear/15 text-bear",
  touched: "border border-line bg-bg-deep text-ink-muted",
};

const MARKET_LABEL: Record<BreadthRow["market"], string> = { twse: "上市", tpex: "上櫃" };

/** 資料格與表頭共用的左右 padding。**窄右欄收成 `px-1`**(9 個 cell 各省 8px = 72px)。
 *
 *  門檻用 **rem 不用 px**:表格內容是 rem 字級,「塞不塞得下」隨 root font-size 縮放
 *  (≥1920 → 112.5%、≥2560 → 125%)—— 41rem = 656@100% / 738@112.5% / 820@125%。
 *  這與 `frontend-conventions` 那條「container query 門檻用 px 任意值」的案例**方向相反**:
 *  那裡量的是固定 px 的面板寬,這裡量的是「rem 內容塞不塞得下 rem 門檻」。 */
const CELL_X = "px-2 @max-[41rem]:px-1";

/** 窄右欄下不顯示的欄位(金額(億) / 量比)。`hidden` = `display:none`,對 table-cell
 *  合法且 th / td 必須成對掛,只掛一邊會讓整張表錯欄。
 *
 *  **為什麼藏這兩欄**:1536 兩欄態的捲動容器只有 431px 而九欄表 scrollWidth 612px,
 *  恆有水平捲軸把狀態徽章推到看不見的地方。只收 padding(→540)或只藏兩欄(→472)
 *  都還是捲,兩者併用才 ~416 < 431。挑中這兩欄是因為它們的**資料與篩選邏輯照舊**
 *  (篩選列的「金額(億)」門檻仍在,量比只是輔助排序線索),藏的只是顯示(W-5)。 */
const NARROW_HIDDEN = "@max-[41rem]:hidden";

/** 表頭儲存格的共用 class(對齊方向逐欄另加)。列表整高內捲後表頭必須黏住,否則
 *  捲兩列就只剩九欄無名數字。
 *
 *  **分隔線走 inset shadow 不用 `border-b`**(WL-4):`border-collapse` 下 th 的 border
 *  被併進表格的邊框模型、由 `<table>` 這個不黏的元素畫 —— 捲到中段時底線留在原地,
 *  黏住的表頭底下就沒有分隔了(1px 的差別,但那是「表頭到哪為止」的唯一線索)。
 *  box-shadow 畫在 th 自己的 box 上,黏到哪畫到哪;`var(--color-line)` 直接取同一顆
 *  token(Tailwind 任意值語法不吃 `theme()` 之外的別名)。
 *  `whitespace-nowrap`:窄右欄(1536 兩欄態 475px)下「金額(億)」會折行把表頭撐高。 */
const TH = `sticky top-0 z-10 whitespace-nowrap bg-surface ${CELL_X} py-1 font-normal shadow-[inset_0_-1px_0_var(--color-line)]`;

/** 一列的唯一狀態;三者皆無 → null(該列不入表)。
 *
 *  「觸及漲停後殺到跌停」這種多狀態列必須歸唯一一類,否則同一檔會在兩個篩選分類下
 *  各出現一次、badge 也會長出兩顆。 */
function statusOf(row: BreadthRow): RowStatus | null {
  if (row.limit_up) return "limit_up";
  if (row.limit_down) return "limit_down";
  if (row.touched_limit_up || row.touched_limit_down) return "touched";
  return null;
}

// ---------------------------------------------------------------------------
// 篩選(OR 狀態 × AND 門檻)
// ---------------------------------------------------------------------------

export interface LimitListFilter {
  twse: boolean;
  tpex: boolean;
  limitUp: boolean;
  limitDown: boolean;
  touched: boolean;
  /** 成交金額下限,**億元**;空字串 = 不限 */
  minAmount: string;
  /** 股價下 / 上限(`close`);空字串 = 不限 */
  priceMin: string;
  priceMax: string;
}

const DEFAULT_FILTER: LimitListFilter = {
  twse: true,
  tpex: true,
  limitUp: true,
  limitDown: true,
  touched: true,
  minAmount: "",
  priceMin: "",
  priceMax: "",
};

/** 門檻欄位是 `string` 不是 `number | null`:number input 的「清空」是空字串,
 *  轉成 0 會靜默變成「金額 ≥ 0 億」這個看起來一樣、語意卻不同的門檻。
 *  非數字(輸入法中途 / 貼上文字)一律視同不限,不讓 NaN 進比較式。
 *
 *  `typeof raw !== "string"` 這道防禦不是多餘的:型別只在編譯期成立,而這個值的
 *  來源是 localStorage(使用者 / 舊版 / 別的分頁都寫得進去)。`loadFilter` 已在入口
 *  正規化,這裡是第二道 —— 它在 render 路徑上,而專案沒有 ErrorBoundary,漏掉就是白屏。 */
function threshold(raw: string): number | null {
  if (typeof raw !== "string") return null;
  if (raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** 缺值一律**不過門檻**(design §5.2):`total_amount` / `close` 為 null 代表快照沒給,
 *  當成 0 會讓「金額 ≥ 5 億」把資料缺漏的列一起濾掉還看不出來,當成無限大更糟。
 *  沒設門檻時它們照常入表 —— 只有「有門檻」才排除。 */
function passes(row: BreadthRow, status: RowStatus, f: LimitListFilter): boolean {
  if (!(row.market === "twse" ? f.twse : f.tpex)) return false;
  if (status === "limit_up" && !f.limitUp) return false;
  if (status === "limit_down" && !f.limitDown) return false;
  if (status === "touched" && !f.touched) return false;

  const minAmount = threshold(f.minAmount);
  if (minAmount !== null && (row.total_amount === null || row.total_amount < minAmount * 1e8)) {
    return false;
  }
  const lo = threshold(f.priceMin);
  if (lo !== null && (row.close === null || row.close < lo)) return false;
  const hi = threshold(f.priceMax);
  if (hi !== null && (row.close === null || row.close > hi)) return false;
  return true;
}

/** 逐欄取值:型別不符即退回該欄預設。
 *
 *  `{ ...DEFAULT_FILTER, ...parsed }` 只擋得掉「整包不是 object」,擋不掉「形狀對但
 *  欄位型別錯」—— 而後者正是舊版 schema / 手動編輯 / 別的分頁寫入會產生的東西,
 *  一路灌進 `threshold` 就是 render 期 TypeError(無 ErrorBoundary = 白屏,且壞值
 *  留在 localStorage 裡,重整也修不好)。 */
function pickBool(src: Record<string, unknown>, key: keyof LimitListFilter, fallback: boolean) {
  const v = src[key];
  return typeof v === "boolean" ? v : fallback;
}

function pickText(src: Record<string, unknown>, key: keyof LimitListFilter): string {
  const v = src[key];
  return typeof v === "string" ? v : "";
}

function loadFilter(): LimitListFilter {
  try {
    const raw = window.localStorage.getItem(LIMIT_LIST_FILTER_KEY);
    if (!raw) return DEFAULT_FILTER;
    const parsed: unknown = JSON.parse(raw);
    // `JSON.parse("null")` 成功且回 null;陣列 / 字串同樣是合法 JSON —— 解構在 try 之外
    // 就會是 TypeError,而這裡是 useState initializer,拋出去就是整頁白屏。
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return DEFAULT_FILTER;
    }
    const o = parsed as Record<string, unknown>;
    return {
      twse: pickBool(o, "twse", DEFAULT_FILTER.twse),
      tpex: pickBool(o, "tpex", DEFAULT_FILTER.tpex),
      limitUp: pickBool(o, "limitUp", DEFAULT_FILTER.limitUp),
      limitDown: pickBool(o, "limitDown", DEFAULT_FILTER.limitDown),
      touched: pickBool(o, "touched", DEFAULT_FILTER.touched),
      minAmount: pickText(o, "minAmount"),
      priceMin: pickText(o, "priceMin"),
      priceMax: pickText(o, "priceMax"),
    };
  } catch {
    return DEFAULT_FILTER;
  }
}

function persistFilter(filter: LimitListFilter): void {
  try {
    window.localStorage.setItem(LIMIT_LIST_FILTER_KEY, JSON.stringify(filter));
  } catch {
    // 存不進去就算了 —— 偏好不落檔遠好於畫面崩掉(useChartToggles 同慣例)
  }
}

// ---------------------------------------------------------------------------
// 排序與文案
// ---------------------------------------------------------------------------

interface Entry {
  row: BreadthRow;
  status: RowStatus;
}

/** 漲停(連板深 → 淺)→ 跌停 → 觸及;組內成交金額 desc。
 *
 *  `streak` 為 null 視為 -1 排該組最後(R8):連板未就緒時整組都是 null → 全部同分,
 *  自然退回金額排序,不會因為 null 參與比較而讓順序在 ready 前後跳動。 */
function amountRank(row: BreadthRow): number {
  return row.total_amount ?? -Infinity;
}

function buildEntries(rows: BreadthRow[], filter: LimitListFilter): Entry[] {
  const entries: Entry[] = [];
  for (const row of rows) {
    const status = statusOf(row);
    if (status === null) continue;
    if (!passes(row, status, filter)) continue;
    entries.push({ row, status });
  }
  entries.sort((a, b) => {
    const group = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
    if (group !== 0) return group;
    const sa = a.row.streak ?? -1;
    const sb = b.row.streak ?? -1;
    if (sa !== sb) return sb - sa;
    const aa = amountRank(a.row);
    const ab = amountRank(b.row);
    // 兩邊都缺值時 `ab - aa` 是 NaN(comparator 回 NaN 的行為未定義)—— 先判等值
    return aa === ab ? 0 : ab - aa;
  });
  return entries;
}

/** 非漲停列一律空白(不是「-」):跌停 / 觸及的列本來就沒有連板這回事,
 *  印破折號會讓人以為是「有但取不到」。「-」專門留給「漲停但連板數不可得」。 */
function streakText(row: BreadthRow): string {
  if (!row.limit_up) return "";
  if (row.streak === null) return "-";
  return row.streak_capped ? `${row.streak}+ 板` : `連 ${row.streak} 板`;
}

function changeText(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function changeTone(v: number): string {
  if (v > 0) return "text-bull";
  if (v < 0) return "text-bear";
  return "text-ink-muted";
}

function amountText(v: number | null): string {
  return v === null ? "—" : (v / 1e8).toFixed(1);
}

function decimalText(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

/** `YYYY-MM-DD` → `MM-DD`(SC-10)。年份在盤面上是雜訊,而月日是「這是哪一天的收盤」
 *  唯一需要的資訊;形狀不合就原樣印出來(寧可醜也不要靜默切錯字串)。 */
function monthDay(iso: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.slice(5) : iso;
}

// ---------------------------------------------------------------------------
// 篩選列元件
// ---------------------------------------------------------------------------

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-xs text-ink-muted">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="accent-accent"
      />
      {label}
    </label>
  );
}

function NumField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="flex items-center gap-1 text-xs text-ink-muted">
      {label}
      <input
        type="number"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-16 rounded border border-line bg-bg px-1 py-0.5 text-right font-mono text-xs text-ink"
      />
    </label>
  );
}

// ---------------------------------------------------------------------------
// 展開後的本體
// ---------------------------------------------------------------------------

function LimitListBody({
  onOpenStock,
  active,
}: {
  onOpenStock?: (code: string) => void;
  active: boolean;
}) {
  const { data, isError } = useBreadthRows(active);
  const [filter, setFilter] = useState<LimitListFilter>(loadFilter);

  function update(patch: Partial<LimitListFilter>): void {
    const next = { ...filter, ...patch };
    setFilter(next);
    persistFilter(next);
  }

  const entries = useMemo(
    () => (data === undefined ? [] : buildEntries(data.rows, filter)),
    [data, filter],
  );

  /** 「今天有幾檔進得了這張表」——**篩選前**的狀態池。與 `entries.length` 分開算才能
   *  把系統態(全市場一檔都沒鎖)與操作結果(自己把篩選收太緊)講成兩句話。 */
  const pool = useMemo(
    () =>
      data === undefined ? 0 : data.rows.reduce((n, r) => (statusOf(r) === null ? n : n + 1), 0),
    [data],
  );

  // 空狀態判別子是 `as_of` 不是 `stale`(design R18):`stale` 在冷啟動 degraded 下恆為
  // true,拿它分流會讓「載入中」與「有資料但延遲」兩態顛倒。
  // `enabled=false` 要排在最前面 —— 那是「去設 .env」不是「等一下就好」。
  // 端點恆 200,能走到 isError 的只有網路 / proxy 斷 —— 但那條路必須說出來:
  // 少了它,`data` 恆 undefined 會讓畫面永遠停在「載入中…」(把已放棄說成還在等)。
  //
  // **`isError` 要跟 `data === undefined` 綁在一起**(review FE-1):TQ v5 的 `isError`
  // 對 refetch 失敗同樣為 true,單看它會讓「已有一整張表、只是這一輪 10 秒輪詢沒抓到」
  // 整表消失換成「載入失敗」—— 盤中最該盯的那份資料因一次網路抖動被清掉。
  // 有 data 就保表,失敗改由標題列的「更新失敗」膠囊說。
  const loadFailed = isError && data === undefined;
  const refetchFailed = isError && data !== undefined;

  // SC-10:非交易日(週末 / 國定假日)開站時 rows 是**上一交易日收盤**的快照,而畫面
  // 上原本沒有任何線索 —— 看到的是一張「今天的漲跌停」。`trade_date` 為 null(冷啟動
  // 未定)不算非今日:那是「還不知道」,標一個日期出來等於編造。
  // 判別走 `isoLocalDate`(本機時區)不是 `toISOString()`:後者是 UTC,台北 08:00 前
  // 會退成前一天 → 每天早盤都會誤標「昨天收盤」。
  const todayIso = isoLocalDate(new Date());
  const tradeDate = data?.trade_date ?? null;
  const tradeMonthDay = tradeDate !== null && tradeDate !== todayIso ? monthDay(tradeDate) : null;
  const notToday = tradeMonthDay !== null;

  let message: string | null = null;
  if (loadFailed) message = "載入失敗";
  else if (data === undefined) message = "載入中…";
  else if (!data.enabled) message = "FinMind 未設定";
  else if (data.as_of === null) message = "載入中…";
  else if (data.rows.length === 0) message = "暫無資料(延遲)";
  else if (pool === 0) message = notToday ? `${tradeMonthDay} 尚無漲跌停` : "今日尚無漲跌停";
  else if (entries.length === 0) message = "無符合條件";

  return (
    <div data-testid="limit-list-body" className="flex min-h-0 flex-1 flex-col gap-2 px-4 pb-4">
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {/* 資料日膠囊(SC-10):與「延遲」同排同形狀,但**中性灰**而非琥珀色 ——
            「這是上一交易日的完整收盤資料」是陳述,不是警示;沿用 stale 的顏色 /
            testid 會把兩件事說成同一件(R2-8 明訂 testid 不得共用)。 */}
        {notToday ? (
          <span
            data-testid="limit-list-asof-date"
            className="rounded bg-bg-deep px-1.5 text-xs text-ink-muted"
          >
            {tradeMonthDay} 收盤
          </span>
        ) : null}
        {data?.stale ? (
          <span
            data-testid="limit-list-stale"
            className="rounded bg-amber-500/20 px-1.5 text-xs text-amber-400"
          >
            延遲
          </span>
        ) : null}
        {refetchFailed ? (
          <span
            data-testid="limit-list-refetch-error"
            className="rounded border border-amber-500/40 px-1.5 text-xs text-amber-400"
          >
            更新失敗
          </span>
        ) : null}
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1">
        <Check label="上市" checked={filter.twse} onChange={(v) => update({ twse: v })} />
        <Check label="上櫃" checked={filter.tpex} onChange={(v) => update({ tpex: v })} />
        <span className="h-3 w-px bg-line" />
        <Check label="漲停" checked={filter.limitUp} onChange={(v) => update({ limitUp: v })} />
        <Check
          label="跌停"
          checked={filter.limitDown}
          onChange={(v) => update({ limitDown: v })}
        />
        <Check label="觸及未鎖" checked={filter.touched} onChange={(v) => update({ touched: v })} />
        <span className="h-3 w-px bg-line" />
        <NumField
          label="金額(億)"
          value={filter.minAmount}
          onChange={(v) => update({ minAmount: v })}
        />
        <NumField
          label="股價下限"
          value={filter.priceMin}
          onChange={(v) => update({ priceMin: v })}
        />
        <NumField
          label="股價上限"
          value={filter.priceMax}
          onChange={(v) => update({ priceMax: v })}
        />
      </div>

      {/* 捲動容器**恆存**(文案與表格兩分支都包在裡面):只包表格的話,空態那一幀
          容器消失 → flex 高度重算 → 資料回來又長回去,右欄會抖一下;SC-3 的量測也
          會在空態量不到節點。整高內捲 = 列表再長也不把左欄推出視窗。 */}
      <div data-testid="limit-list-scroll" className="min-h-0 flex-1 overflow-auto">
        {message !== null ? (
          <p data-testid="limit-list-msg" className="py-6 text-center text-sm text-ink-muted">
            {message}
          </p>
        ) : (
          <table data-testid="limit-list-table" className="w-full border-collapse text-sm">
            <thead>
              {/* sticky 掛在**每個 th** 而不是 tr:`border-collapse` 下 tr 不建立自己的
                  背景 / 邊框層,黏住的只有 th —— tr 上的 border-b 捲動時會留在原地,
                  底色也透不出來。九欄各自帶 bg-surface + inset shadow 分隔線(WL-4:
                  border 同樣不黏,見 `TH`)才是完整的表頭列。 */}
              <tr className="text-ink-dim">
                <th className={cn(TH, "text-left")}>代號</th>
                <th className={cn(TH, "text-left")}>名稱</th>
                <th className={cn(TH, "text-left")}>市場</th>
                <th className={cn(TH, "text-right")}>現價</th>
                <th className={cn(TH, "text-right")}>漲跌幅</th>
                <th className={cn(TH, "text-right")}>連板</th>
                <th className={cn(TH, "text-right", NARROW_HIDDEN)}>金額(億)</th>
                <th className={cn(TH, "text-right", NARROW_HIDDEN)}>量比</th>
                <th className={cn(TH, "text-left")}>狀態</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(({ row, status }) => (
                <tr
                  key={row.stock_id}
                  data-testid={`limit-row-${row.stock_id}`}
                  onClick={() => onOpenStock?.(row.stock_id)}
                  className="cursor-pointer border-b border-line/50 hover:bg-bg-deep"
                >
                  <td className={cn(CELL_X, "py-1 font-mono text-ink")}>{row.stock_id}</td>
                  {/* 名稱與連板兩欄 nowrap:四字檔名(台聯電 / 長榮航太)與「連 4 板」
                      在右欄寬度下會折成兩行,列高從 24 撐到 40px —— 折的是「一屏看得到
                      幾檔」。其餘欄位是數字或兩字標籤,折不了也就不掛。 */}
                  <td
                    data-testid={`limit-name-${row.stock_id}`}
                    className={cn(CELL_X, "py-1 whitespace-nowrap text-ink")}
                  >
                    {row.name}
                  </td>
                  <td
                    data-testid={`limit-market-${row.stock_id}`}
                    className={cn(CELL_X, "py-1 text-ink-muted")}
                  >
                    {MARKET_LABEL[row.market]}
                  </td>
                  <td
                    data-testid={`limit-close-${row.stock_id}`}
                    className={cn(CELL_X, "py-1 text-right font-mono tabular-nums text-ink")}
                  >
                    {decimalText(row.close)}
                  </td>
                  <td
                    data-testid={`limit-change-${row.stock_id}`}
                    className={cn(
                      CELL_X,
                      "py-1 text-right font-mono tabular-nums",
                      changeTone(row.change_rate),
                    )}
                  >
                    {changeText(row.change_rate)}
                  </td>
                  <td
                    data-testid={`limit-streak-${row.stock_id}`}
                    className={cn(CELL_X, "py-1 text-right whitespace-nowrap text-ink")}
                  >
                    {streakText(row)}
                  </td>
                  {/* 金額 / 量比:窄右欄不顯示(th 同步藏,見 `NARROW_HIDDEN`)。
                      資料與篩選邏輯不動 —— 兩者的門檻仍在篩選列上。 */}
                  <td
                    data-testid={`limit-amount-${row.stock_id}`}
                    className={cn(
                      CELL_X,
                      "py-1 text-right font-mono tabular-nums text-ink",
                      NARROW_HIDDEN,
                    )}
                  >
                    {amountText(row.total_amount)}
                  </td>
                  <td
                    data-testid={`limit-ratio-${row.stock_id}`}
                    className={cn(
                      CELL_X,
                      "py-1 text-right font-mono tabular-nums text-ink-muted",
                      NARROW_HIDDEN,
                    )}
                  >
                    {decimalText(row.volume_ratio)}
                  </td>
                  <td className={cn(CELL_X, "py-1")}>
                    <span
                      data-testid={`limit-badge-${row.stock_id}`}
                      // nowrap:窄欄下「觸及未鎖」會被拆成一字一行的直排
                      className={cn(
                        "rounded whitespace-nowrap px-1.5 text-xs",
                        STATUS_TONE[status],
                      )}
                    >
                      {STATUS_LABEL[status]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 右欄外殼
// ---------------------------------------------------------------------------

/** @param active 使用者是否正看著台股綜合 tab(App 的 `tab === "index"`)。本元件**恆掛**
 *  在右欄,主 tab 切換又不 unmount(App 以 `hidden` 保留 DOM)——「掛著被切走」是常態,
 *  那條路要靠這道 gate 停背景輪詢(review FE-2)。未給時預設 true。
 *
 *  `flex min-h-0 flex-1`:高度由右欄框指派,列表自己在框內捲(§4.1)。 */
export function LimitListSection({
  onOpenStock,
  active = true,
}: {
  onOpenStock?: (code: string) => void;
  active?: boolean;
}) {
  return (
    // `@container`:表格降級的 `@max-[41rem]:` 門檻要量的是**右欄自己的寬**。右欄框
    // 刻意不是 container(它的 `@[1050px]` 量的是頁 root,單欄 / 兩欄的語意),所以
    // 不自掛的話這裡量到的是頁 root 寬 → 1536 全螢幕永遠 > 41rem,降級永不發生。
    // 副作用已查(D4):子樹無 absolute / fixed 定位子孫;唯一的 sticky th 其捲動祖先
    // 是 `limit-list-scroll`(在新容器**之內**),不受 containing block 改變影響。
    <div data-testid="limit-list" className="@container flex min-h-0 flex-1 flex-col pt-2">
      <LimitListBody onOpenStock={onOpenStock} active={active} />
    </div>
  );
}

export default LimitListSection;
