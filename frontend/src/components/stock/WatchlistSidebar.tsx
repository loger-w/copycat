import { useRef, useState } from "react";

import { useSaveWatchlist, useStockWatchlist, type Group } from "@/hooks/useStockWatchlist";
import { useStockNames } from "@/hooks/useStockNames";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { dropTargetFromPointer, moveCode, type DropZone } from "@/lib/list-drag";
import { searchStocks } from "@/lib/stock-search";
import { cn } from "@/lib/utils";

const ROW_H = 44;
/** 折疊中的群組名(round4 項 2)。前綴沿用 `copycat-`(docs/next-time.md 的 key 收斂方向) */
const COLLAPSED_KEY = "copycat-stock-wl-collapsed";
const DEFAULT_GROUP = "自選";
/** 提示列筆數:多過這個高度就開始擠掉股票列 */
const SUGGEST_LIMIT = 8;

function fmtPrice(milli: number | null): string {
  if (milli === null) return "-";
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

function errText(message: string): string {
  if (message === "WATCHLIST_FULL") return "自選已達 30 檔上限";
  if (message === "BAD_CODE") return "股號格式不正確";
  if (message === "BAD_GROUP") return "群組名稱不合法";
  return "儲存失敗";
}

function loadCollapsed(): Set<string> {
  try {
    const raw = window.localStorage.getItem(COLLAPSED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    return new Set(Array.isArray(parsed) ? parsed.filter((n): n is string => typeof n === "string") : []);
  } catch {
    return new Set();
  }
}

function persistCollapsed(names: Set<string>): void {
  window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...names]));
}

interface Props {
  active: string | null;
  onSelect: (code: string) => void;
  quotes: Record<string, WatchlistQuote>;
}

