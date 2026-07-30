/** 自選清單拖拉排序純函數(原生 pointer events,不引 dnd-kit;design v4 §3)。 */

export function reorder<T>(list: T[], from: number, to: number): T[] {
  const clampedTo = Math.max(0, Math.min(list.length - 1, to));
  if (from === clampedTo || from < 0 || from >= list.length) return [...list];
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(clampedTo, 0, item as T);
  return next;
}

/** pointer 相對清單頂端的 y → 目標插入 index(過半行高進位)。
 *
 *  上界是 `count − 1`(同組重排:只能換到既有位置)。跨組落點請用
 *  `dropTargetFromPointer`,它的上界是 `count`(要能 append 到尾)—— 兩者語意刻意不同。 */
export function insertIndexFromPointer(y: number, rowHeight: number, count: number): number {
  const idx = Math.round(y / rowHeight);
  return Math.max(0, Math.min(count - 1, idx));
}

/** 一個群組 section 的落點幾何(round4 項 2)。**每次 pointermove 重算** ——
 *  只在 pointerdown 算一次的話,側欄捲動、錯誤文案出現消失都會讓 rect 失效,
 *  而失效的樣態是「拖到別組結果落錯組」= 靜默改資料。 */
export interface DropZone {
  group: string;
  /** section 外框上下緣(含標題列;折疊時只有標題列) */
  top: number;
  bottom: number;
  /** 股票列第一列的上緣。**折疊時不使用**(見 `collapsed`) */
  listTop: number;
  count: number;
  /** 折疊中 → 一律 append 到尾,不走 rowHeight 換算 */
  collapsed: boolean;
}

const EDGE_TOLERANCE = 16;

/** pointer 座標 → 落點群組 + 插入 index;不接受的落點回 `null`(呼叫端據此整個作廢)。
 *
 *  **x 必須驗**:只看 y 的話,在中間 K 線圖上放開只要 y 恰好與某群組同高就會把股票搬組,
 *  而「移動」語意是不可逆的(來源會被移除),舊行為最壞只是同組換位。
 *  y 落在 zone 之間的縫隙(標題列之間)→ 取最近的 zone,拖到縫隙不失敗。 */
export function dropTargetFromPointer(
  p: { x: number; y: number },
  zones: readonly DropZone[],
  rowHeight: number,
  bounds: { left: number; right: number },
): { group: string; index: number } | null {
  if (zones.length === 0) return null;
  if (p.x < bounds.left - EDGE_TOLERANCE || p.x > bounds.right + EDGE_TOLERANCE) return null;
  let best: DropZone | null = null;
  let bestDist = Infinity;
  for (const z of zones) {
    const dist = p.y < z.top ? z.top - p.y : p.y >= z.bottom ? p.y - z.bottom + 1 : 0;
    if (dist < bestDist) {
      best = z;
      bestDist = dist;
    }
  }
  if (best === null) return null;
  const index = best.collapsed
    ? best.count
    : Math.max(0, Math.min(best.count, Math.round((p.y - best.listTop) / rowHeight)));
  return { group: best.group, index };
}

/** 把 `code` 從 `fromGroup` 移到 `toGroup` 的 `index`(`from === to` 時等價於同組重排)。
 *
 *  **移動語意**(user 2026-07-30 拍板):來源組移除。其他群組完全不動 —— 一檔多組的
 *  其他歸屬照樣保留,要改那些走每列的 `⊞` 面板。 */
export function moveCode<G extends { name: string; codes: string[] }>(
  groups: readonly G[],
  code: string,
  fromGroup: string,
  toGroup: string,
  index: number,
): G[] {
  return groups.map((g) => {
    if (g.name === toGroup) {
      // 先 filter 再插入:`from === to` 時這一步同時完成移除與插入
      const base = g.codes.filter((c) => c !== code);
      const at = Math.max(0, Math.min(base.length, index));
      return { ...g, codes: [...base.slice(0, at), code, ...base.slice(at)] };
    }
    if (g.name === fromGroup) return { ...g, codes: g.codes.filter((c) => c !== code) };
    return g;
  });
}
