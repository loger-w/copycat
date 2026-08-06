import { useEffect, useState } from "react";

import { CapitalOrdersList } from "@/components/capital/CapitalOrdersList";
import { CapitalPositionsList } from "@/components/capital/CapitalPositionsList";
import { FuturesLadder } from "@/components/futures/FuturesLadder";
import { PriceLadder, type CenterRequest, type TradeKind } from "@/components/stock/PriceLadder";
import { RAIL_TAB_KEY } from "@/lib/constants";
import { futCloseEstimate } from "@/lib/futures-ladder";
import { initialQtyState, type QtyState } from "@/lib/qty-quick";
import type { StkfutSelection } from "@/lib/stkfut";
import type { StockBook, StockMeta } from "@/lib/stock-accum";
import { cn } from "@/lib/utils";
import type { FuturesProductState } from "@/types";

/** 右欄(SC-2/SC-3;D1 三 tab 平行、D2 內容跟隨當前主 tab、D6 無標的頁顯空狀態)。
 *
 * ⚠ **閃電 tab 的 ladder 一律條件 render,不可改成 `hidden`**(change-spec D-13)。
 * 專案慣例是「`hidden` > 條件 render」保留 DOM,**這裡刻意違反**:ladder 的武裝
 * (arm)state 存活於元件內,unmount 是「離開畫面即解除武裝」(W-A2 第 6 條)的實現手段。
 * 改成 hidden 會讓武裝跨主 tab / 跨右欄 tab 存活 → 使用者在無脈絡下點價即真錢直送。
 *
 * 相對地,交易別 / 數量由本元件持有(R2-10):它們沒有「誤觸即送單」的性質,
 * 靜默重置(融券 → 現股)反而是風險。 */

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

export function RightRail({ ctx }: { ctx: RailContext }) {
  const [tab, setTab] = useState<RailTab>(initialTab);
  const [centerRequest, setCenterRequest] = useState<CenterRequest | null>(null);
  const [tradeKind, setTradeKind] = useState<TradeKind>("cash");
  const [stockQty, setStockQty] = useState<QtyState>(initialQtyState);
  const [futQty, setFutQty] = useState<QtyState>(initialQtyState);

  function selectTab(next: RailTab): void {
    setTab(next);
    window.localStorage.setItem(RAIL_TAB_KEY, next);
    // 離開閃電 tab 就清掉置中請求:ladder 會 unmount,留著的話下次掛載時 effect 會拿
    // 舊 centerRequest 再捲一次到過期價位並關掉跟隨(review phase5 P2-2)。
    // 註:ladder 的 `follow` 也隨 unmount 回到預設 true(重新掛載即置中於現價)—— 這是
    // D-13 的既定代價,刻意不上提:它沒有「誤觸即送單」的性質,回到跟隨現價是合理預設。
    if (next !== "flash") setCenterRequest(null);
  }

  // 五檔點價的唯一 window listener(W-C1 / R2-5):ladder 在非閃電 tab 已 unmount,
  // 收不到事件 → 這裡先切回閃電 tab,再以 centerRequest prop 讓 ladder 掛載後置中。
  const stockCode = ctx.kind === "stock" ? ctx.code : null;
  useEffect(() => {
    const onPriceClick = (e: Event): void => {
      const detail = (e as CustomEvent<{ priceMilli?: number; code?: string }>).detail;
      if (!detail || detail.code !== stockCode || typeof detail.priceMilli !== "number") return;
      setTab("flash");
      window.localStorage.setItem(RAIL_TAB_KEY, "flash");
      setCenterRequest((prev) => ({
        priceMilli: detail.priceMilli as number,
        nonce: (prev?.nonce ?? 0) + 1,
      }));
    };
    window.addEventListener("stock-price-click", onPriceClick);
    return () => {
      window.removeEventListener("stock-price-click", onPriceClick);
      // 換標的:舊的置中請求對新標的無意義,留著會在新 ladder 掛載時捲到不存在的價位
      setCenterRequest(null);
    };
  }, [stockCode]);

  const market = ctx.kind === "futures" ? "fut" : "sec";

  function flashContent() {
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
      const { code, last } = ctx;
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
            aria-selected={tab === id}
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
      {/* 條件 render(非 hidden)—— 見檔頭 D-13 說明,改動前先讀 */}
      {tab === "flash" ? flashContent() : null}
      {tab === "orders" ? <div className="min-h-0 flex-1 overflow-y-auto">{ordersContent()}</div> : null}
      {tab === "positions" ? (
        <div className="min-h-0 flex-1 overflow-y-auto">{positionsContent()}</div>
      ) : null}
    </aside>
  );
}
