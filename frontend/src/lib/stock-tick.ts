/** 台股 tick 檔位(毫元整數運算;對齊後端 market.py 表)+ 閃電梯 buildLadder。
 *
 * buildLadder 為固定界錨定(design v2 R5):rows = 上界..下界全域合法 tick,
 * center 只影響 isCenter / dimmed,不影響 rows 集合(避免逐 tick 窗漂移)。
 */

// [下限毫元, tick 毫元];由高往低查
const TICK_TABLE: [number, number][] = [
  [1_000_000, 5_000],
  [500_000, 1_000],
  [100_000, 500],
  [50_000, 100],
  [10_000, 50],
  [0, 10],
];

export function tickOf(priceMilli: number): number {
  for (const [floor, tick] of TICK_TABLE) {
    if (priceMilli >= floor) return tick;
  }
  return 10;
}

export function stepUp(priceMilli: number): number {
  return priceMilli + tickOf(priceMilli);
}

/** 往下一檔;跨級距時用「下方價格帶」的 tick(100 元 → 99.9,不是 99.5)。 */
export function stepDown(priceMilli: number): number {
  const below = priceMilli - 1;
  return priceMilli - tickOf(below);
}

export function snapDown(priceMilli: number): number {
  const tick = tickOf(priceMilli);
  const snapped = Math.floor(priceMilli / tick) * tick;
  return snapped;
}

export function snapUp(priceMilli: number): number {
  const tick = tickOf(priceMilli);
  return Math.ceil(priceMilli / tick) * tick;
}

export interface LadderRow {
  priceMilli: number;
  bidQty: number;
  askQty: number;
  isCenter: boolean;
  dimmed: boolean;
}

interface LadderInput {
  center: number | null;
  ref: number | null;
  upper: number | null;
  lower: number | null;
  book: { bids: [number, number][]; asks: [number, number][] } | null;
}

export function buildLadder(input: LadderInput): LadderRow[] {
  const anchor = input.center ?? input.ref;
  if (anchor === null) return [];
  // 界:漲跌停;缺 → 假想界 round-then-snap(design R7)
  const upperBound =
    input.upper ?? (input.ref !== null ? snapDown(Math.round(input.ref * 1.1)) : null);
  const lowerBound =
    input.lower ?? (input.ref !== null ? snapUp(Math.round(input.ref * 0.9)) : null);
  if (upperBound === null || lowerBound === null || upperBound < lowerBound) return [];

  const bidMap = new Map(input.book?.bids ?? []);
  const askMap = new Map(input.book?.asks ?? []);

  const rows: LadderRow[] = [];
  let bestDist = Infinity;
  let bestIdx = -1;
  for (let p = upperBound; p >= lowerBound; p = stepDown(p)) {
    const dist = Math.abs(p - anchor);
    if (dist < bestDist) {
      bestDist = dist;
      bestIdx = rows.length;
    }
    rows.push({
      priceMilli: p,
      bidQty: bidMap.get(p) ?? 0,
      askQty: askMap.get(p) ?? 0,
      isCenter: false,
      dimmed: Math.abs(p - anchor) / anchor > 0.05,
    });
  }
  if (bestIdx >= 0) rows[bestIdx]!.isCenter = true;
  return rows;
}

/** snap 到**最近**合法 tick(`snapDown` / `snapUp` 是方向性的,顯示用刻度要取最近)。
 *
 * 跨級距的邊界:先用該價位自己的 tick 算上下兩個候選,再比距離。上界候選可能跨進
 * 更粗的級距(如 99.9 → 100),此時它本身仍是合法檔位(100 在 100-500 帶是 0.5 的倍數),
 * 不必再校正。 */
export function snapNearest(priceMilli: number): number {
  const down = snapDown(priceMilli);
  if (down === priceMilli) return priceMilli;
  const up = down + tickOf(priceMilli);
  return priceMilli - down <= up - priceMilli ? down : up;
}

/** 依該價位帶的 tick 級距決定小數位,再輸出 —— 顯示的價位要「到得了」。
 *
 * tick 5 元 / 1 元 → 0 位(1000 元的股票不會出現 1003);tick 0.5 / 0.1 元 → 1 位
 * (100 元的股票不會出現 102.4);tick 0.05 / 0.01 元 → 2 位。
 * 小數位由 **snap 後**的價位帶決定:跨級距時(如 99.95 → 100)級距會變粗。 */
export function fmtTickPrice(priceMilli: number): string {
  const p = snapNearest(priceMilli);
  const tick = tickOf(p);
  const decimals = tick >= 1_000 ? 0 : tick >= 100 ? 1 : 2;
  return (p / 1000).toFixed(decimals);
}
