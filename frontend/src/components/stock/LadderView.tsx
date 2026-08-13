/** 價格梯 presentation(stkfut-contracts R2-4;自 PriceLadder 抽出,**行為零變更**)。
 *
 *  這一層只管「畫」與「捲」:標題列、武裝列骨架、檔位列 / 市價列 / 部位標記、點價與
 *  刪單按鈕、跟隨置中與 centerRequest 捲動、rowRef 收集。
 *
 *  **留在 container 的**(現股 `PriceLadder` / 個股期 `StkfutLadder` 各一份):送單 hook、
 *  武裝 reducer 與 idle timer、折數 localStorage、部位口徑、點價防抖與送單提示。兩個
 *  container 的差異全落在那些地方 —— 畫面則必須逐像素相同:同一支梯在現貨 / 期貨態
 *  之間切換時若版面跳動,武裝中的點擊目標就會位移。
 */
import { useEffect, useRef, useState, type ReactNode } from "react";

import { fmt } from "@/lib/format";
import type { LadderLot } from "@/lib/ladder-lots";
import { QTY_PRESETS } from "@/lib/qty-quick";
import type { LadderRow } from "@/lib/stock-tick";
import { cn } from "@/lib/utils";

/** OrderBook 點價置中請求。nonce 變化即觸發(同價連點也要重捲);訂閱者是 RightRail
 *  (唯一 window listener),因為右欄非閃電 tab 時本元件已 unmount(change-spec R2-5)。 */
export interface CenterRequest {
  priceMilli: number;
  nonce: number;
}

/** 同價位活單聚合。型別本體在 `lib/ladder-lots.ts`(與聚合函式同居);此處 re-export
 *  保住既有 `@/components/stock/LadderView` 的 import 路徑。 */
export type { LadderLot };

/** 有 seq 可刪(或還有殘量)→ 維持可點紅方格。`seqs` 非空是關鍵條件:actionable 但
 *  殘量算出來是 0 的單(P/U 先到、N 未到)照樣刪得掉,轉成徽章等於沒收刪單入口。 */
function isCancelable(lot: LadderLot): boolean {
  return lot.qty > 0 || lot.seqs.length > 0;
}

/** 紅方格 / 徽章文字:`未成交(已成交)`;無活單時只剩 `(已成交)`。 */
function lotText(lot: LadderLot): string {
  return isCancelable(lot) ? `${lot.qty}(${lot.filled})` : `(${lot.filled})`;
}

/** 全成交徽章:幾何沿紅方格(同側同緣、同級距),但降為 muted 邊框且**不吃點擊** ——
 *  沒有 seq 可刪,長得像可刪的按鈕就是假訊號。 */
const FILLED_BADGE =
  "pointer-events-none my-0.5 flex min-w-5 items-center justify-center rounded border border-line px-0.5 text-[10px] font-bold text-ink-muted";

/** 缺值顯示。部位條上「沒有這個數字」與「這個數字是 0」必須看得出差別。 */
export const DASH = "—";

export function pnlText(pnl: number | null): string {
  if (pnl === null) return DASH;
  return `${pnl > 0 ? "+" : ""}${pnl.toLocaleString("en-US")}`;
}

/** 台股慣例:賺紅賠綠。 */
export function pnlTone(pnl: number | null): string {
  if (pnl === null) return "text-ink-dim";
  return pnl > 0 ? "text-bull" : pnl < 0 ? "text-bear" : "text-ink";
}

