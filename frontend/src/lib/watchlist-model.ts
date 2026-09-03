/** 自選清單模型純函數(stock-ui-round5 §🟢-7)。
 *
 *  schema v3:`codes` = 自選全體(有序)= 訂閱池,`groups` 只記成員關係,
 *  **未分組 = codes − ∪groups 衍生不另存** —— 另存一份會產生「同一檔同時在未分組與
 *  某群組」的可違反不變式,畫面上的樣態是同一檔出現兩次 = 靜默資料錯。
 *
 *  全部純函數;**無變化時回原物件**(呼叫端據此早退,避免送出內容相同的 PUT ——
 *  那會讓後端重設整個訂閱池、TC4 全量 UNSUB/SUB,而且無錯誤訊號、無測試會紅)。 */

import { SCREEN_GROUP_NAME, UNGROUPED_PICK } from "@/lib/constants";

export interface Group {
  name: string;
  codes: string[];
}

export interface Watchlist {
  codes: string[];
  groups: Group[];
}

/** 兩份自選內容是否相同(同一物件 或 深度逐字相同)。
 *
 *  呼叫端的**零 PUT 早退**判定(W-9 三處共用):純函數無變化時回原物件,但
 *  `assignToGroup` 等恆回新陣列 → identity 比對不夠,深度比對不可省。內容相同的
 *  PUT 會讓後端重設整個訂閱池(TC4 全量 UNSUB/SUB),而且無錯誤訊號、畫面也看不出來。 */
export function isSameWatchlist(a: Watchlist, b: Watchlist): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

/** 插入 + off-by-one 補償。
 *
 *  `slot` = 相對目標清單「移除前」渲染索引(含被拖的那一列,即 `dropTargetFromPointer`
 *  直接回傳的值),而真正寫入的是**濾掉該檔之後**的陣列 —— 該檔已在清單中且往下拖時
 *  兩者差 1。少了 `- 1`,`[A,B,C,D]` 拖 A 到槽 3 會得到 `BCDA` 而不是 `BCAD`,
 *  且會靜默寫進後端。 */
function insertAt(list: string[], code: string, slot: number, at: number): string[] {
  const index = at >= 0 && slot > at ? slot - 1 : slot;
  const base = list.filter((c) => c !== code);
  const clamped = Math.max(0, Math.min(base.length, index));
  return [...base.slice(0, clamped), code, ...base.slice(clamped)];
}

/** 未分組清單內的 `slot` → `codes` 的絕對 index 後插入。
 *
 *  未分組是 `codes` 的**子序列**,而被改寫的是 `codes` 本身 —— 直接拿 slot 當 index
 *  會在「未分組之間夾著群組成員」時落錯位置。 */
function reinsertIntoCodes(wl: Watchlist, code: string, slot: number): string[] {
  const ung = ungroupedCodes(wl);
  const target = ung[Math.max(0, slot)];
  const absSlot = target === undefined ? wl.codes.length : wl.codes.indexOf(target);
  return insertAt(wl.codes, code, absSlot, wl.codes.indexOf(code));
}

export function ungroupedCodes(wl: Watchlist): string[] {
  const grouped = new Set(wl.groups.flatMap((g) => g.codes));
  return wl.codes.filter((code) => !grouped.has(code));
}

/** 群組檢視看得到的群組 = 扣掉「盤前篩選」(`SCREEN_GROUP_NAME`;~60 檔不是圖牆要看的,側欄照舊)。
 *  **唯一一份過濾**:`resolveGroupPick` / `groupForCode` 與 GroupGridView 的 pill 清單都吃這裡
 *  (pr-187 review #4:pill 自己再濾一次 = 兩份實作,改成「藏兩組」只改一邊時 pill 列 A、解析回 B,
 *  兩邊都不報錯)。 */
export function visibleGroups(groups: readonly Group[]): Group[] {
  return groups.filter((g) => g.name !== SCREEN_GROUP_NAME);
}

/** 群組檢視實際選中的一組(mod/group-grid-ticks T5,#181)。
 *
 *  可選集合 = `visibleGroups` + 虛擬「未分組」(`UNGROUPED_PICK`,**有成員才可選**;成員即時算
 *  不落檔)。`picked` 是 localStorage 記住的名字:不在集合內(被刪 / 是盤前篩選 / 未分組已空)→
 *  fallback 第一個可見群組,再退未分組,什麼都沒有 → null(呼叫端顯示「尚無群組」空態)。
 *
 *  **唯一一份解析**:GroupGridView 的 pill 選中態與 StockPage 的「訊號切組」都問這裡 ——
 *  各寫一份的漂移樣態是 pill 選中 A、訊號卻以 B 當「現群組」判要不要切。 */
export function resolveGroupPick(
  groups: readonly Group[],
  ungrouped: readonly string[],
  picked: string | null,
): { name: string; codes: readonly string[] } | null {
  const visible = visibleGroups(groups);
  const ungroupedOn = ungrouped.length > 0;
  if (picked === UNGROUPED_PICK && ungroupedOn) return { name: UNGROUPED_PICK, codes: ungrouped };
  const hit = picked === null ? undefined : visible.find((g) => g.name === picked);
  const group = hit ?? visible[0];
  if (group !== undefined) return { name: group.name, codes: group.codes };
  return ungroupedOn ? { name: UNGROUPED_PICK, codes: ungrouped } : null;
}

