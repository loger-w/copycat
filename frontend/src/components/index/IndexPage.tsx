import { useState } from "react";

import { MarketChart } from "@/components/index/MarketChart";
import { useChartToggles } from "@/hooks/useChartToggles";
import type { IndexSeries, TxfQuote } from "@/hooks/useIndexStream";
import { buildOverlayGeometry, X_END_MIN, X_START_MIN } from "@/lib/index-chart-svg";
import { pts } from "@/lib/svg-points";
import {
  coerceMode,
  isMarketKey,
  isMarketMode,
  isModeAvailable,
  MARKET_MODES,
  type MarketKey,
  type MarketMode,
} from "@/lib/timeframe";
import { cn } from "@/lib/utils";

const KEY_STORE = "copycat-market-key";
const MODE_STORE = "copycat-market-tf";
const OVERLAY_STORE = "copycat-index-mode";
/** **不與期貨 tab 的 `copycat-fut-product` 共用**:共用會讓大盤頁選微台時,期貨 tab
 *  與右欄閃電梯的武裝語境一起被換掉(白名單 W-13;review P1-7)。 */
const FUT_STORE = "copycat-market-fut";

const SIZE = { width: 640, height: 220 };
const X_LABELS = [540, 600, 660, 720, 780].map((m) => ({
  minute: m,
  label: `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`,
}));

type FutKey = "TXF" | "MXF" | "TMF";
const FUT_LABELS: readonly (readonly [FutKey, string])[] = [
  ["TXF", "大台"],
  ["MXF", "小台"],
  ["TMF", "微台"],
];
const NAMES: Record<MarketKey, string> = {
  TWSE: "加權指數",
  OTC: "櫃買指數",
  TXF: "台指期(大台)",
  MXF: "台指期(小台)",
  TMF: "台指期(微台)",
};

/** 期貨引擎的 per-product 狀態(App 層 `useFuturesStream` 下傳;頁面不自建 WS —— D-3)。 */
export interface FuturesProductState {
  p: number | null;
  ref: number | null;
}

