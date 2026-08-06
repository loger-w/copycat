/** 個股期閃電梯(stkfut-contracts SC-6 / R2-4)。
 *
 *  **兩種血統各取一半**,這是本檔唯一容易抄錯的地方:
 *  - 檔位幾何走**現股** `buildLadder`(期交所實證:個股期升降單位與現股同級距;
 *    台指期的固定 1 點表在這裡是錯的);
 *  - 送單 / 撤單 / 部位走**期貨**路(`useSubmitFuture`、`market: "fut"`、口數)。
 *
 *  與 FuturesLadder 的差異:symbol 是**月份 leaf** 不是 HOT(使用者選的月份就要送
 *  那個月),且武裝解除鍵是 instrumentKey 不是 product —— 見下方 R2-5 註。
 */
import { useEffect, useReducer, useRef, useState } from "react";

import {
  DASH,
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
  useSubmitFuture,
} from "@/hooks/useCapital";
import { ARM_IDLE_MS, initialArm, reduceArm } from "@/lib/flash-arm";
import { fmt } from "@/lib/format";
import { futExchangeContract } from "@/lib/futures-ladder";
import { initialQtyState, manualQty, pressQuick, type QtyState } from "@/lib/qty-quick";
import {
  instrumentKeyOf,
  isEtfUnderlying,
  stkfutTc4Symbol,
  ymLabel,
  type StkfutSelection,
} from "@/lib/stkfut";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { buildLadder } from "@/lib/stock-tick";
import { tradeErrorText } from "@/lib/trade-text";
import type { CapitalOrder, CapitalPosition } from "@/types";

const CLICK_DEBOUNCE_MS = 500;
const HINT_MS = 3_000;
const ETF_BLOCKED_TEXT = "ETF 期貨下單暫未開放";

/** 本合約 actionable 活單 → 價位(毫元)聚合殘量;點紅方格逐 seq 直刪用。
 *
 *  比對鍵是**期交所契約碼**(CDFI6),不是股號:群益回報的期貨單 `stock_no` 放的是
 *  契約碼,拿股號比會一筆都對不上(而畫面上只是「沒有掛單」,零錯誤訊號)。 */
function aggregateLots(
  orders: CapitalOrder[] | undefined,
  contract: string | null,
): { buy: Map<number, LadderLot>; sell: Map<number, LadderLot> } {
  const buy = new Map<number, LadderLot>();
  const sell = new Map<number, LadderLot>();
  if (contract === null) return { buy, sell };
  for (const o of orders ?? []) {
    if (!o.actionable || o.stock_no !== contract || o.price === null) continue;
    const map = o.buy_sell === "B" ? buy : o.buy_sell === "S" ? sell : null;
    if (map === null) continue;
    const key = Math.round(o.price * 1000);
    const cur = map.get(key) ?? { qty: 0, seqs: [] };
    cur.qty += Math.max(0, o.order_qty - o.filled_qty);
    cur.seqs.push(o.seq_no);
    map.set(key, cur);
  }
  return { buy, sell };
}

/** 本合約部位(fut + 契約碼相等 + qty ≠ 0)。 */
function contractPositions(
  positions: CapitalPosition[] | undefined,
  contract: string | null,
): CapitalPosition[] {
  if (contract === null) return [];
  return (positions ?? []).filter(
    (p) => p.market === "fut" && p.stock_no === contract && p.qty !== 0,
  );
}

interface Props {
  /** **股號**(標題列可指認 + 換股判定);合約走 `contract` 欄(D5 口徑) */
  code: string;
  name?: string;
  contract: StkfutSelection;
  book: StockBook | null;
  last: { p: number; t: string; cum_vol: number } | null;
  meta: StockMeta | null;
  centerRequest?: CenterRequest | null;
  /** 口數由 RightRail 持有 → 切 rail tab 不靜默重置(同 FuturesLadder R2-10) */
  qtyState?: QtyState;
  onQtyState?: (updater: (prev: QtyState) => QtyState) => void;
}

