import { useMemo } from "react";

import { CandleChart } from "@/components/stock/CandleChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { useIndexOverlay } from "@/hooks/useIndexOverlay";
import { useMarketBars } from "@/hooks/useMarketBars";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { aggregateBars } from "@/lib/candle";
import {
  buildIndexGeometry,
  outOfDomainLevels,
  type RightEdgeLabel,
  rightEdgeLabels,
  X_END_MIN,
  X_START_MIN,
} from "@/lib/index-chart-svg";
import {
  LEVEL_FILL,
  LEVEL_STROKE,
  overlayLines,
  type StockOverlay,
} from "@/lib/stock-intraday-svg";
import { pts } from "@/lib/svg-points";
import { HOUR_TICKS } from "@/lib/time-labels";
import { type MarketKey, type MarketMode, marketMinutesOf } from "@/lib/timeframe";
import { cn } from "@/lib/utils";

const SIZE = { width: 640, height: 220 };

/** 資料源代碼 → 畫面文字。**必須逐一列舉**:未知碼原樣顯示(安全漂移),
 *  不要 fallback 成「TC4」之類的漂亮字 —— 那等於替沒把握的來源背書。 */
const SOURCE_TEXT: Record<string, string> = {
  tc4_dk: "達錢 4 日K",
  tc4_1k: "達錢 4 1分K",
  tc4_dk_1k_agg: "達錢 4 1分K 聚合(日K 無資料)",
  mis_poll_synth: "本機合成(MIS 5秒取樣)",
  unavailable: "取不到資料",
  none: "無資料源",
};

