import { useEffect, useReducer, useRef, useState } from "react";

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
import {
  avgTickOf,
  clampDiscount,
  FEE_DISCOUNT_DEFAULT,
  positionEcon,
  secPositionsOf,
  snapBreakEven,
} from "@/lib/ladder-position";
import { initialQtyState, manualQty, pressQuick, QTY_PRESETS, type QtyState } from "@/lib/qty-quick";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { buildLadder } from "@/lib/stock-tick";
import { tradeErrorText } from "@/lib/trade-text";
import { cn } from "@/lib/utils";
import type { CapitalOrder, CapitalPosition } from "@/types";

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

function pnlText(pnl: number | null): string {
  if (pnl === null) return DASH;
  return `${pnl > 0 ? "+" : ""}${pnl.toLocaleString("en-US")}`;
}

/** 台股慣例:賺紅賠綠。 */
function pnlTone(pnl: number | null): string {
  if (pnl === null) return "text-ink-dim";
  return pnl > 0 ? "text-bull" : pnl < 0 ? "text-bear" : "text-ink";
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
  const [discount, setDiscount] = useState<DiscountState>(loadDiscount);
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
  const rows = ladder.rows;
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
        <div className="flex items-center gap-1">
          {/* 折數框放**標題列**不放武裝列(ORD-1):武裝列上它會與張數框變成同型相鄰的
              兩個數字框,而其中一個是真錢張數 —— 誤打折數時張數靜默留舊值,下一次點價
              就用舊張數送真單。折數本身不是下單控制項,不該待在誤送半徑內。
              恆常渲染:空手也要能先把折數設好(D1)。 */}
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
                "w-10 rounded border bg-bg-deep px-1 py-0.5 text-right font-mono text-xs text-ink",
                discountInvalid ? "border-loss" : "border-line",
              )}
            />
            折
          </label>
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
          {/* 市價買單列(項 4)。階梯只涵蓋 [下界, 上界] 的合法 tick,市價單沒有價格
              → 永遠不會落進任何一列,不獨立畫的話它在閃電梯完全消失。
              位置語意:市價買單優先於任何限價買單 → 價格軸最上。
              **不可點、不進 rowRefs**:它沒有價格,既送不了單也不是置中目標(W-15
              的 rows 集合語意不變)。 */}
          {ladder.marketBidQty > 0 ? (
            <div
              data-testid="ladder-market-bid"
              className="grid h-6 grid-cols-[1fr_64px_1fr] items-stretch border-b border-line/50 bg-bull/5 font-mono text-xs"
            >
              <span className="flex items-center justify-end pr-1 text-bull">
                {ladder.marketBidQty}
              </span>
              <span className="flex items-center justify-center text-ink-muted">市價</span>
              <span />
            </div>
          ) : null}
          {rows.map((r) => {
            const buyLot = lots.buy.get(r.priceMilli);
            const sellLot = lots.sell.get(r.priceMilli);
            const buyLocked = r.dimmed || tradeKind === "daytrade_sell";
            const beKinds = beMarks.get(r.priceMilli);
            const avgKinds = avgMarks.get(r.priceMilli);
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
                    r.dimmed && "opacity-35",
                  )}
                >
                  {fmt(r.priceMilli)}
                </span>
                <div className={cn("flex items-stretch", r.dimmed && "opacity-35")}>
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
          {/* 市價賣單列:對稱 —— 優先於任何限價賣單 → 價格軸最下 */}
          {ladder.marketAskQty > 0 ? (
            <div
              data-testid="ladder-market-ask"
              className="grid h-6 grid-cols-[1fr_64px_1fr] items-stretch border-b border-line/50 bg-bear/5 font-mono text-xs"
            >
              <span />
              <span className="flex items-center justify-center text-ink-muted">市價</span>
              <span className="flex items-center pl-1 text-bear">{ladder.marketAskQty}</span>
            </div>
          ) : null}
        </div>
      )}
      {/* 部位條放**卡片最底**(D5):價格梯 scroll 區是 flex-1,部位條出現時 scroll
          視窗從底部縮短,**既有價格列的 y 座標不動**。插在上方會整梯下移 —— 武裝中的
          閃電梯不得因部位資料到達而位移點擊目標。空手 → 整段不渲染(零痕跡)。 */}
      {posRows.length > 0 ? (
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
      ) : null}
    </div>
  );
}