function fmt(millipts: number): string {
  const v = millipts / 1000;
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

function toX(minute: number): number {
  return ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * SIZE.width;
}

function Btn({
  label,
  active,
  disabled,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      aria-disabled={disabled ? "true" : undefined}
      className={cn(
        "rounded border px-2 py-0.5 text-xs",
        disabled
          ? "cursor-not-allowed border-line text-ink-muted opacity-40"
          : active
            ? "border-accent text-accent"
            : "border-line text-ink-dim hover:text-ink",
      )}
    >
      {label}
    </button>
  );
}

/** 加權 vs 櫃買 相對昨收 % 疊線(既有能力;SC-7 保留,計算與外觀不變)。 */
function OverlayCard({ twse, otc }: { twse: IndexSeries; otc: IndexSeries }) {
  const g = buildOverlayGeometry(
    [
      { minutes: twse.minutes, ref: twse.ref },
      { minutes: otc.minutes, ref: otc.ref },
    ],
    SIZE,
  );
  const colors = ["stroke-profit", "stroke-idx-otc"];
  const labels = ["加權", "櫃買"];
  return (
    <figure className="rounded-md border border-line bg-surface p-4">
      <div className="flex items-baseline gap-4">
        <h3 className="text-sm font-bold text-ink">加權 vs 櫃買(相對昨收 %)</h3>
        <span className="font-mono text-xs text-profit">─ 加權</span>
        <span className="font-mono text-xs text-idx-otc">─ 櫃買</span>
      </div>
      <svg
        viewBox={`0 0 ${SIZE.width} ${SIZE.height}`}
        className="mt-2 w-full"
        role="img"
        aria-label="指數重疊走勢"
      >
        {X_LABELS.map(({ minute, label }) => (
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
          y1={g.zeroY}
          y2={g.zeroY}
          className="stroke-line"
          strokeDasharray="2 3"
          strokeWidth={1}
        />
        {g.lines.map((l, i) => (
          <g key={labels[i]}>
            <polyline points={pts(l.pts)} fill="none" className={colors[i]} strokeWidth={1.4} />
            {l.pts.length > 0 ? (
              <text
                x={Math.min(l.pts[l.pts.length - 1]!.x + 4, SIZE.width - 28)}
                y={l.pts[l.pts.length - 1]!.y + 3}
                className={colors[i]!.replace("stroke-", "fill-")}
                fontSize="0.625rem"
              >
                {labels[i]}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
    </figure>
  );
}

function Quote({
  p,
  ref_,
  high,
  low,
}: {
  p: number | null;
  ref_: number | null;
  high?: number | null;
  low?: number | null;
}) {
  const chgPts = p !== null && ref_ !== null ? (p - ref_) / 1000 : null;
  const chgPct = p !== null && ref_ ? ((p - ref_) / ref_) * 100 : null;
  return (
    <>
      <span className="font-mono text-2xl text-ink">{p !== null ? fmt(p) : "-"}</span>
      {chgPts !== null && chgPct !== null ? (
        <span
          className={cn(
            "font-mono text-sm",
            chgPts > 0 ? "text-bull" : chgPts < 0 ? "text-bear" : "text-ink",
          )}
        >
          {`${chgPts > 0 ? "+" : ""}${chgPts.toFixed(2)} (${chgPct > 0 ? "+" : ""}${chgPct.toFixed(2)}%)`}
        </span>
      ) : null}
      <span className="font-mono text-xs text-ink-dim">
        {`高 ${high != null ? fmt(high) : "-"} 低 ${low != null ? fmt(low) : "-"} 昨收 ${
          ref_ !== null ? fmt(ref_) : "-"
        }`}
      </span>
    </>
  );
}

interface Props {
  twse: IndexSeries | null;
  otc: IndexSeries | null;
  txf: TxfQuote | null;
  /** 期貨三檔即時狀態(App 層 `useFuturesStream` 下傳;review P1-6)。 */
  futures?: Record<string, FuturesProductState> | null;
}

export function IndexPage({ twse, otc, txf, futures }: Props) {
  const [futKey, setFutKey] = useState<FutKey>(() => {
    const saved = window.localStorage.getItem(FUT_STORE);
    return saved === "MXF" || saved === "TMF" ? saved : "TXF";
  });
  const [marketKey, setMarketKeyState] = useState<MarketKey>(() => {
    const saved = window.localStorage.getItem(KEY_STORE);
    return isMarketKey(saved) ? saved : "TWSE";
  });
  // mount 初始化也要過 coerceMode:兩個 key 各自持久化,重載後可能復原成
  // 「櫃買 + 日K」這種非法組合(review P1-5)
  const [mode, setModeState] = useState<MarketMode>(() => {
    const savedMode = window.localStorage.getItem(MODE_STORE);
    const savedKey = window.localStorage.getItem(KEY_STORE);
    return coerceMode(
      isMarketKey(savedKey) ? savedKey : "TWSE",
      isMarketMode(savedMode) ? savedMode : "intraday",
    );
  });
  // 舊值 "overlay" / "side" 讀時遷移為布林(§4 backward compat)
  const [overlay, setOverlay] = useState<boolean>(
    () => window.localStorage.getItem(OVERLAY_STORE) === "overlay",
  );
  const { toggles, set } = useChartToggles();

  function selectKey(next: MarketKey): void {
    setMarketKeyState(next);
    window.localStorage.setItem(KEY_STORE, next);
    const coerced = coerceMode(next, mode);
    if (coerced !== mode) {
      setModeState(coerced);
      window.localStorage.setItem(MODE_STORE, coerced);
    }
  }

  function selectMode(next: MarketMode): void {
    setModeState(next);
    window.localStorage.setItem(MODE_STORE, next);
  }

  function selectFut(next: FutKey): void {
    setFutKey(next);
    window.localStorage.setItem(FUT_STORE, next);
    selectKey(next);
  }

  function toggleOverlay(): void {
    const next = !overlay;
    setOverlay(next);
    window.localStorage.setItem(OVERLAY_STORE, next ? "overlay" : "side");
  }

  const isFut = marketKey === "TXF" || marketKey === "MXF" || marketKey === "TMF";
  const series = marketKey === "TWSE" ? twse : marketKey === "OTC" ? otc : null;
  const futState = isFut ? (futures?.[marketKey] ?? null) : null;
  const basis = txf !== null && twse?.p != null ? (txf.p - twse.p) / 1000 : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      {/* 標的列(SC-2) */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          <Btn label="加權" active={marketKey === "TWSE"} onClick={() => selectKey("TWSE")} />
          <Btn label="櫃買" active={marketKey === "OTC"} onClick={() => selectKey("OTC")} />
          <Btn label="台指期" active={isFut} onClick={() => selectKey(futKey)} />
        </div>
        {isFut ? (
          <div className="flex gap-1">
            {FUT_LABELS.map(([id, label]) => (
              <Btn key={id} label={label} active={marketKey === id} onClick={() => selectFut(id)} />
            ))}
          </div>
        ) : null}
        <span data-testid="basis-row" className="font-mono text-xs text-ink-dim">
          台指期 <span className="text-ink">{txf !== null ? fmt(txf.p) : "-"}</span>{" "}
          <span
            className={cn(
              basis !== null && basis > 0
                ? "text-bull"
                : basis !== null && basis < 0
                  ? "text-bear"
                  : "text-ink-dim",
            )}
          >
            {basis !== null ? `價差 ${basis > 0 ? "+" : ""}${basis.toFixed(2)}` : "價差 -"}
          </span>
          {txf?.time ? <span className="ml-2 text-ink-dim">至 {txf.time.slice(0, 5)}</span> : null}
        </span>
      </div>

      {/* 週期列(SC-3);櫃買的日/週/月 disabled(SC-6) */}
      <div className="flex flex-wrap items-center gap-1">
        {MARKET_MODES.map(([id, label]) => (
          <Btn
            key={id}
            label={label}
            active={mode === id}
            disabled={!isModeAvailable(marketKey, id)}
            onClick={() => selectMode(id)}
          />
        ))}
        {mode === "intraday" && !isFut ? (
          <span className="ml-2">
            <Btn label="重疊" active={overlay} onClick={toggleOverlay} />
          </span>
        ) : null}
      </div>

      <figure className="flex min-h-0 flex-1 flex-col rounded-md border border-line bg-surface p-4">
        <figcaption className="flex flex-wrap items-baseline gap-3">
          <h3 className="text-sm font-bold text-ink">{NAMES[marketKey]}</h3>
          {isFut ? (
            <Quote p={futState?.p ?? null} ref_={futState?.ref ?? null} />
          ) : (
            <Quote
              p={series?.p ?? null}
              ref_={series?.ref ?? null}
              high={series?.high ?? null}
              low={series?.low ?? null}
            />
          )}
          {series?.stale ? <span className="text-xs text-ink-dim">資料中斷</span> : null}
        </figcaption>
        <div className="mt-2 flex min-h-0 flex-1 flex-col">
          {overlay && mode === "intraday" && twse !== null && otc !== null ? (
            <OverlayCard twse={twse} otc={otc} />
          ) : (
            <MarketChart
              marketKey={marketKey}
              mode={mode}
              name={NAMES[marketKey]}
              series={series}
              showBb={toggles.bb}
              onToggleBb={(v) => set("bb", v)}
            />
          )}
        </div>
      </figure>
    </div>
  );
}

export default IndexPage;
