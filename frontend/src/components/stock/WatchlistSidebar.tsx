import { useEffect, useRef, useState } from "react";

import { useSaveWatchlist, useStockWatchlist, type Group } from "@/hooks/useStockWatchlist";
import type { WatchlistQuote } from "@/hooks/useStockStream";
import { insertIndexFromPointer, reorder } from "@/lib/list-drag";
import { cn } from "@/lib/utils";

const ROW_H = 44;
const GROUP_KEY = "stock-wl-group";
const DEFAULT_GROUP = "自選";

function fmtPrice(milli: number | null): string {
  if (milli === null) return "-";
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

function unionCodes(groups: Group[]): string[] {
  const seen: string[] = [];
  for (const g of groups) {
    for (const code of g.codes) {
      if (!seen.includes(code)) seen.push(code);
    }
  }
  return seen;
}

function errText(message: string): string {
  if (message === "WATCHLIST_FULL") return "自選已達 30 檔上限";
  if (message === "BAD_CODE") return "股號格式不正確";
  if (message === "BAD_GROUP") return "群組名稱不合法";
  return "儲存失敗";
}

interface Props {
  active: string | null;
  onSelect: (code: string) => void;
  quotes: Record<string, WatchlistQuote>;
}

export function WatchlistSidebar({ active, onSelect, quotes }: Props) {
  const { data: groups = [], error } = useStockWatchlist();
  const save = useSaveWatchlist();
  const [input, setInput] = useState("");
  // activeGroup = null → 「全部」(union 顯示、停用拖拉 — design SC-6)
  const [activeGroup, setActiveGroup] = useState<string | null>(
    () => window.localStorage.getItem(GROUP_KEY) || null,
  );
  const [addingGroup, setAddingGroup] = useState(false);
  const [groupInput, setGroupInput] = useState("");
  const [movingCode, setMovingCode] = useState<string | null>(null);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [dragTo, setDragTo] = useState<number | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);

  useEffect(() => {
    if (activeGroup) window.localStorage.setItem(GROUP_KEY, activeGroup);
    else window.localStorage.removeItem(GROUP_KEY);
  }, [activeGroup]);

  const currentGroup = activeGroup !== null ? groups.find((g) => g.name === activeGroup) : undefined;
  const codes = currentGroup ? [...currentGroup.codes] : unionCodes(groups);
  const displayed = dragFrom !== null && dragTo !== null ? reorder(codes, dragFrom, dragTo) : codes;

  function mutateGroups(next: Group[]): void {
    save.mutate(next);
  }

  function add(): void {
    const code = input.trim().toUpperCase();
    if (!code || codes.includes(code)) return;
    if (currentGroup) {
      mutateGroups(
        groups.map((g) =>
          g.name === currentGroup.name ? { ...g, codes: [...g.codes, code] } : g,
        ),
      );
    } else {
      // 「全部」下新增 → 加入「自選」群組,不存在自動建立(impl-spec R4)
      const target = groups.find((g) => g.name === DEFAULT_GROUP);
      mutateGroups(
        target
          ? groups.map((g) =>
              g.name === DEFAULT_GROUP ? { ...g, codes: [...g.codes, code] } : g,
            )
          : [...groups, { name: DEFAULT_GROUP, codes: [code] }],
      );
    }
    setInput("");
  }

  function remove(code: string): void {
    if (currentGroup) {
      mutateGroups(
        groups.map((g) =>
          g.name === currentGroup.name ? { ...g, codes: g.codes.filter((c) => c !== code) } : g,
        ),
      );
    } else {
      // 「全部」下移除 = 從所有群組移除(impl-spec R4)
      mutateGroups(groups.map((g) => ({ ...g, codes: g.codes.filter((c) => c !== code) })));
    }
  }

  function addGroup(): void {
    const name = groupInput.trim();
    setAddingGroup(false);
    setGroupInput("");
    if (!name || groups.some((g) => g.name === name)) return;
    mutateGroups([...groups, { name, codes: [] }]);
  }

  function removeGroup(name: string): void {
    if (activeGroup === name) setActiveGroup(null);
    mutateGroups(groups.filter((g) => g.name !== name));
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

  function onHandleDown(index: number, e: React.PointerEvent): void {
    if (!currentGroup) return; // 「全部」停用拖拉
    e.preventDefault();
    setDragFrom(index);
    setDragTo(index);
    const list = listRef.current;
    const groupName = currentGroup.name;
    const move = (ev: PointerEvent): void => {
      const top = list?.getBoundingClientRect().top ?? 0;
      setDragTo(insertIndexFromPointer(ev.clientY - top, ROW_H, codes.length));
    };
    const up = (ev: PointerEvent): void => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const top = list?.getBoundingClientRect().top ?? 0;
      const to = insertIndexFromPointer(ev.clientY - top, ROW_H, codes.length);
      setDragFrom(null);
      setDragTo(null);
      if (to !== index) {
        mutateGroups(
          groups.map((g) =>
            g.name === groupName ? { ...g, codes: reorder(g.codes, index, to) } : g,
          ),
        );
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col gap-2">
      {/* 群組 tab 列(SC-6) */}
      <div className="flex flex-wrap items-center gap-1 border-b border-line pb-1" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeGroup === null}
          onClick={() => setActiveGroup(null)}
          className={cn(
            "rounded px-1.5 py-0.5 text-xs",
            activeGroup === null ? "bg-bg-deep text-ink" : "text-ink-dim hover:text-ink",
          )}
        >
          全部
        </button>
        {groups.map((g) => (
          <span key={g.name} className="group/tab relative">
            <button
              type="button"
              role="tab"
              aria-selected={activeGroup === g.name}
              onClick={() => setActiveGroup(g.name)}
              className={cn(
                "rounded px-1.5 py-0.5 text-xs",
                activeGroup === g.name ? "bg-bg-deep text-ink" : "text-ink-dim hover:text-ink",
              )}
            >
              {g.name}
            </button>
            <button
              type="button"
              aria-label={`刪除群組 ${g.name}`}
              onClick={() => removeGroup(g.name)}
              className="invisible absolute -right-1 -top-1 text-xs text-ink-dim hover:text-bear group-hover/tab:visible"
            >
              ×
            </button>
          </span>
        ))}
        {addingGroup ? (
          <input
            autoFocus
            value={groupInput}
            onChange={(e) => setGroupInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addGroup()}
            onBlur={addGroup}
            placeholder="群組名稱"
            className="w-16 rounded border border-line bg-bg px-1 py-0.5 text-xs text-ink outline-none focus:border-accent"
          />
        ) : (
          <button
            type="button"
            aria-label="新增群組"
            onClick={() => setAddingGroup(true)}
            className="rounded px-1 text-xs text-ink-dim hover:text-ink"
          >
            +
          </button>
        )}
      </div>
      <div className="flex gap-1">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="輸入股號"
          className="w-full rounded border border-line bg-bg px-2 py-1 font-mono text-sm text-ink outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={add}
          className="shrink-0 rounded border border-line px-2 py-1 text-sm text-ink hover:border-accent"
        >
          新增
        </button>
      </div>
      {save.error ? <p className="text-xs text-bear">{errText(save.error.message)}</p> : null}
      {error ? <p className="text-xs text-bear">自選清單載入失敗</p> : null}
      <ul ref={listRef} className="flex flex-col overflow-y-auto">
        {displayed.map((code) => {
          const q = quotes[code];
          const index = codes.indexOf(code);
          return (
            <li
              key={code}
              className={cn(
                "group flex h-11 cursor-pointer items-center gap-2 border-b border-line px-1",
                active === code && "bg-bg-deep",
                dragFrom !== null && displayed[dragTo ?? -1] === code && "border-accent",
              )}
              onClick={() => onSelect(code)}
            >
              {currentGroup ? (
                <span
                  role="button"
                  aria-label={`拖拉 ${code}`}
                  className="cursor-grab select-none text-ink-dim"
                  onPointerDown={(e) => onHandleDown(index, e)}
                  onClick={(e) => e.stopPropagation()}
                >
                  ⋮⋮
                </span>
              ) : null}
              <span className="w-14 font-mono text-sm text-ink">{code}</span>
              {q?.no_data ? (
                <span className="flex-1 text-right text-xs text-ink-dim">無資料</span>
              ) : (
                <span className="flex flex-1 items-baseline justify-end gap-2 font-mono text-xs">
                  <span className="text-sm text-ink">{fmtPrice(q?.p ?? null)}</span>
                  <span
                    className={cn(
                      "w-14 text-right",
                      (q?.chg_pct ?? 0) > 0 ? "text-bull" : (q?.chg_pct ?? 0) < 0 ? "text-bear" : "text-ink-dim",
                    )}
                  >
                    {q?.chg_pct != null ? `${q.chg_pct > 0 ? "+" : ""}${q.chg_pct.toFixed(2)}%` : "-"}
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
                  remove(code);
                }}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
      {movingCode !== null ? (
        <div className="rounded border border-line bg-bg-deep p-2">
          <p className="mb-1 font-mono text-xs text-ink-dim">{movingCode} 所屬群組</p>
          {groups.map((g) => (
            <label key={g.name} className="flex items-center gap-1 py-0.5 text-xs text-ink">
              <input
                type="checkbox"
                aria-label={g.name}
                checked={g.codes.includes(movingCode)}
                onChange={() => toggleMembership(movingCode, g.name)}
              />
              {g.name}
            </label>
          ))}
        </div>
      ) : null}
      {displayed.length === 0 ? <p className="text-xs text-ink-dim">尚無自選,輸入股號新增</p> : null}
    </aside>
  );
}
