import { useMemo, useState } from "react";

import { MarketChart } from "@/components/index/MarketChart";
import { RadioPills } from "@/components/ui/RadioPills";
import type { ChartToggles } from "@/hooks/useChartToggles";
import { useContainerSize } from "@/hooks/useContainerSize";
import type { IndexSeries } from "@/hooks/useIndexStream";
import { chgPct, fmtPct } from "@/lib/format";
import { buildOverlayGeometry, X_END_MIN, X_START_MIN } from "@/lib/index-chart-svg";
import {
  PANE_FRAMES,
  paneCandleBox,
  paneIntradayBox,
  paneSvgHeight,
  paneUnitScale,
  svgFontRem,
} from "@/lib/pane-frame";
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

/** 標的列**顯示層**的三個選項(A11Y-p2-1)。第三顆是「台指期」這個位置本身,不是它
 *  當下指到的哪一款期指 —— 直接拿 `futKey` 當 value 的話,換商品會連 React 的 `key` 一起
 *  換掉,整顆 label + input 被卸載重建、焦點掉回 body,而畫面看起來毫無變化。
 *  `FUT ↔ futKey` 的映射留在呼叫端(選中 = `isFut`,與改前的 `active={isFut}` 等價)。 */
type TargetKey = "TWSE" | "OTC" | "FUT";

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

/** 「櫃買快照源(MIS)中斷」的判定寬限:加權要先累積這麼多分鐘格,才開始認為
 *  「櫃買一格都沒有」是壞掉而不是還沒輪到(MIS 是 5s poll,加權是 TC4 push)。
 *  2 格 ≈ 開盤後兩分鐘 —— 比 poll 週期大兩個量級,又短到整天空的日子一眼看得到。 */
const OTC_DEAD_MIN_TWSE_MINUTES = 2;

/** 櫃買快照源是否已中斷(N108)。
 *
 *  MIS(`copycat/server/mis.py`)是非契約的公開端點,壞掉時 `_mis_loop` 拿到 None 就
 *  跳過 —— 從開盤即死透的日子 otc 的 `p`/`ref` 恆 null、`minutes` 恆空,而 **otc 不吃
 *  `stale`**(watchdog 只看加權 TC4 推播),畫面因此是一條沒有任何說明的空線。
 *
 *  判別子刻意**不看時鐘**(不引進交易時段 / 日曆判斷,也就沒有跨日、假日、盤前的誤報):
 *  拿同一條 WS 上的加權當對照 —— 加權都已經有分鐘格了而櫃買一格都沒有,只可能是櫃買
 *  這一路壞了。盤前兩者皆空 → 恆 false。 */
function otcSourceDead(twse: IndexSeries | null, otc: IndexSeries | null): boolean {
  if (otc === null || twse === null) return false;
  if (otc.p !== null || Object.keys(otc.minutes).length > 0) return false;
  return Object.keys(twse.minutes).length >= OTC_DEAD_MIN_TWSE_MINUTES;
}

