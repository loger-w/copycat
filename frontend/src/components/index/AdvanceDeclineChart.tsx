/** 騰落線(market-overview R2 SC-4):當日每分鐘的漲跌家數差,上市 + 上櫃合計一條。
 *
 *  net = (漲停 + 上漲) − (下跌 + 跌停) —— 標準騰落定義把漲停計入上漲(brainstorm Q6)。
 *  後端存的是十桶全量,net 這條定義留在前端一行運算,改定義不動後端。
 *
 *  dataviz:單序列 → **不放 legend**(標題「騰落線」即名),只在右端直接標末值,
 *  不逐點標數字;格線退隱、0 軸比格線明顯一級(騰落線的意義完全繫於零線的哪一側)。
 *  x 用**固定域**(與同頁分時圖同一組 `X_START_MIN`/`X_END_MIN` 常數),盤中累積時
 *  已畫出的點不會隨新資料橫向漂移。
 *
 *  **紅綠雙色**(2026-08-16):0 軸之上 bull 紅、之下 bear 綠,線與面積都是「整條畫兩份 +
 *  clipPath 切上下」——與 `StockIntradayChart` 的昨收上下同一套手法。單色 accent 讀不出
 *  多空側,而騰落線的全部意義就是那一側。 */
import { useId } from "react";

import { useContainerSize } from "@/hooks/useContainerSize";
import { X_END_MIN, X_START_MIN } from "@/lib/index-chart-svg";
import { pts } from "@/lib/svg-points";
import { HOUR_TICKS } from "@/lib/time-labels";
import { cn, safeIdToken } from "@/lib/utils";
import type { BreadthPoint } from "@/types";

/** `width` 是恆定的 viewBox 寬(x 是固定時間域);`height` 只當**量測不可用時的
 *  fallback**(舊常數 150),量得到時 viewBox 高改由容器長寬比反推。 */
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

  // 高度由 CSS 決定(單欄態 `h-24`、兩欄態由外層 flex 指派,見下方 wrapper 註解),
  // viewBox 高一律反推自量到的長寬比 —— 改版前是「寬決定高」(寬 × 150/640),左欄
  // 930px 時這條線獨佔 218px 且與版面預算無關,一頁總覽吃不下。
  const [sizeRef, size] = useContainerSize<HTMLDivElement>();
  const vbHeight =
    size.width > 0 && size.height > 0
      ? Math.round((SIZE.width * size.height) / size.width)
      : SIZE.height;

  return (
    // `min-h-0 flex-1`:兩欄態時 IndexPage 的 section 拿到「左欄剩餘高的 5/11」,這一層
    // 要把它一路傳給下面那支量測 wrapper(可縮鏈斷一段,wrapper 就吃不到高)。單欄態
    // 的 section 是 auto 高、沒有自由空間,`flex-1` 於是等同內容高 = 改動前行為。
    <div data-testid="adl-chart" className="flex min-h-0 flex-1 flex-col gap-1">
      <span className="text-sm text-ink">騰落線</span>
      {/* 恆存 wrapper(空態文案也在其中):ref 只掛有資料那支的話,盤前那段量到 0×0
          而 hook 不會重跑 —— 第一筆資料進來時圖仍是 fallback 比例(useContainerSize
          呼叫端契約 1)。fallback 態由 svg `h-full w-full` + preserveAspectRatio 預設
          meet 縮放置中承接,不溢出(W-10)。

          高度是兩態的:**單欄態** `--idx-*` 未設 → `[flex:var(…,0 0 auto)]` 展開成
          `shrink-0` 的舊值,`h-24` 生效 = 改動前的 96px 逐值不變(SC-6 1366×768)。
          **兩欄態** IndexPage 左欄把 `--idx-adl-wrap-flex` 設成 `1 1 0%`,basis 0% 蓋掉
          `h-24`,實際高改由外層 flex 指派(= section 扣掉家數帶後的剩餘);地板改由
          `--idx-adl-min` 的 10rem 給 —— 它是 min-height 地板,不是指定高,分配權仍在
          外層 flex(useContainerSize 呼叫端契約 2:量測型 svg 的高必須由容器決定)。
          變數為何掛在左欄而不是這裡:最近的 `@container` 祖先是左欄,`@[1050px]:`
          寫在這一層量到的是左欄寬(630–930px)永不成立。 */}
      <div
        ref={sizeRef}
        className="flex h-24 items-center justify-center [flex:var(--idx-adl-wrap-flex,0_0_auto)] [min-height:var(--idx-adl-min,auto)]"
      >
        {points.length === 0 ? (
          <p className="text-sm text-ink-muted">盤中累積後顯示</p>
        ) : (
          <Plot points={points} height={vbHeight} />
        )}
      </div>
    </div>
  );
}

