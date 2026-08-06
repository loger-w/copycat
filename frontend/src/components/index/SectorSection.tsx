/** 台股綜合頁的類股強弱收合區塊(market-overview R4 SC-3;design §9.1)。
 *
 *  **收合 = unmount**(`LimitListSection` / `CorrSection` 同款):輪動快照盤中每 10 秒
 *  一份,收合即 unmount → query 連同輪詢一起消失,頻寬跟著消費者走。
 *
 *  **三層而不是三個面板**:產業 → 子產業 → 成員股全部內嵌在同一棵清單裡,而且
 *  **同時只有一個成員表**。成員層各自獨立展開的話,展開 N 個群組就是 N 個並發鑽取
 *  請求(每個都是一次後端全 universe 掃描),而畫面上完全看不出打了幾發。
 *
 *  **前端零統計**:`avg_change_rate` / `vol_ratio` / `members` 全部由後端算完(產業層
 *  是子產業 stock_id 聯集去重後才平均),這裡只負責把數字與缺值翻成文案。在前端補一份
 *  「把 subs 的平均再平均」會得到看起來很像、但權重錯掉的數字。 */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { SECTOR_OPEN_KEY } from "@/lib/constants";
import { fmtPct } from "@/lib/format";
import {
  fetchSectorMembers,
  fetchSectorState,
  type SectorRotationGroup,
  type SectorRotationIndustry,
} from "@/lib/sector-model";
import { inTradingHours } from "@/lib/trading-hours";
import { cn } from "@/lib/utils";

const POLL_MS = 10_000;

/** 同時只有一個鑽取目標;`sub` null = 該產業所有子產業聯集(單層產業也走這條)。 */
interface Drill {
  industry: string;
  sub: string | null;
}

// ---------------------------------------------------------------------------
// 文案(缺值一律破折號,不得退成 0 —— 那是「量比 0」/「平盤」的意思)
// ---------------------------------------------------------------------------

function ratioText(v: number | null): string {
  return v === null ? "—" : v.toFixed(2);
}

function amountText(v: number | null): string {
  return v === null ? "—" : (v / 1e8).toFixed(1);
}

function changeText(v: number | null): string {
  return v === null ? "—" : fmtPct(v);
}

/** 台股慣例:漲紅(bull)/ 跌綠(bear)。 */
function changeTone(v: number | null): string {
  if (v === null) return "text-ink-muted";
  if (v > 0) return "text-bull";
  if (v < 0) return "text-bear";
  return "text-ink-muted";
}

