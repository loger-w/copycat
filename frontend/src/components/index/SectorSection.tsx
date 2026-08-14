/** 台股綜合頁的類股強弱 subtab panel(market-overview R4 SC-3;design §9.1)。
 *
 *  **非 active subtab = unmount**(`LimitListSection` / `CorrSection` 同款;2026-08-14
 *  subtab 改版前是「收合 = unmount」,掛載閘上移到 `IndexPage` 後語意等價轉移):
 *  輪動快照盤中每 10 秒一份,切走即 unmount → query 連同輪詢一起消失,頻寬跟著消費者走。
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
// 排序凍結(FE-7 拍板 2026-08-12)
// ---------------------------------------------------------------------------
// 清單每 10 秒依後端 avg 重排,展開/鑽取中的列會在游標下位移 —— 誤點成員是
// setStockCode + set_main,代價不只看錯。拍板解:任何展開/鑽取期間凍結**順序**
// (數字照常更新),全收合才恢復即時重排,凍結中顯示「排序已凍結」標籤。

/** 依凍結快照排序;快照裡沒有的新 key 排最後(`Array.sort` 穩定 → 保後端相對順序),
 *  消失的 key 自然不渲染。 */
function frozenSort<T>(
  items: readonly T[],
  order: readonly string[],
  keyOf: (item: T) => string,
): T[] {
  const rank = new Map(order.map((k, i) => [k, i] as const));
  return [...items].sort(
    (a, b) => (rank.get(keyOf(a)) ?? order.length) - (rank.get(keyOf(b)) ?? order.length),
  );
}

/** 凍結當下的完整順序快照:產業層 + 每個產業各自的子產業層。 */
interface OrderSnap {
  industries: readonly string[];
  subs: ReadonlyMap<string, readonly string[]>;
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
  active,
  onOpenStock,
}: {
  drill: Drill;
  /** 與產業列同一道 tab gate(見 `SectorBody`)。 */
  active: boolean;
  onOpenStock?: (code: string) => void;
}) {
  // query key 帶完整鑽取目標:同一個產業的不同子產業是不同結果,共用一把 key 會讓
  // 切換子產業時先閃出上一個的成員表。
  const { data, isError } = useQuery({
    queryKey: ["sector-members", drill.industry, drill.sub],
    queryFn: () => fetchSectorMembers(drill.industry, drill.sub),
    retry: 1,
    // **成員表必須跟上面那層同步輪詢**(review round-2 FE-3):原本沒有這行,而且全
    // repo 沒有任何人 invalidate `["sector-members"]` → 鑽開的成員表從打開那一刻起就
    // 凍結,正上方的產業列卻每 10 秒在更新。兩層數字並排、一層即時一層是幾分鐘前的,
    // 畫面上沒有任何東西能區分 —— 使用者只會以為這幾檔今天很穩。
    // 函式形式的理由同下方 state query:TQ 每次 interval 到期才重新求值,開盤 / 收盤
    // 的開關不依賴外部 re-render 才會生效。
    refetchInterval: () => (active && inTradingHours() ? POLL_MS : false),
  });

  // 成員層是誤點代價最高的一層(點下去就換主圖),而它掛著就代表使用者正在鑽取
  // → 順序從首份資料落地起就凍結,輪詢只更新數字。不需要「鑽取目標變了重拍快照」
  // 的防禦:每個鑽取目標的 panel 都掛在各自 keyed 的 `li` 下,切換目標必定
  // remount、state 歸零(review T-5 證實 key 分支不可達,故刪)。
  // (條件式 render-phase setState 是 React 的 adjust-state-during-render 慣例,不走 effect。)
  const [memberOrder, setMemberOrder] = useState<readonly string[] | null>(null);
  if (data !== undefined && memberOrder === null) {
    setMemberOrder(data.members.map((m) => m.stock_id));
  }
  const members =
    data !== undefined && memberOrder !== null
      ? frozenSort(data.members, memberOrder, (m) => m.stock_id)
      : (data?.members ?? []);

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
          {members.map((m) => (
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

  const industries = data?.rotation?.industries;
  // 凍結判定看「畫面上真的有列展開著」而不是裸 state,判式與 render 的 `open` 同構:
  // 展開/鑽取指到的產業從後端清單消失、或父列收合後 drill 懸空(收合只動 expanded
  // 不動 drill,review C-1)時,裸 state 非空但畫面上沒有任何展開列 —— 拿裸 state
  // 判會無限凍結,且使用者沒有可點的出口。
  const engaged =
    industries !== undefined &&
    industries.some((i) => (i.subs.length > 0 ? expanded.has(i.name) : isDrill(i.name, null)));

  // 凍結快照:進入展開/鑽取的那一刻拍下當前順序,期間輪詢只更新數字;全收合清掉,
  // 下一輪 render 直接回到後端順序。(條件式 render-phase setState,同 MembersPanel。)
  const [orderSnap, setOrderSnap] = useState<OrderSnap | null>(null);
  if (engaged && orderSnap === null) {
    setOrderSnap({
      industries: industries.map((i) => i.name),
      subs: new Map(industries.map((i) => [i.name, i.subs.map((s) => s.name)] as const)),
    });
  }
  if (!engaged && orderSnap !== null) setOrderSnap(null);

  const displayIndustries =
    industries === undefined
      ? undefined
      : orderSnap !== null
        ? frozenSort(industries, orderSnap.industries, (i) => i.name)
        : industries;

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
        {orderSnap !== null ? (
          // 少了這行小字,凍結中的順序會跟右側 avg 越走越對不上,看起來像輪動壞了
          <span
            data-testid="sector-frozen"
            className="rounded border border-line px-1.5 text-xs text-ink-dim"
          >
            排序已凍結
          </span>
        ) : null}
      </div>

      {message !== null ? (
        <p data-testid="sector-msg" className="py-6 text-center text-sm text-ink-muted">
          {message}
        </p>
      ) : (
        <ul data-testid="sector-list" className="flex flex-col text-sm">
          {displayIndustries?.map((ind) => {
            const hasSubs = ind.subs.length > 0;
            const open = hasSubs ? expanded.has(ind.name) : isDrill(ind.name, null);
            const subs =
              orderSnap !== null
                ? frozenSort(ind.subs, orderSnap.subs.get(ind.name) ?? [], (s) => s.name)
                : ind.subs;
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
                    active={active}
                    onOpenStock={onOpenStock}
                  />
                ) : null}

                {hasSubs && open ? (
                  <ul className="mt-1 flex flex-col pl-6">
                    {subs.map((sub) => (
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
                            active={active}
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
// subtab panel 殼
// ---------------------------------------------------------------------------

/** @param active 使用者是否正看著台股綜合 tab(App 的 `tab === "index"`)。非 active
 *  subtab 是 unmount、但**主 tab 切換不是**(App 以 `hidden` 保留 DOM)—— 選中的
 *  subtab 又存在 localStorage,所以「掛著被切走」是常態,那條路要靠這道 gate 停背景
 *  輪詢。未給時預設 true。 */
export function SectorSection({
  onOpenStock,
  active = true,
}: {
  onOpenStock?: (code: string) => void;
  active?: boolean;
}) {
  return (
    <div data-testid="sector-section" className="px-4 pb-4">
      <SectorBody active={active} onOpenStock={onOpenStock} />
    </div>
  );
}

export default SectorSection;
