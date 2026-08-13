import { useEffect, useReducer, useRef, useState } from "react";

import {
  LadderView,
  pnlText,
  pnlTone,
  type CenterRequest,
  type LadderLot,
} from "@/components/stock/LadderView";
import {
  useCancelOrder,
  useCapitalOrders,
  useCapitalPositions,
  useCapitalWsStatus,
  useSubmitStock,
} from "@/hooks/useCapital";
import { FEE_DISCOUNT_KEY } from "@/lib/constants";
import { ARM_IDLE_MS, initialArm, reduceArm } from "@/lib/flash-arm";
import { fmt } from "@/lib/format";
import { aggregateLots } from "@/lib/ladder-lots";
import {
  avgTickOf,
  clampDiscount,
  FEE_DISCOUNT_DEFAULT,
  positionEcon,
  secPositionsOf,
  snapBreakEven,
} from "@/lib/ladder-position";
import { initialQtyState, manualQty, pressQuick, type QtyState } from "@/lib/qty-quick";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { buildLadder } from "@/lib/stock-tick";
import { tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { CapitalPosition } from "@/types";

const CLICK_DEBOUNCE_MS = 500;
const HINT_MS = 3_000;

export const TRADE_KINDS = [
  ["cash", "現股"],
  ["margin", "融資"],
  ["short", "融券"],
  ["daytrade_sell", "無券"],
] as const;
export type TradeKind = (typeof TRADE_KINDS)[number][0];

/** 缺值顯示。部位條上「沒有這個數字」與「這個數字是 0」必須看得出差別。 */
const DASH = "—";

/** kind → 顯示標籤,查表未命中就顯示原字串:群益 `Position.kind` 的值域比本檔的
 *  交易別寬(D13),不認得的部位寧可標籤怪也不要靜默消失。 */
function kindLabel(kind: string): string {
  return TRADE_KINDS.find(([v]) => v === kind)?.[1] ?? kind;
}

interface DiscountState {
  /** 受控輸入的原始值,可暫時為空 / 非法 —— 不吃掉使用者打到一半的按鍵。 */
  raw: string;
  /** 最後一次通過 clampDiscount 的值;計算恆用它。 */
  value: number;
}

/** 讀存檔折數。**整段包 try/catch**:localStorage 在私密視窗 / storage 被政策鎖時
 *  光是存取就會拋,而這是 useState initializer —— 拋出去就是閃電梯首次 render 掛掉
 *  (同 `hooks/useChartToggles.ts::load`)。 */
function loadDiscount(): DiscountState {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(FEE_DISCOUNT_KEY);
  } catch {
    raw = null; // 讀不到 → 走預設,記憶體內照常運作
  }
  const value = clampDiscount(raw ?? "") ?? FEE_DISCOUNT_DEFAULT;
  return { raw: String(value), value };
}

function persistDiscount(value: number): void {
  try {
    window.localStorage.setItem(FEE_DISCOUNT_KEY, String(value));
  } catch {
    // 存不進去就算了 —— 折數不落檔遠好於看盤畫面崩掉(同 useChartToggles::persist)
  }
}

interface PositionRow {
  key: string;
  /** kind 標籤(部位條與標記 title 共用同一份字彙) */
  label: string;
  /** 第一行左側:`現股 2張 @100` / `融券 空2張 @100`(均價缺值 → `@—`) */
  head: string;
  /** 第二行:`打平 100.5`(顯示 snap 後的檔位,與梯內標記同值) */
  beText: string;
  pnl: number | null;
  /** snap 後的打平檔位(毫元);均價缺值 → null */
  beTick: number | null;
  /** 均價所在檔位(毫元);均價缺值 → null */
  avgTick: number | null;
}

