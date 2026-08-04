import { lazy, Suspense, useEffect, useState } from "react";

import { ConnectionBadge } from "@/components/ConnectionBadge";
import { IndexBar } from "@/components/IndexBar";
import { MetricsBar } from "@/components/MetricsBar";
import { OrderPanel } from "@/components/OrderPanel";
import { PnlChart } from "@/components/PnlChart";
import { QuoteTable } from "@/components/QuoteTable";
import { RightRail, type RailContext } from "@/components/rail/RightRail";
import { SeriesSelect } from "@/components/SeriesSelect";
import { ToastStack } from "@/components/ToastStack";
import { useCapitalStream } from "@/hooks/useCapital";
import { useSignalAlerts } from "@/hooks/useSignalAlerts";
import { useFuturesStream } from "@/hooks/useFuturesStream";
import { useIndexStream } from "@/hooks/useIndexStream";
import { useStockStream } from "@/hooks/useStockStream";
import { useTxoSnapshot } from "@/hooks/useTxoSnapshot";
import { MAIN_CODE_KEY, PRODUCT_KEY, TAB_KEY } from "@/lib/constants";
import { futExchangeContract } from "@/lib/futures-ladder";
import { cn } from "@/lib/utils";

const StockPage = lazy(() => import("@/components/stock/StockPage"));
const FuturesPage = lazy(() => import("@/components/futures/FuturesPage"));
const IndexPage = lazy(() => import("@/components/index/IndexPage"));
const CorrPage = lazy(() => import("@/components/corr/CorrPage"));

type Tab = "txo" | "stock" | "futures" | "index" | "corr";

const FUT_PRODUCTS = [
  ["TXF", "大台"],
  ["MXF", "小台"],
  ["TMF", "微台"],
] as const;
export type FutProduct = (typeof FUT_PRODUCTS)[number][0];

/** localStorage 值域**不變**(五個舊值全數仍還原到對應 tab);只有「無值」時的 fallback
 *  由 `txo` 改 `index` —— 大盤自 index-board SC-1 起排第一顆。 */
function initialTab(): Tab {
  const saved = window.localStorage.getItem(TAB_KEY);
  return saved === "stock" || saved === "futures" || saved === "txo" || saved === "corr"
    ? saved
    : "index";
}

function initialProduct(): FutProduct {
  const saved = window.localStorage.getItem(PRODUCT_KEY);
  return saved === "MXF" || saved === "TMF" ? saved : "TXF";
}