export function StkfutLadder({
  code,
  name = "",
  contract,
  book,
  last,
  meta,
  centerRequest = null,
  qtyState: qtyStateProp,
  onQtyState,
}: Props) {
  const [arm, dispatchArm] = useReducer(reduceArm, undefined, initialArm);
  const [qtyLocal, setQtyLocal] = useState(initialQtyState);
  const qtyState = qtyStateProp ?? qtyLocal;
  // 保持 functional updater:同一批次內連按快捷鍵要逐次累加(W-A12)
  const setQtyState = onQtyState ?? setQtyLocal;
  const [dayTrade, setDayTrade] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const idleTimer = useRef<number | undefined>(undefined);
  const hintTimer = useRef<number | undefined>(undefined);
  const lastClick = useRef<{ key: string; ts: number } | null>(null);
  const aliveRef = useRef(true); // unmount 後 mutateAsync 尾段不再碰 state(review B8)

  const wsStatus = useCapitalWsStatus();
  const submitFuture = useSubmitFuture();
  const cancelOrder = useCancelOrder();
  const { data: ordersData } = useCapitalOrders();
  const { data: positionsData } = useCapitalPositions();

  // 武裝解除鍵(R2-5):現貨↔合約、合約↔合約切換時 `code` 恆是股號且元件不 unmount
  // → 掛 code 的話這條永遠不觸發,武裝跨標的殘留 = 繞過確認直送真單。
  const instrumentKey = instrumentKeyOf(code, contract);
  // futExchangeContract 對非 YYYYMM 會 throw;合約來自後端白名單,但未捕捉 = 白屏
  // (App.tsx 對 resolved_contract 同款處理)。null → 活單 / 部位比對自然落空。
  let exchangeContract: string | null = null;
  try {
    exchangeContract = futExchangeContract(contract.prod, contract.ym);
  } catch {
    exchangeContract = null;
  }
  const etfBlocked = isEtfUnderlying(code);

  const lots = aggregateLots(ordersData?.orders, exchangeContract);
  const posRows = contractPositions(positionsData?.positions, exchangeContract);

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
    if (etfBlocked) return; // UI 已 disabled,雙保險(後端亦拒 PRODUCT_NOT_ALLOWED)
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
    // mutateAsync + 自行 then/catch:連發點價逐次計數 send_ok/send_fail(PriceLadder 同註)
    submitFuture
      .mutateAsync({
        tc4_symbol: stkfutTc4Symbol(contract),
        buy_sell: side,
        price: priceMilli / 1000,
        qty,
        price_type: "limit",
        time_in_force: "ROD",
        day_trade: dayTrade,
        source: "flash",
      })
      .then((r) => {
        if (!aliveRef.current) return; // review B8
        if (r.ok) {
          dispatchArm({ type: "send_ok" });
          showHint(`已送 ${side === "buy" ? "買" : "賣"} ${fmt(priceMilli)} × ${qty} 口`);
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

  // 紅方格點刪:閃電規則直刪(無彈窗),逐 seq 送 cancel(market=fut)
  function cancelLot(lot: LadderLot): void {
    touchIdle();
    for (const seq of lot.seqs) cancelOrder.mutate({ seq_no: seq, market: "fut" });
  }

  // 自動解除:換標的 / 換合約(R2-5)
  useEffect(() => {
    dispatchArm({ type: "symbol_changed" });
  }, [instrumentKey]);

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

  const titleName = `${name} ${contract.prod} ${ymLabel(contract.ym)}${
    contract.mini ? " 小型" : ""
  }`.trim();

  return (
    <LadderView
      code={code}
      name={titleName}
      rows={ladder.rows}
      marketBidQty={ladder.marketBidQty}
      marketAskQty={ladder.marketAskQty}
      buyLots={lots.buy}
      sellLots={lots.sell}
      armed={arm.armed}
      armDisabled={etfBlocked}
      armTitle={etfBlocked ? ETF_BLOCKED_TEXT : undefined}
      onToggleArm={() => {
        touchIdle();
        dispatchArm({ type: "toggle" });
      }}
      priceLocked={etfBlocked}
      qty={qtyState.qty}
      qtyLabel="口數"
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
      armControls={
        <label className="flex items-center gap-1 text-xs text-ink-muted">
          <input
            type="checkbox"
            aria-label="當沖"
            checked={dayTrade}
            onChange={(e) => {
              touchIdle();
              setDayTrade(e.target.checked);
            }}
            className="accent-loss"
          />
          當沖
        </label>
      }
      footer={
        posRows.length > 0 ? (
          /* 部位條:**不套現股稅費口徑**(positionEcon 的手續費 / 證交稅 / 借券費是
             證券市場的規則,期貨是期交稅 + 每口手續費)。本輪只顯示群益回報的名目
             損益 —— 自己算一個「含成本打平價」而口徑是錯的,比不顯示更糟。 */
          <div
            data-testid="stkfut-position-bar"
            className="border-t border-line px-2 py-1 font-mono text-xs"
          >
            {posRows.map((p) => (
              <div
                key={`${p.stock_no}:${p.kind}`}
                data-testid="stkfut-position-row"
                className="flex items-baseline justify-between gap-2"
              >
                <span className="text-ink">
                  {`${p.qty > 0 ? "多" : "空"} ${Math.abs(p.qty)} 口 @${
                    p.avg_price !== null && p.avg_price > 0 ? p.avg_price.toFixed(2) : DASH
                  }`}
                </span>
                <span className={pnlTone(p.pnl_base)}>{pnlText(p.pnl_base)}</span>
              </div>
            ))}
          </div>
        ) : null
      }
    />
  );
}