function positionRows(
  positions: CapitalPosition[],
  lastMilli: number | null,
  discount: number,
): PositionRow[] {
  return positions.map((p) => {
    const econ = positionEcon(p.qty, p.avg_price, lastMilli, discount, p.kind);
    // 均價的缺值判定與 positionEcon 同一條規則(0 不是價格)
    const avg = p.avg_price !== null && p.avg_price > 0 ? p.avg_price : null;
    const label = kindLabel(p.kind);
    const beTick = econ.breakEvenMilli === null ? null : snapBreakEven(econ.breakEvenMilli, p.qty);
    // avg_price 是**元**(types.ts CapitalPosition),fmt 吃毫元 → 先 ×1000
    const avgText = avg === null ? DASH : fmt(Math.round(avg * 1000));
    return {
      key: `${p.kind}:${p.stock_no}`,
      label,
      head: `${label} ${p.qty < 0 ? "空" : ""}${Math.abs(p.qty)}張 @${avgText}`,
      beText: `打平 ${beTick === null ? DASH : fmt(beTick)}`,
      pnl: econ.pnl,
      beTick,
      avgTick: avg === null ? null : avgTickOf(avg),
    };
  });
}

/** 檔位(毫元)→ 該檔位上的 kind 標籤陣列。同檔位多 kind 時 title 併列。 */
function markMap(rows: PositionRow[], pick: (r: PositionRow) => number | null): Map<number, string[]> {
  const map = new Map<number, string[]>();
  for (const r of rows) {
    const tick = pick(r);
    if (tick === null) continue;
    const cur = map.get(tick);
    if (cur === undefined) map.set(tick, [r.label]);
    else cur.push(r.label);
  }
  return map;
}

interface Props {
  code: string;
  /** 股名(標題列標的顯示,D-12 降誤送風險) */
  name?: string;
  book: StockBook | null;
  last: { p: number; t: string; cum_vol: number } | null;
  meta: StockMeta | null;
  centerRequest?: CenterRequest | null;
  /** 交易別 / 張數改由 RightRail 持有 → 切 rail tab 不靜默重置(change-spec R2-10)。
   *  未給時退回元件內部 state(獨立使用與既有測試路徑)。 */
  tradeKind?: TradeKind;
  onTradeKind?: (kind: TradeKind) => void;
  qtyState?: QtyState;
  onQtyState?: (updater: (prev: QtyState) => QtyState) => void;
}

