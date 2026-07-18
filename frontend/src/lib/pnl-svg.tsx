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

export function buildScales(curve: CurvePoint[], box: ScaleBox): Scales {
  const xs = curve.map(([x]) => x);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const spanX = maxX - minX || 1;
  const yMax = Math.max(...curve.map(([, y]) => Math.abs(y)), 1);
  const innerW = box.width - box.pad * 2;
  const innerH = box.height - box.pad * 2;
  return {
    x: (v) => box.pad + ((v - minX) / spanX) * innerW,
    y: (v) => box.pad + ((yMax - v) / (2 * yMax)) * innerH,
  };
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

export function curvePath(curve: CurvePoint[], scales: Scales): string {
  return curve
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${fmt(scales.x(x))},${fmt(scales.y(y))}`)
    .join(" ");
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
        const line = seg
          .map(([x, y], i) => `${i === 0 ? "M" : "L"}${fmt(scales.x(x))},${fmt(scales.y(y))}`)
          .join(" ");
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
