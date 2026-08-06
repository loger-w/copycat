import { useMemo } from "react";

import { CandleChart } from "@/components/stock/CandleChart";
import { useMarketBars } from "@/hooks/useMarketBars";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { aggregateBars } from "@/lib/candle";
import { buildIndexGeometry, X_END_MIN, X_START_MIN } from "@/lib/index-chart-svg";
import { pts } from "@/lib/svg-points";
import { HOUR_TICKS } from "@/lib/time-labels";
import { type MarketKey, type MarketMode, marketMinutesOf } from "@/lib/timeframe";

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

function IntradayChart({ name, s }: { name: string; s: IndexSeries }) {
  const g = buildIndexGeometry({ minutes: s.minutes, ref: s.ref, high: s.high, low: s.low }, SIZE);
  return (
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
          <text x={toX(minute) + 2} y={SIZE.height - 2} className="fill-ink-dim" fontSize="0.625rem">
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
          x={2}
          y={Math.min(Math.max(t.y - 2, 8), SIZE.height - 14)}
          className="fill-ink-dim"
          fontSize="0.625rem"
        >
          {fmt(t.priceMilli)}
        </text>
      ))}
      {g.line.length > 0 ? (
        <polyline points={pts(g.line)} fill="none" className="stroke-accent" strokeWidth={1.4} />
      ) : null}
    </svg>
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
  showBb: boolean;
  onToggleBb: (v: boolean) => void;
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
  showBb,
  onToggleBb,
  active = true,
}: Props) {
  const { data, isPending, isError, error } = useMarketBars(marketKey, mode, active);
  const minutes = marketMinutesOf(mode);
  const bars = useMemo(
    () => aggregateBars(data?.bars ?? [], minutes),
    [data?.bars, minutes],
  );

  if (mode === "intraday") {
    if (series === null) {
      return <p className="py-10 text-center text-sm text-ink-muted">等待指數資料…</p>;
    }
    return <IntradayChart name={name} s={series} />;
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
        showBb={showBb}
        onToggleBb={onToggleBb}
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
