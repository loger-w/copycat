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
import { VersionDriftBadge } from "@/components/VersionDriftBadge";
import { useBreadth } from "@/hooks/useBreadth";
import { useCapitalStream } from "@/hooks/useCapital";
import { useSignalAlerts } from "@/hooks/useSignalAlerts";
import { useFuturesStream } from "@/hooks/useFuturesStream";
import { useIndexStream } from "@/hooks/useIndexStream";
import { useStockStream } from "@/hooks/useStockStream";
import { useTxoSnapshot } from "@/hooks/useTxoSnapshot";
import {
  LEGACY_MAIN_CODE_KEY,
  MAIN_CODE_KEY,
  PRODUCT_KEY,
  purgeOrphanKeys,
  TAB_KEY,
} from "@/lib/constants";
import { futExchangeContract } from "@/lib/futures-ladder";
import type { StkfutSelection } from "@/lib/stkfut";
import { cn } from "@/lib/utils";

const StockPage = lazy(() => import("@/components/stock/StockPage"));
const FuturesPage = lazy(() => import("@/components/futures/FuturesPage"));
const IndexPage = lazy(() => import("@/components/index/IndexPage"));

type Tab = "txo" | "stock" | "futures" | "index";

const FUT_PRODUCTS = [
  ["TXF", "大台"],
  ["MXF", "小台"],
  ["TMF", "微台"],
] as const;
export type FutProduct = (typeof FUT_PRODUCTS)[number][0];

/** localStorage 值域**縮減一項**:`corr` 自台股綜合 R1(SC-1)起移出合法清單 ——
 *  相關係數併入台股綜合頁的收合區塊,舊值因此自然 fallback 到 `index`(刻意遷移,
 *  不寫搬移碼)。其餘舊值仍各自還原到對應 tab;「無值」時的 fallback 同樣是
 *  `index` —— 該頁自 index-board SC-1 起排第一顆。 */
function initialTab(): Tab {
  const saved = window.localStorage.getItem(TAB_KEY);
  return saved === "stock" || saved === "futures" || saved === "txo" ? saved : "index";
}

function initialProduct(): FutProduct {
  const saved = window.localStorage.getItem(PRODUCT_KEY);
  return saved === "MXF" || saved === "TMF" ? saved : "TXF";
}

/** 主圖標的初始值 + 舊 key 一次性遷移(`stock-main-code` → `copycat-stock-main-code`)。
 *
 *  新舊都有值時取**新**的:新 key 只可能由改版後的 code 寫入,必定較新。
 *  搬完就刪舊 key,所以整段對同一個瀏覽器只會實際搬一次(之後恆走第一條 return)。
 *
 *  寫入一律包 try/catch(同 `hooks/useChartToggles.ts` 的 `persist()` 慣例):本函式是
 *  `useState` 的 initializer,setItem 在 Safari 私密視窗 / storage 被政策鎖時會拋
 *  `QuotaExceededError`,拋出去就是首次 render 白畫面。這次沒落檔照樣回傳值,
 *  記憶體內的主圖標的正常;順序維持「setItem 成功後才 removeItem」不變。 */
function initialStockCode(): string | null {
  const current = window.localStorage.getItem(MAIN_CODE_KEY);
  if (current) {
    // 新舊同時有值也要清舊 key:雙分頁升版時舊 bundle 會把舊 key 寫回,
    // 新 bundle 每次啟動清一次才收斂(否則殘值永久留著)。
    try {
      window.localStorage.removeItem(LEGACY_MAIN_CODE_KEY);
    } catch {
      // 清不掉就算了 —— 新 key 已優先,舊值不影響行為
    }
    return current;
  }
  const legacy = window.localStorage.getItem(LEGACY_MAIN_CODE_KEY);
  if (!legacy) return null;
  try {
    window.localStorage.setItem(MAIN_CODE_KEY, legacy);
    window.localStorage.removeItem(LEGACY_MAIN_CODE_KEY);
  } catch {
    // 搬不動就下次再搬 —— 不落檔遠好於白畫面
  }
  return legacy;
}

purgeOrphanKeys();

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
  });
  // 主檔 / 期貨商品上提到 App(D-3):右欄常駐且內容跟隨當前 tab,資料留在頁面內就餵不到右欄
  const [stockCode, setStockCode] = useState<string | null>(initialStockCode);
  const [product, setProduct] = useState<FutProduct>(initialProduct);
  // 個股期合約選擇(stkfut-contracts D5):與 stockCode 同層 —— 資料流(useStockStream)、
  // 主圖(StockChart)、右欄(railCtx)三處都要吃同一份,放進 StockPage 就餵不到右欄。
  // **不持久化**:合約每月到期,存下來的月份重開後可能已不存在(訂閱零推播且無錯誤訊號)。
  const [stkfutContract, setStkfutContract] = useState<StkfutSelection | null>(null);
  // 換股重置。用 render 期間調整 state 的官方 pattern 而**不是** effect:effect 版本會
  // 先放行一個「新股號 + 舊合約」的 render,而 useStockStream 在那一拍就會送出
  // `/api/stock/state/2454?contract=CDF:202609` —— 後端 D7 白名單直接 400,畫面停在載入中。
  const [prevStockCode, setPrevStockCode] = useState(stockCode);
  if (prevStockCode !== stockCode) {
    setPrevStockCode(stockCode);
    setStkfutContract(null);
  }

  // 指數流常駐 App 層(SC-1:bar 跨 tab 可見)
  const { twse, otc, txf } = useIndexStream();
  // 家數 / 騰落流同樣常駐 App 層(design R8):IndexPage 維持純展示,tab 切走也不斷線
  // —— 序列是「當日累積」,切回來時要是完整的一整天,不是重新開始那一刻起。
  const breadth = useBreadth();
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
  const stockStream = useStockStream(
    tab === "stock" || visited.stock ? stockCode : null,
    stkfutContract,
  );
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
          // **恆為股號**(D5 口徑寫死):RightRail 的五檔點價 gate 比對 `detail.code === ctx.code`,
          // 而事件是主區的 OrderBook 以股號發的;塞 instrument key 會讓整條點價路徑靜默失效,
          // 下單面也會顯示 `F:CDF:202609`。合約走獨立欄。
          code: stockCode,
          contract: stkfutContract,
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
            ["index", "台股綜合"],
            ["stock", "個股(期)"],
            ["txo", "選擇權"],
            ["futures", "期貨"],
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
        {/* 一個 ml-auto 推到右側,兩個會平分剩餘空間把膠囊卡在 nav 中段(design R4);
            IndexBar 自身的 ml-auto 在這個內容尺寸容器內成為 no-op。 */}
        <div className="ml-auto flex items-baseline gap-3">
          <VersionDriftBadge />
          <IndexBar twse={twse} otc={otc} txf={txf} />
        </div>
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
                <StockPage
                  code={stockCode}
                  onSelect={setStockCode}
                  stream={stockStream}
                  contract={stkfutContract}
                  onContract={setStkfutContract}
                />
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
                  // 期現價差的現貨腿(SC-5);App 已持有,傳進去即可
                  twse={twse}
                  // tab 是 hidden 保留而非 unmount → 主圖的背景輪詢要靠這道 gate 停(LF-2)
                  active={tab === "futures"}
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
                  breadth={breadth}
                />
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
