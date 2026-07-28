import { lazy, Suspense, useEffect, useState } from "react";

import { ConnectionBadge } from "@/components/ConnectionBadge";
import { IndexBar } from "@/components/IndexBar";
import { MetricsBar } from "@/components/MetricsBar";
import { OrderPanel } from "@/components/OrderPanel";
import { PnlChart } from "@/components/PnlChart";
import { QuoteTable } from "@/components/QuoteTable";
import { SeriesSelect } from "@/components/SeriesSelect";
import { useCapitalStream } from "@/hooks/useCapital";
import { useIndexStream } from "@/hooks/useIndexStream";
import { useTxoSnapshot } from "@/hooks/useTxoSnapshot";
import { cn } from "@/lib/utils";

const StockPage = lazy(() => import("@/components/stock/StockPage"));
const FuturesPage = lazy(() => import("@/components/futures/FuturesPage"));
const IndexPage = lazy(() => import("@/components/index/IndexPage"));

type Tab = "txo" | "stock" | "futures" | "index";
const TAB_KEY = "copycat-tab";

function initialTab(): Tab {
  const saved = window.localStorage.getItem(TAB_KEY);
  return saved === "stock" || saved === "futures" || saved === "index" ? saved : "txo";
}

export default function App() {
  const [tab, setTab] = useState<Tab>(initialTab);
  // 首次進入才 mount(lazy + WS 延後建立);之後 hidden 保留 DOM(§3 慣例)
  const [visited, setVisited] = useState<Record<Tab, boolean>>({
    txo: true,
    stock: tab === "stock",
    futures: tab === "futures",
    index: tab === "index",
  });
  // 指數流常駐 App 層(SC-1:bar 跨 tab 可見)
  const { twse, otc, txf } = useIndexStream();
  // capital 下單 WS 常駐 App 層:唯一連線 + 唯一 invalidate 接線(review B2/B4)
  useCapitalStream();

  useEffect(() => {
    window.localStorage.setItem(TAB_KEY, tab);
    setVisited((prev) => (prev[tab] ? prev : { ...prev, [tab]: true }));
  }, [tab]);

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-4 px-4 py-5">
      <nav className="flex items-baseline gap-1 border-b border-line" role="tablist">
        {(
          [
            ["txo", "TXO 綜合損益"],
            ["stock", "個股"],
            ["futures", "期貨"],
            ["index", "指數"],
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
      <div hidden={tab !== "txo"} className={tab === "txo" ? "flex flex-1 flex-col gap-4" : ""}>
        <TxoPage />
      </div>
      {visited.stock ? (
        <div hidden={tab !== "stock"} className={tab === "stock" ? "flex flex-1 flex-col" : ""}>
          <Suspense
            fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
          >
            <StockPage />
          </Suspense>
        </div>
      ) : null}
      {visited.futures ? (
        <div hidden={tab !== "futures"} className={tab === "futures" ? "flex flex-1 flex-col" : ""}>
          <Suspense
            fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
          >
            <FuturesPage />
          </Suspense>
        </div>
      ) : null}
      {visited.index ? (
        <div hidden={tab !== "index"} className={tab === "index" ? "flex flex-1 flex-col" : ""}>
          <Suspense
            fallback={<p className="py-10 text-center text-sm text-ink-muted">載入中…</p>}
          >
            <IndexPage twse={twse} otc={otc} txf={txf} />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}

function TxoPage() {
  const { data: snapshot, wsStatus } = useTxoSnapshot();

  return (
    <div className="flex flex-1 flex-col gap-4">
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