export default function App() {
  const [tab, setTab] = useState<Tab>(initialTab);
  // 首次進入才 mount(lazy:重元件延後載入);之後 hidden 保留 DOM(§3 慣例)。
  // 注意:資料流已上提到本層(D-3),visited 只管元件載入時機,不再兼管 WS 建立。
  // index 改為恆 true(SC-1 起是預設頁);txo 維持恆 true —— TxoPage 本來就未受 visited
  // 閘門管制(直接 render),改成按需會連帶改變 TXO WS 的建立時機(白名單 W-2)。
  const [visited, setVisited] = useState<Record<Tab, boolean>>({
    index: true,
    txo: true,
    stock: tab === "stock",
    futures: tab === "futures",
    corr: tab === "corr",
  });
  // 主檔 / 期貨商品上提到 App(D-3):右欄常駐且內容跟隨當前 tab,資料留在頁面內就餵不到右欄
  const [stockCode, setStockCode] = useState<string | null>(
    () => window.localStorage.getItem(MAIN_CODE_KEY) || null,
  );
  const [product, setProduct] = useState<FutProduct>(initialProduct);

  // 指數流常駐 App 層(SC-1:bar 跨 tab 可見)
  const { twse, otc, txf } = useIndexStream();
  // capital 下單 WS 常駐 App 層:唯一連線 + 唯一 invalidate 接線(review B2/B4)
  useCapitalStream();
  // 訊號提示常駐 App 層(design §8.3):訊號涵蓋整個自選池,人在看期貨頁時個股鎖漲停
  // 一樣要跳出來 —— 掛在個股頁內就只有停在該 tab 時才收得到。**唯一**的 bus 訂閱點,
  // 多掛一份會重複發聲與重複桌面通知。
  const alerts = useSignalAlerts();
  // D-16:沒訪問過個股 tab 時傳 null —— /api/stock/state/{code} 內含 set_main,
  // 會觸發訂閱池變更 + 當日 tick 全量回補,不該只因開了 TXO 頁就發生。
  //
  // 取捨(review phase5 P2-3):`code=null` 只擋掉 set_main / 回補這條**有成本的**路徑,
  // 擋不掉 `/ws/stock` 連線本身(該 hook 的 WS effect deps 為 []);且 watchlist_quote 的
  // setState 現在落在 App 層 → 每秒一批側欄報價會重繪整棵樹。判定可接受:
  // (a) WS 連線本身輕,後端 stock engine 本就常駐訂閱整份 watchlist,與有無 client 無關;
  // (b) App 層本來就會因 useIndexStream 每則指數推播重繪,不是新增的重繪類別。
  // 若日後量測到掉幀,先做的是讓 useStockStream 吃 `enabled` 參數(與這裡同一個開關),
  // 而不是把資料流搬回頁面內 —— 右欄跟隨當前 tab 標的(D2)依賴資料在 App 層。
  const stockStream = useStockStream(tab === "stock" || visited.stock ? stockCode : null);
  const futuresStream = useFuturesStream();

  useEffect(() => {
    window.localStorage.setItem(TAB_KEY, tab);
    setVisited((prev) => (prev[tab] ? prev : { ...prev, [tab]: true }));
  }, [tab]);

  useEffect(() => {
    if (stockCode) window.localStorage.setItem(MAIN_CODE_KEY, stockCode);
  }, [stockCode]);

  useEffect(() => {
    window.localStorage.setItem(PRODUCT_KEY, product);
  }, [product]);

  const accum = stockStream.accum;
  const futProd = futuresStream.state?.products[product] ?? null;
  const resolvedYm = futProd?.resolved_contract ?? null;
  // futExchangeContract 對非 YYYYMM 會 throw。改動前它在 FuturesLadder 內(只炸期貨頁),
  // 移到 App render body 後未捕捉 = 壞掉的 resolved_contract 白屏整個 App(review P2-7)。
  // contract=null 已是 W-A6 的既有安全狀態(武裝鈕 disabled + 強制解除)。
  let futContract: string | null = null;
  if (resolvedYm !== null) {
    try {
      futContract = futExchangeContract(product, resolvedYm);
    } catch {
      futContract = null;
    }
  }

  // 右欄內容跟隨當前 tab 標的,版面位置固定(D2)
  const railCtx: RailContext =
    tab === "stock"
      ? {
          kind: "stock",
          code: stockCode,
          name: accum?.meta?.name ?? "",
          book: accum?.book ?? null,
          last: accum?.last ?? null,
          meta: accum?.meta ?? null,
        }
      : tab === "futures"
        ? { kind: "futures", product, state: futProd, contract: futContract }
        : { kind: "none" };

  return (
    <div className="flex h-full w-full flex-col gap-3 px-4 py-4">
      <nav className="flex items-baseline gap-1 border-b border-line" role="tablist" aria-label="主要分頁">
        {(
          [
            ["index", "大盤"],
            ["stock", "個股(期)"],
            ["txo", "選擇權"],
            ["futures", "期貨"],
            ["corr", "相關係數"],
          ] as [Tab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              "rounded-t px-3 py-1.5 text-sm",
              tab === id ? "border border-b-0 border-line bg-surface text-ink" : "text-ink-dim hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
        <IndexBar twse={twse} otc={otc} txf={txf} />
      </nav>
      {/* 主區 + 常駐右欄(SC-3:切 tab 時右欄位置 / 寬度 / 三顆 tab 都不變) */}
      <div className="flex min-h-0 min-w-0 flex-1 gap-4">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div hidden={tab !== "txo"} className={tab === "txo" ? "flex min-h-0 flex-1 flex-col gap-4" : ""}>
            <TxoPage />
          </div>
          {visited.stock ? (
            <div hidden={tab !== "stock"} className={tab === "stock" ? "flex min-h-0 flex-1 flex-col" : ""}>
              <Suspense
                fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
              >
                <StockPage code={stockCode} onSelect={setStockCode} stream={stockStream} />
              </Suspense>
            </div>
          ) : null}
          {visited.futures ? (
            <div hidden={tab !== "futures"} className={tab === "futures" ? "flex min-h-0 flex-1 flex-col" : ""}>
              <Suspense
                fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
              >
                <FuturesPage
                  products={FUT_PRODUCTS}
                  product={product}
                  onProduct={(p) => setProduct(p as FutProduct)}
                  state={futProd}
                  resolvedYm={resolvedYm}
                  wsStatus={futuresStream.wsStatus}
                />
              </Suspense>
            </div>
          ) : null}
          {visited.index ? (
            <div hidden={tab !== "index"} className={tab === "index" ? "flex min-h-0 flex-1 flex-col" : ""}>
              <Suspense
                fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
              >
                <IndexPage
                  twse={twse}
                  otc={otc}
                  txf={txf}
                  futures={futuresStream.state?.products ?? null}
                />
              </Suspense>
            </div>
          ) : null}
          {visited.corr ? (
            <div hidden={tab !== "corr"} className={tab === "corr" ? "flex min-h-0 flex-1 flex-col" : ""}>
              <Suspense
                fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
              >
                <CorrPage />
              </Suspense>
            </div>
          ) : null}
        </div>
        <RightRail ctx={railCtx} />
      </div>
      {/* fixed 定位 → 不受上面 tab 的 hidden 影響,放在版面樹尾端只是為了疊在最上層 */}
      <ToastStack toasts={alerts.toasts} overflow={alerts.overflow} onDismiss={alerts.dismiss} />
    </div>
  );
}

function TxoPage() {
  const { data: snapshot, wsStatus } = useTxoSnapshot();

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-bold tracking-wide text-ink">
            台指選擇權<span className="text-profit">全市場綜合損益</span>
          </h1>
          <span className="font-mono text-xs text-ink-dim">
            {snapshot?.series_name ?? snapshot?.series_id ?? ""}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <SeriesSelect activeId={snapshot?.series_id ?? null} />
          <ConnectionBadge status={snapshot?.status ?? "connecting"} wsStatus={wsStatus} />
        </div>
      </header>

      {snapshot ? (
        <>
          <MetricsBar snapshot={snapshot} />
          <PnlChart snapshot={snapshot} />
          <QuoteTable
            contracts={snapshot.contracts}
            spotPrice={snapshot.spot?.price ?? null}
          />
          <OrderPanel contracts={snapshot.contracts} />
          <footer className="flex justify-between font-mono text-xs text-ink-dim">
            <span>
              tick {snapshot.totals?.ticks ?? 0} · 未分類 {snapshot.totals?.unclassified_ticks ?? 0}
              {snapshot.totals?.queue_dropped ? ` · 佇列丟棄 ${snapshot.totals.queue_dropped}` : ""}
            </span>
            <span>更新 {snapshot.generated_at ?? "-"}</span>
          </footer>
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-ink-muted">等待伺服器連線…</p>
        </div>
      )}
    </div>
  );
}
