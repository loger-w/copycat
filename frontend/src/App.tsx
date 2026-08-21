import { lazy, Suspense, useEffect, useMemo, useState, type KeyboardEvent } from "react";

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
import { useTradingCalendar } from "@/hooks/useTradingCalendar";
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
import { tablistKeyAction } from "@/lib/tablist-keys";
import { cn } from "@/lib/utils";

const StockPage = lazy(() => import("@/components/stock/StockPage"));
const FuturesPage = lazy(() => import("@/components/futures/FuturesPage"));
const IndexPage = lazy(() => import("@/components/index/IndexPage"));
const CorrPage = lazy(() => import("@/components/corr/CorrPage"));

type Tab = "txo" | "stock" | "futures" | "index" | "corr";

/** 主分頁列的內容(單一來源:tablist 與方向鍵導航都吃它)。原本是 JSX 內的行內字面量,
 *  抽出來是因為鍵盤導航要知道「共幾顆、第幾顆」。 */
const MAIN_TABS: readonly (readonly [Tab, string])[] = [
  ["index", "台股綜合"],
  ["stock", "個股(期)"],
  ["txo", "選擇權"],
  ["futures", "期貨"],
  ["corr", "相關係數"],
];

/** tab ↔ tabpanel 的 id 對(a11y 批 SC-2'')。App 是單例,固定字串即可。 */
const tabId = (id: Tab) => `app-tab-${id}`;
const panelId = (id: Tab) => `app-panel-${id}`;

const FUT_PRODUCTS = [
  ["TXF", "大台"],
  ["MXF", "小台"],
  ["TMF", "微台"],
] as const;
export type FutProduct = (typeof FUT_PRODUCTS)[number][0];

/** 無下單標的的右欄 context(TXO / 台股綜合 / 相關係數三顆 tab)。
 *
 *  **module 級單例**:寫成 inline `{ kind: "none" }` 的話 `railCtx` 每一輪 render 都是
 *  新 identity,`RightRail` 的 memo 形同不存在 —— 停在這三顆 tab 時右欄內容恆定,
 *  卻仍隨 App 的五條流(指數 ~1s / 廣度 / 個股報價批 1s / 期貨 0.1s / 訊號)整棵重繪。 */
const NONE_CTX: RailContext = { kind: "none" };

