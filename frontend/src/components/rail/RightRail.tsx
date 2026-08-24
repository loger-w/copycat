import { memo, useEffect, useState, type KeyboardEvent } from "react";

import { CapitalOrdersList } from "@/components/capital/CapitalOrdersList";
import { CapitalPositionsList } from "@/components/capital/CapitalPositionsList";
import { FuturesLadder } from "@/components/futures/FuturesLadder";
import type { CenterRequest } from "@/components/stock/LadderView";
import { PriceLadder, type TradeKind } from "@/components/stock/PriceLadder";
import { StkfutLadder } from "@/components/stock/StkfutLadder";
import { useFlashArm } from "@/hooks/useFlashArm";
import { RAIL_TAB_KEY } from "@/lib/constants";
import { futCloseEstimate, futExchangeContract } from "@/lib/futures-ladder";
import { initialQtyState, type QtyState } from "@/lib/qty-quick";
import {
  instrumentKeyOf,
  isOrderBlocked,
  stkfutMarketEdgeMilli,
  type StkfutSelection,
} from "@/lib/stkfut";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { tablistKeyAction } from "@/lib/tablist-keys";
import { cn } from "@/lib/utils";
import type { FuturesProductState } from "@/types";

/** 右欄(SC-2/SC-3;D1 三 tab 平行、D2 內容跟隨當前主 tab、D6 無標的頁顯空狀態)。
 *
 * ⚠ **閃電 tab 的 ladder 一律條件 render,不可改成 `hidden`**(change-spec D-13)。
 * 專案慣例是「`hidden` > 條件 render」保留 DOM,**這裡刻意違反**:條件 render 仍是
 * 「離開畫面即解除武裝」(W-A2 第 6 條)的實現手段之一。arm state 本身已上提到本元件
 * (`useFlashArm`)—— 離開畫面的解除改由 ladder 卸載時 dispatch `left_view` 完成,
 * 改成 hidden 會讓 ladder 永不卸載、事件永不發出 → 武裝跨主 tab / 跨右欄 tab 存活,
 * 使用者在無脈絡下點價即真錢直送。
 *
 * 相對地,交易別 / 數量由本元件持有(R2-10):它們沒有「誤觸即送單」的性質,
 * 靜默重置(融券 → 現股)反而是風險。 */

/** 個股期部位的平倉估價工廠(RightRail 的 `positionsContent` 用)。
 *
 *  **module 層純函式**(react-doctor `prefer-module-scope-pure-function`;元件內就地寫的話
 *  這一整段規則會跟著 `positionsContent` 一起長):
 *  - 契約碼算不出來 → 恆 `null` = 平倉鍵鎖住,不放行「估不出價還送單」(後端對 price<=0 直接 raise);
 *  - **邊價走股票 tick 表**(與同頁市價鈕 `stkfutMarketEdgeMilli` 同一支):`FUT_TICK` 的 1 點
 *    對股票是 1 元,拿它 snap 出來的檔位在期交所是非法檔位。後端自 N098 起對「可用現股
 *    tick 表的個股期」(標準 / 小型腿)在 `/api/capital/position/close` 也驗一次 → 未對齊
 *    會 400 BAD_TICK;這裡仍是第一道守門;
 *  - **N099**:ETF 期貨(單位 10,000)與除權息調整腿(2,157 之類)在送單面一律
 *    `PRODUCT_NOT_ALLOWED`,平倉鍵不能反而放行 —— 而且它們正是後端檔位閘的放行分支,
 *    所以這裡是**唯一**守門。回 `null` = 鍵鎖住,比照送單面。
 *  - `code ?? ""`:`unit` 有值時判準完全吃 unit(股號不參與);unit 也不可得時空字串落回
 *    `isEtfUnderlying("") === false` = 不擋,與改動前逐字同行為。 */
