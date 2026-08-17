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
import { useEffect, useRef, useState } from "react";

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
  useSubmitFuture,
} from "@/hooks/useCapital";
import { MarketOrderButtons } from "@/components/stock/MarketOrderButtons";
import { useFlashArm, type FlashArmControl } from "@/hooks/useFlashArm";
import { LOCK_WS_TITLE } from "@/lib/flash-arm";
import { BLOCKED_TEXT, marketButtonState, settleFlashSend } from "@/lib/flash-send";
import { fmt } from "@/lib/format";
import { futExchangeContract } from "@/lib/futures-ladder";
import { aggregateLots, ymdWindow } from "@/lib/ladder-lots";
import { initialQtyState, manualQty, pressQuick, type QtyState } from "@/lib/qty-quick";
import {
  instrumentKeyOf,
  isOrderBlocked,
  stkfutMarketEdgeMilli,
  stkfutTc4Symbol,
  ymLabel,
  type StkfutSelection,
} from "@/lib/stkfut";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { buildLadder } from "@/lib/stock-tick";
import type { CapitalPosition } from "@/types";

const CLICK_DEBOUNCE_MS = 500;
const HINT_MS = 3_000;

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
  /** 武裝狀態由 RightRail 持有(useFlashArm);未給時退回元件內部 hook。 */
  armCtl?: FlashArmControl;
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
  armCtl,
}: Props) {
  const localArm = useFlashArm(armCtl === undefined);
  const arm = armCtl ?? localArm;
  const dispatchArm = arm.dispatch;
  const touchIdle = arm.touch;
  const [qtyLocal, setQtyLocal] = useState(initialQtyState);
  const qtyState = qtyStateProp ?? qtyLocal;
  // 保持 functional updater:同一批次內連按快捷鍵要逐次累加(W-A12)
  const setQtyState = onQtyState ?? setQtyLocal;
  const [dayTrade, setDayTrade] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const hintTimer = useRef<number | undefined>(undefined);
  const lastClick = useRef<{ key: string; ts: number } | null>(null);
  const lastMarketClick = useRef<{ key: string; ts: number } | null>(null);
  const aliveRef = useRef(true); // unmount 後 mutateAsync 尾段不再碰 state(review B8)

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
  // 判準吃契約單位(與後端 `_stkfut_gates` 同一個),單位不可得才落回股號 fallback
  const blocked = isOrderBlocked(code, contract.unit);

  // 個股期有夜盤 → 已成交量的日期界取 ±1 日窗(`date` 在夜盤跨午夜時是交易日還是
  // 日曆日尚未實證,兩種假設都涵蓋);unit 閘不設 —— 契約碼與股號零碰撞,整筆 unit
  // 過濾反而會誤殺 market 缺值 fallback 的期貨單。
  const lots = aggregateLots(
    ordersData?.orders,
    exchangeContract,
    ymdWindow(new Date(), [-1, 0, 1]),
  );
  const posRows = contractPositions(positionsData?.positions, exchangeContract);

  const ladder = buildLadder({
    center: last?.p ?? null,
    ref: meta?.ref ?? null,
    upper: meta?.upper ?? null,
    lower: meta?.lower ?? null,
    book,
  });

  // 市價鈕的貼漲跌停邊價(已 snap 到合法檔位);漲跌停缺 → null = 鎖鈕
  const marketEdge = (side: "buy" | "sell") =>
    stkfutMarketEdgeMilli(side, { upper: meta?.upper ?? null, lower: meta?.lower ?? null });
  const marketState = marketButtonState({
    kind: "stkfut",
    estimateMissing: last === null || marketEdge("buy") === null || marketEdge("sell") === null,
    blocked,
  });

  function showHint(text: string, autoClear = false): void {
    if (!aliveRef.current) return; // unmount 後不設 timer / state(review B8)
    window.clearTimeout(hintTimer.current);
    setHint(text);
    if (autoClear) hintTimer.current = window.setTimeout(() => setHint(null), HINT_MS);
  }

  function clickPrice(priceMilli: number, side: "buy" | "sell"): void {
    touchIdle();
    if (blocked) return; // UI 已 disabled,雙保險(後端亦拒 PRODUCT_NOT_ALLOWED)
    if (!arm.state.armed) {
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
    // mutateAsync + settleFlashSend:連發點價逐次計數 send_ok/send_fail(PriceLadder 同註);
    // 失敗無條件計數、成功留 aliveRef 守門的理由收在 lib/flash-send.ts
    settleFlashSend(
      submitFuture.mutateAsync({
        tc4_symbol: stkfutTc4Symbol(contract),
        buy_sell: side,
        price: priceMilli / 1000,
        qty,
        price_type: "limit",
        time_in_force: "ROD",
        day_trade: dayTrade,
        source: "flash",
      }),
      {
        alive: () => aliveRef.current,
        dispatch: dispatchArm,
        showHint,
        okText: `已送 ${side === "buy" ? "買" : "賣"} ${fmt(priceMilli)} × ${qty} 口`,
      },
    );
  }

  /** 梯頂市價鈕(SC-3)。個股期沒有可用的真市價路徑(後端 fut market → `"M"` literal,
   *  OrderPanel 的 TXO 在用)→ 這裡直送**限價貼漲跌停 + IOC**(D3a):有對手就一路吃穿
   *  各檔位、無對手即刻取消。邊價已 snap 到合法檔位,否則 `_stkfut_gates` 回 BAD_TICK。
   *  防抖走獨立槽位(理由見 PriceLadder 同段註)。 */
  function marketOrder(side: "buy" | "sell"): void {
    touchIdle();
    if (blocked) return; // UI 已 disabled,雙保險(後端亦拒 PRODUCT_NOT_ALLOWED)
    const edge = marketEdge(side);
    if (last === null || edge === null) return; // 估價缺:鈕已 disabled,雙保險
    if (!arm.state.armed) {
      showHint("未武裝 — 市價不送單", true);
      return;
    }
    const now = Date.now();
    if (
      lastMarketClick.current !== null &&
      lastMarketClick.current.key === side &&
      now - lastMarketClick.current.ts < CLICK_DEBOUNCE_MS
    ) {
      return; // 同一顆 500ms 防抖
    }
    lastMarketClick.current = { key: side, ts: now };
    const qty = qtyState.qty;
    settleFlashSend(
      submitFuture.mutateAsync({
        tc4_symbol: stkfutTc4Symbol(contract),
        buy_sell: side,
        price: edge / 1000,
        qty,
        price_type: "limit",
        time_in_force: "IOC",
        day_trade: dayTrade,
        source: "flash",
      }),
      {
        alive: () => aliveRef.current,
        dispatch: dispatchArm,
        showHint,
        // 契約碼缺(YYYYMM 解析失敗)才退回股號 —— hint 不得沒有標的(R-H)
        okText: `已送 ${exchangeContract ?? code} 市價${
          side === "buy" ? "買" : "賣"
        } × ${qty} 口`,
      },
    );
  }

  // 紅方格點刪:閃電規則直刪(無彈窗),逐 seq 送 cancel(market=fut)
  function cancelLot(lot: LadderLot): void {
    touchIdle();
    for (const seq of lot.seqs) cancelOrder.mutate({ seq_no: seq, market: "fut" });
  }

  // 送出口走 ref:觸發條件是換合約 / 卸載,不是 dispatch 本身(理由見 PriceLadder 同段註)
  const armDispatchRef = useRef(dispatchArm);
  useEffect(() => {
    armDispatchRef.current = dispatchArm;
  }, [dispatchArm]);

  // 自動解除:換標的 / 換合約(R2-5)
  useEffect(() => {
    armDispatchRef.current({ type: "symbol_changed" });
  }, [instrumentKey]);

  // 離開畫面(卸載)= 解除武裝(state 已上提到 RightRail,見 useFlashArm)
  useEffect(() => {
    return () => armDispatchRef.current({ type: "left_view" });
  }, []);

  // unmount 清 hint 計時器 + aliveRef(StrictMode remount 時 effect 本體重設 true)
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      window.clearTimeout(hintTimer.current);
    };
  }, []);

  const titleName = `${name} ${contract.prod} ${ymLabel(contract.ym)}${
    contract.mini ? " 小型" : ""
  }`.trim();

  // 鎖定鈕 disabled 只擋**進入**方向,**整條**都要 `&& !locked`(R2 + code review r1 S3):
  // blocked 與 WS 非 open 都只是「不得進入鎖定」的理由,已鎖定時解鎖鈕恆可按 —— 否則
  // 鎖定態在 blocked 契約 / connecting 上就沒有 UI 出口。點價另有 priceLocked 擋。
  const lockDisabled = (blocked || arm.wsStatus !== "open") && !arm.state.locked;

  return (
    <LadderView
      code={code}
      name={titleName}
      rows={ladder.rows}
      marketBidQty={ladder.marketBidQty}
      marketAskQty={ladder.marketAskQty}
      buyLots={lots.buy}
      sellLots={lots.sell}
      armed={arm.state.armed}
      armDisabled={blocked}
      armTitle={blocked ? BLOCKED_TEXT : undefined}
      onToggleArm={() => {
        touchIdle();
        dispatchArm({ type: "toggle" });
      }}
      locked={arm.state.locked}
      lockDisabled={lockDisabled}
      lockTitle={lockDisabled && arm.wsStatus !== "open" ? LOCK_WS_TITLE : undefined}
      onToggleLock={() => {
        touchIdle();
        dispatchArm({ type: arm.state.locked ? "unlock" : "lock" });
      }}
      priceLocked={blocked}
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
      ladderTop={<MarketOrderButtons onMarket={marketOrder} state={marketState} />}
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