function fmt(millipts: number): string {
  const v = millipts / 1000;
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

function toX(minute: number): number {
  return ((minute - X_START_MIN) / (X_END_MIN - X_START_MIN)) * SIZE.width;
}

/** 三態 pill class(選中 / 停用 / 一般)。**單一來源**:標的列 / 期貨商品列 / 週期列
 *  三組 radiogroup 的 label 與仍是 toggle 的「重疊」鈕共用同一份 —— 兩種元素的外觀必須
 *  逐值相同,分兩份寫的失效樣態是只有其中一顆的 padding / 顏色漂掉,而畫面照畫。
 *
 *  `@max-[26.5rem]:px-1`:窄 pane(1536 兩欄態 ~346px)下 17 顆週期鈕會折成 3 行、
 *  吃掉 50px 圖高;收 padding 後估算 ≈ 561px / 346 = 1.6 行 → 2 行。
 *  門檻用 **rem 不用 px** —— 鈕的文字與 padding 全是 rem,rem 門檻讓「塞不塞得下」這個
 *  條件對 root font-size 不變。**本專案 root 目前恆 16px(無縮放 media query),
 *  26.5rem = 424px / 41rem = 656px**;真環境量測(2026-08-21):1536 pane 350 → 降級
 *  (右欄 473 亦降級);1920 pane 466 → 不 compact 但週期列仍 2 行(48px)、右欄 627 →
 *  七欄;2560 pane 658、右欄 883 → 九欄。
 *  標的列的 3–6 顆鈕同縮:只省空間、不改行數,少一個 prop(D3)。 */
function pillClass(item: { disabled?: boolean }, checked: boolean): string {
  return cn(
    "rounded border px-2 py-0.5 text-xs @max-[26.5rem]:px-1",
    item.disabled
      ? "cursor-not-allowed border-line text-ink-muted opacity-40"
      : checked
        ? "border-accent text-accent"
        : "border-line text-ink-dim hover:text-ink",
  );
}

/** 真開關(「重疊」)。三組單選 pill 已改 `RadioPills`(a11y 批 D2'),此元件只剩
 *  toggle 語意 —— `aria-pressed` 是對的(W2)。 */
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
      className={pillClass({ disabled }, active)}
    >
      {label}
    </button>
  );
}

/** 重疊圖兩條線的樣式與標籤,依**輸入序**(0=加權、1=櫃買)。
 *  查表一律用 `line.index`(callee 帶回的原始位置)**不用 `g.lines` 的陣列位置**:
 *  `buildOverlayGeometry` 會濾掉 ref 為 null/0 的腿,單邊缺值時位置會塌陷一格
 *  → 僅剩的櫃買線畫成加權色、標成「加權」(N262,2026-08-24 修)。 */
const OVERLAY_LINES = [
  { color: "stroke-profit", label: "加權" },
  { color: "stroke-idx-otc", label: "櫃買" },
] as const;

