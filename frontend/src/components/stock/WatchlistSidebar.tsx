import { useId, useMemo, useRef, useState } from "react";

import { WatchlistManagerDialog } from "@/components/stock/WatchlistManagerDialog";
import { errText, useSaveWatchlist, useStockWatchlist } from "@/hooks/useStockWatchlist";
import { useStockNames } from "@/hooks/useStockNames";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { WL_COLLAPSED_KEY, WL_UNGROUPED_KEY } from "@/lib/constants";
import { fmt, fmtPct } from "@/lib/format";
import { dropTargetFromPointer, type DropZone } from "@/lib/list-drag";
import { searchStocks, SUGGEST_LIMIT } from "@/lib/stock-search";
import { limitState } from "@/lib/stock-tick";
import { cn, safeIdToken } from "@/lib/utils";
import {
  assignToGroup,
  detachFromGroups,
  isSameWatchlist,
  moveToGroup,
  removeCode,
  removeFromGroup,
  reorderUngrouped,
  ungroupedCodes,
  type Watchlist,
} from "@/lib/watchlist-model";

/** 列高(round4 項 4:44 → 52,兩行式)。
 *
 *  **同時是拖曳落點幾何的分母**(`dropTargetFromPointer`)—— 與畫面上的實際列高一旦
 *  漂移,拖曳愈往下插入位置愈偏,而症狀是「放開後插到別的位置」= 靜默改資料、零錯誤訊號。
 *  所以列高由這個常數用 inline style 指派,不寫 Tailwind class:jsdom 沒有版面引擎,
 *  class 寫的高度沒有任何測試看得到。 */
export const ROW_H = 52;
const EMPTY_WL: Watchlist = { codes: [], groups: [] };

function fmtPrice(milli: number | null): string {
  if (milli === null) return "-";
  return fmt(milli);
}

