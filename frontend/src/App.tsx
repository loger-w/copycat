import { ConnectionBadge } from "@/components/ConnectionBadge";
import { MetricsBar } from "@/components/MetricsBar";
import { OrderPanel } from "@/components/OrderPanel";
import { PnlChart } from "@/components/PnlChart";
import { QuoteTable } from "@/components/QuoteTable";
import { SeriesSelect } from "@/components/SeriesSelect";
import { useTxoSnapshot } from "@/hooks/useTxoSnapshot";

export default function App() {
  const { data: snapshot, wsStatus } = useTxoSnapshot();

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-4 px-4 py-5">
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
          <OrderPanel />
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
