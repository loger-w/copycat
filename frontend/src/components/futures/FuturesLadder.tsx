import { useEffect, useReducer, useRef, useState } from "react";

import {
  useCancelOrder,
  useCapitalOrders,
  useCapitalWsStatus,
  useSubmitFuture,
} from "@/hooks/useCapital";
import { ARM_IDLE_MS, initialArm, reduceArm } from "@/lib/flash-arm";
import { fmt } from "@/lib/format";
import {
  buildFuturesLadder,
  futExchangeContract,
  splitMyLots,
  type FutLadderRow,
} from "@/lib/futures-ladder";
import { initialQtyState, manualQty, pressQuick, QTY_PRESETS, type QtyState } from "@/lib/qty-quick";
import { tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { FuturesProductState } from "@/types";

const CLICK_DEBOUNCE_MS = 500;
const HINT_MS = 3_000;

interface Props {
  product: string; // TXF/MXF/TMF
  state: FuturesProductState | null;
  /** 解析後契約(標題列標的顯示,D-12);null = 未解析 */
  contractLabel?: string | null;
  /** 口數改由 RightRail 持有 → 切 rail tab 不靜默重置(change-spec R2-10);
   *  未給時退回元件內部 state(獨立使用與既有測試路徑)。 */
  qtyState?: QtyState;
  onQtyState?: (updater: (prev: QtyState) => QtyState) => void;
}

/** 期貨閃電梯:武裝機制與 PriceLadder 同款(見該檔註解);差異 = 當沖 checkbox、量單位口、
 *  HOT 直送 + resolved_contract 未解析時鎖武裝(送單層拒單的前置雙保險)。 */
export function FuturesLadder({
  product,
  state,
  contractLabel = null,
  qtyState: qtyStateProp,
  onQtyState,
}: Props) {
  const [follow, setFollow] = useState(true);
  // 武裝 = 唯一繞過確認彈窗的路徑 → 解除從寬:換商品/斷線/idle/Esc/連 3 次失敗/合約失解析/
  // 離開畫面(RightRail 條件 render 讓本元件 unmount,arm state 隨之消滅;change-spec D-13)
  const [arm, dispatchArm] = useReducer(reduceArm, undefined, initialArm);
  const [qtyLocal, setQtyLocal] = useState(initialQtyState);
  const qtyState = qtyStateProp ?? qtyLocal;
  // 保持 functional updater:同一批次內連按快捷鍵要逐次累加(W-A12),
  // 值式會用到 stale state(review P2-9(3))
  const setQtyState = onQtyState ?? setQtyLocal;
  const [dayTrade, setDayTrade] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const centerRef = useRef<HTMLDivElement | null>(null);
  const progScroll = useRef(false);
  const idleTimer = useRef<number | undefined>(undefined);
  const hintTimer = useRef<number | undefined>(undefined);
  const lastClick = useRef<{ key: string; ts: number } | null>(null);
  const aliveRef = useRef(true); // unmount 後 mutateAsync 尾段不再碰 state(review B8)

  const wsStatus = useCapitalWsStatus();
  const submitFuture = useSubmitFuture();
  const cancelOrder = useCancelOrder();
  const { data: ordersData } = useCapitalOrders();

  const resolvedYm = state?.resolved_contract ?? null;
  const contract = resolvedYm !== null ? futExchangeContract(product, resolvedYm) : null;
  const myLots = contract !== null ? splitMyLots(ordersData?.orders ?? [], contract) : [];

  const centerMilli = state?.p ?? state?.ref ?? null;
  const rows: FutLadderRow[] =
    state !== null && centerMilli !== null && state.upper !== null && state.lower !== null
      ? buildFuturesLadder({
          centerMilli,
          upperMilli: state.upper,
          lowerMilli: state.lower,
          bids: state.bids.map(([priceMilli, qty]) => ({ priceMilli, qty })),
          asks: state.asks.map(([priceMilli, qty]) => ({ priceMilli, qty })),
          myLots,
        })
      : [];
  const centerPrice = rows.find((r) => r.isCenter)?.priceMilli ?? null;

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
        tc4_symbol: `TC.F.TWF.${product}.HOT`,
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
  function cancelLot(seqNos: string[]): void {
    touchIdle();
    for (const seq of seqNos) cancelOrder.mutate({ seq_no: seq, market: "fut" });
  }

  // 自動解除:換商品
  useEffect(() => {
    dispatchArm({ type: "symbol_changed" });
  }, [product]);

  // 自動解除:合約失解析(武裝鈕 disabled 之外的雙保險)
  useEffect(() => {
    if (contract === null) dispatchArm({ type: "disarm" });
  }, [contract]);

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

  // 跟隨置中:center 價變更才捲(rows identity 每 tick 變,依 centerPrice 值)
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
      {/* 標的列(D-12):右欄內容會隨主 tab 切換,標的必須畫面可指認以降誤送風險 */}
      <div className="flex items-center justify-between border-b border-line px-2 py-1">
        <span className="truncate font-mono text-sm text-ink">
          {product}
          {contractLabel !== null ? (
            <span className="ml-1 text-ink-muted">{contractLabel}</span>
          ) : null}
        </span>
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
      {/* 武裝列:武裝/解除 + 當沖 + 口數快捷 */}
      <div className="border-b border-line px-2 py-1.5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-pressed={arm.armed}
            disabled={contract === null}
            title={contract === null ? "合約未解析" : undefined}
            onClick={() => {
              touchIdle();
              dispatchArm({ type: "toggle" });
            }}
            className={cn(
              "flex-1 rounded border px-2 py-1 text-xs font-bold",
              arm.armed
                ? "border-loss bg-loss text-bg"
                : "border-line text-ink-dim hover:border-accent hover:text-ink",
              contract === null && "opacity-40",
            )}
          >
            {arm.armed ? "解除" : "武裝"}
          </button>
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
        </div>
        <div className="mt-1 flex items-center gap-1">
          {QTY_PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => {
                touchIdle();
                setQtyState((s) => pressQuick(s, p));
              }}
              className="flex-1 rounded border border-line py-0.5 font-mono text-xs text-ink hover:border-accent"
            >
              {p}
            </button>
          ))}
          <input
            aria-label="口數"
            type="number"
            min={1}
            value={qtyState.qty}
            onChange={(e) => {
              touchIdle();
              setQtyState((s) => manualQty(s, Number(e.target.value)));
            }}
            className="w-12 rounded border border-line bg-bg-deep px-1 py-0.5 text-right font-mono text-xs text-ink"
          />
        </div>
        {hint !== null ? (
          <p className="mt-1 text-center text-xs text-ink-muted">{hint}</p>
        ) : null}
      </div>
      {rows.length === 0 ? (
        <p className="px-2 py-4 text-center text-xs text-ink-dim">無資料</p>
      ) : (
        <div
          className="min-h-0 flex-1 overflow-y-auto"
          onScroll={() => {
            // 手動捲動(非程式捲)自動暫停跟隨
            if (!progScroll.current && follow) setFollow(false);
          }}
        >
          {rows.map((r) => (
            <div
              key={r.priceMilli}
              ref={(el) => {
                if (r.isCenter && el) centerRef.current = el;
              }}
              className={cn(
                "grid h-6 grid-cols-[1fr_72px_1fr] items-stretch border-b border-line/50 font-mono text-xs",
                r.isCenter && "bg-bg-deep",
                !r.clickable && "opacity-35",
              )}
            >
              <div className="flex items-stretch">
                {r.myQty > 0 ? (
                  <button
                    type="button"
                    aria-label={`刪 ${fmt(r.priceMilli)} 掛單`}
                    onClick={() => cancelLot(r.mySeqNos)}
                    className="my-0.5 ml-0.5 min-w-5 rounded border border-loss bg-loss/25 px-0.5 text-[10px] font-bold text-loss"
                  >
                    {r.myQty}
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={!r.clickable}
                  aria-label={`買 ${fmt(r.priceMilli)}`}
                  onClick={() => clickPrice(r.priceMilli, "buy")}
                  className={cn(
                    "min-w-0 flex-1 pr-1 text-right",
                    r.clickable ? "text-bull hover:bg-bull/10" : "text-ink-dim/50",
                  )}
                >
                  {r.bidQty > 0 ? r.bidQty : ""}
                </button>
              </div>
              <span
                className={cn(
                  "flex items-center justify-center",
                  r.isCenter ? "text-accent" : r.clickable ? "text-ink" : "text-ink-dim",
                )}
              >
                {fmt(r.priceMilli)}
              </span>
              <button
                type="button"
                disabled={!r.clickable}
                aria-label={`賣 ${fmt(r.priceMilli)}`}
                onClick={() => clickPrice(r.priceMilli, "sell")}
                className={cn(
                  "min-w-0 pl-1 text-left",
                  r.clickable ? "text-bear hover:bg-bear/10" : "text-ink-dim/50",
                )}
              >
                {r.askQty > 0 ? r.askQty : ""}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
