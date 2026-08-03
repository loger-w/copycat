/** 自選清單拖拉排序純函數(原生 pointer events,不引 dnd-kit;design v4 §3)。 */

/** 一個群組 section 的落點幾何(round4 項 2)。**每次 pointermove 重算** ——
 *  只在 pointerdown 算一次的話,側欄捲動、錯誤文案出現消失都會讓 rect 失效,
 *  而失效的樣態是「拖到別組結果落錯組」= 靜默改資料。 */
export interface DropZone {
  /** `null` = 未分組區塊(round5 §🔴-8) */
  group: string | null;
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
): { group: string | null; index: number } | null {
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