function stkfutClosePriceOf(
  code: string | null,
  contract: StkfutSelection,
  meta: StockMeta | null,
): (pos: { stock_no: string; qty: number }) => number | null {
  if (isOrderBlocked(code ?? "", contract.unit)) return () => null;
  let futKey: string | null = null;
  try {
    futKey = futExchangeContract(contract.prod, contract.ym);
  } catch {
    futKey = null;
  }
  const quote = { upper: meta?.upper ?? null, lower: meta?.lower ?? null };
  return (pos) =>
    futCloseEstimate(pos, futKey, quote, (side, upper, lower) =>
      stkfutMarketEdgeMilli(side, { upper, lower }),
    );
}

const TABS = [
  ["flash", "閃電"],
  ["orders", "委託"],
  ["positions", "部位"],
] as const;
type RailTab = (typeof TABS)[number][0];

function initialTab(): RailTab {
  const saved = window.localStorage.getItem(RAIL_TAB_KEY);
  return saved === "orders" || saved === "positions" ? saved : "flash";
}

/** tab ↔ tabpanel 的 id 對(a11y 批 SC-2')。RightRail 全站只有一個實例(App 常駐
 *  單掛),所以用固定字串而不是 `useId` —— 固定 id 讓 `aria-controls` 在 panel 還沒
 *  mount 時仍是可預期的命名,而不是每次 render 換一個值。 */
const tabId = (id: RailTab) => `rail-tab-${id}`;
const panelId = (id: RailTab) => `rail-panel-${id}`;

export type RailContext =
  | {
      kind: "stock";
      /** **恆為股號**(stkfut-contracts D5),期貨態也一樣 —— 點價 gate 與下單面標的都吃它 */
      code: string | null;
      /** 選中的個股期合約;`null` = 現貨態。與 `code` 分成兩欄而不是塞成一個 key,
       *  是為了讓「這是哪一檔股票」與「這是哪一個合約」兩個問題各自有單一讀法。 */
      contract: StkfutSelection | null;
      name: string;
      book: StockBook | null;
      last: { p: number; t: string; cum_vol: number } | null;
      meta: StockMeta | null;
    }
  | {
      kind: "futures";
      product: string;
      state: FuturesProductState | null;
      contract: string | null;
    }
  | { kind: "none" };

function EmptyFlash() {
  return (
    <div className="flex flex-1 items-center justify-center rounded-md border border-line bg-surface p-4">
      <p className="text-center text-sm text-ink-muted">此頁無可下單標的</p>
    </div>
  );
}

/** `memo` 包裹(refactor/memo-boundaries S1):唯一的 prop 是 `ctx`,而 App 已把它拆成
 *  兩腿 useMemo + 模組常數 `NONE_CTX` —— 兩者要成對才有效(memo 沒有 = ctx 穩定也照重繪;
 *  ctx 每輪新 identity = memo 的比較永遠不過)。具名 `memo(function RightRail(...))` 是
 *  專案慣例:匿名箭頭在 DevTools / react-doctor 的元件樹上會變成 `Memo`。 */