function fmt(millipts: number): string {
  const v = millipts / 1000;
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

function toX(minute: number): number {
  return ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * SIZE.width;
}

/** 右緣標籤文字。**唯一組法** —— 三種 kind 的字面(昨收 / `價位*` / `名稱 價位↑↓`)
 *  各自散在 JSX 裡的話,改一種語彙時另外兩種會靜默留在舊版。 */
function labelText(l: RightEdgeLabel): string {
  if (l.kind === "ref") return l.text;
  if (l.kind === "peg") {
    return `${l.level.toUpperCase()} ${fmt(l.priceMilli)}${l.dir === "up" ? "↑" : "↓"}`;
  }
  // CDP 系印「價位*」(`*` 是 CDP 記號,同個股語彙);MA 系名稱不可省 —— 兩條 MA 同色系
  return l.level === "ma5" || l.level === "ma20"
    ? `${l.level.toUpperCase()} ${fmt(l.priceMilli)}`
    : `${fmt(l.priceMilli)}*`;
}

function labelKey(l: RightEdgeLabel): string {
  return l.kind === "ref" ? "ref" : `${l.kind}-${l.level}`;
}

/** 右緣標籤帶的上下界。與 yTicks 的夾制同值(`[8, height − 14]`)—— 兩處各寫一次的話,
 *  同一個角落的兩種文字會夾制到不同位置。 */
const LABEL_BOUNDS = { top: 8, bottom: SIZE.height - 14 };

interface IntradayProps {
  name: string;
  s: IndexSeries;
  /** 疊線只做加權(櫃買無日 K 來源,已拍板跳過)—— 這個判別子同時決定 toggle 反灰文案 */
  marketKey: MarketKey;
  toggles: ChartToggles;
  onToggle: (key: keyof ChartToggles, value: boolean) => void;
  /** `/api/index/overlay` 的結果;未回 → null。查詢由 MarketChart 層無條件呼叫。 */
  overlay: StockOverlay | null;
  /** 疊線查詢失敗**且該查詢當前有效**(閘由 caller 併入,見那裡的 why)。 */
  overlayError: boolean;
}

function IntradayChart({
  name,
  s,
  marketKey,
  toggles,
  onToggle,
  overlay,
  overlayError,
}: IntradayProps) {
  const g = buildIndexGeometry({ minutes: s.minutes, ref: s.ref, high: s.high, low: s.low }, SIZE);
  const isTwse = marketKey === "TWSE";
  // 可用性同個股語意:資料未回前視為可用(不預先反灰);回了但該類 null / 請求失敗 → 反灰
  const cdpAvailable =
    isTwse && (overlayError ? false : overlay ? overlay.cdp !== null : true);
  const maAvailable =
    isTwse &&
    (overlayError ? false : overlay ? overlay.ma5 !== null || overlay.ma20 !== null : true);
  const offTitle = isTwse ? "無日線資料" : "櫃買無日 K 資料源";
  const toggleDefs: {
    key: keyof ChartToggles;
    label: string;
    available: boolean;
    title?: string;
  }[] = [
    // 指數沒有成交量 → 這條線是**分鐘收盤的算術平均**而不是 VWAP;title 就是用來區辨的
    { key: "vwap", label: "均價", available: true, title: "分鐘收盤均價(指數無成交量)" },
    { key: "cdp", label: "CDP", available: cdpAvailable, title: cdpAvailable ? undefined : offTitle },
    { key: "ma", label: "MA", available: maAvailable, title: maAvailable ? undefined : offTitle },
  ];

  const on = { cdp: toggles.cdp && cdpAvailable, ma: toggles.ma && maAvailable };
  const oLines = overlay !== null && isTwse ? overlayLines(overlay, g, on) : [];
  const pegs = overlay !== null && isTwse ? outOfDomainLevels(overlay, g, on) : [];
  const labels = rightEdgeLabels({
    ref: s.ref !== null ? { y: g.refY, text: `昨收 ${fmt(s.ref)}` } : null,
    oLines,
    outOfDomain: pegs,
    bounds: LABEL_BOUNDS,
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* toggle 列在 **svg 外**:圖的 a11y 錨點是 svg 本身(W-12),把鈕包進去會讓
          role="img" 的子樹含互動元素 */}
      <div className="mb-1 flex h-[1.375rem] items-center justify-end gap-1">
        {toggleDefs.map(({ key, label, available, title }) => (
          <button
            key={key}
            type="button"
            aria-pressed={toggles[key] && available}
            disabled={!available}
            title={title}
            onClick={() => onToggle(key, !toggles[key])}
            className={cn(
              "rounded border px-2 py-0.5 text-xs",
              toggles[key] && available ? "border-accent text-accent" : "border-line text-ink-dim",
              !available && "opacity-40",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <svg
        viewBox={`0 0 ${SIZE.width} ${SIZE.height}`}
        className="w-full"
        role="img"
        aria-label={`${name}分時走勢`}
      >
        {HOUR_TICKS.map(({ minute, label }) => (
          <g key={minute}>
            <line
              x1={toX(minute)}
              x2={toX(minute)}
              y1={0}
              y2={SIZE.height - 12}
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
        <line
          x1={0}
          x2={SIZE.width}
          y1={g.refY}
          y2={g.refY}
          className="stroke-line"
          strokeDasharray="2 3"
          strokeWidth={1}
        />
        {g.yTicks.map((t) => (
          <text
            key={t.priceMilli}
            data-testid="index-ytick"
            x={2}
            y={Math.min(Math.max(t.y - 2, 8), SIZE.height - 14)}
            className="fill-ink-dim"
            fontSize="0.625rem"
          >
            {fmt(t.priceMilli)}
          </text>
        ))}
        {/* 域內疊線;線體橫貫全寬(指數圖無 R_AXIS 保留帶) */}
        {oLines.map((l) => (
          // key 用 level 不用文字:兩條線同價時文字會撞 key
          <line
            key={`o-${l.level}`}
            x1={0}
            x2={SIZE.width}
            y1={l.y}
            y2={l.y}
            className={LEVEL_STROKE[l.level]}
            strokeDasharray="3 2"
            strokeWidth={0.8}
          />
        ))}
        {toggles.vwap && g.avgLine.length > 0 ? (
          <polyline points={pts(g.avgLine)} fill="none" className="stroke-ink" strokeWidth={1.2} />
        ) : null}
        {g.line.length > 0 ? (
          <polyline points={pts(g.line)} fill="none" className="stroke-accent" strokeWidth={1.4} />
        ) : null}
        {/* 右緣文字(昨收 + 疊線價位 + 域外掛牌)一律走 `rightEdgeLabels` 的 y */}
        {labels.map((l) => (
          <text
            key={labelKey(l)}
            x={SIZE.width - 2}
            y={l.y}
            dy="0.35em"
            textAnchor="end"
            className={cn(l.kind === "ref" ? "fill-ink-dim" : LEVEL_FILL[l.level], "stroke-surface")}
            strokeWidth={2}
            paintOrder="stroke"
            fontSize="0.5625rem"
          >
            {labelText(l)}
          </text>
        ))}
      </svg>
    </div>
  );
}

interface Props {
  /** **不能叫 `key`** —— React 會把它抽走當 reconciliation key,元件永遠收到 undefined
   *  且 TS 不報錯(review P0-3)。 */
  marketKey: MarketKey;
  mode: MarketMode;
  name: string;
  /** 分時模式的資料源(加權 / 櫃買);期指不支援分時,傳 null 即可。 */
  series: IndexSeries | null;
  /** 整包下傳而不是拆成 `showBb`/`onToggleBb`:分時態接下來要用到 vwap/cdp/ma 三個鍵,
   *  逐鍵開 props 等於每加一條疊線就改一次 caller 簽名。單一 caller(MarketPane)。 */
  toggles: ChartToggles;
  onToggle: (key: keyof ChartToggles, value: boolean) => void;
  /** 使用者是否正看著本頁 tab(App 的 `tab === "index"`)。分 K 的背景輪詢要靠這道
   *  gate 停(review round-2 XR-4);未給時預設 true。 */
  active?: boolean;
}

/** 大盤主圖:分時走勢 or 蠟燭圖 + 一行來源/涵蓋期間 meta(SC-4/5/6)。 */
export function MarketChart({
  marketKey,
  mode,
  name,
  series,
  toggles,
  onToggle,
  active = true,
}: Props) {
  const { data, isPending, isError, error } = useMarketBars(marketKey, mode, active);
  const minutes = marketMinutesOf(mode);
  const bars = useMemo(
    () => aggregateBars(data?.bars ?? [], minutes),
    [data?.bars, minutes],
  );
  // **無條件呼叫**(rules of hooks):閘全收在 enabled 裡 —— 只有加權分時、且至少一種
  // 疊線開著才打端點。櫃買無日 K 來源(已拍板跳過),K 線模式不畫疊線。
  const overlayGate = mode === "intraday" && marketKey === "TWSE" && (toggles.cdp || toggles.ma);
  const overlayQ = useIndexOverlay(overlayGate);

  if (mode === "intraday") {
    if (series === null) {
      return <p className="py-10 text-center text-sm text-ink-muted">等待指數資料…</p>;
    }
    return (
      <IntradayChart
        name={name}
        s={series}
        marketKey={marketKey}
        toggles={toggles}
        onToggle={onToggle}
        overlay={overlayQ.data ?? null}
        // **error 判定必須跟著 enabled 閘走**:TanStack 在 `enabled` 轉 false 時
        // 既不清 status 也不跑 refetchInterval —— 直接吃 `isError` 的話,「503 一次
        // + 使用者把 CDP/MA 都關掉」會讓兩顆鈕永遠 disabled(自己再也開不回來,
        // 只有重新整理解得開)。閘關著時本來就沒在請求,自然也沒有失敗可言。
        overlayError={overlayGate && overlayQ.isError}
      />
    );
  }

  if (data?.meta.refusal === "NO_HISTORICAL_SOURCE") {
    return (
      <div className="flex flex-1 items-center justify-center py-10">
        <p className="text-center text-sm text-ink-muted">
          達錢 4 未提供櫃買指數,無歷史 K 線資料源
        </p>
      </div>
    );
  }
  if (isError) {
    return (
      <p className="py-10 text-center text-sm text-bear">
        K 線載入失敗:{(error as Error | undefined)?.message ?? "UNKNOWN"}
      </p>
    );
  }
  if (isPending) {
    return <p className="py-10 text-center text-sm text-ink-muted">載入 K 線…</p>;
  }

  const meta = data.meta;
  const coverage =
    meta.coverage_from !== null && meta.coverage_to !== null
      ? `${meta.coverage_from} ~ ${meta.coverage_to}`
      : "無資料";
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <CandleChart
        key={`${marketKey}-${mode}`}
        bars={bars}
        initBars={minutes > 1 ? 240 : 120}
        showBb={toggles.bb}
        onToggleBb={(v) => onToggle("bb", v)}
        showVolume={meta.volume}
      />
      <p data-testid="market-meta" className="mt-1 font-mono text-xs text-ink-dim">
        {SOURCE_TEXT[meta.source] ?? meta.source} · {coverage}
        {meta.synth_since !== null ? ` · 自 ${meta.synth_since} 起` : ""}
        {meta.partial_last ? " · 最後一根未收盤" : ""}
      </p>
    </div>
  );
}
