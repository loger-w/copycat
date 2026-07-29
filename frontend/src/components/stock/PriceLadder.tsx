import { useEffect, useReducer, useRef, useState } from "react";

import {
  useCancelOrder,
  useCapitalOrders,
  useCapitalWsStatus,
  useSubmitStock,
} from "@/hooks/useCapital";
import { ARM_IDLE_MS, initialArm, reduceArm } from "@/lib/flash-arm";
import { initialQtyState, manualQty, pressQuick, QTY_PRESETS, type QtyState } from "@/lib/qty-quick";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { buildLadder } from "@/lib/stock-tick";
import { tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { CapitalOrder } from "@/types";

const CLICK_DEBOUNCE_MS = 500;
const HINT_MS = 3_000;

export const TRADE_KINDS = [
  ["cash", "現股"],
  ["margin", "融資"],
  ["short", "融券"],
  ["daytrade_sell", "無券"],
] as const;
export type TradeKind = (typeof TRADE_KINDS)[number][0];

function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}

interface LotEntry {
  qty: number; // 殘量(order_qty - filled_qty 聚合)
  seqs: string[];
}

/** 本檔 actionable 活單 → 價位(毫元)聚合殘量;點紅方格逐 seq 直刪用。 */
function aggregateLots(
  orders: CapitalOrder[] | undefined,
  code: string,
): { buy: Map<number, LotEntry>; sell: Map<number, LotEntry> } {
  const buy = new Map<number, LotEntry>();
  const sell = new Map<number, LotEntry>();
  for (const o of orders ?? []) {
    if (!o.actionable || o.stock_no !== code || o.price === null) continue;
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

/** OrderBook 點價置中請求。nonce 變化即觸發(同價連點也要重捲);訂閱者是 RightRail
 *  (唯一 window listener),因為右欄非閃電 tab 時本元件已 unmount(change-spec R2-5)。 */
export interface CenterRequest {
  priceMilli: number;
  nonce: number;
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
  const [follow, setFollow] = useState(true);
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
  const centerRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef(new Map<number, HTMLDivElement>());
  const progScroll = useRef(false);
  const idleTimer = useRef<number | undefined>(undefined);
  const hintTimer = useRef<number | undefined>(undefined);
  const lastClick = useRef<{ key: string; ts: number } | null>(null);
  const aliveRef = useRef(true); // unmount 後 mutateAsync 尾段不再碰 state(review B8)

  const wsStatus = useCapitalWsStatus();
  const submitStock = useSubmitStock();
  const cancelOrder = useCancelOrder();
  const { data: ordersData } = useCapitalOrders();
  const lots = aggregateLots(ordersData?.orders, code);

  const rows = buildLadder({
    center: last?.p ?? null,
    ref: meta?.ref ?? null,
    upper: meta?.upper ?? null,
    lower: meta?.lower ?? null,
    book,
  });
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
  function cancelLot(lot: LotEntry): void {
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

  // OrderBook 點價 → 該價置中,不送單(W-C1)。事件由 RightRail 收(唯一 listener)後
  // 以 centerRequest prop 下傳:右欄非閃電 tab 時本元件已 unmount,window listener 收不到。
  useEffect(() => {
    if (centerRequest === null) return;
    const el = rowRefs.current.get(centerRequest.priceMilli);
    if (!el) return;
    setFollow(false);
    el.scrollIntoView({ block: "center" });
  }, [centerRequest?.nonce, centerRequest?.priceMilli]);

  // unmount 清計時器 + aliveRef(StrictMode remount 時 effect 本體重設 true)
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      window.clearTimeout(idleTimer.current);
      window.clearTimeout(hintTimer.current);
    };
  }, []);

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
      {/* 標的列(D-12):右欄內容會隨主 tab 切換,標的必須畫面可指認以降誤送風險 */}
      <div className="flex items-center justify-between border-b border-line px-2 py-1">
        <span className="truncate font-mono text-sm text-ink">
          {code}
          {name !== "" ? <span className="ml-1 font-sans text-ink-muted">{name}</span> : null}
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
      {/* 武裝列:武裝/解除 + 交易別 + 張數快捷 */}
      <div className="border-b border-line px-2 py-1.5">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-pressed={arm.armed}
            onClick={() => {
              touchIdle();
              dispatchArm({ type: "toggle" });
            }}
            className={cn(
              "flex-1 rounded border px-2 py-1 text-xs font-bold",
              arm.armed
                ? "border-loss bg-loss text-bg"
                : "border-line text-ink-dim hover:border-accent hover:text-ink",
            )}
          >
            {arm.armed ? "解除" : "武裝"}
          </button>
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
            aria-label="張數"
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
            // 手動捲動(非程式捲)自動暫停跟隨(design R5)
            if (!progScroll.current && follow) setFollow(false);
          }}
        >
          {rows.map((r) => {
            const buyLot = lots.buy.get(r.priceMilli);
            const sellLot = lots.sell.get(r.priceMilli);
            const buyLocked = r.dimmed || tradeKind === "daytrade_sell";
            return (
              <div
                key={r.priceMilli}
                ref={(el) => {
                  if (el) rowRefs.current.set(r.priceMilli, el);
                  else rowRefs.current.delete(r.priceMilli);
                  if (r.isCenter && el) centerRef.current = el;
                }}
                className={cn(
                  "grid h-6 grid-cols-[1fr_64px_1fr] items-stretch border-b border-line/50 font-mono text-xs",
                  r.isCenter && "bg-bg-deep",
                  r.dimmed && "opacity-35",
                )}
              >
                <div className="flex items-stretch">
                  {buyLot !== undefined ? (
                    <button
                      type="button"
                      aria-label={`刪 ${fmt(r.priceMilli)} 買單`}
                      onClick={() => cancelLot(buyLot)}
                      className="my-0.5 ml-0.5 min-w-5 rounded border border-loss bg-loss/25 px-0.5 text-[10px] font-bold text-loss"
                    >
                      {buyLot.qty}
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={buyLocked}
                    aria-label={`買 ${fmt(r.priceMilli)}`}
                    onClick={() => clickPrice(r.priceMilli, "buy")}
                    className={cn(
                      "min-w-0 flex-1 pr-1 text-right",
                      buyLocked ? "text-ink-dim/50" : "text-bull hover:bg-bull/10",
                    )}
                  >
                    {r.bidQty > 0 ? r.bidQty : ""}
                  </button>
                </div>
                <span
                  className={cn(
                    "flex items-center justify-center",
                    r.isCenter ? "text-accent" : r.dimmed ? "text-ink-dim" : "text-ink",
                  )}
                >
                  {fmt(r.priceMilli)}
                </span>
                <div className="flex items-stretch">
                  <button
                    type="button"
                    disabled={r.dimmed}
                    aria-label={`賣 ${fmt(r.priceMilli)}`}
                    onClick={() => clickPrice(r.priceMilli, "sell")}
                    className={cn(
                      "min-w-0 flex-1 pl-1 text-left",
                      r.dimmed ? "text-ink-dim/50" : "text-bear hover:bg-bear/10",
                    )}
                  >
                    {r.askQty > 0 ? r.askQty : ""}
                  </button>
                  {sellLot !== undefined ? (
                    <button
                      type="button"
                      aria-label={`刪 ${fmt(r.priceMilli)} 賣單`}
                      onClick={() => cancelLot(sellLot)}
                      className="my-0.5 mr-0.5 min-w-5 rounded border border-loss bg-loss/25 px-0.5 text-[10px] font-bold text-loss"
                    >
                      {sellLot.qty}
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