/** 加權 vs 櫃買 相對昨收 % 疊線(既有能力;SC-7 保留,計算與外觀不變)。
 *
 *  `height` 的單位是 **viewBox 單位**(caller 已扣 chrome、已用 `paneSvgHeight` 反解);
 *  未給 → 220(= 改版前的固定 `SIZE`)。`toX` 只吃寬,不隨高改。
 *  `unitScale` = `paneUnitScale` 算出的字級補償:抵銷 svg 等比縮放,未給 → 1(WL-3)。
 *  **本卡是等比縮放與這條補償僅存的讀者** —— 分時態 2026-08-17、K 線態 2026-08-21 先後
 *  改走 1:1 px,縮放比恆 1,補償無用武之地(見 `paneIntradayBox` / `paneCandleBox`)。
 *  它留在這裡是因為 viewBox 寬寫死 640(幾何以 `SIZE.width` 為座標系),不是量測值。 */
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
  // **單一來源**:幾何、viewBox、刻度線三處吃同一個 `size`。改版前幾何那支自己現寫
  // 一份 `{ width: SIZE.width, height }` 字面量,與這裡的 `size` 是兩份 —— 哪天有人只
  // 改其中一份(例如把寬度改吃量測值),圖框與線的座標系就靜默錯開,而 svg 不會報錯、
  // 線照畫,只有位置歪掉。`useMemo([height])` 是為了讓它能安全地當下面那支的 dep
  // (render 內現建的物件當 dep 等於沒 memo,同 L363-366 那條警告)。
  const size = useMemo(() => ({ width: SIZE.width, height }), [height]);
  const font = svgFontRem(0.625, unitScale);
  // **必經 useMemo**:重疊開著時,App 層那五條流(期貨 coalesce 0.1s = 10 Hz 最兇)
  // 每推一次就重繪整棵樹 —— 加權/櫃買一個分鐘點都沒動,兩條全窗 series 的 pct → x/y
  // 換算照樣重跑一遍。症狀只有 CPU 知道,線照畫值照對,沒有任何行為測試會紅。
  // deps 拆成**欄位級**四項 + `size`(自身已 memo 於 `height`);`unitScale` / `font`
  // 只進字級不進幾何,不是輸入。
  const g = useMemo(
    () =>
      buildOverlayGeometry(
        [
          { minutes: twse.minutes, ref: twse.ref },
          { minutes: otc.minutes, ref: otc.ref },
        ],
        size,
      ),
    [twse.minutes, twse.ref, otc.minutes, otc.ref, size],
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
        {g.lines.map((l) => {
          const style = OVERLAY_LINES[l.index];
          if (style === undefined) return null; // 幾何腿數多於樣式表 = 呼叫端漏更新,寧可不畫
          return (
            <g key={style.label}>
              <polyline points={pts(l.pts)} fill="none" className={style.color} strokeWidth={1.4} />
              {l.pts.length > 0 ? (
                <text
                  x={Math.min(l.pts[l.pts.length - 1]!.x + 4, SIZE.width - 28)}
                  y={l.pts[l.pts.length - 1]!.y + 3}
                  className={style.color.replace("stroke-", "fill-")}
                  fontSize={font}
                >
                  {style.label}
                </text>
              ) : null}
            </g>
          );
        })}
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

  const otcDead = otcSourceDead(twse, otc);
  const isFut = marketKey === "TXF" || marketKey === "MXF" || marketKey === "TMF";
  // 標的列顯示層的選中值(見 `TargetKey`)。寫成 narrowing 而不是 `isFut ? "FUT" : marketKey`
  // —— TS 不會用布林變數去窄化 `marketKey`,那樣要多一個 cast。
  const targetKey: TargetKey = marketKey === "TWSE" || marketKey === "OTC" ? marketKey : "FUT";
  const series = marketKey === "TWSE" ? twse : marketKey === "OTC" ? otc : null;
  const futState = isFut ? (futures?.[marketKey] ?? null) : null;

  // 量的是「圖還剩多少空間」而不是「圖現在多高」——ref 掛在高度由外層 flex 指派的
  // wrapper 上(useContainerSize 呼叫端契約 2),且該 wrapper 三種模式都在(契約 1)。
  const [sizeRef, size] = useContainerSize<HTMLDivElement>();
  // 物件而非布林:同一個判別子既要選 chrome 參數表、又要餵 OverlayCard 兩條非 null
  // series,拆成布林會讓 JSX 那側得再判一次 null(或掛 `!` 賭它)。
  const overlayPair =
    overlay && mode === "intraday" && twse !== null && otc !== null ? { twse, otc } : null;
  // 三態各走各的換算,**只有重疊態還是等比縮放**:
  //   重疊 → `PANE_FRAMES.overlay` 反解成 viewBox 單位 + `unitScale` 字級補償
  //   分時(2026-08-17)/ K 線(2026-08-21)→ 1:1 px box,縮放比恆 1,無補償可言
  // `frame` 因此只在重疊態非 null。另外兩態讓它落回某一格 frame 會算出一個沒人讀、
  // 但看起來很正常的高度 —— 哪天有人把它接回去,症狀是圖高差一個 `vbW / svgW` 倍率
  // 而畫面照畫。
  const paneIntraday = overlayPair === null && mode === "intraday";
  const paneCandle = overlayPair === null && mode !== "intraday";
  const frame = overlayPair !== null ? PANE_FRAMES.overlay : null;
  // `svgHeight` / `unitScale` 自此**只餵 OverlayCard**(K 線態 2026-08-21 起改吃 candleBox)
  const svgHeight = frame === null ? undefined : paneSvgHeight(size, frame);
  // 量不到 → 1 = 改版前的字級(W-10:fallback 態的外觀逐值不變)
  const unitScale = frame === null ? 1 : (paneUnitScale(size, frame) ?? 1);
  // **必經 useMemo**:物件 prop 每 render 新 identity 會一路打穿下游的 memo,而症狀
  // 只是 hover 掉幀、沒有任何測試會紅。deps 拆成兩個純量 —— `size` 物件本身每次量測
  // 都是新的,拿它當 dep 等於沒 memo。
  // 量不到 → `undefined`:讓 core 走它自己的 800×260 預設,而不是傳一組 0(svg 不報錯,
  // 純粹畫不出來)。
  const intradayBox = useMemo(() => {
    if (!paneIntraday) return undefined;
    const box = paneIntradayBox({ width: size.width, height: size.height });
    return box.usable ? { width: box.width, height: box.height } : undefined;
  }, [paneIntraday, size.width, size.height]);
  // 同 `intradayBox` 的形狀與理由(memo / 純量 deps / 量不到傳 undefined)。K 線態的
  // fallback 是 `CandleChart` 自有的 1400×578(W-3),不是 0。
  const candleBox = useMemo(() => {
    if (!paneCandle) return undefined;
    const box = paneCandleBox({ width: size.width, height: size.height });
    return box.usable ? { width: box.width, height: box.height } : undefined;
  }, [paneCandle, size.width, size.height]);

  return (
    <section
      data-testid={`market-pane-${paneId}`}
      role="group"
      aria-label={paneId === "left" ? "左圖" : "右圖"}
      // `min-h-0` **無條件**:pane 必須永遠可縮,地板由「顯式 min-height」提供 ——
      // 雙圖 grid 的 `min-h-80` 與本檔 figure 的 `min-h-48`,不是靠 pane 自己不可縮。
      // ⚠ 這裡不可寫成 `@[1050px]:min-h-0`:container query 的門檻量的是**左欄**
      // (左欄自己掛了 `@container`,是最近的 container 祖先),兩欄態左欄只有 630–930px
      // → 門檻永不成立 → pane 退回 grid item 的 `min-height: auto`,軌高被撐到 ≥ pane
      // 內容高(figure 內的 svg 畫的是「當前高」,不會自己縮)→ 雙圖 grid 到 min-h-80
      // 地板後軌道照樣撐開 → 溢出蓋家數帶。
      // 兩種版面下的收斂:兩欄態 pane 縮到軌高,figure / wrapper 跟著縮 → 下一輪量測
      // 讓 svg 跟著矮;單欄態 pane 由內容驅動高,沿 `wrapper − 2` 收斂到 figure 的
      // `min-h-48` 地板(每輪只會變矮不會回彈,不形成迴圈)。
      // `@container`:週期列的 `@max-[26.5rem]:` 門檻要量的是 **pane 自己的寬**。
      // 不掛的話最近的 container 祖先是左欄(兩欄態 630–930px),門檻永不成立。
      // 副作用已查(D4):pane 子樹(MarketChart / CandleChart / StockIntradayChart /
      // ChartReadout)沒有任何 absolute / fixed 定位子孫會被新的 containing block 接走,
      // 也沒有別的 `@[…]` 變體會改量到誰;pane 所在 grid 軌是 `minmax(0,1fr)`,
      // inline-size containment 不改軌算。
      className="@container flex min-h-0 min-w-0 flex-col gap-3"
    >
      {/* 標的列(SC-2)。a11y 批 D2':**拆兩個 radiogroup** —— 「標的」與「期貨商品」
          語意不同(選了台指期才談大/小/微台),合成一群的話「恰一顆 checked」不成立
          (台指期與大台會同時亮)。第三顆的 value 固定 `"FUT"`(A11Y-p2-1,見 `TargetKey`)
          —— 期貨態時 `marketKey` 恆等於 `futKey`(`selectFut` 會同步兩者),所以 checked
          判定與原本的 `active={isFut}` 等價,但換商品不再重掛那顆 radio。 */}
      <div className="flex flex-wrap items-center gap-3">
        <RadioPills<TargetKey>
          ariaLabel="標的"
          className="flex gap-1"
          value={targetKey}
          onChange={(next) => selectKey(next === "FUT" ? futKey : next)}
          items={[
            { value: "TWSE", label: "加權" },
            { value: "OTC", label: "櫃買" },
            { value: "FUT", label: "台指期" },
          ]}
          pillClass={pillClass}
        />
        {isFut ? (
          <RadioPills<FutKey>
            ariaLabel="期貨商品"
            className="flex gap-1"
            value={futKey}
            onChange={selectFut}
            items={FUT_LABELS.map(([id, label]) => ({ value: id, label }))}
            pillClass={pillClass}
          />
        ) : null}
      </div>

      {/* 週期列(SC-3);櫃買的日/週/月 disabled(SC-6)。
          窄 pane 下與 pill 的 px-1 一起收(gap 省 16×0.5 = 8px),同一個 26.5rem 門檻。
          「重疊」是**真開關**(W2 保留 aria-pressed),不進 radio 集合 —— 走 `trailing`
          插槽掛回同一個容器內的原位置,DOM 順序與折行行為零變(D1'')。 */}
      <RadioPills<MarketMode>
        ariaLabel="週期"
        className="flex flex-wrap items-center gap-1 @max-[26.5rem]:gap-0.5"
        value={mode}
        onChange={selectMode}
        items={MARKET_MODES.map(([id, label]) => ({
          value: id,
          label,
          disabled: !isModeAvailable(marketKey, id),
        }))}
        pillClass={pillClass}
        trailing={
          stores.overlay !== undefined && mode === "intraday" && !isFut ? (
            <span className="ml-2">
              <Btn label="重疊" active={overlay} onClick={toggleOverlay} />
            </span>
          ) : null
        }
      />

      {/* 2026-08-16 一頁總覽:圖高改吃**容器剩餘高**(`flex-1`),不再是「寬 × 220/640」
          的固定比例 —— 改版前不 flex-1 是因為整頁可捲、撐滿會把家數帶擠出視窗;現在
          左欄自己就是有界的 flex 欄,撐滿正是要的。`min-h-48`(12rem,amendment r3 自
          15rem 下修)是**唯一**一條 min-height:堆疊 / 內容決定高的模式下給 figure 一個
          地板,量測 → 內容 → 量測才會收斂;同時掛 `min-h-0` 會把地板消掉,退回「圖可以
          被壓成 0 高」。12rem 的算式:192 − chrome 62(border 2 + p-4 32 + caption 20)
          = wrapper 130 → 分時圖 1:1 高 = floor(130 − 26 頂列) − 2 = 102,仍高於
          `paneIntradayBox` 的 96 地板(地板一旦吃到,圖高就與容器脫鉤)。
          **頂列 26 沒隨換元件變**:`IntradayChartCore` 的 readout 列與舊 toggle 列是
          同一組 class(`h-[1.375rem]` + `mb-1`),所以這條算式逐值沿用。 */}
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
          {/* 櫃買專屬(N108):`stale` 是加權 watchdog 的旗標,櫃買沒有等價物 ——
              沒有這一句時「MIS 整天死透」與「櫃買今天沒動」在畫面上完全同形。 */}
          {marketKey === "OTC" && otcDead ? (
            <span className="text-xs text-ink-dim">櫃買快照源中斷</span>
          ) : null}
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
              // 兩態各一個 prop,單位相同(px 1:1)但 chrome 扣法不同(K 線 100/34、
              // 分時 26/0)。同一個 prop 帶兩態時,改其中一態的換算會靜默改到另一態。
              candleBox={candleBox}
              intradayBox={intradayBox}
            />
          )}
        </div>
      </figure>
    </section>
  );
}

export default MarketPane;
