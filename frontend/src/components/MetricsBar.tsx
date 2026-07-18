import { formatNtd, formatPts } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Snapshot } from "@/types";

const DASH = "—";

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "bull" | "bear" | "profit" | "accent";
}) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 border-l-2 border-line pl-3">
      <span className="truncate text-xs text-ink-muted">{label}</span>
      <span
        className={cn(
          "truncate font-mono text-base font-medium",
          tone === "bull" && "text-bull",
          tone === "bear" && "text-bear",
          tone === "profit" && "text-profit",
          tone === "accent" && "text-accent",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function pnlTone(v: number | null | undefined): "bull" | "bear" | undefined {
  if (v == null || v === 0) return undefined;
  return v > 0 ? "bull" : "bear";
}

export function MetricsBar({ snapshot }: { snapshot: Snapshot }) {
  const t = snapshot.totals;
  const coverage =
    t && t.ticks > 0 ? `${(((t.ticks - t.unclassified_ticks) / t.ticks) * 100).toFixed(1)}%` : DASH;
  return (
    <section
      aria-label="關鍵指標"
      className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-5"
    >
      <Metric
        label="全市場最大獲利"
        value={snapshot.max_profit ? formatNtd(snapshot.max_profit.y) : DASH}
        tone="bull"
      />
      <Metric
        label="全市場最大虧損"
        value={snapshot.max_loss ? formatNtd(snapshot.max_loss.y) : DASH}
        tone="bear"
      />
      <Metric
        label="損益兩平點"
        value={
          snapshot.beps && snapshot.beps.length > 0
            ? snapshot.beps.map(formatPts).join(" / ")
            : DASH
        }
        tone="profit"
      />
      <Metric
        label="標的現價"
        value={snapshot.spot?.price != null ? formatPts(snapshot.spot.price) : DASH}
        tone="accent"
      />
      <Metric
        label="現價到期預估"
        value={snapshot.spot_pnl != null ? formatNtd(snapshot.spot_pnl) : DASH}
        tone={pnlTone(snapshot.spot_pnl)}
      />
      <Metric
        label="Call 淨口數"
        value={t ? formatPts(t.call_net_qty) : DASH}
        tone={pnlTone(t?.call_net_qty)}
      />
      <Metric
        label="Put 淨口數"
        value={t ? formatPts(t.put_net_qty) : DASH}
        tone={pnlTone(t?.put_net_qty)}
      />
      <Metric label="參與合約數" value={t ? String(t.contracts_active) : DASH} />
      <Metric label="分類覆蓋率" value={coverage} />
    </section>
  );
}
