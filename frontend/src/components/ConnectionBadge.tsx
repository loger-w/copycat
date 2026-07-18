import { cn } from "@/lib/utils";
import type { WsStatus } from "@/hooks/useTxoSnapshot";

const STATUS_LABEL: Record<string, string> = {
  connecting: "連線中",
  backfilling: "回補中",
  live: "即時連線中",
  reconnecting: "重連中",
  disconnected: "已斷線",
  degraded: "資料降級",
  replay: "回放模式",
};

const STATUS_TONE: Record<string, string> = {
  live: "bg-bear/15 text-bear border-bear/40",
  backfilling: "bg-profit/15 text-profit border-profit/40",
  degraded: "bg-bull/15 text-bull border-bull/40",
  disconnected: "bg-bull/15 text-bull border-bull/40",
};

export function ConnectionBadge({
  status,
  wsStatus,
}: {
  status: string;
  wsStatus: WsStatus;
}) {
  const broken = wsStatus !== "open";
  const label = broken
    ? wsStatus === "connecting"
      ? "連線中"
      : "連線中斷,重試中"
    : (STATUS_LABEL[status] ?? status);
  const tone = broken
    ? "bg-bull/15 text-bull border-bull/40"
    : (STATUS_TONE[status] ?? "bg-surface text-ink-muted border-line");
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 font-mono text-xs",
        tone,
      )}
    >
      <span className="inline-block size-1.5 rounded-full bg-current" aria-hidden />
      {label}
    </span>
  );
}