export function PriceLadder({
  code,
  name = "",
  book,
  last,
  meta,
  centerRequest = null,
  tradeKind: tradeKindProp,
  onTradeKind,
  qtyState: qtyStateProp,
  onQtyState,
}: Props) {
  // 武裝 = 唯一繞過確認彈窗的路徑 → 解除從寬:換股/斷線/idle/Esc/連 3 次失敗/離開畫面
  // (離開畫面 = RightRail 條件 render 讓本元件 unmount,arm state 隨之消滅;change-spec D-13)
  const [arm, dispatchArm] = useReducer(reduceArm, undefined, initialArm);
  const [qtyLocal, setQtyLocal] = useState(initialQtyState);
  const [tradeKindLocal, setTradeKindLocal] = useState<TradeKind>("cash");
  const tradeKind = tradeKindProp ?? tradeKindLocal;
  const setTradeKind = onTradeKind ?? setTradeKindLocal;
  const qtyState = qtyStateProp ?? qtyLocal;
  // 保持 functional updater:同一批次內連按快捷鍵要逐次累加(W-A12),
  // 值式會用到 stale state(review P2-9(3))
  const setQtyState = onQtyState ?? setQtyLocal;
  const [hint, setHint] = useState<string | null>(null);
  const [discount, setDiscount] = useState<DiscountState>(loadDiscount);
  const idleTimer = useRef<number | undefined>(undefined);
  const hintTimer = useRef<number | undefined>(undefined);
  const lastClick = useRef<{ key: string; ts: number } | null>(null);
  const aliveRef = useRef(true); // unmount 後 mutateAsync 尾段不再碰 state(review B8)

  const wsStatus = useCapitalWsStatus();
  const submitStock = useSubmitStock();
  const cancelOrder = useCancelOrder();
  const { data: ordersData } = useCapitalOrders();
  const lots = aggregateLots(ordersData?.orders, code);
  const { data: positionsData } = useCapitalPositions();
  // 每 tick 重算:kinds 量級是個位數的純算術,不值得 memo
  const posRows = positionRows(
    secPositionsOf(positionsData?.positions, code),
    last?.p ?? null,
    discount.value,
  );
  const beMarks = markMap(posRows, (r) => r.beTick);
  const avgMarks = markMap(posRows, (r) => r.avgTick);
  const discountInvalid = clampDiscount(discount.raw) === null;

  const ladder = buildLadder({
    center: last?.p ?? null,
    ref: meta?.ref ?? null,
    upper: meta?.upper ?? null,
    lower: meta?.lower ?? null,
    book,
  });

  function touchIdle(): void {
    window.clearTimeout(idleTimer.current);
    idleTimer.current = window.setTimeout(
      () => dispatchArm({ type: "idle_timeout" }),
      ARM_IDLE_MS,
    );
  }

  function showHint(text: string, autoClear = false): void {
    if (!aliveRef.current) return; // unmount 後不設 timer / state(review B8)
    window.clearTimeout(hintTimer.current);
    setHint(text);
    if (autoClear) hintTimer.current = window.setTimeout(() => setHint(null), HINT_MS);
  }

  function clickPrice(priceMilli: number, side: "buy" | "sell"): void {
    touchIdle();
    if (tradeKind === "daytrade_sell" && side === "buy") return; // UI 已 disabled,雙保險
    if (!arm.armed) {
      showHint("未武裝 — 點價不送單", true);
      return;
    }
    const key = `${side}:${priceMilli}`;
    const now = Date.now();
    if (
      lastClick.current !== null &&
      lastClick.current.key === key &&
      now - lastClick.current.ts < CLICK_DEBOUNCE_MS
    ) {
      return; // 同格 500ms 防抖
    }
    lastClick.current = { key, ts: now };
    const qty = qtyState.qty;
    // mutateAsync + 自行 then/catch:TQ 的 mutate 層 callback 只對「最後一次」呼叫
    // 觸發,連發點價會漏算 send_ok/send_fail(武裝連 3 敗自動解除依賴逐次計數)
    submitStock
      .mutateAsync({
        stock_no: code,
        buy_sell: side,
        price: priceMilli / 1000,
        qty,
        price_type: "limit",
        time_in_force: "ROD",
        trade_kind: tradeKind,
        source: "flash",
      })
      .then((r) => {
        if (!aliveRef.current) return; // review B8
        if (r.ok) {
          dispatchArm({ type: "send_ok" });
          showHint(`已送 ${side === "buy" ? "買" : "賣"} ${fmt(priceMilli)} × ${qty}`);
        } else {
          dispatchArm({ type: "send_fail" });
          showHint(r.message !== "" ? r.message : "送單失敗");
        }
      })
      .catch((err: unknown) => {
        if (!aliveRef.current) return; // review B8
        dispatchArm({ type: "send_fail" });
        showHint(tradeErrorText(err instanceof Error ? err.message : String(err)));
      });
  }

  // 紅方格點刪:閃電規則直刪(無彈窗),逐 seq 送 cancel
  function cancelLot(lot: LadderLot): void {
    touchIdle();
    for (const seq of lot.seqs) cancelOrder.mutate({ seq_no: seq, market: "sec" });
  }

  // 自動解除:換股
  useEffect(() => {
    dispatchArm({ type: "symbol_changed" });
  }, [code]);

  // 自動解除:capital WS 斷線
  useEffect(() => {
    if (wsStatus === "closed") dispatchArm({ type: "conn_lost" });
  }, [wsStatus]);

  // Esc = 鍵盤解除(只在武裝期間掛 window 監聽)
  useEffect(() => {
    if (!arm.armed) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") dispatchArm({ type: "disarm" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [arm.armed]);

  // unmount 清計時器 + aliveRef(StrictMode remount 時 effect 本體重設 true)
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      window.clearTimeout(idleTimer.current);
      window.clearTimeout(hintTimer.current);
    };
  }, []);

  return (
    <LadderView
      code={code}
      name={name}
      rows={ladder.rows}
      marketBidQty={ladder.marketBidQty}
      marketAskQty={ladder.marketAskQty}
      beMarks={beMarks}
      avgMarks={avgMarks}
      buyLots={lots.buy}
      sellLots={lots.sell}
      armed={arm.armed}
      onToggleArm={() => {
        touchIdle();
        dispatchArm({ type: "toggle" });
      }}
      buyLocked={tradeKind === "daytrade_sell"}
      qty={qtyState.qty}
      qtyLabel="張數"
      onQtyPreset={(p) => {
        touchIdle();
        setQtyState((s) => pressQuick(s, p));
      }}
      onQtyInput={(v) => {
        touchIdle();
        setQtyState((s) => manualQty(s, v));
      }}
      hint={hint}
      onClickPrice={clickPrice}
      onCancelLot={cancelLot}
      centerRequest={centerRequest}
      titleExtra={
        /* 折數框放**標題列**不放武裝列(ORD-1):武裝列上它會與張數框變成同型相鄰的
           兩個數字框,而其中一個是真錢張數 —— 誤打折數時張數靜默留舊值,下一次點價
           就用舊張數送真單。折數本身不是下單控制項,不該待在誤送半徑內。
           恆常渲染:空手也要能先把折數設好(D1)。 */
        <label className="flex items-center gap-0.5 text-xs text-ink-dim">
          <input
            aria-label="手續費折數"
            type="number"
            step={0.1}
            min={0.1}
            max={10}
            value={discount.raw}
            // 非法值不是「沒事」:輸入框顯示 raw、計算卻用舊 value,不給訊號就是靜默態
            aria-invalid={discountInvalid ? true : undefined}
            onChange={(e) => {
              const raw = e.target.value;
              const v = clampDiscount(raw);
              // 非法值只更新 raw(不吃掉按鍵),value 沿用上一個合法值 → 計算不跳動
              setDiscount((s) => ({ raw, value: v ?? s.value }));
              if (v !== null) persistDiscount(v);
            }}
            className={cn(
              // **spinner 必須收掉**:Chrome 的 number input 右側恆佔 ~13-16px 給
              // 上下箭頭,吃掉的是可視字元數 —— w-10 時「1.8」的 8 直接被裁掉(真
              // Chrome 實測),使用者讀不到自己設的折數,而折數決定打平價與未實現損益。
              // w-12 下「1.8」完整可讀是真 Chrome 複驗結果
              // (evidence/SC-4_SC-5_rail-after-re1-fix.png);但 w-12 只剛好容 3 字元,
              // 兩位小數的合法折數(2.85 / 0.85)仍會截 —— 收掉 spinner 後同寬可容
              // 約 5 字元,才算真的修好。
              "w-12 rounded border bg-bg-deep px-1 py-0.5 text-right font-mono text-xs text-ink",
              "[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
              discountInvalid ? "border-loss" : "border-line",
            )}
          />
          折
        </label>
      }
      armControls={
        <select
          aria-label="交易別"
          value={tradeKind}
          onChange={(e) => {
            touchIdle();
            setTradeKind(e.target.value as TradeKind);
          }}
          className="rounded border border-line bg-bg-deep px-1 py-1 text-xs text-ink"
        >
          {TRADE_KINDS.map(([v, label]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </select>
      }
      footer={
        posRows.length > 0 ? (
          <div
            data-testid="ladder-position-bar"
            className="border-t border-line px-2 py-1 font-mono text-xs"
          >
            {posRows.map((r) => (
              <div key={r.key} data-testid="ladder-position-row">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-ink">{r.head}</span>
                  <span className={pnlTone(r.pnl)}>{pnlText(r.pnl)}</span>
                </div>
                {/* 兩顆色點分別對應梯內兩根標線,讓「梯上那根線是什麼」不必猜。
                    均價**只給標籤不給數字**(CALC-3):第一行 @ 顯示的是真均價原值,
                    標線位置是 snapNearest 後的近似檔位 —— 兩個口徑的數字並列會讓人
                    以為均價變了。 */}
                <div className="flex items-center gap-1 text-ink-muted">
                  {r.beTick !== null ? (
                    <span aria-hidden="true" className="inline-block h-2 w-0.5 bg-warn" />
                  ) : null}
                  <span>{r.beText}</span>
                  {r.avgTick !== null ? (
                    <>
                      <span aria-hidden="true" className="ml-1 inline-block h-2 w-0.5 bg-ma20" />
                      <span>均價</span>
                    </>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : null
      }
    />
  );
}