interface Props {
  /** 標題列標的(D-12):右欄內容隨主 tab 切換,標的必須畫面可指認以降誤送風險 */
  code: string;
  name?: string;
  /** 標題列右側附加控制項(現股折數框;個股期無)—— 放在跟隨置中鈕左側 */
  titleExtra?: ReactNode;
  /** 武裝列上方的警示帶(期貨態結算警示等);無 = 不佔高度 */
  banner?: ReactNode;
  rows: LadderRow[];
  marketBidQty: number;
  marketAskQty: number;
  /** 檔位(毫元)→ 標記標籤;缺 = 不畫 */
  beMarks?: Map<number, string[]>;
  avgMarks?: Map<number, string[]>;
  buyLots?: Map<number, LadderLot>;
  sellLots?: Map<number, LadderLot>;
  armed: boolean;
  armDisabled?: boolean;
  armTitle?: string;
  onToggleArm: () => void;
  /** 武裝鈕右側的商品別控制項(現股交易別 select / 個股期當沖 checkbox) */
  armControls?: ReactNode;
  /** 買側全鎖(現股無券);與 `dimmed` 疊加 */
  buyLocked?: boolean;
  /** 買賣兩側全鎖(商品本身不開放下單,如 ETF 期貨);與 `dimmed` 疊加 */
  priceLocked?: boolean;
  qty: number;
  /** 數量欄位 aria-label:現股「張數」/ 期貨「口數」 */
  qtyLabel: string;
  onQtyPreset: (preset: number) => void;
  onQtyInput: (value: number) => void;
  hint?: string | null;
  onClickPrice: (priceMilli: number, side: "buy" | "sell") => void;
  onCancelLot: (lot: LadderLot) => void;
  centerRequest?: CenterRequest | null;
  /** 卡片最底的部位條(口徑由 container 決定) */
  footer?: ReactNode;
}

