/** 台股綜合頁的漲跌停列表收合區塊(market-overview R3;design §5.2)。
 *
 *  **收合 = unmount,不是 `hidden`**(CorrSection 同款慣例):payload 是全市場約 2800 列
 *  × 15 欄,盤中每 10 秒一份 —— 用專案慣例的 `hidden` 保 DOM 等於所有開站的人都持續吃
 *  這份頻寬,而它只有列表展開時才有人看。收合即 unmount → `useBreadthRows` 連同 query
 *  一起消失。與 CorrSection 不同的是**這裡不需要 `React.lazy`**:本元件無 WS、無圖表、
 *  無重依賴,lazy 只會多一個 Suspense 空窗與一條測不到的非同步路徑。
 *
 *  **前端零日期推理**(design R1):`streak` / `streak_capped` 都由後端算完,這裡只負責
 *  把 null / capped 翻成文案。任何「今天是不是還要 +1」的算術一旦在前端重做一份,
 *  盤前、假日、rows 為上一交易日快照這三條路就會各錯一種。 */
import { useMemo, useState } from "react";

import { useBreadthRows } from "@/hooks/useBreadthRows";
import { LIMIT_LIST_FILTER_KEY, LIMIT_LIST_OPEN_KEY } from "@/lib/constants";
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
 *  非數字(輸入法中途 / 貼上文字)一律視同不限,不讓 NaN 進比較式。 */
function threshold(raw: string): number | null {
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
    return { ...DEFAULT_FILTER, ...(parsed as Partial<LimitListFilter>) };
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

function LimitListBody({ onOpenStock }: { onOpenStock?: (code: string) => void }) {
  const { data, isError } = useBreadthRows();
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

  // 空狀態判別子是 `as_of` 不是 `stale`(design R18):`stale` 在冷啟動 degraded 下恆為
  // true,拿它分流會讓「載入中」與「有資料但延遲」兩態顛倒。
  // `enabled=false` 要排在最前面 —— 那是「去設 .env」不是「等一下就好」。
  // 端點恆 200,能走到 isError 的只有網路 / proxy 斷 —— 但那條路必須說出來:
  // 少了它,`data` 恆 undefined 會讓畫面永遠停在「載入中…」(把已放棄說成還在等)。
  let message: string | null = null;
  if (isError) message = "載入失敗";
  else if (data === undefined) message = "載入中…";
  else if (!data.enabled) message = "FinMind 未設定";
  else if (data.as_of === null) message = "載入中…";
  else if (data.rows.length === 0) message = "暫無資料(延遲)";
  else if (entries.length === 0) message = "無符合條件";

  const stamp = [data?.trade_date, data?.as_of].filter(Boolean).join(" · ");

  return (
    <div data-testid="limit-list-body" className="flex flex-col gap-2 px-4 pb-4">
      <div className="flex flex-wrap items-center gap-2">
        {stamp ? (
          <span data-testid="limit-list-stamp" className="font-mono text-xs text-ink-dim">
            {stamp}
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
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
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

      {message !== null ? (
        <p data-testid="limit-list-msg" className="py-6 text-center text-sm text-ink-muted">
          {message}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table data-testid="limit-list-table" className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-ink-dim">
                <th className="px-2 py-1 text-left font-normal">代號</th>
                <th className="px-2 py-1 text-left font-normal">名稱</th>
                <th className="px-2 py-1 text-left font-normal">市場</th>
                <th className="px-2 py-1 text-right font-normal">現價</th>
                <th className="px-2 py-1 text-right font-normal">漲跌幅</th>
                <th className="px-2 py-1 text-right font-normal">連板</th>
                <th className="px-2 py-1 text-right font-normal">金額(億)</th>
                <th className="px-2 py-1 text-right font-normal">量比</th>
                <th className="px-2 py-1 text-left font-normal">狀態</th>
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
                  <td className="px-2 py-1 font-mono text-ink">{row.stock_id}</td>
                  <td className="px-2 py-1 text-ink">{row.name}</td>
                  <td
                    data-testid={`limit-market-${row.stock_id}`}
                    className="px-2 py-1 text-ink-muted"
                  >
                    {MARKET_LABEL[row.market]}
                  </td>
                  <td
                    data-testid={`limit-close-${row.stock_id}`}
                    className="px-2 py-1 text-right font-mono tabular-nums text-ink"
                  >
                    {decimalText(row.close)}
                  </td>
                  <td
                    data-testid={`limit-change-${row.stock_id}`}
                    className={cn(
                      "px-2 py-1 text-right font-mono tabular-nums",
                      changeTone(row.change_rate),
                    )}
                  >
                    {changeText(row.change_rate)}
                  </td>
                  <td
                    data-testid={`limit-streak-${row.stock_id}`}
                    className="px-2 py-1 text-right text-ink"
                  >
                    {streakText(row)}
                  </td>
                  <td
                    data-testid={`limit-amount-${row.stock_id}`}
                    className="px-2 py-1 text-right font-mono tabular-nums text-ink"
                  >
                    {amountText(row.total_amount)}
                  </td>
                  <td
                    data-testid={`limit-ratio-${row.stock_id}`}
                    className="px-2 py-1 text-right font-mono tabular-nums text-ink-muted"
                  >
                    {decimalText(row.volume_ratio)}
                  </td>
                  <td className="px-2 py-1">
                    <span
                      data-testid={`limit-badge-${row.stock_id}`}
                      className={cn("rounded px-1.5 text-xs", STATUS_TONE[status])}
                    >
                      {STATUS_LABEL[status]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 收合殼
// ---------------------------------------------------------------------------

export function LimitListSection({ onOpenStock }: { onOpenStock?: (code: string) => void }) {
  // getItem 在 Safari 私密視窗 / storage 被政策鎖時光是存取就會拋,而這裡是 useState 的
  // initializer —— 拋出去就是整頁白屏。降回「收合」遠好過白屏(CorrSection 同慣例)。
  const [open, setOpen] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(LIMIT_LIST_OPEN_KEY) === "1";
    } catch {
      return false;
    }
  });

  function toggle(): void {
    const next = !open;
    setOpen(next);
    try {
      window.localStorage.setItem(LIMIT_LIST_OPEN_KEY, next ? "1" : "0");
    } catch {
      // 存不進去就算了 —— 偏好不落檔遠好於畫面崩掉
    }
  }

  return (
    <section data-testid="limit-list" className="rounded-md border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        className="flex w-full items-center gap-2 px-4 py-2 text-left"
      >
        <span className="text-sm font-bold text-ink">漲跌停</span>
        <span className="text-xs text-ink-dim">{open ? "收合" : "展開"}</span>
      </button>
      {open ? <LimitListBody onOpenStock={onOpenStock} /> : null}
    </section>
  );
}

export default LimitListSection;
