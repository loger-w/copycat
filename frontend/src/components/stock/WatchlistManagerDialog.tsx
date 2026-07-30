import { useEffect, useRef, useState } from "react";

import { errText, useSaveWatchlist } from "@/hooks/useStockWatchlist";
import { useStockNames } from "@/hooks/useStockNames";
import {
  addGroup,
  deleteGroup,
  removeCode,
  renameGroup,
  setMembership,
  type Watchlist,
} from "@/lib/watchlist-model";

interface Props {
  open: boolean;
  wl: Watchlist;
  onClose: () => void;
  /** 刪組成功後通知側欄清折疊孤兒(W-20;collapsed state 住在側欄) */
  onGroupDeleted: (name: string) => void;
}

export function WatchlistManagerDialog({ open, wl, onClose, onGroupDeleted }: Props) {
  const save = useSaveWatchlist();
  const { data: names = [] } = useStockNames();
  const dlgRef = useRef<HTMLDialogElement | null>(null);
  const [groupInput, setGroupInput] = useState("");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [renameInput, setRenameInput] = useState("");
  /** 前端就擋下來的錯誤(撞名 → 零 PUT),與 mutation 錯誤共用同一份文案 */
  const [localError, setLocalError] = useState<string | null>(null);

  // 開關只走這一條路徑,`open` **不進 JSX** —— React 在 commit 階段寫入的 open 屬性會讓
  // 之後的 showModal() 依標準拋 InvalidStateError,而 jsdom 沒有 showModal 會跳過
  // feature-detect → 測試全綠、真瀏覽器第一次點「管理」就白畫面。
  useEffect(() => {
    const el = dlgRef.current;
    if (el === null) return;
    if (typeof el.showModal === "function") {
      if (open) {
        if (!el.open) el.showModal(); // 重複 showModal 在已 open 的元素上同樣會 throw
      } else {
        el.close();
      }
      return;
    }
    // jsdom 26 的 HTMLDialogElement 是空 class(無 showModal / close / Esc 行為)
    if (open) el.setAttribute("open", "");
    else el.removeAttribute("open");
  }, [open]);

  /** 純函數回原物件 = 無變化 → 零 PUT。**這裡不報錯** —— 群組名撞名那條由呼叫端
   *  自己顯示 BAD_GROUP,勾選 / 移除路徑的無變化不該冒出「群組名稱不合法」。 */
  function commit(next: Watchlist, onDone?: () => void): void {
    if (next === wl) return;
    setLocalError(null);
    save.mutate(next, onDone === undefined ? undefined : { onSuccess: onDone });
  }

  function submitAddGroup(): void {
    const name = groupInput.trim();
    if (name === "") return;
    const next = addGroup(wl, name);
    if (next === wl) {
      setLocalError("BAD_GROUP"); // 撞既有名 → 零 PUT + 文案
      return;
    }
    setGroupInput("");
    commit(next);
  }

  function submitRename(from: string): void {
    const next = renameGroup(wl, from, renameInput);
    if (next === wl) {
      setLocalError("BAD_GROUP"); // 撞既有名 / 空白 → 保留輸入框讓使用者改
      return;
    }
    setRenaming(null);
    commit(next);
  }

  const errorMessage = localError ?? (save.error ? save.error.message : null);

  return (
    <dialog
      ref={dlgRef}
      aria-label="管理群組與股票"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      className="w-96 max-w-[90vw] rounded border border-line bg-bg p-3 text-ink backdrop:bg-black/50"
    >
      {/* 關閉時不渲染內容:RTL 的 getAllBy* 不過濾隱藏元素,常駐渲染會讓側欄的計數型
          斷言(2330 出現 2 次 / 握把 4 個)在 Dialog 掛上去之後莫名變 3 / 6 */}
      {open ? (
        <>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm text-ink">管理群組與股票</h2>
            <button
              type="button"
              aria-label="關閉"
              onClick={onClose}
              className="px-1 text-xs text-ink-dim hover:text-ink"
            >
              ×
            </button>
          </div>

          {errorMessage !== null ? (
            <p className="mb-2 text-xs text-bear">{errText(errorMessage)}</p>
          ) : null}

          <section aria-label="群組" className="mb-3">
            <h3 className="mb-1 text-xs text-ink-dim">群組</h3>
            <ul className="flex flex-col">
              {wl.groups.map((g) => (
                <li
                  key={g.name}
                  className="flex items-center gap-2 border-b border-line px-1 py-1 text-xs"
                >
                  {renaming === g.name ? (
                    <input
                      autoFocus
                      value={renameInput}
                      onChange={(e) => setRenameInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") submitRename(g.name);
                        if (e.key === "Escape") {
                          // 不讓它冒泡:取消改名不該順便關掉整個 Dialog
                          e.stopPropagation();
                          setRenaming(null);
                        }
                      }}
                      className="min-w-0 flex-1 rounded border border-line bg-bg px-1 py-0.5 text-ink outline-none focus:border-accent"
                    />
                  ) : (
                    <>
                      <span className="min-w-0 flex-1 truncate text-ink">{g.name}</span>
                      <span className="font-mono text-[0.625rem] text-ink-dim">
                        {g.codes.length}
                      </span>
                      <button
                        type="button"
                        aria-label={`改名 ${g.name}`}
                        onClick={() => {
                          setRenaming(g.name);
                          setRenameInput(g.name);
                        }}
                        className="px-0.5 text-ink-dim hover:text-ink"
                      >
                        ✎
                      </button>
                      <button
                        type="button"
                        aria-label={`刪除群組 ${g.name}`}
                        onClick={() => commit(deleteGroup(wl, g.name), () => onGroupDeleted(g.name))}
                        className="px-0.5 text-ink-dim hover:text-bear"
                      >
                        ×
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
            <div className="mt-1 flex gap-1">
              <input
                value={groupInput}
                onChange={(e) => setGroupInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitAddGroup();
                }}
                placeholder="群組名稱"
                className="min-w-0 flex-1 rounded border border-line bg-bg px-2 py-1 text-xs text-ink outline-none focus:border-accent"
              />
              <button
                type="button"
                aria-label="新增群組"
                onClick={submitAddGroup}
                className="shrink-0 rounded border border-line px-2 py-1 text-xs text-ink hover:border-accent"
              >
                新增群組
              </button>
            </div>
          </section>

          <section aria-label="股票">
            <h3 className="mb-1 text-xs text-ink-dim">股票</h3>
            <ul className="flex flex-col">
              {wl.codes.map((code) => (
                <li
                  key={code}
                  className="flex items-center gap-2 border-b border-line px-1 py-1 text-xs"
                >
                  <span className="w-14 shrink-0 font-mono text-ink">{code}</span>
                  <span className="w-16 shrink-0 truncate text-ink-muted">
                    {names.find((n) => n.code === code)?.name ?? ""}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                    {wl.groups.map((g) => (
                      <label key={g.name} className="flex items-center gap-1 text-ink">
                        <input
                          type="checkbox"
                          aria-label={`${code} 屬於 ${g.name}`}
                          checked={g.codes.includes(code)}
                          onChange={(e) =>
                            commit(setMembership(wl, code, g.name, e.target.checked))
                          }
                        />
                        {g.name}
                      </label>
                    ))}
                  </span>
                  <button
                    type="button"
                    aria-label={`從自選移除 ${code}`}
                    onClick={() => commit(removeCode(wl, code))}
                    className="shrink-0 px-0.5 text-ink-dim hover:text-bear"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </dialog>
  );
}
