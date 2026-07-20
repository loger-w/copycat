import { cn } from "@/lib/utils";
import type { WsStatus } from "@/hooks/useTxoSnapshot";

const WARN_TONE = "bg-bull/15 text-bull border-bull/40";
const DEFAULT_TONE = "bg-surface text-ink-muted border-line";

const STATUS: Record<string, { label: string; tone?: string }> = {
  connecting: { label: "連線中" },
  backfilling: { label: "回補中", tone: "bg-profit/15 text-profit border-profit/40" },
  live: { label: "即時連線中", tone: "bg-bear/15 text-bear border-bear/40" },
  reconnecting: { label: "重連中" },
  disconnected: { label: "已斷線", tone: WARN_TONE },
  degraded: { label: "資料降級", tone: WARN_TONE },
  replay: { label: "回放模式" },
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
    : (STATUS[status]?.label ?? status);
  const tone = broken ? WARN_TONE : (STATUS[status]?.tone ?? DEFAULT_TONE);
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
