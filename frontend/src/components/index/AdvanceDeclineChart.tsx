/** 騰落線(market-overview R2 SC-4):當日每分鐘的漲跌家數差,上市 + 上櫃合計一條。
 *
 *  net = (漲停 + 上漲) − (下跌 + 跌停) —— 標準騰落定義把漲停計入上漲(brainstorm Q6)。
 *  後端存的是十桶全量,net 這條定義留在前端一行運算,改定義不動後端。
 *
 *  dataviz:單序列 → **不放 legend**(標題「騰落線」即名),只在右端直接標末值,
 *  不逐點標數字;格線退隱、0 軸比格線明顯一級(騰落線的意義完全繫於零線的哪一側)。
 *  x 用**固定域**(與同頁分時圖同一組 `X_START_MIN`/`X_END_MIN` 常數),盤中累積時
 *  已畫出的點不會隨新資料橫向漂移。 */
import { X_END_MIN, X_START_MIN } from "@/lib/index-chart-svg";
import { pts } from "@/lib/svg-points";
import { HOUR_TICKS } from "@/lib/time-labels";
import { cn } from "@/lib/utils";
import type { BreadthPoint } from "@/types";

const SIZE = { width: 640, height: 150 };
const PAD_TOP = 10;
const PAD_BOTTOM = 14; // 底部留給 X 軸時刻標籤
const LABEL_W = 46; // 右端末值標註的保留寬度,線不畫進來

/** `HHMM` → 台北分鐘數;非四位數字 / 分鐘不合法 / 域外(0901–1330)一律 `null`。
 *
 *  後端已用 `index_engine.minute_key` 把域外鍵擋掉,這裡是第二道:落檔 restore 的
 *  舊格式、未來新增的定盤時刻(14:30)一旦混進來,靜默畫在圖上比丟掉危險得多。 */
function minuteOf(t: string): number | null {
  if (!/^\d{4}$/.test(t)) return null;
  const hh = Number(t.slice(0, 2));
  const mm = Number(t.slice(2));
  if (mm > 59) return null;
  const minute = hh * 60 + mm;
  if (minute <= X_START_MIN || minute > X_END_MIN) return null;
  return minute;
}

function netOf(p: BreadthPoint): number {
  const [tlu, tu, , td, tld] = p.twse;
  const [olu, ou, , od, old] = p.tpex;
  return tlu + tu + olu + ou - (td + tld + od + old);
}

function toX(minute: number): number {
  const w = SIZE.width - LABEL_W;
  return ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * w;
}

function signed(n: number): string {
  return n > 0 ? `+${n}` : String(n);
}

export function AdvanceDeclineChart({ series }: { series: BreadthPoint[] }) {
  const points = series
    .map((p) => {
      const minute = minuteOf(p.t);
      return minute === null ? null : { minute, net: netOf(p) };
    })
    .filter((v): v is { minute: number; net: number } => v !== null);

  return (
    <div data-testid="adl-chart" className="flex flex-col gap-1">
      <span className="text-sm text-ink">騰落線</span>
      {points.length === 0 ? (
        <p className="py-8 text-center text-sm text-ink-muted">盤中累積後顯示</p>
      ) : (
        <Plot points={points} />
      )}
    </div>
  );
}

function Plot({ points }: { points: { minute: number; net: number }[] }) {
  // 對稱域:零線恆在正中,「多空哪邊佔優」用一眼的高低就讀得出來,不必先找基準線。
  // 下限 1 避免全零時 span=0 除零。
  const span = Math.max(1, ...points.map((p) => Math.abs(p.net)));
  const plotH = SIZE.height - PAD_TOP - PAD_BOTTOM;
  const toY = (net: number): number => PAD_TOP + ((span - net) / (2 * span)) * plotH;
  const zeroY = toY(0);
  const line = points.map((p) => ({ x: toX(p.minute), y: toY(p.net) }));
  const last = points[points.length - 1]!;
  const lastPt = line[line.length - 1]!;

  return (
    <svg
      viewBox={`0 0 ${SIZE.width} ${SIZE.height}`}
      className="w-full"
      role="img"
      aria-label="全市場騰落線"
    >
      {HOUR_TICKS.map(({ minute, label }) => (
        <g key={minute}>
          <line
            x1={toX(minute)}
            x2={toX(minute)}
            y1={PAD_TOP}
            y2={SIZE.height - PAD_BOTTOM}
            className="stroke-line"
            strokeWidth={0.4}
          />
          <text
            x={toX(minute) + 2}
            y={SIZE.height - 2}
            className="fill-ink-dim"
            fontSize="0.625rem"
          >
            {label}
          </text>
        </g>
      ))}
      {/* 0 軸:比格線粗一倍且用 ink-dim(格線是 line/0.4),多空分界不能跟刻度線同重量 */}
      <line
        data-testid="adl-zero"
        x1={0}
        x2={SIZE.width - LABEL_W}
        y1={zeroY}
        y2={zeroY}
        className="stroke-ink-dim"
        strokeWidth={0.8}
      />
      <text x={2} y={zeroY - 2} className="fill-ink-dim" fontSize="0.625rem">
        0
      </text>
      <text x={2} y={PAD_TOP + 8} className="fill-ink-dim" fontSize="0.625rem">
        {signed(span)}
      </text>
      <text x={2} y={SIZE.height - PAD_BOTTOM - 2} className="fill-ink-dim" fontSize="0.625rem">
        {signed(-span)}
      </text>
      <polyline
        data-testid="adl-line"
        points={pts(line)}
        fill="none"
        className="stroke-accent"
        strokeWidth={2}
      />
      <text
        data-testid="adl-last"
        x={lastPt.x + 4}
        y={Math.min(Math.max(lastPt.y + 3, PAD_TOP + 8), SIZE.height - PAD_BOTTOM)}
        className={cn(
          "font-mono",
          // SVG `<text>` 吃的是 fill,不是 color —— `text-bull` 在這裡是 no-op(MarketChart 同慣例)
          last.net > 0 ? "fill-bull" : last.net < 0 ? "fill-bear" : "fill-ink-dim",
        )}
        fontSize="0.6875rem"
      >
        {signed(last.net)}
      </text>
    </svg>
  );
}

export default AdvanceDeclineChart;
