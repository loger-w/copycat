/** 損益曲線 SVG 純計算(無 React 依賴,§3 慣例:純渲染抽 lib)。x = 毫點,y = NTD。 */

export type CurvePoint = [number, number];

export interface ScaleBox {
  width: number;
  height: number;
  pad: number;
}

export interface Scales {
  x: (millipts: number) => number;
  y: (ntd: number) => number;
}

/** x 軸 domain 單一來源:buildScales 與 invertX 皆由此取值,單邊修改不破互逆(DR-2)。 */
export function xDomain(curve: CurvePoint[]): { minX: number; spanX: number } {
  const xs = curve.map(([x]) => x);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  return { minX, spanX: maxX - minX || 1 };
}

export function buildScales(curve: CurvePoint[], box: ScaleBox): Scales {
  const { minX, spanX } = xDomain(curve);
  const yMax = Math.max(...curve.map(([, y]) => Math.abs(y)), 1);
  const innerW = box.width - box.pad * 2;
  const innerH = box.height - box.pad * 2;
  return {
    x: (v) => box.pad + ((v - minX) / spanX) * innerW,
    y: (v) => box.pad + ((yMax - v) / (2 * yMax)) * innerH,
  };
}

/** SVG 使用者座標 px → 毫點;pad 外或反解值超出 domain → null(SC-3)。 */
export function invertX(px: number, curve: CurvePoint[], box: ScaleBox): number | null {
  if (px < box.pad || px > box.width - box.pad) return null;
  const { minX, spanX } = xDomain(curve);
  const innerW = box.width - box.pad * 2;
  const v = minX + ((px - box.pad) / innerW) * spanX;
  if (v < minX || v > minX + spanX) return null;
  return v;
}

/** 線段線性插值(後端 payoff.interp_pnl 同語意);範圍外 → null。 */
export function interpCurve(curve: CurvePoint[], xMillipts: number): number | null {
  for (let i = 1; i < curve.length; i++) {
    const p0 = curve[i - 1];
    const p1 = curve[i];
    if (p0 === undefined || p1 === undefined) continue;
    const [x0, y0] = p0;
    const [x1, y1] = p1;
    if (x0 <= xMillipts && xMillipts <= x1) {
      if (x1 === x0) return y0;
      return y0 + ((y1 - y0) * (xMillipts - x0)) / (x1 - x0);
    }
  }
  return null;
}

/** 依零交叉切段:每段全 ≥0 或全 ≤0,交叉點插值補入兩側。 */
export function splitAtZero(curve: CurvePoint[]): CurvePoint[][] {
  if (curve.length === 0) return [];
  const segments: CurvePoint[][] = [];
  let current: CurvePoint[] = [curve[0] as CurvePoint];
  for (let i = 1; i < curve.length; i++) {
    const prev = curve[i - 1] as CurvePoint;
    const next = curve[i] as CurvePoint;
    if (prev[1] * next[1] < 0) {
      const t = -prev[1] / (next[1] - prev[1]);
      const zero: CurvePoint = [prev[0] + t * (next[0] - prev[0]), 0];
      current.push(zero);
      segments.push(current);
      current = [zero];
    }
    current.push(next);
  }
  segments.push(current);
  return segments;
}

function fmt(n: number): string {
  return String(Math.round(n * 10) / 10);
}

/** M/L 折線 path;curvePath 與 areaPaths 共用同一格式化來源。 */
function linePath(points: CurvePoint[], scales: Scales): string {
  return points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${fmt(scales.x(x))},${fmt(scales.y(y))}`)
    .join(" ");
}

export function curvePath(curve: CurvePoint[], scales: Scales): string {
  return linePath(curve, scales);
}

/** 獲利(y>0)與虧損(y<0)分區面積 path,各自閉合到零線。 */
export function areaPaths(
  curve: CurvePoint[],
  scales: Scales,
): { profit: string; loss: string } {
  const zeroY = fmt(scales.y(0));
  const build = (segs: CurvePoint[][]): string =>
    segs
      .map((seg) => {
        const line = linePath(seg, scales);
        const lastX = fmt(scales.x((seg[seg.length - 1] as CurvePoint)[0]));
        const firstX = fmt(scales.x((seg[0] as CurvePoint)[0]));
        return `${line} L${lastX},${zeroY} L${firstX},${zeroY} Z`;
      })
      .join(" ");
  const segments = splitAtZero(curve);
  return {
    profit: build(segments.filter((seg) => seg.some(([, y]) => y > 0))),
    loss: build(segments.filter((seg) => seg.some(([, y]) => y < 0))),
  };
}