export function WatchlistSidebar({ active, onSelect, quotes }: Props) {
  const { data: groups = [], error } = useStockWatchlist();
  const { data: names = [] } = useStockNames();
  const save = useSaveWatchlist();
  /** 哪一組展開了搜尋框;`""` = 零群組時的 fallback 搜尋框 */
  const [adding, setAdding] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [addingGroup, setAddingGroup] = useState(false);
  const [groupInput, setGroupInput] = useState("");
  const [movingCode, setMovingCode] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(loadCollapsed);
  const [drag, setDrag] = useState<{ code: string; from: string; to: string; index: number } | null>(
    null,
  );
  const asideRef = useRef<HTMLElement | null>(null);
  const sectionRefs = useRef<Map<string, HTMLElement>>(new Map());
  const listRefs = useRef<Map<string, HTMLElement>>(new Map());

  const suggestions = searchStocks(input, names, SUGGEST_LIMIT);

  function mutateGroups(next: Group[]): void {
    save.mutate(next);
  }

  function toggleCollapsed(name: string): void {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      persistCollapsed(next);
      return next;
    });
  }

  /** 加入指定群組;`group` 不在 `groups` 內(零群組 fallback)→ 自動建立該組。 */
  function addTo(group: string, rawCode: string): void {
    const code = rawCode.trim().toUpperCase();
    setAdding(null);
    setInput("");
    if (!code) return;
    const target = groups.find((g) => g.name === group);
    if (target) {
      if (target.codes.includes(code)) return;
      mutateGroups(groups.map((g) => (g.name === group ? { ...g, codes: [...g.codes, code] } : g)));
      return;
    }
    mutateGroups([...groups, { name: group, codes: [code] }]);
  }

  /** Enter / 點「新增」:提示列有命中取第一筆,無命中則原樣當股號(白名單 W-4)。 */
  function submitAdd(group: string): void {
    addTo(group, suggestions[0]?.code ?? input);
  }

  function remove(group: string, code: string): void {
    mutateGroups(
      groups.map((g) => (g.name === group ? { ...g, codes: g.codes.filter((c) => c !== code) } : g)),
    );
  }

  function addGroup(): void {
    const name = groupInput.trim();
    setAddingGroup(false);
    setGroupInput("");
    if (!name || groups.some((g) => g.name === name)) return;
    mutateGroups([...groups, { name, codes: [] }]);
  }

  function removeGroup(name: string): void {
    // mutation 成功才收斂衍生狀態(review A2:失敗時 cache 未動,UI 不該先跳)。
    // 折疊清單必須清掉該組名,否則 localStorage 累積孤兒名,日後建同名群組會意外呈折疊。
    save.mutate(
      groups.filter((g) => g.name !== name),
      {
        onSuccess: () => {
          setCollapsed((prev) => {
            if (!prev.has(name)) return prev;
            const next = new Set(prev);
            next.delete(name);
            persistCollapsed(next);
            return next;
          });
          setAdding((cur) => (cur === name ? null : cur));
        },
      },
    );
  }

  function toggleMembership(code: string, groupName: string): void {
    mutateGroups(
      groups.map((g) => {
        if (g.name !== groupName) return g;
        return g.codes.includes(code)
          ? { ...g, codes: g.codes.filter((c) => c !== code) }
          : { ...g, codes: [...g.codes, code] };
      }),
    );
  }

  /** 落點幾何。**每次 pointermove 重算** —— 只在 pointerdown 算一次的話,側欄捲動或
   *  錯誤文案出現消失都會讓 rect 失效,而失效樣態是「拖到別組結果落錯組」= 靜默改資料。 */
  function zonesNow(): { zones: DropZone[]; bounds: { left: number; right: number } } {
    const zones: DropZone[] = [];
    for (const g of groups) {
      const section = sectionRefs.current.get(g.name);
      if (section === undefined) continue;
      const box = section.getBoundingClientRect();
      const list = listRefs.current.get(g.name);
      const isCollapsed = collapsed.has(g.name) || list === undefined;
      zones.push({
        group: g.name,
        top: box.top,
        bottom: box.bottom,
        listTop: isCollapsed ? box.bottom : list.getBoundingClientRect().top,
        count: g.codes.length,
        collapsed: isCollapsed,
      });
    }
    const aside = asideRef.current?.getBoundingClientRect();
    return { zones, bounds: { left: aside?.left ?? 0, right: aside?.right ?? 0 } };
  }

  function onHandleDown(group: string, code: string, e: React.PointerEvent): void {
    e.preventDefault();
    setDrag({ code, from: group, to: group, index: groups.find((g) => g.name === group)?.codes.indexOf(code) ?? 0 });
    let cancelled = false;
    const teardown = (): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("keydown", onKey);
      setDrag(null);
    };
    const move = (ev: PointerEvent): void => {
      const { zones, bounds } = zonesNow();
      const target = dropTargetFromPointer({ x: ev.clientX, y: ev.clientY }, zones, ROW_H, bounds);
      setDrag((p) => (p === null || target === null ? p : { ...p, to: target.group, index: target.index }));
    };
    const up = (ev: PointerEvent): void => {
      // Esc 取消後放開手指仍會走到這裡 —— 沒有這個早退,取消等於沒取消
      if (cancelled) return;
      const { zones, bounds } = zonesNow();
      const target = dropTargetFromPointer({ x: ev.clientX, y: ev.clientY }, zones, ROW_H, bounds);
      teardown();
      if (target === null) return; // 側欄外放開 → 整個作廢(移動語意不可逆)
      const source = groups.find((g) => g.name === group);
      const at = source?.codes.indexOf(code) ?? -1;
      if (target.group === group && (target.index === at || target.index === at + 1)) return;
      mutateGroups(moveCode(groups, code, group, target.group, target.index));
    };
    const onKey = (ev: KeyboardEvent): void => {
      if (ev.key !== "Escape") return;
      cancelled = true;
      teardown();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("keydown", onKey);
  }

  function searchBox(group: string): React.ReactElement {
    return (
      <div className="px-1 py-1">
        <div className="flex gap-1">
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitAdd(group);
              if (e.key === "Escape") {
                setAdding(null);
                setInput("");
              }
            }}
            placeholder="股號或名稱"
            className="w-full rounded border border-line bg-bg px-2 py-1 font-mono text-sm text-ink outline-none focus:border-accent"
          />
          <button
            type="button"
            onClick={() => submitAdd(group)}
            className="shrink-0 rounded border border-line px-2 py-1 text-sm text-ink hover:border-accent"
          >
            新增
          </button>
        </div>
        {suggestions.length > 0 ? (
          <ul data-testid="stock-suggest" className="mt-1 rounded border border-line bg-bg-deep">
            {suggestions.map((s) => (
              <li key={s.code}>
                <button
                  type="button"
                  aria-label={`加入 ${s.code} ${s.name}`}
                  onClick={() => addTo(group, s.code)}
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
      {save.error ? <p className="text-xs text-bear">{errText(save.error.message)}</p> : null}
      {error ? <p className="text-xs text-bear">自選清單載入失敗</p> : null}

      {groups.map((g) => {
        const isCollapsed = collapsed.has(g.name);
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
            <header className="group/hdr flex items-center gap-1 border-b border-line px-1 py-0.5">
              <button
                type="button"
                aria-label={`${isCollapsed ? "展開" : "折疊"} ${g.name}`}
                onClick={() => toggleCollapsed(g.name)}
                className="w-3 shrink-0 text-xs text-ink-dim hover:text-ink"
              >
                {isCollapsed ? "▸" : "▾"}
              </button>
              <span className="min-w-0 flex-1 truncate text-xs text-ink">{g.name}</span>
              <span className="shrink-0 font-mono text-[0.625rem] text-ink-dim">{g.codes.length}</span>
              <button
                type="button"
                aria-label={`新增到 ${g.name}`}
                onClick={() => {
                  setAdding((cur) => (cur === g.name ? null : g.name));
                  setInput("");
                }}
                className="shrink-0 px-0.5 text-xs text-ink-dim hover:text-ink"
              >
                +
              </button>
              <button
                type="button"
                aria-label={`刪除群組 ${g.name}`}
                onClick={() => removeGroup(g.name)}
                className="invisible shrink-0 px-0.5 text-xs text-ink-dim hover:text-bear group-hover/hdr:visible"
              >
                ×
              </button>
            </header>

            {adding === g.name ? searchBox(g.name) : null}

            {isCollapsed ? null : (
              <ul
                data-testid={`wl-list-${g.name}`}
                ref={(el) => {
                  if (el) listRefs.current.set(g.name, el);
                  else listRefs.current.delete(g.name);
                }}
                className="flex flex-col"
              >
                {g.codes.map((code) => {
                  const q = quotes[code];
                  return (
                    <li key={code}>
                      <div
                        className={cn(
                          "group flex h-11 cursor-pointer items-center gap-2 border-b border-line px-1",
                          active === code && "bg-bg-deep",
                          drag?.code === code && "opacity-50",
                        )}
                        onClick={() => onSelect(code)}
                      >
                        <span
                          role="button"
                          aria-label={`拖拉 ${code}`}
                          className="cursor-grab select-none text-ink-dim"
                          onPointerDown={(e) => onHandleDown(g.name, code, e)}
                          onClick={(e) => e.stopPropagation()}
                        >
                          ⋮⋮
                        </span>
                        <span className="w-14 font-mono text-sm text-ink">{code}</span>
                        {q?.no_data ? (
                          <span className="flex-1 text-right text-xs text-ink-dim">無資料</span>
                        ) : (
                          <span className="flex flex-1 items-baseline justify-end gap-2 font-mono text-xs">
                            <span className="text-sm text-ink">{fmtPrice(q?.p ?? null)}</span>
                            <span
                              className={cn(
                                "w-14 text-right",
                                (q?.chg_pct ?? 0) > 0
                                  ? "text-bull"
                                  : (q?.chg_pct ?? 0) < 0
                                    ? "text-bear"
                                    : "text-ink-dim",
                              )}
                            >
                              {q?.chg_pct != null
                                ? `${q.chg_pct > 0 ? "+" : ""}${q.chg_pct.toFixed(2)}%`
                                : "-"}
                            </span>
                          </span>
                        )}
                        <button
                          type="button"
                          aria-label={`移組 ${code}`}
                          className="invisible text-ink-dim hover:text-accent group-hover:visible"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMovingCode(movingCode === code ? null : code);
                          }}
                        >
                          ⊞
                        </button>
                        <button
                          type="button"
                          aria-label={`移除 ${code}`}
                          className="invisible text-ink-dim hover:text-bear group-hover:visible"
                          onClick={(e) => {
                            e.stopPropagation();
                            remove(g.name, code);
                          }}
                        >
                          ×
                        </button>
                      </div>
                      {/* ⊞ 面板渲染在**該列正下方**:捲動容器搬到 aside 且群組全列出後,
                          放在所有 section 之後會落到側欄底部、常在可視範圍外(W-1 名義
                          保留但實際到不了)。 */}
                      {movingCode === code ? (
                        <div className="rounded border border-line bg-bg-deep p-2">
                          <p className="mb-1 font-mono text-xs text-ink-dim">{code} 所屬群組</p>
                          {groups.map((other) => (
                            <label
                              key={other.name}
                              className="flex items-center gap-1 py-0.5 text-xs text-ink"
                            >
                              <input
                                type="checkbox"
                                aria-label={other.name}
                                checked={other.codes.includes(code)}
                                onChange={() => toggleMembership(code, other.name)}
                              />
                              {other.name}
                            </label>
                          ))}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
                {g.codes.length === 0 ? (
                  <li className="flex min-h-11 items-center px-1 text-xs text-ink-dim">
                    拖曳股票到此
                  </li>
                ) : null}
              </ul>
            )}
          </section>
        );
      })}

      {/* 零群組(冷啟動 / 全刪):既有「全部下新增自動建自選」的語意搬到這裡,
          否則側欄只剩「+ 群組」一條隱性前提 = 死路(白名單 W-16)。 */}
      {groups.length === 0 ? (
        <div>
          <p className="px-1 text-xs text-ink-dim">尚無自選,輸入股號新增</p>
          {searchBox(DEFAULT_GROUP)}
        </div>
      ) : null}

      {addingGroup ? (
        <input
          autoFocus
          value={groupInput}
          onChange={(e) => setGroupInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addGroup()}
          onBlur={addGroup}
          placeholder="群組名稱"
          className="mx-1 rounded border border-line bg-bg px-1 py-0.5 text-xs text-ink outline-none focus:border-accent"
        />
      ) : (
        <button
          type="button"
          aria-label="新增群組"
          onClick={() => setAddingGroup(true)}
          className="mx-1 rounded border border-line px-1 py-0.5 text-xs text-ink-dim hover:text-ink"
        >
          + 群組
        </button>
      )}
    </aside>
  );
}
