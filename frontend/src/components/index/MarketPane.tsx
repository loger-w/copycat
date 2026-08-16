import { useState } from "react";

import { MarketChart } from "@/components/index/MarketChart";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { useContainerSize } from "@/hooks/useContainerSize";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { chgPct, fmtPct } from "@/lib/format";
import { buildOverlayGeometry, X_END_MIN, X_START_MIN } from "@/lib/index-chart-svg";
import { PANE_FRAMES, paneSvgHeight, paneUnitScale, svgFontRem } from "@/lib/pane-frame";
import { pts } from "@/lib/svg-points";
import { HOUR_TICKS } from "@/lib/time-labels";
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

const SIZE = { width: 640, height: 220 };

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

/** 一個 pane 的 localStorage key 組。**每個 pane 一組**,不共用 —— 兩張圖各自記自己的
 *  標的 / 週期 / 期指商品,共用等於右圖跟著左圖動。
 *
 *  `overlay` 是 optional:重疊圖畫的固定是「加權 vs 櫃買」,右 pane 也開的話畫面會出現
 *  兩張一模一樣的圖(連 `aria-label` 都重複)→ 不傳 = 不渲染重疊鈕、不建 overlay state。 */
export interface PaneStores {
  key: string;
  mode: string;
  fut: string;
  overlay?: string;
}

/** 期貨引擎的 per-product 狀態(App 層 `useFuturesStream` 下傳;頁面不自建 WS —— D-3)。
 *
 *  **刻意不叫 `FuturesProductState`**:`@/types` 已有同名的 13 欄完整型別,同名兩份會讓
 *  import 來源變成得逐檔確認的事。這裡只吃現價 / 昨收兩欄。 */