/** 產業列與子產業列共用的右側統計(欄位相同,只有縮排與 testid 前綴不同)。 */
function GroupStats({ id, group }: { id: string; group: SectorRotationGroup }) {
  return (
    <span className="flex shrink-0 items-center gap-3">
      <span
        data-testid={`sector-change-${id}`}
        className={cn("font-mono tabular-nums", changeTone(group.avg_change_rate))}
      >
        {changeText(group.avg_change_rate)}
      </span>
      <span
        data-testid={`sector-ratio-${id}`}
        className="w-10 text-right font-mono tabular-nums text-ink-dim"
      >
        {ratioText(group.vol_ratio)}
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// 成員層(lazy;掛在被鑽取的那一列底下)
// ---------------------------------------------------------------------------

function MembersPanel({
  drill,
  onOpenStock,
}: {
  drill: Drill;
  onOpenStock?: (code: string) => void;
}) {
  // query key 帶完整鑽取目標:同一個產業的不同子產業是不同結果,共用一把 key 會讓
  // 切換子產業時先閃出上一個的成員表。
  const { data, isError } = useQuery({
    queryKey: ["sector-members", drill.industry, drill.sub],
    queryFn: () => fetchSectorMembers(drill.industry, drill.sub),
    retry: 1,
  });

  let message: string | null = null;
  if (isError && data === undefined) message = "成員載入失敗";
  else if (data === undefined) message = "載入中…";
  else if (data.members.length === 0) message = "無成員資料";

  if (message !== null) {
    return (
      <p data-testid="sector-members-msg" className="py-2 pl-6 text-xs text-ink-muted">
        {message}
      </p>
    );
  }

  return (
    <div className="mt-1 border-l border-line pl-2">
      <table data-testid="sector-members-table" className="w-full border-collapse text-xs">
        <thead>
          <tr className="text-ink-dim">
            <th className="px-2 py-0.5 text-left font-normal">名稱</th>
            <th className="px-2 py-0.5 text-right font-normal">漲跌</th>
            <th className="px-2 py-0.5 text-right font-normal">量比</th>
            <th className="px-2 py-0.5 text-right font-normal">成交額</th>
          </tr>
        </thead>
        <tbody>
          {data?.members.map((m) => (
            <tr
              key={m.stock_id}
              data-testid={`sector-member-${m.stock_id}`}
              onClick={() => onOpenStock?.(m.stock_id)}
              className="cursor-pointer hover:bg-bg-deep"
            >
              <td className="px-2 py-0.5 text-ink">{m.name}</td>
              <td
                data-testid={`sector-member-change-${m.stock_id}`}
                className={cn(
                  "px-2 py-0.5 text-right font-mono tabular-nums",
                  changeTone(m.change_rate),
                )}
              >
                {changeText(m.change_rate)}
              </td>
              <td
                data-testid={`sector-member-ratio-${m.stock_id}`}
                className="px-2 py-0.5 text-right font-mono tabular-nums text-ink-muted"
              >
                {ratioText(m.vol_ratio)}
              </td>
              <td
                data-testid={`sector-member-amount-${m.stock_id}`}
                className="px-2 py-0.5 text-right font-mono tabular-nums text-ink"
              >
                {amountText(m.total_amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 展開後的本體
// ---------------------------------------------------------------------------

function SectorBody({
  active,
  onOpenStock,
}: {
  active: boolean;
  onOpenStock?: (code: string) => void;
}) {
  const { data, isError } = useQuery({
    queryKey: ["sector-state"],
    queryFn: fetchSectorState,
    retry: 1,
    // 函式形式(`useBreadthRows` 同慣例):TQ 每次 interval 到期都重新求值,開盤 / 收盤
    // 的開關不依賴外部 re-render 才會生效。`active` 是 tab gate —— 本頁的 DOM 由 App 以
    // `hidden` 保留,展開狀態又存在 localStorage,「展開著被切走」是常態。
    refetchInterval: () => (active && inTradingHours() ? POLL_MS : false),
  });

  // 展開態刻意不持久化(design §9.1):產業排序每天都不一樣,昨天展開的那一格今天
  // 通常已經不是同一個位置,還原它只會讓畫面開場就長歪。
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set<string>());
  const [drill, setDrill] = useState<Drill | null>(null);

  function toggleExpand(name: string): void {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  /** 有子產業 → 展開下一層;沒有 → 直接鑽成員(否則單層產業會是點了沒反應的死列)。 */
  function clickIndustry(ind: SectorRotationIndustry): void {
    if (ind.subs.length > 0) {
      toggleExpand(ind.name);
      return;
    }
    setDrill((cur) =>
      cur !== null && cur.industry === ind.name && cur.sub === null
        ? null
        : { industry: ind.name, sub: null },
    );
  }

  function clickSub(industry: string, sub: string): void {
    setDrill((cur) =>
      cur !== null && cur.industry === industry && cur.sub === sub ? null : { industry, sub },
    );
  }

  function isDrill(industry: string, sub: string | null): boolean {
    return drill !== null && drill.industry === industry && drill.sub === sub;
  }

  // `isError` 必須與 `data === undefined` 綁在一起(`LimitListSection` 同慣例):TQ v5 的
  // `isError` 對 refetch 失敗同樣為 true,單看它會讓「已有整份輪動、只是這一輪 10 秒
  // 輪詢沒抓到」整塊消失。有 data 就保清單,失敗改由膠囊說。
  const loadFailed = isError && data === undefined;
  const refetchFailed = isError && data !== undefined;
  let message: string | null = null;
  if (loadFailed) message = "載入失敗";
  else if (data === undefined) message = "載入中…";
  else if (!data.enabled) message = "FinMind 未設定";
  // `rotation` null 與空 `industries` 不同義:前者是產業鏈快取還沒好(或類股停用),
  // 後者是今天所有產業都沒成員。共用一句文案會把「等一下就有」說成「今天就是沒有」。
  else if (data.rotation === null) message = "類股資料未就緒";
  else if (data.rotation.industries.length === 0) message = "暫無類股資料";

  return (
    <div data-testid="sector-body" className="flex flex-col gap-2 px-4 pb-4">
      <div className="flex flex-wrap items-center gap-2">
        {data?.stale ? (
          <span
            data-testid="sector-stale"
            className="rounded border border-bull/40 bg-bull/15 px-1.5 text-xs text-bull"
          >
            資料延遲
          </span>
        ) : null}
        {refetchFailed ? (
          <span
            data-testid="sector-refetch-error"
            className="rounded border border-amber-500/40 px-1.5 text-xs text-amber-400"
          >
            更新失敗
          </span>
        ) : null}
      </div>

      {message !== null ? (
        <p data-testid="sector-msg" className="py-6 text-center text-sm text-ink-muted">
          {message}
        </p>
      ) : (
        <ul data-testid="sector-list" className="flex flex-col text-sm">
          {data?.rotation?.industries.map((ind) => {
            const hasSubs = ind.subs.length > 0;
            const open = hasSubs ? expanded.has(ind.name) : isDrill(ind.name, null);
            return (
              <li key={ind.name} className="border-b border-line/50 py-1">
                <button
                  type="button"
                  data-testid={`sector-row-btn-${ind.name}`}
                  aria-expanded={open}
                  onClick={() => clickIndustry(ind)}
                  className="flex w-full items-center gap-1 text-left pointer-coarse:min-h-11"
                >
                  <span aria-hidden="true" className="w-4 shrink-0 text-ink-dim">
                    {open ? "▾" : "▸"}
                  </span>
                  <span className="flex flex-1 items-center justify-between gap-2">
                    <span className="text-ink">
                      {ind.name}
                      <span className="ml-1 text-xs text-ink-dim">({ind.members})</span>
                    </span>
                    <GroupStats id={ind.name} group={ind} />
                  </span>
                </button>

                {!hasSubs && isDrill(ind.name, null) ? (
                  <MembersPanel
                    drill={{ industry: ind.name, sub: null }}
                    onOpenStock={onOpenStock}
                  />
                ) : null}

                {hasSubs && open ? (
                  <ul className="mt-1 flex flex-col pl-6">
                    {ind.subs.map((sub) => (
                      <li key={sub.name}>
                        <button
                          type="button"
                          data-testid={`sector-sub-btn-${ind.name}-${sub.name}`}
                          aria-expanded={isDrill(ind.name, sub.name)}
                          onClick={() => clickSub(ind.name, sub.name)}
                          className="flex w-full items-center justify-between gap-2 text-left text-xs pointer-coarse:min-h-11"
                        >
                          <span className="text-ink-muted">
                            {sub.name}
                            <span className="ml-1 text-ink-dim">({sub.members})</span>
                          </span>
                          <GroupStats id={`${ind.name}-${sub.name}`} group={sub} />
                        </button>
                        {isDrill(ind.name, sub.name) ? (
                          <MembersPanel
                            drill={{ industry: ind.name, sub: sub.name }}
                            onOpenStock={onOpenStock}
                          />
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 收合殼
// ---------------------------------------------------------------------------

/** @param active 使用者是否正看著台股綜合 tab(App 的 `tab === "index"`)。收合是
 *  unmount、但 tab 切換不是 —— 展開狀態又存在 localStorage,所以「展開著被切走」
 *  是常態,那條路要靠這道 gate 停背景輪詢。未給時預設 true。 */
export function SectorSection({
  onOpenStock,
  active = true,
}: {
  onOpenStock?: (code: string) => void;
  active?: boolean;
}) {
  // getItem 在 Safari 私密視窗 / storage 被政策鎖時光是存取就會拋,而這裡是 useState 的
  // initializer —— 拋出去就是整頁白屏。降回「收合」遠好過白屏(LimitListSection 同慣例)。
  const [open, setOpen] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(SECTOR_OPEN_KEY) === "1";
    } catch {
      return false;
    }
  });

  function toggle(): void {
    const next = !open;
    setOpen(next);
    try {
      window.localStorage.setItem(SECTOR_OPEN_KEY, next ? "1" : "0");
    } catch {
      // 存不進去就算了 —— 偏好不落檔遠好於畫面崩掉
    }
  }

  return (
    <section data-testid="sector-section" className="rounded-md border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        className="flex w-full items-center gap-2 px-4 py-2 text-left"
      >
        <span className="text-sm font-bold text-ink">類股強弱</span>
        <span className="text-xs text-ink-dim">{open ? "收合" : "展開"}</span>
      </button>
      {open ? <SectorBody active={active} onOpenStock={onOpenStock} /> : null}
    </section>
  );
}

export default SectorSection;
