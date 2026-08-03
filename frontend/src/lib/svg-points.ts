/** SVG polyline / polygon 的 `x,y` 點串:一律 toFixed(1),各圖精度須一致。 */
export function pts(line: { x: number; y: number }[]): string {
  return line.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}