export interface PaneFutState {
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

/** 重疊圖兩條線的樣式與標籤,依**輸入序**(0=加權、1=櫃買)。
 *  ⚠ `buildOverlayGeometry` 會 filter 掉 ref 為 null/0 的 series —— 單邊 ref 缺值時
 *  `g.lines` 的 index 與這裡錯位(僅剩的櫃買線會標成加權)。既存行為,與 hoist 前
 *  逐值相同;修正記於 docs/next-time.md。 */
const OVERLAY_LINES = [
  { color: "stroke-profit", label: "加權" },
  { color: "stroke-idx-otc", label: "櫃買" },
] as const;

/** 加權 vs 櫃買 相對昨收 % 疊線(既有能力;SC-7 保留,計算與外觀不變)。
 *
 *  `height` 同 `MarketChart.height` 的口徑:**viewBox 單位**,caller 已扣 chrome、
 *  已反解;未給 → 220(= 改版前的固定 `SIZE`)。`toX` 只吃寬,不隨高改。
 *  `unitScale` 同 `MarketChart.unitScale`:抵銷 svg 等比縮放,未給 → 1(WL-3)。 */
function OverlayCard({
  twse,
  otc,
  height = SIZE.height,
  unitScale = 1,
}: {
  twse: IndexSeries;
  otc: IndexSeries;
  height?: number;
  unitScale?: number;
}) {
  const size = { width: SIZE.width, height };
  const font = svgFontRem(0.625, unitScale);
  const g = buildOverlayGeometry(
    [
      { minutes: twse.minutes, ref: twse.ref },
      { minutes: otc.minutes, ref: otc.ref },
    ],
    size,
  );
  return (
    <figure className="rounded-md border border-line bg-surface p-4">
      <div className="flex items-baseline gap-4">
        <h3 className="text-sm font-bold text-ink">加權 vs 櫃買(相對昨收 %)</h3>
        <span className="font-mono text-xs text-profit">─ 加權</span>
        <span className="font-mono text-xs text-idx-otc">─ 櫃買</span>
      </div>
      <svg
        viewBox={`0 0 ${size.width} ${size.height}`}
        className="mt-2 w-full"
        role="img"
        aria-label="指數重疊走勢"
      >
        {HOUR_TICKS.map(({ minute, label }) => (
          <g key={minute}>
            <line
              x1={toX(minute)}
              x2={toX(minute)}
              y1={0}
              y2={size.height - 12}
              className="stroke-line"
              strokeWidth={0.4}
            />
            <text
              x={toX(minute) + 2}
              y={size.height - 2}
              className="fill-ink-dim"
              fontSize={font}
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
          <g key={OVERLAY_LINES[i]!.label}>
            <polyline
              points={pts(l.pts)}
              fill="none"
              className={OVERLAY_LINES[i]!.color}
              strokeWidth={1.4}
            />
            {l.pts.length > 0 ? (
              <text
                x={Math.min(l.pts[l.pts.length - 1]!.x + 4, SIZE.width - 28)}
                y={l.pts[l.pts.length - 1]!.y + 3}
                className={OVERLAY_LINES[i]!.color.replace("stroke-", "fill-")}
                fontSize={font}
              >
                {OVERLAY_LINES[i]!.label}
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
  const pctChg = p !== null && ref_ ? chgPct(p, ref_) : null;
  return (
    <>
      <span className="font-mono text-2xl text-ink">{p !== null ? fmt(p) : "-"}</span>
      {chgPts !== null && pctChg !== null ? (
        <span
          className={cn(
            "font-mono text-sm",
            chgPts > 0 ? "text-bull" : chgPts < 0 ? "text-bear" : "text-ink",
          )}
        >
          {`${chgPts > 0 ? "+" : ""}${chgPts.toFixed(2)} (${fmtPct(pctChg)})`}
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
  /** 版面位置。用途是 `data-testid="market-pane-<paneId>"` 與根節點的 `aria-label`
   *  —— 兩個 pane 的按鈕文字完全相同,測試沒有這個錨點就只能裸 `getByRole` 撞
   *  ambiguous,a11y 樹同理(兩 pane 選同標的同週期時無法區分,review F3)。 */
  paneId: "left" | "right";
  twse: IndexSeries | null;
  otc: IndexSeries | null;
  /** 期貨三檔即時狀態(App 層 `useFuturesStream` 下傳;review P1-6)。 */
  futures?: Record<string, PaneFutState> | null;
  stores: PaneStores;
  /** 無存檔時的標的。**兩處 fallback 都吃它**(見下方 state initializer)。 */
  defaultKey: MarketKey;
  /** `useChartToggles` 由 IndexPage 上提後下傳 —— 兩 pane 共用同一份 bb 開關
   *  (與改版前的全域單開關行為一致)。 */
  toggles: ChartToggles;
  onToggle: (key: keyof ChartToggles, value: boolean) => void;
  /** 使用者是否正看著台股綜合 tab。純轉發給 `MarketChart` 的分 K 輪詢 gate
   *  (review round-2 XR-4);未給時預設 true。 */
  active?: boolean;
}

/** 台股綜合的單張指數圖(標的列 + 週期列 + 圖)。
 *
 *  基差列**不在這裡** —— 它與 pane 選什麼標的無關(永遠是台指期 vs 加權),
 *  放進來會在雙 pane 版面下出現兩份相同數字。 */
export function MarketPane({
  paneId,
  twse,
  otc,
  futures,
  stores,
  defaultKey,
  toggles,
  onToggle,
  active = true,
}: Props) {
  const [futKey, setFutKey] = useState<FutKey>(() => {
    const saved = window.localStorage.getItem(stores.fut);
    return saved === "MXF" || saved === "TMF" ? saved : "TXF";
  });
  const [marketKey, setMarketKeyState] = useState<MarketKey>(() => {
    const saved = window.localStorage.getItem(stores.key);
    return isMarketKey(saved) ? saved : defaultKey;
  });
  // mount 初始化也要過 coerceMode:兩個 key 各自持久化,重載後可能復原成
  // 「櫃買 + 日K」這種非法組合(review P1-5)。
  // **這裡的 savedKey fallback 必須跟上面同源 `defaultKey`**:寫死 "TWSE" 的話,
  // 右 pane(defaultKey=OTC)在「只有 mode 存檔、沒有 key 存檔」時會拿 TWSE 去
  // coerce → 保留 day,而實際標的是 OTC → 開場就停在一顆 disabled 的週期鈕上。
  const [mode, setModeState] = useState<MarketMode>(() => {
    const savedMode = window.localStorage.getItem(stores.mode);
    const savedKey = window.localStorage.getItem(stores.key);
    return coerceMode(
      isMarketKey(savedKey) ? savedKey : defaultKey,
      isMarketMode(savedMode) ? savedMode : "intraday",
    );
  });
  // 舊值 "overlay" / "side" 讀時遷移為布林(§4 backward compat);無 overlay key = 恆關
  const [overlay, setOverlay] = useState<boolean>(() =>
    stores.overlay === undefined
      ? false
      : window.localStorage.getItem(stores.overlay) === "overlay",
  );

  function selectKey(next: MarketKey): void {
    setMarketKeyState(next);
    window.localStorage.setItem(stores.key, next);
    const coerced = coerceMode(next, mode);
    if (coerced !== mode) setModeState(coerced);
    // **寫入不可條件化**:mount initializer 的 coerce 結果沒回寫 storage,storage 可能留著
    // 已被畫面 coerce 掉的殘值(key=OTC + mode=day)。若這裡也只在 coerced !== mode 時寫,
    // 一次 no-op coerce 的切換(切回加權)就只寫 key → storage 湊成 TWSE+day 這組
    // 「合法但使用者沒選過」的組合,下次重載直接跳日K。任何標的切換都沖成當下有效值。
    window.localStorage.setItem(stores.mode, coerced);
  }

  function selectMode(next: MarketMode): void {
    setModeState(next);
    window.localStorage.setItem(stores.mode, next);
  }

  function selectFut(next: FutKey): void {
    setFutKey(next);
    window.localStorage.setItem(stores.fut, next);
    selectKey(next);
  }

  function toggleOverlay(): void {
    if (stores.overlay === undefined) return;
    const next = !overlay;
    setOverlay(next);
    window.localStorage.setItem(stores.overlay, next ? "overlay" : "side");
  }

  const isFut = marketKey === "TXF" || marketKey === "MXF" || marketKey === "TMF";
  const series = marketKey === "TWSE" ? twse : marketKey === "OTC" ? otc : null;
  const futState = isFut ? (futures?.[marketKey] ?? null) : null;

  // 量的是「圖還剩多少空間」而不是「圖現在多高」——ref 掛在高度由外層 flex 指派的
  // wrapper 上(useContainerSize 呼叫端契約 2),且該 wrapper 三種模式都在(契約 1)。
  const [sizeRef, size] = useContainerSize<HTMLDivElement>();
  // 物件而非布林:同一個判別子既要選 chrome 參數表、又要餵 OverlayCard 兩條非 null
  // series,拆成布林會讓 JSX 那側得再判一次 null(或掛 `!` 賭它)。
  const overlayPair =
    overlay && mode === "intraday" && twse !== null && otc !== null ? { twse, otc } : null;
  const frame =
    overlayPair !== null
      ? PANE_FRAMES.overlay
      : mode === "intraday"
        ? PANE_FRAMES.intraday
        : PANE_FRAMES.candle;
  const svgHeight = paneSvgHeight(size, frame);
  // 量不到 → 1 = 改版前的字級(W-10:fallback 態的外觀逐值不變)
  const unitScale = paneUnitScale(size, frame) ?? 1;

  return (
    <section
      data-testid={`market-pane-${paneId}`}
      role="group"
      aria-label={paneId === "left" ? "左圖" : "右圖"}
      // `min-h-0` 條件化(amendment r3):無條件掛著時 pane 會被壓到低於自身內容,
      // 圖卡(overflow visible)直接溢出壓在家數帶上,而不是把左欄撐高讓主 grid 出捲軸。
      // ⚠ 這個門檻量的是**左欄**(最近的 `@container` 祖先)而不是 IndexPage root ——
      // 兩欄態下左欄約是容器寬的 6 成,故實務上只有超寬螢幕的 pane 真的可縮。窄於此
      // 由雙圖 grid 的 `min-h-80` 與本檔 figure 的 `min-h-48` 兩層地板定高,超出的部分
      // 走主 grid 的 `overflow-y-auto`(§7 edge 2 逃生口);兩種路徑都不會溢出重疊。
      className="flex min-w-0 flex-col gap-3 @[1050px]:min-h-0"
    >
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
        {stores.overlay !== undefined && mode === "intraday" && !isFut ? (
          <span className="ml-2">
            <Btn label="重疊" active={overlay} onClick={toggleOverlay} />
          </span>
        ) : null}
      </div>

      {/* 2026-08-16 一頁總覽:圖高改吃**容器剩餘高**(`flex-1`),不再是「寬 × 220/640」
          的固定比例 —— 改版前不 flex-1 是因為整頁可捲、撐滿會把家數帶擠出視窗;現在
          左欄自己就是有界的 flex 欄,撐滿正是要的。`min-h-48`(12rem,amendment r3 自
          15rem 下修)是**唯一**一條 min-height:堆疊 / 內容決定高的模式下給 figure 一個
          地板,量測 → 內容 → 量測才會收斂;同時掛 `min-h-0` 會把地板消掉,退回「圖可以
          被壓成 0 高」。12rem 的算式:192 − chrome 62(border 2 + p-4 32 + caption 20)
          = wrapper 130 → svg render 128 − 26 toggle 列 = 102,仍高於 `paneSvgHeight`
          的 96 地板(地板一旦吃到,反解出的高就與容器脫鉤)。 */}
      <figure className="flex min-h-48 flex-1 flex-col rounded-md border border-line bg-surface p-4">
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
        {/* 量測用的恆存 wrapper:重疊 / 分時 / K 線三種模式都掛在它底下(ref 只掛其中
            一支的話,切模式那一幀會量到 0×0 而 hook 不再重跑)。 */}
        <div ref={sizeRef} className="mt-2 flex min-h-0 flex-1 flex-col">
          {overlayPair !== null ? (
            <OverlayCard
              twse={overlayPair.twse}
              otc={overlayPair.otc}
              height={svgHeight}
              unitScale={unitScale}
            />
          ) : (
            <MarketChart
              marketKey={marketKey}
              mode={mode}
              name={NAMES[marketKey]}
              series={series}
              toggles={toggles}
              onToggle={onToggle}
              active={active}
              height={svgHeight}
              unitScale={unitScale}
            />
          )}
        </div>
      </figure>
    </section>
  );
}

export default MarketPane;
