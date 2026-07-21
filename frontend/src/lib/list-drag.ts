/** 自選清單拖拉排序純函數(原生 pointer events,不引 dnd-kit;design v4 §3)。 */

export function reorder<T>(list: T[], from: number, to: number): T[] {
  const clampedTo = Math.max(0, Math.min(list.length - 1, to));
  if (from === clampedTo || from < 0 || from >= list.length) return [...list];
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(clampedTo, 0, item as T);
  return next;
}

/** pointer 相對清單頂端的 y → 目標插入 index(過半行高進位)。 */
export function insertIndexFromPointer(y: number, rowHeight: number, count: number): number {
  const idx = Math.round(y / rowHeight);
  return Math.max(0, Math.min(count - 1, idx));
}