function loadCollapsed(): Set<string> {
  try {
    const raw = window.localStorage.getItem(WL_COLLAPSED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    return new Set(Array.isArray(parsed) ? parsed.filter((n): n is string => typeof n === "string") : []);
  } catch {
    return new Set();
  }
}

function persistCollapsed(names: Set<string>): void {
  window.localStorage.setItem(WL_COLLAPSED_KEY, JSON.stringify([...names]));
}

function loadUngroupedCollapsed(): boolean {
  try {
    return window.localStorage.getItem(WL_UNGROUPED_KEY) === "1";
  } catch {
    return false;
  }
}

interface Props {
  active: string | null;
  onSelect: (code: string) => void;
  quotes: Record<string, WatchlistQuote>;
}

export function WatchlistSidebar({ active, onSelect, quotes }: Props) {
  const { data, error } = useStockWatchlist();
  const wl = data ?? EMPTY_WL;
  const groups = wl.groups;
  const ungrouped = ungroupedCodes(wl);
  const { data: names = [] } = useStockNames();
  const save = useSaveWatchlist();
  const [input, setInput] = useState("");
  /** 哪一檔未分組股票展開了「加入群組」清單 */
  const [assigning, setAssigning] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(loadCollapsed);
  /** `collapsed` 的 imperative 影子(先例:`useStockStream` 的 accumRef)。
   *
   *  三個折疊寫入點一律「讀 ref 算 next → 同步 ref → persist → setState」,持久化因此
   *  移出 updater —— updater 契約是純函式,StrictMode 下 double-invoke 會寫兩次
   *  localStorage,遇到 React 重播(rebase / 中止的 render)持久化值還可能與最終 state 分歧。
   *
   *  為什麼是 ref 而不是直接讀 render 閉包的 `collapsed`:`dropCollapsed` 的唯一呼叫者是
   *  PUT mutation 的 `onSuccess`(WatchlistManagerDialog 的刪組回呼),**不是事件路徑**。
   *  連刪兩組、兩發 PUT 同批 resolve 時,兩個回呼在同一個 tick 連續執行,render 閉包還是
   *  舊的 —— 第二次會把第一次已清掉的組名原樣寫回 localStorage。ref 是同步更新的,守得住
   *  (useLayoutEffect 同步版守不住:同一 tick 內 layout effect 還沒跑)。 */
  const collapsedRef = useRef(collapsed);
  const [ungroupedCollapsed, setUngroupedCollapsed] = useState<boolean>(loadUngroupedCollapsed);
  const [dialogOpen, setDialogOpen] = useState(false);
  // 落點 index 不入 state:插入位置在 pointerup 當下由 `dropTargetFromPointer` 現算,
  // 存一份在這裡只會多一個「拖曳過程中的 index」而沒有任何讀者(DC-20)。
  const [drag, setDrag] = useState<{ code: string; from: string | null; to: string | null } | null>(
    null,
  );
  // aria-controls 的 id 前綴(React 19 的 useId 產出 «r0» 形態 → 過濾成合法 id token)
  const uid = safeIdToken(useId());
  const asideRef = useRef<HTMLElement | null>(null);
  // key = 群組名;`null` = 未分組區塊
  const sectionRefs = useRef<Map<string | null, HTMLElement>>(new Map());
  const listRefs = useRef<Map<string | null, HTMLElement>>(new Map());

  const suggestions = searchStocks(input, names, SUGGEST_LIMIT);
  // 名冊 2,401 筆;每列 `names.find(...)` 是 O(列數 × 2401),而側欄每則 quote 都會 re-render
  const nameOf = useMemo(() => new Map(names.map((n) => [n.code, n.name])), [names]);

  /** 純函數算出的 next 與現況相同 → **零 PUT**。內容相同的 PUT 會讓後端重設整個訂閱池
   *  (TC4 全量 UNSUB/SUB),而且無錯誤訊號、畫面也看不出來(W-22)。 */
  function commit(next: Watchlist): void {
    if (isSameWatchlist(next, wl)) return;
    save.mutate(next);
  }

  function toggleCollapsed(name: string): void {
    const next = new Set(collapsedRef.current);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    collapsedRef.current = next;
    persistCollapsed(next);
    setCollapsed(next);
  }

  /** 未分組折疊是 boolean 且只走純點擊路徑(沒有 mutation 回呼那種同批連發),
   *  直接用 render 閉包的值算 next 就夠,不需要影子 ref。 */
  function toggleUngroupedCollapsed(): void {
    const next = !ungroupedCollapsed;
    window.localStorage.setItem(WL_UNGROUPED_KEY, next ? "1" : "0");
    setUngroupedCollapsed(next);
  }

  /** 刪組成功後由 Dialog 回呼:折疊清單不留該組名,否則日後建同名群組會意外呈折疊(W-20)。
   *  呼叫路徑是 mutation 的 `onSuccess`(非事件),故必須讀 `collapsedRef`(見其宣告處)。 */
  function dropCollapsed(name: string): void {
    if (!collapsedRef.current.has(name)) return; // 本來就不在 → 零寫入
    const next = new Set(collapsedRef.current);
    next.delete(name);
    collapsedRef.current = next;
    persistCollapsed(next);
    setCollapsed(next);
  }

  /** 搜尋命中 → **預覽**該檔(round4 項 4)。
   *
   *  舊行為是直接寫進自選(落未分組)。使用者的抱怨是「還沒看過就被塞進清單」——
   *  現在改成只換主圖;要不要收藏、收藏到哪一組,由分時圖上方的「加入自選」按鈕決定。
   *  非自選股照樣能訂閱看盤(`/api/stock/state/{code}` 內含 `set_main`),
   *  所以「預覽」不需要任何新狀態,直接複用主檔選取。 */
  function preview(rawCode: string): void {
    const code = rawCode.trim().toUpperCase();
    setInput("");
    if (code === "") return;
    onSelect(code);
  }

  /** Enter / 點「查看」:提示列有命中取第一筆,無命中則原樣當股號(W-4 的兩條路徑)。 */
  function submitAdd(): void {
    preview(suggestions[0]?.code ?? input);
  }

  /** 落點幾何。**每次 pointermove 重算** —— 只在 pointerdown 算一次的話,側欄捲動或
   *  錯誤文案出現消失都會讓 rect 失效,而失效樣態是「拖到別組結果落錯組」= 靜默改資料。 */
  function zonesNow(): { zones: DropZone[]; bounds: { left: number; right: number } } {
    const zones: DropZone[] = [];
    const push = (key: string | null, count: number): void => {
      const section = sectionRefs.current.get(key);
      if (section === undefined) return;
      const box = section.getBoundingClientRect();
      const list = listRefs.current.get(key);
      const isCollapsed =
        (key === null ? ungroupedCollapsed : collapsed.has(key)) || list === undefined;
      zones.push({
        group: key,
        top: box.top,
        bottom: box.bottom,
        listTop: isCollapsed ? box.bottom : list.getBoundingClientRect().top,
        count,
        collapsed: isCollapsed,
      });
    };
    push(null, ungrouped.length);
    for (const g of groups) push(g.name, g.codes.length);
    const aside = asideRef.current?.getBoundingClientRect();
    return { zones, bounds: { left: aside?.left ?? 0, right: aside?.right ?? 0 } };
  }

  /** 四條落點路徑(SC-12)。拖進未分組 = 從**所有**群組移除:只移除來源組的話,
   *  一檔多組的股票會從來源組消失卻不出現在未分組(它仍屬別組)= 畫面上像資料被吃掉。 */
  function applyDrop(code: string, from: string | null, to: string | null, slot: number): Watchlist {
    if (to === null) {
      return from === null
        ? reorderUngrouped(wl, code, slot)
        : detachFromGroups(wl, code, slot);
    }
    return from === null
      ? assignToGroup(wl, code, to, slot)
      : moveToGroup(wl, code, from, to, slot);
  }

  function onHandleDown(from: string | null, code: string, e: React.PointerEvent): void {
    e.preventDefault();
    setDrag({ code, from, to: from });
    // 取消(Esc)與完成(pointerup)走**同一個** teardown。取消之所以有效是因為這裡把
    // `pointerup` listener 移掉了 —— 之後放開手指根本進不到 `up`。
    // ⚠ 曾另外加過一個 `cancelled` 旗標在 `up` 開頭早退,mutation test 證明它不可達
    // (把它停用後全部測試照樣綠),所以移除:不可達的防禦等於沒有測試覆蓋的死碼。
    const teardown = (): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("keydown", onKey);
      setDrag(null);
    };
    const move = (ev: PointerEvent): void => {
      const { zones, bounds } = zonesNow();
      const target = dropTargetFromPointer({ x: ev.clientX, y: ev.clientY }, zones, ROW_H, bounds);
      setDrag((p) => (p === null || target === null ? p : { ...p, to: target.group }));
    };
    const up = (ev: PointerEvent): void => {
      const { zones, bounds } = zonesNow();
      const target = dropTargetFromPointer({ x: ev.clientX, y: ev.clientY }, zones, ROW_H, bounds);
      teardown();
      if (target === null) return; // 側欄外放開 → 整個作廢(移動語意不可逆)
      commit(applyDrop(code, from, target.group, target.index));
    };
    const onKey = (ev: KeyboardEvent): void => {
      if (ev.key !== "Escape") return;
      teardown();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("keydown", onKey);
  }

  /** 群組 / 未分組的標題列(round4 項 4)。**整條是一顆 `<button>`** ——
   *  原本只有 3px 寬的 `▸/▾` 可點,而折疊是高頻操作。
   *
   *  用原生 button 不用 `role="button"` + tabIndex:免費得到鍵盤 Enter/Space、
   *  focus ring 與正確的 SR 角色;`role` 版要自己補 `onKeyDown` 處理 Space(且預設會捲頁)。
   *  `▸/▾` 降級成 `aria-hidden` 的狀態指示,狀態改由 `aria-expanded` 播報 ——
   *  兩邊都講會重複播報,而且可能不同步。舊的 `aria-label="折疊 X"` 隨之移除,
   *  可及名稱改由可見文字(組名 + 計數)提供。
   *
   *  `aria-controls` 的 id **不可拿組名拼**:組名是使用者自由輸入(`addGroup` 只 trim),
   *  含空白的名字會產生含空白的 id,而 ID token list 會把它拆成兩個不存在的 token →
   *  a11y 關聯靜默失效;叫 `ungrouped` 的群組還會撞未分組區塊的 id。 */
  function sectionHeader(o: {
    label: string;
    count: number;
    collapsed: boolean;
    listId: string;
    onToggle: () => void;
  }): React.ReactElement {
    return (
      <button
        type="button"
        aria-expanded={!o.collapsed}
        aria-controls={o.listId}
        // 拖曳放開的瞬間 React 可能剛重繪、游標恰落在新的 header 上。天然防線是
        // click 只在 pointerdown/up 的最近共同祖先派發(握把在列內,祖先是 section),
        // 這行是針對時序邊角的顯式守衛。
        onClick={() => {
          if (drag !== null) return;
          o.onToggle();
        }}
        className={cn(
          "flex w-full items-center gap-1 border-b border-line px-1 py-1 text-left",
          "focus-visible:border-b-accent focus-visible:outline-none",
          // 拖曳中關掉 hover 亮色:否則會與落點高亮(border-accent)搶語意 ——
          // 使用者分不清「這是可放的組」還是「這是可點的鈕」
          drag === null && "hover:bg-surface",
        )}
      >
        <span aria-hidden="true" className="w-3 shrink-0 text-xs text-ink-dim">
          {o.collapsed ? "▸" : "▾"}
        </span>
        <span className="min-w-0 flex-1 truncate text-xs text-ink">{o.label}</span>
        <span className="shrink-0 font-mono text-[0.625rem] text-ink-dim">{o.count}</span>
      </button>
    );
  }

  function stockRow(code: string, group: string | null): React.ReactElement {
    const q = quotes[code];
    const name = nameOf.get(code);
    // 側欄亮燈 = **觸停**(現價踩到漲跌停),與主區五檔的**鎖停** badge 語意不同 ——
    // 後者是 `bids[0] === upper`(委買掛在漲停排隊),需要五檔,側欄沒有。
    // 兩者刻意不共用,共用會逼側欄拿不存在的資料或稀釋 badge 語意。
    const limit = limitState(q?.p ?? null, q?.upper ?? null, q?.lower ?? null);
    return (
      <li key={code}>
        <div
          data-testid={`wl-row-${code}`}
          style={{ height: ROW_H }}
          className={cn(
            "group flex cursor-pointer items-center gap-1.5 border-b border-line px-1",
            active === code && "bg-bg-deep",
            drag?.code === code && "opacity-50",
          )}
          onClick={() => onSelect(code)}
        >
          <span
            role="button"
            aria-label={`拖拉 ${code}`}
            className="shrink-0 cursor-grab select-none text-ink-dim"
            onPointerDown={(e) => onHandleDown(group, code, e)}
            onClick={(e) => e.stopPropagation()}
          >
            ⋮⋮
          </span>
          {/* 兩行式(round4 項 4 / 項 5):240px 側欄同一行塞不下「名稱 + 放大代號 +
              放大價位 + 漲幅」(約需 250px)。左上代號 ↔ 右上價位同一條 baseline 都是
              主資訊,左下名稱 ↔ 右下漲幅是輔助 —— 掃第一行找標的與價位,要細節才看第二行。
              漲幅刻意不跟著放大:四個元素同權重反而更難掃。
              `min-w-0` 不可省,少了它 flex 子項不會縮、`truncate` 失效。 */}
          <div className="flex min-w-0 flex-1 flex-col justify-center leading-tight">
            <span className="font-mono text-base text-ink">{code}</span>
            {name !== undefined ? (
              <span className="truncate text-xs text-ink-muted">{name}</span>
            ) : null}
          </div>
          {q?.no_data ? (
            <span className="shrink-0 text-xs text-ink-dim">無資料</span>
          ) : (
            <span
              data-testid={`wl-quote-${code}`}
              className={cn(
                "flex shrink-0 flex-col items-end justify-center font-mono leading-tight",
                // 亮燈時**整塊**吃底色(同主區慣例):盤中要用餘光捕捉,換文字色不夠。
                limit === "upper" && "rounded bg-bull px-1.5 text-white",
                limit === "lower" && "rounded bg-bear px-1.5 text-white",
              )}
            >
              {/* 三態:今日成交價 → 尚無成交但有參考價(灰,標「參考」)→ `-`。
                  參考價**不套漲跌色也不印 0.00%** —— 那會讓昨收看起來像今天的走勢。 */}
              {q?.p != null ? (
                <>
                  <span className={cn("text-base", limit === null ? "text-ink" : "text-white")}>
                    {fmtPrice(q.p)}
                  </span>
                  <span
                    className={cn(
                      "text-xs",
                      // 亮燈時一律白字,不再走漲跌色 —— 紅底紅字看不見(同 OrderBook)
                      limit !== null
                        ? "text-white"
                        : (q.chg_pct ?? 0) > 0
                          ? "text-bull"
                          : (q.chg_pct ?? 0) < 0
                            ? "text-bear"
                            : "text-ink-dim",
                    )}
                  >
                    {q.chg_pct != null ? fmtPct(q.chg_pct) : "-"}
                  </span>
                </>
              ) : q?.ref != null ? (
                <>
                  <span className="text-base text-ink-dim">{fmtPrice(q.ref)}</span>
                  <span className="text-xs text-ink-dim">參考</span>
                </>
              ) : (
                <>
                  <span className="text-base text-ink-dim">-</span>
                  <span className="text-xs text-ink-dim">-</span>
                </>
              )}
            </span>
          )}
          {group === null ? (
            <button
              type="button"
              aria-label={`加入群組 ${code}`}
              // 零群組時沒有可指派的對象 → 停用(SC-9),不是點了沒反應
              disabled={groups.length === 0}
              className="text-ink-dim hover:text-accent disabled:text-ink-dim/40 disabled:hover:text-ink-dim/40"
              onClick={(e) => {
                e.stopPropagation();
                setAssigning((cur) => (cur === code ? null : code));
              }}
            >
              +
            </button>
          ) : null}
          <button
            type="button"
            aria-label={`移除 ${code}`}
            className="invisible text-ink-dim hover:text-bear group-hover:visible"
            onClick={(e) => {
              e.stopPropagation();
              // 群組列 = 只離開該組(該檔掉回未分組);未分組列 = 從自選整個移除
              commit(group === null ? removeCode(wl, code) : removeFromGroup(wl, code, group));
            }}
          >
            ×
          </button>
        </div>
        {/* 群組清單渲染在**該列正下方**:放在區塊之後會落到側欄底部、常在可視範圍外 */}
        {group === null && assigning === code ? (
          <div className="rounded border border-line bg-bg-deep p-2">
            <p className="mb-1 font-mono text-xs text-ink-dim">{code} 加入群組</p>
            <div className="flex flex-wrap gap-1">
              {groups.map((g) => (
                <button
                  key={g.name}
                  type="button"
                  aria-label={`加入 ${code} 到 ${g.name}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setAssigning(null);
                    commit(assignToGroup(wl, code, g.name, g.codes.length));
                  }}
                  className="rounded border border-line px-1 py-0.5 text-xs text-ink hover:border-accent"
                >
                  {g.name}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </li>
    );
  }

  return (
    // overflow-y-auto 掛在 aside(不是單一 ul):群組全列出後側欄高度不再受單組限制。
    // border-r:與中間主區的視覺分隔(round3 項 5);pr-3 讓內容不貼線
    <aside
      ref={asideRef}
      className="flex w-60 shrink-0 flex-col gap-1 overflow-y-auto border-r border-line pr-3"
      aria-label="自選清單"
    >
      {/* 搜尋框恆存且 sticky:群組多起來捲動後仍要看得到(W-16 的新實體) */}
      <div className="sticky top-0 z-10 bg-bg pb-1">
        <div className="flex gap-1">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitAdd();
              if (e.key === "Escape") setInput("");
            }}
            placeholder="股號或名稱"
            className="w-full rounded border border-line bg-bg px-2 py-1 font-mono text-sm text-ink outline-none focus:border-accent"
          />
          <button
            type="button"
            onClick={submitAdd}
            className="shrink-0 rounded border border-line px-2 py-1 text-sm text-ink hover:border-accent"
          >
            查看
          </button>
        </div>
        {suggestions.length > 0 ? (
          <ul data-testid="stock-suggest" className="mt-1 rounded border border-line bg-bg-deep">
            {suggestions.map((s) => (
              <li key={s.code}>
                <button
                  type="button"
                  aria-label={`查看 ${s.code} ${s.name}`}
                  onClick={() => preview(s.code)}
                  className="flex w-full items-baseline gap-2 px-2 py-1 text-left text-xs hover:bg-surface"
                >
                  <span className="w-14 font-mono text-ink">{s.code}</span>
                  <span className="truncate text-ink-muted">{s.name}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {save.error ? <p className="text-xs text-bear">{errText(save.error.message)}</p> : null}
      {error ? <p className="text-xs text-bear">自選清單載入失敗</p> : null}

      <section
        data-testid="wl-ungrouped"
        ref={(el) => {
          if (el) sectionRefs.current.set(null, el);
          else sectionRefs.current.delete(null);
        }}
        className={cn(
          "rounded border border-transparent",
          drag !== null && drag.to === null && "border-accent",
        )}
      >
        {sectionHeader({
          label: "未分組",
          count: ungrouped.length,
          collapsed: ungroupedCollapsed,
          listId: `${uid}-wl-list-ung`,
          onToggle: toggleUngroupedCollapsed,
        })}
        {ungroupedCollapsed ? null : (
          <ul
            id={`${uid}-wl-list-ung`}
            data-testid="wl-list-ungrouped"
            ref={(el) => {
              if (el) listRefs.current.set(null, el);
              else listRefs.current.delete(null);
            }}
            className="flex flex-col"
          >
            {ungrouped.map((code) => stockRow(code, null))}
            {ungrouped.length === 0 ? (
              <li style={{ minHeight: ROW_H }} className="flex items-center px-1 text-xs text-ink-dim">
                拖曳到此移出群組
              </li>
            ) : null}
          </ul>
        )}
      </section>

      {groups.map((g, i) => {
        const isCollapsed = collapsed.has(g.name);
        const listId = `${uid}-wl-list-${i}`;
        return (
          <section
            key={g.name}
            data-testid={`wl-group-${g.name}`}
            ref={(el) => {
              if (el) sectionRefs.current.set(g.name, el);
              else sectionRefs.current.delete(g.name);
            }}
            className={cn(
              "rounded border border-transparent",
              drag !== null && drag.to === g.name && "border-accent",
            )}
          >
            {sectionHeader({
              label: g.name,
              count: g.codes.length,
              collapsed: isCollapsed,
              listId,
              onToggle: () => toggleCollapsed(g.name),
            })}

            {isCollapsed ? null : (
              <ul
                id={listId}
                data-testid={`wl-list-${g.name}`}
                ref={(el) => {
                  if (el) listRefs.current.set(g.name, el);
                  else listRefs.current.delete(g.name);
                }}
                className="flex flex-col"
              >
                {g.codes.map((code) => stockRow(code, g.name))}
                {g.codes.length === 0 ? (
                  <li style={{ minHeight: ROW_H }} className="flex items-center px-1 text-xs text-ink-dim">
                    拖曳股票到此
                  </li>
                ) : null}
              </ul>
            )}
          </section>
        );
      })}

      {/* 自選還沒成功載入過(pending / 失敗)時 `wl` 是 EMPTY_WL —— Dialog 的新增群組 /
          加入股票不依賴既有列,會以空自選為基底整份 PUT(後端無樂觀鎖)把真實自選清空,
          且 commit 守衛比的就是 EMPTY_WL 自身,沒有保護力 → 入口就擋掉。
          Dialog 併進**同一個** gate(而非只擋按鈕):危險窗內連掛載都不給,
          「拿得到 EMPTY_WL 的 Dialog 不存在」就成了本地可讀的不變式,不必追它內部
          有沒有其他開啟路徑。data 一旦成功載入就不會退回 undefined,所以對 Dialog 自己的
          open/close 循環而言它仍是常駐掛載 —— 不影響其 prevOpen 重置設計。 */}
      {data === undefined ? null : (
        <>
          <button
            type="button"
            aria-label="管理群組與股票"
            onClick={() => setDialogOpen(true)}
            className="mx-1 rounded border border-line px-1 py-0.5 text-xs text-ink-dim hover:text-ink"
          >
            管理
          </button>
          <WatchlistManagerDialog
            open={dialogOpen}
            wl={wl}
            onClose={() => setDialogOpen(false)}
            onGroupDeleted={dropCollapsed}
          />
        </>
      )}
    </aside>
  );
}