/** 群組檢視下點訊號 → 圖牆該停在哪一組(mod/group-grid-ticks T6,#184)。
 *
 *  `current` 已含該檔 → 回 `current`(不切:使用者正在看的那組本來就有它);否則群組序第一個
 *  含它的可見群組,再退未分組(`UNGROUPED_PICK`);盤前篩選不算(圖牆選不到它)、不在自選 → null
 *  = 呼叫端只換右欄標的、群組不動。一檔可多組時「群組序第一個」是刻意的簡單規則,不猜偏好。 */
export function groupForCode(
  groups: readonly Group[],
  ungrouped: readonly string[],
  current: string | null,
  code: string,
): string | null {
  const visible = visibleGroups(groups);
  const inUngrouped = ungrouped.includes(code);
  if (current !== null) {
    const cur = current === UNGROUPED_PICK ? inUngrouped : visible.some((g) => g.name === current && g.codes.includes(code));
    if (cur) return current;
  }
  const first = visible.find((g) => g.codes.includes(code));
  if (first !== undefined) return first.name;
  return inUngrouped ? UNGROUPED_PICK : null;
}

/** 加進自選(落未分組);已在自選 → 原物件。 */
export function addCode(wl: Watchlist, code: string): Watchlist {
  if (wl.codes.includes(code)) return wl;
  return { ...wl, codes: [...wl.codes, code] };
}

/** 從自選整個移除(codes 與所有群組)。 */
export function removeCode(wl: Watchlist, code: string): Watchlist {
  return {
    codes: wl.codes.filter((c) => c !== code),
    groups: wl.groups.map((g) => ({ ...g, codes: g.codes.filter((c) => c !== code) })),
  };
}

/** 未分組 → 群組:目標組插入即可,未分組是衍生集合會自動少掉它。 */
export function assignToGroup(
  wl: Watchlist,
  code: string,
  group: string,
  slot: number,
): Watchlist {
  return {
    ...wl,
    groups: wl.groups.map((g) =>
      g.name === group ? { ...g, codes: insertAt(g.codes, code, slot, g.codes.indexOf(code)) } : g,
    ),
  };
}

/** 群組 A → 群組 B:**移動語意**(來源組移除,round 4 拍板不可改成複製)。
 *  `from === to` 時退化為同組排序(W-19);其他群組的歸屬不動(W-1)。 */
export function moveToGroup(
  wl: Watchlist,
  code: string,
  from: string,
  to: string,
  slot: number,
): Watchlist {
  return {
    ...wl,
    groups: wl.groups.map((g) => {
      // 先 filter 再插入:`from === to` 時 insertAt 內的 filter 已完成移除
      if (g.name === to) {
        return { ...g, codes: insertAt(g.codes, code, slot, g.codes.indexOf(code)) };
      }
      if (g.name === from) return { ...g, codes: g.codes.filter((c) => c !== code) };
      return g;
    }),
  };
}

/** 群組 → 未分組:**從所有群組移除**。只移除來源組的話,一檔多組的股票會從來源組
 *  消失卻不出現在未分組(它仍屬別組)= 畫面上像資料被吃掉。 */
export function detachFromGroups(wl: Watchlist, code: string, slot: number): Watchlist {
  return {
    codes: reinsertIntoCodes(wl, code, slot),
    groups: wl.groups.map((g) => ({ ...g, codes: g.codes.filter((c) => c !== code) })),
  };
}

/** 未分組內排序:群組成員在 `codes` 的相對位置不動。 */
export function reorderUngrouped(wl: Watchlist, code: string, slot: number): Watchlist {
  return { ...wl, codes: reinsertIntoCodes(wl, code, slot) };
}

/** 只從該組移除;code 留在自選 → 不屬任何組時自動回未分組。 */
export function removeFromGroup(wl: Watchlist, code: string, group: string): Watchlist {
  return {
    ...wl,
    groups: wl.groups.map((g) =>
      g.name === group ? { ...g, codes: g.codes.filter((c) => c !== code) } : g,
    ),
  };
}

/** 空白名 / 重名 → 原物件(對應後端 BAD_GROUP,呼叫端零 PUT 直接顯示文案)。 */
export function addGroup(wl: Watchlist, name: string): Watchlist {
  const trimmed = name.trim();
  if (trimmed === "" || wl.groups.some((g) => g.name === trimmed)) return wl;
  return { ...wl, groups: [...wl.groups, { name: trimmed, codes: [] }] };
}

/** 空白名 / 撞既有名 → 原物件(改成自己原本的名字也算撞,同樣零 PUT)。 */
export function renameGroup(wl: Watchlist, from: string, to: string): Watchlist {
  const trimmed = to.trim();
  if (trimmed === "" || wl.groups.some((g) => g.name === trimmed)) return wl;
  return { ...wl, groups: wl.groups.map((g) => (g.name === from ? { ...g, name: trimmed } : g)) };
}

/** 只刪群組:成員的 code 留在 `codes` → 自動回到未分組。 */
export function deleteGroup(wl: Watchlist, name: string): Watchlist {
  return { ...wl, groups: wl.groups.filter((g) => g.name !== name) };
}