/** localStorage 值域**加回** `corr`(2026-08-16 R2 SC-1):相關係數升為第 5 顆頂層 tab。
 *  沿革:R1 曾把它併入台股綜合頁(先收合區塊、後 subtab),那段期間 `corr` 不在合法
 *  清單內、舊值一律 fallback 到 `index`;subtab 機制本輪退役後值域回到 R1 前的樣子,
 *  停在該值的瀏覽器重新還原到相關係數頁(D7 預期,零遷移碼)。其餘舊值仍各自還原到
 *  對應 tab;「無值」時的 fallback 是 `index` —— 該頁自 index-board SC-1 起排第一顆。 */
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
    corr: tab === "corr",
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

  // 交易日曆(mod/trading-calendar SC-9):**唯一**掛載點。消費端(lib/trading-hours 的
  // 三支函式)是模組級的,多掛幾份只是多打一次同一個端點;而少了這一支,國定假日整天
  // 每 60s 空打當日段(當日段恆空 → don't-cache-empty → 每次都真的走 TC4)。
  // 取數失敗 / 後端沒載日曆 = 空集合 = 只擋週末 = 改動前行為(W8),不擋 App 起站。
  useTradingCalendar();
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

  // 右欄內容跟隨當前 tab 標的,版面位置固定(D2)。
  //
  // **兩腿各自 useMemo + 模組常數 NONE_CTX**(refactor/memo-boundaries S1):本元件掛五條
  // 流,每則推播都重繪它;單一 inline 物件會讓 `railCtx` 每輪換 identity,期貨 10 Hz tick
  // 因此每秒把右欄閃電梯 subtree(全站最重的 render)重畫 10 次 —— 而使用者停在個股 /
  // 指數 / TXO 頁時,期貨腿與右欄顯示的東西毫無關係。拆成兩腿是為了讓「哪一條流該動
  // 右欄」在 deps 上就講清楚:期貨腿動 futuresCtx、個股腿動 stockCtx,互不牽連。
  //
  // deps 完整性**沒有 lint 守**(本 repo 無 eslint-plugin-react-hooks),守門是
  // `App.memo.test.tsx` 的計次 + 內容斷言:漏掉 `accum` 的樣態是右欄掛著舊五檔 / 舊成交價
  // (真錢面板),畫面與其他測試都不會有任何訊號。
  const stockCtx = useMemo<RailContext>(
    () => ({
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
    }),
    [stockCode, stkfutContract, accum],
  );
  // `futContract` 是 render body 內現算的,但型別是 `string | null`(primitive)→ 值沒變
  // 時 identity 也沒變,可以直接當 dep;`futProd` 則是期貨流每則推播的新物件,本來就該動。
  const futuresCtx = useMemo<RailContext>(
    () => ({ kind: "futures", product, state: futProd, contract: futContract }),
    [product, futProd, futContract],
  );
  const railCtx: RailContext =
    tab === "stock" ? stockCtx : tab === "futures" ? futuresCtx : NONE_CTX;

  /** manual activation(D3',與 RightRail 同一份判斷):方向鍵只移焦點,Enter / Space
   *  才切分頁。自動切換會讓方向鍵掃過的每一頁都真的掛載(lazy chunk + WS gate 全開)。 */
  function onTabKeyDown(e: KeyboardEvent<HTMLButtonElement>, id: Tab): void {
    const action = tablistKeyAction(e, MAIN_TABS.findIndex(([t]) => t === id), MAIN_TABS.length);
    if (action === null) return;
    e.preventDefault();
    if (action === "select") {
      setTab(id);
      return;
    }
    // `[role="tab"]` 而非所有子元素:nav 尾端還有版本膠囊 / 指數列
    const tabs = e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    tabs?.[action]?.focus();
  }

  return (
    <div className="flex h-full w-full flex-col gap-3 px-4 py-4">
      <nav className="flex items-baseline gap-1 border-b border-line" role="tablist" aria-label="主要分頁">
        {MAIN_TABS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={tabId(id)}
            // ⚠ stock / futures / corr 的 panel 受 `visited` 閘門延後 mount → 未造訪時
            // 這條 `aria-controls` 是 dangling(SC-2'' 明記的既定代價);index / txo 恆掛。
            aria-controls={panelId(id)}
            aria-selected={tab === id}
            // roving tabindex:整列只佔一個 tab stop,列內用方向鍵走
            tabIndex={tab === id ? 0 : -1}
            onKeyDown={(e) => onTabKeyDown(e, id)}
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
          <div
            role="tabpanel"
            id={panelId("txo")}
            aria-labelledby={tabId("txo")}
            hidden={tab !== "txo"}
            className={tab === "txo" ? "flex min-h-0 flex-1 flex-col gap-4" : ""}
          >
            <TxoPage />
          </div>
          {visited.stock ? (
            <div
              role="tabpanel"
              id={panelId("stock")}
              aria-labelledby={tabId("stock")}
              hidden={tab !== "stock"}
              className={tab === "stock" ? "flex min-h-0 flex-1 flex-col" : ""}
            >
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
            <div
              role="tabpanel"
              id={panelId("futures")}
              aria-labelledby={tabId("futures")}
              hidden={tab !== "futures"}
              className={tab === "futures" ? "flex min-h-0 flex-1 flex-col" : ""}
            >
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
            <div
              role="tabpanel"
              id={panelId("index")}
              aria-labelledby={tabId("index")}
              hidden={tab !== "index"}
              className={tab === "index" ? "flex min-h-0 flex-1 flex-col" : ""}
            >
              <Suspense
                fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
              >
                <IndexPage
                  twse={twse}
                  otc={otc}
                  txf={txf}
                  futures={futuresStream.state?.products ?? null}
                  breadth={breadth}
                  // R3 SC-5:漲跌停列表點列 → 切個股(期)。走既有 visited gate →
                  // StockPage mount → `/api/stock/state/{code}`(內含 set_main),
                  // 個股頁零改動。順序無所謂:兩個 setState 同批,tab 切換與主檔
                  // 一起生效。
                  onOpenStock={(code) => {
                    setStockCode(code);
                    setTab("stock");
                  }}
                  // tab 是 hidden 保留而非 unmount → 漲跌停列表的背景輪詢要靠這道
                  // gate 停(review FE-2;FuturesPage 的 active 同慣例)
                  active={tab === "index"}
                />
              </Suspense>
            </div>
          ) : null}
          {visited.corr ? (
            <div
              role="tabpanel"
              id={panelId("corr")}
              aria-labelledby={tabId("corr")}
              hidden={tab !== "corr"}
              className={tab === "corr" ? "flex min-h-0 flex-1 flex-col" : ""}
            >
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