function Plot({
  points,
  height,
}: {
  points: { minute: number; net: number }[];
  height: number;
}) {
  // 對稱域:零線恆在正中,「多空哪邊佔優」用一眼的高低就讀得出來,不必先找基準線。
  // 下限 1 避免全零時 span=0 除零。
  const span = Math.max(1, ...points.map((p) => Math.abs(p.net)));
  const plotH = height - PAD_TOP - PAD_BOTTOM;
  const toY = (net: number): number => PAD_TOP + ((span - net) / (2 * span)) * plotH;
  const zeroY = toY(0);
  const line = points.map((p) => ({ x: toX(p.minute), y: toY(p.net) }));
  const last = points[points.length - 1]!;
  const lastPt = line[line.length - 1]!;
  // 面積 = 線 + 沿 0 軸回到起點的封閉多邊形;上下兩半各塗一次,可見範圍交給 clip
  const areaPolygon = `${pts(line)} ${lastPt.x.toFixed(1)},${zeroY.toFixed(1)} ${line[0]!.x.toFixed(1)},${zeroY.toFixed(1)}`;
  // useId 產出含非識別字元(React 19 為 «r0»),過濾後才拼進 url(#…)
  const uid = safeIdToken(useId());
  const clipAbove = `${uid}-above`;
  const clipBelow = `${uid}-below`;

  return (
    <svg
      viewBox={`0 0 ${SIZE.width} ${height}`}
      className="h-full w-full"
      role="img"
      aria-label="全市場騰落線"
    >
      <defs>
        <clipPath id={clipAbove}>
          <rect x={0} y={0} width={SIZE.width} height={Math.max(0, zeroY)} />
        </clipPath>
        <clipPath id={clipBelow}>
          <rect x={0} y={zeroY} width={SIZE.width} height={Math.max(0, height - zeroY)} />
        </clipPath>
      </defs>
      {HOUR_TICKS.map(({ minute, label }) => (
        <g key={minute}>
          <line
            x1={toX(minute)}
            x2={toX(minute)}
            y1={PAD_TOP}
            y2={height - PAD_BOTTOM}
            className="stroke-line"
            strokeWidth={0.4}
          />
          <text
            x={toX(minute) + 2}
            y={height - 2}
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
      <text x={2} y={height - PAD_BOTTOM - 2} className="fill-ink-dim" fontSize="0.625rem">
        {signed(-span)}
      </text>
      {/* 面積與線都是「整份畫兩遍 + clip 切上下」,**恆 render**:依 net 正負條件 render
          的話,全紅那天的下半段元素整個消失,錨點會隨資料時有時無。 */}
      <polygon
        data-testid="adl-area-up"
        points={areaPolygon}
        className="fill-bull"
        fillOpacity="0.15"
        clipPath={`url(#${clipAbove})`}
      />
      <polygon
        data-testid="adl-area-down"
        points={areaPolygon}
        className="fill-bear"
        fillOpacity="0.15"
        clipPath={`url(#${clipBelow})`}
      />
      <polyline
        data-testid="adl-line-up"
        points={pts(line)}
        fill="none"
        className="stroke-bull"
        strokeWidth={2}
        clipPath={`url(#${clipAbove})`}
      />
      <polyline
        data-testid="adl-line-down"
        points={pts(line)}
        fill="none"
        className="stroke-bear"
        strokeWidth={2}
        clipPath={`url(#${clipBelow})`}
      />
      <text
        data-testid="adl-last"
        x={lastPt.x + 4}
        y={Math.min(Math.max(lastPt.y + 3, PAD_TOP + 8), height - PAD_BOTTOM)}
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