export function LadderView({
  code,
  name = "",
  titleExtra = null,
  banner = null,
  rows,
  marketBidQty,
  marketAskQty,
  beMarks,
  avgMarks,
  buyLots,
  sellLots,
  armed,
  armDisabled = false,
  armTitle,
  onToggleArm,
  armControls = null,
  buyLocked = false,
  priceLocked = false,
  qty,
  qtyLabel,
  onQtyPreset,
  onQtyInput,
  hint = null,
  onClickPrice,
  onCancelLot,
  centerRequest = null,
  footer = null,
}: Props) {
  const [follow, setFollow] = useState(true);
  const centerRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef(new Map<number, HTMLDivElement>());
  const progScroll = useRef(false);

  const centerPrice = rows.find((r) => r.isCenter)?.priceMilli ?? null;

  // OrderBook 點價 → 該價置中,不送單(W-C1)。事件由 RightRail 收(唯一 listener)後
  // 以 centerRequest prop 下傳:右欄非閃電 tab 時本元件已 unmount,window listener 收不到。
  useEffect(() => {
    if (centerRequest === null) return;
    const el = rowRefs.current.get(centerRequest.priceMilli);
    if (!el) return;
    setFollow(false);
    el.scrollIntoView({ block: "center" });
  }, [centerRequest?.nonce, centerRequest?.priceMilli]);

  // 跟隨置中:center 價變更才捲(rows identity 每 tick 變,依 centerPrice 值 — R5)
  useEffect(() => {
    if (!follow || centerPrice === null) return;
    progScroll.current = true;
    centerRef.current?.scrollIntoView({ block: "center" });
    requestAnimationFrame(() => {
      progScroll.current = false;
    });
  }, [follow, centerPrice]);

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col rounded-md border border-line bg-surface">
      {/* 標的列(D-12) */}
      <div className="flex items-center justify-between border-b border-line px-2 py-1">
        <span className="truncate font-mono text-sm text-ink">
          {code}
          {name !== "" ? <span className="ml-1 font-sans text-ink-muted">{name}</span> : null}
        </span>
        <div className="flex items-center gap-1">
          {titleExtra}
          <button
            type="button"
            aria-pressed={follow}
            onClick={() => setFollow((f) => !f)}
            className={cn(
              "rounded border px-1.5 py-0.5 text-xs",
              follow ? "border-accent text-accent" : "border-line text-ink-dim",
            )}
          >
            跟隨置中
          </button>
        </div>
      </div>
      {banner}
      {/* 武裝列:武裝/解除 + 商品別控制項 + 數量快捷 */}
      <div className="border-b border-line px-2 py-1.5">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-pressed={armed}
            disabled={armDisabled}
            title={armTitle}
            onClick={onToggleArm}
            className={cn(
              "flex-1 rounded border px-2 py-1 text-xs font-bold",
              armed
                ? "border-loss bg-loss text-bg"
                : "border-line text-ink-dim hover:border-accent hover:text-ink",
              armDisabled && "opacity-40",
            )}
          >
            {armed ? "解除" : "武裝"}
          </button>
          {armControls}
        </div>
        <div className="mt-1 flex items-center gap-1">
          {QTY_PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => onQtyPreset(p)}
              className="flex-1 rounded border border-line py-0.5 font-mono text-xs text-ink hover:border-accent"
            >
              {p}
            </button>
          ))}
          <input
            aria-label={qtyLabel}
            type="number"
            min={1}
            value={qty}
            onChange={(e) => onQtyInput(Number(e.target.value))}
            className="w-12 rounded border border-line bg-bg-deep px-1 py-0.5 text-right font-mono text-xs text-ink"
          />
        </div>
        {hint !== null && hint !== undefined ? (
          <p className="mt-1 text-center text-xs text-ink-muted">{hint}</p>
        ) : null}
      </div>
      {rows.length === 0 ? (
        <p className="px-2 py-4 text-center text-xs text-ink-dim">無資料</p>
      ) : (
        <div
          className="min-h-0 flex-1 overflow-y-auto"
          onScroll={() => {
            // 手動捲動(非程式捲)自動暫停跟隨(design R5)
            if (!progScroll.current && follow) setFollow(false);
          }}
        >
          {/* 市價買單列(項 4)。階梯只涵蓋 [下界, 上界] 的合法 tick,市價單沒有價格
              → 永遠不會落進任何一列,不獨立畫的話它在閃電梯完全消失。
              位置語意:市價買單優先於任何限價買單 → 價格軸最上。
              **不可點、不進 rowRefs**:它沒有價格,既送不了單也不是置中目標(W-15
              的 rows 集合語意不變)。 */}
          {marketBidQty > 0 ? (
            <div
              data-testid="ladder-market-bid"
              className="grid h-6 grid-cols-[1fr_64px_1fr] items-stretch border-b border-line/50 bg-bull/5 font-mono text-xs"
            >
              <span className="flex items-center justify-end pr-1 text-bull">{marketBidQty}</span>
              <span className="flex items-center justify-center text-ink-muted">市價</span>
              <span />
            </div>
          ) : null}
          {rows.map((r) => {
            const buyLot = buyLots?.get(r.priceMilli);
            const sellLot = sellLots?.get(r.priceMilli);
            const buyDisabled = r.dimmed || buyLocked || priceLocked;
            const sellDisabled = r.dimmed || priceLocked;
            const beKinds = beMarks?.get(r.priceMilli);
            const avgKinds = avgMarks?.get(r.priceMilli);
            // title 掛 row 不掛標記(LP-1):標記是 pointer-events-none,永遠不會是
            // hover 目標 → 掛在它身上的 tooltip 永遠不會出現。無標記的列不掛 title,
            // 否則整梯都是空 tooltip。
            const markTitle = [
              beKinds !== undefined ? `打平(${beKinds.join("、")})` : null,
              avgKinds !== undefined ? `均價(${avgKinds.join("、")})` : null,
            ]
              .filter((s) => s !== null)
              .join("、");
            return (
              <div
                key={r.priceMilli}
                data-price={r.priceMilli}
                title={markTitle !== "" ? markTitle : undefined}
                ref={(el) => {
                  if (el) rowRefs.current.set(r.priceMilli, el);
                  else rowRefs.current.delete(r.priceMilli);
                  if (r.isCenter && el) centerRef.current = el;
                }}
                className={cn(
                  "relative grid h-6 grid-cols-[1fr_64px_1fr] items-stretch border-b font-mono text-xs",
                  r.isCenter && "bg-bg-deep",
                  // 分隔線留在 row 容器上 → 淡化移欄後它不再吃 row 的 opacity,
                  // 不自己降階的話反灰列的格線會比改動前**更亮**(LP-4)
                  r.dimmed ? "border-line/20" : "border-line/50",
                )}
              >
                {/* 部位標記(SC-4)。`pointer-events-none` 是必要的:左緣正是刪單紅方格
                    與買鈕的點擊區,標記吃掉點擊會變成「按不到刪單」。
                    `opacity-100` 顯式隔離同列內容的 `opacity-35` —— 遠離現價的打平標記
                    正是最需要看見的那一根。 */}
                {beKinds !== undefined ? (
                  <span
                    data-testid="ladder-be-mark"
                    className="pointer-events-none absolute inset-y-0 left-0 w-0.5 bg-warn opacity-100"
                  />
                ) : null}
                {avgKinds !== undefined ? (
                  <span
                    data-testid="ladder-avg-mark"
                    className="pointer-events-none absolute inset-y-0 left-1 w-0.5 bg-ma20 opacity-100"
                  />
                ) : null}
                {/* 反灰(±5% 外)的淡化套在三個 grid 欄、不套 row 容器:opacity 是
                    合成層屬性,套在容器上時子元素無法「反淡」—— 之後要疊在 row 上的
                    部位標記(打平 / 均價)正好都落在遠離現價的位置。 */}
                <div className={cn("flex items-stretch", r.dimmed && "opacity-35")}>
                  {buyLot !== undefined && isCancelable(buyLot) ? (
                    <button
                      type="button"
                      aria-label={`刪 ${fmt(r.priceMilli)} 買單`}
                      onClick={() => onCancelLot(buyLot)}
                      className="my-0.5 ml-0.5 min-w-5 rounded border border-loss bg-loss/25 px-0.5 text-[10px] font-bold text-loss"
                    >
                      {lotText(buyLot)}
                    </button>
                  ) : buyLot !== undefined ? (
                    <span data-testid="ladder-filled-lot" className={cn(FILLED_BADGE, "ml-0.5")}>
                      {lotText(buyLot)}
                    </span>
                  ) : null}
                  <button
                    type="button"
                    disabled={buyDisabled}
                    aria-label={`買 ${fmt(r.priceMilli)}`}
                    onClick={() => onClickPrice(r.priceMilli, "buy")}
                    className={cn(
                      "min-w-0 flex-1 pr-1 text-right",
                      buyDisabled ? "text-ink-dim/50" : "text-bull hover:bg-bull/10",
                    )}
                  >
                    {r.bidQty > 0 ? r.bidQty : ""}
                  </button>
                </div>
                <span
                  className={cn(
                    "flex items-center justify-center",
                    r.isCenter ? "text-accent" : r.dimmed ? "text-ink-dim" : "text-ink",
                    r.dimmed && "opacity-35",
                  )}
                >
                  {fmt(r.priceMilli)}
                </span>
                <div className={cn("flex items-stretch", r.dimmed && "opacity-35")}>
                  <button
                    type="button"
                    disabled={sellDisabled}
                    aria-label={`賣 ${fmt(r.priceMilli)}`}
                    onClick={() => onClickPrice(r.priceMilli, "sell")}
                    className={cn(
                      "min-w-0 flex-1 pl-1 text-left",
                      sellDisabled ? "text-ink-dim/50" : "text-bear hover:bg-bear/10",
                    )}
                  >
                    {r.askQty > 0 ? r.askQty : ""}
                  </button>
                  {sellLot !== undefined && isCancelable(sellLot) ? (
                    <button
                      type="button"
                      aria-label={`刪 ${fmt(r.priceMilli)} 賣單`}
                      onClick={() => onCancelLot(sellLot)}
                      className="my-0.5 mr-0.5 min-w-5 rounded border border-loss bg-loss/25 px-0.5 text-[10px] font-bold text-loss"
                    >
                      {lotText(sellLot)}
                    </button>
                  ) : sellLot !== undefined ? (
                    <span data-testid="ladder-filled-lot" className={cn(FILLED_BADGE, "mr-0.5")}>
                      {lotText(sellLot)}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
          {/* 市價賣單列:對稱 —— 優先於任何限價賣單 → 價格軸最下 */}
          {marketAskQty > 0 ? (
            <div
              data-testid="ladder-market-ask"
              className="grid h-6 grid-cols-[1fr_64px_1fr] items-stretch border-b border-line/50 bg-bear/5 font-mono text-xs"
            >
              <span />
              <span className="flex items-center justify-center text-ink-muted">市價</span>
              <span className="flex items-center pl-1 text-bear">{marketAskQty}</span>
            </div>
          ) : null}
        </div>
      )}
      {/* 部位條放**卡片最底**(D5):價格梯 scroll 區是 flex-1,部位條出現時 scroll
          視窗從底部縮短,**既有價格列的 y 座標不動**。插在上方會整梯下移 —— 武裝中的
          閃電梯不得因部位資料到達而位移點擊目標。空手 → 整段不渲染(零痕跡)。 */}
      {footer}
    </div>
  );
}
