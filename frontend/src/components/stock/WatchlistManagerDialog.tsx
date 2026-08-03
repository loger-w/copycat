import { useEffect, useMemo, useRef, useState } from "react";

import { errText, useSaveWatchlist } from "@/hooks/useStockWatchlist";
import { useStockNames } from "@/hooks/useStockNames";
import { searchStocks, SUGGEST_LIMIT } from "@/lib/stock-search";
import { cn } from "@/lib/utils";
import {
  addCode,
  addGroup,
  assignToGroup,
  deleteGroup,
  isSameWatchlist,
  removeCode,
  removeFromGroup,
  renameGroup,
  ungroupedCodes,
  type Group,
  type Watchlist,
} from "@/lib/watchlist-model";

/** 「未分組」是左欄第一列的**偽群組**,不是真的可以建的群組名 —— 兩者同名的話畫面上
 *  無法區分(`selected === null` vs 一個真的叫「未分組」的群組)。 */
const UNGROUPED_LABEL = "未分組";

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
  /** 左欄選中的群組名;`null` = 未分組偽群組。**只當意圖**,渲染一律走下面的 derived 值 */
  const [selected, setSelected] = useState<string | null>(null);
  const [stockInput, setStockInput] = useState("");

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

  // 本元件是**常駐掛載**(側欄只切 `open`)→ 每次開啟都要把暫態歸零,否則上次選的組 /
  // 改名輸入 / 錯誤文案會殘留到下一次開啟。
  // 用 render 期間調整 state 的官方 pattern,不用 effect —— 專案有
  // react-you-might-not-need-an-effect lint(同 CandleChart 的 prevTotal 寫法)。
  const [prevOpen, setPrevOpen] = useState(open);
  if (prevOpen !== open) {
    setPrevOpen(open);
    if (open) {
      setSelected(null);
      setRenaming(null);
      setStockInput("");
      setLocalError(null);
    }
  }

  /** 純函數回原物件 = 無變化 → 零 PUT。**這裡不報錯** —— 群組名撞名那條由呼叫端
   *  自己顯示 BAD_GROUP,勾選 / 移除路徑的無變化不該冒出「群組名稱不合法」。 */
  function commit(next: Watchlist, onDone?: () => void): void {
    // 深度比對不可省(W-9 三處之一,review F1):`assignToGroup` / `removeFromGroup` 等
    // 恆回新陣列,內容相同也會送出,而內容相同的 PUT 會讓後端重設整個訂閱池
    // (TC4 全量 UNSUB/SUB),且無錯誤訊號、畫面也看不出來。
    if (isSameWatchlist(next, wl)) return;
    setLocalError(null);
    save.mutate(next, onDone === undefined ? undefined : { onSuccess: onDone });
  }

  function submitAddGroup(): void {
    const name = groupInput.trim();
    if (name === "") return;
    if (name === UNGROUPED_LABEL) {
      setLocalError("BAD_GROUP"); // 保留名:與左欄的偽群組同名會無法區分
      return;
    }
    const next = addGroup(wl, name);
    if (next === wl) {
      setLocalError("BAD_GROUP"); // 撞既有名 → 零 PUT + 文案
      return;
    }
    setGroupInput("");
    commit(next);
  }

  function submitRename(from: string): void {
    if (renameInput.trim() === UNGROUPED_LABEL) {
      setLocalError("BAD_GROUP");
      return;
    }
    const next = renameGroup(wl, from, renameInput);
    if (next === wl) {
      setLocalError("BAD_GROUP"); // 撞既有名 / 空白 → 保留輸入框讓使用者改
      return;
    }
    setRenaming(null);
    // 改名成功前不要動 selected —— 樂觀更新在 PUT 失敗時會留下懸空的選取
    commit(next, () => setSelected(renameInput.trim()));
  }

  // **右欄一律用 derived 值渲染**:`selected` 只是意圖。改名 / 刪除都是先 mutate 再更新
  // UI,失敗時命令式的 setSelected 已經跑掉 → 指向不存在的組、右欄空白且無說明。
  const activeGroup: Group | null =
    selected === null ? null : (wl.groups.find((g) => g.name === selected) ?? null);
  const ungrouped = ungroupedCodes(wl);
  const rows = activeGroup === null ? ungrouped : activeGroup.codes;
  // 名冊 2,401 筆;逐列 `names.find(...)` 是 O(列數 × 2401)。改 Map 查表(同側欄作法,
  // 輸出逐值相同 —— 名冊無重複 code,find 的首筆命中即 Map 的值)。
  const nameMap = useMemo(() => new Map(names.map((n) => [n.code, n.name])), [names]);
  const nameOf = (code: string): string => nameMap.get(code) ?? "";
  const suggestions = searchStocks(stockInput, names, SUGGEST_LIMIT);

  /** 加進本組:`addCode` 與 `assignToGroup` **合成單次 PUT** ——
   *  分兩次會產出「在群組但不在 codes」的中間態。 */
  function addStock(code: string): void {
    setStockInput("");
    const withCode = addCode(wl, code);
    commit(
      activeGroup === null
        ? withCode
        : assignToGroup(withCode, code, activeGroup.name, activeGroup.codes.length),
    );
  }

  const errorMessage = localError ?? (save.error ? save.error.message : null);

  function groupRow(label: string, count: number, key: string | null): React.ReactElement {
    const isSelected = selected === key;
    const real = key !== null;
    return (
      <li key={key ?? "__ungrouped__"}>
        {renaming === key && real ? (
          <input
            autoFocus
            value={renameInput}
            onChange={(e) => setRenameInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitRename(key);
              if (e.key === "Escape") {
                // 不讓它冒泡:取消改名不該順便關掉整個 Dialog
                e.stopPropagation();
                setRenaming(null);
              }
            }}
            className="m-1 w-[calc(100%-0.5rem)] rounded border border-line bg-bg px-1 py-0.5 text-xs text-ink outline-none focus:border-accent"
          />
        ) : (
          // border-l-2 兩態都在,選中不位移;用 side-specific 的 border-l-* 而不是全側
          // border-*(twMerge 會把同 conflict group 的後者靜默吃掉)
          <div
            className={cn(
              "group flex h-9 w-full items-center gap-2 border-l-2 px-2 text-xs",
              isSelected
                ? "border-l-accent bg-bg-deep text-ink"
                : "border-l-transparent text-ink-muted hover:bg-surface hover:text-ink",
            )}
          >
            <button
              type="button"
              onClick={() => setSelected(key)}
              className="min-w-0 flex-1 truncate text-left"
            >
              {label}
            </button>
            <span className="shrink-0 font-mono text-[0.625rem] text-ink-dim">{count}</span>
            {real ? (
              <>
                <button
                  type="button"
                  aria-label={`改名 ${label}`}
                  onClick={() => {
                    setRenaming(key);
                    setRenameInput(label);
                  }}
                  className={cn(
                    "w-4 shrink-0 text-ink-dim hover:text-ink",
                    isSelected ? "visible" : "invisible group-hover:visible",
                  )}
                >
                  ✎
                </button>
                <button
                  type="button"
                  aria-label={`刪除群組 ${label}`}
                  onClick={() =>
                    commit(deleteGroup(wl, key), () => {
                      onGroupDeleted(key);
                      setSelected((cur) => (cur === key ? null : cur));
                    })
                  }
                  className={cn(
                    "w-4 shrink-0 text-ink-dim hover:text-bear",
                    isSelected ? "visible" : "invisible group-hover:visible",
                  )}
                >
                  ×
                </button>
              </>
            ) : null}
          </div>
        )}
      </li>
    );
  }

  return (
    <dialog
      ref={dlgRef}
      aria-label="管理群組與股票"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      // **原生 close 一定要拉回 prop**(review R4)。`display` 現在由 `open` prop 選,
      // 前提是「prop 永遠等於元素真實狀態」。而群組改名輸入框對 Escape 呼叫
      // `stopPropagation()` 且不呼叫 `onClose` —— stopPropagation 只擋 React 合成事件冒泡,
      // 擋不掉瀏覽器對 modal dialog 的原生 cancel/close。那條路徑會讓元素 open 變 false
      // 但 prop 還是 true → class 停在 `flex`、內容仍渲染,而 effect 因 `open` 沒變不會重跑
      // showModal() → 同一個「方框卡在畫面上」的 bug 換形態復發(這次盒子裡還有內容、
      // 非 modal、Esc 也關不掉)。
      onClose={() => {
        if (open) onClose();
      }}
      // **m-auto 不可省**:Tailwind v4 的 preflight 把 `margin: 0` 套到所有元素(含
      // dialog),覆蓋掉 UA stylesheet 給 modal dialog 的 `margin: auto` → 貼在左上角。
      // jsdom 沒有版面引擎,這個 bug 沒有任何測試看得到(同 showModal 的教訓)。
      // 高度**固定**不是 max-h:切換群組時 dialog 不跳高,右欄自己捲。
      //
      // **display 必須跟著 `open` 切**:UA stylesheet 的 `dialog:not([open]) { display:none }`
      // 是**瀏覽器層**規則,而 `flex` 是 author 層 —— author 勝,寫死 `flex` 會讓關閉的
      // dialog 照樣佔版面(896×480 的空盒子壓在圖表上,2026-07-31 真瀏覽器實測)。
      // 這裡刻意用 `open` prop 選 class 而不是 Tailwind 的 `open:` variant:
      // variant 產出的 class 字串恆定,測試只能斷言「有這個 class」,回歸時抓不到;
      // prop 驅動的 class 會隨狀態變化,jsdom 測得到。
      // ⚠ `open` 仍**不進 JSX 的 open 屬性**(見上方 effect 註解)—— 這裡只拿它選 class。
      className={cn(
        open ? "flex" : "hidden",
        "m-auto h-[min(30rem,80vh)] w-[min(56rem,92vw)] flex-col overflow-hidden rounded border border-line bg-bg p-0 text-ink backdrop:bg-black/50",
      )}
    >
      {/* 關閉時不渲染內容:RTL 的 getAllBy* 不過濾隱藏元素,常駐渲染會讓側欄的計數型
          斷言(2330 出現 2 次 / 握把 4 個)在 Dialog 掛上去之後莫名變 3 / 6 */}
      {open ? (
        <>
          <div className="flex h-10 shrink-0 items-center justify-between border-b border-line px-3">
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
            <p className="shrink-0 border-b border-line px-3 py-1 text-xs text-bear">
              {errText(errorMessage)}
            </p>
          ) : null}

          <div className="flex min-h-0 flex-1">
            {/* 左欄:群組。固定寬不用百分比 —— 內容(組名 + 計數 + 兩顆圖示鈕)寬度有
                天花板,百分比會讓它在寬螢幕上白白變胖;要空間的是右欄。 */}
            <section
              aria-label="群組"
              className="flex min-h-0 w-44 shrink-0 flex-col border-r border-line"
            >
              <ul className="flex-1 overflow-y-auto">
                {/* 「未分組」固定置頂。**必須有** —— 舊版的 checkbox 矩陣列的是 codes 全體,
                    是「從自選整個移除」的唯一入口;改成分組視圖後若左欄沒有未分組,
                    未分組的股票在 Dialog 裡完全不可見也刪不掉 = 功能退化。
                    順序也與側欄一致(未分組在上、群組在後),不必重新學。 */}
                {groupRow(UNGROUPED_LABEL, ungrouped.length, null)}
                {wl.groups.map((g) => groupRow(g.name, g.codes.length, g.name))}
                {wl.groups.length === 0 ? (
                  <li className="px-2 py-2 text-xs text-ink-dim">尚無群組,可在下方新增</li>
                ) : null}
              </ul>
              <div className="shrink-0 border-t border-line p-2">
                <div className="flex gap-1">
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
                    新增
                  </button>
                </div>
              </div>
            </section>

            {/* 右欄:目前選中群組的股票 */}
            <section aria-label="股票" className="flex min-h-0 min-w-0 flex-1 flex-col">
              <div className="shrink-0 border-b border-line px-3 py-2">
                <input
                  value={stockInput}
                  onChange={(e) => setStockInput(e.target.value)}
                  placeholder={
                    activeGroup === null
                      ? "加入自選 — 股號或名稱"
                      : `加入股票到「${activeGroup.name}」— 股號或名稱`
                  }
                  className="w-full rounded border border-line bg-bg px-2 py-1 text-xs text-ink outline-none focus:border-accent"
                />
                {suggestions.length > 0 ? (
                  <ul className="mt-1 rounded border border-line bg-bg-deep">
                    {suggestions.map((s) => {
                      // 未分組視圖要看的是「是否已在自選」不是「是否在 rows」(review F6):
                      // 已屬別組的檔不在 ungrouped 裡,若只看 rows 會顯示成可加入,
                      // 但點下去 addCode 回原物件 → 零 PUT 早退,唯一可見變化是搜尋框被
                      // 清空 = 看起來成功、實際什麼都沒發生。
                      const already =
                        activeGroup === null ? wl.codes.includes(s.code) : rows.includes(s.code);
                      return (
                        <li key={s.code}>
                          <button
                            type="button"
                            // `save.isPending` 期間停用(review F1):PUT 未回前 `wl` 仍是
                            // 舊值,commit() 的零 PUT 早退**擋不住**這條 —— 算出來的 next
                            // 與舊 wl 內容確實不同,兩次點擊就是兩筆真 PUT,而每筆都會讓
                            // 後端重設整個訂閱池(TC4 全量 UNSUB/SUB)。
                            disabled={already || save.isPending}
                            aria-label={`加入 ${s.code} 到 ${activeGroup?.name ?? UNGROUPED_LABEL}`}
                            onClick={() => addStock(s.code)}
                            className="flex w-full items-baseline gap-2 px-2 py-1 text-left text-xs hover:bg-surface disabled:opacity-50 disabled:hover:bg-transparent"
                          >
                            <span className="w-14 font-mono text-ink">{s.code}</span>
                            <span className="min-w-0 flex-1 truncate text-ink-muted">{s.name}</span>
                            {already ? (
                              <span className="text-ink-dim">
                                {activeGroup === null ? "已在自選" : "已在此群組"}
                              </span>
                            ) : null}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
              <ul className="min-h-0 flex-1 overflow-y-auto px-1">
                {rows.map((code) => (
                  <li
                    key={code}
                    data-testid={`mgr-row-${code}`}
                    className="flex h-9 items-center gap-2 border-b border-line px-2 text-xs"
                  >
                    <span className="w-14 shrink-0 font-mono text-ink">{code}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-muted">{nameOf(code)}</span>
                    {/* 一檔多組是既有能力;矩陣拆掉後不標的話使用者會以為只能屬一組。
                        唯讀,不可點 —— 免得跟左欄的選取語意打架。 */}
                    <span className="flex shrink-0 gap-1 overflow-hidden whitespace-nowrap">
                      {wl.groups
                        .filter((g) => g.name !== activeGroup?.name && g.codes.includes(code))
                        .map((g) => (
                          <span
                            key={g.name}
                            className="rounded border border-line px-1 text-[0.625rem] text-ink-dim"
                          >
                            {g.name}
                          </span>
                        ))}
                    </span>
                    {activeGroup !== null ? (
                      <button
                        type="button"
                        aria-label={`從 ${activeGroup.name} 移出 ${code}`}
                        onClick={() => commit(removeFromGroup(wl, code, activeGroup.name))}
                        className="w-4 shrink-0 text-ink-dim hover:text-ink"
                      >
                        −
                      </button>
                    ) : null}
                    <button
                      type="button"
                      aria-label={`從自選移除 ${code}`}
                      onClick={() => commit(removeCode(wl, code))}
                      className="w-4 shrink-0 text-ink-dim hover:text-bear"
                    >
                      ×
                    </button>
                  </li>
                ))}
                {rows.length === 0 ? (
                  <li className="px-2 py-3 text-xs text-ink-dim">
                    {activeGroup !== null
                      ? `「${activeGroup.name}」還沒有股票 —— 用上方搜尋加入`
                      : wl.codes.length === 0
                        ? "自選清單是空的 —— 用上方搜尋加入第一檔"
                        : "所有自選股都已分組"}
                  </li>
                ) : null}
              </ul>
            </section>
          </div>
        </>
      ) : null}
    </dialog>
  );
}