export const RightRail = memo(function RightRail({ ctx }: { ctx: RailContext }) {
  const [tab, setTab] = useState<RailTab>(initialTab);
  const [centerRequest, setCenterRequest] = useState<CenterRequest | null>(null);
  const [tradeKind, setTradeKind] = useState<TradeKind>("cash");
  const [stockQty, setStockQty] = useState<QtyState>(initialQtyState);
  const [futQty, setFutQty] = useState<QtyState>(initialQtyState);
  // 個股期口數 **per instrument key**(code review A5)。與台指期分開存還不夠:標準檔
  // (2,000 股)與小型檔(100 股)差 20 倍,共用一格會讓「在小型上按了 20 口再切回標準」
  // 直接變成 20 倍規模的單,而畫面上那個數字本來就是使用者自己按的 —— 沒有任何異狀。
  // 每個合約各一格 = 切合約回到初值(1 口),要多少自己按。
  const [stkfutQty, setStkfutQty] = useState<Record<string, QtyState>>({});
  // 武裝狀態上提到常駐元件:Esc / 斷線監聽在這一層,連停在無梯頁(TXO / 指數)也收得到。
  // 三座梯共用同一份(同時只有一座掛著);未鎖定時 ladder 卸載即 `left_view` 重置。
  const armCtl = useFlashArm();

  function selectTab(next: RailTab): void {
    setTab(next);
    window.localStorage.setItem(RAIL_TAB_KEY, next);
    // 離開閃電 tab 就清掉置中請求:ladder 會 unmount,留著的話下次掛載時 effect 會拿
    // 舊 centerRequest 再捲一次到過期價位並關掉跟隨(review phase5 P2-2)。
    // 註:ladder 的 `follow` 也隨 unmount 回到預設 true(重新掛載即置中於現價)—— 這是
    // D-13 的既定代價,刻意不上提:它沒有「誤觸即送單」的性質,回到跟隨現價是合理預設。
    if (next !== "flash") setCenterRequest(null);
  }

  /** manual activation(D3'):方向鍵只移焦點,Enter / Space 才 `selectTab`。
   *  焦點目標從 tablist 現場查 —— 三顆 tab 恆掛,不必為此多存一組 ref。 */
  function onTabKeyDown(e: KeyboardEvent<HTMLButtonElement>, id: RailTab): void {
    const action = tablistKeyAction(e, TABS.findIndex(([t]) => t === id), TABS.length);
    if (action === null) return;
    e.preventDefault();
    if (action === "select") {
      selectTab(id);
      return;
    }
    const tabs = e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    tabs?.[action]?.focus();
  }

  // R4:選中個股期合約 → 右欄整組換到期貨市場。委託 / 部位若還停在 `sec`,使用者
  // 看到的是現股庫存與現股委託,而閃電梯送出去的是期貨單 —— 兩邊對不起來。
  const stockCode = ctx.kind === "stock" ? ctx.code : null;
  const stkfutContract = ctx.kind === "stock" ? ctx.contract : null;
  const market = ctx.kind === "futures" || stkfutContract !== null ? "fut" : "sec";
  // 「這是哪一個標的」的唯一鍵(code review A7a)。舊碼把「換標的就清掉置中請求」掛在
  // 上面那個 effect 的 cleanup、判準是 `stockCode` —— 兩個問題:
  //   (a) 判準太粗:合約 ↔ 現貨、換月、換產品腿時 `code` 恆是股號不變(D5),cleanup
  //       根本不觸發,舊價位的請求跨 instrument 存活;
  //   (b) 就算把 instrumentKey 加進 deps 也**贏不了同一個 commit 內的子元件掛載**:
  //       合約 ↔ 現貨那一步會把 StkfutLadder 換成 PriceLadder(元件不同 = 真的重新
  //       掛載),而 React 的順序是「先跑全部 destroy、再跑全部 create」—— destroy 裡的
  //       `setCenterRequest(null)` 只是排一次更新,新掛載的梯這一輪拿到的仍是舊值,
  //       開頁就捲到別的價帶並關掉跟隨。
  // 所以改成 render 期間直接調整 state(官方 pattern,同 StockPage 的 pickerOpen):
  // 子元件這一輪就拿到 null,零競態。
  const instrumentKey = instrumentKeyOf(stockCode, stkfutContract);
  const [prevInstrument, setPrevInstrument] = useState(instrumentKey);
  if (prevInstrument !== instrumentKey) {
    setPrevInstrument(instrumentKey);
    setCenterRequest(null);
    // 鎖定態換標的 → 張數回初值(code review r1 S2)。未鎖定時換標的會解除武裝,下一單
    // 必須先重按武裝 —— 那顆鈕就是「你正要在這檔送 N 張」的檢查點,所以 qty 可以留著
    // (W-7 / R2-10)。鎖定把檢查點拿掉了:留著 qty 等於「在 A 檔按到 10 張、切到 B 檔」
    // 就是 B 檔 10 張直送,而畫面上那個數字是使用者自己按的,名目放大零訊號。
    if (armCtl.state.locked) setStockQty(initialQtyState());
  }
  // 期貨腿同理(qty 各梯各自持有,所以要各自打回初值)
  const futProduct = ctx.kind === "futures" ? ctx.product : null;
  const [prevProduct, setPrevProduct] = useState(futProduct);
  if (prevProduct !== futProduct) {
    setPrevProduct(futProduct);
    if (armCtl.state.locked) setFutQty(initialQtyState());
  }

  // 五檔點價的唯一 window listener(W-C1 / R2-5):ladder 在非閃電 tab 已 unmount,
  // 收不到事件 → 這裡先切回閃電 tab,再以 centerRequest prop 讓 ladder 掛載後置中。
  useEffect(() => {
    const onPriceClick = (e: Event): void => {
      const detail = (e as CustomEvent<{ priceMilli?: number; code?: string }>).detail;
      // 事件的比對鍵是**股號**:發事件的 OrderBook 畫的是主圖,而點價 gate 一路都以
      // 股號指認標的(D5)—— 換成 instrumentKey 會讓期貨態的點價全部落空。
      if (!detail || detail.code !== stockCode || typeof detail.priceMilli !== "number") return;
      setTab("flash");
      window.localStorage.setItem(RAIL_TAB_KEY, "flash");
      setCenterRequest((prev) => ({
        priceMilli: detail.priceMilli as number,
        nonce: (prev?.nonce ?? 0) + 1,
      }));
    };
    window.addEventListener("stock-price-click", onPriceClick);
    return () => window.removeEventListener("stock-price-click", onPriceClick);
  }, [stockCode]);

  function flashContent() {
    if (ctx.kind === "stock" && ctx.code !== null && ctx.contract !== null) {
      // 這條分支下 instrumentKey 必非 null(code 與 contract 都有值),`?? ""` 只是
      // 型別收斂 —— 真落到 "" 也只是共用一格,不會壞
      const key = instrumentKey ?? "";
      return (
        <StkfutLadder
          code={ctx.code}
          name={ctx.name}
          contract={ctx.contract}
          book={ctx.book}
          last={ctx.last}
          meta={ctx.meta}
          centerRequest={centerRequest}
          qtyState={stkfutQty[key] ?? initialQtyState()}
          onQtyState={(updater) =>
            setStkfutQty((m) => ({ ...m, [key]: updater(m[key] ?? initialQtyState()) }))
          }
          armCtl={armCtl}
        />
      );
    }
    if (ctx.kind === "stock" && ctx.code !== null) {
      return (
        <PriceLadder
          code={ctx.code}
          name={ctx.name}
          book={ctx.book}
          last={ctx.last}
          meta={ctx.meta}
          centerRequest={centerRequest}
          tradeKind={tradeKind}
          onTradeKind={setTradeKind}
          qtyState={stockQty}
          onQtyState={setStockQty}
          armCtl={armCtl}
        />
      );
    }
    if (ctx.kind === "futures") {
      return (
        <FuturesLadder
          product={ctx.product}
          state={ctx.state}
          contractLabel={ctx.contract}
          qtyState={futQty}
          onQtyState={setFutQty}
          armCtl={armCtl}
        />
      );
    }
    return <EmptyFlash />;
  }

  function ordersContent() {
    // TXO / 指數:無 market 語境 → 證券 + 期貨兩段並排,各自渲染未改動的既有清單
    // (CapitalMarket 型別只有 sec|fut,沒有「全部」;change-spec P0-2)
    if (ctx.kind === "none") {
      return (
        <div className="flex flex-col gap-3">
          <section>
            <h4 className="mb-1 text-xs text-ink-dim">證券</h4>
            <CapitalOrdersList market="sec" />
          </section>
          <section>
            <h4 className="mb-1 text-xs text-ink-dim">期貨</h4>
            <CapitalOrdersList market="fut" />
          </section>
        </div>
      );
    }
    return <CapitalOrdersList market={market} />;
  }

  function positionsContent() {
    if (ctx.kind === "none") {
      // closePriceOf 一律不傳 → 無行情估價 → 平倉鍵 disabled(W-A10)
      return (
        <div className="flex flex-col gap-3">
          <section>
            <h4 className="mb-1 text-xs text-ink-dim">證券</h4>
            <CapitalPositionsList market="sec" />
          </section>
          <section>
            <h4 className="mb-1 text-xs text-ink-dim">期貨</h4>
            <CapitalPositionsList market="fut" />
          </section>
        </div>
      );
    }
    if (ctx.kind === "stock") {
      const { code, last, meta } = ctx;
      if (ctx.contract !== null) {
        // 個股期部位:平倉估價貼漲跌停,規則全收在 module 層的 `stkfutClosePriceOf`
        return (
          <CapitalPositionsList
            market="fut"
            closePriceOf={stkfutClosePriceOf(code, ctx.contract, meta)}
          />
        );
      }
      return (
        <CapitalPositionsList
          market="sec"
          closePriceOf={(pos) => (pos.stock_no === code && last !== null ? last.p / 1000 : null)}
        />
      );
    }
    const { contract, state } = ctx;
    return (
      <CapitalPositionsList
        market="fut"
        closePriceOf={(pos) => futCloseEstimate(pos, contract, state)}
      />
    );
  }

  return (
    // border-l:與中間主區的視覺分隔(round3 項 5)。本元件常駐**全部 tab**,
    // 所以這條線在 TXO / 期貨 / 指數頁也會出現 —— 刻意的一致性。
    <aside
      className="flex w-72 shrink-0 flex-col gap-2 border-l border-line pl-3"
      aria-label="交易面板"
    >
      <div className="flex items-center gap-1 border-b border-line pb-1" role="tablist" aria-label="交易面板分頁">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={tabId(id)}
            // ⚠ 未選中的 tab 指向一個**還沒 mount** 的 panel(dangling):panel 是條件
            // render(D-13,見檔頭),不可改 hidden。這是 spec 明記的既定代價 —— 選中
            // 的那顆恆指得到,AT 的實際使用路徑不受影響。
            aria-controls={panelId(id)}
            aria-selected={tab === id}
            // roving tabindex:整組 tablist 只佔一個 tab stop,組內用方向鍵走
            tabIndex={tab === id ? 0 : -1}
            onKeyDown={(e) => onTabKeyDown(e, id)}
            onClick={() => selectTab(id)}
            className={cn(
              "flex-1 rounded px-2 py-1 text-sm",
              tab === id ? "bg-bg-deep text-ink" : "text-ink-dim hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {/* 條件 render(非 hidden)—— 見檔頭 D-13 說明,改動前先讀。
          閃電分支要一層 wrapper 才掛得上 `role=tabpanel`(它回傳的是各家 ladder 本體);
          委託 / 部位則把 role 掛在**既有**捲動層上,不新增節點。 */}
      {tab === "flash" ? (
        <div
          role="tabpanel"
          id={panelId("flash")}
          aria-labelledby={tabId("flash")}
          className="flex min-h-0 flex-1 flex-col"
        >
          {flashContent()}
        </div>
      ) : null}
      {tab === "orders" ? (
        <div
          role="tabpanel"
          id={panelId("orders")}
          aria-labelledby={tabId("orders")}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {ordersContent()}
        </div>
      ) : null}
      {tab === "positions" ? (
        <div
          role="tabpanel"
          id={panelId("positions")}
          aria-labelledby={tabId("positions")}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {positionsContent()}
        </div>
      ) : null}
    </aside>
  );
});
