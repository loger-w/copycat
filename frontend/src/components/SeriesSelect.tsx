import { useSelectSeries, useSeries } from "@/hooks/useSeries";
import { cn } from "@/lib/utils";

export function SeriesSelect({ activeId }: { activeId: string | null }) {
  const { data: series, isLoading, error } = useSeries();
  const select = useSelectSeries();

  if (isLoading) {
    return <span className="text-xs text-ink-muted">序列載入中…</span>;
  }
  if (error) {
    return <span className="text-xs text-bull">序列載入失敗:{error.message}</span>;
  }
  return (
    <label className="inline-flex items-center gap-2 text-sm text-ink-muted">
      到期序列
      <select
        value={activeId ?? ""}
        disabled={select.isPending}
        onChange={(e) => select.mutate(e.target.value)}
        className={cn(
          "rounded-sm border border-line bg-bg-deep px-2.5 py-1.5 font-mono text-sm text-ink",
          "focus:border-accent focus:outline-none",
          select.isPending && "opacity-50",
        )}
      >
        {(series ?? []).map((s) => (
          <option key={s.series_id} value={s.series_id}>
            {s.name}
          </option>
        ))}
      </select>
      {select.error && <span className="text-xs text-bull">切換失敗:{select.error.message}</span>}
    </label>
  );
}
